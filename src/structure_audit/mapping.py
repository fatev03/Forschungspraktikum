"""Explicit supplied-sequence mappings; no automatic alignment or renumbering."""
from .structures import UnsupportedFormat, selected_atoms

BACKBONE = ("N", "CA", "C", "O")
AA = dict(zip("ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL".split(),
              "ARNDCQEGHILKMFPSTWYV"))


def canonical_residue_map(structure, *, altloc="A"):
    rows = []
    for residue in structure.residues:
        first = residue.atoms[0]
        selected, warnings = selected_atoms(residue, altloc)
        if first.group == "ATOM" and residue.name not in AA:
            warnings.append("unknown/nonstandard polymer residue; sequence identity unsupported")
        rows.append({
            "residue_index": residue.index, "model_id": first.model_id,
            "chain_id": first.chain_id, "segment": first.segment,
            "record_group": first.group, "residue_id": first.residue_id,
            "insertion_code": first.insertion_code, "residue_name": residue.name,
            "label_chain_id": first.label_chain_id, "label_seq_id": first.label_seq_id,
            "source_lines": [a.line for a in residue.atoms],
            "atom_names": sorted(selected), "selected_altloc": altloc,
            "missing_backbone_atoms": [a for a in BACKBONE if a not in selected] if first.group == "ATOM" else [],
            "warnings": warnings,
        })
    return rows


def validate_sequence_mapping(structure, supplied_sequence, entries):
    """Validate a one-to-one mapping for every supplied position (one-based).

    entries: [{sequence_position, residue_index: int|null, reason: str|null}].
    residue_index references the canonical table, so insertion codes and repeated
    author IDs are never discarded. None means explicitly missing/unmapped.
    """
    if not isinstance(supplied_sequence, str) or not supplied_sequence or any(c not in AA.values() for c in supplied_sequence):
        raise UnsupportedFormat("mapping requires an uppercase standard-amino-acid supplied sequence")
    if not isinstance(entries, list) or len(entries) != len(supplied_sequence):
        raise ValueError("Explicit mapping must contain every supplied sequence position")
    positions, used, result = set(), set(), []
    identities = {}
    for residue in structure.residues:
        identities.setdefault(residue.key, []).append(residue.index)
    for entry in entries:
        if set(entry) != {"sequence_position", "residue_index", "reason"}:
            raise ValueError("Mapping fields must be sequence_position, residue_index, reason")
        pos, idx = entry["sequence_position"], entry["residue_index"]
        if type(pos) is not int or pos < 1 or pos > len(supplied_sequence) or pos in positions:
            raise ValueError("Invalid/duplicate sequence position")
        if entry["reason"] is not None and not isinstance(entry["reason"], str):
            raise ValueError("Mapping reason must be a string or null")
        positions.add(pos)
        if idx is None:
            if not entry["reason"]:
                raise ValueError("Unmapped position requires a reason")
            status = "missing_or_unmapped"
        else:
            if type(idx) is not int or not 0 <= idx < len(structure.residues) or idx in used:
                raise ValueError("Invalid or multiply mapped residue_index")
            used.add(idx)
            residue = structure.residues[idx]
            if len(identities[residue.key]) > 1:
                raise UnsupportedFormat("duplicate residue identity prevents unambiguous sequence mapping")
            if residue.key[3] != "ATOM" or residue.name not in AA:
                raise UnsupportedFormat("mapping nonstandard or HETATM residue requires external residue definitions")
            status = "matched" if AA[residue.name] == supplied_sequence[pos-1] else "mismatch"
        result.append({**entry, "status": status})
    return sorted(result, key=lambda r: r["sequence_position"])
