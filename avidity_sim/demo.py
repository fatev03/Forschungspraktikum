"""Üç-domainli bir kaset üzerinde tam analiz akışı.

Çalıştır:  .venv/bin/python demo.py
Üretir:    figures/*.png  ve stdout'a metin rapor
"""

from __future__ import annotations

import os

import numpy as np

from avidity.kinetics import kinetic_avidity, residence_analysis, washout
from avidity.model import (
    Cassette,
    Domain,
    Receptor,
    Surface,
    System,
    apparent_kd,
    avidity_enhancement,
    monovalent_reference,
    state_density_profile,
    titration,
)
from avidity.sweep import (
    density,
    height,
    kd,
    linker_contour,
    log_sensitivity,
    obs_density_all_bound,
    obs_p_at_least,
    obs_residence,
    obs_total,
    persistence_length,
    sweep_2d,
)
from avidity.tether import peptide_linker

FIG = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(FIG, exist_ok=True)


def build() -> System:
    """D1 -L12- D2 -L23- D3 kaseti, üç reseptörlü düzensiz yüzey."""
    domains = [
        Domain("D1", kd=1.0e-6, k_on=1e5, span=2.5),
        Domain("D2", kd=3.0e-7, k_on=1e5, span=2.5),
        Domain("D3", kd=2.0e-6, k_on=1e5, span=2.5),
    ]
    linkers = [peptide_linker(40), peptide_linker(40)]
    receptors = [
        Receptor("R1", density=2.0e-3, height=4.0),  # 2000 / um^2
        Receptor("R2", density=1.0e-3, height=6.0),  # 1000 / um^2
        Receptor("R3", density=5.0e-4, height=3.0),  #  500 / um^2
    ]
    return System(Cassette(domains, linkers), Surface(receptors))


