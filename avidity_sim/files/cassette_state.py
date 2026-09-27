"""GOTNE Phase 2 state layer (v0.3.1): engagement state, evaluation context,
state reasons and codes, and the StateCertificate.

SCOPE (Phase 2 decision record, revision 3)
-------------------------------------------
First link of the acyclic Phase 2 chain
    cassette_state -> cassette_frames -> cassette_budget -> cassette_closure -> cassette_node
This module holds pure data types and certificate packaging only. It computes
no anchor, span, budget or closure predicate, and it produces no STATE result:
evaluate_state lives in cassette_closure (AP-3).

  - EngagementState is the conditioning declaration: labels and target ids,
    never coordinates. Target geometry comes only from EvaluationContext
    (OQ-1), so it never enters state_hash or upstream_state.
  - EvaluationContext owns the targets and the numerical tolerances (OQ-2).
    Both are hashed into context_hash, never into config_identity_hash.
  - TargetGeometry.orientation is context data for the AP-22 placement
    convention. It is not a conditioned bound pose.
  - Several ENGAGED modules may share one target_id (OQ-9).
  - issue_state_certificate validates and packages. It runs no Phase 2
    evaluation stage.

Every object is frozen and validated at construction. Wrong types raise
TypeError; declared values outside their domain raise ValueError.

May import: cassette_schema, status, identity, cassette_topology, math.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, Optional, Tuple

from . import cassette_topology
from .cassette_schema import CassetteConfig, CassettePolicy, TopologyMode
from .identity import (
    CanonicalizationError,
    canonical_form,
    config_identity_hash,
    context_identity_hash,
    state_identity_hash,
)
from .status import METHOD_VERSION, EvaluationResult, Exactness, Provenance, Status

__all__ = [
    "Vec3",
    "Rotation3",
    "EngagementLabel",
    "ModuleAssignment",
    "EngagementState",
    "TargetGeometry",
    "TargetContext",
    "NumericalTolerances",
    "EvaluationContext",
    "StateReason",
    "StateCode",
    "UnsupportedGeometryError",
    "StateCertificate",
    "issue_state_certificate",
]

Vec3 = Tuple[float, float, float]
#: Row-major.
Rotation3 = Tuple[Vec3, Vec3, Vec3]


# --------------------------------------------------------------------------
# Labels, reasons, codes
# --------------------------------------------------------------------------
class EngagementLabel(str, Enum):
    """OQ-1: exactly two labels. A module absent from a state is UNENGAGED."""

    ENGAGED = "ENGAGED"
    UNENGAGED = "UNENGAGED"


class StateReason:
    """Decision record F: the closed set of STATE status reasons. Disjoint from
    every Phase 1c Reason value; policy values are never reasons."""

    STATE_INPUT_INVALID = "STATE_INPUT_INVALID"
    ENGAGEMENT_ORDER_VIOLATION = "ENGAGEMENT_ORDER_VIOLATION"
    JUNCTION_GEOMETRY_UNSUPPORTED = "JUNCTION_GEOMETRY_UNSUPPORTED"
    GEOMETRY_INPUT_INVALID = "GEOMETRY_INPUT_INVALID"
    SPAN_INTERVAL_INVALID = "SPAN_INTERVAL_INVALID"
    ENGAGED_POSE_UNDERDETERMINED = "ENGAGED_POSE_UNDERDETERMINED"
    CHAIN_CLOSURE_VIOLATED = "CHAIN_CLOSURE_VIOLATED"
    #: The only non-failure reason; pairs with VALID (AP-15).
    STATE_NOT_VETOED = "STATE_NOT_VETOED"


class StateCode:
    """Decision record F: the closed set of Phase 2 diagnostic codes, disjoint
    from Phase 1c Code. Code.CHECK_SKIPPED is reused, not repeated here."""

    # ERROR -- the seven failure reasons, plus the node-gate failure
    STATE_INPUT_INVALID = StateReason.STATE_INPUT_INVALID
    ENGAGEMENT_ORDER_VIOLATION = StateReason.ENGAGEMENT_ORDER_VIOLATION
    JUNCTION_GEOMETRY_UNSUPPORTED = StateReason.JUNCTION_GEOMETRY_UNSUPPORTED
    GEOMETRY_INPUT_INVALID = StateReason.GEOMETRY_INPUT_INVALID
    SPAN_INTERVAL_INVALID = StateReason.SPAN_INTERVAL_INVALID
    ENGAGED_POSE_UNDERDETERMINED = StateReason.ENGAGED_POSE_UNDERDETERMINED
    CHAIN_CLOSURE_VIOLATED = StateReason.CHAIN_CLOSURE_VIOLATED
    CONTOUR_BUDGET_VIOLATED = "CONTOUR_BUDGET_VIOLATED"
    # INFO
    CLOSURE_SWEEP = "CLOSURE_SWEEP"
    UNRESOLVED_UPSTREAM = "UNRESOLVED_UPSTREAM"
    CONTOUR_BUDGET = "CONTOUR_BUDGET"
    SHIELDING_ANCESTOR = "SHIELDING_ANCESTOR"
    DERIVED_RIGID_SPAN = "DERIVED_RIGID_SPAN"
    STATE_VETO_PROPAGATED = "STATE_VETO_PROPAGATED"


class UnsupportedGeometryError(ValueError):
    """AP-25: raised by a direct call to a junction-dependent geometry function
    under a junction model Phase 2 does not evaluate (FIXED_RIGID)."""


# --------------------------------------------------------------------------
# Small pure helpers
# --------------------------------------------------------------------------
_HEX64 = re.compile(r"[0-9a-f]{64}")


def _ident_ok(value: object) -> bool:
    """Identifiers are non-empty PLAIN str, as in Phase 1c (v0.3.1 §17.4.2)."""
    return type(value) is str and value != ""


def _require_identifier(value: object, what: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{what} must be a plain str, got {type(value).__qualname__}")
    if value == "":
        raise ValueError(f"{what} must be non-empty")


def _finite_float(value: object, what: str) -> float:
    """A finite real, returned as float. bool is rejected."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} must be a finite real number, got {type(value).__qualname__}")
    try:
        number = float(value)
    except OverflowError:
        number = math.inf
    if not math.isfinite(number):
        raise ValueError(f"{what} must be finite, got {number!r}")
    return number


