"""GOTNE Phase 2 closure (v0.3.1): closure-pair selection and the chain-closure
predicate.

SCOPE (Phase 2 decision record, revision 3)
-------------------------------------------
Fourth link of the acyclic Phase 2 chain
    cassette_state -> cassette_frames -> cassette_budget -> cassette_closure -> cassette_node
It also owns evaluate_state (AP-3), which orchestrates every state-time check
in the stage order of decision record I and returns the STATE result.

CLOSURE PAIRS (N8, N2)
----------------------
A closure pair is two ENGAGED modules consecutive among the ENGAGED modules in
cassette order: no ENGAGED module lies strictly between them. Pairs come out
in increasing upstream index. A pair is never repaired or synthesized.

CLOSURE GATE (OQ-3, AP-22, AP-26)
---------------------------------
For a closure pair (D_i, D_j) with target sites p and orientations R, using the
placement convention of cassette_frames:
    exit_world(D_i)  = R_i.exit_offset_i  + t_i,   t_i = p_i - R_i.capture_offset_vec_i
    entry_world(D_j) = R_j.entry_offset_j + t_j,   t_j = p_j - R_j.capture_offset_vec_j
    d = ||entry_world(D_j) - exit_world(D_i)||
With [D_min, D_max] from closure_span_budget(D_i, D_j), which holds no capture
offset, and eps = context.tolerances.eps_len_nm:
    TRUE          D_min - eps <= d <= D_max + eps
    FALSE         d < D_min - eps  or  d > D_max + eps
    UNDETERMINED  under ORIENTATION_MARGINALIZED, whether or not orientations
                  are supplied: Phase 2 does not marginalize.

Direct calls raise instead of returning an outcome when the call is not
evaluable: TypeError for argument types; ValueError when policy differs from
cfg.policy, cfg is not VALID under Phase 1c, the pair is not a closure pair of
state, an ENGAGED assignment names a module outside the cassette, or inputs are invalid
(GEOMETRY_INPUT_INVALID, then SPAN_INTERVAL_INVALID, every defect listed);
UnsupportedGeometryError unless FREE_SWIVEL (OQ-7). evaluate_state runs those
checks as stages before the sweep, so the predicate never raises there.

May import: cassette_schema, status, identity, cassette_topology,
cassette_state, cassette_frames, cassette_budget, math.
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any, List, Optional, Sequence, Tuple

from . import cassette_budget, cassette_frames, cassette_state, cassette_topology
from .cassette_budget import RIGID_SPAN_ASSUMPTION, BudgetBreakdown, BudgetElementKind
from .cassette_schema import (
    CassetteConfig,
    CassettePolicy,
    EngagedPoseResolution,
    JunctionModel,
    UnresolvedUpstreamPolicy,
)
from .cassette_state import EngagementState, EvaluationContext, StateCode, StateReason, Vec3
from .identity import (
    CanonicalizationError,
    config_identity_hash,
    context_identity_hash,
    result_identity,
    state_identity_hash,
)
from .status import (
    METHOD_VERSION,
    VETO_SET,
    DiagnosticRecord,
    EvaluationResult,
    Provenance,
    Severity,
    Status,
    _freeze_json,
    make_result,
    precedence,
)

__all__ = ["Tri", "chain_closure_feasible", "evaluate_state"]


class Tri(str, Enum):
    """Three-valued predicate outcome. It has no truth value: FALSE is a
    non-empty str and would otherwise test true."""

    TRUE = "TRUE"
    FALSE = "FALSE"
    UNDETERMINED = "UNDETERMINED"

    def __bool__(self) -> bool:
        raise TypeError(
            "Tri has no truth value; compare with Tri.TRUE, Tri.FALSE or Tri.UNDETERMINED"
        )


# --------------------------------------------------------------------------
# Pair selection (stage 5: pure, no geometry)
# --------------------------------------------------------------------------
def _closure_pairs(state: EngagementState, ordered: Sequence[str]) -> Tuple[Tuple[str, str], ...]:
    """N8: consecutive ENGAGED modules in cassette order. ordered is the
    cassette's ordered_modules; modules outside it are not considered."""
    engaged = {a.module_id for a in state.engaged_assignments()}
    chain = [module_id for module_id in ordered if module_id in engaged]
    return tuple(zip(chain, chain[1:]))


