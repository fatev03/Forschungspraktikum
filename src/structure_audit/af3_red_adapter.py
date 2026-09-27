"""AF3-ReD external inventory / pre-admission only (Python 3.10+, stdlib).

Paste cells marked # %% into Colab, or import this module. No import-time I/O,
writes, subprocesses, inference, ranking, geometry or core-schema integration.
An admitted artifact is ready ONLY for explicit mapping preparation.
"""

# %% 1. Records and read-only helpers
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

ADAPTER_VERSION = "0.2"
_SAMPLE = re.compile(r"seed-(0|[1-9][0-9]*)_sample-(0|[1-9][0-9]*)")
_FORMATS = {".cif": "mmcif", ".mmcif": "mmcif", ".pdb": "pdb"}
_SIDECAR = "af3red_adapter_metadata.json"  # Assumed schema, NOT upstream output.


@dataclass(frozen=True)
class AF3ReDRunIdentity:
    run_id: str                 # Local identity: canonical path + input byte hash.
    directory: str
    job_name: str
    input_path: str
    input_sha256: str
    model_seeds: tuple
    declared_ligands: tuple     # Input declarations, not observed ligand presence.
    bias_sigma: float | None
    bias_weight: float | None   # ReD bias parameter, NOT checkpoint weights.
    declaration: dict | None
    provenance: tuple
    missing: tuple


@dataclass(frozen=True)
class StructureArtifact:
    artifact_id: str
    run_id: str
    path: str
    sha256: str
    format: str
    role: str
    seed: int | None
    sample: int | None
    status: str = "candidate"
    reasons: tuple = ()
    binding: dict | None = None
    read_provenance: dict | None = None


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _path(value, root=None):
    path = Path(os.path.abspath(value))
    if path.resolve() != path:
        raise ValueError(f"Symlink aliases are unsupported: {path}")
    if root is not None and not path.is_relative_to(root):
        raise ValueError(f"Path outside declared root: {path}")
    return path


def _read(path):
    path = _path(path)
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"Not a regular file: {path}")
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, f) != getattr(after, f) for f in fields):
        raise ValueError(f"File changed during read: {path}")
    return data, {"path": str(path), "sha256": _digest(data)}


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json(path):
    data, provenance = _read(path)
    obj = json.loads(data, object_pairs_hook=_unique_pairs)
    _json_bytes(obj)  # Reject NaN/Infinity, including overflowing JSON numbers.
    if not isinstance(obj, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return obj, provenance


def _files(root):
    root = _path(root)
    if not root.is_dir():
        raise ValueError(f"Existing output directory required: {root}")
    def fail(error):
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=fail):
        for name in sorted(dirs + files):
            if (Path(directory) / name).is_symlink():
                raise ValueError(f"Symlink in inventory root: {Path(directory) / name}")
        dirs.sort()
        for name in sorted(files):
            yield Path(directory) / name


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected nonempty text")
    return value


