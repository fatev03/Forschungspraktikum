"""Çekirdek matematiğin doğrulanması.

Her test, modelin *iddia ettiği* bir özdeşliği bağımsız bir yolla sınar:
kapalı form, Monte Carlo, ya da başka bir sayısal şema.
"""

import numpy as np
import pytest

from avidity.constants import NM3_TO_MOLAR
from avidity.kinetics import residence_analysis, simulate
from avidity.model import (
    Cassette,
    Domain,
    Receptor,
    Surface,
    System,
    monovalent_reference,
)
from avidity.tether import (
    Chain,
    FJC,
    Gaussian,
    Rod,
    TetherGrid,
    peptide_linker,
    wlc,
    wlc_report,
)

RNG = np.random.default_rng(20240924)


# ==========================================================================
# 1. Tether katmanı
# ==========================================================================


def test_gaussian_matches_closed_form():
    """Gauss zinciri için A(dz) ve P(r) analitik olarak bilinir."""
    msq, eps = 25.0, 0.02
    g = TetherGrid(Chain.of(Gaussian(msq)), eps=eps, z_max=40.0)
    M = msq + eps**2  # düzenleyici varyansı ekler
    alpha = 3.0 / (2 * M)

    z = np.array([0.0, 1.0, 3.0, 5.0, 8.0, 12.0])
    assert np.allclose(
        g.areal_reach(z), np.sqrt(alpha / np.pi) * np.exp(-alpha * z**2), rtol=1e-5
    )
    r = np.array([0.5, 1.0, 3.0, 5.0, 8.0, 12.0])
    assert np.allclose(
        g.radial_density(r), (alpha / np.pi) ** 1.5 * np.exp(-alpha * r**2), rtol=1e-5
    )


def test_normalization_and_second_moment():
    for chain in [
        Chain.of(Gaussian(9.0)),
        Chain.of(FJC(1.0, 8)),
        Chain.of(Rod(4.0), FJC(0.8, 5)),
        Chain.of(wlc(15.0, 0.5), Rod(3.0), wlc(10.0, 0.5)),
    ]:
        g = TetherGrid(chain, eps=0.2)
        chk = g.check_normalization()
        assert chk["norm_3d"] == pytest.approx(1.0, rel=2e-4)
        assert chk["norm_1d"] == pytest.approx(1.0, rel=2e-4)
        assert chk["msq_numeric"] == pytest.approx(chk["msq_analytic"], rel=2e-3)


def test_areal_reach_matches_monte_carlo():
    """A(dz) = p_z(dz); Fourier yolundan bağımsız MC ile karşılaştır."""
    chain = Chain.of(wlc(12.0, 0.5), Rod(3.0), wlc(9.0, 0.5))
    eps = 0.3
    g = TetherGrid(chain, eps=eps)

    n = 2_000_000
    v = chain.sample(RNG, n)
    # düzenleyiciyi MC tarafına da uygula (aynı nesneyi karşılaştırmak için)
    v += RNG.normal(scale=np.sqrt(eps**2 / 3.0), size=(n, 3))
    zc = v[:, 2]

    h = 0.25  # histogram bant genişliği [nm]
    for dz in [0.0, 2.0, 5.0, 9.0]:
        mc = np.mean(np.abs(zc - dz) < h / 2) / h
        ref = float(g.areal_reach(dz))
        assert mc == pytest.approx(ref, rel=0.04), f"dz={dz}: MC={mc:.5f} ref={ref:.5f}"


def test_composition_equals_convolution():
    """0->2 tether'ı, 0->1 ve 1->2'nin konvolüsyonu olmalı (marjinalleştirme)."""
    a = Chain.of(wlc(10.0, 0.5))
    b = Chain.of(Rod(2.5), wlc(7.0, 0.5))
    comp = Chain.of(a, b)

    n = 400_000
    v = a.sample(RNG, n) + b.sample(RNG, n)
    assert (v**2).sum(1).mean() == pytest.approx(comp.msq, rel=0.02)
    assert comp.contour == pytest.approx(a.contour + b.contour)

    g = TetherGrid(comp, eps=0.3)
    vv = v + RNG.normal(scale=np.sqrt(0.3**2 / 3.0), size=(n, 3))
    h = 0.4
    for dz in [0.0, 3.0, 7.0]:
        mc = np.mean(np.abs(vv[:, 2] - dz) < h / 2) / h
        assert mc == pytest.approx(float(g.areal_reach(dz)), rel=0.06)


