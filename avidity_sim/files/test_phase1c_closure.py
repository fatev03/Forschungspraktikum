"""Phase 1c closure tests for the v0.3.1 decision record.

Covers S-1/S-2/S-3/S-5/S-6/S-11/S-12, N-1, N-2, C-1, the §17.8 composition
rule, EvaluationResult integrity, complete diagnosis, determinism, and direct
coverage of every live diagnostic code.

Assertion style: diagnostic-code MEMBERSHIP, never exclusivity, except where
v0.3.1 fixes an exact diagnostic set (the not-applicable contract).
"""

from __future__ import annotations

import json
import os
import pathlib
import random
import subprocess
import sys
import unittest
from dataclasses import fields, replace
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(TESTS))

from gotne import cassette_topology  # noqa: E402
from gotne.cassette_schema import (  # noqa: E402
    MISSING,
    AnchorSpec,
    CassetteConfig,
    CassetteSpec,
    DepEdge,
    DepEdgeKind,
    EngagementOrderPolicy,
    JunctionModel,
    TetherSpec,
    TopologyMode,
    UnresolvedUpstreamPolicy,
)
from gotne.cassette_topology import (  # noqa: E402
    GEOMETRY_PRESENCE_ASSUMPTION,
    Code,
    Reason,
    validate_cassette_config,
    validate_cassette_identity_admissibility,
    validate_cassette_order_constraints,
    validate_cassette_policy_fields,
    validate_cassette_topology,
)
from gotne.identity import config_identity_hash  # noqa: E402
from gotne.status import (  # noqa: E402
    EvaluationResult,
    Exactness,
    Provenance,
    Status,
    make_config_result,
)
from test_cassette_topology import (  # noqa: E402
    CassetteTestCase,
    T34ThreeArmStar,
    T35IndependentAnchors,
    base_policy,
    module,
    ref_cassette_3,
)

VALIDATORS = (
    validate_cassette_policy_fields,
    validate_cassette_topology,
    validate_cassette_order_constraints,
    validate_cassette_identity_admissibility,
    validate_cassette_config,
)
STAGE_NAMES = (
    "validate_cassette_policy_fields",
    "validate_cassette_topology",
    "validate_cassette_order_constraints",
    "validate_cassette_identity_admissibility",
)
EXPLICIT = base_policy(engagement_order_policy=EngagementOrderPolicy.EXPLICIT_PARTIAL_ORDER)
STRICT = base_policy(engagement_order_policy=EngagementOrderPolicy.STRICT_PROXIMAL_TO_DISTAL)


class _Opaque:
    pass


def with_cassette(cfg, **changes):
    return replace(cfg, cassettes=(replace(cfg.cassettes[0], **changes),))


def with_order(order, policy=EXPLICIT, dep_edges=()):
    return with_cassette(ref_cassette_3(policy=policy, dep_edges=dep_edges), explicit_partial_order=order)


def with_module(cfg, index, **changes):
    mods = list(cfg.modules)
    mods[index] = replace(mods[index], **changes)
    return replace(cfg, modules=tuple(mods))


def with_tether(cfg, index, **changes):
    ts = list(cfg.tethers)
    ts[index] = replace(ts[index], **changes)
    return replace(cfg, tethers=tuple(ts))


def single_module_cfg():
    return CassetteConfig(
        id="cfg-n1",
        policy=base_policy(),
        cassettes=(
            CassetteSpec(id="cas1", root_anchor_id="a0", ordered_modules=("D1",), ordered_segments=("s0",)),
        ),
        anchors=(AnchorSpec(id="a0"),),
        modules=(module("D1", 1, terminal=True, exclusion_centre=(0.3, 0.0, 0.0)),),
        tethers=(TetherSpec(id="s0", from_node="a0", to_node="D1", cassette_index=0),),
    )


def valid_fixtures():
    return {
        "ref": ref_cassette_3(),
        "n1": single_module_cfg(),
        "strict_redundant": ref_cassette_3(
            policy=STRICT, dep_edges=(DepEdge("D1", "D2", DepEdgeKind.REQUIRES),)
        ),
        "explicit_empty": with_order([]),
        "explicit_order": with_order([["D1", "D2"], ("D2", "D3")]),
        "shell_bound": replace(
            ref_cassette_3(
                policy=base_policy(
                    unresolved_upstream_policy=UnresolvedUpstreamPolicy.EXCLUDED_SHELL_BOUND
                )
            ),
            modules=tuple(
                replace(m, unresolved_occupancy_fraction=0.5) for m in ref_cassette_3().modules
            ),
        ),
    }


def to_json(result):
    return json.dumps(result.as_dict(), sort_keys=True, allow_nan=False)


def run_with_seed(code, seed):
    env = dict(os.environ, PYTHONHASHSEED=str(seed))
    prefix = f"import sys; sys.path[:0]=[{str(ROOT)!r},{str(TESTS)!r}]\n"
    return subprocess.run(
        [sys.executable, "-c", prefix + code], env=env, capture_output=True, text=True, check=True
    ).stdout


