"""GOTNE demo candidate manifest (v0.3.1): caller-side intake for three slots.

SCOPE (demo_candidate_manifest/1)
---------------------------------
An intake/declaration layer strictly upstream of evaluate_candidate_batch. It
records caller-declared candidate labels and their assignment to the three
declared slots, forms a bounded set of three-slot combinations, and maps each
combination to one public CandidateDeclaration. It evaluates nothing, selects
nothing, scores nothing, ranks nothing and reads nothing.

It may read cassette_candidate_batch (for CandidateDeclaration), cassette_slots,
cassette_state and cassette_schema. It MUST NOT import cassette_frames,
cassette_budget, cassette_closure, cassette_node, cassette_slot_ledger,
cassette_candidate_priority, any Phase 4 or Phase 5 module, or anything under
the structure_audit tree. There is deliberately no loader: nothing here reads a
path, a file, a notebook or a provider output, and no argument, option or flag
can cause one to be read.

THE DECISIVE MAPPING RULE
-------------------------
A declared candidate label becomes SlotAssignment.target_id, never module_id.
validate_slot_binding requires slot k to name the module at cassette position k,
so module_id is read from cfg.cassettes[0].ordered_modules[k] at mapping time
and is never declared by a manifest. policy is cfg.policy, because AP-17
requires the two to be equal. This module does not call validate_slot_binding;
the unchanged batch producer does that at its own boundary.

LABELS ARE OPAQUE
-----------------
A candidate label is an identifier and nothing more. It is never parsed, split,
resolved, dereferenced or read as a sequence, a structure, a coordinate, a
confidence value, a file or a provider identifier. A label repeated across
different slots is permitted, because OQ-9 permits a repeated target_id. Whether
a label names a target the caller's EvaluationContext carries is not knowable
here and is not checked: this module never inspects context.targets, so a label
with no target reaches the kernel as an ordinary declared input and the kernel's
own outcome stands.

SLOTS AND COMBINATIONS
----------------------
Slot order is SLOT_IDS on every construction, so a request's own key order is
never read and no caller input can sort, pool or collapse the slots. Candidate
order inside a slot is the caller's order, preserved exactly. Combination order
is explicit: the declared list order, or, under CARTESIAN_PRODUCT, the odometer
order of the three candidate lists with slot_1 as the most significant position.
Nothing is ever ordered by label, candidate id, slot, source, annotation, hash
or length.

ANNOTATION
----------
source_annotation is carried verbatim and consumed by nothing. It never enters a
candidate id, a slot choice, a binding, a declaration, or any order. Two
manifests differing only in it emit byte-identical declarations.

OUTPUT
------
DemoCandidateManifest is immutable. as_dict() is the document and to_json_bytes()
its canonical serialization; from_dict re-derives every derived field, including
the CARTESIAN_PRODUCT combination list, and refuses any difference.
to_candidate_declarations maps the manifest to a tuple of public
CandidateDeclaration objects in manifest combination order.

ERRORS
  DemoCandidateManifestError(ValueError) with .code, .reason, .slot and .field.
  .code is closed: CONTRACT_INVALID for a malformed request, MANIFEST_INVALID for
  a document that does not re-derive. .reason is closed to REFUSAL_REASONS. No
  partial manifest exists.
"""

from __future__ import annotations

import itertools
import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .cassette_candidate_batch import CandidateDeclaration
from .cassette_schema import CassetteConfig
from .cassette_slots import SLOT_IDS, CassetteSlotBinding, SlotAssignment, SlotId
from .cassette_state import EngagementLabel, EvaluationContext

__all__ = [
    "MANIFEST_DOCUMENT_TYPE",
    "MANIFEST_NON_CLAIM",
    "MAX_ANNOTATION_LENGTH",
    "CONTRACT_INVALID",
    "MANIFEST_INVALID",
    "REFUSAL_REASONS",
    "DemoCandidateManifestError",
    "Presence",
    "CombinationSource",
    "SlotChoice",
    "SlotCandidates",
    "Combination",
    "DemoCandidateManifest",
    "declare_candidate_manifest",
    "cartesian_combinations",
    "to_candidate_declarations",
]

MANIFEST_DOCUMENT_TYPE = "demo_candidate_manifest/1"

