"""Offline import of explicitly bound dl_binder_design AF2 score files.

No upstream imports, silent-file deserialization, inference, or filesystem writes.
The caller-selected profile describes the inspected score format, not proof of
which software produced a file. Monomer RMSDs are always quarantined in v1.
"""
from copy import deepcopy
import math
from pathlib import Path

from .evidence import CandidateEvidence, supplied_metric
from .mapping import canonical_residue_map
from .provenance import hash_config, hash_file
from .structures import read_structure
from .validation import validate_named

PROFILE = "dl_binder_design_sc_v1"
METADATA = "__dl_binder_import__"
_RMSDS = {"binder_aligned_rmsd", "target_aligned_rmsd"}
# context, category, unit, scale. None context means the explicit run mode.
_FIELDS = {
    "plddt_total": (None, "model_confidence", None, "0-100"),
    "plddt_binder": ("monomer", "model_confidence", None, "0-100"),
    "plddt_target": ("complex", "model_confidence", None, "0-100"),
    "pae_binder": ("monomer", "model_confidence", "angstrom", None),
    "pae_target": ("complex", "model_confidence", "angstrom", None),
    "pae_interaction": ("complex", "model_confidence", "angstrom", None),
    "binder_aligned_rmsd": ("monomer", "structural_comparison", "angstrom", None),
    "target_aligned_rmsd": ("complex", "structural_comparison", "angstrom", None),
    "time": ("unassigned", "runtime", "second", None),
}


def _parse_score_file(text):
    header, header_row, rows, seen = None, None, [], set()
    for number, line in enumerate(text.splitlines(), 1):
        tokens = line.split()
        if not tokens or line.lstrip().startswith("#"):
            continue
        if tokens.pop(0) != "SCORE:":
            raise ValueError(f"SC line {number}: expected SCORE: text, not a silent file")
        if "description" in tokens:
            if len(tokens) < 2 or len(set(tokens)) != len(tokens) or METADATA in tokens:
                raise ValueError(f"SC line {number}: duplicate/invalid/reserved header")
            if not any(name in _FIELDS for name in tokens):
                raise ValueError(f"SC line {number}: header must contain a known AF2 score column")
            header, header_row = tokens, number
            continue
        if header is None:
            raise ValueError(f"SC line {number}: missing description header")
        if len(tokens) != len(header):
            raise ValueError(f"SC line {number}: column count mismatch or missing description/tag")
        raw = dict(zip(header, tokens))
        tag = raw["description"]
        if tag.lower() in {"nan", "na", "n/a", "none", "null", ".", "-"}:
            raise ValueError(f"SC line {number}: missing description/tag")
        if tag in seen:
            raise ValueError(f"SC line {number}: duplicate tag {tag!r}")
        seen.add(tag)
        rows.append((number, list(header), header_row, raw, line))
    if not rows:
        raise ValueError("SC contains no data rows")
    return rows


def _configuration(config):
    required = {"profile", "prediction_mode"}
    allowed = required | {"initial_guess", "recycles", "upstream_snapshot"}
    if not isinstance(config, dict) or not required <= set(config) or set(config) - allowed:
        raise ValueError("Invalid dl_binder adapter configuration fields")
    cfg = {"initial_guess": None, "recycles": None, "upstream_snapshot": None, **config}
    if cfg["profile"] != PROFILE or cfg["prediction_mode"] not in ("monomer", "complex"):
        raise ValueError("Unsupported score profile or prediction_mode")
    if cfg["initial_guess"] is not None and type(cfg["initial_guess"]) is not bool:
        raise ValueError("initial_guess must be a boolean or null")
    if cfg["recycles"] is not None and (type(cfg["recycles"]) is not int or cfg["recycles"] < 0):
        raise ValueError("recycles must be a nonnegative integer or null")
    if cfg["upstream_snapshot"] is not None and (
            not isinstance(cfg["upstream_snapshot"], str) or not cfg["upstream_snapshot"].strip()):
        raise ValueError("upstream_snapshot must be supplied text or null")
    return cfg


def _manifest_reference(path, manifest):
    path = Path(path).resolve(strict=True)
    matches = [item for item in manifest["input_files"] if item["path"] == str(path)]
    if len(matches) != 1 or hash_file(path) != matches[0]["sha256"]:
        raise ValueError(f"Missing, duplicated or hash-mismatched manifest input: {path}")
    return dict(matches[0])