# --------------------------------------------------------------------------
# Inputs and placement of one pair
# --------------------------------------------------------------------------
Defects = List[Tuple[str, str, str]]


def _pair_input_defects(
    upstream_module_id: str,
    downstream_module_id: str,
    state: EngagementState,
    cfg: CassetteConfig,
    context: EvaluationContext,
    ordered: Sequence[str],
) -> Tuple[Defects, Defects]:
    """(GEOMETRY_INPUT_INVALID defects, SPAN_INTERVAL_INVALID defects) of one
    pair, complete: every ENGAGED target (OQ-1); under POSE_REQUIRED the two
    orientations and the endpoint offsets placement reads; then the closure
    path, read by the budget's own reader."""
    geometry: Defects = [
        (a.module_id, "target_id", "TARGET_NOT_IN_CONTEXT")
        for a in cassette_state._missing_targets(state, context)
    ]
    if cfg.policy.engaged_pose_resolution is EngagedPoseResolution.POSE_REQUIRED:
        targets = {a.module_id: a.target_id for a in state.engaged_assignments()}
        specs = {m.id: m for m in cfg.modules}
        for module_id, offset_field in (
            (upstream_module_id, "exit_offset"),
            (downstream_module_id, "entry_offset"),
        ):
            target_geometry = context.targets.lookup(targets[module_id])
            if target_geometry is not None and target_geometry.orientation is None:
                geometry.append((targets[module_id], "orientation", "ORIENTATION_REQUIRED"))
            for name in (offset_field, "capture_offset_vec"):
                _, defect = cassette_frames._vector(getattr(specs[module_id], name))
                if defect is not None:
                    geometry.append((module_id, name, defect))
    intervals: Defects = []
    i = ordered.index(upstream_module_id) + 1
    j = ordered.index(downstream_module_id) + 1
    cassette_budget._path(i, j, cfg, ordered, geometry, intervals)
    return geometry, intervals


def _world_points(
    upstream_module_id: str,
    downstream_module_id: str,
    state: EngagementState,
    cfg: CassetteConfig,
    context: EvaluationContext,
) -> Tuple[Vec3, Vec3]:
    """(exit_world(D_i), entry_world(D_j)) by the AP-22 placement convention.
    Requires validated POSE_REQUIRED inputs."""
    targets = {a.module_id: a.target_id for a in state.engaged_assignments()}
    specs = {m.id: m for m in cfg.modules}
    points = []
    for module_id, offset_field in (
        (upstream_module_id, "exit_offset"),
        (downstream_module_id, "entry_offset"),
    ):
        spec = specs[module_id]
        target_geometry = context.targets.lookup(targets[module_id])
        offset, _ = cassette_frames._vector(getattr(spec, offset_field))
        capture, _ = cassette_frames._vector(spec.capture_offset_vec)
        site, rotation = target_geometry.site_nm, target_geometry.orientation
        points.append(cassette_frames._place(offset, site, rotation, capture))
    return points[0], points[1]


def _pair_separation(
    upstream_module_id: str,
    downstream_module_id: str,
    state: EngagementState,
    cfg: CassetteConfig,
    context: EvaluationContext,
) -> Tuple[float, BudgetBreakdown]:
    """(d, closure span budget) of a validated POSE_REQUIRED pair."""
    up, down = upstream_module_id, downstream_module_id
    budget = cassette_budget.closure_span_budget(up, down, state, cfg)
    exit_world, entry_world = _world_points(up, down, state, cfg, context)
    d = math.dist(entry_world, exit_world)
    if not math.isfinite(d):
        raise ValueError(
            f"{StateReason.GEOMETRY_INPUT_INVALID}: "
            f"{upstream_module_id}->{downstream_module_id}.separation=NON_FINITE"
        )
    return d, budget


