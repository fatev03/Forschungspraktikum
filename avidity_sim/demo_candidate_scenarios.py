"""Fixed synthetic public-path demonstration, outside the GOTNE kernel package.

Use build_synthetic_demo() with the existing gotne package on the Python import
path, then render_lines(result). This module configures no paths and performs
no I/O. It imports no test helpers and declares no new evaluation semantics.

The same three all-ENGAGED slot combinations are evaluated in two contexts:
  z-stable             sites 0, 2, 4 nm in both contexts;
  a-context-sensitive  sites 0, 2, 4 nm first, then 0, 200, 4 nm;
  m-excluded           sites 0, 200, 4 nm in both contexts.
All orientations are the identity rotation. Only the explicitly named moving
target changes position. The public kernel determines every outcome; no tier,
exclusion, report or result identity is manufactured here. The fixture exercises
an eligibility change rather than arranging a partially resolved node ledger.

All geometry is synthetic. No biological prediction or scientific validity is
claimed. Existing identity generation inside the mandated public evaluation
path is unchanged; the facade itself computes no hashes or identifiers.
"""

from dataclasses import dataclass

from gotne.cassette_candidate_batch import (
    CandidateBatchReport, CandidateDeclaration, evaluate_candidate_batch,
)
from gotne.cassette_candidate_priority import (
    CandidatePriorityReport, KNOWN_PROVIDERS, evaluate_candidate_priority,
    render_lines as render_priority_lines,
)
from gotne.cassette_scenario_comparison import (
    ScenarioComparisonReport, ScenarioDeclaration, compare_scenarios,
    render_lines as render_comparison_lines,
)
from gotne.cassette_schema import (
    AnchorSpec, CassetteConfig, CassettePolicy, CassetteSpec, CompositeDensityMethod,
    EngagedPoseResolution, EngagementOrderPolicy, JunctionModel, ModuleSpec,
    TetherSpec, TopologyMode, UnresolvedUpstreamPolicy,
)
from gotne.cassette_state import EvaluationContext, NumericalTolerances, TargetContext, TargetGeometry
from gotne.demo_candidate_manifest import (
    Combination, CombinationSource, DemoCandidateManifest, Presence, SlotChoice,
    declare_candidate_manifest, to_candidate_declarations,
)

__all__ = ["SyntheticDemoResult", "build_synthetic_demo", "render_lines"]


@dataclass(frozen=True, slots=True)
class SyntheticDemoResult:
    """Existing inputs and finished objects, in scenario order; no new status.

    The builder returns tuple containers holding the original immutable public
    objects. Rendering neither replaces nor mutates any component report.
    """

    config: CassetteConfig
    contexts: tuple[EvaluationContext, ...]
    manifests: tuple[DemoCandidateManifest, ...]
    candidate_declarations: tuple[tuple[CandidateDeclaration, ...], ...]
    batch_reports: tuple[CandidateBatchReport, ...]
    priority_reports: tuple[CandidatePriorityReport, ...]
    scenarios: tuple[ScenarioDeclaration, ...]
    comparison: ScenarioComparisonReport