# --------------------------------------------------------------------------
# S-2 / S-3: exactness and provenance
# --------------------------------------------------------------------------
class S2S3ExactnessAndProvenance(CassetteTestCase):
    def test_valid_config_exactness_undefined(self):
        for validator in VALIDATORS:
            with self.subTest(validator=validator.__name__):
                result = validator(ref_cassette_3())
                self.assertIs(result.status, Status.VALID)
                self.assertIs(result.exact_or_approximate, Exactness.UNDEFINED)
                self.assertIs(result.provenance.worst_label, Provenance.NOT_COMPUTED)
                self.assertEqual(result.provenance.method_version, "0.3.1")

    def test_veto_config_exactness_exact(self):
        cfg = replace(ref_cassette_3(), policy=base_policy(tau_spacer=2.0))
        result = validate_cassette_config(cfg)
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertIs(result.exact_or_approximate, Exactness.EXACT)

    def test_not_evaluated_exactness_undefined(self):
        cfg = ref_cassette_3()
        cfg = replace(cfg, cassettes=cfg.cassettes * 2)
        result = validate_cassette_order_constraints(cfg)
        self.assertIs(result.status, Status.NOT_EVALUATED)
        self.assertIs(result.exact_or_approximate, Exactness.UNDEFINED)
        self.assertIs(result.provenance.worst_label, Provenance.NOT_COMPUTED)

    def test_phase1c_vetoes_use_structural_provenance(self):
        cases = {
            "P0": (validate_cassette_policy_fields, replace(ref_cassette_3(), policy=base_policy(tau_spacer=2.0))),
            "P1": (validate_cassette_topology, T34ThreeArmStar().build()),
            "P2": (
                validate_cassette_order_constraints,
                ref_cassette_3(dep_edges=(DepEdge("D1", "D2", DepEdgeKind.REQUIRES), DepEdge("D2", "D1", DepEdgeKind.REQUIRES))),
            ),
            "P3": (validate_cassette_identity_admissibility, with_module(ref_cassette_3(), 1, entry_offset={1})),
        }
        for stage, (validator, cfg) in cases.items():
            with self.subTest(stage=stage):
                result = validator(cfg)
                self.assertIs(result.status, Status.INFEASIBLE)
                self.assertVetoFieldPattern(result)

    def test_no_phase1c_result_uses_geometric_veto(self):
        rejects = [
            T34ThreeArmStar().build(),
            T35IndependentAnchors().build(),
            replace(ref_cassette_3(), policy=base_policy(junction_model=JunctionModel.RESTRICTED_CONE)),
            with_order("bad"),
            with_module(ref_cassette_3(), 1, entry_offset=_Opaque()),
        ]
        for cfg in rejects:
            for validator in VALIDATORS:
                result = validator(cfg)
                self.assertIsNot(result.provenance.worst_label, Provenance.EXACT_GEOMETRIC_VETO)


# --------------------------------------------------------------------------
# S-5: geometry-bearing fields are not Phase 1c requirements
# --------------------------------------------------------------------------
class S5GeometryFields(CassetteTestCase):
    def test_missing_geometry_fields_do_not_fail_phase1c(self):
        for value in (MISSING, None):
            cfg = with_module(ref_cassette_3(), 1, entry_offset=value, capture_offset_vec=value)
            result = validate_cassette_config(cfg)
            self.assertIs(result.status, Status.VALID)
            self.assertIn(GEOMETRY_PRESENCE_ASSUMPTION, result.provenance.declared_assumptions)

    def test_missing_geometry_fields_hash_distinctly(self):
        base = ref_cassette_3()
        hashes = {
            config_identity_hash(with_module(base, 1, entry_offset=v))
            for v in (MISSING, None, (0.0, 0.0, 0.0))
        }
        self.assertEqual(len(hashes), 3)

    def test_non_valid_results_do_not_claim_the_assumption_scope(self):
        result = validate_cassette_config(T34ThreeArmStar().build())
        self.assertNotIn(GEOMETRY_PRESENCE_ASSUMPTION, result.provenance.declared_assumptions)