# %% 2. Run discovery: only directories anchored by exactly one *_data.json
def discover_red_runs(output_root):
    """Return AF3-compatible run candidates; layout alone cannot prove ReD use.

    Invalid/ambiguous metadata raises ValueError, without a partial return.
    No anchors means []; source/test CIFs are never treated as inference runs.
    """
    anchors = {}
    for path in _files(output_root):
        if path.name.endswith("_data.json"):
            if path.parent in anchors:
                raise ValueError(f"Ambiguous input JSONs in {path.parent}")
            anchors[path.parent] = path
    runs = []
    for directory, input_path in sorted(anchors.items()):
        if any(p != directory and directory.is_relative_to(p) for p in anchors):
            raise ValueError("Nested run directories are unsupported")
        obj, prov = _load_json(input_path)
        if obj.get("dialect") != "alphafold3" or type(obj.get("version")) is not int or obj["version"] not in (1, 2, 3):
            raise ValueError("Only alphafold3 input versions 1/2/3 are supported")
        job = re.sub(r"[^a-z0-9_.-]", "", _text(obj.get("name")).lower().replace(" ", "_"))
        if not job or input_path.name != f"{job}_data.json":
            raise ValueError("Input filename disagrees with sanitized job name")
        seeds = obj.get("modelSeeds")
        if (not isinstance(seeds, list) or not seeds
                or any(type(s) is not int or s < 0 for s in seeds)
                or len(set(seeds)) != len(seeds)):
            raise ValueError("Expected unique nonnegative integer modelSeeds")
        sequences = obj.get("sequences")
        if not isinstance(sequences, list) or not sequences:
            raise ValueError("Missing input sequences")
        ligands, ids = [], set()
        for entry in sequences:
            if not isinstance(entry, dict) or len(entry) != 1 or not set(entry) <= {"protein", "rna", "dna", "ligand"}:
                raise ValueError("Unsupported sequence entry")
            kind, entity = next(iter(entry.items()))
            if not isinstance(entity, dict):
                raise ValueError("Expected entity object")
            chain_ids = entity.get("id")
            chain_ids = [chain_ids] if isinstance(chain_ids, str) else chain_ids
            if not isinstance(chain_ids, list) or not chain_ids:
                raise ValueError("Explicit entity IDs required")
            for chain in chain_ids:
                _text(chain)
                if chain in ids:
                    raise ValueError("Duplicate input chain ID")
                ids.add(chain)
            if kind == "ligand":
                ccd, smiles = entity.get("ccdCodes"), entity.get("smiles")
                if (ccd is None) == (smiles is None):
                    raise ValueError("Ligand requires exactly one of ccdCodes/smiles")
                if ccd is not None:
                    if not isinstance(ccd, list) or not ccd:
                        raise ValueError("Expected nonempty CCD list")
                    for code in ccd:
                        _text(code)
                else:
                    _text(smiles)
                ligands.append({"ids": chain_ids, "ccdCodes": ccd, "smiles": smiles})
            else:
                _text(entity.get("sequence"))
        declaration, provenance = None, [prov]
        sigma = weight = None
        missing = ["af3red_execution_declaration_missing", "bias_sigma_unknown", "bias_weight_unknown"]
        sidecar = directory / _SIDECAR
        if sidecar.exists():
            declaration, side_prov = _load_json(sidecar)
            expected = {"schema_version", "producer", "declared_run_id", "input_sha256",
                        "bias_sigma", "bias_weight", "source_revision", "evidence_note"}
            if set(declaration) != expected or declaration["schema_version"] != "0.1" or declaration["producer"] != "AF3-ReD":
                raise ValueError("Unsupported adapter sidecar (assumed schema 0.1)")
            if declaration["input_sha256"] != prov["sha256"]:
                raise ValueError("Sidecar input hash mismatch")
            for key in ("declared_run_id", "evidence_note"):
                _text(declaration[key])
            if declaration["source_revision"] is not None:
                _text(declaration["source_revision"])
            sigma, weight = declaration["bias_sigma"], declaration["bias_weight"]
            missing = []
            for key, value, lower in (("bias_sigma", sigma, 0.1), ("bias_weight", weight, 0.0)):
                if value is None:
                    missing.append(key + "_unknown")
                elif type(value) not in (float, int) or not math.isfinite(value) or value < lower:
                    raise ValueError(f"Invalid declared {key}")
            provenance.append(side_prov)
        run_id = _digest(_json_bytes([str(directory), prov["sha256"]]))
        runs.append(AF3ReDRunIdentity(run_id, str(directory), job, str(input_path),
                    prov["sha256"], tuple(seeds), tuple(ligands), sigma, weight,
                    declaration, tuple(provenance), tuple(missing)))
    return tuple(runs)


def _verify_run(run):
    for record in run.provenance:
        if _read(record["path"])[1] != record:
            raise ValueError("Run metadata changed since discovery")
    if run.declaration is None and (Path(run.directory) / _SIDECAR).exists():
        raise ValueError("Run metadata appeared since discovery; rediscover")


# %% 3. Structure inventory: no coordinate interpretation
def _inventory_artifact(path, run):
    path = _path(path, _path(run.directory))
    compressed = any(path.name.lower().endswith(s + ".gz") for s in _FORMATS)
    if path.suffix.lower() not in _FORMATS and not compressed:
        return None
    data, prov = _read(path)
    relative = path.relative_to(run.directory)
    role, seed, sample = "unrecognized_or_converted", None, None
    reasons, status = ["unrecognized_or_converted_layout"], "candidate"
    if len(relative.parts) == 1 and path.name == f"{run.job_name}_model.cif":
        role, reasons = "upstream_selected_copy", ["root_copy_not_an_independent_sample"]
    elif len(relative.parts) == 2 and (match := _SAMPLE.fullmatch(path.parent.name)):
        seed, sample = map(int, match.groups())
        if path.name == f"{run.job_name}_{path.parent.name}_model.cif":
            role, reasons = "native_sample", []
        if seed not in run.model_seeds:
            status, reasons = "rejected", ["seed_not_in_input"]
    if compressed:
        status, reasons = "rejected", ["compressed_structure_unsupported"]
    if not data:
        status, reasons = "rejected", ["empty_structure"]
    artifact_id = _digest(_json_bytes([run.run_id, str(relative), prov["sha256"]]))
    return StructureArtifact(artifact_id, run.run_id, str(path), prov["sha256"],
                             _FORMATS.get(path.suffix.lower(), "unsupported"), role, seed, sample,
                             status, tuple(reasons))


