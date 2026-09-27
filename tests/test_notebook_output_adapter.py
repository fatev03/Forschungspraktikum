from copy import deepcopy
import builtins
import csv
import glob
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from structure_audit import (import_notebook_outputs, NotebookImportError, NotebookImportResult,
                             canonical_residue_map, read_structure, filter_candidates,
                             structure_integrity_check, coarse_steric_clash_check)
from structure_audit.evidence import CandidateEvidence, sequence_hash
from structure_audit.provenance import (hash_config, hash_file, make_manifest, create_run_directory,
                                        write_manifest, write_json_new)
from structure_audit.validation import read_json
from helpers import FIXTURES

FILES = ("mpnn.csv", "boltz0.json", "boltz1.json", "toy.pdb", "notebook.ipynb", "config.json")
NULL_PROV = {"model_id": None, "checkpoint_id": None, "seed": None}


def synthetic_contract(root):
    """Explicit, synthetic file list; shared by tests and the documented offline example."""
    root = Path(root).resolve()
    nb = read_json(root / "notebook.ipynb")
    def ref(index, role):
        source = "".join(nb["cells"][index]["source"])
        return {"artifact_id": "notebook", "cell_index": index,
                "cell_source_sha256": hashlib.sha256(source.encode()).hexdigest(), "role": role}
    def art(kind, filename, run, sample=None):
        producer = "synthetic-csv" if kind == "mpnn_csv" else "synthetic-boltz"
        a = {"kind": kind, "path": str(root / filename), "sha256": hash_file(root / filename),
             "source_run_id": run, "origin": "design", "fallback_used": False,
             "producer": {"name": producer, "version": "fixture-v1", **NULL_PROV, "status": "caller_supplied"},
             "notebook_ref": ref(0, "producer") if kind == "mpnn_csv" else ref(1, "consumer")}
        if sample is not None:
            a["sample_id"] = sample
        return a
    artifacts = {"notebook": {"kind": "notebook", "path": str(root / "notebook.ipynb"), "sha256": hash_file(root / "notebook.ipynb")},
                 "csv": art("mpnn_csv", "mpnn.csv", "csv-run"),
                 "pdb0": art("pdb", "toy.pdb", "csv-run", "0"),
                 "pdb1": art("pdb", "toy.pdb", "csv-run", "1"),
                 "boltz0": art("boltz_json", "boltz0.json", "boltz-run", "sample-zero"),
                 "boltz1": art("boltz_json", "boltz1.json", "boltz-run", "sample-one"),
                 "bpdb0": art("pdb", "toy.pdb", "boltz-run", "sample-zero"),
                 "bpdb1": art("pdb", "toy.pdb", "boltz-run", "sample-one")}
    rows = canonical_residue_map(read_structure(root / "toy.pdb", model_id="1"))
    def pdb(aid):
        return {"artifact_id": aid, "model_id": "1", "residue_map": deepcopy(rows),
                "chains": [{"sequence_index": i, "chain_id": cid, "segment": 0, "role": role,
                            "entries": [{"sequence_position": 1, "residue_index": i, "reason": None}]}
                           for i, cid, role in ((0, "A", "target"), (1, "B", "candidate"))]}
    bindings = []
    for n in ("0", "1"):
        bindings.append({"candidate_id": f"fixture-{n}", "source_run_id": "csv-run", "csv_artifact": "csv",
                         "design": "0", "n": n, "target_id": "synthetic-target", "conformer_id": "synthetic-conformer",
                         "pdb": pdb("pdb" + n), "boltz": [], "boltz_missing_reason": "not generated for this synthetic candidate"})
    bindings[0]["boltz_missing_reason"] = None
    bindings[0]["boltz"] = [{"artifact_id": aid, "source_run_id": "boltz-run", "sample_id": sample,
                             "pdb": pdb(pid), "chain_key_map": {"0": 0, "1": 1}}
                            for aid, sample, pid in (("boltz0", "sample-zero", "bpdb0"), ("boltz1", "sample-one", "bpdb1"))]
    config = read_json(root / "config.json")
    contract = {"config": config, "artifacts_sha256": hash_config(artifacts), "bindings_sha256": hash_config(bindings)}
    paths = list(dict.fromkeys(a["path"] for a in artifacts.values()))
    manifest = make_manifest(root / "audit-run" / "v0001", {"notebook_output_adapter": contract}, paths,
                             project_root=root, warnings=["Synthetic/local fixtures; no inference or biology"])
    return {"artifacts": artifacts, "bindings": bindings, "manifest": manifest, "config": config}


class NotebookOutputAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for name in FILES:
            (self.root / name).write_bytes((FIXTURES / "notebook_outputs" / name).read_bytes())
        self.kw = synthetic_contract(self.root)

    def seal(self):
        """Explicitly re-attest caller metadata after an intentional test mutation."""
        config = self.kw["manifest"]["config"]
        config["notebook_output_adapter"] = {"config": deepcopy(self.kw["config"]),
                                             "artifacts_sha256": hash_config(self.kw["artifacts"]),
                                             "bindings_sha256": hash_config(self.kw["bindings"])}
        self.kw["manifest"]["config_hash"] = hash_config(config)

    def change_file(self, name, text):
        path = self.root / name
        path.write_text(text)
        sha = hash_file(path)
        for a in self.kw["artifacts"].values():
            if a["path"] == str(path): a["sha256"] = sha
        for ref in self.kw["manifest"]["input_files"]:
            if ref["path"] == str(path): ref["sha256"] = sha
        self.seal()

    def result(self):
        return import_notebook_outputs(**self.kw)

    def metric(self, c, name):
        return next(m for m in c.metrics if m["name"] == name)

    def meta(self, c):
        return self.metric(c, "__notebook_import__")["raw_value"]

    def error(self, code=None):
        with self.assertRaises(NotebookImportError) as caught:
            self.result()
        e = caught.exception
        if code: self.assertEqual(e.diagnostics[0]["code"], code)
        self.assertEqual(e.diagnostics[0]["severity"], "error")
        self.assertNotIn("candidates", e.__dict__)
        json.dumps(e.diagnostics, allow_nan=False)
        return e.diagnostics[0]

    def test_positive_two_candidates_multiple_boltz_samples(self):
        before = deepcopy(self.kw)
        result = self.result()
        self.assertIsInstance(result, NotebookImportResult)
        self.assertEqual([c.candidate_id for c in result.candidates], ["fixture-0", "fixture-1"])
        self.assertFalse(result.quarantined)
        c = result.candidates[0]
        self.assertEqual(c.sequence_hash, sequence_hash("A"))
        self.assertEqual(self.metric(c, "csv:/plddt")["raw_value"], "0.913")
        self.assertAlmostEqual(self.metric(c, "csv:/plddt")["value"], 91.3)
        self.assertEqual(self.metric(c, "boltz0:/complex_plddt")["value"], 90)
        self.assertEqual(self.metric(c, "boltz1:/complex_plddt")["value"], 80)
        self.assertEqual(self.kw, before)
        self.assertEqual(self.meta(result.candidates[1])["boltz_missing_reason"], "not generated for this synthetic candidate")
        self.assertIsNone(self.metric(c, "csv:/rmsd")["value"])

    def test_raw_columns_headers_and_exact_multiline_csv_locator(self):
        self.change_file("mpnn.csv", (self.root / "mpnn.csv").read_text().replace("synthetic, not biological", "first\nsecond"))
        c = self.result().candidates[0]
        meta = self.meta(c)
        self.assertEqual(meta["csv_record"]["row"], 2)
        self.assertEqual(meta["csv_record"]["row_end"], 3)
        self.assertEqual(meta["csv_record"]["raw"]["note"], "first\nsecond")
        self.assertEqual(self.metric(c, "csv:/design")["raw_value"], "0")
        self.assertEqual(meta["field_provenance"]["csv:/note"]["locator"]["row_end"], 3)

    def test_reordered_csv_columns(self):
        rows = list(csv.reader(io.StringIO((self.root / "mpnn.csv").read_text())))
        out = io.StringIO(); writer = csv.writer(out)
        for row in rows: writer.writerow(list(reversed(row)))
        self.change_file("mpnn.csv", out.getvalue())
        c = self.result().candidates[0]
        self.assertAlmostEqual(self.metric(c, "csv:/plddt")["value"], 91.3)
        self.assertEqual(self.meta(c)["csv_record"]["header"][0], "note")

    def test_crlf_inside_csv_field_is_preserved(self):
        text = (self.root / "mpnn.csv").read_text().replace("synthetic, not biological", "first\r\nsecond")
        self.change_file("mpnn.csv", text)
        c = self.result().candidates[0]
        self.assertEqual(self.metric(c, "csv:/note")["raw_value"], "first\r\nsecond")
        self.assertIn("first\r\nsecond", self.meta(c)["csv_record"]["raw_record"])

    def test_directional_nested_and_escaped_json_pointers_preserved(self):
        c = self.result().candidates[0]
        self.assertEqual(self.metric(c, "boltz0:/pair_chains_iptm/0/1")["value"], 0.4)
        self.assertEqual(self.metric(c, "boltz0:/pair_chains_iptm/1/0")["value"], 0.6)
        self.assertEqual(self.metric(c, "boltz0:/pair_chains_iptm")["raw_value"], {"0": {"1": 0.4}, "1": {"0": 0.6}})
        self.assertIsNone(self.metric(c, "boltz0:/pair_chains_iptm")["value"])
        nested = self.metric(c, "boltz0:/nested_confidence/a~1b/x~0y")
        self.assertIs(nested["raw_value"], True)
        self.assertIsNone(nested["value"])
        self.assertEqual(self.meta(c)["field_provenance"][nested["name"]]["locator"], {"json_pointer": "/nested_confidence/a~1b/x~0y"})
        self.assertIsNone(self.metric(c, "boltz0:/nested_confidence/scores/1")["raw_value"])
        self.assertNotIn("final_score", c.to_dict())

    def test_per_field_provenance_and_cell_role(self):
        c = self.result().candidates[0]
        fields = self.meta(c)["field_provenance"]
        for name, fm in fields.items():
            self.assertEqual(fm["hash_status"], "verified_local")
            self.assertEqual(fm["producer"]["status"], "caller_supplied")
            self.assertEqual(fm["notebook"]["execution_status"], "not_verified")
            self.assertEqual(fm["source"]["sha256"], self.kw["artifacts"][fm["artifact_id"]]["sha256"])
        self.assertEqual(fields["csv:/plddt"]["notebook"]["role"], "producer")
        self.assertEqual(fields["boltz0:/iptm"]["notebook"]["role"], "consumer")
        self.assertIsNone(fields["boltz0:/iptm"]["notebook"]["cell_id"])
        self.assertEqual(c.provenance, NULL_PROV)
        self.assertEqual(self.meta(c)["manifest"]["sha256"], hash_config(self.kw["manifest"]))

    def test_no_profile_raw_only_no_normalization(self):
        self.kw["config"]["plddt_profiles"] = {}; self.seal()
        c = self.result().candidates[0]
        for name in ("csv:/plddt", "boltz0:/complex_plddt", "boltz1:/complex_plddt"):
            m = self.metric(c, name)
            self.assertIsNone(m["value"]); self.assertIsNone(m["scale"])
            self.assertEqual(m["missing_reason"], "plddt_profile_not_supplied")
        self.assertEqual(self.metric(c, "csv:/plddt")["raw_value"], "0.913")

    def test_percent_identity_profile_and_out_of_range(self):
        self.change_file("mpnn.csv", (self.root / "mpnn.csv").read_text().replace("0.913", "91.300"))
        self.kw["config"]["plddt_profiles"]["csv"]["profile"] = "plddt_0_100_v1"; self.seal()
        c = self.result().candidates[0]
        self.assertAlmostEqual(self.metric(c, "csv:/plddt")["value"], 91.3)
        self.kw["config"]["plddt_profiles"]["csv"]["profile"] = "plddt_0_1_to_0_100_v1"; self.seal()
        c = self.result().candidates[0]
        self.assertIsNone(self.metric(c, "csv:/plddt")["value"])
        self.assertEqual(self.metric(c, "csv:/plddt")["raw_value"], "91.300")

    def test_profile_producer_mismatch(self):
        self.kw["config"]["plddt_profiles"]["csv"]["producer_version"] = "different"; self.seal()
        self.error("profile_producer_mismatch")

    def test_all_origins_separated_from_default_filter_input(self):
        original = deepcopy(self.kw)
        for origin in ("design", "demo", "unknown", "origin_conflict"):
            with self.subTest(origin=origin):
                self.kw = deepcopy(original)
                for a in self.kw["artifacts"].values():
                    if a["kind"] != "notebook": a["origin"] = origin
                self.seal(); result = self.result()
                if origin == "design": self.assertEqual(len(result.candidates), 2)
                else:
                    self.assertEqual(result.candidates, [])
                    self.assertEqual(filter_candidates(result.candidates, []), [])
                    self.assertEqual(len(result.quarantined), 2)
                    for c in result.quarantined:
                        self.assertEqual(self.meta(c)["origin"], origin)
                        self.assertTrue(all(m["value"] is None for m in c.metrics))

    def test_fallback_evidence_conflicts_with_design(self):
        a = self.kw["artifacts"]["bpdb0"]
        a["fallback_used"] = True
        nb = read_json(self.root / "notebook.ipynb")
        a["notebook_ref"] = {"artifact_id": "notebook", "cell_index": 2, "role": "consumer",
                             "cell_source_sha256": hashlib.sha256("".join(nb["cells"][2]["source"]).encode()).hexdigest()}
        self.seal(); result = self.result()
        self.assertEqual([c.candidate_id for c in result.candidates], ["fixture-1"])
        c = result.quarantined[0]
        self.assertEqual(self.meta(c)["origin"], "origin_conflict")
        self.assertEqual(self.metric(c, "csv:/plddt")["raw_value"], "0.913")

    def test_mixed_demo_and_design_is_conflict(self):
        self.kw["artifacts"]["boltz0"]["origin"] = "demo"; self.seal()
        self.assertEqual(self.meta(self.result().quarantined[0])["origin"], "origin_conflict")

    def test_quarantine_preserves_previous_missing_reason(self):
        self.change_file("mpnn.csv", (self.root / "mpnn.csv").read_text().replace("0.913", "nan"))
        self.kw["artifacts"]["boltz0"]["origin"] = "demo"; self.seal()
        c = self.result().quarantined[0]
        f = self.meta(c)["field_provenance"]["csv:/plddt"]
        self.assertEqual(f["status"], "quarantined")
        self.assertEqual(f["raw_status"], "non_finite")
        self.assertEqual(f["raw_reason"], "non_finite_token")
        self.assertEqual(self.metric(c, "csv:/plddt")["raw_value"], "nan")

    def test_non_json_cyclic_contract_has_explicit_diagnostic(self):
        self.kw["config"]["cycle"] = self.kw["config"]
        self.error("contract_error")

    def test_missing_json_fails_without_partial_result(self):
        (self.root / "boltz1.json").unlink()
        d = self.error("artifact_read_error")
        self.assertEqual(d["artifact_id"], "boltz1")

    def test_duplicate_json_key_and_bare_nonfinite_and_overflow(self):
        for text in ('{"iptm":0.2,"iptm":0.3}', '{"iptm":NaN}', '{"iptm":Infinity}', '{"iptm":1e999}'):
            with self.subTest(text=text):
                self.change_file("boltz0.json", text)
                self.error("json_parse_error")

    def test_null_and_string_nan_remain_distinct(self):
        self.change_file("boltz0.json", '{"iptm":null,"complex_plddt":"NaN"}')
        c = self.result().candidates[0]
        self.assertIsNone(self.metric(c, "boltz0:/iptm")["raw_value"])
        self.assertEqual(self.metric(c, "boltz0:/complex_plddt")["raw_value"], "NaN")
        self.assertEqual(self.meta(c)["field_provenance"]["boltz0:/complex_plddt"]["status"], "non_finite")

    def test_csv_nan_and_missing_column(self):
        rows = list(csv.reader(io.StringIO((self.root / "mpnn.csv").read_text())))
        index = rows[0].index("plddt"); rows[1][index] = "nan"
        index = rows[0].index("i_pae")
        out = io.StringIO(); writer = csv.writer(out)
        for row in rows: writer.writerow(row[:index] + row[index+1:])
        self.change_file("mpnn.csv", out.getvalue())
        c = self.result().candidates[0]
        self.assertEqual(self.metric(c, "csv:/plddt")["raw_value"], "nan")
        self.assertIsNone(self.metric(c, "csv:/plddt")["value"])
        self.assertEqual(self.metric(c, "csv:/i_pae")["missing_reason"], "missing_column")

    def test_duplicate_and_malformed_csv_identity(self):
        original = (self.root / "mpnn.csv").read_text()
        for text in (original + original.splitlines()[1] + "\n", original.replace("0,1,G/A", ",1,G/A"), 'design,n,seq\n0,0\n'):
            with self.subTest(text=text):
                self.change_file("mpnn.csv", text); self.error()

    def test_duplicate_candidate_binding(self):
        self.kw["bindings"][1]["candidate_id"] = "fixture-0"; self.seal()
        self.error("duplicate_candidate_binding")

    def test_duplicate_row_binding(self):
        self.kw["bindings"][1]["n"] = "0"; self.seal()
        self.error("duplicate_row_binding")

    def test_unbound_csv_row(self):
        self.kw["bindings"].pop(); self.seal()
        self.error("unbound_csv_rows")

    def test_wrong_source_run(self):
        self.kw["bindings"][0]["source_run_id"] = "another-run"; self.seal()
        self.error("source_run_mismatch")

    def test_boltz_sample_not_mpnn_n(self):
        self.kw["bindings"][0]["boltz"][0]["sample_id"] = "0"; self.seal()
        self.error("boltz_sample_mismatch")

    def test_duplicate_boltz_sample_binding(self):
        self.kw["bindings"][0]["boltz"].append(deepcopy(self.kw["bindings"][0]["boltz"][0])); self.seal()
        self.error("duplicate_sample_binding")

    def test_wrong_pdb_sample(self):
        self.kw["bindings"][0]["pdb"]["artifact_id"] = "pdb1"; self.seal()
        self.error("pdb_sample_mismatch")

    def test_wrong_chain_role(self):
        self.kw["bindings"][0]["pdb"]["chains"][0]["role"] = "candidate"; self.seal()
        self.error("wrong_chain_role")

    def test_wrong_sequence_chain_mapping(self):
        chains = self.kw["bindings"][0]["pdb"]["chains"]
        chains[0]["entries"][0]["residue_index"] = 1; self.seal()
        self.error("sequence_mapping_mismatch")

    def test_stale_map(self):
        self.kw["bindings"][0]["pdb"]["residue_map"][0]["residue_id"] = 42; self.seal()
        self.error("stale_residue_map")

    def test_unknown_directional_chain(self):
        self.change_file("boltz0.json", '{"pair_chains_iptm":{"0":{"unknown":0.5}}}')
        self.error("unknown_pair_chain")

    def test_ambiguous_filename_and_pattern_rejected(self):
        for name in ("toy.pdb", str(self.root / "*.pdb")):
            with self.subTest(name=name):
                self.kw["artifacts"]["pdb0"]["path"] = name; self.seal()
                self.error("ambiguous_filename")

    def test_same_basename_is_safe_with_explicit_paths_and_hashes(self):
        directory = self.root / "other"; directory.mkdir()
        target = directory / "toy.pdb"; target.write_bytes((self.root / "toy.pdb").read_bytes())
        self.kw["artifacts"]["pdb1"]["path"] = str(target)
        self.kw["manifest"]["input_files"].append({"path": str(target), "sha256": hash_file(target)})
        self.seal(); self.assertEqual(len(self.result().candidates), 2)

    def test_stale_artifact_hash(self):
        (self.root / "boltz0.json").write_text('{}')
        self.error("stale_artifact_hash")

    def test_stale_notebook_cell_hash(self):
        self.kw["artifacts"]["csv"]["notebook_ref"]["cell_source_sha256"] = "0" * 64; self.seal()
        self.error("stale_cell_hash")

    def test_manifest_binding_tampering(self):
        self.kw["bindings"][0]["candidate_id"] = "tampered"
        self.error("manifest_contract_mismatch")

    def test_unknown_producer_and_notebook_metadata(self):
        self.kw["config"]["plddt_profiles"] = {}
        self.kw["artifacts"]["csv"]["producer"] = {"name": None, "version": None, **NULL_PROV, "status": "unknown"}
        self.kw["artifacts"]["csv"]["notebook_ref"] = None; self.seal()
        c = self.result().candidates[0]
        f = self.meta(c)["field_provenance"]["csv:/plddt"]
        self.assertEqual(f["notebook"]["status"], "unknown")
        self.assertEqual(f["producer"]["status"], "unknown")
        self.assertIsNone(f["producer"]["seed"])

    def test_producer_cannot_claim_verified(self):
        self.kw["artifacts"]["csv"]["producer"]["status"] = "verified_local"; self.seal()
        self.error("unverified_producer")

    def test_distinct_producer_models_and_seeds_are_not_collapsed(self):
        csv_prov = {"model_id": "synthetic-af-model", "checkpoint_id": "synthetic-af-weights", "seed": 7}
        boltz_prov = {"model_id": "synthetic-boltz-model", "checkpoint_id": "synthetic-boltz-weights", "seed": 9}
        self.kw["artifacts"]["csv"]["producer"].update(csv_prov)
        self.kw["artifacts"]["boltz0"]["producer"].update(boltz_prov)
        self.kw["manifest"]["supplied_models"] = [csv_prov, boltz_prov]
        self.seal(); c = self.result().candidates[0]
        self.assertEqual(self.metric(c, "csv:/plddt")["provenance"], csv_prov)
        self.assertEqual(self.metric(c, "boltz0:/iptm")["provenance"], boltz_prov)
        self.assertEqual(c.provenance, NULL_PROV)

    def test_late_error_does_not_return_first_candidate(self):
        self.kw["bindings"][1]["pdb"]["chains"][0]["role"] = "candidate"; self.seal()
        d = self.error("wrong_chain_role")
        self.assertEqual(d["candidate_id"], "fixture-1")

    def test_schema_roundtrip_filters_checks_and_exclusive_output(self):
        run = create_run_directory(self.root, "audit-run")
        self.kw["manifest"]["output_paths"] = [str(run / name) for name in ("result.json", "manifest.json")]
        result = self.result(); serialized = json.loads(json.dumps(result.to_dict(), allow_nan=False))
        for c in serialized["candidates"]: self.assertEqual(CandidateEvidence(**c).to_dict(), c)
        decisions = filter_candidates(result.candidates, [{"context": "complex", "name": "csv:/plddt", "min": 90}])
        self.assertEqual([d["accepted"] for d in decisions], [True, False])
        structure = read_structure(self.root / "toy.pdb")
        for check in (structure_integrity_check(structure), coarse_steric_clash_check(structure)):
            self.assertEqual(check.provenance["input_sha256"], self.meta(result.candidates[0])["pdb_bindings"][0]["sha256"])
        write_json_new(run / "result.json", serialized)
        with self.assertRaises(FileExistsError): write_json_new(run / "result.json", serialized)
        self.assertNotEqual(run, create_run_directory(self.root, "audit-run"))
        write_manifest(run / "manifest.json", self.kw["manifest"])
        self.assertEqual(self.meta(result.candidates[0])["manifest"]["sha256"], hash_config(read_json(run / "manifest.json")))

    def test_no_scan_network_subprocess_writes_or_model_imports(self):
        before = {name: (self.root / name).read_bytes() for name in FILES}
        patches = [(glob, "glob"), (os, "listdir"), (os, "scandir"), (os, "walk"),
                   (Path, "glob"), (Path, "rglob"), (socket, "socket"), (subprocess, "Popen")]
        from contextlib import ExitStack
        with ExitStack() as stack:
            for obj, attr in patches:
                stack.enter_context(patch.object(obj, attr, side_effect=AssertionError(f"Forbidden: {attr}")))
            original_open, original_io_open = builtins.open, io.open
            def read_only(function):
                def guarded(file, mode="r", *args, **kwargs):
                    if any(c in mode for c in "wax+"):
                        raise AssertionError(f"Forbidden write mode: {mode}")
                    return function(file, mode, *args, **kwargs)
                return guarded
            stack.enter_context(patch.object(builtins, "open", side_effect=read_only(original_open)))
            stack.enter_context(patch.object(io, "open", side_effect=read_only(original_io_open)))
            a = self.result().to_dict(); b = self.result().to_dict()
            self.assertEqual(a, b)
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in FILES})
        for module in ("torch", "jax", "pyrosetta", "colabdesign", "boltz"):
            self.assertNotIn(module, sys.modules)

    def test_hash_change_during_import_is_fatal(self):
        original = canonical_residue_map
        def mutate(structure):
            (self.root / "boltz1.json").write_text('{"iptm":0.8}')
            return original(structure)
        with patch("structure_audit.notebook_output_adapter.canonical_residue_map", side_effect=mutate):
            self.error("artifact_changed_during_import")


if __name__ == "__main__":
    unittest.main()
