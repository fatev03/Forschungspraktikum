"""Offline report orchestration, confined to newly allocated run directories."""
import csv
import json
from pathlib import Path

from .checks import structure_integrity_check, coarse_steric_clash_check
from .mapping import canonical_residue_map
from .provenance import create_run_directory, make_manifest, write_manifest, write_json_new, hash_file
from .structures import read_structure
from .validation import read_json


def audit_supplied_structure(input_path, output_root, config, *, project_root, run_id=None):
    if not isinstance(config, dict) or set(config) - {"model_id", "integrity", "clash", "seed", "supplied_models"}:
        raise ValueError("Unknown top-level configuration")
    structure = read_structure(input_path, model_id=config.get("model_id"))
    results = [structure_integrity_check(structure, config.get("integrity")),
               coarse_steric_clash_check(structure, config.get("clash"))]
    residue_map = canonical_residue_map(structure, altloc=results[0].configuration["altloc"])
    # Validate before allocating output. Unknown upstream provenance is explicit.
    run_dir = create_run_directory(output_root, run_id)
    try:
        output_paths = [str(run_dir / name) for name in ("checks.json", "residue_map.csv", "manifest.json")]
        manifest = make_manifest(run_dir, config, [input_path], project_root=project_root,
                                 seed=config.get("seed"), supplied_models=config.get("supplied_models"),
                                 output_paths=output_paths,
                                 warnings=[f"{r.check}: {r.status}" for r in results if r.status != "pass"])
        if manifest["input_files"][0]["sha256"] != structure.source_hash:
            raise ValueError("Input changed between parsing and manifest creation")
        write_json_new(run_dir / "checks.json", {"category": "format/geometric plausibility only",
                                                "checks": [r.to_dict() for r in results]})
        with (run_dir / "residue_map.csv").open("x", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(residue_map[0]))
            writer.writeheader()
            for row in residue_map:
                writer.writerow({k: json.dumps(v) if isinstance(v, list) else v for k, v in row.items()})
        if hash_file(input_path) != structure.source_hash:
            raise ValueError("Input changed while report was written")
        write_manifest(run_dir / "manifest.json", manifest)
    except Exception as exc:
        # Leave a visible failure record; no partial output is presented as completed.
        write_json_new(run_dir / "failure.json", {"status": "failed", "error": str(exc)})
        raise
    return run_dir


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Audit a supplied structure offline; no model execution")
    parser.add_argument("input")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    print(audit_supplied_structure(args.input, args.output_root, read_json(args.config),
                                   project_root=args.project_root, run_id=args.run_id))
