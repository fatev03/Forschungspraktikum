"""Read-only collection and manual-selection surface for already-produced artifact
references (contracts notebook_artifact_inventory/1, notebook_artifact_selection/1,
notebook_artifact_handoff/1).

Standard library plus the existing canonical serializer; no import-time I/O. This layer
records references the caller already holds and metadata the caller already declared, and
records which of them a human chose to carry forward. It opens no file, resolves no path,
imports no adapter, starts no subprocess, reaches no network, and executes no evaluation
path. There is deliberately no loader and no discovery: nothing here reads a path, a
directory, a notebook or a producer output, and no argument, option or flag can cause one
to be read.

WHY THIS LAYER EXISTS

  A reader who already has local artifact references and their declared metadata needs a
  deterministic list to look at, and a way to say, by hand, which entries should be
  carried forward into the existing candidate-manifest intake. Collecting and choosing are
  not evaluating. Keeping them in their own contract means the choice is a recorded human
  act with a serialized trail, instead of an inference hidden inside a producer.

WHAT AN ITEM IS

  One item is exactly three declared fields:

    item_id            an opaque label, 1-100 label characters
    reference          opaque reference text, carried verbatim
    declared_metadata  a JSON object, carried verbatim

  reference is never opened, resolved, dereferenced, joined, normalized, existence-checked
  or read; it is text the caller already had. declared_metadata is never parsed,
  interpreted, summarized, unit-converted, thresholded, aggregated or reduced; its keys and
  values reach the document exactly as supplied. This layer therefore cannot tell whether
  an item is good, usable, comparable or relevant, and it reports nothing of the kind.

ENUMERATION AND ORDER

  Inventory order is the caller's supplied list order, preserved exactly. Selection order
  is the caller's supplied identifier order, preserved exactly, and is deliberately not
  re-projected onto inventory order. Nothing is ever sorted, ranked, pooled, grouped,
  deduplicated, filtered, truncated, padded or reordered, by any field or by any value
  inside declared_metadata.

REFUSAL INVARIANTS (each one is enforced below)

  never repaired      a duplicate identifier and an unknown identifier are refusals; they
                      are never deduplicated, dropped, corrected, matched loosely or
                      resolved to a nearest entry
  named emptiness     an empty selection is a valid selection that names its own emptiness;
                      it is never a missing document, a null, or an implicit "take all"
  no automatic choice there is no default, preferred, first, best, top-N or fallback item,
                      and no argument, option or flag selects anything: select_inventory_items
                      takes the identifiers the caller typed and nothing else
  minted-field guard  every field this layer mints is checked against
                      FORBIDDEN_FIELD_SUBSTRINGS, so no score, rank, priority, eligibility,
                      recommendation, automatic-selection or status-of-quality field can be
                      introduced here by a later edit without failing immediately
  linkage checked     a handoff re-checks that its selection was taken from the inventory it
                      is being joined to, rather than trusting the pairing

HANDOFF

  The handoff is reference-only. It names its target seam as the module constant
  HANDOFF_TARGET_SEAM, a string and nothing more: no seam module is imported, no
  CandidateDeclaration, manifest, slot mapping or combination is constructed, and no
  candidate is declared. Mapping selected identifiers to slots and combinations stays a
  separate, explicit step performed by the existing intake seam, which applies its own
  label contract and may refuse an identifier this layer carried verbatim.

  The label pattern below is reused verbatim from target_slot_declaration/1, which the
  existing intake seam also uses, so an identifier accepted here is syntactically shaped
  like a label that seam accepts. That is an observation about text, not an admission, a
  guarantee of acceptance, or a claim about the item.

OUTPUT

  Each document is immutable and held only as its canonical bytes
  (provenance.canonical_json), so no upstream object is aliased, retained or mutated.
  to_dict() returns a fresh object on every call and to_json_bytes() is the canonical
  serialization. from_dict and the bytes constructor re-derive every derived field,
  including the order arrays and the emitted non-claim, and reject any difference.

ERRORS
  NotebookArtifactInventoryError(ValueError) with .code, .reason, .item_id and .field.
  .code is closed: CONTRACT_INVALID for a malformed request, DOCUMENT_INVALID for a
  document that does not re-derive. .reason is closed to REFUSAL_REASONS. No partial
  inventory, selection or handoff exists.
"""
from dataclasses import dataclass
import hashlib
import json
import re

