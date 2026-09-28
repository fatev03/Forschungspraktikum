"""Descriptive table over an already-finished candidate priority report
(contract candidate_combinations_table/1).

Standard library plus the existing canonical serializer; no import-time I/O. This layer is a
presentation consumer of documents that are already final. It reads a serialized
cassette_candidate_priority/1 report, and optionally a serialized demo_candidate_manifest/1
manifest, and arranges what they already contain into rows. It opens no file, imports no
kernel or seam module, evaluates nothing, and mints no value of its own.

WHY IT TAKES DOCUMENTS AND NOT OBJECTS

  The report and the manifest arrive as their own serialized documents, exactly as their
  producers emit them. Nothing here imports cassette_candidate_priority,
  cassette_candidate_batch, cassette_slot_ledger or demo_candidate_manifest, so this table
  cannot become an input to the chain that produced them, cannot change what they compute,
  and cannot go stale against their internals. The pointer sets below are fixed by this
  contract and are never chosen by a caller.

ORDER IS READ, NEVER COMPUTED

  Ranked rows follow the source report's own groups array, and within each group its own
  members array, in exactly those orders. Excluded rows follow the source report's own
  excluded array, in exactly that order, in a separate section after the ranked rows. No
  row is sorted, resorted, grouped, regrouped, merged, interleaved, promoted, demoted,
  filtered or dropped, and no value on a row is ever an ordering input here.

  The source's own invariants stay the source's. This layer does not re-check rank
  contiguity, tier order, the ranked/excluded partition or any other rule the priority layer
  enforces, because re-deriving them here would be a second implementation of ranking. It
  reads the arrays it is given and states their order.

VERBATIM CARRIAGE

  A row's carried subtree holds the source values at the fixed pointers in
  RANKED_CARRIED_FIELDS or EXCLUDED_CARRIED_FIELDS, copied unchanged. rank, geometry_tier,
  evidence_coverage, ineligibility_reason and vetoed_slots are the priority layer's own
  minted fields and are carried, never recomputed, reinterpreted, combined, weighted,
  thresholded, translated or summarized. This layer adds no composite field of any kind.

COMBINATIONS

  When a manifest document is supplied, a row also carries the combination the manifest
  already declared for that exact candidate_id, at the fixed pointers in
  COMBINATION_CARRIED_FIELDS. Matching is exact string equality on candidate_id and nothing
  else: no prefix, suffix, case, slot, hash or near match. A combination is never fabricated,
  defaulted, inherited or guessed, and its absence is always named rather than left as a bare
  null: COMBINATION_NOT_DECLARED when a manifest was supplied but declares nothing for that
  candidate_id, MANIFEST_NOT_SUPPLIED when no manifest was supplied at all. The two cases stay
  separable, because collapsing them would let a missing input look like a missing entry.

DISPLAY WINDOW

  row_limit is an explicitly declared cut on how many ranked rows are shown. It is a display
  window and nothing else: it never reorders, never chooses which rows survive beyond
  "the leading rows of the order the source already fixed", and never touches the excluded
  section, because hiding an excluded candidate could read as a filter. The document always
  records ranked_rows_in_source alongside ranked_rows_shown and truncated, so a windowed
  table states its own incompleteness. None means every row.

NO CLAIM

  A row is a restatement of a finished report. It is not a recommendation, a shortlist, a
  selection, a score, a composite, a ranking produced here, or a statement that a candidate
  is good, usable, admissible or likely to succeed. Equal rank means equal tier, exactly as
  the source says. Position inside a rank is the source's listing sequence, never precedence.

OUTPUT

  CandidateCombinationsTable is immutable and held only as its canonical bytes
  (provenance.canonical_json), so no upstream object is aliased, retained or mutated.
  to_dict() returns a fresh object on every call; from_dict and the bytes constructor
  re-derive every derived field, including row_order and the emitted non-claim, and reject
  any difference.

ERRORS
  CandidateCombinationsTableError(ValueError) with .code, .reason, .candidate_id and .field.
  .code is closed: CONTRACT_INVALID for a malformed request, DOCUMENT_INVALID for a document
  that does not re-derive. .reason is closed to REFUSAL_REASONS. No partial table exists.
"""
from dataclasses import dataclass
import hashlib
import json

from .provenance import canonical_json

TABLE_DOCUMENT_TYPE = "candidate_combinations_table/1"

