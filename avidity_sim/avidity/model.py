"""Çok-değerlikli bağlanmanın denge state-space modeli.

Kurulum
-------
n adet bağlayıcı domain'i tek bir doğrusal kaset üzerinde taşıyan bir
ligand, üzerinde n tür reseptör bulunan bir yüzeyle etkileşiyor. Domain i
yalnızca reseptör i'yi tanıyor; monovalent ayrışma sabiti K_i.

Durum (state) = bağlı domain'lerin alt kümesi  S subset {0,...,n-1}.
Toplam 2^n durum.

Ağırlıklar
----------
Referans durum: ligand çözeltide serbest, derişim [L].

Bir durumun istatistiksel ağırlığı, "çapa" (ilk bağ, 3B ikimoleküler) ve
"kapanış" bağları (tether'ın dayattığı etkin yerel derişimle, tek
moleküler) ayrıştırılarak yazılır. S = (s_0 < s_1 < ... < s_{m-1}) için

    w(S) = ([L] / K_{s0}) * sigma_free[s0]
             * prod_{k=0}^{m-2}  c_eff(s_k, s_{k+1}) / K_{s_{k+1}}

Birim: nm^-2, yani "bu durumda olan ligandların yüzey yoğunluğu".

Neden ardışık çiftlerin çarpımı?
--------------------------------
Doğrusal ideal zincir Markov'dur: domain konumları kontur boyunca bir
Markov zinciri oluşturur. Dolayısıyla S içindeki domain'lerin ortak
konum yoğunluğu, S'deki *ardışık* çiftlerin geçiş çekirdeklerinin
çarpımına ayrışır. Örneğin S={0,2} için 1 numaralı domain serbesttir ve
marjinalleştirilir: 0-2 tether'ı linker0 + domain1 + linker1'dir.

Bu yapının kritik sonucu: w(S) hangi bağın önce kurulduğuna bağlı
DEĞİLDİR. Termodinamik yol-bağımsızlığı modelde kimliksel olarak
sağlanır (bkz. tests/test_core.py::test_path_independence); elle
dayatılan bir kısıt değildir.

Etkin yerel derişim
-------------------
İki modu vardır:

* ``"disordered"`` -- reseptörler bir düzlemde sürekli, yoğunluk
  sigma_j [nm^-2]. Domain s_k bağlıyken domain s_{k+1}'in gördüğü etkin
  derişim, tether'ın düzlemsel erişimi ile yoğunluğun çarpımıdır:

      c_eff(i,j) = kappa * sigma_free[j] * A_ij(dz_ij) * chi_ij

  kappa = 1.6605 M nm^3 (nm^-3 -> M), A_ij tether.TetherGrid'den,
  dz_ij = |z_i - z_j| epitop yükseklik farkı, chi_ij kullanıcı tanımlı
  sterik erişim faktörü (varsayılan 1).

* ``"fixed"`` -- reseptörler bilinen konumlarda (tek bir hedef kompleks
  ya da tasarlanmış bir yüzey deseni). Bu durumda

      c_eff(i,j) = kappa * P_ij(d_ij) * chi_ij

  ve w(S) boyutsuzdur: tek bir kompleksin doluluk oranı (odds).

Doygunluk
---------
Serbest reseptör yoğunlukları öz-uyumlu çözülür:

    sigma_free[i] = sigma_tot[i] - sum_{S ni i} rho(S)

Ayrıca isteğe bağlı ligand ayak-izi dışlaması: tüm ağırlıklar
(1 - a_L * rho_tot)_+ ile çarpılır (birinci mertebe Langmuir düzeltmesi).

Fizibilite
----------
``feasibility(S) -> bool`` geri çağrısı verilirse, False dönen
durumların ağırlığı sıfırlanır. Not: kontur sınırı zaten fizikten
geliyor (tether kontur uzunluğundan uzak reseptörler için A -> 0), bu
kanca onun dışındaki kısıtlar içindir.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

import numpy as np

from .constants import NM3_TO_MOLAR
from .tether import Chain, Rod, TetherGrid

State = tuple[int, ...]


# --------------------------------------------------------------------------
# Bileşenler
# --------------------------------------------------------------------------


@dataclass
class Domain:
    """Kasetteki tek bir bağlayıcı domain."""

    name: str
    kd: float
    """Monovalent ayrışma sabiti [M]. np.inf = bu domain bağlanamaz."""
    k_on: float = 1e5
    """İkimoleküler birleşme hız sabiti [1/(M s)]; k_off = kd * k_on."""
    span: float = 2.5
    """Domain'i kontur boyunca geçerken kat edilen rijit mesafe [nm]."""
    site_offset: float = 0.0
    """Ana zincirden epitop temas noktasına rijit sapma [nm]."""

    @property
    def k_off(self) -> float:
        return self.kd * self.k_on