from .provenance import canonical_json

INVENTORY_DOCUMENT_TYPE = "notebook_artifact_inventory/1"
SELECTION_DOCUMENT_TYPE = "notebook_artifact_selection/1"
HANDOFF_DOCUMENT_TYPE = "notebook_artifact_handoff/1"

#: Derived from this constant, never from an argument. No call, option or flag can change
#: it, and it is the only status any of these documents carries.
COLLECTION_STATUS = "COLLECTED_NOT_EVALUATED"

#: Derived from this constant. A handoff is a reference list, never a declaration.
HANDOFF_KIND = "REFERENCE_ONLY"

#: The existing intake seam this handoff is addressed to, as text. Nothing is imported
#: from it and nothing of its is constructed here.
HANDOFF_TARGET_SEAM = "demo_candidate_manifest/1"

#: Emitted verbatim in every document and re-derived on load.
INVENTORY_NON_CLAIM = (
    "This document collects artifact references the caller already held and metadata the "
    "caller already declared, and records identifiers a human selected by hand.\n"
    "\n"
    "Collection is not evaluation and manual selection is not declaration. A reference is "
    "opaque text: it is never opened, resolved, dereferenced, existence-checked or read. "
    "Declared metadata is carried verbatim: it is never parsed, interpreted, converted, "
    "thresholded, aggregated or reduced. Nothing here scores, ranks, sorts by quality, "
    "filters, recommends, admits, vetoes, prioritizes or automatically selects anything, "
    "and no entry is ordered by any value it carries.\n"
    "\n"
    "Presence in this document is not evidence about the item. It carries no claim of "
    "quality, correctness, completeness, usability, comparability, relevance, readiness or "
    "outcome, and it confers no admission, eligibility, priority or standing anywhere "
    "downstream. A selected identifier is a human's stated intent to look further; "
    "whether anything may be declared from it is decided entirely by the separate intake "
    "seam, which applies its own contract and may refuse."
)

#: Printed immediately above any rendering.
INVENTORY_DISPLAY_DISCLAIMER = (
    "Collected references and declared metadata only - no evaluation, no ranking, no "
    "automatic selection. List order is the order supplied. Presence is not evidence "
    "about an item."
)

ITEM_FIELDS = ("item_id", "reference", "declared_metadata")
INVENTORY_FIELDS = ("document_type", "non_claim", "collection_status", "order", "items")
SELECTION_FIELDS = (
    "document_type", "non_claim", "collection_status", "inventory_digest",
    "selected_order", "items",
)
HANDOFF_FIELDS = (
    "document_type", "non_claim", "collection_status", "handoff_kind", "target_seam",
    "inventory_digest", "selection_digest", "selected_order", "items",
)

#: Checked against every field name this layer mints, at construction time, so the
#: no-judgement boundary cannot drift silently. declared_metadata keys are the caller's
#: own text and are deliberately exempt: they are carried verbatim, never read.
FORBIDDEN_FIELD_SUBSTRINGS = (
    "score", "rank", "priority", "eligib", "recommend", "admit", "admission", "veto",
    "select_auto", "auto_select", "quality", "confidence", "tier", "grade", "weight",
)

#: A bound on carried reference text. It bounds text length only and is not a threshold on
#: any declared value.
MAX_REFERENCE_LENGTH = 4096

#: Reused verbatim from target_slot_declaration/1.
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

CONTRACT_INVALID = "CONTRACT_INVALID"
DOCUMENT_INVALID = "DOCUMENT_INVALID"

