"""GOTNE Phase 1c: pure structural validation for LINEAR_ORDERED_CASSETTE.

PURITY CONTRACT
---------------
This module performs NO geometry and NO numerical computation. It reads:
  - identifiers and their multiplicities,
  - graph adjacency,
  - integer indices,
  - the PRESENCE or ABSENCE of declared fields,
  - scalar domain checks on declared policy fields (range membership only).
It never reads the components of a position, normal, offset, or length, and it
never imports math, numpy, or any GOTNE evaluation module.

ENTRY CONTRACT (v0.3.1 §9.2)
----------------------------
Every public validator first checks SCHEMA STRUCTURE: the argument must be a
CassetteConfig, its policy a CassettePolicy, and each of cassettes / anchors /
modules / tethers / dep_edges a list or tuple of the matching schema class.
A violation raises TypeError deterministically, before any stage runs.
Everything else is DECLARED INPUT: no declared value, however malformed, makes
a public validator raise. It returns a structured EvaluationResult instead.

EXECUTION ORDER
---------------
validate_cassette_config runs, in this order and never reordered:
  gate  topology_mode applicability            (v0.3.1 §3.1.1)
  P0    validate_cassette_policy_fields
  P1    validate_cassette_topology              (invariants C1-C14, N-1)
  P2    validate_cassette_order_constraints     (decision D8, N-2)
  P3    validate_cassette_identity_admissibility (v0.3.1 §17.7)
A stage runs only if every earlier stage returned VALID; otherwise it is
recorded as CHECK_SKIPPED. The composed status is VALID iff every executed
stage is VALID (v0.3.1 §17.8). All run BEFORE WF1-WF7, which belong to the
base validator and are untouched here.

COMPLETE-DIAGNOSIS POLICY
-------------------------
Within a stage, every check whose own prerequisites hold runs and every
violation is reported. A check whose prerequisite failed emits an INFO
CHECK_SKIPPED diagnostic naming the check and the reason; nothing is guessed.
The only stage-level exits are the mode gate and the prerequisites listed in
each stage's docstring, and each of them emits CHECK_SKIPPED for what it skips.

Specification references: Addendum A v0.3 sections 17.1, 17.2, 17.4, 17.5,
17.6, 18.4, 19.2.1, 19.3.1, 20.6, 11.8; v0.3.1 decision record.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet, List, Mapping, Optional, Sequence, Set, Tuple

from .cassette_schema import (
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
    Missing,
    ModuleSpec,
    SUPPORTED_JUNCTION_MODELS_V1,
    TetherSpec,
    TopologyMode,
    UnresolvedUpstreamPolicy,
)
from .identity import noncanonical_values
from .status import (
    DiagnosticRecord,
    EvaluationResult,
    Severity,
    Status,
    make_config_result,
    precedence,
)

__all__ = [
    "Reason",
    "Code",
    "RUNTIME_ENFORCED_INVARIANTS",
    "INVARIANT_OF_CODE",
    "GEOMETRY_PRESENCE_ASSUMPTION",
    "validate_cassette_policy_fields",
    "validate_cassette_topology",
    "validate_cassette_order_constraints",
    "validate_cassette_identity_admissibility",
    "validate_cassette_config",
]


# --------------------------------------------------------------------------
# Reason strings (§17.4: topology failures share ONE reason; order and policy
# failures use distinct reasons, audit item L21)
# --------------------------------------------------------------------------
class Reason:
    TOPOLOGY = "TOPOLOGY_NOT_LINEAR_ORDERED_CASSETTE"
    ORDER = "ENGAGEMENT_ORDER_CONSTRAINTS_UNSATISFIABLE"
    POLICY_MISSING = "POLICY_FIELD_MISSING"
    POLICY_RANGE = "POLICY_FIELD_OUT_OF_RANGE"
    JUNCTION_UNSUPPORTED = "JUNCTION_MODEL_NOT_SUPPORTED_V1"
    OK = "ALL_STRUCTURAL_CHECKS_PASSED"
    NOT_APPLICABLE = "CASSETTE_VALIDATION_NOT_APPLICABLE"
    #: v0.3.1 §17.4.1: reason of a NOT_EVALUATED stage whose checks could not run.
    PREREQUISITE_FAILED = "STAGE_PREREQUISITE_FAILED"
    #: v0.3.1 §17.7: P3 failure.
    NOT_CANONICALIZABLE = "CONFIG_NOT_CANONICALIZABLE"


class Code:
    # C1 / C1a / C12 -- anchoring and declaration
    CASSETTE_COUNT_INVALID = "CASSETTE_COUNT_INVALID"
    CASSETTE_EMPTY = "CASSETTE_EMPTY"
    MULTI_ANCHOR_IN_CASSETTE = "MULTI_ANCHOR_IN_CASSETTE"
    ROOT_ANCHOR_MISSING = "ROOT_ANCHOR_MISSING"
    ROOT_ANCHOR_MISMATCH = "ROOT_ANCHOR_MISMATCH"
    SECONDARY_SURFACE_ANCHOR = "SECONDARY_SURFACE_ANCHOR"
    # C2 / C3 -- degrees
    PARENT_COUNT_INVALID = "PARENT_COUNT_INVALID"
    CHILD_COUNT_INVALID = "CHILD_COUNT_INVALID"
    # C4 / C13 -- connectivity
    NOT_A_SINGLE_PATH = "NOT_A_SINGLE_PATH"
    SEGMENT_SEQUENCE_INVALID = "SEGMENT_SEQUENCE_INVALID"
    MULTIPATH_CONNECTIVITY = "MULTIPATH_CONNECTIVITY"
    # C10a / C10b -- offsets
    EXIT_OFFSET_MALFORMED = "EXIT_OFFSET_MALFORMED"
    TERMINAL_EXCLUSION_CENTRE_MISSING = "TERMINAL_EXCLUSION_CENTRE_MISSING"
    # C11 / C14 -- membership and declaration integrity
    INDEX_SEQUENCE_INVALID = "INDEX_SEQUENCE_INVALID"
    ORPHAN_MODULE = "ORPHAN_MODULE"
    DUPLICATE_IDENTIFIER = "DUPLICATE_IDENTIFIER"  # v0.3.1 §17.4.1
    IDENTIFIER_MALFORMED = "IDENTIFIER_MALFORMED"  # v0.3.1 §17.4.2 (N-1)
    # C9 -- summary
    BRANCHING_OR_PARALLEL_TOPOLOGY = "BRANCHING_OR_PARALLEL_TOPOLOGY"
    # policy
    TOPOLOGY_MODE_MISSING = "TOPOLOGY_MODE_MISSING"
    POLICY_FIELD_MISSING = "POLICY_FIELD_MISSING"
    RESTRICTED_CONE_NOT_IMPLEMENTED = "RESTRICTED_CONE_NOT_IMPLEMENTED"
    TAU_SPACER_OUT_OF_RANGE = "TAU_SPACER_OUT_OF_RANGE"
    POSE_LEVEL_OUT_OF_RANGE = "POSE_LEVEL_OUT_OF_RANGE"
    OCCUPANCY_FRACTION_MISSING = "OCCUPANCY_FRACTION_MISSING"
    OCCUPANCY_FRACTION_OUT_OF_RANGE = "OCCUPANCY_FRACTION_OUT_OF_RANGE"
    EXPLICIT_ORDER_MISSING = "EXPLICIT_ORDER_MISSING"
    EXPLICIT_ORDER_UNEXPECTED = "EXPLICIT_ORDER_UNEXPECTED"
    EXPLICIT_ORDER_MALFORMED = "EXPLICIT_ORDER_MALFORMED"  # v0.3.1 §20.6.1
    EXPLICIT_ORDER_INVALID_REFERENCE = "EXPLICIT_ORDER_INVALID_REFERENCE"  # v0.3.1 §20.6.1
    # order constraints
    REQUIRES_CYCLE_IN_CASSETTE = "REQUIRES_CYCLE_IN_CASSETTE"
    ENGAGEMENT_ORDER_CONFLICT = "ENGAGEMENT_ORDER_CONFLICT"
    REDUNDANT_REQUIRES_EDGE = "REDUNDANT_REQUIRES_EDGE"
    DEP_EDGE_UNKNOWN_NODE = "DEP_EDGE_UNKNOWN_NODE"
    DEP_EDGE_MALFORMED = "DEP_EDGE_MALFORMED"  # v0.3.1 §17.4.2 (N-2)
    # identity admissibility
    NON_CANONICAL_VALUE = "NON_CANONICAL_VALUE"  # v0.3.1 §17.7
    # process
    CHECK_SKIPPED = "CHECK_SKIPPED"
    MODE_NOT_APPLICABLE = "MODE_NOT_APPLICABLE"


#: C5-C8 are runtime invariants. Phase 1c does NOT enforce them and does not
#: pretend to; they are registered here so that an auditor can see the gap.
RUNTIME_ENFORCED_INVARIANTS: Tuple[str, ...] = ("C5", "C6", "C7", "C8")

INVARIANT_OF_CODE: Mapping[str, str] = {
    Code.CASSETTE_COUNT_INVALID: "C1a",
    Code.CASSETTE_EMPTY: "C11",
    Code.MULTI_ANCHOR_IN_CASSETTE: "C1",
    Code.ROOT_ANCHOR_MISSING: "C1",
    Code.ROOT_ANCHOR_MISMATCH: "C1",
    Code.SECONDARY_SURFACE_ANCHOR: "C12",
    Code.PARENT_COUNT_INVALID: "C2",
    Code.CHILD_COUNT_INVALID: "C3",
    Code.NOT_A_SINGLE_PATH: "C4",
    Code.SEGMENT_SEQUENCE_INVALID: "C4",
    Code.MULTIPATH_CONNECTIVITY: "C13",
    Code.EXIT_OFFSET_MALFORMED: "C10a",
    Code.TERMINAL_EXCLUSION_CENTRE_MISSING: "C10b",
    Code.INDEX_SEQUENCE_INVALID: "C11",
    Code.ORPHAN_MODULE: "C14",
    Code.DUPLICATE_IDENTIFIER: "C14",
    Code.IDENTIFIER_MALFORMED: "C14",
    Code.BRANCHING_OR_PARALLEL_TOPOLOGY: "C9",
}

#: v0.3.1 §17.6.1: carried by every Phase 1c VALID CONFIG result.
GEOMETRY_PRESENCE_ASSUMPTION = "geometry_presence_unchecked=entry_offset,capture_offset_vec"

#: C9 is the union of C1, C2, C3, C4. It is emitted as a summary whenever any
#: of its constituents fired.
_C9_TRIGGER_CODES = frozenset(
    {
        Code.MULTI_ANCHOR_IN_CASSETTE,
        Code.ROOT_ANCHOR_MISSING,
        Code.ROOT_ANCHOR_MISMATCH,
        Code.PARENT_COUNT_INVALID,
        Code.CHILD_COUNT_INVALID,
        Code.NOT_A_SINGLE_PATH,
        Code.SEGMENT_SEQUENCE_INVALID,
    }
)

_REQUIRED_POLICY_FIELDS: Tuple[Tuple[str, type], ...] = (
    ("junction_model", JunctionModel),
    ("engagement_order_policy", EngagementOrderPolicy),
    ("unresolved_upstream_policy", UnresolvedUpstreamPolicy),
    ("engaged_pose_resolution", EngagedPoseResolution),
    ("composite_density_method", CompositeDensityMethod),
)

#: Deterministic reason selection when a stage produces several kinds of
#: failure. Missing fields come first because absent fields make the remaining
#: checks meaningless.
_POLICY_REASON_PRIORITY: Tuple[str, ...] = (
    Reason.POLICY_MISSING,
    Reason.JUNCTION_UNSUPPORTED,
    Reason.POLICY_RANGE,
)

_SCHEMA_SEQUENCES: Tuple[Tuple[str, type], ...] = (
    ("cassettes", CassetteSpec),
    ("anchors", AnchorSpec),
    ("modules", ModuleSpec),
    ("tethers", TetherSpec),
    ("dep_edges", DepEdge),
)

_POSITIVE_INFINITY = float("inf")
_NEGATIVE_INFINITY = float("-inf")


# --------------------------------------------------------------------------
# Small pure helpers
# --------------------------------------------------------------------------
def _declared(value: object) -> bool:
    """True iff the field was declared at all (MISSING means not declared).
    Explicit null (None) counts as declared."""
    return not isinstance(value, Missing)


def _is_real_number(value: object) -> bool:
    """Finite real check without importing math. bool is rejected: a boolean
    where a fraction is expected is a declaration error, not a 0/1 value."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if value != value:  # NaN
        return False
    return value not in (_POSITIVE_INFINITY, _NEGATIVE_INFINITY)


