"""Synthetic native-format checks; no AF3 execution or core integration."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from structure_audit.af3_native_bridge import (
    AF3NativeCIF, AF3NativeFormatError, read_af3_native_cif,
)
from structure_audit.af3_red_adapter import (
    build_red_manifest, discover_red_runs, discover_structure_files,
    validate_basic_mapping_readiness,
)
from structure_audit.structures import read_structure, UnsupportedFormat

FIXTURES = Path(__file__).parent / "fixtures" / "af3_native"
PROJECT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NativeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.path = self.root / "native.cif"
        self.path.write_bytes((FIXTURES / "minimal.cif").read_bytes())

    def read(self):
        return read_af3_native_cif(self.path, model_id="1")

    def variant(self, *, remove=(), extra=(), change=None):
        """Alter fixture columns/rows without depending on the bridge parser."""
        text = (FIXTURES / "minimal.cif").read_text()
        head, table = text.split("loop_\n", 1)
        lines = table.splitlines()
        columns = [line for line in lines if line.startswith("_atom_site.")]
        rows = [dict(zip(columns, line.split())) for line in lines if line[:1].isdigit()]
        for row in rows:
            if change:
                change(row)
            for key, value in extra:
                row[key] = value
        columns = [key for key in columns if key not in remove] + [key for key, _ in extra]
        text = head + "loop_\n" + "\n".join(columns) + "\n"
        text += "\n".join(" ".join(row[k] for k in columns) for row in rows) + "\n#\n"
        self.path.write_text(text)

    def test_present_fields_only_explicit_namespaces_and_raw_tokens(self):
        before = (sha(self.path), self.path.stat().st_mtime_ns)
        native = self.read()
        self.assertIsInstance(native, AF3NativeCIF)
        self.assertFalse(hasattr(native, "atoms"))
        self.assertFalse(hasattr(native, "residues"))
        row = native.rows[0]
        self.assertEqual(set(row.fields), {c.lower() for c in native.columns})
        self.assertEqual(row.fields["_atom_site.label_atom_id"], "N")
        self.assertEqual(row.fields["_atom_site.label_asym_id"], "A")
        self.assertEqual(row.fields["_atom_site.auth_asym_id"], "AA")
        self.assertEqual(row.fields["_atom_site.label_seq_id"], "1")
        self.assertEqual(row.fields["_atom_site.auth_seq_id"], "10")
        self.assertEqual(row.fields["_atom_site.pdbx_pdb_ins_code"], "?")
        self.assertNotIn("_atom_site.auth_atom_id", row.fields)
        self.assertNotIn("_atom_site.auth_comp_id", row.fields)
        self.assertFalse(any("segment" in k or "target" in k for k in row.fields))
        self.assertEqual(native.source_sha256, sha(self.path))
        self.assertEqual(native.provenance()["profile"], "af3_native_v1")
        self.assertEqual(native.provenance()["reader_version"], "0.1")
        self.assertFalse(native.provenance()["producer_verified"])
        json.dumps(native.to_dict(), allow_nan=False)
        source = self.path.read_text().splitlines()
        self.assertTrue(source[row.source_lines[0] - 1].startswith("1 ATOM"))
        self.assertEqual(before, (sha(self.path), self.path.stat().st_mtime_ns))

    def test_strict_reader_still_rejects_same_fixture(self):
        with self.assertRaisesRegex(UnsupportedFormat, "missing explicit atom_site fields"):
            read_structure(self.path, model_id="1")

    def test_hetatm_placeholders_preserved_without_label_residue_invention(self):
        rows = [r.fields for r in self.read().rows if r.fields["_atom_site.group_pdb"] == "HETATM"]
        self.assertEqual([r["_atom_site.label_seq_id"] for r in rows], [".", ".", "?"])
        self.assertEqual(rows[0]["_atom_site.auth_seq_id"], "1")

    def test_multimodel_requires_explicit_existing_model(self):
        self.path.write_bytes((FIXTURES / "multimodel.cif").read_bytes())
        second = read_af3_native_cif(self.path, model_id="2")
        self.assertEqual(second.available_models, ("1", "2"))
        self.assertEqual(len(second.rows), 1)
        self.assertEqual(second.rows[0].fields["_atom_site.pdbx_pdb_model_num"], "2")
        for model in (None, 1, "", "0", "3"):
            with self.subTest(model=model), self.assertRaises(AF3NativeFormatError):
                read_af3_native_cif(self.path, model_id=model)
        with self.assertRaises(TypeError):
            read_af3_native_cif(self.path)

    def test_missing_model_or_author_identity_never_defaults(self):
        for tag in ("pdbx_PDB_model_num", "auth_asym_id", "auth_seq_id", "label_seq_id", "id"):
            self.variant(remove=("_atom_site." + tag,))
            with self.subTest(tag=tag), self.assertRaisesRegex(AF3NativeFormatError, "Missing explicit"):
                self.read()

    def test_present_author_atom_fields_require_another_explicit_profile(self):
        for extra in ((('_atom_site.auth_atom_id', 'N'),),
                      (('_atom_site.auth_comp_id', 'GLY'),),
                      (('_atom_site.auth_atom_id', 'N'), ('_atom_site.auth_comp_id', 'GLY'))):
            self.variant(extra=extra)
            with self.assertRaisesRegex(AF3NativeFormatError, "requires absent"):
                self.read()

    def test_nonfinite_and_malformed_coordinates(self):
        for value in ("nan", "inf", "-inf", "1e999", "nonnumeric", "?", "."):
            self.variant(change=lambda row: row.update({"_atom_site.Cartn_x": value}))
            with self.subTest(value=value), self.assertRaises(AF3NativeFormatError):
                self.read()

    def test_duplicate_atom_identity_despite_distinct_site_ids(self):
        self.path.write_bytes((FIXTURES / "duplicate_identity.cif").read_bytes())
        with self.assertRaisesRegex(AF3NativeFormatError, "Duplicate atom identity"):
            self.read()

    def test_duplicate_site_id(self):
        self.variant(change=lambda row: row.update({"_atom_site.id": "1"}))
        with self.assertRaisesRegex(AF3NativeFormatError, "Duplicate atom-site ID"):
            self.read()

    def test_altlocs_and_quoted_placeholders_rejected(self):
        for value in ("A", "B", "'.'", '"?"'):
            self.variant(change=lambda row: row.update({"_atom_site.label_alt_id": value}))
            with self.subTest(value=value), self.assertRaises(AF3NativeFormatError):
                self.read()

    def test_chain_aliases_in_both_directions_rejected(self):
        for key, value in (("auth_asym_id", "AA"), ("label_asym_id", "A")):
            self.variant(change=lambda row: row.update({"_atom_site." + key: value})
                         if row["_atom_site.id"] in ("3", "4") else None)
            with self.subTest(key=key), self.assertRaisesRegex(AF3NativeFormatError, "chain aliases"):
                self.read()

    def test_conflicting_residue_relations_and_components_rejected(self):
        for key, value in (("auth_seq_id", "11"), ("label_seq_id", "2"), ("label_comp_id", "ALA")):
            self.variant(change=lambda row: row.update({"_atom_site." + key: value})
                         if row["_atom_site.id"] == "2" else None)
            with self.subTest(key=key), self.assertRaises(AF3NativeFormatError):
                self.read()

    def test_insertion_codes_preserved_and_ambiguous_relation_rejected(self):
        self.assertEqual(self.read().rows[2].fields["_atom_site.pdbx_pdb_ins_code"], "A")
        self.variant(change=lambda row: row.update({"_atom_site.pdbx_PDB_ins_code": "B"})
                     if row["_atom_site.id"] == "4" else None)
        with self.assertRaisesRegex(AF3NativeFormatError, "label/author residue"):
            self.read()

    def test_unknown_identity_tokens_rejected(self):
        for key in ("auth_seq_id", "auth_asym_id", "label_atom_id", "label_comp_id", "label_seq_id", "pdbx_PDB_model_num"):
            self.variant(change=lambda row: row.update({"_atom_site." + key: "?"}))
            with self.subTest(key=key), self.assertRaises(AF3NativeFormatError):
                self.read()

    def test_optional_columns_absent_are_not_fabricated(self):
        self.variant(remove=("_atom_site.occupancy", "_atom_site.B_iso_or_equiv", "_atom_site.label_entity_id"))
        self.assertNotIn("_atom_site.occupancy", self.read().rows[0].fields)

    def test_quoted_fields_and_wrapped_rows_keep_source_locations(self):
        self.path.write_text(self.path.read_text().replace("1 ATOM N N . GLY", "1 ATOM N 'N'\n. GLY"))
        row = self.read().rows[0]
        self.assertEqual(len(row.source_lines), 2)
        self.assertIn("_atom_site.label_atom_id", row.quoted_fields)

    def test_malformed_or_unsupported_cif_syntax(self):
        original = self.path.read_text()
        variants = [original + "data_second\n", original + "stop_\n",
                    original.replace("_atom_site.id\n", "_atom_site.id\n_atom_site.id\n"),
                    original.replace("1 ATOM N N", "1 ATOM N"),
                    original.replace("_atom_site.id", "_other.id"),
                    original.replace("_entry.id 'synthetic native'", "_entry.id"),
                    original + "loop_\n_atom_site.foo\nx\n",
                    "#\\#CIF_2.0\n" + original, original.replace("\n;\n", "\n", 1),
                    original.replace("'synthetic native'", "'unterminated")]
        for index, text in enumerate(variants):
            self.path.write_text(text)
            with self.subTest(index=index), self.assertRaises(AF3NativeFormatError):
                self.read()

    def test_symlink_and_compressed_inputs_rejected(self):
        alias = self.root / "alias.cif"
        alias.symlink_to(self.path)
        compressed = self.root / "native.cif.gz"
        compressed.write_bytes(self.path.read_bytes())
        for path in (alias, compressed):
            with self.assertRaises(AF3NativeFormatError):
                read_af3_native_cif(path, model_id="1")

    def test_file_changed_during_read_rejected(self):
        import structure_audit.af3_native_bridge as bridge
        original_table = bridge._native_table
        def change(text):
            self.path.write_text(text + "\n# concurrent edit\n")
            return original_table(text)
        with patch.object(bridge, "_native_table", side_effect=change):
            with self.assertRaisesRegex(AF3NativeFormatError, "changed"):
                self.read()


class NativeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.run_dir = self.root / "toy"
        sample = self.run_dir / "seed-7_sample-0"
        sample.mkdir(parents=True)
        self.path = sample / "toy_seed-7_sample-0_model.cif"
        self.path.write_bytes((FIXTURES / "minimal.cif").read_bytes())
        data = self.run_dir / "toy_data.json"
        data.write_text(json.dumps({"name": "Toy", "dialect": "alphafold3", "version": 3,
            "modelSeeds": [7], "sequences": [{"protein": {"id": "A", "sequence": "G"}}]}))
        self.side = self.run_dir / "af3red_adapter_metadata.json"
        self.side.write_text(json.dumps({"schema_version": "0.1", "producer": "AF3-ReD",
            "declared_run_id": "synthetic", "input_sha256": sha(data),
            "bias_sigma": 2.0, "bias_weight": 90.0, "source_revision": None,
            "evidence_note": "Synthetic test, not inference"}))
        self.run, = discover_red_runs(self.root)
        self.artifact, = discover_structure_files(self.run)
        self.binding = {"artifact_sha256": self.artifact.sha256, "target_id": "supplied-target",
                        "model_id": "1", "auth_asym_id": "AA", "label_asym_id": "A"}

    def manifest(self, binding=None, **kwargs):
        return build_red_manifest(self.root, profile="af3_native_v1",
            bindings={self.artifact.artifact_id: self.binding if binding is None else binding}, **kwargs)

    def test_explicit_native_profile_admits_only_mapping_prep_and_attests_profile(self):
        before = {str(p): (sha(p), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()}
        manifest = self.manifest()
        row, = manifest["artifacts"]
        self.assertEqual(manifest["schema"], "af3red_external_inventory/0.2")
        self.assertEqual(manifest["reader_profile"], "af3_native_v1")
        self.assertEqual(row["status"], "admitted")
        self.assertEqual(row["reasons"], ["external_mapping_preparation_only"])
        self.assertTrue(row["read_provenance"]["read_completed"])
        self.assertEqual(row["read_provenance"]["source_sha256"], self.artifact.sha256)
        self.assertEqual(row["read_provenance"]["profile"], "af3_native_v1")
        self.assertNotIn("segment", row["binding"])
        self.assertEqual(before, {str(p): (sha(p), p.stat().st_mtime_ns) for p in self.root.rglob("*") if p.is_file()})
        self.assertEqual(manifest, self.manifest())

    def test_no_binding_or_missing_run_declaration_remains_candidate(self):
        manifest = build_red_manifest(self.root, profile="af3_native_v1")
        self.assertEqual(manifest["artifacts"][0]["status"], "candidate")
        self.assertFalse(manifest["artifacts"][0]["read_provenance"]["read_completed"])
        self.side.unlink()
        manifest = self.manifest()
        self.assertEqual(manifest["artifacts"][0]["status"], "candidate")
        self.assertTrue(manifest["artifacts"][0]["read_provenance"]["read_completed"])

    def test_wrong_binding_and_hetatm_target_rejected(self):
        for update in ({"auth_asym_id": "A"}, {"label_asym_id": "AA"}, {"model_id": "7"},
                       {"artifact_sha256": "0"*64}, {"segment": 0},
                       {"auth_asym_id": "LC", "label_asym_id": "C"}):
            with self.subTest(update=update):
                row = self.manifest({**self.binding, **update})["artifacts"][0]
                self.assertEqual(row["status"], "rejected")

    def test_default_strict_path_does_not_autodetect_or_fallback(self):
        binding = {"artifact_sha256": self.artifact.sha256, "target_id": "supplied-target",
                   "model_id": "1", "auth_chain_id": "AA", "segment": 0}
        manifest = build_red_manifest(self.root, bindings={self.artifact.artifact_id: binding}, reader=read_structure)
        row = manifest["artifacts"][0]
        self.assertEqual(row["status"], "rejected")
        self.assertEqual(manifest["reader_profile"], "strict")
        self.assertIn("missing explicit atom_site fields", row["reasons"][0])

    def test_unknown_profiles_and_callback_mixing_fail_even_without_bindings(self):
        for kwargs in ({"profile": "auto"}, {"profile": "af3_native_v1", "reader": read_structure},
                       {"reader": read_af3_native_cif}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                build_red_manifest(self.root, **kwargs)
        with self.assertRaises(ValueError):
            validate_basic_mapping_readiness(self.artifact, self.run, reader=read_af3_native_cif)

    def test_wrapped_bridge_is_not_accepted_as_strict_structure(self):
        binding = {"artifact_sha256": self.artifact.sha256, "target_id": "supplied-target",
                   "model_id": "1", "auth_chain_id": "AA", "segment": 0}
        row = build_red_manifest(self.root, bindings={self.artifact.artifact_id: binding},
            reader=lambda path, model_id: read_af3_native_cif(path, model_id=model_id))["artifacts"][0]
        self.assertEqual(row["status"], "rejected")
        self.assertIn("no native bridge substitution", row["reasons"][0])

    def test_stale_bytes_and_metadata_remain_rejected(self):
        self.path.write_text(self.path.read_text() + "\n# changed\n")
        result = validate_basic_mapping_readiness(self.artifact, self.run,
            binding=self.binding, profile="af3_native_v1")
        self.assertEqual(result.status, "rejected")
        with self.assertRaisesRegex(ValueError, "stale artifact"):
            self.manifest()

    def test_reader_error_preserves_profile_and_version(self):
        self.path.write_bytes((FIXTURES / "duplicate_identity.cif").read_bytes())
        self.run, = discover_red_runs(self.root)
        self.artifact, = discover_structure_files(self.run)
        self.binding["artifact_sha256"] = self.artifact.sha256
        row = self.manifest()["artifacts"][0]
        self.assertEqual(row["status"], "rejected")
        self.assertEqual(row["read_provenance"]["profile"], "af3_native_v1")
        self.assertEqual(row["read_provenance"]["reader_version"], "0.1")
        self.assertFalse(row["read_provenance"]["read_completed"])

    def test_standalone_notebook_bridge_parity_and_native_admission(self):
        notebook = json.loads((PROJECT / "examples/af3_red_colab.ipynb").read_text())
        bridge_cells = [c for c in notebook["cells"] if c.get("metadata", {}).get("af3_component") == "native_bridge"]
        self.assertEqual(len(bridge_cells), 1)
        source = "".join(bridge_cells[0]["source"])
        self.assertEqual(source, (PROJECT / "src/structure_audit/af3_native_bridge.py").read_text())
        namespace = {"__name__": "__main__"}
        for cell in notebook["cells"]:
            if cell["cell_type"] == "code":
                exec(compile("".join(cell["source"]), "<notebook>", "exec"), namespace)
        result = namespace["build_red_manifest"](self.root, profile="af3_native_v1",
                    bindings={self.artifact.artifact_id: self.binding})
        self.assertEqual(result, self.manifest())


if __name__ == "__main__":
    unittest.main()
