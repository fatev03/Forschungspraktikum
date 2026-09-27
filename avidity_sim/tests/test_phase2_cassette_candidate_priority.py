"""Phase 2 candidate priority: cassette_candidate_priority.

Covers the caller-side consumer only: the eligibility gate and its explicit
non-gate for evidence state, the geometry-tier function, the coverage
vocabulary, tie-group ordering, completeness against candidate_order,
immutability, canonical serialization and the import boundary.

Every kernel outcome comes from the real kernel over the budget fixture. The
fixture declares a root anchor position, which the shared budget fixture leaves
MISSING; without it the first ENGAGED module's node gate reads an invalid input
and every candidate would be SLOT_VETOED, so no eligible tier would exist:

  rooted cfg, all slots ENGAGED       VALID          eligible, T1
  rooted cfg, all slots UNENGAGED     VALID          eligible, T3
  rooted cfg, a subset of node results VALID         eligible, T2
  unrooted cfg, all slots ENGAGED     VALID          SLOT_VETOED (D1 node)
  rooted cfg, FAR sites               UNREACHABLE    STATE_NOT_VALID
  rooted cfg, FIXED_RIGID             NOT_EVALUATED  STATE_NOT_VALID
  rooted cfg, ORIENTATION_MARGINALIZED DEGENERATE    STATE_NOT_VALID
  modules permuted against cassette order            DECLARATION_REFUSED

T2, CERTIFICATE_ABSENT, SLOT_UNEVALUABLE and LEDGER_ABSENT are not producible by
evaluate_candidate_batch, which supplies a node result for every ENGAGED slot of
a certified VALID state and always carries a certificate and a ledger. They are
reached by arranging finished kernel results into a ledger the slot-ledger
contract explicitly permits, and are marked ARRANGED below. SLOT_UNEVALUABLE in
particular cannot be produced by any kernel combination in this fixture family:
a DEGENERATE state is in UNKNOWN_SET and propagates no NODE result, so no
unevaluable node result can coexist with a VALID state.

Run: python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError, replace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from gotne import cassette_candidate_priority as priority  # noqa: E402
from gotne.cassette_candidate_batch import (  # noqa: E402
    CandidateDeclaration,
    CandidateEntry,
    EntryKind,
    evaluate_candidate_batch,
)
from gotne.cassette_candidate_priority import (  # noqa: E402
    AF3_RED_PROVIDER,
    KNOWN_PROVIDERS,
    PRIORITY_DISPLAY_DISCLAIMER,
    PRIORITY_DOCUMENT_TYPE,
    PRIORITY_NON_CLAIM,
    TIER_ORDER,
    CandidatePriorityReport,
    EvidenceCoverage,
    GeometryTier,
    IneligibilityReason,
    PriorityGroup,
    StructureEvidenceRecord,
    classify_evidence,
    evaluate_candidate_priority,
    geometry_tier,
    ineligibility_reason,
    render_lines,
)
from gotne.cassette_closure import evaluate_state  # noqa: E402
from gotne.cassette_node import evaluate_node  # noqa: E402
from gotne.cassette_schema import (  # noqa: E402
    EngagedPoseResolution,
    EngagementOrderPolicy,
    JunctionModel,
)
from gotne.cassette_slot_ledger import FailureClass, NodePresence, build_slot_ledger  # noqa: E402
from gotne.cassette_slots import (  # noqa: E402
    SLOT_IDS,
    project_engagement_state,
    slot_binding_hash,
)
from gotne.cassette_state import EngagementLabel, issue_state_certificate  # noqa: E402
from gotne.status import Status  # noqa: E402
from test_cassette_topology import base_policy  # noqa: E402
from test_phase2_cassette_budget import budget_cfg  # noqa: E402
from test_phase2_cassette_candidate_batch import FAR, binding, context  # noqa: E402

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT_DIR / "gotne"
MODULE = "cassette_candidate_priority"
PHASE45 = ("composite_density", "so3_grids", "pose_marginalization", "shell_bounds", "intervals")
CHAIN_MODULES = ("cassette_frames", "cassette_budget", "cassette_closure", "cassette_node")
EXTERNAL_INTAKE = (
    "structure_audit",
    "demo_external_reference",
    "af3_red_adapter",
    "af3_native_bridge",
    "declared_geometry_input",
    "f01_coordinate_admission",
    "structures",
)
IO_MODULES = ("os", "io", "pathlib", "subprocess", "socket", "urllib", "shutil", "tempfile")

#: The shared budget fixture leaves the root anchor position MISSING; declaring
#: it is what makes an eligible tier reachable at all.
ROOT_POSITION = (0.0, 0.0, 0.0)

ENGAGED = EngagementLabel.ENGAGED

#: Verbatim from the notebook's optional external-reference cell. String literals
#: only: nothing here opens an artifact, resolves a reference or hashes a file.
NOTEBOOK_ARTIFACT_ID = "5b4690580b352de100439cc68cb460847c4f4729c3b9151ca6ba739f8ce2aad7"
NOTEBOOK_SHA256 = "58f38cc8f279fb827851c27ff735bdc4b310ca22276a6a2cf8ebbb2414a882ed"
NOTEBOOK_REASONS = (
    "af3red_execution_declaration_missing",
    "bias_sigma_unknown",
    "bias_weight_unknown",
)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
def rooted_cfg(policy=None):
    """The budget fixture with the root anchor position declared."""
    cfg = budget_cfg(policy)
    return replace(cfg, anchors=tuple(replace(a, position=ROOT_POSITION) for a in cfg.anchors))


def declaration(candidate_id, *, b=None, policy=None, sites=None, cfg=None):
    cfg = rooted_cfg(policy) if cfg is None else cfg
    return CandidateDeclaration(
        candidate_id=candidate_id,
        binding=b if b is not None else binding(),
        cfg=cfg,
        policy=cfg.policy,
        context=context(sites),
    )


T1_D = lambda cid="t1": declaration(cid)  # noqa: E731
T3_D = lambda cid="t3": declaration(cid, b=binding(t1=None, t2=None, t3=None))  # noqa: E731
VETOED_D = lambda cid="vetoed": declaration(cid, cfg=budget_cfg())  # noqa: E731
UNREACHABLE_D = lambda cid="unreachable": declaration(cid, sites=FAR)  # noqa: E731
UNSUPPORTED_D = lambda cid="unsupported": declaration(  # noqa: E731
    cid, policy=base_policy(junction_model=JunctionModel.FIXED_RIGID)
)
DEGENERATE_D = lambda cid="degenerate": declaration(  # noqa: E731
    cid, policy=base_policy(engaged_pose_resolution=EngagedPoseResolution.ORIENTATION_MARGINALIZED)
)
INFEASIBLE_D = lambda cid="infeasible": declaration(  # noqa: E731
    cid,
    b=binding(t2=None),
    policy=base_policy(engagement_order_policy=EngagementOrderPolicy.STRICT_PROXIMAL_TO_DISTAL),
)
REFUSED_D = lambda cid="refused": declaration(  # noqa: E731
    cid, b=binding(modules=("D3", "D2", "D1"), t1="t3", t3="t1")
)


def priority_of(declarations, *, evidence=None, providers=KNOWN_PROVIDERS):
    """One priority report over a real batch. Evidence and providers stay explicit."""
    return evaluate_candidate_priority(
        evaluate_candidate_batch(list(declarations)),
        evidence={} if evidence is None else evidence,
        providers=providers,
    )


def kernel_results(b=None, *, cfg=None, sites=None, nodes=None):
    """(cfg, state_result, node_results, certificate) from the real kernel."""
    b = binding() if b is None else b
    cfg = rooted_cfg() if cfg is None else cfg
    ctx = context(sites)
    state = project_engagement_state(b)
    state_result = evaluate_state(state, cfg, cfg.policy, ctx)
    certificate = issue_state_certificate(state_result, state, cfg, cfg.policy, ctx)
    engaged = tuple(a.module_id for a in b.ordered_assignments() if a.label is ENGAGED)
    chosen = engaged if nodes is None else nodes
    return (
        cfg,
        state_result,
        tuple(evaluate_node(m, certificate, cfg, cfg.policy) for m in chosen),
        certificate,
    )


def arranged_entry(candidate_id, *, nodes=None, certificate=True, row_class=None):
    """ARRANGED: finished kernel results placed in a ledger the ledger contract
    permits but evaluate_candidate_batch never emits."""
    b = binding()
    cfg, state_result, node_results, cert = kernel_results(b, nodes=nodes)
    ledger = build_slot_ledger(
        b, cfg, state_result, node_results, cert if certificate else None
    )
    if row_class is not None:
        rows = (replace(ledger.rows[0], failure_class=row_class),) + ledger.rows[1:]
        ledger = replace(ledger, rows=rows)
    return CandidateEntry(
        candidate_id, slot_binding_hash(b), EntryKind.EVALUATED, ledger, None
    )


def evidence_record(**overrides):
    """The notebook's supplied record, with explicit per-field overrides."""
    fields = dict(
        provider=AF3_RED_PROVIDER,
        profile="af3_native_v1",
        artifact_id=NOTEBOOK_ARTIFACT_ID,
        observed_sha256=NOTEBOOK_SHA256,
        source_status="candidate",
        read_completed=True,
        execution_state="completed",
        validation_status="passed_with_nonfatal_observations",
        non_admission_reasons=NOTEBOOK_REASONS,
    )
    fields.update(overrides)
    return StructureEvidenceRecord(**fields)


