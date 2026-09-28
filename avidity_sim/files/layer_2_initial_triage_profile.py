"""Layer 2 initial triage profile (contract ``layer_2_initial_triage_profile/1``).

Standard library only. This module reads three kinds of already-finished serialized
documents — one cohort-level ``cassette_candidate_priority/1`` report, three
``layer_2a_descriptor_input/1`` local documents per candidate and one
``layer_2b_descriptor_input/1`` collective document per candidate — and emits one
canonical triage profile for an explicitly declared comparison cohort.

It opens no file, resolves no locator, reads no clock or environment, starts no
subprocess and reaches no network. It imports no producer and no input module: the
documents arrive as mappings or as their canonical bytes.

WHAT IS NEVER DONE

  No score, weight, probability, fitted parameter, learned model or biological
  interpretation. No scalar is minted. No ordering direction is inferred, guessed,
  defaulted or hardcoded: every direction is caller-declared, and a dimension without a
  declared direction is suspended. Values are never aggregated, averaged, summed,
  normalized or picked by heuristic, units are never converted, and candidate identifiers
  and input order are never used to break a tie. Layer 1 exclusions and vetoes are
  binding and are never rescued or reinterpreted. Missing evidence is not negative
  evidence: ``REVIEW_REQUIRED`` and ``COMPARISON_UNSUPPORTED`` are not losses.

ERRORS

  ``Layer2TriageProfileError`` exposes exactly ``.code`` (one ``TRIAGE_ERROR_CODES``
  token), ``.field`` (JSON Pointer, root is ``""``), ``.index`` (outermost array index
  involved, or None) and ``.message``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import json

# ================================================================================
# Contract constants and closed vocabularies
# ================================================================================

TRIAGE_DOCUMENT_TYPE = "layer_2_initial_triage_profile/1"
TRIAGE_CONVENTION_VERSION = "layer_2_initial_triage/1"

SOURCE_PRIORITY_DOCUMENT_TYPE = "cassette_candidate_priority/1"
SOURCE_LOCAL_DOCUMENT_TYPE = "layer_2a_descriptor_input/1"
SOURCE_COLLECTIVE_DOCUMENT_TYPE = "layer_2b_descriptor_input/1"

#: Layer 1's own deterministic order. Copied, never recomputed.
TIER_ORDER = (
    "T1_ENGAGED_SLOTS_FULLY_RESOLVED",
    "T2_ENGAGED_SLOTS_PARTIALLY_RESOLVED",
    "T3_NO_RESOLVED_ENGAGED_SLOT",
)

GATES = (
    "IDENTITY_PROVENANCE",
    "LAYER1_BOUNDARY",
    "COHORT_COMPARABILITY",
    "COLLECTIVE_SCOPE",
    "REQUIRED_COLLECTIVE_EVIDENCE",
    "COMMON_ACTIVE_DIMENSIONS",
)
GATE_DISPOSITIONS = ("PASSED", "FAILED", "NOT_EVALUATED")
GATE_FAILURE_REASONS = (
    "CANDIDATE_IDENTITY_MISMATCH",
    "LOCAL_POSITION_SET_MISMATCH",
    "LAYER1_ENTRY_ABSENT",
    "LAYER1_EXCLUDED",
    "TARGET_SYSTEM_IDENTITY_MISMATCH",
    "LAYER1_COMPARISON_BASIS_MISMATCH",
    "COLLECTIVE_TASK_SCOPE_MISMATCH",
    "ORDERED_LOCAL_ROLES_MISMATCH",
    "CONVENTION_VERSION_MISMATCH",
    "COLLECTIVE_SCOPE_INCOMPLETE",
    "REQUIRED_COLLECTIVE_EVIDENCE_ABSENT",
    "NO_COMMON_ACTIVE_DIMENSION",
)

PROFILE_STATES = (
    "EXPERIMENTAL_PRIORITY",
    "EXPERIMENTAL_PRIORITY_TIE",
    "NOT_PRIORITIZED_BY_PROFILE",
    "REVIEW_REQUIRED",
    "COMPARISON_UNSUPPORTED",
)

COLLECTIVE_DIMENSIONS = (
    "COLLECTIVE_INTERFERENCE",
    "COLLECTIVE_DEFORMATION_RESTRAINT_BURDEN",
)
LOCAL_TIE_BREAK_DIMENSION = "LOCAL_ISOLATED_REFERENCE_DEFORMATION_BURDEN"
TRIAGE_DIMENSIONS = COLLECTIVE_DIMENSIONS + (LOCAL_TIE_BREAK_DIMENSION,)

DIRECTIONS = ("LOWER_IS_PREFERRED", "HIGHER_IS_PREFERRED", "NO_DIRECTION_DECLARED")
DIMENSION_STATES = ("ACTIVE", "SUSPENDED")
SUSPENSION_REASONS = (
    "NO_DIRECTION_DECLARED",
    "NO_QUALIFYING_DESCRIPTOR",
    "MULTIPLE_QUALIFYING_DESCRIPTORS",
    "NO_QUALIFYING_OBSERVATION",
    "MULTIPLE_QUALIFYING_OBSERVATIONS",
    "OBSERVABLE_NAME_MISMATCH",
    "DEFINITION_REFERENCE_MISMATCH",
    "UNIT_CLASS_MISMATCH",
    "UNIT_SYMBOL_MISMATCH",
    "LAYER1_STATUS_NOT_RETAINED",
    "CANDIDATE_NOT_GATE_PASSED",
)

RELATION_SCOPES = ("COHORT_WIDE", "GATE_PASSED_SUBSET_ONLY")
RELATION_WITHHELD_REASONS = (
    "RETAINED_MEMBER_NOT_GATE_PASSED",
    "NO_GATE_PASSED_CANDIDATE",
)
LAYER1_DISPOSITIONS = ("RANKED", "EXCLUDED", "ABSENT")

TRIAGE_ERROR_CODES = (
    "STRUCTURAL_INVALID",
    "REFERENCE_INVALID",
    "INVARIANT_INVALID",
    "NON_CANONICAL_BYTES",
)

TRIAGE_NON_CLAIM = (
    "This profile restates already-finished Layer 1 outcomes and supplied Layer 2 "
    "descriptors for one explicitly declared comparison cohort, under caller-declared "
    "directions. It mints no score, weight or probability, establishes no binding, "
    "affinity, avidity, thermodynamic truth, compatibility, biological activity, safety "
    "or experimental success, and changes no deterministic outcome. Missing evidence is "
    "not negative evidence, and a withheld or subset-only relation is not a ranking of "
    "the cohort."
)


# ================================================================================
# The single exception type
# ================================================================================


def _outermost_index(pointer):
    if not pointer:
        return None
    for token in pointer.split("/")[1:]:
        if token and all("0" <= character <= "9" for character in token):
            return int(token)
    return None


class Layer2TriageProfileError(ValueError):
    """The only error this module raises."""

    __slots__ = ("code", "field", "index", "message")

    def __init__(self, code, field, message):
        if code not in TRIAGE_ERROR_CODES:
            raise AssertionError("error code outside the closed vocabulary")
        self.code = code
        self.field = field
        self.index = _outermost_index(field)
        self.message = message
        super().__init__(
            "{0} at {1}: {2}".format(code, field if field else "<root>", message)
        )


def _fail(code, field, message):
    raise Layer2TriageProfileError(code, field, message)


def _structural(field_path, message):
    _fail("STRUCTURAL_INVALID", field_path, message)


def _reference_error(field_path, message):
    _fail("REFERENCE_INVALID", field_path, message)


def _invariant(field_path, message):
    _fail("INVARIANT_INVALID", field_path, message)


# ================================================================================
# Primitives
# ================================================================================


def _is_control(character):
    return character < " " or character == "\x7f"


def _identifier(value, field_path):
    if not isinstance(value, str):
        _structural(field_path, "identifier must be a string")
    if value == "":
        _structural(field_path, "identifier must not be empty")
    for character in value:
        if _is_control(character):
            _structural(field_path, "identifier must not contain control characters")
    if value != value.strip():
        _structural(field_path, "identifier must not have leading or trailing whitespace")
    return value


def _opt_identifier(value, field_path):
    return None if value is None else _identifier(value, field_path)


def _text(value, field_path):
    if not isinstance(value, str):
        _structural(field_path, "text must be a string")
    if value == "":
        _structural(field_path, "text must not be empty; absence is explicit null")
    return value


def _opt_text(value, field_path):
    return None if value is None else _text(value, field_path)


def _token(value, allowed, field_path):
    if not isinstance(value, str):
        _structural(field_path, "token must be a string")
    if value not in allowed:
        _structural(field_path, "token outside the closed vocabulary")
    return value


def _opt_token(value, allowed, field_path):
    return None if value is None else _token(value, allowed, field_path)


def _timestamp(value, field_path):
    """Exactly ``YYYY-MM-DDTHH:mm:ssZ``, caller-supplied. No clock is read."""
    if not isinstance(value, str):
        _structural(field_path, "timestamp must be a string")
    if len(value) != 20 or value[4] != "-" or value[7] != "-" or value[10] != "T":
        _structural(field_path, "timestamp must be exactly YYYY-MM-DDTHH:mm:ssZ")
    if value[13] != ":" or value[16] != ":" or value[19] != "Z":
        _structural(field_path, "timestamp must be exactly YYYY-MM-DDTHH:mm:ssZ")
    parts = (value[0:4], value[5:7], value[8:10], value[11:13], value[14:16], value[17:19])
    for part in parts:
        if not part.isdigit() or not part.isascii():
            _structural(field_path, "timestamp fields must be ASCII digits")
    year, month, day, hour, minute, second = (int(part) for part in parts)
    if not 1 <= month <= 12 or hour > 23 or minute > 59 or second > 59:
        _structural(field_path, "timestamp carries an impossible calendar field")
    days = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)[month - 1]
    if month == 2 and (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
        days = 29
    if not 1 <= day <= days:
        _structural(field_path, "timestamp carries an impossible calendar field")
    return value


def _decimal_order_key(value, field_path):
    """An exact ordering key for a supplied decimal string. The string is never rewritten."""
    if not isinstance(value, str) or value == "":
        _structural(field_path, "decimal must be a non-empty string")
    body = value[1:] if value.startswith("-") else value
    integer, _, fraction = body.partition(".")
    for part in (integer, fraction) if fraction else (integer,):
        if not part.isdigit() or not part.isascii():
            _structural(field_path, "decimal must carry only ASCII digits")
    return Decimal(value)


def _tuple(value, field_path):
    if isinstance(value, (str, bytes, dict)) or not hasattr(value, "__iter__"):
        _structural(field_path, "value must be a sequence")
    return tuple(value)


def _record_tuple(value, expected, field_path):
    items = _tuple(value, field_path)
    for position, item in enumerate(items):
        if type(item) is not expected:
            _structural(
                "{0}/{1}".format(field_path, position),
                "value must be a {0} record".format(expected.__name__),
            )
    return items


def _no_duplicates(items, field_path, what):
    seen = set()
    for position, item in enumerate(items):
        if item in seen:
            _invariant(
                "{0}/{1}".format(field_path, position),
                "{0} must not contain exact duplicates".format(what),
            )
        seen.add(item)


def _canonical_bytes(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


# ================================================================================
# Supplied-document access (mapping or canonical bytes; nothing is opened)
# ================================================================================


def _source_document(value, expected_type, field_path):
    if isinstance(value, (bytes, bytearray)):
        try:
            value = json.loads(bytes(value).decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            _structural(field_path, "supplied bytes are not one JSON document")
    if not isinstance(value, dict):
        _structural(field_path, "a supplied document must be a mapping or canonical bytes")
    if value.get("document_type") != expected_type:
        _structural(
            field_path,
            "document_type must be exactly {0!r}".format(expected_type),
        )
    return value


def _mapping(value, field_path):
    if not isinstance(value, dict):
        _structural(field_path, "value must be a mapping")
    return value


def _array(value, field_path):
    if not isinstance(value, list):
        _structural(field_path, "value must be an array")
    return value


def _required(mapping, key, field_path):
    if key not in mapping:
        _structural("{0}/{1}".format(field_path, key), "required key is absent")
    return mapping[key]


# ================================================================================
# Declaration and input records
# ================================================================================


@dataclass(frozen=True)
class TriageDimensionDirection:
    """One caller-declared comparison direction. Nothing here is inferred."""

    dimension: str
    direction: str

    def __post_init__(self):
        _token(self.dimension, TRIAGE_DIMENSIONS, "/dimension")
        _token(self.direction, DIRECTIONS, "/direction")

    def as_dict(self):
        return {"dimension": self.dimension, "direction": self.direction}


@dataclass(frozen=True)
class TriageCohortDeclaration:
    """The explicitly declared comparison cohort. Every field is caller-supplied."""

    target_system_identity: str
    layer1_comparison_basis: str
    ordered_local_position_roles: tuple
    collective_task_scope_type: str
    triage_convention_version: str
    dimension_directions: tuple

    def __post_init__(self):
        _identifier(self.target_system_identity, "/target_system_identity")
        _identifier(self.layer1_comparison_basis, "/layer1_comparison_basis")
        roles = _tuple(self.ordered_local_position_roles, "/ordered_local_position_roles")
        for position, role in enumerate(roles):
            _identifier(role, "/ordered_local_position_roles/{0}".format(position))
        if len(roles) != 3:
            _invariant(
                "/ordered_local_position_roles",
                "exactly three ordered local positions are declared",
            )
        _no_duplicates(roles, "/ordered_local_position_roles", "local positions")
        object.__setattr__(self, "ordered_local_position_roles", roles)
        _text(self.collective_task_scope_type, "/collective_task_scope_type")
        _identifier(self.triage_convention_version, "/triage_convention_version")
        directions = _record_tuple(
            self.dimension_directions, TriageDimensionDirection, "/dimension_directions"
        )
        declared = tuple(item.dimension for item in directions)
        if declared != TRIAGE_DIMENSIONS:
            _invariant(
                "/dimension_directions",
                "each dimension is declared exactly once, in TRIAGE_DIMENSIONS order",
            )
        object.__setattr__(self, "dimension_directions", directions)

    def direction_of(self, dimension):
        for item in self.dimension_directions:
            if item.dimension == dimension:
                return item.direction
        raise AssertionError("dimension outside the closed vocabulary")

    def as_dict(self):
        return {
            "target_system_identity": self.target_system_identity,
            "layer1_comparison_basis": self.layer1_comparison_basis,
            "ordered_local_position_roles": list(self.ordered_local_position_roles),
            "collective_task_scope_type": self.collective_task_scope_type,
            "triage_convention_version": self.triage_convention_version,
            "dimension_directions": [item.as_dict() for item in self.dimension_directions],
        }


@dataclass(frozen=True)
class TriageLocalInput:
    """One ordered local position and the layer_2a document declared for it."""

    position_role: str
    document: dict

    def __post_init__(self):
        _identifier(self.position_role, "/position_role")
        object.__setattr__(
            self,
            "document",
            _source_document(self.document, SOURCE_LOCAL_DOCUMENT_TYPE, "/document"),
        )


@dataclass(frozen=True)
class TriageCandidateInput:
    """One candidate: three ordered local documents and one collective document."""

    candidate_id: str
    local_inputs: tuple
    collective_document: dict

    def __post_init__(self):
        _identifier(self.candidate_id, "/candidate_id")
        locals_ = _record_tuple(self.local_inputs, TriageLocalInput, "/local_inputs")
        if len(locals_) != 3:
            _invariant("/local_inputs", "exactly three local documents are required")
        object.__setattr__(self, "local_inputs", locals_)
        object.__setattr__(
            self,
            "collective_document",
            _source_document(
                self.collective_document,
                SOURCE_COLLECTIVE_DOCUMENT_TYPE,
                "/collective_document",
            ),
        )


# ================================================================================
# Emitted records
# ================================================================================


@dataclass(frozen=True)
class TriageGateDisposition:
    gate: str
    disposition: str
    reason: str | None

    def __post_init__(self):
        _token(self.gate, GATES, "/gate")
        _token(self.disposition, GATE_DISPOSITIONS, "/disposition")
        _opt_token(self.reason, GATE_FAILURE_REASONS, "/reason")
        if (self.disposition == "FAILED") != (self.reason is not None):
            _invariant("/reason", "a failed gate carries exactly one reason")

    def as_dict(self):
        return {"gate": self.gate, "disposition": self.disposition, "reason": self.reason}


@dataclass(frozen=True)
class TriageComparableRecord:
    """The one comparable observation a candidate contributes for one dimension."""

    descriptor_id: str
    observation_id: str
    value: str
    observable_name: str
    definition_reference: object
    unit_class: str | None
    unit_symbol: str | None

    def __post_init__(self):
        _identifier(self.descriptor_id, "/descriptor_id")
        _identifier(self.observation_id, "/observation_id")
        _text(self.value, "/value")
        _text(self.observable_name, "/observable_name")
        try:
            _canonical_bytes(self.definition_reference)
        except (TypeError, ValueError):
            _structural("/definition_reference", "the supplied reference is not JSON data")
        _opt_text(self.unit_class, "/unit_class")
        _opt_text(self.unit_symbol, "/unit_symbol")

    def comparability_key(self):
        return (
            self.observable_name,
            _canonical_bytes(self.definition_reference),
            self.unit_class,
            self.unit_symbol,
        )

    def as_dict(self):
        return {
            "descriptor_id": self.descriptor_id,
            "observation_id": self.observation_id,
            "value": self.value,
            "observable_name": self.observable_name,
            "definition_reference": json.loads(
                _canonical_bytes(self.definition_reference).decode("utf-8")
            ),
            "unit_class": self.unit_class,
            "unit_symbol": self.unit_symbol,
        }


@dataclass(frozen=True)
class TriageDimensionState:
    dimension: str
    position_role: str | None
    state: str
    direction: str
    suspension_reason: str | None
    record: TriageComparableRecord | None

    def __post_init__(self):
        _token(self.dimension, TRIAGE_DIMENSIONS, "/dimension")
        _opt_identifier(self.position_role, "/position_role")
        _token(self.state, DIMENSION_STATES, "/state")
        _token(self.direction, DIRECTIONS, "/direction")
        _opt_token(self.suspension_reason, SUSPENSION_REASONS, "/suspension_reason")
        if (self.state == "SUSPENDED") != (self.suspension_reason is not None):
            _invariant("/suspension_reason", "a suspended dimension carries one reason")
        if self.record is not None and type(self.record) is not TriageComparableRecord:
            _structural("/record", "value must be a TriageComparableRecord record")
        if self.state == "ACTIVE" and self.record is None:
            _invariant("/record", "an active dimension carries its comparable record")

    def as_dict(self):
        return {
            "dimension": self.dimension,
            "position_role": self.position_role,
            "state": self.state,
            "direction": self.direction,
            "suspension_reason": self.suspension_reason,
            "record": None if self.record is None else self.record.as_dict(),
        }


@dataclass(frozen=True)
class TriageLayer1Outcome:
    """The candidate's Layer 1 entry, copied. Nothing is recomputed or rescued."""

    disposition: str
    source_pointer: str | None
    rank: int | None
    geometry_tier: str | None
    evidence_coverage: str | None
    ineligibility_reason: str | None

    def __post_init__(self):
        _token(self.disposition, LAYER1_DISPOSITIONS, "/disposition")
        _opt_text(self.source_pointer, "/source_pointer")
        if (self.disposition == "ABSENT") != (self.source_pointer is None):
            _invariant("/source_pointer", "only an absent entry carries no pointer")
        if self.rank is not None and (type(self.rank) is not int or self.rank < 1):
            _structural("/rank", "rank must be a 1-based integer or null")
        _opt_token(self.geometry_tier, TIER_ORDER, "/geometry_tier")
        _opt_text(self.evidence_coverage, "/evidence_coverage")
        _opt_text(self.ineligibility_reason, "/ineligibility_reason")

    def as_dict(self):
        return {
            "disposition": self.disposition,
            "source_pointer": self.source_pointer,
            "rank": self.rank,
            "geometry_tier": self.geometry_tier,
            "evidence_coverage": self.evidence_coverage,
            "ineligibility_reason": self.ineligibility_reason,
        }


