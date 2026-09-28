"""Contract tests for the frozen synthetic Layer 2 fixture pack.

The fixture pack is synthetic and non-biological; these tests pin its inventory, its
contract validity, the Layer 1 identities it copies and the profile behavior the current
contracts actually produce. Nothing here evaluates Layer 1 or edits any notebook.

Run: python3 -B -m unittest discover -s tests -t tests \
         -p 'test_demo_layer_2_fixture_pack.py' -v
"""
from __future__ import annotations

import ast
import copy
import json
import pathlib
import sys
import types
import unittest

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

# The kernel package lives at avidity_sim/files while its consumers import it as gotne.
# Binding it here keeps this test runnable at the repository's current layout; nothing is
# copied, moved or written.
if "gotne" not in sys.modules:
    package = types.ModuleType("gotne")
    package.__path__ = [str(ROOT_DIR / "files")]
    sys.modules["gotne"] = package

import demo_candidate_scenarios as demo  # noqa: E402
import demo_layer_2_fixture_pack as fixture  # noqa: E402
from gotne import layer_2a_descriptor_input as local_contract  # noqa: E402
from gotne import layer_2b_descriptor_input as collective_contract  # noqa: E402
from gotne.layer_2_initial_triage_profile import Layer2InitialTriageProfile  # noqa: E402

MODULE_PATH = pathlib.Path(fixture.__file__)
NOTEBOOK = ROOT_DIR.parent / "diffusion_fixed.ipynb"


def demo_result():
    return demo.build_synthetic_demo()


class FixtureInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = demo_result()
        cls.pack = fixture.build_layer_2_fixture_pack(cls.result)

    def test_the_pack_holds_nine_local_three_collective_and_one_cohort(self):
        self.assertEqual(len(self.pack.local_documents), 9)
        self.assertEqual(len(self.pack.collective_documents), 3)
        self.assertEqual(len(self.pack.candidates), 3)
        self.assertEqual(len(self.pack.cohort.dimension_directions), 3)

    def test_every_candidate_declares_three_ordered_local_positions(self):
        for candidate in self.pack.candidates:
            with self.subTest(candidate=candidate.candidate_id):
                self.assertEqual(
                    tuple(item.position_role for item in candidate.local_inputs),
                    ("slot_1", "slot_2", "slot_3"),
                )

    def test_the_frozen_slot_bindings_are_used_unchanged(self):
        self.assertEqual(
            fixture.CANDIDATE_SLOT_BINDINGS,
            {
                "z-stable": ("start", "middle", "end"),
                "a-context-sensitive": ("start", "moving", "end"),
                "m-excluded": ("start", "far", "end"),
            },
        )
        for document in self.pack.local_documents:
            with self.subTest(document=document.document_id):
                candidate_id = document.candidate_anchor.candidate_id
                position = ("slot_1", "slot_2", "slot_3").index(document.scope.slot_id)
                self.assertEqual(
                    document.scope.target_site_declaration,
                    fixture.CANDIDATE_SLOT_BINDINGS[candidate_id][position],
                )

    def test_retained_candidates_are_populated_and_the_excluded_one_is_not(self):
        populated = [d for d in self.pack.local_documents if d.descriptors]
        self.assertEqual(len(populated), 6)
        self.assertEqual(
            {d.candidate_anchor.candidate_id for d in populated},
            {"z-stable", "a-context-sensitive"},
        )
        excluded_local = [
            d for d in self.pack.local_documents
            if d.candidate_anchor.candidate_id == "m-excluded"
        ]
        self.assertEqual(len(excluded_local), 3)
        for document in excluded_local:
            with self.subTest(document=document.document_id):
                self.assertEqual(document.descriptors, ())
                self.assertEqual(document.poses, ())
        excluded_collective = next(
            d for d in self.pack.collective_documents
            if d.candidate_anchor.candidate_id == "m-excluded"
        )
        self.assertEqual(excluded_collective.descriptors, ())
        self.assertEqual(excluded_collective.poses, ())
        self.assertIsNone(excluded_collective.scope.joint_frame)

    def test_document_ids_are_distinct_and_revisions_fixed(self):
        documents = self.pack.local_documents + self.pack.collective_documents
        identifiers = [document.document_id for document in documents]
        self.assertEqual(len(set(identifiers)), len(identifiers))
        for document in documents:
            with self.subTest(document=document.document_id):
                self.assertEqual(document.revision, "synthetic-rev-1")
                self.assertEqual(document.declared_by, "synthetic-demo-fixture")
                self.assertEqual(document.declared_at, "2026-01-01T00:00:00Z")

    def test_the_topology_is_the_frozen_chain(self):
        collective = next(
            d for d in self.pack.collective_documents
            if d.candidate_anchor.candidate_id == "z-stable"
        )
        kinds = {element.element_id: element.kind for element in collective.scope.assembly_elements}
        self.assertEqual(kinds["a0"], "ANCHOR")
        for linker in ("s0", "s1", "s2"):
            self.assertEqual(kinds[linker], "LINKER")
        edges = [
            (connection.first_subject_id, connection.second_subject_id)
            for connection in collective.scope.connections
        ]
        self.assertEqual(
            edges,
            [
                ("a0", "s0"),
                ("s0", "synthetic-binder-D1"),
                ("synthetic-binder-D1", "s1"),
                ("s1", "synthetic-binder-D2"),
                ("synthetic-binder-D2", "s2"),
                ("s2", "synthetic-binder-D3"),
            ],
        )

    def test_the_collective_frame_is_separately_declared(self):
        collective = next(
            d for d in self.pack.collective_documents
            if d.candidate_anchor.candidate_id == "z-stable"
        )
        local_pose_ids = {
            pose.pose_id
            for document in self.pack.local_documents
            for pose in document.poses
        }
        frame = collective.scope.joint_frame
        self.assertEqual(frame.frame_kind, "CALLER_DECLARED_ARTIFACT_MODEL_FRAME")
        self.assertEqual(len(frame.pose_ids), 1)
        self.assertNotIn(frame.pose_ids[0], local_pose_ids)


