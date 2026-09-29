"""GOTNE Phase 2 evidence completeness (v0.3.1): a descriptive, non-decision record.

SCOPE (cassette_evidence_completeness/1)
----------------------------------------
A read-only descriptive layer over already-serialized documents. It reports
whether the fields of a declared structure-evidence document were filled in and
well formed, and it carries the immutable source-admission reference beside that
report without touching it. It decides nothing.

It is not a link in any chain and is an input to nothing. It evaluates no
geometry, issues no certificate, vetoes nothing, promotes nothing, mints no
identifier, computes no hash and performs no I/O. It emits no scalar, no score,
no rank, no sort key, no ordering, no recommendation and no comparison between
candidates, and it holds no arithmetic over any reported value.

Standard library only. This module imports nothing from gotne, by contract: it
consumes the *serialized* forms (the mappings produced by
StructureEvidenceRecord.as_dict() and by the priority document's member and
excluded entries), exactly as analytic_proxy consumes serialized Phase 2 output.
That keeps the four existing package-wide import sweeps intact and makes this
layer unable to reach an evaluator even by accident.

WHAT IT ADDS, AND WHY
---------------------
cassette_candidate_priority classifies evidence coverage from source_status
alone; its other eight fields are documented and tested as display-only. As a
result a document whose descriptive fields are all empty, a document with a
malformed digest, and a fully well-formed document all carry the same coverage
value. Completeness of the declared fields is therefore invisible at that layer.
This module makes it visible. It does so without ranking, because coverage is
already excluded from the priority ordering key at every precedence, and this
record is never read by the priority layer at all.

STATE
-----
One state per candidate, from a closed enumeration, by the fixed precedence in
STATE_PRECEDENCE. The first matching rule wins and the rest are not consulted:

  UNAVAILABLE   no evidence document was declared for this candidate. Not a
                fault, not a pass, not neutrality, not an absent value that
                some later reader may fill in.
  INVALID       a document was declared but is not a readable nine-field
                evidence document: not a mapping, a missing key, a key outside
                the closed set, or a field of the wrong type. Never repaired,
                never partially read.
  UNSUPPORTED   readable, but provider is outside the caller's declared
                allowlist or source_status is outside DECLARED_SOURCE_STATUS.
                Completeness is NOT ASSESSABLE against an undeclared
                vocabulary, so it is not assessed and not folded into
                INCOMPLETE.
  INCOMPLETE    readable and supported; at least one field checked for
                emptiness is empty, or observed_sha256 is not a well-formed
                digest. Every such field is named in reasons.
  COMPLETE      readable, supported, every checked field non-empty, digest well
                formed.

COMPLETE MEANS ONE THING
------------------------
COMPLETE means only that the declared fields were filled in and well formed. It
is not a statement that the evidence is correct, sufficient, trustworthy, recent
or relevant; not that the referenced artifact exists, was read, or validated;
and not that the candidate is better than any other candidate. Two candidates
that share a state are not biologically, structurally or functionally
equivalent, and nothing here compares them.

DECLARED OBSERVATIONS ARE NEVER VERDICTS
----------------------------------------
read_completed and non_admission_reasons are carried as declared and never
change the state. A declared read_completed of false is a *complete* declaration
of an incomplete read; lowering the state for it would convert an observation
into a completeness verdict. validation_status and execution_state are reported
for availability only -- whether a value was declared -- never for what the
value says. Availability is not quality.

ADMISSION STAYS IMMUTABLE AND SEPARATE
--------------------------------------
The admission reference is copied verbatim into its own sub-object and is never
recomputed, re-derived, repaired or defaulted. A malformed admission reference
raises rather than yielding a record: a completeness record cannot exist without
an immutable admission anchor, so this layer can never become a vehicle for a
fabricated admission. An ineligibility_reason present in the reference is copied
and never consulted when classifying, so no evidence state can promote a vetoed
or excluded candidate, and no field of this record carries eligibility.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "COMPLETENESS_DOCUMENT_TYPE",
    "COMPLETENESS_NON_CLAIM",
    "COMPLETENESS_DISPLAY_DISCLAIMER",
    "EVIDENCE_DOCUMENT_KEYS",
    "EMPTINESS_CHECKED_FIELDS",
    "QC_RESULT_FIELDS",
    "ADMISSION_REFERENCE_KEYS",
    "REQUIRED_ADMISSION_KEYS",
    "DECLARED_SOURCE_STATUS",
    "CompletenessState",
    "STATE_PRECEDENCE",
    "ReasonCode",
    "Declared",
    "DigestForm",
    "Recognition",
    "ReadCompletion",
    "QcResultAvailability",
    "CompletenessReason",
    "EvidenceDimensions",
    "AdmissionReference",
    "EvidenceCompletenessRecord",
    "completeness_state",
    "build_evidence_completeness",
    "render_lines",
]

COMPLETENESS_DOCUMENT_TYPE = "cassette_evidence_completeness/1"

#: Emitted verbatim in every record and above every rendering. Never reworded,
#: abridged or parameterized.
COMPLETENESS_NON_CLAIM = (
    "This record reports whether the fields of a declared structure-evidence "
    "document were filled in and well formed, and nothing else.\n"
    "\n"
    "COMPLETE means only that the declared fields were present and well formed. "
    "It is not a claim that the evidence is correct, sufficient, trustworthy, "
    "recent or relevant; not that the referenced artifact exists, was read, or "
    "validated; and not a claim about receptor biology, abundance, "
    "accessibility, expression, membrane context, glycosylation, or dynamics; "
    "not about affinity, KD, kinetics, occupancy, avidity magnitude, binding "
    "probability, efficacy, safety, specificity, or experimental success. "
    "Evidence availability is not evidence quality. Two candidates sharing a "
    "state are not biologically, structurally or functionally equivalent, and "
    "nothing here compares, ranks, scores or orders candidates. This record "
    "confers no eligibility and cannot promote a vetoed or excluded candidate; "
    "the admission reference it carries is copied verbatim and is decided "
    "elsewhere."
)

#: Printed immediately above any rendered completeness block.
COMPLETENESS_DISPLAY_DISCLAIMER = (
    "Evidence completeness - declared-field presence and form only. UNAVAILABLE, "
    "UNSUPPORTED and INVALID are never pass, neutrality or completeness. "
    "COMPLETE is not quality. Equal state is not equivalence. This record "
    "changes no admission, veto, exclusion, tier or ordering."
)

#: The nine serialized evidence fields, in declaration order. The set is closed:
#: a document carrying any other key is INVALID, never partially read.
EVIDENCE_DOCUMENT_KEYS: Tuple[str, ...] = (
    "provider",
    "profile",
    "artifact_id",
    "observed_sha256",
    "source_status",
    "read_completed",
    "execution_state",
    "validation_status",
    "non_admission_reasons",
)

#: The seven fields serialized as text.
_TEXT_FIELDS: Tuple[str, ...] = (
    "provider",
    "profile",
    "artifact_id",
    "observed_sha256",
    "source_status",
    "execution_state",
    "validation_status",
)

#: Checked for emptiness once the document is readable and supported. provider
#: and source_status are absent here because recognition already decided them:
#: an empty string is in neither declared vocabulary.
EMPTINESS_CHECKED_FIELDS: Tuple[str, ...] = (
    "profile",
    "artifact_id",
    "observed_sha256",
    "execution_state",
    "validation_status",
)

#: Reported for availability only -- whether a value was declared. What the
#: value says is never read.
QC_RESULT_FIELDS: Tuple[str, ...] = ("execution_state", "validation_status")

#: Copied verbatim from a serialized priority member or excluded entry. Absence
#: of an optional key is named, never inferred and never defaulted.
ADMISSION_REFERENCE_KEYS: Tuple[str, ...] = (
    "candidate_id",
    "slot_binding_hash",
    "state_result_id",
    "ineligibility_reason",
    "certificate_present",
)

#: Present in both the member and the excluded-entry shapes. Without them there
#: is no immutable anchor and no record is produced.
REQUIRED_ADMISSION_KEYS: Tuple[str, ...] = ("candidate_id", "slot_binding_hash")

#: The declared external status vocabulary, restated locally because this module
#: imports nothing from gotne. A token outside it is UNSUPPORTED.
DECLARED_SOURCE_STATUS: Tuple[str, ...] = ("candidate", "admitted", "rejected")

#: A well-formed digest is lowercase hex of the serialized width. Matched whole.
_DIGEST = re.compile(r"[0-9a-f]{64}")


class CompletenessState(str, Enum):
    """The closed state enumeration. No member carries a magnitude, and the
    order of declaration is not a precedence; STATE_PRECEDENCE is."""

    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNAVAILABLE = "UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID = "INVALID"


#: The fixed rule order. First match wins; later rules are not consulted.
STATE_PRECEDENCE: Tuple[CompletenessState, ...] = (
    CompletenessState.UNAVAILABLE,
    CompletenessState.INVALID,
    CompletenessState.UNSUPPORTED,
    CompletenessState.INCOMPLETE,
    CompletenessState.COMPLETE,
)


class ReasonCode(str, Enum):
    """Closed reason vocabulary. A reason names a declared fact, never a remedy,
    a severity or a judgement."""

    DOCUMENT_ABSENT = "DOCUMENT_ABSENT"
    DOCUMENT_NOT_A_MAPPING = "DOCUMENT_NOT_A_MAPPING"
    DOCUMENT_KEY_MISSING = "DOCUMENT_KEY_MISSING"
    DOCUMENT_KEY_UNKNOWN = "DOCUMENT_KEY_UNKNOWN"
    DOCUMENT_FIELD_TYPE = "DOCUMENT_FIELD_TYPE"
    PROVIDER_NOT_DECLARED = "PROVIDER_NOT_DECLARED"
    SOURCE_STATUS_NOT_DECLARED = "SOURCE_STATUS_NOT_DECLARED"
    FIELD_EMPTY = "FIELD_EMPTY"
    DIGEST_MALFORMED = "DIGEST_MALFORMED"


class Declared(str, Enum):
    """Whether a text field carried a non-empty value. NOT_ASSESSED is a real
    outcome, never a stand-in for PRESENT."""

    PRESENT = "PRESENT"
    EMPTY = "EMPTY"
    NOT_ASSESSED = "NOT_ASSESSED"


class DigestForm(str, Enum):
    """The form of observed_sha256. An empty value is NOT_ASSESSED here because
    emptiness already named it; absence is never encoded as well formed."""

    WELL_FORMED = "WELL_FORMED"
    MALFORMED = "MALFORMED"
    NOT_ASSESSED = "NOT_ASSESSED"


class Recognition(str, Enum):
    """Whether a token is inside a declared vocabulary. Not a quality."""

    DECLARED = "DECLARED"
    NOT_DECLARED = "NOT_DECLARED"
    NOT_ASSESSED = "NOT_ASSESSED"


class ReadCompletion(str, Enum):
    """The declared read_completed observation, carried as declared. It never
    changes the state."""

    DECLARED_TRUE = "DECLARED_TRUE"
    DECLARED_FALSE = "DECLARED_FALSE"
    NOT_ASSESSED = "NOT_ASSESSED"


class QcResultAvailability(str, Enum):
    """Whether the QC-result fields carried values. Availability only; what the
    values say is never read."""

    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    ABSENT = "ABSENT"
    NOT_ASSESSED = "NOT_ASSESSED"


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _require_providers(providers: object) -> None:
    """The caller's allowlist, always explicit. There is no default provider."""
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
# Output records
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class CompletenessReason:
    """One declared fact. field names an evidence key, or is None when the
    reason is about the document as a whole."""

    code: ReasonCode
    field: Optional[str]

    def __post_init__(self) -> None:
        if not isinstance(self.code, ReasonCode):
            raise TypeError(
                f"CompletenessReason.code must be a ReasonCode, "
                f"got {type(self.code).__qualname__}"
            )
        if self.field is not None and type(self.field) is not str:
            raise TypeError("CompletenessReason.field must be a plain str or None")

    def as_dict(self) -> Dict[str, Any]:
        return {"code": self.code.value, "field": self.field}


