import tempfile
import unittest
from pathlib import Path

from structure_audit import read_structure, canonical_residue_map, validate_sequence_mapping
from structure_audit.structures import UnsupportedFormat, StructureFormatError
from structure_audit.checks import structure_integrity_check, coarse_steric_clash_check
from helpers import atom, backbone, FIXTURES


class StructuresTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def read(self, text, suffix=".pdb", **kwargs):
        path = Path(self.tmp.name)/("input"+suffix)
        path.write_text(text)
        return read_structure(path, **kwargs)

    def test_insertion_codes_preserved(self):
        st = self.read(backbone(10)+backbone(10, offset=3.5, icode="A"))
        rows = canonical_residue_map(st)
        self.assertEqual([(r["residue_id"],r["insertion_code"]) for r in rows], [(10,""),(10,"A")])
        self.assertEqual(structure_integrity_check(st).metrics["duplicate_id_warning_count"],0)

    def test_missing_atom_and_supplied_missing_residue(self):
        st = self.read(backbone(1,skip=("O",))+backbone(3,offset=7))
        check = structure_integrity_check(st, {"expected_residues":[{"chain_id":"A","residue_id":2,"insertion_code":""}]})
        self.assertEqual(check.metrics["missing_backbone"][0]["atoms"],["O"])
        self.assertEqual(check.metrics["missing_expected_residues"][0]["residue_id"],2)
        self.assertEqual(check.metrics["numbering_gaps"][0]["numbering_gap_size"],1)
        self.assertEqual(check.status,"warn")

    def test_numbering_gap_does_not_prove_missing_residue(self):
        st = self.read(backbone(1)+backbone(3,offset=3.5))
        check = structure_integrity_check(st)
        self.assertEqual(check.metrics["missing_expected_residues"],[])
        self.assertTrue(check.metrics["numbering_gaps"])

    def test_multichain_and_blank_chain(self):
        st = self.read(backbone(chain="")+backbone(chain="B",offset=20))
        self.assertEqual([r["chain_id"] for r in canonical_residue_map(st)],["","B"])
        self.assertEqual(structure_integrity_check(st).metrics["chain_breaks"],[])

    def test_duplicate_residue_occurrences_retained(self):
        st = self.read(backbone(1)+backbone(2,offset=3.5)+backbone(1,offset=7))
        self.assertEqual(len(st.residues),3)
        self.assertEqual(structure_integrity_check(st).status,"fail")
        self.assertIn("duplicate_residue_id",{w["code"] for w in st.warnings})

    def test_duplicate_atom_not_silently_selected(self):
        st = self.read(backbone()+atom(name="CA"))
        self.assertEqual(len(st.atoms),5)
        check = structure_integrity_check(st)
        self.assertEqual(check.status,"fail")
        self.assertIn("CA",check.metrics["missing_backbone"][0]["atoms"])

    def test_chain_break(self):
        st = self.read(backbone()+backbone(2,offset=30))
        breaks = structure_integrity_check(st).metrics["chain_breaks"]
        self.assertEqual(len(breaks),1)
        self.assertGreater(breaks[0]["cn_distance_angstrom"],20)

    def test_ter_is_explicit_boundary(self):
        st = self.read(backbone()+"TER\n"+backbone(2,offset=30))
        check = structure_integrity_check(st)
        self.assertEqual(check.metrics["chain_breaks"],[])
        self.assertEqual(check.metrics["ter_boundary_count"],1)

    def test_chain_continuity_missing_atoms_not_passed(self):
        st = self.read(backbone(skip=("C",))+backbone(2,offset=3.5))
        self.assertEqual(structure_integrity_check(st).metrics["unavailable_neighbor_count"],1)

    def test_deliberate_clash(self):
        st = self.read(atom(chain="A")+atom(chain="B",xyz=(0.5,0,0)))
        check = coarse_steric_clash_check(st,{"fail_at_count":1})
        self.assertEqual(check.metrics["close_contact_count"],1)
        self.assertEqual(check.metrics["pairs"][0]["distance_angstrom"],0.5)
        self.assertEqual(check.status,"fail")
        self.assertEqual(check.category,"format/geometric plausibility only")

    def test_far_apart_chains_pass(self):
        st = self.read(backbone()+backbone(chain="B",offset=20))
        self.assertEqual(coarse_steric_clash_check(st).status,"pass")

    def test_integrity_pass_with_explicit_completeness(self):
        st = self.read(backbone())
        self.assertEqual(structure_integrity_check(st,{"expected_residues":[{"chain_id":"A","residue_id":1,"insertion_code":""}]}).status,"pass")

    def test_single_chain_scope_unavailable(self):
        self.assertEqual(coarse_steric_clash_check(self.read(backbone())).status,"warn")

    def test_clash_threshold_is_strict(self):
        st = self.read(atom()+atom(chain="B",xyz=(2,0,0)))
        self.assertEqual(coarse_steric_clash_check(st).metrics["close_contact_count"],0)

    def test_nonlocal_excludes_neighbors(self):
        st = self.read(atom(res=1)+atom(res=2)+atom(res=3))
        check = coarse_steric_clash_check(st,{"scope":"nonlocal"})
        self.assertEqual(check.metrics["close_contact_count"],1)

    def test_invalid_coordinates(self):
        st = self.read(atom(xyz=(float('nan'),0,0))+atom(chain="B"))
        self.assertEqual(structure_integrity_check(st).status,"fail")
        clash = coarse_steric_clash_check(st)
        self.assertTrue(clash.metrics["partial"])
        self.assertNotEqual(clash.status,"pass")

    def test_missing_element_not_guessed(self):
        st = self.read(atom(element="")+atom(chain="B"))
        self.assertEqual(coarse_steric_clash_check(st).metrics["excluded_atom_count"],1)

    def test_altloc_explicit_no_fallback(self):
        st = self.read(atom(alt="A")+atom(alt="B",xyz=(20,0,0)))
        self.assertEqual(st.warnings,[])
        self.assertEqual(canonical_residue_map(st,altloc="A")[0]["atom_names"],["CA"])
        self.assertEqual(canonical_residue_map(st,altloc="C")[0]["atom_names"],[])

    def test_multi_model_requires_selection(self):
        text = "MODEL        1\n"+backbone()+"ENDMDL\nMODEL        2\n"+backbone()+"ENDMDL\n"
        with self.assertRaisesRegex(UnsupportedFormat,"model_id"):
            self.read(text)
        st = self.read(text,model_id="2")
        self.assertEqual(st.model_id,"2")
        self.assertEqual(len(st.residues),1)

    def test_microheterogeneity_explicitly_unsupported(self):
        with self.assertRaisesRegex(UnsupportedFormat,"microheterogeneity"):
            self.read(atom(residue="GLY")+atom(name="N",residue="ALA"))

    def test_mmcif_auth_label_and_insertion(self):
        st = read_structure(FIXTURES/"minimal.cif")
        rows = canonical_residue_map(st)
        self.assertEqual(rows[0]["chain_id"],"AA")
        self.assertEqual(rows[0]["label_chain_id"],"X")
        self.assertEqual(rows[0]["insertion_code"],"A")
        self.assertEqual(rows[0]["residue_id"],10)
        self.assertEqual(rows[0]["label_seq_id"],1)

    def test_mmcif_missing_identifier_unsupported(self):
        text = (FIXTURES/"minimal.cif").read_text().replace("_atom_site.auth_asym_id","_atom_site.other_asym_id")
        with self.assertRaisesRegex(UnsupportedFormat,"missing explicit"):
            self.read(text,".cif")

    def test_mmcif_unknown_identifier_no_fallback(self):
        text = (FIXTURES/"minimal.cif").read_text().replace("GLY AA 10", "GLY ? 10")
        with self.assertRaisesRegex(UnsupportedFormat,"unknown atom_site.auth_asym_id"):
            self.read(text,".cif")

    def test_mmcif_quoted_unknown_not_blank(self):
        text = (FIXTURES/"minimal.cif").read_text().replace("GLY AA 10", "GLY '?' 10")
        with self.assertRaisesRegex(UnsupportedFormat,"quoted placeholder"):
            self.read(text,".cif")

    def test_mmcif_auth_label_collision_unsupported(self):
        text = (FIXTURES/"minimal.cif").read_text().replace("GLY BB 1", "GLY AA 1")
        with self.assertRaisesRegex(UnsupportedFormat,"multiple label chains"):
            self.read(text,".cif")

    def test_mmcif_reverse_alias_collision_unsupported(self):
        text = (FIXTURES/"minimal.cif").read_text().replace("GLY Y 1", "GLY X 1")
        with self.assertRaisesRegex(UnsupportedFormat,"multiple author chains"):
            self.read(text,".cif")

    def test_mmcif_unknown_polymer_label_sequence_rejected(self):
        text = (FIXTURES/"minimal.cif").read_text().replace("GLY X 1", "GLY X ?")
        with self.assertRaisesRegex(UnsupportedFormat,"unknown atom_site.label_seq_id"):
            self.read(text,".cif")

    def test_cell_list_matches_independent_distance_count(self):
        import math
        import random
        rng = random.Random(42)
        points = [(round(rng.uniform(-4,4),3), round(rng.uniform(-4,4),3), round(rng.uniform(-4,4),3)) for _ in range(30)]
        text = ''.join(atom(i+1,res=i+1,chain='A' if i<15 else 'B',xyz=p) for i,p in enumerate(points))
        expected = sum(math.dist(a,b)<2.0 for a in points[:15] for b in points[15:])
        actual = coarse_steric_clash_check(self.read(text))
        self.assertEqual(actual.metrics['close_contact_count'],expected)

    def test_mmcif_multiline_metadata_and_quotes(self):
        text = (FIXTURES/"minimal.cif").read_text().replace("data_fixture", "data_fixture\n_note.text\n;non-instruction fixture\nsecond line\n;\n_note.title 'quoted title'")
        self.assertEqual(len(self.read(text,".cif").atoms),8)

    def test_mmcif_row_width_rejected(self):
        text = (FIXTURES/"minimal.cif").read_text()+"extra\n"
        with self.assertRaises(StructureFormatError):
            self.read(text,".cif")

    def test_mmcif_multiple_data_blocks_rejected(self):
        with self.assertRaisesRegex(UnsupportedFormat,"multiple CIF"):
            self.read((FIXTURES/"minimal.cif").read_text()+"\ndata_other\n",".cif")

    def test_cif2_rejected(self):
        with self.assertRaisesRegex(UnsupportedFormat,"CIF 2.0"):
            self.read('#\\#CIF_2.0\ndata_a\n',".cif")

    def test_mapping_identity_mismatch_and_missing(self):
        st = self.read(backbone())
        entry = {"sequence_position":1,"residue_index":0,"reason":None}
        self.assertEqual(validate_sequence_mapping(st,"G",[entry])[0]["status"],"matched")
        self.assertEqual(validate_sequence_mapping(st,"A",[entry])[0]["status"],"mismatch")
        self.assertEqual(validate_sequence_mapping(st,"G",[{**entry,"residue_index":None,"reason":"supplied gap"}])[0]["status"],"missing_or_unmapped")

    def test_mapping_ambiguous_or_nonstandard_rejected(self):
        st = self.read(atom(residue="UNK"))
        with self.assertRaises(UnsupportedFormat):
            validate_sequence_mapping(st,"G",[{"sequence_position":1,"residue_index":0,"reason":None}])

    def test_mapping_requires_all_positions(self):
        with self.assertRaises(ValueError):
            validate_sequence_mapping(self.read(backbone()),"G",[])

    def test_invalid_check_config_rejected(self):
        st = self.read(backbone())
        for config in ({"cutoff_angstrom":-1},{"cutoff_angstrom":float('nan')},{"scope":"auto"},{"unknown":1}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                coarse_steric_clash_check(st,config)

    def test_empty_and_truncated_pdb_rejected(self):
        for text in ("", "ATOM  1\n"):
            with self.assertRaises(StructureFormatError):
                self.read(text)