def test_contour_cutoff_is_physical():
    """Kontur uzunluğunun ötesinde erişim tam sıfır -- elle konmuş bir veto değil."""
    chain = Chain.of(FJC(1.0, 6))  # kontur = 6 nm
    g = TetherGrid(chain, eps=0.1)
    assert g.radial_density(3.0) > 0
    assert g.radial_density(5.8) > 0
    assert g.radial_density(6.5) == 0.0
    assert g.areal_reach(7.0) == 0.0


def test_wlc_matches_kratky_porod_moments():
    for L, lp in [(20, 0.5), (6, 2.0), (3, 0.4), (50, 0.5), (12, 0.6), (1.0, 5.0)]:
        r = wlc_report(L, lp)
        assert abs(r["rel_error_msq"]) < 1e-9
        assert abs(r["rel_error_contour"]) < 1e-12


# ==========================================================================
# 2. Denge modeli
# ==========================================================================


def build_system(kds=(1e-6, 3e-7, 2e-6), densities=(2e-3, 1e-3, 5e-4), **kw):
    doms = [
        Domain("D1", kds[0], k_on=1e5, span=2.5),
        Domain("D2", kds[1], k_on=1e5, span=2.5),
        Domain("D3", kds[2], k_on=1e5, span=2.5),
    ]
    links = [peptide_linker(20), peptide_linker(20)]
    recs = [
        Receptor("R1", densities[0], height=4.0),
        Receptor("R2", densities[1], height=6.0),
        Receptor("R3", densities[2], height=3.0),
    ]
    return System(Cassette(doms, links), Surface(recs), **kw)


def test_monovalent_reduces_to_langmuir():
    """Tek yetkin domain + tükenme => tam Langmuir izotermi."""
    sysm = build_system()
    K, sig = sysm.cassette.domains[0].kd, sysm.surface.receptors[0].density
    for L in [1e-9, 1e-7, 1e-6, 1e-5]:
        eq = monovalent_reference(sysm, L, keep=0)
        assert eq.total == pytest.approx(sig * L / (K + L), rel=1e-9)


def test_bivalent_closed_form():
    """İki domain, tükenmesiz: ağırlıklar elle yazılabilir."""
    sysm = build_system(kds=(1e-6, 3e-7, np.inf))
    L = 1e-9
    eq = sysm.solve(L, deplete=False)

    K0, K1 = 1e-6, 3e-7
    s0, s1 = 2e-3, 1e-3
    A01 = float(sysm.grid(0, 1).areal_reach(sysm.surface.dz(0, 1)))
    ce01 = NM3_TO_MOLAR * s1 * A01

    w0 = L / K0 * s0
    w1 = L / K1 * s1
    w01 = w0 * ce01 / K1

    assert eq.p_state([0]) * eq.total == pytest.approx(w0, rel=1e-9)
    assert eq.p_state([1]) * eq.total == pytest.approx(w1, rel=1e-9)
    assert eq.p_state([0, 1]) * eq.total == pytest.approx(w01, rel=1e-9)