@dataclass(frozen=True)
class TriageSourceReference:
    """An exact reference to one supplied document. Its contents are not copied."""

    document_type: str
    document_id: str | None
    revision: str | None
    position_role: str | None

    def __post_init__(self):
        _text(self.document_type, "/document_type")
        _opt_identifier(self.document_id, "/document_id")
        _opt_identifier(self.revision, "/revision")
        _opt_identifier(self.position_role, "/position_role")

    def as_dict(self):
        return {
            "document_type": self.document_type,
            "document_id": self.document_id,
            "revision": self.revision,
            "position_role": self.position_role,
        }


@dataclass(frozen=True)
class TriageCandidateProfile:
    candidate_id: str
    profile_state: str
    layer1: TriageLayer1Outcome
    gates: tuple
    dimensions: tuple
    sources: tuple

    def __post_init__(self):
        _identifier(self.candidate_id, "/candidate_id")
        _token(self.profile_state, PROFILE_STATES, "/profile_state")
        if type(self.layer1) is not TriageLayer1Outcome:
            _structural("/layer1", "value must be a TriageLayer1Outcome record")
        gates = _record_tuple(self.gates, TriageGateDisposition, "/gates")
        if tuple(item.gate for item in gates) != GATES:
            _invariant("/gates", "every gate is reported exactly once, in GATES order")
        object.__setattr__(self, "gates", gates)
        dimensions = _record_tuple(self.dimensions, TriageDimensionState, "/dimensions")
        object.__setattr__(self, "dimensions", dimensions)
        sources = _record_tuple(self.sources, TriageSourceReference, "/sources")
        object.__setattr__(self, "sources", sources)

    def as_dict(self):
        return {
            "candidate_id": self.candidate_id,
            "profile_state": self.profile_state,
            "layer1": self.layer1.as_dict(),
            "gates": [item.as_dict() for item in self.gates],
            "dimensions": [item.as_dict() for item in self.dimensions],
            "sources": [item.as_dict() for item in self.sources],
        }