#: The two source contracts this table reads, by name. Neither module is imported.
SOURCE_PRIORITY_DOCUMENT_TYPE = "cassette_candidate_priority/1"
SOURCE_MANIFEST_DOCUMENT_TYPE = "demo_candidate_manifest/1"

#: Derived from this constant, never from an argument.
TABLE_KIND = "DESCRIPTIVE_RESTATEMENT"

#: The two named absences. A row without a combination always says which case it is, so
#: "no manifest was supplied" is never confused with "this manifest declares no combination
#: for this candidate". Absence is never a bare null.
COMBINATION_NOT_DECLARED = "COMBINATION_NOT_DECLARED"
MANIFEST_NOT_SUPPLIED = "MANIFEST_NOT_SUPPLIED"
COMBINATION_ABSENCE_REASONS = (COMBINATION_NOT_DECLARED, MANIFEST_NOT_SUPPLIED)

ROW_RANKED = "RANKED"
ROW_EXCLUDED = "EXCLUDED"
ROW_KINDS = (ROW_RANKED, ROW_EXCLUDED)

#: Fixed by this contract, never chosen by a caller. Each name is read from the source
#: member record, or from its enclosing group for "rank", and copied unchanged.
RANKED_CARRIED_FIELDS = (
    "rank", "geometry_tier", "evidence_coverage", "slot_binding_hash", "state_result_id",
    "certificate_present",
)
#: Fixed by this contract. Read from the source excluded record and copied unchanged.
EXCLUDED_CARRIED_FIELDS = (
    "ineligibility_reason", "state_status", "state_status_reason", "vetoed_slots",
    "slot_binding_hash",
)
#: Fixed by this contract. Read from the manifest combination record and copied unchanged.
COMBINATION_CARRIED_FIELDS = ("candidate_id", "choices")

#: "rank" lives on the group, not the member, so it is read from there and named here.
_GROUP_SOURCED = ("rank",)

ROW_FIELDS = ("candidate_id", "row_kind", "carried", "combination", "combination_absence")
WINDOW_FIELDS = ("declared_row_limit", "ranked_rows_in_source", "ranked_rows_shown",
                 "truncated")
TABLE_FIELDS = (
    "document_type", "non_claim", "table_kind", "source_priority_digest",
    "source_manifest_digest", "display_window", "row_order", "rows",
)

#: Every subtree whose contents are the source's own values. They are carried verbatim and
#: are deliberately exempt from the minted-name guard, which applies to names this layer
#: introduces itself.
_VERBATIM_SUBTREES = ("carried", "combination")

#: The only minted names allowed to reuse the source report's own section vocabulary. Each
#: is a count of rows in the source's ranked section, never a rank, score or judgement of
#: this layer's own. The list is deliberately exhaustive and closed: a new name carrying a
#: forbidden substring has to be added here explicitly, which is a reviewable change, and
#: passing data to this layer can never produce one.
SOURCE_VOCABULARY_NAMES = ("ranked_rows_in_source", "ranked_rows_shown")

#: Checked against every field name this layer mints. The carried subtrees legitimately hold
#: the source's own rank and tier names; nothing outside them may, except the closed
#: SOURCE_VOCABULARY_NAMES above.
FORBIDDEN_MINTED_SUBSTRINGS = (
    "score", "rank", "priority_of", "eligib", "recommend", "admit", "veto", "auto",
    "best", "top", "prefer", "favor", "quality", "confidence", "tier", "grade", "weight",
    "composite", "shortlist", "verdict",
)

#: Emitted verbatim in every table and re-derived on load.
TABLE_NON_CLAIM = (
    "This table restates a finished candidate priority report. It computes no order and "
    "mints no value.\n"
    "\n"
    "Row order is read from the source report's own arrays: ranked rows follow its groups "
    "and, inside each group, its members; excluded rows follow its excluded array, in a "
    "separate section. Nothing here sorts, regroups, promotes, demotes, filters, scores, "
    "weights, combines or recommends, and no carried value is an ordering input. rank, "
    "geometry_tier, evidence_coverage, ineligibility_reason and vetoed_slots are the "
    "priority layer's own fields, carried unchanged and never recomputed or "
    "reinterpreted. A declared row limit is a display cut over the order the source "
    "already fixed; it is not a selection, a shortlist or a recommendation, and the "
    "table always states how many ranked rows the source held.\n"
    "\n"
    "A row is not a claim that a candidate is good, usable, admissible, eligible or likely "
    "to succeed, and it is not a claim about receptor biology, structure, binding, "
    "affinity, avidity, occupancy, accessibility, expression, specificity, safety or "
    "experimental outcome. Equal rank means equal tier, exactly as the source says, not "
    "equivalence. Listing position inside a rank is the source's sequence, never "
    "precedence. A declared combination is an opaque set of labels the manifest already "
    "recorded; it is never resolved, parsed or read."
)

