"""Passive declaration of three ordered, non-interchangeable target slots
(contract target_slot_declaration/1).

Standard library plus the existing canonical serializer and validation helper; no
import-time I/O. This layer declares slot identities and nothing else. It opens no
input file, imports no adapter, reads no notebook state, computes nothing, returns no
measurement or result, and exposes no argument, option, flag or lane through which a
later caller could execute anything. The only file read is this contract's own schema,
through validate_named. There is deliberately no loader: nothing here reads a path.

WHY THIS LAYER EXISTS

  The current contracts carry one scalar target_id per record (candidate_evidence and
  every document that quotes its identity). A later phase may need three ordered
  target-side slots. Nothing here widens, reads, wraps or reinterprets those contracts:
  this document type stands beside them, unreferenced by any of them, so that the slot
  names, their fixed order and the refusal rules are settled before any behaviour
  depends on them. No existing document gains a field and no existing path changes.

SLOTS

  TARGET_SLOTS = ("slot_1", "slot_2", "slot_3"), in exactly this order. The three slots
  are distinct named identities. They are not a set, a pool, a multi-target field, a
  ranked list or a collection whose length may vary.

REFUSAL INVARIANTS (the substance of this layer; each one is enforced below)

  named identity      a slot is a named object key, never a position in a caller-supplied
                      array; each slot record restates its own name and a record whose
                      name disagrees with its key is rejected
  derived order       order is derived from TARGET_SLOTS on every construction; a
                      caller-supplied, permuted, shortened, lengthened or duplicated
                      order is rejected, never trusted and never repaired
  no reordering       no caller input can sort, pool, deduplicate, merge or collapse the
                      slots; TARGET_SLOTS drives every iteration, so the request's own
                      key order is never read
  no privileged slot  slot_1 is not a default, primary, preferred or fallback slot; no
                      slot substitutes for another and no slot is selected when a caller
                      references none
  explicit absence    an absent slot keeps its key and carries one closed absence_reason;
                      absence is never an omitted key, a shortened collection or a bare
                      null without a reason

SLOT CONTENT

  Each slot is either REFERENCED, carrying one opaque external reference_id, or ABSENT,
  carrying one ABSENCE_REASONS member. Exactly one of the two is present and the other
  field is null. The reference identifier is an opaque label: it is never resolved,
  parsed, split, dereferenced, looked up or read, and no evidence, envelope, handoff,
  adapter or notebook document is quoted, embedded or summarized here.

EXECUTION STATUS

  execution_status is fixed to DECLARED_NOT_EXECUTABLE. It is derived from the module
  constant, not from any argument, so no call, option or flag can change it. A later
  phase that wants a different status must edit this module, which is a reviewable
  change; passing data to this layer can never produce one.

OUTPUT

  declare_target_slots returns TargetSlotDeclaration, immutable and held only as its
  canonical bytes (provenance.canonical_json). to_dict() conforms to
  schemas/target_slot_declaration.schema.json and to_json_bytes() is the canonical
  serialization. Slot order lives in the order array, which canonical_json preserves;
  it never depends on object key order. from_dict re-derives every derived field and
  rejects any difference.

ERRORS
  TargetSlotDeclarationError(ValueError) with .code, .slot and .field. The codes are
  closed: CONTRACT_INVALID for a malformed request, DECLARATION_INVALID for a document
  that does not re-derive. No partial declaration exists.
"""
from dataclasses import dataclass
import json
import re

from .provenance import canonical_json
from .validation import validate_named

DOCUMENT_TYPE = "target_slot_declaration/1"
TARGET_SLOTS = ("slot_1", "slot_2", "slot_3")
EXECUTION_STATUS = "DECLARED_NOT_EXECUTABLE"

REFERENCED = "REFERENCED"
ABSENT = "ABSENT"
PRESENCES = (REFERENCED, ABSENT)
# Closed and structural: neither reason describes a domain, a target or an outcome.
ABSENCE_REASONS = ("NO_REFERENCE_SUPPLIED", "REFERENCE_NOT_DECLARABLE_IN_THIS_PHASE")

DOCUMENT_FIELDS = ("document_type", "order", *TARGET_SLOTS, "execution_status")
SLOT_FIELDS = ("slot", "presence", "reference_id", "absence_reason")
# The caller supplies exactly one of these per slot; slot, presence and order are derived.
REQUEST_FIELDS = ("reference_id", "absence_reason")

_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")

CONTRACT_INVALID = "CONTRACT_INVALID"
DECLARATION_INVALID = "DECLARATION_INVALID"


class TargetSlotDeclarationError(ValueError):
    """Malformed request or document. No partial declaration exists."""

    def __init__(self, code, message, *, slot=None, field=None):
        self.code, self.slot, self.field = code, slot, field
        self.diagnostics = [{"severity": "error", "code": code, "message": message,
                             "slot": slot, "field": field}]
        super().__init__(f"{code}: {message}")


def _contract(message, *, slot=None, field=None):
    return TargetSlotDeclarationError(CONTRACT_INVALID, message, slot=slot, field=field)


def _invalid(message, *, slot=None, field=None):
    return TargetSlotDeclarationError(DECLARATION_INVALID, message, slot=slot, field=field)