@dataclass(frozen=True)
class TriageRestrictedRelation:
    """The emitted order. Subset-only relations are labeled, never presented as cohort-wide."""

    scope: str
    withheld_reason: str | None
    ordered_groups: tuple
    basis_dimensions: tuple

    def __post_init__(self):
        _token(self.scope, RELATION_SCOPES, "/scope")
        _opt_token(self.withheld_reason, RELATION_WITHHELD_REASONS, "/withheld_reason")
        if (self.scope == "GATE_PASSED_SUBSET_ONLY") != (self.withheld_reason is not None):
            _invariant(
                "/withheld_reason",
                "a subset-only relation carries exactly one withheld reason",
            )
        groups = _tuple(self.ordered_groups, "/ordered_groups")
        checked = []
        for position, group in enumerate(groups):
            members = _tuple(group, "/ordered_groups/{0}".format(position))
            for offset, member in enumerate(members):
                _identifier(member, "/ordered_groups/{0}/{1}".format(position, offset))
            if not members:
                _invariant(
                    "/ordered_groups/{0}".format(position), "a group is never empty"
                )
            checked.append(members)
        object.__setattr__(self, "ordered_groups", tuple(checked))
        basis = _tuple(self.basis_dimensions, "/basis_dimensions")
        for position, dimension in enumerate(basis):
            _token(dimension, TRIAGE_DIMENSIONS, "/basis_dimensions/{0}".format(position))
        object.__setattr__(self, "basis_dimensions", basis)

    def as_dict(self):
        return {
            "scope": self.scope,
            "withheld_reason": self.withheld_reason,
            "ordered_groups": [list(group) for group in self.ordered_groups],
            "basis_dimensions": list(self.basis_dimensions),
        }