#: Printed immediately above any rendering.
TABLE_DISPLAY_DISCLAIMER = (
    "Descriptive restatement of a finished priority report - no ordering, scoring or "
    "recommendation is produced here. Rank and tier are carried from the source. Equal "
    "rank means equal tier. A row limit hides rows, it selects nothing."
)

CONTRACT_INVALID = "CONTRACT_INVALID"
DOCUMENT_INVALID = "DOCUMENT_INVALID"

#: Closed. Every refusal names exactly one of these; none is a fallback.
REFUSAL_REASONS = (
    "SOURCE_DOCUMENT_TYPE_UNEXPECTED",
    "SOURCE_SHAPE_UNEXPECTED",
    "SOURCE_FIELD_ABSENT",
    "DUPLICATE_CANDIDATE_ID",
    "INVALID_ROW_LIMIT",
    "UNKNOWN_FIELD",
    "MISSING_FIELD",
    "MINTED_FIELD_FORBIDDEN",
    "ROW_ORDER_NOT_DERIVED",
    "WINDOW_NOT_DERIVED",
    "DUPLICATE_JSON_KEY",
    "NOT_CANONICAL_BYTES",
    "MALFORMED_DOCUMENT",
    "NON_CLAIM_ALTERED",
)

__all__ = [
    "TABLE_DOCUMENT_TYPE",
    "SOURCE_PRIORITY_DOCUMENT_TYPE",
    "SOURCE_MANIFEST_DOCUMENT_TYPE",
    "TABLE_KIND",
    "COMBINATION_NOT_DECLARED",
    "MANIFEST_NOT_SUPPLIED",
    "COMBINATION_ABSENCE_REASONS",
    "ROW_RANKED",
    "ROW_EXCLUDED",
    "ROW_KINDS",
    "RANKED_CARRIED_FIELDS",
    "EXCLUDED_CARRIED_FIELDS",
    "COMBINATION_CARRIED_FIELDS",
    "SOURCE_VOCABULARY_NAMES",
    "ROW_FIELDS",
    "WINDOW_FIELDS",
    "TABLE_FIELDS",
    "FORBIDDEN_MINTED_SUBSTRINGS",
    "TABLE_NON_CLAIM",
    "TABLE_DISPLAY_DISCLAIMER",
    "CONTRACT_INVALID",
    "DOCUMENT_INVALID",
    "REFUSAL_REASONS",
    "CandidateCombinationsTableError",
    "CandidateCombinationsTable",
    "build_combinations_table",
    "render_table_lines",
    "notebook_cell_sources",
]


class CandidateCombinationsTableError(ValueError):
    """Malformed request or document. No partial table exists."""

    def __init__(self, code, reason, message, *, candidate_id=None, field=None):
        if code not in (CONTRACT_INVALID, DOCUMENT_INVALID):
            raise AssertionError(f"unknown error code {code!r}")
        if reason not in REFUSAL_REASONS:
            raise AssertionError(f"unknown refusal reason {reason!r}")
        self.code, self.reason = code, reason
        self.candidate_id, self.field = candidate_id, field
        self.diagnostics = [{"severity": "error", "code": code, "reason": reason,
                             "message": message, "candidate_id": candidate_id,
                             "field": field}]
        super().__init__(f"{code}/{reason}: {message}")


def _contract(reason, message, *, candidate_id=None, field=None):
    return CandidateCombinationsTableError(
        CONTRACT_INVALID, reason, message, candidate_id=candidate_id, field=field)


def _invalid(reason, message, *, candidate_id=None, field=None):
    return CandidateCombinationsTableError(
        DOCUMENT_INVALID, reason, message, candidate_id=candidate_id, field=field)