#: Closed. Every refusal names exactly one of these; none is a fallback.
REFUSAL_REASONS = (
    "INVALID_ITEM_ID",
    "DUPLICATE_ITEM_ID",
    "UNKNOWN_ITEM_ID",
    "DUPLICATE_SELECTED_ID",
    "INVALID_REFERENCE",
    "INVALID_DECLARED_METADATA",
    "UNKNOWN_FIELD",
    "MISSING_FIELD",
    "MINTED_FIELD_FORBIDDEN",
    "ORDER_NOT_DERIVED",
    "SELECTION_INVENTORY_MISMATCH",
    "DUPLICATE_JSON_KEY",
    "NOT_CANONICAL_BYTES",
    "MALFORMED_DOCUMENT",
    "NON_CLAIM_ALTERED",
)

__all__ = [
    "INVENTORY_DOCUMENT_TYPE",
    "SELECTION_DOCUMENT_TYPE",
    "HANDOFF_DOCUMENT_TYPE",
    "COLLECTION_STATUS",
    "HANDOFF_KIND",
    "HANDOFF_TARGET_SEAM",
    "INVENTORY_NON_CLAIM",
    "INVENTORY_DISPLAY_DISCLAIMER",
    "ITEM_FIELDS",
    "INVENTORY_FIELDS",
    "SELECTION_FIELDS",
    "HANDOFF_FIELDS",
    "FORBIDDEN_FIELD_SUBSTRINGS",
    "MAX_REFERENCE_LENGTH",
    "CONTRACT_INVALID",
    "DOCUMENT_INVALID",
    "REFUSAL_REASONS",
    "NotebookArtifactInventoryError",
    "ArtifactInventory",
    "ArtifactSelection",
    "ArtifactHandoff",
    "collect_artifact_inventory",
    "select_inventory_items",
    "build_handoff_manifest",
    "render_inventory_lines",
    "render_selection_lines",
    "notebook_cell_sources",
]


class NotebookArtifactInventoryError(ValueError):
    """Malformed request or document. No partial document exists."""

    def __init__(self, code, reason, message, *, item_id=None, field=None):
        if code not in (CONTRACT_INVALID, DOCUMENT_INVALID):
            raise AssertionError(f"unknown error code {code!r}")
        if reason not in REFUSAL_REASONS:
            raise AssertionError(f"unknown refusal reason {reason!r}")
        self.code, self.reason, self.item_id, self.field = code, reason, item_id, field
        self.diagnostics = [{"severity": "error", "code": code, "reason": reason,
                             "message": message, "item_id": item_id, "field": field}]
        super().__init__(f"{code}/{reason}: {message}")


def _contract(reason, message, *, item_id=None, field=None):
    return NotebookArtifactInventoryError(
        CONTRACT_INVALID, reason, message, item_id=item_id, field=field)


def _invalid(reason, message, *, item_id=None, field=None):
    return NotebookArtifactInventoryError(
        DOCUMENT_INVALID, reason, message, item_id=item_id, field=field)


# --------------------------------------------------------------------------
# Minted-field guard
# --------------------------------------------------------------------------
def _minted_names_are_clean(names, *, where):
    """Refuse any field this layer mints whose name suggests a judgement.

    Runs on every construction rather than in a test only, so the boundary cannot be
    widened by an edit that forgets the test. declared_metadata contents are the caller's
    verbatim text and are never passed in here.
    """
    for name in names:
        lowered = name.lower()
        for forbidden in FORBIDDEN_FIELD_SUBSTRINGS:
            if forbidden in lowered:
                raise _invalid(
                    "MINTED_FIELD_FORBIDDEN",
                    f"{where} field {name!r} carries {forbidden!r}; this layer mints no "
                    "score, rank, priority, eligibility, recommendation, "
                    "automatic-selection or quality-status field",
                    field=name)


for _names, _where in ((ITEM_FIELDS, "item"), (INVENTORY_FIELDS, "inventory"),
                       (SELECTION_FIELDS, "selection"), (HANDOFF_FIELDS, "handoff")):
    _minted_names_are_clean(_names, where=_where)
del _names, _where