# --------------------------------------------------------------------------
# Non-claim
# --------------------------------------------------------------------------
class NonClaim(unittest.TestCase):
    def test_the_statement_names_every_prohibited_claim(self):
        for term in (
            "receptor biology",
            "abundance",
            "accessibility",
            "expression",
            "membrane context",
            "glycosylation",
            "dynamics",
            "affinity",
            "KD",
            "kinetics",
            "occupancy",
            "avidity magnitude",
            "binding probability",
            "efficacy",
            "safety",
            "specificity",
            "experimental success",
            "not ground truth",
            "20.7.3 N0",
        ):
            with self.subTest(term=term):
                self.assertIn(term, PRIORITY_NON_CLAIM)

    def test_the_document_carries_the_statement_verbatim(self):
        report = priority_of([T1_D()])
        self.assertEqual(report.as_dict()["non_claim"], PRIORITY_NON_CLAIM)
        self.assertEqual(report.non_claim, PRIORITY_NON_CLAIM)
        self.assertEqual(json.loads(report.to_json_bytes())["non_claim"], PRIORITY_NON_CLAIM)

    def test_rendering_puts_the_statement_and_disclaimer_before_the_first_group(self):
        report = priority_of([T1_D()])
        lines = render_lines(report)
        first_group = next(i for i, line in enumerate(lines) if line.startswith("rank "))
        self.assertEqual(lines[: len(PRIORITY_NON_CLAIM.split("\n"))], PRIORITY_NON_CLAIM.split("\n"))
        self.assertIn(PRIORITY_DISPLAY_DISCLAIMER, lines[:first_group])
        self.assertIn("caller sequence, not precedence", PRIORITY_DISPLAY_DISCLAIMER)

    def test_rendering_refuses_a_non_report(self):
        for value in (None, {}, priority_of([T1_D()]).as_dict()):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(TypeError):
                    render_lines(value)


