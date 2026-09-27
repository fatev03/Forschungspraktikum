"""Explicit local notebook-output bindings; standard library, read-only, no discovery.

An audit manifest attests bytes/config, not the biological truth of a source run.
No notebook cells, model code, subprocesses or serialized Python objects execute.
"""
from copy import deepcopy
import csv
from dataclasses import dataclass, field
import hashlib
import io
import math
from pathlib import Path
import re

from .evidence import CandidateEvidence, sequence_hash, supplied_metric
from .mapping import canonical_residue_map, validate_sequence_mapping
from .provenance import hash_config, hash_file
from .structures import read_structure
from .validation import read_json, validate_named

_META = "__notebook_import__"
_ORIGINS = {"design", "demo", "unknown", "origin_conflict"}
_CSV_SCORES = {"mpnn", "plddt", "i_ptm", "i_pae", "rmsd"}
_BOLTZ_SCORES = {"confidence_score", "ptm", "iptm", "protein_iptm", "ligand_iptm",
                 "complex_plddt", "complex_iplddt", "complex_pde", "complex_ipde"}
_PLDDT = {"plddt", "complex_plddt", "complex_iplddt"}
_NULL_PROVENANCE = {"model_id": None, "checkpoint_id": None, "seed": None}
_PROFILES = {"plddt_0_1_to_0_100_v1": (1, 100), "plddt_0_100_v1": (100, 1)}


class NotebookImportError(ValueError):
    """Fatal contract/parse/identity error. Diagnostics never contain partial candidates."""
    def __init__(self, code, message, *, artifact_id=None, candidate_id=None, locator=None):
        self.diagnostics = [{"severity": "error", "code": code, "message": message,
                             "artifact_id": artifact_id, "candidate_id": candidate_id, "locator": locator}]
        super().__init__(f"{code}: {message}")


@dataclass
class NotebookImportResult:
    """Only candidates is intended for default filter_candidates input.

    quarantined is audit-only; the existing filter API has no origin policy.
    This object deliberately is not iterable as an undifferentiated candidate list.
    """
    candidates: list = field(default_factory=list)
    quarantined: list = field(default_factory=list)
    diagnostics: list = field(default_factory=list)

    def to_dict(self):
        return {"candidates": [c.to_dict() for c in self.candidates],
                "quarantined": [c.to_dict() for c in self.quarantined],
                "diagnostics": deepcopy(self.diagnostics)}


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ValueError(f"Expected object fields {sorted(required)}; optional {sorted(optional)}")


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected nonempty text")
    return value


