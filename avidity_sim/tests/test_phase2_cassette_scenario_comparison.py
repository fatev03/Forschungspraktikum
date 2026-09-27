"""Finished-report comparison only; arranged records are not new evaluations.

Uses the repository's existing gotne package layout convention. The current
files/ checkout can be exposed as gotne in a temporary test layout without
changing the repository. No source fixture or upstream baseline is modified.
"""

import ast
import builtins
import pathlib
import socket
import sys
import unittest
from contextlib import ExitStack
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from gotne import cassette_candidate_batch as batch_module
from gotne import cassette_candidate_priority as priority_module
from gotne import cassette_scenario_comparison as comparison
from gotne.cassette_candidate_batch import (
    CandidateBatchReport, CandidateEntry, DeclarationRefusal, EntryKind, RefusalStage,
)
from gotne.cassette_candidate_priority import (
    CandidatePriorityReport, EvidenceCoverage, ExcludedEntry, GeometryTier,
    IneligibilityReason, PriorityGroup, PriorityMember, StructureEvidenceRecord,
    TierBasisRow, TIER_ORDER, PRIORITY_NON_CLAIM, PRIORITY_DISPLAY_DISCLAIMER,
)
from gotne.cassette_scenario_comparison import (
    ScenarioDeclaration, ScenarioComparisonReport, compare_scenarios, render_lines,
)
from gotne.cassette_slot_ledger import FailureClass, NodePresence, SlotLedger, SlotLedgerRow
from gotne.cassette_slots import SLOT_IDS
from gotne.cassette_state import EngagementLabel
from gotne.status import Status

T1, T2, T3 = TIER_ORDER


def finished(sid, *, order=("zebra", "alpha", "middle"), tiers=(T1, T2, T3),
             excluded=(), evidence=None, context=True):
    """Arrange public finished records; no evaluator runs in this fixture.

    All slot bindings stay fixed. T2/T3 use absent node results, which the
    existing ledger/priority contracts permit even though the batch producer
    normally supplies every engaged node. These exercise reporting, not kernel
    reachability. The real-public-path test below separately uses evaluated data.
    """
    entries, groups, exclusions = [], [], []
    buckets = {tier: [] for tier in TIER_ORDER}
    for cid, tier in zip(order, tiers):
        excluded_here = cid in excluded
        state_status = Status.UNREACHABLE if excluded_here else Status.VALID
        failure = FailureClass.UNREACHABLE_GEOMETRIC_VETO if excluded_here else FailureClass.NOT_VETOED
        state_id = f"state:{sid}:{cid}"
        rows = tuple(SlotLedgerRow(
            slot=slot, module_id=f"module:{slot.value}", label=EngagementLabel.ENGAGED,
            target_id=f"target:{cid}:{slot.value}", cassette_index=0,
            failure_class=failure, state_result_id=state_id, state_status=state_status,
            state_status_reason="CHAIN_CLOSURE_VIOLATED" if excluded_here else "unchanged producer reason",
            node_presence=NodePresence.PRESENT if tier is T1 or (tier is T2 and index == 0)
                          else NodePresence.ABSENT_NOT_SUPPLIED,
            node_object_id=f"node:{slot.value}", node_result_id=f"node-result:{sid}:{cid}:{slot.value}",
            node_status=state_status, node_status_reason="unchanged node reason",
        ) for index, slot in enumerate(SLOT_IDS))
        ledger = SlotLedger(rows, f"binding:{cid}", state_id, "existing-config-identity",
                            f"existing-context:{sid}" if context else None, not excluded_here)
        entries.append(CandidateEntry(cid, ledger.slot_binding_hash, EntryKind.EVALUATED, ledger, None))
        if excluded_here:
            exclusions.append(ExcludedEntry(cid, ledger.slot_binding_hash,
                IneligibilityReason.STATE_NOT_VALID, state_status, rows[0].state_status_reason,
                (), None, None, None))
        else:
            buckets[tier].append(PriorityMember(cid, ledger.slot_binding_hash, state_id,
                ledger.certificate_present, tier,
                EvidenceCoverage.ABSENT if evidence is None else EvidenceCoverage.CANDIDATE,
                evidence, tuple(TierBasisRow(r.slot, r.label, r.node_presence, r.failure_class) for r in rows)))
    for tier in TIER_ORDER:
        if buckets[tier]:
            groups.append(PriorityGroup(len(groups) + 1, tier, tuple(buckets[tier])))
    return CandidateBatchReport(tuple(entries)), CandidatePriorityReport(tuple(order), tuple(groups), tuple(exclusions))