def discover_structure_files(run):
    """Inventory structures inside one run; retain root copy as a separate role.

    Only exact native sample CIF names can advance to pre-admission. Renamed,
    converted or compressed structures remain visible but cannot be promoted.
    """
    _verify_run(run)
    root, artifacts = _path(run.directory), []
    for path in _files(root):
        if path.name.endswith("_data.json") and str(path) != run.input_path:
            raise ValueError("Unexpected/nested input JSON; rediscover runs")
        artifact = _inventory_artifact(path, run)
        if artifact is not None:
            artifacts.append(artifact)
    _verify_run(run)
    return tuple(artifacts)


# %% 4. Explicit, narrow readiness gate (reader supplied by the notebook)
def _check_reader_profile(profile, reader):
    if profile not in ("strict", "af3_native_v1"):
        raise ValueError("Unknown reader profile; expected strict or af3_native_v1")
    if profile == "af3_native_v1" and reader is not None:
        raise ValueError("Native profile selects its bridge explicitly; reader= is strict-only")
    if reader is not None and (not callable(reader) or getattr(reader, "reader_profile", "strict") != "strict"):
        raise ValueError("reader= requires a strict callback; select profile='af3_native_v1' for the bridge")


def _get_native_reader():
    if globals().get("__package__"):
        from .af3_native_bridge import read_af3_native_cif
    else:
        # Standalone notebook: bridge cell must be executed explicitly first.
        read_af3_native_cif = globals().get("read_af3_native_cif")
    if not callable(read_af3_native_cif) or getattr(read_af3_native_cif, "reader_profile", None) != "af3_native_v1":
        raise ValueError("AF3 native bridge unavailable; execute its notebook cell first")
    return read_af3_native_cif