# --------------------------------------------------------------------------
# S-6: explicit_partial_order declaration contract (§20.6.1)
# --------------------------------------------------------------------------
class S6ExplicitOrderContract(CassetteTestCase):
    def order_diags(self, result, code):
        return [x for x in result.diagnostics if x.code == code]

    def test_explicit_order_container_types(self):
        for value in ("D1D2", b"D1", {("D1", "D2")}, {"D1": "D2"}, 5, True, None, _Opaque(), TopologyMode.GENERAL_DAG):
            with self.subTest(value=type(value).__name__):
                cfg = with_order(value)
                p0 = validate_cassette_policy_fields(cfg)
                self.assertIs(p0.status, Status.INFEASIBLE)
                self.assertEqual(p0.status_reason, Reason.POLICY_RANGE)
                d = self.order_diags(p0, Code.EXPLICIT_ORDER_MALFORMED)
                self.assertEqual(len(d), 1)
                self.assertEqual(d[0].quantities["problem"], "CONTAINER_TYPE")
                self.assertIsNone(d[0].quantities["pair_index"])
                self.assertIsInstance(d[0].quantities["found_type"], str)
                self.assertCode(p0, Code.CHECK_SKIPPED)
                self.assertIs(validate_cassette_config(cfg).status, Status.INFEASIBLE)
                self.assertIs(validate_cassette_order_constraints(cfg).status, Status.NOT_EVALUATED)

    def test_explicit_order_entry_shape(self):
        cases = [
            ([("D1", "D2", "D3")], "ENTRY_ARITY", 0),
            ([("D1",)], "ENTRY_ARITY", 0),
            (["D1D2"], "ENTRY_TYPE", 0),
            ([("D1", "D2"), ("D1", 2)], "ELEMENT_TYPE", 1),
            ([(TopologyMode.GENERAL_DAG, "D1")], "ELEMENT_TYPE", 0),
            ([("D1", "D2"), {"D1", "D2"}], "ENTRY_TYPE", 1),
        ]
        for order, problem, index in cases:
            with self.subTest(order=str(order)):
                p0 = validate_cassette_policy_fields(with_order(order))
                self.assertIs(p0.status, Status.INFEASIBLE)
                d = self.order_diags(p0, Code.EXPLICIT_ORDER_MALFORMED)
                self.assertEqual([x.quantities["problem"] for x in d], [problem])
                self.assertEqual(d[0].quantities["pair_index"], index)

    def test_arity_reported_for_arity_errors(self):
        p0 = validate_cassette_policy_fields(with_order([("D1", "D2", "D3")]))
        d = self.order_diags(p0, Code.EXPLICIT_ORDER_MALFORMED)[0]
        self.assertEqual(d.quantities["arity"], 3)

    def test_every_malformed_entry_is_diagnosed(self):
        p0 = validate_cassette_policy_fields(with_order([("D1",), ("D1", "D2"), "x", ("D1", "D1")]))
        indices = sorted(
            x.quantities["pair_index"]
            for x in p0.diagnostics
            if x.code in (Code.EXPLICIT_ORDER_MALFORMED, Code.EXPLICIT_ORDER_INVALID_REFERENCE)
        )
        self.assertEqual(indices, [0, 2, 3])

    def test_explicit_order_empty_is_evaluated(self):
        for empty in ([], ()):
            with self.subTest(empty=type(empty).__name__):
                cfg = with_order(empty)
                self.assertIs(validate_cassette_config(cfg).status, Status.VALID)
                p2 = validate_cassette_order_constraints(cfg)
                self.assertIs(p2.status, Status.VALID)
                self.assertNotIn(Code.CHECK_SKIPPED, p2.codes())

    def test_explicit_order_unknown_module_in_p0(self):
        cfg = with_order([("D1", "DX")])
        p0 = validate_cassette_policy_fields(cfg)
        self.assertIs(p0.status, Status.INFEASIBLE)
        self.assertEqual(p0.status_reason, Reason.POLICY_RANGE)
        d = self.order_diags(p0, Code.EXPLICIT_ORDER_INVALID_REFERENCE)[0]
        self.assertEqual(d.quantities["problems"], ["UNKNOWN_MODULE"])
        self.assertEqual(d.quantities["pair"], ["D1", "DX"])
        composed = validate_cassette_config(cfg)
        self.assertEqual(composed.status_reason, Reason.POLICY_RANGE)
        self.assertNotIn(Code.DEP_EDGE_UNKNOWN_NODE, composed.codes())
        skipped = {x.quantities["check"] for x in composed.diagnostics if x.code == Code.CHECK_SKIPPED}
        self.assertIn("P2 order constraints", skipped)

    def test_explicit_order_self_loop(self):
        d = self.order_diags(validate_cassette_policy_fields(with_order([("D1", "D1")])), Code.EXPLICIT_ORDER_INVALID_REFERENCE)
        self.assertEqual(d[0].quantities["problems"], ["SELF_LOOP"])
        d = self.order_diags(validate_cassette_policy_fields(with_order([("DX", "DX")])), Code.EXPLICIT_ORDER_INVALID_REFERENCE)
        self.assertEqual(d[0].quantities["problems"], ["SELF_LOOP", "UNKNOWN_MODULE"])

    def test_explicit_order_direction(self):
        requires = (DepEdge("D1", "D2", DepEdgeKind.REQUIRES),)
        conflict = validate_cassette_config(with_order([("D2", "D1")], dep_edges=requires))
        self.assertIs(conflict.status, Status.INFEASIBLE)
        self.assertEqual(conflict.status_reason, Reason.ORDER)
        self.assertCode(conflict, Code.ENGAGEMENT_ORDER_CONFLICT)
        agree = validate_cassette_config(with_order([("D1", "D2")], dep_edges=requires))
        self.assertIs(agree.status, Status.VALID)

    def test_explicit_order_duplicate_pairs_idempotent(self):
        once = validate_cassette_config(with_order([("D1", "D2")]))
        twice = validate_cassette_config(with_order([("D1", "D2"), ["D1", "D2"]]))
        self.assertIs(twice.status, Status.VALID)
        self.assertEqual(once.codes(), twice.codes())

    def test_malformed_order_under_non_explicit_policy_is_only_unexpected(self):
        for value in ("x", {("D1", "D2")}, None, [], [("D1",)], _Opaque()):
            with self.subTest(value=type(value).__name__):
                result = validate_cassette_policy_fields(with_order(value, policy=base_policy()))
                self.assertEqual(result.error_codes(), [Code.EXPLICIT_ORDER_UNEXPECTED])

    def test_p2_standalone_malformed_order_not_evaluated(self):
        for value in ("x", [("D1",)], [("D1", "DX")], None):
            with self.subTest(value=str(value)):
                result = validate_cassette_order_constraints(with_order(value))
                self.assertIs(result.status, Status.NOT_EVALUATED)
                self.assertEqual(result.status_reason, Reason.PREREQUISITE_FAILED)
                self.assertCode(result, Code.CHECK_SKIPPED)


