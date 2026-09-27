"""GOTNE Phase 2 node layer (v0.3.1): the node gate and state-veto propagation.

SCOPE (Phase 2 decision record, revision 3)
-------------------------------------------
Last link of the acyclic Phase 2 chain
    cassette_state -> cassette_frames -> cassette_budget -> cassette_closure -> cassette_node
It is the only producer of NODE results, and it has two producers:

  evaluate_node(node_id, state_certificate, cfg, policy)
      For an ENGAGED module of a certified (VALID) state, the OQ-6 node gate
      d = ||site(target of node_id) - effective_anchor.point|| against the node
      contour budget [D_min, D_max], with eps = context.tolerances.eps_len_nm
      and the context taken from the certificate:
        VALID / NODE_NOT_VETOED                  D_min - eps <= d <= D_max + eps
        UNREACHABLE / CONTOUR_BUDGET_VIOLATED    otherwise (side BELOW_D_MIN or ABOVE_D_MAX)
        NOT_EVALUATED / JUNCTION_GEOMETRY_UNSUPPORTED   unless FREE_SWIVEL (OQ-7)
        INFEASIBLE / GEOMETRY_INPUT_INVALID, SPAN_INTERVAL_INVALID   node-path inputs
        DEGENERATE / ENGAGED_POSE_UNDERDETERMINED   the anchor point needs an
            orientation Phase 2 does not condition on (ORIENTATION_MARGINALIZED)
  propagate_state_veto(node_id, state_result, cfg, policy)
      For any module of the cassette under a vetoed STATE result: the state's
      status, reason, exactness and worst label, the same upstream_state, and
      exactly one STATE_VETO_PROPAGATED diagnostic (G, MNH26). A STATE result
      in UNKNOWN_SET produces no NODE result.

A NODE result's object_id is node_id and its result_id is
result_identity("NODE", [config hash, state hash, node_id, context hash,
METHOD_VERSION, method_id, topology_mode]) (H). The node layer computes no
probability, density or interval; VALID means only that the Phase 2 node gate
does not veto the node (N0, N17).

May import: cassette_schema, status, identity, cassette_topology,
cassette_state, cassette_frames, cassette_budget, cassette_closure, math.
"""

from __future__ import annotations

import math
from typing import Any, List, Mapping, Optional, Sequence

from . import cassette_budget, cassette_closure, cassette_frames, cassette_state
from .cassette_budget import BudgetElementKind
from .cassette_schema import CassetteConfig, CassettePolicy, JunctionModel
from .cassette_state import EngagementLabel, StateCertificate, StateCode, StateReason
from .identity import CanonicalizationError, config_identity_hash, result_identity
from .status import (
    METHOD_VERSION,
    VETO_SET,
    DiagnosticRecord,
    EvaluationResult,
    Provenance,
    Severity,
    Status,
    make_result,
)

__all__ = ["NodeReason", "evaluate_node", "propagate_state_veto"]


class NodeReason:
    """Decision record F: the closed set of reasons only NODE results use.
    NODE results reuse StateReason for the failures they share with STATE
    results and copy a vetoing state's reason when propagated."""

    CONTOUR_BUDGET_VIOLATED = "CONTOUR_BUDGET_VIOLATED"
    NODE_NOT_VETOED = "NODE_NOT_VETOED"


_diagnostic = cassette_closure._diagnostic
_STRUCTURAL_VETO = Provenance.EXACT_STRUCTURAL_VETO


def _config_hash(cfg: CassetteConfig) -> Optional[str]:
    try:
        return config_identity_hash(cfg)
    except CanonicalizationError:
        return None


def _entry_checks(
    node_id: object, cfg: object, policy: object, name: str, value: object, cls: type
) -> None:
    if type(node_id) is not str:
        raise TypeError(f"node_id must be a plain str, got {type(node_id).__qualname__}")
    for arg_name, arg, arg_cls in (
        (name, value, cls),
        ("cfg", cfg, CassetteConfig),
        ("policy", policy, CassettePolicy),
    ):
        if not isinstance(arg, arg_cls):
            raise TypeError(
                f"{arg_name} must be a {arg_cls.__name__}, got {type(arg).__qualname__}"
            )
    if not cassette_state._same_policy(policy, cfg.policy):
        raise ValueError("policy must equal cfg.policy (AP-17)")


def _node_result(
    node_id: str,
    upstream_state: Mapping[str, Any],
    tolerances: Mapping[str, Any],
    cfg: CassetteConfig,
    config_hash: str,
    method_id: str,
    status: Status,
    reason: str,
    diagnostics: Sequence[DiagnosticRecord],
    veto_provenance: Optional[Provenance],
    assumptions: Sequence[str],
) -> EvaluationResult:
    result_id = result_identity(
        "NODE",
        [config_hash, upstream_state["state_hash"], node_id, upstream_state["context_hash"],
         METHOD_VERSION, method_id, cfg.policy.topology_mode],
    )
    return make_result(
        "NODE",
        node_id,
        status,
        reason,
        diagnostics,
        method_id=method_id,
        veto_provenance=veto_provenance,
        declared_assumptions=tuple(dict.fromkeys(assumptions)),
        upstream_state=upstream_state,
        numerical_tolerance_used=tolerances,
        result_id=result_id,
    )


