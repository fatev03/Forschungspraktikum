"""Tests for analytic_proxy.

Every Phase 2 input comes from fixtures/phase2_examples.json, which
make_phase2_examples.py produces through GOTNE's public API. Engagement counts
in the fixture: S0 0; S1, S2, S3 1; S12, S13, S23 2; S123 3 (all VALID). V14
(2) and V124 (3) are closure vetoes, G19 (1) is INFEASIBLE, M12_marginalized
(2) is DEGENERATE. *_context_b share targets with context A but not its
tolerances, so their context_hash differs. S2_config_b (1, VALID) is S2 under a
second configuration: same state_hash and context_hash as S2, a different
result_id, and a certificate with a different config_identity_hash.

Run: python -m unittest discover -s analytic_proxy/tests -t .
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import math
import pathlib
import random
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError, replace

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from analytic_proxy import (  # noqa: E402
    SCHEMA_VERSION,
    ExclusionRecord,
    ScenarioParameters,
    ScenarioSummary,
    StateInput,
    StateWeight,
    compute_state_weights,
    eligible_states,
    normalize_weights,
    summarize_scenario,
)

PACKAGE = ROOT / "analytic_proxy"
FIXTURE = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "phase2_examples.json")
                     .read_text(encoding="utf-8"))
RESULTS, CERTIFICATES = FIXTURE["state_results"], FIXTURE["certificates"]
VALID_NAMES = ("S0", "S1", "S2", "S3", "S12", "S13", "S23", "S123")
CONFIG_A = CERTIFICATES["S1"]["config_identity_hash"]
CONFIG_B = CERTIFICATES["S2_config_b"]["config_identity_hash"]
#: Terms the package must never emit; the first is assembled so this file stays free of it.
BANNED_WORDS = ("occu" + "pancy", "affinity", "probability", "kinetic", "residence")


def state_hash(name):
    return RESULTS[name]["upstream_state"]["state_hash"]


def candidate(name, certificate=False):
    return StateInput.from_serialized(RESULTS[name], CERTIFICATES[name] if certificate else None)


def certificate_only(name):
    return StateInput.from_serialized(certificate=CERTIFICATES[name])


def parameters(values, names=("scale",), scenario_id="scenario-1"):
    """values: fixture name -> factor mapping (or a single number for one-factor scenarios)."""
    factors = {state_hash(n): (v if isinstance(v, dict) else {names[0]: v}) for n, v in values.items()}
    return ScenarioParameters(scenario_id, names, factors)


def summary_json(summary):
    return json.dumps(summary.as_dict(), sort_keys=True, allow_nan=False)


class Fixture(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("gotne"), "gotne is not importable here")
    def test_fixture_is_current_phase2_output(self):
        from analytic_proxy.tests import make_phase2_examples

        self.assertEqual(json.loads(make_phase2_examples.render(make_phase2_examples.build())), FIXTURE)

    def test_fixture_statuses(self):
        expected = {name: ("VALID", "STATE_NOT_VETOED") for name in VALID_NAMES + ("S2_context_b", "S2_config_b")}
        expected.update(V14=("UNREACHABLE", "CHAIN_CLOSURE_VIOLATED"), V124=("UNREACHABLE", "CHAIN_CLOSURE_VIOLATED"),
                        V14_context_b=("UNREACHABLE", "CHAIN_CLOSURE_VIOLATED"),
                        G19=("INFEASIBLE", "GEOMETRY_INPUT_INVALID"),
                        M12_marginalized=("DEGENERATE", "ENGAGED_POSE_UNDERDETERMINED"))
        self.assertEqual({n: (r["status"], r["status_reason"]) for n, r in RESULTS.items()}, expected)
        self.assertEqual(set(CERTIFICATES), set(VALID_NAMES) | {"S2_context_b", "S2_config_b"})
        self.assertEqual({CERTIFICATES[n]["config_identity_hash"] for n in CERTIFICATES if n != "S2_config_b"},
                         {CONFIG_A})
        self.assertNotEqual(CONFIG_B, CONFIG_A)


# --------------------------------------------------------------------------
# StateInput
# --------------------------------------------------------------------------
class StateInputParsing(unittest.TestCase):
    def test_from_state_result(self):
        c = candidate("S123")
        self.assertEqual((c.state_hash, c.result_id), (state_hash("S123"), RESULTS["S123"]["result_id"]))
        self.assertEqual(c.context_hash, RESULTS["S123"]["upstream_state"]["context_hash"])
        self.assertEqual((c.phase2_status, c.phase2_status_reason), ("VALID", "STATE_NOT_VETOED"))
        self.assertEqual((c.engaged_modules, c.engagement_count), (("D1", "D2", "D3"), 3))
        self.assertEqual((c.has_state_result, c.has_certificate), (True, False))
        self.assertEqual(candidate("S0").engagement_count, 0)

    def test_with_matching_certificate(self):
        with_certificate = candidate("S12", certificate=True)
        self.assertTrue(with_certificate.has_certificate)
        self.assertEqual(replace(with_certificate, has_certificate=False, config_identity_hash=None), candidate("S12"))

    def test_certificate_only_has_no_engagement(self):
        c = certificate_only("S3")
        self.assertEqual((c.has_state_result, c.engaged_modules, c.engagement_count, c.phase2_status_reason),
                         (False, None, None, None))
        self.assertEqual(c.state_hash, state_hash("S3"))

    def test_certificate_must_match_its_state_result(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            StateInput.from_serialized(RESULTS["S1"], CERTIFICATES["S2"])
        for key, value in (("state_result_id", RESULTS["S2"]["result_id"]), ("state_hash", state_hash("S2")),
                           ("context_hash", RESULTS["S2_context_b"]["upstream_state"]["context_hash"]),
                           ("status", "UNREACHABLE")):
            tampered = dict(CERTIFICATES["S1"], **{key: value})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "does not match"):
                StateInput.from_serialized(RESULTS["S1"], tampered)

    def test_malformed_serializations_rejected(self):
        base = RESULTS["S12"]

        def edit(**changes):
            data = copy.deepcopy(base)
            data.update(changes)
            return data

        upstream = base["upstream_state"]
        cases = {
            "NODE result": edit(object_kind="NODE"),
            "CONFIG result": edit(object_kind="CONFIG"),
            "missing upstream_state": {k: v for k, v in base.items() if k != "upstream_state"},
            "missing status": {k: v for k, v in base.items() if k != "status"},
            "bad result_id": edit(result_id="st-0007"),
            "node result id": edit(result_id="nd-" + "a" * 64),
            "unknown status": edit(status="MAYBE"),
            "empty reason": edit(status_reason=""),
            "object_id mismatch": edit(object_id="S:" + "0" * 64),
            "bad state hash": edit(upstream_state=dict(upstream, state_hash="xyz")),
            "assignments not an object": edit(upstream_state=dict(upstream, assignments=["D1"])),
            "unknown label": edit(upstream_state=dict(upstream, assignments={"D1": {"label": "BOUND", "target_id": "t1"}})),
            "not a mapping": ["STATE"],
        }
        for label, data in cases.items():
            with self.subTest(case=label), self.assertRaises(ValueError):
                StateInput.from_serialized(data)
        with self.assertRaises(ValueError):
            StateInput.from_serialized()
        with self.assertRaises(ValueError):
            StateInput.from_serialized(certificate={k: v for k, v in CERTIFICATES["S1"].items() if k != "state_hash"})

    def test_unengaged_entries_are_not_counted(self):
        data = copy.deepcopy(RESULTS["S12"])
        data["upstream_state"]["assignments"]["D3"] = {"label": "UNENGAGED", "target_id": None}
        self.assertEqual(StateInput.from_serialized(data).engaged_modules, ("D1", "D2"))

    def test_inputs_not_mutated_and_json_round_trip_equal(self):
        before = copy.deepcopy(FIXTURE)
        direct = candidate("S23", certificate=True)
        self.assertEqual(FIXTURE, before)
        round_tripped = StateInput.from_serialized(json.loads(json.dumps(RESULTS["S23"])),
                                                   json.loads(json.dumps(CERTIFICATES["S23"])))
        self.assertEqual(direct, round_tripped)
        self.assertEqual(json.loads(json.dumps(direct.as_dict()))["engagement_count"], 2)

    def test_frozen(self):
        c = candidate("S1")
        with self.assertRaises(FrozenInstanceError):
            c.phase2_status = "INFEASIBLE"


# --------------------------------------------------------------------------
# Eligibility
# --------------------------------------------------------------------------
class Eligibility(unittest.TestCase):
    def test_only_valid_not_vetoed_states_with_assignments(self):
        submitted = [candidate(n) for n in ("S1", "S12", "V14", "V124", "G19")] + [certificate_only("S3")]
        eligible, exclusions = eligible_states(submitted)
        self.assertEqual({c.state_hash for c in eligible}, {state_hash("S1"), state_hash("S12")})
        records = {e.state_hash: e for e in exclusions}
        self.assertEqual(records[state_hash("V14")].as_dict(), {
            "state_hash": state_hash("V14"), "result_id": RESULTS["V14"]["result_id"],
            "reason": "PHASE2_STATUS_NOT_VALID", "phase2_status": "UNREACHABLE",
            "phase2_status_reason": "CHAIN_CLOSURE_VIOLATED", "engagement_count": 2})
        self.assertEqual(records[state_hash("G19")].reason, ExclusionRecord.PHASE2_STATUS_NOT_VALID)
        self.assertEqual(records[state_hash("V124")].engagement_count, 3)
        self.assertEqual((records[state_hash("S3")].reason, records[state_hash("S3")].engagement_count),
                         (ExclusionRecord.ENGAGEMENT_ASSIGNMENTS_UNAVAILABLE, None))
        degenerate = eligible_states([candidate("M12_marginalized")])[1][0]
        self.assertEqual((degenerate.reason, degenerate.phase2_status), ("PHASE2_STATUS_NOT_VALID", "DEGENERATE"))

    def test_valid_with_a_veto_reason_is_excluded(self):
        tampered = StateInput.from_serialized(dict(RESULTS["S1"], status_reason="CHAIN_CLOSURE_VIOLATED"))
        (record,) = eligible_states([tampered])[1]
        self.assertEqual(record.reason, ExclusionRecord.PHASE2_VETO_REASON_PRESENT)

    def test_ordering_ignores_submission_order(self):
        submitted = [candidate(n) for n in VALID_NAMES + ("V14", "G19")]
        expected = eligible_states(submitted)
        rng = random.Random(20260925)
        for _ in range(20):
            shuffled = rng.sample(submitted, len(submitted))
            self.assertEqual(eligible_states(shuffled), expected)
        self.assertEqual([c.state_hash for c in expected[0]], sorted(c.state_hash for c in expected[0]))

    def test_duplicates_rejected(self):
        for names in (("S1", "S1"), ("S12", "M12_marginalized"), ("S2", "S2_context_b"), ("S2", "S2_config_b")):
            with self.subTest(names=names), self.assertRaisesRegex(ValueError, "duplicate"):
                eligible_states([candidate(n) for n in names])
        with self.assertRaisesRegex(ValueError, "duplicate state_hash"):  # distinct result ids
            eligible_states([candidate("S2"), candidate("S2_context_b")])
        with self.assertRaisesRegex(ValueError, "duplicate result_id"):  # a certificate carries its result id
            eligible_states([candidate("S3"), certificate_only("S3")])

    def test_eligible_states_share_one_context(self):
        with self.assertRaisesRegex(ValueError, "different contexts"):
            eligible_states([candidate("S1"), candidate("S2_context_b")])
        eligible, exclusions = eligible_states([candidate("S1"), candidate("V14_context_b")])  # excluded may differ
        self.assertEqual((len(eligible), len(exclusions)), (1, 1))

    def test_argument_types(self):
        for bad in ({"S1": candidate("S1")}, candidate("S1"), [RESULTS["S1"]]):
            with self.assertRaises(TypeError):
                eligible_states(bad)


# --------------------------------------------------------------------------
# Scenario parameters
# --------------------------------------------------------------------------
class ScenarioParametersValidation(unittest.TestCase):
    def test_normalized_storage(self):
        p = ScenarioParameters("scn", ["b", "a"], {state_hash("S2"): {"b": 2, "a": 0.5}, state_hash("S1"): {"a": 1, "b": 1}})
        self.assertEqual(p.factor_names, ("a", "b"))
        self.assertEqual([key for key, _ in p.state_factors], sorted([state_hash("S1"), state_hash("S2")]))
        self.assertEqual(p.factors_for(state_hash("S2")), (("a", 0.5), ("b", 2.0)))
        self.assertIsNone(p.factors_for(state_hash("S3")))
        pairs = ScenarioParameters("scn", ("a", "b"), [(state_hash("S1"), [("b", 1), ("a", 1)]),
                                                        (state_hash("S2"), {"a": 0.5, "b": 2})])
        self.assertEqual(pairs, p)
        self.assertEqual(json.loads(json.dumps(p.as_dict()))["state_factors"][state_hash("S2")], {"a": 0.5, "b": 2.0})

    def test_factor_values_finite_non_negative(self):
        for bad in (-1.0, -1e-300, math.nan, math.inf, -math.inf, True, "1", None, 10**400, [1.0]):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                parameters({"S1": bad})
        self.assertEqual(parameters({"S1": 0}).factors_for(state_hash("S1")), (("scale", 0.0),))

    def test_missing_and_undeclared_factors(self):
        with self.assertRaisesRegex(ValueError, "missing declared factors"):
            parameters({"S1": {"a": 1.0}}, names=("a", "b"))
        with self.assertRaisesRegex(ValueError, "undeclared factors"):
            parameters({"S1": {"a": 1.0, "c": 1.0}}, names=("a",))

    def test_factor_names(self):
        for names in ((), ["a", "a"], ["Scale"], ["1x"], ["a-b"], [""], [3]):
            with self.subTest(names=names), self.assertRaises(ValueError):
                ScenarioParameters("scn", names, {})
        for reserved in ("affinity", "binding_probability", "residence_time", "kinetic_constant", "x_" + BANNED_WORDS[0]):
            with self.subTest(name=reserved), self.assertRaisesRegex(ValueError, "reserved term"):
                ScenarioParameters("scn", [reserved], {})

    def test_state_keys_and_scenario_id(self):
        for factors in ({"not-a-hash": {"scale": 1.0}}, [(state_hash("S1"), {"scale": 1}), (state_hash("S1"), {"scale": 2})],
                        "scale=1"):
            with self.assertRaises(ValueError):
                ScenarioParameters("scn", ("scale",), factors)
        for scenario_id in ("", None, 7):
            with self.assertRaises(ValueError):
                ScenarioParameters(scenario_id, ("scale",), {})

    def test_caller_mapping_copied_not_mutated(self):
        factors = {state_hash("S1"): {"scale": 2.0}}
        snapshot = copy.deepcopy(factors)
        p = ScenarioParameters("scn", ["scale"], factors)
        self.assertEqual(factors, snapshot)
        factors[state_hash("S1")]["scale"] = 5.0
        self.assertEqual(p.factors_for(state_hash("S1")), (("scale", 2.0),))
        with self.assertRaises(FrozenInstanceError):
            p.scenario_id = "other"


# --------------------------------------------------------------------------
# Conditional weights and normalization
# --------------------------------------------------------------------------
class Weights(unittest.TestCase):
    def test_product_of_declared_factors(self):
        p = parameters({"S1": {"a": 2.0, "b": 0.5, "c": 3.0}}, names=("c", "a", "b"))
        (weight,) = compute_state_weights([candidate("S1")], p)
        self.assertEqual(weight.conditional_weight, 3.0)
        self.assertEqual(weight.factors, (("a", 2.0), ("b", 0.5), ("c", 3.0)))
        self.assertIsNone(weight.normalized_fraction)

    def test_zero_factor_gives_zero_weight(self):
        (weight,) = compute_state_weights([candidate("S1")], parameters({"S1": {"a": 4.0, "b": 0.0}}, names=("a", "b")))
        self.assertEqual(weight.conditional_weight, 0.0)

    def test_ineligible_or_unparameterized_states_get_no_weight(self):
        p = parameters({"V14": 1.0, "S1": 1.0})
        for c in (candidate("V14"), certificate_only("S3"), candidate("G19")):
            with self.subTest(state=c.phase2_status), self.assertRaisesRegex(ValueError, "not eligible"):
                compute_state_weights([c], p)
        with self.assertRaisesRegex(ValueError, "no factors supplied"):
            compute_state_weights([candidate("S2")], p)

    def test_non_finite_product_rejected(self):
        with self.assertRaisesRegex(ValueError, "not finite"):
            compute_state_weights([candidate("S1")], parameters({"S1": {"a": 1e200, "b": 1e200}}, names=("a", "b")))

    def test_state_weight_consistency(self):
        (weight,) = compute_state_weights([candidate("S1")], parameters({"S1": 2.0}))
        for change in (dict(conditional_weight=3.0), dict(normalized_fraction=1.5), dict(normalized_fraction=1),
                       dict(factors=())):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(weight, **change)

    def test_normalization(self):
        p = parameters({"S1": 1.0, "S2": 1.0, "S12": 2.0})
        weights = normalize_weights(compute_state_weights([candidate(n) for n in ("S12", "S2", "S1")], p))
        self.assertEqual({w.state_hash: w.normalized_fraction for w in weights},
                         {state_hash("S1"): 0.25, state_hash("S2"): 0.25, state_hash("S12"): 0.5})
        self.assertEqual(math.fsum(w.normalized_fraction for w in weights), 1.0)
        self.assertEqual([w.state_hash for w in weights], sorted(w.state_hash for w in weights))

    def test_zero_total_is_not_normalized(self):
        zero = compute_state_weights([candidate("S1"), candidate("S2")], parameters({"S1": 0.0, "S2": 0.0}))
        self.assertEqual([w.normalized_fraction for w in normalize_weights(zero)], [None, None])
        self.assertEqual(normalize_weights(()), ())
        with self.assertRaisesRegex(ValueError, "duplicate"):
            normalize_weights(zero + zero[:1])


# --------------------------------------------------------------------------
# Scenario summary
# --------------------------------------------------------------------------
ALL_ELIGIBLE = {"S0": 1.0, "S1": 1.0, "S2": 1.0, "S12": 1.0, "S13": 1.0, "S23": 1.0, "S123": 2.0}


def full_scenario(values=None, extra_factors=None):
    submitted = [candidate(n) for n in ALL_ELIGIBLE] + [candidate(n) for n in ("V14", "V124", "G19")]
    submitted.append(certificate_only("S3"))
    return submitted, parameters({**(values or ALL_ELIGIBLE), **(extra_factors or {})})


class Summary(unittest.TestCase):
    def test_counts_groups_and_fractions(self):
        summary = summarize_scenario(*full_scenario())
        self.assertEqual((summary.candidate_count, summary.eligible_count, summary.excluded_count), (11, 7, 4))
        self.assertEqual(summary.normalization_status, ScenarioSummary.NORMALIZED)
        self.assertIsNone(summary.normalization_reason)
        self.assertEqual(summary.total_conditional_weight, 8.0)
        self.assertEqual(dict(summary.fractions_by_engagement_count), {"0": 0.125, "1": 0.25, "2": 0.375, "3+": 0.25})
        self.assertEqual(summary.fraction_engaged_at_least_2, 0.625)
        self.assertEqual((summary.fully_engaged_count, summary.fraction_fully_engaged), (3, 0.25))
        per_state = {w.state_hash: (w.conditional_weight, w.normalized_fraction) for w in summary.weights}
        self.assertEqual(per_state[state_hash("S123")], (2.0, 0.25))
        self.assertEqual(per_state[state_hash("S0")], (1.0, 0.125))
        self.assertEqual(dict(summary.provenance["exclusion_reason_counts"]),
                         {"PHASE2_STATUS_NOT_VALID": 3, "ENGAGEMENT_ASSIGNMENTS_UNAVAILABLE": 1})

    def test_fully_engaged_counts_excluded_candidates(self):
        summary = summarize_scenario([candidate("S1"), candidate("S12"), candidate("V124")],
                                     parameters({"S1": 1.0, "S12": 1.0}))
        self.assertEqual(summary.fully_engaged_count, 3)
        self.assertEqual(summary.fraction_fully_engaged, 0.0)
        self.assertEqual(summary.fraction_engaged_at_least_2, 0.5)
        unreadable = summarize_scenario([candidate("S1"), certificate_only("S12")], parameters({"S1": 1.0}))
        self.assertEqual((unreadable.fully_engaged_count, unreadable.fraction_fully_engaged), (1, 1.0))

    def test_zero_total_summary(self):
        summary = summarize_scenario(*full_scenario({n: 0.0 for n in ALL_ELIGIBLE}))
        self.assertEqual(summary.normalization_status, ScenarioSummary.NOT_NORMALIZED_ZERO_TOTAL)
        self.assertEqual(summary.normalization_reason, "total conditional weight is zero")
        self.assertEqual(summary.total_conditional_weight, 0.0)
        self.assertEqual(summary.eligible_count, 7)
        self.assertTrue(all(w.normalized_fraction is None for w in summary.weights))
        self.assertIsNone(summary.fractions_by_engagement_count)
        self.assertIsNone(summary.fraction_engaged_at_least_2)
        self.assertIsNone(summary.fraction_fully_engaged)
        self.assertEqual(summary.fully_engaged_count, 3)
        json.loads(summary_json(summary))

    def test_no_eligible_state_summary(self):
        summary = summarize_scenario([candidate("V124"), candidate("G19")], parameters({"V124": 1.0}))
        self.assertEqual(summary.normalization_status, ScenarioSummary.NOT_NORMALIZED_NO_ELIGIBLE_STATES)
        self.assertEqual((summary.weights, summary.total_conditional_weight, summary.fully_engaged_count), ((), 0.0, 3))
        self.assertIsNone(summary.provenance["context_hash"])

    def test_vetoed_states_never_enter_normalization(self):
        base = summarize_scenario(*full_scenario(extra_factors={"V14": 1e6, "V124": 7.0, "G19": 3.0}))
        other = summarize_scenario(*full_scenario(extra_factors={"V14": 0.0, "V124": 1e9, "G19": 0.5}))
        self.assertEqual(summary_json(base), summary_json(other))
        self.assertEqual(base.total_conditional_weight, 8.0)
        excluded = {state_hash(n) for n in ("V14", "V124", "G19", "S3")}
        self.assertFalse(excluded & {w.state_hash for w in base.weights})
        self.assertEqual(excluded, {e.state_hash for e in base.exclusions})

    def test_factors_for_unsubmitted_state_rejected(self):
        with self.assertRaisesRegex(ValueError, "not submitted"):
            summarize_scenario([candidate("S1")], parameters({"S1": 1.0, "S2": 1.0}))
        with self.assertRaisesRegex(ValueError, "no factors supplied"):
            summarize_scenario([candidate("S1"), candidate("S2")], parameters({"S1": 1.0}))

    def test_provenance(self):
        summary = summarize_scenario(*full_scenario())
        provenance = summary.as_dict()["provenance"]
        self.assertEqual(provenance["schema_version"], SCHEMA_VERSION)
        self.assertEqual(provenance["scenario_id"], "scenario-1")
        self.assertEqual(provenance["factor_names"], ["scale"])
        self.assertEqual(provenance["engagement_groups"], ["0", "1", "2", "3+"])
        self.assertEqual(provenance["normalization_status"], "NORMALIZED")
        self.assertEqual(provenance["fully_engaged_count"], 3)
        self.assertIn("including excluded candidates", provenance["fully_engaged_rule"])
        self.assertIn("ascending state_hash", provenance["input_ordering_rule"])
        self.assertIn("STATE_NOT_VETOED", provenance["eligibility_rule"])
        self.assertEqual(provenance["context_hash"], RESULTS["S1"]["upstream_state"]["context_hash"])
        self.assertEqual(provenance["config_identity_validation_status"], "CONFIG_IDENTITY_VALIDATION_NOT_PERFORMED")
        self.assertEqual(provenance["eligible_config_identity_hashes"], [])
        for key in ("scope", "weight_rule", "engagement_count_rule", "normalization_reason", "exclusion_reason_counts"):
            self.assertIn(key, provenance)

    def test_deterministic_and_json_stable(self):
        submitted, p = full_scenario()
        expected = summary_json(summarize_scenario(submitted, p))
        rng = random.Random(7)
        for _ in range(20):
            self.assertEqual(summary_json(summarize_scenario(rng.sample(submitted, len(submitted)), p)), expected)
        data = json.loads(expected)
        self.assertEqual(json.loads(json.dumps(data, sort_keys=True)), data)
        self.assertEqual(summary_json(summarize_scenario(submitted, p)), expected)

    def test_inputs_not_mutated_and_summary_frozen(self):
        before, fixture_before = copy.deepcopy(ALL_ELIGIBLE), copy.deepcopy(FIXTURE)
        submitted, p = full_scenario()
        order = list(submitted)
        summary = summarize_scenario(submitted, p)
        self.assertEqual((ALL_ELIGIBLE, FIXTURE, submitted), (before, fixture_before, order))
        with self.assertRaises(FrozenInstanceError):
            summary.total_conditional_weight = 0.0
        with self.assertRaises(TypeError):
            summary.provenance["scenario_id"] = "x"

    def test_vocabulary(self):
        text = summary_json(summarize_scenario(*full_scenario())).lower()
        for word in BANNED_WORDS:
            self.assertNotIn(word, text)
        for path in (PACKAGE / "core.py", PACKAGE / "__init__.py"):
            self.assertNotIn(BANNED_WORDS[0], path.read_text(encoding="utf-8").lower(), path.name)


# --------------------------------------------------------------------------
# Configuration identity
# --------------------------------------------------------------------------
VALIDATED = ScenarioSummary.CONFIG_IDENTITY_VALIDATED
PARTIAL = ScenarioSummary.CONFIG_IDENTITY_VALIDATION_PARTIAL
NOT_PERFORMED = ScenarioSummary.CONFIG_IDENTITY_VALIDATION_NOT_PERFORMED


def vetoed_config_b():
    """S2_config_b's STATE result with a veto reason, given with its own (matching)
    certificate: an excluded candidate that carries CONFIG_B."""
    return StateInput.from_serialized(dict(RESULTS["S2_config_b"], status_reason="CHAIN_CLOSURE_VIOLATED"),
                                      CERTIFICATES["S2_config_b"])


def config_check(summary):
    provenance = summary.provenance
    return provenance["config_identity_validation_status"], provenance["eligible_config_identity_hashes"]


def unit_factors(*names):
    return parameters({n: 1.0 for n in names})


class ConfigIdentity(unittest.TestCase):
    def test_state_input_takes_the_hash_of_a_matching_certificate_only(self):
        self.assertEqual(candidate("S1", certificate=True).config_identity_hash, CONFIG_A)
        self.assertEqual(candidate("S2_config_b", certificate=True).config_identity_hash, CONFIG_B)
        self.assertIsNone(candidate("S1").config_identity_hash)
        only = certificate_only("S2_config_b")
        self.assertEqual((only.has_certificate, only.config_identity_hash), (True, None))
        self.assertEqual(json.loads(json.dumps(candidate("S1", certificate=True).as_dict()))["config_identity_hash"],
                         CONFIG_A)
        self.assertIsNone(json.loads(json.dumps(candidate("S1").as_dict()))["config_identity_hash"])

    def test_non_matching_certificate_hash_is_never_trusted(self):
        # S2 and S2_config_b share state_hash, context_hash and status; only result_id differs
        for result, certificate in (("S2", "S2_config_b"), ("S2_config_b", "S2"), ("S1", "S2_config_b")):
            with self.subTest(result=result, certificate=certificate), \
                    self.assertRaisesRegex(ValueError, "does not match"):
                StateInput.from_serialized(RESULTS[result], CERTIFICATES[certificate])
        for certificate in (dict(CERTIFICATES["S1"], config_identity_hash="xyz"),
                            {k: v for k, v in CERTIFICATES["S1"].items() if k != "config_identity_hash"}):
            with self.assertRaisesRegex(ValueError, "config_identity_hash"):
                StateInput.from_serialized(RESULTS["S1"], certificate)

    def test_state_input_hash_invariant(self):
        certified, bare = candidate("S1", certificate=True), candidate("S1")
        cases = {
            "certificate without hash": lambda: replace(certified, config_identity_hash=None),
            "hash without certificate": lambda: replace(bare, config_identity_hash=CONFIG_A),
            "hash on a certificate-only candidate": lambda: replace(certificate_only("S3"), config_identity_hash=CONFIG_A),
            "malformed hash": lambda: replace(certified, config_identity_hash="xyz"),
        }
        for label, build in cases.items():
            with self.subTest(case=label), self.assertRaises(ValueError):
                build()

    def test_shared_matching_config_hash(self):
        names = ("S0", "S1", "S2", "S12", "S123")
        summary = summarize_scenario([candidate(n, certificate=True) for n in names], unit_factors(*names))
        self.assertEqual(config_check(summary), (VALIDATED, (CONFIG_A,)))
        self.assertIn("all 5 eligible states", summary.provenance["config_identity_validation_reason"])
        only_b = summarize_scenario([candidate("S2_config_b", certificate=True)], unit_factors("S2_config_b"))
        self.assertEqual(config_check(only_b), (VALIDATED, (CONFIG_B,)))

    def test_conflicting_eligible_config_hashes(self):
        cases = {
            "two certified": ["S1", "S2_config_b"],
            "plus uncertified eligible": ["S1", "S2_config_b", "S12"],
            "plus excluded": ["S1", "S2_config_b", "V14"],
        }
        for label, names in cases.items():
            submitted = [candidate(n, certificate=n in ("S1", "S2_config_b")) for n in names]
            for order in (submitted, submitted[::-1]):
                with self.subTest(case=label, reversed=order is not submitted):
                    with self.assertRaisesRegex(ValueError, "2 different config_identity_hash values") as caught:
                        eligible_states(order)
                    self.assertIn(CONFIG_A, str(caught.exception))
                    self.assertIn(CONFIG_B, str(caught.exception))
                    with self.assertRaisesRegex(ValueError, "config_identity_hash"):
                        summarize_scenario(order, unit_factors(*names))

    def test_partial_config_hash_availability(self):
        names = ("S1", "S12", "S2", "S123")
        submitted = [candidate("S1", True), candidate("S12", True), candidate("S2"), candidate("S123")]
        summary = summarize_scenario(submitted, unit_factors(*names))
        self.assertEqual(config_check(summary), (PARTIAL, (CONFIG_A,)))
        reason = summary.provenance["config_identity_validation_reason"]
        self.assertIn("2 of 4 eligible states", reason)
        self.assertIn("unchecked", reason)
        # the unchecked states are not compared: a second configuration among them is not seen
        hidden = summarize_scenario([candidate("S1", True), candidate("S2_config_b")], unit_factors("S1", "S2_config_b"))
        self.assertEqual(config_check(hidden), (PARTIAL, (CONFIG_A,)))

    def test_all_config_hashes_unavailable(self):
        summary = summarize_scenario(*full_scenario())
        self.assertEqual(config_check(summary), (NOT_PERFORMED, ()))
        self.assertIn("unavailable for all 7 eligible states", summary.provenance["config_identity_validation_reason"])
        mixed = summarize_scenario([candidate("S1"), candidate("S2_config_b")], unit_factors("S1", "S2_config_b"))
        self.assertEqual(config_check(mixed), (NOT_PERFORMED, ()))
        none_eligible = summarize_scenario([candidate("V14"), certificate_only("S1")], unit_factors("V14"))
        self.assertEqual(config_check(none_eligible), (NOT_PERFORMED, ()))
        self.assertEqual(none_eligible.provenance["config_identity_validation_reason"], "no eligible state")

    def test_conflicting_hashes_on_excluded_states_have_no_effect(self):
        eligible_a = [candidate(n, certificate=True) for n in ("S1", "S3", "S13")]
        p = parameters({"S1": 1.0, "S3": 2.0, "S13": 1.0})
        reference = summarize_scenario(eligible_a, p)
        self.assertEqual(vetoed_config_b().config_identity_hash, CONFIG_B)
        excluded = {
            "VALID with veto reason, certified": vetoed_config_b(),
            "certificate only": certificate_only("S2_config_b"),
            "not VALID, other context": candidate("V14_context_b"),
        }
        for label, extra in excluded.items():
            with self.subTest(case=label):
                summary = summarize_scenario(eligible_a + [extra], p)
                self.assertEqual(summary.excluded_count, 1)
                for key in ("config_identity_validation_status", "config_identity_validation_reason",
                            "eligible_config_identity_hashes"):
                    self.assertEqual(summary.provenance[key], reference.provenance[key])
                self.assertEqual([w.as_dict() for w in summary.weights], [w.as_dict() for w in reference.weights])
        uncertified = summarize_scenario([candidate("S1"), vetoed_config_b()], unit_factors("S1"))
        self.assertEqual(config_check(uncertified), (NOT_PERFORMED, ()))

    def test_provenance_deterministic_and_json_round_trip(self):
        scenarios = {
            VALIDATED: [candidate(n, True) for n in ("S0", "S1", "S12", "S123")] + [candidate("V14"), vetoed_config_b()],
            PARTIAL: [candidate("S1", True), candidate("S2"), candidate("S23", True), candidate("G19")],
            NOT_PERFORMED: [candidate(n) for n in ("S0", "S13", "V124")] + [certificate_only("S2_config_b")],
        }
        rng = random.Random(20260925)
        for status, submitted in scenarios.items():
            with self.subTest(status=status):
                p = ScenarioParameters("scn", ("scale",), {c.state_hash: {"scale": 1.0} for c in submitted})
                summary = summarize_scenario(submitted, p)
                expected = summary_json(summary)
                for _ in range(10):
                    self.assertEqual(summary_json(summarize_scenario(rng.sample(submitted, len(submitted)), p)), expected)
                self.assertIsInstance(summary.provenance["eligible_config_identity_hashes"], tuple)
                data = json.loads(expected)
                provenance = data["provenance"]
                self.assertEqual(provenance["config_identity_validation_status"], status)
                self.assertIsInstance(provenance["config_identity_validation_reason"], str)
                self.assertEqual(provenance["eligible_config_identity_hashes"],
                                 [] if status == NOT_PERFORMED else [CONFIG_A])
                self.assertEqual(json.loads(json.dumps(data, sort_keys=True, allow_nan=False)), data)
                rebuilt = replace(summary, provenance=provenance)
                self.assertEqual(summary_json(rebuilt), expected)
                self.assertIsInstance(rebuilt.provenance["eligible_config_identity_hashes"], tuple)
        self.assertEqual(SCHEMA_VERSION, "analytic_proxy.scenario_summary/2")
        self.assertEqual((VALIDATED, PARTIAL, NOT_PERFORMED), ("CONFIG_IDENTITY_VALIDATED",
                                                               "CONFIG_IDENTITY_VALIDATION_PARTIAL",
                                                               "CONFIG_IDENTITY_VALIDATION_NOT_PERFORMED"))

    def test_summary_rejects_inconsistent_config_provenance(self):
        summary = summarize_scenario([candidate("S1", True), candidate("S2")], unit_factors("S1", "S2"))
        base = dict(summary.provenance)

        def without(key):
            return {k: v for k, v in base.items() if k != key}

        cases = {
            "unknown status": dict(base, config_identity_validation_status="VALIDATED"),
            "missing status": without("config_identity_validation_status"),
            "empty reason": dict(base, config_identity_validation_reason=""),
            "missing reason": without("config_identity_validation_reason"),
            "missing hashes": without("eligible_config_identity_hashes"),
            "performed without a hash": dict(base, eligible_config_identity_hashes=()),
            "not performed with a hash": dict(base, config_identity_validation_status=NOT_PERFORMED),
            "two hashes": dict(base, eligible_config_identity_hashes=(CONFIG_A, CONFIG_B)),
            "malformed hash": dict(base, eligible_config_identity_hashes=("xyz",)),
            "hashes as a string": dict(base, eligible_config_identity_hashes=CONFIG_A),
        }
        for label, provenance in cases.items():
            with self.subTest(case=label), self.assertRaises(ValueError):
                replace(summary, provenance=provenance)
        empty = summarize_scenario([candidate("V14")], unit_factors("V14"))
        with self.assertRaises(ValueError):
            replace(empty, provenance=dict(empty.provenance, config_identity_validation_status=VALIDATED,
                                           eligible_config_identity_hashes=(CONFIG_A,)))


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------
class Isolation(unittest.TestCase):
    def test_standard_library_only(self):
        allowed = {"__future__", "collections", "dataclasses", "math", "re", "types", "typing"}
        for name in ("core.py", "__init__.py"):
            tree = ast.parse((PACKAGE / name).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level:
                    self.assertEqual(node.module, "core", name)
                elif isinstance(node, ast.ImportFrom):
                    self.assertIn(node.module.split(".")[0], allowed, name)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertIn(alias.name.split(".")[0], allowed, name)

    def test_importing_the_package_loads_no_project_package(self):
        code = (f"import sys; sys.path.insert(0, {str(ROOT)!r}); import analytic_proxy;"
                "print(sorted(m for m in sys.modules if m.split('.')[0] in ('gotne', 'avidity', 'numpy')))")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(out, "[]")


if __name__ == "__main__":
    unittest.main(verbosity=2)
