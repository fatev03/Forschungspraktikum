"""Conditional weights and normalized scenario fractions over Phase 2 states.

SCOPE
-----
A dependency-light analytic proxy that consumes serialized GOTNE Phase 2
outputs (STATE results, optionally with their state certificates) and
caller-supplied scenario factors. It computes:

  - a conditional weight per eligible state: the product of the caller's
    declared factors for that state;
  - normalized scenario fractions, when the total conditional weight is
    positive;
  - a scenario summary grouped by engagement count.

It re-derives no Phase 2 decision (topology, anchors, budgets, closure, node
gates), infers no missing value, and attaches no physical, chemical or
biological meaning to any number. A Phase 2 VALID result means only that the
Phase 2 deterministic checks did not veto the state; it is not evidence that
the state occurs.

ELIGIBILITY
-----------
A candidate is eligible iff it carries its serialized STATE result, that
result's status is VALID and its status_reason is STATE_NOT_VETOED. Every other
candidate becomes an ExclusionRecord; it is never repaired, reinterpreted or
weighted. A certificate alone lacks the engagement assignments and is excluded
with ENGAGEMENT_ASSIGNMENTS_UNAVAILABLE.

CONFIGURATION IDENTITY
----------------------
A serialized STATE result does not carry its config_identity_hash. A
candidate's config_identity_hash is taken from its certificate, and only after
that certificate has matched the candidate's STATE result by result_id,
state_hash, context_hash and status; without a STATE result and a matching
certificate it is None (unavailable). Certificates stay optional. The check
compares eligible states only; excluded states never take part:

  - two different available values: input error (ValueError);
  - available and equal for every eligible state: CONFIG_IDENTITY_VALIDATED;
  - available and equal for some eligible states, unavailable for the rest:
    CONFIG_IDENTITY_VALIDATION_PARTIAL (the rest are unchecked);
  - unavailable for every eligible state, or no eligible state:
    CONFIG_IDENTITY_VALIDATION_NOT_PERFORMED.

Provenance records config_identity_validation_status,
config_identity_validation_reason and eligible_config_identity_hashes (the
distinct available values: one entry when the check was performed, none
otherwise). No Phase 2 identity is recomputed.

INPUT ERRORS (ValueError / TypeError, never an exclusion)
--------------------------------------------------------
Malformed serialized data; a certificate that does not match its STATE
result; duplicate result_id or state_hash among candidates; eligible states
with different context_hash values or different available config_identity_hash
values; undeclared, missing, negative, NaN or infinite factors; factors for a
state that was not submitted.

Standard library only. No import from GOTNE or any other project package.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, ClassVar, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "SCHEMA_VERSION",
    "ScenarioParameters",
    "StateInput",
    "ExclusionRecord",
    "StateWeight",
    "ScenarioSummary",
    "eligible_states",
    "compute_state_weights",
    "normalize_weights",
    "summarize_scenario",
]

SCHEMA_VERSION = "analytic_proxy.scenario_summary/2"

#: The eight GOTNE Phase 2 status names, as serialized.
_PHASE2_STATUSES = frozenset(
    {
        "NUMERIC_FAILURE",
        "INFEASIBLE",
        "DEGENERATE",
        "UNREACHABLE",
        "BLOCKED",
        "APPROXIMATION_REQUIRED",
        "VALID",
        "NOT_EVALUATED",
    }
)
_VALID = "VALID"
_NOT_VETOED = "STATE_NOT_VETOED"
_ENGAGED, _UNENGAGED = "ENGAGED", "UNENGAGED"

_HEX64 = re.compile(r"[0-9a-f]{64}")
_STATE_RESULT_ID = re.compile(r"st-[0-9a-f]{64}")
_FACTOR_NAME = re.compile(r"[a-z][a-z0-9_]*")
#: Factor names may not suggest a physical, chemical or rate quantity.
_RESERVED_FACTOR_TERMS = ("affinity", "probability", "residence_time", "kinetic", "occupan")

ENGAGEMENT_GROUPS: Tuple[str, ...] = ("0", "1", "2", "3+")

_ORDERING_RULE = (
    "candidates, weights and exclusions are ordered by ascending state_hash; "
    "submission order is ignored"
)
_ELIGIBILITY_RULE = (
    "a STATE result is present with status VALID and status_reason STATE_NOT_VETOED; "
    "Phase 2 VALID means only that the Phase 2 checks did not veto the state"
)
_WEIGHT_RULE = "conditional weight = product of the declared factors, taken in factor_names order"
_ENGAGEMENT_RULE = "number of ENGAGED entries in the STATE result's upstream_state.assignments"
_FULLY_ENGAGED_RULE = (
    "maximum readable engagement count among all submitted candidates, including excluded "
    "candidates; readable means the candidate carries its STATE result"
)
_SCOPE = (
    "conditional weights and normalized scenario fractions under caller-supplied factors; "
    "scenario summaries only, with no physical or biological interpretation"
)


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _plain_str(value: object, what: str) -> str:
    if type(value) is not str or value == "":
        raise ValueError(f"{what} must be a non-empty string, got {type(value).__qualname__}")
    return value


def _hex64(value: object, what: str) -> str:
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise ValueError(f"{what} must be a 64-character lowercase hex digest")
    return value


def _state_result_id(value: object, what: str) -> str:
    if type(value) is not str or _STATE_RESULT_ID.fullmatch(value) is None:
        raise ValueError(f"{what} must be a Phase 2 STATE result id 'st-<64 hex>'")
    return value


def _field(data: Mapping, key: str, what: str) -> Any:
    if key not in data:
        raise ValueError(f"{what} is missing required key {key!r}")
    return data[key]


def _mapping(value: object, what: str) -> Mapping:
    if not isinstance(value, Mapping):
        raise ValueError(f"{what} must be a JSON object, got {type(value).__qualname__}")
    return value


def _factor_value(value: object, what: str) -> float:
    """A finite, non-negative real, returned as float. bool is rejected."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{what} must be a finite non-negative number, got {type(value).__qualname__}")
    try:
        number = float(value)
    except OverflowError:
        raise ValueError(f"{what} is not finite") from None
    if not math.isfinite(number):
        raise ValueError(f"{what} is not finite: {number!r}")
    if number < 0.0:
        raise ValueError(f"{what} is negative: {number!r}")
    return number