def _is_index(value: object) -> bool:
    """Strict integer index. bool and float are rejected."""
    return type(value) is int


def _ident_ok(value: object) -> bool:
    """v0.3.1 §17.4.2: identifiers are non-empty PLAIN str (no subclasses, so
    no str-Enum members)."""
    return type(value) is str and value != ""


def _seq_ok(value: object) -> bool:
    return isinstance(value, (list, tuple))


def _type_name(value: object) -> str:
    return "MISSING" if isinstance(value, Missing) else type(value).__qualname__


def _safe(value: object) -> object:
    """v0.3.1 §9.1.1: JSON-safe, run-independent rendering of a declared value.
    Never uses repr()."""
    if isinstance(value, Missing):
        return "MISSING"
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        if value != value:
            return "nan"
        if value in (_POSITIVE_INFINITY, _NEGATIVE_INFINITY):
            return "inf" if value > 0 else "-inf"
        return value
    if isinstance(value, Enum):
        return f"{type(value).__qualname__}.{value.name}"
    return {"type": type(value).__qualname__}


def _object_id(cfg: CassetteConfig) -> str:
    return cfg.id if _ident_ok(cfg.id) else f"<malformed id: {_type_name(cfg.id)}>"


def _err(code: str, message: str, **quantities: object) -> DiagnosticRecord:
    return DiagnosticRecord(
        code=code, severity=Severity.ERROR, message=message, quantities=dict(quantities)
    )


def _info(code: str, message: str, **quantities: object) -> DiagnosticRecord:
    return DiagnosticRecord(
        code=code, severity=Severity.INFO, message=message, quantities=dict(quantities)
    )


def _skipped(check: str, because: str) -> DiagnosticRecord:
    return _info(
        Code.CHECK_SKIPPED,
        "check skipped because a prerequisite failed",
        check=check,
        because=because,
    )


def _assumption_value(value: object) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if type(value) in (bool, int, float, str):
        return str(value)
    return f"<{_type_name(value)}>"


def _assumptions(cfg: CassetteConfig) -> Tuple[str, ...]:
    out: List[str] = []
    p = cfg.policy
    for name in (
        "topology_mode",
        "junction_model",
        "engagement_order_policy",
        "unresolved_upstream_policy",
        "engaged_pose_resolution",
        "composite_density_method",
    ):
        v = getattr(p, name)
        if _declared(v):
            out.append(f"{name}={_assumption_value(v)}")
    out.append(f"tau_spacer={_assumption_value(p.tau_spacer)}")
    out.append(
        f"pose_marginalization_max_level={_assumption_value(p.pose_marginalization_max_level)}"
    )
    return tuple(out)


