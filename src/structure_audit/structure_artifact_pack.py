"""Reference-only artifact pack for external inspection tools
(contract structure_artifact_pack/1).

Standard library plus the existing canonical serializer and the accepted collection layer;
no import-time I/O. This layer restates an already-built artifact inventory or manual
selection as a pack a person can carry to an external inspection tool by hand. It opens no
file, resolves no path, checks no file's existence, reads no structure, and executes nothing.

WHY IT EXISTS

  Having chosen some references by hand, a reader wants them in one place, with the metadata
  already declared for them, in a shape that is obviously a list of references rather than a
  result. Keeping that in its own contract means the pack can be handed around without ever
  being mistaken for an analysis.

INPUT

  build_artifact_pack takes one ArtifactInventory or ArtifactSelection from
  notebook_artifact_inventory. Its items are carried verbatim, in that source document's own
  order, and the source contract and digest are recorded so a pack always states what it came
  from. Nothing is re-collected, re-selected, re-ordered, added or removed here.

WHAT A PACK DELIBERATELY DOES NOT CONTAIN

  No tool command, script, session, macro, selection expression, object name, colouring,
  representation, alignment, superposition, pairing, grouping or load instruction is emitted.
  Writing even a load line would assert that a reference names a file an inspection tool can
  open as a structure, and this layer never reads a reference, so it cannot know that. The
  pack lists references; a person decides what, if anything, to open.

  No score, rank, priority, eligibility, recommendation, pose, complex, contact, interface,
  distance or quality field is minted, and none is derived from a reference or from declared
  metadata. FORBIDDEN_MINTED_SUBSTRINGS is checked against every name this layer mints, on
  every construction, so that boundary cannot be widened by a later edit.

NO CLAIM

  The references in a pack are inspection references. They are not validated bound complexes,
  not best or representative poses, not docked, superposed, minimized or refined structures,
  and not binding, contact, affinity or avidity proofs. Presence in a pack is not evidence
  about an item, and the order of the pack is the order the source document already had, not
  a preference.

OUTPUT

  StructureArtifactPack is immutable and held only as its canonical bytes
  (provenance.canonical_json), so no upstream object is aliased, retained or mutated.
  to_dict() returns a fresh object on every call; from_dict and the bytes constructor
  re-derive every derived field, including order and the emitted non-claim, and reject any
  difference.

ERRORS
  StructureArtifactPackError(ValueError) with .code, .reason, .item_id and .field. .code is
  closed: CONTRACT_INVALID for a malformed request, DOCUMENT_INVALID for a document that does
  not re-derive. .reason is closed to REFUSAL_REASONS. No partial pack exists.
"""
from dataclasses import dataclass
import hashlib
import json

from .notebook_artifact_inventory import (
    INVENTORY_DOCUMENT_TYPE, ITEM_FIELDS, SELECTION_DOCUMENT_TYPE, ArtifactInventory,
    ArtifactSelection,
)
from .provenance import canonical_json

PACK_DOCUMENT_TYPE = "structure_artifact_pack/1"

#: The two source contracts a pack may be built from. Both come from the accepted
#: collection layer; nothing else is accepted, and neither is re-derived here.
SOURCE_DOCUMENT_TYPES = (INVENTORY_DOCUMENT_TYPE, SELECTION_DOCUMENT_TYPE)

#: Derived from this constant, never from an argument. No call, option or flag can change it.
INSPECTION_KIND = "REFERENCE_ONLY_INSPECTION"

#: Fixed by this contract. Each is copied from the source item unchanged.
PACK_ITEM_FIELDS = ITEM_FIELDS

PACK_FIELDS = ("document_type", "non_claim", "inspection_kind", "source_document_type",
               "source_digest", "order", "items")

#: Carried verbatim from the caller's own declaration; never read, so exempt from the guard.
_VERBATIM_SUBTREES = ("declared_metadata",)

#: Checked against every name this layer mints, on every construction.
FORBIDDEN_MINTED_SUBSTRINGS = (
    "score", "rank", "priority", "eligib", "recommend", "admit", "veto", "auto", "best",
    "top", "prefer", "favor", "quality", "confidence", "tier", "grade", "weight",
    "pose", "complex", "bound", "docked", "superpos", "align", "contact", "interface",
    "distance", "rmsd", "affinity", "avidity", "binding",
)