# --------------------------------------------------------------------------
# Field checks
# --------------------------------------------------------------------------
def _item_id(value, *, error=_contract, reason="INVALID_ITEM_ID"):
    if type(value) is not str or _LABEL.fullmatch(value) is None:
        raise error(reason,
                    "an item_id must be 1-100 label characters starting with a letter or "
                    "digit; it is an opaque identifier and is never parsed or resolved",
                    field="item_id")
    return value


def _reference(value, item_id, *, error=_contract):
    if type(value) is not str or value == "":
        raise error("INVALID_REFERENCE",
                    "reference must be a non-empty string; it is opaque text and is never "
                    "opened, resolved or read",
                    item_id=item_id, field="reference")
    if len(value) > MAX_REFERENCE_LENGTH:
        raise error("INVALID_REFERENCE",
                    f"reference must be at most {MAX_REFERENCE_LENGTH} characters",
                    item_id=item_id, field="reference")
    if _CONTROL.search(value) is not None:
        raise error("INVALID_REFERENCE",
                    "reference must contain no control character; it is never rewritten, "
                    "stripped or normalized to make it acceptable",
                    item_id=item_id, field="reference")
    return value


def _declared_metadata(value, item_id, *, error=_contract):
    """Accept a JSON object and carry it verbatim. Its contents are never read."""
    if type(value) is not dict:
        raise error("INVALID_DECLARED_METADATA",
                    "declared_metadata must be a JSON object; an empty object is valid and "
                    "is never filled in, defaulted or inherited from another item",
                    item_id=item_id, field="declared_metadata")
    for key in value:
        if type(key) is not str:
            raise error("INVALID_DECLARED_METADATA",
                        "declared_metadata keys must be strings",
                        item_id=item_id, field="declared_metadata")
    return value


def _item_record(raw, *, error=_contract):
    """One item, from exactly the three declared fields. Nothing is derived from content."""
    if type(raw) is not dict:
        raise error("MALFORMED_DOCUMENT", f"an item must be a JSON object, got "
                    f"{type(raw).__qualname__}")
    unknown = sorted(set(raw) - set(ITEM_FIELDS))
    if unknown:
        raise error("UNKNOWN_FIELD",
                    f"unknown item fields {unknown}; an item declares exactly "
                    f"{list(ITEM_FIELDS)}",
                    field=unknown[0])
    missing = [name for name in ITEM_FIELDS if name not in raw]
    if missing:
        raise error("MISSING_FIELD",
                    f"every item field must be declared explicitly; {missing} absent",
                    field=missing[0])
    item_id = _item_id(raw["item_id"], error=error)
    return {
        "item_id": item_id,
        "reference": _reference(raw["reference"], item_id, error=error),
        "declared_metadata": _declared_metadata(
            raw["declared_metadata"], item_id, error=error),
    }


def _items_in_supplied_order(raw_items, *, error=_contract):
    """Validate every item, keep the supplied order exactly, refuse a repeated id."""
    if type(raw_items) not in (list, tuple):
        raise error("MALFORMED_DOCUMENT", "items must be a list or tuple")
    records, seen = [], []
    for raw in raw_items:
        record = _item_record(raw, error=error)
        if record["item_id"] in seen:
            raise error("DUPLICATE_ITEM_ID",
                        f"item_id {record['item_id']!r} is declared twice; a repeated "
                        "identifier is refused, never deduplicated or renamed",
                        item_id=record["item_id"], field="item_id")
        seen.append(record["item_id"])
        records.append(record)
    return records