def _triple(value: object, what: str) -> Tuple[Any, Any, Any]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{what} must be a list or tuple of length 3")
    return tuple(value)  # type: ignore[return-value]


def _vec3(value: object, what: str) -> Vec3:
    a, b, c = _triple(value, what)
    return (
        _finite_float(a, f"{what}[0]"),
        _finite_float(b, f"{what}[1]"),
        _finite_float(c, f"{what}[2]"),
    )


def _rotation_defect(rows: Rotation3, eps: float) -> Optional[str]:
    """None iff rows is orthonormal with determinant +1 within eps.
    Entries are bounded first, so no product below can overflow."""
    if any(abs(x) > 1.0 + eps for row in rows for x in row):
        return "has an entry outside [-1, 1]"
    for i in range(3):
        for j in range(3):
            dot = sum(rows[i][k] * rows[j][k] for k in range(3))
            if not abs(dot - (1.0 if i == j else 0.0)) <= eps:
                return f"is not orthonormal within eps_rotation={eps!r}"
    a, b, c = rows
    det = (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )
    if not abs(det - 1.0) <= eps:
        return f"has determinant {det!r}, not +1 within eps_rotation={eps!r}"
    return None


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ModuleAssignment:
    """OQ-1. ENGAGED requires a non-empty plain str target_id; UNENGAGED
    requires target_id None. Several ENGAGED assignments may share one
    target_id (OQ-9)."""

    module_id: str
    label: EngagementLabel
    target_id: Optional[str] = None

    def __post_init__(self) -> None:
        _require_identifier(self.module_id, "ModuleAssignment.module_id")
        if not isinstance(self.label, EngagementLabel):
            raise TypeError(
                "ModuleAssignment.label must be an EngagementLabel member, got "
                f"{type(self.label).__qualname__}"
            )
        if self.label is EngagementLabel.ENGAGED and not _ident_ok(self.target_id):
            raise ValueError(
                f"ENGAGED module {self.module_id!r} requires a non-empty plain str target_id"
            )
        if self.label is EngagementLabel.UNENGAGED and self.target_id is not None:
            raise ValueError(f"UNENGAGED module {self.module_id!r} must have target_id None")