def _result(
    cfg: CassetteConfig,
    status: Status,
    reason: str,
    diagnostics: Sequence[DiagnosticRecord],
    method_id: str,
) -> EvaluationResult:
    assumptions = _assumptions(cfg)
    if status is Status.VALID:
        assumptions += (GEOMETRY_PRESENCE_ASSUMPTION,)
    return make_config_result(
        object_id=_object_id(cfg),
        status=status,
        status_reason=reason,
        diagnostics=tuple(diagnostics),
        declared_assumptions=assumptions,
        method_id=method_id,
    )


def _require_schema(cfg: object) -> None:
    """v0.3.1 §9.2: the only permitted raise from a public validator."""
    if not isinstance(cfg, CassetteConfig):
        raise TypeError(f"expected CassetteConfig, got {type(cfg).__qualname__}")
    if not isinstance(cfg.policy, CassettePolicy):
        raise TypeError(
            f"CassetteConfig.policy must be a CassettePolicy, got {type(cfg.policy).__qualname__}"
        )
    for name, cls in _SCHEMA_SEQUENCES:
        seq = getattr(cfg, name)
        if not isinstance(seq, (list, tuple)):
            raise TypeError(
                f"CassetteConfig.{name} must be a list or tuple of {cls.__name__}, "
                f"got {type(seq).__qualname__}"
            )
        for index, item in enumerate(seq):
            if not isinstance(item, cls):
                raise TypeError(
                    f"CassetteConfig.{name}[{index}] must be a {cls.__name__}, "
                    f"got {type(item).__qualname__}"
                )


def _mode_gate(
    cfg: CassetteConfig, method_id: str, skipped: Sequence[str]
) -> Optional[EvaluationResult]:
    """Shared entry gate (v0.3.1 §3.1.1). None means: cassette mode, run.

    A TopologyMode member other than LINEAR_ORDERED_CASSETTE yields the
    NOT_EVALUATED not-applicable contract with exactly one MODE_NOT_APPLICABLE
    diagnostic. Anything else is rejected as TOPOLOGY_MODE_MISSING, and every
    check the caller would have run is recorded as CHECK_SKIPPED."""
    mode = cfg.policy.topology_mode
    if mode is TopologyMode.LINEAR_ORDERED_CASSETTE:
        return None
    if isinstance(mode, TopologyMode):
        return make_config_result(
            object_id=_object_id(cfg),
            status=Status.NOT_EVALUATED,
            status_reason=Reason.NOT_APPLICABLE,
            diagnostics=(
                _info(
                    Code.MODE_NOT_APPLICABLE,
                    "cassette validation does not apply to this topology mode",
                    topology_mode=mode.value,
                ),
            ),
            declared_assumptions=(f"topology_mode={mode.value}",),
            method_id=method_id,
        )
    declared = _declared(mode)
    diagnostics = [
        _err(
            Code.TOPOLOGY_MODE_MISSING,
            "topology_mode is REQUIRED, has no default, and must be a TopologyMode member",
            field="topology_mode",
            declared=declared,
            declared_type=_type_name(mode) if declared else None,
        )
    ]
    diagnostics.extend(_skipped(check, "topology_mode is invalid") for check in skipped)
    return _result(cfg, Status.INFEASIBLE, Reason.POLICY_MISSING, diagnostics, method_id)


def _ordered_members(cas: CassetteSpec) -> FrozenSet[str]:
    """Well-formed identifier entries of a well-formed ordered_modules
    container. A malformed container declares no members."""
    if not _seq_ok(cas.ordered_modules):
        return frozenset()
    return frozenset(m for m in cas.ordered_modules if _ident_ok(m))


def _normalize_explicit_order(
    cas: CassetteSpec, members: FrozenSet[str]
) -> Tuple[Optional[Tuple[Tuple[str, str], ...]], List[DiagnosticRecord]]:
    """v0.3.1 §20.6.1. The ONLY reader of a declared explicit_partial_order.

    Returns (pairs, diagnostics). pairs is the deduplicated, declaration-ordered
    tuple of (a, b) meaning a ≺ b, or None if the declaration violates the
    contract (then diagnostics explains why). The value must already be
    DECLARED; MISSING is handled by the caller."""
    cassette = _safe(cas.id)
    value = cas.explicit_partial_order
    diagnostics: List[DiagnosticRecord] = []
    if not _seq_ok(value):
        diagnostics.append(
            _err(
                Code.EXPLICIT_ORDER_MALFORMED,
                "explicit_partial_order must be a list or tuple of [from, to] pairs",
                cassette=cassette,
                problem="CONTAINER_TYPE",
                pair_index=None,
                found_type=_type_name(value),
            )
        )
        diagnostics.append(
            _skipped("explicit_partial_order entries and references", "container is malformed")
        )
        return None, diagnostics

    pairs: List[Tuple[str, str]] = []
    for index, entry in enumerate(value):
        if not _seq_ok(entry):
            diagnostics.append(
                _err(
                    Code.EXPLICIT_ORDER_MALFORMED,
                    "each explicit_partial_order entry must be a list or tuple",
                    cassette=cassette,
                    problem="ENTRY_TYPE",
                    pair_index=index,
                    found_type=_type_name(entry),
                )
            )
            continue
        if len(entry) != 2:
            diagnostics.append(
                _err(
                    Code.EXPLICIT_ORDER_MALFORMED,
                    "each explicit_partial_order entry must have exactly two elements",
                    cassette=cassette,
                    problem="ENTRY_ARITY",
                    pair_index=index,
                    found_type=_type_name(entry),
                    arity=len(entry),
                )
            )
            continue
        a, b = entry[0], entry[1]
        if type(a) is not str or type(b) is not str:
            diagnostics.append(
                _err(
                    Code.EXPLICIT_ORDER_MALFORMED,
                    "explicit_partial_order elements must be plain str module ids",
                    cassette=cassette,
                    problem="ELEMENT_TYPE",
                    pair_index=index,
                    found_type=[_type_name(a), _type_name(b)],
                )
            )
            continue
        problems = []
        if a == b:
            problems.append("SELF_LOOP")
        if a not in members or b not in members:
            problems.append("UNKNOWN_MODULE")
        if problems:
            diagnostics.append(
                _err(
                    Code.EXPLICIT_ORDER_INVALID_REFERENCE,
                    "explicit_partial_order entry is not a pair of distinct cassette modules",
                    cassette=cassette,
                    pair_index=index,
                    pair=[a, b],
                    problems=sorted(problems),
                )
            )
            continue
        if (a, b) not in pairs:  # idempotent duplicates (R_policy is a relation)
            pairs.append((a, b))
    if diagnostics:
        return None, diagnostics
    return tuple(pairs), diagnostics


# --------------------------------------------------------------------------
# P0 -- policy field validation
# --------------------------------------------------------------------------
_P0_CHECKS = ("P0 policy fields",)


