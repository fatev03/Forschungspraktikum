#@title Trivalent joint geometry: three receptors, receptor-spacing sweep (CPU, seconds)
pair_specs = "GIPR:/content/boltz_out/gipr_ecd_best.pdb:A:B; GLP1R:/content/boltz_out/glp1r_ecd_best.pdb:A:B; GCGR:/content/boltz_out/gcgr_ecd_best.pdb:A:B"  #@param {type:"string"}
linker_lengths = "25,25"     #@param {type:"string"}
kd_mono_nM = "500,2000,5000" #@param {type:"string"}
spacing_nm = "5,8,10,13,16,20,25,30" #@param {type:"string"}
iface_cutoff_A = 8.0 #@param {type:"number"}
clash_cutoff = 2.5   #@param {type:"number"}

# ---------------------------------------------------------------------------
# Why this cell exists
#
# The original geometry cell pools every target chain into ONE point cloud and
# takes ONE kd_mono_nM. With three DIFFERENT receptors that breaks two ways:
#   1. a binder's "distance to target" is measured against whichever receptor
#      happens to be nearest, not against its own receptor;
#   2. one Kd cannot describe three arms with different affinities.
# It also reads the binder-to-binder gap out of the coordinates, which only
# means something if all three receptors sit in one structure at their true
# relative positions. No such structure exists.
#
# This cell instead reads the three PAIRWISE complexes (one per receptor) and
# treats receptor spacing as a swept parameter. Per spacing it brackets each
# linker's gap between the best and worst terminus orientation, so the answer
# is a range with stated assumptions rather than one invented number.
#
# Assumptions, stated in the output as well:
#   - the three receptors are collinear and equally spaced on the membrane;
#   - spacing is measured between adjacent binding-site (interface) centroids;
#   - best case = both termini point at each other, worst case = both point away.
#
# Polymer physics identical to the original cell (Kohn et al. 2004 scaling,
# Gaussian-chain Ceff), so numbers stay comparable.
# ---------------------------------------------------------------------------
import numpy as np
import pandas as pd

COIL_RG_PREFACTOR = 1.927
COIL_RG_EXPONENT = 0.598
EXTENDED_PER_RES = 3.5
A3_TO_MOLAR = 1660.5388
MSQ_PREFACTOR = 6.0 * COIL_RG_PREFACTOR ** 2
MSQ_EXPONENT = 2.0 * COIL_RG_EXPONENT


def mean_sq_ee(n):
    return MSQ_PREFACTOR * np.power(np.asarray(n, dtype=float), MSQ_EXPONENT)


def coil_span(n):
    return np.sqrt(mean_sq_ee(n))


def extended_span(n):
    return EXTENDED_PER_RES * np.asarray(n, dtype=float)


def ceff_molar(d, n):
    u = mean_sq_ee(n)
    p = (3.0 / (2.0 * np.pi * u)) ** 1.5 * np.exp(-3.0 * d * d / (2.0 * u))
    return p * A3_TO_MOLAR


def optimal_linker(d):
    return float((d * d / MSQ_PREFACTOR) ** (1.0 / MSQ_EXPONENT))


# --- minimal PDB reader (no biopython dependency) --------------------------
def read_chains(path):
    """{chain: {"ca": Nx3, "heavy": Mx3, "nres": int}} from ATOM records."""
    ca, heavy = {}, {}
    with open(path) as fh:
        for line in fh:
            if not line.startswith("ATOM") or len(line) < 54:
                continue
            if line[16] not in (" ", "A"):
                continue
            name = line[12:16].strip()
            elem = line[76:78].strip() if len(line) >= 78 else ""
            if elem == "H" or (not elem and name.startswith("H")):
                continue
            ch = line[21]
            xyz = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
            heavy.setdefault(ch, []).append(xyz)
            if name == "CA":
                ca.setdefault(ch, []).append(xyz)
    out = {}
    for ch in heavy:
        out[ch] = {
            "ca": np.asarray(ca.get(ch, []), dtype=float),
            "heavy": np.asarray(heavy[ch], dtype=float),
            "nres": len(ca.get(ch, [])),
        }
    return out


def min_dists(a, b):
    """For each row of a, distance to the nearest row of b."""
    if len(a) == 0 or len(b) == 0:
        return np.full(len(a), np.nan)
    d = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1))
    return d.min(axis=1)


def parse_pairs(spec):
    pairs = []
    for part in spec.split(";"):
        part = part.strip()
        if not part:
            continue
        bits = [x.strip() for x in part.split(":")]
        if len(bits) != 4:
            raise ValueError("each pair needs name:pdb:target_chain:binder_chain, got %r" % part)
        pairs.append({"name": bits[0], "pdb": bits[1], "tgt": bits[2], "bnd": bits[3]})
    return pairs


def parse_floats(s):
    return [float(x) for x in s.replace(" ", "").split(",") if x]