# --------------------------------------------------------------------------
# The eligibility gate
# --------------------------------------------------------------------------
class Gate(unittest.TestCase):
    def test_each_reason_is_reached_and_named(self):
        expected = {
            "refused": IneligibilityReason.DECLARATION_REFUSED,
            "vetoed": IneligibilityReason.SLOT_VETOED,
            "unreachable": IneligibilityReason.STATE_NOT_VALID,
            "unsupported": IneligibilityReason.STATE_NOT_VALID,
            "degenerate": IneligibilityReason.STATE_NOT_VALID,
            "infeasible": IneligibilityReason.STATE_NOT_VALID,
        }
        report = evaluate_candidate_batch(
            [
                REFUSED_D(),
                VETOED_D(),
                UNREACHABLE_D(),
                UNSUPPORTED_D(),
                DEGENERATE_D(),
                INFEASIBLE_D(),
            ]
        )
        for entry in report.entries:
            with self.subTest(candidate=entry.candidate_id):
                self.assertIs(ineligibility_reason(entry), expected[entry.candidate_id])

    def test_arranged_certificate_absent_and_slot_unevaluable(self):
        self.assertIs(
            ineligibility_reason(arranged_entry("no-cert", certificate=False)),
            IneligibilityReason.CERTIFICATE_ABSENT,
        )
        self.assertIs(
            ineligibility_reason(
                arranged_entry("unevaluable", row_class=FailureClass.UNEVALUABLE)
            ),
            IneligibilityReason.SLOT_UNEVALUABLE,
        )

    def test_a_ledger_absent_entry_is_refused_not_assumed(self):
        # CandidateEntry's own invariant makes this unreachable; the gate stays
        # total if that invariant ever widens.
        entry = arranged_entry("widened")
        object.__setattr__(entry, "ledger", None)
        self.assertIs(ineligibility_reason(entry), IneligibilityReason.LEDGER_ABSENT)

    def test_an_unmapped_row_class_raises_rather_than_folding(self):
        entry = arranged_entry("contract", row_class=FailureClass.CONTRACT_INVALID)
        with self.assertRaises(ValueError) as caught:
            ineligibility_reason(entry)
        self.assertIn("not folded into a neighbouring class", str(caught.exception))

    def test_state_not_valid_precedes_certificate_absent(self):
        entry = next(iter(evaluate_candidate_batch([UNREACHABLE_D()]).entries))
        self.assertFalse(entry.ledger.certificate_present)
        self.assertIs(ineligibility_reason(entry), IneligibilityReason.STATE_NOT_VALID)

    def test_the_gate_is_total_and_takes_only_a_candidate_entry(self):
        with self.assertRaises(TypeError):
            ineligibility_reason(evaluate_candidate_batch([T1_D()]))
        self.assertIsNone(ineligibility_reason(evaluate_candidate_batch([T1_D()]).entries[0]))

    def test_evidence_state_is_never_an_ineligibility_reason(self):
        names = {reason.value for reason in IneligibilityReason}
        for forbidden in ("EVIDENCE", "COVERAGE", "ARTIFACT", "PROVIDER", "AF3"):
            self.assertFalse(
                any(forbidden in name for name in names), f"{forbidden} gates eligibility"
            )

    def test_every_coverage_value_leaves_eligibility_unchanged(self):
        for record in (
            None,
            evidence_record(),
            evidence_record(source_status="rejected"),
            evidence_record(source_status="admitted"),
            evidence_record(source_status="whatever"),
            "not a record",
        ):
            with self.subTest(record=type(record).__name__):
                report = priority_of([T1_D("c")], evidence={"c": record})
                self.assertEqual(report.excluded, ())
                self.assertEqual(len(report.groups), 1)
                self.assertEqual(report.groups[0].members[0].candidate_id, "c")