def validate_cassette_policy_fields(cfg: CassetteConfig) -> EvaluationResult:
    """Stage P0. Presence, enum membership, and scalar domain of declared
    policy fields; the full explicit_partial_order declaration contract
    (v0.3.1 §20.6.1). Decisions D2, D3, D4, D5, D8, D9.

    No REQUIRED field is ever filled in by this function (MNH14)."""
    _require_schema(cfg)
    method = "validate_cassette_policy_fields"
    gate = _mode_gate(cfg, method, _P0_CHECKS)
    if gate is not None:
        return gate

    policy = cfg.policy
    diagnostics: List[DiagnosticRecord] = []
    reasons: Set[str] = set()

    # Required enum fields.
    for name, enum_cls in _REQUIRED_POLICY_FIELDS:
        value = getattr(policy, name)
        if not _declared(value):
            diagnostics.append(
                _err(
                    Code.POLICY_FIELD_MISSING,
                    f"{name} is REQUIRED and has no default",
                    field=name,
                )
            )
            reasons.add(Reason.POLICY_MISSING)
        elif not isinstance(value, enum_cls):
            diagnostics.append(
                _err(
                    Code.POLICY_FIELD_MISSING,
                    f"{name} is not a member of {enum_cls.__name__}",
                    field=name,
                    declared=_safe(value),
                    declared_type=_type_name(value),
                )
            )
            reasons.add(Reason.POLICY_MISSING)

    # D2: RESTRICTED_CONE declared but not implemented in v1.
    junction = policy.junction_model
    if isinstance(junction, JunctionModel) and junction not in SUPPORTED_JUNCTION_MODELS_V1:
        diagnostics.append(
            DiagnosticRecord(
                code=Code.RESTRICTED_CONE_NOT_IMPLEMENTED,
                severity=Severity.ERROR,
                message=(
                    "junction_model RESTRICTED_CONE is declared in the schema but "
                    "not implemented in v1 and MUST NOT be mapped onto another model"
                ),
                quantities={
                    "junction_model": junction.value,
                    "supported": [j.value for j in SUPPORTED_JUNCTION_MODELS_V1],
                },
                remediation=(
                    "use FIXED_RIGID if the relative junction rotations are known, "
                    "or EXTERNAL_SAMPLED_CHAIN if they are not"
                ),
            )
        )
        reasons.add(Reason.JUNCTION_UNSUPPORTED)

    # D3: tau_spacer domain [0, 1].
    tau = policy.tau_spacer
    if not _is_real_number(tau) or not (0.0 <= float(tau) <= 1.0):
        diagnostics.append(
            _err(
                Code.TAU_SPACER_OUT_OF_RANGE,
                "tau_spacer must be a finite real in the closed interval [0, 1]",
                field="tau_spacer",
                declared=_safe(tau),
                valid_range="[0.0, 1.0]",
            )
        )
        reasons.add(Reason.POLICY_RANGE)

    # D5: pose marginalization refinement cap.
    level = policy.pose_marginalization_max_level
    if not _is_index(level) or not (0 <= level <= 6):
        diagnostics.append(
            _err(
                Code.POSE_LEVEL_OUT_OF_RANGE,
                "pose_marginalization_max_level must be an integer in [0, 6]",
                field="pose_marginalization_max_level",
                declared=_safe(level),
                valid_range="[0, 6]",
            )
        )
        reasons.add(Reason.POLICY_RANGE)

    # D4: per-module occupancy fraction under EXCLUDED_SHELL_BOUND.
    if policy.unresolved_upstream_policy is UnresolvedUpstreamPolicy.EXCLUDED_SHELL_BOUND:
        for module in cfg.modules:
            phi = module.unresolved_occupancy_fraction
            if not _declared(phi) or phi is None:
                diagnostics.append(
                    _err(
                        Code.OCCUPANCY_FRACTION_MISSING,
                        "unresolved_occupancy_fraction is REQUIRED for every cassette "
                        "module under EXCLUDED_SHELL_BOUND",
                        module=_safe(module.id),
                    )
                )
                reasons.add(Reason.POLICY_MISSING)
            elif not _is_real_number(phi) or not (0.0 <= float(phi) <= 1.0):
                diagnostics.append(
                    _err(
                        Code.OCCUPANCY_FRACTION_OUT_OF_RANGE,
                        "unresolved_occupancy_fraction must be a finite real in [0, 1]",
                        module=_safe(module.id),
                        declared=_safe(phi),
                        valid_range="[0.0, 1.0]",
                    )
                )
                reasons.add(Reason.POLICY_RANGE)

    # D8 + v0.3.1 §20.6.1: explicit partial order, per declared cassette.
    order_policy = policy.engagement_order_policy
    if not isinstance(order_policy, EngagementOrderPolicy):
        diagnostics.append(
            _skipped("explicit_partial_order contract", "engagement_order_policy is invalid")
        )
    else:
        for cas in cfg.cassettes:
            declared_order = _declared(cas.explicit_partial_order)
            if order_policy is EngagementOrderPolicy.EXPLICIT_PARTIAL_ORDER:
                if not declared_order:
                    diagnostics.append(
                        _err(
                            Code.EXPLICIT_ORDER_MISSING,
                            "explicit_partial_order is REQUIRED under EXPLICIT_PARTIAL_ORDER",
                            cassette=_safe(cas.id),
                            declared=False,
                        )
                    )
                    reasons.add(Reason.POLICY_MISSING)
                    continue
                _, order_diags = _normalize_explicit_order(cas, _ordered_members(cas))
                diagnostics.extend(order_diags)
                if any(x.severity is Severity.ERROR for x in order_diags):
                    reasons.add(Reason.POLICY_RANGE)
            elif declared_order:
                # Declared null is declared, not MISSING (D7, D8). Shape is not
                # inspected under a non-explicit policy (v0.3.1 §20.6.1).
                diagnostics.append(
                    _err(
                        Code.EXPLICIT_ORDER_UNEXPECTED,
                        "explicit_partial_order may only be declared under "
                        "EXPLICIT_PARTIAL_ORDER",
                        cassette=_safe(cas.id),
                        engagement_order_policy=order_policy.value,
                    )
                )
                reasons.add(Reason.POLICY_MISSING)

    if not reasons:
        return _result(cfg, Status.VALID, Reason.OK, diagnostics, method)
    reason = next(r for r in _POLICY_REASON_PRIORITY if r in reasons)
    return _result(cfg, Status.INFEASIBLE, reason, diagnostics, method)


# --------------------------------------------------------------------------
# P1 -- topology validation, invariants C1..C14
# --------------------------------------------------------------------------
_P1_CHECKS = ("P1 topology",)

_CASSETTE_DEPENDENT_CHECKS = (
    "C14", "C11", "C1 root_anchor_id match", "C12", "C2", "C3", "C4", "C13",
    "segment cardinality", "segment membership", "segment references",
    "C10a", "C10b",
)
_ORDERED_DEPENDENT_CHECKS = (
    "C14", "C11", "C12", "C2/C3", "C4", "C13", "segment cardinality", "C10a", "C10b",
)
_SEGMENT_DEPENDENT_CHECKS = (
    "segment cardinality", "segment membership", "segment references", "C4 segment/edge match",
)


def _count_walks(
    out: Mapping[str, Sequence[str]], start: str, target: str, cap: int = 2
) -> int:
    """Count distinct tether walks start -> target, stopping at `cap`.
    Cycle-safe: a node already on the current stack is not re-entered."""
    count = 0
    stack: List[Tuple[str, Tuple[str, ...]]] = [(start, (start,))]
    while stack:
        node, path = stack.pop()
        if node == target and len(path) > 1:
            count += 1
            if count >= cap:
                return count
            continue
        for nxt in out.get(node, ()):
            if nxt in path:
                continue
            stack.append((nxt, path + (nxt,)))
    return count


def _check_identifier_list(
    value: object, path: str, d: List[DiagnosticRecord]
) -> Optional[List[str]]:
    """Returns the list if the container and every entry are well formed."""
    if not _seq_ok(value):
        d.append(
            _err(
                Code.IDENTIFIER_MALFORMED,
                "identifier list must be a list or tuple",
                path=path,
                found_type=_type_name(value),
            )
        )
        return None
    ok = True
    for index, entry in enumerate(value):
        if not _ident_ok(entry):
            d.append(
                _err(
                    Code.IDENTIFIER_MALFORMED,
                    "identifier must be a non-empty plain str",
                    path=f"{path}[{index}]",
                    found_type=_type_name(entry),
                )
            )
            ok = False
    return list(value) if ok else None


def _check_identifier(value: object, path: str, d: List[DiagnosticRecord]) -> bool:
    if _ident_ok(value):
        return True
    d.append(
        _err(
            Code.IDENTIFIER_MALFORMED,
            "identifier must be a non-empty plain str",
            path=path,
            found_type=_type_name(value),
        )
    )
    return False