@dataclass
class Receptor:
    """Yüzeydeki hedef."""

    name: str
    density: float = 0.0
    """Toplam yüzey yoğunluğu [nm^-2]. ``"disordered"`` modunda kullanılır."""
    height: float = 0.0
    """Epitopun membran düzlemi üstündeki yüksekliği [nm]."""
    position: tuple[float, float, float] | None = None
    """``"fixed"`` modunda epitopun 3B konumu [nm]."""


@dataclass
class Cassette:
    """Doğrusal domain kaseti:  D0 -L0- D1 -L1- D2 ..."""

    domains: list[Domain]
    linkers: list[Chain]
    """len(linkers) == len(domains) - 1."""

    def __post_init__(self) -> None:
        if len(self.linkers) != len(self.domains) - 1:
            raise ValueError(
                f"{len(self.domains)} domain için {len(self.domains)-1} linker gerekir, "
                f"{len(self.linkers)} verildi"
            )

    @property
    def n(self) -> int:
        return len(self.domains)

    def tether(self, i: int, j: int) -> Chain:
        """i ve j epitop temas noktaları arasındaki zincir (i < j).

        Aradaki bağlı-olmayan domain'ler rijit çubuk olarak dâhil edilir;
        konfigürasyonel olarak marjinalleştirilmiş olurlar.
        """
        if i >= j:
            i, j = j, i
        parts: list = []
        off_i = self.domains[i].site_offset
        if off_i > 0:
            parts.append(Rod(off_i))
        for m in range(i, j):
            parts.append(self.linkers[m])
            if m + 1 < j:
                span = self.domains[m + 1].span
                if span > 0:
                    parts.append(Rod(span))
        off_j = self.domains[j].site_offset
        if off_j > 0:
            parts.append(Rod(off_j))
        return Chain.of(*parts)


@dataclass
class Surface:
    """Reseptör bağlamı."""

    receptors: list[Receptor]
    mode: str = "disordered"
    """``"disordered"`` veya ``"fixed"``."""
    steric: dict[tuple[int, int], float] = field(default_factory=dict)
    """(i,j) -> chi_ij sterik erişim faktörü, varsayılan 1.0."""
    ligand_footprint: float = 0.0
    """Ligand ayak izi alanı [nm^2]; 0 = dışlama yok."""

    def chi(self, i: int, j: int) -> float:
        key = (min(i, j), max(i, j))
        return self.steric.get(key, 1.0)

    def separation(self, i: int, j: int) -> float:
        pi, pj = self.receptors[i].position, self.receptors[j].position
        if pi is None or pj is None:
            raise ValueError("'fixed' modu için Receptor.position gerekli")
        return float(np.linalg.norm(np.asarray(pi) - np.asarray(pj)))

    def dz(self, i: int, j: int) -> float:
        return abs(self.receptors[i].height - self.receptors[j].height)


# --------------------------------------------------------------------------
# Sistem
# --------------------------------------------------------------------------


def all_states(n: int) -> list[State]:
    """Tüm 2^n alt kümeler, boş kümeden tam kümeye, artan büyüklükte."""
    out: list[State] = []
    for m in range(n + 1):
        out.extend(itertools.combinations(range(n), m))
    return out