def _engagement_group(count: int) -> str:
    return "3+" if count >= 3 else str(count)


# --------------------------------------------------------------------------
# Scenario parameters
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ScenarioParameters:
    """Caller-supplied scenario: named multiplicative factors per state.

    factor_names declares every factor; state_factors maps a state_hash to a
    value for every declared name and nothing else. There are no defaults: a
    missing, undeclared, negative, NaN or infinite factor raises ValueError.
    state_factors may be given as a mapping or as (state_hash, factors) pairs;
    it is stored as a tuple ordered by state_hash, each factor tuple ordered
    by name. Caller mappings are copied, never modified."""

    scenario_id: str
    factor_names: Tuple[str, ...]
    state_factors: Tuple[Tuple[str, Tuple[Tuple[str, float], ...]], ...]

    def __post_init__(self) -> None:
        _plain_str(self.scenario_id, "scenario_id")
        if not isinstance(self.factor_names, (list, tuple)) or not self.factor_names:
            raise ValueError("factor_names must be a non-empty list or tuple of factor names")
        for name in self.factor_names:
            if type(name) is not str or _FACTOR_NAME.fullmatch(name) is None:
                raise ValueError(f"factor name {name!r} must match [a-z][a-z0-9_]*")
            reserved = [term for term in _RESERVED_FACTOR_TERMS if term in name]
            if reserved:
                raise ValueError(f"factor name {name!r} uses a reserved term {reserved[0]!r}")
        names = tuple(sorted(self.factor_names))
        if len(set(names)) != len(names):
            raise ValueError("factor_names must be unique")
        if isinstance(self.state_factors, Mapping):
            entries = list(self.state_factors.items())
        elif isinstance(self.state_factors, (list, tuple)):
            entries = []
            for entry in self.state_factors:
                if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                    raise ValueError("state_factors entries must be (state_hash, factors) pairs")
                entries.append((entry[0], entry[1]))
        else:
            raise ValueError("state_factors must be a mapping or a list of (state_hash, factors) pairs")
        normalized: Dict[str, Tuple[Tuple[str, float], ...]] = {}
        for state_hash, factors in entries:
            _hex64(state_hash, "state_factors key")
            if state_hash in normalized:
                raise ValueError(f"state_factors lists state {state_hash} twice")
            if isinstance(factors, Mapping):
                items = list(factors.items())
            elif isinstance(factors, (list, tuple)):
                items = [tuple(item) for item in factors]
                if any(len(item) != 2 for item in items):
                    raise ValueError(f"factors of state {state_hash} must be (name, value) pairs")
            else:
                raise ValueError(f"factors of state {state_hash} must be a mapping of name to value")
            supplied = [name for name, _ in items]
            if len(set(supplied)) != len(supplied):
                raise ValueError(f"state {state_hash} repeats a factor name")
            unknown = sorted(set(supplied) - set(names), key=str)
            if unknown:
                raise ValueError(f"state {state_hash} supplies undeclared factors {unknown}")
            missing = sorted(set(names) - set(supplied))
            if missing:
                raise ValueError(f"state {state_hash} is missing declared factors {missing}")
            values = dict(items)
            normalized[state_hash] = tuple(
                (name, _factor_value(values[name], f"factor {name!r} of state {state_hash}"))
                for name in names
            )
        object.__setattr__(self, "factor_names", names)
        object.__setattr__(self, "state_factors", tuple(sorted(normalized.items())))

    def factors_for(self, state_hash: str) -> Optional[Tuple[Tuple[str, float], ...]]:
        for key, factors in self.state_factors:
            if key == state_hash:
                return factors
        return None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "factor_names": list(self.factor_names),
            "state_factors": {key: dict(factors) for key, factors in self.state_factors},
        }


# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------
def _parse_state_result(data: object) -> Dict[str, Any]:
    result = _mapping(data, "state_result")
    if _field(result, "object_kind", "state_result") != "STATE":
        raise ValueError("state_result.object_kind must be 'STATE'")
    result_id = _state_result_id(_field(result, "result_id", "state_result"), "state_result.result_id")
    status = _field(result, "status", "state_result")
    if status not in _PHASE2_STATUSES:
        raise ValueError(f"state_result.status {status!r} is not a Phase 2 status")
    reason = _plain_str(_field(result, "status_reason", "state_result"), "state_result.status_reason")
    upstream = _mapping(_field(result, "upstream_state", "state_result"), "state_result.upstream_state")
    state_hash = _hex64(_field(upstream, "state_hash", "upstream_state"), "upstream_state.state_hash")
    context_hash = _hex64(_field(upstream, "context_hash", "upstream_state"), "upstream_state.context_hash")
    if _field(result, "object_id", "state_result") != "S:" + state_hash:
        raise ValueError("state_result.object_id must be 'S:' + upstream_state.state_hash")
    assignments = _mapping(_field(upstream, "assignments", "upstream_state"), "upstream_state.assignments")
    engaged: List[str] = []
    for module_id, entry in assignments.items():
        _plain_str(module_id, "assignment module id")
        label = _field(_mapping(entry, f"assignment {module_id}"), "label", f"assignment {module_id}")
        if label not in (_ENGAGED, _UNENGAGED):
            raise ValueError(f"assignment {module_id} has unknown label {label!r}")
        if label == _ENGAGED:
            engaged.append(module_id)
    return dict(
        result_id=result_id,
        state_hash=state_hash,
        context_hash=context_hash,
        phase2_status=status,
        phase2_status_reason=reason,
        engaged_modules=tuple(sorted(engaged)),
    )


def _parse_certificate(data: object) -> Dict[str, Any]:
    certificate = _mapping(data, "certificate")
    status = _field(certificate, "status", "certificate")
    if status not in _PHASE2_STATUSES:
        raise ValueError(f"certificate.status {status!r} is not a Phase 2 status")
    return dict(
        result_id=_state_result_id(
            _field(certificate, "state_result_id", "certificate"), "certificate.state_result_id"
        ),
        state_hash=_hex64(_field(certificate, "state_hash", "certificate"), "certificate.state_hash"),
        context_hash=_hex64(_field(certificate, "context_hash", "certificate"), "certificate.context_hash"),
        phase2_status=status,
        config_identity_hash=_hex64(
            _field(certificate, "config_identity_hash", "certificate"), "certificate.config_identity_hash"
        ),
    )