def test_weights_are_anchor_independent():
    """w(S), hangi bağın 'çapa' sayıldığına bağlı olmamalı (yol-bağımsızlık).

    Referans formül S'nin en küçük elemanını çapa alır. Burada her olası
    çapa için ardışık-çift açılımı elle kurulup karşılaştırılır.
    """
    sysm = build_system()
    L = 1e-8
    eq = sysm.solve(L, deplete=True)
    sf = eq.sigma_free
    kd = np.array([d.kd for d in sysm.cassette.domains])

    def weight_from_anchor(S, anchor):
        """S'yi anchor'dan başlayıp kontur boyunca iki yöne tarayarak kur."""
        k = S.index(anchor)
        val = (L / kd[anchor]) * sf[anchor]
        for m in range(k, 0, -1):  # sola doğru
            val *= sysm.c_eff(S[m], S[m - 1], sf) / kd[S[m - 1]]
        for m in range(k, len(S) - 1):  # sağa doğru
            val *= sysm.c_eff(S[m], S[m + 1], sf) / kd[S[m + 1]]
        return val

    for S in sysm.states:
        if len(S) < 2:
            continue
        ref = eq.weights[sysm.state_index[S]]
        for anchor in S:
            assert weight_from_anchor(S, anchor) == pytest.approx(ref, rel=1e-12)


def test_feasibility_veto_zeroes_state():
    veto = lambda S: S != (0, 1, 2)
    sysm = build_system(**{"feasibility": veto})
    eq = sysm.solve(1e-8)
    assert eq.p_state([0, 1, 2]) == 0.0
    assert eq.p_at_least(2) > 0.0


def test_depletion_conserves_receptors():
    sysm = build_system(densities=(2e-3, 1e-3, 5e-4))
    eq = sysm.solve(1e-4)  # doygunluğa yakın
    bound = np.zeros(3)
    for idx, S in enumerate(sysm.states):
        for i in S:
            bound[i] += eq.weights[idx]
    assert np.allclose(eq.sigma_free + bound, eq.sigma_total, rtol=1e-6)
    assert np.all(eq.sigma_free >= -1e-18)
    assert np.all(eq.receptor_occupancy() <= 1.0 + 1e-9)


# ==========================================================================
# 3. Kinetik
# ==========================================================================


def test_detailed_balance_of_generator():
    """w(S) q(S->S') = w(S') q(S'->S) her kenar için."""
    sysm = build_system()
    eq = sysm.solve(1e-8)
    ra = residence_analysis(eq)
    w = np.array([eq.weights[sysm.state_index[S]] for S in ra.states])
    n = len(ra.states)
    for a in range(n):
        for b in range(n):
            if a == b or ra.Q[a, b] == 0:
                continue
            assert w[a] * ra.Q[a, b] == pytest.approx(w[b] * ra.Q[b, a], rel=1e-9)


def test_kolmogorov_cycle_criterion():
    """Hiper-küpteki her 4-döngüde ileri/geri hız çarpımları eşit olmalı."""
    sysm = build_system()
    ra = residence_analysis(sysm.solve(1e-8))
    pos = {S: m for m, S in enumerate(ra.states)}
    # döngü: {0} -> {0,1} -> {0,1,2} -> {0,2} -> {0}
    cyc = [(0,), (0, 1), (0, 1, 2), (0, 2), (0,)]
    fwd = bwd = 1.0
    for a, b in zip(cyc, cyc[1:]):
        fwd *= ra.Q[pos[a], pos[b]]
        bwd *= ra.Q[pos[b], pos[a]]
    assert fwd == pytest.approx(bwd, rel=1e-9)


def test_monovalent_mfpt_is_inverse_koff():
    sysm = build_system()
    eq = monovalent_reference(sysm, 1e-9, keep=1)
    ra = residence_analysis(eq)
    assert ra.tau_entry == pytest.approx(1.0 / sysm.cassette.domains[1].k_off, rel=1e-9)


def test_multivalency_extends_residence():
    sysm = build_system()
    multi = residence_analysis(sysm.solve(1e-9)).tau_entry
    best_mono = max(
        residence_analysis(monovalent_reference(sysm, 1e-9, keep=i)).tau_entry
        for i in range(3)
    )
    assert multi > best_mono


def test_survival_mean_equals_mfpt():
    """int_0^inf Sv(t) dt = tau (ortalama ikamet süresi)."""
    sysm = build_system()
    ra = residence_analysis(sysm.solve(1e-9))
    t = np.linspace(0, 60 * ra.tau_entry, 4000)
    integral = np.trapezoid(ra.survival(t), t)
    assert integral == pytest.approx(ra.tau_entry, rel=2e-3)


