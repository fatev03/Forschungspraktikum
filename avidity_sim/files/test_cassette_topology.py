"""Phase 1c test suite.

Mandated tests: T34, T35, T36, T37, T38, T55, T56.
Additional Phase 1c tests from the v0.3 decision record: T59, T60, T61, T62,
T67, T68, T69, T70, T71, T72, T73, T74, T75, T76, T78.

v0.3.1: T55's cassette-validator expectation changed from VALID to the
§3.1.1 NOT_EVALUATED contract; the veto helper asserts §6.3/§10.8.

Assertion style: diagnostic-code MEMBERSHIP, never exclusivity. Phase 1c uses
the complete-diagnosis policy, so a malformed config legitimately reports
several codes at once.

Run: python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import importlib
import importlib.util
import pathlib
import re
import sys
import types
import unittest
from dataclasses import replace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from gotne.cassette_schema import (  # noqa: E402
    MISSING,
    AnchorSpec,
    CassetteConfig,
    CassettePolicy,
    CassetteSpec,
    CompositeDensityMethod,
    DepEdge,
    DepEdgeKind,
    EngagedPoseResolution,
    EngagementOrderPolicy,
    JunctionModel,
    ModuleSpec,
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
from gotne.identity import cache_key, config_identity_hash  # noqa: E402
from gotne.mode_applicability import (  # noqa: E402
    ModeApplicability,
    applicability_marker,
    mode_applicability,
)
from gotne.status import (  # noqa: E402
    CANONICAL_VALUE_FIELDS,
    Exactness,
    Provenance,
    Severity,
    Status,
)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
def base_policy(**overrides) -> CassettePolicy:
    kwargs = dict(
        topology_mode=TopologyMode.LINEAR_ORDERED_CASSETTE,
        junction_model=JunctionModel.FREE_SWIVEL,
        engagement_order_policy=EngagementOrderPolicy.ANY_ORDER,
        unresolved_upstream_policy=UnresolvedUpstreamPolicy.SELF_AVOIDANCE_IGNORED,
        engaged_pose_resolution=EngagedPoseResolution.POSE_REQUIRED,
        composite_density_method=CompositeDensityMethod.GAUSSIAN_MOMENT_MATCH,
    )
    kwargs.update(overrides)
    return CassettePolicy(**kwargs)


def module(mid, index, terminal=False, **overrides) -> ModuleSpec:
    kwargs = dict(
        id=mid,
        cassette_id="cas1",
        cassette_index=index,
        entry_offset=(0.0, 0.0, 0.0),
        exit_offset=None if terminal else (1.2, 0.0, 0.0),
        capture_offset_vec=(0.6, 0.0, 0.0),
        exclusion_centre=(0.6, 0.0, 0.0),
        rho=1.0,
    )
    kwargs.update(overrides)
    return ModuleSpec(**kwargs)


def ref_cassette_3(policy=None, dep_edges=()) -> CassetteConfig:
    """REF-CASSETTE-3: a0 -> D1 -> D2 -> D3. Structurally valid."""
    return CassetteConfig(
        id="REF-CASSETTE-3",
        policy=policy or base_policy(),
        cassettes=(
            CassetteSpec(
                id="cas1",
                root_anchor_id="a0",
                ordered_modules=("D1", "D2", "D3"),
                ordered_segments=("s0", "s1", "s2"),
            ),
        ),
        anchors=(AnchorSpec(id="a0", surface_id="S0"),),
        modules=(
            module("D1", 1),
            module("D2", 2),
            module("D3", 3, terminal=True, exclusion_centre=(0.5, 0.0, 0.0)),
        ),
        tethers=(
            TetherSpec(id="s0", from_node="a0", to_node="D1", cassette_index=0),
            TetherSpec(id="s1", from_node="D1", to_node="D2", cassette_index=1),
            TetherSpec(id="s2", from_node="D2", to_node="D3", cassette_index=2),
        ),
        dep_edges=tuple(dep_edges),
    )


class CassetteTestCase(unittest.TestCase):
    def assertCode(self, result, code, msg=""):
        self.assertIn(
            code,
            result.codes(),
            f"{msg} expected diagnostic {code}; got {result.codes()}",
        )

    def assertTopologyRejection(self, result, code):
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertEqual(result.status_reason, Reason.TOPOLOGY)
        self.assertCode(result, code)
        self.assertVetoFieldPattern(result)

    def assertVetoFieldPattern(self, result):
        """§10.1: veto statuses zero the probability-like and measure-like
        fields and null the density-like fields."""
        self.assertTrue(result.zeroed_due_to_status)
        self.assertFalse(result.nulled_due_to_status)
        self.assertEqual(result.values["conditional_probability"], 0.0)
        self.assertEqual(result.values["capture_integral"], 0.0)
        self.assertEqual(result.values["survival_correction"], 0.0)
        self.assertEqual(result.values["joint_score"], 0.0)
        self.assertIsNone(result.values["effective_local_concentration"])
        # v0.3.1 §6.3 / §10.8
        self.assertIs(result.provenance.worst_label, Provenance.EXACT_STRUCTURAL_VETO)
        self.assertIs(result.exact_or_approximate, Exactness.EXACT)


# --------------------------------------------------------------------------
# T34 -- three-arm star rejected (C3, C9)
# --------------------------------------------------------------------------
class T34ThreeArmStar(CassetteTestCase):
    def build(self) -> CassetteConfig:
        return CassetteConfig(
            id="cfg-star-3arm",
            policy=base_policy(),
            cassettes=(
                CassetteSpec(
                    id="cas1",
                    root_anchor_id="a0",
                    ordered_modules=("D1", "D2a", "D2b", "D2c"),
                    ordered_segments=("s0", "s1", "s2", "s3"),
                ),
            ),
            anchors=(AnchorSpec(id="a0"),),
            modules=(
                module("D1", 1),
                module("D2a", 2),
                module("D2b", 3),
                module("D2c", 4, terminal=True),
            ),
            tethers=(
                TetherSpec(id="s0", from_node="a0", to_node="D1", cassette_index=0),
                TetherSpec(id="s1", from_node="D1", to_node="D2a", cassette_index=1),
                TetherSpec(id="s2", from_node="D1", to_node="D2b", cassette_index=2),
                TetherSpec(id="s3", from_node="D1", to_node="D2c", cassette_index=3),
            ),
        )

    def test_star_is_rejected(self):
        result = validate_cassette_topology(self.build())
        self.assertTopologyRejection(result, Code.CHILD_COUNT_INVALID)

    def test_reports_outdegree_three(self):
        result = validate_cassette_topology(self.build())
        d = next(x for x in result.diagnostics if x.code == Code.CHILD_COUNT_INVALID)
        self.assertEqual(d.quantities["node"], "D1")
        self.assertEqual(d.quantities["outdeg"], 3)
        self.assertEqual(d.quantities["max_allowed"], 1)

    def test_c9_summary_emitted(self):
        result = validate_cassette_topology(self.build())
        self.assertCode(result, Code.BRANCHING_OR_PARALLEL_TOPOLOGY)


# --------------------------------------------------------------------------
# T35 -- three independently surface-anchored modules rejected (C1, C12)
# --------------------------------------------------------------------------
class T35IndependentAnchors(CassetteTestCase):
    def build(self) -> CassetteConfig:
        return CassetteConfig(
            id="cfg-three-anchors",
            policy=base_policy(),
            cassettes=(
                CassetteSpec(
                    id="cas1",
                    root_anchor_id="a1",
                    ordered_modules=("D1", "D2", "D3"),
                    ordered_segments=("s1", "s2", "s3"),
                ),
            ),
            anchors=(AnchorSpec(id="a1"), AnchorSpec(id="a2"), AnchorSpec(id="a3")),
            modules=(
                module("D1", 1),
                module("D2", 2),
                module("D3", 3, terminal=True),
            ),
            tethers=(
                TetherSpec(id="s1", from_node="a1", to_node="D1", cassette_index=0),
                TetherSpec(id="s2", from_node="a2", to_node="D2", cassette_index=1),
                TetherSpec(id="s3", from_node="a3", to_node="D3", cassette_index=2),
            ),
        )

    def test_rejected_with_both_anchor_codes(self):
        result = validate_cassette_topology(self.build())
        self.assertTopologyRejection(result, Code.MULTI_ANCHOR_IN_CASSETTE)
        self.assertCode(result, Code.SECONDARY_SURFACE_ANCHOR)

    def test_downstream_modules_flagged_as_surface_parented(self):
        result = validate_cassette_topology(self.build())
        flagged = {
            x.quantities.get("module")
            for x in result.diagnostics
            if x.code == Code.SECONDARY_SURFACE_ANCHOR
        }
        self.assertEqual(flagged, {"D2", "D3"})
        self.assertCode(result, Code.PARENT_COUNT_INVALID)


# --------------------------------------------------------------------------
# T36 -- branching node rejected (C3, C4)
# --------------------------------------------------------------------------
class T36BranchingNode(CassetteTestCase):
    def build(self) -> CassetteConfig:
        cfg = ref_cassette_3()
        return replace(
            cfg,
            id="cfg-branch",
            modules=cfg.modules + (module("D4", MISSING, terminal=True),),
            tethers=cfg.tethers
            + (TetherSpec(id="s3", from_node="D2", to_node="D4", cassette_index=3),),
        )

    def test_branch_is_rejected(self):
        result = validate_cassette_topology(self.build())
        self.assertTopologyRejection(result, Code.CHILD_COUNT_INVALID)
        d = next(x for x in result.diagnostics if x.code == Code.CHILD_COUNT_INVALID)
        self.assertEqual(d.quantities["node"], "D2")
        self.assertEqual(d.quantities["outdeg"], 2)

    def test_walk_no_longer_covers_the_cassette(self):
        result = validate_cassette_topology(self.build())
        self.assertCode(result, Code.NOT_A_SINGLE_PATH)


# --------------------------------------------------------------------------
# T37 -- disconnected downstream module rejected (C2, C4, C14)
# --------------------------------------------------------------------------
class T37DisconnectedModule(CassetteTestCase):
    def build(self) -> CassetteConfig:
        cfg = ref_cassette_3()
        return replace(
            cfg,
            id="cfg-disconnected",
            cassettes=(
                CassetteSpec(
                    id="cas1",
                    root_anchor_id="a0",
                    ordered_modules=("D1", "D2", "D3"),
                    ordered_segments=("s0", "s1"),
                ),
            ),
            tethers=cfg.tethers[:2],
        )

    def test_disconnected_module_rejected(self):
        result = validate_cassette_topology(self.build())
        self.assertTopologyRejection(result, Code.PARENT_COUNT_INVALID)
        self.assertCode(result, Code.NOT_A_SINGLE_PATH)

    def test_indegree_zero_reported(self):
        result = validate_cassette_topology(self.build())
        d = next(
            x
            for x in result.diagnostics
            if x.code == Code.PARENT_COUNT_INVALID and x.quantities.get("module") == "D3"
        )
        self.assertEqual(d.quantities["indeg"], 0)

    def test_segment_count_mismatch_reported(self):
        result = validate_cassette_topology(self.build())
        self.assertCode(result, Code.SEGMENT_SEQUENCE_INVALID)


# --------------------------------------------------------------------------
# T38 -- valid Anchor -> D1 -> D2 -> D3 chain accepted
# --------------------------------------------------------------------------
class T38ValidChain(CassetteTestCase):
    def test_topology_valid(self):
        result = validate_cassette_topology(ref_cassette_3())
        self.assertIs(result.status, Status.VALID)
        self.assertEqual(result.status_reason, Reason.OK)
        self.assertEqual(result.error_codes(), [])

    def test_full_config_valid(self):
        result = validate_cassette_config(ref_cassette_3())
        self.assertIs(result.status, Status.VALID)
        self.assertEqual(result.error_codes(), [])
        self.assertFalse(result.zeroed_due_to_status)
        self.assertFalse(result.nulled_due_to_status)
        # v0.3.1 §10.8, §17.4.1, §17.6.1
        self.assertIs(result.exact_or_approximate, Exactness.UNDEFINED)
        self.assertIs(result.provenance.worst_label, Provenance.NOT_COMPUTED)
        self.assertEqual(result.provenance.method_version, "0.3.1")
        self.assertIn(GEOMETRY_PRESENCE_ASSUMPTION, result.provenance.declared_assumptions)

    def test_declared_assumptions_recorded(self):
        result = validate_cassette_config(ref_cassette_3())
        assumptions = list(result.provenance.declared_assumptions)
        self.assertIn("topology_mode=LINEAR_ORDERED_CASSETTE", assumptions)
        self.assertIn("junction_model=FREE_SWIVEL", assumptions)
        self.assertIn("tau_spacer=0.25", assumptions)


# --------------------------------------------------------------------------
# T55 -- incompatible base tests marked MODE_NOT_APPLICABLE
# --------------------------------------------------------------------------
class T55ModeApplicability(CassetteTestCase):
    def test_t12_not_applicable_in_cassette_mode(self):
        self.assertIs(
            mode_applicability("T12", TopologyMode.LINEAR_ORDERED_CASSETTE),
            ModeApplicability.MODE_NOT_APPLICABLE,
        )

    def test_t12_applicable_in_general_dag(self):
        self.assertIs(
            mode_applicability("T12", TopologyMode.GENERAL_DAG),
            ModeApplicability.APPLICABLE,
        )

    def test_marker_is_not_pass_or_skip(self):
        marker = applicability_marker("T12", TopologyMode.LINEAR_ORDERED_CASSETTE)
        self.assertIn("MODE_NOT_APPLICABLE", marker)
        self.assertNotIn("PASS", marker)
        self.assertNotIn("SKIP", marker)

    def test_cassette_validator_is_inert_in_general_dag(self):
        """v0.3.1 §3.1.1 replaces the former VALID expectation: a validator
        that ran no check must not report a pass (L11)."""
        cfg = replace(
            ref_cassette_3(),
            policy=base_policy(topology_mode=TopologyMode.GENERAL_DAG),
        )
        for validator in (
            validate_cassette_policy_fields,
            validate_cassette_topology,
            validate_cassette_order_constraints,
            validate_cassette_identity_admissibility,
            validate_cassette_config,
        ):
            with self.subTest(validator=validator.__name__):
                result = validator(cfg)
                self.assertIs(result.status, Status.NOT_EVALUATED)
                self.assertEqual(result.status_reason, Reason.NOT_APPLICABLE)
                self.assertEqual(
                    dict(result.values), {k: None for k in CANONICAL_VALUE_FIELDS}
                )
                self.assertEqual(dict(result.value_intervals), {})
                self.assertFalse(result.zeroed_due_to_status)
                self.assertTrue(result.nulled_due_to_status)
                self.assertIs(result.provenance.worst_label, Provenance.NOT_COMPUTED)
                self.assertIs(result.exact_or_approximate, Exactness.UNDEFINED)
                self.assertEqual(result.codes(), [Code.MODE_NOT_APPLICABLE])
                self.assertIs(result.diagnostics[0].severity, Severity.INFO)


# --------------------------------------------------------------------------
# T56 / T78 -- cross-mode hash isolation and determinism
# --------------------------------------------------------------------------
class T56CacheIsolation(CassetteTestCase):
    def test_topology_mode_changes_geometry_hash(self):
        cassette = ref_cassette_3()
        general = replace(
            cassette, policy=base_policy(topology_mode=TopologyMode.GENERAL_DAG)
        )
        self.assertNotEqual(
            config_identity_hash(cassette), config_identity_hash(general)
        )

    def test_topology_mode_changes_cache_key(self):
        cassette = ref_cassette_3()
        general = replace(
            cassette, policy=base_policy(topology_mode=TopologyMode.GENERAL_DAG)
        )
        common = dict(
            node_id="D2",
            state_hash="S0",
            policy_hash="P0",
            tolerance_hash="T0",
            method_version="1.0.0",
        )
        k1 = cache_key(
            geometry_hash=config_identity_hash(cassette),
            topology_mode=TopologyMode.LINEAR_ORDERED_CASSETTE,
            **common,
        )
        k2 = cache_key(
            geometry_hash=config_identity_hash(general),
            topology_mode=TopologyMode.GENERAL_DAG,
            **common,
        )
        self.assertNotEqual(k1, k2)

    def test_cache_key_signature_excludes_shielding_ancestor(self):
        import inspect

        params = set(inspect.signature(cache_key).parameters)
        self.assertNotIn("shielding_ancestor", params)  # MNH28
        self.assertIn("topology_mode", params)

    def test_hashes_are_deterministic(self):  # T78
        self.assertEqual(
            config_identity_hash(ref_cassette_3()),
            config_identity_hash(ref_cassette_3()),
        )

    def test_missing_and_explicit_null_hash_differently(self):
        cfg_a = ref_cassette_3()
        cfg_b = replace(
            cfg_a,
            modules=(
                module("D1", 1, exclusion_centre=MISSING),
                cfg_a.modules[1],
                cfg_a.modules[2],
            ),
        )
        cfg_c = replace(
            cfg_a,
            modules=(
                module("D1", 1, exclusion_centre=None),
                cfg_a.modules[1],
                cfg_a.modules[2],
            ),
        )
        self.assertNotEqual(config_identity_hash(cfg_b), config_identity_hash(cfg_c))


# --------------------------------------------------------------------------
# Decision-specific Phase 1c tests
# --------------------------------------------------------------------------
class PolicyFieldTests(CassetteTestCase):
    def test_t59_restricted_cone_rejected(self):
        cfg = replace(
            ref_cassette_3(),
            policy=base_policy(junction_model=JunctionModel.RESTRICTED_CONE),
        )
        result = validate_cassette_policy_fields(cfg)
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertEqual(result.status_reason, Reason.JUNCTION_UNSUPPORTED)
        self.assertCode(result, Code.RESTRICTED_CONE_NOT_IMPLEMENTED)

    def test_t59_topology_stage_skipped_when_policy_fails(self):
        cfg = replace(
            ref_cassette_3(),
            policy=base_policy(junction_model=JunctionModel.RESTRICTED_CONE),
        )
        result = validate_cassette_config(cfg)
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertCode(result, Code.CHECK_SKIPPED)
        self.assertVetoFieldPattern(result)

    def test_t60_tau_spacer_out_of_range(self):
        cfg = replace(ref_cassette_3(), policy=base_policy(tau_spacer=1.4))
        result = validate_cassette_policy_fields(cfg)
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertEqual(result.status_reason, Reason.POLICY_RANGE)
        self.assertCode(result, Code.TAU_SPACER_OUT_OF_RANGE)

    def test_tau_spacer_boundaries_accepted(self):
        for value in (0.0, 0.25, 1.0):
            cfg = replace(ref_cassette_3(), policy=base_policy(tau_spacer=value))
            self.assertIs(
                validate_cassette_policy_fields(cfg).status,
                Status.VALID,
                f"tau_spacer={value} must be inside the closed interval",
            )

    def test_t61_occupancy_fraction_missing(self):
        cfg = ref_cassette_3(
            policy=base_policy(
                unresolved_upstream_policy=UnresolvedUpstreamPolicy.EXCLUDED_SHELL_BOUND
            )
        )
        result = validate_cassette_policy_fields(cfg)
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertEqual(result.status_reason, Reason.POLICY_MISSING)
        self.assertCode(result, Code.OCCUPANCY_FRACTION_MISSING)
        flagged = {
            x.quantities.get("module")
            for x in result.diagnostics
            if x.code == Code.OCCUPANCY_FRACTION_MISSING
        }
        self.assertEqual(flagged, {"D1", "D2", "D3"})

    def test_t62_occupancy_fraction_out_of_range(self):
        cfg = ref_cassette_3(
            policy=base_policy(
                unresolved_upstream_policy=UnresolvedUpstreamPolicy.EXCLUDED_SHELL_BOUND
            )
        )
        cfg = replace(
            cfg,
            modules=tuple(
                replace(m, unresolved_occupancy_fraction=1.3) for m in cfg.modules
            ),
        )
        result = validate_cassette_policy_fields(cfg)
        self.assertCode(result, Code.OCCUPANCY_FRACTION_OUT_OF_RANGE)

    def test_t73_explicit_order_missing(self):
        cfg = ref_cassette_3(
            policy=base_policy(
                engagement_order_policy=EngagementOrderPolicy.EXPLICIT_PARTIAL_ORDER
            )
        )
        result = validate_cassette_policy_fields(cfg)
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertEqual(result.status_reason, Reason.POLICY_MISSING)
        self.assertCode(result, Code.EXPLICIT_ORDER_MISSING)
        d = next(x for x in result.diagnostics if x.code == Code.EXPLICIT_ORDER_MISSING)
        self.assertIs(d.quantities["declared"], False)

    def test_missing_required_field(self):
        cfg = replace(ref_cassette_3(), policy=base_policy(junction_model=MISSING))
        result = validate_cassette_policy_fields(cfg)
        self.assertEqual(result.status_reason, Reason.POLICY_MISSING)
        self.assertCode(result, Code.POLICY_FIELD_MISSING)

    def test_missing_topology_mode(self):
        cfg = replace(ref_cassette_3(), policy=base_policy(topology_mode=MISSING))
        result = validate_cassette_policy_fields(cfg)
        self.assertCode(result, Code.TOPOLOGY_MODE_MISSING)


class TerminalOffsetTests(CassetteTestCase):
    def test_t67_terminal_exclusion_centre_missing(self):
        cfg = ref_cassette_3()
        cfg = replace(
            cfg,
            modules=cfg.modules[:2]
            + (module("D3", 3, terminal=True, exclusion_centre=MISSING),),
        )
        result = validate_cassette_topology(cfg)
        self.assertTopologyRejection(result, Code.TERMINAL_EXCLUSION_CENTRE_MISSING)

    def test_t68_non_terminal_declared_null_exit(self):
        cfg = ref_cassette_3()
        cfg = replace(
            cfg,
            modules=(cfg.modules[0], module("D2", 2, exit_offset=None), cfg.modules[2]),
        )
        result = validate_cassette_topology(cfg)
        self.assertTopologyRejection(result, Code.EXIT_OFFSET_MALFORMED)

    def test_t69_undeclared_exit_offset_is_not_null(self):
        cfg = ref_cassette_3()
        cfg = replace(
            cfg,
            modules=cfg.modules[:2]
            + (
                module(
                    "D3",
                    3,
                    exit_offset=MISSING,
                    exclusion_centre=(0.5, 0.0, 0.0),
                ),
            ),
        )
        result = validate_cassette_topology(cfg)
        self.assertTopologyRejection(result, Code.EXIT_OFFSET_MALFORMED)
        d = next(x for x in result.diagnostics if x.code == Code.EXIT_OFFSET_MALFORMED)
        self.assertIs(d.quantities["declared"], False)


class OrderConstraintTests(CassetteTestCase):
    def test_t70_requires_against_strict_order(self):
        cfg = ref_cassette_3(
            policy=base_policy(
                engagement_order_policy=EngagementOrderPolicy.STRICT_PROXIMAL_TO_DISTAL
            ),
            dep_edges=(DepEdge("D3", "D1", DepEdgeKind.REQUIRES),),
        )
        result = validate_cassette_order_constraints(cfg)
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertEqual(result.status_reason, Reason.ORDER)
        self.assertCode(result, Code.ENGAGEMENT_ORDER_CONFLICT)
        self.assertNotEqual(result.status_reason, Reason.TOPOLOGY)  # audit L21

    def test_t71_requires_cycle(self):
        cfg = ref_cassette_3(
            dep_edges=(
                DepEdge("D1", "D2", DepEdgeKind.REQUIRES),
                DepEdge("D2", "D1", DepEdgeKind.REQUIRES),
            )
        )
        result = validate_cassette_order_constraints(cfg)
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertCode(result, Code.REQUIRES_CYCLE_IN_CASSETTE)

    def test_t72_redundant_requires_is_info_only(self):
        cfg = ref_cassette_3(
            policy=base_policy(
                engagement_order_policy=EngagementOrderPolicy.STRICT_PROXIMAL_TO_DISTAL
            ),
            dep_edges=(DepEdge("D1", "D2", DepEdgeKind.REQUIRES),),
        )
        result = validate_cassette_order_constraints(cfg)
        self.assertIs(result.status, Status.VALID)
        self.assertCode(result, Code.REDUNDANT_REQUIRES_EDGE)
        self.assertEqual(result.error_codes(), [])

    def test_dep_edge_outside_cassette(self):
        cfg = ref_cassette_3(dep_edges=(DepEdge("D1", "DX", DepEdgeKind.REQUIRES),))
        result = validate_cassette_order_constraints(cfg)
        self.assertCode(result, Code.DEP_EDGE_UNKNOWN_NODE)


class CardinalityTests(CassetteTestCase):
    def test_t74_single_module_cassette_accepted(self):
        cfg = CassetteConfig(
            id="cfg-n1",
            policy=base_policy(),
            cassettes=(
                CassetteSpec(
                    id="cas1",
                    root_anchor_id="a0",
                    ordered_modules=("D1",),
                    ordered_segments=("s0",),
                ),
            ),
            anchors=(AnchorSpec(id="a0"),),
            modules=(module("D1", 1, terminal=True, exclusion_centre=(0.3, 0.0, 0.0)),),
            tethers=(
                TetherSpec(id="s0", from_node="a0", to_node="D1", cassette_index=0),
            ),
        )
        result = validate_cassette_config(cfg)
        self.assertIs(result.status, Status.VALID)
        self.assertEqual(result.error_codes(), [])

    def test_t75_single_module_terminal_centre_required(self):
        cfg = CassetteConfig(
            id="cfg-n1-bad",
            policy=base_policy(),
            cassettes=(
                CassetteSpec(
                    id="cas1",
                    root_anchor_id="a0",
                    ordered_modules=("D1",),
                    ordered_segments=("s0",),
                ),
            ),
            anchors=(AnchorSpec(id="a0"),),
            modules=(module("D1", 1, terminal=True, exclusion_centre=MISSING),),
            tethers=(
                TetherSpec(id="s0", from_node="a0", to_node="D1", cassette_index=0),
            ),
        )
        result = validate_cassette_topology(cfg)
        self.assertTopologyRejection(result, Code.TERMINAL_EXCLUSION_CENTRE_MISSING)

    def test_t76_empty_cassette_rejected(self):
        cfg = replace(
            ref_cassette_3(),
            cassettes=(
                CassetteSpec(
                    id="cas1",
                    root_anchor_id="a0",
                    ordered_modules=(),
                    ordered_segments=(),
                ),
            ),
        )
        result = validate_cassette_topology(cfg)
        self.assertTopologyRejection(result, Code.CASSETTE_EMPTY)

    def test_two_cassettes_rejected(self):
        cfg = ref_cassette_3()
        cfg = replace(cfg, cassettes=cfg.cassettes + cfg.cassettes)
        result = validate_cassette_topology(cfg)
        self.assertTopologyRejection(result, Code.CASSETTE_COUNT_INVALID)

    def test_tether_cycle_rejected(self):
        cfg = ref_cassette_3()
        cfg = replace(
            cfg,
            tethers=cfg.tethers
            + (TetherSpec(id="s3", from_node="D3", to_node="D1", cassette_index=3),),
        )
        result = validate_cassette_topology(cfg)
        self.assertTopologyRejection(result, Code.NOT_A_SINGLE_PATH)

    def test_index_sequence_mismatch_rejected(self):
        cfg = ref_cassette_3()
        cfg = replace(
            cfg,
            modules=(cfg.modules[0], module("D2", 7), cfg.modules[2]),
        )
        result = validate_cassette_topology(cfg)
        self.assertTopologyRejection(result, Code.INDEX_SEQUENCE_INVALID)


# --------------------------------------------------------------------------
# Purity contract
# --------------------------------------------------------------------------
class PurityTests(CassetteTestCase):
    FORBIDDEN = re.compile(r"^\s*(?:import|from)\s+(math|numpy|scipy|random)\b", re.M)

    def test_phase1c_modules_import_no_numerics(self):
        root = pathlib.Path(__file__).resolve().parents[1] / "gotne"
        for name in (
            "status.py",
            "cassette_schema.py",
            "cassette_topology.py",
            "mode_applicability.py",
            "identity.py",
        ):
            source = (root / name).read_text(encoding="utf-8")
            self.assertIsNone(
                self.FORBIDDEN.search(source),
                f"{name} imports a numerical or stochastic module",
            )

    # AP-1 / AP-2 (Phase 2 decision record rev. 3, L1-L3): the package surface
    # is an exact allowlist. These tests replace the Phase 1c no-leak rule.
    def test_public_api_allowlist(self):  # L1
        import gotne

        self.assertEqual(len(gotne.__all__), len(set(gotne.__all__)), "duplicate __all__ entry")
        self.assertEqual(set(gotne.__all__), PUBLIC_API)
        public = {
            name
            for name in dir(gotne)
            if not name.startswith("_") and not isinstance(getattr(gotne, name), types.ModuleType)
        }
        self.assertEqual(public, PUBLIC_API, "undeclared or missing package-level name")
        namespace: dict = {}
        exec("from gotne import *", namespace)
        self.assertEqual(set(namespace) - {"__builtins__"}, PUBLIC_API)

    def test_forbidden_names_absent(self):  # L2
        import gotne

        for name in FORBIDDEN_PACKAGE_NAMES:
            self.assertFalse(hasattr(gotne, name), f"package must not expose {name}")
        for name in FORBIDDEN_SUBMODULES:
            self.assertIsNone(importlib.util.find_spec(f"gotne.{name}"), f"gotne.{name} must not exist")

    def test_exports_are_the_submodule_objects(self):  # L3
        import gotne

        self.assertEqual(sum(len(names) for names in PHASE1C_PUBLIC_API.values()), 39)
        for table in (PHASE1C_PUBLIC_API, PHASE2_PUBLIC_API):
            for module_name, names in table.items():
                submodule = importlib.import_module(f"gotne.{module_name}")
                for name in names:
                    self.assertIs(getattr(gotne, name), getattr(submodule, name), f"{module_name}.{name}")


#: AP-2: the exact package-level public surface, keyed by defining submodule.
PHASE1C_PUBLIC_API = {
    "cassette_schema": (
        "MISSING", "AnchorSpec", "CassetteConfig", "CassettePolicy", "CassetteSpec",
        "CompositeDensityMethod", "DepEdge", "DepEdgeKind", "EngagedPoseResolution",
        "EngagementOrderPolicy", "JunctionModel", "ModuleSpec", "TetherSpec", "TopologyMode",
        "UnresolvedUpstreamPolicy",
    ),
    "cassette_topology": (
        "GEOMETRY_PRESENCE_ASSUMPTION", "Code", "Reason", "validate_cassette_config",
        "validate_cassette_identity_admissibility", "validate_cassette_order_constraints",
        "validate_cassette_policy_fields", "validate_cassette_topology",
    ),
    "identity": (
        "CANONICAL_FORM_VERSION", "CanonicalizationError", "cache_key", "config_identity_hash",
        "noncanonical_values",
    ),
    "mode_applicability": ("ModeApplicability", "applicability_marker", "mode_applicability"),
    "status": (
        "METHOD_VERSION", "DiagnosticRecord", "EvaluationResult", "Exactness", "Provenance",
        "Severity", "Status", "apply_status_field_pattern",
    ),
}
#: The 27 Phase 2 names of the decision record allowlist.
PHASE2_PUBLIC_API = {
    "cassette_state": (
        "EngagementLabel", "ModuleAssignment", "EngagementState", "TargetGeometry",
        "TargetContext", "NumericalTolerances", "EvaluationContext", "StateReason",
        "StateCertificate", "UnsupportedGeometryError", "issue_state_certificate",
    ),
    "identity": ("state_identity_hash", "context_identity_hash"),
    "cassette_frames": ("ROOT", "EffectiveAnchor", "cassette_effective_anchor"),
    "cassette_budget": (
        "SpanBasis", "BudgetElementKind", "BudgetElement", "BudgetBreakdown", "cassette_contour_budget",
    ),
    "cassette_closure": ("Tri", "chain_closure_feasible", "evaluate_state"),
    "cassette_node": ("NodeReason", "evaluate_node", "propagate_state_veto"),
}
PUBLIC_API = frozenset(
    name for table in (PHASE1C_PUBLIC_API, PHASE2_PUBLIC_API) for names in table.values() for name in names
)
#: Implementation helpers, later-seam APIs and Phase 4/5 names (decision record A).
FORBIDDEN_PACKAGE_NAMES = (
    "Root", "POSE_PLACEMENT_ASSUMPTION", "Vec3", "Rotation3", "StateCode", "OBJECT_KINDS",
    "make_result", "make_config_result", "result_identity", "tolerance_identity_hash",
    "closure_span_budget", "RIGID_SPAN_ASSUMPTION", "DERIVED_RIGID_SPAN_MESSAGE",
    "compute_conditional_density", "composite_second_moment", "so3_grid",
    "compute_pose_marginalized", "at_risk_region", "at_risk_capture_weight",
    "compute_shell_bound", "evaluate_path", "evaluate_network",
)
FORBIDDEN_SUBMODULES = (
    "composite_density", "so3_grids", "pose_marginalization", "shell_bounds", "intervals",
    "evaluate_node", "closure",
)


if __name__ == "__main__":
    unittest.main(verbosity=2)
