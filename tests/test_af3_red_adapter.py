"""Synthetic inventories only; never AF3-ReD inference or biological fixtures."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from structure_audit.af3_red_adapter import (
    build_red_manifest, discover_red_runs, discover_structure_files,
    validate_basic_mapping_readiness,
)
from structure_audit.structures import read_structure

FIXTURES = Path(__file__).parent / "fixtures"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RedAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.run_dir = self.root / "toy_20260924_120000"
        self.run_dir.mkdir()
        self.data = self.run_dir / "toy_data.json"
        self.input = {"name": "Toy", "dialect": "alphafold3", "version": 3,
                      "modelSeeds": [7], "sequences": [
                          {"protein": {"id": ["A", "B"], "sequence": "G"}},
                          {"ligand": {"id": "L", "ccdCodes": ["ATP"]}}]}
        self.data.write_text(json.dumps(self.input))
        sample = self.run_dir / "seed-7_sample-0"
        sample.mkdir()
        self.cif = sample / "toy_seed-7_sample-0_model.cif"
        self.cif.write_bytes((FIXTURES / "minimal.cif").read_bytes())

    def declaration(self):
        side = self.run_dir / "af3red_adapter_metadata.json"
        side.write_text(json.dumps({"schema_version": "0.1", "producer": "AF3-ReD",
            "declared_run_id": "synthetic-test-only", "input_sha256": digest(self.data),
            "bias_sigma": 2.0, "bias_weight": 90.0, "source_revision": None,
            "evidence_note": "Synthetic declaration; not an executed run"}))
        return side

    def records(self):
        run, = discover_red_runs(self.root)
        artifact, = discover_structure_files(run)
        return run, artifact

    def binding(self, artifact):
        return {"artifact_sha256": artifact.sha256, "target_id": "synthetic-target",
                "model_id": "1", "auth_chain_id": "AA", "segment": 0}

    def check(self, run, artifact, binding=None):
        return validate_basic_mapping_readiness(artifact, run,
            binding=self.binding(artifact) if binding is None else binding, reader=read_structure)

    def test_no_outputs_does_not_invent_runs(self):
        empty = self.root / "source_checkout"
        empty.mkdir()
        (empty / "template.cif").write_bytes(self.cif.read_bytes())
        manifest = build_red_manifest(empty)
        self.assertEqual(manifest["runs"], [])
        self.assertIn("no_recognized_runs", manifest["diagnostics"])

    def test_discovery_metadata_and_unknown_bias(self):
        run, artifact = self.records()
        self.assertEqual(run.job_name, "toy")
        self.assertIsNone(run.bias_sigma)
        self.assertIsNone(run.bias_weight)
        self.assertEqual(run.declared_ligands[0]["ccdCodes"], ["ATP"])
        self.assertEqual((artifact.seed, artifact.sample), (7, 0))
        self.assertEqual(self.check(run, artifact).status, "candidate")

    def test_admitted_is_explicit_preparation_only_and_reader_only(self):
        self.declaration()
        before = {str(p): (digest(p), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        run, artifact = self.records()
        manifest = build_red_manifest(self.root,
            bindings={artifact.artifact_id: self.binding(artifact)}, reader=read_structure)
        row, = manifest["artifacts"]
        self.assertEqual(row["status"], "admitted")
        self.assertEqual(row["reasons"], ["external_mapping_preparation_only"])
        self.assertEqual(manifest, build_red_manifest(self.root,
            bindings={artifact.artifact_id: self.binding(artifact)}, reader=read_structure))
        body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        self.assertEqual(manifest["manifest_sha256"], hashlib.sha256(encoded).hexdigest())
        self.assertEqual(before, {str(p): (digest(p), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()})
        self.assertEqual(artifact.status, "candidate")  # Never mutate supplied records.
        self.assertEqual(set(row), {"artifact_id", "run_id", "path", "sha256", "format",
                                  "role", "seed", "sample", "status", "reasons", "binding", "read_provenance"})
        self.assertEqual(manifest["reader_profile"], "strict")
        self.assertEqual(row["read_provenance"]["profile"], "strict")

    def test_no_binding_or_reader_never_admits(self):
        self.declaration()
        run, artifact = self.records()
        self.assertEqual(validate_basic_mapping_readiness(artifact, run).status, "candidate")
        self.assertEqual(validate_basic_mapping_readiness(artifact, run,
                         binding=self.binding(artifact)).status, "candidate")

    def test_bad_hash_chain_and_model_rejected(self):
        self.declaration()
        run, artifact = self.records()
        for key, value in (("artifact_sha256", "0" * 64), ("auth_chain_id", "X"), ("model_id", "99"), ("segment", True)):
            with self.subTest(key=key):
                self.assertEqual(self.check(run, artifact, {**self.binding(artifact), key: value}).status, "rejected")

    def test_changed_artifact_and_stale_binding_fail_closed(self):
        self.declaration()
        run, artifact = self.records()
        self.cif.write_text(self.cif.read_text() + "\n# changed\n")
        self.assertEqual(self.check(run, artifact).status, "rejected")
        with self.assertRaisesRegex(ValueError, "stale artifact"):
            build_red_manifest(self.root, bindings={artifact.artifact_id: self.binding(artifact)})

    def test_changed_metadata_fails_closed(self):
        side = self.declaration()
        run, artifact = self.records()
        side.write_text(side.read_text() + "\n")
        self.assertEqual(self.check(run, artifact).status, "rejected")
        with self.assertRaisesRegex(ValueError, "changed"):
            discover_structure_files(run)

    def test_native_writer_missing_auth_fields_rejected_without_repair(self):
        # Mimics upstream writer's field omission, not an actual AF3 output.
        lines = self.cif.read_text().splitlines()
        lines = [x for x in lines if x not in ("_atom_site.auth_atom_id", "_atom_site.auth_comp_id")]
        lines = [" ".join(x.split()[:9] + x.split()[11:]) if x.startswith("ATOM ") else x for x in lines]
        self.cif.write_text("\n".join(lines) + "\n")
        self.declaration()
        run, artifact = self.records()
        checked = self.check(run, artifact)
        self.assertEqual(checked.status, "rejected")
        self.assertIn("missing explicit atom_site fields", checked.reasons[0])
        self.assertEqual(artifact.status, "candidate")

    def test_root_copy_not_independent_even_if_bytes_differ(self):
        self.declaration()
        copy = self.run_dir / "toy_model.cif"
        copy.write_text(self.cif.read_text() + "\n# upstream metadata timestamp\n")
        run, = discover_red_runs(self.root)
        artifacts = discover_structure_files(run)
        root_copy, = [a for a in artifacts if a.role == "upstream_selected_copy"]
        self.assertIsNone(root_copy.seed)
        self.assertEqual(self.check(run, root_copy).status, "candidate")

    def test_wrong_seed_empty_compressed_and_converted(self):
        wrong = self.run_dir / "seed-8_sample-0"
        wrong.mkdir()
        (wrong / "toy_seed-8_sample-0_model.cif").write_bytes(self.cif.read_bytes())
        (self.run_dir / "empty.pdb").touch()
        (self.run_dir / "model.cif.gz").write_bytes(b"compressed-not-parsed")
        (self.run_dir / "converted.pdb").write_bytes((FIXTURES / "minimal.pdb").read_bytes())
        run, = discover_red_runs(self.root)
        artifacts = {Path(a.path).name: a for a in discover_structure_files(run)}
        for name in ("toy_seed-8_sample-0_model.cif", "empty.pdb", "model.cif.gz"):
            self.assertEqual(artifacts[name].status, "rejected")
        self.assertEqual(artifacts["converted.pdb"].status, "candidate")

    def test_duplicate_atom_and_nonfinite_coordinates_rejected(self):
        original = self.cif.read_text()
        for text in (original + next(x for x in original.splitlines() if x.startswith("ATOM ")) + "\n",
                     original.replace("1.4 0 0", "nan 0 0")):
            self.cif.write_text(text)
            self.declaration()
            run, artifact = self.records()
            self.assertEqual(self.check(run, artifact).status, "rejected")

    def test_ambiguous_input_invalid_metadata_and_wrong_sidecar_hash(self):
        side = self.declaration()
        obj = json.loads(side.read_text())
        for key, value in (("input_sha256", "0" * 64), ("bias_sigma", True), ("bias_weight", float("nan"))):
            side.write_text(json.dumps({**obj, key: value}))
            with self.assertRaises(ValueError):
                discover_red_runs(self.root)
        side.unlink()
        (self.run_dir / "other_data.json").write_bytes(self.data.read_bytes())
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            discover_red_runs(self.root)

    def test_duplicate_json_key_and_unknown_dialect_rejected(self):
        self.data.write_text('{"name":"Toy", "name":"Other"}')
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            discover_red_runs(self.root)
        self.data.write_text(json.dumps({**self.input, "dialect": "alphafoldserver"}))
        with self.assertRaisesRegex(ValueError, "versions"):
            discover_red_runs(self.root)

    def test_symlink_escape_rejected(self):
        (self.run_dir / "alias.cif").symlink_to(self.cif)
        with self.assertRaisesRegex(ValueError, "Symlink"):
            build_red_manifest(self.root)

    def test_duplicate_target_sequences_do_not_merge_runs(self):
        other = self.root / "another_run"
        other.mkdir()
        (other / "toy_data.json").write_bytes(self.data.read_bytes())
        runs = discover_red_runs(self.root)
        self.assertEqual(len(runs), 2)
        self.assertNotEqual(runs[0].run_id, runs[1].run_id)
        self.assertEqual(runs[0].input_sha256, runs[1].input_sha256)

    def test_forged_sample_identity_rejected(self):
        run, artifact = self.records()
        self.assertEqual(self.check(run, replace(artifact, seed=999)).status, "rejected")

    def test_no_structures_is_explicit(self):
        self.cif.unlink()
        manifest = build_red_manifest(self.root)
        self.assertEqual(len(manifest["runs"]), 1)
        self.assertIn("no_structure_artifacts", manifest["diagnostics"])

    def test_notebook_has_identical_adapter_and_compiles(self):
        project = Path(__file__).resolve().parents[1]
        notebook = json.loads((project / "examples/af3_red_colab.ipynb").read_text())
        cells = ["".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code"]
        adapter = (project / "src/structure_audit/af3_red_adapter.py").read_text()
        self.assertEqual("".join(cells[:5]), adapter)
        for code in cells:
            compile(code, "<notebook-cell>", "exec")
        namespace = {"__name__": "__main__"}
        for code in cells[:5]:
            exec(code, namespace)
        self.assertEqual(namespace["build_red_manifest"](self.root), build_red_manifest(self.root))


if __name__ == "__main__":
    unittest.main()