@dataclass(frozen=True)
class EngagementState:
    """The conditioning declaration (OQ-1, AP-27). Assignments are stored in
    ascending module_id; a module absent from them is UNENGAGED. Whether an
    ENGAGED module_id belongs to the cassette is config-relative and is checked at
    evaluation (OQ-4), not here."""

    assignments: Tuple[ModuleAssignment, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.assignments, (list, tuple)):
            raise TypeError(
                "EngagementState.assignments must be a list or tuple of ModuleAssignment, "
                f"got {type(self.assignments).__qualname__}"
            )
        for index, assignment in enumerate(self.assignments):
            if not isinstance(assignment, ModuleAssignment):
                raise TypeError(
                    f"EngagementState.assignments[{index}] must be a ModuleAssignment, "
                    f"got {type(assignment).__qualname__}"
                )
        ordered = tuple(sorted(self.assignments, key=lambda a: a.module_id))
        duplicates = sorted(
            {a.module_id for a, b in zip(ordered, ordered[1:]) if a.module_id == b.module_id}
        )
        if duplicates:
            raise ValueError(f"duplicate module_id in EngagementState: {duplicates}")
        object.__setattr__(self, "assignments", ordered)

    def label_of(self, module_id: str) -> EngagementLabel:
        """The declared label, or UNENGAGED for an omitted module."""
        _require_identifier(module_id, "module_id")
        for assignment in self.assignments:
            if assignment.module_id == module_id:
                return assignment.label
        return EngagementLabel.UNENGAGED

    def engaged_assignments(self) -> Tuple[ModuleAssignment, ...]:
        return tuple(a for a in self.assignments if a.label is EngagementLabel.ENGAGED)


# --------------------------------------------------------------------------
# Evaluation context
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class NumericalTolerances:
    """OQ-2 / AP-21. Owned by EvaluationContext, never by CassettePolicy or
    CassetteConfig. Hashed into context_hash and tolerance_hash, never into
    config_identity_hash."""

    eps_len_nm: float = 1e-9
    eps_rotation: float = 1e-9

    def __post_init__(self) -> None:
        for name in ("eps_len_nm", "eps_rotation"):
            value = _finite_float(getattr(self, name), f"NumericalTolerances.{name}")
            if not value > 0.0:
                raise ValueError(f"NumericalTolerances.{name} must be > 0, got {value!r}")
            object.__setattr__(self, name, value)

    def as_dict(self) -> Dict[str, float]:
        return {"eps_len_nm": self.eps_len_nm, "eps_rotation": self.eps_rotation}


_DEFAULT_TOLERANCES = NumericalTolerances()


@dataclass(frozen=True)
class TargetGeometry:
    """One target site, laboratory frame, nm.

    orientation is optional context data used only by the AP-22 placement
    convention under POSE_REQUIRED. It is never a conditioned bound pose, and
    pose-dependent predicates ignore it under ORIENTATION_MARGINALIZED. It is
    checked here against the default eps_rotation, and again against the
    owning context's eps_rotation by EvaluationContext."""

    site_nm: Vec3
    orientation: Optional[Rotation3] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "site_nm", _vec3(self.site_nm, "TargetGeometry.site_nm"))
        if self.orientation is None:
            return
        rows = _triple(self.orientation, "TargetGeometry.orientation")
        rotation = tuple(
            _vec3(row, f"TargetGeometry.orientation[{index}]") for index, row in enumerate(rows)
        )
        defect = _rotation_defect(rotation, _DEFAULT_TOLERANCES.eps_rotation)
        if defect is not None:
            raise ValueError(f"TargetGeometry.orientation {defect}")
        object.__setattr__(self, "orientation", rotation)


