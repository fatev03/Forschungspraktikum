"""Regenerate fixtures/phase2_examples.json from GOTNE's public API.

Development tool only: analytic_proxy itself never imports GOTNE. This script
uses names from gotne.__all__ and builds its configuration inline. Run it
where the gotne package is importable:

    python -m analytic_proxy.tests.make_phase2_examples

Geometry (identity orientations, exit 1.25, capture 0.5, entry 0 along x):
t1 = 0, t2 = 2.25, t3 = 4.0 close every pair of D1..D3; t4 = 20 is out of reach,
so any state engaging a module on t4 behind an engaged neighbour is vetoed.
S2_config_b evaluates S2 under a configuration that differs from the others
only in its id, so its certificate carries a different config_identity_hash.
"""

from __future__ import annotations

import json
import pathlib

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "phase2_examples.json"

#: name -> {module_id: target_id} for ENGAGED modules (all others omitted)
STATES = {
    "S0": {},
    "S1": {"D1": "t1"},
    "S2": {"D2": "t2"},
    "S3": {"D3": "t3"},
    "S12": {"D1": "t1", "D2": "t2"},
    "S13": {"D1": "t1", "D3": "t3"},
    "S23": {"D2": "t2", "D3": "t3"},
    "S123": {"D1": "t1", "D2": "t2", "D3": "t3"},
    "V14": {"D1": "t1", "D3": "t4"},
    "V124": {"D1": "t1", "D2": "t2", "D3": "t4"},
    "G19": {"D1": "t9"},
}


def build() -> dict:
    import gotne
    from gotne import (
        AnchorSpec,
        CassetteConfig,
        CassettePolicy,
        CassetteSpec,
        CompositeDensityMethod,
        EngagedPoseResolution,
        EngagementLabel,
        EngagementOrderPolicy,
        EngagementState,
        EvaluationContext,
        JunctionModel,
        ModuleAssignment,
        ModuleSpec,
        NumericalTolerances,
        Status,
        TargetContext,
        TargetGeometry,
        TetherSpec,
        TopologyMode,
        UnresolvedUpstreamPolicy,
        evaluate_state,
        issue_state_certificate,
    )

    def config(pose: EngagedPoseResolution, config_id: str = "PROXY-FIXTURE-3") -> CassetteConfig:
        policy = CassettePolicy(
            topology_mode=TopologyMode.LINEAR_ORDERED_CASSETTE,
            junction_model=JunctionModel.FREE_SWIVEL,
            engagement_order_policy=EngagementOrderPolicy.ANY_ORDER,
            unresolved_upstream_policy=UnresolvedUpstreamPolicy.SELF_AVOIDANCE_IGNORED,
            engaged_pose_resolution=pose,
            composite_density_method=CompositeDensityMethod.GAUSSIAN_MOMENT_MATCH,
        )
        shared = dict(cassette_id="cas1", entry_offset=(0.0, 0.0, 0.0), capture_offset_vec=(0.5, 0.0, 0.0),
                      exclusion_centre=(0.5, 0.0, 0.0), rho=1.0)
        lengths = {"s0": (0.0, 2.0), "s1": (0.5, 1.5), "s2": (0.25, 1.0)}
        return CassetteConfig(
            id=config_id,
            policy=policy,
            cassettes=(CassetteSpec(id="cas1", root_anchor_id="a0", ordered_modules=("D1", "D2", "D3"),
                                    ordered_segments=("s0", "s1", "s2")),),
            anchors=(AnchorSpec(id="a0", surface_id="S0", position=(0.0, 0.0, 0.0)),),
            modules=(
                ModuleSpec(id="D1", cassette_index=1, exit_offset=(1.25, 0.0, 0.0), **shared),
                ModuleSpec(id="D2", cassette_index=2, exit_offset=(1.25, 0.0, 0.0), **shared),
                ModuleSpec(id="D3", cassette_index=3, exit_offset=None, **shared),
            ),
            tethers=tuple(
                TetherSpec(id=sid, from_node=a, to_node=b, cassette_index=i, L_min=lengths[sid][0],
                           L=lengths[sid][1])
                for i, (sid, a, b) in enumerate((("s0", "a0", "D1"), ("s1", "D1", "D2"), ("s2", "D2", "D3")))
            ),
        )

    identity = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    sites = {"t1": 0.0, "t2": 2.25, "t3": 4.0, "t4": 20.0}
    targets = TargetContext(tuple((t, TargetGeometry((x, 0.0, 0.0), identity)) for t, x in sites.items()))
    context_a = EvaluationContext(targets)
    context_b = EvaluationContext(targets, NumericalTolerances(eps_len_nm=1e-6))
    pose_required = config(EngagedPoseResolution.POSE_REQUIRED)
    marginalized = config(EngagedPoseResolution.ORIENTATION_MARGINALIZED)
    config_b = config(EngagedPoseResolution.POSE_REQUIRED, "PROXY-FIXTURE-3B")

    def state(assignment: dict) -> EngagementState:
        return EngagementState(tuple(ModuleAssignment(m, EngagementLabel.ENGAGED, t) for m, t in assignment.items()))

    runs = {name: (STATES[name], pose_required, context_a) for name in STATES}
    runs["M12_marginalized"] = (STATES["S12"], marginalized, context_a)
    runs["S2_context_b"] = (STATES["S2"], pose_required, context_b)
    runs["V14_context_b"] = (STATES["V14"], pose_required, context_b)
    runs["S2_config_b"] = (STATES["S2"], config_b, context_a)

    results, certificates = {}, {}
    for name, (assignment, cfg, context) in runs.items():
        st = state(assignment)
        result = evaluate_state(st, cfg, cfg.policy, context)
        results[name] = result.as_dict()
        if result.status is Status.VALID:
            certificates[name] = issue_state_certificate(result, st, cfg, cfg.policy, context).as_dict()
    return {
        "generator": "analytic_proxy/tests/make_phase2_examples.py",
        "gotne_version": gotne.__version__,
        "state_results": results,
        "certificates": certificates,
    }


def render(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, indent=1, allow_nan=False) + "\n"


if __name__ == "__main__":
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(render(build()), encoding="utf-8")
    print(f"wrote {FIXTURE}")