def validate_cassette_topology(cfg: CassetteConfig) -> EvaluationResult:
    """Stage P1. Invariants C1-C14, §17.5 (v0.3), plus v0.3.1 §17.4.1/§17.4.2.

    Every structural violation reports status INFEASIBLE with the single
    mandated status_reason TOPOLOGY_NOT_LINEAR_ORDERED_CASSETTE; the specific
    invariant is carried by the diagnostic code.

    Prerequisites, each recorded as CHECK_SKIPPED when it fails:
      - identifier and duplicate checks: none;
      - cassette-dependent checks: exactly one declared cassette;
      - checks reading ordered_modules / ordered_segments: that list is well formed;
      - C4 walk and C13: a unique root anchor;
      - C10a/C10b: a valid index sequence (C11).
    A graph element with a malformed identifier is excluded from every
    identifier-keyed structure and recorded as CHECK_SKIPPED."""
    _require_schema(cfg)
    method = "validate_cassette_topology"
    gate = _mode_gate(cfg, method, _P1_CHECKS)
    if gate is not None:
        return gate

    d: List[DiagnosticRecord] = []

    # ---- Stage A: declaration integrity (no prerequisites) ---------------
    _check_identifier(cfg.id, "id", d)

    anchors: List[AnchorSpec] = []
    for i, a in enumerate(cfg.anchors):
        if _check_identifier(a.id, f"anchors[{i}].id", d):
            anchors.append(a)
        else:
            d.append(_skipped(f"graph checks involving anchors[{i}]", "identifier is malformed"))
    modules: List[ModuleSpec] = []
    for i, m in enumerate(cfg.modules):
        if _check_identifier(m.id, f"modules[{i}].id", d):
            modules.append(m)
        else:
            d.append(_skipped(f"graph checks involving modules[{i}]", "identifier is malformed"))
    named_tethers: List[TetherSpec] = []  # well-formed id
    graph_tethers: List[TetherSpec] = []  # well-formed id and endpoints
    for i, t in enumerate(cfg.tethers):
        id_ok = _check_identifier(t.id, f"tethers[{i}].id", d)
        from_ok = _check_identifier(t.from_node, f"tethers[{i}].from_node", d)
        to_ok = _check_identifier(t.to_node, f"tethers[{i}].to_node", d)
        if id_ok:
            named_tethers.append(t)
        if id_ok and from_ok and to_ok:
            graph_tethers.append(t)
        else:
            d.append(_skipped(f"graph checks involving tethers[{i}]", "identifier is malformed"))

    # Duplicates. Anchors and modules share the node namespace; tethers have
    # their own. A dict built from repeated keys keeps the LAST declaration,
    # so every later lookup would read one arbitrary copy.
    node_kinds: Dict[str, List[str]] = {}
    for a in anchors:
        node_kinds.setdefault(a.id, []).append("anchor")
    for m in modules:
        node_kinds.setdefault(m.id, []).append("module")
    for nid in sorted(node_kinds):
        kinds = node_kinds[nid]
        if len(kinds) > 1:
            d.append(
                _err(
                    Code.DUPLICATE_IDENTIFIER,
                    "node identifier is declared more than once",
                    namespace="node",
                    id=nid,
                    count=len(kinds),
                    kinds=sorted(kinds),
                )
            )
    tether_counts: Dict[str, int] = {}
    for t in named_tethers:
        tether_counts[t.id] = tether_counts.get(t.id, 0) + 1
    duplicate_tethers = {tid for tid, c in tether_counts.items() if c > 1}
    for tid in sorted(duplicate_tethers):
        d.append(
            _err(
                Code.DUPLICATE_IDENTIFIER,
                "tether identifier is declared more than once",
                namespace="tether",
                id=tid,
                count=tether_counts[tid],
            )
        )
    duplicate_modules = {
        nid for nid, kinds in node_kinds.items() if len(kinds) > 1 and "module" in kinds
    }

    cassette_fields: List[Tuple[bool, Optional[List[str]], Optional[List[str]], bool]] = []
    for k, cas in enumerate(cfg.cassettes):
        cas_id_ok = _check_identifier(cas.id, f"cassettes[{k}].id", d)
        root_ok = _check_identifier(cas.root_anchor_id, f"cassettes[{k}].root_anchor_id", d)
        ordered_k = _check_identifier_list(
            cas.ordered_modules, f"cassettes[{k}].ordered_modules", d
        )
        segments_k = _check_identifier_list(
            cas.ordered_segments, f"cassettes[{k}].ordered_segments", d
        )
        cassette_fields.append((cas_id_ok, ordered_k, segments_k, root_ok))

    module_by_id = {m.id: m for m in modules}
    anchor_ids = {a.id for a in anchors}

    # Adjacency over well-formed graph tethers only.
    out_adj: Dict[str, List[str]] = {}
    in_adj: Dict[str, List[str]] = {}
    edge_id: Dict[Tuple[str, str], str] = {}
    for t in graph_tethers:
        out_adj.setdefault(t.from_node, []).append(t.to_node)
        in_adj.setdefault(t.to_node, []).append(t.from_node)
        edge_id[(t.from_node, t.to_node)] = t.id

    # C1 root multiplicity: depends only on anchors and tethers.
    roots = sorted(a for a in anchor_ids if out_adj.get(a))
    root: Optional[str] = None
    if len(roots) == 0:
        d.append(
            _err(
                Code.ROOT_ANCHOR_MISSING,
                "no surface anchor carries an outgoing tether edge",
                cassette=_safe(cfg.cassettes[0].id) if len(cfg.cassettes) == 1 else None,
            )
        )
    elif len(roots) > 1:
        d.append(
            _err(
                Code.MULTI_ANCHOR_IN_CASSETTE,
                "more than one surface anchor carries outgoing tether edges; "
                "LINEAR_ORDERED_CASSETTE permits exactly one root anchor",
                anchors=roots,
                required=1,
            )
        )
    else:
        root = roots[0]

    # C1a
    if len(cfg.cassettes) != 1:
        d.append(
            _err(
                Code.CASSETTE_COUNT_INVALID,
                "LINEAR_ORDERED_CASSETTE requires exactly one declared cassette",
                declared=len(cfg.cassettes),
                required=1,
            )
        )
        for check in _CASSETTE_DEPENDENT_CHECKS:
            d.append(_skipped(check, "cassette count is not 1"))
        return _topology_result(cfg, d)

    cas: CassetteSpec = cfg.cassettes[0]
    cas_id_ok, ordered, segments, root_id_ok = cassette_fields[0]
    ordered_ok = ordered is not None
    segments_ok = segments is not None
    if not ordered_ok:
        for check in _ORDERED_DEPENDENT_CHECKS:
            d.append(_skipped(check, "ordered_modules is malformed"))
    if not segments_ok:
        for check in _SEGMENT_DEPENDENT_CHECKS:
            if not (check == "segment cardinality" and not ordered_ok):
                d.append(_skipped(check, "ordered_segments is malformed"))
    n = len(ordered) if ordered_ok else 0

    # N >= 1 (decision D9)
    if ordered_ok and n == 0:
        d.append(
            _err(
                Code.CASSETTE_EMPTY,
                "ordered_modules is empty; N must be at least 1",
                cassette=_safe(cas.id),
            )
        )

    # C14: orphan / unknown modules
    if ordered_ok:
        declared_ids = set(module_by_id)
        ordered_set = set(ordered)
        for mid in sorted(declared_ids - ordered_set):
            d.append(
                _err(
                    Code.ORPHAN_MODULE,
                    "module is declared but is not a member of the cassette",
                    module=mid,
                    cassette=_safe(cas.id),
                )
            )
        for mid in sorted(ordered_set - declared_ids):
            d.append(
                _err(
                    Code.ORPHAN_MODULE,
                    "cassette lists a module that is not declared",
                    module=mid,
                    cassette=_safe(cas.id),
                )
            )

    # C11: index sequence 1..N without gaps or repeats, matching position
    index_ok = ordered_ok and n > 0
    if ordered_ok and n > 0:
        if len(set(ordered)) != n:
            d.append(
                _err(
                    Code.INDEX_SEQUENCE_INVALID,
                    "ordered_modules contains a repeated module id",
                    cassette=_safe(cas.id),
                )
            )
            index_ok = False
        if not cas_id_ok:
            d.append(_skipped("module cassette_id consistency", "cassette id is malformed"))
        for position, mid in enumerate(ordered, start=1):
            if mid in duplicate_modules:
                d.append(_skipped("C11", f"module identifier {mid} is not unique"))
                index_ok = False
                continue
            module = module_by_id.get(mid)
            if module is None:
                index_ok = False
                continue
            if not _is_index(module.cassette_index) or module.cassette_index != position:
                d.append(
                    _err(
                        Code.INDEX_SEQUENCE_INVALID,
                        "cassette_index does not match the position in ordered_modules",
                        module=mid,
                        declared_index=_safe(module.cassette_index),
                        expected_index=position,
                    )
                )
                index_ok = False
            if cas_id_ok and not (module.cassette_id is None or module.cassette_id == cas.id):
                d.append(
                    _err(
                        Code.ORPHAN_MODULE,
                        "module declares membership in a different cassette",
                        module=mid,
                        declared_cassette=_safe(module.cassette_id),
                        expected_cassette=cas.id,
                    )
                )

    # ---- Stage B: anchoring ---------------------------------------------
    if root is not None:
        if not root_id_ok:
            d.append(_skipped("C1 root_anchor_id match", "root_anchor_id is malformed"))
        elif cas.root_anchor_id != root:
            d.append(
                _err(
                    Code.ROOT_ANCHOR_MISMATCH,
                    "declared root_anchor_id is not the anchor that carries the "
                    "root tether edge",
                    declared=cas.root_anchor_id,
                    observed=root,
                )
            )

    # C12: no secondary surface anchor
    if ordered_ok:
        first_module = ordered[0] if n > 0 else None
        for t in graph_tethers:
            if t.from_node in anchor_ids and t.to_node != first_module:
                d.append(
                    _err(
                        Code.SECONDARY_SURFACE_ANCHOR,
                        "a surface anchor is tethered to a module other than Module_1",
                        tether=t.id,
                        anchor=t.from_node,
                        module=t.to_node,
                        module_1=first_module,
                    )
                )

    # ---- Stage C: degrees ------------------------------------------------
    if ordered_ok and n == 0:
        d.append(_skipped("C2/C3", "cassette is empty"))
    elif ordered_ok:
        for position, mid in enumerate(ordered, start=1):
            parents = in_adj.get(mid, [])
            children = out_adj.get(mid, [])

            # C2
            if len(parents) != 1:
                d.append(
                    _err(
                        Code.PARENT_COUNT_INVALID,
                        "module must have exactly one immediate upstream parent",
                        module=mid,
                        indeg=len(parents),
                        required=1,
                        parents=sorted(parents),
                    )
                )
            else:
                parent = parents[0]
                if position == 1:
                    if parent not in anchor_ids:
                        d.append(
                            _err(
                                Code.PARENT_COUNT_INVALID,
                                "Module_1 must be parented by the root surface anchor",
                                module=mid,
                                parent=parent,
                            )
                        )
                elif parent in anchor_ids:
                    d.append(
                        _err(
                            Code.PARENT_COUNT_INVALID,
                            "only Module_1 may be parented by a surface anchor",
                            module=mid,
                            parent=parent,
                            cassette_index=position,
                        )
                    )

            # C3
            if len(children) > 1:
                d.append(
                    _err(
                        Code.CHILD_COUNT_INVALID,
                        "module has more than one outgoing tether edge; a cassette "
                        "permits at most one immediate downstream child",
                        node=mid,
                        outdeg=len(children),
                        max_allowed=1,
                        children=sorted(children),
                    )
                )
            elif position < n and len(children) == 0:
                d.append(
                    _err(
                        Code.NOT_A_SINGLE_PATH,
                        "non-terminal module has no downstream child",
                        module=mid,
                        cassette_index=position,
                        terminal_index=n,
                    )
                )
            elif position == n and len(children) != 0:
                d.append(
                    _err(
                        Code.NOT_A_SINGLE_PATH,
                        "terminal module has an outgoing tether edge",
                        module=mid,
                        children=sorted(children),
                    )
                )

    # ---- Stage D: segments (no root prerequisite) --------------------------
    if segments_ok:
        # Every declared tether must be a cassette segment (B6).
        segment_ids = set(segments)
        for t in named_tethers:
            if t.id not in segment_ids:
                d.append(
                    _err(
                        Code.SEGMENT_SEQUENCE_INVALID,
                        "declared tether is not a segment of the cassette",
                        tether=t.id,
                        from_node=_safe(t.from_node),
                        to_node=_safe(t.to_node),
                    )
                )
        if ordered_ok and len(segments) != n:
            d.append(
                _err(
                    Code.SEGMENT_SEQUENCE_INVALID,
                    "ordered_segments must contain exactly N entries",
                    declared=len(segments),
                    required=n,
                )
            )
        tether_by_id = {t.id: t for t in named_tethers}
        for expected_index, sid in enumerate(segments):
            if sid in duplicate_tethers:
                d.append(_skipped("segment references", f"tether identifier {sid} is not unique"))
                continue
            t = tether_by_id.get(sid)
            if t is None:
                d.append(
                    _err(
                        Code.SEGMENT_SEQUENCE_INVALID,
                        "ordered_segments references an undeclared tether",
                        segment=sid,
                    )
                )
            elif _declared(t.cassette_index) and (
                not _is_index(t.cassette_index) or t.cassette_index != expected_index
            ):
                d.append(
                    _err(
                        Code.SEGMENT_SEQUENCE_INVALID,
                        "tether cassette_index does not match its position in "
                        "ordered_segments",
                        segment=sid,
                        declared_index=_safe(t.cassette_index),
                        expected_index=expected_index,
                    )
                )

    # ---- Stage D: connectivity (unique root) ----------------------------
    if root is None:
        d.append(_skipped("C4", "root anchor is not unique"))
        d.append(_skipped("C13", "root anchor is not unique"))
    elif ordered_ok:
        walk: List[str] = [root]
        seen: Set[str] = {root}
        node = root
        while True:
            children = out_adj.get(node, [])
            if len(children) != 1:
                break
            nxt = children[0]
            if nxt in seen:
                d.append(
                    _err(
                        Code.NOT_A_SINGLE_PATH,
                        "tether edges form a cycle",
                        at=node,
                        revisits=nxt,
                    )
                )
                break
            seen.add(nxt)
            walk.append(nxt)
            node = nxt

        walked_modules = [x for x in walk if x != root]
        if walked_modules != ordered:
            d.append(
                _err(
                    Code.NOT_A_SINGLE_PATH,
                    "the tether walk from the root anchor does not traverse exactly "
                    "ordered_modules in order",
                    walked=walked_modules,
                    ordered_modules=ordered,
                )
            )
        elif segments_ok and len(segments) == n:
            walk_edges = [edge_id.get((walk[i], walk[i + 1])) for i in range(len(walk) - 1)]
            if walk_edges != segments:
                d.append(
                    _err(
                        Code.SEGMENT_SEQUENCE_INVALID,
                        "ordered_segments does not match the tether edges of the walk",
                        walk_edges=walk_edges,
                        ordered_segments=segments,
                    )
                )

        # C13: uniqueness of the root-to-module walk
        for mid in ordered:
            if _count_walks(out_adj, root, mid) > 1:
                d.append(
                    _err(
                        Code.MULTIPATH_CONNECTIVITY,
                        "module is reachable from the root by more than one tether walk",
                        module=mid,
                        root=root,
                    )
                )

    # ---- Stage E: offsets -------------------------------------------------
    if not index_ok:
        if ordered_ok:
            d.append(_skipped("C10a", "index sequence is invalid; terminal module unknown"))
            d.append(_skipped("C10b", "index sequence is invalid; terminal module unknown"))
    else:
        for position, mid in enumerate(ordered, start=1):
            module = module_by_id[mid]
            is_terminal = position == n
            # C10a: exit_offset declared-null iff terminal
            if not _declared(module.exit_offset):
                d.append(
                    _err(
                        Code.EXIT_OFFSET_MALFORMED,
                        "exit_offset must be declared; explicit null marks the "
                        "terminal module and MISSING is not a substitute",
                        module=mid,
                        declared=False,
                        is_terminal=is_terminal,
                    )
                )
            else:
                declared_null = module.exit_offset is None
                if declared_null != is_terminal:
                    d.append(
                        _err(
                            Code.EXIT_OFFSET_MALFORMED,
                            "exit_offset must be null for the terminal module and "
                            "non-null for every other module",
                            module=mid,
                            cassette_index=position,
                            terminal_index=n,
                            exit_offset_is_null=declared_null,
                        )
                    )
            # C10b: terminal exclusion centre must be declared explicitly (D7)
            if is_terminal and (
                not _declared(module.exclusion_centre) or module.exclusion_centre is None
            ):
                d.append(
                    DiagnosticRecord(
                        code=Code.TERMINAL_EXCLUSION_CENTRE_MISSING,
                        severity=Severity.ERROR,
                        message=(
                            "exclusion_centre must be declared explicitly for the "
                            "terminal module; midpoint defaulting is undefined because "
                            "exit_offset is null"
                        ),
                        quantities={"module": mid, "cassette_index": position},
                        remediation="declare exclusion_centre for the terminal module",
                    )
                )

    return _topology_result(cfg, d)