def test_ode_fixed_point_matches_equilibrium():
    """ODE'nin kararlı durumu, denge çözücüsüyle aynı noktaya gitmeli."""
    sysm = build_system()
    L = 1e-7
    eq = sysm.solve(L)
    traj = simulate(sysm, L, t_end=4000.0, n_out=50)
    final = traj.rho[:, -1]
    assert np.allclose(final, eq.weights, rtol=2e-3, atol=1e-14)


def test_ode_respects_receptor_capacity():
    sysm = build_system()
    traj = simulate(sysm, 1e-3, t_end=2000.0, n_out=50)
    bound = np.zeros((3, traj.rho.shape[1]))
    for idx, S in enumerate(sysm.states):
        for i in S:
            bound[i] += traj.rho[idx]
    for i, r in enumerate(sysm.surface.receptors):
        assert np.all(bound[i] <= r.density * (1 + 1e-6))


def test_weights_are_multilinear_in_density():
    """w(S) = C_S * prod_{i in S} sigma_i -- solver bu yapıya dayanıyor."""
    sysm = build_system()
    L = 1e-8
    C = sysm.coefficients(L)
    rng = np.random.default_rng(7)
    for _ in range(5):
        sf = rng.uniform(1e-5, 3e-3, size=3)
        w = sysm._raw_weights(L, sf)
        for idx, S in enumerate(sysm.states):
            expect = C[idx] * np.prod([sf[i] for i in S]) if S else 0.0
            assert w[idx] == pytest.approx(expect, rel=1e-12)


def test_solver_across_twelve_decades():
    """Zayıf bağlanmadan tam doygunluğa kadar çözücü kararlı kalmalı."""
    sysm = build_system()
    prev = -np.inf
    for L in np.logspace(-14, -2, 40):
        eq = sysm.solve(float(L))
        assert eq.residual / eq.sigma_total.max() < 1e-8
        assert eq.total >= prev - 1e-18  # toplam bağlanma monoton artmalı
        prev = eq.total
        occ = eq.receptor_occupancy()
        assert np.all(occ >= -1e-12) and np.all(occ <= 1 + 1e-9)


def test_high_concentration_saturates_a_receptor():
    sysm = build_system()
    eq = sysm.solve(1e-2)
    assert eq.receptor_occupancy().max() == pytest.approx(1.0, abs=1e-3)


def test_areal_reach_has_interior_optimum():
    """A(dz) linker uzunluğunda monoton DEĞİL: dz > 0 için iç optimum var.

    Gauss zinciri için A(dz) = sqrt(3/(2 pi m)) exp(-3 dz^2 / (2m)).
    d/dm = 0  =>  m* = 3 dz^2.  Kısa linker yükseklik farkını köprüleyemez,
    uzun linker entropik olarak seyrelir.
    """
    dz = 3.0
    ms = np.linspace(2.0, 120.0, 400)
    A = np.array([float(TetherGrid(Chain.of(Gaussian(m)), eps=1e-3,
                                   z_max=60.0, n_grid=2**12 + 1).areal_reach(dz))
                  for m in ms[::20]])
    assert A.argmax() not in (0, len(A) - 1)  # iç optimum
    m_star = ms[::20][A.argmax()]
    assert m_star == pytest.approx(3 * dz**2, rel=0.25)

    # dz = 0 hâlinde optimum yok: kısa her zaman daha iyi
    A0 = np.array([float(TetherGrid(Chain.of(Gaussian(m)), eps=1e-3,
                                    z_max=60.0, n_grid=2**12 + 1).areal_reach(0.0))
                   for m in [4.0, 16.0, 64.0]])
    assert A0[0] > A0[1] > A0[2]