def hr(title: str) -> None:
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def report(sysm: System, conc: float) -> None:
    names = [d.name for d in sysm.cassette.domains]

    hr("1. TETHER GEOMETRİSİ  (state ağırlıklarına giren tek geometrik girdi)")
    print(f"{'çift':<8}{'kontur':>9}{'rms':>8}{'dz':>7}{'A(dz)':>12}{'c_eff@sigma':>14}")
    print(f"{'':8}{'[nm]':>9}{'[nm]':>8}{'[nm]':>7}{'[1/nm]':>12}{'[M]':>14}")
    for row in sysm.reach_summary():
        i, j = row["pair"]
        ce = sysm.c_eff(i, j, np.array([r.density for r in sysm.surface.receptors]))
        print(
            f"{names[i]}-{names[j]:<4}{row['contour_nm']:>9.1f}{row['rms_nm']:>8.2f}"
            f"{row['dz_nm']:>7.1f}{row['areal_reach_per_nm']:>12.3e}{ce:>14.3e}"
        )
    print("\n  Yorum: c_eff / K_D oranı, o kapanış bağının 'avidite kazancı'dır.")
    for i, j in [(0, 1), (1, 2), (0, 2)]:
        ce = sysm.c_eff(i, j, np.array([r.density for r in sysm.surface.receptors]))
        print(f"    {names[i]}->{names[j]}:  c_eff/K_D = {ce / sysm.cassette.domains[j].kd:9.1f}")

    hr(f"2. DENGE DURUM DAĞILIMI  ([L] = {conc:.1e} M)")
    eq = sysm.solve(conc)
    print(f"{'durum':<14}{'valans':>8}{'yoğunluk [1/um^2]':>20}{'fraksiyon':>12}")
    for row in eq.table():
        print(
            f"{row['state']:<14}{row['valency']:>8}"
            f"{row['weight']*1e6:>20.4g}{row['fraction']:>12.4f}"
        )
    print(f"\n  toplam bağlı      = {eq.total*1e6:.4g} /um^2")
    print(f"  ortalama valans   = {eq.mean_valency():.3f}")
    print(f"  P(>=2 bağ)        = {eq.p_at_least(2):.4f}")
    print(f"  P(3 bağ)          = {eq.p_at_least(3):.4f}")
    print(f"  reseptör doluluğu = {np.array2string(eq.receptor_occupancy(), precision=4)}")
    print(f"  çözücü artığı     = {eq.residual:.2e} (nfev={eq.iterations})")

    print("\n  Koşullu bağlanma:")
    print(f"    P(D2 | D1)        = {eq.p_conditional(1, [0]):.4f}")
    print(f"    P(D3 | D1,D2)     = {eq.p_conditional(2, [0, 1]):.4f}")
    print(f"    P(D3 | D1)        = {eq.p_conditional(2, [0]):.4f}")
    print(f"    P(D1 | D3)        = {eq.p_conditional(0, [2]):.4f}")

    hr("3. AVİDİTE: DENGE VE KİNETİK")
    av = avidity_enhancement(sysm, conc)
    print("  Denge (toplam bağlı ligand):")
    for k, v in av["monovalent_totals"].items():
        print(f"    yalnız {k:<4} -> {v*1e6:12.4g} /um^2")
    print(f"    üçlü kaset -> {av['multivalent_total']*1e6:12.4g} /um^2")
    print(f"    kazanç (en iyi monovalente göre) = {av['enhancement']:.1f}x")

    ka = kinetic_avidity(sysm, conc)
    print("\n  Kinetik (yüzeyde ortalama kalma süresi):")
    for k, v in ka["monovalent_tau_s"].items():
        print(f"    yalnız {k:<4} -> {v:12.4g} s")
    print(f"    üçlü kaset -> {ka['tau_entry_s']:12.4g} s")
    print(f"    kazanç = {ka['residence_enhancement']:.1f}x")
    print(f"    etkin k_off = {ka['k_off_eff_per_s']:.3e} 1/s")
    print("    gevşeme modları [1/s]: "
          + ", ".join(f"{r:.3e}" for r in ka["relaxation_rates_per_s"]))

    ec = apparent_kd(sysm)
    print(f"\n  Görünür EC50 (toplam bağlanma) = {ec['ec50']:.3e} M"
          f"   (plato {ec['plateau']*1e6:.4g} /um^2)")
    print(f"  En güçlü monovalent K_D        = "
          f"{min(d.kd for d in sysm.cassette.domains):.1e} M")
    print("  -> EC50 avidite'yi ÖLÇMEZ: plato reseptör kapasitesiyle belirlenir ve")
    print("     yüksek [L]'de her reseptöre ayrı bir ligand monovalent bağlanır.")

    hr("4. PROZONE (HOOK) ETKİSİ")
    prof = state_density_profile(sysm, [0, 1, 2], lo=1e-15, hi=1e-3, n_points=70)
    print("  Üçlü-bağlı yoğunluk derişimde MONOTON DEĞİL:")
    print(f"    tepe   [L] = {prof['peak_conc']:.3e} M")
    print(f"    tepede rho = {prof['peak_density']*1e6:.4g} /um^2")
    print(f"    1e-3 M'de  = {prof['density'][-1]*1e6:.4g} /um^2"
          f"  ({prof['density'][-1]/prof['peak_density']*100:.1f}% tepenin)")
    print("\n  Neden: ligand fazlası reseptörleri tek tek işgal eder; çoklu")
    print("  bağlanma için ortak reseptör kalmaz. 'Daha çok ligand her zaman")
    print("  daha çok üçlü bağlanma' yanlıştır -- optimum bir doz vardır.")

    hr("5. YEREL DUYARLILIK  d ln(y) / d ln(theta)")
    params = [kd(0), kd(1), kd(2), density(0), density(1), density(2),
              height(0), height(1), height(2),
              linker_contour(0), linker_contour(1),
              persistence_length(0), persistence_length(1)]
    obs = {
        "rho(3 bağlı)": obs_density_all_bound,
        "toplam bağlı": obs_total,
        "ikamet süresi": obs_residence,
    }
    low = 1e-13  # düşük doluluk: duyarlılıklar doygunlukla maskelenmesin
    print(f"  (düşük doluluk rejiminde, [L] = {low:.0e} M)\n")
    head = f"{'parametre':<16}" + "".join(f"{k:>16}" for k in obs)
    print(head)
    print("-" * len(head))
    rows = {}
    for name, f in obs.items():
        rows[name] = log_sensitivity(sysm, low, f, params)
    for p in params:
        line = f"{p.name:<16}"
        for name in obs:
            line += f"{rows[name][p.name]:>16.3f}"
        print(line)
    print("\n  Okuma: 1.0 = parametre %1 artınca gözlenebilir %1 artar.")
    print("  P(>=2) burada raporlanmıyor: bu rejimde 1'e doymuş, türevi sıfır.")
    return eq