# --------------------------------------------------------------------------
# Minted-field guard
# --------------------------------------------------------------------------
def _minted_names_are_clean(names, *, where):
    """Refuse any name this layer mints that suggests a judgement it does not make.

    Runs on every construction, not in a test only, so the boundary cannot be widened by an
    edit that forgets the test. Names inside _VERBATIM_SUBTREES are the source's own and are
    never passed in here; the closed SOURCE_VOCABULARY_NAMES are row counts over the source's
    own ranked section and are exempt by name, never by pattern.
    """
    for name in names:
        if name in SOURCE_VOCABULARY_NAMES:
            continue
        lowered = name.lower()
        for forbidden in FORBIDDEN_MINTED_SUBSTRINGS:
            if forbidden in lowered:
                raise _invalid(
                    "MINTED_FIELD_FORBIDDEN",
                    f"{where} field {name!r} carries {forbidden!r}; this layer mints no "
                    "ranking, scoring, composite, recommendation or eligibility field of "
                    f"its own, and the source's own fields belong in {_VERBATIM_SUBTREES}",
                    field=name)


for _names, _where in ((ROW_FIELDS, "row"), (WINDOW_FIELDS, "display_window"),
                       (TABLE_FIELDS, "table")):
    _minted_names_are_clean(_names, where=_where)
del _names, _where


