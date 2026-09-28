"""Contract tests for the ``layer_2_initial_triage_profile/1`` display adapter.

The adapter and the profile contract it validates through are loaded from their files
under a throwaway package name, so no package initializer runs.

Run: python3 -B -m unittest discover -s tests -t tests \
         -p 'test_layer_2_triage_profile_report.py' -v
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import pathlib
import sys
import types
import unittest

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT_DIR / "files"
PACKAGE_NAME = "triage_report_pkg"
REPORT_PATH = PACKAGE_DIR / "layer_2_triage_profile_report.py"


def _load(module_name, path):
    spec = importlib.util.spec_from_file_location(
        "{0}.{1}".format(PACKAGE_NAME, module_name), path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(PACKAGE_DIR)]
sys.modules.setdefault(PACKAGE_NAME, package)
profile_module = _load(
    "layer_2_initial_triage_profile", PACKAGE_DIR / "layer_2_initial_triage_profile.py"
)
r = _load("layer_2_triage_profile_report", REPORT_PATH)
ProfileError = profile_module.Layer2TriageProfileError
ReportError = r.TriageProfileReportError

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import test_layer_2_initial_triage_profile as fixtures  # noqa: E402

# The comparator suite's builders are reused so no fixture is duplicated here.
fixtures.m = profile_module
build = fixtures.build
candidate = fixtures.candidate
cohort = fixtures.cohort
priority_document = fixtures.priority_document
TIER1 = fixtures.TIER1


def comparable_profile():
    return build((candidate("c1", "1.0", "1.0"), candidate("c2", "2.0", "3.0")))


def tied_profile():
    return build((candidate("c1", "1.0", "5.0"), candidate("c2", "5.0", "1.0")))


def subset_profile():
    return build(
        (
            candidate("c1", "1.0", "1.0"),
            candidate("c2", "2.0", "2.0"),
            candidate("c3", "3.0", "3.0", joint_frame=False),
        ),
        priority=priority_document(ranked=(("c1", TIER1), ("c2", TIER1), ("c3", TIER1))),
    )


def unsupported_profile():
    return build(
        (candidate("c1"), candidate("c2", "2.0", "2.0")),
        declaration=cohort(
            directions=(
                "NO_DIRECTION_DECLARED",
                "NO_DIRECTION_DECLARED",
                "NO_DIRECTION_DECLARED",
            )
        ),
    )


class LoadingAndValidation(unittest.TestCase):
    def setUp(self):
        self.profile = comparable_profile()

    def test_a_profile_a_mapping_and_canonical_bytes_all_load(self):
        for label, document in (
            ("record", self.profile),
            ("mapping", self.profile.as_dict()),
            ("bytes", self.profile.to_json_bytes()),
        ):
            with self.subTest(form=label):
                loaded = r.load_profile(document)
                self.assertEqual(loaded.to_json_bytes(), self.profile.to_json_bytes())

    def test_loading_validates_through_the_profile_contract(self):
        payload = copy.deepcopy(self.profile.as_dict())
        payload["non_claim"] = "modified"
        with self.assertRaises(ProfileError) as caught:
            r.load_profile(payload)
        self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")

    def test_noncanonical_bytes_are_refused_by_the_contract(self):
        data = json.dumps(self.profile.as_dict(), sort_keys=True, indent=2).encode("utf-8")
        with self.assertRaises(ProfileError) as caught:
            r.load_profile(data)
        self.assertEqual(caught.exception.code, "NON_CANONICAL_BYTES")

    def test_another_object_is_refused_by_the_adapter(self):
        for value in (None, 7, "profile", [1]):
            with self.subTest(value=value):
                with self.assertRaises(ReportError):
                    r.load_profile(value)

    def test_rendering_does_not_mutate_the_profile(self):
        before = self.profile.to_json_bytes()
        r.render_profile_lines(self.profile)
        r.candidate_inventory_rows(self.profile)
        r.top_candidate_combinations_rows(self.profile)
        self.assertEqual(self.profile.to_json_bytes(), before)


class InventoryView(unittest.TestCase):
    def test_the_inventory_keeps_the_profile_candidate_order(self):
        profile = build((candidate("c2", "2.0", "2.0"), candidate("c1", "1.0", "1.0")))
        rows = r.candidate_inventory_rows(profile)
        self.assertEqual([row["candidate_id"] for row in rows], ["c2", "c1"])

    def test_every_row_carries_exactly_the_declared_fields(self):
        for row in r.candidate_inventory_rows(comparable_profile()):
            self.assertEqual(tuple(row), r.ROW_FIELDS)

    def test_rows_are_plain_data(self):
        for row in r.candidate_inventory_rows(comparable_profile()):
            for key, value in row.items():
                with self.subTest(key=key):
                    self.assertIsInstance(value, (str, int, tuple, type(None)))
                    for item in value if isinstance(value, tuple) else ():
                        self.assertIsInstance(item, (str, dict))
                        if isinstance(item, dict):
                            self.assertEqual(tuple(item), r.ACTIVE_DIMENSION_DETAIL_FIELDS)
                            for detail in item.values():
                                self.assertIsInstance(detail, (str, type(None)))

    def test_layer_1_disposition_rank_and_tier_are_copied(self):
        rows = {row["candidate_id"]: row for row in r.candidate_inventory_rows(comparable_profile())}
        self.assertEqual(rows["c1"]["layer1_disposition"], "RANKED")
        self.assertEqual(rows["c1"]["layer1_rank"], 1)
        self.assertEqual(rows["c1"]["layer1_geometry_tier"], TIER1)

    def test_an_excluded_candidate_is_shown_without_rank_or_tier(self):
        profile = build(
            (candidate("c1"), candidate("c2", "0.1", "0.1")),
            priority=priority_document(
                ranked=(("c1", TIER1),), excluded=(("c2", "STATE_NOT_VALID"),)
            ),
        )
        rows = {row["candidate_id"]: row for row in r.candidate_inventory_rows(profile)}
        self.assertEqual(rows["c2"]["layer1_disposition"], "EXCLUDED")
        self.assertIsNone(rows["c2"]["layer1_rank"])
        self.assertIsNone(rows["c2"]["layer1_geometry_tier"])
        self.assertIsNone(rows["c2"]["group_index"])
        self.assertEqual(rows["c2"]["profile_state"], "NOT_PRIORITIZED_BY_PROFILE")

    def test_review_required_and_unsupported_states_are_displayed_as_declared(self):
        rows = {row["candidate_id"]: row for row in r.candidate_inventory_rows(subset_profile())}
        self.assertEqual(rows["c3"]["profile_state"], "REVIEW_REQUIRED")
        self.assertIsNone(rows["c3"]["group_index"])
        rows = {
            row["candidate_id"]: row
            for row in r.candidate_inventory_rows(unsupported_profile())
        }
        self.assertEqual(rows["c1"]["profile_state"], "COMPARISON_UNSUPPORTED")

    def test_active_and_suspended_dimensions_carry_their_reasons(self):
        profile = build(
            (candidate("c1", "1.0", "9.0"), candidate("c2", "2.0", "1.0")),
            declaration=cohort(
                directions=("LOWER_IS_PREFERRED", "NO_DIRECTION_DECLARED", "LOWER_IS_PREFERRED")
            ),
        )
        row = r.candidate_inventory_rows(profile)[0]
        self.assertIn("COLLECTIVE_INTERFERENCE", row["active_dimensions"])
        self.assertIn(
            "COLLECTIVE_DEFORMATION_RESTRAINT_BURDEN: NO_DIRECTION_DECLARED",
            row["suspended_dimensions"],
        )

    def test_local_dimensions_are_labeled_by_position(self):
        row = r.candidate_inventory_rows(comparable_profile())[0]
        labels = row["active_dimensions"] + row["suspended_dimensions"]
        self.assertTrue(
            any(label.startswith("LOCAL_ISOLATED_REFERENCE_DEFORMATION_BURDEN@slot_2")
                for label in labels)
        )

    def test_source_references_are_shown_and_never_opened(self):
        row = r.candidate_inventory_rows(comparable_profile())[0]
        self.assertEqual(
            row["source_references"][0], "cassette_candidate_priority/1/groups/0/members/0"
        )
        self.assertIn("layer_2b_descriptor_input/1 b-c1 rev-1", row["source_references"])
        self.assertIn(
            "layer_2a_descriptor_input/1@slot_3 a-c1-slot_3 rev-1", row["source_references"]
        )


class TopCandidateCombinations(unittest.TestCase):
    def test_the_leading_group_is_the_relation_group_zero(self):
        rows = r.top_candidate_combinations_rows(comparable_profile())
        self.assertEqual([row["candidate_id"] for row in rows], ["c1"])
        self.assertEqual(rows[0]["profile_state"], "EXPERIMENTAL_PRIORITY")
        self.assertEqual(rows[0]["group_index"], 0)

    def test_a_tie_group_lists_every_member(self):
        rows = r.top_candidate_combinations_rows(tied_profile())
        self.assertEqual([row["candidate_id"] for row in rows], ["c1", "c2"])
        for row in rows:
            self.assertEqual(row["profile_state"], "EXPERIMENTAL_PRIORITY_TIE")

    def test_a_later_group_is_selectable(self):
        rows = r.top_candidate_combinations_rows(comparable_profile(), group_index=1)
        self.assertEqual([row["candidate_id"] for row in rows], ["c2"])
        self.assertEqual(rows[0]["profile_state"], "NOT_PRIORITIZED_BY_PROFILE")

    def test_an_empty_relation_promotes_nobody(self):
        self.assertEqual(r.top_candidate_combinations_rows(unsupported_profile()), ())

    def test_an_out_of_range_or_invalid_group_is_refused(self):
        profile = comparable_profile()
        for value in (5, -1, "0", True):
            with self.subTest(value=value):
                with self.assertRaises(ReportError):
                    r.top_candidate_combinations_rows(profile, group_index=value)

    def test_a_subset_only_top_row_is_labeled_subset_only(self):
        rows = r.top_candidate_combinations_rows(subset_profile())
        self.assertEqual(rows[0]["relation_scope"], "GATE_PASSED_SUBSET_ONLY")
        self.assertEqual(rows[0]["withheld_reason"], "RETAINED_MEMBER_NOT_GATE_PASSED")

    def test_a_cohort_wide_top_row_carries_no_withheld_reason(self):
        rows = r.top_candidate_combinations_rows(comparable_profile())
        self.assertEqual(rows[0]["relation_scope"], "COHORT_WIDE")
        self.assertIsNone(rows[0]["withheld_reason"])

    def test_the_rows_are_deterministic(self):
        profile = subset_profile()
        self.assertEqual(
            r.top_candidate_combinations_rows(profile),
            r.top_candidate_combinations_rows(profile),
        )


class Rendering(unittest.TestCase):
    def test_rendering_is_deterministic_and_plain(self):
        profile = comparable_profile()
        first = r.render_profile_lines(profile)
        self.assertEqual(first, r.render_profile_lines(profile))
        self.assertTrue(all(isinstance(line, str) for line in first))

    def test_the_footer_is_the_non_claim(self):
        lines = r.render_profile_lines(comparable_profile())
        self.assertEqual(lines[-1], r.REPORT_NON_CLAIM)
        self.assertIn("not a cohort ranking", r.REPORT_NON_CLAIM)

    def test_a_subset_only_relation_is_labeled_in_the_rendering(self):
        lines = r.render_profile_lines(subset_profile())
        self.assertIn("relation scope: GATE_PASSED_SUBSET_ONLY", lines)
        self.assertIn(r.SUBSET_ONLY_LABEL, lines)
        self.assertIn(
            "full-cohort issuance withheld: RETAINED_MEMBER_NOT_GATE_PASSED", lines
        )

    def test_a_cohort_wide_relation_carries_no_subset_label(self):
        lines = r.render_profile_lines(comparable_profile())
        self.assertIn("relation scope: COHORT_WIDE", lines)
        self.assertNotIn(r.SUBSET_ONLY_LABEL, lines)

    def test_the_grouping_uses_the_relation_order(self):
        lines = r.render_profile_lines(comparable_profile())
        self.assertIn("  group 0: c1", lines)
        self.assertIn("  group 1: c2", lines)

    def test_an_unissued_comparison_is_stated_plainly(self):
        lines = r.render_profile_lines(unsupported_profile())
        self.assertIn("Priority grouping: no comparison was issued", lines)
        self.assertIn("comparison basis dimensions: none active", lines)

    def test_failed_gates_are_shown_with_their_reasons(self):
        lines = r.render_profile_lines(subset_profile())
        self.assertIn(
            "    gate COLLECTIVE_SCOPE: FAILED (COLLECTIVE_SCOPE_INCOMPLETE)", lines
        )

    def test_the_cohort_declaration_and_directions_are_restated(self):
        lines = r.render_profile_lines(comparable_profile())
        self.assertIn("convention: " + profile_module.TRIAGE_CONVENTION_VERSION, lines)
        self.assertIn("  COLLECTIVE_INTERFERENCE: LOWER_IS_PREFERRED", lines)


class DisplayBoundaries(unittest.TestCase):
    def imported_modules(self):
        tree = ast.parse(REPORT_PATH.read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
        return modules - {"__future__"}

    def test_only_the_profile_contract_is_imported(self):
        self.assertEqual(self.imported_modules(), {"layer_2_initial_triage_profile"})

    def test_no_producer_reader_or_tool_name_is_called(self):
        tree = ast.parse(REPORT_PATH.read_text(encoding="utf-8"))
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = node.func
                called.add(
                    target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
                )
        for banned in (
            "open", "eval", "exec", "compile", "__import__", "read_text", "read_bytes",
            "glob", "listdir", "walk", "urlopen", "Popen", "run", "cmd", "pymol",
            "build_initial_triage_profile", "sort", "sorted",
        ):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, called)

    def test_the_adapter_mints_no_document_type(self):
        source = REPORT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("/1\"", source.replace('TRIAGE_DOCUMENT_TYPE', ""))
        self.assertNotIn("to_json_bytes", source)


class ActiveDimensionDetail(unittest.TestCase):
    def details(self, profile, candidate_id="c1"):
        rows = {row["candidate_id"]: row for row in r.candidate_inventory_rows(profile)}
        return rows[candidate_id]["active_dimension_details"]

    def test_every_active_dimension_carries_value_unit_and_observable(self):
        details = self.details(comparable_profile())
        self.assertEqual(len(details), 5)
        for detail in details:
            with self.subTest(dimension=detail["dimension"]):
                self.assertEqual(tuple(detail), r.ACTIVE_DIMENSION_DETAIL_FIELDS)
                self.assertEqual(detail["unit_symbol"], "nm")
                self.assertEqual(detail["observable_name"], "observable")
        self.assertEqual([detail["value"] for detail in details[:2]], ["1.0", "1.0"])

    def test_a_collective_detail_carries_no_position_role(self):
        for detail in self.details(comparable_profile()):
            if detail["dimension"] in fixtures.m.COLLECTIVE_DIMENSIONS:
                with self.subTest(dimension=detail["dimension"]):
                    self.assertIsNone(detail["position_role"])

    def test_a_local_detail_carries_its_declared_position_role(self):
        local = [
            detail
            for detail in self.details(comparable_profile())
            if detail["dimension"] == fixtures.LOCAL
        ]
        self.assertEqual(
            [detail["position_role"] for detail in local], list(fixtures.POSITIONS)
        )

    def test_the_decimal_string_is_the_supplied_one(self):
        profile = build(
            (
                candidate("c1", "0.500", "2.0", locals_=("1.250", "1.0", "1.0")),
                candidate("c2", "2.0", "3.0"),
            )
        )
        values = [detail["value"] for detail in self.details(profile)]
        self.assertIn("0.500", values)
        self.assertIn("1.250", values)

    def test_a_suspended_dimension_contributes_no_detail(self):
        profile = build(
            (candidate("c1", "1.0", "9.0"), candidate("c2", "2.0", "1.0")),
            declaration=cohort(
                directions=("LOWER_IS_PREFERRED", "NO_DIRECTION_DECLARED", "LOWER_IS_PREFERRED")
            ),
        )
        dimensions = {detail["dimension"] for detail in self.details(profile)}
        self.assertNotIn("COLLECTIVE_DEFORMATION_RESTRAINT_BURDEN", dimensions)
        rows = {row["candidate_id"]: row for row in r.candidate_inventory_rows(profile)}
        self.assertIn(
            "COLLECTIVE_DEFORMATION_RESTRAINT_BURDEN: NO_DIRECTION_DECLARED",
            rows["c1"]["suspended_dimensions"],
        )


class TidyRowHelpers(unittest.TestCase):
    def test_active_dimension_rows_are_tidy_and_ordered(self):
        rows = r.active_dimension_rows(comparable_profile())
        self.assertEqual(len(rows), 10)
        for row in rows:
            self.assertEqual(tuple(row), r.ACTIVE_DIMENSION_ROW_FIELDS)
        self.assertEqual([row["candidate_id"] for row in rows[:5]], ["c1"] * 5)
        self.assertEqual(rows[0]["dimension"], "COLLECTIVE_INTERFERENCE")
        self.assertEqual(rows[0]["value"], "1.0")
        self.assertEqual(rows[0]["unit_class"], "LENGTH")
        self.assertEqual(rows[0]["descriptor_id"], "d-int-c1")
        self.assertIsNone(rows[0]["position_role"])
        self.assertEqual(rows[2]["position_role"], "slot_1")

    def test_active_dimension_rows_keep_relation_context(self):
        rows = r.active_dimension_rows(subset_profile())
        for row in rows:
            with self.subTest(candidate=row["candidate_id"]):
                self.assertEqual(row["relation_scope"], "GATE_PASSED_SUBSET_ONLY")
        leading = [row for row in rows if row["candidate_id"] == "c1"]
        self.assertTrue(leading)
        self.assertEqual(leading[0]["group_index"], 0)
        self.assertEqual(leading[0]["profile_state"], "EXPERIMENTAL_PRIORITY")

    def test_an_unsupported_profile_has_no_active_dimension_rows(self):
        self.assertEqual(r.active_dimension_rows(unsupported_profile()), ())

    def test_source_reference_rows_are_plain_and_open_nothing(self):
        rows = r.source_reference_rows(comparable_profile())
        for row in rows:
            self.assertEqual(tuple(row), r.SOURCE_ROW_FIELDS)
            for value in row.values():
                self.assertIsInstance(value, (str, type(None)))
        kinds = [row["source_kind"] for row in rows if row["candidate_id"] == "c1"]
        self.assertEqual(kinds, ["LAYER1", "COLLECTIVE", "LOCAL", "LOCAL", "LOCAL"])
        layer1 = rows[0]
        self.assertEqual(layer1["document_type"], "cassette_candidate_priority/1")
        self.assertEqual(layer1["pointer"], "/groups/0/members/0")
        self.assertIsNone(layer1["document_id"])

    def test_the_helpers_are_deterministic_and_do_not_mutate(self):
        profile = subset_profile()
        before = profile.to_json_bytes()
        self.assertEqual(r.active_dimension_rows(profile), r.active_dimension_rows(profile))
        self.assertEqual(r.source_reference_rows(profile), r.source_reference_rows(profile))
        self.assertEqual(profile.to_json_bytes(), before)

    def test_helpers_accept_a_mapping_and_canonical_bytes(self):
        profile = comparable_profile()
        for document in (profile.as_dict(), profile.to_json_bytes()):
            with self.subTest(form=type(document).__name__):
                self.assertEqual(
                    r.active_dimension_rows(document), r.active_dimension_rows(profile)
                )


class RenderingWithValues(unittest.TestCase):
    def test_the_short_rendering_still_shows_only_non_passing_gates(self):
        lines = r.render_profile_lines(subset_profile())
        self.assertIn(
            "    gate COLLECTIVE_SCOPE: FAILED (COLLECTIVE_SCOPE_INCOMPLETE)", lines
        )
        self.assertFalse(any("PASSED" in line and "gate" in line for line in lines))

    def test_active_lines_carry_the_value_and_unit(self):
        lines = r.render_profile_lines(comparable_profile())
        self.assertIn("    active COLLECTIVE_INTERFERENCE: 1.0 nm", lines)
        self.assertIn(
            "    active LOCAL_ISOLATED_REFERENCE_DEFORMATION_BURDEN@slot_2: 1.0 nm", lines
        )

    def test_a_candidate_without_active_dimensions_says_none(self):
        lines = r.render_profile_lines(unsupported_profile())
        self.assertIn("    active: none", lines)

    def test_rendering_remains_deterministic(self):
        profile = subset_profile()
        self.assertEqual(r.render_profile_lines(profile), r.render_profile_lines(profile))


class NotebookSurface(unittest.TestCase):
    """The paste-ready cells: text a reader pastes, never an edit this module performs."""

    def test_the_cells_are_returned_fresh_and_identically_on_every_call(self):
        self.assertEqual(r.notebook_cell_sources(), r.notebook_cell_sources())
        self.assertEqual(
            [(cell_id, kind) for cell_id, kind, _ in r.notebook_cell_sources()],
            [
                ("triage-profile-00-section", "markdown"),
                ("triage-profile-01-load", "code"),
                ("triage-profile-02-inventory", "code"),
                ("triage-profile-03-top-candidates", "code"),
                ("triage-profile-04-dimensions", "code"),
                ("triage-profile-05-sources", "code"),
            ],
        )

    def test_returning_the_cells_opens_and_writes_no_notebook(self):
        notebook = ROOT_DIR.parent / "diffusion_fixed.ipynb"
        before = notebook.stat().st_mtime_ns if notebook.is_file() else None
        r.notebook_cell_sources()
        self.assertEqual(
            notebook.stat().st_mtime_ns if notebook.is_file() else None, before
        )

    def test_every_code_cell_parses_and_imports_only_this_layer(self):
        for cell_id, kind, source in r.notebook_cell_sources():
            if kind != "code":
                continue
            modules = set()
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Import):
                    modules |= {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules.add(node.module)
            with self.subTest(cell=cell_id):
                self.assertTrue(
                    modules <= {"gotne.layer_2_triage_profile_report", "pandas"}, modules
                )

    def test_no_code_cell_reaches_a_producer_a_reader_or_a_tool(self):
        forbidden = {
            "open", "eval", "exec", "compile", "__import__", "Path", "read_text",
            "read_bytes", "glob", "listdir", "walk", "urlopen", "Popen", "run", "cmd",
            "pymol", "vina", "dock", "sorted", "sort",
            "build_initial_triage_profile", "build_combinations_table",
        }
        for cell_id, kind, source in r.notebook_cell_sources():
            if kind != "code":
                continue
            used = set()
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Name):
                    used.add(node.id)
                elif isinstance(node, ast.Attribute):
                    used.add(node.attr)
            with self.subTest(cell=cell_id):
                self.assertEqual(used & forbidden, set())

    def test_the_section_cell_states_the_read_only_boundaries(self):
        section = r.notebook_cell_sources()[0][2]
        for phrase in (
            "recomputes, reorders, aggregates or ranks",
            "GATE_PASSED_SUBSET_ONLY",
            "not a cohort-wide priority",
            "not losses",
            "missing evidence is not negative evidence",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, section)

    def test_the_cells_run_in_order_against_a_supplied_profile(self):
        namespace = {"TRIAGE_PROFILE_DOCUMENT": subset_profile().as_dict()}
        printed = []
        namespace["print"] = lambda *args, **kwargs: printed.append(
            " ".join(str(item) for item in args)
        )
        package = types.ModuleType("gotne")
        package.layer_2_triage_profile_report = r
        sys.modules.setdefault("gotne", package)
        sys.modules.setdefault("gotne.layer_2_triage_profile_report", r)
        has_pandas = importlib.util.find_spec("pandas") is not None
        skipped = []
        for cell_id, kind, source in r.notebook_cell_sources():
            if kind != "code":
                continue
            if "import pandas" in source and not has_pandas:
                # These display cells use the pandas idiom the notebook already uses.
                # This checkout has no pandas, so they are reported as not executed here
                # rather than partially simulated; their row calls are covered by the
                # TidyRowHelpers and InventoryView tests.
                skipped.append(cell_id)
                continue
            with self.subTest(cell=cell_id):
                exec(compile(source, cell_id, "exec"), namespace)
        self.assertEqual(
            skipped,
            []
            if has_pandas
            else [
                "triage-profile-02-inventory",
                "triage-profile-04-dimensions",
                "triage-profile-05-sources",
            ],
        )
        text = "\n".join(printed)
        self.assertIn("subset-only: gate-passed candidates", text)
        self.assertIn("RETAINED_MEMBER_NOT_GATE_PASSED", text)
        self.assertIn("REVIEW_REQUIRED", text)
        self.assertIn("COLLECTIVE_INTERFERENCE", text)


if __name__ == "__main__":
    unittest.main()
