"""Phase 2, final seam: evaluate_state, the node layer and Migration Step 2
(decision record revision 3 with amendments A1 and A2).

Covers the result builder and freezing (AP-4, AP-5, AP-11: L6, L7, L9),
result_identity (AP-9: L8), evaluate_state in the stage order of record I
(T79, T83, L10-L12, L16-L18), evaluate_node (OQ-6), propagate_state_veto (G,
MNH26), NodeReason, and the dynamic import boundary (L13).

Fixture geometry is binary-exact. With identity orientations and the budget
fixture (entry 0, exit 1.25, capture 0.5 along x; tethers s0 [0, 2],
s1 [0.5, 1.5], s2 [0.25, 1]) the node budget of D1 from ROOT is [0, 2.5].

Run: python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import contextlib
import importlib
import json
import os
import pathlib
import subprocess
import sys
import unittest
from dataclasses import replace
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from gotne import cassette_closure, cassette_node, identity, status  # noqa: E402
from gotne.cassette_closure import Tri, chain_closure_feasible, evaluate_state  # noqa: E402
from gotne.cassette_node import NodeReason, evaluate_node, propagate_state_veto  # noqa: E402
from gotne.cassette_schema import (  # noqa: E402
    MISSING,
    AnchorSpec,
    DepEdge,
    DepEdgeKind,
    EngagedPoseResolution,
    EngagementOrderPolicy,
    JunctionModel,
    TopologyMode,
    UnresolvedUpstreamPolicy,
)
from gotne.cassette_state import (  # noqa: E402
    NumericalTolerances,
    StateCertificate,
    StateCode,
    StateReason,
    issue_state_certificate,
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
from gotne.identity import (  # noqa: E402
    config_identity_hash,
    context_identity_hash,
    result_identity,
    state_identity_hash,
)
from gotne.status import (  # noqa: E402
    CANONICAL_UNITS,
    METHOD_VERSION,
    OBJECT_KINDS,
    VETO_SET,
    EvaluationResult,
    Exactness,
    Provenance,
    ProvenanceRecord,
    Status,
    apply_status_field_pattern,
    make_config_result,
    make_result,
)
from test_cassette_topology import T34ThreeArmStar, base_policy, module, ref_cassette_3  # noqa: E402
from test_phase2_cassette_budget import S13, S123, budget_cfg, state  # noqa: E402
from test_phase2_cassette_closure import EPS, TINY, make_context, separated  # noqa: E402
from test_phase2_cassette_frames import R90  # noqa: E402
from test_phase2_cassette_state import engaged, imported_modules, unengaged  # noqa: E402
from test_phase2_cassette_state import state_result as hand_built_state_result  # noqa: E402

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
S1 = state(engaged("D1", "t1"))
S12 = state(engaged("D1", "t1"), engaged("D2", "t2"))
MARGINALIZED = base_policy(engaged_pose_resolution=EngagedPoseResolution.ORIENTATION_MARGINALIZED)
FIXED_RIGID = base_policy(junction_model=JunctionModel.FIXED_RIGID)
STRICT = base_policy(engagement_order_policy=EngagementOrderPolicy.STRICT_PROXIMAL_TO_DISTAL)
SHELL = base_policy(unresolved_upstream_policy=UnresolvedUpstreamPolicy.EXCLUDED_SHELL_BOUND)
FORBIDDEN_MODULES = ("composite_density", "so3_grids", "pose_marginalization", "shell_bounds", "intervals")
STAGES = ["state input", "engagement order", "closure pair selection", "junction support",
          "geometry input", "span intervals", "closure sweep"]
SPY_TARGETS = (
    "gotne.cassette_closure.chain_closure_feasible",
    "gotne.cassette_budget.closure_span_budget",
    "gotne.cassette_budget.cassette_contour_budget",
    "gotne.cassette_frames.cassette_effective_anchor",
)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
def node_cfg(policy=None, position=(0.0, 0.0, 0.0), **overrides):
    """The budget fixture with a root anchor position."""
    cfg = budget_cfg(policy, **overrides)
    return replace(cfg, anchors=(AnchorSpec(id="a0", surface_id="S0", position=position),))


def shell_cfg():
    """EXCLUDED_SHELL_BOUND needs unresolved_occupancy_fraction on every module (D4)."""
    fraction = {"unresolved_occupancy_fraction": 0.5}
    return node_cfg(SHELL, modules={"D1": fraction, "D2": fraction, "D3": fraction})


def site_context(d, tolerances=None, orientation_t1=R90):
    """Target t1 at (d, 0, 0): the node gate of D1 from ROOT (origin) sees d."""
    return make_context({"t1": (d, 0.0, 0.0)}, {"t1": orientation_t1}, tolerances)


def evaluate(st, cfg, context):
    return evaluate_state(st, cfg, cfg.policy, context)


def certify(st, cfg, context):
    result = evaluate(st, cfg, context)
    assert result.status is Status.VALID, result.as_dict()
    return issue_state_certificate(result, st, cfg, cfg.policy, context)


def node(node_id, st, cfg, context):
    return evaluate_node(node_id, certify(st, cfg, context), cfg, cfg.policy)


def diagnostics_of(result, code):
    return [d for d in result.diagnostics if d.code == code]


def only(result, code):
    (record,) = diagnostics_of(result, code)
    return record


def as_json(result):
    return json.dumps(result.as_dict(), sort_keys=True, allow_nan=False)


@contextlib.contextmanager
def spies():
    """Call-counting spies on the four canonical spy paths (decision record B)."""
    with contextlib.ExitStack() as stack:
        found = {}
        for target in SPY_TARGETS:
            module_name, attribute = target.rsplit(".", 1)
            original = getattr(importlib.import_module(module_name), attribute)
            found[attribute] = stack.enter_context(mock.patch(target, wraps=original))
        yield found


def phase2_fields(**overrides):
    fields = dict(
        method_id="evaluate_state",
        upstream_state={"state_hash": "a" * 64, "context_hash": "b" * 64, "assignments": {}},
        numerical_tolerance_used={"eps_len_nm": 1e-9, "eps_rotation": 1e-9},
        result_id="st-" + "c" * 64,
    )
    fields.update(overrides)
    return fields


def legacy_make_config_result(object_id, status, status_reason, diagnostics, declared_assumptions=(),
                              method_id="validate_cassette_config", method_version=METHOD_VERSION):
    """The Phase 1c implementation, verbatim: the L7 golden reference."""
    values, zeroed, nulled = apply_status_field_pattern(status, None)
    if status in VETO_SET:
        label, exactness = Provenance.EXACT_STRUCTURAL_VETO, Exactness.EXACT
    else:
        label, exactness = Provenance.NOT_COMPUTED, Exactness.UNDEFINED
    return EvaluationResult(
        object_kind="CONFIG", object_id=object_id, status=status, status_reason=status_reason,
        exact_or_approximate=exactness,
        provenance=ProvenanceRecord(worst_label=label, contributing_labels=(label,), method_id=method_id,
                                    method_version=method_version, declared_assumptions=tuple(declared_assumptions)),
        values=values, value_intervals={}, units={k: CANONICAL_UNITS[k] for k in values if k in CANONICAL_UNITS},
        zeroed_due_to_status=zeroed, nulled_due_to_status=nulled, diagnostics=tuple(diagnostics),
        upstream_state=None, numerical_tolerance_used=None,
    )


class FixtureSanity(unittest.TestCase):
    def test_fixtures_valid_under_phase1c(self):
        for cfg in (node_cfg(), node_cfg(MARGINALIZED), node_cfg(FIXED_RIGID), node_cfg(STRICT), shell_cfg()):
            self.assertIs(validate_cassette_config(cfg).status, Status.VALID)


# --------------------------------------------------------------------------
# Migration Step 2: builder, payload rule, freezing (AP-4, AP-5, AP-11)
# --------------------------------------------------------------------------
class StatusBuilder(unittest.TestCase):
    def test_object_kinds_closed(self):
        self.assertEqual(OBJECT_KINDS, ("CONFIG", "STATE", "NODE"))
        with self.assertRaises(ValueError):
            replace(validate_cassette_config(ref_cassette_3()), object_kind="PATH")

    def test_make_result_per_status_class(self):
        valid = make_result("STATE", "S:x", Status.VALID, "STATE_NOT_VETOED", (), **phase2_fields())
        self.assertIs(valid.exact_or_approximate, Exactness.UNDEFINED)
        self.assertIs(valid.provenance.worst_label, Provenance.NOT_COMPUTED)
        self.assertTrue(all(v is None for v in valid.values.values()))
        self.assertEqual(dict(valid.value_intervals), {})
        veto = make_result("STATE", "S:x", Status.UNREACHABLE, "CHAIN_CLOSURE_VIOLATED", (),
                           veto_provenance=Provenance.EXACT_GEOMETRIC_VETO, **phase2_fields())
        self.assertIs(veto.exact_or_approximate, Exactness.EXACT)
        self.assertTrue(veto.zeroed_due_to_status)
        unknown = make_result("STATE", "S:x", Status.DEGENERATE, "ENGAGED_POSE_UNDERDETERMINED", (), **phase2_fields())
        self.assertTrue(unknown.nulled_due_to_status)
        for status_value, veto_label in ((Status.INFEASIBLE, None), (Status.INFEASIBLE, Provenance.NOT_COMPUTED),
                                         (Status.INFEASIBLE, "EXACT_STRUCTURAL_VETO"),
                                         (Status.VALID, Provenance.EXACT_STRUCTURAL_VETO),
                                         (Status.APPROXIMATION_REQUIRED, None)):
            with self.subTest(status=status_value, veto=veto_label), self.assertRaises(ValueError):
                make_result("STATE", "S:x", status_value, "r", (), veto_provenance=veto_label, **phase2_fields())

    def test_make_config_result_golden(self):  # L7
        diagnostics = validate_cassette_config(T34ThreeArmStar().build()).diagnostics
        for status_value in Status:
            with self.subTest(status=status_value):
                args = ("cfg-1", status_value, "SOME_REASON", diagnostics, ("a=1", "b=2"), "m", "9.9")
                self.assertEqual(make_config_result(*args).as_dict(), legacy_make_config_result(*args).as_dict())
        configs = (ref_cassette_3(), T34ThreeArmStar().build(), replace(ref_cassette_3(), cassettes=()),
                   ref_cassette_3(policy=base_policy(topology_mode=TopologyMode.GENERAL_DAG)),
                   ref_cassette_3(policy=STRICT, dep_edges=(DepEdge("D3", "D1", DepEdgeKind.REQUIRES),)))
        validators = (validate_cassette_config, validate_cassette_topology, validate_cassette_order_constraints,
                      validate_cassette_policy_fields, validate_cassette_identity_admissibility)
        for cfg in configs:
            for validator in validators:
                result = validator(cfg)
                legacy = legacy_make_config_result(result.object_id, result.status, result.status_reason,
                                                   result.diagnostics, result.provenance.declared_assumptions,
                                                   result.provenance.method_id)
                with self.subTest(cfg=cfg.id, validator=validator.__name__):
                    self.assertEqual(result.as_dict(), legacy.as_dict())

    def test_payload_free_results_undefined(self):  # L6
        results = (validate_cassette_config(ref_cassette_3()),
                   make_result("STATE", "S:x", Status.VALID, "STATE_NOT_VETOED", (), **phase2_fields()),
                   make_result("NODE", "D1", Status.DEGENERATE, "ENGAGED_POSE_UNDERDETERMINED", (),
                               **phase2_fields(method_id="evaluate_node", result_id="nd-" + "c" * 64)))
        for result in results:
            for exactness in (Exactness.EXACT, Exactness.APPROXIMATE, Exactness.BOUND):
                with self.subTest(kind=result.object_kind, exactness=exactness), self.assertRaises(ValueError):
                    replace(result, exact_or_approximate=exactness)

    def test_veto_labels_only_on_vetoes(self):  # L6
        valid = make_result("STATE", "S:x", Status.VALID, "STATE_NOT_VETOED", (), **phase2_fields())
        veto = make_result("STATE", "S:x", Status.UNREACHABLE, "CHAIN_CLOSURE_VIOLATED", (),
                           veto_provenance=Provenance.EXACT_GEOMETRIC_VETO, **phase2_fields())
        for build in (
            lambda: replace(valid, provenance=ProvenanceRecord(Provenance.EXACT_GEOMETRIC_VETO)),
            lambda: replace(valid, provenance=ProvenanceRecord(Provenance.NOT_COMPUTED,
                                                               (Provenance.EXACT_STRUCTURAL_VETO,))),
            lambda: replace(veto, provenance=ProvenanceRecord(Provenance.NOT_COMPUTED)),
            lambda: replace(valid, provenance=ProvenanceRecord(Provenance.BOUND_ONLY)),
            lambda: replace(valid, provenance=ProvenanceRecord(Provenance.ANALYTIC_APPROXIMATION)),
        ):
            with self.assertRaises(ValueError):
                build()

    def test_config_and_phase2_field_rules(self):
        config = validate_cassette_config(ref_cassette_3())
        good = phase2_fields()
        for build in (
            lambda: replace(config, result_id="st-" + "c" * 64),
            lambda: replace(config, upstream_state=good["upstream_state"]),
            lambda: make_result("STATE", "S:x", Status.VALID, "r", (), **phase2_fields(result_id=None)),
            lambda: make_result("NODE", "D1", Status.VALID, "r", (), **phase2_fields(upstream_state=None)),
            lambda: make_result("STATE", "S:x", Status.VALID, "r", (), **phase2_fields(numerical_tolerance_used=None)),
            lambda: make_result("STATE", "S:x", Status.VALID, "r", (),
                                **phase2_fields(upstream_state=dict(good["upstream_state"], extra=1))),
            lambda: make_result("STATE", "S:x", Status.VALID, "r", (),
                                **phase2_fields(numerical_tolerance_used={"eps_len_nm": 1, "eps_rotation": 1e-9})),
        ):
            with self.assertRaises(ValueError):
                build()

    def test_upstream_state_immutable_and_detached(self):  # L9
        source = {"state_hash": "a" * 64, "context_hash": "b" * 64,
                  "assignments": {"D1": {"label": "ENGAGED", "target_id": "t1"}}}
        result = make_result("STATE", "S:x", Status.VALID, "r", (), **phase2_fields(upstream_state=source))
        source["assignments"]["D1"]["target_id"] = "changed"
        source["state_hash"] = "z"
        self.assertEqual(result.upstream_state["assignments"]["D1"]["target_id"], "t1")
        self.assertEqual(result.upstream_state["state_hash"], "a" * 64)
        with self.assertRaises(TypeError):
            result.upstream_state["state_hash"] = "x"
        with self.assertRaises(TypeError):
            result.upstream_state["assignments"]["D1"]["label"] = "x"
        with self.assertRaises(TypeError):
            result.numerical_tolerance_used["eps_len_nm"] = 1.0
        exported = result.as_dict()["upstream_state"]
        self.assertIs(type(exported), dict)
        exported["assignments"]["D1"]["label"] = "mutated"
        self.assertEqual(result.as_dict()["upstream_state"]["assignments"]["D1"]["label"], "ENGAGED")
        for bad_leaf in (float("nan"), object(), b"bytes"):
            with self.subTest(leaf=type(bad_leaf).__name__), self.assertRaises(TypeError):
                make_result("STATE", "S:x", Status.VALID, "r", (),
                            **phase2_fields(upstream_state=dict(source, assignments={"D1": {"x": bad_leaf}})))

    def test_frozen_json_quantities(self):
        frozen = status._freeze_json({"a": [1, {"b": Tri.FALSE}], "c": None})
        self.assertEqual(json.loads(json.dumps(frozen, sort_keys=True)), {"a": [1, {"b": "FALSE"}], "c": None})
        for mutate in (lambda: frozen.__setitem__("x", 1), lambda: frozen["a"][1].update(b=2), lambda: frozen.pop("a")):
            with self.assertRaises(TypeError):
                mutate()
        with self.assertRaises(TypeError):
            status._freeze_json(float("inf"))


# --------------------------------------------------------------------------
# result_identity (AP-9, L8)
# --------------------------------------------------------------------------
class ResultIdentity(unittest.TestCase):
    def test_form_and_determinism(self):
        components = ["a" * 64, "b" * 64, "c" * 64, METHOD_VERSION, "evaluate_state", TopologyMode.LINEAR_ORDERED_CASSETTE]
        state_id = result_identity("STATE", components)
        self.assertRegex(state_id, r"^st-[0-9a-f]{64}$")
        self.assertEqual(state_id, result_identity("STATE", tuple(components)))
        self.assertRegex(result_identity("NODE", components), r"^nd-[0-9a-f]{64}$")
        self.assertNotEqual(result_identity("NODE", components)[3:], state_id[3:])
        for index in range(len(components)):
            changed = list(components)
            changed[index] = "LINEAR_ORDERED_CASSETTE" if index == 5 else "x"
            self.assertNotEqual(result_identity("STATE", changed), state_id, index)
        with self.assertRaises(ValueError):
            result_identity("CONFIG", components)
        with self.assertRaises(TypeError):
            result_identity("STATE", "abc")

    def test_state_result_id_formula_and_sensitivity(self):
        cfg, context = node_cfg(), separated(2.0, downstream_target="t3")
        result = evaluate(S13, cfg, context)
        expected = result_identity("STATE", [config_identity_hash(cfg), state_identity_hash(S13),
                                             context_identity_hash(context), METHOD_VERSION, "evaluate_state",
                                             TopologyMode.LINEAR_ORDERED_CASSETTE])
        self.assertEqual(result.result_id, expected)
        self.assertEqual(result.object_id, "S:" + state_identity_hash(S13))
        changed = (
            evaluate(S13, node_cfg(tethers={"s1": {"L": 1.75}}), context),  # config
            evaluate(state(engaged("D1", "t1"), engaged("D3", "t2")),  # state
                     cfg, separated(2.0, downstream_target="t3", t2=(3.25, 0.0, 0.0))),
            evaluate(S13, cfg, separated(2.0, downstream_target="t3",  # context
                                         tolerances=NumericalTolerances(eps_len_nm=1e-6))),
        )
        for other in changed:
            self.assertNotEqual(other.result_id, result.result_id)
        self.assertEqual(evaluate(S13, node_cfg(), separated(2.0, downstream_target="t3")).result_id, result.result_id)

    def test_equal_result_id_implies_equal_as_dict(self):  # H with AP-27 and A2
        cfg, context = node_cfg(), separated(2.0, downstream_target="t3")
        variants = (S13, state(engaged("D3", "t3"), engaged("D1", "t1")),
                    state(engaged("D1", "t1"), unengaged("D2"), engaged("D3", "t3")),
                    state(engaged("D1", "t1"), engaged("D3", "t3"), unengaged("D7"), unengaged("D8")))
        results = [evaluate(st, cfg, context) for st in variants]
        self.assertEqual(len({r.result_id for r in results}), 1)
        self.assertEqual(len({as_json(r) for r in results}), 1)

    def test_state_result_stable_across_hash_seeds(self):
        code = (
            "import sys, json; sys.path[:0]=[{r!r},{t!r}];"
            "from test_phase2_cassette_node import node_cfg, evaluate, S13, separated;"
            "print(json.dumps(evaluate(S13, node_cfg(), separated(9.0, downstream_target='t3')).as_dict(),"
            " sort_keys=True, allow_nan=False))"
        ).format(r=str(ROOT_DIR), t=str(ROOT_DIR / "tests"))
        outs = set()
        for seed in ("1", "2", "977"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outs.add(subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True,
                                    check=True).stdout.strip())
        self.assertEqual(len(outs), 1)


# --------------------------------------------------------------------------
# evaluate_state: sweep outcomes (T79, OQ-3 mapping, precedence)
# --------------------------------------------------------------------------
class EvaluateStateSweep(unittest.TestCase):
    def assertNoPhase2Payload(self, result):  # L14
        self.assertTrue(all(v is None or v == 0.0 for v in result.values.values()))
        self.assertEqual(dict(result.value_intervals), {})
        text = as_json(result)
        for word in ("SHELL_BOUND\"", "BOUND_ONLY", "ANALYTIC_APPROXIMATION", "\"BOUND\"", "APPROXIMATE\""):
            self.assertNotIn(word, text)

    def test_t79_single_engaged_module(self):
        cfg = node_cfg()
        with spies() as spy:
            result = evaluate(S1, cfg, site_context(2.0))
        self.assertIs(result.status, Status.VALID)
        self.assertEqual(result.status_reason, StateReason.STATE_NOT_VETOED)
        sweep = only(result, StateCode.CLOSURE_SWEEP)
        self.assertIn("closure_pairs", sweep.quantities)
        self.assertEqual(sweep.quantities["closure_pairs"], ())
        serialized = json.loads(as_json(result))["diagnostics"]
        self.assertEqual([d["quantities"]["closure_pairs"] for d in serialized if d["code"] == "CLOSURE_SWEEP"], [[]])
        self.assertEqual(sweep.quantities["closure_predicate_invocations"], 0)
        self.assertIn("empty domain", sweep.message)
        self.assertEqual({name: s.call_count for name, s in spy.items()},
                         dict.fromkeys(("chain_closure_feasible", "closure_span_budget", "cassette_contour_budget",
                                        "cassette_effective_anchor"), 0))
        self.assertTrue(all(v is None for v in result.values.values()))
        self.assertIs(result.exact_or_approximate, Exactness.UNDEFINED)
        self.assertFalse(result.zeroed_due_to_status or result.nulled_due_to_status)
        self.assertNotIn("vetoing_state_result_id", as_json(result))
        self.assertNotIn(result.status_reason, (StateReason.CHAIN_CLOSURE_VIOLATED,
                                                StateReason.ENGAGEMENT_ORDER_VIOLATION,
                                                StateReason.ENGAGED_POSE_UNDERDETERMINED))
        self.assertNoPhase2Payload(result)

    def test_feasible_pairs_invoke_predicate_once_each_in_order(self):
        cfg = node_cfg()
        context = make_context({"t1": (0.0, 0.0, 0.0), "t2": (2.25, 0.0, 0.0), "t3": (3.25, 0.0, 0.0)})
        with spies() as spy:
            result = evaluate(S123, cfg, context)
        self.assertIs(result.status, Status.VALID)
        self.assertEqual([c.args[:2] for c in spy["chain_closure_feasible"].call_args_list], [("D1", "D2"), ("D2", "D3")])
        sweep = only(result, StateCode.CLOSURE_SWEEP)
        self.assertEqual(sweep.quantities["closure_pairs"], (("D1", "D2"), ("D2", "D3")))
        self.assertEqual(sweep.quantities["closure_predicate_invocations"], 2)
        self.assertEqual(spy["cassette_contour_budget"].call_count, 0)
        self.assertEqual(spy["cassette_effective_anchor"].call_count, 0)

    def test_false_maps_to_chain_closure_violated(self):
        result = evaluate(S13, node_cfg(), separated(9.0, downstream_target="t3"))
        self.assertIs(result.status, Status.UNREACHABLE)
        self.assertEqual(result.status_reason, StateReason.CHAIN_CLOSURE_VIOLATED)
        self.assertIs(result.exact_or_approximate, Exactness.EXACT)
        self.assertIs(result.provenance.worst_label, Provenance.EXACT_GEOMETRIC_VETO)
        self.assertTrue(result.zeroed_due_to_status)
        violated = only(result, StateCode.CHAIN_CLOSURE_VIOLATED)
        self.assertEqual(dict(violated.quantities), {"upstream_module_id": "D1", "downstream_module_id": "D3",
                                                     "d_nm": 9.0, "D_min_nm": 0.0, "D_max_nm": 3.75,
                                                     "eps_len_nm": 1e-9, "side": "ABOVE_D_MAX"})
        below = evaluate(S13, node_cfg(modules={"D2": {"exit_offset": (5.0, 0.0, 0.0)}}),
                         separated(1.0, downstream_target="t3"))
        self.assertEqual(only(below, StateCode.CHAIN_CLOSURE_VIOLATED).quantities["side"], "BELOW_D_MIN")
        self.assertNoPhase2Payload(result)

    def test_undetermined_maps_to_engaged_pose_underdetermined(self):
        result = evaluate(S13, node_cfg(MARGINALIZED), separated(2.0, downstream_target="t3"))
        self.assertIs(result.status, Status.DEGENERATE)
        self.assertEqual(result.status_reason, StateReason.ENGAGED_POSE_UNDERDETERMINED)
        self.assertIs(result.exact_or_approximate, Exactness.UNDEFINED)
        self.assertIs(result.provenance.worst_label, Provenance.NOT_COMPUTED)
        self.assertTrue(result.nulled_due_to_status)
        self.assertNotIn(cassette_closure.cassette_frames.POSE_PLACEMENT_ASSUMPTION, result.provenance.declared_assumptions)
        self.assertEqual(diagnostics_of(result, StateCode.DERIVED_RIGID_SPAN), [])

    def test_mixed_outcomes_resolved_by_precedence(self):  # §3.3: DEGENERATE (3) beats UNREACHABLE (4)
        cfg = node_cfg()
        context = make_context({"t1": (0.0, 0.0, 0.0), "t2": (9.0, 0.0, 0.0), "t3": (19.0, 0.0, 0.0)})
        for outcomes, expected in (
            ((Tri.FALSE, Tri.UNDETERMINED), (Status.DEGENERATE, StateReason.ENGAGED_POSE_UNDERDETERMINED)),
            ((Tri.UNDETERMINED, Tri.FALSE), (Status.DEGENERATE, StateReason.ENGAGED_POSE_UNDERDETERMINED)),
            ((Tri.TRUE, Tri.FALSE), (Status.UNREACHABLE, StateReason.CHAIN_CLOSURE_VIOLATED)),
        ):
            with self.subTest(outcomes=outcomes), \
                    mock.patch("gotne.cassette_closure.chain_closure_feasible", side_effect=list(outcomes)):
                result = evaluate(S123, cfg, context)
                self.assertEqual((result.status, result.status_reason), expected)
                self.assertEqual(len(diagnostics_of(result, StateCode.CHAIN_CLOSURE_VIOLATED)),
                                 outcomes.count(Tri.FALSE))
                self.assertEqual(len(diagnostics_of(result, StateCode.ENGAGED_POSE_UNDERDETERMINED)),
                                 outcomes.count(Tri.UNDETERMINED))
        with mock.patch("gotne.cassette_closure.chain_closure_feasible", return_value=True), \
                self.assertRaises(RuntimeError):
            evaluate(S123, cfg, context)


# --------------------------------------------------------------------------
# evaluate_state: stage order (record I) and fail-closed inputs
# --------------------------------------------------------------------------
class EvaluateStateStages(unittest.TestCase):
    def assertSkipped(self, result, stages, because=None):
        skipped = [d for d in result.diagnostics if d.code == Code.CHECK_SKIPPED and d.quantities["check"] in STAGES]
        self.assertEqual([d.quantities["check"] for d in skipped], stages)
        if because is not None:
            self.assertTrue(all(d.quantities["because"] == because for d in skipped))

    def test_stage_1_entry(self):
        cfg, context = node_cfg(), site_context(2.0)
        for args in ((S1.assignments, cfg, cfg.policy, context), (S1, {}, cfg.policy, context),
                     (S1, cfg, "policy", context), (S1, cfg, cfg.policy, None)):
            with self.assertRaises(TypeError):
                evaluate_state(*args)
        with self.assertRaisesRegex(ValueError, "AP-17"):
            evaluate_state(S1, cfg, STRICT, context)
        with self.assertRaises(TypeError):
            evaluate_state(S1, replace(cfg, modules={"D1": cfg.modules[0]}), cfg.policy, context)

    def test_stage_2_config_not_valid(self):
        broken = replace(node_cfg(), cassettes=())
        with spies() as spy:
            result = evaluate(S13, broken, separated(2.0, downstream_target="t3"))
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertEqual(result.status_reason, Reason.TOPOLOGY)
        self.assertIs(result.provenance.worst_label, Provenance.EXACT_STRUCTURAL_VETO)
        self.assertSkipped(result, STAGES, "Phase 1c configuration validation is not VALID")
        self.assertTrue(all(s.call_count == 0 for s in spy.values()))
        dag = node_cfg(base_policy(topology_mode=TopologyMode.GENERAL_DAG))
        not_applicable = evaluate(S1, dag, site_context(2.0))
        self.assertEqual((not_applicable.status, not_applicable.status_reason),
                         (Status.NOT_EVALUATED, Reason.NOT_APPLICABLE))
        self.assertIs(not_applicable.exact_or_approximate, Exactness.UNDEFINED)

    def test_stage_2_config_without_identity_raises(self):  # amendment A2
        cfg = node_cfg()
        unhashable = replace(cfg, cassettes=(replace(cfg.cassettes[0], explicit_partial_order={("D1", "D2")}),))
        with self.assertRaisesRegex(ValueError, "canonical identity"):
            evaluate(S1, unhashable, site_context(2.0))

    def test_stage_3_state_input(self):  # L18, amendment A2
        cfg, context = node_cfg(), separated(2.0, downstream_target="t3")
        bad = state(engaged("D1", "t1"), engaged("D7", "t3"), engaged("D9", "t3"), engaged("D3", "t3"))
        with spies() as spy:
            result = evaluate(bad, cfg, context)
        self.assertEqual((result.status, result.status_reason), (Status.INFEASIBLE, StateReason.STATE_INPUT_INVALID))
        self.assertEqual([dict(d.quantities) for d in diagnostics_of(result, StateCode.STATE_INPUT_INVALID)],
                         [{"module_id": "D7", "defect": "UNKNOWN_MODULE"}, {"module_id": "D9", "defect": "UNKNOWN_MODULE"}])
        self.assertSkipped(result, STAGES[1:])
        self.assertTrue(all(s.call_count == 0 for s in spy.values()))
        omitted = evaluate(S13, cfg, context)
        outside_unengaged = evaluate(state(engaged("D1", "t1"), engaged("D3", "t3"), unengaged("D7")), cfg, context)
        self.assertIs(outside_unengaged.status, Status.VALID)
        self.assertEqual(as_json(outside_unengaged), as_json(omitted))

    def test_stage_4_order_violation_t83_policy_b(self):  # L12, N16
        cfg = node_cfg(STRICT)
        with spies() as spy:
            result = evaluate(S13, cfg, separated(2.0, downstream_target="t3"))
        self.assertEqual((result.status, result.status_reason),
                         (Status.INFEASIBLE, StateReason.ENGAGEMENT_ORDER_VIOLATION))
        self.assertIs(result.provenance.worst_label, Provenance.EXACT_STRUCTURAL_VETO)
        violation = only(result, StateCode.ENGAGEMENT_ORDER_VIOLATION)
        self.assertEqual(violation.message, "engaged set is not down-closed under R_union")
        self.assertEqual(dict(violation.quantities), {"module_id": "D3", "missing_predecessors": ("D2",),
                                                      "engagement_order_policy": "STRICT_PROXIMAL_TO_DISTAL"})
        self.assertSkipped(result, STAGES[2:], "state is not down-closed under R_union")
        self.assertNotIn("closure_pairs", as_json(result))
        self.assertTrue(all(s.call_count == 0 for s in spy.values()))
        self.assertEqual(result.values["conditional_probability"], 0.0)
        self.assertTrue(result.zeroed_due_to_status)

    def test_stage_4_r_union_sources(self):
        cases = (
            (node_cfg(STRICT), state(engaged("D3", "t3")), ("D1", "D2")),
            (replace(node_cfg(), dep_edges=(DepEdge("D1", "D3", DepEdgeKind.REQUIRES),)), state(engaged("D3", "t3")),
             ("D1",)),
            (replace(node_cfg(base_policy(engagement_order_policy=EngagementOrderPolicy.EXPLICIT_PARTIAL_ORDER)),
                     cassettes=(replace(node_cfg().cassettes[0], explicit_partial_order=(("D2", "D3"),)),)),
             S13, ("D2",)),
        )
        for cfg, st, missing in cases:
            with self.subTest(policy=cfg.policy.engagement_order_policy, missing=missing):
                self.assertIs(validate_cassette_config(cfg).status, Status.VALID)
                result = evaluate(st, cfg, separated(2.0, downstream_target="t3"))
                self.assertEqual(only(result, StateCode.ENGAGEMENT_ORDER_VIOLATION).quantities["missing_predecessors"],
                                 missing)
        self.assertIs(evaluate(S123, node_cfg(STRICT), make_context(
            {"t1": (0.0, 0.0, 0.0), "t2": (2.25, 0.0, 0.0), "t3": (3.25, 0.0, 0.0)})).status, Status.VALID)

    def test_stage_3_precedes_stage_4(self):
        result = evaluate(state(engaged("D3", "t3"), engaged("D7", "t3")), node_cfg(STRICT),
                          separated(2.0, downstream_target="t3"))
        self.assertEqual(result.status_reason, StateReason.STATE_INPUT_INVALID)

    def test_stage_6_junction_support(self):  # L17, OQ-7
        rigid = node_cfg(FIXED_RIGID)
        with spies() as spy:
            result = evaluate(S13, rigid, make_context({"t1": (0.0, 0.0, 0.0)}))  # t3 missing: stage 7 not reached
        self.assertEqual((result.status, result.status_reason),
                         (Status.NOT_EVALUATED, StateReason.JUNCTION_GEOMETRY_UNSUPPORTED))
        self.assertIs(result.exact_or_approximate, Exactness.UNDEFINED)
        self.assertSkipped(result, STAGES[4:])
        self.assertTrue(all(s.call_count == 0 for s in spy.values()))
        self.assertNotEqual(as_json(result), as_json(evaluate(S13, node_cfg(), separated(2.0, downstream_target="t3"))))
        self.assertIs(evaluate(S1, rigid, site_context(2.0)).status, Status.VALID)  # N0: no pair, no junction geometry

    def test_stage_7_geometry_input_is_a_result(self):  # L16, OQ-5
        with spies() as spy:
            missing = evaluate(state(engaged("D1", "t9")), node_cfg(), site_context(2.0))  # zero pairs
        self.assertEqual((missing.status, missing.status_reason), (Status.INFEASIBLE, StateReason.GEOMETRY_INPUT_INVALID))
        self.assertEqual(dict(only(missing, StateCode.GEOMETRY_INPUT_INVALID).quantities),
                         {"source_id": "D1", "field": "target_id", "defect": "TARGET_NOT_IN_CONTEXT"})
        self.assertSkipped(missing, STAGES[5:])
        self.assertTrue(all(s.call_count == 0 for s in spy.values()))
        cfg = node_cfg(modules={"D2": {"entry_offset": MISSING}}, tethers={"s2": {"L": MISSING}})
        context = make_context({"t1": (0.0, 0.0, 0.0), "t2": (2.0, 0.0, 0.0), "t3": (4.0, 0.0, 0.0)}, {"t1": None})
        with spies() as spy:
            result = evaluate(S123, cfg, context)
        self.assertEqual(result.status_reason, StateReason.GEOMETRY_INPUT_INVALID)
        self.assertEqual([(d.quantities["source_id"], d.quantities["field"], d.quantities["defect"])
                          for d in diagnostics_of(result, StateCode.GEOMETRY_INPUT_INVALID)],
                         [("t1", "orientation", "ORIENTATION_REQUIRED"), ("D2", "entry_offset", "MISSING"),
                          ("s2", "L", "MISSING")])
        self.assertEqual(spy["chain_closure_feasible"].call_count, 0)

    def test_stage_8_span_intervals(self):
        interval = node_cfg(tethers={"s1": {"L_min": 2.0}})
        result = evaluate(S12, interval, make_context({"t1": (0.0, 0.0, 0.0), "t2": (2.25, 0.0, 0.0)}))
        self.assertEqual((result.status, result.status_reason), (Status.INFEASIBLE, StateReason.SPAN_INTERVAL_INVALID))
        self.assertEqual(dict(only(result, StateCode.SPAN_INTERVAL_INVALID).quantities),
                         {"source_id": "s1", "field": "L_min", "defect": "L_MIN_EXCEEDS_L"})
        self.assertSkipped(result, STAGES[6:])
        both = evaluate(S12, node_cfg(tethers={"s1": {"L_min": 2.0}}, modules={"D2": {"entry_offset": MISSING}}),
                        make_context({"t1": (0.0, 0.0, 0.0), "t2": (2.25, 0.0, 0.0)}))
        self.assertEqual(both.status_reason, StateReason.GEOMETRY_INPUT_INVALID)

    def test_no_direct_call_exception_escapes(self):
        cfg = node_cfg(modules={"D1": {"exit_offset": (1.0, 0.0)}})
        result = evaluate(S12, cfg, make_context({"t1": (0.0, 0.0, 0.0), "t2": (2.25, 0.0, 0.0)}))
        self.assertEqual(result.status_reason, StateReason.GEOMETRY_INPUT_INVALID)
        with self.assertRaises(ValueError):
            chain_closure_feasible("D1", "D2", S12, cfg, cfg.policy,
                                   make_context({"t1": (0.0, 0.0, 0.0), "t2": (2.25, 0.0, 0.0)}))

    def test_serialization_of_every_stage_outcome(self):
        cases = (evaluate(S1, node_cfg(), site_context(2.0)),
                 evaluate(S13, node_cfg(), separated(9.0, downstream_target="t3")),
                 evaluate(S13, node_cfg(STRICT), separated(2.0, downstream_target="t3")),
                 evaluate(S13, node_cfg(FIXED_RIGID), separated(2.0, downstream_target="t3")),
                 evaluate(state(engaged("D1", "t9")), node_cfg(), site_context(2.0)),
                 evaluate(S13, replace(node_cfg(), cassettes=()), separated(2.0, downstream_target="t3")))
        for result in cases:
            with self.subTest(reason=result.status_reason):
                json.loads(as_json(result))
                self.assertEqual(result.provenance.method_version, METHOD_VERSION)  # L11
                self.assertRegex(result.result_id, r"^st-[0-9a-f]{64}$")


# --------------------------------------------------------------------------
# evaluate_state: provenance and diagnostic context (K, OQ-8, N12-N15, T83 A)
# --------------------------------------------------------------------------
class EvaluateStateProvenance(unittest.TestCase):
    def test_placement_and_derived_span_assumptions(self):
        result = evaluate(S13, node_cfg(), separated(2.0, downstream_target="t3"))
        assumptions = result.provenance.declared_assumptions
        self.assertIn("topology_mode=LINEAR_ORDERED_CASSETTE", assumptions)
        self.assertIn("pose_placement=CAPTURE_POINT_ON_TARGET_SITE", assumptions)
        self.assertIn("rigid_span_basis=DERIVED_FROM_ENTRY_EXIT_OFFSETS", assumptions)
        self.assertNotIn(GEOMETRY_PRESENCE_ASSUMPTION, assumptions)
        span = only(result, StateCode.DERIVED_RIGID_SPAN)
        self.assertEqual(span.quantities["element_ids"], ("D2.span",))
        self.assertIn("derived from declared entry/exit offsets (provisional)", span.message)
        adjacent = evaluate(S12, node_cfg(), make_context({"t1": (0.0, 0.0, 0.0), "t2": (2.25, 0.0, 0.0)}))
        self.assertIn("pose_placement=CAPTURE_POINT_ON_TARGET_SITE", adjacent.provenance.declared_assumptions)
        self.assertNotIn("rigid_span_basis=DERIVED_FROM_ENTRY_EXIT_OFFSETS", adjacent.provenance.declared_assumptions)
        single = evaluate(S1, node_cfg(), site_context(2.0)).provenance.declared_assumptions
        self.assertFalse([a for a in single if a.startswith(("pose_placement", "rigid_span_basis"))])

    def test_unresolved_upstream_ids(self):
        cases = ((S13, ("D2",)), (S1, ()), (state(engaged("D3", "t3")), ("D1", "D2")), (S123, ()))
        for st, expected in cases:
            context = make_context({"t1": (0.0, 0.0, 0.0), "t2": (2.25, 0.0, 0.0), "t3": (3.25, 0.0, 0.0)})
            if st == S13:
                context = separated(2.0, downstream_target="t3")
            with self.subTest(state=[a.module_id for a in st.engaged_assignments()]):
                record = only(evaluate(st, node_cfg(), context), StateCode.UNRESOLVED_UPSTREAM)
                self.assertEqual(dict(record.quantities), {"unresolved_upstream_ids": expected})

    def test_t83_policy_a_excluded_shell_bound(self):  # N8-N15, amendment A2 on T83 #11
        result = evaluate(S13, shell_cfg(), separated(2.0, downstream_target="t3"))
        self.assertEqual(only(result, StateCode.CLOSURE_SWEEP).quantities["closure_pairs"], (("D1", "D3"),))
        self.assertEqual(dict(only(result, StateCode.UNRESOLVED_UPSTREAM).quantities),
                         {"unresolved_upstream_ids": ("D2",), "unresolved_upstream_policy": "EXCLUDED_SHELL_BOUND",
                          "downstream_numerical_evaluation_deferred": True})
        self.assertEqual(dict(result.value_intervals), {})
        self.assertTrue(all(v is None for v in result.values.values()))
        self.assertNotIn("BOUND_ONLY", as_json(result))
        self.assertNotIn("SHELL_BOUND", result.status_reason)
        quantities = json.dumps([dict(d.quantities) for d in result.diagnostics]).replace("EXCLUDED_SHELL_BOUND", "")
        for banned in ("SHELL_BOUND", "occupancy", "at_risk", "survival", "obstacle", "weight"):
            self.assertNotIn(banned, quantities)
        d2_records = [d.code for d in result.diagnostics if "D2" in json.dumps(dict(d.quantities))]
        self.assertEqual(sorted(d2_records), sorted([StateCode.UNRESOLVED_UPSTREAM, StateCode.DERIVED_RIGID_SPAN]))

    def test_certificate_only_for_valid(self):
        cfg, context = node_cfg(), separated(2.0, downstream_target="t3")
        result = evaluate(S13, cfg, context)
        cert = issue_state_certificate(result, S13, cfg, cfg.policy, context)
        self.assertIs(cert.state_result, result)
        vetoed = evaluate(S13, cfg, separated(9.0, downstream_target="t3"))
        with self.assertRaises(ValueError):
            issue_state_certificate(vetoed, S13, cfg, cfg.policy, separated(9.0, downstream_target="t3"))


# --------------------------------------------------------------------------
# evaluate_node (OQ-6)
# --------------------------------------------------------------------------
class EvaluateNode(unittest.TestCase):
    def test_valid_node(self):
        cfg = node_cfg()
        result = node("D1", S1, cfg, site_context(2.0))
        self.assertEqual((result.object_kind, result.object_id, result.status, result.status_reason),
                         ("NODE", "D1", Status.VALID, NodeReason.NODE_NOT_VETOED))
        self.assertIs(result.exact_or_approximate, Exactness.UNDEFINED)
        self.assertTrue(all(v is None for v in result.values.values()))
        self.assertEqual(dict(only(result, StateCode.SHIELDING_ANCESTOR).quantities["shielding_ancestor"]),
                         {"kind": "ROOT", "id": None, "module_cassette_index": 0})
        breakdown = only(result, StateCode.CONTOUR_BUDGET).quantities["contour_budget_breakdown"]
        self.assertEqual([e["element_id"] for e in breakdown["elements"]], ["s0.seg", "D1.capture"])
        self.assertEqual((breakdown["D_min_nm"], breakdown["D_max_nm"]), (0.0, 2.5))
        self.assertEqual(dict(only(result, StateCode.UNRESOLVED_UPSTREAM).quantities), {"unresolved_upstream_ids": ()})
        json.loads(as_json(result))

    def test_gate_boundaries_with_eps(self):
        loose = NumericalTolerances(eps_len_nm=EPS)
        cfg = node_cfg()
        for d, expected, side in ((2.5 + EPS, Status.VALID, None), (2.5 + EPS + TINY, Status.UNREACHABLE, "ABOVE_D_MAX")):
            with self.subTest(d=d):
                result = node("D1", S1, cfg, site_context(d, loose))
                self.assertIs(result.status, expected)
                if side:
                    gate = only(result, StateCode.CONTOUR_BUDGET_VIOLATED)
                    self.assertEqual(dict(gate.quantities), {"module_id": "D1", "d_nm": d, "D_min_nm": 0.0,
                                                             "D_max_nm": 2.5, "eps_len_nm": EPS, "side": side})
                    self.assertEqual(result.status_reason, NodeReason.CONTOUR_BUDGET_VIOLATED)
                    self.assertIs(result.provenance.worst_label, Provenance.EXACT_GEOMETRIC_VETO)
                    self.assertTrue(result.zeroed_due_to_status)
        dominated = node_cfg(tethers={"s0": {"L_min": 3.0, "L": 4.0}})  # node budget [2.5, 4.5]
        for d, expected in ((2.5 - EPS, Status.VALID), (2.5 - EPS - TINY, Status.UNREACHABLE)):
            with self.subTest(d=d):
                result = node("D1", S1, dominated, site_context(d, loose))
                self.assertIs(result.status, expected)
        below = node("D1", S1, dominated, site_context(1.0))
        self.assertEqual(only(below, StateCode.CONTOUR_BUDGET_VIOLATED).quantities["side"], "BELOW_D_MIN")
        self.assertIs(node("D1", S1, cfg, site_context(2.5 + EPS)).status, Status.UNREACHABLE)  # default eps

    def test_module_ancestor_node(self):
        cfg, context = node_cfg(), separated(2.0, downstream_target="t3")
        with spies() as spy:
            result = node("D3", S13, cfg, context)
        self.assertIs(result.status, Status.VALID)
        self.assertEqual(spy["cassette_contour_budget"].call_count, 1)
        self.assertEqual(spy["cassette_effective_anchor"].call_count, 1)
        self.assertEqual(dict(only(result, StateCode.SHIELDING_ANCESTOR).quantities["shielding_ancestor"]),
                         {"kind": "MODULE", "id": "D1", "module_cassette_index": 1})
        self.assertEqual(only(result, StateCode.UNRESOLVED_UPSTREAM).quantities["unresolved_upstream_ids"], ("D2",))
        self.assertEqual(only(result, StateCode.DERIVED_RIGID_SPAN).quantities["element_ids"], ("D2.span",))
        assumptions = result.provenance.declared_assumptions
        self.assertIn("pose_placement=CAPTURE_POINT_ON_TARGET_SITE", assumptions)
        self.assertIn("rigid_span_basis=DERIVED_FROM_ENTRY_EXIT_OFFSETS", assumptions)
        self.assertEqual(len(assumptions), len(set(assumptions)))

    def test_node_provenance_carries_its_own_assumptions(self):
        # the state declares neither assumption; only the node's budget / anchor use them
        cfg, context = node_cfg(), make_context({"t2": (3.0, 0.0, 0.0)})
        single = state(engaged("D2", "t2"))
        state_assumptions = evaluate(single, cfg, context).provenance.declared_assumptions
        self.assertNotIn("rigid_span_basis=DERIVED_FROM_ENTRY_EXIT_OFFSETS", state_assumptions)
        root_path = node("D2", single, cfg, context)  # s0, D1.span, s1, D2.capture from ROOT
        self.assertIs(root_path.status, Status.VALID)
        self.assertIn("rigid_span_basis=DERIVED_FROM_ENTRY_EXIT_OFFSETS", root_path.provenance.declared_assumptions)
        self.assertNotIn("pose_placement=CAPTURE_POINT_ON_TARGET_SITE", root_path.provenance.declared_assumptions)
        context = separated(2.0, downstream_target="t3")
        bare = hand_built_state_result(S13, context)  # a VALID STATE result with no declared assumptions
        cert = StateCertificate(bare, S13, context, config_identity_hash(cfg), context_identity_hash(context))
        placed = evaluate_node("D3", cert, cfg, cfg.policy)
        self.assertEqual(placed.provenance.declared_assumptions,
                         ("rigid_span_basis=DERIVED_FROM_ENTRY_EXIT_OFFSETS", "pose_placement=CAPTURE_POINT_ON_TARGET_SITE"))

    def test_node_result_identity_and_upstream_state(self):
        cfg, context = node_cfg(), site_context(2.0)
        cert = certify(S1, cfg, context)
        result = evaluate_node("D1", cert, cfg, cfg.policy)
        self.assertEqual(result.as_dict()["upstream_state"], cert.state_result.as_dict()["upstream_state"])
        self.assertEqual(result.as_dict()["numerical_tolerance_used"], context.tolerances.as_dict())
        expected = result_identity("NODE", [config_identity_hash(cfg), state_identity_hash(S1), "D1",
                                            context_identity_hash(context), METHOD_VERSION, "evaluate_node",
                                            TopologyMode.LINEAR_ORDERED_CASSETTE])
        self.assertEqual(result.result_id, expected)
        self.assertEqual(as_json(result), as_json(evaluate_node("D1", cert, cfg, cfg.policy)))

    def test_fixed_rigid_not_evaluated(self):  # OQ-7
        rigid = node_cfg(FIXED_RIGID)
        with spies() as spy:
            result = node("D1", S1, rigid, site_context(2.0))
        self.assertEqual((result.status, result.status_reason),
                         (Status.NOT_EVALUATED, StateReason.JUNCTION_GEOMETRY_UNSUPPORTED))
        self.assertEqual(spy["cassette_contour_budget"].call_count + spy["cassette_effective_anchor"].call_count, 0)

    def test_node_path_inputs_become_results(self):
        with spies() as spy:
            missing_root = node("D1", S1, node_cfg(position=MISSING, tethers={"s0": {"L": None}}), site_context(2.0))
        self.assertEqual((missing_root.status, missing_root.status_reason),
                         (Status.INFEASIBLE, StateReason.GEOMETRY_INPUT_INVALID))
        self.assertEqual([(d.quantities["source_id"], d.quantities["field"], d.quantities["defect"])
                          for d in diagnostics_of(missing_root, StateCode.GEOMETRY_INPUT_INVALID)],
                         [("a0", "position", "MISSING"), ("s0", "L", "NULL")])
        self.assertEqual(spy["cassette_contour_budget"].call_count + spy["cassette_effective_anchor"].call_count, 0)
        interval = node("D1", S1, node_cfg(tethers={"s0": {"L_min": 3.0}}), site_context(2.0))
        self.assertEqual(interval.status_reason, StateReason.SPAN_INTERVAL_INVALID)

    def test_marginalized_module_ancestor_degenerate(self):
        cfg = node_cfg(MARGINALIZED)
        context = separated(2.0, downstream_target="t3")
        self.assertIs(evaluate(S13, cfg, context).status, Status.DEGENERATE)  # no certificate from evaluate_state
        by_hand = hand_built_state_result(S13, context)
        cert = StateCertificate(by_hand, S13, context, config_identity_hash(cfg), context_identity_hash(context))
        result = evaluate_node("D3", cert, cfg, cfg.policy)
        self.assertEqual((result.status, result.status_reason),
                         (Status.DEGENERATE, StateReason.ENGAGED_POSE_UNDERDETERMINED))
        self.assertIsNotNone(only(result, StateCode.CONTOUR_BUDGET))
        self.assertNotIn("pose_placement=CAPTURE_POINT_ON_TARGET_SITE", result.provenance.declared_assumptions)
        self.assertIs(node("D1", S1, cfg, site_context(2.0, orientation_t1=None)).status, Status.VALID)  # ROOT ancestor

    def test_entry_checks(self):
        cfg, context = node_cfg(), separated(2.0, downstream_target="t3")
        cert = certify(S13, cfg, context)
        for args in ((1, cert, cfg, cfg.policy), ("D3", cert.state_result, cfg, cfg.policy),
                     ("D3", cert, {}, cfg.policy), ("D3", cert, cfg, None)):
            with self.assertRaises(TypeError):
                evaluate_node(*args)
        for node_id, config, policy, pattern in (
            ("D3", cfg, STRICT, "AP-17"),
            ("D3", node_cfg(tethers={"s1": {"L": 1.75}}), cfg.policy, "certificate"),
            ("D2", cfg, cfg.policy, "not an ENGAGED module"),
            ("D9", cfg, cfg.policy, "not an ENGAGED module"),
        ):
            with self.subTest(node=node_id, pattern=pattern), self.assertRaisesRegex(ValueError, pattern):
                evaluate_node(node_id, cert, config, policy)


# --------------------------------------------------------------------------
# propagate_state_veto (G, MNH26)
# --------------------------------------------------------------------------
class PropagateStateVeto(unittest.TestCase):
    def test_closure_veto_propagates_to_every_module(self):
        cfg = node_cfg()
        vetoed = evaluate(S13, cfg, separated(9.0, downstream_target="t3"))
        for node_id in ("D1", "D2", "D3"):
            with self.subTest(node=node_id):
                result = propagate_state_veto(node_id, vetoed, cfg, cfg.policy)
                self.assertEqual((result.object_kind, result.object_id), ("NODE", node_id))
                self.assertEqual((result.status, result.status_reason, result.exact_or_approximate,
                                  result.provenance.worst_label),
                                 (vetoed.status, vetoed.status_reason, vetoed.exact_or_approximate,
                                  vetoed.provenance.worst_label))
                self.assertTrue(result.zeroed_due_to_status)
                (record,) = result.diagnostics
                self.assertEqual(record.code, StateCode.STATE_VETO_PROPAGATED)
                self.assertEqual(dict(record.quantities), {"vetoing_state_result_id": vetoed.result_id,
                                                           "vetoing_status": "UNREACHABLE",
                                                           "vetoing_status_reason": "CHAIN_CLOSURE_VIOLATED"})
                self.assertEqual(result.as_dict()["upstream_state"], vetoed.as_dict()["upstream_state"])
                self.assertNotIn("vetoing_state_result_id", json.dumps(result.as_dict()["upstream_state"]))
                self.assertEqual(result.provenance.declared_assumptions, vetoed.provenance.declared_assumptions)
                self.assertRegex(result.result_id, r"^nd-[0-9a-f]{64}$")
                self.assertEqual(as_json(result), as_json(propagate_state_veto(node_id, vetoed, cfg, cfg.policy)))

    def test_structural_vetoes_propagate(self):
        order = evaluate(S13, node_cfg(STRICT), separated(2.0, downstream_target="t3"))
        result = propagate_state_veto("D3", order, node_cfg(STRICT), STRICT)
        self.assertEqual((result.status_reason, result.provenance.worst_label),
                         (StateReason.ENGAGEMENT_ORDER_VIOLATION, Provenance.EXACT_STRUCTURAL_VETO))
        bad_topology = replace(node_cfg(), modules=(module("D1", 1), module("D2", 7), node_cfg().modules[2]))
        config_veto = evaluate(S13, bad_topology, separated(2.0, downstream_target="t3"))
        self.assertEqual(propagate_state_veto("D2", config_veto, bad_topology, bad_topology.policy).status_reason,
                         Reason.TOPOLOGY)
        no_cassette = replace(node_cfg(), cassettes=())
        with self.assertRaisesRegex(ValueError, "not a module of the cassette"):
            propagate_state_veto("D1", evaluate(S13, no_cassette, separated(2.0, downstream_target="t3")),
                                 no_cassette, no_cassette.policy)

    def test_rejects_non_propagating_inputs(self):
        cfg = node_cfg()
        vetoed = evaluate(S13, cfg, separated(9.0, downstream_target="t3"))
        valid = evaluate(S13, cfg, separated(2.0, downstream_target="t3"))
        degenerate = evaluate(S13, node_cfg(MARGINALIZED), separated(2.0, downstream_target="t3"))
        for label, args in {
            "VALID state": ("D3", valid, cfg, cfg.policy),
            "UNKNOWN_SET state": ("D3", degenerate, node_cfg(MARGINALIZED), MARGINALIZED),
        }.items():
            with self.subTest(case=label), self.assertRaisesRegex(ValueError, "only a vetoed STATE result propagates"):
                propagate_state_veto(*args)
        for label, args in {
            "CONFIG result": ("D3", validate_cassette_config(cfg), cfg, cfg.policy),
            "tampered result_id": ("D3", replace(vetoed, result_id="st-" + "0" * 64), cfg, cfg.policy),
            "other cfg": ("D3", vetoed, node_cfg(tethers={"s1": {"L": 1.75}}), cfg.policy),
            "outside module": ("D9", vetoed, cfg, cfg.policy),
            "policy mismatch": ("D3", vetoed, cfg, STRICT),
        }.items():
            with self.subTest(case=label), self.assertRaises(ValueError):
                propagate_state_veto(*args)
        for args in ((3, vetoed, cfg, cfg.policy), ("D3", vetoed.as_dict(), cfg, cfg.policy),
                     ("D3", vetoed, None, cfg.policy)):
            with self.assertRaises(TypeError):
                propagate_state_veto(*args)


# --------------------------------------------------------------------------
# NodeReason, module surface and import boundary (L4, L13)
# --------------------------------------------------------------------------
class NodeSurface(unittest.TestCase):
    def test_node_reason_closed_set(self):
        values = {v for k, v in vars(NodeReason).items() if not k.startswith("_") and isinstance(v, str)}
        self.assertEqual(values, {"CONTOUR_BUDGET_VIOLATED", "NODE_NOT_VETOED"})
        self.assertEqual(NodeReason.CONTOUR_BUDGET_VIOLATED, StateCode.CONTOUR_BUDGET_VIOLATED)
        phase1c = {v for k, v in vars(Reason).items() if not k.startswith("_") and isinstance(v, str)}
        self.assertEqual(values & phase1c, set())

    def test_module_all(self):
        self.assertEqual(set(cassette_node.__all__), {"NodeReason", "evaluate_node", "propagate_state_veto"})
        self.assertEqual(set(cassette_closure.__all__), {"Tri", "chain_closure_feasible", "evaluate_state"})
        self.assertIn("result_identity", identity.__all__)
        self.assertIn("make_result", status.__all__)

    def test_imports_acyclic(self):
        relative, absolute = imported_modules(ROOT_DIR / "gotne" / "cassette_node.py")
        self.assertLessEqual(relative, {"cassette_schema", "cassette_state", "cassette_frames", "cassette_budget",
                                        "cassette_closure", "cassette_topology", "identity", "status"})
        self.assertLessEqual(absolute, {"__future__", "math", "typing"})
        for name in ("cassette_closure.py", "cassette_budget.py", "cassette_frames.py", "cassette_state.py",
                     "identity.py", "status.py", "cassette_schema.py", "cassette_topology.py"):
            relative, _ = imported_modules(ROOT_DIR / "gotne" / name)
            self.assertNotIn("cassette_node", relative, name)

    def test_no_phase4_or_phase5_import_at_runtime(self):  # L13 dynamic
        hits = []

        class Trap:
            def find_spec(self, name, path=None, target=None):
                if name.rsplit(".", 1)[-1] in FORBIDDEN_MODULES:
                    hits.append(name)
                return None

        trap = Trap()
        sys.meta_path.insert(0, trap)
        try:
            cfg = node_cfg()
            vetoed = evaluate(S13, cfg, separated(9.0, downstream_target="t3"))
            propagate_state_veto("D2", vetoed, cfg, cfg.policy)
            node("D3", S13, cfg, separated(2.0, downstream_target="t3"))
            evaluate(S13, node_cfg(MARGINALIZED), separated(2.0, downstream_target="t3"))
        finally:
            sys.meta_path.remove(trap)
        self.assertEqual(hits, [])
        self.assertEqual([m for m in sys.modules if m.rsplit(".", 1)[-1] in FORBIDDEN_MODULES], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