@dataclass(frozen=True)
class TargetContext:
    """Declared target sites as (target_id, TargetGeometry) pairs, stored in
    ascending target_id as a tuple so identity.canonical_form accepts it. One
    entry may serve any number of ENGAGED assignments (OQ-9)."""

    targets: Tuple[Tuple[str, TargetGeometry], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.targets, (list, tuple)):
            raise TypeError(
                "TargetContext.targets must be a list or tuple of (target_id, TargetGeometry) "
                f"pairs, got {type(self.targets).__qualname__}"
            )
        entries = []
        for index, entry in enumerate(self.targets):
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                raise TypeError(
                    f"TargetContext.targets[{index}] must be a (target_id, TargetGeometry) pair"
                )
            target_id, geometry = entry
            _require_identifier(target_id, f"TargetContext.targets[{index}] target_id")
            if not isinstance(geometry, TargetGeometry):
                raise TypeError(
                    f"TargetContext.targets[{index}] geometry must be a TargetGeometry, "
                    f"got {type(geometry).__qualname__}"
                )
            entries.append((target_id, geometry))
        entries.sort(key=lambda e: e[0])
        duplicates = sorted({a for (a, _), (b, _) in zip(entries, entries[1:]) if a == b})
        if duplicates:
            raise ValueError(f"duplicate target_id in TargetContext: {duplicates}")
        object.__setattr__(self, "targets", tuple(entries))

    def lookup(self, target_id: str) -> Optional[TargetGeometry]:
        _require_identifier(target_id, "target_id")
        for key, geometry in self.targets:
            if key == target_id:
                return geometry
        return None


@dataclass(frozen=True)
class EvaluationContext:
    """AP-20: what an evaluation reads besides cfg and state. targets has no
    default, so geometry cannot run without declared targets; pass an empty
    TargetContext() explicitly when none is needed."""

    targets: TargetContext
    tolerances: NumericalTolerances = _DEFAULT_TOLERANCES

    def __post_init__(self) -> None:
        if not isinstance(self.targets, TargetContext):
            raise TypeError(
                "EvaluationContext.targets must be a TargetContext, got "
                f"{type(self.targets).__qualname__}"
            )
        if not isinstance(self.tolerances, NumericalTolerances):
            raise TypeError(
                "EvaluationContext.tolerances must be a NumericalTolerances, got "
                f"{type(self.tolerances).__qualname__}"
            )
        for target_id, geometry in self.targets.targets:
            if geometry.orientation is None:
                continue
            defect = _rotation_defect(geometry.orientation, self.tolerances.eps_rotation)
            if defect is not None:
                raise ValueError(f"orientation of target {target_id!r} {defect}")


# --------------------------------------------------------------------------
# Config- and context-relative input helpers (shared with evaluate_state)
# --------------------------------------------------------------------------
def _unknown_module_ids(state: EngagementState, cfg: CassetteConfig) -> Tuple[str, ...]:
    """OQ-4 stage-3 trigger, as amended (A2): every ENGAGED module_id that is
    not in the cassette's ordered_modules, ascending. An UNENGAGED assignment
    is equivalent to omission inside or outside the cassette, so it never
    triggers. Requires a Phase 1c VALID cfg, which has exactly one cassette."""
    if len(cfg.cassettes) != 1:
        raise ValueError("module membership needs exactly one declared cassette")
    members = frozenset(cfg.cassettes[0].ordered_modules)
    return tuple(a.module_id for a in state.engaged_assignments() if a.module_id not in members)


def _down_closure_violations(
    state: EngagementState, cfg: CassetteConfig
) -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
    """§20.7 stage 4: every R_union predecessor of an ENGAGED module must be
    ENGAGED. Returns (module_id, missing predecessors) for each violating
    module, both in cassette order. Requires a Phase 1c VALID cfg and a state
    whose ENGAGED modules are all in the cassette."""
    ordered = tuple(cfg.cassettes[0].ordered_modules)
    engaged = {a.module_id for a in state.engaged_assignments()}
    predecessors: Dict[str, set] = {}
    for before, after in cassette_topology._union_order_edges(cfg):
        predecessors.setdefault(after, set()).add(before)
    violations = []
    for module_id in ordered:
        if module_id in engaged:
            missing = tuple(
                m for m in ordered if m in predecessors.get(module_id, ()) and m not in engaged
            )
            if missing:
                violations.append((module_id, missing))
    return tuple(violations)


def _missing_targets(
    state: EngagementState, context: EvaluationContext
) -> Tuple[ModuleAssignment, ...]:
    """OQ-1 / OQ-5: every ENGAGED assignment whose target_id is absent from
    context, ascending module_id. A shared target_id is never a trigger."""
    lookup = context.targets.lookup
    return tuple(a for a in state.engaged_assignments() if lookup(a.target_id) is None)