@dataclass(frozen=True)
class StateInput:
    """One submitted candidate, extracted from serialized Phase 2 output.

    engaged_modules and phase2_status_reason are None exactly when the
    candidate has no STATE result (certificate only). config_identity_hash
    is the certificate's value when a STATE result and a matching
    certificate are both given, and None (unavailable) otherwise. Build it
    with from_serialized; the serialized mappings are read, never kept or
    modified."""

    state_hash: str
    context_hash: str
    result_id: str
    phase2_status: str
    phase2_status_reason: Optional[str]
    engaged_modules: Optional[Tuple[str, ...]]
    has_state_result: bool
    has_certificate: bool
    config_identity_hash: Optional[str] = None

    def __post_init__(self) -> None:
        _hex64(self.state_hash, "state_hash")
        _hex64(self.context_hash, "context_hash")
        _state_result_id(self.result_id, "result_id")
        if self.phase2_status not in _PHASE2_STATUSES:
            raise ValueError(f"phase2_status {self.phase2_status!r} is not a Phase 2 status")
        if type(self.has_state_result) is not bool or type(self.has_certificate) is not bool:
            raise ValueError("has_state_result and has_certificate must be bool")
        if (self.config_identity_hash is not None) != (self.has_state_result and self.has_certificate):
            raise ValueError(
                "config_identity_hash is given exactly when a STATE result and a matching certificate are"
            )
        if self.config_identity_hash is not None:
            _hex64(self.config_identity_hash, "config_identity_hash")
        if not (self.has_state_result or self.has_certificate):
            raise ValueError("a candidate needs a STATE result or a certificate")
        if self.has_state_result:
            _plain_str(self.phase2_status_reason, "phase2_status_reason")
            if not isinstance(self.engaged_modules, (list, tuple)):
                raise ValueError("engaged_modules must list the ENGAGED module ids")
            modules = tuple(_plain_str(m, "engaged module id") for m in self.engaged_modules)
            if len(set(modules)) != len(modules):
                raise ValueError("engaged_modules must be unique")
            object.__setattr__(self, "engaged_modules", tuple(sorted(modules)))
        elif self.phase2_status_reason is not None or self.engaged_modules is not None:
            raise ValueError("without a STATE result there is no status_reason and no engaged_modules")

    @classmethod
    def from_serialized(
        cls, state_result: Optional[Mapping] = None, certificate: Optional[Mapping] = None
    ) -> "StateInput":
        """From StateResult.as_dict() and / or StateCertificate.as_dict() output
        (or their JSON round trip). A certificate given with its STATE result
        must match it by result id, state_hash, context_hash and status; only
        then is its config_identity_hash taken."""
        if state_result is None and certificate is None:
            raise ValueError("a candidate needs a serialized STATE result or certificate")
        parsed = _parse_state_result(state_result) if state_result is not None else None
        cert = _parse_certificate(certificate) if certificate is not None else None
        config_identity_hash = None
        if parsed is not None and cert is not None:
            for key in ("result_id", "state_hash", "context_hash", "phase2_status"):
                if parsed[key] != cert[key]:
                    raise ValueError(f"certificate does not match its STATE result: {key} differs")
            config_identity_hash = cert["config_identity_hash"]
        base = parsed if parsed is not None else cert
        return cls(
            state_hash=base["state_hash"],
            context_hash=base["context_hash"],
            result_id=base["result_id"],
            phase2_status=base["phase2_status"],
            phase2_status_reason=parsed["phase2_status_reason"] if parsed is not None else None,
            engaged_modules=parsed["engaged_modules"] if parsed is not None else None,
            has_state_result=parsed is not None,
            has_certificate=cert is not None,
            config_identity_hash=config_identity_hash,
        )

    @property
    def engagement_count(self) -> Optional[int]:
        return None if self.engaged_modules is None else len(self.engaged_modules)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "state_hash": self.state_hash,
            "context_hash": self.context_hash,
            "result_id": self.result_id,
            "phase2_status": self.phase2_status,
            "phase2_status_reason": self.phase2_status_reason,
            "engaged_modules": None if self.engaged_modules is None else list(self.engaged_modules),
            "engagement_count": self.engagement_count,
            "has_state_result": self.has_state_result,
            "has_certificate": self.has_certificate,
            "config_identity_hash": self.config_identity_hash,
        }