class FixtureValues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = fixture.build_layer_2_fixture_pack(demo_result())

    def populated_descriptors(self, documents):
        return [descriptor for document in documents for descriptor in document.descriptors]

    def test_the_canonical_decimal_spelling_is_used(self):
        self.assertEqual(fixture.FIXTURE_VALUE, "1")
        for descriptor in self.populated_descriptors(
            self.pack.local_documents + self.pack.collective_documents
        ):
            with self.subTest(descriptor=descriptor.descriptor_id):
                value = descriptor.observations[0].value
                self.assertEqual((value.kind, value.number, value.category), ("NUMERIC", "1", None))
                self.assertEqual(descriptor.definition.unit_class, "LENGTH")
                self.assertEqual(descriptor.definition.unit_symbol, "nm")

    def test_local_observable_metadata_is_identical_and_distinct_from_collective(self):
        local = self.populated_descriptors(self.pack.local_documents)
        collective = self.populated_descriptors(self.pack.collective_documents)
        self.assertEqual(len(local), 6)
        self.assertEqual(len(collective), 2)
        local_keys = {
            (d.definition.observable_name, d.definition.definition_reference) for d in local
        }
        collective_keys = {
            (d.definition.observable_name, d.definition.definition_reference) for d in collective
        }
        self.assertEqual(len(local_keys), 1)
        self.assertEqual(len(collective_keys), 1)
        self.assertEqual(local_keys & collective_keys, set())

    def test_every_populated_descriptor_carries_the_six_unknown_uncertainties(self):
        for descriptor in self.populated_descriptors(
            self.pack.local_documents + self.pack.collective_documents
        ):
            with self.subTest(descriptor=descriptor.descriptor_id):
                self.assertEqual(
                    tuple(item.kind for item in descriptor.uncertainties),
                    local_contract.L2_UNCERTAINTY_KINDS,
                )
                for item in descriptor.uncertainties:
                    self.assertEqual(item.state, "UNKNOWN")
                    self.assertEqual(item.declaration, fixture.UNCERTAINTY_DECLARATION)
                self.assertEqual(descriptor.ambiguities, ())
                self.assertEqual(descriptor.conflicts, ())

    def test_the_fixture_source_wording_is_carried(self):
        self.assertEqual(
            fixture.FIXTURE_SOURCE_WORDING,
            "Synthetic stand-in for declared computational evidence; manually assigned, "
            "not computed or measured.",
        )
        for descriptor in self.populated_descriptors(self.pack.local_documents):
            with self.subTest(descriptor=descriptor.descriptor_id):
                self.assertEqual(
                    descriptor.definition.method.representation, fixture.FIXTURE_SOURCE_WORDING
                )

    def test_anchors_carry_no_invented_digest(self):
        for document in self.pack.local_documents + self.pack.collective_documents:
            for pose in document.poses:
                with self.subTest(pose=pose.pose_id):
                    self.assertEqual(pose.artifact_anchor.kind, "IMMUTABLE_SNAPSHOT")
                    self.assertIsNone(pose.artifact_anchor.algorithm)
                    self.assertIsNone(pose.artifact_anchor.digest)
                    self.assertIsNone(pose.locator)

    def test_the_cohort_declaration_is_the_frozen_one(self):
        cohort = self.pack.cohort
        self.assertEqual(cohort.layer1_comparison_basis, "synthetic-near")
        self.assertEqual(cohort.target_system_identity, "synthetic-near-target-system")
        self.assertEqual(
            cohort.collective_task_scope_type,
            "Synthetic demo only: cas1 with D1-D2-D3, anchor a0, and linkers s0-s1-s2.",
        )
        self.assertEqual(cohort.triage_convention_version, "layer_2_initial_triage/1")
        self.assertEqual(cohort.ordered_local_position_roles, ("slot_1", "slot_2", "slot_3"))
        self.assertEqual(
            [(item.dimension, item.direction) for item in cohort.dimension_directions],
            [
                ("COLLECTIVE_INTERFERENCE", "LOWER_IS_PREFERRED"),
                ("COLLECTIVE_DEFORMATION_RESTRAINT_BURDEN", "NO_DIRECTION_DECLARED"),
                ("LOCAL_ISOLATED_REFERENCE_DEFORMATION_BURDEN", "LOWER_IS_PREFERRED"),
            ],
        )

    def test_the_cohort_carriers_match_every_populated_collective_document(self):
        for document in self.pack.collective_documents:
            if not document.descriptors:
                continue
            with self.subTest(document=document.document_id):
                self.assertEqual(
                    document.scope.target_site_declaration, self.pack.cohort.target_system_identity
                )
                self.assertEqual(
                    document.scope.assembly_task_declaration,
                    self.pack.cohort.collective_task_scope_type,
                )