def _upstream_state(state: EngagementState, context: EvaluationContext) -> Mapping[str, Any]:
    """Decision record J under the AP-27 equivalence: the frozen upstream_state
    snapshot lists only ENGAGED assignments, so an explicit UNENGAGED
    assignment and an omitted module serialize identically, exactly as they
    hash identically in state_identity_hash. Carries no target coordinates and
    no result metadata."""
    return MappingProxyType(
        {
            "state_hash": state_identity_hash(state),
            "context_hash": context_identity_hash(context),
            "assignments": MappingProxyType(
                {
                    a.module_id: MappingProxyType(
                        {"label": a.label.value, "target_id": a.target_id}
                    )
                    for a in state.engaged_assignments()
                }
            ),
        }
    )


def _frozen_equal(actual: object, expected: object) -> bool:
    """actual equals expected, with every mapping level read-only and every
    leaf of exactly the expected type."""
    if isinstance(expected, Mapping):
        return (
            isinstance(actual, Mapping)
            and not isinstance(actual, MutableMapping)
            and set(actual.keys()) == set(expected.keys())
            and all(_frozen_equal(actual[key], value) for key, value in expected.items())
        )
    return type(actual) is type(expected) and actual == expected


def _same_policy(policy: CassettePolicy, cfg_policy: object) -> bool:
    """AP-17, type-tagged: a plain str where cfg.policy holds an Enum member
    compares equal under == but is not the same policy."""
    if policy is cfg_policy:
        return True
    try:
        return canonical_form(policy) == canonical_form(cfg_policy)
    except CanonicalizationError:
        return False


# --------------------------------------------------------------------------
# Certificate
# --------------------------------------------------------------------------
def _state_result_defect(
    result: EvaluationResult,
    state: EngagementState,
    context: EvaluationContext,
    context_hash: str,
) -> Optional[str]:
    """First reason result cannot back a certificate for (state, context), or
    None. result_id is checked for form only; recomputing it needs
    identity.result_identity, which arrives with evaluate_state."""
    state_hash = state_identity_hash(state)
    expected_context_hash = context_identity_hash(context)
    upstream = result.upstream_state
    result_id = result.result_id
    provenance = result.provenance
    checks = (
        (result.object_kind == "STATE", "object_kind must be STATE"),
        (result.status is Status.VALID, "status must be VALID"),
        (
            result.status_reason == StateReason.STATE_NOT_VETOED,
            "status_reason must be STATE_NOT_VETOED",
        ),
        (
            result.exact_or_approximate is Exactness.UNDEFINED,
            "exact_or_approximate must be UNDEFINED",
        ),
        (provenance.worst_label is Provenance.NOT_COMPUTED, "provenance must be NOT_COMPUTED"),
        (provenance.method_id == "evaluate_state", "method_id must be evaluate_state"),
        (
            provenance.method_version == METHOD_VERSION,
            f"method_version must be {METHOD_VERSION}",
        ),
        (
            all(v is None for v in result.values.values()) and not result.value_intervals,
            "a VALID STATE result carries no payload",
        ),
        (not result.error_codes(), "a VALID STATE result carries no ERROR diagnostic"),
        (
            type(result_id) is str
            and result_id[:3] == "st-"
            and _HEX64.fullmatch(result_id[3:]) is not None,
            "result_id must be st-<64 hex>",
        ),
        (result.object_id == "S:" + state_hash, "object_id must be S:<state_hash>"),
        (result.supersedes is None, "supersedes must be None"),
        (
            context_hash == expected_context_hash,
            "context_hash must equal context_identity_hash(context)",
        ),
        (
            isinstance(upstream, Mapping) and upstream.get("state_hash") == state_hash,
            "upstream_state['state_hash'] must equal state_identity_hash(state)",
        ),
        (
            isinstance(upstream, Mapping) and upstream.get("context_hash") == expected_context_hash,
            "upstream_state['context_hash'] must equal context_identity_hash(context)",
        ),
        (
            _frozen_equal(upstream, _upstream_state(state, context)),
            "upstream_state must be exactly the frozen snapshot of state and context",
        ),
        (
            _frozen_equal(result.numerical_tolerance_used, context.tolerances.as_dict()),
            "numerical_tolerance_used must be the frozen context.tolerances",
        ),
    )
    for ok, message in checks:
        if not ok:
            return message
    return None


