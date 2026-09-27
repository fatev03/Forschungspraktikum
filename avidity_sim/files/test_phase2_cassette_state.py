"""Phase 2, first seam: cassette_state (decision record revision 3).

Covers the state layer only: ModuleAssignment / EngagementState, the
evaluation context, StateReason / StateCode, the identity helpers
state_identity_hash / context_identity_hash / tolerance_identity_hash, and
StateCertificate packaging. Frames, budget, closure and node code does not
exist yet and nothing here reaches for it.

evaluate_state is not implemented, so the VALID STATE results that back a
certificate are built by hand below, with upstream_state constructed
independently of cassette_state from the decision record J shape, restricted
to ENGAGED assignments (the AP-27 equivalence).

Run: python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import ast
import json
import math
import os
import pathlib
import subprocess
import sys
import unittest
import warnings
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, fields, replace
from itertools import product
from types import MappingProxyType

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from gotne import cassette_state  # noqa: E402
from gotne.cassette_schema import (  # noqa: E402
    CassetteConfig,
    CassettePolicy,
    EngagementOrderPolicy,
    TopologyMode,
    UnresolvedUpstreamPolicy,
)
from gotne.cassette_state import (  # noqa: E402
    EngagementLabel,
    EngagementState,
    EvaluationContext,
    ModuleAssignment,
    NumericalTolerances,
    StateCertificate,
    StateCode,
    StateReason,
    TargetContext,
    TargetGeometry,
    UnsupportedGeometryError,
    issue_state_certificate,
)
from gotne.cassette_topology import Code, Reason  # noqa: E402
from gotne.identity import (  # noqa: E402
    config_identity_hash,
    context_identity_hash,
    state_identity_hash,
    tolerance_identity_hash,
)
from gotne.status import (  # noqa: E402
    METHOD_VERSION,
    DiagnosticRecord,
    EvaluationResult,
    Exactness,
    Provenance,
    ProvenanceRecord,
    Severity,
    Status,
    apply_status_field_pattern,
)
from test_cassette_topology import base_policy, ref_cassette_3  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
HEX64 = frozenset("0123456789abcdef")
#: Stands in for a result_identity digest; result_identity is a later seam.
RESULT_ID = "st-" + "ab" * 32


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
def engaged(module_id, target_id):
    return ModuleAssignment(module_id, EngagementLabel.ENGAGED, target_id)


def unengaged(module_id):
    return ModuleAssignment(module_id, EngagementLabel.UNENGAGED)


def rot_z(theta):
    c, s = math.cos(theta), math.sin(theta)
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def make_context(*target_ids, orientation=None, tolerances=None):
    targets = TargetContext(
        tuple((t, TargetGeometry((float(i), 1.0, -2.5), orientation)) for i, t in enumerate(target_ids))
    )
    if tolerances is None:
        return EvaluationContext(targets)
    return EvaluationContext(targets, tolerances)


def snapshot(state, context):
    """Decision record J upstream_state, built without cassette_state. Lists
    ENGAGED assignments only (AP-27 equivalence)."""
    return MappingProxyType(
        {
            "state_hash": state_identity_hash(state),
            "context_hash": context_identity_hash(context),
            "assignments": MappingProxyType(
                {
                    a.module_id: MappingProxyType({"label": a.label.value, "target_id": a.target_id})
                    for a in state.assignments
                    if a.label is EngagementLabel.ENGAGED
                }
            ),
        }
    )


def thaw(value):
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    return value


def serialized_upstream(state, context):
    return json.dumps(thaw(cassette_state._upstream_state(state, context)), sort_keys=True)


def state_result(state, context, status=Status.VALID, **overrides):
    values, zeroed, nulled = apply_status_field_pattern(status)
    kwargs = dict(
        object_kind="STATE",
        object_id="S:" + state_identity_hash(state),
        status=status,
        status_reason=StateReason.STATE_NOT_VETOED,
        exact_or_approximate=Exactness.UNDEFINED,
        provenance=ProvenanceRecord(
            worst_label=Provenance.NOT_COMPUTED,
            contributing_labels=(Provenance.NOT_COMPUTED,),
            method_id="evaluate_state",
            method_version=METHOD_VERSION,
        ),
        values=values,
        value_intervals={},
        units={},
        zeroed_due_to_status=zeroed,
        nulled_due_to_status=nulled,
        diagnostics=(),
        upstream_state=snapshot(state, context),
        numerical_tolerance_used=MappingProxyType(context.tolerances.as_dict()),
        result_id=RESULT_ID,
    )
    kwargs.update(overrides)
    return EvaluationResult(**kwargs)


def scenario():
    """REF-CASSETTE-3 with D1 and D2 engaged on distinct targets."""
    cfg = ref_cassette_3()
    state = EngagementState((engaged("D2", "t2"), engaged("D1", "t1")))
    context = make_context("t1", "t2")
    return cfg, state, context, state_result(state, context)


# --------------------------------------------------------------------------
# State objects
# --------------------------------------------------------------------------
class StateObjects(unittest.TestCase):
    def test_labels_closed_set(self):
        self.assertEqual({m.value for m in EngagementLabel}, {"ENGAGED", "UNENGAGED"})

    def test_engaged_requires_plain_nonempty_target_id(self):
        for bad in (None, "", 7, EngagementLabel.ENGAGED):
            with self.subTest(target_id=bad), self.assertRaises(ValueError):
                ModuleAssignment("D1", EngagementLabel.ENGAGED, bad)

    def test_unengaged_forbids_target_id(self):
        with self.assertRaises(ValueError):
            ModuleAssignment("D1", EngagementLabel.UNENGAGED, "t1")
        self.assertIsNone(unengaged("D1").target_id)

    def test_module_id_must_be_plain_nonempty_str(self):
        for bad in (1, None, EngagementLabel.ENGAGED, b"D1"):
            with self.subTest(module_id=bad), self.assertRaises(TypeError):
                ModuleAssignment(bad, EngagementLabel.UNENGAGED)
        with self.assertRaises(ValueError):
            ModuleAssignment("", EngagementLabel.UNENGAGED)

    def test_label_must_be_member_not_string(self):
        with self.assertRaises(TypeError):
            ModuleAssignment("D1", "ENGAGED", "t1")

    def test_assignments_sorted_by_module_id(self):
        state = EngagementState([engaged("D3", "t3"), unengaged("D1"), engaged("D2", "t2")])
        self.assertIsInstance(state.assignments, tuple)
        self.assertEqual([a.module_id for a in state.assignments], ["D1", "D2", "D3"])
        self.assertEqual(state, EngagementState((unengaged("D1"), engaged("D2", "t2"), engaged("D3", "t3"))))

    def test_duplicate_module_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "D2"):
            EngagementState((engaged("D2", "t1"), engaged("D1", "t1"), unengaged("D2")))

    def test_container_and_element_types(self):
        for bad in ({"D1": engaged("D1", "t1")}, engaged("D1", "t1"), None):
            with self.subTest(container=type(bad).__name__), self.assertRaises(TypeError):
                EngagementState(bad)
        with self.assertRaises(TypeError):
            EngagementState((("D1", "ENGAGED", "t1"),))

    def test_omitted_module_is_unengaged(self):
        state = EngagementState((engaged("D1", "t1"), unengaged("D2")))
        self.assertIs(state.label_of("D1"), EngagementLabel.ENGAGED)
        self.assertIs(state.label_of("D2"), EngagementLabel.UNENGAGED)
        self.assertIs(state.label_of("D9"), EngagementLabel.UNENGAGED)
        self.assertEqual(state.engaged_assignments(), (engaged("D1", "t1"),))
        with self.assertRaises(TypeError):
            state.label_of(1)

    def test_shared_target_id_allowed(self):  # OQ-9, L19 at this seam
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            state = EngagementState((engaged("D1", "t1"), engaged("D3", "t1")))
        self.assertEqual([a.target_id for a in state.engaged_assignments()], ["t1", "t1"])

    def test_state_objects_frozen(self):
        state = EngagementState((engaged("D1", "t1"),))
        with self.assertRaises(FrozenInstanceError):
            state.assignments = ()
        with self.assertRaises(FrozenInstanceError):
            state.assignments[0].target_id = "t2"


# --------------------------------------------------------------------------
# Evaluation context
# --------------------------------------------------------------------------
class ContextObjects(unittest.TestCase):
    def test_context_owns_targets_and_tolerances(self):
        self.assertEqual([f.name for f in fields(EvaluationContext)], ["targets", "tolerances"])
        for schema in (CassettePolicy, CassetteConfig):
            names = {f.name for f in fields(schema)}
            self.assertFalse({n for n in names if "eps" in n or "target" in n}, schema.__name__)

    def test_tolerance_defaults(self):
        tolerances = NumericalTolerances()
        self.assertEqual(tolerances.as_dict(), {"eps_len_nm": 1e-9, "eps_rotation": 1e-9})
        self.assertEqual(EvaluationContext(TargetContext()).tolerances, tolerances)

    def test_tolerances_finite_and_positive(self):
        for field_name in ("eps_len_nm", "eps_rotation"):
            for bad in (0, 0.0, -1e-9, math.nan, math.inf, -math.inf, True, "1e-9", None, 10**400):
                with self.subTest(field=field_name, value=bad), self.assertRaises(ValueError):
                    NumericalTolerances(**{field_name: bad})
        tolerances = NumericalTolerances(eps_len_nm=1, eps_rotation=2.5e-7)
        self.assertIs(type(tolerances.eps_len_nm), float)
        self.assertEqual(tolerances.as_dict(), {"eps_len_nm": 1.0, "eps_rotation": 2.5e-7})

    def test_site_is_three_finite_reals(self):
        for bad in ((0.0, 0.0), (0.0, 0.0, 0.0, 0.0), (math.nan, 0.0, 0.0), (0.0, math.inf, 0.0),
                    (True, 0.0, 0.0), ("0", 0.0, 0.0), "abc", None, {0.0, 1.0, 2.0}):
            with self.subTest(site=bad), self.assertRaises(ValueError):
                TargetGeometry(bad)
        geometry = TargetGeometry([1, 2.5, -3])
        self.assertEqual(geometry.site_nm, (1.0, 2.5, -3.0))
        self.assertTrue(all(type(x) is float for x in geometry.site_nm))

    def test_orientation_proper_rotation_only(self):
        self.assertEqual(TargetGeometry((0.0, 0.0, 0.0), rot_z(0.7)).orientation, rot_z(0.7))
        reflection = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0))
        scaled = ((2.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        skewed = ((1.0, 1e-6, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        for bad in (reflection, scaled, skewed, ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
                    ((1.0, 0.0, math.nan), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
                    ((1e200, 1e200, 0.0), (1e200, -1e200, 0.0), (0.0, 0.0, 1.0))):
            with self.subTest(orientation=bad), self.assertRaises(ValueError):
                TargetGeometry((0.0, 0.0, 0.0), bad)
        stored = TargetGeometry((0.0, 0.0, 0.0), [[1, 0, 0], [0, 1, 0], [0, 0, 1]]).orientation
        self.assertEqual(stored, ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))
        self.assertIsInstance(stored[0], tuple)

    def test_context_rechecks_orientation_against_its_own_eps(self):
        near = ((1.0 + 1e-10, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        targets = TargetContext((("t1", TargetGeometry((0.0, 0.0, 0.0), near)),))
        EvaluationContext(targets)  # within the default 1e-9
        with self.assertRaisesRegex(ValueError, "t1"):
            EvaluationContext(targets, NumericalTolerances(eps_rotation=1e-12))

    def test_context_types(self):
        with self.assertRaises(TypeError):
            EvaluationContext()  # targets has no default
        with self.assertRaises(TypeError):
            EvaluationContext(())
        with self.assertRaises(TypeError):
            EvaluationContext(TargetContext(), {"eps_len_nm": 1e-9, "eps_rotation": 1e-9})

    def test_target_context_sorted_and_unique(self):
        g1, g2 = TargetGeometry((1.0, 0.0, 0.0)), TargetGeometry((2.0, 0.0, 0.0))
        targets = TargetContext([("t2", g2), ["t1", g1]])
        self.assertEqual(targets.targets, (("t1", g1), ("t2", g2)))
        with self.assertRaisesRegex(ValueError, "t1"):
            TargetContext((("t1", g1), ("t2", g2), ("t1", g2)))

    def test_target_context_entry_validation(self):
        geometry = TargetGeometry((0.0, 0.0, 0.0))
        for bad in ({"t1": geometry}, (("t1",),), (("t1", (0.0, 0.0, 0.0)),), ((1, geometry),)):
            with self.subTest(targets=bad), self.assertRaises(TypeError):
                TargetContext(bad)
        with self.assertRaises(ValueError):
            TargetContext((("", geometry),))

    def test_target_lookup(self):
        g1 = TargetGeometry((1.0, 0.0, 0.0))
        targets = TargetContext((("t1", g1),))
        self.assertIs(targets.lookup("t1"), g1)
        self.assertIsNone(targets.lookup("t9"))
        with self.assertRaises(TypeError):
            targets.lookup(1)
        with self.assertRaises(ValueError):
            targets.lookup("")

    def test_context_objects_frozen(self):
        context = make_context("t1", orientation=rot_z(0.1))
        with self.assertRaises(FrozenInstanceError):
            context.tolerances = NumericalTolerances()
        with self.assertRaises(FrozenInstanceError):
            context.targets.lookup("t1").site_nm = (0.0, 0.0, 0.0)


# --------------------------------------------------------------------------
# Reasons and codes
# --------------------------------------------------------------------------
def constants(cls):
    return {name: value for name, value in vars(cls).items() if not name.startswith("_") and isinstance(value, str)}


class ReasonsAndCodes(unittest.TestCase):
    FAILURES = {
        "STATE_INPUT_INVALID",
        "ENGAGEMENT_ORDER_VIOLATION",
        "JUNCTION_GEOMETRY_UNSUPPORTED",
        "GEOMETRY_INPUT_INVALID",
        "SPAN_INTERVAL_INVALID",
        "ENGAGED_POSE_UNDERDETERMINED",
        "CHAIN_CLOSURE_VIOLATED",
    }

    def test_state_reason_closed_set(self):
        reasons = constants(StateReason)
        self.assertEqual(set(reasons), self.FAILURES | {"STATE_NOT_VETOED"})
        self.assertTrue(all(name == value for name, value in reasons.items()))

    def test_state_code_closed_set(self):
        codes = constants(StateCode)
        info = {"CLOSURE_SWEEP", "UNRESOLVED_UPSTREAM", "CONTOUR_BUDGET", "SHIELDING_ANCESTOR",
                "DERIVED_RIGID_SPAN", "STATE_VETO_PROPAGATED"}
        self.assertEqual(set(codes), self.FAILURES | {"CONTOUR_BUDGET_VIOLATED"} | info)
        self.assertTrue(all(name == value for name, value in codes.items()))
        self.assertNotIn("CHECK_SKIPPED", codes)
        self.assertNotIn("STATE_NOT_VETOED", codes)

    def test_disjoint_from_phase1c_and_policy_values(self):
        phase1c = set(constants(Reason).values()) | set(constants(Code).values())
        policy_values = {m.value for m in UnresolvedUpstreamPolicy}
        phase2 = set(constants(StateReason).values()) | set(constants(StateCode).values())
        self.assertEqual(phase2 & phase1c, set())
        self.assertEqual(phase2 & policy_values, set())
        self.assertNotIn(Code.ENGAGEMENT_ORDER_CONFLICT, phase2)
        self.assertNotEqual(Reason.ORDER, StateReason.ENGAGEMENT_ORDER_VIOLATION)

    def test_no_shell_bound_or_self_avoidance_reason(self):
        for cls in (StateReason, StateCode):
            for value in constants(cls).values():
                self.assertNotIn("SHELL_BOUND", value)
                self.assertNotIn("SELF_AVOIDANCE", value)

    def test_unsupported_geometry_error_is_value_error(self):
        self.assertTrue(issubclass(UnsupportedGeometryError, ValueError))


# --------------------------------------------------------------------------
# Identity hashing
# --------------------------------------------------------------------------
class IdentityHashing(unittest.TestCase):
    def assertDigest(self, value):
        self.assertIs(type(value), str)
        self.assertEqual(len(value), 64)
        self.assertLessEqual(set(value), HEX64)

    def test_digest_form(self):
        _, state, context, _ = scenario()
        self.assertDigest(state_identity_hash(state))
        self.assertDigest(context_identity_hash(context))
        self.assertDigest(tolerance_identity_hash(context.tolerances))

    def test_state_hash_ignores_declaration_order(self):
        a = EngagementState((engaged("D1", "t1"), engaged("D2", "t2")))
        b = EngagementState((engaged("D2", "t2"), engaged("D1", "t1")))
        self.assertEqual(state_identity_hash(a), state_identity_hash(b))

    def test_unengaged_normalization(self):  # AP-27
        omitted = EngagementState((engaged("D1", "t1"),))
        explicit = EngagementState((engaged("D1", "t1"), unengaged("D2"), unengaged("D3")))
        self.assertNotEqual(omitted, explicit)
        self.assertEqual(state_identity_hash(omitted), state_identity_hash(explicit))
        self.assertEqual(state_identity_hash(EngagementState()), state_identity_hash(EngagementState((unengaged("D1"),))))

    def test_state_hash_distinguishes_engagement(self):
        hashes = {
            state_identity_hash(s)
            for s in (
                EngagementState(),
                EngagementState((engaged("D1", "t1"),)),
                EngagementState((engaged("D1", "t2"),)),
                EngagementState((engaged("D2", "t1"),)),
                EngagementState((engaged("D1", "t1"), engaged("D2", "t1"))),
                EngagementState((engaged("D1", "t1"), engaged("D2", "t2"))),
            )
        }
        self.assertEqual(len(hashes), 6)

    def test_context_hash_covers_targets_and_tolerances(self):
        base = make_context("t1", "t2")
        variants = (
            make_context("t1"),
            make_context("t1", "t3"),
            make_context("t1", "t2", orientation=rot_z(0.3)),
            make_context("t1", "t2", tolerances=NumericalTolerances(eps_len_nm=1e-6)),
            make_context("t1", "t2", tolerances=NumericalTolerances(eps_rotation=1e-6)),
            EvaluationContext(TargetContext((("t1", TargetGeometry((0.0, 1.0, -2.5))),
                                             ("t2", TargetGeometry((1.0, 1.0, -2.4)))))),
        )
        hashes = {context_identity_hash(c) for c in (base,) + variants}
        self.assertEqual(len(hashes), 1 + len(variants))
        self.assertEqual(context_identity_hash(base), context_identity_hash(make_context("t1", "t2")))

    def test_tolerance_hash(self):
        self.assertEqual(tolerance_identity_hash(NumericalTolerances()), tolerance_identity_hash(NumericalTolerances(1e-9, 1e-9)))
        self.assertNotEqual(tolerance_identity_hash(NumericalTolerances()), tolerance_identity_hash(NumericalTolerances(eps_len_nm=2e-9)))
        self.assertNotEqual(tolerance_identity_hash(NumericalTolerances()), tolerance_identity_hash(NumericalTolerances(eps_rotation=2e-9)))

    def test_domains_separated(self):
        empty_context = EvaluationContext(TargetContext())
        values = [
            state_identity_hash(EngagementState()),
            context_identity_hash(empty_context),
            tolerance_identity_hash(empty_context.tolerances),
            config_identity_hash(ref_cassette_3()),
        ]
        self.assertEqual(len(set(values)), len(values))

    def test_hashes_reject_wrong_types(self):
        _, state, context, _ = scenario()
        for function in (state_identity_hash, context_identity_hash, tolerance_identity_hash):
            for bad in (None, {}, state.assignments, context.targets):
                with self.subTest(function=function.__name__, arg=type(bad).__name__), self.assertRaises(TypeError):
                    function(bad)

    def test_hashes_stable_across_interpreter_hash_seeds(self):  # L8, identity part
        code = (
            "import sys; sys.path[:0]=[{r!r}];"
            "from gotne.cassette_state import *;"
            "from gotne.identity import state_identity_hash, context_identity_hash, tolerance_identity_hash;"
            "E=EngagementLabel;"
            "s=EngagementState((ModuleAssignment('D3',E.ENGAGED,'t1'),ModuleAssignment('D2',E.UNENGAGED),"
            "ModuleAssignment('D1',E.ENGAGED,'t1')));"
            "c=EvaluationContext(TargetContext((('t2',TargetGeometry((1.0,2.0,3.0))),"
            "('t1',TargetGeometry((0.5,0.0,-1.0),((0.0,-1.0,0.0),(1.0,0.0,0.0),(0.0,0.0,1.0)))))),"
            "NumericalTolerances(2e-9,3e-9));"
            "print(state_identity_hash(s),context_identity_hash(c),tolerance_identity_hash(c.tolerances))"
        ).format(r=str(ROOT))
        outs = set()
        for seed in ("1", "2", "977"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outs.add(
                subprocess.run(
                    [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
                ).stdout.strip()
            )
        self.assertEqual(len(outs), 1, outs)


# --------------------------------------------------------------------------
# Certificate packaging
# --------------------------------------------------------------------------
class CertificatePackaging(unittest.TestCase):
    def test_packages_exactly_five_frozen_fields(self):
        cfg, state, context, result = scenario()
        cert = issue_state_certificate(result, state, cfg, cfg.policy, context)
        self.assertEqual(
            [f.name for f in fields(StateCertificate)],
            ["state_result", "state", "context", "config_identity_hash", "context_hash"],
        )
        self.assertIs(cert.state_result, result)
        self.assertIs(cert.state, state)
        self.assertIs(cert.context, context)
        self.assertEqual(cert.config_identity_hash, config_identity_hash(cfg))
        self.assertEqual(cert.context_hash, context_identity_hash(context))
        for name, value in (("context_hash", "0" * 64), ("state", EngagementState()), ("state_result", None)):
            with self.subTest(field=name), self.assertRaises(FrozenInstanceError):
                setattr(cert, name, value)

    def test_serialized_form(self):
        cfg, state, context, result = scenario()
        cert = issue_state_certificate(result, state, cfg, cfg.policy, context)
        data = json.loads(json.dumps(cert.as_dict(), sort_keys=True, allow_nan=False))
        self.assertEqual(
            data,
            {
                "state_result_id": RESULT_ID,
                "state_hash": state_identity_hash(state),
                "context_hash": context_identity_hash(context),
                "config_identity_hash": config_identity_hash(cfg),
                "topology_mode": "LINEAR_ORDERED_CASSETTE",
                "status": "VALID",
                "exact_or_approximate": "UNDEFINED",
                "provenance": {
                    "worst_label": "NOT_COMPUTED",
                    "contributing_labels": ["NOT_COMPUTED"],
                    "method_id": "evaluate_state",
                    "method_version": METHOD_VERSION,
                    "declared_assumptions": [],
                },
                "numerical_tolerance_used": {"eps_len_nm": 1e-9, "eps_rotation": 1e-9},
            },
        )

    def test_empty_state_certifiable(self):  # N0: a zero-pair state can be VALID
        cfg = ref_cassette_3()
        state, context = EngagementState(), EvaluationContext(TargetContext())
        cert = issue_state_certificate(state_result(state, context), state, cfg, cfg.policy, context)
        self.assertEqual(dict(cert.state_result.upstream_state["assignments"]), {})

    def test_shared_target_id_certifiable(self):  # OQ-9, L19 at this seam
        cfg = ref_cassette_3()
        state = EngagementState((engaged("D1", "t1"), engaged("D3", "t1")))
        context = make_context("t1")
        cert = issue_state_certificate(state_result(state, context), state, cfg, cfg.policy, context)
        self.assertEqual(cert.state, state)

    def test_orientation_is_context_data_not_state(self):
        cfg = ref_cassette_3()
        state = EngagementState((engaged("D1", "t1"),))
        plain, oriented = make_context("t1"), make_context("t1", orientation=rot_z(0.4))
        self.assertNotEqual(context_identity_hash(plain), context_identity_hash(oriented))
        cert = issue_state_certificate(state_result(state, oriented), state, cfg, cfg.policy, oriented)
        upstream = cert.state_result.upstream_state
        self.assertEqual(upstream["state_hash"], state_identity_hash(state))
        self.assertEqual(set(upstream["assignments"]["D1"]), {"label", "target_id"})
        text = json.dumps(cert.as_dict(), sort_keys=True).lower()
        self.assertNotIn("pose", text)
        self.assertNotIn("orientation", text)
        self.assertNotIn("site", text)

    def test_entry_type_errors(self):
        cfg, state, context, result = scenario()
        good = (result, state, cfg, cfg.policy, context)
        wrong = (result.as_dict(), state.assignments, cfg.cassettes, "policy", context.targets)
        for index in range(5):
            args = list(good)
            args[index] = wrong[index]
            with self.subTest(argument=index), self.assertRaises(TypeError):
                issue_state_certificate(*args)

    def test_policy_must_equal_cfg_policy(self):  # AP-17
        cfg, state, context, result = scenario()
        issue_state_certificate(result, state, cfg, base_policy(), context)  # equal, distinct object
        for policy in (
            base_policy(engagement_order_policy=EngagementOrderPolicy.STRICT_PROXIMAL_TO_DISTAL),
            base_policy(topology_mode="LINEAR_ORDERED_CASSETTE"),  # == the member, not the same policy
        ):
            with self.subTest(policy=policy), self.assertRaisesRegex(ValueError, "AP-17"):
                issue_state_certificate(result, state, cfg, policy, context)

    def test_config_must_be_valid(self):
        _, state, context, result = scenario()
        for cfg in (
            ref_cassette_3(policy=base_policy(topology_mode=TopologyMode.GENERAL_DAG)),
            replace(ref_cassette_3(), cassettes=()),
        ):
            with self.subTest(cfg=cfg.policy.topology_mode), self.assertRaisesRegex(ValueError, "Phase 1c"):
                issue_state_certificate(result, state, cfg, cfg.policy, context)

    def test_engaged_unknown_module_rejected_with_complete_list(self):  # OQ-4 as amended (A2)
        cfg = ref_cassette_3()
        state = EngagementState((engaged("D1", "t1"), engaged("D7", "t1"), unengaged("D8"), engaged("D9", "t1")))
        context = make_context("t1")
        with self.assertRaises(ValueError) as caught:
            issue_state_certificate(state_result(state, context), state, cfg, cfg.policy, context)
        self.assertIn("['D7', 'D9']", str(caught.exception))
        self.assertNotIn("D8", str(caught.exception))

    def test_unengaged_outside_module_is_omission(self):  # amendment A2
        cfg, context = ref_cassette_3(), make_context("t1")
        omitted = EngagementState((engaged("D1", "t1"),))
        outside = EngagementState((engaged("D1", "t1"), unengaged("D8")))
        self.assertEqual(state_identity_hash(outside), state_identity_hash(omitted))
        cert = issue_state_certificate(state_result(omitted, context), outside, cfg, cfg.policy, context)
        self.assertIs(cert.state, outside)

    def test_missing_target_rejected(self):  # OQ-1
        cfg = ref_cassette_3()
        state = EngagementState((engaged("D1", "t1"), engaged("D2", "t9")))
        context = make_context("t1")
        with self.assertRaisesRegex(ValueError, "D2->t9"):
            issue_state_certificate(state_result(state, context), state, cfg, cfg.policy, context)

    def test_rejects_non_certifying_results(self):
        cfg, state, context, _ = scenario()
        veto = dict(
            status_reason=StateReason.CHAIN_CLOSURE_VIOLATED,
            exact_or_approximate=Exactness.EXACT,
            provenance=ProvenanceRecord(Provenance.EXACT_GEOMETRIC_VETO, (Provenance.EXACT_GEOMETRIC_VETO,),
                                        "evaluate_state", METHOD_VERSION),
        )
        error = DiagnosticRecord(StateCode.CHAIN_CLOSURE_VIOLATED, Severity.ERROR, "x")
        # Each result is built inside assertRaises: since AP-4/AP-5 some of them
        # (CONFIG with upstream_state, STATE without result_id, EXACT without
        # payload) can no longer be constructed at all.
        cases = {
            "object_kind CONFIG": lambda: state_result(state, context, object_kind="CONFIG"),
            "status UNREACHABLE": lambda: state_result(state, context, Status.UNREACHABLE, **veto),
            "status DEGENERATE": lambda: state_result(state, context, Status.DEGENERATE,
                                                      status_reason=StateReason.ENGAGED_POSE_UNDERDETERMINED),
            "status APPROXIMATION_REQUIRED": lambda: state_result(state, context, Status.APPROXIMATION_REQUIRED),
            "reason": lambda: state_result(state, context, status_reason=Reason.OK),
            "exactness": lambda: state_result(state, context, exact_or_approximate=Exactness.EXACT),
            "method_id": lambda: state_result(state, context, provenance=ProvenanceRecord(
                Provenance.NOT_COMPUTED, (Provenance.NOT_COMPUTED,), "validate_cassette_config", METHOD_VERSION)),
            "method_version": lambda: state_result(state, context, provenance=ProvenanceRecord(
                Provenance.NOT_COMPUTED, (Provenance.NOT_COMPUTED,), "evaluate_state", "1.0.0")),
            "payload": lambda: state_result(state, context, values=dict(apply_status_field_pattern(Status.VALID)[0],
                                                                        joint_score=1.0)),
            "error diagnostic": lambda: state_result(state, context, diagnostics=(error,)),
            "result_id None": lambda: state_result(state, context, result_id=None),
            "result_id counter": lambda: state_result(state, context, result_id="st-0007"),
            "result_id prefix": lambda: state_result(state, context, result_id="nd-" + "ab" * 32),
            "object_id": lambda: state_result(state, context, object_id="S:other"),
            "supersedes": lambda: state_result(state, context, supersedes=RESULT_ID),
        }
        for label, build in cases.items():
            with self.subTest(case=label), self.assertRaises(ValueError):
                issue_state_certificate(build(), state, cfg, cfg.policy, context)

    def test_upstream_state_must_match_state_and_context(self):
        cfg, state, context, _ = scenario()
        other_state = EngagementState((engaged("D1", "t1"),))
        other_context = make_context("t1", "t2", tolerances=NumericalTolerances(eps_len_nm=1e-6))
        good = snapshot(state, context)
        extra = MappingProxyType(dict(good, vetoing_state_result_id=RESULT_ID))
        relabelled = MappingProxyType(dict(good, assignments=MappingProxyType(
            dict(good["assignments"], D3=MappingProxyType({"label": "UNENGAGED", "target_id": None})))))
        cases = {
            "missing": None,
            "state of another state": snapshot(other_state, context),
            "context of another context": snapshot(state, other_context),
            "result metadata key": extra,
            "UNENGAGED entry listed": relabelled,
        }
        for label, upstream in cases.items():
            with self.subTest(case=label), self.assertRaises(ValueError):
                issue_state_certificate(
                    state_result(state, context, upstream_state=upstream), state, cfg, cfg.policy, context
                )
        # AP-11: the result deep-freezes a caller's mutable mapping, so it certifies
        for upstream in (thaw(good), MappingProxyType(dict(good, assignments=dict(good["assignments"])))):
            result = state_result(state, context, upstream_state=upstream)
            issue_state_certificate(result, state, cfg, cfg.policy, context)
            self.assertIsNot(result.upstream_state, upstream)

    def test_upstream_state_follows_ap27_equivalence(self):
        cfg, context = ref_cassette_3(), make_context("t1")
        omitted = EngagementState((engaged("D1", "t1"),))
        explicit = EngagementState((engaged("D1", "t1"), unengaged("D2"), unengaged("D3")))
        self.assertEqual(serialized_upstream(omitted, context), serialized_upstream(explicit, context))
        self.assertEqual(set(cassette_state._upstream_state(explicit, context)["assignments"]), {"D1"})
        for built_for, certified in ((omitted, explicit), (explicit, omitted)):
            cert = issue_state_certificate(state_result(built_for, context), certified, cfg, cfg.policy, context)
            self.assertEqual(thaw(cert.state_result.upstream_state), thaw(snapshot(omitted, context)))
        good = snapshot(explicit, context)
        legacy = MappingProxyType(dict(good, assignments=MappingProxyType(dict(
            good["assignments"],
            D2=MappingProxyType({"label": "UNENGAGED", "target_id": None}),
            D3=MappingProxyType({"label": "UNENGAGED", "target_id": None}),
        ))))
        with self.assertRaisesRegex(ValueError, "frozen snapshot"):
            issue_state_certificate(
                state_result(explicit, context, upstream_state=legacy), explicit, cfg, cfg.policy, context
            )

    def test_equal_state_hash_iff_equal_serialized_upstream_state(self):
        context = make_context("t1", "t2")
        states = (
            EngagementState(),
            EngagementState((unengaged("D1"),)),
            EngagementState((unengaged("D1"), unengaged("D2"), unengaged("D3"))),
            EngagementState((engaged("D1", "t1"),)),
            EngagementState((engaged("D1", "t1"), unengaged("D2"))),
            EngagementState((engaged("D1", "t2"),)),
            EngagementState((engaged("D1", "t1"), engaged("D2", "t1"))),
            EngagementState((engaged("D1", "t1"), engaged("D2", "t1"), unengaged("D3"))),
            EngagementState((engaged("D2", "t1"), unengaged("D1"))),
        )
        for a, b in product(states, repeat=2):
            with self.subTest(a=a, b=b):
                self.assertEqual(
                    state_identity_hash(a) == state_identity_hash(b),
                    serialized_upstream(a, context) == serialized_upstream(b, context),
                )

    def test_tolerances_used_must_be_frozen_context_tolerances(self):
        cfg, state, context, _ = scenario()
        for label, used in {
            "missing": None,
            "other value": MappingProxyType({"eps_len_nm": 1e-6, "eps_rotation": 1e-9}),
            "int leaf": MappingProxyType({"eps_len_nm": 1, "eps_rotation": 1e-9}),
        }.items():
            with self.subTest(case=label), self.assertRaises(ValueError):
                issue_state_certificate(
                    state_result(state, context, numerical_tolerance_used=used), state, cfg, cfg.policy, context
                )
        # AP-11: a plain dict is frozen by the result, so it certifies
        issue_state_certificate(
            state_result(state, context, numerical_tolerance_used=context.tolerances.as_dict()),
            state, cfg, cfg.policy, context,
        )

    def test_direct_construction_enforces_consistency(self):
        cfg, state, context, result = scenario()
        good = dict(state_result=result, state=state, context=context,
                    config_identity_hash=config_identity_hash(cfg), context_hash=context_identity_hash(context))
        StateCertificate(**good)
        for name, value, error in (
            ("context_hash", "0" * 64, ValueError),
            ("context_hash", "XYZ", ValueError),
            ("config_identity_hash", "g" * 64, ValueError),
            ("config_identity_hash", None, TypeError),
            ("context", make_context("t1", "t2", orientation=rot_z(0.2)), ValueError),
            ("state", EngagementState((engaged("D1", "t1"),)), ValueError),
            ("state_result", result.as_dict(), TypeError),
        ):
            with self.subTest(field=name, value=value), self.assertRaises(error):
                StateCertificate(**dict(good, **{name: value}))


# --------------------------------------------------------------------------
# Import boundary for this seam. The package-level export allowlist lives in
# test_cassette_topology.PurityTests (AP-1 / AP-2).
# --------------------------------------------------------------------------
def imported_modules(path):
    relative, absolute = set(), set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level:
            relative.update([node.module.split(".")[0]] if node.module else [a.name for a in node.names])
        elif isinstance(node, ast.ImportFrom):
            absolute.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            absolute.update(a.name.split(".")[0] for a in node.names)
    return relative, absolute


class SeamBoundary(unittest.TestCase):
    def test_cassette_state_imports_only_permitted_modules(self):
        relative, absolute = imported_modules(ROOT / "gotne" / "cassette_state.py")
        self.assertLessEqual(relative, {"cassette_schema", "cassette_topology", "identity", "status"})
        self.assertLessEqual(absolute, {"__future__", "collections", "dataclasses", "enum", "math", "re", "types", "typing"})

    def test_identity_reaches_only_cassette_state_in_phase2(self):
        relative, absolute = imported_modules(ROOT / "gotne" / "identity.py")
        self.assertEqual(relative, {"cassette_schema", "cassette_state"})
        self.assertNotIn("math", absolute)


if __name__ == "__main__":
    unittest.main(verbosity=2)