# --------------------------------------------------------------------------
# §17.8 composition on every return path (H-2)
# --------------------------------------------------------------------------
class CompositionGuard(CassetteTestCase):
    def test_composition_guard_all_paths(self):
        cfg = ref_cassette_3()
        for index, stage in enumerate(STAGE_NAMES):
            with self.subTest(stage=stage):
                double = make_config_result(
                    object_id=cfg.id,
                    status=Status.NOT_EVALUATED,
                    status_reason=Reason.PREREQUISITE_FAILED,
                    diagnostics=(),
                )
                with mock.patch.object(cassette_topology, stage, return_value=double):
                    result = cassette_topology.validate_cassette_config(cfg)
                self.assertIs(result.status, Status.NOT_EVALUATED)
                self.assertEqual(result.status_reason, Reason.PREREQUISITE_FAILED)
                skipped = [x for x in result.diagnostics if x.code == Code.CHECK_SKIPPED]
                self.assertEqual(len(skipped), len(STAGE_NAMES) - index - 1)

    def test_veto_beats_not_evaluated_is_not_reachable_by_promotion(self):
        cfg = replace(ref_cassette_3(), policy=base_policy(tau_spacer=2.0))
        self.assertIs(validate_cassette_config(cfg).status, Status.INFEASIBLE)


# --------------------------------------------------------------------------
# H-3: EvaluationResult integrity
# --------------------------------------------------------------------------
class ResultIntegrity(unittest.TestCase):
    def setUp(self):
        self.veto = validate_cassette_config(T34ThreeArmStar().build())
        self.valid = validate_cassette_config(ref_cassette_3())
        cfg = ref_cassette_3()
        self.unknown = validate_cassette_order_constraints(replace(cfg, cassettes=cfg.cassettes * 2))

    def test_evaluation_result_rejects_pattern_violation(self):
        bad = [
            (self.veto, dict(values={**self.veto.values, "conditional_probability": 0.7})),
            (self.veto, dict(zeroed_due_to_status=False)),
            (self.veto, dict(values={**self.veto.values, "effective_local_concentration": 1.0})),
            (self.veto, dict(value_intervals={"conditional_probability": [0.1, 0.2]})),
            (self.unknown, dict(values={**self.unknown.values, "joint_score": 0.0})),
            (self.unknown, dict(nulled_due_to_status=False)),
            (self.valid, dict(values={**self.valid.values, "bogus": 1.0})),
            (self.valid, dict(status=Status.INFEASIBLE)),
            (self.valid, dict(exact_or_approximate=Exactness.EXACT)),
            (self.valid, dict(units={"bogus": "1"})),
            (self.valid, dict(values={**self.valid.values, "joint_score": "0.5"})),
            (self.valid, dict(values={**self.valid.values, "joint_score": float("nan")})),
        ]
        for result, change in bad:
            with self.subTest(change=sorted(change)):
                with self.assertRaises((ValueError, TypeError)):
                    replace(result, **change)

    def test_non_status_rejected_at_construction(self):
        with self.assertRaises(TypeError):
            replace(self.valid, status="VALID")

    def test_faithful_replace_still_allowed(self):
        self.assertEqual(replace(self.veto).as_dict(), self.veto.as_dict())

    def test_result_values_read_only(self):
        for mapping in (
            self.veto.values,
            self.veto.value_intervals,
            self.veto.units,
            self.veto.diagnostics[0].quantities,
        ):
            with self.assertRaises(TypeError):
                mapping["conditional_probability"] = 0.5  # type: ignore[index]


# --------------------------------------------------------------------------
# S-11: P3 identity admissibility
# --------------------------------------------------------------------------
class S11IdentityAdmissibility(CassetteTestCase):
    def test_noncanonical_opaque_value_rejected(self):
        for value in ({1, 2}, _Opaque(), b"xy", frozenset()):
            with self.subTest(value=type(value).__name__):
                cfg = with_module(ref_cassette_3(), 1, entry_offset=value)
                for validator in (validate_cassette_identity_admissibility, validate_cassette_config):
                    result = validator(cfg)
                    self.assertIs(result.status, Status.INFEASIBLE)
                    self.assertEqual(result.status_reason, Reason.NOT_CANONICALIZABLE)
                    d = next(x for x in result.diagnostics if x.code == Code.NON_CANONICAL_VALUE)
                    self.assertEqual(d.quantities["path"], "modules[1].entry_offset")
                    self.assertEqual(d.quantities["found_type"], type(value).__qualname__)

    def test_one_diagnostic_per_offending_value(self):
        cfg = with_module(with_module(ref_cassette_3(), 0, rho=_Opaque()), 2, exclusion_centre=[{1}, b"x"])
        paths = [
            x.quantities["path"]
            for x in validate_cassette_identity_admissibility(cfg).diagnostics
            if x.code == Code.NON_CANONICAL_VALUE
        ]
        self.assertEqual(
            paths, ["modules[0].rho", "modules[2].exclusion_centre[0]", "modules[2].exclusion_centre[1]"]
        )

    def test_valid_implies_canonicalizable(self):
        for name, cfg in valid_fixtures().items():
            with self.subTest(fixture=name):
                self.assertIs(validate_cassette_config(cfg).status, Status.VALID)
                self.assertEqual(len(config_identity_hash(cfg)), 64)

    def test_p3_skipped_when_earlier_stage_fails(self):
        cfg = with_module(
            replace(ref_cassette_3(), policy=base_policy(junction_model=JunctionModel.RESTRICTED_CONE)),
            1,
            entry_offset={1},
        )
        result = validate_cassette_config(cfg)
        self.assertEqual(result.status_reason, Reason.JUNCTION_UNSUPPORTED)
        self.assertNotIn(Code.NON_CANONICAL_VALUE, result.codes())
        skipped = {x.quantities["check"] for x in result.diagnostics if x.code == Code.CHECK_SKIPPED}
        self.assertIn("P3 identity admissibility", skipped)