@dataclass(frozen=True)
class EvidenceDimensions:
    """The reported dimensions. Every one is availability or form; none is a
    quality, a magnitude or an ordering input."""

    field_presence: Tuple[Tuple[str, Declared], ...]
    digest_form: DigestForm
    provider_recognition: Recognition
    source_status_recognition: Recognition
    qc_result_availability: QcResultAvailability
    read_completion: ReadCompletion
    non_admission_reasons: Tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        """A fresh presentation record; reasons verbatim and in declared order."""
        return {
            "field_presence": [
                {"field": name, "declared": value.value} for name, value in self.field_presence
            ],
            "digest_form": self.digest_form.value,
            "provider_recognition": self.provider_recognition.value,
            "source_status_recognition": self.source_status_recognition.value,
            "qc_result_availability": self.qc_result_availability.value,
            "read_completion": self.read_completion.value,
            "non_admission_reasons": list(self.non_admission_reasons),
        }


@dataclass(frozen=True)
class AdmissionReference:
    """The immutable source-admission anchor, copied verbatim. Nothing here is
    recomputed, re-derived, repaired or defaulted, and absent optional keys are
    named in absent_keys rather than silently becoming null facts."""

    candidate_id: str
    slot_binding_hash: str
    state_result_id: Optional[str]
    ineligibility_reason: Optional[str]
    certificate_present: Optional[bool]
    absent_keys: Tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "slot_binding_hash": self.slot_binding_hash,
            "state_result_id": self.state_result_id,
            "ineligibility_reason": self.ineligibility_reason,
            "certificate_present": self.certificate_present,
            "absent_keys": list(self.absent_keys),
        }