_TOP_LEVEL_KEYS = (
    "document_type",
    "profile_id",
    "revision",
    "declared_by",
    "declared_at",
    "cohort",
    "layer1_source",
    "cohort_dimensions",
    "candidates",
    "relation",
    "non_claim",
)


@dataclass(frozen=True)
class Layer2InitialTriageProfile:
    """One immutable ``layer_2_initial_triage_profile/1`` document."""

    profile_id: str
    revision: str
    declared_by: str
    declared_at: str
    cohort: TriageCohortDeclaration
    layer1_source: TriageSourceReference
    cohort_dimensions: tuple
    candidates: tuple
    relation: TriageRestrictedRelation
    document_type: str = field(init=False, default=TRIAGE_DOCUMENT_TYPE)
    non_claim: str = field(init=False, default=TRIAGE_NON_CLAIM)

    def __post_init__(self):
        _identifier(self.profile_id, "/profile_id")
        _identifier(self.revision, "/revision")
        _identifier(self.declared_by, "/declared_by")
        _timestamp(self.declared_at, "/declared_at")
        if type(self.cohort) is not TriageCohortDeclaration:
            _structural("/cohort", "value must be a TriageCohortDeclaration record")
        if type(self.layer1_source) is not TriageSourceReference:
            _structural("/layer1_source", "value must be a TriageSourceReference record")
        dimensions = _record_tuple(
            self.cohort_dimensions, TriageDimensionState, "/cohort_dimensions"
        )
        if tuple(item.dimension for item in dimensions) != TRIAGE_DIMENSIONS:
            _invariant(
                "/cohort_dimensions",
                "each dimension is reported exactly once, in TRIAGE_DIMENSIONS order",
            )
        object.__setattr__(self, "cohort_dimensions", dimensions)
        candidates = _record_tuple(self.candidates, TriageCandidateProfile, "/candidates")
        if not candidates:
            _invariant("/candidates", "a cohort declares at least one candidate")
        _no_duplicates(
            tuple(item.candidate_id for item in candidates), "/candidates", "candidates"
        )
        object.__setattr__(self, "candidates", candidates)
        if type(self.relation) is not TriageRestrictedRelation:
            _structural("/relation", "value must be a TriageRestrictedRelation record")
        known = {item.candidate_id for item in candidates}
        listed = [member for group in self.relation.ordered_groups for member in group]
        for member in listed:
            if member not in known:
                _reference_error(
                    "/relation/ordered_groups",
                    "a relation member must be one of this cohort's candidates",
                )
        if len(set(listed)) != len(listed):
            _invariant(
                "/relation/ordered_groups", "a candidate appears in at most one group"
            )

    def as_dict(self):
        """A fresh detached structure on every call, in canonical emission order."""
        return {
            "document_type": self.document_type,
            "profile_id": self.profile_id,
            "revision": self.revision,
            "declared_by": self.declared_by,
            "declared_at": self.declared_at,
            "cohort": self.cohort.as_dict(),
            "layer1_source": self.layer1_source.as_dict(),
            "cohort_dimensions": [item.as_dict() for item in self.cohort_dimensions],
            "candidates": [item.as_dict() for item in self.candidates],
            "relation": self.relation.as_dict(),
            "non_claim": self.non_claim,
        }

    def to_json_bytes(self):
        return _canonical_bytes(self.as_dict())

    @classmethod
    def from_dict(cls, mapping):
        _keys(mapping, _TOP_LEVEL_KEYS, "")
        if mapping["document_type"] != TRIAGE_DOCUMENT_TYPE:
            _structural("/document_type", "the document type constant was modified")
        _identifier(mapping["profile_id"], "/profile_id")
        _identifier(mapping["revision"], "/revision")
        _identifier(mapping["declared_by"], "/declared_by")
        _timestamp(mapping["declared_at"], "/declared_at")
        cohort = _build_cohort(mapping["cohort"], "/cohort")
        layer1_source = _build_source(mapping["layer1_source"], "/layer1_source")
        cohort_dimensions = tuple(
            _build_dimension(item, "/cohort_dimensions/{0}".format(position))
            for position, item in enumerate(
                _array(mapping["cohort_dimensions"], "/cohort_dimensions")
            )
        )
        candidates = tuple(
            _build_candidate(item, "/candidates/{0}".format(position))
            for position, item in enumerate(_array(mapping["candidates"], "/candidates"))
        )
        relation = _build_relation(mapping["relation"], "/relation")
        if mapping["non_claim"] != TRIAGE_NON_CLAIM:
            _structural("/non_claim", "the non-claim constant was modified")
        return _at(
            "",
            cls,
            profile_id=mapping["profile_id"],
            revision=mapping["revision"],
            declared_by=mapping["declared_by"],
            declared_at=mapping["declared_at"],
            cohort=cohort,
            layer1_source=layer1_source,
            cohort_dimensions=cohort_dimensions,
            candidates=candidates,
            relation=relation,
        )

    @classmethod
    def from_json_bytes(cls, data):
        if not isinstance(data, (bytes, bytearray)):
            _structural("", "canonical input must be bytes")
        data = bytes(data)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            _structural("", "canonical bytes must decode as UTF-8")
        text = text[1:] if text.startswith("﻿") else text
        try:
            decoded = json.loads(text, object_pairs_hook=_object_pairs)
        except Layer2TriageProfileError:
            raise
        except ValueError:
            _structural("", "canonical bytes must be a single JSON document")
        document = cls.from_dict(decoded)
        if document.to_json_bytes() != data:
            _fail(
                "NON_CANONICAL_BYTES",
                "",
                "input is not the exact canonical serialization of this document",
            )
        return document