# --------------------------------------------------------------------------
# Predicate
# --------------------------------------------------------------------------
def chain_closure_feasible(
    upstream_module_id: str,
    downstream_module_id: str,
    state: EngagementState,
    cfg: CassetteConfig,
    policy: CassettePolicy,
    context: EvaluationContext,
) -> Tri:
    """OQ-3 closure gate for one closure pair of state; see the module
    docstring for the outcomes and for what raises instead."""
    for name, value in (
        ("upstream_module_id", upstream_module_id),
        ("downstream_module_id", downstream_module_id),
    ):
        if type(value) is not str:
            raise TypeError(f"{name} must be a plain str, got {type(value).__qualname__}")
    for name, value, cls in (
        ("state", state, EngagementState),
        ("cfg", cfg, CassetteConfig),
        ("policy", policy, CassettePolicy),
        ("context", context, EvaluationContext),
    ):
        if not isinstance(value, cls):
            raise TypeError(f"{name} must be a {cls.__name__}, got {type(value).__qualname__}")
    if not cassette_state._same_policy(policy, cfg.policy):
        raise ValueError("policy must equal cfg.policy (AP-17)")
    pair = (upstream_module_id, downstream_module_id)
    ordered = cassette_budget._ordered_modules(pair, state, cfg)
    if (upstream_module_id, downstream_module_id) not in _closure_pairs(state, ordered):
        raise ValueError(
            f"({upstream_module_id!r}, {downstream_module_id!r}) is not a closure pair of state; "
            "pairs are never repaired (N2)"
        )
    cassette_budget._require_free_swivel(cfg)
    geometry, intervals = _pair_input_defects(
        upstream_module_id, downstream_module_id, state, cfg, context, ordered
    )
    cassette_budget._raise_defects(geometry, intervals)
    if cfg.policy.engaged_pose_resolution is EngagedPoseResolution.ORIENTATION_MARGINALIZED:
        return Tri.UNDETERMINED
    d, budget = _pair_separation(upstream_module_id, downstream_module_id, state, cfg, context)
    eps = context.tolerances.eps_len_nm
    if budget.D_min_nm - eps <= d <= budget.D_max_nm + eps:
        return Tri.TRUE
    return Tri.FALSE


# --------------------------------------------------------------------------
# Diagnostics shared with the node layer
# --------------------------------------------------------------------------
#: K: the wording every DERIVED_RIGID_SPAN diagnostic carries.
DERIVED_RIGID_SPAN_MESSAGE = "rigid spans derived from declared entry/exit offsets (provisional)"


def _diagnostic(code: str, severity: Severity, message: str, **quantities: Any) -> DiagnosticRecord:
    """Decision record J: Phase 2 quantities are frozen and JSON-safe."""
    return DiagnosticRecord(
        code=code,
        severity=severity,
        message=message,
        quantities={name: _freeze_json(value) for name, value in quantities.items()},
    )


def _skipped(checks: Sequence[str], because: str) -> List[DiagnosticRecord]:
    """Phase 1c convention: one INFO CHECK_SKIPPED per check that did not run."""
    return [
        _diagnostic(
            cassette_topology.Code.CHECK_SKIPPED,
            Severity.INFO,
            "check skipped because a prerequisite failed",
            check=check,
            because=because,
        )
        for check in checks
    ]


def _defect_diagnostics(code: str, message: str, defects: Defects) -> List[DiagnosticRecord]:
    """One ERROR per (source_id, field, defect): complete diagnosis."""
    return [
        _diagnostic(code, Severity.ERROR, message, source_id=source_id, field=name, defect=defect)
        for source_id, name, defect in defects
    ]


def _unresolved_upstream_ids(
    state: EngagementState, ordered: Sequence[str], module_id: Optional[str] = None
) -> Tuple[str, ...]:
    """N12 (amendment A2): the modules strictly between a module's shielding
    ancestor and the module, whose pose the state leaves unresolved. With
    module_id None, the union over every ENGAGED module. Cassette order."""
    engaged = {a.module_id for a in state.engaged_assignments()}
    modules = [module_id] if module_id is not None else [m for m in ordered if m in engaged]
    between = set()
    for module in modules:
        _, k = cassette_frames._shielding_ancestor(module, state, ordered)
        between.update(ordered[k : ordered.index(module)])
    return tuple(m for m in ordered if m in between)