def _topology_result(
    cfg: CassetteConfig, diagnostics: Sequence[DiagnosticRecord]
) -> EvaluationResult:
    errors = [x for x in diagnostics if x.severity is Severity.ERROR]
    out = list(diagnostics)
    if any(x.code in _C9_TRIGGER_CODES for x in errors):
        out.append(
            _info(
                Code.BRANCHING_OR_PARALLEL_TOPOLOGY,
                "C9 summary: the declared tether graph is not a single anchored path",
                constituent_codes=sorted({x.code for x in errors if x.code in _C9_TRIGGER_CODES}),
            )
        )
    status = Status.INFEASIBLE if errors else Status.VALID
    reason = Reason.TOPOLOGY if errors else Reason.OK
    return _result(cfg, status, reason, out, "validate_cassette_topology")


# --------------------------------------------------------------------------
# P2 -- engagement-order constraint satisfiability (decision D8)
# --------------------------------------------------------------------------
_P2_CHECKS = ("P2 order constraints",)


def _find_cycle(
    nodes: Sequence[str], edges: Mapping[str, Sequence[str]]
) -> Optional[List[str]]:
    """Return one directed cycle as a node list, or None. Deterministic:
    nodes and successors are visited in the order supplied."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour: Dict[str, int] = {node: WHITE for node in nodes}
    parent: Dict[str, Optional[str]] = {node: None for node in nodes}

    for start in nodes:
        if colour[start] != WHITE:
            continue
        stack: List[Tuple[str, int]] = [(start, 0)]
        colour[start] = GREY
        while stack:
            node, idx = stack[-1]
            succs = list(edges.get(node, ()))
            if idx >= len(succs):
                colour[node] = BLACK
                stack.pop()
                continue
            stack[-1] = (node, idx + 1)
            nxt = succs[idx]
            if nxt not in colour:
                continue
            if colour[nxt] == GREY:
                cycle = [nxt]
                cur: Optional[str] = node
                while cur is not None and cur != nxt:
                    cycle.append(cur)
                    cur = parent[cur]
                cycle.append(nxt)
                cycle.reverse()
                return cycle
            if colour[nxt] == WHITE:
                colour[nxt] = GREY
                parent[nxt] = node
                stack.append((nxt, 0))
    return None


def validate_cassette_order_constraints(cfg: CassetteConfig) -> EvaluationResult:
    """Stage P2, decision D8. REQUIRES edges act as ADDITIONAL constraints
    intersected with engagement_order_policy. A cycle in the union relation
    means the intersection admits no order and the config is unsatisfiable.

    This stage never uses status_reason TOPOLOGY_NOT_LINEAR_ORDERED_CASSETTE:
    connectivity and order are different failures (audit item L21).

    Standalone prerequisites (in the composed flow P0/P1 already guarantee
    them): exactly one cassette; ordered_modules a list of unique well-formed
    identifiers; a valid engagement_order_policy; and, under
    EXPLICIT_PARTIAL_ORDER, an explicit order satisfying §20.6.1. The raw
    explicit order is only ever read through _normalize_explicit_order. A
    check this stage owns but cannot run makes it NOT_EVALUATED, never VALID."""
    _require_schema(cfg)
    method = "validate_cassette_order_constraints"
    gate = _mode_gate(cfg, method, _P2_CHECKS)
    if gate is not None:
        return gate

    d: List[DiagnosticRecord] = []
    if len(cfg.cassettes) != 1:
        d.append(_skipped("order constraints", "cassette count is not 1"))
        return _result(cfg, Status.NOT_EVALUATED, Reason.PREREQUISITE_FAILED, d, method)

    cas = cfg.cassettes[0]
    ordered_raw = cas.ordered_modules
    if (
        not _seq_ok(ordered_raw)
        or not all(_ident_ok(m) for m in ordered_raw)
        or len(set(ordered_raw)) != len(ordered_raw)
    ):
        d.append(_skipped("order constraints", "ordered_modules is malformed"))
        return _result(cfg, Status.NOT_EVALUATED, Reason.PREREQUISITE_FAILED, d, method)
    policy = cfg.policy.engagement_order_policy
    if not isinstance(policy, EngagementOrderPolicy):
        d.append(_skipped("order constraints", "engagement_order_policy is invalid"))
        return _result(cfg, Status.NOT_EVALUATED, Reason.PREREQUISITE_FAILED, d, method)

    ordered = list(ordered_raw)
    position_of = {mid: i + 1 for i, mid in enumerate(ordered)}

    requires, edge_diagnostics = _requires_edges(cfg, position_of)
    d.extend(edge_diagnostics)

    has_error = any(x.severity is Severity.ERROR for x in d)
    owned_check_skipped = False

    # Cycles within REQUIRES alone.
    req_adj: Dict[str, List[str]] = {}
    for a, b in requires:
        req_adj.setdefault(a, []).append(b)
    cycle = _find_cycle(ordered, req_adj)
    if cycle is not None:
        d.append(
            _err(
                Code.REQUIRES_CYCLE_IN_CASSETTE,
                "REQUIRES edges form a directed cycle; no engagement order satisfies them",
                cycle=cycle,
            )
        )
        has_error = True

    if policy is EngagementOrderPolicy.STRICT_PROXIMAL_TO_DISTAL:
        for a, b in requires:
            if position_of[a] > position_of[b]:
                d.append(
                    _err(
                        Code.ENGAGEMENT_ORDER_CONFLICT,
                        "REQUIRES edge contradicts STRICT_PROXIMAL_TO_DISTAL",
                        requires_edge=[a, b],
                        policy_path=[b, a],
                        indices=[position_of[a], position_of[b]],
                    )
                )
                has_error = True
            else:
                d.append(
                    _info(
                        Code.REDUNDANT_REQUIRES_EDGE,
                        "REQUIRES edge is already implied by the policy order",
                        requires_edge=[a, b],
                    )
                )
    elif policy is EngagementOrderPolicy.EXPLICIT_PARTIAL_ORDER:
        pairs: Optional[Tuple[Tuple[str, str], ...]] = None
        if _declared(cas.explicit_partial_order):
            pairs, _ = _normalize_explicit_order(cas, frozenset(ordered))
        if pairs is None:
            d.append(
                _skipped(
                    "union cycle check",
                    "explicit_partial_order is missing or violates §20.6.1",
                )
            )
            owned_check_skipped = True
        else:
            union_adj: Dict[str, List[str]] = {k: list(v) for k, v in req_adj.items()}
            for a, b in pairs:
                union_adj.setdefault(a, []).append(b)
            union_cycle = _find_cycle(ordered, union_adj)
            if union_cycle is not None and cycle is None:
                d.append(
                    _err(
                        Code.ENGAGEMENT_ORDER_CONFLICT,
                        "the union of REQUIRES edges and the explicit partial order "
                        "contains a directed cycle",
                        cycle=union_cycle,
                    )
                )
                has_error = True
    # ANY_ORDER contributes no policy edges; only REQUIRES cycles can conflict.

    if has_error:
        return _result(cfg, Status.INFEASIBLE, Reason.ORDER, d, method)
    if owned_check_skipped:
        return _result(cfg, Status.NOT_EVALUATED, Reason.PREREQUISITE_FAILED, d, method)
    return _result(cfg, Status.VALID, Reason.OK, d, method)


def _requires_edges(
    cfg: CassetteConfig, position_of: Mapping[str, int]
) -> Tuple[List[Tuple[str, str]], List[DiagnosticRecord]]:
    """The well-formed REQUIRES edges between cassette modules, as
    (from_node, to_node): from_node precedes to_node (D-record T70), plus a
    diagnostic for every malformed or out-of-cassette edge. Shared by P2 and by
    the Phase 2 state-time R_union (decision record F)."""
    d: List[DiagnosticRecord] = []
    # N-2: malformed dependency edges are reported, never silently dropped.
    requires: List[Tuple[str, str]] = []
    for index, e in enumerate(cfg.dep_edges):
        malformed = False
        if not isinstance(e.kind, DepEdgeKind):
            d.append(
                _err(
                    Code.DEP_EDGE_MALFORMED,
                    "dependency edge kind must be a DepEdgeKind member",
                    edge_index=index,
                    field="kind",
                    found_type=_type_name(e.kind),
                )
            )
            malformed = True
        for field_name in ("from_node", "to_node"):
            endpoint = getattr(e, field_name)
            if not _ident_ok(endpoint):
                d.append(
                    _err(
                        Code.DEP_EDGE_MALFORMED,
                        "dependency edge endpoint must be a non-empty plain str",
                        edge_index=index,
                        field=field_name,
                        found_type=_type_name(endpoint),
                    )
                )
                malformed = True
        if malformed or e.kind is not DepEdgeKind.REQUIRES:
            continue
        if e.from_node not in position_of or e.to_node not in position_of:
            d.append(
                _err(
                    Code.DEP_EDGE_UNKNOWN_NODE,
                    "REQUIRES edge references a node outside the cassette",
                    from_node=e.from_node,
                    to_node=e.to_node,
                )
            )
            continue
        requires.append((e.from_node, e.to_node))

    return requires, d


def _union_order_edges(cfg: CassetteConfig) -> Tuple[Tuple[str, str], ...]:
    """Phase 2 decision record F: R_union = R_policy ∪ R_requires with the edge
    semantics of validate_cassette_order_constraints, (a, b) meaning a
    precedes b. STRICT_PROXIMAL_TO_DISTAL orders every proximal module before
    every distal one, which is why P2 calls any forward REQUIRES edge implied;
    ANY_ORDER adds no edges; EXPLICIT_PARTIAL_ORDER adds the normalized
    explicit pairs. Requires a cfg that validate_cassette_config finds VALID.
    Edges come out in cassette order."""
    cas = cfg.cassettes[0]
    ordered = list(cas.ordered_modules)
    position_of = {mid: i + 1 for i, mid in enumerate(ordered)}
    edges = set(_requires_edges(cfg, position_of)[0])
    policy = cfg.policy.engagement_order_policy
    if policy is EngagementOrderPolicy.STRICT_PROXIMAL_TO_DISTAL:
        edges.update((a, b) for i, a in enumerate(ordered) for b in ordered[i + 1 :])
    elif policy is EngagementOrderPolicy.EXPLICIT_PARTIAL_ORDER:
        pairs, _ = _normalize_explicit_order(cas, frozenset(ordered))
        edges.update(pairs or ())
    return tuple(sorted(edges, key=lambda e: (position_of[e[0]], position_of[e[1]])))


# --------------------------------------------------------------------------
# P3 -- identity admissibility (v0.3.1 §17.7)
# --------------------------------------------------------------------------
_P3_CHECKS = ("P3 identity admissibility",)


def validate_cassette_identity_admissibility(cfg: CassetteConfig) -> EvaluationResult:
    """Stage P3. The configuration must be canonicalizable by
    config_identity_hash. Uses the SAME canonicalizer (identity._canon via
    noncanonical_values); there is no parallel type whitelist."""
    _require_schema(cfg)
    method = "validate_cassette_identity_admissibility"
    gate = _mode_gate(cfg, method, _P3_CHECKS)
    if gate is not None:
        return gate
    d = [
        _err(
            Code.NON_CANONICAL_VALUE,
            "declared value has no canonical identity form",
            path=path,
            found_type=type_name,
        )
        for path, type_name in noncanonical_values(cfg)
    ]
    if d:
        return _result(cfg, Status.INFEASIBLE, Reason.NOT_CANONICALIZABLE, d, method)
    return _result(cfg, Status.VALID, Reason.OK, d, method)


# --------------------------------------------------------------------------
# Composition (v0.3.1 §17.8)
# --------------------------------------------------------------------------
_STAGES: Tuple[Tuple[str, str], ...] = (
    ("P0 policy fields", "validate_cassette_policy_fields"),
    ("P1 topology", "validate_cassette_topology"),
    ("P2 order constraints", "validate_cassette_order_constraints"),
    ("P3 identity admissibility", "validate_cassette_identity_admissibility"),
)


def _compose(
    cfg: CassetteConfig,
    executed: Sequence[EvaluationResult],
    diagnostics: Sequence[DiagnosticRecord],
) -> EvaluationResult:
    """THE composition rule, used by every composed return path: VALID iff
    every executed stage is VALID; otherwise the §3.3 precedence minimum over
    the non-VALID stage statuses, with the reason of the first such stage."""
    failing = [r for r in executed if r.status is not Status.VALID]
    if not failing:
        return _result(cfg, Status.VALID, Reason.OK, diagnostics, "validate_cassette_config")
    status = precedence(*(r.status for r in failing))
    return _result(cfg, status, failing[0].status_reason, diagnostics, "validate_cassette_config")


def validate_cassette_config(cfg: CassetteConfig) -> EvaluationResult:
    """Run the gate and P0, P1, P2, P3 in the locked order. Runs before WF1-WF7.

    A stage runs only if every earlier stage returned VALID; each stage not
    run is recorded as CHECK_SKIPPED. A composed VALID implies that
    config_identity_hash(cfg) succeeds."""
    _require_schema(cfg)
    gate = _mode_gate(cfg, "validate_cassette_config", tuple(name for name, _ in _STAGES))
    if gate is not None:
        return gate

    # Stages are resolved through module globals at call time, so the
    # composition rule is exercised identically when a stage is replaced.
    module_globals = globals()
    diagnostics: List[DiagnosticRecord] = []
    executed: List[EvaluationResult] = []
    for index, (_, function_name) in enumerate(_STAGES):
        if executed and executed[-1].status is not Status.VALID:
            for skipped_name, _ in _STAGES[index:]:
                diagnostics.append(_skipped(skipped_name, f"{_STAGES[index - 1][0]} is not VALID"))
            break
        result = module_globals[function_name](cfg)
        executed.append(result)
        diagnostics.extend(result.diagnostics)
    return _compose(cfg, executed, diagnostics)
