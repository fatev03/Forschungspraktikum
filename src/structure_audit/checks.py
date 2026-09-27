"""Format/geometric plausibility checks only; no binding or function predictions."""
import math
from dataclasses import asdict, dataclass

from . import __version__
from .mapping import canonical_residue_map
from .structures import selected_atoms

LABEL = "format/geometric plausibility only"


@dataclass
class CheckResult:
    check: str
    status: str
    metrics: dict
    configuration: dict
    messages: list
    provenance: dict
    category: str = LABEL

    def to_dict(self):
        return asdict(self)


def _result(structure, check, status, metrics, configuration, messages):
    return CheckResult(check, status, metrics, configuration, messages,
                       {"utility_version": __version__, "check_version": "1.0",
                        "input_path": structure.source, "input_sha256": structure.source_hash,
                        "model_id": structure.model_id})


def _finite(atom):
    return all(math.isfinite(x) for x in atom.xyz)


def _config(defaults, config):
    config = dict(config or {})
    if set(config) - set(defaults):
        raise ValueError(f"Unknown check configuration: {sorted(set(config)-set(defaults))}")
    return {**defaults, **config}


def _positive(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")


def structure_integrity_check(structure, config=None):
    cfg = _config({"altloc": "A", "max_peptide_cn_distance": 2.0, "expected_residues": []}, config)
    _positive(cfg["max_peptide_cn_distance"], "max_peptide_cn_distance")
    rows = canonical_residue_map(structure, altloc=cfg["altloc"])
    messages = [dict(w) for w in structure.warnings]
    invalid = sum(not _finite(a) for a in structure.atoms)
    duplicate = sum(w["code"] in ("duplicate_residue_id", "duplicate_atom_id") for w in messages)
    missing_atoms, breaks, gaps, unavailable, ter_boundaries = [], [], [], 0, 0
    previous = {}
    selected_by_index = {}
    for row, residue in zip(rows, structure.residues):
        if row["record_group"] != "ATOM":
            continue
        selected, _ = selected_atoms(residue, cfg["altloc"])
        selected_by_index[residue.index] = selected
        if row["missing_backbone_atoms"]:
            missing_atoms.append({"residue_index": residue.index, "atoms": row["missing_backbone_atoms"]})
        messages.extend({"code": "residue_warning", "residue_index": residue.index, "message": m} for m in row["warnings"])
        chain = row["chain_id"]
        if chain in previous:
            prev = previous[chain]
            if prev["segment"] != row["segment"]:
                ter_boundaries += 1
            else:
                delta = row["residue_id"] - prev["residue_id"]
                if delta > 1:
                    gaps.append({"after_index": prev["residue_index"], "before_index": residue.index,
                                 "numbering_gap_size": delta-1})
                if delta < 0:
                    messages.append({"code": "nonmonotonic_numbering", "message": f"Residue {residue.index}: numbering decreases"})
                c_atom = selected_by_index[prev["residue_index"]].get("C")
                n_atom = selected.get("N")
                if c_atom is None or n_atom is None or not _finite(c_atom) or not _finite(n_atom):
                    unavailable += 1
                else:
                    distance = math.dist(c_atom.xyz, n_atom.xyz)
                    if distance > cfg["max_peptide_cn_distance"]:
                        breaks.append({"after_index": prev["residue_index"], "before_index": residue.index,
                                       "cn_distance_angstrom": distance})
        previous[chain] = row
    expected = cfg["expected_residues"]
    if not isinstance(expected, list):
        raise ValueError("expected_residues must be a list")
    observed = {(r["chain_id"], r["residue_id"], r["insertion_code"]) for r in rows if r["record_group"] == "ATOM"}
    missing_residues, seen = [], set()
    for entry in expected:
        if not isinstance(entry, dict) or set(entry) != {"chain_id", "residue_id", "insertion_code"}:
            raise ValueError("Expected residue needs chain_id, residue_id, insertion_code")
        if not isinstance(entry["chain_id"], str) or type(entry["residue_id"]) is not int or not isinstance(entry["insertion_code"], str):
            raise ValueError("Invalid expected residue identity")
        key = (entry["chain_id"], entry["residue_id"], entry["insertion_code"])
        if key in seen:
            raise ValueError("Duplicate expected residue identity")
        seen.add(key)
        if key not in observed:
            missing_residues.append(entry)
    polymer_count = sum(r["record_group"] == "ATOM" for r in rows)
    for code, count, message in [
        ("missing_backbone_atoms", len(missing_atoms), "Required N/CA/C/O atoms missing or not uniquely selectable"),
        ("numbering_gap", len(gaps), "Numbering gaps are possible omissions, not proof of missing residues"),
        ("missing_expected_residue", len(missing_residues), "User-supplied expected residue absent"),
        ("geometric_chain_break", len(breaks), "Observed neighboring peptide C-N distance exceeds threshold"),
        ("unavailable_chain_continuity", unavailable, "Continuity not evaluable for some neighbors"),
        ("ter_boundary", ter_boundaries, "Explicit TER boundary; not treated as a peptide bond"),
        ("invalid_coordinates", invalid, "Non-finite coordinates"),
    ]:
        if count:
            messages.append({"code": code, "count": count, "message": message})
    if not expected:
        messages.append({"code": "completeness_unknown", "message": "No expected residue inventory supplied; absolute residue completeness is not assessed"})
    if not polymer_count:
        messages.append({"code": "no_polymer_records", "message": "No ATOM polymer records to evaluate"})
    status = "fail" if invalid or duplicate else "warn" if messages else "pass"
    return _result(structure, "structure_integrity_check", status,
                   {"atom_count": len(structure.atoms), "residue_count": len(rows),
                    "polymer_residue_count": polymer_count, "invalid_coordinate_count": invalid,
                    "duplicate_id_warning_count": duplicate, "missing_backbone": missing_atoms,
                    "missing_expected_residues": missing_residues, "numbering_gaps": gaps,
                    "chain_breaks": breaks, "unavailable_neighbor_count": unavailable,
                    "ter_boundary_count": ter_boundaries}, cfg, messages)


def coarse_steric_clash_check(structure, config=None):
    cfg = _config({"altloc": "A", "cutoff_angstrom": 2.0, "scope": "interchain",
                   "fail_at_count": None, "max_reported_pairs": 100}, config)
    _positive(cfg["cutoff_angstrom"], "cutoff_angstrom")
    if cfg["scope"] not in ("interchain", "nonlocal"):
        raise ValueError("scope must be interchain or nonlocal")
    for key in ("fail_at_count", "max_reported_pairs"):
        if cfg[key] is None and key == "fail_at_count":
            continue
        if type(cfg[key]) is not int or cfg[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    atoms, messages, excluded, local_order = [], [], 0, {}
    counters = {}
    for residue in structure.residues:
        if residue.key[3] != "ATOM":
            continue
        chain_seg = residue.key[1:3]
        ordinal = counters.get(chain_seg, 0)
        counters[chain_seg] = ordinal + 1
        local_order[residue.index] = ordinal
        selected, notes = selected_atoms(residue, cfg["altloc"])
        messages.extend({"code": "selection_incomplete", "message": m, "residue_index": residue.index} for m in notes)
        for atom in selected.values():
            if not _finite(atom) or not atom.element or atom.occupancy is None or not math.isfinite(atom.occupancy) or atom.occupancy <= 0:
                excluded += 1
            elif atom.element not in ("H", "D"):
                atoms.append((residue.index, atom))
    if excluded:
        messages.append({"code": "excluded_atoms", "count": excluded,
                         "message": "Missing element/occupancy, nonpositive occupancy or invalid coordinates; no inference used"})
    duplicate = any(w["code"] in ("duplicate_residue_id", "duplicate_atom_id") for w in structure.warnings)
    if duplicate:
        messages.append({"code": "duplicate_identity", "message": "Clash count is partial because duplicate identities exist"})
    # Cell list avoids an all-pairs coordinate array; detailed output is bounded.
    grid, count, pairs, evaluated = {}, 0, [], 0
    cutoff = cfg["cutoff_angstrom"]
    for idx, atom in atoms:
        cell = tuple(math.floor(v/cutoff) for v in atom.xyz)
        for x in (-1, 0, 1):
            for y in (-1, 0, 1):
                for z in (-1, 0, 1):
                    for jdx, other in grid.get((cell[0]+x, cell[1]+y, cell[2]+z), []):
                        same_chain = atom.chain_id == other.chain_id
                        if idx == jdx or (cfg["scope"] == "interchain" and same_chain):
                            continue
                        if same_chain and atom.segment == other.segment and abs(local_order[idx]-local_order[jdx]) <= 1:
                            continue
                        evaluated += 1
                        distance = math.dist(atom.xyz, other.xyz)
                        if distance < cutoff:
                            count += 1
                            if len(pairs) < cfg["max_reported_pairs"]:
                                pairs.append({"residue_indices": [jdx, idx], "atom_names": [other.atom_name, atom.atom_name],
                                              "source_lines": [other.line, atom.line], "distance_angstrom": distance})
        grid.setdefault(cell, []).append((idx, atom))
    groups = {}
    for idx, atom in atoms:
        groups.setdefault((atom.chain_id, atom.segment), set()).add(local_order[idx])
    assessable = len({a.chain_id for _, a in atoms}) > 1
    if cfg["scope"] == "nonlocal":
        assessable = len(groups) > 1 or any(max(v)-min(v) > 1 for v in groups.values())
    if not assessable:
        messages.append({"code": "no_eligible_pairs", "message": "Selected structure has no pairs in the configured scope"})
    if count:
        messages.append({"code": "close_contacts", "message": "Coarse close contacts; covalent interchain links and atom-specific radii are not modeled"})
    status = "warn" if messages else "pass"
    if cfg["fail_at_count"] is not None and count >= cfg["fail_at_count"]:
        status = "fail"
    return _result(structure, "coarse_steric_clash_check", status,
                   {"close_contact_count": count, "pairs": pairs, "pairs_truncated": count > len(pairs),
                    "selected_heavy_atom_count": len(atoms), "excluded_atom_count": excluded,
                    "nearby_pair_comparisons": evaluated, "assessable": assessable,
                    "partial": bool(excluded or duplicate or any(m["code"] == "selection_incomplete" for m in messages))},
                   cfg, messages)