@dataclass(frozen=True)
class StateCertificate:
    """Proof that state was evaluated and not vetoed under context (§10.7,
    AP-7, AP-20). Only a VALID STATE result can back one. evaluate_node reads
    its context from here and matches config_identity_hash against its cfg.

    Construction enforces consistency among the five fields; binding to a cfg
    is what issue_state_certificate adds."""

    state_result: EvaluationResult
    state: EngagementState
    context: EvaluationContext
    config_identity_hash: str
    context_hash: str

    def __post_init__(self) -> None:
        for name, cls in (
            ("state_result", EvaluationResult),
            ("state", EngagementState),
            ("context", EvaluationContext),
        ):
            value = getattr(self, name)
            if not isinstance(value, cls):
                raise TypeError(
                    f"StateCertificate.{name} must be a {cls.__name__}, "
                    f"got {type(value).__qualname__}"
                )
        for name in ("config_identity_hash", "context_hash"):
            value = getattr(self, name)
            if type(value) is not str:
                raise TypeError(
                    f"StateCertificate.{name} must be a plain str, got {type(value).__qualname__}"
                )
            if _HEX64.fullmatch(value) is None:
                raise ValueError(f"StateCertificate.{name} must be a 64-hex sha256 digest")
        defect = _state_result_defect(
            self.state_result, self.state, self.context, self.context_hash
        )
        if defect is not None:
            raise ValueError(f"no StateCertificate: {defect}")

    def as_dict(self) -> Dict[str, Any]:
        """Serialized form of decision record E. topology_mode is constant:
        only LINEAR_ORDERED_CASSETTE can produce a VALID STATE result."""
        result = self.state_result
        return {
            "state_result_id": result.result_id,
            "state_hash": result.upstream_state["state_hash"],
            "context_hash": self.context_hash,
            "config_identity_hash": self.config_identity_hash,
            "topology_mode": TopologyMode.LINEAR_ORDERED_CASSETTE.value,
            "status": result.status.value,
            "exact_or_approximate": result.exact_or_approximate.value,
            "provenance": result.provenance.as_dict(),
            "numerical_tolerance_used": self.context.tolerances.as_dict(),
        }


def issue_state_certificate(
    state_result: EvaluationResult,
    state: EngagementState,
    cfg: CassetteConfig,
    policy: CassettePolicy,
    context: EvaluationContext,
) -> StateCertificate:
    """AP-7 / AP-20. Package a VALID STATE result with the state, context and
    config it was evaluated under.

    Refuses (ValueError) when policy differs from cfg.policy (AP-17), when cfg
    is not VALID under Phase 1c, when an ENGAGED assignment names a module
    outside the cassette (OQ-4, A2), when an ENGAGED target_id is absent from
    context (OQ-1),
    or when state_result is inconsistent with state and context. Wrong
    argument types raise TypeError. Runs no Phase 2 evaluation stage."""
    for name, value, cls in (
        ("state_result", state_result, EvaluationResult),
        ("state", state, EngagementState),
        ("cfg", cfg, CassetteConfig),
        ("policy", policy, CassettePolicy),
        ("context", context, EvaluationContext),
    ):
        if not isinstance(value, cls):
            raise TypeError(f"{name} must be a {cls.__name__}, got {type(value).__qualname__}")
    if not _same_policy(policy, cfg.policy):
        raise ValueError("policy must equal cfg.policy (AP-17)")
    config_result = cassette_topology.validate_cassette_config(cfg)
    if config_result.status is not Status.VALID:
        raise ValueError(
            f"cfg is {config_result.status.value} ({config_result.status_reason}) under Phase 1c; "
            "no certificate is issued"
        )
    unknown = _unknown_module_ids(state, cfg)
    if unknown:
        raise ValueError(f"state engages modules that are not in the cassette: {list(unknown)}")
    missing = _missing_targets(state, context)
    if missing:
        raise ValueError(
            "ENGAGED target_id not in context: "
            f"{[f'{a.module_id}->{a.target_id}' for a in missing]}"
        )
    return StateCertificate(
        state_result=state_result,
        state=state,
        context=context,
        config_identity_hash=config_identity_hash(cfg),
        context_hash=context_identity_hash(context),
    )