def _at(path, factory, **kwargs):
    try:
        return factory(**kwargs)
    except Layer2TriageProfileError as err:
        raise Layer2TriageProfileError(err.code, path + err.field, err.message) from None


def _object_pairs(pairs):
    seen = set()
    for key, _value in pairs:
        if key in seen:
            _structural("", "duplicate JSON object key: {0}".format(key))
        seen.add(key)
    return dict(pairs)


def _keys(value, expected, path):
    if not isinstance(value, dict):
        _structural(path, "value must be a mapping")
    for key in expected:
        if key not in value:
            _structural(path + "/" + key, "required key is absent")
    for key in value:
        if key not in expected:
            _structural(path + "/" + str(key), "unknown key")
    return value


# ================================================================================
# Decoded-document builders
# ================================================================================


def _build_cohort(raw, path):
    _keys(
        raw,
        (
            "target_system_identity",
            "layer1_comparison_basis",
            "ordered_local_position_roles",
            "collective_task_scope_type",
            "triage_convention_version",
            "dimension_directions",
        ),
        path,
    )
    directions = tuple(
        _at(
            "{0}/dimension_directions/{1}".format(path, position),
            TriageDimensionDirection,
            **_keys(item, ("dimension", "direction"), path),
        )
        for position, item in enumerate(
            _array(raw["dimension_directions"], path + "/dimension_directions")
        )
    )
    return _at(
        path,
        TriageCohortDeclaration,
        target_system_identity=raw["target_system_identity"],
        layer1_comparison_basis=raw["layer1_comparison_basis"],
        ordered_local_position_roles=tuple(
            _array(raw["ordered_local_position_roles"], path + "/ordered_local_position_roles")
        ),
        collective_task_scope_type=raw["collective_task_scope_type"],
        triage_convention_version=raw["triage_convention_version"],
        dimension_directions=directions,
    )


def _build_source(raw, path):
    _keys(raw, ("document_type", "document_id", "revision", "position_role"), path)
    return _at(path, TriageSourceReference, **raw)


def _build_comparable(raw, path):
    _keys(
        raw,
        (
            "descriptor_id",
            "observation_id",
            "value",
            "observable_name",
            "definition_reference",
            "unit_class",
            "unit_symbol",
        ),
        path,
    )
    return _at(path, TriageComparableRecord, **raw)


def _build_dimension(raw, path):
    _keys(
        raw,
        ("dimension", "position_role", "state", "direction", "suspension_reason", "record"),
        path,
    )
    record = (
        None
        if raw["record"] is None
        else _build_comparable(_mapping(raw["record"], path + "/record"), path + "/record")
    )
    return _at(
        path,
        TriageDimensionState,
        dimension=raw["dimension"],
        position_role=raw["position_role"],
        state=raw["state"],
        direction=raw["direction"],
        suspension_reason=raw["suspension_reason"],
        record=record,
    )


def _build_candidate(raw, path):
    _keys(
        raw,
        ("candidate_id", "profile_state", "layer1", "gates", "dimensions", "sources"),
        path,
    )
    layer1_raw = _keys(
        _mapping(raw["layer1"], path + "/layer1"),
        (
            "disposition",
            "source_pointer",
            "rank",
            "geometry_tier",
            "evidence_coverage",
            "ineligibility_reason",
        ),
        path + "/layer1",
    )
    gates = tuple(
        _at(
            "{0}/gates/{1}".format(path, position),
            TriageGateDisposition,
            **_keys(item, ("gate", "disposition", "reason"), path),
        )
        for position, item in enumerate(_array(raw["gates"], path + "/gates"))
    )
    dimensions = tuple(
        _build_dimension(item, "{0}/dimensions/{1}".format(path, position))
        for position, item in enumerate(_array(raw["dimensions"], path + "/dimensions"))
    )
    sources = tuple(
        _build_source(item, "{0}/sources/{1}".format(path, position))
        for position, item in enumerate(_array(raw["sources"], path + "/sources"))
    )
    return _at(
        path,
        TriageCandidateProfile,
        candidate_id=raw["candidate_id"],
        profile_state=raw["profile_state"],
        layer1=_at(path + "/layer1", TriageLayer1Outcome, **layer1_raw),
        gates=gates,
        dimensions=dimensions,
        sources=sources,
    )


def _build_relation(raw, path):
    _keys(raw, ("scope", "withheld_reason", "ordered_groups", "basis_dimensions"), path)
    groups = tuple(
        tuple(_array(group, "{0}/ordered_groups/{1}".format(path, position)))
        for position, group in enumerate(_array(raw["ordered_groups"], path + "/ordered_groups"))
    )
    return _at(
        path,
        TriageRestrictedRelation,
        scope=raw["scope"],
        withheld_reason=raw["withheld_reason"],
        ordered_groups=groups,
        basis_dimensions=tuple(_array(raw["basis_dimensions"], path + "/basis_dimensions")),
    )


# ================================================================================
# Layer 1 resolution
# ================================================================================


def _resolve_layer1(priority, candidate_id, field_path):
    """The candidate's own entry in the cohort-level priority report, copied verbatim."""
    found = None
    for group_position, group_raw in enumerate(
        _array(_required(priority, "groups", field_path), field_path + "/groups")
    ):
        group = _mapping(group_raw, "{0}/groups/{1}".format(field_path, group_position))
        for member_position, member_raw in enumerate(
            _array(
                _required(group, "members", "{0}/groups/{1}".format(field_path, group_position)),
                "{0}/groups/{1}/members".format(field_path, group_position),
            )
        ):
            member = _mapping(
                member_raw,
                "{0}/groups/{1}/members/{2}".format(field_path, group_position, member_position),
            )
            if member.get("candidate_id") != candidate_id:
                continue
            if found is not None:
                _invariant(
                    field_path,
                    "the priority report names candidate {0!r} more than once; it is "
                    "refused, never merged".format(candidate_id),
                )
            found = TriageLayer1Outcome(
                disposition="RANKED",
                source_pointer="/groups/{0}/members/{1}".format(
                    group_position, member_position
                ),
                rank=group.get("rank"),
                geometry_tier=group.get("geometry_tier"),
                evidence_coverage=member.get("evidence_coverage"),
                ineligibility_reason=None,
            )
    for position, excluded_raw in enumerate(
        _array(_required(priority, "excluded", field_path), field_path + "/excluded")
    ):
        excluded = _mapping(excluded_raw, "{0}/excluded/{1}".format(field_path, position))
        if excluded.get("candidate_id") != candidate_id:
            continue
        if found is not None:
            _invariant(
                field_path,
                "the priority report names candidate {0!r} more than once; it is "
                "refused, never merged".format(candidate_id),
            )
        found = TriageLayer1Outcome(
            disposition="EXCLUDED",
            source_pointer="/excluded/{0}".format(position),
            rank=None,
            geometry_tier=None,
            evidence_coverage=None,
            ineligibility_reason=excluded.get("ineligibility_reason"),
        )
    if found is None:
        found = TriageLayer1Outcome(
            disposition="ABSENT",
            source_pointer=None,
            rank=None,
            geometry_tier=None,
            evidence_coverage=None,
            ineligibility_reason=None,
        )
    return found