# --------------------------------------------------------------------------
# Exclusions
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ExclusionRecord:
    """A submitted candidate that receives no conditional weight."""

    ENGAGEMENT_ASSIGNMENTS_UNAVAILABLE: ClassVar[str] = "ENGAGEMENT_ASSIGNMENTS_UNAVAILABLE"
    PHASE2_STATUS_NOT_VALID: ClassVar[str] = "PHASE2_STATUS_NOT_VALID"
    PHASE2_VETO_REASON_PRESENT: ClassVar[str] = "PHASE2_VETO_REASON_PRESENT"
    REASONS: ClassVar[Tuple[str, ...]] = (
        "ENGAGEMENT_ASSIGNMENTS_UNAVAILABLE",
        "PHASE2_STATUS_NOT_VALID",
        "PHASE2_VETO_REASON_PRESENT",
    )

    state_hash: str
    result_id: str
    reason: str
    phase2_status: str
    phase2_status_reason: Optional[str]
    engagement_count: Optional[int]

    def __post_init__(self) -> None:
        if self.reason not in self.REASONS:
            raise ValueError(f"exclusion reason {self.reason!r} is not one of {self.REASONS}")
        _hex64(self.state_hash, "state_hash")
        _state_result_id(self.result_id, "result_id")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "state_hash": self.state_hash,
            "result_id": self.result_id,
            "reason": self.reason,
            "phase2_status": self.phase2_status,
            "phase2_status_reason": self.phase2_status_reason,
            "engagement_count": self.engagement_count,
        }


def _exclusion_reason(candidate: StateInput) -> Optional[str]:
    """None iff the candidate is eligible (module docstring, ELIGIBILITY)."""
    if not candidate.has_state_result:
        return ExclusionRecord.ENGAGEMENT_ASSIGNMENTS_UNAVAILABLE
    if candidate.phase2_status != _VALID:
        return ExclusionRecord.PHASE2_STATUS_NOT_VALID
    if candidate.phase2_status_reason != _NOT_VETOED:
        return ExclusionRecord.PHASE2_VETO_REASON_PRESENT
    return None


def _ordered_candidates(candidates: object) -> Tuple[StateInput, ...]:
    """Type-checked, duplicate-free, ordered by state_hash."""
    if not isinstance(candidates, (list, tuple)):
        raise TypeError(f"candidates must be a list or tuple of StateInput, got {type(candidates).__qualname__}")
    for candidate in candidates:
        if not isinstance(candidate, StateInput):
            raise TypeError(f"candidates must be StateInput records, got {type(candidate).__qualname__}")
    for key in ("result_id", "state_hash"):
        values = [getattr(c, key) for c in candidates]
        duplicates = sorted({v for v in values if values.count(v) > 1})
        if duplicates:
            raise ValueError(f"duplicate {key} among candidates: {duplicates}")
    return tuple(sorted(candidates, key=lambda c: c.state_hash))


