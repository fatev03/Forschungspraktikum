"""Read-only supplied structural samples; no candidate, model, check or report API.

Public API: import_supplied_conformers(*, artifacts, bindings, manifest, config),
ConformerImportResult, ConformerImportError. Contract version is 1.0.

config: exactly version='1.0', allowed_input_roots=[canonical absolute paths],
altloc='A'. artifacts: nonempty dictionary of explicit IDs to objects containing
kind ('pdb'/'mmcif'), path, sha256, source_run_id, producer, generation, conversion.
producer: name, version, model_id, checkpoint_id, seed (each nullable), plus
missing_reasons (exactly the null fields, with nonempty reasons). Non-null model
provenance triples must occur in manifest.supplied_models. Producer history is
always caller-supplied, never verified. generation/conversion each contain
details (JSON object or null) and missing_reason (nonempty only for null details).
These are inert declarations, not commands, defaults or executable settings.

bindings: nonempty list of binding_id, artifact_id, ensemble_id, sample_id,
target_id, model_id (the structural model, NOT the producer model),
selection_reason, residue_map, residue_map_sha256, chains. Each ordered polymer
chain/segment must occur once in chains, with chain_id, segment, role='target',
sequence, sequence_sha256, entries, missing_reason. Sequence fields are either
all null with a reason, or an explicitly supplied standard-AA sequence, its
exact-text hash and existing validate_sequence_mapping entries. Missing positions
are allowed with reasons; mismatches and wrong-chain mappings are errors.

The existing manifest config must contain supplied_conformer_output_adapter =
{config, artifacts_sha256: hash_config(artifacts),
 bindings_sha256: hash_config(bindings)}. Every registered artifact is bound and
matches exactly one manifest input. Extra manifest inputs are not opened.

Result.samples contains separate identity/map/sequence/provenance audit records;
diagnostics are structured warnings. Fatal errors raise ConformerImportError
with diagnostics and NO partial result. to_dict() returns a detached JSON value.
Unselected models are not audited; selection_reason states the caller's scope.
No inference, sequence assignment/generation, alignment, repair, B-factor import,
geometry check, filesystem write, discovery, network or subprocess is performed.
See docs/HANDOFF.md for limitations and a synthetic test-helper example.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
import re

from .mapping import canonical_residue_map, validate_sequence_mapping
from .provenance import hash_config, hash_file
from .evidence import sequence_hash
from .structures import read_structure, UnsupportedFormat, StructureFormatError
from .validation import validate_named

__all__ = ["import_supplied_conformers", "ConformerImportResult", "ConformerImportError"]
_NAME = "supplied_conformer_output_adapter"
_LIMITATIONS = [
    "Local byte/map consistency only; target identity and producer history are caller-supplied",
    "Supplied structural samples only; no equilibrium population, free-energy distribution or kinetic pathway",
    "No geometric checks, candidate evidence, confidence metrics or CheckReport integration",
    "Only explicitly selected models are audited; no inference about omitted samples",
]


class ConformerImportError(ValueError):
    """Fatal import failure; diagnostics never expose a partial sample result."""

    def __init__(self, code, message, *, artifact_id=None, binding_id=None, locator=None):
        self.diagnostics = [{"severity": "error", "code": code, "message": message,
                             "artifact_id": artifact_id, "binding_id": binding_id,
                             "locator": locator}]
        super().__init__(f"{code}: {message}")


@dataclass
class ConformerImportResult:
    """In-memory audit, deliberately not a candidate/filter iterable."""

    samples: list
    diagnostics: list
    audit: dict

    def to_dict(self):
        result = deepcopy({"samples": self.samples, "diagnostics": self.diagnostics,
                           "audit": self.audit})
        hash_config(result)  # Enforce strict finite JSON without changing old schemas.
        return result


def _keys(obj, names):
    if not isinstance(obj, dict) or set(obj) != set(names.split()):
        raise ValueError(f"Expected exactly these fields: {names}")


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected nonempty string")
    return value


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Expected lowercase SHA-256")


def _path(value, roots=None):
    p = Path(_text(value))
    if (not p.is_absolute() or str(p) != value or ".." in p.parts
            or any(c in value for c in "*?[]") or p.resolve() != p):
        raise ValueError("Exact canonical absolute local path required; no patterns or symlink aliases")
    if roots is not None and not any(p.is_relative_to(r) for r in roots):
        raise ValueError("Artifact outside allowed_input_roots")
    return p


def _declaration(obj):
    _keys(obj, "details missing_reason")
    if obj["details"] is None:
        _text(obj["missing_reason"])
    elif not isinstance(obj["details"], dict) or not obj["details"] or obj["missing_reason"] is not None:
        raise ValueError("Declaration needs nonempty JSON details or null with a missing reason")


class _Import:
    def __init__(self, artifacts, bindings, manifest, config):
        self.artifacts, self.bindings, self.manifest, self.config = deepcopy((artifacts, bindings, manifest, config))
        self.artifact_id = self.binding_id = None
        self.phase = "invalid_contract"
        self.paths, self.samples, self.diagnostics = {}, [], []

    def fail(self, code, message, locator=None):
        raise ConformerImportError(code, message, artifact_id=self.artifact_id,
                                   binding_id=self.binding_id, locator=locator)

    def warn(self, code, message, locator=None):
        self.diagnostics.append({"severity": "warning", "code": code, "message": message,
                                 "artifact_id": self.artifact_id, "binding_id": self.binding_id,
                                 "locator": locator})

    def prepare(self):
        # All contract/path validation precedes artifact content reads.
        hash_config([self.artifacts, self.bindings, self.manifest, self.config])
        _keys(self.config, "version allowed_input_roots altloc")
        if self.config["version"] != "1.0" or self.config["altloc"] != "A":
            self.fail("unsupported_config", "Version 1.0 requires canonical default altloc A")
        roots = self.config["allowed_input_roots"]
        if not isinstance(roots, list) or not roots:
            raise ValueError("Nonempty allowed_input_roots required")
        self.phase = "unsafe_path"
        self.roots = [_path(r) for r in roots]
        if len(set(self.roots)) != len(self.roots) or any(not r.is_dir() for r in self.roots):
            raise ValueError("Input roots must be unique existing directories")
        self.phase = "manifest_contract"
        validate_named(self.manifest, "run_manifest")
        if self.manifest["config_hash"] != hash_config(self.manifest["config"]):
            raise ValueError("Manifest config hash mismatch")
        stamp = datetime.fromisoformat(self.manifest["timestamp"])
        if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
            raise ValueError("Manifest timestamp must be UTC")
        run_dir = _path(self.manifest["run_directory"])
        for path in self.manifest["output_paths"]:
            if not _path(path).is_relative_to(run_dir):
                raise ValueError("Manifest output outside run directory")
        contract = {"config": self.config, "artifacts_sha256": hash_config(self.artifacts),
                    "bindings_sha256": hash_config(self.bindings)}
        if hash_config(self.manifest["config"].get(_NAME)) != hash_config(contract):
            raise ValueError("Manifest does not attest exact config/artifacts/bindings")
        self.phase = "invalid_contract"
        if not isinstance(self.artifacts, dict) or not self.artifacts or not isinstance(self.bindings, list) or not self.bindings:
            raise ValueError("Nonempty artifact registry and binding list required")
        seen_paths = set()
        for aid, a in self.artifacts.items():
            self.artifact_id = aid
            _text(aid)
            _keys(a, "kind path sha256 source_run_id producer generation conversion")
            if a["kind"] not in ("pdb", "mmcif"):
                self.fail("unsupported_format", "Only supplied PDB/mmCIF artifacts are supported")
            self.phase = "unsafe_path"
            path = _path(a["path"], self.roots)
            self.phase = "invalid_contract"
            if path.suffix.lower() not in ({".pdb"} if a["kind"] == "pdb" else {".cif", ".mmcif"}):
                self.fail("unsupported_format", "Artifact kind and uncompressed file suffix must agree")
            if path in seen_paths:
                raise ValueError("Register a file once; bind its distinct models explicitly")
            seen_paths.add(path)
            _digest(a["sha256"]); _text(a["source_run_id"])
            matches = [x for x in self.manifest["input_files"] if x["path"] == str(path)]
            if matches != [{"path": str(path), "sha256": a["sha256"]}]:
                self.fail("manifest_artifact_mismatch", "Artifact must match exactly one manifest input path/hash")
            self.paths[aid] = path
            p = a["producer"]
            _keys(p, "name version model_id checkpoint_id seed missing_reasons")
            nulls = {k for k in ("name", "version", "model_id", "checkpoint_id", "seed") if p[k] is None}
            if not isinstance(p["missing_reasons"], dict) or set(p["missing_reasons"]) != nulls:
                raise ValueError("Producer missing_reasons must cover exactly its null fields")
            for reason in p["missing_reasons"].values():
                _text(reason)
            for k in ("name", "version", "model_id", "checkpoint_id"):
                if p[k] is not None:
                    _text(p[k])
            if p["seed"] is not None and (type(p["seed"]) is not int or p["seed"] < 0):
                raise ValueError("Producer seed must be null or nonnegative integer")
            triple = {k: p[k] for k in ("model_id", "checkpoint_id", "seed")}
            if any(v is not None for v in triple.values()) and not any(
                    hash_config(triple) == hash_config(m) for m in self.manifest["supplied_models"]):
                self.fail("manifest_producer_mismatch", "Producer model/checkpoint/seed absent from supplied_models")
            _declaration(a["generation"]); _declaration(a["conversion"])
        self.artifact_id = None
        ids, samples, upstream_samples, selected, used, targets = set(), set(), set(), set(), set(), {}
        for b in self.bindings:
            _keys(b, "binding_id artifact_id ensemble_id sample_id target_id model_id selection_reason residue_map residue_map_sha256 chains")
            self.binding_id = _text(b["binding_id"])
            self.artifact_id = _text(b["artifact_id"])
            if self.artifact_id not in self.artifacts:
                raise ValueError("Binding references unregistered artifact")
            for k in ("ensemble_id", "sample_id", "target_id", "model_id", "selection_reason"):
                _text(b[k])
            keys = (b["binding_id"], (b["ensemble_id"], b["sample_id"]),
                    (self.artifacts[self.artifact_id]["source_run_id"], b["target_id"], b["sample_id"]),
                    (self.artifact_id, b["model_id"]))
            for key, seen in zip(keys, (ids, samples, upstream_samples, selected)):
                if key in seen:
                    self.fail("duplicate_identity", "Duplicate binding, sample or selected artifact/model")
                seen.add(key)
            if targets.setdefault(b["ensemble_id"], b["target_id"]) != b["target_id"]:
                self.fail("target_conflict", "One ensemble cannot declare multiple target identities")
            used.add(self.artifact_id)
            _digest(b["residue_map_sha256"])
            if not isinstance(b["residue_map"], list) or not b["residue_map"]:
                raise ValueError("Explicit nonempty canonical residue map required")
            if hash_config(b["residue_map"]) != b["residue_map_sha256"]:
                self.fail("residue_map_mismatch", "Supplied residue-map hash mismatch")
            if not isinstance(b["chains"], list) or not b["chains"]:
                raise ValueError("Explicit polymer chain bindings required")
            for c in b["chains"]:
                _keys(c, "chain_id segment role sequence sequence_sha256 entries missing_reason")
                if not isinstance(c["chain_id"], str) or type(c["segment"]) is not int or c["segment"] < 0 or c["role"] != "target":
                    self.fail("chain_binding", "Explicit target-only chain/segment roles required")
                if c["sequence"] is None:
                    if c["entries"] is not None or c["sequence_sha256"] is not None:
                        raise ValueError("Unknown supplied sequence requires null hash and entries")
                    _text(c["missing_reason"])
                elif (c["missing_reason"] is not None or sequence_hash(c["sequence"]) != c["sequence_sha256"]
                      or not isinstance(c["entries"], list)):
                    self.fail("sequence_binding", "Supplied sequence needs exact hash, entries and null missing_reason")
        if used != set(self.artifacts):
            self.fail("unbound_artifact", "Every registered artifact must be explicitly bound")
        self.artifact_id = self.binding_id = None

    def verify_file(self, aid):
        self.artifact_id = aid
        self.phase = "unsafe_path"
        path = _path(self.artifacts[aid]["path"], self.roots)
        self.phase = "artifact_read_error"
        if not path.is_file():
            self.fail("artifact_read_error", "Artifact must be an existing regular file")
        if hash_file(path) != self.artifacts[aid]["sha256"]:
            self.fail("stale_artifact_hash", "Artifact bytes differ from declared hash or changed during import")

    def read_sample(self, b):
        self.artifact_id, self.binding_id = b["artifact_id"], b["binding_id"]
        a, path = self.artifacts[self.artifact_id], self.paths[self.artifact_id]
        self.verify_file(self.artifact_id)
        self.phase = "structure_parse_error"
        if a["kind"] == "pdb":
            for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if re.fullmatch(r"MODEL [0-9]+\s*", line):
                    self.fail("native_alphaflow_model_header", "Unpadded MODEL header (including native AlphaFlow MODEL 0) is unsupported; no repair performed", line_no)
        structure = read_structure(path, model_id=b["model_id"])
        if structure.source_hash != a["sha256"]:
            self.fail("stale_artifact_hash", "Artifact changed before structure parsing")
        if any(not all(math.isfinite(x) for x in atom.xyz) for atom in structure.atoms):
            self.fail("nonfinite_coordinates", "Selected sample has non-finite coordinates")
        if any(w["code"] in ("duplicate_atom_id", "duplicate_residue_id") for w in structure.warnings):
            self.fail("ambiguous_structure_identity", "Duplicate atom/residue identity prevents unambiguous sample binding")
        rows = canonical_residue_map(structure, altloc="A")
        if hash_config(rows) != b["residue_map_sha256"]:
            self.fail("residue_map_mismatch", "Canonical map differs for this file/model/default-altloc-A")
        observed = list(dict.fromkeys((r["chain_id"], r["segment"]) for r in rows if r["record_group"] == "ATOM"))
        if [(c["chain_id"], c["segment"]) for c in b["chains"]] != observed:
            self.fail("chain_binding", "Chains must cover the ordered polymer chain/segment inventory exactly")
        sequence_audit = []
        self.phase = "sequence_binding"
        for c in b["chains"]:
            if c["sequence"] is None:
                self.warn("sequence_not_supplied", c["missing_reason"], {"chain_id": c["chain_id"], "segment": c["segment"]})
                sequence_audit.append({**c, "mapping": None, "status": "not_supplied"})
                continue
            mapping = validate_sequence_mapping(structure, c["sequence"], c["entries"])
            covered = set()
            for entry in mapping:
                if entry["status"] == "mismatch":
                    self.fail("sequence_mismatch", "Supplied sequence disagrees with observed residue", entry["sequence_position"])
                idx = entry["residue_index"]
                if idx is not None:
                    if (rows[idx]["chain_id"], rows[idx]["segment"]) != (c["chain_id"], c["segment"]):
                        self.fail("chain_binding", "Sequence mapping points to another chain/segment", idx)
                    covered.add(idx)
            unobserved = [m["sequence_position"] for m in mapping if m["status"] == "missing_or_unmapped"]
            unbound = [r["residue_index"] for r in rows if r["record_group"] == "ATOM"
                       and (r["chain_id"], r["segment"]) == (c["chain_id"], c["segment"])
                       and r["residue_index"] not in covered]
            if unobserved or unbound:
                self.warn("partial_sequence_mapping", "Missing/unmapped supplied positions or unmapped observed residues",
                          {"chain_id": c["chain_id"], "segment": c["segment"], "sequence_positions": unobserved, "residue_indices": unbound})
            sequence_audit.append({**c, "mapping": mapping, "unmapped_observed_residues": unbound,
                                   "status": "partial" if unobserved or unbound else "matched"})
        for w in structure.warnings:
            self.warn("structure_parser_warning", w["message"], w.get("line"))
        for r in rows:
            if r["warnings"] or r["missing_backbone_atoms"] or r["record_group"] != "ATOM":
                self.warn("residue_scope_warning", "See preserved residue warnings/missing atoms/record group", r["residue_index"])
        if a["producer"]["missing_reasons"] or any(a[k]["details"] is None for k in ("generation", "conversion")):
            self.warn("incomplete_provenance", "Unknown producer/generation/conversion metadata retained with reasons")
        self.samples.append({"binding_id": b["binding_id"], "ensemble_id": b["ensemble_id"],
                             "sample_id": b["sample_id"], "target_id": b["target_id"],
                             "artifact_id": b["artifact_id"], "artifact": deepcopy(a),
                             "model_id": structure.model_id, "format": structure.format,
                             "selection_reason": b["selection_reason"], "identity_status": "verified_local",
                             "producer_verification": "caller_supplied_not_verified",
                             "residue_map": rows, "residue_map_sha256": hash_config(rows),
                             "chains": sequence_audit, "parser_warnings": deepcopy(structure.warnings),
                             "binding_sha256": hash_config(b), "import_run_id": self.manifest["run_id"],
                             "manifest_sha256": hash_config(self.manifest)})

    def run(self):
        self.prepare()
        for b in self.bindings:
            self.read_sample(b)
        self.binding_id = None
        for aid in self.artifacts:
            self.verify_file(aid)
        result = ConformerImportResult(self.samples, self.diagnostics,
            {"adapter": _NAME, "adapter_version": "1.0", "category": "supplied_structural_samples_only",
             "configuration": self.config, "configuration_sha256": hash_config(self.config),
             "manifest": deepcopy(self.manifest), "manifest_sha256": hash_config(self.manifest),
             "artifacts": self.artifacts, "bindings": self.bindings, "limitations": list(_LIMITATIONS)})
        result.to_dict()
        return result


def import_supplied_conformers(*, artifacts, bindings, manifest, config):
    """Verify explicit local sample bindings, without writing or running checks.

    Returns ConformerImportResult. Any malformed contract, parse/identity error or
    late file change raises ConformerImportError; no partial result is returned.
    """
    importer = None
    try:
        # Reject non-JSON objects before deepcopy can invoke a custom object hook.
        hash_config([artifacts, bindings, manifest, config])
        importer = _Import(artifacts, bindings, manifest, config)
        return importer.run()
    except ConformerImportError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OSError, AttributeError, RecursionError) as exc:
        code = "unsupported_format" if isinstance(exc, UnsupportedFormat) else (
            "structure_parse_error" if isinstance(exc, StructureFormatError) else
            importer.phase if importer is not None else "invalid_contract")
        raise ConformerImportError(code, str(exc),
            artifact_id=importer.artifact_id if importer else None,
            binding_id=importer.binding_id if importer else None) from exc