# --------------------------------------------------------------------------
# The geometry tier
# --------------------------------------------------------------------------
class Tiers(unittest.TestCase):
    def test_t1_from_the_real_batch(self):
        entry = evaluate_candidate_batch([T1_D()]).entries[0]
        rows = entry.ledger.rows
        self.assertTrue(all(r.node_presence is NodePresence.PRESENT for r in rows))
        self.assertIs(geometry_tier(entry.ledger), GeometryTier.T1_ENGAGED_SLOTS_FULLY_RESOLVED)

    def test_t3_when_no_slot_is_engaged(self):
        entry = evaluate_candidate_batch([T3_D()]).entries[0]
        rows = entry.ledger.rows
        self.assertTrue(all(r.label is EngagementLabel.UNENGAGED for r in rows))
        self.assertTrue(all(r.node_presence is NodePresence.ABSENT_UNENGAGED for r in rows))
        self.assertIs(geometry_tier(entry.ledger), GeometryTier.T3_NO_RESOLVED_ENGAGED_SLOT)

    def test_arranged_t2_and_t3_over_absent_not_supplied(self):
        for nodes, tier in (
            (("D1",), GeometryTier.T2_ENGAGED_SLOTS_PARTIALLY_RESOLVED),
            (("D1", "D2"), GeometryTier.T2_ENGAGED_SLOTS_PARTIALLY_RESOLVED),
            ((), GeometryTier.T3_NO_RESOLVED_ENGAGED_SLOT),
        ):
            with self.subTest(nodes=nodes):
                entry = arranged_entry("arranged", nodes=nodes)
                presences = {r.node_presence for r in entry.ledger.rows}
                if nodes != ("D1", "D2", "D3"):
                    self.assertIn(NodePresence.ABSENT_NOT_SUPPLIED, presences)
                self.assertIsNone(ineligibility_reason(entry))
                self.assertIs(geometry_tier(entry.ledger), tier)

    def test_tier_order_is_the_closed_enumeration(self):
        self.assertEqual(TIER_ORDER, tuple(GeometryTier))
        self.assertEqual(len(set(TIER_ORDER)), 3)

    def test_the_tier_carries_no_number_and_takes_only_a_ledger(self):
        for tier in GeometryTier:
            self.assertNotIn("=", tier.value)
        with self.assertRaises(TypeError):
            geometry_tier(evaluate_candidate_batch([T1_D()]).entries[0])

    def test_tier_basis_names_every_slot_without_a_count(self):
        member = priority_of([T1_D()]).groups[0].members[0]
        self.assertEqual([row.slot for row in member.tier_basis], list(SLOT_IDS))
        serialized = member.as_dict()["tier_basis"]
        self.assertEqual(
            [set(row) for row in serialized],
            [{"slot", "label", "node_presence", "failure_class"}] * 3,
        )


# --------------------------------------------------------------------------
# Evidence coverage
# --------------------------------------------------------------------------
class Coverage(unittest.TestCase):
    def test_the_vocabulary_is_closed_and_excludes_supported(self):
        self.assertEqual(
            {c.value for c in EvidenceCoverage},
            {"ABSENT", "CANDIDATE", "ADMITTED_MAPPING_PREP_ONLY", "REJECTED", "UNSUPPORTED"},
        )
        self.assertNotIn("SUPPORTED", {c.value for c in EvidenceCoverage})

    def test_source_status_is_the_only_coverage_input(self):
        cases = {
            "candidate": EvidenceCoverage.CANDIDATE,
            "admitted": EvidenceCoverage.ADMITTED_MAPPING_PREP_ONLY,
            "rejected": EvidenceCoverage.REJECTED,
            "ADMITTED": EvidenceCoverage.UNSUPPORTED,
            "": EvidenceCoverage.UNSUPPORTED,
            "provisional": EvidenceCoverage.UNSUPPORTED,
        }
        for status, coverage in cases.items():
            with self.subTest(source_status=status):
                self.assertIs(
                    classify_evidence(evidence_record(source_status=status), KNOWN_PROVIDERS),
                    coverage,
                )

    def test_display_only_fields_never_change_coverage(self):
        for overrides in (
            {"read_completed": False},
            {"execution_state": "aborted"},
            {"validation_status": "failed"},
            {"profile": "strict"},
            {"non_admission_reasons": ()},
            {"artifact_id": "x", "observed_sha256": "y"},
        ):
            with self.subTest(**overrides):
                self.assertIs(
                    classify_evidence(evidence_record(**overrides), KNOWN_PROVIDERS),
                    EvidenceCoverage.CANDIDATE,
                )

    def test_absent_and_malformed_records(self):
        self.assertIs(classify_evidence(None, KNOWN_PROVIDERS), EvidenceCoverage.ABSENT)
        for value in ("not a record", 7, {"provider": AF3_RED_PROVIDER}, object()):
            with self.subTest(value=type(value).__name__):
                self.assertIs(
                    classify_evidence(value, KNOWN_PROVIDERS), EvidenceCoverage.UNSUPPORTED
                )
        self.assertIs(
            classify_evidence(evidence_record(provider="boltz"), KNOWN_PROVIDERS),
            EvidenceCoverage.UNSUPPORTED,
        )
        self.assertIs(
            classify_evidence(evidence_record(provider="boltz"), ("boltz",)),
            EvidenceCoverage.CANDIDATE,
        )

    def test_the_provider_allowlist_has_no_implicit_default(self):
        batch = evaluate_candidate_batch([T1_D()])
        with self.assertRaises(TypeError):
            evaluate_candidate_priority(batch, evidence={})
        for bad in ((), []):
            with self.assertRaises(ValueError):
                evaluate_candidate_priority(batch, evidence={}, providers=bad)
        for bad in ("af3-red", (None,), (7,)):
            with self.assertRaises(TypeError):
                evaluate_candidate_priority(batch, evidence={}, providers=bad)
        with self.assertRaises(ValueError):
            evaluate_candidate_priority(batch, evidence={}, providers=("",))

    def test_the_record_type_checks_its_own_fields(self):
        with self.assertRaises(TypeError):
            evidence_record(provider=None)
        with self.assertRaises(TypeError):
            evidence_record(read_completed="true")
        with self.assertRaises(TypeError):
            evidence_record(non_admission_reasons=(1,))
        with self.assertRaises(TypeError):
            evidence_record(non_admission_reasons="reason")

    def test_non_admission_reasons_are_carried_verbatim_and_in_order(self):
        report = priority_of([T1_D("c")], evidence={"c": evidence_record()})
        member = report.groups[0].members[0]
        self.assertEqual(member.evidence.non_admission_reasons, NOTEBOOK_REASONS)
        serialized = json.loads(report.to_json_bytes())
        evidence = serialized["groups"][0]["members"][0]["evidence"]
        self.assertEqual(evidence["non_admission_reasons"], list(NOTEBOOK_REASONS))
        self.assertEqual(evidence["artifact_id"], NOTEBOOK_ARTIFACT_ID)
        self.assertEqual(evidence["observed_sha256"], NOTEBOOK_SHA256)
        self.assertEqual(evidence["source_status"], "candidate")

    def test_a_malformed_record_is_reported_but_not_carried(self):
        report = priority_of([T1_D("c")], evidence={"c": "not a record"})
        member = report.groups[0].members[0]
        self.assertIs(member.evidence_coverage, EvidenceCoverage.UNSUPPORTED)
        self.assertIsNone(member.evidence, "an unusable record is never presented as one")

    def test_evidence_naming_an_unknown_candidate_raises_before_any_output(self):
        batch = evaluate_candidate_batch([T1_D("c")])
        with self.assertRaises(ValueError) as caught:
            evaluate_candidate_priority(
                batch, evidence={"ghost": evidence_record()}, providers=KNOWN_PROVIDERS
            )
        self.assertIn("ghost", str(caught.exception))
        with self.assertRaises(TypeError):
            evaluate_candidate_priority(batch, evidence=[], providers=KNOWN_PROVIDERS)
        with self.assertRaises(TypeError):
            evaluate_candidate_priority(
                batch.entries, evidence={}, providers=KNOWN_PROVIDERS
            )