# --------------------------------------------------------------------------
# Weights
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class StateWeight:
    """The conditional weight of one eligible state, and its normalized
    scenario fraction once normalize_weights defines one."""

    state_hash: str
    result_id: str
    engaged_modules: Tuple[str, ...]
    factors: Tuple[Tuple[str, float], ...]
    conditional_weight: float
    normalized_fraction: Optional[float] = None

    def __post_init__(self) -> None:
        _hex64(self.state_hash, "state_hash")
        _state_result_id(self.result_id, "result_id")
        if not isinstance(self.factors, tuple) or not self.factors:
            raise ValueError("factors must be a non-empty tuple of (name, value) pairs")
        product = math.prod(_factor_value(value, f"factor {name!r}") for name, value in self.factors)
        if self.conditional_weight != product or type(self.conditional_weight) is not float:
            raise ValueError("conditional_weight must equal the product of the factors")
        fraction = self.normalized_fraction
        if fraction is not None and not (type(fraction) is float and 0.0 <= fraction <= 1.0):
            raise ValueError("normalized_fraction must be None or a float in [0, 1]")

    @property
    def engagement_count(self) -> int:
        return len(self.engaged_modules)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "state_hash": self.state_hash,
            "result_id": self.result_id,
            "engaged_modules": list(self.engaged_modules),
            "engagement_count": self.engagement_count,
            "engagement_group": _engagement_group(self.engagement_count),
            "factors": dict(self.factors),
            "conditional_weight": self.conditional_weight,
            "normalized_fraction": self.normalized_fraction,
        }


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ScenarioSummary:
    """Scenario summary of one set of submitted candidates.

    The fraction fields are None exactly when normalization is not defined
    (no eligible state, or a zero total conditional weight); the reason is
    then recorded in normalization_reason and in provenance. provenance must
    carry the configuration-identity fields (module docstring, CONFIGURATION
    IDENTITY), consistent with one another."""

    NORMALIZED: ClassVar[str] = "NORMALIZED"
    NOT_NORMALIZED_ZERO_TOTAL: ClassVar[str] = "NOT_NORMALIZED_ZERO_TOTAL"
    NOT_NORMALIZED_NO_ELIGIBLE_STATES: ClassVar[str] = "NOT_NORMALIZED_NO_ELIGIBLE_STATES"
    CONFIG_IDENTITY_VALIDATED: ClassVar[str] = "CONFIG_IDENTITY_VALIDATED"
    CONFIG_IDENTITY_VALIDATION_PARTIAL: ClassVar[str] = "CONFIG_IDENTITY_VALIDATION_PARTIAL"
    CONFIG_IDENTITY_VALIDATION_NOT_PERFORMED: ClassVar[str] = "CONFIG_IDENTITY_VALIDATION_NOT_PERFORMED"

    scenario_id: str
    candidate_count: int
    eligible_count: int
    excluded_count: int
    weights: Tuple[StateWeight, ...]
    exclusions: Tuple[ExclusionRecord, ...]
    total_conditional_weight: float
    normalization_status: str
    normalization_reason: Optional[str]
    fractions_by_engagement_count: Optional[Tuple[Tuple[str, float], ...]]
    fraction_engaged_at_least_2: Optional[float]
    fraction_fully_engaged: Optional[float]
    fully_engaged_count: Optional[int]
    provenance: Mapping[str, Any]

    def __post_init__(self) -> None:
        statuses = (self.NORMALIZED, self.NOT_NORMALIZED_ZERO_TOTAL, self.NOT_NORMALIZED_NO_ELIGIBLE_STATES)
        if self.normalization_status not in statuses:
            raise ValueError(f"normalization_status must be one of {statuses}")
        if (self.eligible_count, self.excluded_count) != (len(self.weights), len(self.exclusions)):
            raise ValueError("eligible_count / excluded_count must match weights / exclusions")
        if self.candidate_count != self.eligible_count + self.excluded_count:
            raise ValueError("candidate_count must be eligible_count + excluded_count")
        normalized = self.normalization_status == self.NORMALIZED
        fractions = (
            self.fractions_by_engagement_count,
            self.fraction_engaged_at_least_2,
            self.fraction_fully_engaged,
        )
        if normalized != all(f is not None for f in fractions) or (
            not normalized and any(f is not None for f in fractions)
        ):
            raise ValueError("fraction fields are present exactly when normalization is defined")
        if normalized != (self.normalization_reason is None):
            raise ValueError("normalization_reason is given exactly when normalization is not defined")
        provenance = dict(self.provenance)
        config_statuses = (
            self.CONFIG_IDENTITY_VALIDATED,
            self.CONFIG_IDENTITY_VALIDATION_PARTIAL,
            self.CONFIG_IDENTITY_VALIDATION_NOT_PERFORMED,
        )
        if provenance.get("config_identity_validation_status") not in config_statuses:
            raise ValueError(f"provenance config_identity_validation_status must be one of {config_statuses}")
        _plain_str(provenance.get("config_identity_validation_reason"), "provenance config_identity_validation_reason")
        hashes = provenance.get("eligible_config_identity_hashes")
        if not isinstance(hashes, (list, tuple)):
            raise ValueError("provenance eligible_config_identity_hashes must be a list of digests")
        hashes = tuple(_hex64(h, "eligible config_identity_hash") for h in hashes)
        performed = provenance["config_identity_validation_status"] != self.CONFIG_IDENTITY_VALIDATION_NOT_PERFORMED
        if len(hashes) != (1 if performed else 0) or (performed and self.eligible_count == 0):
            raise ValueError(
                "eligible_config_identity_hashes holds one value exactly when config identity validation "
                "was performed over eligible states"
            )
        provenance["eligible_config_identity_hashes"] = hashes
        object.__setattr__(self, "provenance", MappingProxyType(provenance))

    def as_dict(self) -> Dict[str, Any]:
        grouped = self.fractions_by_engagement_count
        return {
            "scenario_id": self.scenario_id,
            "candidate_count": self.candidate_count,
            "eligible_count": self.eligible_count,
            "excluded_count": self.excluded_count,
            "weights": [w.as_dict() for w in self.weights],
            "exclusions": [e.as_dict() for e in self.exclusions],
            "total_conditional_weight": self.total_conditional_weight,
            "normalization_status": self.normalization_status,
            "normalization_reason": self.normalization_reason,
            "fractions_by_engagement_count": None if grouped is None else dict(grouped),
            "fraction_engaged_at_least_2": self.fraction_engaged_at_least_2,
            "fraction_fully_engaged": self.fraction_fully_engaged,
            "fully_engaged_count": self.fully_engaged_count,
            "provenance": {
                key: (list(value) if isinstance(value, tuple) else dict(value) if isinstance(value, Mapping) else value)
                for key, value in self.provenance.items()
            },
        }