#: Emitted verbatim in every pack and re-derived on load.
PACK_NON_CLAIM = (
    "This pack lists artifact references for manual inspection. It is a reference list, "
    "not a result.\n"
    "\n"
    "Every reference and every metadata value is carried verbatim from an already-built "
    "inventory or manual selection. A reference is opaque text: it is never opened, "
    "resolved, dereferenced, existence-checked or read, so this pack cannot know what any "
    "reference names. It emits no tool command, script, session, selection expression, "
    "alignment, superposition or load instruction, and it pairs, groups and orders nothing "
    "beyond the order the source document already had.\n"
    "\n"
    "These are inspection references. They are not validated bound complexes, not best or "
    "representative poses, not docked, superposed, minimized or refined structures, and not "
    "binding, contact, affinity or avidity proofs. Nothing here scores, ranks, filters, "
    "recommends, admits or selects anything. Presence in this pack is not evidence about an "
    "item and confers no admission, eligibility, priority or standing anywhere downstream. "
    "Whether a reference is worth opening, and what it shows if opened, is entirely for the "
    "person inspecting it to determine."
)

#: Printed immediately above any rendering.
PACK_DISPLAY_DISCLAIMER = (
    "Inspection references only - not validated bound complexes, best poses or binding "
    "proofs. References are carried verbatim and were never opened. No tool command or "
    "session is generated. Order is the source document's order, not a preference."
)

CONTRACT_INVALID = "CONTRACT_INVALID"
DOCUMENT_INVALID = "DOCUMENT_INVALID"

#: Closed. Every refusal names exactly one of these; none is a fallback.
REFUSAL_REASONS = (
    "SOURCE_KIND_UNEXPECTED",
    "SOURCE_DOCUMENT_TYPE_UNEXPECTED",
    "DUPLICATE_ITEM_ID",
    "UNKNOWN_FIELD",
    "MISSING_FIELD",
    "MINTED_FIELD_FORBIDDEN",
    "ORDER_NOT_DERIVED",
    "DUPLICATE_JSON_KEY",
    "NOT_CANONICAL_BYTES",
    "MALFORMED_DOCUMENT",
    "NON_CLAIM_ALTERED",
)

__all__ = [
    "PACK_DOCUMENT_TYPE",
    "SOURCE_DOCUMENT_TYPES",
    "INSPECTION_KIND",
    "PACK_ITEM_FIELDS",
    "PACK_FIELDS",
    "FORBIDDEN_MINTED_SUBSTRINGS",
    "PACK_NON_CLAIM",
    "PACK_DISPLAY_DISCLAIMER",
    "CONTRACT_INVALID",
    "DOCUMENT_INVALID",
    "REFUSAL_REASONS",
    "StructureArtifactPackError",
    "StructureArtifactPack",
    "build_artifact_pack",
    "render_pack_lines",
    "notebook_cell_sources",
]


class StructureArtifactPackError(ValueError):
    """Malformed request or document. No partial pack exists."""

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
    return StructureArtifactPackError(
        CONTRACT_INVALID, reason, message, item_id=item_id, field=field)


def _invalid(reason, message, *, item_id=None, field=None):
    return StructureArtifactPackError(
        DOCUMENT_INVALID, reason, message, item_id=item_id, field=field)


# --------------------------------------------------------------------------
# Minted-field guard
# --------------------------------------------------------------------------
def _minted_names_are_clean(names, *, where):
    """Refuse any name this layer mints that suggests an inspection result.

    Runs on every construction, not in a test only. Names inside _VERBATIM_SUBTREES are the
    caller's own declared text and are never passed in here.
    """
    for name in names:
        lowered = name.lower()
        for forbidden in FORBIDDEN_MINTED_SUBSTRINGS:
            if forbidden in lowered:
                raise _invalid(
                    "MINTED_FIELD_FORBIDDEN",
                    f"{where} field {name!r} carries {forbidden!r}; a pack mints no score, "
                    "rank, pose, complex, alignment, contact or quality field, and declared "
                    "metadata is carried verbatim rather than promoted to a field",
                    field=name)


for _names, _where in ((PACK_ITEM_FIELDS, "item"), (PACK_FIELDS, "pack")):
    _minted_names_are_clean(_names, where=_where)
del _names, _where


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------
def _strict(raw):
    """Parse pack bytes; duplicate keys and non-finite tokens are not JSON here."""
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
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=constant)
    except UnicodeDecodeError as exc:
        raise _invalid("MALFORMED_DOCUMENT", f"not UTF-8 text: {exc}") from None
    except json.JSONDecodeError as exc:
        raise _invalid("MALFORMED_DOCUMENT", f"not a JSON document: {exc}") from None


def _digest(payload):
    """sha256 of already-produced bytes. It identifies bytes, nothing else."""
    return hashlib.sha256(payload).hexdigest()