# --------------------------------------------------------------------------
# Fixture 1 and fixture 5 of the accepted contract
# --------------------------------------------------------------------------
class EvidenceIsInert(unittest.TestCase):
    """Identical geometry with absent versus declared evidence, and a record that
    is displayed in full while changing nothing else."""

    def _member_without_evidence(self, document):
        member = dict(document["groups"][0]["members"][0])
        member.pop("evidence")
        member.pop("evidence_coverage")
        return member

    def test_absent_and_candidate_evidence_share_rank_group_and_payload(self):
        absent = priority_of([T1_D("c")])
        supplied = priority_of([T1_D("c")], evidence={"c": evidence_record()})
        self.assertEqual(absent.groups[0].rank, supplied.groups[0].rank)
        self.assertEqual(absent.groups[0].geometry_tier, supplied.groups[0].geometry_tier)
        self.assertIs(absent.groups[0].members[0].evidence_coverage, EvidenceCoverage.ABSENT)
        self.assertIs(supplied.groups[0].members[0].evidence_coverage, EvidenceCoverage.CANDIDATE)
        self.assertEqual(
            self._member_without_evidence(absent.as_dict()),
            self._member_without_evidence(supplied.as_dict()),
            "only the evidence fields differ",
        )

    def test_a_fully_populated_record_is_displayed_and_still_inert(self):
        record = evidence_record(
            read_completed=True,
            execution_state="completed",
            validation_status="passed_with_nonfatal_observations",
        )
        supplied = priority_of([T1_D("c")], evidence={"c": record})
        absent = priority_of([T1_D("c")])
        displayed = supplied.as_dict()["groups"][0]["members"][0]["evidence"]
        self.assertEqual(
            set(displayed),
            {
                "provider",
                "profile",
                "artifact_id",
                "observed_sha256",
                "source_status",
                "read_completed",
                "execution_state",
                "validation_status",
                "non_admission_reasons",
            },
            "all nine seam fields are displayed",
        )
        self.assertEqual(
            self._member_without_evidence(absent.as_dict()),
            self._member_without_evidence(supplied.as_dict()),
        )
        self.assertEqual(absent.candidate_order, supplied.candidate_order)
        self.assertEqual(len(absent.groups), len(supplied.groups))
        self.assertEqual(absent.excluded, supplied.excluded)

    def test_differing_coverage_never_reorders_a_tie_group(self):
        first = priority_of(
            [T1_D("a"), T1_D("b")],
            evidence={"a": evidence_record(source_status="rejected"), "b": evidence_record()},
        )
        second = priority_of(
            [T1_D("a"), T1_D("b")],
            evidence={"a": evidence_record(), "b": evidence_record(source_status="rejected")},
        )
        for report in (first, second):
            self.assertEqual([m.candidate_id for m in report.groups[0].members], ["a", "b"])
            self.assertEqual({m.rank for m in [report.groups[0]]}, {1})