def _strict(raw, *, reason_owner="document"):
    """Parse document bytes; duplicate keys and non-finite tokens are not JSON here."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise _invalid("DUPLICATE_JSON_KEY", f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def constant(token):
        raise _invalid("MALFORMED_DOCUMENT", f"non-finite JSON token {token}")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except UnicodeDecodeError as exc:
        raise _invalid("MALFORMED_DOCUMENT", f"{reason_owner} is not UTF-8 text: {exc}") from None
    except json.JSONDecodeError as exc:
        raise _invalid("MALFORMED_DOCUMENT",
                       f"{reason_owner} is not a JSON document: {exc}") from None


def _digest(payload):
    """sha256 of already-produced canonical bytes. It identifies bytes, nothing else."""
    return hashlib.sha256(payload).hexdigest()


def _shell(data, fields, document_type):
    """The checks every one of the three documents shares."""
    if type(data) is not dict:
        raise _invalid("MALFORMED_DOCUMENT", "a document must be a JSON object")
    unknown = sorted(set(data) - set(fields))
    if unknown:
        raise _invalid("UNKNOWN_FIELD",
                       f"unknown document fields {unknown}; the declared fields are "
                       f"{list(fields)}", field=unknown[0])
    missing = [name for name in fields if name not in data]
    if missing:
        raise _invalid("MISSING_FIELD", f"missing document fields {missing}",
                       field=missing[0])
    _minted_names_are_clean(data.keys(), where="document")
    if data["document_type"] != document_type:
        raise _invalid("MALFORMED_DOCUMENT",
                       f"document_type must be exactly {document_type!r}",
                       field="document_type")
    if data["non_claim"] != INVENTORY_NON_CLAIM:
        raise _invalid("NON_CLAIM_ALTERED",
                       "non_claim must be emitted verbatim; it is never reworded, "
                       "abridged or parameterized", field="non_claim")
    if data["collection_status"] != COLLECTION_STATUS:
        raise _invalid("MALFORMED_DOCUMENT",
                       f"collection_status is fixed to {COLLECTION_STATUS!r} and no "
                       "request can change it", field="collection_status")


def _verified_items(data, order_field):
    """Re-derive the order array from the items array and reject any difference."""
    records = _items_in_supplied_order(data["items"], error=_invalid)
    for record in records:
        _minted_names_are_clean(record.keys(), where="item")
    if data[order_field] != [record["item_id"] for record in records]:
        raise _invalid("ORDER_NOT_DERIVED",
                       f"{order_field} must be exactly the item_id of each entry of items, "
                       "in the same order; a supplied order is never trusted, sorted or "
                       "normalized", field=order_field)
    return records


def _digest_text(value, field):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise _invalid("MALFORMED_DOCUMENT",
                       f"{field} must be 64 lowercase hex characters", field=field)
    return value


def _verified_inventory(data):
    _shell(data, INVENTORY_FIELDS, INVENTORY_DOCUMENT_TYPE)
    _verified_items(data, "order")


def _verified_selection(data):
    _shell(data, SELECTION_FIELDS, SELECTION_DOCUMENT_TYPE)
    _digest_text(data["inventory_digest"], "inventory_digest")
    _verified_items(data, "selected_order")


def _verified_handoff(data):
    _shell(data, HANDOFF_FIELDS, HANDOFF_DOCUMENT_TYPE)
    if data["handoff_kind"] != HANDOFF_KIND:
        raise _invalid("MALFORMED_DOCUMENT",
                       f"handoff_kind is fixed to {HANDOFF_KIND!r}", field="handoff_kind")
    if data["target_seam"] != HANDOFF_TARGET_SEAM:
        raise _invalid("MALFORMED_DOCUMENT",
                       f"target_seam is fixed to {HANDOFF_TARGET_SEAM!r} and is a name "
                       "only; no seam object is constructed here", field="target_seam")
    _digest_text(data["inventory_digest"], "inventory_digest")
    _digest_text(data["selection_digest"], "selection_digest")
    _verified_items(data, "selected_order")


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class _Document:
    """An immutable document, held only as canonical bytes so nothing upstream is aliased."""

    json_bytes: bytes

    _DOCUMENT_TYPE = None
    _VERIFY = None

    def __post_init__(self):
        if type(self.json_bytes) is not bytes:
            raise _invalid("MALFORMED_DOCUMENT", "json_bytes must be bytes")
        data = _strict(self.json_bytes, reason_owner=type(self)._DOCUMENT_TYPE)
        type(self)._VERIFY(data)
        if canonical_json(data) != self.json_bytes:
            raise _invalid("NOT_CANONICAL_BYTES",
                           "bytes are not the canonical serialization of the document")

    @classmethod
    def from_dict(cls, data):
        cls._VERIFY(data)
        try:
            return cls(canonical_json(data))
        except NotebookArtifactInventoryError:
            raise
        except (TypeError, ValueError) as exc:
            raise _invalid("MALFORMED_DOCUMENT", f"not a JSON document: {exc}") from None

    @property
    def document_type(self):
        return self.to_dict()["document_type"]

    @property
    def collection_status(self):
        return self.to_dict()["collection_status"]

    @property
    def non_claim(self):
        return self.to_dict()["non_claim"]

    @property
    def items(self):
        """A fresh list on every call; the document is never handed out by reference."""
        return self.to_dict()["items"]

    @property
    def digest(self):
        return _digest(self.json_bytes)

    def to_dict(self):
        return json.loads(self.json_bytes)

    def to_json_bytes(self):
        return self.json_bytes


@dataclass(frozen=True)
class ArtifactInventory(_Document):
    """An immutable notebook_artifact_inventory/1 document."""

    _DOCUMENT_TYPE = INVENTORY_DOCUMENT_TYPE
    _VERIFY = staticmethod(_verified_inventory)

    @property
    def order(self):
        return self.to_dict()["order"]


@dataclass(frozen=True)
class ArtifactSelection(_Document):
    """An immutable notebook_artifact_selection/1 document. An empty selection is valid."""

    _DOCUMENT_TYPE = SELECTION_DOCUMENT_TYPE
    _VERIFY = staticmethod(_verified_selection)

    @property
    def selected_order(self):
        return self.to_dict()["selected_order"]

    @property
    def inventory_digest(self):
        return self.to_dict()["inventory_digest"]


@dataclass(frozen=True)
class ArtifactHandoff(_Document):
    """An immutable notebook_artifact_handoff/1 document. Reference-only by construction."""

    _DOCUMENT_TYPE = HANDOFF_DOCUMENT_TYPE
    _VERIFY = staticmethod(_verified_handoff)

    @property
    def selected_order(self):
        return self.to_dict()["selected_order"]

    @property
    def inventory_digest(self):
        return self.to_dict()["inventory_digest"]

    @property
    def selection_digest(self):
        return self.to_dict()["selection_digest"]

    @property
    def target_seam(self):
        return self.to_dict()["target_seam"]


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------
def collect_artifact_inventory(items):
    """Collect explicitly supplied artifact references into one deterministic inventory.

    ``items`` is the caller's ordered list of item requests, each declaring exactly
    ITEM_FIELDS. Pure: reads nothing, opens nothing and selects nothing. The supplied order
    is the document order; no item is sorted, grouped, deduplicated, filtered or dropped,
    and an empty list yields a valid empty inventory that names its own emptiness through
    an empty order array.
    """
    records = _items_in_supplied_order(items)
    return ArtifactInventory.from_dict({
        "document_type": INVENTORY_DOCUMENT_TYPE,
        "non_claim": INVENTORY_NON_CLAIM,
        "collection_status": COLLECTION_STATUS,
        "order": [record["item_id"] for record in records],
        "items": records,
    })


def select_inventory_items(inventory, item_ids):
    """Record the identifiers a human chose, in exactly the order they were supplied.

    ``item_ids`` is the caller's own sequence. An empty sequence is a valid selection and
    never means "all". A repeated identifier and an identifier absent from the inventory
    are both refusals: neither is deduplicated, dropped, corrected or matched loosely.
    Nothing is chosen for the caller, and the inventory's own order is deliberately not
    imposed on the result.
    """
    if not isinstance(inventory, ArtifactInventory):
        raise _contract("MALFORMED_DOCUMENT",
                        f"inventory must be an ArtifactInventory, got "
                        f"{type(inventory).__qualname__}")
    if type(item_ids) not in (list, tuple):
        raise _contract("MALFORMED_DOCUMENT",
                        "item_ids must be a list or tuple of item_id values; an empty list "
                        "is a valid, explicitly empty selection")
    known = {record["item_id"]: record for record in inventory.items}
    chosen, seen = [], []
    for value in item_ids:
        item_id = _item_id(value)
        if item_id in seen:
            raise _contract("DUPLICATE_SELECTED_ID",
                            f"item_id {item_id!r} is selected twice; a repeated selection "
                            "is refused, never deduplicated",
                            item_id=item_id, field="item_ids")
        if item_id not in known:
            raise _contract("UNKNOWN_ITEM_ID",
                            f"item_id {item_id!r} is not in the inventory; an unknown "
                            "identifier is refused, never dropped or matched loosely",
                            item_id=item_id, field="item_ids")
        seen.append(item_id)
        chosen.append(known[item_id])
    return ArtifactSelection.from_dict({
        "document_type": SELECTION_DOCUMENT_TYPE,
        "non_claim": INVENTORY_NON_CLAIM,
        "collection_status": COLLECTION_STATUS,
        "inventory_digest": inventory.digest,
        "selected_order": [record["item_id"] for record in chosen],
        "items": chosen,
    })


def build_handoff_manifest(inventory, selection):
    """Serialize a reference-only handoff addressed to the existing intake seam by name.

    The pairing is re-checked rather than trusted: a selection taken from a different
    inventory is refused. Nothing is declared, mapped to a slot, combined or constructed
    here; ``target_seam`` is the module constant HANDOFF_TARGET_SEAM and no seam module is
    imported. An empty selection yields a valid, explicitly empty handoff.
    """
    if not isinstance(inventory, ArtifactInventory):
        raise _contract("MALFORMED_DOCUMENT",
                        f"inventory must be an ArtifactInventory, got "
                        f"{type(inventory).__qualname__}")
    if not isinstance(selection, ArtifactSelection):
        raise _contract("MALFORMED_DOCUMENT",
                        f"selection must be an ArtifactSelection, got "
                        f"{type(selection).__qualname__}")
    if selection.inventory_digest != inventory.digest:
        raise _contract("SELECTION_INVENTORY_MISMATCH",
                        "the selection was not taken from this inventory; the pairing is "
                        "checked, never assumed", field="inventory_digest")
    return ArtifactHandoff.from_dict({
        "document_type": HANDOFF_DOCUMENT_TYPE,
        "non_claim": INVENTORY_NON_CLAIM,
        "collection_status": COLLECTION_STATUS,
        "handoff_kind": HANDOFF_KIND,
        "target_seam": HANDOFF_TARGET_SEAM,
        "inventory_digest": inventory.digest,
        "selection_digest": selection.digest,
        "selected_order": list(selection.selected_order),
        "items": selection.items,
    })


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def _metadata_lines(record):
    """Declared metadata, one canonical line, carried verbatim and never summarized."""
    return ["    declared_metadata: "
            + canonical_json(record["declared_metadata"]).decode("utf-8")]


def _item_lines(position, record):
    return ([f"  [{position}] item_id: {record['item_id']}",
             f"    reference: {record['reference']}"]
            + _metadata_lines(record))


def render_inventory_lines(inventory):
    """Return fresh display lines for one inventory, in document order."""
    if not isinstance(inventory, ArtifactInventory):
        raise _contract("MALFORMED_DOCUMENT",
                        f"inventory must be an ArtifactInventory, got "
                        f"{type(inventory).__qualname__}")
    data = inventory.to_dict()
    lines = [INVENTORY_DISPLAY_DISCLAIMER, "",
             f"document_type: {data['document_type']}",
             f"collection_status: {data['collection_status']}",
             f"inventory_digest: {inventory.digest}"]
    if not data["items"]:
        return lines + ["No artifact reference supplied."]
    lines.append(f"Collected references ({len(data['items'])}), in the order supplied:")
    for position, record in enumerate(data["items"]):
        lines.extend(_item_lines(position, record))
    return lines


def render_selection_lines(selection):
    """Return fresh display lines for one selection, in the order the caller supplied."""
    if not isinstance(selection, ArtifactSelection):
        raise _contract("MALFORMED_DOCUMENT",
                        f"selection must be an ArtifactSelection, got "
                        f"{type(selection).__qualname__}")
    data = selection.to_dict()
    lines = [INVENTORY_DISPLAY_DISCLAIMER, "",
             f"document_type: {data['document_type']}",
             f"collection_status: {data['collection_status']}",
             f"inventory_digest: {data['inventory_digest']}",
             f"selection_digest: {selection.digest}"]
    if not data["items"]:
        return lines + ["No item selected. An empty selection is a valid selection and "
                        "does not mean every item."]
    lines.append(f"Manually selected ({len(data['items'])}), in the order supplied:")
    for position, record in enumerate(data["items"]):
        lines.extend(_item_lines(position, record))
    return lines


# --------------------------------------------------------------------------
# Notebook surface
# --------------------------------------------------------------------------
#: Paste-ready cells. They are text here, not an edit: this module writes nothing into any
#: notebook, and returning the sources keeps the notebook's own cell sequence untouched.
#: Each code cell declares its own inputs literally, calls only this module's entry points,
#: and prints. No cell opens a file, resolves a path, imports an adapter or a kernel
#: module, or enters an evaluation path.
_CELLS = (
    ("artifact-inventory-00-section", "markdown", """\
