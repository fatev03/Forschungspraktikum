"""Opt-in, single-real-run golden skeleton. No generated inputs or baselines.

Set AF3_RED_GOLDEN_CASE to a manually reviewed case JSON described in
docs/AF3_RED_GOLDEN_VALIDATION.md. Unset -> SKIP, not validated. Set but invalid
-> FAIL. This test never downloads, infers, repairs, copies or writes artifacts.
"""
import hashlib
import json
import os
from pathlib import Path
import unittest

from structure_audit.af3_native_bridge import read_af3_native_cif
from structure_audit.af3_red_adapter import (
    discover_red_runs, discover_structure_files, build_red_manifest,
)


def _sha(path):
    with path.open("rb") as handle:
        digest = hashlib.sha256()
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value):
    if not isinstance(value, str) or not value:
        raise ValueError("Explicit canonical absolute path required")
    path = Path(value)
    if not path.is_absolute() or str(path.resolve()) != value:
        raise ValueError("Canonical absolute path required; no aliases")
    return path


def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate case JSON key: " + key)
        obj[key] = value
    return obj


class AF3ReDRealGoldenTest(unittest.TestCase):
    def test_one_reviewed_real_run(self):
        case_path = os.environ.get("AF3_RED_GOLDEN_CASE")
        if case_path is None:
            self.skipTest("Real AF3-ReD output/baseline not supplied; set AF3_RED_GOLDEN_CASE")
        case_file = _canonical(case_path)
        case = json.loads(case_file.read_text(), object_pairs_hook=_unique)
        json.dumps(case, allow_nan=False)
        self.assertEqual(set(case), {
            "run_directory", "source", "real_output_record", "review_note",
            "expected_input_sha256", "expected_sidecar_sha256", "sample_relative_path",
            "binding", "expected_artifacts", "expected_read_provenance",
            "expected_hetatm_rows", "expected_root_copy",
        })
        self.assertEqual(case["source"], "AF3-ReD")
        self.assertIsInstance(case["review_note"], str)
        self.assertTrue(case["review_note"].strip(), "Reviewed real-run provenance required")
        # Hash the operator-selected actual run record; its authenticity is not inferred.
        source_record = case["real_output_record"]
        self.assertEqual(set(source_record), {"path", "sha256"})
        evidence_path = _canonical(source_record["path"])
        self.assertEqual(_sha(evidence_path), source_record["sha256"])
        root = _canonical(case["run_directory"])
        runs = discover_red_runs(root)
        self.assertEqual(len(runs), 1, "Exactly one real run required")
        run = runs[0]
        self.assertEqual(run.directory, str(root), "Select the run itself, not its parent")
        self.assertEqual(run.input_sha256, case["expected_input_sha256"])
        sidecar = root / "af3red_adapter_metadata.json"
        self.assertEqual(_sha(sidecar) if sidecar.exists() else None, case["expected_sidecar_sha256"])
        artifacts = discover_structure_files(run)
        by_path = {str(Path(a.path).relative_to(root)): a for a in artifacts}
        self.assertIn(case["sample_relative_path"], by_path)
        sample = by_path[case["sample_relative_path"]]
        self.assertEqual(sample.role, "native_sample", "Golden selection must be a sample, not a root copy")
        binding = case["binding"]
        self.assertEqual(set(binding), {"artifact_sha256", "target_id", "model_id", "auth_asym_id", "label_asym_id"})
        self.assertEqual(binding["artifact_sha256"], sample.sha256)
        watched = {case_file, evidence_path, *(Path(a.path) for a in artifacts),
                   *(Path(p["path"]) for p in run.provenance)}
        before = {str(p): (_sha(p), p.stat().st_mtime_ns) for p in watched}
        # Assert unchanged bytes/mtime even if baseline comparison fails later.
        self.addCleanup(lambda: self.assertEqual(
            before, {str(p): (_sha(p), p.stat().st_mtime_ns) for p in watched}))
        manifest = build_red_manifest(root, profile="af3_native_v1",
                                      bindings={sample.artifact_id: binding})
        self.assertEqual(manifest["reader_profile"], "af3_native_v1")
        inventory = {str(Path(a["path"]).relative_to(root)):
                     {k: a[k] for k in ("sha256", "role", "status", "reasons")}
                     for a in manifest["artifacts"]}
        selected = next(a for a in manifest["artifacts"] if a["artifact_id"] == sample.artifact_id)
        provenance = dict(selected["read_provenance"])
        if "source_path" in provenance:
            self.assertEqual(provenance["source_path"], sample.path)
            provenance["source_path"] = case["sample_relative_path"]  # Portable golden comparison only.
        hetatm_rows = None
        if provenance["read_completed"]:
            native = read_af3_native_cif(sample.path, model_id=binding["model_id"])
            self.assertEqual(native.source_sha256, sample.sha256)
            hetatm_rows = sum(r.fields["_atom_site.group_pdb"] == "HETATM" for r in native.rows)
        copies = [a for a in artifacts if a.role == "upstream_selected_copy"]
        self.assertLessEqual(len(copies), 1)
        root_copy = None if not copies else {
            "relative_path": str(Path(copies[0].path).relative_to(root)),
            "sha256": copies[0].sha256,
            "byte_equal_to_selected_sample": copies[0].sha256 == sample.sha256,
        }
        observation = {
            "reader_profile": manifest["reader_profile"], "artifacts": inventory,
            "selected_read_provenance": provenance, "selected_hetatm_rows": hetatm_rows,
            "root_copy": root_copy, "real_output_record": source_record,
            "source_authenticity": "operator-reviewed declaration; not independently verified",
        }
        print("AF3-ReD real golden observation:\n" + json.dumps(observation, indent=2, ensure_ascii=False))
        # No auto-accept/update mode: expected values must be independently reviewed.
        self.assertEqual(inventory, case["expected_artifacts"])
        self.assertEqual(provenance, case["expected_read_provenance"])
        self.assertEqual(hetatm_rows, case["expected_hetatm_rows"])
        self.assertEqual(root_copy, case["expected_root_copy"])


if __name__ == "__main__":
    unittest.main()