# --------------------------------------------------------------------------
# Functions
# --------------------------------------------------------------------------
def _config_identity_validation(eligible: Sequence[StateInput]) -> Tuple[str, str, Tuple[str, ...]]:
    """(status, reason, distinct available config_identity_hash values) over
    eligible states only (module docstring, CONFIGURATION IDENTITY). Raises
    ValueError when two available values differ."""
    known = [c.config_identity_hash for c in eligible if c.config_identity_hash is not None]
    hashes = tuple(sorted(set(known)))
    if len(hashes) > 1:
        raise ValueError(
            f"eligible states carry {len(hashes)} different config_identity_hash values from matching "
            f"certificates: {list(hashes)}"
        )
    if not eligible:
        return ScenarioSummary.CONFIG_IDENTITY_VALIDATION_NOT_PERFORMED, "no eligible state", hashes
    if not known:
        return (
            ScenarioSummary.CONFIG_IDENTITY_VALIDATION_NOT_PERFORMED,
            f"config_identity_hash is unavailable for all {len(eligible)} eligible states: "
            "none carries a matching certificate",
            hashes,
        )
    if len(known) < len(eligible):
        return (
            ScenarioSummary.CONFIG_IDENTITY_VALIDATION_PARTIAL,
            f"config_identity_hash is available and equal for {len(known)} of {len(eligible)} eligible "
            f"states; the other {len(eligible) - len(known)} carry no matching certificate and are unchecked",
            hashes,
        )
    return (
        ScenarioSummary.CONFIG_IDENTITY_VALIDATED,
        f"config_identity_hash is available and equal for all {len(eligible)} eligible states",
        hashes,
    )


def eligible_states(
    candidates: Sequence[StateInput],
) -> Tuple[Tuple[StateInput, ...], Tuple[ExclusionRecord, ...]]:
    """(eligible candidates, exclusion records), both ordered by state_hash.

    Raises ValueError on duplicate result_id or state_hash, or when eligible
    candidates carry different context_hash values or different available
    config_identity_hash values. Excluded candidates are not compared."""
    eligible: List[StateInput] = []
    exclusions: List[ExclusionRecord] = []
    for candidate in _ordered_candidates(candidates):
        reason = _exclusion_reason(candidate)
        if reason is None:
            eligible.append(candidate)
        else:
            exclusions.append(
                ExclusionRecord(
                    state_hash=candidate.state_hash,
                    result_id=candidate.result_id,
                    reason=reason,
                    phase2_status=candidate.phase2_status,
                    phase2_status_reason=candidate.phase2_status_reason,
                    engagement_count=candidate.engagement_count,
                )
            )
    contexts = sorted({c.context_hash for c in eligible})
    if len(contexts) > 1:
        raise ValueError(f"eligible states come from {len(contexts)} different contexts: {contexts}")
    _config_identity_validation(eligible)
    return tuple(eligible), tuple(exclusions)


def compute_state_weights(
    eligible: Sequence[StateInput], parameters: ScenarioParameters
) -> Tuple[StateWeight, ...]:
    """The conditional weight of every eligible state, ordered by state_hash:
    the product of its declared factors. A zero factor gives weight zero.
    Raises ValueError for an ineligible candidate, a state without factors, or
    a product that is not finite."""
    if not isinstance(parameters, ScenarioParameters):
        raise TypeError(f"parameters must be ScenarioParameters, got {type(parameters).__qualname__}")
    weights = []
    for candidate in _ordered_candidates(eligible):
        reason = _exclusion_reason(candidate)
        if reason is not None:
            raise ValueError(f"state {candidate.state_hash} is not eligible ({reason}); it gets no weight")
        factors = parameters.factors_for(candidate.state_hash)
        if factors is None:
            raise ValueError(f"no factors supplied for eligible state {candidate.state_hash}")
        weight = math.prod(value for _, value in factors)
        if not math.isfinite(weight):
            raise ValueError(f"the conditional weight of state {candidate.state_hash} is not finite")
        weights.append(
            StateWeight(
                state_hash=candidate.state_hash,
                result_id=candidate.result_id,
                engaged_modules=candidate.engaged_modules,
                factors=factors,
                conditional_weight=weight,
            )
        )
    return tuple(weights)


