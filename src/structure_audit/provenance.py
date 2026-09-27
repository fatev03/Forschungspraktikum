"""Strict JSON provenance and output allocation; never overwrite results."""
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from . import __version__
from .validation import validate, validate_named


def canonical_json(value):
    validate(value, {})
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_config(config):
    return hashlib.sha256(canonical_json(config)).hexdigest()


def create_run_directory(root, run_id=None):
    run_id = run_id or (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12])
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", run_id):
        raise ValueError("run_id must be 1-100 safe filename characters")
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    parent = root / run_id
    if parent.is_symlink():
        raise ValueError("Run parent must not be a symlink")
    parent.mkdir(exist_ok=True)
    for version in range(1, 1000000):
        path = parent / f"v{version:04d}"
        try:
            path.mkdir()  # exclusive, also rejects existing symlinks
            return path
        except FileExistsError:
            continue
    raise RuntimeError("Run version limit reached")


def git_provenance(root):
    root = Path(root).resolve()
    if not (root / ".git").exists():
        return None, None, ["git_unavailable: supplied project root has no .git"]
    try:
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "--no-optional-locks", "-C", str(root),
                                     "status", "--porcelain"], capture_output=True,
                                    text=True, check=True).stdout)
        return commit, dirty, []
    except (OSError, subprocess.CalledProcessError):
        return None, None, ["git_unavailable: unable to read local git provenance"]


def make_manifest(run_dir, config, input_files, *, project_root, seed=None,
                  supplied_models=None, output_paths=None, status="completed", warnings=None):
    run_dir = Path(run_dir).resolve()
    commit, dirty, git_warnings = git_provenance(project_root)
    notes = list(warnings or []) + git_warnings
    if seed is None:
        notes.append("seed_not_supplied: upstream random seed is unknown")
    models = list(supplied_models or [])
    if not models:
        notes.append("model_provenance_not_supplied")
    inputs = [{"path": str(Path(p).resolve()), "sha256": hash_file(p)} for p in input_files]
    result = {
        "schema_version": "1.0", "run_id": run_dir.parent.name,
        "run_directory": str(run_dir), "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": commit, "git_dirty": dirty, "config": config,
        "config_hash": hash_config(config), "input_files": inputs,
        "random_seed": seed, "supplied_models": models,
        "output_paths": list(output_paths or []), "status": status,
        "warnings": notes, "utility_version": __version__,
    }
    validate_named(result, "run_manifest")
    return result


def write_json_new(path, data):
    content = canonical_json(data).decode("utf-8") + "\n"
    with Path(path).open("x", encoding="utf-8") as handle:
        handle.write(content)


def write_manifest(path, manifest):
    validate_named(manifest, "run_manifest")
    if manifest["config_hash"] != hash_config(manifest["config"]):
        raise ValueError("Manifest config hash mismatch")
    try:
        stamp = datetime.fromisoformat(manifest["timestamp"])
    except ValueError as exc:
        raise ValueError("Invalid manifest timestamp") from exc
    if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError("Manifest timestamp must be UTC")
    run_dir = Path(manifest["run_directory"]).resolve()
    if Path(path).resolve().parent != run_dir:
        raise ValueError("Manifest must be written inside its run directory")
    for output in manifest["output_paths"]:
        if not Path(output).resolve().is_relative_to(run_dir):
            raise ValueError("Output path escapes run directory")
    write_json_new(path, manifest)