def build_synthetic_demo() -> SyntheticDemoResult:
    """Run one fixed, deterministic manifest → batch → priority → comparison demo.

    No arguments, implicit discovery, external evidence or provider execution.
    The required priority provider vocabulary is supplied explicitly, with an
    empty evidence mapping; it is not a request to invoke a provider.
    """
    policy = CassettePolicy(
        topology_mode=TopologyMode.LINEAR_ORDERED_CASSETTE,
        junction_model=JunctionModel.FREE_SWIVEL,
        engagement_order_policy=EngagementOrderPolicy.ANY_ORDER,
        unresolved_upstream_policy=UnresolvedUpstreamPolicy.SELF_AVOIDANCE_IGNORED,
        engaged_pose_resolution=EngagedPoseResolution.POSE_REQUIRED,
        composite_density_method=CompositeDensityMethod.GAUSSIAN_MOMENT_MATCH,
        tau_spacer=0.25, pose_marginalization_max_level=4,
    )
    config = CassetteConfig(
        id="synthetic-demo-cassette", policy=policy,
        cassettes=(CassetteSpec("cas1", "a0", ("D1", "D2", "D3"), ("s0", "s1", "s2")),),
        anchors=(AnchorSpec("a0", "synthetic-surface", position=(0.0, 0.0, 0.0)),),
        modules=(
            ModuleSpec("D1", "cas1", 1, entry_offset=(0.0, 0.0, 0.0), exit_offset=(1.25, 0.0, 0.0),
                       capture_offset_vec=(0.5, 0.0, 0.0), exclusion_centre=(0.5, 0.0, 0.0), rho=1.0),
            ModuleSpec("D2", "cas1", 2, entry_offset=(0.0, 0.0, 0.0), exit_offset=(1.25, 0.0, 0.0),
                       capture_offset_vec=(0.5, 0.0, 0.0), exclusion_centre=(0.5, 0.0, 0.0), rho=1.0),
            ModuleSpec("D3", "cas1", 3, entry_offset=(0.0, 0.0, 0.0), exit_offset=None,
                       capture_offset_vec=(0.5, 0.0, 0.0), exclusion_centre=(0.5, 0.0, 0.0), rho=1.0),
        ),
        tethers=(TetherSpec("s0", "a0", "D1", 0, L=2.0, L_min=0.0),
                 TetherSpec("s1", "D1", "D2", 1, L=1.5, L_min=0.5),
                 TetherSpec("s2", "D2", "D3", 2, L=1.0, L_min=0.25)),
        dep_edges=(),
    )
    rotation = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    scenario_inputs = (
        ("synthetic-near", "Moving target at 2 nm", "synthetic-near-run", (2.0, 0.0, 0.0)),
        ("synthetic-shifted", "Moving target at 200 nm", "synthetic-shifted-run", (200.0, 0.0, 0.0)),
    )
    combinations = (
        Combination("z-stable", (SlotChoice(Presence.CANDIDATE, "start"),
                                 SlotChoice(Presence.CANDIDATE, "middle"),
                                 SlotChoice(Presence.CANDIDATE, "end"))),
        Combination("a-context-sensitive", (SlotChoice(Presence.CANDIDATE, "start"),
                                             SlotChoice(Presence.CANDIDATE, "moving"),
                                             SlotChoice(Presence.CANDIDATE, "end"))),
        Combination("m-excluded", (SlotChoice(Presence.CANDIDATE, "start"),
                                   SlotChoice(Presence.CANDIDATE, "far"),
                                   SlotChoice(Presence.CANDIDATE, "end"))),
    )
    contexts, manifests, declarations, batches, priorities, scenarios = [], [], [], [], [], []
    for scenario_id, label, run_ref, moving_site in scenario_inputs:
        context = EvaluationContext(
            targets=TargetContext((
                ("start", TargetGeometry((0.0, 0.0, 0.0), rotation)),
                ("middle", TargetGeometry((2.0, 0.0, 0.0), rotation)),
                ("moving", TargetGeometry(moving_site, rotation)),
                ("far", TargetGeometry((200.0, 0.0, 0.0), rotation)),
                ("end", TargetGeometry((4.0, 0.0, 0.0), rotation)),
            )),
            tolerances=NumericalTolerances(eps_len_nm=1e-9, eps_rotation=1e-9),
        )
        manifest = declare_candidate_manifest(
            scenario_id=scenario_id, primary_context_ref=run_ref,
            slots={"slot_1": ("start",), "slot_2": ("middle", "moving", "far"), "slot_3": ("end",)},
            combination_source=CombinationSource.DECLARED_LIST,
            max_combinations=3, combinations=combinations, candidate_id_prefix=None,
            source_annotation="Fixed synthetic demonstration only; no scientific validity claim.",
        )
        candidates = to_candidate_declarations(manifest, config, context)
        batch = evaluate_candidate_batch(candidates)
        priority = evaluate_candidate_priority(batch, evidence={}, providers=KNOWN_PROVIDERS)
        scenario = ScenarioDeclaration(scenario_id, label, run_ref, batch, priority)
        contexts.append(context)
        manifests.append(manifest)
        declarations.append(candidates)
        batches.append(batch)
        priorities.append(priority)
        scenarios.append(scenario)
    comparison = compare_scenarios(tuple(scenarios))
    return SyntheticDemoResult(config, tuple(contexts), tuple(manifests), tuple(declarations),
                               tuple(batches), tuple(priorities), tuple(scenarios), comparison)


def render_lines(result: SyntheticDemoResult) -> list[str]:
    """Render existing report blocks unchanged; introduce no combined status."""
    lines = ["Fixed synthetic public-path demonstration; no scientific validity or biological prediction claim.", ""]
    for scenario, priority in zip(result.scenarios, result.priority_reports):
        lines += [f"Scenario {scenario.scenario_id} — {scenario.label}; run {scenario.evaluation_run_ref}"]
        lines += render_priority_lines(priority) + [""]
    return lines + ["Declared-scenario comparison", *render_comparison_lines(result.comparison)]
