"""Parametre taraması ve duyarlılık analizi.

İki tür duyarlılık:

* Yerel: log-log türev  S = d ln(y) / d ln(theta), merkezi farkla.
  Yorum: "theta %1 artarsa y yaklaşık %S artar." Ölçekten bağımsız
  olduğu için farklı birimlerdeki parametreler doğrudan kıyaslanabilir.

* Küresel: Latin hiperküp örneklemesi + sıra (rank) dönüşümlü regresyon.
  SRRC (standardized rank regression coefficient) monoton modeller için
  standart bir küresel duyarlılık ölçüsüdür; birlikte raporlanan R^2,
  sıra-doğrusal yaklaşımın ne kadar yeterli olduğunu söyler. R^2 düşükse
  model o bölgede güçlü etkileşimlidir ve SRRC'ler tek başına yanıltır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

from .kinetics import residence_analysis
from .model import System, apparent_kd
from .tether import wlc


# --------------------------------------------------------------------------
# Parametre tutamakları
# --------------------------------------------------------------------------


@dataclass
class Param:
    """Bir sistem parametresine okuma/yazma tutamağı."""

    name: str
    get: Callable[[System], float]
    set: Callable[[System, float], None]
    invalidates_geometry: bool = False

    def apply(self, sysm: System, value: float) -> None:
        self.set(sysm, value)
        if self.invalidates_geometry:
            sysm._grids.clear()
            sysm._geom.clear()


def kd(i: int) -> Param:
    return Param(
        f"KD[{i}]",
        lambda s: s.cassette.domains[i].kd,
        lambda s, v: setattr(s.cassette.domains[i], "kd", v),
    )


def k_on(i: int) -> Param:
    return Param(
        f"kon[{i}]",
        lambda s: s.cassette.domains[i].k_on,
        lambda s, v: setattr(s.cassette.domains[i], "k_on", v),
    )


def density(i: int) -> Param:
    return Param(
        f"sigma[{i}]",
        lambda s: s.surface.receptors[i].density,
        lambda s, v: setattr(s.surface.receptors[i], "density", v),
    )


def height(i: int) -> Param:
    return Param(
        f"z[{i}]",
        lambda s: s.surface.receptors[i].height,
        lambda s, v: setattr(s.surface.receptors[i], "height", v),
        invalidates_geometry=True,
    )


def linker_contour(m: int, persistence: float = 0.5) -> Param:
    """m'inci linkerin kontur uzunluğu [nm]; sabit persistans uzunluğuyla."""
    return Param(
        f"Lc[link{m}]",
        lambda s: s.cassette.linkers[m].contour,
        lambda s, v: s.cassette.linkers.__setitem__(m, wlc(max(v, 1e-3), persistence)),
        invalidates_geometry=True,
    )


def persistence_length(m: int) -> Param:
    """m'inci linkerin persistans uzunluğu [nm]; kontur sabit tutulur."""

    def _set(s: System, v: float) -> None:
        Lc = s.cassette.linkers[m].contour
        s.cassette.linkers[m] = wlc(Lc, max(v, 1e-3))

    def _get(s: System) -> float:
        ch = s.cassette.linkers[m]
        return ch.msq / (2.0 * ch.contour)  # 2 lp Lc yaklaşımının tersi

    return Param(f"lp[link{m}]", _get, _set, invalidates_geometry=True)


def domain_span(i: int) -> Param:
    return Param(
        f"span[{i}]",
        lambda s: s.cassette.domains[i].span,
        lambda s, v: setattr(s.cassette.domains[i], "span", v),
        invalidates_geometry=True,
    )


def steric(i: int, j: int) -> Param:
    key = (min(i, j), max(i, j))
    return Param(
        f"chi{key}",
        lambda s: s.surface.steric.get(key, 1.0),
        lambda s, v: s.surface.steric.__setitem__(key, v),
        invalidates_geometry=True,
    )


# --------------------------------------------------------------------------
# Gözlenebilirler
# --------------------------------------------------------------------------

Observable = Callable[[System, float], float]


def obs_total(s: System, c: float) -> float:
    return s.solve(c).total


def obs_p_all(s: System, c: float) -> float:
    return s.solve(c).p_state(range(s.n))


def obs_p_at_least(k: int) -> Observable:
    return lambda s, c: s.solve(c).p_at_least(k)


def obs_density_all_bound(s: System, c: float) -> float:
    eq = s.solve(c)
    return eq.p_state(range(s.n)) * eq.total


def obs_mean_valency(s: System, c: float) -> float:
    return s.solve(c).mean_valency()


def obs_residence(s: System, c: float) -> float:
    return residence_analysis(s.solve(c)).tau_entry


def obs_ec50(s: System, c: float) -> float:
    return apparent_kd(s)["ec50"]


# --------------------------------------------------------------------------
# Yerel duyarlılık
# --------------------------------------------------------------------------


def _with_value(sysm: System, p: Param, v: float, fn):
    old = p.get(sysm)
    try:
        p.apply(sysm, v)
        return fn()
    finally:
        p.apply(sysm, old)


