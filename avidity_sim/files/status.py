"""GOTNE status taxonomy, diagnostics, and the single §10.1 field-pattern implementation.

Phase 1c scope, extended by the Phase 2 result builder, payload rule and
freezing (decision record C, D, J). This module is PURE: it performs no
geometry, no probability, and no numerical computation. It imports only the
standard library and nothing from GOTNE's evaluation layers.

Specification references:
  §3.1   Status enum
  §3.3   Precedence
  §3.6   Mandatory zeroing rule
  §6.3   Provenance labels
  §10.1  Field pattern by status
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

__all__ = [
    "Status",
    "Severity",
    "Exactness",
    "Provenance",
    "VETO_SET",
    "UNKNOWN_SET",
    "STATUS_RANK",
    "precedence",
    "DiagnosticRecord",
    "ProvenanceRecord",
    "EvaluationResult",
    "apply_status_field_pattern",
    "OBJECT_KINDS",
    "make_result",
    "METHOD_VERSION",
    "PROBABILITY_LIKE_FIELDS",
    "MEASURE_LIKE_FIELDS",
    "DENSITY_LIKE_FIELDS",
    "CANONICAL_VALUE_FIELDS",
]


class Status(str, Enum):
    """§3.1. Ordered by rank in STATUS_RANK, not by declaration order."""

    NUMERIC_FAILURE = "NUMERIC_FAILURE"
    INFEASIBLE = "INFEASIBLE"
    DEGENERATE = "DEGENERATE"
    UNREACHABLE = "UNREACHABLE"
    BLOCKED = "BLOCKED"
    APPROXIMATION_REQUIRED = "APPROXIMATION_REQUIRED"
    VALID = "VALID"
    NOT_EVALUATED = "NOT_EVALUATED"


class Severity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class Exactness(str, Enum):
    EXACT = "EXACT"
    APPROXIMATE = "APPROXIMATE"
    BOUND = "BOUND"
    UNDEFINED = "UNDEFINED"


class Provenance(str, Enum):
    """§6.3."""

    EXACT_CLOSED_FORM = "EXACT_CLOSED_FORM"
    EXACT_GEOMETRIC_VETO = "EXACT_GEOMETRIC_VETO"
    #: v0.3.1 §6.3: veto decided from declarations/graph structure only.
    #: Every Phase 1c veto carries this label; GEOMETRIC is reserved for
    #: vetoes derived from a geometric evaluation (Phase 2+).
    EXACT_STRUCTURAL_VETO = "EXACT_STRUCTURAL_VETO"
    ANALYTIC_APPROXIMATION = "ANALYTIC_APPROXIMATION"
    NUMERICAL_QUADRATURE = "NUMERICAL_QUADRATURE"
    CACHED_INTERPOLATION = "CACHED_INTERPOLATION"
    EXTERNAL_SAMPLED = "EXTERNAL_SAMPLED"
    BOUND_ONLY = "BOUND_ONLY"
    UNDERFLOW_CLAMPED = "UNDERFLOW_CLAMPED"
    NOT_COMPUTED = "NOT_COMPUTED"


# §3.6
VETO_SET = frozenset({Status.INFEASIBLE, Status.UNREACHABLE, Status.BLOCKED})
UNKNOWN_SET = frozenset(
    {Status.DEGENERATE, Status.NUMERIC_FAILURE, Status.NOT_EVALUATED}
)

# §3.3 lower rank wins
STATUS_RANK: Mapping[Status, int] = {
    Status.NUMERIC_FAILURE: 1,
    Status.INFEASIBLE: 2,
    Status.DEGENERATE: 3,
    Status.UNREACHABLE: 4,
    Status.BLOCKED: 5,
    Status.APPROXIMATION_REQUIRED: 6,
    Status.VALID: 7,
    Status.NOT_EVALUATED: 8,
}


def precedence(*statuses: Status) -> Status:
    """§3.3. Returns the lowest-rank status. Raises on an empty argument list
    rather than inventing a default."""
    if not statuses:
        raise ValueError("precedence() requires at least one status")
    return min(statuses, key=lambda s: STATUS_RANK[s])


# §10.1 field classes
PROBABILITY_LIKE_FIELDS = frozenset(
    {"conditional_probability", "survival_correction", "joint_score"}
)
MEASURE_LIKE_FIELDS = frozenset({"capture_integral"})
DENSITY_LIKE_FIELDS = frozenset(
    {"effective_local_concentration", "conditional_density"}
)

CANONICAL_VALUE_FIELDS: Tuple[str, ...] = (
    "conditional_probability",
    "effective_local_concentration",
    "capture_integral",
    "survival_correction",
    "joint_score",
)

#: Every field name the §10.1 pattern knows how to treat under every status.
_KNOWN_VALUE_FIELDS = frozenset(
    set(CANONICAL_VALUE_FIELDS)
    | PROBABILITY_LIKE_FIELDS
    | MEASURE_LIKE_FIELDS
    | DENSITY_LIKE_FIELDS
)

CANONICAL_UNITS: Mapping[str, str] = {
    "conditional_probability": "1",
    "effective_local_concentration": "M",
    "conditional_density": "nm^-3",
    "capture_integral": "1",
    "survival_correction": "1",
    "joint_score": "1",
}


#: v0.3.1 §17.4.1: method_version carried by every config-level result.
METHOD_VERSION = "0.3.1"

#: Phase 2 decision record C (AP-4): the closed set of object kinds.
OBJECT_KINDS: Tuple[str, ...] = ("CONFIG", "STATE", "NODE")

#: Decision record D (AP-5): veto labels appear on veto statuses only.
_VETO_LABELS = frozenset({Provenance.EXACT_STRUCTURAL_VETO, Provenance.EXACT_GEOMETRIC_VETO})
#: Decision record D: never carried by a Phase 2 (STATE / NODE) result.
_PHASE2_EXCLUDED_EXACTNESS = frozenset({Exactness.BOUND, Exactness.APPROXIMATE})
_PHASE2_EXCLUDED_PROVENANCE = frozenset({Provenance.BOUND_ONLY, Provenance.ANALYTIC_APPROXIMATION})
#: Decision record G / J: the conditioning snapshot and the tolerance record.
_UPSTREAM_STATE_KEYS = frozenset({"state_hash", "context_hash", "assignments"})
_TOLERANCE_KEYS = frozenset({"eps_len_nm", "eps_rotation"})

_INF = float("inf")


def _read_only(mapping: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    return MappingProxyType(dict(mapping or {}))


def _finite_float(value: object) -> bool:
    return type(value) is float and value == value and value not in (_INF, -_INF)


def _deep_freeze(value: Any, path: str) -> Any:
    """AP-11: a detached copy with read-only mappings and tuples. Leaves must
    be str, int, bool, None or finite float; anything else raises TypeError."""
    if isinstance(value, Mapping):
        frozen: Dict[str, Any] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError(f"{path}: mapping keys must be plain str")
            frozen[key] = _deep_freeze(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item, f"{path}[{i}]") for i, item in enumerate(value))
    if value is None or type(value) in (str, int, bool) or _finite_float(value):
        return value
    raise TypeError(f"{path}: {type(value).__qualname__} is not a finite JSON leaf")


def _thaw(value: Any) -> Any:
    """Plain JSON types for as_dict(): dicts and lists, fresh on every call."""
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


class _FrozenJSONDict(dict):
    """Read-only dict. It serializes as a JSON object, which MappingProxyType
    does not, so nested Phase 2 diagnostic quantities stay frozen and
    JSON-safe while DiagnosticRecord itself is unchanged."""

    __slots__ = ()

    def _refuse(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("read-only mapping")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = _refuse

    def __ior__(self, other: Any) -> "_FrozenJSONDict":
        raise TypeError("read-only mapping")


def _freeze_json(value: Any) -> Any:
    """Decision record J: a frozen, JSON-safe diagnostic quantity value."""
    if isinstance(value, Mapping):
        return _FrozenJSONDict((key, _freeze_json(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if isinstance(value, Enum):
        return value.value
    if value is None or type(value) in (str, int, bool) or _finite_float(value):
        return value
    raise TypeError(f"{type(value).__qualname__} is not a finite JSON leaf")


@dataclass(frozen=True)
class DiagnosticRecord:
    code: str
    severity: Severity
    message: str
    quantities: Mapping[str, Any] = field(default_factory=dict)
    remediation: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantities", _read_only(self.quantities))

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "quantities": dict(self.quantities),
            "remediation": self.remediation,
        }


@dataclass(frozen=True)
class ProvenanceRecord:
    worst_label: Provenance
    contributing_labels: Sequence[Provenance] = ()
    method_id: Optional[str] = None
    method_version: Optional[str] = None
    declared_assumptions: Sequence[str] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "worst_label": self.worst_label.value,
            "contributing_labels": [p.value for p in self.contributing_labels],
            "method_id": self.method_id,
            "method_version": self.method_version,
            "declared_assumptions": list(self.declared_assumptions),
        }


def apply_status_field_pattern(
    status: Status, values: Optional[Mapping[str, Optional[float]]] = None
) -> Tuple[Dict[str, Optional[float]], bool, bool]:
    """§10.1 / §3.6. THE single implementation of the field pattern.

    Every result construction site in GOTNE routes through this function
    (audit item C1). Returns (values, zeroed_due_to_status, nulled_due_to_status).

    Veto statuses   -> probability-like and measure-like fields are exactly 0.0,
                       density-like fields are typed null.
    Unknown statuses-> every field is typed null.
    Otherwise       -> the supplied values pass through unchanged.
    """
    if not isinstance(status, Status):
        # A str-Enum member compares equal to its text, so a plain string would
        # otherwise select a branch by accident, and garbage would pass through.
        raise TypeError(f"status must be a Status member, got {type(status).__qualname__}")
    supplied: Dict[str, Optional[float]] = dict(values or {})
    unknown = sorted(set(supplied) - _KNOWN_VALUE_FIELDS)
    if unknown:
        # Fail closed: an unclassified field would bypass zeroing/nulling.
        raise ValueError(f"fields not classified by §10.1: {unknown}")

    if status in VETO_SET:
        out: Dict[str, Optional[float]] = {}
        for name in CANONICAL_VALUE_FIELDS:
            if name in DENSITY_LIKE_FIELDS:
                out[name] = None
            else:
                out[name] = 0.0
        for name in supplied:
            out[name] = None if name in DENSITY_LIKE_FIELDS else 0.0
        return out, True, False

    if status in UNKNOWN_SET:
        out = {name: None for name in CANONICAL_VALUE_FIELDS}
        for name in supplied:
            out[name] = None
        return out, False, True

    out = {name: None for name in CANONICAL_VALUE_FIELDS}
    out.update(supplied)
    return out, False, False


@dataclass(frozen=True)
class EvaluationResult:
    """§9.1 / §10. object_kind is CONFIG (Phase 1c) or STATE / NODE (Phase 2)."""

    object_kind: str
    object_id: str
    status: Status
    status_reason: str
    exact_or_approximate: Exactness
    provenance: ProvenanceRecord
    values: Mapping[str, Optional[float]]
    value_intervals: Mapping[str, Optional[Sequence[float]]]
    units: Mapping[str, str]
    zeroed_due_to_status: bool
    nulled_due_to_status: bool
    diagnostics: Sequence[DiagnosticRecord]
    upstream_state: Optional[Mapping[str, Any]]
    numerical_tolerance_used: Optional[Mapping[str, Any]]
    result_id: Optional[str] = None
    supersedes: Optional[str] = None

    def __post_init__(self) -> None:
        """Construction-time enforcement of §10.1 / §3.6 / §10.8 (v0.3.1) and of
        the Phase 2 decision record C, D, J (AP-4, AP-5, AP-11).

        Runs for direct construction AND for dataclasses.replace(), which
        re-invokes __init__. A result whose payload or flags disagree with its
        status cannot exist. The three mappings are stored read-only; a STATE or
        NODE result's upstream_state and numerical_tolerance_used are deep-copied
        and deep-frozen, and as_dict() returns them as plain JSON types."""
        if not isinstance(self.status, Status):
            raise TypeError("status must be a Status member")
        if not isinstance(self.exact_or_approximate, Exactness):
            raise TypeError("exact_or_approximate must be an Exactness member")
        if not isinstance(self.provenance, ProvenanceRecord):
            raise TypeError("provenance must be a ProvenanceRecord")
        for name in ("object_kind", "object_id", "status_reason"):
            if type(getattr(self, name)) is not str:
                raise TypeError(f"{name} must be a plain str")

        values = dict(self.values)
        intervals = dict(self.value_intervals)
        units = dict(self.units)
        for label, mapping in (("values", values), ("value_intervals", intervals), ("units", units)):
            unknown = sorted(set(mapping) - _KNOWN_VALUE_FIELDS)
            if unknown:
                raise ValueError(f"{label} contains fields not classified by §10.1: {unknown}")

        for k, v in values.items():
            if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
                raise TypeError(f"value field {k} must be a real number or None")
        expected, zeroed, nulled = apply_status_field_pattern(self.status, values)
        if values.keys() != expected.keys() or any(
            (values[k] is None) != (expected[k] is None) or values[k] != expected[k]
            for k in expected
        ):
            raise ValueError(
                f"values violate the §10.1 field pattern for status {self.status.value}"
            )
        if (self.zeroed_due_to_status, self.nulled_due_to_status) != (zeroed, nulled):
            raise ValueError(
                f"zeroed/nulled flags violate the §10.1 field pattern for status "
                f"{self.status.value}"
            )
        if self.status in VETO_SET or self.status in UNKNOWN_SET:
            populated = sorted(k for k, v in intervals.items() if v is not None)
            if populated:
                raise ValueError(
                    f"status {self.status.value} forbids populated value_intervals: {populated}"
                )
        if self.object_kind not in OBJECT_KINDS:
            raise ValueError(f"object_kind must be one of {OBJECT_KINDS}, got {self.object_kind!r}")
        # §10.8 generalized by AP-5: a result without payload is UNDEFINED.
        payload = any(v is not None for v in values.values()) or any(
            v is not None for v in intervals.values()
        )
        if not payload and self.exact_or_approximate is not Exactness.UNDEFINED:
            raise ValueError(
                "§10.8: a result with no numeric payload must be UNDEFINED, got "
                f"{self.exact_or_approximate.value}"
            )
        labels = {self.provenance.worst_label, *self.provenance.contributing_labels}
        if self.status in VETO_SET:
            if (
                self.exact_or_approximate is Exactness.EXACT
                and self.provenance.worst_label not in _VETO_LABELS
            ):
                raise ValueError("an EXACT veto must carry an EXACT_*_VETO provenance label")
        elif labels & _VETO_LABELS:
            raise ValueError(
                f"veto provenance labels require a veto status, got {self.status.value}"
            )

        upstream_state = self.upstream_state
        tolerances = self.numerical_tolerance_used
        if self.object_kind == "CONFIG":
            if upstream_state is not None or tolerances is not None or self.result_id is not None:
                raise ValueError(
                    "a CONFIG result has no upstream_state, numerical_tolerance_used or result_id"
                )
        else:
            if upstream_state is None or tolerances is None or self.result_id is None:
                raise ValueError(
                    f"a {self.object_kind} result needs upstream_state, "
                    "numerical_tolerance_used and result_id"
                )
            if type(self.result_id) is not str:
                raise TypeError("result_id must be a plain str")
            if self.exact_or_approximate in _PHASE2_EXCLUDED_EXACTNESS or (
                labels & _PHASE2_EXCLUDED_PROVENANCE
            ):
                raise ValueError(
                    "Phase 2 results never carry BOUND/APPROXIMATE exactness or provenance"
                )
            upstream_state = _deep_freeze(upstream_state, "upstream_state")
            if (
                not isinstance(upstream_state, Mapping)
                or set(upstream_state) != _UPSTREAM_STATE_KEYS
            ):
                raise ValueError(f"upstream_state must hold exactly {sorted(_UPSTREAM_STATE_KEYS)}")
            tolerances = _deep_freeze(tolerances, "numerical_tolerance_used")
            if (
                not isinstance(tolerances, Mapping)
                or set(tolerances) != _TOLERANCE_KEYS
                or not all(_finite_float(v) for v in tolerances.values())
            ):
                raise ValueError(
                    f"numerical_tolerance_used must map exactly {sorted(_TOLERANCE_KEYS)} to floats"
                )

        object.__setattr__(self, "upstream_state", upstream_state)
        object.__setattr__(self, "numerical_tolerance_used", tolerances)
        object.__setattr__(self, "values", _read_only(values))
        object.__setattr__(self, "value_intervals", _read_only(intervals))
        object.__setattr__(self, "units", _read_only(units))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def codes(self) -> List[str]:
        """Diagnostic codes present, in emission order. Tests assert membership,
        never exclusivity (see the Phase 1c complete-diagnosis policy)."""
        return [d.code for d in self.diagnostics]

    def error_codes(self) -> List[str]:
        return [d.code for d in self.diagnostics if d.severity is Severity.ERROR]

    def has_code(self, code: str) -> bool:
        return code in self.codes()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "object_kind": self.object_kind,
            "object_id": self.object_id,
            "status": self.status.value,
            "status_reason": self.status_reason,
            "exact_or_approximate": self.exact_or_approximate.value,
            "provenance": self.provenance.as_dict(),
            "values": dict(self.values),
            "value_intervals": dict(self.value_intervals),
            "units": dict(self.units),
            "zeroed_due_to_status": self.zeroed_due_to_status,
            "nulled_due_to_status": self.nulled_due_to_status,
            "diagnostics": [d.as_dict() for d in self.diagnostics],
            "upstream_state": _thaw(self.upstream_state),
            "numerical_tolerance_used": _thaw(self.numerical_tolerance_used),
            "result_id": self.result_id,
            "supersedes": self.supersedes,
        }


def _make(
    object_kind: str,
    object_id: str,
    status: Status,
    status_reason: str,
    diagnostics: Sequence[DiagnosticRecord],
    *,
    method_id: str,
    veto_provenance: Optional[Provenance],
    declared_assumptions: Sequence[str],
    method_version: str,
    upstream_state: Optional[Mapping[str, Any]],
    numerical_tolerance_used: Optional[Mapping[str, Any]],
    result_id: Optional[str],
    allow_approximation_required: bool,
) -> EvaluationResult:
    values, zeroed, nulled = apply_status_field_pattern(status, None)
    if status is Status.APPROXIMATION_REQUIRED and not allow_approximation_required:
        raise ValueError("make_result never builds APPROXIMATION_REQUIRED")
    if status in VETO_SET:
        if not isinstance(veto_provenance, Provenance) or veto_provenance not in _VETO_LABELS:
            raise ValueError(
                "a veto result needs veto_provenance EXACT_STRUCTURAL_VETO or EXACT_GEOMETRIC_VETO"
            )
        provenance_label, exactness = veto_provenance, Exactness.EXACT
    else:
        if veto_provenance is not None:
            raise ValueError(f"status {status.value} takes no veto_provenance")
        provenance_label, exactness = Provenance.NOT_COMPUTED, Exactness.UNDEFINED
    return EvaluationResult(
        object_kind=object_kind,
        object_id=object_id,
        status=status,
        status_reason=status_reason,
        exact_or_approximate=exactness,
        provenance=ProvenanceRecord(
            worst_label=provenance_label,
            contributing_labels=(provenance_label,),
            method_id=method_id,
            method_version=method_version,
            declared_assumptions=tuple(declared_assumptions),
        ),
        values=values,
        value_intervals={},
        units={k: CANONICAL_UNITS[k] for k in values if k in CANONICAL_UNITS},
        zeroed_due_to_status=zeroed,
        nulled_due_to_status=nulled,
        diagnostics=tuple(diagnostics),
        upstream_state=upstream_state,
        numerical_tolerance_used=numerical_tolerance_used,
        result_id=result_id,
    )


def make_result(
    object_kind: str,
    object_id: str,
    status: Status,
    status_reason: str,
    diagnostics: Sequence[DiagnosticRecord],
    *,
    method_id: str,
    veto_provenance: Optional[Provenance] = None,
    declared_assumptions: Sequence[str] = (),
    method_version: str = METHOD_VERSION,
    upstream_state: Optional[Mapping[str, Any]] = None,
    numerical_tolerance_used: Optional[Mapping[str, Any]] = None,
    result_id: Optional[str] = None,
) -> EvaluationResult:
    """Decision record C (AP-4): the general result builder.

    Values come only from apply_status_field_pattern; invariants live only in
    EvaluationResult.__post_init__. A veto is EXACT with the required
    veto_provenance; every other status is UNDEFINED / NOT_COMPUTED and takes
    no veto_provenance. APPROXIMATION_REQUIRED raises ValueError. There is no
    values or value_intervals argument: value_intervals is always empty."""
    return _make(
        object_kind,
        object_id,
        status,
        status_reason,
        diagnostics,
        method_id=method_id,
        veto_provenance=veto_provenance,
        declared_assumptions=declared_assumptions,
        method_version=method_version,
        upstream_state=upstream_state,
        numerical_tolerance_used=numerical_tolerance_used,
        result_id=result_id,
        allow_approximation_required=False,
    )


def make_config_result(
    object_id: str,
    status: Status,
    status_reason: str,
    diagnostics: Sequence[DiagnosticRecord],
    declared_assumptions: Sequence[str] = (),
    method_id: str = "validate_cassette_config",
    method_version: str = METHOD_VERSION,
) -> EvaluationResult:
    """Construct a config-level result with the §10.1 pattern applied.

    Phase 1c never produces a numeric value. Veto results carry exact zeroed
    fields, so they are EXACT with provenance EXACT_STRUCTURAL_VETO (v0.3.1
    §6.3, §10.8). VALID and NOT_EVALUATED results carry no numeric payload, so
    they are UNDEFINED with provenance NOT_COMPUTED. Exactness describes the
    payload, not the verdict.

    AP-4: a wrapper over the make_result builder whose output is identical to
    the Phase 1c implementation for every input.
    """
    return _make(
        "CONFIG",
        object_id,
        status,
        status_reason,
        diagnostics,
        method_id=method_id,
        veto_provenance=Provenance.EXACT_STRUCTURAL_VETO if status in VETO_SET else None,
        declared_assumptions=declared_assumptions,
        method_version=method_version,
        upstream_state=None,
        numerical_tolerance_used=None,
        result_id=None,
        allow_approximation_required=True,
    )
