"""Contract tests for ``layer_2_initial_triage_profile/1``.

The module under test is loaded directly from its file so that no package initializer
runs and no project module is imported on its behalf. Every input document is a
serialized mapping, exactly as the producing layer emits it.

Run: python3 -B -m unittest discover -s tests -t tests \
         -p 'test_layer_2_initial_triage_profile.py' -v
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import pathlib
import subprocess
import sys
import unittest

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT_DIR / "files"
MODULE_NAME = "layer_2_initial_triage_profile"
MODULE_PATH = PACKAGE_DIR / (MODULE_NAME + ".py")


def _load_module():
    spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


m = _load_module()
Error = m.Layer2TriageProfileError

STAMP = "2026-09-28T09:15:00Z"
TARGET = "target-system-1"
BASIS = "scenario-1"
TASK = "three binder anchored assembly, declared"
POSITIONS = ("slot_1", "slot_2", "slot_3")
TIER1 = "T1_ENGAGED_SLOTS_FULLY_RESOLVED"
TIER2 = "T2_ENGAGED_SLOTS_PARTIALLY_RESOLVED"
INTERFERENCE = "COLLECTIVE_INTERFERENCE"
BURDEN = "COLLECTIVE_DEFORMATION_RESTRAINT_BURDEN"
LOCAL = m.LOCAL_TIE_BREAK_DIMENSION


def canon(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


# ================================================================================
# Input builders: serialized documents, exactly as their own layers emit them
# ================================================================================


def priority_document(ranked=(("c1", TIER1), ("c2", TIER1)), excluded=()):
    groups = []
    for rank, tier in enumerate(m.TIER_ORDER, start=1):
        members = [
            {
                "candidate_id": identifier,
                "slot_binding_hash": "hash-" + identifier,
                "state_result_id": "state-" + identifier,
                "certificate_present": True,
                "geometry_tier": tier,
                "evidence_coverage": "AVAILABLE",
                "evidence": None,
                "tier_basis": [],
            }
            for identifier, member_tier in ranked
            if member_tier == tier
        ]
        if members:
            groups.append({"rank": rank, "geometry_tier": tier, "members": members})
    return {
        "document_type": "cassette_candidate_priority/1",
        "non_claim": "supplied",
        "candidate_order": [identifier for identifier, _tier in ranked],
        "groups": groups,
        "excluded": [
            {
                "candidate_id": identifier,
                "slot_binding_hash": "hash-" + identifier,
                "ineligibility_reason": reason,
                "state_status": None,
                "state_status_reason": None,
                "vetoed_slots": [],
                "refusal_stage": None,
                "refusal_error_class": None,
                "refusal_detail": None,
            }
            for identifier, reason in excluded
        ],
    }


def definition_payload(name="observable", reference="def-1", unit_class="LENGTH", unit="nm"):
    return {
        "definition_reference": {"namespace": "ns", "identifier": reference, "revision": "v1"},
        "observable_name": name,
        "unit_class": unit_class,
        "unit_symbol": unit,
    }


def descriptor_payload(
    descriptor_id,
    family,
    number="1.5",
    conditions=("PROVIDED",),
    observations=None,
    definition=None,
):
    if observations is None:
        observations = [
            {
                "observation_id": "o-" + descriptor_id,
                "value": None if number is None else {"kind": "NUMERIC", "number": number},
            }
        ]
    return {
        "descriptor_id": descriptor_id,
        "family": family,
        "definition": definition or definition_payload(),
        "observations": observations,
        "conditions": list(conditions),
        "reasons": [],
    }


def collective_document(
    candidate_id,
    interference="1.0",
    burden="2.0",
    *,
    scenario_id=BASIS,
    target=TARGET,
    task=TASK,
    joint_frame=True,
    connections=True,
    elements=("ANCHOR", "LINKER"),
    descriptors=None,
    associations=None,
):
    if descriptors is None:
        descriptors = []
        if interference is not None:
            descriptors.append(descriptor_payload("d-int-" + candidate_id, INTERFERENCE, interference))
        if burden is not None:
            descriptors.append(descriptor_payload("d-bur-" + candidate_id, BURDEN, burden))
    return {
        "document_type": "layer_2b_descriptor_input/1",
        "document_id": "b-" + candidate_id,
        "revision": "rev-1",
        "candidate_anchor": {"candidate_id": candidate_id, "scenario_id": scenario_id},
        "scope": {
            "joint_frame": {"frame_id": "frame-1"} if joint_frame else None,
            "local_associations": [
                {"slot_id": slot, "binder_participant_id": "b-" + slot}
                for slot in (POSITIONS if associations is None else associations)
            ],
            "connections": [{"connection_id": "conn-1"}] if connections else [],
            "assembly_elements": [
                {"element_id": "e-{0}".format(position), "kind": kind}
                for position, kind in enumerate(elements)
            ],
            "target_site_declaration": target,
            "assembly_task_declaration": task,
        },
        "descriptors": descriptors,
    }


def local_document(candidate_id, slot_id, number="1.0", **overrides):
    payload = {
        "document_type": "layer_2a_descriptor_input/1",
        "document_id": "a-{0}-{1}".format(candidate_id, slot_id),
        "revision": "rev-1",
        "candidate_anchor": {"candidate_id": candidate_id, "scenario_id": BASIS},
        "scope": {"slot_id": slot_id},
        "descriptors": [
            descriptor_payload("d-loc-{0}-{1}".format(candidate_id, slot_id), LOCAL, number)
        ],
    }
    payload.update(overrides)
    return payload


def cohort(directions=None, **overrides):
    if directions is None:
        directions = ("LOWER_IS_PREFERRED", "LOWER_IS_PREFERRED", "LOWER_IS_PREFERRED")
    payload = dict(
        target_system_identity=TARGET,
        layer1_comparison_basis=BASIS,
        ordered_local_position_roles=POSITIONS,
        collective_task_scope_type=TASK,
        triage_convention_version=m.TRIAGE_CONVENTION_VERSION,
        dimension_directions=tuple(
            m.TriageDimensionDirection(dimension=dimension, direction=direction)
            for dimension, direction in zip(m.TRIAGE_DIMENSIONS, directions)
        ),
    )
    payload.update(overrides)
    return m.TriageCohortDeclaration(**payload)


def candidate(candidate_id, interference="1.0", burden="2.0", locals_=("1.0", "1.0", "1.0"), **kwargs):
    return m.TriageCandidateInput(
        candidate_id=candidate_id,
        local_inputs=tuple(
            m.TriageLocalInput(
                position_role=slot, document=local_document(candidate_id, slot, number)
            )
            for slot, number in zip(POSITIONS, locals_)
        ),
        collective_document=collective_document(
            candidate_id, interference, burden, **kwargs
        ),
    )


def build(candidates, priority=None, declaration=None, **overrides):
    payload = dict(
        profile_id="profile-1",
        revision="rev-1",
        declared_by="party-1",
        declared_at=STAMP,
        cohort=declaration or cohort(),
        priority_document=priority or priority_document(),
        candidates=tuple(candidates),
    )
    payload.update(overrides)
    return m.build_initial_triage_profile(**payload)


def states_of(profile):
    return {item.candidate_id: item.profile_state for item in profile.candidates}


def gates_of(profile, candidate_id):
    entry = next(item for item in profile.candidates if item.candidate_id == candidate_id)
    return {item.gate: (item.disposition, item.reason) for item in entry.gates}


def groups_of(profile):
    return [list(group) for group in profile.relation.ordered_groups]


def cohort_dimension(profile, dimension):
    return next(
        item for item in profile.cohort_dimensions if item.dimension == dimension
    )


# ================================================================================
# 1. Comparable cohort
# ================================================================================


class ComparableCohort(unittest.TestCase):
    def test_a_full_cohort_comparable_triage_issues_one_priority(self):
        profile = build((candidate("c1", "1.0", "1.0"), candidate("c2", "2.0", "2.0")))
        self.assertEqual(profile.relation.scope, "COHORT_WIDE")
        self.assertIsNone(profile.relation.withheld_reason)
        self.assertEqual(groups_of(profile), [["c1"], ["c2"]])
        self.assertEqual(
            states_of(profile),
            {"c1": "EXPERIMENTAL_PRIORITY", "c2": "NOT_PRIORITIZED_BY_PROFILE"},
        )

    def test_every_gate_passes_and_is_reported_in_order(self):
        profile = build((candidate("c1", "1.0", "1.0"), candidate("c2", "2.0", "2.0")))
        gates = gates_of(profile, "c1")
        self.assertEqual(tuple(gates), m.GATES)
        for gate, (disposition, reason) in gates.items():
            with self.subTest(gate=gate):
                self.assertEqual(disposition, "PASSED")
                self.assertIsNone(reason)

    def test_the_profile_keeps_exact_source_references(self):
        profile = build((candidate("c1"), candidate("c2", "2.0", "2.0")))
        entry = next(item for item in profile.candidates if item.candidate_id == "c1")
        references = [
            (item.document_type, item.document_id, item.position_role)
            for item in entry.sources
        ]
        self.assertEqual(
            references,
            [
                ("layer_2b_descriptor_input/1", "b-c1", None),
                ("layer_2a_descriptor_input/1", "a-c1-slot_1", "slot_1"),
                ("layer_2a_descriptor_input/1", "a-c1-slot_2", "slot_2"),
                ("layer_2a_descriptor_input/1", "a-c1-slot_3", "slot_3"),
            ],
        )
        self.assertEqual(entry.layer1.source_pointer, "/groups/0/members/0")
        self.assertEqual(entry.layer1.geometry_tier, TIER1)
        self.assertEqual(profile.layer1_source.document_type, "cassette_candidate_priority/1")

    def test_layer_1_tier_precedes_the_collective_vector(self):
        profile = build(
            (candidate("c1", "9.0", "9.0"), candidate("c2", "1.0", "1.0")),
            priority=priority_document(ranked=(("c1", TIER1), ("c2", TIER2))),
        )
        self.assertEqual(groups_of(profile), [["c1"], ["c2"]])
        self.assertEqual(states_of(profile)["c1"], "EXPERIMENTAL_PRIORITY")


# ================================================================================
# 2. Layer 1 boundary
# ================================================================================


class Layer1Boundary(unittest.TestCase):
    def test_a_layer_1_exclusion_refuses_comparison_and_is_never_rescued(self):
        profile = build(
            (candidate("c1"), candidate("c2", "0.1", "0.1")),
            priority=priority_document(
                ranked=(("c1", TIER1),), excluded=(("c2", "STATE_NOT_VALID"),)
            ),
        )
        self.assertEqual(gates_of(profile, "c2")["LAYER1_BOUNDARY"], ("FAILED", "LAYER1_EXCLUDED"))
        self.assertEqual(states_of(profile)["c2"], "NOT_PRIORITIZED_BY_PROFILE")
        self.assertNotIn("c2", [member for group in groups_of(profile) for member in group])
        entry = next(item for item in profile.candidates if item.candidate_id == "c2")
        self.assertEqual(entry.layer1.disposition, "EXCLUDED")
        self.assertEqual(entry.layer1.ineligibility_reason, "STATE_NOT_VALID")

    def test_an_absent_layer_1_entry_is_not_comparable(self):
        profile = build(
            (candidate("c1"), candidate("c2")),
            priority=priority_document(ranked=(("c1", TIER1),)),
        )
        self.assertEqual(gates_of(profile, "c2")["LAYER1_BOUNDARY"], ("FAILED", "LAYER1_ENTRY_ABSENT"))
        self.assertEqual(states_of(profile)["c2"], "COMPARISON_UNSUPPORTED")

    def test_a_candidate_named_twice_by_the_report_is_refused(self):
        priority = priority_document(ranked=(("c1", TIER1),), excluded=(("c1", "STATE_NOT_VALID"),))
        with self.assertRaises(Error) as caught:
            build((candidate("c1"),), priority=priority)
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")


# ================================================================================
# 3. Withheld issuance and the subset-only relation
# ================================================================================


class WithheldIssuance(unittest.TestCase):
    def setUp(self):
        self.profile = build(
            (
                candidate("c1", "1.0", "1.0"),
                candidate("c2", "2.0", "2.0"),
                candidate("c3", "3.0", "3.0", joint_frame=False),
            ),
            priority=priority_document(
                ranked=(("c1", TIER1), ("c2", TIER1), ("c3", TIER1))
            ),
        )

    def test_one_review_required_member_withholds_full_cohort_issuance(self):
        self.assertEqual(
            gates_of(self.profile, "c3")["COLLECTIVE_SCOPE"],
            ("FAILED", "COLLECTIVE_SCOPE_INCOMPLETE"),
        )
        self.assertEqual(states_of(self.profile)["c3"], "REVIEW_REQUIRED")
        self.assertEqual(self.profile.relation.scope, "GATE_PASSED_SUBSET_ONLY")

    def test_the_relation_is_labeled_subset_only(self):
        self.assertEqual(self.profile.relation.scope, "GATE_PASSED_SUBSET_ONLY")
        self.assertEqual(
            self.profile.relation.withheld_reason, "RETAINED_MEMBER_NOT_GATE_PASSED"
        )
        self.assertEqual(groups_of(self.profile), [["c1"], ["c2"]])
        self.assertNotIn("c3", [member for group in groups_of(self.profile) for member in group])

    def test_the_subset_leader_keeps_its_priority_state(self):
        self.assertEqual(states_of(self.profile)["c1"], "EXPERIMENTAL_PRIORITY")
        self.assertEqual(states_of(self.profile)["c2"], "NOT_PRIORITIZED_BY_PROFILE")

    def test_a_subset_only_priority_is_never_serialized_as_cohort_wide(self):
        payload = self.profile.as_dict()["relation"]
        self.assertEqual(payload["scope"], "GATE_PASSED_SUBSET_ONLY")
        self.assertEqual(payload["withheld_reason"], "RETAINED_MEMBER_NOT_GATE_PASSED")
        self.assertNotIn("COHORT_WIDE", json.dumps(payload))
        lines = m.render_profile_lines(self.profile)
        self.assertIn("relation scope: GATE_PASSED_SUBSET_ONLY", lines)
        self.assertIn(
            "full-cohort issuance withheld: RETAINED_MEMBER_NOT_GATE_PASSED", lines
        )

    def test_a_tied_subset_leader_is_a_priority_tie(self):
        profile = build(
            (
                candidate("c1", "1.0", "1.0"),
                candidate("c2", "1.0", "1.0"),
                candidate("c3", "3.0", "3.0", joint_frame=False),
            ),
            priority=priority_document(
                ranked=(("c1", TIER1), ("c2", TIER1), ("c3", TIER1))
            ),
        )
        self.assertEqual(profile.relation.scope, "GATE_PASSED_SUBSET_ONLY")
        self.assertEqual(groups_of(profile), [["c1", "c2"]])
        self.assertEqual(states_of(profile)["c1"], "EXPERIMENTAL_PRIORITY_TIE")
        self.assertEqual(states_of(profile)["c2"], "EXPERIMENTAL_PRIORITY_TIE")
        self.assertEqual(states_of(profile)["c3"], "REVIEW_REQUIRED")

    def test_missing_evidence_is_not_a_loss(self):
        profile = build(
            (candidate("c1"), candidate("c2", interference=None, burden=None))
        )
        self.assertEqual(
            gates_of(profile, "c2")["REQUIRED_COLLECTIVE_EVIDENCE"],
            ("FAILED", "REQUIRED_COLLECTIVE_EVIDENCE_ABSENT"),
        )
        self.assertEqual(states_of(profile)["c2"], "REVIEW_REQUIRED")
        self.assertEqual(profile.relation.scope, "GATE_PASSED_SUBSET_ONLY")


# ================================================================================
# 4. Collective Pareto behavior
# ================================================================================


class CollectivePareto(unittest.TestCase):
    def test_dominance_orders_the_dominated_candidate_second(self):
        profile = build((candidate("c1", "1.0", "1.0"), candidate("c2", "2.0", "3.0")))
        self.assertEqual(groups_of(profile), [["c1"], ["c2"]])

    def test_a_tradeoff_produces_one_tie_set(self):
        profile = build((candidate("c1", "1.0", "5.0"), candidate("c2", "5.0", "1.0")))
        self.assertEqual(groups_of(profile), [["c1", "c2"]])
        self.assertEqual(
            states_of(profile),
            {"c1": "EXPERIMENTAL_PRIORITY_TIE", "c2": "EXPERIMENTAL_PRIORITY_TIE"},
        )

    def test_direction_is_caller_declared_and_reverses_the_order(self):
        candidates = (candidate("c1", "1.0", "1.0"), candidate("c2", "2.0", "2.0"))
        lower = build(candidates)
        higher = build(
            candidates,
            declaration=cohort(
                directions=(
                    "HIGHER_IS_PREFERRED",
                    "HIGHER_IS_PREFERRED",
                    "LOWER_IS_PREFERRED",
                )
            ),
        )
        self.assertEqual(groups_of(lower), [["c1"], ["c2"]])
        self.assertEqual(groups_of(higher), [["c2"], ["c1"]])

    def test_an_undeclared_direction_suspends_the_dimension(self):
        profile = build(
            (candidate("c1", "1.0", "9.0"), candidate("c2", "2.0", "1.0")),
            declaration=cohort(
                directions=("LOWER_IS_PREFERRED", "NO_DIRECTION_DECLARED", "LOWER_IS_PREFERRED")
            ),
        )
        suspended = cohort_dimension(profile, BURDEN)
        self.assertEqual(suspended.state, "SUSPENDED")
        self.assertEqual(suspended.suspension_reason, "NO_DIRECTION_DECLARED")
        self.assertEqual(profile.relation.basis_dimensions, (INTERFERENCE,))
        self.assertEqual(groups_of(profile), [["c1"], ["c2"]])

    def test_two_qualifying_descriptors_suspend_the_dimension_cohort_wide(self):
        crowded = candidate("c1")
        crowded.collective_document["descriptors"].append(
            descriptor_payload("d-int-extra", INTERFERENCE, "0.5")
        )
        profile = build((crowded, candidate("c2", "2.0", "2.0")))
        suspended = cohort_dimension(profile, INTERFERENCE)
        self.assertEqual(suspended.suspension_reason, "MULTIPLE_QUALIFYING_DESCRIPTORS")
        self.assertEqual(profile.relation.basis_dimensions, (BURDEN,))

    def test_a_unit_mismatch_suspends_the_dimension_cohort_wide(self):
        odd = candidate("c2", "2.0", "2.0")
        odd.collective_document["descriptors"][0]["definition"] = definition_payload(unit="pm")
        profile = build((candidate("c1"), odd))
        suspended = cohort_dimension(profile, INTERFERENCE)
        self.assertEqual(suspended.suspension_reason, "UNIT_SYMBOL_MISMATCH")
        self.assertNotIn(INTERFERENCE, profile.relation.basis_dimensions)

    def test_no_common_active_dimension_makes_comparison_unsupported(self):
        profile = build(
            (candidate("c1"), candidate("c2", "2.0", "2.0")),
            declaration=cohort(
                directions=(
                    "NO_DIRECTION_DECLARED",
                    "NO_DIRECTION_DECLARED",
                    "NO_DIRECTION_DECLARED",
                )
            ),
        )
        self.assertEqual(
            gates_of(profile, "c1")["COMMON_ACTIVE_DIMENSIONS"],
            ("FAILED", "NO_COMMON_ACTIVE_DIMENSION"),
        )
        self.assertEqual(set(states_of(profile).values()), {"COMPARISON_UNSUPPORTED"})
        self.assertEqual(groups_of(profile), [])


# ================================================================================
# 5. Local comparison, only after exact collective equality
# ================================================================================


class LocalTieBreak(unittest.TestCase):
    def test_local_positions_break_an_exact_collective_tie(self):
        profile = build(
            (
                candidate("c1", "1.0", "1.0", locals_=("1.0", "1.0", "1.0")),
                candidate("c2", "1.0", "1.0", locals_=("1.0", "2.0", "1.0")),
            )
        )
        self.assertEqual(groups_of(profile), [["c1"], ["c2"]])
        self.assertEqual(states_of(profile)["c1"], "EXPERIMENTAL_PRIORITY")

    def test_local_comparison_is_lexicographic_in_declared_position_order(self):
        profile = build(
            (
                candidate("c1", "1.0", "1.0", locals_=("2.0", "0.0", "0.0")),
                candidate("c2", "1.0", "1.0", locals_=("1.0", "9.0", "9.0")),
            )
        )
        self.assertEqual(groups_of(profile), [["c2"], ["c1"]])

    def test_local_comparison_is_not_reached_on_a_collective_tradeoff(self):
        profile = build(
            (
                candidate("c1", "1.0", "5.0", locals_=("1.0", "1.0", "1.0")),
                candidate("c2", "5.0", "1.0", locals_=("9.0", "9.0", "9.0")),
            )
        )
        self.assertEqual(groups_of(profile), [["c1", "c2"]])

    def test_local_comparison_is_not_reached_while_the_collective_vector_differs(self):
        profile = build(
            (
                candidate("c1", "1.0", "1.0", locals_=("9.0", "9.0", "9.0")),
                candidate("c2", "2.0", "2.0", locals_=("0.1", "0.1", "0.1")),
            )
        )
        self.assertEqual(groups_of(profile), [["c1"], ["c2"]])

    def test_equal_local_positions_remain_one_tie_set(self):
        profile = build(
            (
                candidate("c1", "1.0", "1.0", locals_=("1.0", "1.0", "1.0")),
                candidate("c2", "1.0", "1.0", locals_=("1.0", "1.0", "1.0")),
            )
        )
        self.assertEqual(groups_of(profile), [["c1", "c2"]])
        self.assertEqual(set(states_of(profile).values()), {"EXPERIMENTAL_PRIORITY_TIE"})


# ================================================================================
# 6. Cohort identity verification
# ================================================================================


class CohortIdentity(unittest.TestCase):
    def mismatch(self, **kwargs):
        profile = build((candidate("c1", **kwargs), candidate("c2", "2.0", "2.0")))
        return gates_of(profile, "c1")["COHORT_COMPARABILITY"], states_of(profile)["c1"]

    def test_a_comparison_basis_mismatch_is_incomparable(self):
        gate, state = self.mismatch(scenario_id="other-scenario")
        self.assertEqual(gate, ("FAILED", "LAYER1_COMPARISON_BASIS_MISMATCH"))
        self.assertEqual(state, "COMPARISON_UNSUPPORTED")

    def test_a_target_system_mismatch_is_incomparable(self):
        gate, state = self.mismatch(target="other-target")
        self.assertEqual(gate, ("FAILED", "TARGET_SYSTEM_IDENTITY_MISMATCH"))
        self.assertEqual(state, "COMPARISON_UNSUPPORTED")

    def test_a_task_scope_text_mismatch_is_incomparable(self):
        gate, state = self.mismatch(task=TASK + " ")
        self.assertEqual(gate, ("FAILED", "COLLECTIVE_TASK_SCOPE_MISMATCH"))
        self.assertEqual(state, "COMPARISON_UNSUPPORTED")

    def test_a_convention_version_mismatch_is_incomparable(self):
        profile = build(
            (candidate("c1"), candidate("c2", "2.0", "2.0")),
            declaration=cohort(triage_convention_version="layer_2_initial_triage/0"),
        )
        self.assertEqual(
            gates_of(profile, "c1")["COHORT_COMPARABILITY"],
            ("FAILED", "CONVENTION_VERSION_MISMATCH"),
        )
        self.assertEqual(set(states_of(profile).values()), {"COMPARISON_UNSUPPORTED"})
        self.assertEqual(groups_of(profile), [])

    def test_a_candidate_identity_mismatch_fails_the_first_gate(self):
        odd = candidate("c1")
        odd.collective_document["candidate_anchor"]["candidate_id"] = "other"
        profile = build((odd, candidate("c2", "2.0", "2.0")))
        self.assertEqual(
            gates_of(profile, "c1")["IDENTITY_PROVENANCE"],
            ("FAILED", "CANDIDATE_IDENTITY_MISMATCH"),
        )
        self.assertEqual(gates_of(profile, "c1")["LAYER1_BOUNDARY"], ("NOT_EVALUATED", None))

    def test_a_local_slot_mismatch_is_a_source_reference_fault(self):
        odd = m.TriageCandidateInput(
            candidate_id="c1",
            local_inputs=tuple(
                m.TriageLocalInput(
                    position_role=slot, document=local_document("c1", "slot_1", "1.0")
                )
                for slot in POSITIONS
            ),
            collective_document=collective_document("c1"),
        )
        profile = build((odd, candidate("c2", "2.0", "2.0")))
        self.assertEqual(
            gates_of(profile, "c1")["IDENTITY_PROVENANCE"],
            ("FAILED", "LOCAL_POSITION_SET_MISMATCH"),
        )
        self.assertEqual(states_of(profile)["c1"], "COMPARISON_UNSUPPORTED")

    def test_the_declaration_requires_every_dimension_exactly_once(self):
        with self.assertRaises(Error) as caught:
            cohort(
                dimension_directions=(
                    m.TriageDimensionDirection(
                        dimension=INTERFERENCE, direction="LOWER_IS_PREFERRED"
                    ),
                )
            )
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")

    def test_the_declaration_requires_three_ordered_positions(self):
        with self.assertRaises(Error) as caught:
            cohort(ordered_local_position_roles=("slot_1", "slot_2"))
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")


# ================================================================================
# 7. No identifier or input-order tie-break
# ================================================================================


class NoIdentifierTieBreak(unittest.TestCase):
    def test_equal_candidates_stay_in_one_group_whatever_their_identifiers(self):
        for first, second in (("a1", "z9"), ("z9", "a1")):
            with self.subTest(pair=(first, second)):
                profile = build(
                    (candidate(first, "1.0", "1.0"), candidate(second, "1.0", "1.0")),
                    priority=priority_document(ranked=((first, TIER1), (second, TIER1))),
                )
                self.assertEqual(len(groups_of(profile)), 1)
                self.assertEqual(sorted(groups_of(profile)[0]), sorted([first, second]))

    def test_input_order_does_not_change_the_relation(self):
        priority = priority_document(ranked=(("c1", TIER1), ("c2", TIER1)))
        forward = build((candidate("c1", "1.0", "5.0"), candidate("c2", "5.0", "1.0")), priority=priority)
        reverse = build((candidate("c2", "5.0", "1.0"), candidate("c1", "1.0", "5.0")), priority=priority)
        self.assertEqual(
            canon(forward.relation.as_dict()), canon(reverse.relation.as_dict())
        )
        self.assertEqual(states_of(forward), states_of(reverse))

    def test_input_order_does_not_change_a_dominance_result(self):
        priority = priority_document(ranked=(("c1", TIER1), ("c2", TIER1)))
        forward = build((candidate("c1", "1.0", "1.0"), candidate("c2", "2.0", "2.0")), priority=priority)
        reverse = build((candidate("c2", "2.0", "2.0"), candidate("c1", "1.0", "1.0")), priority=priority)
        self.assertEqual(groups_of(forward), groups_of(reverse))
        self.assertEqual(groups_of(forward), [["c1"], ["c2"]])


# ================================================================================
# 8. Canonical serialization
# ================================================================================


class CanonicalSerialization(unittest.TestCase):
    def setUp(self):
        self.profile = build((candidate("c1", "1.0", "1.0"), candidate("c2", "2.0", "3.0")))

    def test_the_document_constants_are_derived_not_supplied(self):
        self.assertEqual(self.profile.document_type, m.TRIAGE_DOCUMENT_TYPE)
        self.assertEqual(self.profile.non_claim, m.TRIAGE_NON_CLAIM)
        payload = self.profile.as_dict()
        self.assertEqual(list(payload)[0], "document_type")
        self.assertEqual(list(payload)[-1], "non_claim")

    def test_canonical_bytes_are_compact_sorted_and_stable(self):
        first = self.profile.to_json_bytes()
        self.assertEqual(first, self.profile.to_json_bytes())
        self.assertEqual(canon(json.loads(first.decode("utf-8"))), first)
        self.assertFalse(first.endswith(b"\n"))
        self.assertFalse(first.startswith(b"\xef\xbb\xbf"))
        decoded = json.loads(first.decode("utf-8"))
        self.assertEqual(list(decoded), sorted(decoded))

    def test_identical_inputs_produce_identical_bytes(self):
        again = build((candidate("c1", "1.0", "1.0"), candidate("c2", "2.0", "3.0")))
        self.assertEqual(again.to_json_bytes(), self.profile.to_json_bytes())

    def test_bytes_are_stable_across_fresh_processes_and_hash_seeds(self):
        script = (
            "import importlib.util,sys,hashlib\n"
            "spec=importlib.util.spec_from_file_location('m',{0!r})\n"
            "mod=importlib.util.module_from_spec(spec);sys.modules['m']=mod\n"
            "spec.loader.exec_module(mod)\n"
            "sys.path.insert(0,{1!r})\n"
            "import test_layer_2_initial_triage_profile as t\n"
            "p=t.build((t.candidate('c1','1.0','1.0'),t.candidate('c2','2.0','3.0')))\n"
            "print(hashlib.sha256(p.to_json_bytes()).hexdigest())\n"
        ).format(str(MODULE_PATH), str(pathlib.Path(__file__).resolve().parent))
        digests = set()
        for seed in ("0", "1", "2"):
            done = subprocess.run(
                [sys.executable, "-B", "-c", script],
                env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
                capture_output=True,
                text=True,
            )
            self.assertEqual(done.returncode, 0, done.stderr[-2000:])
            digests.add(done.stdout.strip())
        self.assertEqual(len(digests), 1)

    def test_round_trip_from_dict_and_from_bytes(self):
        payload = self.profile.as_dict()
        self.assertEqual(
            m.Layer2InitialTriageProfile.from_dict(payload).to_json_bytes(),
            self.profile.to_json_bytes(),
        )
        self.assertEqual(
            m.Layer2InitialTriageProfile.from_json_bytes(
                self.profile.to_json_bytes()
            ).to_json_bytes(),
            self.profile.to_json_bytes(),
        )

    def test_as_dict_returns_a_fresh_detached_structure(self):
        first = self.profile.as_dict()
        first["candidates"][0]["profile_state"] = "REVIEW_REQUIRED"
        self.assertEqual(
            self.profile.as_dict()["candidates"][0]["profile_state"],
            "EXPERIMENTAL_PRIORITY",
        )

    def test_noncanonical_bytes_are_refused_after_validation(self):
        payload = self.profile.as_dict()
        variants = {
            "indented": json.dumps(payload, sort_keys=True, indent=2).encode("utf-8"),
            "unsorted": json.dumps(payload, sort_keys=False, separators=(",", ":")).encode("utf-8"),
            "trailing_newline": canon(payload) + b"\n",
            "byte_order_mark": b"\xef\xbb\xbf" + canon(payload),
        }
        for name, data in variants.items():
            with self.subTest(variant=name):
                with self.assertRaises(Error) as caught:
                    m.Layer2InitialTriageProfile.from_json_bytes(data)
                self.assertEqual(caught.exception.code, "NON_CANONICAL_BYTES")

    def test_a_structural_fault_outranks_noncanonical_bytes(self):
        payload = copy.deepcopy(self.profile.as_dict())
        payload["profile_id"] = ""
        data = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
        with self.assertRaises(Error) as caught:
            m.Layer2InitialTriageProfile.from_json_bytes(data)
        self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")
        self.assertEqual(caught.exception.field, "/profile_id")

    def test_unknown_and_missing_keys_are_refused(self):
        payload = copy.deepcopy(self.profile.as_dict())
        payload["extra"] = "x"
        with self.assertRaises(Error) as caught:
            m.Layer2InitialTriageProfile.from_dict(payload)
        self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")
        payload = copy.deepcopy(self.profile.as_dict())
        del payload["relation"]
        with self.assertRaises(Error) as caught:
            m.Layer2InitialTriageProfile.from_dict(payload)
        self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")

    def test_modified_document_constants_are_refused(self):
        for key in ("document_type", "non_claim"):
            with self.subTest(key=key):
                payload = copy.deepcopy(self.profile.as_dict())
                payload[key] = "modified"
                with self.assertRaises(Error) as caught:
                    m.Layer2InitialTriageProfile.from_dict(payload)
                self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")

    def test_the_error_exposes_code_field_index_and_message(self):
        payload = copy.deepcopy(self.profile.as_dict())
        payload["candidates"][1]["profile_state"] = "WINNER"
        with self.assertRaises(Error) as caught:
            m.Layer2InitialTriageProfile.from_dict(payload)
        self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")
        self.assertEqual(caught.exception.field, "/candidates/1/profile_state")
        self.assertEqual(caught.exception.index, 1)
        self.assertTrue(caught.exception.message)

    def test_rendering_restates_the_profile_without_new_claims(self):
        lines = m.render_profile_lines(self.profile)
        self.assertEqual(lines[0], m.TRIAGE_NON_CLAIM)
        self.assertIn("relation scope: COHORT_WIDE", lines)
        self.assertIn("  position 1: c1", lines)


# ================================================================================
# 9. Isolation
# ================================================================================


class Isolation(unittest.TestCase):
    def test_only_the_allowed_standard_library_modules_are_imported(self):
        names = {
            value.__name__
            for value in vars(m).values()
            if getattr(value, "__class__", None).__name__ == "module"
        }
        self.assertEqual(names, {"json"})

    def imported_modules(self):
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
        return modules

    def test_no_filesystem_clock_process_or_network_module_is_imported(self):
        for banned in (
            "os", "io", "pathlib", "socket", "subprocess", "datetime", "time",
            "random", "urllib", "urllib.request", "shutil", "tempfile",
        ):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, self.imported_modules())

    def test_no_reader_or_process_name_is_called(self):
        """Swept over resolved call names, so contract prose is never mistaken for code."""
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = node.func
                called.add(target.id if isinstance(target, ast.Name) else getattr(target, "attr", ""))
        for banned in ("open", "eval", "exec", "compile", "__import__", "read_text",
                       "read_bytes", "glob", "listdir", "walk", "urlopen", "Popen", "run"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, called)

    def test_the_module_imports_no_layer_module(self):
        for banned in ("gotne", "layer_2a_descriptor_input", "layer_2b_descriptor_input",
                       "cassette_candidate_priority", "structure_audit"):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, self.imported_modules())


# ================================================================================
# 10. Frozen cohort-identity carriers
# ================================================================================


class FrozenCarriers(unittest.TestCase):
    """Each declaration is verified against one carrier only, by exact equality."""

    def gate3(self, profile, candidate_id="c1"):
        return gates_of(profile, candidate_id)["COHORT_COMPARABILITY"]

    def test_the_target_carrier_is_the_collective_target_site_declaration(self):
        odd = candidate("c1")
        odd.collective_document["scope"]["target_site_declaration"] = TARGET + "x"
        profile = build((odd, candidate("c2", "2.0", "2.0")))
        self.assertEqual(self.gate3(profile), ("FAILED", "TARGET_SYSTEM_IDENTITY_MISMATCH"))

    def test_a_participant_identity_reference_is_not_a_target_carrier(self):
        odd = candidate("c1")
        odd.collective_document["scope"]["target_site_declaration"] = "other"
        odd.collective_document["scope"]["participants"] = [
            {"participant_id": "p", "role": "RECEPTOR", "identity_reference": TARGET}
        ]
        profile = build((odd, candidate("c2", "2.0", "2.0")))
        self.assertEqual(self.gate3(profile), ("FAILED", "TARGET_SYSTEM_IDENTITY_MISMATCH"))

    def test_the_basis_carrier_is_the_collective_scenario_id(self):
        odd = candidate("c1", scenario_id="other-scenario")
        profile = build((odd, candidate("c2", "2.0", "2.0")))
        self.assertEqual(self.gate3(profile), ("FAILED", "LAYER1_COMPARISON_BASIS_MISMATCH"))

    def test_an_evaluation_run_ref_is_not_a_basis_fallback(self):
        odd = candidate("c1", scenario_id="other-scenario")
        odd.collective_document["candidate_anchor"]["evaluation_run_ref"] = BASIS
        profile = build((odd, candidate("c2", "2.0", "2.0")))
        self.assertEqual(self.gate3(profile), ("FAILED", "LAYER1_COMPARISON_BASIS_MISMATCH"))

    def test_the_task_carrier_is_the_assembly_task_declaration_by_exact_text(self):
        odd = candidate("c1", task=TASK.upper())
        profile = build((odd, candidate("c2", "2.0", "2.0")))
        self.assertEqual(self.gate3(profile), ("FAILED", "COLLECTIVE_TASK_SCOPE_MISMATCH"))

    def test_the_ordered_roles_carrier_is_the_collective_local_association_order(self):
        odd = candidate("c1", associations=("slot_2", "slot_1", "slot_3"))
        profile = build((odd, candidate("c2", "2.0", "2.0")))
        self.assertEqual(self.gate3(profile), ("FAILED", "ORDERED_LOCAL_ROLES_MISMATCH"))
        self.assertEqual(states_of(profile)["c1"], "COMPARISON_UNSUPPORTED")

    def test_absent_local_associations_are_never_synthesized(self):
        odd = candidate("c1")
        del odd.collective_document["scope"]["local_associations"]
        profile = build((odd, candidate("c2", "2.0", "2.0")))
        self.assertEqual(self.gate3(profile), ("FAILED", "ORDERED_LOCAL_ROLES_MISMATCH"))

    def test_a_missing_association_position_is_a_mismatch(self):
        odd = candidate("c1", associations=("slot_1", "slot_2"))
        profile = build((odd, candidate("c2", "2.0", "2.0")))
        self.assertEqual(self.gate3(profile), ("FAILED", "ORDERED_LOCAL_ROLES_MISMATCH"))

    def test_the_convention_version_is_carried_only_by_the_declaration(self):
        declaration = cohort(triage_convention_version="layer_2_initial_triage/0")
        carrier = candidate("c1")
        carrier.collective_document["scope"]["triage_convention_version"] = (
            m.TRIAGE_CONVENTION_VERSION
        )
        profile = build((carrier, candidate("c2", "2.0", "2.0")), declaration=declaration)
        self.assertEqual(self.gate3(profile), ("FAILED", "CONVENTION_VERSION_MISMATCH"))


# ================================================================================
# 11. Frozen collective-scope gate
# ================================================================================


class CollectiveScopeGate(unittest.TestCase):
    def assert_incomplete(self, **kwargs):
        profile = build(
            (candidate("c1", **kwargs), candidate("c2", "2.0", "2.0")),
            priority=priority_document(ranked=(("c1", TIER1), ("c2", TIER1))),
        )
        self.assertEqual(
            gates_of(profile, "c1")["COLLECTIVE_SCOPE"],
            ("FAILED", "COLLECTIVE_SCOPE_INCOMPLETE"),
        )
        self.assertEqual(states_of(profile)["c1"], "REVIEW_REQUIRED")
        self.assertEqual(
            gates_of(profile, "c1")["REQUIRED_COLLECTIVE_EVIDENCE"], ("NOT_EVALUATED", None)
        )

    def test_an_absent_joint_frame_fails_the_gate(self):
        self.assert_incomplete(joint_frame=False)

    def test_an_absent_connection_fails_the_gate(self):
        self.assert_incomplete(connections=False)

    def test_an_absent_anchor_element_fails_the_gate(self):
        self.assert_incomplete(elements=("LINKER",))

    def test_an_absent_linker_element_fails_the_gate(self):
        self.assert_incomplete(elements=("ANCHOR",))

    def test_a_complete_scope_passes_the_gate(self):
        profile = build((candidate("c1"), candidate("c2", "2.0", "2.0")))
        self.assertEqual(gates_of(profile, "c1")["COLLECTIVE_SCOPE"], ("PASSED", None))


# ================================================================================
# 12. Terminal gate-to-profile mapping
# ================================================================================


class TerminalGateMapping(unittest.TestCase):
    def outcome(self, subject, priority=None, declaration=None):
        profile = build(
            (subject, candidate("c2", "2.0", "2.0")),
            priority=priority or priority_document(),
            declaration=declaration,
        )
        entry = next(item for item in profile.candidates if item.candidate_id == "c1")
        failed = next(
            (item for item in entry.gates if item.disposition == "FAILED"), None
        )
        return (None if failed is None else (failed.gate, failed.reason), entry.profile_state)

    def test_gate_1_identity_is_comparison_unsupported(self):
        odd = candidate("c1")
        odd.collective_document["candidate_anchor"]["candidate_id"] = "other"
        self.assertEqual(
            self.outcome(odd),
            (("IDENTITY_PROVENANCE", "CANDIDATE_IDENTITY_MISMATCH"), "COMPARISON_UNSUPPORTED"),
        )

    def test_gate_2_layer1_exclusion_is_not_prioritized_by_profile(self):
        self.assertEqual(
            self.outcome(
                candidate("c1"),
                priority=priority_document(
                    ranked=(("c2", TIER1),), excluded=(("c1", "STATE_NOT_VALID"),)
                ),
            ),
            (("LAYER1_BOUNDARY", "LAYER1_EXCLUDED"), "NOT_PRIORITIZED_BY_PROFILE"),
        )

    def test_gate_2_absence_is_comparison_unsupported(self):
        self.assertEqual(
            self.outcome(candidate("c1"), priority=priority_document(ranked=(("c2", TIER1),))),
            (("LAYER1_BOUNDARY", "LAYER1_ENTRY_ABSENT"), "COMPARISON_UNSUPPORTED"),
        )

    def test_gate_3_mismatch_is_comparison_unsupported(self):
        for label, subject in (
            ("target", candidate("c1", target="other")),
            ("basis", candidate("c1", scenario_id="other")),
            ("task", candidate("c1", task="other")),
            ("roles", candidate("c1", associations=("slot_3", "slot_2", "slot_1"))),
        ):
            with self.subTest(carrier=label):
                gate, state = self.outcome(subject)
                self.assertEqual(gate[0], "COHORT_COMPARABILITY")
                self.assertEqual(state, "COMPARISON_UNSUPPORTED")

    def test_gate_4_incomplete_scope_is_review_required(self):
        self.assertEqual(
            self.outcome(candidate("c1", connections=False)),
            (("COLLECTIVE_SCOPE", "COLLECTIVE_SCOPE_INCOMPLETE"), "REVIEW_REQUIRED"),
        )

    def test_gate_5_absent_evidence_is_review_required(self):
        self.assertEqual(
            self.outcome(candidate("c1", interference=None, burden=None)),
            (
                ("REQUIRED_COLLECTIVE_EVIDENCE", "REQUIRED_COLLECTIVE_EVIDENCE_ABSENT"),
                "REVIEW_REQUIRED",
            ),
        )

    def test_gate_5_non_qualifying_evidence_is_review_required(self):
        subject = candidate("c1")
        for descriptor in subject.collective_document["descriptors"]:
            descriptor["conditions"] = ["UNAVAILABLE"]
        self.assertEqual(
            self.outcome(subject),
            (
                ("REQUIRED_COLLECTIVE_EVIDENCE", "REQUIRED_COLLECTIVE_EVIDENCE_ABSENT"),
                "REVIEW_REQUIRED",
            ),
        )

    def test_gate_6_without_a_common_dimension_is_comparison_unsupported(self):
        self.assertEqual(
            self.outcome(
                candidate("c1"),
                declaration=cohort(
                    directions=(
                        "NO_DIRECTION_DECLARED",
                        "NO_DIRECTION_DECLARED",
                        "NO_DIRECTION_DECLARED",
                    )
                ),
            ),
            (
                ("COMMON_ACTIVE_DIMENSIONS", "NO_COMMON_ACTIVE_DIMENSION"),
                "COMPARISON_UNSUPPORTED",
            ),
        )

    def test_only_the_first_failed_gate_is_terminal(self):
        subject = candidate("c1", target="other", connections=False)
        gate, state = self.outcome(subject)
        self.assertEqual(gate, ("COHORT_COMPARABILITY", "TARGET_SYSTEM_IDENTITY_MISMATCH"))
        self.assertEqual(state, "COMPARISON_UNSUPPORTED")
        profile = build((subject, candidate("c2", "2.0", "2.0")))
        self.assertEqual(
            gates_of(profile, "c1")["COLLECTIVE_SCOPE"], ("NOT_EVALUATED", None)
        )


if __name__ == "__main__":
    unittest.main()