def test_trivalent_density_peaks_at_intermediate_linker():
    """A(dz)'deki iç optimum tam modele taşınmalı -- düşük doluluk rejiminde.

    Yüksek derişimde dağılımı doygunluk kısıtı belirler ve optimum
    görünmez; bu yüzden reseptör doluluğunun %1'in altında kaldığı bir
    derişim seçilir.

    Beklenen konum: ortak linker ikinci momenti m için
        ln[A01(dz01) A12(dz12)] = sabit - ln m - 3(dz01^2 + dz12^2)/(2m)
        => m* = 3(dz01^2 + dz12^2)/2 = 3(4+9)/2 = 19.5 nm^2
        => L_c ~ m*/(2 l_p) = 19.5 nm ~ 53 residü
    """
    from avidity.tether import peptide_linker

    lengths = [8, 16, 24, 32, 48, 72, 110]
    rho3, occ = [], []
    for n_res in lengths:
        s = build_system()
        s.cassette.linkers = [peptide_linker(n_res), peptide_linker(n_res)]
        s._grids.clear()
        s._geom.clear()
        eq = s.solve(1e-13)
        rho3.append(eq.p_state([0, 1, 2]) * eq.total)
        occ.append(eq.receptor_occupancy().max())

    assert max(occ) < 0.01, f"doluluk çok yüksek: {max(occ):.3f}"
    k = int(np.argmax(rho3))
    assert k not in (0, len(rho3) - 1), f"iç optimum yok: {rho3}"
    assert 24 <= lengths[k] <= 72


def test_multivalent_state_shows_prozone_peak():
    """Üçlü-bağlı yoğunluk derişimde monoton olmamalı (hook etkisi).

    Yüksek [L]'de ligand fazlası reseptörleri tek tek işgal eder ve ortak
    bağlanma için reseptör bırakmaz; bu yüzden üçlü yoğunluk bir tepe
    yapıp düşer. Toplam bağlanma ise monoton artmaya devam eder.
    """
    from avidity.model import state_density_profile

    sysm = build_system()
    prof = state_density_profile(sysm, [0, 1, 2], lo=1e-15, hi=1e-3, n_points=60)
    assert prof["has_interior_peak"]
    assert prof["density"][-1] < 0.5 * prof["peak_density"]

    tot = np.array([sysm.solve(float(c)).total for c in prof["conc"]])
    assert np.all(np.diff(tot) >= -1e-18)  # toplam monoton


def test_linker_optimum_matches_analytic_prediction():
    """Her linkerin optimum konturu, köprülediği yükseklik farkıyla belirlenir.

    Gauss rejiminde A(dz) = sqrt(3/(2 pi m)) exp(-3 dz^2 / 2m) ve m = 2 lp Lc,
    dolayısıyla
        m*  = 3 dz^2        =>      Lc* = 3 dz^2 / (2 lp).

    İki linker bağımsız olarak taranır; her biri kendi dz'sine karşılık
    gelen optimuma oturmalı. Bu, ardışık-çift ayrışmasının da bir testidir:
    L12 yalnızca dz(R1,R2)'yi, L23 yalnızca dz(R2,R3)'ü görmeli.
    """
    from avidity.sweep import linker_contour, obs_density_all_bound, sweep_2d

    sysm = build_system()
    lp = 0.5
    lc = np.linspace(3.0, 60.0, 40)
    grid = sweep_2d(sysm, 1e-13, obs_density_all_bound,
                    linker_contour(0, lp), lc, linker_contour(1, lp), lc)
    a, b = np.unravel_index(np.argmax(grid), grid.shape)

    for found, dz in [(lc[a], sysm.surface.dz(0, 1)), (lc[b], sysm.surface.dz(1, 2))]:
        assert found == pytest.approx(3 * dz**2 / (2 * lp), rel=0.30)


# ==========================================================================
# 4. Sabit geometri modu
# ==========================================================================


def build_fixed(sep_13: float, linker_res: int = 20):
    """Reseptörler bilinen konumlarda; R1-R3 ayrımı parametre."""
    from avidity.tether import peptide_linker

    doms = [Domain("D1", 1e-6), Domain("D2", 3e-7), Domain("D3", 2e-6)]
    links = [peptide_linker(linker_res), peptide_linker(linker_res)]
    recs = [
        Receptor("R1", position=(0.0, 0.0, 0.0)),
        Receptor("R2", position=(sep_13 / 2, 0.0, 0.0)),
        Receptor("R3", position=(sep_13, 0.0, 0.0)),
    ]
    return System(Cassette(doms, links), Surface(recs, mode="fixed"))