# --------------------------------------------------------------------------
# Source reading
# --------------------------------------------------------------------------
def _source_document(value, expected_type, what):
    """Accept a serialized source document as a mapping or its canonical bytes."""
    if isinstance(value, (bytes, bytearray)):
        try:
            value = json.loads(bytes(value).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _contract("SOURCE_SHAPE_UNEXPECTED",
                            f"{what} is not a JSON document: {exc}") from None
    if type(value) is not dict:
        raise _contract("SOURCE_SHAPE_UNEXPECTED",
                        f"{what} must be a {expected_type} document as a mapping or its "
                        f"canonical bytes, got {type(value).__qualname__}")
    if value.get("document_type") != expected_type:
        raise _contract("SOURCE_DOCUMENT_TYPE_UNEXPECTED",
                        f"{what} must declare document_type {expected_type!r}, got "
                        f"{value.get('document_type')!r}; a document of another contract is "
                        "refused, never adapted", field="document_type")
    return value


def _array(container, name, what):
    if name not in container:
        raise _contract("SOURCE_FIELD_ABSENT",
                        f"{what} declares no {name!r}; an absent source array is refused, "
                        f"never treated as empty", field=name)
    value = container[name]
    if type(value) is not list:
        raise _contract("SOURCE_SHAPE_UNEXPECTED",
                        f"{what} field {name!r} must be an array", field=name)
    return value


def _mapping(value, what, *, field=None):
    if type(value) is not dict:
        raise _contract("SOURCE_SHAPE_UNEXPECTED",
                        f"{what} must be a JSON object, got {type(value).__qualname__}",
                        field=field)
    return value


def _carried(record, names, what, *, group=None):
    """Copy the fixed pointer set out of one source record, unchanged."""
    carried = {}
    for name in names:
        container = group if name in _GROUP_SOURCED else record
        if container is None or name not in container:
            raise _contract("SOURCE_FIELD_ABSENT",
                            f"{what} carries no {name!r}; a carried field is copied from "
                            "the source, never defaulted, derived or substituted",
                            field=name)
        carried[name] = container[name]
    return carried


def _candidate_id(record, what):
    value = record.get("candidate_id")
    if type(value) is not str or value == "":
        raise _contract("SOURCE_SHAPE_UNEXPECTED",
                        f"{what} must carry a non-empty string candidate_id",
                        field="candidate_id")
    return value


def _combinations_by_candidate(manifest):
    """Index the manifest's already-declared combinations by exact candidate_id."""
    if manifest is None:
        return None
    indexed = {}
    for entry in _array(manifest, "combinations", "the manifest document"):
        record = _mapping(entry, "a manifest combination", field="combinations")
        candidate_id = _candidate_id(record, "a manifest combination")
        if candidate_id in indexed:
            raise _contract("DUPLICATE_CANDIDATE_ID",
                            f"the manifest declares candidate_id {candidate_id!r} twice; a "
                            "repeated identifier is refused, never deduplicated",
                            candidate_id=candidate_id, field="combinations")
        indexed[candidate_id] = _carried(
            record, COMBINATION_CARRIED_FIELDS, f"manifest combination {candidate_id!r}")
    return indexed


def _row(candidate_id, row_kind, carried, combinations):
    """One row. combination is the manifest's own record or a named absence, never guessed."""
    if combinations is None:
        combination, absence = None, MANIFEST_NOT_SUPPLIED
    elif candidate_id not in combinations:
        combination, absence = None, COMBINATION_NOT_DECLARED
    else:
        combination, absence = combinations[candidate_id], None
    row = {"candidate_id": candidate_id, "row_kind": row_kind, "carried": carried,
           "combination": combination, "combination_absence": absence}
    _minted_names_are_clean(
        [name for name in row if name not in _VERBATIM_SUBTREES], where="row")
    return row


def _rows_in_source_order(priority, combinations):
    """Ranked rows in the report's own group/member order, then its own excluded order."""
    ranked, excluded, seen = [], [], []

    def once(candidate_id):
        if candidate_id in seen:
            raise _contract("DUPLICATE_CANDIDATE_ID",
                            f"the source report reports candidate_id {candidate_id!r} more "
                            "than once; it is refused, never merged",
                            candidate_id=candidate_id)
        seen.append(candidate_id)

    for group_entry in _array(priority, "groups", "the priority document"):
        group = _mapping(group_entry, "a priority group", field="groups")
        for member_entry in _array(group, "members", "a priority group"):
            member = _mapping(member_entry, "a priority member", field="members")
            candidate_id = _candidate_id(member, "a priority member")
            once(candidate_id)
            ranked.append(_row(
                candidate_id, ROW_RANKED,
                _carried(member, RANKED_CARRIED_FIELDS,
                         f"priority member {candidate_id!r}", group=group),
                combinations))
    for excluded_entry in _array(priority, "excluded", "the priority document"):
        record = _mapping(excluded_entry, "an excluded entry", field="excluded")
        candidate_id = _candidate_id(record, "an excluded entry")
        once(candidate_id)
        excluded.append(_row(
            candidate_id, ROW_EXCLUDED,
            _carried(record, EXCLUDED_CARRIED_FIELDS,
                     f"excluded entry {candidate_id!r}"),
            combinations))
    return ranked, excluded


def _row_limit(value):
    if value is None:
        return None
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise _contract("INVALID_ROW_LIMIT",
                        "row_limit must be None for every row, or a non-negative plain int; "
                        "it is a display cut and is never inferred, defaulted or clamped",
                        field="row_limit")
    return value


def _digest(payload):
    """sha256 of already-produced bytes. It identifies bytes, nothing else."""
    return hashlib.sha256(payload).hexdigest()


def _source_digest(document):
    """Identify which source document a table was built from.

    The digest is taken over this contract's own canonical serialization of the source, so it
    is stable whether the caller handed over a mapping or bytes. It deliberately does not
    attempt to reproduce the producer's own byte digest, whose serializer settings belong to
    that producer; it identifies content, and it is never an ordering or carried value.
    """
    return None if document is None else _digest(canonical_json(document))


# --------------------------------------------------------------------------
# Verification
# --------------------------------------------------------------------------
def _strict(raw):
    """Parse table bytes; duplicate keys and non-finite tokens are not JSON here."""
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


def _digest_or_none(value, field):
    if value is None:
        return None
    if type(value) is not str or len(value) != 64 or value.strip("0123456789abcdef") != "":
        raise _invalid("MALFORMED_DOCUMENT",
                       f"{field} must be 64 lowercase hex characters or null", field=field)
    return value


def _verified_table(data):
    """Re-derive every derived field of a table and reject any difference."""
    if type(data) is not dict:
        raise _invalid("MALFORMED_DOCUMENT", "a table must be a JSON object")
    unknown = sorted(set(data) - set(TABLE_FIELDS))
    if unknown:
        raise _invalid("UNKNOWN_FIELD",
                       f"unknown table fields {unknown}; the declared fields are "
                       f"{list(TABLE_FIELDS)}", field=unknown[0])
    missing = [name for name in TABLE_FIELDS if name not in data]
    if missing:
        raise _invalid("MISSING_FIELD", f"missing table fields {missing}", field=missing[0])
    _minted_names_are_clean(data.keys(), where="table")
    if data["document_type"] != TABLE_DOCUMENT_TYPE:
        raise _invalid("MALFORMED_DOCUMENT",
                       f"document_type must be exactly {TABLE_DOCUMENT_TYPE!r}",
                       field="document_type")
    if data["non_claim"] != TABLE_NON_CLAIM:
        raise _invalid("NON_CLAIM_ALTERED",
                       "non_claim must be emitted verbatim; it is never reworded, abridged "
                       "or parameterized", field="non_claim")
    if data["table_kind"] != TABLE_KIND:
        raise _invalid("MALFORMED_DOCUMENT",
                       f"table_kind is fixed to {TABLE_KIND!r} and no request can change it",
                       field="table_kind")
    _digest_or_none(data["source_priority_digest"], "source_priority_digest")
    _digest_or_none(data["source_manifest_digest"], "source_manifest_digest")
    rows = _verified_rows(data)
    _verified_window(data, rows)


def _verified_rows(data):
    if type(data["rows"]) is not list:
        raise _invalid("MALFORMED_DOCUMENT", "rows must be an array", field="rows")
    in_ranked_prefix = True
    for row in data["rows"]:
        if type(row) is not dict:
            raise _invalid("MALFORMED_DOCUMENT", "a row must be a JSON object", field="rows")
        if sorted(row) != sorted(ROW_FIELDS):
            raise _invalid("MALFORMED_DOCUMENT",
                           f"a row declares exactly {list(ROW_FIELDS)}", field="rows")
        _minted_names_are_clean(
            [name for name in row if name not in _VERBATIM_SUBTREES], where="row")
        if row["row_kind"] not in ROW_KINDS:
            raise _invalid("MALFORMED_DOCUMENT",
                           f"row_kind must be one of {list(ROW_KINDS)}", field="row_kind")
        if type(row["carried"]) is not dict:
            raise _invalid("MALFORMED_DOCUMENT", "carried must be a JSON object",
                           field="carried")
        expected = (RANKED_CARRIED_FIELDS if row["row_kind"] == ROW_RANKED
                    else EXCLUDED_CARRIED_FIELDS)
        if sorted(row["carried"]) != sorted(expected):
            raise _invalid("MALFORMED_DOCUMENT",
                           f"a {row['row_kind']} row carries exactly {list(expected)}; the "
                           "pointer set is fixed by this contract",
                           candidate_id=row["candidate_id"], field="carried")
        if (row["combination"] is None) == (row["combination_absence"] is None):
            raise _invalid("MALFORMED_DOCUMENT",
                           "a row carries a combination or a named absence, never both and "
                           "never neither; an absent combination is never a bare null",
                           candidate_id=row["candidate_id"], field="combination_absence")
        if (row["combination_absence"] is not None
                and row["combination_absence"] not in COMBINATION_ABSENCE_REASONS):
            raise _invalid("MALFORMED_DOCUMENT",
                           f"combination_absence must be one of "
                           f"{list(COMBINATION_ABSENCE_REASONS)}",
                           candidate_id=row["candidate_id"], field="combination_absence")
        if row["combination"] is not None and sorted(row["combination"]) != sorted(
                COMBINATION_CARRIED_FIELDS):
            raise _invalid("MALFORMED_DOCUMENT",
                           f"a combination carries exactly "
                           f"{list(COMBINATION_CARRIED_FIELDS)}",
                           candidate_id=row["candidate_id"], field="combination")
        if row["row_kind"] == ROW_RANKED and not in_ranked_prefix:
            raise _invalid("MALFORMED_DOCUMENT",
                           "every ranked row precedes every excluded row; the two sections "
                           "are never interleaved", field="rows")
        in_ranked_prefix = in_ranked_prefix and row["row_kind"] == ROW_RANKED
    if data["row_order"] != [row["candidate_id"] for row in data["rows"]]:
        raise _invalid("ROW_ORDER_NOT_DERIVED",
                       "row_order must be exactly the candidate_id of each row, in row "
                       "order; a supplied order is never trusted, sorted or normalized",
                       field="row_order")
    identifiers = data["row_order"]
    if len(set(identifiers)) != len(identifiers):
        raise _invalid("DUPLICATE_CANDIDATE_ID", "a candidate_id appears on two rows",
                       field="row_order")
    return data["rows"]


def _verified_window(data, rows):
    window = data["display_window"]
    if type(window) is not dict or sorted(window) != sorted(WINDOW_FIELDS):
        raise _invalid("MALFORMED_DOCUMENT",
                       f"display_window declares exactly {list(WINDOW_FIELDS)}",
                       field="display_window")
    _minted_names_are_clean(window.keys(), where="display_window")
    shown = len([row for row in rows if row["row_kind"] == ROW_RANKED])
    if window["ranked_rows_shown"] != shown:
        raise _invalid("WINDOW_NOT_DERIVED",
                       "ranked_rows_shown must equal the number of ranked rows present",
                       field="ranked_rows_shown")
    total = window["ranked_rows_in_source"]
    if type(total) is not int or isinstance(total, bool) or total < shown:
        raise _invalid("WINDOW_NOT_DERIVED",
                       "ranked_rows_in_source must be an int no smaller than "
                       "ranked_rows_shown; a window never invents rows",
                       field="ranked_rows_in_source")
    limit = window["declared_row_limit"]
    if limit is not None and (type(limit) is not int or isinstance(limit, bool) or limit < 0):
        raise _invalid("WINDOW_NOT_DERIVED",
                       "declared_row_limit must be null or a non-negative int",
                       field="declared_row_limit")
    if window["truncated"] is not (shown < total):
        raise _invalid("WINDOW_NOT_DERIVED",
                       "truncated must state exactly whether ranked rows were withheld",
                       field="truncated")
    if limit is None and shown != total:
        raise _invalid("WINDOW_NOT_DERIVED",
                       "a table with no declared row limit shows every ranked row",
                       field="declared_row_limit")
    if limit is not None and shown != min(limit, total):
        raise _invalid("WINDOW_NOT_DERIVED",
                       "a declared row limit shows the leading min(limit, source) ranked "
                       "rows; it never reorders or reaches past the source",
                       field="declared_row_limit")


# --------------------------------------------------------------------------
# Document
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class CandidateCombinationsTable:
    """An immutable candidate_combinations_table/1 document, held only as canonical bytes."""

    json_bytes: bytes

    def __post_init__(self):
        if type(self.json_bytes) is not bytes:
            raise _invalid("MALFORMED_DOCUMENT", "json_bytes must be bytes")
        data = _strict(self.json_bytes)
        _verified_table(data)
        if canonical_json(data) != self.json_bytes:
            raise _invalid("NOT_CANONICAL_BYTES",
                           "bytes are not the canonical serialization of the document")

    @classmethod
    def from_dict(cls, data):
        _verified_table(data)
        try:
            return cls(canonical_json(data))
        except CandidateCombinationsTableError:
            raise
        except (TypeError, ValueError) as exc:
            raise _invalid("MALFORMED_DOCUMENT", f"not a JSON document: {exc}") from None

    @property
    def document_type(self):
        return self.to_dict()["document_type"]

    @property
    def table_kind(self):
        return self.to_dict()["table_kind"]

    @property
    def non_claim(self):
        return self.to_dict()["non_claim"]

    @property
    def row_order(self):
        """A fresh list on every call; the document is never handed out by reference."""
        return self.to_dict()["row_order"]

    @property
    def rows(self):
        return self.to_dict()["rows"]

    @property
    def display_window(self):
        return self.to_dict()["display_window"]

    @property
    def source_priority_digest(self):
        return self.to_dict()["source_priority_digest"]

    @property
    def source_manifest_digest(self):
        return self.to_dict()["source_manifest_digest"]

    @property
    def digest(self):
        return _digest(self.json_bytes)

    def ranked_rows(self):
        return [row for row in self.rows if row["row_kind"] == ROW_RANKED]

    def excluded_rows(self):
        return [row for row in self.rows if row["row_kind"] == ROW_EXCLUDED]

    def to_dict(self):
        return json.loads(self.json_bytes)

    def to_json_bytes(self):
        return self.json_bytes


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def build_combinations_table(priority_document, *, manifest_document=None, row_limit=None):
    """Restate a finished priority report as rows, in the report's own order.

    ``priority_document`` is a serialized cassette_candidate_priority/1 document, as a
    mapping or its canonical bytes. ``manifest_document``, when supplied, is a serialized
    demo_candidate_manifest/1 document whose already-declared combinations are joined by
    exact candidate_id. ``row_limit`` is an explicitly declared display cut on the ranked
    section; None shows every row.

    Pure: reads no file, imports no producer, and computes no order. Ranked rows follow the
    report's groups and members arrays, excluded rows follow its excluded array, and no row
    is sorted, regrouped, filtered, scored or dropped.
    """
    priority = _source_document(priority_document, SOURCE_PRIORITY_DOCUMENT_TYPE,
                               "the priority document")
    manifest = (None if manifest_document is None
                else _source_document(manifest_document, SOURCE_MANIFEST_DOCUMENT_TYPE,
                                      "the manifest document"))
    limit = _row_limit(row_limit)
    ranked, excluded = _rows_in_source_order(priority, _combinations_by_candidate(manifest))
    shown = ranked if limit is None else ranked[:limit]
    rows = shown + excluded
    return CandidateCombinationsTable.from_dict({
        "document_type": TABLE_DOCUMENT_TYPE,
        "non_claim": TABLE_NON_CLAIM,
        "table_kind": TABLE_KIND,
        "source_priority_digest": _source_digest(priority),
        "source_manifest_digest": _source_digest(manifest),
        "display_window": {
            "declared_row_limit": limit,
            "ranked_rows_in_source": len(ranked),
            "ranked_rows_shown": len(shown),
            "truncated": len(shown) < len(ranked),
        },
        "row_order": [row["candidate_id"] for row in rows],
        "rows": rows,
    })


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------
def _cell(value):
    if value is None:
        return "-"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) in (int, str):
        return str(value)
    return canonical_json(value).decode("utf-8")


