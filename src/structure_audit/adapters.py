"""Read explicit existing notebook outputs; never import or execute the notebook."""
import csv
from pathlib import Path

from .evidence import CandidateEvidence, sequence_hash, supplied_metric
from .provenance import hash_file
from .validation import read_json

_CATEGORIES = {"mpnn": "sequence_model_score", "plddt": "model_confidence",
               "i_ptm": "model_confidence", "i_pae": "model_confidence", "rmsd": "structural_comparison"}


def import_mpnn_csv(path, *, target_id, conformer_id, chain_roles, provenance,
                    metric_contexts, candidate_prefix="candidate"):
    """Import all rows. chain_roles lists target/candidate per slash-delimited chain.

    metric_contexts must explicitly label mpnn/plddt/i_ptm/i_pae/rmsd as
    monomer, complex, or counter_screen. Model mode is never inferred.
    """
    path = Path(path)
    if not chain_roles or set(chain_roles) - {"target", "candidate"} or "candidate" not in chain_roles:
        raise ValueError("Supply explicit target/candidate chain roles")
    if set(metric_contexts) != set(_CATEGORIES):
        raise ValueError("Supply context for every supported CSV metric")
    source = {"path": str(path.resolve()), "sha256": hash_file(path), "row": None}
    candidates, ids = [], set()
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("CSV headers missing or duplicated")
        if not {"design", "n", "seq"} <= set(reader.fieldnames):
            raise ValueError("CSV requires design, n and seq")
        for row_no, row in enumerate(reader, 2):
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f"CSV row {row_no}: column count mismatch")
            if not row["design"] or not row["n"]:
                raise ValueError("CSV design/n identity is empty")
            candidate_id = f"{candidate_prefix}:{row['design']}:{row['n']}"
            if candidate_id in ids:
                raise ValueError("Duplicate CSV candidate identity")
            ids.add(candidate_id)
            chains = row["seq"].split("/")
            if len(chains) != len(chain_roles) or any(not s for s in chains):
                raise ValueError("Sequence chains do not match explicit chain_roles")
            supplied = "/".join(s for s, role in zip(chains, chain_roles) if role == "candidate")
            row_source = {**source, "row": row_no}
            metrics = [supplied_metric(k, row.get(k), context=metric_contexts[k],
                                       category=v, source=row_source, provenance=provenance)
                       for k, v in _CATEGORIES.items()]
            unknown = {k: v for k, v in row.items() if k not in {*_CATEGORIES, "seq", "design", "n"}}
            if unknown:
                metrics.append(supplied_metric("unclassified_columns", unknown,
                                               context="unassigned", category="unclassified_supplied",
                                               source=row_source, provenance=provenance,
                                               missing_reason="raw non-scalar columns; context requires caller review"))
            candidate = CandidateEvidence(candidate_id, sequence_hash(supplied), target_id, conformer_id,
                                          metrics, dict(provenance),
                                          ["Metric units/scales not inferred; upstream values retained",
                                           "Candidate sequence hash uses exact supplied candidate chains joined with '/'"],
                                          {k: "not supplied" for k, v in {"target_id": target_id, "conformer_id": conformer_id}.items() if v is None})
            candidate.to_dict(); candidates.append(candidate)
    if hash_file(path) != source["sha256"]:
        raise ValueError("CSV changed during import")
    return candidates


def import_boltz_confidence(path, *, provenance):
    path = Path(path)
    before = hash_file(path)
    raw = read_json(path)
    if not isinstance(raw, dict):
        raise ValueError("Confidence JSON must be an object")
    if hash_file(path) != before:
        raise ValueError("Confidence JSON changed during import")
    source = {"path": str(path.resolve()), "sha256": before, "row": None}
    known = {"confidence_score", "ptm", "iptm", "protein_iptm", "ligand_iptm",
             "complex_plddt", "complex_iplddt", "complex_pde", "complex_ipde", "pair_chains_iptm"}
    return [supplied_metric(k, v, context="complex",
                            category="model_confidence" if k in known else "unclassified_supplied",
                            source=source, provenance=provenance) for k, v in raw.items()]