class ContractValidity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = fixture.build_layer_2_fixture_pack(demo_result())

    def test_every_local_document_round_trips_through_its_contract(self):
        for document in self.pack.local_documents:
            with self.subTest(document=document.document_id):
                again = local_contract.Layer2ADescriptorInput.from_json_bytes(
                    document.to_json_bytes()
                )
                self.assertEqual(again.to_json_bytes(), document.to_json_bytes())

    def test_every_collective_document_round_trips_through_its_contract(self):
        for document in self.pack.collective_documents:
            with self.subTest(document=document.document_id):
                again = collective_contract.Layer2BDescriptorInput.from_json_bytes(
                    document.to_json_bytes()
                )
                self.assertEqual(again.to_json_bytes(), document.to_json_bytes())

    def test_populated_descriptors_are_derived_as_provided(self):
        for document in self.pack.local_documents + self.pack.collective_documents:
            for index, descriptor in enumerate(document.descriptors):
                with self.subTest(document=document.document_id, descriptor=descriptor.descriptor_id):
                    self.assertEqual(document.descriptor_conditions[index], ("PROVIDED",))
                    self.assertEqual(document.descriptor_reasons[index], ())

    def test_the_pack_is_rebuilt_identically_on_every_call(self):
        first = fixture.build_layer_2_fixture_pack(demo_result())
        second = fixture.build_layer_2_fixture_pack(demo_result())
        self.assertEqual(
            [d.to_json_bytes() for d in first.local_documents],
            [d.to_json_bytes() for d in second.local_documents],
        )
        self.assertEqual(
            [d.to_json_bytes() for d in first.collective_documents],
            [d.to_json_bytes() for d in second.collective_documents],
        )