def _combination_cell(row):
    if row["combination"] is None:
        return "-" if row["combination_absence"] is None else row["combination_absence"]
    return " | ".join(
        ("UNENGAGED" if choice.get("label") is None else str(choice.get("label")))
        for choice in row["combination"]["choices"])


def _section(rows, names, heading):
    lines = [heading]
    if not rows:
        return lines + ["  (none)"]
    lines.append("  " + " | ".join(("candidate_id", *names, "combination")))
    for row in rows:
        lines.append("  " + " | ".join(
            (row["candidate_id"], *(_cell(row["carried"][name]) for name in names),
             _combination_cell(row))))
    return lines


def render_table_lines(table):
    """Return fresh display lines for one table, in document row order."""
    if not isinstance(table, CandidateCombinationsTable):
        raise _contract("MALFORMED_DOCUMENT",
                        f"table must be a CandidateCombinationsTable, got "
                        f"{type(table).__qualname__}")
    data = table.to_dict()
    window = data["display_window"]
    lines = [TABLE_DISPLAY_DISCLAIMER, "",
             f"document_type: {data['document_type']}",
             f"table_kind: {data['table_kind']}",
             f"source_priority_digest: {_cell(data['source_priority_digest'])}",
             f"source_manifest_digest: {_cell(data['source_manifest_digest'])}",
             f"ranked rows shown: {window['ranked_rows_shown']} of "
             f"{window['ranked_rows_in_source']} in source"
             f"{' (truncated by a declared display limit)' if window['truncated'] else ''}"]
    lines.extend(_section(table.ranked_rows(), RANKED_CARRIED_FIELDS,
                          "Ranked rows, in the source report's own order:"))
    lines.extend(_section(table.excluded_rows(), EXCLUDED_CARRIED_FIELDS,
                          "Excluded rows, in the source report's own order (never ranked, "
                          "never hidden by a row limit):"))
    return lines