def analyse_pair(p, iface_cutoff):
    chains = read_chains(p["pdb"])
    for key in ("tgt", "bnd"):
        if p[key] not in chains:
            raise ValueError("%s: chain %s not in %s (found %s)"
                             % (p["name"], p[key], p["pdb"], sorted(chains)))
    b, t = chains[p["bnd"]], chains[p["tgt"]]
    ca = b["ca"]
    if len(ca) < 2:
        raise ValueError("%s: binder chain %s has %d CA atoms" % (p["name"], p["bnd"], len(ca)))

    d_ca_to_tgt = min_dists(ca, t["heavy"])
    mask = d_ca_to_tgt < iface_cutoff
    centroid = ca.mean(axis=0)
    iface_centroid = ca[mask].mean(axis=0) if mask.any() else centroid

    away = centroid - iface_centroid
    nrm = float(np.linalg.norm(away))

    def outward(term):
        if nrm < 1e-6:
            return float("nan")
        v = term - centroid
        nv = float(np.linalg.norm(v))
        return float(np.dot(v, away) / (nv * nrm)) if nv > 1e-6 else float("nan")

    n_term, c_term = ca[0], ca[-1]
    pair_clash = int((min_dists(b["heavy"], t["heavy"]) < clash_cutoff).sum())

    return {
        "name": p["name"],
        "pdb": p["pdb"],
        "nres": b["nres"],
        "n_off": float(np.linalg.norm(n_term - iface_centroid)),
        "c_off": float(np.linalg.norm(c_term - iface_centroid)),
        "n_to_tgt": float(min_dists(n_term[None, :], t["heavy"])[0]),
        "c_to_tgt": float(min_dists(c_term[None, :], t["heavy"])[0]),
        "n_outward": outward(n_term),
        "c_outward": outward(c_term),
        "body_span": float(np.linalg.norm(c_term - n_term)),
        "iface_res": int(mask.sum()),
        "clash_atoms": pair_clash,
    }