#: Emitted verbatim in every document and re-derived on load.
MANIFEST_NON_CLAIM = (
    "This manifest records caller-declared candidate labels and their assignment "
    "to three declared slots. A label is an opaque identifier: it is never "
    "parsed, resolved, dereferenced, or read as a sequence, a structure, a file, "
    "or a provider identifier.\n"
    "\n"
    "The manifest makes no claim about sequence quality, structure, affinity, "
    "binding, avidity magnitude, expression, specificity, activity, "
    "accessibility, safety, probability, biological performance, or experimental "
    "outcome. It selects nothing, scores nothing, ranks nothing, and predicts "
    "nothing. Whether a declared combination is admissible is decided entirely "
    "by the unchanged Phase 2 kernel downstream, and a manifest entry is not "
    "evidence that it will be."
)

#: A bound on the carried annotation. It bounds text length only and is not a
#: threshold on any declared value.
MAX_ANNOTATION_LENGTH = 1000

CONTRACT_INVALID = "CONTRACT_INVALID"
MANIFEST_INVALID = "MANIFEST_INVALID"

#: Closed. Every refusal names exactly one of these; none is a fallback.
REFUSAL_REASONS: Tuple[str, ...] = (
    "INVALID_LABEL",
    "EMPTY_SLOT_CANDIDATE_LIST",
    "DUPLICATE_CANDIDATE_LABEL",
    "MISSING_SLOT",
    "SLOT_RECORD_MISNAMED",
    "DUPLICATE_SLOT",
    "CHOICE_PRESENCE_INCONSISTENT",
    "UNDECLARED_CANDIDATE_REFERENCE",
    "DUPLICATE_COMBINATION",
    "EMPTY_COMBINATION_LIST",
    "DUPLICATE_CANDIDATE_ID",
    "COMBINATION_SOURCE_AMBIGUOUS",
    "MAX_COMBINATIONS_EXCEEDED",
    "UNKNOWN_FIELD",
    "DUPLICATE_JSON_KEY",
    "NOT_CANONICAL_BYTES",
    "MALFORMED_DOCUMENT",
    "NON_CLAIM_ALTERED",
    "CASSETTE_ARITY_UNSUPPORTED",
)

#: Reused verbatim from target_slot_declaration/1.
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")

_DOCUMENT_FIELDS = (
    "document_type",
    "non_claim",
    "scenario_id",
    "primary_context_ref",
    "order",
    "slots",
    "combination_source",
    "max_combinations",
    "candidate_id_prefix",
    "combinations",
    "source_annotation",
)
_SLOT_FIELDS = ("slot", "candidates")
_CHOICE_FIELDS = ("presence", "label")
_COMBINATION_FIELDS = ("candidate_id", "choices")


class DemoCandidateManifestError(ValueError):
    """Malformed request or document. No partial manifest exists."""

    def __init__(self, code, reason, message, *, slot=None, field=None):
        if code not in (CONTRACT_INVALID, MANIFEST_INVALID):
            raise AssertionError(f"unknown error code {code!r}")
        if reason not in REFUSAL_REASONS:
            raise AssertionError(f"unknown refusal reason {reason!r}")
        self.code, self.reason, self.slot, self.field = code, reason, slot, field
        self.diagnostics = [
            {
                "severity": "error",
                "code": code,
                "reason": reason,
                "message": message,
                "slot": slot,
                "field": field,
            }
        ]
        super().__init__(f"{code}/{reason}: {message}")


def _contract(reason, message, *, slot=None, field=None):
    return DemoCandidateManifestError(CONTRACT_INVALID, reason, message, slot=slot, field=field)


def _invalid(reason, message, *, slot=None, field=None):
    return DemoCandidateManifestError(MANIFEST_INVALID, reason, message, slot=slot, field=field)


class Presence(str, Enum):
    """Whether a slot choice names a candidate or declares no engagement.
    Absence is always named, never a bare null and never an omitted position."""

    CANDIDATE = "CANDIDATE"
    UNENGAGED = "UNENGAGED"


class CombinationSource(str, Enum):
    """How the combination list came about. Exactly one mode is declared."""

    DECLARED_LIST = "DECLARED_LIST"
    CARTESIAN_PRODUCT = "CARTESIAN_PRODUCT"