# ================================================================================
# Comparable-record extraction
# ================================================================================


def _descriptors_of(document, family, field_path):
    return [
        (position, _mapping(item, "{0}/descriptors/{1}".format(field_path, position)))
        for position, item in enumerate(
            _array(_required(document, "descriptors", field_path), field_path + "/descriptors")
        )
        if _mapping(item, "{0}/descriptors/{1}".format(field_path, position)).get("family")
        == family
    ]


def _comparable_record(document, family, field_path):
    """(record, suspension reason). Exactly one PROVIDED descriptor with one value."""
    provided = [
        (position, descriptor)
        for position, descriptor in _descriptors_of(document, family, field_path)
        if "PROVIDED" in _array(
            descriptor.get("conditions", []),
            "{0}/descriptors/{1}/conditions".format(field_path, position),
        )
    ]
    if not provided:
        return None, "NO_QUALIFYING_DESCRIPTOR"
    if len(provided) > 1:
        return None, "MULTIPLE_QUALIFYING_DESCRIPTORS"
    position, descriptor = provided[0]
    base = "{0}/descriptors/{1}".format(field_path, position)
    valued = []
    for offset, observation_raw in enumerate(
        _array(_required(descriptor, "observations", base), base + "/observations")
    ):
        observation = _mapping(observation_raw, "{0}/observations/{1}".format(base, offset))
        value = observation.get("value")
        if value is None:
            continue
        value = _mapping(value, "{0}/observations/{1}/value".format(base, offset))
        if value.get("kind") != "NUMERIC" or value.get("number") is None:
            continue
        valued.append((observation, value))
    if not valued:
        return None, "NO_QUALIFYING_OBSERVATION"
    if len(valued) > 1:
        return None, "MULTIPLE_QUALIFYING_OBSERVATIONS"
    observation, value = valued[0]
    definition = _mapping(_required(descriptor, "definition", base), base + "/definition")
    reference = definition.get("definition_reference")
    record = TriageComparableRecord(
        descriptor_id=descriptor.get("descriptor_id"),
        observation_id=observation.get("observation_id"),
        value=value.get("number"),
        observable_name=definition.get("observable_name"),
        definition_reference=reference,
        unit_class=definition.get("unit_class"),
        unit_symbol=definition.get("unit_symbol"),
    )
    _decimal_order_key(record.value, base + "/observations/value/number")
    return record, None


# ================================================================================
# Gates
# ================================================================================


def _document_reference(document, document_type, position_role):
    return TriageSourceReference(
        document_type=document_type,
        document_id=document.get("document_id"),
        revision=document.get("revision"),
        position_role=position_role,
    )


def _collective_scope_complete(collective, field_path):
    """The declared collective scope the 2B contract requires for provided observations."""
    scope = _mapping(_required(collective, "scope", field_path), field_path + "/scope")
    if scope.get("joint_frame") is None:
        return False
    if not _array(scope.get("connections", []), field_path + "/scope/connections"):
        return False
    elements = _array(
        scope.get("assembly_elements", []), field_path + "/scope/assembly_elements"
    )
    kinds = {
        _mapping(item, field_path + "/scope/assembly_elements").get("kind")
        for item in elements
    }
    return "ANCHOR" in kinds and "LINKER" in kinds


def _ordered_roles_agree(cohort, candidate, scope):
    """The declared order, the supplied local positions and 2B's own association order.

    The only carrier is ``layer_2b.scope.local_associations``, read in its declared
    order. No participant identity reference and no other field substitutes for it.
    """
    declared = cohort.ordered_local_position_roles
    supplied = tuple(item.position_role for item in candidate.local_inputs)
    associations = scope.get("local_associations")
    if not isinstance(associations, list):
        return False
    carried = tuple(
        item.get("slot_id") if isinstance(item, dict) else None for item in associations
    )
    return supplied == declared and carried == declared


def _candidate_gates(cohort, candidate, layer1):
    """The six gates, in order. Evaluation stops at the first failure."""
    collective = candidate.collective_document
    anchor = _mapping(
        _required(collective, "candidate_anchor", "/collective_document"),
        "/collective_document/candidate_anchor",
    )
    scope = _mapping(
        _required(collective, "scope", "/collective_document"), "/collective_document/scope"
    )
    failures = []

    # 1. identity and provenance
    reason = None
    if anchor.get("candidate_id") != candidate.candidate_id:
        reason = "CANDIDATE_IDENTITY_MISMATCH"
    else:
        for local in candidate.local_inputs:
            local_anchor = _mapping(
                _required(local.document, "candidate_anchor", "/local_document"),
                "/local_document/candidate_anchor",
            )
            if local_anchor.get("candidate_id") != candidate.candidate_id:
                reason = "CANDIDATE_IDENTITY_MISMATCH"
                break
            local_scope = _mapping(
                _required(local.document, "scope", "/local_document"), "/local_document/scope"
            )
            if local_scope.get("slot_id") != local.position_role:
                reason = "LOCAL_POSITION_SET_MISMATCH"
                break
    failures.append(("IDENTITY_PROVENANCE", reason))

    # 2. Layer 1 boundary
    reason = None
    if layer1.disposition == "ABSENT":
        reason = "LAYER1_ENTRY_ABSENT"
    elif layer1.disposition == "EXCLUDED":
        reason = "LAYER1_EXCLUDED"
    failures.append(("LAYER1_BOUNDARY", reason))

    # 3. cohort comparability
    reason = None
    if cohort.triage_convention_version != TRIAGE_CONVENTION_VERSION:
        reason = "CONVENTION_VERSION_MISMATCH"
    elif anchor.get("scenario_id") != cohort.layer1_comparison_basis:
        reason = "LAYER1_COMPARISON_BASIS_MISMATCH"
    elif scope.get("target_site_declaration") != cohort.target_system_identity:
        reason = "TARGET_SYSTEM_IDENTITY_MISMATCH"
    elif scope.get("assembly_task_declaration") != cohort.collective_task_scope_type:
        reason = "COLLECTIVE_TASK_SCOPE_MISMATCH"
    elif not _ordered_roles_agree(cohort, candidate, scope):
        reason = "ORDERED_LOCAL_ROLES_MISMATCH"
    failures.append(("COHORT_COMPARABILITY", reason))

    # 4. collective scope
    reason = (
        None
        if _collective_scope_complete(collective, "/collective_document")
        else "COLLECTIVE_SCOPE_INCOMPLETE"
    )
    failures.append(("COLLECTIVE_SCOPE", reason))

    # 5. required collective evidence
    records = {}
    reason = "REQUIRED_COLLECTIVE_EVIDENCE_ABSENT"
    for dimension in COLLECTIVE_DIMENSIONS:
        record, suspension = _comparable_record(
            collective, dimension, "/collective_document"
        )
        records[dimension] = (record, suspension)
        if record is not None:
            reason = None
    failures.append(("REQUIRED_COLLECTIVE_EVIDENCE", reason))

    dispositions = []
    failed = False
    for gate, gate_reason in failures:
        if failed:
            dispositions.append(TriageGateDisposition(gate, "NOT_EVALUATED", None))
        elif gate_reason is None:
            dispositions.append(TriageGateDisposition(gate, "PASSED", None))
        else:
            dispositions.append(TriageGateDisposition(gate, "FAILED", gate_reason))
            failed = True
    dispositions.append(TriageGateDisposition("COMMON_ACTIVE_DIMENSIONS", "NOT_EVALUATED", None))
    return tuple(dispositions), records