def _unresolved_upstream_diagnostic(ids: Tuple[str, ...], cfg: CassetteConfig) -> DiagnosticRecord:
    """OQ-8 / N12-N14: diagnostic context only, never a number. Under
    EXCLUDED_SHELL_BOUND exactly the three N14 keys are reported."""
    quantities: dict = {"unresolved_upstream_ids": ids}
    if cfg.policy.unresolved_upstream_policy is UnresolvedUpstreamPolicy.EXCLUDED_SHELL_BOUND:
        quantities["unresolved_upstream_policy"] = cfg.policy.unresolved_upstream_policy.value
        quantities["downstream_numerical_evaluation_deferred"] = True
    return _diagnostic(
        StateCode.UNRESOLVED_UPSTREAM,
        Severity.INFO,
        "intervening modules whose pose this state leaves unresolved (diagnostic context only)",
        **quantities,
    )


# --------------------------------------------------------------------------
# evaluate_state (decision record I)
# --------------------------------------------------------------------------
#: Stages 3-9. A stage runs only if every earlier stage passed; each stage
#: not run is recorded as CHECK_SKIPPED.
_STAGES = (
    "state input",
    "engagement order",
    "closure pair selection",
    "junction support",
    "geometry input",
    "span intervals",
    "closure sweep",
)
_STRUCTURAL_VETO = Provenance.EXACT_STRUCTURAL_VETO
_GEOMETRIC_VETO = Provenance.EXACT_GEOMETRIC_VETO
#: Non-TRUE sweep outcome -> (status, reason, veto provenance).
_SWEEP_VERDICT = {
    Tri.FALSE: (Status.UNREACHABLE, StateReason.CHAIN_CLOSURE_VIOLATED, _GEOMETRIC_VETO),
    Tri.UNDETERMINED: (Status.DEGENERATE, StateReason.ENGAGED_POSE_UNDERDETERMINED, None),
}


def _span_element_ids(
    upstream_module_id: str, downstream_module_id: str, cfg: CassetteConfig, ordered: Sequence[str]
) -> List[str]:
    """Derived-span element ids of a validated closure path."""
    i = ordered.index(upstream_module_id) + 1
    j = ordered.index(downstream_module_id) + 1
    elements = cassette_budget._path(i, j, cfg, ordered, [], [])
    return [e.element_id for e in elements if e.kind is BudgetElementKind.SPAN]


def _state_result(
    state: EngagementState,
    cfg: CassetteConfig,
    context: EvaluationContext,
    config_hash: str,
    status: Status,
    reason: str,
    diagnostics: Sequence[DiagnosticRecord],
    veto_provenance: Optional[Provenance],
    assumptions: Sequence[str],
) -> EvaluationResult:
    """H / J: a STATE result with its deterministic result_id."""
    state_hash = state_identity_hash(state)
    context_hash = context_identity_hash(context)
    return make_result(
        "STATE",
        "S:" + state_hash,
        status,
        reason,
        diagnostics,
        method_id="evaluate_state",
        veto_provenance=veto_provenance,
        declared_assumptions=tuple(dict.fromkeys(assumptions)),
        upstream_state=cassette_state._upstream_state(state, context),
        numerical_tolerance_used=context.tolerances.as_dict(),
        result_id=result_identity(
            "STATE",
            [config_hash, state_hash, context_hash, METHOD_VERSION, "evaluate_state",
             cfg.policy.topology_mode],
        ),
    )