# --------------------------------------------------------------------------
# Ordering, ranks and ties
# --------------------------------------------------------------------------
class Ordering(unittest.TestCase):
    def test_groups_follow_tier_order_with_contiguous_ranks(self):
        report = priority_of([T3_D("low"), T1_D("high")])
        self.assertEqual(
            [g.geometry_tier for g in report.groups],
            [GeometryTier.T1_ENGAGED_SLOTS_FULLY_RESOLVED, GeometryTier.T3_NO_RESOLVED_ENGAGED_SLOT],
            "tier order, not caller order, orders the groups",
        )
        self.assertEqual([g.rank for g in report.groups], [1, 2])
        self.assertEqual([g.members[0].candidate_id for g in report.groups], ["high", "low"])

    def test_an_empty_tier_produces_no_group_and_ranks_stay_contiguous(self):
        report = priority_of([T1_D("a"), T3_D("b")])
        self.assertEqual(len(report.groups), 2)
        self.assertNotIn(
            GeometryTier.T2_ENGAGED_SLOTS_PARTIALLY_RESOLVED,
            [g.geometry_tier for g in report.groups],
        )
        self.assertEqual([g.rank for g in report.groups], [1, 2])

    def test_equal_candidates_share_one_group_one_rank_and_caller_sequence(self):
        report = priority_of([T1_D("zebra"), T1_D("alpha"), T1_D("mid")])
        self.assertEqual(len(report.groups), 1)
        group = report.groups[0]
        self.assertEqual(group.rank, 1)
        self.assertEqual(
            [m.candidate_id for m in group.members],
            ["zebra", "alpha", "mid"],
            "caller sequence is preserved and is not alphabetical",
        )

    def test_reversing_caller_sequence_changes_listing_only(self):
        forward = priority_of([T1_D("a"), T1_D("b")])
        reverse = priority_of([T1_D("b"), T1_D("a")])
        self.assertEqual([m.candidate_id for m in forward.groups[0].members], ["a", "b"])
        self.assertEqual([m.candidate_id for m in reverse.groups[0].members], ["b", "a"])
        self.assertEqual(forward.groups[0].rank, reverse.groups[0].rank)
        self.assertEqual(
            {m.candidate_id for m in forward.groups[0].members},
            {m.candidate_id for m in reverse.groups[0].members},
        )

    def test_no_forbidden_value_orders_a_tie_group(self):
        report = priority_of([T1_D("zebra"), T1_D("alpha")])
        members = report.groups[0].members
        ids = [m.candidate_id for m in members]
        self.assertNotEqual(ids, sorted(ids), "candidate_id does not order a group")
        hashes = [m.slot_binding_hash for m in members]
        self.assertEqual(len(set(hashes)), 1, "equal bindings share a hash, so it cannot order")
        self.assertEqual(
            len({m.state_result_id for m in members}), 1, "equal states share a result id"
        )

    def test_excluded_candidates_are_unranked_and_in_caller_sequence(self):
        report = priority_of([UNREACHABLE_D("x"), T1_D("ok"), REFUSED_D("y")])
        self.assertEqual([e.candidate_id for e in report.excluded], ["x", "y"])
        self.assertFalse(hasattr(report.excluded[0], "rank"))
        self.assertNotIn("rank", report.excluded[0].as_dict())

    def test_a_group_refuses_an_inconsistent_member_or_rank(self):
        member = priority_of([T1_D()]).groups[0].members[0]
        with self.assertRaises(ValueError):
            PriorityGroup(0, member.geometry_tier, (member,))
        with self.assertRaises(ValueError):
            PriorityGroup(1, member.geometry_tier, ())
        with self.assertRaises(ValueError):
            PriorityGroup(1, GeometryTier.T3_NO_RESOLVED_ENGAGED_SLOT, (member,))


# --------------------------------------------------------------------------
# Completeness and carried reasons
# --------------------------------------------------------------------------
class Completeness(unittest.TestCase):
    def setUp(self):
        self.declarations = [
            UNREACHABLE_D(),
            REFUSED_D(),
            T1_D(),
            DEGENERATE_D(),
            INFEASIBLE_D(),
            UNSUPPORTED_D(),
            VETOED_D(),
            T3_D(),
        ]
        self.report = priority_of(self.declarations)

    def test_every_candidate_appears_exactly_once(self):
        ranked = [m.candidate_id for g in self.report.groups for m in g.members]
        excluded = [e.candidate_id for e in self.report.excluded]
        self.assertEqual(
            sorted(ranked + excluded), sorted(d.candidate_id for d in self.declarations)
        )
        self.assertEqual(len(set(ranked + excluded)), len(self.declarations))
        self.assertEqual(
            list(self.report.candidate_order), [d.candidate_id for d in self.declarations]
        )

    def test_the_report_refuses_an_incomplete_union(self):
        with self.assertRaises(ValueError):
            CandidatePriorityReport(("a", "b"), self.report.groups, ())
        with self.assertRaises(ValueError):
            CandidatePriorityReport(self.report.candidate_order, (), ())

    def test_the_report_refuses_non_contiguous_ranks_and_wrong_tier_order(self):
        low = priority_of([T3_D("low")]).groups[0]
        high = priority_of([T1_D("high")]).groups[0]
        with self.assertRaises(ValueError):
            CandidatePriorityReport(("high", "low"), (replace(high, rank=2), replace(low, rank=1)), ())
        with self.assertRaises(ValueError):
            CandidatePriorityReport(("low", "high"), (replace(low, rank=1), replace(high, rank=2)), ())

    def test_kernel_status_and_reason_are_carried_verbatim(self):
        batch = {e.candidate_id: e for e in evaluate_candidate_batch(self.declarations).entries}
        for entry in self.report.excluded:
            with self.subTest(candidate=entry.candidate_id):
                source = batch[entry.candidate_id]
                self.assertEqual(entry.slot_binding_hash, source.slot_binding_hash)
                if source.ledger is None:
                    self.assertIsNone(entry.state_status)
                    self.assertEqual(entry.refusal_stage, source.refusal.stage.value)
                    self.assertEqual(entry.refusal_error_class, source.refusal.error_class)
                    self.assertEqual(entry.refusal_detail, source.refusal.detail)
                else:
                    self.assertIs(entry.state_status, source.ledger.rows[0].state_status)
                    self.assertEqual(
                        entry.state_status_reason, source.ledger.rows[0].state_status_reason
                    )
                    self.assertIsNone(entry.refusal_stage)

    def test_a_vetoed_exclusion_names_every_vetoed_slot(self):
        entry = next(e for e in self.report.excluded if e.candidate_id == "vetoed")
        self.assertIs(entry.ineligibility_reason, IneligibilityReason.SLOT_VETOED)
        self.assertEqual(entry.vetoed_slots, (SLOT_IDS[0],))
        self.assertEqual(entry.as_dict()["vetoed_slots"], ["slot_1"])
        other = next(e for e in self.report.excluded if e.candidate_id == "unreachable")
        self.assertEqual(other.vetoed_slots, ())

    def test_an_empty_batch_yields_an_empty_report(self):
        report = priority_of([])
        self.assertEqual((report.candidate_order, report.groups, report.excluded), ((), (), ()))
        self.assertEqual(json.loads(report.to_json_bytes())["candidate_order"], [])