def _local_records(candidate):
    """One comparable record per ordered local position, in declared position order."""
    found = []
    for local in candidate.local_inputs:
        record, suspension = _comparable_record(
            local.document, LOCAL_TIE_BREAK_DIMENSION, "/local_document"
        )
        found.append((local.position_role, record, suspension))
    return tuple(found)


# ================================================================================
# Ordering
# ================================================================================


def _preferred(direction, left, right):
    """True when ``left`` is at least as preferred as ``right`` under the declaration."""
    if direction == "LOWER_IS_PREFERRED":
        return left <= right
    return left >= right


def _dominates(direction_of, active, left, right):
    """Pareto dominance over the active dimensions only. No scalar is formed."""
    strictly_better = False
    for dimension in active:
        direction = direction_of(dimension)
        if not _preferred(direction, left[dimension], right[dimension]):
            return False
        if left[dimension] != right[dimension]:
            strictly_better = True
    return strictly_better


def _pareto_layers(members, vectors, direction_of, active):
    """Successive non-dominated fronts. Input order never decides membership."""
    remaining = list(members)
    layers = []
    while remaining:
        front = [
            member
            for member in remaining
            if not any(
                _dominates(direction_of, active, vectors[other], vectors[member])
                for other in remaining
                if other != member
            )
        ]
        layers.append(front)
        remaining = [member for member in remaining if member not in front]
    return layers


def _local_split(front, local_vectors, direction, positions):
    """Lexicographic position 1 -> 2 -> 3 split of an exactly tied front."""
    if direction == "NO_DIRECTION_DECLARED":
        return [front]
    for member in front:
        if any(local_vectors[member].get(position) is None for position in positions):
            return [front]
    ordered = sorted(
        front,
        key=lambda member: tuple(
            local_vectors[member][position]
            if direction == "LOWER_IS_PREFERRED"
            else -local_vectors[member][position]
            for position in positions
        ),
    )
    groups = []
    for member in ordered:
        key = tuple(local_vectors[member][position] for position in positions)
        if groups and groups[-1][0] == key:
            groups[-1][1].append(member)
        else:
            groups.append((key, [member]))
    return [group for _key, group in groups]


# ================================================================================
# The public entry point
# ================================================================================


