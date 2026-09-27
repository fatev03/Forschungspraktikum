"""Read-only association of supplied evidence and checks; never execute checks.

The bridge verifies local identity, not producer history or scientific validity.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .checks import CheckResult, LABEL
from .evidence import CandidateEvidence
from .mapping import canonical_residue_map
from .provenance import hash_config, hash_file
from .structures import read_structure, UnsupportedFormat
from .validation import validate_named

_CHECKS = {"structure_integrity_check", "coarse_steric_clash_check"}
_STATES = {"pass", "warn", "fail", "missing", "not_run", "error", "unsupported"}
_ORIGINS = {"design", "demo", "unknown", "origin_conflict"}
_ADAPTERS = {"dl_binder_output_adapter": "__dl_binder_import__", "notebook_output_adapter": "__notebook_import__"}


class CheckReportError(ValueError):
    """Invalid global contract. No normal or partial report is returned."""
    def __init__(self, code, message):
        self.diagnostics = [{"severity": "error", "code": code, "message": message}]
        super().__init__(f"{code}: {message}")


@dataclass
class CheckReport:
    """Report wrapper, deliberately not a candidate/filter iterable."""
    data: dict

    def to_dict(self):
        result = deepcopy(self.data)
        validate_named(result, "check_report")
        return result


def _keys(obj, names):
    if not isinstance(obj, dict) or set(obj) != set(names.split()):
        raise ValueError(f"Expected exactly these fields: {names}")


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected nonempty string")
    return value


def _same(a, b, message):
    # Canonical JSON comparison avoids bool/int equivalence in identity records.
    if hash_config(a) != hash_config(b):
        raise ValueError(message)


def _path(value, roots):
    p = Path(_text(value))
    if not p.is_absolute() or any(x in value for x in ("*", "?", "[", "]")) or ".." in p.parts:
        raise ValueError("Exact absolute local path required; patterns/traversal forbidden")
    resolved = p.resolve()
    if p != resolved or not any(resolved.is_relative_to(root) for root in roots):
        raise ValueError("Noncanonical path, symlink or path outside explicit input roots")
    return resolved


def _configuration(name, cfg):
    if name not in _CHECKS:
        raise ValueError("Only the two fixed built-in check names are accepted")
    fields = ("altloc max_peptide_cn_distance expected_residues" if name == "structure_integrity_check"
              else "altloc cutoff_angstrom scope fail_at_count max_reported_pairs")
    _keys(cfg, fields)
    if not isinstance(cfg["altloc"], str) or len(cfg["altloc"]) != 1:
        raise ValueError("Supply one explicit altloc character")
    key = "max_peptide_cn_distance" if name == "structure_integrity_check" else "cutoff_angstrom"
    if type(cfg[key]) not in (int, float) or cfg[key] <= 0:
        raise ValueError("Check distance must be positive and finite")
    if name == "structure_integrity_check":
        if not isinstance(cfg["expected_residues"], list):
            raise ValueError("expected_residues must be a list")
        seen = set()
        for r in cfg["expected_residues"]:
            _keys(r, "chain_id residue_id insertion_code")
            if not isinstance(r["chain_id"], str) or type(r["residue_id"]) is not int or not isinstance(r["insertion_code"], str):
                raise ValueError("Invalid expected residue identity")
            key = hash_config(r)
            if key in seen:
                raise ValueError("Duplicate expected residue")
            seen.add(key)
    else:
        if cfg["scope"] not in ("interchain", "nonlocal"):
            raise ValueError("Invalid clash scope")
        for key in ("fail_at_count", "max_reported_pairs"):
            if key == "fail_at_count" and cfg[key] is None:
                continue
            if type(cfg[key]) is not int or cfg[key] < 1:
                raise ValueError("Check counts must be positive integers")


def _observed(record):
    result = record.get("result") if isinstance(record, dict) else None
    prov = result.get("provenance") if isinstance(result, dict) else None
    cfg = result.get("configuration") if isinstance(result, dict) else None
    return {"observed_check_version": prov.get("check_version") if isinstance(prov, dict) else None,
            "observed_config_sha256": hash_config(cfg) if cfg is not None else None,
            "result_sha256": hash_config(result) if result is not None else None}


class _Bridge:
    def __init__(self, batches, records, bindings, manifests, config):
        self.batches, self.records, self.bindings, self.manifests, self.config = deepcopy((batches, records, bindings, manifests, config))
        self.evidence, self.entries, self.checked_files = {}, {}, {}
        self.report = None

    def prepare(self):
        # Only the two existing concrete data classes are serialized; no dynamic hooks.
        for batch in self.batches:
            for group in ("candidates", "quarantined"):
                for eid, candidate in batch[group].items():
                    if type(candidate) is CandidateEvidence:
                        batch[group][eid] = candidate.to_dict()
        for record in self.records.values():
            if type(record.get("result")) is CheckResult:
                record["result"] = record["result"].to_dict()
        hash_config([self.batches, self.records, self.bindings, self.manifests, self.config])
        _keys(self.config, "version bridge_manifest_id allowed_input_roots")
        if self.config["version"] != "1.0":
            raise ValueError("Unsupported bridge config version")
        roots = self.config["allowed_input_roots"]
        if not isinstance(roots, list) or not roots:
            raise ValueError("Explicit input roots required")
        self.roots = []
        for root in roots:
            p = Path(_text(root))
            if not p.is_absolute() or p != p.resolve() or ".." in p.parts or not p.is_dir():
                raise ValueError("Input root must be an existing canonical directory")
            self.roots.append(p)
        if not isinstance(self.manifests, dict) or self.config["bridge_manifest_id"] not in self.manifests:
            raise ValueError("Bridge manifest missing")
        for mid, manifest in self.manifests.items():
            _text(mid)
            validate_named(manifest, "run_manifest")
            _same(manifest["config_hash"], hash_config(manifest["config"]), "Manifest config hash mismatch")
            stamp = datetime.fromisoformat(manifest["timestamp"])
            if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
                raise ValueError("Manifest timestamp must be UTC")
            directory = Path(manifest["run_directory"])
            if not directory.is_absolute() or directory != directory.resolve() or ".." in directory.parts:
                raise ValueError("Manifest run directory must be canonical and absolute")
            for output in manifest["output_paths"]:
                p = Path(output)
                if not p.is_absolute() or p != p.resolve() or ".." in p.parts or not p.is_relative_to(directory):
                    raise ValueError("Manifest output path escapes run directory or uses symlink")
        bridge_id = self.config["bridge_manifest_id"]
        self.manifest = self.manifests[bridge_id]
        contract = {"config": self.config, "evidence_batches_sha256": hash_config(self.batches),
                    "check_records_sha256": hash_config(self.records), "bindings_sha256": hash_config(self.bindings),
                    "source_manifests_sha256": hash_config({k: m for k, m in self.manifests.items() if k != bridge_id})}
        _same(self.manifest["config"].get("check_report_bridge"), contract, "Bridge manifest does not attest exact input contract")
        if not isinstance(self.batches, list) or not self.batches or not isinstance(self.bindings, list):
            raise ValueError("Nonempty batches and explicit binding list required")
        self.report = {"schema_version": "1.0", "bridge_version": "1.0", "category": LABEL,
                       "run_id": self.manifest["run_id"], "manifest_sha256": hash_config(self.manifest),
                       "configuration": self.config, "configuration_sha256": hash_config(self.config),
                       "candidate_reports": [], "audit": {"quarantined_evidence": [], "metrics": [], "unresolved_bindings": []},
                       "bindings": [], "diagnostics": [],
                       "snapshots": {"evidence_batches": self.batches, "check_records": self.records, "manifests": self.manifests,
                                     "bindings": self.bindings},
                       "limitations": ["Supplied check values are not recomputed or independently verified",
                                       "Local consistency does not prove producer history or biological identity",
                                       "pass applies only to the supplied format/geometric check scope"]}
        batch_ids, candidates = set(), set()
        for batch in self.batches:
            _keys(batch, "batch_id adapter adapter_version manifest_id candidates quarantined diagnostics")
            bid = _text(batch["batch_id"])
            if bid in batch_ids or batch["adapter"] not in _ADAPTERS or batch["adapter_version"] != "1.0":
                raise ValueError("Duplicate batch or unsupported adapter/version")
            batch_ids.add(bid)
            if batch["manifest_id"] == bridge_id or batch["manifest_id"] not in self.manifests:
                raise ValueError("Explicit source import manifest required")
            if not isinstance(batch["diagnostics"], list):
                raise ValueError("Batch diagnostics must be an explicit list")
            for group in ("candidates", "quarantined"):
                if not isinstance(batch[group], dict):
                    raise ValueError("Evidence groups must be dictionaries keyed by evidence_id")
                for eid, candidate in batch[group].items():
                    _text(eid)
                    candidate = CandidateEvidence(**candidate).to_dict()
                    key = (hash_config(self.manifests[batch["manifest_id"]]), candidate["candidate_id"])
                    if eid in self.evidence or key in candidates:
                        raise ValueError("Duplicate evidence_id or candidate in one import manifest")
                    candidates.add(key)
                    self.evidence[eid] = (batch, candidate, group)
        ids, checks, used_records, used_evidence = set(), set(), set(), set()
        for binding in self.bindings:
            _keys(binding, "binding_id evidence_id artifact prediction_context origin_declaration checks")
            identifier = _text(binding["binding_id"])
            if identifier in ids or binding["evidence_id"] not in self.evidence:
                raise ValueError("Duplicate binding or unknown evidence_id")
            ids.add(identifier); used_evidence.add(binding["evidence_id"])
            a = binding["artifact"]
            _keys(a, "artifact_id path sha256 model_id source_run_id sample_id residue_map residue_map_sha256 chain_roles")
            _text(a["artifact_id"]); _text(a["model_id"])
            _path(a["path"], self.roots)  # Contract-level path rejection before any file reads.
            for key in ("source_run_id", "sample_id"):
                if a[key] is not None:
                    _text(a[key])
            if binding["prediction_context"] not in ("monomer", "complex", "counter_screen", "unassigned"):
                raise ValueError("Invalid explicit prediction context")
            declaration = binding["origin_declaration"]
            if declaration is not None:
                _keys(declaration, "origin reason")
                if declaration["origin"] not in _ORIGINS:
                    raise ValueError("Invalid origin declaration")
                _text(declaration["reason"])
            if not isinstance(binding["checks"], list) or not binding["checks"]:
                raise ValueError("Explicit expected check list required")
            for expected in binding["checks"]:
                _keys(expected, "check_id check check_version configuration config_sha256 record_id not_run_reason")
                cid = _text(expected["check_id"])
                if cid in checks:
                    raise ValueError("Duplicate check_id")
                checks.add(cid)
                _text(expected["check_version"])
                _configuration(expected["check"], expected["configuration"])
                _same(expected["config_sha256"], hash_config(expected["configuration"]), "Expected check config hash mismatch")
                rid = expected["record_id"]
                if rid is not None:
                    _text(rid)
                    if rid in used_records or expected["not_run_reason"] is not None:
                        raise ValueError("Duplicate check record reference or conflicting not_run declaration")
                    used_records.add(rid)
                elif expected["not_run_reason"] is not None:
                    _text(expected["not_run_reason"])
        if used_evidence != set(self.evidence) or set(self.records) - used_records:
            raise ValueError("Every evidence and supplied check record must be explicitly bound")

    def source_ref(self, mid, artifact):
        m = self.manifests[mid]
        expected = {"path": artifact["path"], "sha256": artifact["sha256"]}
        if m["input_files"].count(expected) != 1 or sum(x["path"] == artifact["path"] for x in m["input_files"]) != 1:
            raise ValueError("Artifact path/hash differs from exactly one source manifest input")
        return {"manifest_id": mid, "run_id": m["run_id"], "sha256": hash_config(m)}

    def identify(self, binding, batch, candidate):
        a = binding["artifact"]
        self.source_ref(batch["manifest_id"], a)
        meta = [m["raw_value"] for m in candidate["metrics"] if m["name"] == _ADAPTERS[batch["adapter"]]]
        if len(meta) != 1:
            raise ValueError("Exactly one adapter audit record required")
        meta = meta[0]
        if meta["adapter"] != batch["adapter"] or meta["manifest"]["sha256"] != hash_config(self.manifests[batch["manifest_id"]]):
            raise ValueError("Adapter metadata/source manifest mismatch")
        if meta["manifest"]["run_id"] != self.manifests[batch["manifest_id"]]["run_id"]:
            raise ValueError("Adapter source run mismatch")
        if batch["adapter"] == "dl_binder_output_adapter":
            if meta["adapter_version"] != batch["adapter_version"] or a["artifact_id"] != "prediction_pdb":
                raise ValueError("Unsupported dl_binder artifact/version")
            ref = meta["binding"]
            _same(ref["pdb"], {"path": a["path"], "sha256": a["sha256"]}, "Wrong dl_binder PDB")
            for left, right in (("pdb_model_id", "model_id"), ("residue_map", "residue_map"),
                                ("residue_map_sha256", "residue_map_sha256"), ("chain_roles", "chain_roles")):
                _same(ref[left], a[right], "dl_binder map/model/chain-role mismatch")
            if binding["prediction_context"] != meta["configuration"]["prediction_mode"]:
                raise ValueError("Prediction context differs from dl_binder mode")
            if a["source_run_id"] is not None or a["sample_id"] is not None:
                raise ValueError("dl_binder does not attest upstream run/sample; keep unknown")
            producer = {"model_provenance": candidate["provenance"], "status": meta["producer_metadata_status"]}
        else:
            if meta["version"] != batch["adapter_version"] or meta["binding"]["candidate_id"] != candidate["candidate_id"]:
                raise ValueError("Notebook candidate/version mismatch")
            matches = [p for p in meta["pdb_bindings"] if p["artifact_id"] == a["artifact_id"]]
            if len(matches) != 1:
                raise ValueError("Notebook PDB artifact must match exactly one explicit binding")
            ref = matches[0]
            for key in ("path", "sha256", "model_id", "residue_map", "residue_map_sha256"):
                _same(ref[key], a[key], "Notebook PDB/map/model mismatch")
            roles = [{k: c[k] for k in ("chain_id", "segment", "role")} for c in ref["chains"]]
            _same(roles, a["chain_roles"], "Notebook chain-role mismatch")
            ar = meta["artifacts"][a["artifact_id"]]
            for key in ("path", "sha256", "source_run_id", "sample_id"):
                _same(ar[key], a[key], "Notebook source run/sample/artifact mismatch")
            boltz_pdbs = {p["pdb"]["artifact_id"] for p in meta["binding"]["boltz"]}
            if a["artifact_id"] in boltz_pdbs and binding["prediction_context"] != "complex":
                raise ValueError("Boltz complex artifact cannot be relabeled monomer")
            producer = ar["producer"]
        _same(a["residue_map_sha256"], hash_config(a["residue_map"]), "Declared residue map hash mismatch")
        p = _path(a["path"], self.roots)
        observed = hash_file(p)
        if observed != a["sha256"]:
            raise ValueError("Stale artifact hash")
        structure = read_structure(p, model_id=a["model_id"])
        if structure.source_hash != observed:
            raise ValueError("Artifact changed during structure parsing")
        _same(canonical_residue_map(structure), a["residue_map"], "Canonical default-altloc-A map differs from adapter")
        self.checked_files[str(p)] = observed
        return producer, structure

    def origin(self, eid):
        batch, candidate, group = self.evidence[eid]
        meta = next((m["raw_value"] for m in candidate["metrics"] if m["name"] == _ADAPTERS[batch["adapter"]]), {})
        if batch["adapter"] == "notebook_output_adapter":
            original = meta.get("origin", "unknown")
            if original not in _ORIGINS:
                original = "unknown"
        else:
            original = "unknown"
        declared = {b["origin_declaration"]["origin"] for b in self.bindings
                    if b["evidence_id"] == eid and b["origin_declaration"] is not None}
        if len(declared) > 1:
            origin = "origin_conflict"
        elif declared:
            declaration = next(iter(declared))
            origin = declaration if batch["adapter"] == "dl_binder_output_adapter" else original if declaration == original else "origin_conflict"
        else:
            origin = original
        if group == "quarantined" and origin == "design":
            origin = "origin_conflict"
        # A flattened notebook quarantine list must not evade its field-level markers.
        if any(m["category"] == "quarantined_origin" for m in candidate["metrics"]) and origin == "design":
            origin = "origin_conflict"
        return origin, original

    def declared_producer(self, batch, candidate, artifact):
        """Retain declared producer even when artifact identity cannot be verified."""
        if batch["adapter"] == "dl_binder_output_adapter":
            return {"model_provenance": deepcopy(candidate["provenance"]), "status": "caller_supplied_not_verified"}
        for metric in candidate["metrics"]:
            if metric["name"] == _ADAPTERS[batch["adapter"]] and isinstance(metric["raw_value"], dict):
                records = metric["raw_value"].get("artifacts", {})
                record = records.get(artifact["artifact_id"], {}) if isinstance(records, dict) else {}
                producer = record.get("producer") if isinstance(record, dict) else None
                return deepcopy(producer) if isinstance(producer, dict) else None
        return None

    def check(self, expected, artifact, structure):
        rid = expected["record_id"]
        row = {"check_id": expected["check_id"], "check": expected["check"], "check_version": expected["check_version"],
               "configuration": expected["configuration"], "config_sha256": expected["config_sha256"],
               "record_id": rid, "status": "missing", "raw_status": None, "reason": "Expected check result not supplied",
               "check_manifest": None, "check_residue_map_sha256": None, "verification": "unavailable"}
        row.update(_observed(self.records.get(rid)))
        if rid is None:
            if expected["not_run_reason"] is not None:
                row.update(status="not_run", reason=expected["not_run_reason"])
            return row
        if rid not in self.records:
            return row
        record = self.records[rid]
        try:
            _keys(record, "manifest_id status reason result")
            row["raw_status"] = record["status"]
            if record["status"] not in _STATES:
                raise ValueError("Invalid supplied check status")
            mid = record["manifest_id"]
            if mid not in self.manifests or mid == self.config["bridge_manifest_id"]:
                raise ValueError("Explicit source check manifest required")
            row["check_manifest"] = self.source_ref(mid, artifact)
            result = record["result"]
            if record["status"] in ("missing", "not_run", "error", "unsupported"):
                if result is not None:
                    raise ValueError("Noncompleted state requires null result; preserve details in reason")
                _text(record["reason"])
                row.update(status=record["status"], reason=record["reason"], verification="caller_supplied_state")
                return row
            if record["reason"] is not None:
                raise ValueError("Completed result reason must be null; use result.messages")
            _keys(result, "check status metrics configuration messages provenance category")
            if result["status"] != record["status"] or result["check"] != expected["check"] or result["category"] != LABEL:
                raise ValueError("Supplied check identity/status/category mismatch")
            if not isinstance(result["metrics"], dict) or not isinstance(result["messages"], list):
                raise ValueError("Invalid check metrics/messages")
            prov = result["provenance"]
            _keys(prov, "utility_version check_version input_path input_sha256 model_id")
            _text(prov["utility_version"])
            if prov["check_version"] != "1.0" or expected["check_version"] != "1.0":
                row.update(status="unsupported", reason="Unsupported supplied/expected check version")
                return row
            _same(result["configuration"], expected["configuration"], "Check effective configuration mismatch")
            _same([prov["input_path"], prov["input_sha256"], prov["model_id"]],
                  [artifact["path"], artifact["sha256"], artifact["model_id"]], "Check PDB/hash/model mismatch")
            row["check_residue_map_sha256"] = hash_config(canonical_residue_map(structure, altloc=result["configuration"]["altloc"]))
            row.update(status=record["status"], reason=None, verification="local_identity_only_not_recomputed")
        except (ValueError, TypeError, KeyError, IndexError, OSError) as exc:
            row.update(status="error", reason=str(exc), verification="failed")
        return row

    def run(self):
        self.prepare()
        for eid, (batch, candidate, group) in self.evidence.items():
            origin, original = self.origin(eid)
            entry = {"evidence_id": eid, "batch_id": batch["batch_id"], "candidate_id": candidate["candidate_id"],
                     "import_run_id": self.manifests[batch["manifest_id"]]["run_id"],
                     "evidence_sha256": hash_config(candidate), "origin": origin, "source_origin": original,
                     "origin_verification": "caller_supplied", "binding_refs": [], "metric_refs": []}
            for index, m in enumerate(candidate["metrics"]):
                if m["category"] == "import_metadata":
                    continue
                ref = {"evidence_id": eid, "metric_index": index, "context": m["context"], "name": m["name"]}
                if origin != "design" or m["value"] is None or m["category"] in ("unsupported_semantics", "quarantined_origin"):
                    self.report["audit"]["metrics"].append({**ref, "reason": m["missing_reason"] or f"origin={origin}"})
                else:
                    entry["metric_refs"].append(ref)
            self.entries[eid] = entry
            (self.report["candidate_reports"] if origin == "design" else self.report["audit"]["quarantined_evidence"]).append(entry)
        for b in self.bindings:
            eid, a = b["evidence_id"], b["artifact"]
            batch, candidate, group = self.evidence[eid]
            entry = self.entries[eid]
            row = {"binding_id": b["binding_id"], "evidence_id": eid, "candidate_id": candidate["candidate_id"],
                   "run_id": self.manifest["run_id"], "import_run_id": entry["import_run_id"],
                   "source_manifest_sha256": hash_config(self.manifests[batch["manifest_id"]]),
                   "artifact": a, "prediction_context": b["prediction_context"], "origin": entry["origin"],
                   "producer": self.declared_producer(batch, candidate, a),
                   "identity_status": "error", "identity_reason": None, "checks": []}
            entry["binding_refs"].append(b["binding_id"])
            try:
                producer, structure = self.identify(b, batch, candidate)
                row.update(producer=producer, identity_status="verified_local")
                row["checks"] = [self.check(expected, a, structure) for expected in b["checks"]]
            except (ValueError, TypeError, KeyError, IndexError, OSError) as exc:
                status = "unsupported" if isinstance(exc, UnsupportedFormat) else "error"
                row.update(identity_status=status, identity_reason=str(exc))
                for expected in b["checks"]:
                    record = self.records.get(expected["record_id"], {})
                    row["checks"].append({"check_id": expected["check_id"], "check": expected["check"],
                        "check_version": expected["check_version"], "configuration": expected["configuration"],
                        "config_sha256": expected["config_sha256"], "record_id": expected["record_id"],
                        "status": status, "raw_status": record.get("status"), "reason": str(exc),
                        "check_manifest": None, "check_residue_map_sha256": None, "verification": "failed",
                        **_observed(record)})
            self.report["bindings"].append(row)
        # Detect files changed after one relationship was checked; retain all raw snapshots.
        changed = set()
        for path, digest in self.checked_files.items():
            try:
                if hash_file(path) != digest:
                    changed.add(path)
            except OSError:
                changed.add(path)
        for row in self.report["bindings"]:
            if row["artifact"]["path"] in changed:
                row.update(identity_status="error", identity_reason="Artifact changed during bridge build")
                for check in row["checks"]:
                    check.update(status="error", reason=row["identity_reason"], verification="failed")
            if row["identity_status"] != "verified_local":
                self.report["audit"]["unresolved_bindings"].append(row["binding_id"])
            for check in row["checks"]:
                if check["status"] != "pass":
                    self.report["diagnostics"].append({"binding_id": row["binding_id"], "evidence_id": row["evidence_id"],
                        "check_id": check["check_id"], "status": check["status"], "message": check["reason"] or "See supplied check messages"})
        result = CheckReport(self.report)
        result.to_dict()
        return result


def build_check_report(*, evidence_batches, check_records, bindings, manifests, config):
    """Build an offline association report, preserving raw evidence/check snapshots.

    Global contract errors raise CheckReportError. Individual linkage/check errors
    remain visible records; other evidence is never discarded. No checks execute.
    """
    try:
        return _Bridge(evidence_batches, check_records, bindings, manifests, config).run()
    except CheckReportError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OSError, AttributeError, RecursionError) as exc:
        raise CheckReportError("invalid_bridge_contract", str(exc)) from exc