# --------------------------------------------------------------------------
# Node gate
# --------------------------------------------------------------------------
def evaluate_node(
    node_id: str,
    state_certificate: StateCertificate,
    cfg: CassetteConfig,
    policy: CassettePolicy,
) -> EvaluationResult:
    """OQ-6: the node gate of node_id under a certified state; see the module
    docstring for the outcomes. Raises TypeError for argument types and
    ValueError when policy differs from cfg.policy, cfg is not the certified
    configuration, or node_id is not an ENGAGED module of the certified state."""
    _entry_checks(node_id, cfg, policy, "state_certificate", state_certificate, StateCertificate)
    config_hash = _config_hash(cfg)
    if config_hash != state_certificate.config_identity_hash:
        raise ValueError("cfg is not the configuration the state certificate was issued for")
    state, context = state_certificate.state, state_certificate.context
    ordered = tuple(cfg.cassettes[0].ordered_modules)
    if node_id not in ordered or state.label_of(node_id) is not EngagementLabel.ENGAGED:
        raise ValueError(f"node {node_id!r} is not an ENGAGED module of the certified state")
    state_result = state_certificate.state_result
    diagnostics: List[DiagnosticRecord] = []
    assumptions = list(state_result.provenance.declared_assumptions)

    def finish(status: Status, reason: str, veto: Optional[Provenance] = None) -> EvaluationResult:
        return _node_result(
            node_id, state_result.upstream_state, context.tolerances.as_dict(), cfg, config_hash,
            "evaluate_node", status, reason, diagnostics, veto, assumptions,
        )

    junction_model = cfg.policy.junction_model
    # OQ-7: the node gate is junction-dependent, so only FREE_SWIVEL evaluates it.
    if junction_model is not JunctionModel.FREE_SWIVEL:
        diagnostics.append(
            _diagnostic(
                StateCode.JUNCTION_GEOMETRY_UNSUPPORTED,
                Severity.ERROR,
                "the junction model has no Phase 2 node-gate geometry",
                junction_model=junction_model.value,
            )
        )
        diagnostics += cassette_closure._skipped(
            ("node geometry input", "node span intervals", "node gate"),
            "junction geometry is unsupported",
        )
        return finish(Status.NOT_EVALUATED, StateReason.JUNCTION_GEOMETRY_UNSUPPORTED)

    ancestor, k = cassette_frames._shielding_ancestor(node_id, state, ordered)
    diagnostics.append(
        _diagnostic(
            StateCode.SHIELDING_ANCESTOR,
            Severity.INFO,
            "shielding ancestor of the node (AP-18)",
            module_id=node_id,
            shielding_ancestor=cassette_frames._tagged_ancestor(ancestor, k),
        )
    )
    diagnostics.append(
        cassette_closure._unresolved_upstream_diagnostic(
            cassette_closure._unresolved_upstream_ids(state, ordered, node_id), cfg
        )
    )

    # Inputs the node gate reads, diagnosed before any geometry runs.
    j = ordered.index(node_id) + 1
    geometry = [
        (a.module_id, "target_id", "TARGET_NOT_IN_CONTEXT")
        for a in cassette_state._missing_targets(state, context)
    ]
    geometry += cassette_frames._anchor_input_defects(ancestor, state, cfg, context)
    intervals: List[Any] = []
    cassette_budget._path(k, j, cfg, ordered, geometry, intervals)
    cassette_budget._capture(next(m for m in cfg.modules if m.id == node_id), j, geometry)
    if geometry:
        diagnostics += cassette_closure._defect_diagnostics(
            StateCode.GEOMETRY_INPUT_INVALID,
            "an input the node gate reads is missing or malformed",
            geometry,
        )
        diagnostics += cassette_closure._skipped(
            ("node span intervals", "node gate"), "geometry input is invalid"
        )
        return finish(Status.INFEASIBLE, StateReason.GEOMETRY_INPUT_INVALID, _STRUCTURAL_VETO)
    if intervals:
        diagnostics += cassette_closure._defect_diagnostics(
            StateCode.SPAN_INTERVAL_INVALID, "a segment has L_min > L", intervals
        )
        diagnostics += cassette_closure._skipped(("node gate",), "a span interval is invalid")
        return finish(Status.INFEASIBLE, StateReason.SPAN_INTERVAL_INVALID, _STRUCTURAL_VETO)

    budget = cassette_budget.cassette_contour_budget(node_id, state, cfg)
    diagnostics.append(
        _diagnostic(
            StateCode.CONTOUR_BUDGET,
            Severity.INFO,
            "node contour budget from the shielding ancestor, capture offset included once",
            contour_budget_breakdown=budget.as_dict(),
        )
    )
    span_ids = [e.element_id for e in budget.elements if e.kind is BudgetElementKind.SPAN]
    if span_ids:
        diagnostics.append(
            _diagnostic(
                StateCode.DERIVED_RIGID_SPAN,
                Severity.INFO,
                cassette_closure.DERIVED_RIGID_SPAN_MESSAGE,
                element_ids=span_ids,
            )
        )
    assumptions += budget.declared_assumptions

    anchor = cassette_frames.cassette_effective_anchor(node_id, state, cfg, context)
    assumptions += anchor.declared_assumptions
    if anchor.point is None:
        diagnostics.append(
            _diagnostic(
                StateCode.ENGAGED_POSE_UNDERDETERMINED,
                Severity.ERROR,
                "the effective anchor needs an orientation Phase 2 does not condition on",
                module_id=node_id,
                engaged_pose_resolution=cfg.policy.engaged_pose_resolution.value,
            )
        )
        diagnostics += cassette_closure._skipped(
            ("node gate",), "the effective anchor point is undetermined"
        )
        return finish(Status.DEGENERATE, StateReason.ENGAGED_POSE_UNDERDETERMINED)

    target_id = next(a.target_id for a in state.engaged_assignments() if a.module_id == node_id)
    d = math.dist(context.targets.lookup(target_id).site_nm, anchor.point)
    if not math.isfinite(d):
        diagnostics += cassette_closure._defect_diagnostics(
            StateCode.GEOMETRY_INPUT_INVALID,
            "the node separation is not finite",
            [(node_id, "separation", "NON_FINITE")],
        )
        return finish(Status.INFEASIBLE, StateReason.GEOMETRY_INPUT_INVALID, _STRUCTURAL_VETO)
    eps = context.tolerances.eps_len_nm
    if budget.D_min_nm - eps <= d <= budget.D_max_nm + eps:
        return finish(Status.VALID, NodeReason.NODE_NOT_VETOED)
    diagnostics.append(
        _diagnostic(
            StateCode.CONTOUR_BUDGET_VIOLATED,
            Severity.ERROR,
            "the target site lies outside the contour budget of the shielding path",
            module_id=node_id,
            d_nm=d,
            D_min_nm=budget.D_min_nm,
            D_max_nm=budget.D_max_nm,
            eps_len_nm=eps,
            side="BELOW_D_MIN" if d < budget.D_min_nm - eps else "ABOVE_D_MAX",
        )
    )
    return finish(
        Status.UNREACHABLE, NodeReason.CONTOUR_BUDGET_VIOLATED, Provenance.EXACT_GEOMETRIC_VETO
    )