## Collected artifact references and manual selection

Read-only collection surface (`notebook_artifact_inventory/1`). It lists artifact
references already produced elsewhere together with the metadata already declared for
them, and records which identifiers a reader selects by hand.

Collection is not evaluation and manual selection is not declaration. References are
opaque text and are never opened or resolved; declared metadata is carried verbatim and
never interpreted. Nothing here scores, ranks, sorts by quality, filters, recommends or
selects automatically, and presence in the list is not evidence about an item. Whether
anything may be declared from a selected identifier is decided entirely by the separate
intake seam, which applies its own contract and may refuse.
"""),
    ("artifact-inventory-01-collect", "code", """\
from structure_audit.notebook_artifact_inventory import (
    collect_artifact_inventory, render_inventory_lines,
)

# Declared literally here. Nothing is discovered, globbed, listed or read: edit this list
# by hand to describe references you already have. declared_metadata is carried verbatim.
ARTIFACT_ITEMS = [
    {"item_id": "run-a", "reference": "external_artifacts/run-a",
     "declared_metadata": {}},
    {"item_id": "run-b", "reference": "external_artifacts/run-b",
     "declared_metadata": {}},
]

inventory = collect_artifact_inventory(ARTIFACT_ITEMS)
print("\\n".join(render_inventory_lines(inventory)))
"""),
    ("artifact-inventory-02-select", "code", """\
from structure_audit.notebook_artifact_inventory import (
    build_handoff_manifest, render_selection_lines, select_inventory_items,
)

# Type the identifiers you choose, in the order you want them carried forward. [] is a
# valid, explicitly empty selection and does not mean every item. A repeated or unknown
# identifier is refused rather than repaired.
SELECTED_IDS = []

selection = select_inventory_items(inventory, SELECTED_IDS)
print("\\n".join(render_selection_lines(selection)))

# Reference-only: it names the intake seam and carries the identifiers verbatim. No
# candidate, declaration, slot mapping or combination is constructed here.
handoff = build_handoff_manifest(inventory, selection)
print()
print("handoff target_seam:", handoff.target_seam)
print("handoff bytes:", len(handoff.to_json_bytes()))
"""),
)


def notebook_cell_sources():
    """Return the paste-ready (cell_id, cell_type, source) triples, fresh on every call.

    This is the notebook surface: text a reader pastes, never an edit this module performs.
    No notebook is opened, parsed or written, and the returned sources enter no evaluation
    path.
    """
    return tuple((cell_id, cell_type, source) for cell_id, cell_type, source in _CELLS)
