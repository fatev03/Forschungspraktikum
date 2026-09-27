"""GOTNE Phase 2 candidate priority (v0.3.1): caller-side test-priority ordering.

SCOPE (cassette_candidate_priority/1)
-------------------------------------
A caller-side consumer above the batch producer, never a link in the chain and
never an input to it. It reads a finished CandidateBatchReport and a
caller-declared evidence mapping, and arranges what they already contain. It
evaluates no geometry, issues no certificate, vetoes nothing, mints no
identifier, computes no hash and performs no I/O. Every identifier it reports is
copied from the producer that minted it.

It may read cassette_candidate_batch, cassette_slot_ledger, cassette_slots,
cassette_state and status. It MUST NOT import cassette_frames, cassette_budget,
cassette_closure or cassette_node directly, MUST NOT import any Phase 4 or
Phase 5 module (composite_density, so3_grids, pose_marginalization,
shell_bounds, intervals), and MUST NOT import any external-intake module: the
structure_audit tree is a separate package, and coupling the two would make a
kernel-side artefact depend on an external-output reader. Structure evidence
therefore enters as StructureEvidenceRecord, which the caller constructs
explicitly, so the conversion is visible at the call site.

TWO AXES
--------
Axis A, the geometry/state tier, is a total function over an eligible entry's
declared facts, yielding one member of a closed enumeration. There is no
arithmetic, no weight, no fitted constant and no cross-batch scalar.

Axis B, structure-evidence coverage, is a reported dimension only. It is not
part of the ordering key at any precedence. The stricter rule was chosen over
coverage-as-tie-break because a secondary key still changes the emitted ordinal
within a tier, which a reader cannot distinguish from promotion.

SUPPORTED is deliberately absent from the coverage vocabulary. The strongest
status an external artefact currently carries means mapping-preparation
readiness, not support, so ADMITTED_MAPPING_PREP_ONLY names what is actually
declared. A source_status outside the three declared tokens is UNSUPPORTED
rather than folded into a neighbour.

ORDER
-----
The ordering key is the geometry tier and nothing else. rank is a 1-based
ordinal on the group, identical for every member of it, so rank is a function of
the key alone. Within a group members keep the caller's sequence, which is
stable presentation and never precedence: candidate_id, input position, every
hash, every result identifier and the coverage value are all excluded as
ordering inputs, and there is no residual or fallback tie-break. A tie is
emitted as a tie.

READING
-------
A tier is a restatement of declared inputs and finished Phase 2 results. A
NOT_VETOED outcome carries exactly the scope of Section 20.7.3 N0: it is not
observed engagement, binding, occupancy, simultaneity, persistence or
probability, and the presence of an evidence record is not evidence of candidate
quality. Nothing here scores, weights or predicts.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .cassette_candidate_batch import CandidateBatchReport, CandidateEntry, EntryKind
from .cassette_slot_ledger import FailureClass, NodePresence, SlotLedger
from .cassette_slots import SlotId
from .cassette_state import EngagementLabel
from .status import Status

__all__ = [
    "PRIORITY_DOCUMENT_TYPE",
    "PRIORITY_NON_CLAIM",
    "PRIORITY_DISPLAY_DISCLAIMER",
    "AF3_RED_PROVIDER",
    "KNOWN_PROVIDERS",
    "DECLARED_SOURCE_STATUS",
    "GeometryTier",
    "TIER_ORDER",
    "EvidenceCoverage",
    "IneligibilityReason",
    "StructureEvidenceRecord",
    "TierBasisRow",
    "PriorityMember",
    "PriorityGroup",
    "ExcludedEntry",
    "CandidatePriorityReport",
    "classify_evidence",
    "geometry_tier",
    "ineligibility_reason",
    "evaluate_candidate_priority",
    "render_lines",
]

PRIORITY_DOCUMENT_TYPE = "cassette_candidate_priority/1"

#: Emitted verbatim in every report and above every rendering. Never reworded,
#: abridged or parameterized.
PRIORITY_NON_CLAIM = (
    "This ordered three-slot candidate is a stronger test-priority hypothesis "
    "under the declared geometry/state inputs and the explicitly available "
    "structure-evidence record.\n"
    "\n"
    "This ordering is a deterministic restatement of declared inputs and "
    "finished Phase 2 results. It is not a claim about receptor biology, "
    "abundance, accessibility, expression, membrane context, glycosylation, or "
    "dynamics; not about affinity, KD, kinetics, occupancy, avidity magnitude, "
    "binding probability, efficacy, safety, specificity, or experimental "
    "success. A structure prediction or external artifact referenced here is "
    "not ground truth, and the presence of an AF3-ReD evidence record is not "
    "evidence of candidate quality. A NOT_VETOED Phase 2 outcome carries "
    "exactly the scope of 20.7.3 N0 and nothing further."
)

#: Printed immediately above any rendered priority block.
PRIORITY_DISPLAY_DISCLAIMER = (
    "Test-priority ordering - declared geometry/state and declared evidence "
    "coverage only. Rank is a function of the Phase 2 geometry/state tier "
    "alone. Evidence coverage is reported, never ranked on. Equal rank means "
    "equal tier, not equivalence. Listing position within a rank is caller "
    "sequence, not precedence."
)

#: The one provider with both a checked-in artefact and a notebook seam. It is a
#: named constant for a caller to pass, never an implicit default.
AF3_RED_PROVIDER = "af3-red"
KNOWN_PROVIDERS: Tuple[str, ...] = (AF3_RED_PROVIDER,)

#: The declared external status vocabulary, mapped in _COVERAGE_OF_STATUS. A
#: token outside it is UNSUPPORTED, never folded into a neighbour.
DECLARED_SOURCE_STATUS: Tuple[str, ...] = ("candidate", "admitted", "rejected")


class GeometryTier(str, Enum):
    """The closed geometry/state enumeration. Order is TIER_ORDER, never a
    computed key, and no member carries a magnitude."""

    T1_ENGAGED_SLOTS_FULLY_RESOLVED = "T1_ENGAGED_SLOTS_FULLY_RESOLVED"
    T2_ENGAGED_SLOTS_PARTIALLY_RESOLVED = "T2_ENGAGED_SLOTS_PARTIALLY_RESOLVED"
    T3_NO_RESOLVED_ENGAGED_SLOT = "T3_NO_RESOLVED_ENGAGED_SLOT"


#: The only ordering key. Groups are emitted in this order; nothing else ranks.
TIER_ORDER: Tuple[GeometryTier, GeometryTier, GeometryTier] = (
    GeometryTier.T1_ENGAGED_SLOTS_FULLY_RESOLVED,
    GeometryTier.T2_ENGAGED_SLOTS_PARTIALLY_RESOLVED,
    GeometryTier.T3_NO_RESOLVED_ENGAGED_SLOT,
)


class EvidenceCoverage(str, Enum):
    """Reported only. Never an ordering input, a tie-break or a promotion.
    SUPPORTED is absent by design; see the module docstring."""

    ABSENT = "ABSENT"
    CANDIDATE = "CANDIDATE"
    ADMITTED_MAPPING_PREP_ONLY = "ADMITTED_MAPPING_PREP_ONLY"
    REJECTED = "REJECTED"
    UNSUPPORTED = "UNSUPPORTED"


class IneligibilityReason(str, Enum):
    """Why an entry carries no tier. Evaluated in declaration order, first match
    wins, and the matched reason is the reported one."""

    DECLARATION_REFUSED = "DECLARATION_REFUSED"
    LEDGER_ABSENT = "LEDGER_ABSENT"
    STATE_NOT_VALID = "STATE_NOT_VALID"
    CERTIFICATE_ABSENT = "CERTIFICATE_ABSENT"
    SLOT_VETOED = "SLOT_VETOED"
    SLOT_UNEVALUABLE = "SLOT_UNEVALUABLE"


_COVERAGE_OF_STATUS = {
    "candidate": EvidenceCoverage.CANDIDATE,
    "admitted": EvidenceCoverage.ADMITTED_MAPPING_PREP_ONLY,
    "rejected": EvidenceCoverage.REJECTED,
}

#: The two veto classes and the unevaluable class, kept separable. A row class
#: outside this mapping has no gate meaning here and raises rather than passing.
_VETO_CLASSES = (
    FailureClass.INFEASIBLE_DECLARED_INPUT,
    FailureClass.UNREACHABLE_GEOMETRIC_VETO,
)
_GATE_CLASSES = (FailureClass.NOT_VETOED, FailureClass.UNEVALUABLE) + _VETO_CLASSES


# --------------------------------------------------------------------------
# Evidence intake
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class StructureEvidenceRecord:
    """The nine fields of the notebook external-reference seam, restated locally
    so this module imports no external-intake package. The caller constructs it
    explicitly; nothing here reads an artefact, resolves a reference or
    recomputes a hash."""

    provider: str
    profile: str
    artifact_id: str
    observed_sha256: str
    source_status: str
    read_completed: bool
    execution_state: str
    validation_status: str
    non_admission_reasons: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "provider",
            "profile",
            "artifact_id",
            "observed_sha256",
            "source_status",
            "execution_state",
            "validation_status",
        ):
            value = getattr(self, name)
            if type(value) is not str:
                raise TypeError(
                    f"StructureEvidenceRecord.{name} must be a plain str, "
                    f"got {type(value).__qualname__}"
                )
        if type(self.read_completed) is not bool:
            raise TypeError(
                "StructureEvidenceRecord.read_completed must be a bool, got "
                f"{type(self.read_completed).__qualname__}"
            )
        reasons = self.non_admission_reasons
        if type(reasons) not in (list, tuple) or any(type(r) is not str for r in reasons):
            raise TypeError(
                "StructureEvidenceRecord.non_admission_reasons must be a list or tuple of str"
            )
        object.__setattr__(self, "non_admission_reasons", tuple(reasons))

    def as_dict(self) -> Dict[str, Any]:
        """A fresh presentation record; every field verbatim, reasons in order."""
        return {
            "provider": self.provider,
            "profile": self.profile,
            "artifact_id": self.artifact_id,
            "observed_sha256": self.observed_sha256,
            "source_status": self.source_status,
            "read_completed": self.read_completed,
            "execution_state": self.execution_state,
            "validation_status": self.validation_status,
            "non_admission_reasons": list(self.non_admission_reasons),
        }


def classify_evidence(record: object, providers: Tuple[str, ...]) -> EvidenceCoverage:
    """The coverage value of one declared record. source_status is the only input.

    A record that is not a StructureEvidenceRecord, a provider outside the
    caller's declared allowlist, or a source_status outside
    DECLARED_SOURCE_STATUS all yield UNSUPPORTED. non_admission_reasons,
    read_completed, execution_state, validation_status, profile, artifact_id and
    observed_sha256 never raise or lower the value: they are display-only.
    """
    _require_providers(providers)
    if record is None:
        return EvidenceCoverage.ABSENT
    if not isinstance(record, StructureEvidenceRecord):
        return EvidenceCoverage.UNSUPPORTED
    if record.provider not in providers:
        return EvidenceCoverage.UNSUPPORTED
    return _COVERAGE_OF_STATUS.get(record.source_status, EvidenceCoverage.UNSUPPORTED)


def _require_providers(providers: object) -> None:
    if type(providers) not in (list, tuple):
        raise TypeError(
            f"providers must be a list or tuple, got {type(providers).__qualname__}"
        )
    if not providers:
        raise ValueError("providers must declare at least one provider; there is no default")
    for position, provider in enumerate(providers):
        if type(provider) is not str:
            raise TypeError(f"providers[{position}] must be a plain str")
        if provider == "":
            raise ValueError(f"providers[{position}] must be non-empty")


# --------------------------------------------------------------------------
# The gate and the tier
# --------------------------------------------------------------------------
def ineligibility_reason(entry: CandidateEntry) -> Optional[IneligibilityReason]:
    """The entry's ineligibility reason, or None when it is eligible.

    Total over CandidateEntry. It copies every status and reason it reports and
    reinterprets none. Absent, unresolved, candidate-status, rejected-status or
    malformed structure evidence is NOT a reason here and never appears: a
    geometry-eligible candidate stays eligible whatever its evidence state.
    """
    if not isinstance(entry, CandidateEntry):
        raise TypeError(f"entry must be a CandidateEntry, got {type(entry).__qualname__}")
    if entry.entry_kind is EntryKind.DECLARATION_REFUSED:
        return IneligibilityReason.DECLARATION_REFUSED
    # Unreachable through CandidateEntry's own invariant; refused rather than
    # assumed, so the gate stays total if that invariant ever widens.
    if entry.ledger is None:
        return IneligibilityReason.LEDGER_ABSENT
    rows = entry.ledger.rows
    for row in rows:
        if row.failure_class not in _GATE_CLASSES:
            raise ValueError(
                f"row {row.slot.value!r} carries failure class {row.failure_class.value}, "
                "which has no gate meaning here; it is not folded into a neighbouring class"
            )
    if rows[0].state_status is not Status.VALID:
        return IneligibilityReason.STATE_NOT_VALID
    if not entry.ledger.certificate_present:
        return IneligibilityReason.CERTIFICATE_ABSENT
    if any(row.failure_class in _VETO_CLASSES for row in rows):
        return IneligibilityReason.SLOT_VETOED
    if any(row.failure_class is FailureClass.UNEVALUABLE for row in rows):
        return IneligibilityReason.SLOT_UNEVALUABLE
    return None


def geometry_tier(ledger: SlotLedger) -> GeometryTier:
    """The tier of an eligible entry's ledger. Total; no arithmetic and no score.

    An ENGAGED row is resolved when it carries a PRESENT node result whose class
    is NOT_VETOED. A binding with no ENGAGED slot is a legitimate declared state
    and lands in T3, not a defect. ABSENT_NOT_SUPPLIED does not arise from
    evaluate_candidate_batch, which produces a node result for every ENGAGED
    slot of a certified VALID state; the function is total over it anyway.
    """
    if not isinstance(ledger, SlotLedger):
        raise TypeError(f"ledger must be a SlotLedger, got {type(ledger).__qualname__}")
    engaged = [row for row in ledger.rows if row.label is EngagementLabel.ENGAGED]
    resolved = [
        row
        for row in engaged
        if row.node_presence is NodePresence.PRESENT
        and row.failure_class is FailureClass.NOT_VETOED
    ]
    if engaged and len(resolved) == len(engaged):
        return GeometryTier.T1_ENGAGED_SLOTS_FULLY_RESOLVED
    if resolved:
        return GeometryTier.T2_ENGAGED_SLOTS_PARTIALLY_RESOLVED
    return GeometryTier.T3_NO_RESOLVED_ENGAGED_SLOT


# --------------------------------------------------------------------------
# Output records
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class TierBasisRow:
    """One slot's enumerated facts, exactly as the ledger recorded them. The
    tier predicate is stated over these; no count is emitted."""

    slot: SlotId
    label: EngagementLabel
    node_presence: NodePresence
    failure_class: FailureClass

    def as_dict(self) -> Dict[str, Any]:
        return {
            "slot": self.slot.value,
            "label": self.label.value,
            "node_presence": self.node_presence.value,
            "failure_class": self.failure_class.value,
        }


@dataclass(frozen=True)
class PriorityMember:
    """One eligible candidate. Every identifier is copied from its producer."""

    candidate_id: str
    slot_binding_hash: str
    state_result_id: Optional[str]
    certificate_present: bool
    geometry_tier: GeometryTier
    evidence_coverage: EvidenceCoverage
    evidence: Optional[StructureEvidenceRecord]
    tier_basis: Tuple[TierBasisRow, ...]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "slot_binding_hash": self.slot_binding_hash,
            "state_result_id": self.state_result_id,
            "certificate_present": self.certificate_present,
            "geometry_tier": self.geometry_tier.value,
            "evidence_coverage": self.evidence_coverage.value,
            "evidence": None if self.evidence is None else self.evidence.as_dict(),
            "tier_basis": [row.as_dict() for row in self.tier_basis],
        }


@dataclass(frozen=True)
class PriorityGroup:
    """One tie group. rank is a function of geometry_tier alone and is identical
    for every member, so listing position inside a group is never precedence."""

    rank: int
    geometry_tier: GeometryTier
    members: Tuple[PriorityMember, ...]

    def __post_init__(self) -> None:
        if type(self.rank) is not int or self.rank < 1:
            raise ValueError("rank must be a 1-based positive int")
        if not self.members:
            raise ValueError("a group is emitted only for an occupied tier")
        for member in self.members:
            if member.geometry_tier is not self.geometry_tier:
                raise ValueError(
                    f"member {member.candidate_id!r} carries tier "
                    f"{member.geometry_tier.value}, not the group's "
                    f"{self.geometry_tier.value}"
                )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "geometry_tier": self.geometry_tier.value,
            "members": [member.as_dict() for member in self.members],
        }


@dataclass(frozen=True)
class ExcludedEntry:
    """One ineligible candidate. Never dropped and never ranked. The kernel's own
    status and reason are carried verbatim."""

    candidate_id: str
    slot_binding_hash: str
    ineligibility_reason: IneligibilityReason
    state_status: Optional[Status]
    state_status_reason: Optional[str]
    vetoed_slots: Tuple[SlotId, ...]
    refusal_stage: Optional[str]
    refusal_error_class: Optional[str]
    refusal_detail: Optional[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "slot_binding_hash": self.slot_binding_hash,
            "ineligibility_reason": self.ineligibility_reason.value,
            "state_status": None if self.state_status is None else self.state_status.value,
            "state_status_reason": self.state_status_reason,
            "vetoed_slots": [slot.value for slot in self.vetoed_slots],
            "refusal_stage": self.refusal_stage,
            "refusal_error_class": self.refusal_error_class,
            "refusal_detail": self.refusal_detail,
        }


@dataclass(frozen=True)
class CandidatePriorityReport:
    """Tie groups in tier order plus every excluded candidate in caller order.

    The union of ranked and excluded candidate ids equals the source batch's
    candidate_order exactly; nothing is omitted, merged or duplicated.
    """

    candidate_order: Tuple[str, ...]
    groups: Tuple[PriorityGroup, ...]
    excluded: Tuple[ExcludedEntry, ...]

    def __post_init__(self) -> None:
        ranked = [m.candidate_id for group in self.groups for m in group.members]
        excluded = [entry.candidate_id for entry in self.excluded]
        reported = ranked + excluded
        if sorted(reported) != sorted(self.candidate_order):
            raise ValueError(
                "the union of ranked and excluded candidates must equal candidate_order "
                "exactly; no candidate is omitted, added or duplicated"
            )
        if len(set(reported)) != len(reported):
            raise ValueError("a candidate appears more than once in the report")
        expected = [index + 1 for index in range(len(self.groups))]
        if [group.rank for group in self.groups] != expected:
            raise ValueError("group ranks must be contiguous and 1-based in tier order")
        tiers = [group.geometry_tier for group in self.groups]
        if tiers != [tier for tier in TIER_ORDER if tier in tiers]:
            raise ValueError("groups must be emitted in TIER_ORDER")

    @property
    def non_claim(self) -> str:
        return PRIORITY_NON_CLAIM

    def as_dict(self) -> Dict[str, Any]:
        return {
            "document_type": PRIORITY_DOCUMENT_TYPE,
            "non_claim": PRIORITY_NON_CLAIM,
            "candidate_order": list(self.candidate_order),
            "groups": [group.as_dict() for group in self.groups],
            "excluded": [entry.as_dict() for entry in self.excluded],
        }

    def to_json_bytes(self) -> bytes:
        """Canonical bytes. sort_keys orders object keys only; candidate_order,
        groups, members, excluded and tier_basis keep the order they were built
        in."""
        return json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")


# --------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------
def _member(
    entry: CandidateEntry, coverage: EvidenceCoverage, record: Optional[StructureEvidenceRecord]
) -> PriorityMember:
    ledger = entry.ledger
    return PriorityMember(
        candidate_id=entry.candidate_id,
        slot_binding_hash=entry.slot_binding_hash,
        state_result_id=ledger.state_result_id,
        certificate_present=ledger.certificate_present,
        geometry_tier=geometry_tier(ledger),
        evidence_coverage=coverage,
        evidence=record,
        tier_basis=tuple(
            TierBasisRow(row.slot, row.label, row.node_presence, row.failure_class)
            for row in ledger.rows
        ),
    )


def _excluded(entry: CandidateEntry, reason: IneligibilityReason) -> ExcludedEntry:
    ledger, refusal = entry.ledger, entry.refusal
    rows = () if ledger is None else ledger.rows
    if reason is IneligibilityReason.SLOT_VETOED:
        vetoed = tuple(row.slot for row in rows if row.failure_class in _VETO_CLASSES)
    elif reason is IneligibilityReason.SLOT_UNEVALUABLE:
        vetoed = tuple(
            row.slot for row in rows if row.failure_class is FailureClass.UNEVALUABLE
        )
    else:
        vetoed = ()
    return ExcludedEntry(
        candidate_id=entry.candidate_id,
        slot_binding_hash=entry.slot_binding_hash,
        ineligibility_reason=reason,
        state_status=None if not rows else rows[0].state_status,
        state_status_reason=None if not rows else rows[0].state_status_reason,
        vetoed_slots=vetoed,
        refusal_stage=None if refusal is None else refusal.stage.value,
        refusal_error_class=None if refusal is None else refusal.error_class,
        refusal_detail=None if refusal is None else refusal.detail,
    )


def evaluate_candidate_priority(
    batch_report: CandidateBatchReport,
    *,
    evidence: Mapping[str, object],
    providers: Tuple[str, ...],
) -> CandidatePriorityReport:
    """Arrange one finished batch report into tie groups. Pure and read-only.

    ``evidence`` maps candidate_id to one declared StructureEvidenceRecord. Both
    arguments are required: there is no implicit default for either the mapping
    or the provider allowlist. A key naming a candidate the batch does not carry
    raises before any output exists, mirroring the external adapter's refusal of
    a stale artefact id; there is no partial report.

    Ordering is by geometry tier alone. Coverage is reported and never ranked on.
    Nothing is sorted, scored, repaired, defaulted or omitted.
    """
    if not isinstance(batch_report, CandidateBatchReport):
        raise TypeError(
            "batch_report must be a CandidateBatchReport, got "
            f"{type(batch_report).__qualname__}"
        )
    _require_providers(providers)
    if not isinstance(evidence, Mapping):
        raise TypeError(
            f"evidence must be a mapping, got {type(evidence).__qualname__}"
        )
    order = tuple(entry.candidate_id for entry in batch_report.entries)
    unknown = sorted(key for key in evidence if key not in set(order))
    if unknown:
        raise ValueError(
            f"evidence names candidates the batch does not carry: {unknown}"
        )

    buckets: Dict[GeometryTier, List[PriorityMember]] = {tier: [] for tier in TIER_ORDER}
    excluded: List[ExcludedEntry] = []
    for entry in batch_report.entries:
        reason = ineligibility_reason(entry)
        if reason is not None:
            excluded.append(_excluded(entry, reason))
            continue
        record = evidence.get(entry.candidate_id)
        coverage = classify_evidence(record, providers)
        member = _member(
            entry,
            coverage,
            record if isinstance(record, StructureEvidenceRecord) else None,
        )
        buckets[member.geometry_tier].append(member)

    groups: List[PriorityGroup] = []
    for tier in TIER_ORDER:
        members = buckets[tier]
        if not members:
            continue
        groups.append(PriorityGroup(len(groups) + 1, tier, tuple(members)))
    return CandidatePriorityReport(order, tuple(groups), tuple(excluded))


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def render_lines(report: CandidatePriorityReport) -> List[str]:
    """Fresh display lines. The non-claim statement and the disclaimer come
    before the first group; a non-report is refused rather than rendered."""
    if not isinstance(report, CandidatePriorityReport):
        raise TypeError(
            "report must be a CandidatePriorityReport, got "
            f"{type(report).__qualname__}"
        )
    document = report.as_dict()
    if document["non_claim"] != PRIORITY_NON_CLAIM:
        raise ValueError("the non-claim statement is absent or altered; nothing is rendered")
    lines = PRIORITY_NON_CLAIM.split("\n") + ["", PRIORITY_DISPLAY_DISCLAIMER, ""]
    for group in report.groups:
        lines.append(f"rank {group.rank}  {group.geometry_tier.value}")
        for member in group.members:
            lines.append(
                f"  {member.candidate_id}  coverage {member.evidence_coverage.value}"
            )
    for entry in report.excluded:
        lines.append(
            f"excluded  {entry.candidate_id}  {entry.ineligibility_reason.value}"
        )
    return lines