def test_fixed_mode_contour_veto_is_emergent():
    """Ulaşılamayacak kadar uzak reseptörler, ağırlığı KENDİLİĞİNDEN sıfırlar.

    Bu bir fizibilite kuralı değil: tether'ın kontur uzunluğunun ötesinde
    P(d) tam olarak sıfırdır, dolayısıyla o kapanış bağının etkin yerel
    derişimi sıfır ve durumun ağırlığı sıfır olur.
    """
    near = build_fixed(sep_13=6.0)
    far = build_fixed(sep_13=60.0)  # tek linker konturu ~7.3 nm

    assert near.solve(1e-6).p_state([0, 1, 2]) > 0
    eq_far = far.solve(1e-6)
    assert eq_far.p_state([0, 1, 2]) == 0.0
    assert eq_far.p_state([0, 1]) == 0.0
    assert eq_far.p_state([0]) > 0  # tek bağ hâlâ mümkün

    rs = {tuple(r["pair"]): r for r in far.reach_summary()}
    assert rs[(0, 1)]["reachable"] is False
    assert rs[(0, 2)]["reachable"] is False


def test_fixed_mode_weights_are_dimensionless_odds():
    """'fixed' modunda w(S), tek bir kompleksin doluluk oranıdır (odds)."""
    from avidity.constants import NM3_TO_MOLAR

    sysm = build_fixed(sep_13=6.0)
    L = 1e-7
    eq = sysm.solve(L)
    P01 = float(sysm.grid(0, 1).radial_density(sysm.surface.separation(0, 1)))
    expect = (L / 1e-6) * (NM3_TO_MOLAR * P01 / 3e-7)
    assert eq.p_state([0, 1]) * eq.total == pytest.approx(expect, rel=1e-9)


def test_fixed_mode_weight_decreases_with_separation():
    """Sabit geometride c_eff'e giren P(d) yoğunluktur ve d'de monoton azalır.

    (Radyal dağılım 4 pi d^2 P(d) ile karıştırılmamalı; o d=0'da sıfırdır.)
    Kontur uzunluğunun ötesinde tam sıfır olur.
    """
    seps = [1.0, 3.0, 5.0, 7.0, 9.0, 11.0, 20.0]
    w3 = []
    for sp in seps:
        eq = build_fixed(sp).solve(1e-6)
        w3.append(eq.p_state([0, 1, 2]) * eq.total)
    w3 = np.array(w3)
    assert np.all(np.diff(w3) <= 1e-18), w3
    assert w3[-1] == 0.0


def test_fixed_mode_linker_optimum_differs_from_disordered():
    """Sabit geometride optimum m* = d^2; düzensiz yüzeyde m* = 3 dz^2.

    Fark, hangi niceliğin girdiği: sabit geometride 3B yoğunluk
    P(d) ~ m^{-3/2} exp(-3d^2/2m), düzensiz yüzeyde düzlemsel marjinal
    A(dz) ~ m^{-1/2} exp(-3 dz^2/2m). Üs farkı optimumu 3 kat kaydırır.
    """
    sep = 6.0           # R1-R2 ve R2-R3 ayrımı 3 nm
    d = sep / 2
    lp, rise = 0.5, 0.365
    res = np.array([6, 10, 16, 20, 26, 34, 46, 64, 90])
    w3 = []
    for r in res:
        eq = build_fixed(sep, linker_res=int(r)).solve(1e-6)
        w3.append(eq.p_state([0, 1, 2]) * eq.total)
    w3 = np.array(w3)
    k = int(np.argmax(w3))
    assert k not in (0, len(w3) - 1), w3

    lc_found = res[k] * rise
    lc_pred = d**2 / (2 * lp)          # m* = d^2,  m = 2 lp Lc
    assert lc_found == pytest.approx(lc_pred, rel=0.45)
    # düzensiz moddaki tahminden belirgin biçimde farklı olmalı
    assert lc_found < 0.6 * (3 * d**2 / (2 * lp))