# --------------------------------------------------------------------------
# Immutability and serialization
# --------------------------------------------------------------------------
class Immutability(unittest.TestCase):
    def test_records_are_frozen(self):
        report = priority_of([T1_D("c")], evidence={"c": evidence_record()})
        with self.assertRaises(FrozenInstanceError):
            report.groups = ()
        with self.assertRaises(FrozenInstanceError):
            report.groups[0].rank = 2
        with self.assertRaises(FrozenInstanceError):
            report.groups[0].members[0].geometry_tier = GeometryTier.T3_NO_RESOLVED_ENGAGED_SLOT
        with self.assertRaises(FrozenInstanceError):
            report.groups[0].members[0].evidence.provider = "x"

    def test_as_dict_returns_fresh_containers(self):
        report = priority_of([T1_D("c")], evidence={"c": evidence_record()})
        first, second = report.as_dict(), report.as_dict()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        first["groups"].clear()
        first["candidate_order"].append("ghost")
        self.assertEqual(report.as_dict(), second)

    def test_the_source_batch_is_not_mutated(self):
        batch = evaluate_candidate_batch([T1_D("a"), UNREACHABLE_D("b")])
        before = batch.to_json_bytes()
        evaluate_candidate_priority(batch, evidence={}, providers=KNOWN_PROVIDERS)
        self.assertEqual(batch.to_json_bytes(), before)

    def test_every_container_is_a_tuple(self):
        report = priority_of([T1_D("c")], evidence={"c": evidence_record()})
        self.assertIsInstance(report.groups, tuple)
        self.assertIsInstance(report.candidate_order, tuple)
        self.assertIsInstance(report.groups[0].members, tuple)
        self.assertIsInstance(report.groups[0].members[0].tier_basis, tuple)
        self.assertIsInstance(report.groups[0].members[0].evidence.non_admission_reasons, tuple)