# --------------------------------------------------------------------------
# S-12: totality of public validators, schema-structure TypeError
# --------------------------------------------------------------------------
HOSTILE = (
    None, MISSING, 0, 5, -1, 1.5, True, float("nan"), float("inf"), "", "x", "D1",
    [], (), {}, set(), frozenset({"a"}), _Opaque(), b"x", TopologyMode.GENERAL_DAG,
    ["D1"], [["D1", "D2"]], ("D1", "D2", "D3"),
)


def mutations(cfg):
    """Every declared (non-schema-structure) field of cfg, as setter closures."""
    out = [("id", lambda v: replace(cfg, id=v))]
    for f in fields(cfg.policy):
        out.append((f"policy.{f.name}", lambda v, n=f.name: replace(cfg, policy=replace(cfg.policy, **{n: v}))))
    for f in fields(cfg.cassettes[0]):
        out.append((f"cassettes[0].{f.name}", lambda v, n=f.name: with_cassette(cfg, **{n: v})))
    for coll, idx in (("modules", 1), ("modules", 2), ("anchors", 0), ("tethers", 1), ("dep_edges", 0)):
        items = getattr(cfg, coll)
        if len(items) <= idx:
            continue
        for f in fields(items[idx]):
            def setter(v, c=coll, i=idx, n=f.name):
                seq = list(getattr(cfg, c))
                seq[i] = replace(seq[i], **{n: v})
                return replace(cfg, **{c: tuple(seq)})
            out.append((f"{coll}[{idx}].{f.name}", setter))
    return out


class S12ValidatorTotality(unittest.TestCase):
    BASES = {
        "any_order_requires": ref_cassette_3(dep_edges=(DepEdge("D1", "D2", DepEdgeKind.REQUIRES),)),
        "explicit": with_order([("D1", "D2")], dep_edges=(DepEdge("D2", "D3", DepEdgeKind.REQUIRES),)),
        "shell_bound": valid_fixtures()["shell_bound"],
    }

    def test_validators_never_raise_on_declared_input(self):
        calls = 0
        for base_name, base in self.BASES.items():
            for path, setter in mutations(base):
                for value in HOSTILE:
                    cfg = setter(value)
                    for validator in VALIDATORS:
                        try:
                            result = validator(cfg)
                            payload = to_json(result)
                        except Exception as exc:  # pragma: no cover - failure path
                            self.fail(
                                f"{validator.__name__} raised {type(exc).__name__} for "
                                f"{base_name}:{path}={type(value).__qualname__}: {exc}"
                            )
                        self.assertIsInstance(result, EvaluationResult)
                        self.assertNotRegex(payload, r" at 0x[0-9a-f]+")
                        if validator is validate_cassette_config and result.status is Status.VALID:
                            config_identity_hash(cfg)  # S-11: VALID implies hashable
                        calls += 1
        self.assertGreater(calls, 10000)

    def test_schema_structure_errors_raise_type_error(self):
        base = ref_cassette_3()
        bad = [
            None,
            "cfg",
            replace(base, policy=None),
            replace(base, cassettes=None),
            replace(base, modules=({},)),
            replace(base, anchors=[AnchorSpec(id="a0"), "a1"]),
            replace(base, tethers={"s0"}),
            replace(base, dep_edges=(("D1", "D2"),)),
        ]
        for cfg in bad:
            for validator in VALIDATORS:
                with self.subTest(cfg=type(cfg).__name__, validator=validator.__name__):
                    with self.assertRaises(TypeError) as first:
                        validator(cfg)
                    with self.assertRaises(TypeError) as second:
                        validator(cfg)
                    self.assertEqual(str(first.exception), str(second.exception))


# --------------------------------------------------------------------------
# N-1 / N-2
# --------------------------------------------------------------------------
class N1MalformedIdentifiers(CassetteTestCase):
    def test_malformed_identifier_rejected(self):
        base = ref_cassette_3()
        cases = {
            "modules[1].id": lambda v: with_module(base, 1, id=v),
            "anchors[0].id": lambda v: replace(base, anchors=(replace(base.anchors[0], id=v),)),
            "tethers[1].from_node": lambda v: with_tether(base, 1, from_node=v),
            "cassettes[0].root_anchor_id": lambda v: with_cassette(base, root_anchor_id=v),
            "cassettes[0].ordered_modules[1]": lambda v: with_cassette(base, ordered_modules=("D1", v, "D3")),
            "id": lambda v: replace(base, id=v),
        }
        for path, build in cases.items():
            for value in (5, None, ["x"], "", TopologyMode.GENERAL_DAG):
                with self.subTest(path=path, value=type(value).__name__):
                    result = validate_cassette_topology(build(value))
                    self.assertTopologyRejection(result, Code.IDENTIFIER_MALFORMED)
                    d = [x for x in result.diagnostics if x.code == Code.IDENTIFIER_MALFORMED]
                    self.assertIn(path, [x.quantities["path"] for x in d])
                    self.assertIs(validate_cassette_config(build(value)).status, Status.INFEASIBLE)

    def test_malformed_container_rejected_and_dependents_skipped(self):
        result = validate_cassette_topology(with_cassette(ref_cassette_3(), ordered_modules="D1D2D3"))
        self.assertTopologyRejection(result, Code.IDENTIFIER_MALFORMED)
        skipped = {x.quantities["check"] for x in result.diagnostics if x.code == Code.CHECK_SKIPPED}
        self.assertTrue({"C11", "C2/C3", "C10a", "C10b"} <= skipped)

    def test_malformed_config_id_gives_safe_object_id(self):
        result = validate_cassette_config(replace(ref_cassette_3(), id=_Opaque()))
        self.assertEqual(result.object_id, "<malformed id: _Opaque>")