# --------------------------------------------------------------------------
# Notebook surface
# --------------------------------------------------------------------------
#: Paste-ready cells. They are text here, not an edit: this module writes nothing into any
#: notebook. The code cell reads two documents the caller already has in the notebook
#: namespace and prints a table; it enters no evaluation path and produces no order.
_CELLS = (
    ("combinations-table-00-section", "markdown", """\
## Candidate combinations table

Descriptive restatement of a finished `cassette_candidate_priority/1` report
(`candidate_combinations_table/1`), optionally joined to the combinations a
`demo_candidate_manifest/1` document already declared.

This view computes no order and mints no value. Ranked rows follow the source report's own
groups and members arrays; excluded rows follow its own excluded array, in a separate
section, and are never hidden. `rank`, `geometry_tier`, `evidence_coverage`,
`ineligibility_reason` and `vetoed_slots` are carried from the source unchanged. Nothing
here sorts, scores, weights, combines, filters or recommends, and a declared row limit is a
display cut over the order the source already fixed, never a selection or a shortlist.
Equal rank means equal tier, exactly as the source says.
"""),
    ("combinations-table-01-render", "code", """\
from structure_audit.candidate_combinations_table import (
    build_combinations_table, render_table_lines,
)

# PRIORITY_DOCUMENT is a finished cassette_candidate_priority/1 document, as a dict or its
# canonical bytes, produced earlier by its own layer. MANIFEST_DOCUMENT is optional.
# Nothing is recomputed here and no producer is imported.
table = build_combinations_table(
    PRIORITY_DOCUMENT,
    manifest_document=MANIFEST_DOCUMENT,
    row_limit=None,           # None shows every ranked row; an int is a display cut only
)
print("\\n".join(render_table_lines(table)))
"""),
)


def notebook_cell_sources():
    """Return the paste-ready (cell_id, cell_type, source) triples, fresh on every call.

    This is the notebook surface: text a reader pastes, never an edit this module performs.
    No notebook is opened, parsed or written.
    """
    return tuple((cell_id, cell_type, source) for cell_id, cell_type, source in _CELLS)