def _label(value, reason, what, *, slot=None, error=_contract):
    if type(value) is not str or _LABEL.fullmatch(value) is None:
        raise error(
            reason,
            f"{what} must be 1-100 label characters starting with a letter or digit; "
            "a candidate label is opaque and is never parsed or resolved",
            slot=slot,
            field=what,
        )
    return value


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class SlotChoice:
    """One slot's choice inside one combination. presence/label agreement mirrors
    OQ-1 exactly as SlotAssignment does, so the projection can neither widen nor
    narrow what the public constructor already refuses."""

    presence: Presence
    label: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.presence, Presence):
            raise _contract(
                "CHOICE_PRESENCE_INCONSISTENT",
                f"SlotChoice.presence must be a Presence, got {type(self.presence).__qualname__}",
                field="presence",
            )
        if self.presence is Presence.CANDIDATE:
            _label(self.label, "CHOICE_PRESENCE_INCONSISTENT", "SlotChoice.label")
        elif self.label is not None:
            raise _contract(
                "CHOICE_PRESENCE_INCONSISTENT",
                f"an {Presence.UNENGAGED.value} choice must have label None",
                field="label",
            )

    def as_dict(self) -> Dict[str, Any]:
        return {"presence": self.presence.value, "label": self.label}


@dataclass(frozen=True)
class SlotCandidates:
    """One slot's ordered, bounded candidate list. The record restates its own
    slot; a record whose slot disagrees with its position is refused."""

    slot: SlotId
    candidates: Tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.slot, SlotId):
            raise _contract(
                "SLOT_RECORD_MISNAMED",
                f"SlotCandidates.slot must be a SlotId, got {type(self.slot).__qualname__}",
                field="slot",
            )
        if type(self.candidates) not in (list, tuple):
            raise _contract(
                "EMPTY_SLOT_CANDIDATE_LIST",
                "SlotCandidates.candidates must be a list or tuple",
                slot=self.slot.value,
                field="candidates",
            )
        if not self.candidates:
            raise _contract(
                "EMPTY_SLOT_CANDIDATE_LIST",
                f"slot {self.slot.value!r} declares no candidate; an empty list is never "
                "defaulted, padded or inherited from another slot",
                slot=self.slot.value,
                field="candidates",
            )
        for value in self.candidates:
            _label(value, "INVALID_LABEL", "candidate", slot=self.slot.value)
        seen: List[str] = []
        for value in self.candidates:
            if value in seen:
                raise _contract(
                    "DUPLICATE_CANDIDATE_LABEL",
                    f"candidate {value!r} is declared twice in slot {self.slot.value!r}",
                    slot=self.slot.value,
                    field="candidates",
                )
            seen.append(value)
        object.__setattr__(self, "candidates", tuple(self.candidates))

    def as_dict(self) -> Dict[str, Any]:
        return {"slot": self.slot.value, "candidates": list(self.candidates)}


@dataclass(frozen=True)
class Combination:
    """One three-slot combination and the candidate id it will carry. choices are
    in SLOT_IDS order; there is no sequence field to permute or shorten."""

    candidate_id: str
    choices: Tuple[SlotChoice, ...]

    def __post_init__(self) -> None:
        _label(self.candidate_id, "INVALID_LABEL", "Combination.candidate_id")
        if type(self.choices) not in (list, tuple) or len(self.choices) != len(SLOT_IDS):
            raise _contract(
                "CHOICE_PRESENCE_INCONSISTENT",
                f"a combination declares exactly {len(SLOT_IDS)} choices, in "
                f"{[s.value for s in SLOT_IDS]} order",
                field="choices",
            )
        for choice in self.choices:
            if not isinstance(choice, SlotChoice):
                raise _contract(
                    "CHOICE_PRESENCE_INCONSISTENT",
                    f"a choice must be a SlotChoice, got {type(choice).__qualname__}",
                    field="choices",
                )
        object.__setattr__(self, "choices", tuple(self.choices))

    @property
    def key(self) -> Tuple[Tuple[str, Optional[str]], ...]:
        """The identity a duplicate check compares. The candidate id is not part
        of it: two ids for the same three choices are one combination twice."""
        return tuple((c.presence.value, c.label) for c in self.choices)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "choices": [choice.as_dict() for choice in self.choices],
        }