# --------------------------------------------------------------------------
# Veto propagation
# --------------------------------------------------------------------------
def propagate_state_veto(
    node_id: str,
    state_result: EvaluationResult,
    cfg: CassetteConfig,
    policy: CassettePolicy,
) -> EvaluationResult:
    """Decision record G: the NODE result of node_id under a vetoed STATE
    result. Raises TypeError for argument types and ValueError when policy
    differs from cfg.policy, state_result is not a vetoed STATE result,
    its result_id is not the evaluate_state id for cfg, or node_id is not a
    module of the cassette."""
    _entry_checks(node_id, cfg, policy, "state_result", state_result, EvaluationResult)
    if state_result.object_kind != "STATE" or state_result.status not in VETO_SET:
        raise ValueError(
            "only a vetoed STATE result propagates; "
            "a STATE result in UNKNOWN_SET produces no NODE result"
        )
    config_hash = _config_hash(cfg)
    if config_hash is None:
        raise ValueError("cfg has no canonical identity (amendment A2)")
    upstream = state_result.upstream_state
    expected = result_identity(
        "STATE",
        [config_hash, upstream["state_hash"], upstream["context_hash"], METHOD_VERSION,
         "evaluate_state", cfg.policy.topology_mode],
    )
    if state_result.result_id != expected:
        raise ValueError(
            "state_result is not the evaluate_state result for this cfg (result_id mismatch)"
        )
    members = cfg.cassettes[0].ordered_modules if len(cfg.cassettes) == 1 else ()
    if not isinstance(members, (list, tuple)) or node_id not in members:
        raise ValueError(f"node {node_id!r} is not a module of the cassette")
    diagnostics = [
        _diagnostic(
            StateCode.STATE_VETO_PROPAGATED,
            Severity.INFO,
            "conditioning state was vetoed; node not evaluated",
            vetoing_state_result_id=state_result.result_id,
            vetoing_status=state_result.status.value,
            vetoing_status_reason=state_result.status_reason,
        )
    ]
    return _node_result(
        node_id,
        upstream,
        state_result.numerical_tolerance_used,
        cfg,
        config_hash,
        "propagate_state_veto",
        state_result.status,
        state_result.status_reason,
        diagnostics,
        state_result.provenance.worst_label,
        state_result.provenance.declared_assumptions,
    )