def figures(sysm: System, conc: float) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"figure.dpi": 130, "font.size": 9,
                         "axes.grid": True, "grid.alpha": 0.25})
    names = [d.name for d in sysm.cassette.domains]

    # --- Şekil 1: titrasyon -------------------------------------------------
    cs = np.logspace(-15, -4, 90)
    tt = titration(sysm, cs)
    monos = {
        d.name: np.array([monovalent_reference(sysm, float(c), i).total for c in cs])
        for i, d in enumerate(sysm.cassette.domains)
    }

    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    rho3 = np.array([sysm.solve(float(c)).p_state(range(sysm.n)) for c in cs])
    rho3 = rho3 * tt["total"]
    ax[0].loglog(cs, tt["total"] * 1e6, "k-", lw=2, label="üçlü kaset, toplam")
    ax[0].loglog(cs, rho3 * 1e6, color="crimson", lw=2, label="üçlü kaset, 3 bağlı")
    k = int(np.argmax(rho3))
    ax[0].plot(cs[k], rho3[k] * 1e6, "*", color="crimson", ms=14, mec="w", mew=0.8)
    ax[0].annotate("prozone tepesi", (cs[k], rho3[k] * 1e6),
                   textcoords="offset points", xytext=(6, -16),
                   fontsize=7, color="crimson")
    for nm, v in monos.items():
        ax[0].loglog(cs, v * 1e6, "--", lw=1.1, label=f"yalnız {nm}")
    ax[0].set_xlabel("[L]  (M)")
    ax[0].set_ylabel("bağlı ligand  (1/µm²)")
    ax[0].set_title("Bağlanma izotermi")
    ax[0].legend(fontsize=7)
    ax[0].set_ylim(1e-4, None)

    for k in range(1, sysm.n + 1):
        ax[1].semilogx(cs, tt["valency"][:, k], lw=1.6, label=f"{k} bağ")
    ax[1].set_xlabel("[L]  (M)")
    ax[1].set_ylabel("bağlı ligandlar içindeki pay")
    ax[1].set_title("Valans dağılımı")
    ax[1].set_ylim(0, 1)
    ax[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(f"{FIG}/01_titrasyon.png")
    plt.close(fig)

    # --- Şekil 2: linker uzunluğu ızgarası ----------------------------------
    lc = np.linspace(3.0, 55.0, 26)
    low = 1e-13
    grid_rho = sweep_2d(sysm, low, obs_density_all_bound,
                        linker_contour(0), lc, linker_contour(1), lc)
    grid_tau = sweep_2d(sysm, low, obs_residence,
                        linker_contour(0), lc, linker_contour(1), lc)

    fig, ax = plt.subplots(1, 2, figsize=(10, 4.0))
    lp = 0.5
    dz01 = sysm.surface.dz(0, 1)
    dz12 = sysm.surface.dz(1, 2)
    pred = (3 * dz01**2 / (2 * lp), 3 * dz12**2 / (2 * lp))
    for a, g, t in [
        (ax[0], grid_rho, "üçlü-bağlı yoğunluk"),
        (ax[1], grid_tau, "ikamet süresi"),
    ]:
        gn = g.T / g.max()
        im = a.pcolormesh(lc, lc, gn, cmap="viridis", shading="auto", vmin=0, vmax=1)
        cs_ = a.contour(lc, lc, gn, levels=[0.5, 0.8, 0.9, 0.97, 0.995],
                        colors="w", linewidths=0.7)
        a.clabel(cs_, fmt="%.3g", fontsize=6)
        k = np.unravel_index(np.argmax(g), g.shape)
        a.plot(lc[k[0]], lc[k[1]], "r*", ms=15, mec="w", mew=0.9,
               label=f"sayısal ({lc[k[0]]:.0f}, {lc[k[1]]:.0f})")
        a.plot(*pred, "o", mfc="none", mec="orangered", mew=1.6, ms=11,
               label=f"analitik ({pred[0]:.0f}, {pred[1]:.0f})")
        a.set_xlabel("L₁₂ kontur (nm)")
        a.set_ylabel("L₂₃ kontur (nm)")
        a.set_title(t + "  (maksimuma göre normalize)")
        a.legend(fontsize=7, loc="lower right")
        fig.colorbar(im, ax=a)
        a.grid(False)
    fig.suptitle("Linker tarama — her linkerin optimumu köprülediği Δz ile belirlenir:"
                 "  Lc* = 3Δz²/(2ℓp)", y=1.02)
    fig.tight_layout()
    fig.savefig(f"{FIG}/02_linker_taramasi.png", bbox_inches="tight")
    plt.close(fig)

    # --- Şekil 3: dissosiyasyon ---------------------------------------------
    ra = residence_analysis(sysm.solve(conc))
    tmax = 5 * ra.tau_entry
    # monovalent (~10 s) ve çok-değerlikli (~10^4 s) ölçekler aynı grafikte
    # görünsün diye zaman ekseni logaritmik
    t = np.logspace(-2, np.log10(tmax), 600)

    fig, ax = plt.subplots(1, 2, figsize=(10, 3.8))
    ax[0].loglog(t, ra.survival(t), "k-", lw=2, label="üçlü kaset")
    for i, d in enumerate(sysm.cassette.domains):
        ax[0].loglog(t, np.exp(-d.k_off * t), "--", lw=1.1, label=f"yalnız {d.name}")
    for lbl, tau, col in [("τ mono (en iyi)", max(1 / d.k_off for d in sysm.cassette.domains), "gray"),
                          ("τ üçlü", ra.tau_entry, "k")]:
        ax[0].axvline(tau, color=col, ls=":", lw=1)
    ax[0].set_xlabel("t (s)")
    ax[0].set_ylabel("bağlı kalma olasılığı")
    ax[0].set_ylim(1e-4, 1.6)
    ax[0].set_title(f"Kaçış: tek-ligand CTMC  (τ kazancı ≈ {ra.tau_entry / max(1/d.k_off for d in sysm.cassette.domains):.0f}×)")
    ax[0].legend(fontsize=7, loc="lower left")

    tr = washout(sysm, conc, t_end=tmax)
    vc = tr.valency_curves()
    tot = tr.total()
    ax[1].plot(tr.t, tot / tot[0], "k-", lw=2, label="toplam")
    for k in range(1, sysm.n + 1):
        ax[1].plot(tr.t, vc[k] / tot[0], lw=1.2, label=f"{k} bağ")
    ax[1].set_xlabel("t (s)")
    ax[1].set_ylabel("başlangıç yoğunluğuna oran")
    ax[1].set_title("Yıkama: popülasyon ODE'si")
    ax[1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(f"{FIG}/03_dissosiyasyon.png")
    plt.close(fig)

    # --- Şekil 4: reseptör yoğunluğu senaryoları ----------------------------
    s2 = np.logspace(-5, -2, 26)
    s3 = np.logspace(-5, -2, 26)
    gd = sweep_2d(sysm, conc, obs_density_all_bound, density(1), s2, density(2), s3)
    gp = sweep_2d(sysm, conc, obs_p_at_least(3), density(1), s2, density(2), s3)

    fig, ax = plt.subplots(1, 2, figsize=(10, 4.0))
    im = ax[0].pcolormesh(s2 * 1e6, s3 * 1e6, np.log10(np.maximum(gd.T * 1e6, 1e-6)),
                          cmap="viridis", shading="auto")
    ax[0].set_title("log₁₀ ρ(3 bağlı)   [1/µm²]")
    fig.colorbar(im, ax=ax[0])

    im = ax[1].pcolormesh(s2 * 1e6, s3 * 1e6, gp.T, cmap="magma",
                          vmin=0, vmax=1, shading="auto")
    cs_ = ax[1].contour(s2 * 1e6, s3 * 1e6, gp.T, levels=[0.3, 0.5, 0.7, 0.9],
                        colors="w", linewidths=0.7)
    ax[1].clabel(cs_, fmt="%.1f", fontsize=6)
    ax[1].set_title("P(3 bağ | ligand bağlı)")
    fig.colorbar(im, ax=ax[1])

    for a_ in ax:
        a_.set_xscale("log")
        a_.set_yscale("log")
        a_.set_xlabel("σ(R2)  (1/µm²)")
        a_.set_ylabel("σ(R3)  (1/µm²)")
        a_.plot(sysm.surface.receptors[1].density * 1e6,
                sysm.surface.receptors[2].density * 1e6,
                "wo", mec="k", ms=7, label="temel senaryo")
        a_.legend(fontsize=7, loc="lower right")
        a_.grid(False)
    fig.suptitle("Seçicilik: hangi reseptör bağlamında üçlü bağlanmaya geçiliyor?"
                 "  (σ(R1) = 2000/µm² sabit)", y=1.02)
    fig.tight_layout()
    fig.savefig(f"{FIG}/04_secicilik.png", bbox_inches="tight")
    plt.close(fig)

    # --- Şekil 5: duyarlılık tornado ----------------------------------------
    params = [kd(0), kd(1), kd(2), density(0), density(1), density(2),
              height(0), height(1), height(2),
              linker_contour(0), linker_contour(1)]
    sens = log_sensitivity(sysm, 1e-13, obs_density_all_bound, params)
    items = sorted(sens.items(), key=lambda kv: abs(kv[1]))
    fig, a = plt.subplots(figsize=(5.6, 4.2))
    vals = [v for _, v in items]
    a.barh([k for k, _ in items], vals,
           color=["#c44" if v < 0 else "#268" for v in vals])
    a.axvline(0, color="k", lw=0.8)
    a.set_xlabel("d ln ρ(3 bağlı) / d ln θ")
    a.set_title("Yerel duyarlılık")
    fig.tight_layout()
    fig.savefig(f"{FIG}/05_duyarlilik.png")
    plt.close(fig)

    print(f"\n  Şekiller: {FIG}/")


if __name__ == "__main__":
    system = build()
    conc = 1e-10
    report(system, conc)
    figures(system, conc)