@dataclass(frozen=True)
class DemoCandidateManifest:
    """An immutable demo_candidate_manifest/1 document.

    Construct through declare_candidate_manifest or from_dict; both re-derive
    every derived field and refuse any difference.
    """

    scenario_id: str
    primary_context_ref: str
    slots: Tuple[SlotCandidates, ...]
    combination_source: CombinationSource
    max_combinations: int
    candidate_id_prefix: Optional[str]
    combinations: Tuple[Combination, ...]
    source_annotation: str

    def __post_init__(self) -> None:
        _label(self.scenario_id, "INVALID_LABEL", "scenario_id")
        _label(self.primary_context_ref, "INVALID_LABEL", "primary_context_ref")
        if not isinstance(self.combination_source, CombinationSource):
            raise _contract(
                "COMBINATION_SOURCE_AMBIGUOUS",
                "combination_source must be a CombinationSource member",
                field="combination_source",
            )
        if type(self.max_combinations) is not int or isinstance(self.max_combinations, bool):
            raise _contract(
                "MAX_COMBINATIONS_EXCEEDED",
                "max_combinations must be a plain int",
                field="max_combinations",
            )
        if self.max_combinations < 1:
            raise _contract(
                "MAX_COMBINATIONS_EXCEEDED",
                "max_combinations must be at least 1 and is always required",
                field="max_combinations",
            )
        _require_slot_records(self.slots)
        product_mode = self.combination_source is CombinationSource.CARTESIAN_PRODUCT
        if product_mode:
            _label(self.candidate_id_prefix, "INVALID_LABEL", "candidate_id_prefix")
        elif self.candidate_id_prefix is not None:
            raise _contract(
                "COMBINATION_SOURCE_AMBIGUOUS",
                f"candidate_id_prefix belongs to {CombinationSource.CARTESIAN_PRODUCT.value} "
                f"only; a {CombinationSource.DECLARED_LIST.value} manifest declares each id",
                field="candidate_id_prefix",
            )
        if type(self.source_annotation) is not str:
            raise _contract(
                "MALFORMED_DOCUMENT",
                "source_annotation must be a plain str; it is carried verbatim and read by "
                "nothing",
                field="source_annotation",
            )
        if len(self.source_annotation) > MAX_ANNOTATION_LENGTH:
            raise _contract(
                "MALFORMED_DOCUMENT",
                f"source_annotation must be at most {MAX_ANNOTATION_LENGTH} characters",
                field="source_annotation",
            )
        try:
            self.source_annotation.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise _contract(
                "MALFORMED_DOCUMENT",
                f"source_annotation is not encodable as UTF-8: {exc}",
                field="source_annotation",
            ) from None
        _require_combinations(self.combinations, self.slots, self.max_combinations)
        object.__setattr__(self, "slots", tuple(self.slots))
        object.__setattr__(self, "combinations", tuple(self.combinations))
        if product_mode:
            derived = cartesian_combinations(
                self.slots, self.candidate_id_prefix, self.max_combinations
            )
            if tuple(c.as_dict() for c in self.combinations) != tuple(
                c.as_dict() for c in derived
            ):
                raise _invalid(
                    "MALFORMED_DOCUMENT",
                    f"a {CombinationSource.CARTESIAN_PRODUCT.value} combination list is "
                    "derived from the slots and the prefix; a supplied list that differs is "
                    "never trusted, sorted or repaired",
                    field="combinations",
                )

    # -- derived views ----------------------------------------------------
    def slot(self, name) -> SlotCandidates:
        """One slot by name. Positional access is not offered: slots are named."""
        for record in self.slots:
            if record.slot.value == name or record.slot is name:
                return record
        raise _invalid(
            "MISSING_SLOT",
            f"unknown slot {name!r}; the declared slots are {[s.value for s in SLOT_IDS]}",
            field="slot",
        )

    @property
    def non_claim(self) -> str:
        return MANIFEST_NON_CLAIM

    def as_dict(self) -> Dict[str, Any]:
        return {
            "document_type": MANIFEST_DOCUMENT_TYPE,
            "non_claim": MANIFEST_NON_CLAIM,
            "scenario_id": self.scenario_id,
            "primary_context_ref": self.primary_context_ref,
            "order": [s.value for s in SLOT_IDS],
            "slots": [record.as_dict() for record in self.slots],
            "combination_source": self.combination_source.value,
            "max_combinations": self.max_combinations,
            "candidate_id_prefix": self.candidate_id_prefix,
            "combinations": [c.as_dict() for c in self.combinations],
            "source_annotation": self.source_annotation,
        }

    def to_json_bytes(self) -> bytes:
        """Canonical bytes. sort_keys orders object keys only; the order, slots,
        candidates, combinations and choices arrays keep their declared order."""
        return json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")

    # -- reconstruction ---------------------------------------------------
    @classmethod
    def from_dict(cls, data) -> "DemoCandidateManifest":
        """Re-derive a manifest from its document and refuse any difference."""
        if type(data) is not dict:
            raise _invalid("MALFORMED_DOCUMENT", "a manifest must be a JSON object")
        _exact(data, _DOCUMENT_FIELDS, "manifest", error=_invalid)
        if data["document_type"] != MANIFEST_DOCUMENT_TYPE:
            raise _invalid(
                "MALFORMED_DOCUMENT",
                f"document_type must be exactly {MANIFEST_DOCUMENT_TYPE!r}",
                field="document_type",
            )
        if data["non_claim"] != MANIFEST_NON_CLAIM:
            raise _invalid(
                "NON_CLAIM_ALTERED",
                "the non-claim statement is absent or altered",
                field="non_claim",
            )
        if data["order"] != [s.value for s in SLOT_IDS]:
            raise _invalid(
                "MALFORMED_DOCUMENT",
                f"order must be exactly {[s.value for s in SLOT_IDS]}; a supplied order is "
                "never trusted, sorted or normalized",
                field="order",
            )
        source = _member(data["combination_source"], CombinationSource, "combination_source")
        slots = _slot_records_from(data["slots"])
        combinations = _combinations_from(data["combinations"])
        return cls(
            scenario_id=data["scenario_id"],
            primary_context_ref=data["primary_context_ref"],
            slots=slots,
            combination_source=source,
            max_combinations=data["max_combinations"],
            candidate_id_prefix=data["candidate_id_prefix"],
            combinations=combinations,
            source_annotation=data["source_annotation"],
        )

    @classmethod
    def from_json_bytes(cls, raw) -> "DemoCandidateManifest":
        """Parse canonical bytes. Duplicate keys and non-finite tokens are not
        JSON here, and bytes that are not the canonical form are refused."""
        if type(raw) is not bytes:
            raise _invalid("MALFORMED_DOCUMENT", "json_bytes must be bytes")
        manifest = cls.from_dict(_strict(raw))
        if manifest.to_json_bytes() != raw:
            raise _invalid(
                "NOT_CANONICAL_BYTES",
                "bytes are not the canonical serialization of the document",
            )
        return manifest