def _verified_pack(data):
    """Re-derive every derived field of a pack and reject any difference."""
    if type(data) is not dict:
        raise _invalid("MALFORMED_DOCUMENT", "a pack must be a JSON object")
    unknown = sorted(set(data) - set(PACK_FIELDS))
    if unknown:
        raise _invalid("UNKNOWN_FIELD",
                       f"unknown pack fields {unknown}; the declared fields are "
                       f"{list(PACK_FIELDS)}", field=unknown[0])
    missing = [name for name in PACK_FIELDS if name not in data]
    if missing:
        raise _invalid("MISSING_FIELD", f"missing pack fields {missing}", field=missing[0])
    _minted_names_are_clean(data.keys(), where="pack")
    if data["document_type"] != PACK_DOCUMENT_TYPE:
        raise _invalid("MALFORMED_DOCUMENT",
                       f"document_type must be exactly {PACK_DOCUMENT_TYPE!r}",
                       field="document_type")
    if data["non_claim"] != PACK_NON_CLAIM:
        raise _invalid("NON_CLAIM_ALTERED",
                       "non_claim must be emitted verbatim; it is never reworded, abridged "
                       "or parameterized", field="non_claim")
    if data["inspection_kind"] != INSPECTION_KIND:
        raise _invalid("MALFORMED_DOCUMENT",
                       f"inspection_kind is fixed to {INSPECTION_KIND!r} and no request can "
                       "change it", field="inspection_kind")
    if data["source_document_type"] not in SOURCE_DOCUMENT_TYPES:
        raise _invalid("SOURCE_DOCUMENT_TYPE_UNEXPECTED",
                       f"source_document_type must be one of "
                       f"{list(SOURCE_DOCUMENT_TYPES)}", field="source_document_type")
    digest = data["source_digest"]
    if type(digest) is not str or len(digest) != 64 or digest.strip("0123456789abcdef") != "":
        raise _invalid("MALFORMED_DOCUMENT",
                       "source_digest must be 64 lowercase hex characters",
                       field="source_digest")
    if type(data["items"]) is not list:
        raise _invalid("MALFORMED_DOCUMENT", "items must be an array", field="items")
    seen = []
    for item in data["items"]:
        if type(item) is not dict or sorted(item) != sorted(PACK_ITEM_FIELDS):
            raise _invalid("MALFORMED_DOCUMENT",
                           f"a pack item declares exactly {list(PACK_ITEM_FIELDS)}",
                           field="items")
        _minted_names_are_clean(
            [name for name in item if name not in _VERBATIM_SUBTREES], where="item")
        item_id = item["item_id"]
        if type(item_id) is not str or item_id == "":
            raise _invalid("MALFORMED_DOCUMENT",
                           "a pack item carries a non-empty string item_id", field="item_id")
        if type(item["reference"]) is not str or item["reference"] == "":
            raise _invalid("MALFORMED_DOCUMENT",
                           "a pack item carries a non-empty string reference; it is opaque "
                           "text and is never opened or resolved",
                           item_id=item_id, field="reference")
        if type(item["declared_metadata"]) is not dict:
            raise _invalid("MALFORMED_DOCUMENT",
                           "declared_metadata must be a JSON object, carried verbatim",
                           item_id=item_id, field="declared_metadata")
        if item_id in seen:
            raise _invalid("DUPLICATE_ITEM_ID",
                           f"item_id {item_id!r} appears twice; a repeated identifier is "
                           "refused, never deduplicated", item_id=item_id, field="items")
        seen.append(item_id)
    if data["order"] != seen:
        raise _invalid("ORDER_NOT_DERIVED",
                       "order must be exactly the item_id of each entry of items, in the "
                       "same order; a supplied order is never trusted, sorted or normalized",
                       field="order")