def validate_basic_mapping_readiness(artifact, run, *, binding=None, reader=None, profile="strict"):
    """Return a NEW record; no profile sniffing or automatic reader fallback.

    Strict binding: artifact_sha256, target_id, model_id, auth_chain_id, segment.
    Native binding: artifact_sha256, target_id, model_id, auth_asym_id, label_asym_id.
    reader= remains strict-only. Invalid profile/callback combinations raise.
    This checks bytes and explicitly selected observed identities, not receptor
    identity, sequence correspondence, completeness or downstream admission.
    """
    _check_reader_profile(profile, reader)
    read_provenance = {"profile": profile, "read_completed": False}

    def result(status, *reasons, bound=None):
        return replace(artifact, status=status, reasons=tuple(reasons), binding=bound,
                       read_provenance=json.loads(_json_bytes(read_provenance)))
    try:
        _verify_run(run)
        path = _path(artifact.path, _path(run.directory))
        if artifact.run_id != run.run_id or _read(path)[1]["sha256"] != artifact.sha256:
            raise ValueError("Artifact/run or byte hash mismatch")
        # Never trust a caller-modified role/seed/status to authorize promotion.
        current = _inventory_artifact(path, run)
        if current is None or any(getattr(current, k) != getattr(artifact, k) for k in
                                  ("artifact_id", "format", "role", "seed", "sample")):
            raise ValueError("Artifact inventory identity mismatch")
        if current.status == "rejected":
            return result("rejected", *current.reasons)
        if artifact.role != "native_sample":
            return result("candidate", *current.reasons)
        if binding is None:
            return result("candidate", *run.missing, "explicit_target_model_chain_binding_required")
        required = {"artifact_sha256", "target_id", "model_id"} | (
            {"auth_asym_id", "label_asym_id"} if profile == "af3_native_v1" else {"auth_chain_id", "segment"})
        if not isinstance(binding, dict) or set(binding) != required:
            raise ValueError("Invalid binding fields")
        binding = json.loads(_json_bytes(binding))  # Detached audit copy.
        if binding["artifact_sha256"] != artifact.sha256:
            raise ValueError("Binding artifact hash mismatch")
        for key in ("target_id", "model_id"):
            _text(binding[key])
        if profile == "af3_native_v1":
            for key in ("auth_asym_id", "label_asym_id"):
                _text(binding[key])
            native_reader = _get_native_reader()
            read_provenance.update(reader="read_af3_native_cif", reader_version=native_reader.reader_version)
            native = native_reader(path, model_id=binding["model_id"])
            read_provenance.update(native.provenance(), read_completed=True)
            if native.source_sha256 != artifact.sha256 or native.selected_model != binding["model_id"]:
                raise ValueError("Native reader source hash/model mismatch")
            if not any(row.fields["_atom_site.group_pdb"] == "ATOM" and
                       row.fields["_atom_site.auth_asym_id"] == binding["auth_asym_id"] and
                       row.fields["_atom_site.label_asym_id"] == binding["label_asym_id"] for row in native.rows):
                raise ValueError("Selected ATOM author/label chain pair absent")
        else:
            _text(binding["auth_chain_id"])
            if type(binding["segment"]) is not int or binding["segment"] < 0:
                raise ValueError("Invalid segment")
            if reader is None:
                return result("candidate", *run.missing, "structure_reader_required", bound=binding)
            read_provenance.update(reader=getattr(reader, "__module__", "") + "." +
                                   getattr(reader, "__qualname__", type(reader).__name__))
            structure = reader(path, model_id=binding["model_id"])
            if not all(hasattr(structure, name) for name in ("source_hash", "model_id", "atoms", "warnings")):
                raise ValueError("Strict callback must return the strict Structure API; no native bridge substitution")
            read_provenance.update(source_sha256=structure.source_hash, selected_model=structure.model_id,
                                   read_completed=True)
            if structure.source_hash != artifact.sha256 or str(structure.model_id) != binding["model_id"]:
                raise ValueError("Reader source hash/model mismatch")
            if not structure.atoms or any(not all(math.isfinite(v) for v in atom.xyz) for atom in structure.atoms):
                raise ValueError("Empty/nonfinite coordinate records")
            if any(w["code"] in {"duplicate_atom_id", "duplicate_residue_id"} for w in structure.warnings):
                raise ValueError("Ambiguous atom/residue identity")
            if any(a.altloc for a in structure.atoms):
                raise ValueError("Alternate locations require a later explicit policy")
            if not any(a.group == "ATOM" and (a.chain_id, a.segment) ==
                       (binding["auth_chain_id"], binding["segment"]) for a in structure.atoms):
                raise ValueError("Selected ATOM author chain/segment absent")
        _verify_run(run)
        if _read(path)[1]["sha256"] != artifact.sha256:
            raise ValueError("Artifact changed during validation")
        if run.missing:
            return result("candidate", *run.missing, bound=binding)
        return result("admitted", "external_mapping_preparation_only", bound=binding)
    except (OSError, ValueError, UnicodeError) as exc:
        return result("rejected", f"{type(exc).__name__}: {exc}")


# %% 5. In-memory manifest, deliberately separate from the core run_manifest
def build_red_manifest(output_root, *, bindings=None, reader=None, profile="strict"):
    """bindings maps artifact_id -> explicit binding; never writes a manifest.

    Unknown bindings/invalid run metadata abort the call (no partial return).
    Per-structure failures remain rejected inventory records. Rebuild to recheck.
    """
    _check_reader_profile(profile, reader)
    bindings = {} if bindings is None else json.loads(_json_bytes(bindings))
    if not isinstance(bindings, dict):
        raise ValueError("bindings must be an artifact-ID dictionary")
    runs = discover_red_runs(output_root)
    artifacts = []
    for run in runs:
        for artifact in discover_structure_files(run):
            artifacts.append(validate_basic_mapping_readiness(
                artifact, run, binding=bindings.get(artifact.artifact_id), reader=reader, profile=profile))
    if set(bindings) - {a.artifact_id for a in artifacts}:
        raise ValueError("Binding refers to an undiscovered/stale artifact ID")
    for run in runs:
        _verify_run(run)
    manifest = {"schema": "af3red_external_inventory/0.2", "adapter_version": ADAPTER_VERSION,
                "reader_profile": profile,
                "scope": "external_conformer_inventory_and_admission_prep",
                "status_scope": "admitted_means_mapping_preparation_only",
                "root": str(_path(output_root)), "runs": [asdict(r) for r in runs],
                "artifacts": [asdict(a) for a in artifacts],
                "diagnostics": (["no_recognized_runs"] if not runs else []) +
                               (["no_structure_artifacts"] if not artifacts else [])}
    manifest = json.loads(_json_bytes(manifest))
    manifest["manifest_sha256"] = _digest(_json_bytes(manifest))
    return manifest