@dataclass(frozen=True)
class EvidenceCompletenessRecord:
    """One candidate's descriptive record. The admission reference and the
    completeness report are separate sub-objects and stay separately visible.

    There is deliberately no eligibility, rank, score, order, priority, tier or
    comparison field, and no key whose value is derived from another candidate.
    """

    admission_reference: AdmissionReference
    state: CompletenessState
    dimensions: EvidenceDimensions
    reasons: Tuple[CompletenessReason, ...]
    evidence_document: Optional[Dict[str, Any]]

    def __post_init__(self) -> None:
        if not isinstance(self.admission_reference, AdmissionReference):
            raise TypeError("admission_reference must be an AdmissionReference")
        if not isinstance(self.state, CompletenessState):
            raise TypeError("state must be a CompletenessState")
        if not isinstance(self.dimensions, EvidenceDimensions):
            raise TypeError("dimensions must be an EvidenceDimensions")
        empty = self.state in (CompletenessState.COMPLETE,)
        if empty != (self.reasons == ()):
            raise ValueError(
                "COMPLETE carries no reason and every other state names at least one"
            )

    @property
    def non_claim(self) -> str:
        return COMPLETENESS_NON_CLAIM

    def as_dict(self) -> Dict[str, Any]:
        """A fresh document. Every container is rebuilt, so no caller can reach
        this record's storage through it."""
        return {
            "document_type": COMPLETENESS_DOCUMENT_TYPE,
            "non_claim": COMPLETENESS_NON_CLAIM,
            "admission_reference": self.admission_reference.as_dict(),
            "completeness": {
                "state": self.state.value,
                "dimensions": self.dimensions.as_dict(),
                "reasons": [reason.as_dict() for reason in self.reasons],
            },
            "evidence_document": (
                None if self.evidence_document is None else dict(self.evidence_document)
            ),
        }

    def to_json_bytes(self) -> bytes:
        """Canonical bytes. sort_keys orders object keys only; field_presence,
        reasons and non_admission_reasons keep their declared order."""
        return json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")