class N2DepEdgeKind(CassetteTestCase):
    def test_string_dep_edge_kind_rejected(self):
        cfg = ref_cassette_3(
            dep_edges=(DepEdge("D1", "D2", "REQUIRES"), DepEdge("D2", "D1", "REQUIRES"))
        )
        result = validate_cassette_config(cfg)
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertEqual(result.status_reason, Reason.ORDER)
        d = [x for x in result.diagnostics if x.code == Code.DEP_EDGE_MALFORMED]
        self.assertEqual([(x.quantities["edge_index"], x.quantities["field"]) for x in d], [(0, "kind"), (1, "kind")])

    def test_malformed_dep_edge_endpoint_rejected(self):
        for value in (5, None, "", ["D1"]):
            with self.subTest(value=type(value).__name__):
                cfg = ref_cassette_3(dep_edges=(DepEdge(value, "D2", DepEdgeKind.REQUIRES),))
                result = validate_cassette_order_constraints(cfg)
                self.assertIs(result.status, Status.INFEASIBLE)
                d = next(x for x in result.diagnostics if x.code == Code.DEP_EDGE_MALFORMED)
                self.assertEqual(d.quantities["field"], "from_node")


# --------------------------------------------------------------------------
# C-1: diagnostics JSON-safe and seed-stable
# --------------------------------------------------------------------------
_HOSTILE_DIAG_CFG = """
from dataclasses import replace
from test_cassette_topology import ref_cassette_3, base_policy, module
from gotne.cassette_schema import MISSING, UnresolvedUpstreamPolicy, DepEdge, DepEdgeKind
class Opaque: pass
cfg = ref_cassette_3(policy=base_policy(junction_model=Opaque(), tau_spacer=float("nan"),
      unresolved_upstream_policy=UnresolvedUpstreamPolicy.EXCLUDED_SHELL_BOUND))
cfg = replace(cfg, modules=(module("D1", 1, cassette_id=MISSING, unresolved_occupancy_fraction=Opaque()),) + cfg.modules[1:])
topo = replace(ref_cassette_3(), modules=(module("D1", 1, cassette_id=MISSING),) + ref_cassette_3().modules[1:])
cyc = ref_cassette_3(dep_edges=(DepEdge("D1","D2",DepEdgeKind.REQUIRES), DepEdge("D2","D1",DepEdgeKind.REQUIRES)))
"""


class C1DiagnosticsSerializable(unittest.TestCase):
    def test_diagnostics_json_serializable_and_seed_stable(self):
        code = _HOSTILE_DIAG_CFG + (
            "import json\n"
            "from gotne.cassette_topology import *\n"
            "out = [validate_cassette_policy_fields(cfg), validate_cassette_topology(topo), "
            "validate_cassette_config(cyc), validate_cassette_config(ref_cassette_3())]\n"
            "print(json.dumps([r.as_dict() for r in out], sort_keys=True, allow_nan=False))\n"
        )
        outputs = {run_with_seed(code, seed) for seed in (0, 1, 42, 999)}
        self.assertEqual(len(outputs), 1)
        payload = outputs.pop()
        self.assertNotRegex(payload, r" at 0x[0-9a-f]+")
        self.assertIn('"MISSING"', payload)


# --------------------------------------------------------------------------
# H-5: complete diagnosis
# --------------------------------------------------------------------------
class H5CompleteDiagnosis(CassetteTestCase):
    def test_duplicates_reported_with_invalid_cassette_count(self):
        cfg = ref_cassette_3()
        two = replace(cfg, cassettes=cfg.cassettes * 2, modules=cfg.modules + (cfg.modules[0],))
        result = validate_cassette_topology(two)
        self.assertCode(result, Code.CASSETTE_COUNT_INVALID)
        self.assertCode(result, Code.DUPLICATE_IDENTIFIER)
        zero = replace(cfg, cassettes=(), anchors=cfg.anchors * 2)
        result = validate_cassette_topology(zero)
        self.assertCode(result, Code.CASSETTE_COUNT_INVALID)
        self.assertCode(result, Code.DUPLICATE_IDENTIFIER)

    def test_root_multiplicity_reported_with_invalid_cassette_count(self):
        cfg = T35IndependentAnchors().build()
        result = validate_cassette_topology(replace(cfg, cassettes=cfg.cassettes * 2))
        self.assertCode(result, Code.MULTI_ANCHOR_IN_CASSETTE)

    def test_segment_checks_independent_of_root(self):
        cfg = ref_cassette_3()
        cfg = replace(
            cfg,
            anchors=cfg.anchors + (AnchorSpec(id="a1"),),
            tethers=cfg.tethers + (TetherSpec(id="sx", from_node="a1", to_node="D1", cassette_index=9),),
        )
        cfg = with_cassette(cfg, ordered_segments=("s0", "s1", "s2", "sx", "s9"))
        result = validate_cassette_topology(cfg)
        self.assertCode(result, Code.MULTI_ANCHOR_IN_CASSETTE)
        messages = {x.message for x in result.diagnostics if x.code == Code.SEGMENT_SEQUENCE_INVALID}
        self.assertIn("ordered_segments must contain exactly N entries", messages)
        self.assertIn("ordered_segments references an undeclared tether", messages)
        self.assertIn("tether cassette_index does not match its position in ordered_segments", messages)

    def test_mode_gate_marks_skipped_checks(self):
        cfg = replace(ref_cassette_3(), policy=base_policy(topology_mode=None, junction_model=MISSING))
        composed = validate_cassette_config(cfg)
        skipped = [x.quantities["check"] for x in composed.diagnostics if x.code == Code.CHECK_SKIPPED]
        self.assertEqual(
            skipped,
            ["P0 policy fields", "P1 topology", "P2 order constraints", "P3 identity admissibility"],
        )
        p0 = validate_cassette_policy_fields(cfg)
        self.assertEqual(
            [x.quantities["check"] for x in p0.diagnostics if x.code == Code.CHECK_SKIPPED],
            ["P0 policy fields"],
        )