def evaluate_state(
    state: EngagementState,
    cfg: CassetteConfig,
    policy: CassettePolicy,
    context: EvaluationContext,
) -> EvaluationResult:
    """Decision record I: the STATE result of state under cfg and context.

    Stages, in this order; a stage runs only if every earlier one passed:
      1  entry checks: argument types (TypeError), policy == cfg.policy
         (ValueError, AP-17); a cfg without canonical identity raises
         ValueError and yields no result (amendment A2)
      2  Phase 1c validate_cassette_config, composed by §17.8 when not VALID
      3  state input: an ENGAGED module outside the cassette ->
         INFEASIBLE / STATE_INPUT_INVALID
      4  down-closure under R_union -> INFEASIBLE / ENGAGEMENT_ORDER_VIOLATION
      5  closure-pair selection (no geometry)
      6  junction support: not FREE_SWIVEL with a pair ->
         NOT_EVALUATED / JUNCTION_GEOMETRY_UNSUPPORTED
      7  geometry input -> INFEASIBLE / GEOMETRY_INPUT_INVALID
      8  span intervals -> INFEASIBLE / SPAN_INTERVAL_INVALID
      9  closure sweep, every pair in cassette order: FALSE ->
         UNREACHABLE / CHAIN_CLOSURE_VIOLATED, UNDETERMINED ->
         DEGENERATE / ENGAGED_POSE_UNDERDETERMINED, mixed by §3.3 precedence
      10 otherwise VALID / STATE_NOT_VETOED
    Stages 3-8 never call chain_closure_feasible, and inputs are diagnosed
    before the sweep, so no per-pair exception escapes."""
    # Stage 1
    for name, value, cls in (
        ("state", state, EngagementState),
        ("cfg", cfg, CassetteConfig),
        ("policy", policy, CassettePolicy),
        ("context", context, EvaluationContext),
    ):
        if not isinstance(value, cls):
            raise TypeError(f"{name} must be a {cls.__name__}, got {type(value).__qualname__}")
    if not cassette_state._same_policy(policy, cfg.policy):
        raise ValueError("policy must equal cfg.policy (AP-17)")

    # Stage 2
    config_result = cassette_topology.validate_cassette_config(cfg)
    try:
        config_hash = config_identity_hash(cfg)
    except CanonicalizationError as error:
        raise ValueError(
            "cfg has no canonical identity, so no STATE result can carry a result_id (amendment A2)"
        ) from error
    assumptions = [
        a
        for a in config_result.provenance.declared_assumptions
        if a != cassette_topology.GEOMETRY_PRESENCE_ASSUMPTION
    ]
    diagnostics: List[DiagnosticRecord] = list(config_result.diagnostics)

    def finish(status: Status, reason: str, veto: Optional[Provenance] = None) -> EvaluationResult:
        return _state_result(
            state, cfg, context, config_hash, status, reason, diagnostics, veto, assumptions
        )

    if config_result.status is not Status.VALID:
        diagnostics += _skipped(_STAGES, "Phase 1c configuration validation is not VALID")
        veto = _STRUCTURAL_VETO if config_result.status in VETO_SET else None
        return finish(config_result.status, config_result.status_reason, veto)
    ordered = tuple(cfg.cassettes[0].ordered_modules)

    # Stage 3
    unknown = cassette_state._unknown_module_ids(state, cfg)
    if unknown:
        diagnostics += [
            _diagnostic(
                StateCode.STATE_INPUT_INVALID,
                Severity.ERROR,
                "an ENGAGED assignment names a module outside the cassette",
                module_id=module_id,
                defect="UNKNOWN_MODULE",
            )
            for module_id in unknown
        ]
        diagnostics += _skipped(_STAGES[1:], "state engages modules outside the cassette")
        return finish(Status.INFEASIBLE, StateReason.STATE_INPUT_INVALID, _STRUCTURAL_VETO)

    # Stage 4
    violations = cassette_state._down_closure_violations(state, cfg)
    if violations:
        diagnostics += [
            _diagnostic(
                StateCode.ENGAGEMENT_ORDER_VIOLATION,
                Severity.ERROR,
                "engaged set is not down-closed under R_union",
                module_id=module_id,
                missing_predecessors=missing,
                engagement_order_policy=cfg.policy.engagement_order_policy.value,
            )
            for module_id, missing in violations
        ]
        diagnostics += _skipped(_STAGES[2:], "state is not down-closed under R_union")
        return finish(Status.INFEASIBLE, StateReason.ENGAGEMENT_ORDER_VIOLATION, _STRUCTURAL_VETO)

    # Stage 5
    pairs = _closure_pairs(state, ordered)

    # Stage 6
    junction_model = cfg.policy.junction_model
    if pairs and junction_model is not JunctionModel.FREE_SWIVEL:
        diagnostics.append(
            _diagnostic(
                StateCode.JUNCTION_GEOMETRY_UNSUPPORTED,
                Severity.ERROR,
                "the junction model has no Phase 2 closure geometry",
                junction_model=junction_model.value,
                unsupported_pairs=pairs,
            )
        )
        diagnostics += _skipped(_STAGES[4:], "junction geometry is unsupported")
        return finish(Status.NOT_EVALUATED, StateReason.JUNCTION_GEOMETRY_UNSUPPORTED)

    # Stages 7 and 8: every ENGAGED target, then the inputs of every pair
    geometry: Defects = [
        (a.module_id, "target_id", "TARGET_NOT_IN_CONTEXT")
        for a in cassette_state._missing_targets(state, context)
    ]
    intervals: Defects = []
    for up, down in pairs:
        pair_geometry, pair_intervals = _pair_input_defects(up, down, state, cfg, context, ordered)
        geometry += [defect for defect in pair_geometry if defect not in geometry]
        intervals += [defect for defect in pair_intervals if defect not in intervals]
    if geometry:
        diagnostics += _defect_diagnostics(
            StateCode.GEOMETRY_INPUT_INVALID,
            "an input the state-time gates read is missing or malformed",
            geometry,
        )
        diagnostics += _skipped(_STAGES[5:], "geometry input is invalid")
        return finish(Status.INFEASIBLE, StateReason.GEOMETRY_INPUT_INVALID, _STRUCTURAL_VETO)
    if intervals:
        diagnostics += _defect_diagnostics(
            StateCode.SPAN_INTERVAL_INVALID, "a segment has L_min > L", intervals
        )
        diagnostics += _skipped(_STAGES[6:], "a span interval is invalid")
        return finish(Status.INFEASIBLE, StateReason.SPAN_INTERVAL_INVALID, _STRUCTURAL_VETO)

    # Stage 9
    pose_required = cfg.policy.engaged_pose_resolution is EngagedPoseResolution.POSE_REQUIRED
    outcomes: List[Tri] = []
    span_ids: List[str] = []
    for up, down in pairs:
        outcome = chain_closure_feasible(up, down, state, cfg, policy, context)
        outcomes.append(outcome)
        if outcome is Tri.FALSE:
            d, budget = _pair_separation(up, down, state, cfg, context)
            eps = context.tolerances.eps_len_nm
            diagnostics.append(
                _diagnostic(
                    StateCode.CHAIN_CLOSURE_VIOLATED,
                    Severity.ERROR,
                    "consecutive engaged pair cannot be closed within its span budget",
                    upstream_module_id=up,
                    downstream_module_id=down,
                    d_nm=d,
                    D_min_nm=budget.D_min_nm,
                    D_max_nm=budget.D_max_nm,
                    eps_len_nm=eps,
                    side="BELOW_D_MIN" if d < budget.D_min_nm - eps else "ABOVE_D_MAX",
                )
            )
        elif outcome is Tri.UNDETERMINED:
            diagnostics.append(
                _diagnostic(
                    StateCode.ENGAGED_POSE_UNDERDETERMINED,
                    Severity.ERROR,
                    "closure needs an orientation Phase 2 does not condition on",
                    upstream_module_id=up,
                    downstream_module_id=down,
                    engaged_pose_resolution=cfg.policy.engaged_pose_resolution.value,
                )
            )
        elif outcome is not Tri.TRUE:
            raise RuntimeError(f"chain_closure_feasible returned {outcome!r}, not a Tri")
        if pose_required:
            span_ids += [e for e in _span_element_ids(up, down, cfg, ordered) if e not in span_ids]
    diagnostics.append(
        _diagnostic(
            StateCode.CLOSURE_SWEEP,
            Severity.INFO,
            "closure sweep executed over every closure pair"
            if pairs
            else "closure sweep executed over an empty domain",
            closure_pairs=pairs,
            closure_predicate_invocations=len(outcomes),
        )
    )
    unresolved = _unresolved_upstream_ids(state, ordered)
    diagnostics.append(_unresolved_upstream_diagnostic(unresolved, cfg))
    if pose_required and pairs:
        assumptions.append(cassette_frames.POSE_PLACEMENT_ASSUMPTION)
    if span_ids:
        diagnostics.append(
            _diagnostic(
                StateCode.DERIVED_RIGID_SPAN,
                Severity.INFO,
                DERIVED_RIGID_SPAN_MESSAGE,
                element_ids=span_ids,
            )
        )
        assumptions.append(RIGID_SPAN_ASSUMPTION)

    # Stage 10
    verdicts = [_SWEEP_VERDICT[outcome] for outcome in outcomes if outcome is not Tri.TRUE]
    if not verdicts:
        return finish(Status.VALID, StateReason.STATE_NOT_VETOED)
    status = precedence(*(verdict[0] for verdict in verdicts))
    _, reason, veto = next(verdict for verdict in verdicts if verdict[0] is status)
    return finish(status, reason, veto)