def _binding(binding, manifest, mode):
    required = {"candidate_id", "target_id", "conformer_id", "pdb_path", "pdb_model_id",
                "residue_map", "chain_roles"}
    if not isinstance(binding, dict) or set(binding) != required:
        raise ValueError("Binding requires candidate/target/conformer IDs, PDB/model, residue_map and chain_roles")
    if not isinstance(binding["candidate_id"], str) or not binding["candidate_id"].strip():
        raise ValueError("Binding candidate_id must be nonempty")
    for key in ("target_id", "conformer_id"):
        if binding[key] is not None and (not isinstance(binding[key], str) or not binding[key].strip()):
            raise ValueError(f"Binding {key} must be nonempty text or null")
    if not isinstance(binding["pdb_model_id"], str) or not binding["pdb_model_id"]:
        raise ValueError("Supply the explicit PDB model ID")
    path = Path(binding["pdb_path"])
    if path.suffix.lower() != ".pdb":
        raise ValueError("Only an explicit existing PDB reference is supported")
    reference = _manifest_reference(path, manifest)
    structure = read_structure(reference["path"], model_id=binding["pdb_model_id"])
    if structure.source_hash != reference["sha256"]:
        raise ValueError("PDB changed during parsing")
    if structure.format != "pdb":
        raise ValueError("PDB reference contains a different format")
    supplied_map = binding["residue_map"]
    if supplied_map != canonical_residue_map(structure):
        raise ValueError("residue_map does not match this PDB/model and default altloc A")
    identities, chains = set(), []
    for row in supplied_map:
        if row["record_group"] != "ATOM":
            raise ValueError("This AF2 profile supports polymer ATOM residues only")
        identity = (row["chain_id"], row["segment"], row["residue_id"], row["insertion_code"])
        if identity in identities:
            raise ValueError("Ambiguous duplicate residue identity")
        identities.add(identity)
        chain = (row["chain_id"], row["segment"])
        if not chains or chains[-1] != chain:
            chains.append(chain)
    expected_roles = ["candidate", "target"] if mode == "complex" else ["candidate"]
    if len(chains) != len(expected_roles) or len(set(chains)) != len(chains):
        raise ValueError("PDB chain count/order does not match explicit prediction_mode")
    expected = [{"chain_id": chain, "segment": segment, "role": role}
                for (chain, segment), role in zip(chains, expected_roles)]
    if binding["chain_roles"] != expected:
        raise ValueError("Wrong chain-role mapping: this profile requires binder first, then target")
    return reference, {"pdb": reference, "pdb_model_id": structure.model_id,
                       "residue_map": deepcopy(supplied_map),
                       "residue_map_sha256": hash_config(supplied_map),
                       "chain_roles": deepcopy(expected),
                       "binding_sha256": hash_config(binding)}


def _metric(name, raw, *, present, mode, source, provenance):
    context, category, unit, scale = _FIELDS.get(
        name, ("unassigned", "unclassified_supplied", None, None))
    metric = supplied_metric(name, raw, context=context or mode, category=category,
                             unit=unit, scale=scale, source=source, provenance=provenance)
    state, reason = "available", None
    if not present:
        state, reason = "missing", "missing_column"
    elif metric["value"] is None:
        token = raw.lower()
        try:
            non_finite = not math.isfinite(float(raw))
        except ValueError:
            non_finite = False
        state = ("missing" if token in {"na", "n/a", "none", "null", ".", "-"}
                 else "non_finite" if non_finite
                 else "invalid_numeric")
        reason = state
    elif metric["value"] < 0 or (scale == "0-100" and metric["value"] > 100):
        state, reason = "invalid_numeric", "outside profile domain; no automatic rescaling"
    # Keep the original token even when its numeric interpretation is unusable.
    raw_state = state
    if name not in _FIELDS:
        state, reason = "quarantined", "unsupported_semantics: unknown upstream column"
    elif mode == "monomer" and name in _RMSDS:
        state = "quarantined"
        reason = "unsupported_semantics: monomer binderlen=-1 contaminates upstream RMSD target mask"
    elif mode == "monomer" and context == "complex":
        state, reason = "quarantined", "unsupported_semantics: complex metric in monomer mode"
    if state != "available":
        metric["value"] = None
        metric["missing_reason"] = reason
    if state == "quarantined":
        metric["category"] = "unsupported_semantics"
    return metric, {"status": state, "raw_status": raw_state, "reason": reason,
                    "prediction_context": mode}