def run():
    pairs = parse_pairs(pair_specs)
    links = [int(x) for x in parse_floats(linker_lengths)]
    kds = parse_floats(kd_mono_nM)
    grid = parse_floats(spacing_nm)

    if len(links) != len(pairs) - 1:
        raise ValueError("%d arms need %d linkers, got %d" % (len(pairs), len(pairs) - 1, len(links)))
    if len(kds) != len(pairs):
        raise ValueError("%d arms need %d Kd values, got %d" % (len(pairs), len(pairs), len(kds)))

    arms = [analyse_pair(p, iface_cutoff_A) for p in pairs]

    print("ARM GEOMETRY (each binder measured against ITS OWN receptor)")
    print(pd.DataFrame([{
        "arm": a["name"],
        "binder res": a["nres"],
        "iface res": a["iface_res"],
        "N-C span (A)": round(a["body_span"], 1),
        "N off-centre (A)": round(a["n_off"], 1),
        "C off-centre (A)": round(a["c_off"], 1),
        "N to target (A)": round(a["n_to_tgt"], 1),
        "C to target (A)": round(a["c_to_tgt"], 1),
        "N outward": round(a["n_outward"], 2),
        "C outward": round(a["c_outward"], 2),
        "clash atoms": a["clash_atoms"],
    } for a in arms]).to_string(index=False))
    print()
    print("  'off-centre' is the terminus distance from that binder's own interface centroid;")
    print("  it sets how much the linker gap differs from the bare receptor spacing.")
    print("  A 'to target' distance below 8 A means fusing at that terminus may disturb the interface.")
    print("  outward ranges -1..+1; positive means the terminus points away from the interface.")
    print()

    print("FUSION ORDER: " + " -- L1 -- ".join([arms[0]["name"]])
          + "".join([" -- L%d -- %s" % (i + 1, arms[i + 1]["name"]) for i in range(len(links))]))
    print("linker residues: %s | monovalent Kd (nM): %s" % (links, kds))
    print()

    rows = []
    for s_nm in grid:
        s = s_nm * 10.0
        joint_ok, gains_best, gains_worst, detail = True, [], [], []
        for i, n in enumerate(links):
            gap_best = max(s - arms[i]["c_off"] - arms[i + 1]["n_off"], 0.0)
            gap_worst = s + arms[i]["c_off"] + arms[i + 1]["n_off"]
            ext = float(extended_span(n))
            ok = gap_worst <= ext
            joint_ok = joint_ok and ok
            ce_best = float(ceff_molar(gap_best, n))
            ce_worst = float(ceff_molar(gap_worst, n)) if ok else 0.0
            n_opt_i = int(round(optimal_linker(max(gap_best, 1.0))))
            kd_next = kds[i + 1] * 1e-9
            gains_best.append(ce_best / kd_next)
            gains_worst.append(ce_worst / kd_next)
            detail.append({
                "spacing (nm)": s_nm,
                "linker": "L%d %s->%s" % (i + 1, arms[i]["name"], arms[i + 1]["name"]),
                "residues": n,
                "gap best (A)": round(gap_best, 1),
                "gap worst (A)": round(gap_worst, 1),
                "RMS span (A)": round(float(coil_span(n)), 1),
                "max span (A)": round(ext, 1),
                "optimal res (best gap)": n_opt_i,
                "length assessment": ("too short" if n < 0.5 * n_opt_i
                                      else "unnecessarily long" if n > 2.0 * n_opt_i
                                      else "suitable"),
                "Ceff best (uM)": round(ce_best * 1e6, 2),
                "Ceff worst (uM)": round(ce_worst * 1e6, 2),
                "worst case reachable": "yes" if ok else "NO",
            })
        rows.append({
            "spacing (nm)": s_nm,
            "all linkers reach (worst case)": "yes" if joint_ok else "NO",
            "trivalent gain, best": round(float(np.prod(gains_best)), 1),
            "trivalent gain, worst": round(float(np.prod(gains_worst)), 1),
            "_detail": detail,
        })

    print("PER-LINKER BRACKET ACROSS THE SPACING GRID")
    flat = [d for r in rows for d in r["_detail"]]
    print(pd.DataFrame(flat).to_string(index=False))
    print()

    print("JOINT VERDICT PER SPACING (all three arms engaged at once)")
    print(pd.DataFrame([{k: v for k, v in r.items() if k != "_detail"} for r in rows]).to_string(index=False))
    print()
    print("  Trivalent gain = product over the two later binding events of Ceff / Kd of that arm.")
    print("  It uses the three separate Kd values, which one kd_mono_nM cannot represent.")
    print("  UPPER BOUND: strain, entropy loss and steric hindrance are omitted.")
    print("  'worst case' assumes both termini point away from each other; a gain of 0 means")
    print("  that orientation is out of reach and the construct depends on favourable geometry.")
    print()

    feasible = [r for r in rows if r["all linkers reach (worst case)"] == "yes"]
    print("REACHABLE SPACING WINDOW")
    if feasible:
        lo = min(r["spacing (nm)"] for r in feasible)
        hi = max(r["spacing (nm)"] for r in feasible)
        s_best = hi
        print("  all three arms reach at once from %.1f to %.1f nm receptor spacing," % (lo, hi))
        print("  even when both termini point away from each other.")
        if hi == max(r["spacing (nm)"] for r in rows):
            print("  NOTE: %.1f nm is the top of the grid, so the real limit may be wider." % hi)
        print("  Avidity gain is largest at the tightest spacing and falls as spacing grows,")
        print("  so the two ends of this window are the optimistic and the conservative case.")
        print("  Exporting at %.1f nm, the conservative end: Ceff there is the floor, not the peak." % s_best)
    else:
        s_best = min(r["spacing (nm)"] for r in rows)
        print("  NO spacing on the grid lets all three arms reach in the worst orientation.")
        print("  The construct would depend on favourable terminus orientation, or on longer linkers.")
        print("  Try longer linkers, or swap which terminus each arm is fused at.")
        print("  Exporting at %.1f nm (tightest grid point) so the next cell still has inputs;" % s_best)
        print("  treat those numbers as best case only.")
    print()

    if not links:
        print("Only one arm: no linker, no Ceff and no trivalent gain to report.")
        print("Nothing is exported for the selectivity cell; run this with the full")
        print("fusion order to get ARM_REACH_NM and CEFF_M.")
        return {"arms": arms, "rows": rows, "ARM_REACH_NM": None,
                "ARM_REACH_WITH_BODY_NM": None, "CEFF_M": None,
                "spacing_nm": s_best}

    gaps_best = [max(s_best * 10.0 - arms[i]["c_off"] - arms[i + 1]["n_off"], 0.0)
                 for i in range(len(links))]
    ARM_REACH_NM = float(np.mean([coil_span(n) for n in links])) / 10.0
    ARM_REACH_WITH_BODY_NM = ARM_REACH_NM + float(np.mean([a["body_span"] for a in arms])) / 10.0
    ceffs = [float(ceff_molar(g, n)) for g, n in zip(gaps_best, links)]
    CEFF_M = float(np.exp(np.mean(np.log(np.maximum(ceffs, 1e-30)))))

    print("EXPORTED FOR THE SELECTIVITY CELL")
    print("  ARM_REACH_NM            = %.1f   (linker RMS span only, same definition as the original cell)" % ARM_REACH_NM)
    print("  ARM_REACH_WITH_BODY_NM  = %.1f   (linker + mean binder body; use if you want the arm's full reach)" % ARM_REACH_WITH_BODY_NM)
    print("  CEFF_M                  = %.3g  (geometric mean over arms, best-case gaps)" % CEFF_M)
    print("  ceff_uM                 = %.2f" % (CEFF_M * 1e6))
    print()
    print("  Paste into the selectivity cell (valency placeholder v, set per construct copy count):")
    print('    binders = "%s"' % ", ".join("%s:%g:v" % (a["name"], k) for a, k in zip(arms, kds)))
    print()
    print("  The geometric mean is used because the arms bind sequentially: one weak link")
    print("  limits the chain, and an arithmetic mean would hide it.")

    return {"arms": arms, "rows": rows, "ARM_REACH_NM": ARM_REACH_NM,
            "ARM_REACH_WITH_BODY_NM": ARM_REACH_WITH_BODY_NM, "CEFF_M": CEFF_M,
            "spacing_nm": s_best}


TRIJOINT = run()