# --------------------------------------------------------------------------
# Shared validation
# --------------------------------------------------------------------------
def _exact(mapping, fields, what, *, error=_contract, reason="UNKNOWN_FIELD"):
    if type(mapping) is not dict:
        raise error("MALFORMED_DOCUMENT", f"{what} must be a JSON object")
    unknown = sorted(set(mapping) - set(fields))
    if unknown:
        raise error(reason, f"{what} carries unknown fields {unknown}", field=unknown[0])
    missing = [name for name in fields if name not in mapping]
    if missing:
        raise error(
            "MALFORMED_DOCUMENT",
            f"{what} omits required fields {missing}; nothing is defaulted",
            field=missing[0],
        )


def _member(value, enum, what):
    for candidate in enum:
        if value == candidate.value:
            return candidate
    raise _invalid(
        "COMBINATION_SOURCE_AMBIGUOUS" if enum is CombinationSource else "MALFORMED_DOCUMENT",
        f"{what} must be one of {[m.value for m in enum]}, got {value!r}",
        field=what,
    )


def _strict(raw):
    """Parse manifest bytes; duplicate keys and non-finite tokens are refused."""

    def pairs(items):
        result: Dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise _invalid("DUPLICATE_JSON_KEY", f"duplicate JSON key {key!r}", field=key)
            result[key] = value
        return result

    def constant(token):
        raise _invalid("MALFORMED_DOCUMENT", f"non-finite JSON token {token}")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except UnicodeDecodeError as exc:
        raise _invalid("MALFORMED_DOCUMENT", f"not UTF-8 text: {exc}") from None
    except json.JSONDecodeError as exc:
        raise _invalid("MALFORMED_DOCUMENT", f"not a JSON document: {exc}") from None