def import_dl_binder_sc(path, *, bindings, manifest, config, provenance):
    """Return validated CandidateEvidence records for every explicitly bound tag.

    ``bindings`` maps exact SC description tags to candidate/target/conformer IDs,
    an existing PDB/model, its canonical residue_map and ordered chain_roles.
    ``config`` must equal manifest.config['dl_binder_output_adapter']; SC and every
    PDB must be hashed input_files in that manifest. Unknown sequence identities
    stay null: an ATOM table is not a supplied full candidate sequence.

    The reserved unassigned raw-object metric ``__dl_binder_import__`` retains
    headers, tags, raw rows, binding/config/manifest provenance and field states
    within the existing schema. Its value is always null. Semantic quarantines
    also have null values, so existing numeric filters cannot use the raw number.
    Invalid file identities/format/mappings raise ValueError, returning no partial
    list. Missing files and parser exceptions propagate. Nothing is written.
    """
    bindings, manifest, config, provenance = deepcopy((bindings, manifest, config, provenance))
    cfg = _configuration(config)
    validate_named(manifest, "run_manifest")
    if manifest["config_hash"] != hash_config(manifest["config"]):
        raise ValueError("Manifest config hash mismatch")
    if manifest["config"].get("dl_binder_output_adapter") != config:
        raise ValueError("Adapter config differs from manifest configuration")
    if provenance not in manifest["supplied_models"] and not (
            not manifest["supplied_models"] and provenance == {"model_id": None, "checkpoint_id": None, "seed": None}):
        raise ValueError("Supplied provenance differs from manifest supplied_models")
    path = Path(path)
    if path.suffix.lower() != ".sc":
        raise ValueError("Supply an explicit local .sc file; silent files are unsupported")
    source = _manifest_reference(path, manifest)
    rows = _parse_score_file(Path(source["path"]).read_text(encoding="utf-8-sig"))
    tags = {raw["description"] for _, _, _, raw, _ in rows}
    if not isinstance(bindings, dict) or set(bindings) != tags:
        raise ValueError("Bindings must match all SC description tags exactly (missing/extra tag)")
    candidates, seen_ids, references = [], set(), [source]
    for line_no, header, header_row, raw, raw_line in rows:
        tag = raw["description"]
        binding = bindings[tag]
        reference, binding_metadata = _binding(binding, manifest, cfg["prediction_mode"])
        references.append(reference)
        if binding["candidate_id"] in seen_ids:
            raise ValueError("Multiple tags bind to the same candidate_id")
        seen_ids.add(binding["candidate_id"])
        row_source = {**source, "row": line_no}
        names = [name for name in header if name != "description"]
        names.extend(name for name in _FIELDS if name not in names)
        metrics, statuses = [], {}
        for name in names:
            metric, status = _metric(name, raw.get(name), present=name in raw,
                                      mode=cfg["prediction_mode"], source=row_source, provenance=provenance)
            metrics.append(metric)
            statuses[name] = status
        metadata = {"adapter": "dl_binder_output_adapter", "adapter_version": "1.0",
                    "description": tag, "header": header, "header_row": header_row,
                    "raw_columns": raw, "raw_line": raw_line, "field_statuses": statuses,
                    "binding": binding_metadata, "configuration": cfg,
                    "configuration_sha256": hash_config(cfg),
                    "producer_metadata_status": "caller_supplied_not_verified",
                    "manifest": {"run_id": manifest["run_id"], "run_directory": manifest["run_directory"],
                                 "sha256": hash_config(manifest), "config_hash": manifest["config_hash"]}}
        metrics.append(supplied_metric(METADATA, metadata, context="unassigned", category="import_metadata",
                                       source=row_source, provenance=provenance,
                                       missing_reason="non-scalar import audit record; not a metric"))
        warnings = ["Computational evidence only; no binding, affinity or success prediction",
                    "Monomer-context fields from a complex run are not independent monomer predictions",
                    "RMSDs compare against upstream initial coordinates, not an experimental reference",
                    "Producer profile/initial guess/recycles/snapshot are caller supplied, not verified"]
        warnings.extend(f"{name}: {state['reason']}" for name, state in statuses.items()
                        if state["status"] != "available")
        missing = {"sequence_hash": "No full candidate sequence supplied; not inferred from PDB ATOM records"}
        missing.update({key: "not supplied" for key in ("target_id", "conformer_id") if binding[key] is None})
        candidate = CandidateEvidence(binding["candidate_id"], None, binding["target_id"],
                                      binding["conformer_id"], metrics, deepcopy(provenance), warnings, missing)
        candidate.to_dict()
        candidates.append(candidate)
    for reference in references:
        if hash_file(reference["path"]) != reference["sha256"]:
            raise ValueError("Input changed during score import")
    return candidates
