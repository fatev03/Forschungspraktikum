"""Standalone Colab UI smoke-check; temporary synthetic inputs, no inference."""
import builtins
from contextlib import contextmanager, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
NOTEBOOK = PROJECT / "examples/af3_red_colab.ipynb"


def snapshot(root):
    return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(),
                                     p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


@contextmanager
def readonly_standalone():
    original_import = builtins.__import__
    builtin_open, io_open = builtins.open, io.open

    def no_local_src(name, *args, **kwargs):
        if name == "structure_audit" or name.startswith("structure_audit."):
            raise AssertionError("Notebook must run without local src imports")
        return original_import(name, *args, **kwargs)

    def guard(opener):
        def read_only(file, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+"):
                raise AssertionError("Notebook attempted a file write")
            return opener(file, mode, *args, **kwargs)
        return read_only

    with patch("builtins.__import__", no_local_src), \
         patch("builtins.open", guard(builtin_open)), \
         patch("io.open", guard(io_open)), redirect_stdout(io.StringIO()):
        yield


class ColabAuditSmoke(unittest.TestCase):
    def setUp(self):
        self.notebook = json.loads(NOTEBOOK.read_text())
        self.cells = [c for c in self.notebook["cells"] if c["cell_type"] == "code"]
        self.steps = {c["metadata"]["audit_step"]: "".join(c["source"])
                      for c in self.cells if "audit_step" in c["metadata"]}
        self.ns = {"__name__": "__main__"}
        with readonly_standalone():
            for i, cell in enumerate(self.cells):
                exec(compile("".join(cell["source"]), f"notebook-cell-{i}", "exec"), self.ns)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def step(self, name):
        with readonly_standalone():
            exec(compile(self.steps[name], f"notebook-{name}", "exec"), self.ns)

    def fixture(self, sidecar=False):
        # Harness-only setup. The notebook never creates these files.
        input_path = self.root / "toy_data.json"
        input_path.write_text(json.dumps({"name": "toy", "dialect": "alphafold3",
                                         "version": 1, "modelSeeds": [1],
                                         "sequences": [{"protein": {"id": "A", "sequence": "G"}}]}))
        sample = self.root / "seed-1_sample-0" / "toy_seed-1_sample-0_model.cif"
        sample.parent.mkdir()
        data = (PROJECT / "tests/fixtures/af3_native/minimal.cif").read_bytes()
        sample.write_bytes(data)
        (self.root / "toy_model.cif").write_bytes(data)
        if sidecar:
            (self.root / "af3red_adapter_metadata.json").write_text(json.dumps({
                "schema_version": "0.1", "producer": "AF3-ReD", "declared_run_id": "synthetic",
                "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
                "bias_sigma": 1.0, "bias_weight": 0.0, "source_revision": None,
                "evidence_note": "Synthetic UI smoke fixture, not an inference result."}))
        self.before = snapshot(self.root)
        self.ns.update(OUTPUT_ROOT=str(self.root), READER_PROFILE="af3_native_v1")
        self.step("inventory")
        sample_row = next(a for a in self.ns["inventory"]["artifacts"] if a["role"] == "native_sample")
        self.ns.update(SELECTED_ARTIFACT_ID=sample_row["artifact_id"], ARTIFACT_SHA256=sample_row["sha256"],
                       TARGET_ID="demo_target", MODEL_ID="1", AUTH_ASYM_ID="AA", LABEL_ASYM_ID="A")

    def test_empty_defaults_and_embedded_source_parity(self):
        self.assertIsNone(self.ns["inventory"])
        self.assertIsNone(self.ns["selection_result"])
        for field in ("OUTPUT_ROOT", "SELECTED_ARTIFACT_ID", "ARTIFACT_SHA256", "TARGET_ID",
                      "MODEL_ID", "AUTH_ASYM_ID", "LABEL_ASYM_ID", "STRICT_AUTH_CHAIN_ID", "STRICT_SEGMENT"):
            self.assertEqual(self.ns[field], "")
        self.assertEqual(self.ns["READER_PROFILE"], "strict")
        self.assertEqual("".join("".join(c["source"]) for c in self.cells[:5]),
                         (PROJECT / "src/structure_audit/af3_red_adapter.py").read_text())
        bridge = [c for c in self.cells if c["metadata"].get("af3_component") == "native_bridge"]
        self.assertEqual(len(bridge), 1)
        self.assertEqual("".join(bridge[0]["source"]),
                         (PROJECT / "src/structure_audit/af3_native_bridge.py").read_text())
        for c in self.cells:
            self.assertIsNone(c["execution_count"])
            self.assertEqual(c["outputs"], [])
        self.assertNotIn("/Users/", NOTEBOOK.read_text())
        self.assertNotIn("CRBN-DDB1", NOTEBOOK.read_text())

    def test_native_candidate_and_root_copy_remain_readonly(self):
        self.fixture()
        self.assertEqual(len(self.ns["inventory"]["artifacts"]), 2)
        self.assertTrue(all(a["status"] == "candidate" for a in self.ns["inventory"]["artifacts"]))
        self.step("readiness")
        result = self.ns["selection_result"]
        self.assertEqual(result["status"], "candidate")
        self.assertTrue(result["read_provenance"]["read_completed"])
        self.assertIn("af3red_execution_declaration_missing", result["reasons"])
        self.assertEqual(result["binding"]["auth_asym_id"], "AA")
        self.assertEqual(result["binding"]["label_asym_id"], "A")
        self.step("checks")
        self.ns["TARGET_ID"] = "changed_target"
        with self.assertRaisesRegex(AssertionError, "Binding/reader"):
            self.step("checks")
        self.ns["TARGET_ID"] = "demo_target"
        root_copy = next(a for a in self.ns["inventory"]["artifacts"] if a["role"] == "upstream_selected_copy")
        self.ns["SELECTED_ARTIFACT_ID"] = root_copy["artifact_id"]
        self.step("readiness")
        self.assertEqual(self.ns["selection_result"]["status"], "candidate")
        self.assertIn("root_copy_not_an_independent_sample", self.ns["selection_result"]["reasons"])
        self.assertEqual(snapshot(self.root), self.before)

    def test_explicit_native_admitted_scope_and_rejected_chain(self):
        self.fixture(sidecar=True)
        self.step("readiness")
        self.assertEqual(self.ns["selection_result"]["status"], "admitted")
        self.assertEqual(self.ns["selection_result"]["reasons"], ("external_mapping_preparation_only",))
        self.step("checks")
        self.ns["LABEL_ASYM_ID"] = "absent"
        self.step("readiness")
        self.assertEqual(self.ns["selection_result"]["status"], "rejected")
        self.assertIn("Selected ATOM author/label chain pair absent", self.ns["selection_result"]["reasons"][0])
        self.assertEqual(snapshot(self.root), self.before)

    def test_invalid_and_stale_selection_fail_closed(self):
        self.fixture()
        valid = dict(self.ns)
        cases = [({"SELECTED_ARTIFACT_ID": "unknown"}, "Artifact ID"),
                 ({"ARTIFACT_SHA256": "0" * 64}, "SHA-256"),
                 ({"TARGET_ID": ""}, "TARGET_ID"),
                 ({"AUTH_ASYM_ID": ""}, "namespace"),
                 ({"STRICT_SEGMENT": "0"}, "strict binding"),
                 ({"READER_PROFILE": "strict"}, "envanter"),
                 ({"OUTPUT_ROOT": str(self.root.parent)}, "envanter")]
        for change, message in cases:
            with self.subTest(change=change):
                self.ns.update(valid)
                self.step("readiness")
                self.assertIsNotNone(self.ns["selection_result"])
                self.ns.update(change)
                with self.assertRaisesRegex(ValueError, message):
                    self.step("readiness")
                self.assertIsNone(self.ns["selection_result"])
        self.assertEqual(snapshot(self.root), self.before)

    def test_strict_no_reader_and_inventory_errors(self):
        self.fixture()
        self.ns.update(READER_PROFILE="strict", AUTH_ASYM_ID="", LABEL_ASYM_ID="",
                       STRICT_AUTH_CHAIN_ID="AA", STRICT_SEGMENT="0")
        self.step("inventory")
        self.step("readiness")
        result = self.ns["selection_result"]
        self.assertEqual(result["status"], "candidate")
        self.assertIn("structure_reader_required", result["reasons"])
        self.assertFalse(result["read_provenance"]["read_completed"])
        self.step("checks")
        self.ns["STRICT_SEGMENT"] = ""
        with self.assertRaisesRegex(ValueError, "segment"):
            self.step("readiness")
        self.ns["READER_PROFILE"] = "auto"
        with self.assertRaisesRegex(ValueError, "READER_PROFILE"):
            self.step("inventory")
        self.assertIsNone(self.ns["inventory"])
        self.assertIsNone(self.ns["selection_result"])
        self.ns.update(READER_PROFILE="strict", OUTPUT_ROOT="relative/path")
        with self.assertRaisesRegex(ValueError, "mutlak"):
            self.step("inventory")
        self.assertEqual(snapshot(self.root), self.before)

    def test_no_run_anchor_is_a_diagnostic(self):
        self.ns.update(OUTPUT_ROOT=str(self.root), READER_PROFILE="af3_native_v1")
        self.step("inventory")
        self.assertEqual(self.ns["inventory"]["runs"], [])
        self.assertIn("no_recognized_runs", self.ns["inventory"]["diagnostics"])
        self.assertIsNone(self.ns["selection_result"])
        self.assertEqual(snapshot(self.root), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