class CopiedLayer1Identities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = demo_result()
        position = [s.scenario_id for s in cls.result.scenarios].index("synthetic-near")
        cls.report = cls.result.priority_reports[position].as_dict()
        cls.pack = fixture.build_layer_2_fixture_pack(cls.result)

    def test_the_supplied_report_is_not_mutated(self):
        before = json.dumps(self.report, sort_keys=True)
        fixture.build_layer_2_fixture_pack(self.result)
        fixture.build_synthetic_triage_profile(self.result)
        position = [s.scenario_id for s in self.result.scenarios].index("synthetic-near")
        after = json.dumps(self.result.priority_reports[position].as_dict(), sort_keys=True)
        self.assertEqual(after, before)

    def test_admission_identities_are_copied_from_the_report(self):
        members = {
            member["candidate_id"]: member
            for group in self.report["groups"]
            for member in group["members"]
        }
        excluded = {entry["candidate_id"]: entry for entry in self.report["excluded"]}
        for document in self.pack.local_documents + self.pack.collective_documents:
            candidate_id = document.candidate_anchor.candidate_id
            admission = document.candidate_anchor.admission_reference
            with self.subTest(document=document.document_id):
                source = members.get(candidate_id) or excluded[candidate_id]
                self.assertEqual(admission.slot_binding_hash, source["slot_binding_hash"])
                if candidate_id in members:
                    self.assertEqual(admission.state_result_id, source["state_result_id"])
                    self.assertEqual(admission.certificate_present, source["certificate_present"])
                    self.assertIsNone(admission.ineligibility_reason)
                    self.assertEqual(admission.absent_keys, ("ineligibility_reason",))
                else:
                    self.assertEqual(
                        admission.ineligibility_reason, source["ineligibility_reason"]
                    )
                    self.assertIsNone(admission.state_result_id)
                    self.assertEqual(
                        admission.absent_keys, ("state_result_id", "certificate_present")
                    )

    def test_scenario_and_run_identities_are_the_frozen_ones(self):
        for document in self.pack.local_documents + self.pack.collective_documents:
            with self.subTest(document=document.document_id):
                self.assertEqual(document.candidate_anchor.scenario_id, "synthetic-near")
                self.assertEqual(
                    document.candidate_anchor.evaluation_run_ref, "synthetic-near-run"
                )

    def test_a_report_without_the_cohort_is_refused(self):
        report = copy.deepcopy(self.report)
        report["groups"] = []
        report["excluded"] = []
        with self.assertRaises(ValueError):
            fixture.build_layer_2_fixture_pack(report)

    def test_the_shifted_scenario_is_never_used(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertNotIn("synthetic-shifted", source)


class ProfileBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profile = fixture.build_synthetic_triage_profile(demo_result())

    def states(self):
        return {item.candidate_id: item.profile_state for item in self.profile.candidates}

    def test_the_relation_is_one_cohort_wide_two_member_group(self):
        self.assertEqual(self.profile.relation.scope, "COHORT_WIDE")
        self.assertIsNone(self.profile.relation.withheld_reason)
        self.assertEqual(
            [list(group) for group in self.profile.relation.ordered_groups],
            [["a-context-sensitive", "z-stable"]],
        )

    def test_both_retained_candidates_tie(self):
        states = self.states()
        self.assertEqual(states["z-stable"], "EXPERIMENTAL_PRIORITY_TIE")
        self.assertEqual(states["a-context-sensitive"], "EXPERIMENTAL_PRIORITY_TIE")

    def test_the_excluded_candidate_fails_only_at_the_layer_1_boundary(self):
        entry = next(
            item for item in self.profile.candidates if item.candidate_id == "m-excluded"
        )
        self.assertEqual(entry.profile_state, "NOT_PRIORITIZED_BY_PROFILE")
        self.assertEqual(entry.layer1.disposition, "EXCLUDED")
        failed = [gate for gate in entry.gates if gate.disposition == "FAILED"]
        self.assertEqual(
            [(gate.gate, gate.reason) for gate in failed],
            [("LAYER1_BOUNDARY", "LAYER1_EXCLUDED")],
        )
        self.assertEqual(entry.gates[0].disposition, "PASSED")
        for gate in entry.gates[2:]:
            self.assertEqual(gate.disposition, "NOT_EVALUATED")

    def test_missing_layer_2_evidence_creates_no_adverse_preference(self):
        entry = next(
            item for item in self.profile.candidates if item.candidate_id == "m-excluded"
        )
        for state in entry.dimensions:
            with self.subTest(dimension=state.dimension):
                self.assertEqual(state.state, "SUSPENDED")
                self.assertIsNone(state.record)
        self.assertNotIn(
            "m-excluded",
            [member for group in self.profile.relation.ordered_groups for member in group],
        )

    def test_the_active_and_suspended_dimensions_are_the_frozen_ones(self):
        self.assertEqual(
            [(item.dimension, item.state, item.suspension_reason) for item in self.profile.cohort_dimensions],
            [
                ("COLLECTIVE_INTERFERENCE", "ACTIVE", None),
                ("COLLECTIVE_DEFORMATION_RESTRAINT_BURDEN", "SUSPENDED", "NO_DIRECTION_DECLARED"),
                ("LOCAL_ISOLATED_REFERENCE_DEFORMATION_BURDEN", "ACTIVE", None),
            ],
        )
        self.assertEqual(
            self.profile.relation.basis_dimensions, ("COLLECTIVE_INTERFERENCE",)
        )

    def test_the_profile_is_canonical_and_reproducible(self):
        again = fixture.build_synthetic_triage_profile(demo_result())
        self.assertEqual(again.to_json_bytes(), self.profile.to_json_bytes())
        reloaded = Layer2InitialTriageProfile.from_json_bytes(self.profile.to_json_bytes())
        self.assertEqual(reloaded.to_json_bytes(), self.profile.to_json_bytes())


class FixtureBoundaries(unittest.TestCase):
    def imported_modules(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
        return modules - {"__future__"}

    def test_the_module_imports_only_the_contracts_it_fills(self):
        self.assertEqual(
            self.imported_modules(),
            {
                "dataclasses",
                "gotne",
                "gotne.layer_2_initial_triage_profile",
            },
        )

    def test_the_module_evaluates_no_layer_1_and_opens_nothing(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = node.func
                called.add(
                    target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
                )
        for banned in (
            "open", "eval", "exec", "compile", "__import__", "read_text", "read_bytes",
            "glob", "listdir", "walk", "urlopen", "Popen", "run", "evaluate_state",
            "evaluate_node", "evaluate_candidate_batch", "evaluate_candidate_priority",
            "declare_candidate_manifest", "compare_scenarios", "build_synthetic_demo",
            "sha256", "hash", "sorted", "sort",
        ):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, called)

    def test_no_kernel_package_file_imports_this_fixture_or_the_demo_facade(self):
        for path in (ROOT_DIR / "files").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""] + [alias.name for alias in node.names]
                else:
                    continue
                for name in names:
                    with self.subTest(path=path.name, name=name):
                        self.assertNotIn(
                            name.split(".")[-1],
                            {"demo_layer_2_fixture_pack", "demo_candidate_scenarios"},
                        )

    def test_the_fixture_labels_itself_synthetic(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("SYNTHETIC DEMO ONLY — NON-BIOLOGICAL", source)
        self.assertIn("Missing evidence is not\nnegative evidence", source)


class NotebookAssignment(unittest.TestCase):
    """The notebook seam: the assignment cell and the untouched published cells."""

    @classmethod
    def setUpClass(cls):
        cls.cells = json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]
        cls.ids = [cell["metadata"]["id"] for cell in cls.cells]

    def test_the_assignment_cells_sit_immediately_before_the_published_block(self):
        self.assertIn("triage-profile-00-assignment", self.ids)
        self.assertIn("triage-profile-00-disclaimer", self.ids)
        position = self.ids.index("triage-profile-00-disclaimer")
        self.assertEqual(
            self.ids[position:position + 3],
            [
                "triage-profile-00-disclaimer",
                "triage-profile-00-assignment",
                "triage-profile-00-section",
            ],
        )

    def test_the_assignment_defines_exactly_one_document_variable(self):
        cell = self.cells[self.ids.index("triage-profile-00-assignment")]
        source = "".join(cell["source"])
        assigned = [
            node.targets[0].id
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
        ]
        self.assertIn("TRIAGE_PROFILE_DOCUMENT", assigned)
        self.assertEqual(assigned.count("TRIAGE_PROFILE_DOCUMENT"), 1)
        self.assertEqual(cell["execution_count"], None)
        self.assertEqual(cell["outputs"], [])

    def test_the_disclaimer_is_the_frozen_text(self):
        cell = self.cells[self.ids.index("triage-profile-00-disclaimer")]
        source = "".join(cell["source"])
        self.assertEqual(cell["cell_type"], "markdown")
        for phrase in (
            "SYNTHETIC DEMO ONLY — NON-BIOLOGICAL",
            "manually invented\nstand-ins for computational descriptors",
            "Missing\nevidence is not negative evidence.",
        ):
            with self.subTest(phrase=phrase.replace("\n", " ")):
                self.assertIn(phrase, source)

    def test_the_six_published_cells_are_unchanged_and_contiguous(self):
        from gotne import layer_2_triage_profile_report as report

        published = report.notebook_cell_sources()
        start = self.ids.index(published[0][0])
        block = self.cells[start:start + len(published)]
        self.assertEqual(
            [(cell["metadata"]["id"], cell["cell_type"]) for cell in block],
            [(cell_id, kind) for cell_id, kind, _ in published],
        )
        for cell, (_cell_id, _kind, source) in zip(block, published):
            self.assertEqual("".join(cell["source"]), source)

    def test_the_assignment_opens_no_file_and_launches_no_tool(self):
        cell = self.cells[self.ids.index("triage-profile-00-assignment")]
        tree = ast.parse("".join(cell["source"]))
        called, modules = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = node.func
                called.add(
                    target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
                )
            elif isinstance(node, ast.Import):
                modules |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
        for banned in ("open", "eval", "exec", "compile", "__import__", "urlopen",
                       "Popen", "run", "write_text", "to_csv", "savefig", "pymol", "vina"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, called)
        self.assertTrue(
            modules <= {"demo_candidate_scenarios", "demo_layer_2_fixture_pack"}, modules
        )


if __name__ == "__main__":
    unittest.main()