def build_initial_triage_profile(
    *, profile_id, revision, declared_by, declared_at, cohort, priority_document, candidates
):
    """Derive one canonical triage profile for the declared cohort.

    ``priority_document`` is one finished ``cassette_candidate_priority/1`` document,
    as a mapping or its canonical bytes. ``candidates`` are ``TriageCandidateInput``
    records. Nothing is opened, recomputed, aggregated or ranked outside the declared
    directions, and no Layer 1 outcome is reinterpreted.
    """
    if type(cohort) is not TriageCohortDeclaration:
        _structural("/cohort", "value must be a TriageCohortDeclaration record")
    inputs = _record_tuple(candidates, TriageCandidateInput, "/candidates")
    if not inputs:
        _invariant("/candidates", "a cohort declares at least one candidate")
    _no_duplicates(
        tuple(item.candidate_id for item in inputs), "/candidates", "candidates"
    )
    priority = _source_document(
        priority_document, SOURCE_PRIORITY_DOCUMENT_TYPE, "/priority_document"
    )

    direction_of = cohort.direction_of
    positions = cohort.ordered_local_position_roles

    gates, collective_records, local_records, layer1 = {}, {}, {}, {}
    for candidate in inputs:
        identifier = candidate.candidate_id
        layer1[identifier] = _resolve_layer1(priority, identifier, "/priority_document")
        gates[identifier], collective_records[identifier] = _candidate_gates(
            cohort, candidate, layer1[identifier]
        )
        local_records[identifier] = _local_records(candidate)

    gate_passed = [
        candidate.candidate_id
        for candidate in inputs
        if all(item.disposition == "PASSED" for item in gates[candidate.candidate_id][:5])
    ]

    # Cohort-common dimension determination over the gate-passed subset only.
    cohort_dimensions = []
    active = []
    for dimension in COLLECTIVE_DIMENSIONS:
        direction = direction_of(dimension)
        reason = None
        if direction == "NO_DIRECTION_DECLARED":
            reason = "NO_DIRECTION_DECLARED"
        elif not gate_passed:
            reason = "CANDIDATE_NOT_GATE_PASSED"
        else:
            keys = []
            for identifier in gate_passed:
                record, suspension = collective_records[identifier][dimension]
                if record is None:
                    reason = suspension
                    break
                keys.append(record.comparability_key())
            if reason is None:
                first = keys[0]
                for key in keys[1:]:
                    for offset, name in enumerate(
                        (
                            "OBSERVABLE_NAME_MISMATCH",
                            "DEFINITION_REFERENCE_MISMATCH",
                            "UNIT_CLASS_MISMATCH",
                            "UNIT_SYMBOL_MISMATCH",
                        )
                    ):
                        if key[offset] != first[offset]:
                            reason = name
                            break
                    if reason is not None:
                        break
        if reason is None:
            active.append(dimension)
        cohort_dimensions.append(
            TriageDimensionState(
                dimension=dimension,
                position_role=None,
                state="SUSPENDED" if reason else "ACTIVE",
                direction=direction,
                suspension_reason=reason,
                record=None
                if reason
                else collective_records[gate_passed[0]][dimension][0],
            )
        )

    local_direction = direction_of(LOCAL_TIE_BREAK_DIMENSION)
    local_reason = None
    if local_direction == "NO_DIRECTION_DECLARED":
        local_reason = "NO_DIRECTION_DECLARED"
    elif not gate_passed:
        local_reason = "CANDIDATE_NOT_GATE_PASSED"
    else:
        keys = []
        for identifier in gate_passed:
            for _role, record, suspension in local_records[identifier]:
                if record is None:
                    local_reason = suspension
                    break
                keys.append(record.comparability_key())
            if local_reason is not None:
                break
        if local_reason is None and len(set(keys)) > 1:
            first = keys[0]
            for key in keys[1:]:
                for offset, name in enumerate(
                    (
                        "OBSERVABLE_NAME_MISMATCH",
                        "DEFINITION_REFERENCE_MISMATCH",
                        "UNIT_CLASS_MISMATCH",
                        "UNIT_SYMBOL_MISMATCH",
                    )
                ):
                    if key[offset] != first[offset]:
                        local_reason = name
                        break
                if local_reason is not None:
                    break
    cohort_dimensions.append(
        TriageDimensionState(
            dimension=LOCAL_TIE_BREAK_DIMENSION,
            position_role=None,
            state="SUSPENDED" if local_reason else "ACTIVE",
            direction=local_direction,
            suspension_reason=local_reason,
            record=None
            if local_reason
            else local_records[gate_passed[0]][0][1],
        )
    )

    # Gate 6 closes over the cohort-common determination.
    for candidate in inputs:
        identifier = candidate.candidate_id
        dispositions = list(gates[identifier])
        if identifier in gate_passed:
            dispositions[5] = (
                TriageGateDisposition("COMMON_ACTIVE_DIMENSIONS", "PASSED", None)
                if active
                else TriageGateDisposition(
                    "COMMON_ACTIVE_DIMENSIONS", "FAILED", "NO_COMMON_ACTIVE_DIMENSION"
                )
            )
        gates[identifier] = tuple(dispositions)
    comparable = [
        identifier
        for identifier in gate_passed
        if gates[identifier][5].disposition == "PASSED"
    ]

    # Hierarchical order: Layer 1 tier first, then the collective Pareto vector, then
    # the ordered local positions when the collective vector is exactly tied.
    ordered_groups = []
    if comparable:
        vectors = {
            identifier: {
                dimension: _decimal_order_key(
                    collective_records[identifier][dimension][0].value, "/collective_document"
                )
                for dimension in active
            }
            for identifier in comparable
        }
        local_vectors = {
            identifier: {
                role: None
                if record is None
                else _decimal_order_key(record.value, "/local_document")
                for role, record, _reason in local_records[identifier]
            }
            for identifier in comparable
        }
        for tier in TIER_ORDER:
            members = [
                identifier
                for identifier in comparable
                if layer1[identifier].geometry_tier == tier
            ]
            if not members:
                continue
            for front in _pareto_layers(members, vectors, direction_of, active):
                distinct = {
                    tuple(vectors[member][dimension] for dimension in active)
                    for member in front
                }
                if len(distinct) == 1 and local_reason is None:
                    ordered_groups.extend(
                        _local_split(front, local_vectors, local_direction, positions)
                    )
                else:
                    ordered_groups.append(list(front))

    retained_not_passed = [
        candidate.candidate_id
        for candidate in inputs
        if layer1[candidate.candidate_id].disposition == "RANKED"
        and candidate.candidate_id not in comparable
    ]
    if not comparable:
        scope = "GATE_PASSED_SUBSET_ONLY"
        withheld = "NO_GATE_PASSED_CANDIDATE"
    elif retained_not_passed:
        scope = "GATE_PASSED_SUBSET_ONLY"
        withheld = "RETAINED_MEMBER_NOT_GATE_PASSED"
    else:
        scope = "COHORT_WIDE"
        withheld = None
    relation = TriageRestrictedRelation(
        scope=scope,
        withheld_reason=withheld,
        ordered_groups=tuple(tuple(sorted(group)) for group in ordered_groups),
        basis_dimensions=tuple(active),
    )

    profiles = []
    leading = set(ordered_groups[0]) if ordered_groups else set()
    for candidate in inputs:
        identifier = candidate.candidate_id
        dispositions = gates[identifier]
        failed = next(
            (item for item in dispositions if item.disposition == "FAILED"), None
        )
        if failed is None:
            if identifier in leading:
                state = (
                    "EXPERIMENTAL_PRIORITY"
                    if len(leading) == 1
                    else "EXPERIMENTAL_PRIORITY_TIE"
                )
            else:
                state = "NOT_PRIORITIZED_BY_PROFILE"
        elif failed.reason == "LAYER1_EXCLUDED":
            state = "NOT_PRIORITIZED_BY_PROFILE"
        elif failed.reason in (
            "CANDIDATE_IDENTITY_MISMATCH",
            "LOCAL_POSITION_SET_MISMATCH",
            "LAYER1_ENTRY_ABSENT",
            "CONVENTION_VERSION_MISMATCH",
            "LAYER1_COMPARISON_BASIS_MISMATCH",
            "TARGET_SYSTEM_IDENTITY_MISMATCH",
            "COLLECTIVE_TASK_SCOPE_MISMATCH",
            "ORDERED_LOCAL_ROLES_MISMATCH",
            "NO_COMMON_ACTIVE_DIMENSION",
        ):
            state = "COMPARISON_UNSUPPORTED"
        else:
            state = "REVIEW_REQUIRED"

        dimensions = []
        for dimension in COLLECTIVE_DIMENSIONS:
            record, suspension = collective_records[identifier][dimension]
            reason = suspension
            if reason is None and dimension not in active:
                reason = next(
                    item.suspension_reason
                    for item in cohort_dimensions
                    if item.dimension == dimension
                )
            if reason is None and identifier not in comparable:
                reason = "CANDIDATE_NOT_GATE_PASSED"
            if reason is None and layer1[identifier].disposition != "RANKED":
                reason = "LAYER1_STATUS_NOT_RETAINED"
            dimensions.append(
                TriageDimensionState(
                    dimension=dimension,
                    position_role=None,
                    state="SUSPENDED" if reason else "ACTIVE",
                    direction=direction_of(dimension),
                    suspension_reason=reason,
                    record=record,
                )
            )
        for role, record, suspension in local_records[identifier]:
            reason = suspension or local_reason
            if reason is None and identifier not in comparable:
                reason = "CANDIDATE_NOT_GATE_PASSED"
            dimensions.append(
                TriageDimensionState(
                    dimension=LOCAL_TIE_BREAK_DIMENSION,
                    position_role=role,
                    state="SUSPENDED" if reason else "ACTIVE",
                    direction=local_direction,
                    suspension_reason=reason,
                    record=record,
                )
            )

        sources = [
            _document_reference(
                candidate.collective_document, SOURCE_COLLECTIVE_DOCUMENT_TYPE, None
            )
        ]
        for local in candidate.local_inputs:
            sources.append(
                _document_reference(
                    local.document, SOURCE_LOCAL_DOCUMENT_TYPE, local.position_role
                )
            )
        profiles.append(
            TriageCandidateProfile(
                candidate_id=identifier,
                profile_state=state,
                layer1=layer1[identifier],
                gates=dispositions,
                dimensions=tuple(dimensions),
                sources=tuple(sources),
            )
        )

    return Layer2InitialTriageProfile(
        profile_id=profile_id,
        revision=revision,
        declared_by=declared_by,
        declared_at=declared_at,
        cohort=cohort,
        layer1_source=TriageSourceReference(
            document_type=SOURCE_PRIORITY_DOCUMENT_TYPE,
            document_id=None,
            revision=None,
            position_role=None,
        ),
        cohort_dimensions=tuple(cohort_dimensions),
        candidates=tuple(profiles),
        relation=relation,
    )


def render_profile_lines(profile):
    """Presentation only: the emitted profile, restated line by line."""
    lines = [
        TRIAGE_NON_CLAIM,
        "",
        "document_type: " + profile.document_type,
        "relation scope: " + profile.relation.scope,
    ]
    if profile.relation.withheld_reason is not None:
        lines.append("full-cohort issuance withheld: " + profile.relation.withheld_reason)
    lines.append(
        "basis dimensions: "
        + (", ".join(profile.relation.basis_dimensions) or "none active")
    )
    for position, group in enumerate(profile.relation.ordered_groups):
        lines.append("  position {0}: {1}".format(position + 1, ", ".join(group)))
    lines.append("")
    for candidate in profile.candidates:
        lines.append(
            "{0}  {1}  layer 1 {2}".format(
                candidate.candidate_id,
                candidate.profile_state,
                candidate.layer1.disposition,
            )
        )
        for gate in candidate.gates:
            if gate.disposition != "PASSED":
                lines.append(
                    "    gate {0}: {1}{2}".format(
                        gate.gate,
                        gate.disposition,
                        "" if gate.reason is None else " (" + gate.reason + ")",
                    )
                )
    return lines