def _require_slot_records(slots) -> None:
    """Exactly one record per SLOT_IDS name, in SLOT_IDS order."""
    if type(slots) not in (list, tuple):
        raise _contract("MISSING_SLOT", "slots must be a list or tuple of SlotCandidates")
    for record in slots:
        if not isinstance(record, SlotCandidates):
            raise _contract(
                "MISSING_SLOT",
                f"a slot record must be a SlotCandidates, got {type(record).__qualname__}",
            )
    declared = [record.slot for record in slots]
    duplicates = sorted({s.value for s in declared if declared.count(s) > 1})
    if duplicates:
        raise _contract(
            "DUPLICATE_SLOT",
            f"slot declared more than once: {duplicates}",
            slot=duplicates[0],
            field="slots",
        )
    missing = [s.value for s in SLOT_IDS if s not in declared]
    if missing:
        raise _contract(
            "MISSING_SLOT",
            f"every slot must be declared explicitly; {missing} absent",
            slot=missing[0],
            field="slots",
        )
    if declared != list(SLOT_IDS):
        raise _contract(
            "SLOT_RECORD_MISNAMED",
            f"slot records must appear in {[s.value for s in SLOT_IDS]} order; order is "
            "derived from SLOT_IDS and a supplied order is never trusted or sorted",
            slot=declared[0].value,
            field="slots",
        )


def _require_combinations(combinations, slots, max_combinations) -> None:
    if type(combinations) not in (list, tuple):
        raise _contract(
            "EMPTY_COMBINATION_LIST", "combinations must be a list or tuple of Combination"
        )
    for combination in combinations:
        if not isinstance(combination, Combination):
            raise _contract(
                "EMPTY_COMBINATION_LIST",
                f"a combination must be a Combination, got {type(combination).__qualname__}",
            )
    if not combinations:
        raise _contract(
            "EMPTY_COMBINATION_LIST",
            "a manifest declares at least one combination; an empty list is never defaulted",
            field="combinations",
        )
    if len(combinations) > max_combinations:
        raise _contract(
            "MAX_COMBINATIONS_EXCEEDED",
            f"{len(combinations)} combinations exceed the declared maximum "
            f"{max_combinations}; nothing is truncated",
            field="combinations",
        )
    declared = {record.slot: record.candidates for record in slots}
    for combination in combinations:
        for index, choice in enumerate(combination.choices):
            slot = SLOT_IDS[index]
            if choice.presence is Presence.CANDIDATE and choice.label not in declared[slot]:
                raise _contract(
                    "UNDECLARED_CANDIDATE_REFERENCE",
                    f"combination {combination.candidate_id!r} names candidate "
                    f"{choice.label!r} in slot {slot.value!r}, which that slot does not declare",
                    slot=slot.value,
                    field="choices",
                )
    keys: List[Any] = []
    for combination in combinations:
        if combination.key in keys:
            raise _contract(
                "DUPLICATE_COMBINATION",
                f"the choices of {combination.candidate_id!r} repeat an earlier combination; "
                "a duplicate is refused, never deduplicated",
                field="combinations",
            )
        keys.append(combination.key)
    ids = [combination.candidate_id for combination in combinations]
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise _contract(
            "DUPLICATE_CANDIDATE_ID",
            f"duplicate candidate_id: {repeated}",
            field="candidate_id",
        )


def _slot_records_from(value) -> Tuple[SlotCandidates, ...]:
    if type(value) is not list:
        raise _invalid("MISSING_SLOT", "slots must be a JSON array", field="slots")
    records = []
    for position, entry in enumerate(value):
        _exact(entry, _SLOT_FIELDS, f"slots[{position}]", error=_invalid)
        name = entry["slot"]
        matched = [s for s in SLOT_IDS if s.value == name]
        if not matched:
            raise _invalid(
                "SLOT_RECORD_MISNAMED",
                f"slots[{position}] names unknown slot {name!r}",
                field="slot",
            )
        candidates = entry["candidates"]
        if type(candidates) is not list:
            raise _invalid(
                "EMPTY_SLOT_CANDIDATE_LIST",
                f"slots[{position}].candidates must be a JSON array",
                slot=name,
                field="candidates",
            )
        records.append(SlotCandidates(matched[0], tuple(candidates)))
    return tuple(records)