# --------------------------------------------------------------------------
# Admission intake
# --------------------------------------------------------------------------
def _admission_reference(reference: object) -> AdmissionReference:
    """Copy the anchor verbatim, or refuse. A malformed anchor yields no record."""
    if not isinstance(reference, Mapping):
        raise TypeError(
            "admission_reference must be a mapping copied from a serialized "
            f"priority member or excluded entry, got {type(reference).__qualname__}"
        )
    unknown = sorted(key for key in reference if key not in ADMISSION_REFERENCE_KEYS)
    if unknown:
        raise ValueError(
            f"admission_reference carries keys outside the copied set: {unknown}"
        )
    for key in REQUIRED_ADMISSION_KEYS:
        if key not in reference:
            raise ValueError(f"admission_reference is missing required key {key!r}")
        if type(reference[key]) is not str or reference[key] == "":
            raise ValueError(f"admission_reference[{key!r}] must be a non-empty str")
    for key in ("state_result_id", "ineligibility_reason"):
        if key in reference and reference[key] is not None and type(reference[key]) is not str:
            raise ValueError(f"admission_reference[{key!r}] must be a str or null")
    if (
        "certificate_present" in reference
        and reference["certificate_present"] is not None
        and type(reference["certificate_present"]) is not bool
    ):
        raise ValueError("admission_reference['certificate_present'] must be a bool or null")
    absent = tuple(key for key in ADMISSION_REFERENCE_KEYS if key not in reference)
    return AdmissionReference(
        candidate_id=reference["candidate_id"],
        slot_binding_hash=reference["slot_binding_hash"],
        state_result_id=reference.get("state_result_id"),
        ineligibility_reason=reference.get("ineligibility_reason"),
        certificate_present=reference.get("certificate_present"),
        absent_keys=absent,
    )


# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------
def _unassessed_presence() -> Tuple[Tuple[str, Declared], ...]:
    return tuple((name, Declared.NOT_ASSESSED) for name in EMPTINESS_CHECKED_FIELDS)


def _unassessed_dimensions(
    *,
    provider_recognition: Recognition = Recognition.NOT_ASSESSED,
    source_status_recognition: Recognition = Recognition.NOT_ASSESSED,
    read_completion: ReadCompletion = ReadCompletion.NOT_ASSESSED,
    non_admission_reasons: Tuple[str, ...] = (),
) -> EvidenceDimensions:
    return EvidenceDimensions(
        field_presence=_unassessed_presence(),
        digest_form=DigestForm.NOT_ASSESSED,
        provider_recognition=provider_recognition,
        source_status_recognition=source_status_recognition,
        qc_result_availability=QcResultAvailability.NOT_ASSESSED,
        read_completion=read_completion,
        non_admission_reasons=non_admission_reasons,
    )


def _readable_reasons(document: Mapping) -> List[CompletenessReason]:
    """Shape and type faults, in declared key order then sorted unknown keys."""
    reasons: List[CompletenessReason] = []
    for key in EVIDENCE_DOCUMENT_KEYS:
        if key not in document:
            reasons.append(CompletenessReason(ReasonCode.DOCUMENT_KEY_MISSING, key))
    for key in sorted(str(key) for key in document):
        if key not in EVIDENCE_DOCUMENT_KEYS:
            reasons.append(CompletenessReason(ReasonCode.DOCUMENT_KEY_UNKNOWN, key))
    if reasons:
        return reasons
    for key in _TEXT_FIELDS:
        if type(document[key]) is not str:
            reasons.append(CompletenessReason(ReasonCode.DOCUMENT_FIELD_TYPE, key))
    if type(document["read_completed"]) is not bool:
        reasons.append(CompletenessReason(ReasonCode.DOCUMENT_FIELD_TYPE, "read_completed"))
    declared = document["non_admission_reasons"]
    if type(declared) not in (list, tuple) or any(type(item) is not str for item in declared):
        reasons.append(
            CompletenessReason(ReasonCode.DOCUMENT_FIELD_TYPE, "non_admission_reasons")
        )
    return reasons


def _qc_availability(document: Mapping) -> QcResultAvailability:
    declared = tuple(name for name in QC_RESULT_FIELDS if document[name] != "")
    if len(declared) == len(QC_RESULT_FIELDS):
        return QcResultAvailability.AVAILABLE
    if declared:
        return QcResultAvailability.PARTIAL
    return QcResultAvailability.ABSENT