class Serialization(unittest.TestCase):
    def _mixed(self):
        return [
            UNREACHABLE_D(),
            T1_D("zebra"),
            REFUSED_D(),
            T1_D("alpha"),
            T3_D(),
            VETOED_D(),
        ]

    def test_canonical_bytes_are_deterministic(self):
        first = priority_of(self._mixed()).to_json_bytes()
        second = priority_of(self._mixed()).to_json_bytes()
        self.assertEqual(first, second)
        data = json.loads(first)
        self.assertEqual(data["document_type"], PRIORITY_DOCUMENT_TYPE)
        self.assertEqual(list(data), sorted(data), "sort_keys orders object keys")
        self.assertNotEqual(
            data["candidate_order"],
            sorted(data["candidate_order"]),
            "arrays keep the order they were built in",
        )
        self.assertEqual(
            [m["candidate_id"] for m in data["groups"][0]["members"]],
            ["zebra", "alpha"],
            "member arrays keep caller sequence, not sorted order",
        )

    def test_the_document_carries_exactly_the_declared_keys(self):
        data = json.loads(priority_of([T1_D()]).to_json_bytes())
        self.assertEqual(
            set(data), {"document_type", "non_claim", "candidate_order", "groups", "excluded"}
        )

    def test_canonical_bytes_are_stable_across_pythonhashseed(self):
        program = (
            "import sys\n"
            f"sys.path.insert(0, {str(ROOT_DIR)!r})\n"
            f"sys.path.insert(0, {str(ROOT_DIR / 'tests')!r})\n"
            "from test_phase2_cassette_candidate_priority import Serialization, priority_of\n"
            "case = Serialization('test_canonical_bytes_are_deterministic')\n"
            "sys.stdout.write(priority_of(case._mixed()).to_json_bytes().hex())\n"
        )
        digests = set()
        for seed in ("0", "1", "12345"):
            completed = subprocess.run(
                [sys.executable, "-B", "-c", program],
                capture_output=True,
                text=True,
                timeout=300,
                env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
            digests.add(completed.stdout)
        self.assertEqual(len(digests), 1, "priority bytes differ across PYTHONHASHSEED")

    def test_no_nan_or_infinity_can_enter_the_document(self):
        report = priority_of([T1_D()])
        text = report.to_json_bytes().decode("utf-8")
        for token in ("NaN", "Infinity", "-Infinity"):
            self.assertNotIn(token, text)


# --------------------------------------------------------------------------
# Import boundary
# --------------------------------------------------------------------------
class ImportBoundary(unittest.TestCase):
    def _imported(self, source):
        names = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[-1] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    if node.module:
                        names.add(node.module.split(".")[-1])
                    names.update(a.name for a in node.names)
                elif node.module and node.module.startswith("gotne"):
                    names.add(node.module.split(".")[-1])
                    names.update(a.name for a in node.names)
        return names

    def test_direct_imports_avoid_the_chain_the_intake_tree_and_io(self):
        imported = self._imported((PACKAGE_DIR / f"{MODULE}.py").read_text())
        for forbidden in CHAIN_MODULES + PHASE45 + EXTERNAL_INTAKE + IO_MODULES:
            with self.subTest(module=forbidden):
                self.assertNotIn(forbidden, imported, f"{MODULE} imports {forbidden}")
        self.assertIn("cassette_candidate_batch", imported, "the consumed contract is read")
        self.assertIn("cassette_slot_ledger", imported)

    def test_static_closure_reaches_no_phase4_or_phase5_module(self):
        seen, queue = set(), [MODULE]
        while queue:
            name = queue.pop()
            if name in seen:
                continue
            path = PACKAGE_DIR / f"{name}.py"
            if not path.is_file():
                continue
            seen.add(name)
            for imported in self._imported(path.read_text()):
                self.assertNotIn(imported, PHASE45, f"{name} reaches {imported}")
                queue.append(imported)
        self.assertIn("cassette_candidate_batch", seen, "the scan walked into the consumed seam")

    def test_no_existing_module_imports_the_priority_layer(self):
        for path in sorted(PACKAGE_DIR.glob("*.py")):
            imported = self._imported(path.read_text())
            if path.stem != "cassette_scenario_comparison":
                self.assertNotIn(
                    "cassette_scenario_comparison", imported,
                    f"{path.stem} must not depend on the scenario-comparison consumer",
                )
            if path.stem in (MODULE, "cassette_scenario_comparison"):
                continue
            with self.subTest(module=path.stem):
                self.assertNotIn(
                    MODULE, imported, f"{path.stem} imports {MODULE}"
                )

    def test_scenario_comparison_imports_only_finished_reporting_contracts(self):
        """Pin the new consumer's exact project imports; no evaluator or sibling seam."""
        allowed = {
            "cassette_candidate_batch": {"CandidateBatchReport"},
            "cassette_candidate_priority": {
                "CandidatePriorityReport", "IneligibilityReason", "TIER_ORDER",
                "PRIORITY_NON_CLAIM", "PRIORITY_DISPLAY_DISCLAIMER", "PRIORITY_DOCUMENT_TYPE",
            },
        }
        observed = {}
        source = (PACKAGE_DIR / "cassette_scenario_comparison.py").read_text()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(alias.name == "gotne" or alias.name.startswith("gotne."),
                                     "import reporting symbols explicitly, not entire project modules")
            elif isinstance(node, ast.ImportFrom):
                if not node.level and node.module and not node.module.startswith("gotne"):
                    continue
                module = (node.module or "").removeprefix("gotne.")
                self.assertIn(node.level, (0, 1))
                self.assertIn(module, allowed, "no unrelated project import is authorized")
                observed.setdefault(module, set()).update(alias.name for alias in node.names)
        self.assertEqual(observed, allowed, "only the existing reporting symbols are authorized")

    def test_the_package_surface_is_unchanged(self):
        import gotne

        self.assertNotIn(MODULE, gotne.__all__)
        for name in ("CandidatePriorityReport", "GeometryTier", "EvidenceCoverage"):
            self.assertNotIn(name, gotne.__all__, "the priority layer is reachable by submodule")

    def test_dynamic_run_loads_no_phase4_or_phase5_module(self):
        program = (
            "import sys\n"
            f"sys.path.insert(0, {str(ROOT_DIR)!r})\n"
            f"sys.path.insert(0, {str(ROOT_DIR / 'tests')!r})\n"
            "from test_phase2_cassette_candidate_priority import Serialization, priority_of\n"
            "case = Serialization('test_canonical_bytes_are_deterministic')\n"
            "priority_of(case._mixed())\n"
            f"leaked = [m for m in sys.modules if m.split('.')[-1] in {PHASE45!r}]\n"
            "print('LEAKED:' + ','.join(sorted(leaked)))\n"
        )
        completed = subprocess.run(
            [sys.executable, "-B", "-c", program], capture_output=True, text=True, timeout=300
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        self.assertIn("LEAKED:\n", completed.stdout, completed.stdout)

    def test_the_module_declares_no_numeric_or_fitted_constant(self):
        source = (PACKAGE_DIR / f"{MODULE}.py").read_text()
        numeric = []
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name) and t.id.isupper()]
            if names and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, (int, float)) and not isinstance(
                    node.value.value, bool
                ):
                    numeric.extend(names)
        self.assertEqual(numeric, [], f"module-level numeric constants declared: {numeric}")
        for banned in ("threshold", "weight", "probability", "score", "confidence", "fitted"):
            with self.subTest(term=banned):
                self.assertNotIn(
                    f"{banned} =", source.lower(), f"the module assigns a {banned}"
                )

    def test_no_arithmetic_operator_touches_a_reported_value(self):
        source = (PACKAGE_DIR / f"{MODULE}.py").read_text()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.BinOp):
                self.assertIsInstance(
                    node.op,
                    (ast.Add,),
                    "only the group-rank successor and string/tuple joins use an operator",
                )

    def test_the_priority_layer_calls_no_evaluation_entry_point(self):
        source = (PACKAGE_DIR / f"{MODULE}.py").read_text()
        called = {
            node.func.id
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for entry_point in (
            "evaluate_state",
            "evaluate_node",
            "issue_state_certificate",
            "evaluate_candidate_batch",
            "build_slot_ledger",
            "open",
        ):
            with self.subTest(entry_point=entry_point):
                self.assertNotIn(entry_point, called, f"{MODULE} calls {entry_point}")


if __name__ == "__main__":
    unittest.main()