# --------------------------------------------------------------------------
# Direct coverage for previously uncovered or indirectly covered branches
# --------------------------------------------------------------------------
class DirectCoverage(CassetteTestCase):
    def test_root_anchor_missing(self):
        cfg = replace(ref_cassette_3(), tethers=ref_cassette_3().tethers[1:])
        cfg = with_cassette(cfg, ordered_segments=("s1", "s2"))
        result = validate_cassette_topology(cfg)
        self.assertTopologyRejection(result, Code.ROOT_ANCHOR_MISSING)
        skipped = {x.quantities["check"] for x in result.diagnostics if x.code == Code.CHECK_SKIPPED}
        self.assertTrue({"C4", "C13"} <= skipped)

    def test_root_anchor_mismatch(self):
        result = validate_cassette_topology(with_cassette(ref_cassette_3(), root_anchor_id="a9"))
        self.assertTopologyRejection(result, Code.ROOT_ANCHOR_MISMATCH)

    def test_multipath_connectivity_and_parallel_tethers(self):
        cfg = ref_cassette_3()
        cfg = replace(cfg, tethers=cfg.tethers + (TetherSpec(id="s1b", from_node="D1", to_node="D2"),))
        result = validate_cassette_topology(cfg)
        self.assertTopologyRejection(result, Code.MULTIPATH_CONNECTIVITY)
        self.assertCode(result, Code.CHILD_COUNT_INVALID)
        self.assertCode(result, Code.PARENT_COUNT_INVALID)
        flagged = {x.quantities["module"] for x in result.diagnostics if x.code == Code.MULTIPATH_CONNECTIVITY}
        self.assertEqual(flagged, {"D2", "D3"})

    def test_orphan_module_variants(self):
        cfg = ref_cassette_3()
        cases = [
            replace(cfg, modules=cfg.modules + (module("D9", 4),)),
            with_cassette(cfg, ordered_modules=("D1", "D2", "D3", "D4")),
            with_module(cfg, 1, cassette_id="cas-other"),
        ]
        for case in cases:
            self.assertTopologyRejection(validate_cassette_topology(case), Code.ORPHAN_MODULE)

    def test_pose_level_out_of_range(self):
        for level in (-1, 7, True, 2.0, None):
            with self.subTest(level=level):
                result = validate_cassette_policy_fields(
                    replace(ref_cassette_3(), policy=base_policy(pose_marginalization_max_level=level))
                )
                self.assertEqual(result.status_reason, Reason.POLICY_RANGE)
                self.assertCode(result, Code.POSE_LEVEL_OUT_OF_RANGE)

    def test_tau_spacer_non_finite(self):
        for tau in (float("nan"), float("inf"), True, "0.2"):
            with self.subTest(tau=str(tau)):
                result = validate_cassette_policy_fields(replace(ref_cassette_3(), policy=base_policy(tau_spacer=tau)))
                self.assertCode(result, Code.TAU_SPACER_OUT_OF_RANGE)

    def test_required_policy_field_non_member(self):
        result = validate_cassette_policy_fields(
            replace(ref_cassette_3(), policy=base_policy(junction_model="FREE_SWIVEL"))
        )
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertCode(result, Code.POLICY_FIELD_MISSING)  # deferred S-9 labelling

    def test_occupancy_fraction_declared_null_nan_bool(self):
        policy = base_policy(unresolved_upstream_policy=UnresolvedUpstreamPolicy.EXCLUDED_SHELL_BOUND)
        for value, code in ((None, Code.OCCUPANCY_FRACTION_MISSING), (float("nan"), Code.OCCUPANCY_FRACTION_OUT_OF_RANGE), (True, Code.OCCUPANCY_FRACTION_OUT_OF_RANGE)):
            with self.subTest(value=str(value)):
                cfg = replace(
                    ref_cassette_3(policy=policy),
                    modules=tuple(replace(m, unresolved_occupancy_fraction=value) for m in ref_cassette_3().modules),
                )
                self.assertCode(validate_cassette_policy_fields(cfg), code)

    def test_t61_spec_setup_only_d2_missing(self):
        policy = base_policy(unresolved_upstream_policy=UnresolvedUpstreamPolicy.EXCLUDED_SHELL_BOUND)
        mods = tuple(replace(m, unresolved_occupancy_fraction=0.5) for m in ref_cassette_3().modules)
        cfg = replace(ref_cassette_3(policy=policy), modules=mods)
        cfg = with_module(cfg, 1, unresolved_occupancy_fraction=MISSING)
        result = validate_cassette_policy_fields(cfg)
        self.assertEqual(result.status_reason, Reason.POLICY_MISSING)
        flagged = {x.quantities["module"] for x in result.diagnostics if x.code == Code.OCCUPANCY_FRACTION_MISSING}
        self.assertEqual(flagged, {"D2"})

    def test_t59_no_topology_diagnostics_emitted(self):
        cfg = replace(ref_cassette_3(), policy=base_policy(junction_model=JunctionModel.RESTRICTED_CONE))
        result = validate_cassette_config(cfg)
        p1_codes = {v for k, v in vars(Code).items() if not k.startswith("_")} & set(
            cassette_topology.INVARIANT_OF_CODE
        )
        self.assertFalse(p1_codes & set(result.codes()))
        self.assertIn(
            "P1 topology",
            {x.quantities["check"] for x in result.diagnostics if x.code == Code.CHECK_SKIPPED},
        )

    def test_ordered_segment_repeat_rejected(self):
        result = validate_cassette_topology(with_cassette(ref_cassette_3(), ordered_segments=("s0", "s1", "s1")))
        self.assertTopologyRejection(result, Code.SEGMENT_SEQUENCE_INVALID)

    def test_explicit_order_unexpected_non_empty(self):
        result = validate_cassette_policy_fields(with_order([("D1", "D2")], policy=base_policy()))
        self.assertCode(result, Code.EXPLICIT_ORDER_UNEXPECTED)

    def test_explicit_union_conflict_via_explicit_order_alone(self):
        result = validate_cassette_order_constraints(with_order([("D1", "D2"), ("D2", "D3"), ("D3", "D1")]))
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertCode(result, Code.ENGAGEMENT_ORDER_CONFLICT)

    def test_every_live_code_has_a_direct_test(self):
        sources = "".join(p.read_text(encoding="utf-8") for p in TESTS.glob("test_*.py"))
        missing = [
            name
            for name, value in vars(Code).items()
            if not name.startswith("_") and isinstance(value, str) and f"Code.{name}" not in sources
        ]
        self.assertEqual(missing, [])


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------
class Determinism(unittest.TestCase):
    RICH = (
        "from dataclasses import replace\n"
        "from test_cassette_topology import ref_cassette_3, base_policy, module\n"
        "from gotne.cassette_schema import *\n"
        "c = ref_cassette_3(policy=base_policy(engagement_order_policy=EngagementOrderPolicy.EXPLICIT_PARTIAL_ORDER),"
        " dep_edges=(DepEdge('D1','D3',DepEdgeKind.REQUIRES),))\n"
        "c = replace(c, cassettes=(replace(c.cassettes[0], explicit_partial_order=[('D1','D2')]),),"
        " modules=(module('D1', 1, rho={'b': 1.0, 'a': 2, 'c': None}),) + c.modules[1:])\n"
    )

    def test_hash_stable_across_seeds_rich_config(self):
        code = self.RICH + "from gotne.identity import config_identity_hash\nprint(config_identity_hash(c))\n"
        self.assertEqual(len({run_with_seed(code, s) for s in (0, 1, 42, 999)}), 1)

    def test_result_as_dict_stable_across_seeds(self):
        code = self.RICH + (
            "import json\nfrom gotne.cassette_topology import validate_cassette_config\n"
            "cyc = ref_cassette_3(dep_edges=(DepEdge('D1','D2',DepEdgeKind.REQUIRES), DepEdge('D2','D3',DepEdgeKind.REQUIRES), DepEdge('D3','D1',DepEdgeKind.REQUIRES)))\n"
            "print(json.dumps([validate_cassette_config(x).as_dict() for x in (c, cyc)], sort_keys=True))\n"
        )
        self.assertEqual(len({run_with_seed(code, s) for s in (0, 1, 42, 999)}), 1)

    def test_verdict_invariant_under_declaration_permutation(self):
        base = ref_cassette_3()
        configs = [
            base,
            T34ThreeArmStar().build(),
            T35IndependentAnchors().build(),
            replace(
                base,
                modules=base.modules + (base.modules[1],),
                anchors=base.anchors + (AnchorSpec(id="D3"),),
                tethers=base.tethers + (TetherSpec(id="s1", from_node="D1", to_node="D3"), TetherSpec(id="q", from_node="x", to_node="y")),
            ),
            ref_cassette_3(
                policy=STRICT,
                dep_edges=(DepEdge("D3", "D1", DepEdgeKind.REQUIRES), DepEdge("D1", "D2", DepEdgeKind.REQUIRES), DepEdge("D2", "DX", DepEdgeKind.REQUIRES)),
            ),
        ]
        rng = random.Random(20260923)

        def signature(cfg):
            r = validate_cassette_config(cfg)
            return r.status, r.status_reason, frozenset(r.error_codes())

        for cfg in configs:
            expected = signature(cfg)
            for _ in range(150):
                shuffled = replace(
                    cfg,
                    modules=tuple(rng.sample(list(cfg.modules), len(cfg.modules))),
                    anchors=tuple(rng.sample(list(cfg.anchors), len(cfg.anchors))),
                    tethers=tuple(rng.sample(list(cfg.tethers), len(cfg.tethers))),
                    dep_edges=tuple(rng.sample(list(cfg.dep_edges), len(cfg.dep_edges))),
                )
                self.assertEqual(signature(shuffled), expected, cfg.id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