def log_sensitivity(
    sysm: System,
    conc: float,
    observable: Observable,
    params: Sequence[Param],
    rel_step: float = 0.02,
) -> dict[str, float]:
    """d ln(y) / d ln(theta), her parametre için merkezi farkla."""
    out: dict[str, float] = {}
    for p in params:
        theta = p.get(sysm)
        if theta == 0 or not np.isfinite(theta):
            out[p.name] = np.nan
            continue
        hi = _with_value(sysm, p, theta * (1 + rel_step), lambda: observable(sysm, conc))
        lo = _with_value(sysm, p, theta * (1 - rel_step), lambda: observable(sysm, conc))
        if hi <= 0 or lo <= 0:
            out[p.name] = np.nan
        else:
            out[p.name] = float((np.log(hi) - np.log(lo)) / (2 * np.log1p(rel_step)))
    return out


# --------------------------------------------------------------------------
# Izgara taramaları
# --------------------------------------------------------------------------


def sweep_1d(
    sysm: System, conc: float, observable: Observable, p: Param, values: Sequence[float]
) -> np.ndarray:
    return np.array(
        [_with_value(sysm, p, float(v), lambda: observable(sysm, conc)) for v in values]
    )


def sweep_2d(
    sysm: System,
    conc: float,
    observable: Observable,
    p1: Param,
    v1: Sequence[float],
    p2: Param,
    v2: Sequence[float],
) -> np.ndarray:
    """shape (len(v1), len(v2)) ızgara."""
    out = np.empty((len(v1), len(v2)))
    for a, x in enumerate(v1):
        for b, y in enumerate(v2):
            out[a, b] = _with_value(
                sysm,
                p1,
                float(x),
                lambda: _with_value(sysm, p2, float(y), lambda: observable(sysm, conc)),
            )
    return out


# --------------------------------------------------------------------------
# Küresel duyarlılık
# --------------------------------------------------------------------------


def latin_hypercube(n: int, d: int, rng: np.random.Generator) -> np.ndarray:
    """(n, d) LHS örneklemi, [0,1)^d üzerinde."""
    cut = (np.arange(n)[:, None] + rng.random((n, d))) / n
    for j in range(d):
        rng.shuffle(cut[:, j])
    return cut


def global_sensitivity(
    sysm: System,
    conc: float,
    observable: Observable,
    ranges: dict[Param, tuple[float, float]],
    n_samples: int = 256,
    seed: int = 0,
) -> dict:
    """LHS + sıra-regresyonu ile küresel duyarlılık.

    ``ranges``: Param -> (alt, üst). Log ölçekte örneklenir (hepsi pozitif
    olmalı). Döndürülen SRRC'ler sıra-dönüşümlü standartlaştırılmış
    regresyon katsayılarıdır; ``r2`` düşükse (< ~0.7) model o bölgede
    monoton-doğrusal değildir ve SRRC yorumu zayıflar.
    """
    ps = list(ranges.keys())
    lohi = np.array([ranges[p] for p in ps], dtype=float)
    if np.any(lohi <= 0):
        raise ValueError("log örnekleme için tüm sınırlar pozitif olmalı")

    rng = np.random.default_rng(seed)
    u = latin_hypercube(n_samples, len(ps), rng)
    logs = np.log(lohi)
    X = np.exp(logs[:, 0] + u * (logs[:, 1] - logs[:, 0]))

    originals = [p.get(sysm) for p in ps]
    y = np.empty(n_samples)
    try:
        for m in range(n_samples):
            for p, v in zip(ps, X[m]):
                p.set(sysm, float(v))
            sysm._grids.clear()
            sysm._geom.clear()
            try:
                y[m] = observable(sysm, conc)
            except Exception:
                y[m] = np.nan
    finally:
        for p, v in zip(ps, originals):
            p.set(sysm, v)
        sysm._grids.clear()
        sysm._geom.clear()

    ok = np.isfinite(y) & (y > 0)
    if ok.sum() < len(ps) + 5:
        raise RuntimeError(f"yeterli geçerli örnek yok ({ok.sum()}/{n_samples})")

    def ranks(a: np.ndarray) -> np.ndarray:
        order = np.argsort(a)
        r = np.empty(len(a))
        r[order] = np.arange(len(a), dtype=float)
        return r

    R = np.column_stack([ranks(X[ok, j]) for j in range(len(ps))])
    ry = ranks(y[ok])
    Rz = (R - R.mean(0)) / R.std(0)
    yz = (ry - ry.mean()) / ry.std()
    beta, *_ = np.linalg.lstsq(Rz, yz, rcond=None)
    r2 = 1.0 - np.sum((yz - Rz @ beta) ** 2) / np.sum(yz**2)

    return {
        "params": [p.name for p in ps],
        "srrc": dict(zip((p.name for p in ps), beta)),
        "r2": float(r2),
        "n_valid": int(ok.sum()),
        "samples": X[ok],
        "y": y[ok],
    }