# --------------------------------------------------------------------------
# Document
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class StructureArtifactPack:
    """An immutable structure_artifact_pack/1 document, held only as canonical bytes."""

    json_bytes: bytes

    def __post_init__(self):
        if type(self.json_bytes) is not bytes:
            raise _invalid("MALFORMED_DOCUMENT", "json_bytes must be bytes")
        data = _strict(self.json_bytes)
        _verified_pack(data)
        if canonical_json(data) != self.json_bytes:
            raise _invalid("NOT_CANONICAL_BYTES",
                           "bytes are not the canonical serialization of the document")

    @classmethod
    def from_dict(cls, data):
        _verified_pack(data)
        try:
            return cls(canonical_json(data))
        except StructureArtifactPackError:
            raise
        except (TypeError, ValueError) as exc:
            raise _invalid("MALFORMED_DOCUMENT", f"not a JSON document: {exc}") from None

    @property
    def document_type(self):
        return self.to_dict()["document_type"]

    @property
    def inspection_kind(self):
        return self.to_dict()["inspection_kind"]

    @property
    def non_claim(self):
        return self.to_dict()["non_claim"]

    @property
    def source_document_type(self):
        return self.to_dict()["source_document_type"]

    @property
    def source_digest(self):
        return self.to_dict()["source_digest"]

    @property
    def order(self):
        """A fresh list on every call; the document is never handed out by reference."""
        return self.to_dict()["order"]

    @property
    def items(self):
        return self.to_dict()["items"]

    @property
    def digest(self):
        return _digest(self.json_bytes)

    def references(self):
        """The carried reference text, in document order. No reference is opened."""
        return [item["reference"] for item in self.items]

    def to_dict(self):
        return json.loads(self.json_bytes)

    def to_json_bytes(self):
        return self.json_bytes


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def build_artifact_pack(source):
    """Restate one inventory or manual selection as a reference-only inspection pack.

    ``source`` is an ArtifactInventory or an ArtifactSelection from the accepted collection
    layer. Its items are carried verbatim, in that document's own order, and its contract and
    digest are recorded. Pure: opens no file, resolves no reference, generates no tool command
    or session, and adds, removes, reorders and derives nothing.
    """
    if isinstance(source, ArtifactInventory):
        source_document_type = INVENTORY_DOCUMENT_TYPE
    elif isinstance(source, ArtifactSelection):
        source_document_type = SELECTION_DOCUMENT_TYPE
    else:
        raise _contract("SOURCE_KIND_UNEXPECTED",
                        "source must be an ArtifactInventory or an ArtifactSelection from "
                        "notebook_artifact_inventory, got "
                        f"{type(source).__qualname__}")
    items = source.items
    return StructureArtifactPack.from_dict({
        "document_type": PACK_DOCUMENT_TYPE,
        "non_claim": PACK_NON_CLAIM,
        "inspection_kind": INSPECTION_KIND,
        "source_document_type": source_document_type,
        "source_digest": source.digest,
        "order": [item["item_id"] for item in items],
        "items": items,
    })


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def render_pack_lines(pack):
    """Return fresh display lines for one pack, in document order.

    The reference is printed verbatim on its own line. No tool command, load instruction,
    selection expression or session directive is emitted, because that would assert what a
    reference names, and this layer never reads one.
    """
    if not isinstance(pack, StructureArtifactPack):
        raise _contract("MALFORMED_DOCUMENT",
                        f"pack must be a StructureArtifactPack, got "
                        f"{type(pack).__qualname__}")
    data = pack.to_dict()
    lines = [PACK_DISPLAY_DISCLAIMER, "",
             f"document_type: {data['document_type']}",
             f"inspection_kind: {data['inspection_kind']}",
             f"source_document_type: {data['source_document_type']}",
             f"source_digest: {data['source_digest']}",
             f"pack_digest: {pack.digest}"]
    if not data["items"]:
        return lines + ["No artifact reference in this pack. An empty pack is a valid pack "
                        "and does not mean every artifact."]
    lines.append(f"Inspection references ({len(data['items'])}), in the source document's "
                 "own order:")
    for position, item in enumerate(data["items"]):
        lines.extend([
            f"  [{position}] item_id: {item['item_id']}",
            f"    reference: {item['reference']}",
            "    declared_metadata: "
            + canonical_json(item["declared_metadata"]).decode("utf-8"),
        ])
    return lines


# --------------------------------------------------------------------------
# Notebook surface
# --------------------------------------------------------------------------
#: Paste-ready cells. They are text here, not an edit: this module writes nothing into any
#: notebook. The code cell restates a selection the caller already built and prints it; it
#: opens no file and generates no tool command.
_CELLS = (
    ("artifact-pack-00-section", "markdown", """\
## Structure artifact pack for external inspection

Reference-only view (`structure_artifact_pack/1`) over an artifact inventory or manual
selection already built by the collection layer. It is a list you carry by hand to an
external inspection tool, such as a molecular viewer.

Every reference and metadata value is carried verbatim and was never opened, resolved or
read. No tool command, script, session, selection expression, alignment or superposition is
generated, because writing one would assert what a reference names, and this view never
reads one.

These are inspection references. They are **not** validated bound complexes, **not** best or
representative poses, **not** docked, superposed, minimized or refined structures, and
**not** binding, contact, affinity or avidity proofs. Presence in the pack is not evidence
about an item, and pack order is the source document's order, not a preference.
"""),
    ("artifact-pack-01-render", "code", """\
from structure_audit.structure_artifact_pack import build_artifact_pack, render_pack_lines

# `selection` (or `inventory`) comes from the collection cells above. Nothing is
# re-collected, re-selected or reordered here, and no reference is opened.
pack = build_artifact_pack(selection)
print("\\n".join(render_pack_lines(pack)))

# The carried reference text, in the source document's own order. Decide by hand what, if
# anything, to open in your inspection tool.
print()
for reference in pack.references():
    print(reference)
"""),
)


def notebook_cell_sources():
    """Return the paste-ready (cell_id, cell_type, source) triples, fresh on every call.

    This is the notebook surface: text a reader pastes, never an edit this module performs.
    No notebook is opened, parsed or written.
    """
    return tuple((cell_id, cell_type, source) for cell_id, cell_type, source in _CELLS)