def _strict(raw):
    """Parse declaration bytes; duplicate keys and non-finite tokens are not JSON here."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise _invalid(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def constant(token):
        raise _invalid(f"non-finite JSON token {token}")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except UnicodeDecodeError as exc:
        raise _invalid(f"not UTF-8 text: {exc}") from None
    except json.JSONDecodeError as exc:
        raise _invalid(f"not a JSON document: {exc}") from None


def _slot_record(name, request):
    """One named slot record, derived from the slot's own name and its single declared field."""
    if type(request) is not dict or len(request) != 1 or not set(request) <= set(REQUEST_FIELDS):
        raise _contract(f"a slot request declares exactly one of {list(REQUEST_FIELDS)}", slot=name)
    if "reference_id" in request:
        reference_id = request["reference_id"]
        if type(reference_id) is not str or _LABEL.fullmatch(reference_id) is None:
            raise _contract("reference_id must be 1-100 label characters starting with a letter or "
                            "digit; it is an opaque identifier and is never resolved or read",
                            slot=name, field="reference_id")
        return {"slot": name, "presence": REFERENCED,
                "reference_id": reference_id, "absence_reason": None}
    reason = request["absence_reason"]
    if not isinstance(reason, str) or reason not in ABSENCE_REASONS:
        raise _contract(f"absence_reason must be one of {list(ABSENCE_REASONS)}",
                        slot=name, field="absence_reason")
    return {"slot": name, "presence": ABSENT, "reference_id": None, "absence_reason": reason}


def _verified(data):
    """Re-derive every derived field of a declaration and reject any difference."""
    if type(data) is not dict:
        raise _invalid("a declaration must be a JSON object")
    try:
        validate_named(data, "target_slot_declaration")
    except ValueError as exc:
        raise _invalid(str(exc)) from None
    if data["document_type"] != DOCUMENT_TYPE:
        raise _invalid(f"document_type must be exactly {DOCUMENT_TYPE!r}", field="document_type")
    # A permuted, shortened, lengthened or duplicated order is a rejection, never a repair.
    if data["order"] != list(TARGET_SLOTS):
        raise _invalid(f"order must be exactly {list(TARGET_SLOTS)}; a caller-supplied order is "
                       "never trusted, sorted or normalized", field="order")
    if data["execution_status"] != EXECUTION_STATUS:
        raise _invalid(f"execution_status is fixed to {EXECUTION_STATUS!r} and no request can "
                       "change it", field="execution_status")
    for name in TARGET_SLOTS:
        slot = data[name]
        if slot["slot"] != name:
            raise _invalid("a slot record must name its own key; slot identity is never positional",
                           slot=name, field="slot")
        referenced = slot["presence"] == REFERENCED
        if referenced != (slot["reference_id"] is not None):
            raise _invalid(f"a slot carries a reference_id exactly when it is {REFERENCED}",
                           slot=name, field="reference_id")
        if referenced == (slot["absence_reason"] is not None):
            raise _invalid(f"a slot carries an absence_reason exactly when it is {ABSENT}; an "
                           "absent slot is never a bare null without a reason",
                           slot=name, field="absence_reason")


@dataclass(frozen=True)
class TargetSlotDeclaration:
    """An immutable target_slot_declaration/1 document, held only as canonical bytes."""

    json_bytes: bytes

    def __post_init__(self):
        if type(self.json_bytes) is not bytes:
            raise _invalid("json_bytes must be bytes")
        data = _strict(self.json_bytes)
        _verified(data)
        if canonical_json(data) != self.json_bytes:
            raise _invalid("bytes are not the canonical serialization of the document")

    @classmethod
    def from_dict(cls, data):
        _verified(data)
        try:
            return cls(canonical_json(data))
        except (TypeError, ValueError) as exc:
            if isinstance(exc, TargetSlotDeclarationError):
                raise
            raise _invalid(f"not a JSON document: {exc}") from None

    @property
    def document_type(self):
        return self.to_dict()["document_type"]

    @property
    def order(self):
        return self.to_dict()["order"]

    @property
    def execution_status(self):
        return self.to_dict()["execution_status"]

    def slot(self, name):
        """One slot by name. Positional access is not offered: slots are named identities."""
        if name not in TARGET_SLOTS:
            raise _invalid(f"unknown slot {name!r}; the declared slots are {list(TARGET_SLOTS)}")
        return self.to_dict()[name]

    def to_dict(self):
        return json.loads(self.json_bytes)

    def to_json_bytes(self):
        return self.json_bytes


def declare_target_slots(slots):
    """Declare the three ordered target slots. Pure: reads nothing and selects nothing.

    ``slots`` maps every name in TARGET_SLOTS to exactly one slot request:

        {"reference_id": <opaque label>}          the slot is REFERENCED
        {"absence_reason": <ABSENCE_REASONS member>}  the slot is ABSENT

    Every name is required. A slot is never omitted, defaulted, inherited from another
    slot or inferred, and the mapping's own iteration order is never read: TARGET_SLOTS
    drives the iteration, so no request can reorder, pool or collapse the slots.
    """
    if type(slots) is not dict:
        raise _contract("slots must be a mapping from every slot name to one slot request")
    unknown = sorted(set(slots) - set(TARGET_SLOTS))
    if unknown:
        raise _contract(f"unknown slot names {unknown}; the declared slots are {list(TARGET_SLOTS)}")
    missing = [name for name in TARGET_SLOTS if name not in slots]
    if missing:
        raise _contract(f"every slot must be declared explicitly; {missing} absent from the request")
    return TargetSlotDeclaration.from_dict({
        "document_type": DOCUMENT_TYPE, "order": list(TARGET_SLOTS),
        "execution_status": EXECUTION_STATUS,
        **{name: _slot_record(name, slots[name]) for name in TARGET_SLOTS},
    })