@dataclass
class System:
    """Kaset + yüzey; tether tabloları önbelleklenir."""

    cassette: Cassette
    surface: Surface
    eps: float = 0.25
    """Tether tablolarının çözünürlük uzunluğu [nm]."""
    feasibility: Callable[[State], bool] | None = None
    n_grid: int = 2**13 + 1

    def __post_init__(self) -> None:
        if len(self.surface.receptors) != self.cassette.n:
            raise ValueError("reseptör sayısı domain sayısına eşit olmalı")
        self._grids: dict[tuple[int, int], TetherGrid] = {}
        self._geom: dict[tuple[int, int], float] = {}
        self.states: list[State] = all_states(self.cassette.n)
        self.state_index: dict[State, int] = {S: i for i, S in enumerate(self.states)}

    @property
    def n(self) -> int:
        return self.cassette.n

    def grid(self, i: int, j: int) -> TetherGrid:
        key = (min(i, j), max(i, j))
        if key not in self._grids:
            self._grids[key] = TetherGrid(
                self.cassette.tether(*key), eps=self.eps, n_grid=self.n_grid
            )
        return self._grids[key]

    # --- etkin yerel derişim ---------------------------------------------

    def geom_factor(self, i: int, j: int) -> float:
        """Etkin derişimin reseptör-yoğunluğundan bağımsız geometrik kısmı.

        ``"disordered"``:  G_ij = kappa * A_ij(dz) * chi_ij   [M nm^2]
                           c_eff(i,j) = G_ij * sigma_free[j]
        ``"fixed"``:       G_ij = kappa * P_ij(d_ij) * chi_ij [M]
                           c_eff(i,j) = G_ij
        """
        key = (min(i, j), max(i, j))
        if key not in self._geom:
            chi = self.surface.chi(i, j)
            g = self.grid(i, j)
            if self.surface.mode == "disordered":
                val = NM3_TO_MOLAR * float(g.areal_reach(self.surface.dz(i, j))) * chi
            elif self.surface.mode == "fixed":
                val = NM3_TO_MOLAR * float(g.radial_density(self.surface.separation(i, j))) * chi
            else:
                raise ValueError(f"bilinmeyen mod: {self.surface.mode}")
            self._geom[key] = val
        return self._geom[key]

    def c_eff(self, i: int, j: int, sigma_free: np.ndarray) -> float:
        """Domain i bağlıyken domain j'nin gördüğü etkin derişim [M]."""
        g = self.geom_factor(i, j)
        return g * sigma_free[j] if self.surface.mode == "disordered" else g

    def reach_summary(self) -> list[dict]:
        """Her domain çifti için tether geometrisinin özeti (teşhis)."""
        rows = []
        for i, j in itertools.combinations(range(self.n), 2):
            ch = self.cassette.tether(i, j)
            g = self.grid(i, j)
            dz = self.surface.dz(i, j)
            row = {
                "pair": (i, j),
                "contour_nm": ch.contour,
                "rms_nm": ch.rms,
                "dz_nm": dz,
                "areal_reach_per_nm": float(g.areal_reach(dz)),
                "chi": self.surface.chi(i, j),
            }
            if self.surface.mode == "fixed":
                d = self.surface.separation(i, j)
                row["separation_nm"] = d
                row["P_d_per_nm3"] = float(g.radial_density(d))
                row["reachable"] = d < ch.contour
            rows.append(row)
        return rows

    # --- durum ağırlıkları -------------------------------------------------

    def _raw_weights(self, conc: float, sigma_free: np.ndarray) -> np.ndarray:
        """Doygunluk düzeltmesi uygulanmadan w(S)."""
        kd = np.array([d.kd for d in self.cassette.domains])
        w = np.zeros(len(self.states))
        for idx, S in enumerate(self.states):
            if not S:
                continue
            if self.feasibility is not None and not self.feasibility(S):
                continue
            if any(not np.isfinite(kd[i]) for i in S):
                continue
            anchor = S[0]
            if self.surface.mode == "disordered":
                val = (conc / kd[anchor]) * sigma_free[anchor]
            else:
                val = conc / kd[anchor]
            ok = True
            for a, b in zip(S, S[1:]):
                ce = self.c_eff(a, b, sigma_free)
                if ce <= 0.0:
                    ok = False
                    break
                val *= ce / kd[b]
            w[idx] = val if ok else 0.0
        return w

    # --- öz-uyumlu çözüm ---------------------------------------------------

    def weights_and_bound(
        self, conc: float, sigma_free: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Verilen serbest yoğunluklarda w(S) ve reseptör başına bağlı miktar.

        Ligand ayak-izi dışlaması öz-uyumlu Langmuir formunda uygulanır:
        rho_tot = W / (1 + a_L W), W = düzeltilmemiş toplam. Bu, kırpma
        gerektirmez ve her zaman rho_tot < 1/a_L verir.
        """
        w = self._raw_weights(conc, sigma_free)
        a = self.surface.ligand_footprint
        if a > 0:
            W = float(w.sum())
            w = w / (1.0 + a * W)
        bound = np.zeros(self.n)
        for idx, S in enumerate(self.states):
            if w[idx] > 0.0:
                for i in S:
                    bound[i] += w[idx]
        return w, bound

    def coefficients(self, conc: float) -> np.ndarray:
        """Çok-doğrusal katsayılar C_S, öyle ki w(S) = C_S * prod_{i in S} sigma_i.

        Ağırlık formülünde her bağlı domain'in sigma'sı tam bir kez geçer
        (çapa kendi sigma'sıyla, kapanış bağları c_eff = G * sigma ile),
        dolayısıyla w(S) sigma_free'de bir tek terimlidir. Bu yapı,
        doygunluk denklemini log uzayında konveks hâle getirir.
        """
        return self._raw_weights(conc, np.ones(self.n))

    def solve(
        self,
        conc: float,
        deplete: bool = True,
        tol: float = 1e-12,
    ) -> "Equilibrium":
        """Verilen ligand derişiminde denge durum dağılımını çözer.

        Doygunluk denklemi
        ------------------
        Serbest reseptör yoğunlukları şunu sağlamalı:

            sigma_i + sum_{S ni i} w(S)  =  sigma_tot_i

        w(S) = C_S prod_{j in S} sigma_j olduğundan, x = ln(sigma)
        değişkeninde sol taraf bir log-sum-exp'tir:

            r_i(x) = log( e^{x_i} + sum_{S ni i} C_S e^{sum_{j in S} x_j} )
                     - log(sigma_tot_i)  =  0

        Her r_i, x'in her bileşeninde kesin artan ve konvekstir; bu
        sistem kimyasal denge kodlarının standart formudur ve analitik
        Jacobian'lı Newton ile güvenilir biçimde çözülür. Doğrudan
        sigma uzayında sönümlü sabit-nokta iterasyonu, güçlü avidite
        rejiminde (bağlanmanın sigma'da kübik büyüdüğü yerde) yakınsamaz.
        """
        from scipy.optimize import root

        sigma_tot = np.array([r.density for r in self.surface.receptors], dtype=float)

        if self.surface.mode == "fixed" or not deplete:
            w, _ = self.weights_and_bound(conc, sigma_tot)
            return self._package(conc, w, sigma_tot, sigma_tot, 0, 0.0)

        active = sigma_tot > 0
        if not active.any():
            w, _ = self.weights_and_bound(conc, sigma_tot)
            return self._package(conc, w, sigma_tot, sigma_tot, 0, 0.0)

        C = self.coefficients(conc)
        live = [idx for idx, S in enumerate(self.states) if S and C[idx] > 0]
        masks = np.zeros((len(live), self.n), dtype=bool)
        for m, idx in enumerate(live):
            masks[m, list(self.states[idx])] = True
        coef = C[live]
        a_L = self.surface.ligand_footprint
        idx_active = np.flatnonzero(active)
        log_tot = np.log(sigma_tot[idx_active])

        def terms(x_full: np.ndarray) -> np.ndarray:
            """Her canlı durumun ağırlığı w(S) = C_S exp(sum_{j in S} x_j)."""
            return coef * np.exp(masks @ x_full)

        def residual_and_jac(xa: np.ndarray):
            x_full = np.full(self.n, -700.0)
            x_full[idx_active] = xa
            t = terms(x_full)
            if a_L > 0:
                t = t / (1.0 + a_L * t.sum())
            sig = np.exp(xa)
            # bound_i = sum_{S ni i} w(S)
            bound = (masks[:, idx_active] * t[:, None]).sum(axis=0)
            lhs = sig + bound
            r = np.log(lhs) - log_tot
            # d lhs_i / d x_k = delta_ik sig_i + sum_{S ni i, k in S} w(S)
            J = (masks[:, idx_active][:, :, None] * masks[:, idx_active][:, None, :]
                 * t[:, None, None]).sum(axis=0)
            J[np.diag_indices_from(J)] += sig
            return r, J / lhs[:, None]

        x0 = np.log(sigma_tot[idx_active])
        sol = root(
            lambda xa: residual_and_jac(xa)[0],
            x0,
            jac=lambda xa: residual_and_jac(xa)[1],
            method="hybr",
            tol=tol,
        )

        sigma_free = np.zeros(self.n)
        sigma_free[idx_active] = np.exp(sol.x)
        w, bound = self.weights_and_bound(conc, sigma_free)
        resid = float(np.max(np.abs((sigma_free + bound - sigma_tot)[active])))
        rel = resid / float(sigma_tot[active].max())

        if rel > 1e-8:
            raise RuntimeError(
                f"reseptör tükenmesi çözülemedi (bağıl artık={rel:.3e}): {sol.message}"
            )
        return self._package(conc, w, sigma_free, sigma_tot, int(sol.nfev), resid)

    def _package(self, conc, w, sigma_free, sigma_tot, iters, resid) -> "Equilibrium":
        return Equilibrium(
            system=self,
            conc=conc,
            weights=w,
            sigma_free=sigma_free,
            sigma_total=sigma_tot,
            iterations=iters,
            residual=resid,
        )


# --------------------------------------------------------------------------
# Sonuç nesnesi
# --------------------------------------------------------------------------


@dataclass
class Equilibrium:
    system: System
    conc: float
    weights: np.ndarray
    sigma_free: np.ndarray
    sigma_total: np.ndarray
    iterations: int
    residual: float

    @property
    def states(self) -> list[State]:
        return self.system.states

    @property
    def total(self) -> float:
        """Toplam bağlı ligand (yoğunluk [nm^-2] ya da odds)."""
        return float(self.weights.sum())

    @property
    def fractions(self) -> np.ndarray:
        """Bağlı ligandlar arasında durum dağılımı (toplamı 1)."""
        t = self.total
        if t <= 0:
            return np.zeros_like(self.weights)
        return self.weights / t

    def valency_distribution(self) -> np.ndarray:
        """Bağlı ligandlar arasında k-değerlikli olma olasılığı, k=0..n."""
        out = np.zeros(self.system.n + 1)
        f = self.fractions
        for idx, S in enumerate(self.states):
            out[len(S)] += f[idx]
        return out

    def p_at_least(self, k: int) -> float:
        """P(en az k bağ | ligand bağlı)."""
        return float(self.valency_distribution()[k:].sum())

    def p_state(self, S: Iterable[int]) -> float:
        S = tuple(sorted(S))
        return float(self.fractions[self.states.index(S)])

    def p_conditional(self, target: int, given: Iterable[int]) -> float:
        """P(target bağlı | given'deki tümü bağlı)."""
        given = set(given)
        num = den = 0.0
        f = self.fractions
        for idx, S in enumerate(self.states):
            if given <= set(S):
                den += f[idx]
                if target in S:
                    num += f[idx]
        return float(num / den) if den > 0 else float("nan")

    def mean_valency(self) -> float:
        vd = self.valency_distribution()
        return float(np.dot(np.arange(len(vd)), vd))

    def receptor_occupancy(self) -> np.ndarray:
        """Her reseptör türünün doluluk oranı (bağlı / toplam)."""
        bound = np.zeros(self.system.n)
        for idx, S in enumerate(self.states):
            for i in S:
                bound[i] += self.weights[idx]
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(self.sigma_total > 0, bound / self.sigma_total, np.nan)

    def table(self) -> list[dict]:
        names = [d.name for d in self.system.cassette.domains]
        f = self.fractions
        rows = []
        for idx, S in enumerate(self.states):
            if not S:
                continue
            rows.append(
                {
                    "state": "+".join(names[i] for i in S) if S else "-",
                    "valency": len(S),
                    "weight": float(self.weights[idx]),
                    "fraction": float(f[idx]),
                }
            )
        rows.sort(key=lambda r: -r["fraction"])
        return rows


# --------------------------------------------------------------------------
# Türev nicelikler
# --------------------------------------------------------------------------


def monovalent_reference(system: System, conc: float, keep: int, **kw) -> Equilibrium:
    """Yalnızca ``keep`` domain'i yetkin bırakılmış sistemi çözer."""
    doms = []
    for i, d in enumerate(system.cassette.domains):
        doms.append(d if i == keep else Domain(d.name, np.inf, d.k_on, d.span, d.site_offset))
    ref = System(
        cassette=Cassette(doms, list(system.cassette.linkers)),
        surface=system.surface,
        eps=system.eps,
        feasibility=system.feasibility,
        n_grid=system.n_grid,
    )
    ref._grids = system._grids  # tether tablolarını ve geometriyi paylaş
    ref._geom = system._geom
    return ref.solve(conc, **kw)


def avidity_enhancement(system: System, conc: float, **kw) -> dict:
    """Çok-değerlikli toplam bağlanmanın en iyi monovalente oranı."""
    multi = system.solve(conc, **kw)
    monos = {}
    for i, d in enumerate(system.cassette.domains):
        if not np.isfinite(d.kd):
            continue
        monos[d.name] = monovalent_reference(system, conc, i, **kw).total
    best = max(monos.values()) if monos else np.nan
    return {
        "multivalent_total": multi.total,
        "monovalent_totals": monos,
        "best_monovalent": best,
        "enhancement": multi.total / best if best > 0 else np.inf,
    }


def titration(system: System, concentrations: Sequence[float], **kw) -> dict:
    """Derişim taraması: toplam bağlanma ve valans dağılımı."""
    concentrations = np.asarray(concentrations, dtype=float)
    total = np.empty(len(concentrations))
    valency = np.empty((len(concentrations), system.n + 1))
    for m, c in enumerate(concentrations):
        eq = system.solve(float(c), **kw)
        total[m] = eq.total
        valency[m] = eq.valency_distribution()
    return {"conc": concentrations, "total": total, "valency": valency}


def state_density_profile(
    system: System,
    state: Iterable[int],
    lo: float = 1e-16,
    hi: float = 1e-3,
    n_points: int = 160,
    **kw,
) -> dict:
    """Belirli bir durumun yoğunluğunu derişime karşı tarar ve tepeyi bulur.

    Çok-değerlikli durumların yoğunluğu derişimde genellikle MONOTON
    DEĞİLDİR: yüksek [L]'de ligandlar reseptörler için yarışır, her biri
    tek bir reseptörü işgal eder ve çoklu bağlanma için ortak reseptör
    kalmaz (prozone / hook etkisi). Dolayısıyla "daha çok ligand her
    zaman daha çok üçlü bağlanma" yanlıştır ve optimum bir doz vardır.
    """
    S = tuple(sorted(state))
    grid = np.logspace(np.log10(lo), np.log10(hi), n_points)
    rho = np.empty(n_points)
    for m, c in enumerate(grid):
        eq = system.solve(float(c), **kw)
        rho[m] = eq.p_state(S) * eq.total
    k = int(np.argmax(rho))
    interior = 0 < k < n_points - 1
    return {
        "conc": grid,
        "density": rho,
        "peak_conc": float(grid[k]),
        "peak_density": float(rho[k]),
        "has_interior_peak": bool(interior),
    }


def apparent_kd(
    system: System,
    lo: float = 1e-15,
    hi: float = 1e-2,
    n_points: int = 200,
    **kw,
) -> dict:
    """Görünür EC50: TOPLAM bağlanmanın platosunun yarısına ulaştığı derişim.

    Doygunluk (reseptör tükenmesi) açıkken plato sonludur; kapalıyken
    plato tanımsızdır ve NaN döner.

    UYARI -- bu bir avidite ölçüsü DEĞİLDİR. Plato, reseptör kapasitesiyle
    belirlenir ve yüksek [L]'de her reseptöre ayrı bir ligand monovalent
    bağlanır; dolayısıyla yarı-plato noktası monovalent K_D tarafından
    yönetilir ve çok-değerlikliliğin kazancını gizler. Avidite için
    ``avidity_enhancement``, ``kinetics.kinetic_avidity`` ya da
    ``state_density_profile`` kullanın.
    """
    grid = np.logspace(np.log10(lo), np.log10(hi), n_points)
    t = titration(system, grid, **kw)["total"]
    plateau = t[-1]
    if not np.isfinite(plateau) or plateau <= 0:
        return {"ec50": float("nan"), "plateau": float(plateau)}
    # plato gerçekten doymuş mu?
    saturated = t[-1] / max(t[-2], 1e-300) < 1.05
    half = plateau / 2.0
    idx = int(np.searchsorted(t, half))
    if idx == 0 or idx >= len(grid):
        return {"ec50": float("nan"), "plateau": float(plateau), "saturated": saturated}
    x0, x1 = np.log10(grid[idx - 1]), np.log10(grid[idx])
    y0, y1 = t[idx - 1], t[idx]
    ec50 = 10 ** (x0 + (half - y0) * (x1 - x0) / (y1 - y0))
    return {"ec50": float(ec50), "plateau": float(plateau), "saturated": bool(saturated)}