def _combinations_from(value) -> Tuple[Combination, ...]:
    if type(value) is not list:
        raise _invalid(
            "EMPTY_COMBINATION_LIST", "combinations must be a JSON array", field="combinations"
        )
    combinations = []
    for position, entry in enumerate(value):
        _exact(entry, _COMBINATION_FIELDS, f"combinations[{position}]", error=_invalid)
        choices = entry["choices"]
        if type(choices) is not list:
            raise _invalid(
                "CHOICE_PRESENCE_INCONSISTENT",
                f"combinations[{position}].choices must be a JSON array",
                field="choices",
            )
        built = []
        for index, choice in enumerate(choices):
            _exact(
                choice,
                _CHOICE_FIELDS,
                f"combinations[{position}].choices[{index}]",
                error=_invalid,
            )
            built.append(
                SlotChoice(_member(choice["presence"], Presence, "presence"), choice["label"])
            )
        combinations.append(Combination(entry["candidate_id"], tuple(built)))
    return tuple(combinations)


# --------------------------------------------------------------------------
# Construction
# --------------------------------------------------------------------------
def cartesian_combinations(slots, candidate_id_prefix, max_combinations):
    """The product of the three candidate lists, in odometer order with slot_1 as
    the most significant position. Pure and derived; nothing is sorted.

    The i-th combination takes candidate_id f"{prefix}-{i}" with a plain 0-based
    decimal index in product order. That is a declared template, not a generated
    identifier: no counter, clock, randomness, hash or path participates. The
    product emits only CANDIDATE choices; an UNENGAGED slot is declared
    explicitly and never produced here.
    """
    _require_slot_records(slots)
    _label(candidate_id_prefix, "INVALID_LABEL", "candidate_id_prefix")
    if type(max_combinations) is not int or isinstance(max_combinations, bool):
        raise _contract(
            "MAX_COMBINATIONS_EXCEEDED",
            "max_combinations must be a plain int",
            field="max_combinations",
        )
    lists = [record.candidates for record in slots]
    cardinality = 1
    for entry in lists:
        cardinality = cardinality * len(entry)
    if cardinality > max_combinations:
        raise _contract(
            "MAX_COMBINATIONS_EXCEEDED",
            f"the product of the declared candidate lists holds {cardinality} combinations, "
            f"above the declared maximum {max_combinations}; nothing is truncated or sampled",
            field="max_combinations",
        )
    # itertools.product varies the rightmost position fastest, so slot_1 is the
    # most significant position, exactly as the contract states.
    return tuple(
        Combination(
            f"{candidate_id_prefix}-{index}",
            tuple(SlotChoice(Presence.CANDIDATE, label) for label in labels),
        )
        for index, labels in enumerate(itertools.product(*lists))
    )


