from copy import deepcopy
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from structure_audit import (import_dl_binder_sc, read_structure, canonical_residue_map,
                             structure_integrity_check, coarse_steric_clash_check, filter_candidates)
from structure_audit.dl_binder_output_adapter import METADATA
from structure_audit.evidence import CandidateEvidence
from structure_audit.provenance import (create_run_directory, make_manifest, hash_file, hash_config,
                                        write_manifest, write_json_new)
from structure_audit.validation import read_json
from helpers import FIXTURES

PROVENANCE = {"model_id": "synthetic-only", "checkpoint_id": None, "seed": None}


class DlBinderOutputAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sc = self.root / "input.sc"
        self.sc.write_bytes((FIXTURES / "dl_binder.sc").read_bytes())
        self.pdb = self.root / "input.pdb"
        self.pdb.write_bytes((FIXTURES / "minimal.pdb").read_bytes())
        self.config = read_json(FIXTURES / "dl_binder_config.json")
        self.run = create_run_directory(self.root / "runs", "fixture")
        self.bindings = {"synthetic_complex": self.binding()}

    def binding(self):
        structure = read_structure(self.pdb, model_id="1")
        rows = canonical_residue_map(structure)
        chains = list(dict.fromkeys((r["chain_id"], r["segment"]) for r in rows))
        return {"candidate_id": "candidate-1", "target_id": "target", "conformer_id": "conformer",
                "pdb_path": str(self.pdb.resolve()), "pdb_model_id": "1", "residue_map": rows,
                "chain_roles": [{"chain_id": c, "segment": s, "role": role}
                                for (c, s), role in zip(chains, ["candidate", "target"])]}

    def kwargs(self):
        manifest = make_manifest(self.run, {"dl_binder_output_adapter": self.config},
                                 [self.sc, self.pdb], project_root=self.root,
                                 supplied_models=[PROVENANCE])
        return dict(bindings=self.bindings, manifest=manifest, config=self.config, provenance=PROVENANCE)

    def imported(self, **overrides):
        return import_dl_binder_sc(self.sc, **{**self.kwargs(), **overrides})

    def metric(self, candidate, name):
        return next(m for m in candidate.metrics if m["name"] == name)

    def metadata(self, candidate):
        return self.metric(candidate, METADATA)["raw_value"]

    def monomer(self):
        self.config["prediction_mode"] = "monomer"
        # Derive a one-residue fixture from the existing synthetic PDB only.
        text = self.pdb.read_text()
        self.pdb.write_text("".join(line + "\n" for line in text.splitlines()
                                  if not line.startswith("ATOM") or line[21] == "A"))
        self.bindings = {"synthetic_complex": self.binding()}

    def test_schema_raw_columns_tag_and_provenance(self):
        kwargs = self.kwargs()
        before = deepcopy(kwargs)
        candidate = import_dl_binder_sc(self.sc, **kwargs)[0]
        self.assertEqual(kwargs, before)
        data = candidate.to_dict()
        self.assertEqual(CandidateEvidence(**json.loads(json.dumps(data, allow_nan=False))).to_dict(), data)
        meta = self.metadata(candidate)
        self.assertEqual(meta["description"], "synthetic_complex")
        self.assertEqual(meta["raw_columns"]["description"], "synthetic_complex")
        self.assertEqual(meta["header_row"], 2)
        self.assertEqual(meta["manifest"]["sha256"], hash_config(kwargs["manifest"]))
        self.assertEqual(meta["binding"]["residue_map_sha256"], hash_config(self.binding()["residue_map"]))
        self.assertEqual(candidate.provenance, PROVENANCE)
        self.assertIsNone(candidate.sequence_hash)
        self.assertIn("sequence_hash", candidate.missing_values)
        metric = self.metric(candidate, "pae_interaction")
        self.assertEqual((metric["name"], metric["raw_value"], metric["value"]), ("pae_interaction", "8.500", 8.5))
        self.assertEqual(metric["source"], {"path": str(self.sc.resolve()), "sha256": hash_file(self.sc), "row": 3})
        self.assertEqual(metric["provenance"], PROVENANCE)
        self.assertEqual(self.metric(candidate, "plddt_binder")["scale"], "0-100")
        self.assertEqual(self.metric(candidate, "extra")["raw_value"], "opaque")
        self.assertIsNone(self.metric(candidate, "extra")["value"])
        self.assertNotIn("final_score", data)

    def test_reordered_columns_and_repeated_reordered_header(self):
        self.sc.write_text("SCORE: description pae_interaction plddt_binder\n"
                           "SCORE: tag1 8.500 85.000\n"
                           "SCORE: plddt_binder description pae_interaction\n"
                           "SCORE: 91.000 tag2 2.750\n")
        second = self.binding(); second["candidate_id"] = "candidate-2"
        self.bindings = {"tag1": self.binding(), "tag2": second}
        a, b = self.imported()
        self.assertEqual(self.metric(a, "pae_interaction")["value"], 8.5)
        self.assertEqual(self.metric(b, "pae_interaction")["value"], 2.75)
        self.assertEqual(self.metadata(b)["header"], ["plddt_binder", "description", "pae_interaction"])
        self.assertEqual(self.metadata(b)["header_row"], 3)

    def test_duplicate_tag_rejected(self):
        self.sc.write_text(self.sc.read_text() + self.sc.read_text().splitlines()[-1] + "\n")
        with self.assertRaisesRegex(ValueError, "duplicate tag"):
            self.imported()

    def test_nan_preserved_and_excluded_by_existing_filter(self):
        self.sc.write_text(self.sc.read_text().replace("8.500", "NaN"))
        c = self.imported()[0]
        m = self.metric(c, "pae_interaction")
        self.assertEqual(m["raw_value"], "NaN")
        self.assertIsNone(m["value"])
        self.assertEqual(self.metadata(c)["field_statuses"]["pae_interaction"]["status"], "non_finite")
        json.dumps(c.to_dict(), allow_nan=False)
        self.assertFalse(filter_candidates([c], [{"context": "complex", "name": "pae_interaction", "max": 10}])[0]["accepted"])

    def test_missing_tag_token_rejected(self):
        self.sc.write_text("SCORE: pae_interaction description\nSCORE: 8.5\n")
        with self.assertRaisesRegex(ValueError, "missing description/tag"):
            self.imported()

    def test_missing_tag_placeholder_rejected(self):
        self.sc.write_text("SCORE: pae_interaction description\nSCORE: 8.5 nan\n")
        with self.assertRaisesRegex(ValueError, "missing description/tag"):
            self.imported()

    def test_missing_or_extra_binding_rejected(self):
        for bindings in ({}, {**self.bindings, "absent": self.binding()}):
            with self.subTest(bindings=bindings), self.assertRaisesRegex(ValueError, "missing/extra tag"):
                self.imported(bindings=bindings)

    def test_wrong_chain_role_mapping_rejected(self):
        roles = self.bindings["synthetic_complex"]["chain_roles"]
        roles[0]["role"], roles[1]["role"] = "target", "candidate"
        with self.assertRaisesRegex(ValueError, "Wrong chain-role"):
            self.imported()

    def test_stale_residue_map_and_wrong_model_rejected(self):
        binding = self.bindings["synthetic_complex"]
        binding["residue_map"][0]["insertion_code"] = "X"
        with self.assertRaisesRegex(ValueError, "residue_map"):
            self.imported()
        self.bindings = {"synthetic_complex": self.binding()}
        self.bindings["synthetic_complex"]["pdb_model_id"] = "2"
        with self.assertRaises(ValueError):
            self.imported()

    def test_monomer_sentinel_rmsds_quarantined_even_if_finite(self):
        self.monomer()
        c = self.imported()[0]
        for name, raw in (("binder_aligned_rmsd", "0.250"), ("target_aligned_rmsd", "7.250")):
            with self.subTest(name=name):
                metric = self.metric(c, name)
                self.assertEqual(metric["raw_value"], raw)
                self.assertIsNone(metric["value"])
                self.assertEqual(metric["category"], "unsupported_semantics")
                self.assertIn("binderlen=-1", metric["missing_reason"])
                self.assertEqual(self.metadata(c)["field_statuses"][name]["status"], "quarantined")
                rule = [{"context": metric["context"], "name": name, "max": 100}]
                self.assertFalse(filter_candidates([c], rule)[0]["accepted"])
                with self.assertRaises(ValueError):
                    filter_candidates([c], rule, missing="error")
                included = filter_candidates([c], rule, missing="include")[0]
                self.assertTrue(included["accepted"])
                self.assertTrue(included["reasons"])  # Existing explicit include policy still warns.
        self.assertIsNone(self.metric(c, "pae_interaction")["value"])
        self.assertEqual(self.metric(c, "plddt_binder")["value"], 85.0)

    def test_monomer_nan_and_absent_rmsd_states_preserved(self):
        self.monomer()
        self.sc.write_text("SCORE: binder_aligned_rmsd description\nSCORE: nan synthetic_complex\n")
        c = self.imported()[0]
        statuses = self.metadata(c)["field_statuses"]
        self.assertEqual(statuses["binder_aligned_rmsd"]["raw_status"], "non_finite")
        self.assertEqual(statuses["target_aligned_rmsd"]["raw_status"], "missing")
        self.assertEqual(statuses["target_aligned_rmsd"]["status"], "quarantined")

    def test_monomer_mode_requires_monomer_output_reference(self):
        self.config["prediction_mode"] = "monomer"
        with self.assertRaisesRegex(ValueError, "chain count/order"):
            self.imported()

    def test_complex_shape_and_placement_remain_separate(self):
        c = self.imported()[0]
        shape = self.metric(c, "binder_aligned_rmsd")
        placement = self.metric(c, "target_aligned_rmsd")
        self.assertEqual((shape["context"], shape["value"]), ("monomer", 0.25))
        self.assertEqual((placement["context"], placement["value"]), ("complex", 7.25))
        self.assertEqual(self.metadata(c)["field_statuses"]["plddt_binder"]["prediction_context"], "complex")

    def test_absent_column_missing_token_and_unknown_number_preserved(self):
        self.sc.write_text("SCORE: pae_interaction mystery description\nSCORE: NA 99.0 synthetic_complex\n")
        c = self.imported()[0]
        self.assertEqual(self.metric(c, "pae_interaction")["raw_value"], "NA")
        self.assertIsNone(self.metric(c, "plddt_binder")["raw_value"])
        self.assertEqual(self.metric(c, "plddt_binder")["missing_reason"], "missing_column")
        self.assertEqual(self.metric(c, "mystery")["raw_value"], "99.0")
        self.assertIsNone(self.metric(c, "mystery")["value"])

    def test_bad_headers_and_silent_content_rejected(self):
        for content in ("", "SCORE: 2.0 tag\n", "SCORE: description description\n",
                        "SEQUENCE: G\n", "SCORE: __dl_binder_import__ description\n"):
            with self.subTest(content=content):
                self.sc.write_text(content)
                with self.assertRaises(ValueError):
                    self.imported()

    def test_manifest_config_and_input_hash_mismatches_rejected(self):
        for kind in ("config_hash", "adapter_config", "input_hash", "missing_input", "provenance"):
            kw = self.kwargs()
            if kind == "config_hash": kw["manifest"]["config_hash"] = "0" * 64
            if kind == "adapter_config": kw["config"] = {**self.config, "recycles": 4}
            if kind == "input_hash": kw["manifest"]["input_files"][1]["sha256"] = "0" * 64
            if kind == "missing_input": kw["manifest"]["input_files"].pop()
            if kind == "provenance": kw["provenance"] = {**PROVENANCE, "model_id": "different"}
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                import_dl_binder_sc(self.sc, **kw)

    def test_invalid_config_and_provenance_rejected(self):
        for config in ({**self.config, "profile": "unknown"}, {**self.config, "recycles": True},
                       {**self.config, "initial_guess": "yes"}, {**self.config, "run_inference": True}):
            self.config = config
            with self.subTest(config=config), self.assertRaises(ValueError):
                self.imported()
        self.config = read_json(FIXTURES / "dl_binder_config.json")
        with self.assertRaises(ValueError):
            self.imported(provenance={**PROVENANCE, "seed": -1})

    def test_duplicate_candidate_id_rejected(self):
        self.sc.write_text("SCORE: pae_interaction description\nSCORE: 8.5 a\nSCORE: 9.0 b\n")
        self.bindings = {"a": self.binding(), "b": self.binding()}
        with self.assertRaisesRegex(ValueError, "same candidate_id"):
            self.imported()

    def test_domain_violation_quarantined_without_rescaling(self):
        self.sc.write_text(self.sc.read_text().replace("85.000", "850.000"))
        c = self.imported()[0]
        m = self.metric(c, "plddt_binder")
        self.assertEqual(m["raw_value"], "850.000")
        self.assertIsNone(m["value"])
        self.assertIn("no automatic rescaling", m["missing_reason"])

    def test_overflow_token_is_non_finite(self):
        self.sc.write_text(self.sc.read_text().replace("8.500", "1e999"))
        c = self.imported()[0]
        self.assertEqual(self.metric(c, "pae_interaction")["raw_value"], "1e999")
        self.assertEqual(self.metadata(c)["field_statuses"]["pae_interaction"]["status"], "non_finite")

    def test_input_mutation_during_import_rejected(self):
        kw = self.kwargs()
        original = canonical_residue_map
        def mutate(structure):
            self.sc.write_text(self.sc.read_text() + "# changed\n")
            return original(structure)
        with patch("structure_audit.dl_binder_output_adapter.canonical_residue_map", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "Input changed"):
                import_dl_binder_sc(self.sc, **kw)

    def test_unknown_producer_fields_remain_null(self):
        kw = self.kwargs()
        kw["manifest"]["supplied_models"] = []
        kw["provenance"] = {"model_id": None, "checkpoint_id": None, "seed": None}
        c = import_dl_binder_sc(self.sc, **kw)[0]
        self.assertEqual(c.provenance, kw["provenance"])
        self.assertIsNone(self.metadata(c)["configuration"]["upstream_snapshot"])

    def test_compatible_checks_manifest_serialization_and_versioned_output(self):
        kw = self.kwargs()
        c = import_dl_binder_sc(self.sc, **kw)[0]
        structure = read_structure(self.pdb)
        checks = [structure_integrity_check(structure), coarse_steric_clash_check(structure)]
        out = self.run / "candidate_evidence.json"
        write_json_new(out, [c.to_dict()])
        write_json_new(self.run / "checks.json", [check.to_dict() for check in checks])
        # Persist the exact manifest referenced by candidate metadata.
        write_manifest(self.run / "manifest.json", kw["manifest"])
        self.assertEqual(read_json(out)[0]["candidate_id"], "candidate-1")
        self.assertEqual(checks[0].provenance["input_sha256"], self.metadata(c)["binding"]["pdb"]["sha256"])
        self.assertEqual(checks[0].category, "format/geometric plausibility only")
        with self.assertRaises(FileExistsError): write_json_new(out, [c.to_dict()])
        self.assertNotEqual(create_run_directory(self.root / "runs", "fixture"), self.run)

    def test_import_has_no_network_process_or_write_side_effect(self):
        kw = self.kwargs()
        before = {str(p): hash_file(p) for p in self.root.rglob("*") if p.is_file()}
        with patch.object(socket, "create_connection", side_effect=AssertionError("network")), \
                patch.object(subprocess, "Popen", side_effect=AssertionError("subprocess")):
            c = import_dl_binder_sc(self.sc, **kw)[0]
            self.assertEqual(c.to_dict(), import_dl_binder_sc(self.sc, **kw)[0].to_dict())
        after = {str(p): hash_file(p) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        for module in ("torch", "jax", "pyrosetta", "colabdesign", "boltz"):
            self.assertNotIn(module, sys.modules)


if __name__ == "__main__":
    unittest.main()
