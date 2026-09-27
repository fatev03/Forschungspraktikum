"""Phase 2, second seam: cassette_frames (decision record revision 3).

Covers ROOT, EffectiveAnchor and cassette_effective_anchor only: shielding
ancestor selection (AP-18), the AP-22 placement convention and its declared
assumption, ORIENTATION_MARGINALIZED as an undetermined point, and fail-closed
input handling (OQ-1, OQ-4, OQ-5). Budget, closure and node code does not
exist yet and nothing here reaches for it.

Run: python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import copy
import math
import pathlib
import pickle
import sys
import unittest
from dataclasses import replace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from gotne import cassette_frames  # noqa: E402
from gotne.cassette_frames import (  # noqa: E402
    POSE_PLACEMENT_ASSUMPTION,
    ROOT,
    EffectiveAnchor,
    Root,
    cassette_effective_anchor,
)
from gotne.cassette_schema import (  # noqa: E402
    MISSING,
    AnchorSpec,
    EngagedPoseResolution,
    JunctionModel,
    TopologyMode,
)
from gotne.cassette_state import (  # noqa: E402
    EngagementState,
    EvaluationContext,
    TargetContext,
    TargetGeometry,
)
from gotne.cassette_topology import validate_cassette_config  # noqa: E402
from gotne.status import Status  # noqa: E402
from test_cassette_topology import base_policy, module, ref_cassette_3  # noqa: E402
from test_phase2_cassette_state import (  # noqa: E402
    engaged,
    imported_modules,
    rot_z,
    unengaged,
)

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
ROOT_POSITION = (1.0, 2.0, 3.0)
#: Rotation by +90 degrees about z, exact in binary floating point.
R90 = ((0.0, -1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
IDENTITY = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
SITES = {"t1": (10.0, 20.0, 30.0), "t2": (-4.0, 8.0, 2.5), "t3": (0.0, 0.0, 100.0)}
MARGINALIZED = EngagedPoseResolution.ORIENTATION_MARGINALIZED


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
def frames_cfg(policy=None, position=ROOT_POSITION, **d1_overrides):
    """REF-CASSETTE-3 with a root position and binary-exact offsets:
    exit (1.25, 0, 0), capture (0.5, 0, 0)."""
    cfg = ref_cassette_3(policy=policy)
    offsets = dict(exit_offset=(1.25, 0.0, 0.0), capture_offset_vec=(0.5, 0.0, 0.0))
    return replace(
        cfg,
        anchors=(AnchorSpec(id="a0", surface_id="S0", position=position),),
        modules=(
            module("D1", 1, **dict(offsets, **d1_overrides)),
            module("D2", 2, **offsets),
            module("D3", 3, terminal=True, capture_offset_vec=(0.5, 0.0, 0.0), exclusion_centre=(0.5, 0.0, 0.0)),
        ),
    )


def make_context(orientation=R90, **orientations):
    """Targets t1..t3 at SITES; orientation per target overridable by name."""
    return EvaluationContext(
        TargetContext(
            tuple((t, TargetGeometry(site, orientations.get(t, orientation))) for t, site in SITES.items())
        )
    )


def state(*assignments):
    return EngagementState(assignments)


def anchor(module_id, st, cfg=None, context=None):
    return cassette_effective_anchor(module_id, st, cfg or frames_cfg(), context or make_context())


class FixtureSanity(unittest.TestCase):
    def test_fixture_configs_valid_under_phase1c(self):
        for policy in (None, base_policy(engaged_pose_resolution=MARGINALIZED),
                       base_policy(junction_model=JunctionModel.FIXED_RIGID)):
            self.assertIs(validate_cassette_config(frames_cfg(policy)).status, Status.VALID)


# --------------------------------------------------------------------------
# ROOT and EffectiveAnchor
# --------------------------------------------------------------------------
class RootAndAnchorTypes(unittest.TestCase):
    def test_root_singleton_never_a_string(self):
        self.assertIs(Root(), ROOT)
        self.assertIs(copy.copy(ROOT), ROOT)
        self.assertIs(copy.deepcopy(ROOT), ROOT)
        self.assertIs(pickle.loads(pickle.dumps(ROOT)), ROOT)
        self.assertNotEqual(ROOT, "ROOT")
        self.assertNotIn(ROOT, {"ROOT", "a0", "D1"})
        self.assertNotIsInstance(ROOT, str)
        self.assertEqual(repr(ROOT), "ROOT")

    def test_effective_anchor_shape_and_immutability(self):
        self.assertEqual(EffectiveAnchor._fields, ("point", "ancestor", "ancestor_module_cassette_index"))
        result = anchor("D2", state(engaged("D1", "t1")))
        point, ancestor, index = result
        self.assertEqual((point, ancestor, index), (result.point, result.ancestor, result.ancestor_module_cassette_index))
        self.assertIsInstance(result.point, tuple)
        with self.assertRaises(AttributeError):
            result.point = (0.0, 0.0, 0.0)
        with self.assertRaises(AttributeError):
            result.declared_assumptions = ()


# --------------------------------------------------------------------------
# Shielding ancestor (AP-18)
# --------------------------------------------------------------------------
class ShieldingAncestor(unittest.TestCase):
    def test_root_when_nothing_engaged_upstream(self):
        for module_id in ("D1", "D2", "D3"):
            with self.subTest(module=module_id):
                result = anchor(module_id, state())
                self.assertIs(result.ancestor, ROOT)
                self.assertEqual(result.ancestor_module_cassette_index, 0)
                self.assertEqual(result.point, ROOT_POSITION)
                self.assertEqual(result.declared_assumptions, ())

    def test_module_does_not_shield_itself(self):
        self.assertIs(anchor("D1", state(engaged("D1", "t1"))).ancestor, ROOT)
        self.assertIs(anchor("D2", state(engaged("D2", "t2"))).ancestor, ROOT)

    def test_nearest_upstream_engaged_module(self):
        cases = (
            (state(engaged("D1", "t1"), engaged("D2", "t2")), "D3", "D2", 2),
            (state(engaged("D1", "t1"), unengaged("D2")), "D3", "D1", 1),
            (state(engaged("D1", "t1")), "D3", "D1", 1),
            (state(engaged("D1", "t1"), engaged("D2", "t2"), engaged("D3", "t3")), "D2", "D1", 1),
        )
        for st, module_id, expected, index in cases:
            with self.subTest(module=module_id, expected=expected):
                result = anchor(module_id, st)
                self.assertEqual(result.ancestor, expected)
                self.assertIs(type(result.ancestor), str)
                self.assertEqual(result.ancestor_module_cassette_index, index)

    def test_downstream_engagement_ignored(self):
        st = state(engaged("D3", "t3"))
        self.assertIs(anchor("D2", st).ancestor, ROOT)
        self.assertIs(anchor("D3", st).ancestor, ROOT)

    def test_explicit_unengaged_equals_omitted(self):
        omitted = state(engaged("D1", "t1"))
        explicit = state(engaged("D1", "t1"), unengaged("D2"), unengaged("D3"))
        for module_id in ("D1", "D2", "D3"):
            self.assertEqual(anchor(module_id, omitted), anchor(module_id, explicit))


# --------------------------------------------------------------------------
# Placement convention (AP-22)
# --------------------------------------------------------------------------
class Placement(unittest.TestCase):
    def test_exact_placement_with_valid_orientation(self):
        # t = p - R.c = (10, 20, 30) - (0, 0.5, 0); point = R.exit + t = (0, 1.25, 0) + t
        result = anchor("D2", state(engaged("D1", "t1")))
        self.assertEqual(result, EffectiveAnchor((10.0, 20.75, 30.0), "D1", 1))
        identity = anchor("D2", state(engaged("D1", "t1")), context=make_context(IDENTITY))
        self.assertEqual(identity.point, (10.75, 20.0, 30.0))

    def test_declared_assumption_whenever_convention_applied(self):
        self.assertEqual(anchor("D2", state(engaged("D1", "t1"))).declared_assumptions,
                         (POSE_PLACEMENT_ASSUMPTION,))
        self.assertEqual(POSE_PLACEMENT_ASSUMPTION, "pose_placement=CAPTURE_POINT_ON_TARGET_SITE")
        self.assertEqual(anchor("D2", state()).declared_assumptions, ())

    def test_general_rotation_matches_convention_and_is_deterministic(self):
        rotation = rot_z(0.3)
        context = make_context(rotation)
        results = {anchor("D3", st, context=context) for st in (
            state(engaged("D1", "t1"), engaged("D2", "t2")),
            state(engaged("D2", "t2"), engaged("D1", "t1")),
            state(engaged("D2", "t2"), engaged("D1", "t1"), unengaged("D3")),
        )}
        self.assertEqual(len(results), 1)
        (result,) = results
        p, c, e = SITES["t2"], (0.5, 0.0, 0.0), (1.25, 0.0, 0.0)
        expected = tuple(p[i] + sum(rotation[i][k] * (e[k] - c[k]) for k in range(3)) for i in range(3))
        for got, want in zip(result.point, expected):
            self.assertAlmostEqual(got, want, places=12)
        self.assertEqual(result.ancestor, "D2")

    def test_anchor_ignores_the_modules_own_target(self):
        base = anchor("D2", state(engaged("D1", "t1"), engaged("D2", "t2")))
        moved = anchor("D2", state(engaged("D1", "t1"), engaged("D2", "t3")))
        self.assertEqual(base, moved)

    def test_junction_independent(self):  # OQ-7
        st = state(engaged("D1", "t1"))
        rigid = frames_cfg(base_policy(junction_model=JunctionModel.FIXED_RIGID))
        self.assertEqual(anchor("D2", st, cfg=rigid), anchor("D2", st))

    def test_no_bound_pose_wording(self):
        result = anchor("D2", state(engaged("D1", "t1")))
        texts = list(result.declared_assumptions) + [cassette_frames.__doc__]
        for text in texts:
            self.assertNotIn("bound pose", text.lower())


# --------------------------------------------------------------------------
# ORIENTATION_MARGINALIZED
# --------------------------------------------------------------------------
class OrientationMarginalized(unittest.TestCase):
    CFG = staticmethod(lambda: frames_cfg(base_policy(engaged_pose_resolution=MARGINALIZED)))

    def test_module_ancestor_point_undetermined(self):
        result = anchor("D2", state(engaged("D1", "t1")), cfg=self.CFG())
        self.assertEqual(result, EffectiveAnchor(None, "D1", 1))
        self.assertIsNone(result.point)
        self.assertEqual(result.declared_assumptions, ())

    def test_supplied_orientation_does_not_determine_the_point(self):
        st = state(engaged("D1", "t1"), engaged("D2", "t2"))
        contexts = (make_context(R90), make_context(IDENTITY), make_context(rot_z(1.1)), make_context(None))
        results = {anchor("D3", st, cfg=self.CFG(), context=c) for c in contexts}
        self.assertEqual(results, {EffectiveAnchor(None, "D2", 2)})
        # control: the same inputs under POSE_REQUIRED give distinct, determined points
        required = {anchor("D3", st, context=c).point for c in contexts[:3]}
        self.assertEqual(len(required), 3)
        self.assertNotIn(None, required)

    def test_root_ancestor_stays_determined(self):
        result = anchor("D1", state(engaged("D1", "t1")), cfg=self.CFG())
        self.assertEqual(result, EffectiveAnchor(ROOT_POSITION, ROOT, 0))

    def test_missing_target_still_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "TARGET_NOT_IN_CONTEXT"):
            anchor("D2", state(engaged("D1", "t9")), cfg=self.CFG())


# --------------------------------------------------------------------------
# Fail-closed inputs
# --------------------------------------------------------------------------
class FailClosed(unittest.TestCase):
    def test_missing_target_rejected(self):  # OQ-1
        for st in (state(engaged("D1", "t9")), state(engaged("D1", "t1"), engaged("D3", "t9"))):
            with self.subTest(state=st), self.assertRaisesRegex(ValueError, "GEOMETRY_INPUT_INVALID.*TARGET_NOT_IN_CONTEXT"):
                anchor("D2", st)

    def test_pose_required_needs_ancestor_orientation(self):  # OQ-5
        context = make_context(R90, t1=None)
        with self.assertRaisesRegex(ValueError, r"t1\.orientation=ORIENTATION_REQUIRED"):
            anchor("D2", state(engaged("D1", "t1")), context=context)
        # an orientation-less target that is not placed is not needed
        self.assertIs(anchor("D1", state(engaged("D1", "t1")), context=context).ancestor, ROOT)
        self.assertEqual(anchor("D3", state(engaged("D1", "t1"), engaged("D2", "t2")), context=context).ancestor, "D2")

    def test_root_position_defects(self):
        for position, defect in ((MISSING, "MISSING"), (None, "NULL"), ((0.0, 0.0), "MALFORMED"),
                                 ((True, 0.0, 0.0), "MALFORMED"), (("0", 0.0, 0.0), "MALFORMED"),
                                 ((math.nan, 0.0, 0.0), "NON_FINITE"), ((0.0, 10**400, 0.0), "NON_FINITE")):
            with self.subTest(position=position), self.assertRaisesRegex(ValueError, rf"a0\.position={defect}"):
                anchor("D1", state(), cfg=frames_cfg(position=position))

    def test_ancestor_offset_defects(self):
        cases = (
            (dict(capture_offset_vec=MISSING), r"D1\.capture_offset_vec=MISSING"),
            (dict(capture_offset_vec=None), r"D1\.capture_offset_vec=NULL"),
            (dict(exit_offset=(1.0, 0.0)), r"D1\.exit_offset=MALFORMED"),
            (dict(exit_offset=(math.inf, 0.0, 0.0)), r"D1\.exit_offset=NON_FINITE"),
        )
        for overrides, pattern in cases:
            cfg = frames_cfg(**overrides)
            self.assertIs(validate_cassette_config(cfg).status, Status.VALID)  # Phase 1c does not read them
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ValueError, pattern):
                anchor("D2", state(engaged("D1", "t1")), cfg=cfg)

    def test_complete_defect_list(self):
        cfg = frames_cfg(capture_offset_vec=None, exit_offset=(1.0, 0.0))
        with self.assertRaises(ValueError) as caught:
            anchor("D2", state(engaged("D1", "t1")), cfg=cfg, context=make_context(R90, t1=None))
        message = str(caught.exception)
        for part in ("t1.orientation=ORIENTATION_REQUIRED", "D1.exit_offset=MALFORMED", "D1.capture_offset_vec=NULL"):
            self.assertIn(part, message)

    def test_entry_types(self):
        st, cfg, context = state(), frames_cfg(), make_context()
        for args in ((1, st, cfg, context), ("D1", st.assignments, cfg, context),
                     ("D1", st, cfg.cassettes, context), ("D1", st, cfg, context.targets)):
            with self.subTest(args=[type(a).__name__ for a in args]), self.assertRaises(TypeError):
                cassette_effective_anchor(*args)

    def test_module_and_state_must_belong_to_the_cassette(self):
        with self.assertRaisesRegex(ValueError, "not in the cassette"):
            anchor("D9", state())
        with self.assertRaisesRegex(ValueError, "STATE_INPUT_INVALID.*D7"):
            anchor("D2", state(engaged("D1", "t1"), engaged("D7", "t1")))
        # amendment A2: an UNENGAGED module outside the cassette is omission
        self.assertEqual(anchor("D2", state(engaged("D1", "t1"), unengaged("D7"))), anchor("D2", state(engaged("D1", "t1"))))

    def test_config_must_be_valid(self):
        for cfg in (frames_cfg(base_policy(topology_mode=TopologyMode.GENERAL_DAG)), replace(frames_cfg(), cassettes=())):
            with self.subTest(cfg=cfg.policy.topology_mode), self.assertRaisesRegex(ValueError, "Phase 1c"):
                anchor("D1", state(), cfg=cfg)


# --------------------------------------------------------------------------
# Module surface and import boundary for this seam. The package-level export
# allowlist lives in test_cassette_topology.PurityTests (AP-1 / AP-2).
# --------------------------------------------------------------------------
class SeamBoundary(unittest.TestCase):
    def test_module_all(self):
        self.assertEqual(set(cassette_frames.__all__), {"ROOT", "EffectiveAnchor", "cassette_effective_anchor"})

    def test_cassette_frames_imports_only_permitted_modules(self):
        relative, absolute = imported_modules(ROOT_DIR / "gotne" / "cassette_frames.py")
        self.assertLessEqual(relative, {"cassette_schema", "cassette_state", "cassette_topology", "identity", "status"})
        self.assertLessEqual(absolute, {"__future__", "math", "typing"})

    def test_earlier_modules_do_not_import_frames(self):
        for name in ("cassette_state.py", "identity.py", "status.py", "cassette_schema.py", "cassette_topology.py"):
            relative, _ = imported_modules(ROOT_DIR / "gotne" / name)
            self.assertNotIn("cassette_frames", relative, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