def declare_candidate_manifest(
    *,
    scenario_id,
    primary_context_ref,
    slots,
    combination_source,
    max_combinations,
    combinations,
    candidate_id_prefix,
    source_annotation,
):
    """Declare one manifest. Pure: reads nothing and selects nothing.

    Every keyword is required; None means explicitly not declared, never a
    default. ``slots`` maps every SLOT_IDS name to that slot's ordered candidate
    tuple; SLOT_IDS drives the iteration, so the mapping's own key order is never
    read and no request can reorder, pool or collapse the slots.

    Exactly one combination mode is declared. Under DECLARED_LIST, combinations
    is the caller's ordered list and candidate_id_prefix is None. Under
    CARTESIAN_PRODUCT, combinations is None and candidate_id_prefix is required;
    the product is derived here and stored explicitly.
    """
    if type(slots) is not dict:
        raise _contract(
            "MISSING_SLOT", "slots must be a mapping from every slot name to its candidates"
        )
    names = {s.value for s in SLOT_IDS}
    unknown = sorted(set(slots) - names)
    if unknown:
        raise _contract(
            "UNKNOWN_FIELD",
            f"unknown slot names {unknown}; the declared slots are {sorted(names)}",
            slot=unknown[0],
            field="slots",
        )
    missing = [s.value for s in SLOT_IDS if s.value not in slots]
    if missing:
        raise _contract(
            "MISSING_SLOT",
            f"every slot must be declared explicitly; {missing} absent from the request",
            slot=missing[0],
            field="slots",
        )
    records = tuple(SlotCandidates(s, tuple(slots[s.value])) for s in SLOT_IDS)
    source = combination_source
    if not isinstance(source, CombinationSource):
        raise _contract(
            "COMBINATION_SOURCE_AMBIGUOUS",
            f"combination_source must be a CombinationSource member, got {source!r}",
            field="combination_source",
        )
    if source is CombinationSource.CARTESIAN_PRODUCT:
        if combinations is not None:
            raise _contract(
                "COMBINATION_SOURCE_AMBIGUOUS",
                f"a {source.value} manifest derives its combinations; supplying a list as "
                "well is ambiguous and is never merged",
                field="combinations",
            )
        derived = cartesian_combinations(records, candidate_id_prefix, max_combinations)
    else:
        if candidate_id_prefix is not None:
            raise _contract(
                "COMBINATION_SOURCE_AMBIGUOUS",
                f"a {source.value} manifest declares each candidate_id; a prefix belongs to "
                f"{CombinationSource.CARTESIAN_PRODUCT.value} only",
                field="candidate_id_prefix",
            )
        if combinations is None:
            raise _contract(
                "COMBINATION_SOURCE_AMBIGUOUS",
                f"a {source.value} manifest requires an explicit combination list",
                field="combinations",
            )
        derived = tuple(combinations)
    return DemoCandidateManifest(
        scenario_id=scenario_id,
        primary_context_ref=primary_context_ref,
        slots=records,
        combination_source=source,
        max_combinations=max_combinations,
        candidate_id_prefix=candidate_id_prefix,
        combinations=derived,
        source_annotation=source_annotation,
    )


# --------------------------------------------------------------------------
# Mapping to the public path
# --------------------------------------------------------------------------
def to_candidate_declarations(manifest, cfg, context):
    """Map the manifest to public CandidateDeclaration objects, in manifest order.

    ``cfg`` and ``context`` are the caller's own objects, carried by reference
    and unchanged. The only thing read from cfg is cassettes[0].ordered_modules,
    because validate_slot_binding requires slot k to name the module at cassette
    position k; a manifest therefore declares no module_id. policy is cfg.policy,
    because AP-17 requires the two to be equal.

    context.targets is never inspected: whether a declared label names a target
    is not knowable here, and the unchanged kernel decides it downstream. No
    evaluation is invoked and validate_slot_binding is not called.
    """
    if not isinstance(manifest, DemoCandidateManifest):
        raise _contract(
            "MALFORMED_DOCUMENT",
            f"manifest must be a DemoCandidateManifest, got {type(manifest).__qualname__}",
            field="manifest",
        )
    if not isinstance(cfg, CassetteConfig):
        raise _contract(
            "CASSETTE_ARITY_UNSUPPORTED",
            f"cfg must be a CassetteConfig, got {type(cfg).__qualname__}",
            field="cfg",
        )
    if not isinstance(context, EvaluationContext):
        raise _contract(
            "MALFORMED_DOCUMENT",
            f"context must be an EvaluationContext, got {type(context).__qualname__}",
            field="context",
        )
    cassettes = tuple(cfg.cassettes)
    if not cassettes:
        raise _contract(
            "CASSETTE_ARITY_UNSUPPORTED",
            "cfg declares no cassette; a slot binding has no modules to name",
            field="cfg",
        )
    modules = tuple(cassettes[0].ordered_modules)
    if len(modules) != len(SLOT_IDS):
        raise _contract(
            "CASSETTE_ARITY_UNSUPPORTED",
            f"a slot binding requires exactly {len(SLOT_IDS)} ordered modules, cassette has "
            f"{len(modules)}",
            field="cfg",
        )
    declarations = []
    for combination in manifest.combinations:
        assignments = tuple(
            SlotAssignment(
                SLOT_IDS[index],
                modules[index],
                EngagementLabel.ENGAGED
                if choice.presence is Presence.CANDIDATE
                else EngagementLabel.UNENGAGED,
                choice.label,
            )
            for index, choice in enumerate(combination.choices)
        )
        declarations.append(
            CandidateDeclaration(
                candidate_id=combination.candidate_id,
                binding=CassetteSlotBinding(*assignments),
                cfg=cfg,
                policy=cfg.policy,
                context=context,
            )
        )
    return tuple(declarations)