def _classify(
    document: object, providers: Tuple[str, ...]
) -> Tuple[CompletenessState, EvidenceDimensions, Tuple[CompletenessReason, ...]]:
    """The total classifier. Rules are applied in STATE_PRECEDENCE order and the
    first match returns; no later rule can override or soften it."""
    if document is None:
        return (
            CompletenessState.UNAVAILABLE,
            _unassessed_dimensions(),
            (CompletenessReason(ReasonCode.DOCUMENT_ABSENT, None),),
        )
    if not isinstance(document, Mapping):
        return (
            CompletenessState.INVALID,
            _unassessed_dimensions(),
            (CompletenessReason(ReasonCode.DOCUMENT_NOT_A_MAPPING, None),),
        )
    faults = _readable_reasons(document)
    if faults:
        return CompletenessState.INVALID, _unassessed_dimensions(), tuple(faults)

    # Readable from here on: the declared observations are carried as declared.
    read_completion = (
        ReadCompletion.DECLARED_TRUE
        if document["read_completed"]
        else ReadCompletion.DECLARED_FALSE
    )
    carried = tuple(document["non_admission_reasons"])
    provider_recognition = (
        Recognition.DECLARED if document["provider"] in providers else Recognition.NOT_DECLARED
    )
    source_status_recognition = (
        Recognition.DECLARED
        if document["source_status"] in DECLARED_SOURCE_STATUS
        else Recognition.NOT_DECLARED
    )
    unsupported: List[CompletenessReason] = []
    if provider_recognition is Recognition.NOT_DECLARED:
        unsupported.append(CompletenessReason(ReasonCode.PROVIDER_NOT_DECLARED, "provider"))
    if source_status_recognition is Recognition.NOT_DECLARED:
        unsupported.append(
            CompletenessReason(ReasonCode.SOURCE_STATUS_NOT_DECLARED, "source_status")
        )
    if unsupported:
        # Completeness is not assessable against an undeclared vocabulary, so it
        # is left NOT_ASSESSED rather than folded into INCOMPLETE.
        return (
            CompletenessState.UNSUPPORTED,
            _unassessed_dimensions(
                provider_recognition=provider_recognition,
                source_status_recognition=source_status_recognition,
                read_completion=read_completion,
                non_admission_reasons=carried,
            ),
            tuple(unsupported),
        )

    presence = tuple(
        (name, Declared.PRESENT if document[name] != "" else Declared.EMPTY)
        for name in EMPTINESS_CHECKED_FIELDS
    )
    digest = document["observed_sha256"]
    if digest == "":
        # Emptiness already names it; absence is never reported as well formed.
        digest_form = DigestForm.NOT_ASSESSED
    elif _DIGEST.fullmatch(digest) is None:
        digest_form = DigestForm.MALFORMED
    else:
        digest_form = DigestForm.WELL_FORMED
    dimensions = EvidenceDimensions(
        field_presence=presence,
        digest_form=digest_form,
        provider_recognition=provider_recognition,
        source_status_recognition=source_status_recognition,
        qc_result_availability=_qc_availability(document),
        read_completion=read_completion,
        non_admission_reasons=carried,
    )

    reasons = [
        CompletenessReason(ReasonCode.FIELD_EMPTY, name)
        for name, value in presence
        if value is Declared.EMPTY
    ]
    if digest_form is DigestForm.MALFORMED:
        reasons.append(CompletenessReason(ReasonCode.DIGEST_MALFORMED, "observed_sha256"))
    if reasons:
        return CompletenessState.INCOMPLETE, dimensions, tuple(reasons)
    return CompletenessState.COMPLETE, dimensions, ()


def completeness_state(document: object, *, providers: Tuple[str, ...]) -> CompletenessState:
    """The state of one serialized evidence document, or UNAVAILABLE for None.

    Pure and total. providers is the caller's declared allowlist and is required.
    """
    _require_providers(providers)
    return _classify(document, tuple(providers))[0]


def build_evidence_completeness(
    admission_reference: object,
    evidence_document: object,
    *,
    providers: Tuple[str, ...],
) -> EvidenceCompletenessRecord:
    """One descriptive record. Pure, read-only and deterministic.

    ``admission_reference`` is a mapping copied from a serialized priority member
    or excluded entry; it is carried verbatim and a malformed one raises rather
    than yielding a record. ``evidence_document`` is the serialized nine-field
    evidence mapping, or None when no evidence was declared. ``providers`` is
    the caller's declared allowlist and has no default.

    The admission reference is never consulted while classifying, so no evidence
    state can change any admission, veto, exclusion, tier or ordering.
    """
    _require_providers(providers)
    anchor = _admission_reference(admission_reference)
    state, dimensions, reasons = _classify(evidence_document, tuple(providers))
    carried = (
        dict(evidence_document) if isinstance(evidence_document, Mapping) else None
    )
    return EvidenceCompletenessRecord(
        admission_reference=anchor,
        state=state,
        dimensions=dimensions,
        reasons=reasons,
        evidence_document=carried,
    )


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def render_lines(record: EvidenceCompletenessRecord) -> List[str]:
    """Fresh display lines. The non-claim statement and the disclaimer come
    first; a non-record is refused rather than rendered."""
    if not isinstance(record, EvidenceCompletenessRecord):
        raise TypeError(
            "record must be an EvidenceCompletenessRecord, got "
            f"{type(record).__qualname__}"
        )
    document = record.as_dict()
    if document["non_claim"] != COMPLETENESS_NON_CLAIM:
        raise ValueError("the non-claim statement is absent or altered; nothing is rendered")
    lines = COMPLETENESS_NON_CLAIM.split("\n") + ["", COMPLETENESS_DISPLAY_DISCLAIMER, ""]
    anchor = record.admission_reference
    lines.append(f"candidate {anchor.candidate_id}  state {record.state.value}")
    lines.append(f"  admission ineligibility_reason {anchor.ineligibility_reason}")
    for reason in record.reasons:
        lines.append(f"  reason {reason.code.value} {reason.field}")
    return lines
