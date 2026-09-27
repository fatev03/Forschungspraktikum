"""Durum ağı üzerinde kinetik: ikamet süresi, etkin k_off, geçici rejim.

İki ayrı matematiksel nesne var; karıştırılmamaları önemli.

A) Tek-ligand CTMC (bağlı durumlar üzerinde, bosluk durumu yutucu)
   ------------------------------------------------------------------
   Avidite'nin asıl imzası burada: çok-değerlikli bağlanma genellikle
   k_on'u değil, *kaçış süresini* değiştirir.

   Üreteç (generator) Q, bağlı durumlar üzerinde:

       S -> S u {j} :  k_on_j * c_eff(j | S)
       S -> S minus {j} :  k_off_j = K_j * k_on_j
       |S| = 1      :  tek bağ koptuğunda bosluga yutulur

   Koşullu etkin derişim doğrudan denge ağırlıklarından türetilir:

       c_eff(j | S) = K_j * w(S u {j}) / w(S)

   Bu tanım ayrıntılı dengeyi (detailed balance) kimliksel olarak sağlar:

       w(S) * k_{S->S+j} = k_on_j K_j w(S+j) = k_off_j * w(S+j)      (*)

   Yutulmaya kadar ortalama ilk-geçiş süresi (MFPT):

       tau = -Q^{-1} 1        (Q, bağlı durumlara kısıtlanmış üreteç)

   Hayatta kalma fonksiyonu:  Sv(t) = 1^T exp(Q t) p0.

B) Popülasyon ODE'si (tüm durumlar, yüzey yoğunlukları)
   -----------------------------------------------------
   Reseptör tükenmesi nedeniyle NONLINEER:

       d rho_S / dt = sum_{S'} rho_{S'} q_{S'->S} - rho_S sum q_{S->.}
       rho_{i} için ayrıca varış terimi: k_on_i * [L] * sigma_free_i
       sigma_free_i = sigma_tot_i - sum_{S ni i} rho_S

   Varış hız sabiti ayrıntılı dengeden k_on_i olarak sabitlenir; böylece
   ODE'nin sabit noktası model.System.solve()'un denge çözümüne eşittir
   (bkz. tests/test_core.py::test_ode_fixed_point_matches_equilibrium).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import expm

from .model import Equilibrium, State, System


# --------------------------------------------------------------------------
# A) Tek-ligand CTMC
# --------------------------------------------------------------------------


@dataclass
class ResidenceAnalysis:
    system: System
    states: list[State]
    """Bağlı durumlar (boş küme hariç), Q ile aynı sırada."""
    Q: np.ndarray
    """Bağlı durumlara kısıtlanmış üreteç [1/s]."""
    mfpt: np.ndarray
    """Her bağlı durumdan bosluga ortalama ilk-geçiş süresi [s]."""
    entry_p: np.ndarray
    """Çözeltiden gelen ligandın ilk bağ dağılımı."""
    qss_p: np.ndarray
    """Bağlı popülasyonun yarı-kararlı dağılımı (denge ağırlıkları)."""

    @property
    def tau_entry(self) -> float:
        """Varış anından itibaren ortalama yüzeyde kalma süresi [s]."""
        return float(self.entry_p @ self.mfpt)

    @property
    def tau_qss(self) -> float:
        """Hâlihazırda bağlı bir ligandın kalan ortalama ömrü [s]."""
        return float(self.qss_p @ self.mfpt)

    @property
    def k_off_eff(self) -> float:
        """Etkin ayrışma hız sabiti [1/s] = 1 / tau_entry."""
        return 1.0 / self.tau_entry if self.tau_entry > 0 else np.inf

    def survival(self, t: np.ndarray, p0: np.ndarray | None = None) -> np.ndarray:
        """Sv(t) = 1^T exp(Q^T t) p0; çoklu-üstel dissosiyasyon eğrisi.

        Q "satır = kaynak durum" konvansiyonunda kurulur, dolayısıyla
        sütun-vektör olasılıkları için dp/dt = Q^T p. Ortalama ikamet
        süresiyle tutarlılık: int_0^inf Sv dt = p0 . mfpt.
        """
        p0 = self.entry_p if p0 is None else np.asarray(p0, dtype=float)
        t = np.atleast_1d(np.asarray(t, dtype=float))
        QT = self.Q.T
        out = np.empty(len(t))
        for m, tv in enumerate(t):
            out[m] = float(np.ones(len(p0)) @ (expm(QT * tv) @ p0))
        return out

    def relaxation_spectrum(self) -> np.ndarray:
        """-Re(eigvals(Q)) artan sırada [1/s]: dissosiyasyonun hız modları."""
        ev = np.linalg.eigvals(self.Q)
        return np.sort(-np.real(ev))


def residence_analysis(eq: Equilibrium) -> ResidenceAnalysis:
    """Bir denge çözümünden tek-ligand kaçış kinetiğini kurar."""
    sys_ = eq.system
    kd = np.array([d.kd for d in sys_.cassette.domains])
    kon = np.array([d.k_on for d in sys_.cassette.domains])
    koff = kd * kon

    # Yalnızca erişilebilir (w > 0) durumlar üreteçte yer alır. Ağırlığı
    # sıfır olan durumlar (fizibilite vetosu, K_D = inf, sigma = 0) ne
    # doldurulabilir ne de boşaltılabilir; üretece alınırlarsa sonsuz ya
    # da tanımsız hızlar üretirler.
    bound_idx = [i for i, S in enumerate(sys_.states) if S and eq.weights[i] > 0.0]
    if not bound_idx:
        raise ValueError("erişilebilir bağlı durum yok; ikamet analizi tanımsız")
    states = [sys_.states[i] for i in bound_idx]
    pos = {S: m for m, S in enumerate(states)}
    w = eq.weights[bound_idx]
    nb = len(states)

    Q = np.zeros((nb, nb))
    for m, S in enumerate(states):
        # kopma
        for j in S:
            rest = tuple(x for x in S if x != j)
            rate = koff[j]
            Q[m, m] -= rate
            # boş küme -- ve erişilemez her durum -- yutucudur; satır açığı
            # olarak bırakılır, böylece MFPT onları çıkış saymış olur
            if rest and rest in pos:
                Q[m, pos[rest]] += rate
        # ek bağ kurulumu, ayrıntılı dengeden
        for j in range(sys_.n):
            if j in S or not np.isfinite(kd[j]):
                continue
            nxt = tuple(sorted(S + (j,)))
            if nxt not in pos:
                continue
            wn = eq.weights[sys_.state_index[nxt]]
            if w[m] <= 0 or wn <= 0:
                continue
            rate = kon[j] * kd[j] * wn / w[m]
            Q[m, m] -= rate
            Q[m, pos[nxt]] += rate

    mfpt = np.linalg.solve(Q, -np.ones(nb))

    # varış dağılımı: tek-bağlı durumlara, kon_i * [L] * sigma_free_i ile orantılı
    entry = np.zeros(nb)
    for m, S in enumerate(states):
        if len(S) == 1:
            i = S[0]
            if np.isfinite(kd[i]):
                sig = eq.sigma_free[i] if sys_.surface.mode == "disordered" else 1.0
                entry[m] = kon[i] * eq.conc * sig
    if entry.sum() > 0:
        entry /= entry.sum()

    qss = w / w.sum() if w.sum() > 0 else np.zeros(nb)

    return ResidenceAnalysis(sys_, states, Q, mfpt, entry, qss)


def kinetic_avidity(system: System, conc: float, **kw) -> dict:
    """Çok-değerlikli ikamet süresinin en iyi monovalente oranı."""
    from .model import monovalent_reference

    multi = residence_analysis(system.solve(conc, **kw))
    monos: dict[str, float] = {}
    for i, d in enumerate(system.cassette.domains):
        if not np.isfinite(d.kd):
            continue
        ref_eq = monovalent_reference(system, conc, i, **kw)
        if ref_eq.total <= 0:
            monos[d.name] = 1.0 / d.k_off
            continue
        monos[d.name] = residence_analysis(ref_eq).tau_entry
    best = max(monos.values()) if monos else np.nan
    return {
        "tau_entry_s": multi.tau_entry,
        "tau_qss_s": multi.tau_qss,
        "k_off_eff_per_s": multi.k_off_eff,
        "monovalent_tau_s": monos,
        "best_monovalent_tau_s": best,
        "residence_enhancement": multi.tau_entry / best if best > 0 else np.inf,
        "relaxation_rates_per_s": multi.relaxation_spectrum().tolist(),
    }


# --------------------------------------------------------------------------
# B) Popülasyon ODE'si
# --------------------------------------------------------------------------


def _rates_from_densities(sys_: System, rho: np.ndarray, conc: float):
    """Verilen durum yoğunluklarında anlık hızları kurar (nonlineer).

    Bağ kurulum hızları ayrıntılı dengeden alınır:

        k_{S -> S+j} = k_on_j * K_j * w(S+j) / w(S)

    w oranları ligand derişiminden bağımsızdır (her boş-olmayan durumun
    ağırlığında [L] tam olarak bir kez geçer), bu yüzden w referans
    derişim 1 M ile anlık sigma_free'de hesaplanır. Bu tanım, sadece
    "j'nin en yakın komşusuna erişimi" demekten farklıdır: zaten bağlı
    iki domain'in *arasına* bir domain yerleştirmek ilmek-kapanışı
    bedeli taşır ve oran bunu kendiliğinden içerir.
    """
    kd = np.array([d.kd for d in sys_.cassette.domains])
    kon = np.array([d.k_on for d in sys_.cassette.domains])
    sigma_tot = np.array([r.density for r in sys_.surface.receptors])
    index = sys_.state_index

    bound = np.zeros(sys_.n)
    for idx, S in enumerate(sys_.states):
        for i in S:
            bound[i] += rho[idx]
    sigma_free = np.maximum(sigma_tot - bound, 0.0)

    w = sys_._raw_weights(1.0, sigma_free)

    drho = np.zeros_like(rho)
    for idx, S in enumerate(sys_.states):
        if not S:
            continue
        # kopma: S -> S\{j}
        for j in S:
            rest = tuple(x for x in S if x != j)
            flux = kd[j] * kon[j] * rho[idx]
            drho[idx] -= flux
            if rest:
                drho[index[rest]] += flux
        # kurulum: S -> S u {j}
        if w[idx] <= 0.0:
            continue
        for j in range(sys_.n):
            if j in S or not np.isfinite(kd[j]):
                continue
            nxt = tuple(sorted(S + (j,)))
            wn = w[index[nxt]]
            if wn <= 0.0:
                continue
            flux = kon[j] * kd[j] * (wn / w[idx]) * rho[idx]
            drho[idx] -= flux
            drho[index[nxt]] += flux

    # çözeltiden varış: boşluk -> {i}
    for i in range(sys_.n):
        if not np.isfinite(kd[i]):
            continue
        single = (i,)
        if sys_.feasibility is not None and not sys_.feasibility(single):
            continue
        sig = sigma_free[i] if sys_.surface.mode == "disordered" else 1.0
        arrival = kon[i] * conc * sig
        if sys_.surface.ligand_footprint > 0:
            arrival *= max(1.0 - sys_.surface.ligand_footprint * rho.sum(), 0.0)
        drho[index[single]] += arrival

    return drho, sigma_free


@dataclass
class Trajectory:
    t: np.ndarray
    rho: np.ndarray
    """shape (n_states, n_t) durum yoğunlukları [nm^-2]."""
    states: list[State]

    def total(self) -> np.ndarray:
        return self.rho.sum(axis=0)

    def valency_curves(self) -> np.ndarray:
        """shape (n+1, n_t): k-değerlikli ligand yoğunluğu."""
        nmax = max(len(S) for S in self.states)
        out = np.zeros((nmax + 1, self.rho.shape[1]))
        for idx, S in enumerate(self.states):
            out[len(S)] += self.rho[idx]
        return out


def simulate(
    system: System,
    conc: float,
    t_end: float,
    rho0: np.ndarray | None = None,
    n_out: int = 400,
    rtol: float = 1e-8,
    atol: float = 1e-16,
) -> Trajectory:
    """Popülasyon ODE'sini integre eder (birleşme veya yıkama)."""
    n_states = len(system.states)
    y0 = np.zeros(n_states) if rho0 is None else np.asarray(rho0, dtype=float).copy()

    def rhs(_t, y):
        y = np.maximum(y, 0.0)
        d, _ = _rates_from_densities(system, y, conc)
        return d

    t_eval = np.linspace(0.0, t_end, n_out)
    sol = solve_ivp(
        rhs, (0.0, t_end), y0, t_eval=t_eval, method="LSODA", rtol=rtol, atol=atol
    )
    if not sol.success:
        raise RuntimeError(f"ODE çözümü başarısız: {sol.message}")
    return Trajectory(sol.t, np.maximum(sol.y, 0.0), system.states)


def washout(system: System, conc_load: float, t_end: float, **kw) -> Trajectory:
    """Dengede yükle, sonra [L]=0 ile yıka: deneysel dissosiyasyon eğrisi."""
    eq = system.solve(conc_load)
    return simulate(system, 0.0, t_end, rho0=eq.weights, **kw)