def _pointer(parts):
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _nodes(value, parts=()):
    """Include containers and leaves without dropping directional keys or reducing values."""
    if parts:
        yield parts, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _nodes(child, (*parts, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _nodes(child, (*parts, index))


class _Import:
    def __init__(self, artifacts, bindings, manifest, config):
        self.artifacts, self.bindings, self.manifest, self.config = deepcopy((artifacts, bindings, manifest, config))
        self.artifact_id = self.candidate_id = self.locator = None
        self.phase = "contract_error"
        self.paths, self.loaded, self.notebooks, self.csv_rows = {}, {}, {}, {}
        self.used, self.selected_rows, self.selected_json = set(), set(), set()
        self.result = NotebookImportResult()

    def fail(self, code, message):
        raise NotebookImportError(code, message, artifact_id=self.artifact_id,
                                  candidate_id=self.candidate_id, locator=self.locator)

    def artifact(self, aid, kind):
        self.artifact_id = aid
        if aid not in self.artifacts or self.artifacts[aid]["kind"] != kind:
            self.fail("artifact_identity", f"Explicit artifact {aid!r} is not {kind}")
        self.used.add(aid)
        return self.artifacts[aid]

    def prepare(self):
        # Reject non-JSON contracts before doing I/O, including non-finite numbers.
        hash_config([self.artifacts, self.bindings, self.config])
        _keys(self.config, {"version", "sequence_roles", "metric_contexts", "plddt_profiles"})
        if self.config["version"] != "1.0":
            self.fail("unsupported_config", "Unsupported notebook adapter configuration version")
        if not isinstance(self.artifacts, dict) or not self.artifacts or not isinstance(self.bindings, list) or not self.bindings:
            self.fail("invalid_contract", "Nonempty artifact registry and binding list required")
        validate_named(self.manifest, "run_manifest")
        contract = {"config": self.config, "artifacts_sha256": hash_config(self.artifacts),
                    "bindings_sha256": hash_config(self.bindings)}
        if (self.manifest["config_hash"] != hash_config(self.manifest["config"])
                or self.manifest["config"].get("notebook_output_adapter") != contract):
            self.fail("manifest_contract_mismatch", "Manifest must bind the exact config, artifacts and bindings")
        csv_ids = {aid for aid, a in self.artifacts.items() if isinstance(a, dict) and a.get("kind") == "mpnn_csv"}
        if not csv_ids:
            self.fail("invalid_contract", "At least one explicit MPNN CSV artifact is required")
        for key in ("sequence_roles", "metric_contexts"):
            if not isinstance(self.config[key], dict) or set(self.config[key]) != csv_ids:
                self.fail("invalid_config", f"{key} must explicitly cover every CSV artifact")
        for aid in csv_ids:
            roles = self.config["sequence_roles"][aid]
            if (not isinstance(roles, list) or not roles or set(roles) - {"candidate", "target"}
                    or "candidate" not in roles):
                self.fail("invalid_roles", "Supply ordered sequence roles with at least one candidate")
            contexts = self.config["metric_contexts"][aid]
            if (not isinstance(contexts, dict) or set(contexts) != _CSV_SCORES
                    or any(c not in ("monomer", "complex", "counter_screen", "unassigned") for c in contexts.values())):
                self.fail("invalid_contexts", "Supply context for each MPNN/AF2 score")
        common = {"kind", "path", "sha256", "source_run_id", "origin", "fallback_used", "producer", "notebook_ref"}
        for aid, a in self.artifacts.items():
            self.artifact_id = aid
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", aid):
                self.fail("artifact_identity", "Artifact IDs must be simple identifiers, not paths or patterns")
            if not isinstance(a, dict) or a.get("kind") not in ("mpnn_csv", "boltz_json", "pdb", "notebook"):
                self.fail("unsupported_artifact", "Supported artifacts: mpnn_csv, boltz_json, pdb, notebook")
            required = {"kind", "path", "sha256"} if a["kind"] == "notebook" else common
            if a["kind"] in ("pdb", "boltz_json"):
                required = required | {"sample_id"}
            _keys(a, required)
            path = Path(_text(a["path"]))
            if not path.is_absolute() or any(c in a["path"] for c in "*?[]"):
                self.fail("ambiguous_filename", "Provide an exact absolute path; no basename or pattern fallback")
            suffix = {"mpnn_csv": ".csv", "boltz_json": ".json", "pdb": ".pdb", "notebook": ".ipynb"}[a["kind"]]
            if path.suffix.lower() != suffix:
                self.fail("unsupported_artifact", f"Expected a {suffix} artifact")
            self.phase = "artifact_read_error"
            path = path.resolve(strict=True)
            if not path.is_file():
                self.fail("artifact_read_error", "Artifact must be an existing regular file")
            expected = {"path": str(path), "sha256": a["sha256"]}
            if self.manifest["input_files"].count(expected) != 1 or sum(i["path"] == str(path) for i in self.manifest["input_files"]) != 1:
                self.fail("manifest_artifact_mismatch", "Artifact must match exactly one manifest input path/hash")
            if hash_file(path) != a["sha256"]:
                self.fail("stale_artifact_hash", "Artifact bytes do not match the declared SHA-256")
            self.paths[aid] = path
            self.phase = "contract_error"
            if a["kind"] == "notebook":
                continue
            _text(a["source_run_id"])
            if "sample_id" in a:
                _text(a["sample_id"])
            if a["origin"] not in _ORIGINS or (a["fallback_used"] is not None and type(a["fallback_used"]) is not bool):
                self.fail("invalid_origin", "Explicit origin and boolean/null fallback_used required")
            p = a["producer"]
            _keys(p, {"name", "version", "model_id", "checkpoint_id", "seed", "status"})
            if p["status"] not in ("caller_supplied", "unknown"):
                self.fail("unverified_producer", "Producer truth cannot be labeled verified by this adapter")
            for key in ("name", "version", "model_id", "checkpoint_id"):
                if p[key] is not None:
                    _text(p[key])
            if p["seed"] is not None and (type(p["seed"]) is not int or p["seed"] < 0):
                self.fail("invalid_producer", "Seed must be a nonnegative integer or null")
            if p["status"] == "unknown" and any(p[k] is not None for k in ("name", "version", "model_id", "checkpoint_id", "seed")):
                self.fail("invalid_producer", "Unknown producer must retain null metadata")
            prov = {k: p[k] for k in _NULL_PROVENANCE}
            if prov not in self.manifest["supplied_models"] and prov != _NULL_PROVENANCE:
                self.fail("manifest_producer_mismatch", "Producer provenance absent from manifest supplied_models")
        profiles = self.config["plddt_profiles"]
        if not isinstance(profiles, dict):
            self.fail("invalid_profile", "plddt_profiles must be an artifact-keyed object")
        for aid, profile in profiles.items():
            self.artifact_id = aid
            if aid not in self.artifacts or self.artifacts[aid]["kind"] not in ("mpnn_csv", "boltz_json"):
                self.fail("invalid_profile", "Profile must refer to a registered CSV/JSON producer")
            _keys(profile, {"profile", "producer_name", "producer_version"})
            p = self.artifacts[aid]["producer"]
            if (profile["profile"] not in _PROFILES or not p["name"] or not p["version"]
                    or profile["producer_name"] != p["name"] or profile["producer_version"] != p["version"]):
                self.fail("profile_producer_mismatch", "Explicit supported profile must match the declared producer/version")

    def notebook_reference(self, aid):
        ref = self.artifacts[aid]["notebook_ref"]
        if ref is None:
            return {"status": "unknown", "reason": "Notebook cell reference not supplied"}
        _keys(ref, {"artifact_id", "cell_index", "cell_source_sha256", "role"})
        nb = self.artifact(ref["artifact_id"], "notebook")
        if ref["role"] not in ("producer", "consumer") or type(ref["cell_index"]) is not int or ref["cell_index"] < 0:
            self.fail("invalid_cell_reference", "Supply a zero-based cell index and producer/consumer role")
        self.phase = "notebook_parse_error"
        if ref["artifact_id"] not in self.loaded:
            self.loaded[ref["artifact_id"]] = read_json(self.paths[ref["artifact_id"]])
        doc = self.loaded[ref["artifact_id"]]
        cell = doc["cells"][ref["cell_index"]]
        source = cell["source"]
        if isinstance(source, list) and all(isinstance(s, str) for s in source):
            source = "".join(source)
        if not isinstance(source, str):
            self.fail("invalid_cell_reference", "Notebook cell source must be text")
        if hashlib.sha256(source.encode("utf-8")).hexdigest() != ref["cell_source_sha256"]:
            self.fail("stale_cell_hash", "Notebook cell source differs from binding")
        self.phase = "identity_error"
        return {**ref, "notebook_path": str(self.paths[ref["artifact_id"]]), "notebook_sha256": nb["sha256"],
                "cell_id": cell.get("id"), "status": "verified_local", "execution_status": "not_verified"}

    def read_csv(self, aid):
        if aid in self.csv_rows:
            return self.csv_rows[aid]
        self.artifact(aid, "mpnn_csv")
        self.phase = "csv_parse_error"
        with self.paths[aid].open(encoding="utf-8-sig", newline="") as stream:
            text = stream.read()
        lines = text.splitlines(keepends=True)
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader, None)
        if not header or len(set(header)) != len(header) or not {"design", "n", "seq"} <= set(header) or any(not h for h in header):
            self.fail("csv_header_error", "Unique nonempty columns including design/n/seq required")
        rows, previous, record = {}, reader.line_num, 0
        for values in reader:
            start, end = previous + 1, reader.line_num
            previous = end
            if not values:
                continue
            record += 1
            self.locator = {"row": start, "row_end": end, "record": record}
            if len(values) != len(header):
                self.fail("csv_width_error", "CSV record width differs from header")
            raw = dict(zip(header, values))
            for key in ("design", "n"):
                if not re.fullmatch(r"[0-9]+", raw[key]):
                    self.fail("missing_csv_identity", "design/n must be explicit digit strings; no normalization")
            key = (raw["design"], raw["n"])
            if key in rows:
                self.fail("duplicate_csv_identity", "Repeated design/n in the same CSV artifact")
            rows[key] = {"raw": raw, "header": header, "row": start, "row_end": end,
                         "record": record, "raw_record": "".join(lines[start-1:end])}
        if not rows:
            self.fail("empty_csv", "CSV must contain data records")
        self.csv_rows[aid] = rows
        return rows

    def pdb_binding(self, binding, sequences, roles, run_id, sample_id):
        _keys(binding, {"artifact_id", "model_id", "residue_map", "chains"})
        aid = binding["artifact_id"]
        a = self.artifact(aid, "pdb")
        if a["source_run_id"] != run_id or a["sample_id"] != sample_id:
            self.fail("pdb_sample_mismatch", "PDB source run/sample differs from explicit score binding")
        _text(binding["model_id"])
        self.phase = "pdb_parse_error"
        structure = read_structure(self.paths[aid], model_id=binding["model_id"])
        self.phase = "identity_error"
        rows = canonical_residue_map(structure)
        if rows != binding["residue_map"] or structure.source_hash != a["sha256"]:
            self.fail("stale_residue_map", "Canonical map/PDB hash must match this explicit model and altloc A")
        if not isinstance(binding["chains"], list) or len(binding["chains"]) != len(sequences):
            self.fail("chain_mapping_mismatch", "Explicit mapping required for every slash-delimited sequence chain")
        mapped, identities = set(), set()
        for index, (chain, seq, role) in enumerate(zip(binding["chains"], sequences, roles)):
            _keys(chain, {"sequence_index", "chain_id", "segment", "role", "entries"})
            if type(chain["sequence_index"]) is not int or chain["sequence_index"] != index or chain["role"] != role:
                self.fail("wrong_chain_role", "Chain role/index differs from explicit CSV sequence-role configuration")
            if not isinstance(chain["chain_id"], str) or type(chain["segment"]) is not int:
                self.fail("chain_mapping_mismatch", "Chain ID/segment must preserve canonical types")
            identity = (chain["chain_id"], chain["segment"])
            if identity in identities:
                self.fail("chain_mapping_mismatch", "Two sequence chains cannot map to one PDB chain/segment")
            identities.add(identity)
            checks = validate_sequence_mapping(structure, seq, chain["entries"])
            for check in checks:
                if check["status"] != "matched":
                    self.fail("sequence_mapping_mismatch", "v1 requires complete matched sequence-to-PDB mapping")
                idx = check["residue_index"]
                row = rows[idx]
                if idx in mapped or (row["chain_id"], row["segment"]) != identity:
                    self.fail("chain_mapping_mismatch", "Sequence position maps to the wrong or repeated chain residue")
                mapped.add(idx)
        if mapped != {r["residue_index"] for r in rows} or any(r["record_group"] != "ATOM" for r in rows):
            self.fail("chain_mapping_mismatch", "Every supplied PDB residue must be mapped polymer ATOM")
        return {"artifact_id": aid, "path": str(self.paths[aid]), "sha256": a["sha256"],
                "model_id": structure.model_id, "residue_map_sha256": hash_config(rows),
                "residue_map": rows, "chains": deepcopy(binding["chains"]),
                "notebook": deepcopy(self.notebooks[aid]), "producer": deepcopy(a["producer"]),
                "hash_status": "verified_local", "identity_status": "caller_supplied_binding_locally_consistent"}

    def metric(self, aid, parts, raw, *, row=None, row_end=None, record=None, present=True):
        a = self.artifacts[aid]
        pointer = _pointer(parts)
        name = f"{aid}:{pointer}"
        key = parts[0]
        is_csv = a["kind"] == "mpnn_csv"
        pair = not is_csv and len(parts) == 3 and key == "pair_chains_iptm"
        known = key in _CSV_SCORES if is_csv else (len(parts) == 1 and key in _BOLTZ_SCORES) or pair
        context = self.config["metric_contexts"][aid].get(key, "unassigned") if is_csv else "complex" if known else "unassigned"
        category = "sequence_model_score" if is_csv and key == "mpnn" else "model_confidence" if known else "unclassified_supplied"
        source = {"path": str(self.paths[aid]), "sha256": a["sha256"], "row": row}
        prov = {k: a["producer"][k] for k in _NULL_PROVENANCE}
        m = supplied_metric(name, raw, context=context, category=category, source=source, provenance=prov)
        status, reason, transform = "available", None, None
        if not present or raw is None or (isinstance(raw, str) and raw.strip().lower() in ("", "na", "n/a", "null", "none")):
            status, reason = "missing", "missing_column" if not present else "missing_value"
        elif isinstance(raw, (dict, list)):
            status, reason = "raw_only", "nested_container_preserved_without_aggregation"
        elif m["value"] is None:
            try:
                nonfinite = isinstance(raw, str) and not math.isfinite(float(raw))
            except (ValueError, OverflowError):
                nonfinite = False
            status, reason = ("non_finite", "non_finite_token") if nonfinite else ("raw_only", "not_a_finite_numeric_scalar")
        if status == "available" and not known:
            status, reason = "raw_only", "unsupported_semantics: unclassified field"
        if status == "available" and is_csv and key == "rmsd":
            status, reason = "raw_only", "unsupported_semantics: RMSD atom selection/alignment not verified"
        if status == "available" and key in _PLDDT:
            profile = self.config["plddt_profiles"].get(aid)
            if profile is None:
                status, reason = "raw_only", "plddt_profile_not_supplied"
            else:
                maximum, factor = _PROFILES[profile["profile"]]
                if not 0 <= m["value"] <= maximum:
                    status, reason = "invalid_value", "plddt_outside_explicit_profile_range"
                else:
                    m["value"] *= factor
                    m["scale"] = "0-100"
                    transform = {**profile, "factor": factor, "input_scale": f"0-{maximum}", "output_scale": "0-100"}
        if status == "available":
            bounded = pair or key in ("i_ptm", "confidence_score", "ptm", "iptm", "protein_iptm", "ligand_iptm")
            if m["value"] < 0 or (bounded and m["value"] > 1):
                status, reason = "invalid_value", "outside_supported_numeric_domain"
        if status != "available":
            m["value"], m["missing_reason"] = None, reason
        locator = {"column": key, "record": record, "row": row, "row_end": row_end} if is_csv else {"json_pointer": pointer}
        meta = {"raw_name": key, "locator": locator, "source": source, "status": status, "reason": reason,
                "producer": deepcopy(a["producer"]), "notebook": self.notebooks[aid],
                "artifact_id": aid, "source_run_id": a["source_run_id"], "sample_id": a.get("sample_id"),
                "declared_origin": a["origin"], "fallback_used": a["fallback_used"],
                "hash_status": "verified_local", "identity_status": "caller_supplied_binding_locally_consistent",
                "transform": transform}
        return m, meta

    def run(self):
        self.prepare()
        for aid, a in self.artifacts.items():
            if a["kind"] != "notebook":
                self.artifact_id = aid
                self.notebooks[aid] = self.notebook_reference(aid)
        ids = set()
        for b in self.bindings:
            self.phase, self.locator, self.artifact_id = "identity_error", None, None
            _keys(b, {"candidate_id", "source_run_id", "csv_artifact", "design", "n", "target_id",
                      "conformer_id", "pdb", "boltz", "boltz_missing_reason"})
            self.candidate_id = _text(b["candidate_id"])
            if b["candidate_id"] in ids:
                self.fail("duplicate_candidate_binding", "Each candidate ID must have exactly one binding")
            ids.add(b["candidate_id"])
            for key in ("source_run_id", "design", "n"):
                _text(b[key])
            for key in ("target_id", "conformer_id"):
                if b[key] is not None:
                    _text(b[key])
            aid = b["csv_artifact"]
            csv_art = self.artifact(aid, "mpnn_csv")
            if b["source_run_id"] != csv_art["source_run_id"]:
                self.fail("source_run_mismatch", "CSV binding source_run_id differs from registry")
            selector = (aid, b["design"], b["n"])
            if selector in self.selected_rows:
                self.fail("duplicate_row_binding", "A CSV design/n record may bind to only one candidate")
            self.selected_rows.add(selector)
            rows = self.read_csv(aid)
            if (b["design"], b["n"]) not in rows:
                self.fail("missing_csv_binding", "Explicit design/n not present in CSV")
            row = rows[(b["design"], b["n"])]
            self.phase, self.locator = "identity_error", {"row": row["row"]}
            seqs = row["raw"]["seq"].split("/")
            roles = self.config["sequence_roles"][aid]
            if len(seqs) != len(roles) or any(not s for s in seqs):
                self.fail("sequence_role_mismatch", "CSV chains differ from explicit sequence-role configuration")
            pdbs = [self.pdb_binding(b["pdb"], seqs, roles, b["source_run_id"], b["n"])]
            metrics, fields, bound = [], {}, [aid, b["pdb"]["artifact_id"]]
            names = list(row["header"]) + sorted(_CSV_SCORES - set(row["header"]))
            for key in names:
                m, field_meta = self.metric(aid, (key,), row["raw"].get(key), row=row["row"], row_end=row["row_end"],
                                             record=row["record"], present=key in row["raw"])
                metrics.append(m); fields[m["name"]] = field_meta
            if not isinstance(b["boltz"], list):
                self.fail("invalid_binding", "boltz must explicitly list all confidence artifacts, or [] with a reason")
            if not b["boltz"]:
                _text(b["boltz_missing_reason"])
            elif b["boltz_missing_reason"] is not None:
                self.fail("invalid_binding", "boltz_missing_reason must be null when predictions are supplied")
            samples = set()
            for prediction in b["boltz"]:
                _keys(prediction, {"artifact_id", "source_run_id", "sample_id", "pdb", "chain_key_map"})
                bid = prediction["artifact_id"]
                a = self.artifact(bid, "boltz_json")
                self.locator = None
                sample = (prediction["source_run_id"], prediction["sample_id"])
                if sample != (a["source_run_id"], a["sample_id"]):
                    self.fail("boltz_sample_mismatch", "Explicit Boltz run/sample differs from registry")
                if bid in self.selected_json or sample in samples:
                    self.fail("duplicate_sample_binding", "Boltz artifact/sample cannot bind twice or to two candidates")
                self.selected_json.add(bid); samples.add(sample)
                keymap = prediction["chain_key_map"]
                if (not isinstance(keymap, dict) or len(keymap) != len(seqs)
                        or any(not isinstance(k, str) or not k for k in keymap)
                        or any(type(v) is not int for v in keymap.values()) or set(keymap.values()) != set(range(len(seqs)))):
                    self.fail("invalid_chain_key_map", "Boltz chain keys must map one-to-one onto all CSV sequence indices")
                pdbs.append(self.pdb_binding(prediction["pdb"], seqs, roles, *sample))
                self.artifact_id, self.phase = bid, "json_parse_error"
                raw = read_json(self.paths[bid])
                hash_config(raw)  # Reject numeric overflow to non-finite JSON.
                if not isinstance(raw, dict):
                    self.fail("json_shape_error", "Boltz confidence must be a JSON object")
                pairs = raw.get("pair_chains_iptm")
                if pairs is not None:
                    self.phase = "identity_error"
                    if not isinstance(pairs, dict) or any(k not in keymap for k in pairs):
                        self.fail("unknown_pair_chain", "Directional chain key absent from explicit chain_key_map")
                    for neighbors in pairs.values():
                        if not isinstance(neighbors, dict) or any(k not in keymap for k in neighbors):
                            self.fail("unknown_pair_chain", "Directional partner key absent from explicit chain_key_map")
                for parts, value in _nodes(raw):
                    m, fm = self.metric(bid, parts, value)
                    metrics.append(m); fields[m["name"]] = fm
                # Explicitly represent missing known top-level confidence fields.
                for key in sorted(_BOLTZ_SCORES - set(raw)):
                    m, fm = self.metric(bid, (key,), None, present=False)
                    metrics.append(m); fields[m["name"]] = fm
                bound.extend((bid, prediction["pdb"]["artifact_id"]))
            declared = {self.artifacts[x]["origin"] for x in bound}
            conflict = "origin_conflict" in declared or ("design" in declared and "demo" in declared)
            conflict |= any(self.artifacts[x]["origin"] == "design" and self.artifacts[x]["fallback_used"] is True for x in bound)
            origin = "origin_conflict" if conflict else "unknown" if "unknown" in declared else "demo" if "demo" in declared else "design"
            diagnostics = []
            for m in metrics:
                fm = fields[m["name"]]
                if origin != "design":
                    fm["raw_status"] = fm["status"]
                    fm["raw_reason"] = fm["reason"]
                    fm["status"], fm["reason"] = "quarantined", f"origin={origin}"
                    m["value"], m["category"], m["missing_reason"] = None, "quarantined_origin", f"origin={origin}"
                if fm["status"] != "available":
                    diagnostics.append({"severity": "warning", "code": fm["status"], "message": fm["reason"],
                                        "candidate_id": b["candidate_id"], "artifact_id": fm["artifact_id"],
                                        "locator": fm["locator"], "metric": m["name"]})
            audit = {"adapter": "notebook_output_adapter", "version": "1.0", "origin": origin,
                     "binding": deepcopy(b), "binding_sha256": hash_config(b), "csv_record": row,
                     "field_provenance": fields, "pdb_bindings": pdbs,
                     "artifacts": {x: deepcopy(self.artifacts[x]) for x in dict.fromkeys(bound)},
                     "configuration": self.config, "configuration_sha256": hash_config(self.config),
                     "manifest": {"run_id": self.manifest["run_id"], "sha256": hash_config(self.manifest),
                                  "config_hash": self.manifest["config_hash"]},
                     "boltz_missing_reason": b["boltz_missing_reason"]}
            metrics.append(supplied_metric(_META, audit, context="unassigned", category="import_metadata",
                                           source={"path": str(self.paths[aid]), "sha256": csv_art["sha256"], "row": row["row"]},
                                           provenance=_NULL_PROVENANCE, missing_reason="non-scalar audit metadata"))
            seq = "/".join(s for s, role in zip(seqs, roles) if role == "candidate")
            missing = {key: "not supplied" for key in ("target_id", "conformer_id") if b[key] is None}
            c = CandidateEvidence(b["candidate_id"], sequence_hash(seq), b["target_id"], b["conformer_id"], metrics,
                                  deepcopy(_NULL_PROVENANCE),
                                  [f"origin={origin}", "Producer provenance is per metric; aggregate producer is unassigned",
                                   "Local binding consistency is not verified upstream run history or biological identity",
                                   "Confidence is not measured affinity, specificity, uptake or biological success",
                                   "Monomer-context fields in complex predictions are not independent monomer inference"], missing)
            c.to_dict()
            (self.result.candidates if origin == "design" else self.result.quarantined).append(c)
            self.result.diagnostics.extend(diagnostics)
        self.candidate_id, self.locator = None, None
        expected = {(aid, d, n) for aid in self.config["sequence_roles"] for d, n in self.read_csv(aid)}
        if self.selected_rows != expected:
            self.fail("unbound_csv_rows", "Every supplied CSV record requires exactly one explicit binding")
        if self.used != set(self.artifacts):
            self.fail("unused_artifacts", "Registered artifacts must be explicitly consumed; no silent selection")
        for aid, path in self.paths.items():
            self.artifact_id = aid
            if hash_file(path) != self.artifacts[aid]["sha256"]:
                self.fail("artifact_changed_during_import", "Artifact bytes changed before import completed")
        self.result.to_dict()
        return self.result


def import_notebook_outputs(*, artifacts, bindings, manifest, config):
    """Import explicit CSV/JSON/PDB references with all-or-error identity validation.

    Returns NotebookImportResult. Fatal errors raise NotebookImportError with
    diagnostics and no partial candidates. See docs/API.md for the version-1
    registry/binding contract. Unknown/demo/conflicting origins never enter
    result.candidates; only that list is intended for default numeric filtering.
    """
    job = None
    try:
        job = _Import(artifacts, bindings, manifest, config)
        return job.run()
    except NotebookImportError:
        raise
    except (ValueError, TypeError, KeyError, IndexError, OSError, csv.Error, OverflowError, AttributeError, RecursionError) as exc:
        if job is None:
            raise NotebookImportError("contract_error", str(exc)) from exc
        raise NotebookImportError(job.phase, str(exc), artifact_id=job.artifact_id,
                                  candidate_id=job.candidate_id, locator=job.locator) from exc