def normalize_weights(weights: Sequence[StateWeight]) -> Tuple[StateWeight, ...]:
    """Each weight with normalized_fraction = weight / total, ordered by
    state_hash. When there is no weight or the total is zero, the weights are
    returned with normalized_fraction None: nothing is divided."""
    if not isinstance(weights, (list, tuple)) or not all(isinstance(w, StateWeight) for w in weights):
        raise TypeError("weights must be a list or tuple of StateWeight")
    hashes = [w.state_hash for w in weights]
    if len(set(hashes)) != len(hashes):
        raise ValueError("duplicate state_hash among weights")
    ordered = sorted(weights, key=lambda w: w.state_hash)
    try:
        total = math.fsum(w.conditional_weight for w in ordered)
    except OverflowError:
        raise ValueError("the total conditional weight is not finite") from None
    if total == 0.0:
        return tuple(replace(w, normalized_fraction=None) for w in ordered)
    return tuple(replace(w, normalized_fraction=w.conditional_weight / total) for w in ordered)


def summarize_scenario(
    candidates: Sequence[StateInput], parameters: ScenarioParameters
) -> ScenarioSummary:
    """The scenario summary of the submitted candidates under parameters.

    Raises ValueError for the input errors listed in the module docstring,
    including factors supplied for a state that was not submitted. Factors
    supplied for an excluded state are validated but never used."""
    if not isinstance(parameters, ScenarioParameters):
        raise TypeError(f"parameters must be ScenarioParameters, got {type(parameters).__qualname__}")
    eligible, exclusions = eligible_states(candidates)
    submitted = {c.state_hash for c in candidates}
    unknown = sorted(key for key, _ in parameters.state_factors if key not in submitted)
    if unknown:
        raise ValueError(f"factors supplied for states that were not submitted: {unknown}")
    weights = normalize_weights(compute_state_weights(eligible, parameters))
    total = math.fsum(w.conditional_weight for w in weights)

    readable = [c.engagement_count for c in candidates if c.engagement_count is not None]
    fully = max(readable) if readable else None
    grouped = at_least_2 = fully_fraction = None
    if not eligible:
        status, reason = ScenarioSummary.NOT_NORMALIZED_NO_ELIGIBLE_STATES, "no eligible state"
    elif total == 0.0:
        status, reason = ScenarioSummary.NOT_NORMALIZED_ZERO_TOTAL, "total conditional weight is zero"
    else:
        status, reason = ScenarioSummary.NORMALIZED, None
        grouped = tuple(
            (group, math.fsum(w.normalized_fraction for w in weights
                              if _engagement_group(w.engagement_count) == group))
            for group in ENGAGEMENT_GROUPS
        )
        at_least_2 = math.fsum(w.normalized_fraction for w in weights if w.engagement_count >= 2)
        fully_fraction = math.fsum(w.normalized_fraction for w in weights if w.engagement_count == fully)

    config_status, config_reason, config_hashes = _config_identity_validation(eligible)
    reason_counts = {r: sum(1 for e in exclusions if e.reason == r) for r in ExclusionRecord.REASONS}
    provenance = {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": parameters.scenario_id,
        "scope": _SCOPE,
        "eligibility_rule": _ELIGIBILITY_RULE,
        "input_ordering_rule": _ORDERING_RULE,
        "factor_names": parameters.factor_names,
        "weight_rule": _WEIGHT_RULE,
        "engagement_count_rule": _ENGAGEMENT_RULE,
        "engagement_groups": ENGAGEMENT_GROUPS,
        "fully_engaged_rule": _FULLY_ENGAGED_RULE,
        "fully_engaged_count": fully,
        "normalization_status": status,
        "normalization_reason": reason,
        "context_hash": eligible[0].context_hash if eligible else None,
        "config_identity_validation_status": config_status,
        "config_identity_validation_reason": config_reason,
        "eligible_config_identity_hashes": config_hashes,
        "exclusion_reason_counts": MappingProxyType({r: n for r, n in reason_counts.items() if n}),
    }
    return ScenarioSummary(
        scenario_id=parameters.scenario_id,
        candidate_count=len(candidates),
        eligible_count=len(eligible),
        excluded_count=len(exclusions),
        weights=weights,
        exclusions=exclusions,
        total_conditional_weight=total,
        normalization_status=status,
        normalization_reason=reason,
        fractions_by_engagement_count=grouped,
        fraction_engaged_at_least_2=at_least_2,
        fraction_fully_engaged=fully_fraction,
        fully_engaged_count=fully,
        provenance=provenance,
    )
