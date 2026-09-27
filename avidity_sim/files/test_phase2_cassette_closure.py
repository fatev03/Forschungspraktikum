"""Phase 2, fourth seam: cassette_closure (decision record revision 3).

Covers Tri, closure-pair selection and chain_closure_feasible only: N8 pair
selection, the AP-22 placement of exit_world / entry_world, the OQ-3 closure
gate with both bounds and eps_len_nm, ORIENTATION_MARGINALIZED as UNDETERMINED,
FIXED_RIGID refusal (OQ-7) and fail-closed inputs (OQ-1, OQ-5). evaluate_state
and the node layer do not exist yet.

Fixture geometry is binary-exact, so separations and bounds compare with ==.
With identity orientations and the budget fixture offsets (entry 0, exit 1.25,
capture 0.5 along x), exit_world(D_i) = p_i + (0.75, 0, 0) and
entry_world(D_j) = p_j - (0.5, 0, 0).

Run: python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from gotne import cassette_closure  # noqa: E402
from gotne.cassette_budget import cassette_contour_budget, closure_span_budget  # noqa: E402
from gotne.cassette_closure import Tri, chain_closure_feasible  # noqa: E402
from gotne.cassette_frames import cassette_effective_anchor  # noqa: E402
from gotne.cassette_schema import (  # noqa: E402
    MISSING,
    AnchorSpec,
    CassetteConfig,
    CassetteSpec,
    EngagedPoseResolution,
    EngagementOrderPolicy,
    JunctionModel,
    TetherSpec,
    TopologyMode,
)
from gotne.cassette_state import (  # noqa: E402
    EvaluationContext,
    NumericalTolerances,
    TargetContext,
    TargetGeometry,
    UnsupportedGeometryError,
)
from gotne.cassette_topology import validate_cassette_config  # noqa: E402
from gotne.status import Status  # noqa: E402
from test_cassette_topology import base_policy, module  # noqa: E402
from test_phase2_cassette_budget import ORDER, S13, S123, all_states, budget_cfg, state  # noqa: E402
from test_phase2_cassette_frames import IDENTITY, R90  # noqa: E402
from test_phase2_cassette_state import engaged, imported_modules, rot_z, unengaged  # noqa: E402

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
S12 = state(engaged("D1", "t1"), engaged("D2", "t2"))
EPS = 2.0 ** -10
TINY = 2.0 ** -20
MARGINALIZED = base_policy(engaged_pose_resolution=EngagedPoseResolution.ORIENTATION_MARGINALIZED)
FIXED_RIGID = base_policy(junction_model=JunctionModel.FIXED_RIGID)
_DEFAULT = object()


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
def make_context(sites, orientations=None, tolerances=None):
    """sites: target_id -> site; orientation IDENTITY unless given (None allowed)."""
    orientations = orientations or {}
    targets = TargetContext(
        tuple((t, TargetGeometry(site, orientations.get(t, IDENTITY))) for t, site in sites.items())
    )
    return EvaluationContext(targets) if tolerances is None else EvaluationContext(targets, tolerances)


def separated(d, downstream_target="t2", tolerances=None, orientations=None, **more_sites):
    """Identity placement with entry_world(D_j) - exit_world(D_i) = (d, 0, 0)."""
    sites = {"t1": (0.0, 0.0, 0.0), downstream_target: (1.25 + d, 0.0, 0.0), **more_sites}
    return make_context(sites, orientations, tolerances)


def feasible(up, down, st, cfg, context):
    return chain_closure_feasible(up, down, st, cfg, cfg.policy, context)


def long_cfg():
    """a0 -> D1 -> ... -> D5, budget fixture offsets, every tether [0.5, 1.5]."""
    ids = ("D1", "D2", "D3", "D4", "D5")
    offsets = dict(entry_offset=(0.0, 0.0, 0.0), exit_offset=(1.25, 0.0, 0.0), capture_offset_vec=(0.5, 0.0, 0.0))
    modules = tuple(module(m, i + 1, **offsets) for i, m in enumerate(ids[:-1])) + (
        module("D5", 5, terminal=True, entry_offset=(0.0, 0.0, 0.0), capture_offset_vec=(0.5, 0.0, 0.0)),
    )
    tethers = tuple(
        TetherSpec(id=f"s{i}", from_node="a0" if i == 0 else ids[i - 1], to_node=ids[i], cassette_index=i,
                   L_min=0.5, L=1.5)
        for i in range(5)
    )
    return CassetteConfig(
        id="LONG-5",
        policy=base_policy(),
        cassettes=(CassetteSpec(id="cas1", root_anchor_id="a0", ordered_modules=ids,
                                ordered_segments=tuple(f"s{i}" for i in range(5))),),
        anchors=(AnchorSpec(id="a0", surface_id="S0"),),
        modules=modules,
        tethers=tethers,
    )


class FixtureSanity(unittest.TestCase):
    def test_fixtures_valid_under_phase1c(self):
        for cfg in (budget_cfg(), budget_cfg(MARGINALIZED), budget_cfg(FIXED_RIGID), long_cfg(),
                    budget_cfg(modules={"D2": {"entry_offset": MISSING}, "D1": {"exit_offset": (1.0, 0.0)}})):
            self.assertIs(validate_cassette_config(cfg).status, Status.VALID)

    def test_separation_fixture_is_exact(self):
        for d in (1.0, 1.5 + EPS, 0.5 - EPS - TINY):
            self.assertEqual(cassette_closure._pair_separation("D1", "D2", S12, budget_cfg(), separated(d))[0], d)


# --------------------------------------------------------------------------
# Tri
# --------------------------------------------------------------------------
class TriType(unittest.TestCase):
    def test_members_and_no_truth_value(self):
        self.assertEqual([m.value for m in Tri], ["TRUE", "FALSE", "UNDETERMINED"])
        for member in Tri:
            with self.subTest(member=member.value):
                with self.assertRaises(TypeError):
                    bool(member)
                with self.assertRaises(TypeError):
                    if member:
                        pass
                with self.assertRaises(TypeError):
                    not member  # noqa: B015
        self.assertEqual(json.dumps(Tri.FALSE), '"FALSE"')


# --------------------------------------------------------------------------
# Pair selection (N8)
# --------------------------------------------------------------------------
EXPECTED_PAIRS = {
    frozenset(): (),
    frozenset({"D1"}): (),
    frozenset({"D2"}): (),
    frozenset({"D3"}): (),
    frozenset({"D1", "D2"}): (("D1", "D2"),),
    frozenset({"D1", "D3"}): (("D1", "D3"),),
    frozenset({"D2", "D3"}): (("D2", "D3"),),
    frozenset({"D1", "D2", "D3"}): (("D1", "D2"), ("D2", "D3")),
}
ALL_TARGETS = {"t1": (0.0, 0.0, 0.0), "t2": (2.0, 0.0, 0.0), "t3": (4.0, 0.0, 0.0)}


class PairSelection(unittest.TestCase):
    def test_every_engagement_subset(self):
        for st in all_states():  # each subset twice: omitted and explicit UNENGAGED
            chosen = frozenset(a.module_id for a in st.engaged_assignments())
            with self.subTest(state=[(a.module_id, a.label.value) for a in st.assignments]):
                pairs = cassette_closure._closure_pairs(st, ORDER)
                self.assertEqual(pairs, EXPECTED_PAIRS[chosen])
                self.assertIsInstance(pairs, tuple)
                self.assertTrue(all(type(p) is tuple and len(p) == 2 for p in pairs))

    def test_order_and_determinism_in_a_longer_cassette(self):
        ids = ("D1", "D2", "D3", "D4", "D5")
        cases = (
            (state(engaged("D1", "t1"), unengaged("D2"), engaged("D3", "t3"), engaged("D4", "t4")),
             (("D1", "D3"), ("D3", "D4"))),
            (state(engaged("D4", "t4"), engaged("D3", "t3"), engaged("D1", "t1")), (("D1", "D3"), ("D3", "D4"))),
            (state(*(engaged(m, "t") for m in reversed(ids))), (("D1", "D2"), ("D2", "D3"), ("D3", "D4"), ("D4", "D5"))),
            (state(engaged("D2", "t"), engaged("D5", "t")), (("D2", "D5"),)),
        )
        for st, expected in cases:
            self.assertEqual(cassette_closure._closure_pairs(st, ids), expected)
            self.assertEqual(cassette_closure._closure_pairs(st, ids), cassette_closure._closure_pairs(st, ids))

    def test_predicate_and_budget_accept_exactly_the_selected_pairs(self):  # N2
        cfg, context = budget_cfg(), make_context(ALL_TARGETS)
        for st in all_states():
            pairs = cassette_closure._closure_pairs(st, ORDER)
            for up in ORDER:
                for down in ORDER:
                    with self.subTest(state=[(a.module_id, a.label.value) for a in st.assignments], pair=(up, down)):
                        if (up, down) in pairs:
                            closure_span_budget(up, down, st, cfg)
                            self.assertIn(feasible(up, down, st, cfg, context), (Tri.TRUE, Tri.FALSE))
                        else:
                            with self.assertRaisesRegex(ValueError, "consecutive ENGAGED pair"):
                                closure_span_budget(up, down, st, cfg)
                            with self.assertRaisesRegex(ValueError, r"not a closure pair.*never repaired"):
                                feasible(up, down, st, cfg, context)


# --------------------------------------------------------------------------
# Placement (AP-22)
# --------------------------------------------------------------------------
class Placement(unittest.TestCase):
    P1, P2 = (1.0, 2.0, 3.0), (10.0, 0.0, 0.0)

    def points(self, cfg=None, **orientations):
        context = make_context({"t1": self.P1, "t2": self.P2}, orientations)
        return cassette_closure._world_points("D1", "D2", S12, cfg or budget_cfg(), context)

    def test_identity_placement(self):
        self.assertEqual(self.points(), ((1.75, 2.0, 3.0), (9.5, 0.0, 0.0)))

    def test_rotated_placement_translates_by_rotated_capture(self):
        self.assertEqual(self.points(t1=R90, t2=R90), ((1.0, 2.75, 3.0), (10.0, -0.5, 0.0)))
        self.assertEqual(self.points(t1=R90), ((1.0, 2.75, 3.0), (9.5, 0.0, 0.0)))
        # entry offset and capture offset read separately: R.entry + p - R.capture
        cfg = budget_cfg(modules={"D2": {"entry_offset": (0.25, 0.0, 0.0), "capture_offset_vec": (1.0, 0.0, 0.0)}})
        self.assertEqual(self.points(cfg, t2=R90)[1], (10.0, -0.75, 0.0))

    def test_general_rotation_follows_the_convention(self):
        rotation = rot_z(0.3)
        exit_world, _ = self.points(t1=rotation)
        exit_offset, capture = (1.25, 0.0, 0.0), (0.5, 0.0, 0.0)
        expected = tuple(self.P1[i] + sum(rotation[i][k] * exit_offset[k] for k in range(3))
                         - sum(rotation[i][k] * capture[k] for k in range(3)) for i in range(3))
        for got, want in zip(exit_world, expected):
            self.assertAlmostEqual(got, want, places=12)

    def test_exit_world_is_the_effective_anchor_of_the_next_module(self):
        cfg = budget_cfg()
        context = make_context({"t1": self.P1, "t2": self.P2}, {"t1": rot_z(1.1)})
        exit_world, _ = cassette_closure._world_points("D1", "D2", S12, cfg, context)
        self.assertEqual(exit_world, cassette_effective_anchor("D2", S12, cfg, context).point)

    def test_verdict_uses_the_orientations(self):
        cfg = budget_cfg()
        # with R90 on both: exit_world = (0, 0.75, 0), entry_world = (0, 1.75, 0), d = 1.0
        sites = {"t1": (0.0, 0.0, 0.0), "t2": (0.0, 2.25, 0.0)}
        self.assertIs(feasible("D1", "D2", S12, cfg, make_context(sites, {"t1": R90, "t2": R90})), Tri.TRUE)
        self.assertIs(feasible("D1", "D2", S12, cfg, make_context(sites)), Tri.FALSE)


# --------------------------------------------------------------------------
# Closure gate (OQ-3): D_min - eps <= d <= D_max + eps over closure_span_budget
# --------------------------------------------------------------------------
class Gate(unittest.TestCase):
    def test_boundaries_with_eps(self):  # pair (D1, D2): [D_min, D_max] = [0.5, 1.5]
        cfg, loose = budget_cfg(), NumericalTolerances(eps_len_nm=EPS)
        cases = ((1.0, Tri.TRUE), (1.5 + EPS, Tri.TRUE), (1.5 + EPS + TINY, Tri.FALSE),
                 (0.5 - EPS, Tri.TRUE), (0.5 - EPS - TINY, Tri.FALSE))
        for d, expected in cases:
            with self.subTest(d=d):
                self.assertIs(feasible("D1", "D2", S12, cfg, separated(d, tolerances=loose)), expected)

    def test_default_eps_boundaries(self):
        cfg = budget_cfg()
        for d, expected in ((1.5, Tri.TRUE), (1.5 + TINY, Tri.FALSE), (0.5, Tri.TRUE), (0.5 - TINY, Tri.FALSE)):
            with self.subTest(d=d):
                self.assertIs(feasible("D1", "D2", S12, cfg, separated(d)), expected)

    def test_eps_len_from_context_only(self):
        cfg, d = budget_cfg(), 1.5 + EPS
        self.assertIs(feasible("D1", "D2", S12, cfg, separated(d)), Tri.FALSE)
        self.assertIs(feasible("D1", "D2", S12, cfg, separated(d, tolerances=NumericalTolerances(eps_len_nm=EPS))), Tri.TRUE)
        self.assertIs(feasible("D1", "D2", S12, cfg, separated(d, tolerances=NumericalTolerances(eps_rotation=EPS))),
                      Tri.FALSE)

    def test_clearly_infeasible_both_sides(self):
        self.assertIs(feasible("D1", "D2", S12, budget_cfg(), separated(10.0)), Tri.FALSE)
        cfg = budget_cfg(modules={"D2": {"exit_offset": (5.0, 0.0, 0.0)}})  # (D1, D3): [2.5, 7.5]
        for d, expected in ((1.0, Tri.FALSE), (2.5, Tri.TRUE), (3.0, Tri.TRUE), (7.5, Tri.TRUE), (8.0, Tri.FALSE)):
            with self.subTest(d=d):
                self.assertIs(feasible("D1", "D3", S13, cfg, separated(d, downstream_target="t3")), expected)

    def test_closure_span_budget_used_and_capture_excluded(self):
        cfg, context = budget_cfg(), separated(1.75)
        # a node budget of D2 from D1 would allow 2.0 (capture included); the closure span allows 1.5
        self.assertEqual(cassette_contour_budget("D2", S12, cfg).D_max_nm, 2.0)
        with mock.patch("gotne.cassette_budget.closure_span_budget", wraps=closure_span_budget) as spy, \
                mock.patch("gotne.cassette_budget.cassette_contour_budget", side_effect=AssertionError("node budget")), \
                mock.patch("gotne.cassette_frames.cassette_effective_anchor", side_effect=AssertionError("anchor")):
            self.assertIs(feasible("D1", "D2", S12, cfg, context), Tri.FALSE)
        spy.assert_called_once_with("D1", "D2", S12, cfg)

    def test_multiple_pairs_in_a_longer_cassette(self):
        cfg = long_cfg()
        st = state(engaged("D1", "t1"), unengaged("D2"), engaged("D3", "t3"), engaged("D4", "t4"))
        context = make_context({"t1": (0.0, 0.0, 0.0), "t3": (4.0, 0.0, 0.0), "t4": (7.5, 0.0, 0.0)})
        self.assertEqual(cassette_closure._closure_pairs(st, cfg.cassettes[0].ordered_modules), (("D1", "D3"), ("D3", "D4")))
        self.assertIs(feasible("D1", "D3", st, cfg, context), Tri.TRUE)  # d = 2.75 in [0, 4.25]
        self.assertIs(feasible("D3", "D4", st, cfg, context), Tri.FALSE)  # d = 2.25 > 1.5
        for up, down in (("D1", "D4"), ("D1", "D2"), ("D2", "D3"), ("D4", "D5"), ("D4", "D3")):
            with self.subTest(pair=(up, down)), self.assertRaisesRegex(ValueError, "not a closure pair"):
                feasible(up, down, st, cfg, context)


# --------------------------------------------------------------------------
# Inputs (OQ-1, OQ-5)
# --------------------------------------------------------------------------
class Inputs(unittest.TestCase):
    def test_missing_target(self):
        with self.assertRaisesRegex(ValueError, r"^GEOMETRY_INPUT_INVALID: D2\.target_id=TARGET_NOT_IN_CONTEXT"):
            feasible("D1", "D2", S12, budget_cfg(), make_context({"t1": (0.0, 0.0, 0.0)}))
        with self.assertRaisesRegex(ValueError, r"D3\.target_id=TARGET_NOT_IN_CONTEXT"):  # outside the pair too
            feasible("D1", "D2", S123, budget_cfg(), separated(1.0))

    def test_orientation_required(self):
        for target in ("t1", "t2"):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, rf"{target}\.orientation=ORIENTATION_REQUIRED"):
                feasible("D1", "D2", S12, budget_cfg(), separated(1.0, orientations={target: None}))

    def test_endpoint_offset_defects(self):
        cases = (
            ({"D1": {"exit_offset": (1.0, 0.0)}}, r"D1\.exit_offset=MALFORMED"),
            ({"D1": {"exit_offset": (math.inf, 0.0, 0.0)}}, r"D1\.exit_offset=NON_FINITE"),
            ({"D1": {"capture_offset_vec": None}}, r"D1\.capture_offset_vec=NULL"),
            ({"D2": {"entry_offset": MISSING}}, r"D2\.entry_offset=MISSING"),
            ({"D2": {"entry_offset": (True, 0.0, 0.0)}}, r"D2\.entry_offset=MALFORMED"),
            ({"D2": {"capture_offset_vec": (math.nan, 0.0, 0.0)}}, r"D2\.capture_offset_vec=NON_FINITE"),
        )
        for modules, pattern in cases:
            with self.subTest(modules=modules), self.assertRaisesRegex(ValueError, "^GEOMETRY_INPUT_INVALID: .*" + pattern):
                feasible("D1", "D2", S12, budget_cfg(modules=modules), separated(1.0))

    def test_only_inputs_of_this_gate_read(self):
        # D1.entry_offset, D2.exit_offset and the root position are not on the (D1, D2) gate
        cfg = budget_cfg(modules={"D1": {"entry_offset": None}, "D2": {"exit_offset": (1.0, 0.0)}})
        self.assertIs(feasible("D1", "D2", S12, cfg, separated(1.0)), Tri.TRUE)
        self.assertIsInstance(cfg.anchors[0].position, type(MISSING))

    def test_defects_aggregated_across_endpoints_and_path(self):
        cfg = budget_cfg(modules={"D2": {"entry_offset": MISSING}}, tethers={"s1": {"L": MISSING}})
        with self.assertRaises(ValueError) as caught:
            feasible("D1", "D2", S12, cfg, separated(1.0, orientations={"t1": None}))
        self.assertEqual(str(caught.exception), "GEOMETRY_INPUT_INVALID: t1.orientation=ORIENTATION_REQUIRED, "
                                                "D2.entry_offset=MISSING, s1.L=MISSING")

    def test_span_interval_after_geometry(self):
        interval = budget_cfg(tethers={"s1": {"L_min": 2.0}})
        with self.assertRaisesRegex(ValueError, r"^SPAN_INTERVAL_INVALID: s1\.L_min=L_MIN_EXCEEDS_L$"):
            feasible("D1", "D2", S12, interval, separated(1.0))
        both = budget_cfg(tethers={"s1": {"L_min": 2.0}}, modules={"D2": {"entry_offset": MISSING}})
        with self.assertRaisesRegex(ValueError, r"^GEOMETRY_INPUT_INVALID: D2\.entry_offset=MISSING$"):
            feasible("D1", "D2", S12, both, separated(1.0))

    def test_non_finite_separation(self):
        context = make_context({"t1": (-1.7e308, 0.0, 0.0), "t2": (1.7e308, 0.0, 0.0)})
        with self.assertRaisesRegex(ValueError, r"D1->D2\.separation=NON_FINITE"):
            feasible("D1", "D2", S12, budget_cfg(), context)

    def test_positions_and_tolerances_cannot_be_invalid_in_a_context(self):
        for site in ((math.nan, 0.0, 0.0), (0.0, math.inf, 0.0), (0.0, 0.0)):
            with self.subTest(site=site), self.assertRaises(ValueError):
                TargetGeometry(site)
        for eps in (0.0, -1e-9, math.nan, math.inf):
            with self.subTest(eps=eps), self.assertRaises(ValueError):
                NumericalTolerances(eps_len_nm=eps)
        with self.assertRaises(TypeError):
            feasible("D1", "D2", S12, budget_cfg(), {"eps_len_nm": 1e-9})


# --------------------------------------------------------------------------
# Non-evaluable outcomes
# --------------------------------------------------------------------------
class OrientationMarginalized(unittest.TestCase):
    def test_undetermined_whatever_orientation_is_supplied(self):
        cfg = budget_cfg(MARGINALIZED)
        for orientation in (R90, IDENTITY, rot_z(1.1), None):
            for d in (1.0, 100.0):
                context = separated(d, orientations={"t1": orientation, "t2": orientation})
                with self.subTest(orientation=orientation, d=d):
                    self.assertIs(feasible("D1", "D2", S12, cfg, context), Tri.UNDETERMINED)

    def test_endpoint_offsets_not_required(self):
        cfg = budget_cfg(MARGINALIZED, modules={"D1": {"exit_offset": (1.0, 0.0)}, "D2": {"capture_offset_vec": None}})
        self.assertIs(feasible("D1", "D2", S12, cfg, separated(1.0)), Tri.UNDETERMINED)

    def test_targets_path_and_pair_still_checked(self):
        cfg = budget_cfg(MARGINALIZED)
        with self.assertRaisesRegex(ValueError, "TARGET_NOT_IN_CONTEXT"):
            feasible("D1", "D2", S12, cfg, make_context({"t1": (0.0, 0.0, 0.0)}))
        with self.assertRaisesRegex(ValueError, r"^GEOMETRY_INPUT_INVALID: s1\.L=MISSING"):
            feasible("D1", "D2", S12, budget_cfg(MARGINALIZED, tethers={"s1": {"L": MISSING}}), separated(1.0))
        with self.assertRaisesRegex(ValueError, "not a closure pair"):
            feasible("D1", "D3", S123, cfg, separated(1.0, t3=(9.0, 0.0, 0.0)))


class FixedRigid(unittest.TestCase):  # OQ-7, AP-25
    def test_unsupported_geometry_raised(self):
        for policy in (FIXED_RIGID, base_policy(junction_model=JunctionModel.FIXED_RIGID,
                                                engaged_pose_resolution=EngagedPoseResolution.ORIENTATION_MARGINALIZED)):
            cfg = budget_cfg(policy)
            for context in (separated(1.0), make_context({"t1": (0.0, 0.0, 0.0)})):  # before geometry input checks
                with self.subTest(policy=policy.engaged_pose_resolution), \
                        self.assertRaisesRegex(UnsupportedGeometryError, "^JUNCTION_GEOMETRY_UNSUPPORTED: FIXED_RIGID"):
                    feasible("D1", "D2", S12, cfg, context)

    def test_argument_errors_precede_the_junction_check(self):
        with self.assertRaises(ValueError) as caught:
            feasible("D2", "D1", S12, budget_cfg(FIXED_RIGID), separated(1.0))
        self.assertNotIsInstance(caught.exception, UnsupportedGeometryError)


# --------------------------------------------------------------------------
# Entry checks and determinism
# --------------------------------------------------------------------------
class EntryChecks(unittest.TestCase):
    def test_types(self):
        cfg, context = budget_cfg(), separated(1.0)
        good = ["D1", "D2", S12, cfg, cfg.policy, context]
        wrong = [1, None, S12.assignments, cfg.cassettes, "policy", context.targets]
        for index in range(6):
            args = list(good)
            args[index] = wrong[index]
            with self.subTest(argument=index), self.assertRaises(TypeError):
                chain_closure_feasible(*args)
        with self.assertRaises(TypeError):
            chain_closure_feasible("D1", "D2", S12, cfg, cfg.policy)  # context has no default

    def test_policy_must_equal_cfg_policy(self):  # AP-17
        cfg, context = budget_cfg(), separated(1.0)
        self.assertIs(chain_closure_feasible("D1", "D2", S12, cfg, base_policy(), context), Tri.TRUE)
        for policy in (base_policy(engagement_order_policy=EngagementOrderPolicy.STRICT_PROXIMAL_TO_DISTAL),
                       base_policy(topology_mode="LINEAR_ORDERED_CASSETTE")):
            with self.subTest(policy=policy), self.assertRaisesRegex(ValueError, "AP-17"):
                chain_closure_feasible("D1", "D2", S12, cfg, policy, context)

    def test_config_and_state_must_fit(self):
        dag = budget_cfg(base_policy(topology_mode=TopologyMode.GENERAL_DAG))
        with self.assertRaisesRegex(ValueError, "Phase 1c"):
            feasible("D1", "D2", S12, dag, separated(1.0))
        with self.assertRaisesRegex(ValueError, "^STATE_INPUT_INVALID.*D7"):
            feasible("D1", "D2", state(engaged("D1", "t1"), engaged("D2", "t2"), engaged("D7", "t7")), budget_cfg(),
                     separated(1.0))
        # amendment A2: an UNENGAGED module outside the cassette is omission
        self.assertIs(feasible("D1", "D2", state(engaged("D1", "t1"), engaged("D2", "t2"), unengaged("D7")),
                               budget_cfg(), separated(1.0)), Tri.TRUE)
        with self.assertRaisesRegex(ValueError, "not in the cassette"):
            feasible("D1", "D9", S12, budget_cfg(), separated(1.0))


class Determinism(unittest.TestCase):
    def test_repeatable_and_declaration_order_free(self):
        cfg = budget_cfg()
        permuted = state(engaged("D2", "t2"), unengaged("D3"), engaged("D1", "t1"))
        for d in (1.0, 10.0, 0.25):
            context = separated(d)
            outcomes = {feasible("D1", "D2", st, cfg, context) for st in (S12, S12, permuted)}
            self.assertEqual(len(outcomes), 1, d)


# --------------------------------------------------------------------------
# Module surface and import boundary for this seam. The package-level export
# allowlist lives in test_cassette_topology.PurityTests (AP-1 / AP-2).
# --------------------------------------------------------------------------
class SeamBoundary(unittest.TestCase):
    def test_module_all(self):
        self.assertEqual(set(cassette_closure.__all__), {"Tri", "chain_closure_feasible", "evaluate_state"})

    def test_cassette_closure_imports_only_permitted_modules(self):
        relative, absolute = imported_modules(ROOT_DIR / "gotne" / "cassette_closure.py")
        self.assertLessEqual(relative, {"cassette_schema", "cassette_state", "cassette_frames", "cassette_budget",
                                        "cassette_topology", "identity", "status"})
        self.assertLessEqual(absolute, {"__future__", "enum", "math", "typing"})

    def test_earlier_modules_do_not_import_closure(self):
        for name in ("cassette_budget.py", "cassette_frames.py", "cassette_state.py", "identity.py", "status.py",
                     "cassette_schema.py", "cassette_topology.py"):
            relative, _ = imported_modules(ROOT_DIR / "gotne" / name)
            self.assertNotIn("cassette_closure", relative, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