def declaration(sid, reports=None, **kwargs):
    batch, priority = finished(sid, **kwargs) if reports is None else reports
    return ScenarioDeclaration(sid, f"Label {sid}", f"existing-run:{sid}", batch, priority)


def unsafe_report(report, **fields):
    """Simulate corrupt upstream data that normal constructors would reject."""
    other = replace(report)
    for key, value in fields.items():
        object.__setattr__(other, key, value)
    return other


class ScenarioComparison(unittest.TestCase):
    def document(self, *scenarios):
        return compare_scenarios(list(scenarios)).as_dict()

    def codes(self, document):
        return [d["code"] for d in document["diagnostics"]]

    def assert_not_comparable(self, code, *scenarios):
        result = self.document(*scenarios)
        self.assertEqual(result["ordering_stability"], "NOT_COMPARABLE")
        self.assertIn(code, self.codes(result))
        self.assertIsNone(result["stable_top"])
        self.assertIsNone(result["eligibility_changed"])
        self.assertEqual(result["movements"], [])
        self.assertEqual(result["candidate_order"], [])
        self.assertIn("Ordering is not comparable", result["conclusion"])
        return result

    def test_stable_ordering_and_all_copied_fields(self):
        first, second = finished("first"), finished("second")
        result = self.document(declaration("first", first), declaration("second", second))
        self.assertEqual(result["ordering_stability"], "STABLE")
        self.assertFalse(result["eligibility_changed"])
        self.assertTrue(result["stable_top"])
        for scenario, (batch, priority) in zip(result["scenarios"], (first, second)):
            self.assertEqual(scenario["batch_report"], batch.as_dict())
            self.assertEqual(scenario["priority_report"], priority.as_dict())
        self.assertEqual(result["scenario_order"], ["first", "second"])
        self.assertEqual(result["candidate_order"], ["zebra", "alpha", "middle"])

    def test_unstable_ordering_and_changed_top(self):
        result = self.document(declaration("s1"), declaration("s2", tiers=(T3, T2, T1)))
        self.assertEqual(result["ordering_stability"], "UNSTABLE")
        self.assertFalse(result["stable_top"])
        self.assertFalse(result["eligibility_changed"])
        self.assertEqual(result["top_groups"], [
            {"scenario_id": "s1", "candidate_ids": ["zebra"]},
            {"scenario_id": "s2", "candidate_ids": ["middle"]}])

    def test_stable_top_tie_group_never_selects_a_winner(self):
        result = self.document(declaration("s1", tiers=(T1, T1, T3)),
                               declaration("s2", tiers=(T1, T1, T3)))
        self.assertTrue(result["stable_top"])
        self.assertEqual(result["top_groups"][0]["candidate_ids"], ["zebra", "alpha"])
        self.assertEqual([m["observations"][0]["rank"] for m in result["movements"]], [1, 1, 2])
        self.assertNotIn("winner", result)

    def test_changed_top_tie_membership_is_not_stable_top(self):
        result = self.document(declaration("s1", tiers=(T1, T1, T3)),
                               declaration("s2", tiers=(T1, T2, T3)))
        self.assertFalse(result["stable_top"])
        self.assertEqual(result["ordering_stability"], "UNSTABLE")
        self.assertEqual(result["movements"][0]["changes"][0]["kinds"], ["TIE_GROUP_CHANGED"])

    def test_stable_top_does_not_hide_changes_below_it(self):
        result = self.document(declaration("s1"), declaration("s2", tiers=(T1, T3, T2)))
        self.assertTrue(result["stable_top"])
        self.assertEqual(result["ordering_stability"], "UNSTABLE")

    def test_eligibility_changes_are_not_rank_zero(self):
        result = self.document(declaration("s1"), declaration("s2", excluded=("alpha",)), declaration("s3"))
        movement = result["movements"][1]
        self.assertTrue(result["eligibility_changed"])
        self.assertEqual(result["ordering_stability"], "UNSTABLE")
        self.assertEqual([c["kinds"] for c in movement["changes"]], [["BECAME_EXCLUDED"], ["BECAME_RANKED"]])
        observation = movement["observations"][1]
        self.assertIsNone(observation["rank"])
        self.assertIsNone(observation["geometry_tier"])
        self.assertEqual(observation["exclusion"]["state_status_reason"], "CHAIN_CLOSURE_VIOLATED")

    def test_dense_rank_change_can_occur_without_tier_change(self):
        result = self.document(declaration("s1"), declaration("s2", excluded=("alpha",)))
        movement = result["movements"][2]
        self.assertEqual(movement["changes"][0]["kinds"], ["RANK_CHANGED"])
        self.assertEqual([o["geometry_tier"] for o in movement["observations"]], [T3.value, T3.value])
        self.assertEqual([o["rank"] for o in movement["observations"]], [3, 2])

    def test_tier_change_can_leave_ordering_and_top_stable(self):
        result = self.document(declaration("s1", tiers=(T1, T1, T1)),
                               declaration("s2", tiers=(T2, T2, T2)))
        self.assertEqual(result["ordering_stability"], "STABLE")
        self.assertTrue(result["stable_top"])
        for movement in result["movements"]:
            self.assertEqual(movement["changes"][0]["kinds"], ["TIER_CHANGED"])

    def test_all_excluded_keeps_eligibility_changes_visible(self):
        result = self.document(declaration("s1"), declaration("s2", excluded=("zebra", "alpha", "middle")))
        self.assertEqual(result["ordering_stability"], "NOT_COMPARABLE")
        self.assertTrue(result["eligibility_changed"])
        self.assertIsNone(result["stable_top"])
        self.assertEqual(self.codes(result), ["ALL_EXCLUDED_SCENARIO"])
        self.assertEqual(result["diagnostics"][0]["scenario_position"], 2)
        self.assertEqual(len(result["movements"]), 3)
        self.assertIn("eligibility differs", result["conclusion"])
        self.assertEqual(result["top_groups"][1]["candidate_ids"], [])

    def test_every_scenario_all_excluded_is_not_stable_ranking(self):
        both = [declaration(s, excluded=("zebra", "alpha", "middle")) for s in ("s1", "s2")]
        result = self.document(*both)
        self.assertEqual(result["ordering_stability"], "NOT_COMPARABLE")
        self.assertFalse(result["eligibility_changed"])
        self.assertEqual(self.codes(result), ["ALL_EXCLUDED_SCENARIO", "ALL_EXCLUDED_SCENARIO"])
        self.assertEqual(result["movements"][0]["changes"][0]["kinds"], ["REMAINED_EXCLUDED"])

    def test_persistent_exclusion_details_are_preserved(self):
        batch, priority = finished("s2", excluded=("alpha",))
        entry = batch.entries[1]
        ledger = replace(entry.ledger, rows=tuple(replace(r, state_status_reason="other exact reason") for r in entry.ledger.rows))
        batch = replace(batch, entries=(batch.entries[0], replace(entry, ledger=ledger), batch.entries[2]))
        priority = replace(priority, excluded=(replace(priority.excluded[0], state_status_reason="other exact reason"),))
        result = self.document(declaration("s1", excluded=("alpha",)), declaration("s2", (batch, priority)))
        self.assertEqual(result["movements"][1]["changes"][0]["kinds"], ["REMAINED_EXCLUDED", "EXCLUSION_DETAILS_CHANGED"])
        self.assertFalse(result["eligibility_changed"])

    def test_missing_scenario_identity(self):
        for missing in (None, "", "   "):
            with self.subTest(value=missing):
                batch, priority = finished("s2")
                self.assert_not_comparable("SCENARIO_ID_MISSING", declaration("s1"),
                    ScenarioDeclaration(missing, "declared label", "existing run", batch, priority))

    def test_duplicate_scenario_identity(self):
        result = self.assert_not_comparable("SCENARIO_ID_DUPLICATE", declaration("s1"), declaration("s1"))
        self.assertEqual(result["scenario_order"], ["s1", "s1"])
        self.assertEqual(len(result["scenarios"]), 2)

    def test_missing_label_and_run_reference(self):
        batch, priority = finished("s2")
        for field, code in (("label", "SCENARIO_LABEL_MISSING"), ("evaluation_run_ref", "EVALUATION_RUN_REF_MISSING")):
            with self.subTest(field=field):
                kwargs = dict(scenario_id="s2", label="label", evaluation_run_ref="run", batch_report=batch, priority_report=priority)
                kwargs[field] = None
                self.assert_not_comparable(code, declaration("s1"), ScenarioDeclaration(**kwargs))

    def test_candidate_universe_mismatch(self):
        result = self.assert_not_comparable("CANDIDATE_UNIVERSE_MISMATCH", declaration("s1"),
                                           declaration("s2", order=("zebra", "alpha", "extra")))
        self.assertIn("middle", result["diagnostics"][0]["detail"])
        self.assertIn("extra", result["diagnostics"][0]["detail"])

    def test_candidate_order_mismatch_no_silent_sort(self):
        self.assert_not_comparable("CANDIDATE_ORDER_MISMATCH", declaration("s1"),
                                   declaration("s2", order=("alpha", "zebra", "middle")))

    def test_slot_binding_mismatch_even_for_excluded_candidate(self):
        for excluded in ((), ("zebra",)):
            with self.subTest(excluded=excluded):
                batch, priority = finished("s2", excluded=excluded)
                entry = batch.entries[0]
                entry = replace(entry, slot_binding_hash="changed-binding",
                                ledger=replace(entry.ledger, slot_binding_hash="changed-binding"))
                batch = replace(batch, entries=(entry, *batch.entries[1:]))
                if excluded:
                    priority = replace(priority, excluded=(replace(priority.excluded[0], slot_binding_hash="changed-binding"),))
                else:
                    group = priority.groups[0]
                    priority = replace(priority, groups=(replace(group, members=(replace(group.members[0], slot_binding_hash="changed-binding"),)), *priority.groups[1:]))
                self.assert_not_comparable("SLOT_BINDING_MISMATCH", declaration("s1", excluded=excluded), declaration("s2", (batch, priority)))

    def test_incompatible_report_types_and_malformed_fields(self):
        batch, priority = finished("s2")
        for invalid in (None, priority.as_dict(), unsafe_report(priority, groups=(None,)),
                        unsafe_report(priority, candidate_order=42)):
            with self.subTest(value=type(invalid).__name__):
                self.assert_not_comparable("INCOMPATIBLE_REPORT_SHAPE", declaration("s1"),
                                           ScenarioDeclaration("s2", "label", "run", batch, invalid))
        self.assert_not_comparable("INCOMPATIBLE_REPORT_SHAPE", declaration("s1"), None)

    def test_incomplete_coverage_and_duplicates(self):
        batch, priority = finished("s2")
        corrupt = (unsafe_report(priority, groups=priority.groups[:-1]),
                   unsafe_report(priority, candidate_order=("zebra", "alpha", "alpha")))
        for malformed in corrupt:
            with self.subTest(report=malformed):
                self.assert_not_comparable("INCOMPLETE_CANDIDATE_COVERAGE", declaration("s1"), declaration("s2", (batch, malformed)))

    def test_insufficient_scenario_count(self):
        self.assert_not_comparable("INSUFFICIENT_SCENARIO_COUNT")
        self.assert_not_comparable("INSUFFICIENT_SCENARIO_COUNT", declaration("s1"))

    def test_empty_candidate_universe(self):
        self.assert_not_comparable("EMPTY_CANDIDATE_UNIVERSE",
            declaration("s1", order=(), tiers=()), declaration("s2", order=(), tiers=()))

    def test_conflicting_context_hashes(self):
        batch, priority = finished("s2")
        entry = batch.entries[1]
        batch = replace(batch, entries=(batch.entries[0], replace(entry, ledger=replace(entry.ledger, context_hash="another context")), batch.entries[2]))
        self.assert_not_comparable("CONTEXT_ASSOCIATION_AMBIGUOUS", declaration("s1"), declaration("s2", (batch, priority)))

    def test_absent_context_hash_is_not_inferred(self):
        result = self.document(declaration("s1", context=False), declaration("s2", context=False))
        self.assertEqual(result["ordering_stability"], "STABLE")
        self.assertEqual(result["scenarios"][1]["evaluation_run_ref"], "existing-run:s2")
        self.assertIsNone(result["scenarios"][1]["batch_report"]["entries"][0]["ledger"]["context_hash"])
        self.assertIn("caller-supplied run links", "\n".join(render_lines(compare_scenarios([declaration("s1", context=False), declaration("s2", context=False)]))))

    def test_batch_report_identity_and_shared_field_mismatches(self):
        batch, priority = finished("s2")
        entry = batch.entries[0]
        for change in ({"state_result_id": "different result"}, {"certificate_present": False},
                       {"slot_binding_hash": "different binding"}):
            with self.subTest(change=change):
                altered = replace(batch, entries=(replace(entry, ledger=replace(entry.ledger, **change)), *batch.entries[1:]))
                self.assert_not_comparable("BATCH_REPORT_MISMATCH", declaration("s1"), declaration("s2", (altered, priority)))
        altered = replace(batch, entries=tuple(reversed(batch.entries)))
        self.assert_not_comparable("BATCH_REPORT_MISMATCH", declaration("s1"), declaration("s2", (altered, priority)))

    def test_tier_basis_mismatch_is_not_reclassified(self):
        batch, priority = finished("s2")
        group = priority.groups[0]
        member = group.members[0]
        member = replace(member, tier_basis=tuple(replace(row, node_presence=NodePresence.ABSENT_NOT_SUPPLIED) for row in member.tier_basis))
        altered = replace(priority, groups=(replace(group, members=(member,)), *priority.groups[1:]))
        self.assert_not_comparable("BATCH_REPORT_MISMATCH", declaration("s1"), declaration("s2", (batch, altered)))

    def test_group_and_exclusion_order_incompatibility(self):
        batch, priority = finished("s2", tiers=(T1, T1, T1))
        reversed_group = replace(priority.groups[0], members=tuple(reversed(priority.groups[0].members)))
        self.assert_not_comparable("INCOMPATIBLE_REPORT_SHAPE", declaration("s1"),
            declaration("s2", (batch, replace(priority, groups=(reversed_group,)))))
        batch, priority = finished("s2", excluded=("zebra", "alpha"))
        self.assert_not_comparable("INCOMPATIBLE_REPORT_SHAPE", declaration("s1"),
            declaration("s2", (batch, replace(priority, excluded=tuple(reversed(priority.excluded))))))

    def test_refusal_without_ledger_is_visible(self):
        pairs = []
        for sid in ("s1", "s2"):
            refusal = DeclarationRefusal("refused", RefusalStage.SLOT_BINDING, "ValueError", "exact refusal detail")
            batch = CandidateBatchReport((CandidateEntry("refused", "existing binding", EntryKind.DECLARATION_REFUSED, None, refusal),))
            priority = CandidatePriorityReport(("refused",), (), (ExcludedEntry("refused", "existing binding", IneligibilityReason.DECLARATION_REFUSED,
                None, None, (), refusal.stage.value, refusal.error_class, refusal.detail),))
            pairs.append(declaration(sid, (batch, priority)))
        result = self.document(*pairs)
        self.assertEqual(self.codes(result), ["ALL_EXCLUDED_SCENARIO", "ALL_EXCLUDED_SCENARIO"])
        self.assertEqual(result["movements"][0]["observations"][1]["exclusion"]["refusal_detail"], "exact refusal detail")

    def test_evidence_is_inert_and_preserved_verbatim(self):
        record = StructureEvidenceRecord("af3-red", "af3_native_v1", "existing-artifact", "existing-sha",
            "candidate", True, "completed", "passed_with_nonfatal_observations",
            ("af3red_execution_declaration_missing", "bias_sigma_unknown", "bias_weight_unknown"))
        absent = self.document(declaration("s1"), declaration("s2"))
        supplied = self.document(declaration("s1", evidence=record), declaration("s2", evidence=record))
        for key in ("movements", "ordering_stability", "eligibility_changed", "stable_top", "top_groups", "conclusion"):
            self.assertEqual(absent[key], supplied[key])
        member = supplied["scenarios"][0]["priority_report"]["groups"][0]["members"][0]
        self.assertEqual(member["evidence"], record.as_dict())
        self.assertEqual(member["evidence_coverage"], "CANDIDATE")
        self.assertEqual(member["evidence"]["source_status"], "candidate")

    def test_deterministic_rendering_and_required_nonclaims(self):
        scenarios = [declaration("last alphabetically"), declaration("first alphabetically", excluded=("alpha",))]
        report = compare_scenarios(scenarios)
        text = "\n".join(render_lines(report))
        self.assertTrue(text.startswith(PRIORITY_NON_CLAIM + "\n\n" + PRIORITY_DISPLAY_DISCLAIMER))
        self.assertEqual(render_lines(report), render_lines(compare_scenarios(scenarios)))
        self.assertEqual(report.as_dict(), compare_scenarios(scenarios).as_dict())
        self.assertEqual(sum(line.startswith("Candidate |") for line in render_lines(report)), 1)
        self.assertIn("EXCLUDED · STATE_NOT_VALID", text)
        self.assertIn("Movement/eligibility", text)

    def test_inputs_and_stored_behavior_are_immutable(self):
        batch, priority = finished("s1")
        original = (batch.to_json_bytes(), priority.to_json_bytes())
        declaration_one = declaration("s1", (batch, priority))
        scenarios = [declaration_one, declaration("s2")]
        report = compare_scenarios(scenarios)
        expected = report.as_dict()
        self.assertEqual((batch.to_json_bytes(), priority.to_json_bytes()), original)
        with self.assertRaises(FrozenInstanceError):
            declaration_one.scenario_id = "changed"
        with self.assertRaises(FrozenInstanceError):
            report._document = b"{}"
        scenarios.clear()
        report.as_dict()["scenarios"].clear()
        declaration_one.as_dict()["priority_report"]["groups"].clear()
        # Even an explicit bypass of an upstream frozen record cannot alter a snapshot.
        object.__setattr__(priority, "groups", [])
        self.assertEqual(report.as_dict(), expected)
        self.assertEqual(declaration_one.as_dict()["priority_report"], expected["scenarios"][0]["priority_report"])

    def test_sequence_and_public_argument_types_are_explicit(self):
        for value in ({}, iter(()), None):
            with self.assertRaises(TypeError):
                compare_scenarios(value)
        with self.assertRaises(TypeError):
            render_lines({})
        with self.assertRaises(TypeError):
            ScenarioComparisonReport({})
        with self.assertRaises(TypeError):
            ScenarioDeclaration([], "label", "ref", *finished("s1"))

    def test_no_evaluation_hash_or_io_calls(self):
        batch, priority = finished("s1")
        from gotne import cassette_closure, cassette_node, cassette_slots, cassette_slot_ledger, cassette_state, identity
        with ExitStack() as stack:
            for module, name in (
                (batch_module, "evaluate_candidate_batch"), (priority_module, "evaluate_candidate_priority"),
                (priority_module, "classify_evidence"), (priority_module, "geometry_tier"),
                (priority_module, "ineligibility_reason"), (cassette_closure, "evaluate_state"),
                (cassette_node, "evaluate_node"), (cassette_state, "issue_state_certificate"),
                (cassette_slots, "slot_binding_hash"), (cassette_slots, "validate_slot_binding"),
                (cassette_slot_ledger, "build_slot_ledger"), (identity, "_digest"),
                (builtins, "open"), (socket, "socket"),
            ):
                stack.enter_context(patch.object(module, name, side_effect=AssertionError(f"forbidden: {name}")))
            first = declaration("s1", (batch, priority))
            second = declaration("s2", (batch, priority))
            self.assertEqual(compare_scenarios([first, second]).ordering_stability, "STABLE")
            render_lines(compare_scenarios([first, second]))

    def test_static_import_and_call_boundary(self):
        tree = ast.parse(pathlib.Path(comparison.__file__).read_text())
        allowed = {"__future__", "json", "dataclasses", "typing", "cassette_candidate_batch", "cassette_candidate_priority"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(all(alias.name in allowed for alias in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertIn(node.module, allowed)
            elif isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                self.assertNotIn(name, {"open", "read_text", "read_bytes", "write_text", "write_bytes", "sorted",
                    "sort", "evaluate_candidate_batch", "evaluate_candidate_priority", "evaluate_state", "evaluate_node",
                    "classify_evidence", "geometry_tier", "ineligibility_reason", "slot_binding_hash", "hash", "sha256"})

    def test_real_finished_public_path_is_read_without_reevaluation(self):
        # Evaluation is fixture preparation, outside the comparison layer.
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from test_phase2_cassette_candidate_priority import T1_D, VETOED_D
        batch = batch_module.evaluate_candidate_batch([T1_D("ranked"), VETOED_D("excluded")])
        priority = priority_module.evaluate_candidate_priority(batch, evidence={}, providers=("af3-red",))
        before = (batch.to_json_bytes(), priority.to_json_bytes())
        with patch.object(batch_module, "evaluate_candidate_batch", side_effect=AssertionError("reevaluation")), \
             patch.object(priority_module, "evaluate_candidate_priority", side_effect=AssertionError("reevaluation")):
            report = compare_scenarios([declaration("observed-run-a", (batch, priority)),
                                        declaration("observed-run-b", (batch, priority))])
        self.assertEqual(report.ordering_stability, "STABLE")
        self.assertEqual((batch.to_json_bytes(), priority.to_json_bytes()), before)
        self.assertEqual(report.as_dict()["movements"][1]["observations"][0]["exclusion"]["ineligibility_reason"], "SLOT_VETOED")


if __name__ == "__main__":
    unittest.main()
