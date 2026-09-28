"""Layer 2B descriptor input document (contract ``layer_2b_descriptor_input/1``).

Standard library only. This module holds the shared primitive and immutable record
vocabulary that ``layer_2b_descriptor_input/1`` requires, plus the public document
record. It opens no file, resolves no locator, parses no coordinate or trajectory,
reads no provider output, computes no hash, reads no clock or environment, starts no
subprocess and reaches no network.

Every field name, vocabulary token, family label, condition, reason and non-claim text
is opaque contract data. This module neither assigns nor interprets meaning for any of
them. It checks shape, spelling, cardinality, internal reference resolution and the
collective invariants, and it derives exactly three things: the two document constants
and, per descriptor, ``conditions`` and ``reasons``.

DELIBERATE DUPLICATION

  The shared primitive and record vocabulary is copied verbatim from the Layer 2A
  module rather than imported. The two document types are separate immutable
  contracts, and neither depends on the other at import time.

COLLECTIVE SCOPE ONLY

  Only ``L2_COLLECTIVE_FAMILIES`` exists here. The local families and the Layer 2A
  local-scope record are out of scope and are neither defined nor accepted.
  ``L2LocalAssociation`` names a Layer 2A document; it never loads, reconstructs or
  validates its external contents, and it never creates a collective frame.

WHAT IS NEVER DONE

  No score, rank, triage, comparison, feature calculation, uncertainty estimate or
  eligibility decision. No external reference is resolved or loaded, and there is no
  cross-document loader. Absent, unavailable, ambiguous and contradictory
  declarations are preserved exactly as supplied.

ERRORS

  ``Layer2DescriptorInputError`` exposes exactly ``.code`` (one ``L2_ERROR_CODES``
  token), ``.field`` (JSON Pointer, root is ``""``), ``.index`` (outermost array index
  involved, or None) and ``.message``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json

# ================================================================================
# Closed vocabularies
# ================================================================================

L2_COLLECTIVE_FAMILIES = (
    "COLLECTIVE_INTERFERENCE",
    "COLLECTIVE_DEFORMATION_RESTRAINT_BURDEN",
    "COLLECTIVE_ANCHOR_LINKER_CONFIGURATION",
)
L2_SLOT_IDS = ("slot_1", "slot_2", "slot_3")
L2_PARTICIPANT_ROLES = ("BINDER", "RECEPTOR", "LIGAND", "CONTEXT")
L2_ELEMENT_KINDS = ("ANCHOR", "LINKER")
L2_INFORMATION_STATES = ("SUPPLIED", "ABSENT", "AMBIGUOUS")
L2_PROFILE_STATES = ("SUPPLIED", "UNAVAILABLE")
L2_CONDITIONS = ("PROVIDED", "UNAVAILABLE", "AMBIGUOUS", "CONTRADICTORY")
L2_REASON_CODES = (
    "EVIDENCE_NOT_SUPPLIED",
    "DECLARATION_MISSING",
    "DECLARATION_AMBIGUOUS",
    "OBSERVATIONS_CONFLICT",
)
L2_UNCERTAINTY_KINDS = (
    "POSE_CONFORMER",
    "SAMPLING",
    "METHOD",
    "CONDITIONS",
    "CONTEXT",
    "REFERENCE_STATE",
)
L2_UNCERTAINTY_STATES = ("DECLARED", "UNKNOWN", "NOT_APPLICABLE")
L2_VALUE_KINDS = ("NUMERIC", "CATEGORICAL")
L2_UNIT_CLASSES = (
    "DIMENSIONLESS",
    "LENGTH",
    "ANGLE",
    "AREA",
    "ENERGY",
    "ENERGY_PER_MOLE",
    "METHOD_DEFINED",
    "OTHER",
)
L2_ANCHOR_KINDS = ("CONTENT_HASH", "IMMUTABLE_SNAPSHOT")
L2_FRAME_KINDS = ("CALLER_DECLARED_ARTIFACT_MODEL_FRAME",)
L2_REFERENCE_STATE_KINDS = (
    "ISOLATED_FROZEN",
    "ISOLATED_RELAXED",
    "ASSEMBLY_REFERENCE",
    "ANCHOR_LINKER_REFERENCE",
    "RESTRAINT_REFERENCE",
    "NOT_APPLICABLE",
    "UNAVAILABLE",
)
L2_CONTEXT_TREATMENTS = (
    "REPRESENTED",
    "FIXED",
    "MOBILE",
    "RESTRAINED",
    "OMITTED",
    "UNKNOWN",
    "NOT_APPLICABLE",
)
L2_ERROR_CODES = (
    "STRUCTURAL_INVALID",
    "REFERENCE_INVALID",
    "INVARIANT_INVALID",
    "NON_CANONICAL_BYTES",
)

# ================================================================================
# Document constants
# ================================================================================

LAYER_2B_DOCUMENT_TYPE = "layer_2b_descriptor_input/1"
LAYER_2B_FAMILIES = L2_COLLECTIVE_FAMILIES
LAYER_2B_NON_CLAIM = (
    "This document preserves supplied computational descriptors for a "
    "caller-declared three-binder, anchor/linker and shared-target scope, with "
    "their provenance, assumptions and uncertainty. The declared joint scope does "
    "not establish simultaneous engagement, binding, affinity, avidity, "
    "thermodynamic truth, compatibility, biological activity, safety or "
    "experimental success. Missing evidence is not negative evidence. It assigns "
    "no priority and changes no deterministic outcome."
)

#: The document type an L2LocalDocumentReference names. It is never loaded.
LOCAL_DOCUMENT_TYPE = "layer_2a_descriptor_input/1"

#: Families whose values are numeric only.
DIRECTIONAL_FAMILIES = (
    "COLLECTIVE_INTERFERENCE",
    "COLLECTIVE_DEFORMATION_RESTRAINT_BURDEN",
)

#: Reference-state kinds the collective deformation/restraint family accepts.
COLLECTIVE_DEFORMATION_REFERENCE_STATE_KINDS = (
    "ASSEMBLY_REFERENCE",
    "ANCHOR_LINKER_REFERENCE",
    "RESTRAINT_REFERENCE",
    "UNAVAILABLE",
)

#: Reference-state kinds that do not supply an applicable reference state.
_INAPPLICABLE_REFERENCE_STATES = ("NOT_APPLICABLE", "UNAVAILABLE")

#: The ordered fields an admission reference may list as absent.
_ADMISSION_ABSENT_KEYS = ("state_result_id", "ineligibility_reason", "certificate_present")

#: The six nullable identity/reference fields that govern a local association reason.
_LOCAL_ASSOCIATION_OPTIONAL = (
    "binder_participant_id",
    "target_participant_id",
    "candidate_id",
    "scenario_id",
    "pose_association_reference",
    "local_document_reference",
)

_CONTENT_HASH_ALGORITHM = "sha256"
_CONTENT_HASH_DIGEST_LENGTH = 64
_HEX_DIGITS = frozenset("0123456789abcdef")


# ================================================================================
# The single exception type
# ================================================================================


def _outermost_index(pointer):
    """The first array position in a JSON Pointer, or None when none applies."""
    if not pointer:
        return None
    for token in pointer.split("/")[1:]:
        if token and all("0" <= character <= "9" for character in token):
            return int(token)
    return None


class Layer2DescriptorInputError(ValueError):
    """The only error this module raises."""

    __slots__ = ("code", "field", "index", "message")

    def __init__(self, code, field, message):
        if code not in L2_ERROR_CODES:
            raise AssertionError("error code outside the closed vocabulary")
        self.code = code
        self.field = field
        self.index = _outermost_index(field)
        self.message = message
        super().__init__(
            "{0} at {1}: {2}".format(code, field if field else "<root>", message)
        )


def _fail(code, field, message):
    raise Layer2DescriptorInputError(code, field, message)


def _structural(field_path, message):
    _fail("STRUCTURAL_INVALID", field_path, message)


def _reference_error(field_path, message):
    _fail("REFERENCE_INVALID", field_path, message)


def _invariant(field_path, message):
    _fail("INVARIANT_INVALID", field_path, message)


def _at(path, factory, **kwargs):
    """Build a record, re-raising its relative pointer under ``path``."""
    try:
        return factory(**kwargs)
    except Layer2DescriptorInputError as err:
        raise Layer2DescriptorInputError(
            err.code, path + err.field, err.message
        ) from None


# ================================================================================
# Primitives
# ================================================================================


def _is_control(character):
    point = ord(character)
    return point < 0x20 or 0x7F <= point <= 0x9F


def _digits(text):
    if not text:
        return False
    for character in text:
        if character < "0" or character > "9":
            return False
    return True


def _identifier(value, field_path):
    if not isinstance(value, str):
        _structural(field_path, "identifier must be a string")
    if value == "":
        _structural(field_path, "identifier must not be empty")
    for character in value:
        if _is_control(character):
            _structural(field_path, "identifier must not contain control characters")
    if value != value.strip():
        _structural(
            field_path, "identifier must not have leading or trailing whitespace"
        )
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


def _boolean(value, field_path):
    if value is not True and value is not False:
        _structural(field_path, "boolean must be true or false")
    return value


def _opt_boolean(value, field_path):
    return None if value is None else _boolean(value, field_path)


def _pointer(value, field_path):
    """A JSON Pointer, including the empty root pointer."""
    if not isinstance(value, str):
        _structural(field_path, "pointer must be a string")
    for character in value:
        if _is_control(character):
            _structural(field_path, "pointer must not contain control characters")
    if value != "" and not value.startswith("/"):
        _structural(field_path, "a non-empty pointer must begin with '/'")
    position = 0
    while position < len(value):
        if value[position] != "~":
            position += 1
            continue
        if position + 1 >= len(value) or value[position + 1] not in ("0", "1"):
            _structural(field_path, "'~' must occur only as the escape ~0 or ~1")
        position += 2
    return value


_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _timestamp(value, field_path):
    """Exactly ``YYYY-MM-DDTHH:mm:ssZ``, calendar-validated, caller-supplied."""
    if not isinstance(value, str):
        _structural(field_path, "timestamp must be a string")
    if len(value) != 20:
        _structural(field_path, "timestamp must be exactly YYYY-MM-DDTHH:mm:ssZ")
    if value[4] != "-" or value[7] != "-" or value[10] != "T":
        _structural(field_path, "timestamp must be exactly YYYY-MM-DDTHH:mm:ssZ")
    if value[13] != ":" or value[16] != ":" or value[19] != "Z":
        _structural(field_path, "timestamp must be exactly YYYY-MM-DDTHH:mm:ssZ")
    parts = (
        value[0:4],
        value[5:7],
        value[8:10],
        value[11:13],
        value[14:16],
        value[17:19],
    )
    for part in parts:
        if not _digits(part):
            _structural(field_path, "timestamp must be exactly YYYY-MM-DDTHH:mm:ssZ")
    year, month, day, hour, minute, second = (int(part) for part in parts)
    if month < 1 or month > 12:
        _structural(field_path, "timestamp month is not a calendar month")
    limit = _DAYS_IN_MONTH[month - 1]
    if month == 2 and year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        limit = 29
    if day < 1 or day > limit:
        _structural(field_path, "timestamp day is not a calendar day of that month")
    if hour > 23 or minute > 59 or second > 59:
        _structural(field_path, "timestamp time field is out of range")
    return value


def _decimal(value, field_path):
    """An exact finite decimal string. No coercion, no normalization."""
    if not isinstance(value, str):
        _structural(field_path, "decimal must be a string")
    body = value
    negative = False
    if body.startswith("-"):
        negative = True
        body = body[1:]
    if "." in body:
        integer, _, fraction = body.partition(".")
        if fraction == "":
            _structural(field_path, "decimal fractional part must be non-empty")
        if not _digits(fraction):
            _structural(field_path, "decimal fractional part must be digits")
        if fraction.endswith("0"):
            _structural(field_path, "decimal fractional part must not end in zero")
    else:
        integer, fraction = body, ""
    if not _digits(integer):
        _structural(field_path, "decimal integer part must be digits")
    if len(integer) > 1 and integer[0] == "0":
        _structural(field_path, "decimal integer part must not have leading zeros")
    if negative and integer.strip("0") == "" and fraction.strip("0") == "":
        _structural(field_path, "negative zero is not permitted")
    return value


def _opt_decimal(value, field_path):
    return None if value is None else _decimal(value, field_path)


def _sequence(value, field_path):
    if isinstance(value, (str, bytes, bytearray, dict)):
        _structural(field_path, "value must be an array")
    if not isinstance(value, (list, tuple)):
        _structural(field_path, "value must be an array")
    return tuple(value)


def _record(value, expected, field_path):
    if not isinstance(value, expected):
        _structural(field_path, "value must be a {0} record".format(expected.__name__))
    return value


def _opt_record(value, expected, field_path):
    return None if value is None else _record(value, expected, field_path)


def _record_tuple(value, expected, field_path):
    items = _sequence(value, field_path)
    for position, item in enumerate(items):
        _record(item, expected, "{0}/{1}".format(field_path, position))
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
    return items


def _identifier_tuple(value, field_path):
    items = _sequence(value, field_path)
    for position, item in enumerate(items):
        _identifier(item, "{0}/{1}".format(field_path, position))
    return _no_duplicates(items, field_path, "identifier array")


def _pointer_tuple(value, field_path):
    items = _sequence(value, field_path)
    for position, item in enumerate(items):
        _pointer(item, "{0}/{1}".format(field_path, position))
    return _no_duplicates(items, field_path, "pointer array")


def _source_tuple(value, field_path):
    items = _record_tuple(value, L2SourceRecord, field_path)
    return _no_duplicates(items, field_path, "source-reference array")


# ================================================================================
# Shared immutable reference and scope records
# ================================================================================


@dataclass(frozen=True)
class L2ImmutableReference:
    namespace: str
    identifier: str
    revision: str | None
    snapshot_reference: str | None

    def __post_init__(self):
        _identifier(self.namespace, "/namespace")
        _identifier(self.identifier, "/identifier")
        _opt_identifier(self.revision, "/revision")
        _opt_identifier(self.snapshot_reference, "/snapshot_reference")
        if self.revision is None and self.snapshot_reference is None:
            _invariant(
                "/revision", "at least one of revision and snapshot_reference is required"
            )

    def as_dict(self):
        return {
            "namespace": self.namespace,
            "identifier": self.identifier,
            "revision": self.revision,
            "snapshot_reference": self.snapshot_reference,
        }


@dataclass(frozen=True)
class L2SourceRecord:
    reference: L2ImmutableReference
    locator: str | None

    def __post_init__(self):
        _record(self.reference, L2ImmutableReference, "/reference")
        _opt_text(self.locator, "/locator")

    def as_dict(self):
        return {"reference": self.reference.as_dict(), "locator": self.locator}


@dataclass(frozen=True)
class L2ArtifactAnchor:
    kind: str
    algorithm: str | None
    digest: str | None
    snapshot_reference: L2ImmutableReference | None

    def __post_init__(self):
        _token(self.kind, L2_ANCHOR_KINDS, "/kind")
        if self.kind == "CONTENT_HASH":
            if self.snapshot_reference is not None:
                _invariant(
                    "/snapshot_reference",
                    "CONTENT_HASH requires a null snapshot_reference",
                )
            if self.algorithm != _CONTENT_HASH_ALGORITHM:
                _structural("/algorithm", "CONTENT_HASH accepts only the sha256 spelling")
            if not isinstance(self.digest, str):
                _structural("/digest", "CONTENT_HASH requires a digest string")
            if len(self.digest) != _CONTENT_HASH_DIGEST_LENGTH:
                _structural("/digest", "digest must be exactly 64 characters")
            for character in self.digest:
                if character not in _HEX_DIGITS:
                    _structural(
                        "/digest", "digest must be lowercase hexadecimal; no normalization"
                    )
        else:
            if self.algorithm is not None:
                _invariant("/algorithm", "IMMUTABLE_SNAPSHOT requires a null algorithm")
            if self.digest is not None:
                _invariant("/digest", "IMMUTABLE_SNAPSHOT requires a null digest")
            if self.snapshot_reference is None:
                _invariant(
                    "/snapshot_reference",
                    "IMMUTABLE_SNAPSHOT requires a snapshot_reference",
                )
            _record(self.snapshot_reference, L2ImmutableReference, "/snapshot_reference")

    def as_dict(self):
        return {
            "kind": self.kind,
            "algorithm": self.algorithm,
            "digest": self.digest,
            "snapshot_reference": (
                None
                if self.snapshot_reference is None
                else self.snapshot_reference.as_dict()
            ),
        }


@dataclass(frozen=True)
class L2AssociationReference:
    association_id: str
    revision: str
    reference: L2ImmutableReference

    def __post_init__(self):
        _identifier(self.association_id, "/association_id")
        _identifier(self.revision, "/revision")
        _record(self.reference, L2ImmutableReference, "/reference")

    def as_dict(self):
        return {
            "association_id": self.association_id,
            "revision": self.revision,
            "reference": self.reference.as_dict(),
        }


@dataclass(frozen=True)
class L2AdmissionReference:
    candidate_id: str
    slot_binding_hash: str
    state_result_id: str | None
    ineligibility_reason: str | None
    certificate_present: bool | None
    absent_keys: tuple

    def __post_init__(self):
        _identifier(self.candidate_id, "/candidate_id")
        _identifier(self.slot_binding_hash, "/slot_binding_hash")
        _opt_identifier(self.state_result_id, "/state_result_id")
        _opt_identifier(self.ineligibility_reason, "/ineligibility_reason")
        _opt_boolean(self.certificate_present, "/certificate_present")
        keys = _identifier_tuple(self.absent_keys, "/absent_keys")
        object.__setattr__(self, "absent_keys", keys)
        previous = -1
        for position, name in enumerate(keys):
            if name not in _ADMISSION_ABSENT_KEYS:
                _invariant(
                    "/absent_keys/{0}".format(position),
                    "absent_keys may name only the three optional fields",
                )
            current = _ADMISSION_ABSENT_KEYS.index(name)
            if current <= previous:
                _invariant(
                    "/absent_keys/{0}".format(position),
                    "absent_keys must follow the declared field order",
                )
            previous = current
            if getattr(self, name) is not None:
                _invariant(
                    "/{0}".format(name), "a field listed in absent_keys must be null"
                )

    def as_dict(self):
        return {
            "candidate_id": self.candidate_id,
            "slot_binding_hash": self.slot_binding_hash,
            "state_result_id": self.state_result_id,
            "ineligibility_reason": self.ineligibility_reason,
            "certificate_present": self.certificate_present,
            "absent_keys": list(self.absent_keys),
        }


@dataclass(frozen=True)
class L2CandidateAnchor:
    candidate_id: str | None
    scenario_id: str | None
    evaluation_run_ref: str | None
    batch_report_reference: L2SourceRecord | None
    priority_report_reference: L2SourceRecord | None
    scenario_comparison_reference: L2SourceRecord | None
    admission_reference: L2AdmissionReference | None

    def __post_init__(self):
        _opt_identifier(self.candidate_id, "/candidate_id")
        _opt_identifier(self.scenario_id, "/scenario_id")
        _opt_identifier(self.evaluation_run_ref, "/evaluation_run_ref")
        _opt_record(self.batch_report_reference, L2SourceRecord, "/batch_report_reference")
        _opt_record(
            self.priority_report_reference, L2SourceRecord, "/priority_report_reference"
        )
        _opt_record(
            self.scenario_comparison_reference,
            L2SourceRecord,
            "/scenario_comparison_reference",
        )
        _opt_record(
            self.admission_reference, L2AdmissionReference, "/admission_reference"
        )

    def as_dict(self):
        return {
            "candidate_id": self.candidate_id,
            "scenario_id": self.scenario_id,
            "evaluation_run_ref": self.evaluation_run_ref,
            "batch_report_reference": (
                None
                if self.batch_report_reference is None
                else self.batch_report_reference.as_dict()
            ),
            "priority_report_reference": (
                None
                if self.priority_report_reference is None
                else self.priority_report_reference.as_dict()
            ),
            "scenario_comparison_reference": (
                None
                if self.scenario_comparison_reference is None
                else self.scenario_comparison_reference.as_dict()
            ),
            "admission_reference": (
                None
                if self.admission_reference is None
                else self.admission_reference.as_dict()
            ),
        }


@dataclass(frozen=True)
class L2PoseRecord:
    pose_id: str
    artifact_anchor: L2ArtifactAnchor
    locator: str | None
    model_id: str | None
    conformer_id: str | None
    frame_id: str | None
    association_reference: L2AssociationReference | None
    source_reference: L2SourceRecord | None
    run_reference: L2ImmutableReference | None
    method_reference: L2ImmutableReference | None

    def __post_init__(self):
        _identifier(self.pose_id, "/pose_id")
        _record(self.artifact_anchor, L2ArtifactAnchor, "/artifact_anchor")
        _opt_text(self.locator, "/locator")
        _opt_identifier(self.model_id, "/model_id")
        _opt_identifier(self.conformer_id, "/conformer_id")
        _opt_identifier(self.frame_id, "/frame_id")
        _opt_record(
            self.association_reference, L2AssociationReference, "/association_reference"
        )
        _opt_record(self.source_reference, L2SourceRecord, "/source_reference")
        _opt_record(self.run_reference, L2ImmutableReference, "/run_reference")
        _opt_record(self.method_reference, L2ImmutableReference, "/method_reference")

    def as_dict(self):
        return {
            "pose_id": self.pose_id,
            "artifact_anchor": self.artifact_anchor.as_dict(),
            "locator": self.locator,
            "model_id": self.model_id,
            "conformer_id": self.conformer_id,
            "frame_id": self.frame_id,
            "association_reference": (
                None
                if self.association_reference is None
                else self.association_reference.as_dict()
            ),
            "source_reference": (
                None if self.source_reference is None else self.source_reference.as_dict()
            ),
            "run_reference": (
                None if self.run_reference is None else self.run_reference.as_dict()
            ),
            "method_reference": (
                None if self.method_reference is None else self.method_reference.as_dict()
            ),
        }


@dataclass(frozen=True)
class L2ChainInstance:
    identifier_namespace: str | None
    chain_id: str | None
    instance_id: str | None
    residue_addressing_reference: L2SourceRecord | None
    selection_declaration: str | None

    def __post_init__(self):
        _opt_identifier(self.identifier_namespace, "/identifier_namespace")
        _opt_identifier(self.chain_id, "/chain_id")
        _opt_identifier(self.instance_id, "/instance_id")
        _opt_record(
            self.residue_addressing_reference,
            L2SourceRecord,
            "/residue_addressing_reference",
        )
        _opt_text(self.selection_declaration, "/selection_declaration")

    def as_dict(self):
        return {
            "identifier_namespace": self.identifier_namespace,
            "chain_id": self.chain_id,
            "instance_id": self.instance_id,
            "residue_addressing_reference": (
                None
                if self.residue_addressing_reference is None
                else self.residue_addressing_reference.as_dict()
            ),
            "selection_declaration": self.selection_declaration,
        }


@dataclass(frozen=True)
class L2MappingAlternative:
    pose_id: str | None
    chain_instances: tuple
    source_reference: L2SourceRecord | None

    def __post_init__(self):
        _opt_identifier(self.pose_id, "/pose_id")
        instances = _record_tuple(self.chain_instances, L2ChainInstance, "/chain_instances")
        object.__setattr__(self, "chain_instances", instances)
        _opt_record(self.source_reference, L2SourceRecord, "/source_reference")

    def as_dict(self):
        return {
            "pose_id": self.pose_id,
            "chain_instances": [item.as_dict() for item in self.chain_instances],
            "source_reference": (
                None if self.source_reference is None else self.source_reference.as_dict()
            ),
        }


def _check_mapping_cardinality(state, alternatives, field_path):
    _no_duplicates(alternatives, field_path, "mapping alternatives")
    if state == "SUPPLIED":
        if len(alternatives) != 1:
            _invariant(field_path, "SUPPLIED requires exactly one alternative")
    elif state == "ABSENT":
        if len(alternatives) != 0:
            _invariant(field_path, "ABSENT requires no alternatives")
    else:
        if len(alternatives) < 2:
            _invariant(
                field_path, "AMBIGUOUS requires at least two distinct alternatives"
            )


@dataclass(frozen=True)
class L2MolecularParticipant:
    participant_id: str
    role: str
    identity_reference: L2ImmutableReference | None
    construct_id: str | None
    construct_version: str | None
    mapping_state: str
    mapping_alternatives: tuple

    def __post_init__(self):
        _identifier(self.participant_id, "/participant_id")
        _token(self.role, L2_PARTICIPANT_ROLES, "/role")
        _opt_record(self.identity_reference, L2ImmutableReference, "/identity_reference")
        _opt_identifier(self.construct_id, "/construct_id")
        _opt_identifier(self.construct_version, "/construct_version")
        _token(self.mapping_state, L2_INFORMATION_STATES, "/mapping_state")
        alternatives = _record_tuple(
            self.mapping_alternatives, L2MappingAlternative, "/mapping_alternatives"
        )
        object.__setattr__(self, "mapping_alternatives", alternatives)
        _check_mapping_cardinality(
            self.mapping_state, alternatives, "/mapping_alternatives"
        )

    def as_dict(self):
        return {
            "participant_id": self.participant_id,
            "role": self.role,
            "identity_reference": (
                None
                if self.identity_reference is None
                else self.identity_reference.as_dict()
            ),
            "construct_id": self.construct_id,
            "construct_version": self.construct_version,
            "mapping_state": self.mapping_state,
            "mapping_alternatives": [
                item.as_dict() for item in self.mapping_alternatives
            ],
        }


@dataclass(frozen=True)
class L2ContextDeclaration:
    context_id: str
    subject_declaration: str
    treatment: str
    declaration: str
    source_reference: L2SourceRecord | None

    def __post_init__(self):
        _identifier(self.context_id, "/context_id")
        _text(self.subject_declaration, "/subject_declaration")
        _token(self.treatment, L2_CONTEXT_TREATMENTS, "/treatment")
        _text(self.declaration, "/declaration")
        _opt_record(self.source_reference, L2SourceRecord, "/source_reference")

    def as_dict(self):
        return {
            "context_id": self.context_id,
            "subject_declaration": self.subject_declaration,
            "treatment": self.treatment,
            "declaration": self.declaration,
            "source_reference": (
                None if self.source_reference is None else self.source_reference.as_dict()
            ),
        }


@dataclass(frozen=True)
class L2MissingDeclaration:
    field: str
    reason: str

    def __post_init__(self):
        _pointer(self.field, "/field")
        _text(self.reason, "/reason")

    def as_dict(self):
        return {"field": self.field, "reason": self.reason}


# ================================================================================
# Shared descriptor records
# ================================================================================


@dataclass(frozen=True)
class L2ConditionsProfileReference:
    state: str
    reference: L2ImmutableReference | None
    reason: str | None

    def __post_init__(self):
        _token(self.state, L2_PROFILE_STATES, "/state")
        _opt_record(self.reference, L2ImmutableReference, "/reference")
        _opt_text(self.reason, "/reason")
        if self.state == "SUPPLIED":
            if self.reference is None:
                _invariant("/reference", "SUPPLIED requires a reference")
            if self.reason is not None:
                _invariant("/reason", "SUPPLIED requires a null reason")
        else:
            if self.reference is not None:
                _invariant("/reference", "UNAVAILABLE requires a null reference")
            if self.reason is None:
                _invariant("/reason", "UNAVAILABLE requires a reason")

    def as_dict(self):
        return {
            "state": self.state,
            "reference": None if self.reference is None else self.reference.as_dict(),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class L2NamedDeclaration:
    name: str
    value: str

    def __post_init__(self):
        _identifier(self.name, "/name")
        _text(self.value, "/value")

    def as_dict(self):
        return {"name": self.name, "value": self.value}


@dataclass(frozen=True)
class L2MethodDeclaration:
    reference: L2ImmutableReference | None
    parameters: tuple
    representation: str | None
    run_reference: L2ImmutableReference | None

    def __post_init__(self):
        _opt_record(self.reference, L2ImmutableReference, "/reference")
        parameters = _record_tuple(self.parameters, L2NamedDeclaration, "/parameters")
        object.__setattr__(self, "parameters", parameters)
        seen = set()
        for position, parameter in enumerate(parameters):
            if parameter.name in seen:
                _invariant(
                    "/parameters/{0}/name".format(position),
                    "parameter names must be unique",
                )
            seen.add(parameter.name)
        _opt_text(self.representation, "/representation")
        _opt_record(self.run_reference, L2ImmutableReference, "/run_reference")

    def as_dict(self):
        return {
            "reference": None if self.reference is None else self.reference.as_dict(),
            "parameters": [item.as_dict() for item in self.parameters],
            "representation": self.representation,
            "run_reference": (
                None if self.run_reference is None else self.run_reference.as_dict()
            ),
        }


@dataclass(frozen=True)
class L2ReferenceState:
    kind: str
    references: tuple
    declaration: str

    def __post_init__(self):
        _token(self.kind, L2_REFERENCE_STATE_KINDS, "/kind")
        references = _source_tuple(self.references, "/references")
        object.__setattr__(self, "references", references)
        _text(self.declaration, "/declaration")
        if self.kind in _INAPPLICABLE_REFERENCE_STATES:
            if len(references) != 0:
                _invariant(
                    "/references",
                    "{0} requires an empty reference tuple".format(self.kind),
                )
        elif len(references) == 0:
            _invariant("/references", "this kind requires at least one reference")

    def as_dict(self):
        return {
            "kind": self.kind,
            "references": [item.as_dict() for item in self.references],
            "declaration": self.declaration,
        }


@dataclass(frozen=True)
class L2ObservableDefinition:
    definition_reference: L2ImmutableReference | None
    observable_name: str
    subject_ids: tuple
    selection_declaration: str | None
    unit_class: str | None
    unit_symbol: str | None
    conditions_required: bool
    method: L2MethodDeclaration
    conditions_profile: L2ConditionsProfileReference
    reference_state: L2ReferenceState
    comparability_reference: L2SourceRecord | None
    limitation: str | None

    def __post_init__(self):
        _opt_record(
            self.definition_reference, L2ImmutableReference, "/definition_reference"
        )
        _text(self.observable_name, "/observable_name")
        subjects = _identifier_tuple(self.subject_ids, "/subject_ids")
        object.__setattr__(self, "subject_ids", subjects)
        _opt_text(self.selection_declaration, "/selection_declaration")
        _opt_token(self.unit_class, L2_UNIT_CLASSES, "/unit_class")
        _opt_text(self.unit_symbol, "/unit_symbol")
        _boolean(self.conditions_required, "/conditions_required")
        _record(self.method, L2MethodDeclaration, "/method")
        _record(
            self.conditions_profile, L2ConditionsProfileReference, "/conditions_profile"
        )
        _record(self.reference_state, L2ReferenceState, "/reference_state")
        _opt_record(
            self.comparability_reference, L2SourceRecord, "/comparability_reference"
        )
        _opt_text(self.limitation, "/limitation")

    def as_dict(self):
        return {
            "definition_reference": (
                None
                if self.definition_reference is None
                else self.definition_reference.as_dict()
            ),
            "observable_name": self.observable_name,
            "subject_ids": list(self.subject_ids),
            "selection_declaration": self.selection_declaration,
            "unit_class": self.unit_class,
            "unit_symbol": self.unit_symbol,
            "conditions_required": self.conditions_required,
            "method": self.method.as_dict(),
            "conditions_profile": self.conditions_profile.as_dict(),
            "reference_state": self.reference_state.as_dict(),
            "comparability_reference": (
                None
                if self.comparability_reference is None
                else self.comparability_reference.as_dict()
            ),
            "limitation": self.limitation,
        }


@dataclass(frozen=True)
class L2DescriptorValue:
    kind: str
    number: str | None
    category: str | None

    def __post_init__(self):
        _token(self.kind, L2_VALUE_KINDS, "/kind")
        _opt_decimal(self.number, "/number")
        _opt_text(self.category, "/category")
        if self.kind == "NUMERIC":
            if self.number is None:
                _invariant("/number", "NUMERIC requires a number")
            if self.category is not None:
                _invariant("/category", "NUMERIC requires a null category")
        else:
            if self.category is None:
                _invariant("/category", "CATEGORICAL requires a category")
            if self.number is not None:
                _invariant("/number", "CATEGORICAL requires a null number")

    def as_dict(self):
        return {"kind": self.kind, "number": self.number, "category": self.category}


@dataclass(frozen=True)
class L2DescriptorObservation:
    observation_id: str
    pose_id: str | None
    sample_id: str | None
    replicate_id: str | None
    source_reference: L2SourceRecord | None
    value: L2DescriptorValue | None
    missing_declarations: tuple

    def __post_init__(self):
        _identifier(self.observation_id, "/observation_id")
        _opt_identifier(self.pose_id, "/pose_id")
        _opt_identifier(self.sample_id, "/sample_id")
        _opt_identifier(self.replicate_id, "/replicate_id")
        _opt_record(self.source_reference, L2SourceRecord, "/source_reference")
        _opt_record(self.value, L2DescriptorValue, "/value")
        missing = _record_tuple(
            self.missing_declarations, L2MissingDeclaration, "/missing_declarations"
        )
        object.__setattr__(self, "missing_declarations", missing)

    def as_dict(self):
        return {
            "observation_id": self.observation_id,
            "pose_id": self.pose_id,
            "sample_id": self.sample_id,
            "replicate_id": self.replicate_id,
            "source_reference": (
                None if self.source_reference is None else self.source_reference.as_dict()
            ),
            "value": None if self.value is None else self.value.as_dict(),
            "missing_declarations": [
                item.as_dict() for item in self.missing_declarations
            ],
        }


@dataclass(frozen=True)
class L2UncertaintyRecord:
    uncertainty_id: str
    kind: str
    state: str
    observation_ids: tuple
    declaration: str
    source_references: tuple

    def __post_init__(self):
        _identifier(self.uncertainty_id, "/uncertainty_id")
        _token(self.kind, L2_UNCERTAINTY_KINDS, "/kind")
        _token(self.state, L2_UNCERTAINTY_STATES, "/state")
        observations = _identifier_tuple(self.observation_ids, "/observation_ids")
        object.__setattr__(self, "observation_ids", observations)
        _text(self.declaration, "/declaration")
        sources = _source_tuple(self.source_references, "/source_references")
        object.__setattr__(self, "source_references", sources)
        if self.state == "DECLARED" and len(sources) == 0:
            _invariant(
                "/source_references", "DECLARED requires at least one source reference"
            )

    def as_dict(self):
        return {
            "uncertainty_id": self.uncertainty_id,
            "kind": self.kind,
            "state": self.state,
            "observation_ids": list(self.observation_ids),
            "declaration": self.declaration,
            "source_references": [item.as_dict() for item in self.source_references],
        }


@dataclass(frozen=True)
class L2AmbiguityAlternative:
    declaration: str
    source_references: tuple

    def __post_init__(self):
        _text(self.declaration, "/declaration")
        sources = _source_tuple(self.source_references, "/source_references")
        object.__setattr__(self, "source_references", sources)

    def as_dict(self):
        return {
            "declaration": self.declaration,
            "source_references": [item.as_dict() for item in self.source_references],
        }


@dataclass(frozen=True)
class L2AmbiguityRecord:
    ambiguity_id: str
    field_paths: tuple
    observation_ids: tuple
    alternatives: tuple
    declaration: str

    def __post_init__(self):
        _identifier(self.ambiguity_id, "/ambiguity_id")
        paths = _pointer_tuple(self.field_paths, "/field_paths")
        object.__setattr__(self, "field_paths", paths)
        if len(paths) == 0:
            _invariant("/field_paths", "at least one field path is required")
        observations = _identifier_tuple(self.observation_ids, "/observation_ids")
        object.__setattr__(self, "observation_ids", observations)
        alternatives = _record_tuple(
            self.alternatives, L2AmbiguityAlternative, "/alternatives"
        )
        _no_duplicates(alternatives, "/alternatives", "ambiguity alternatives")
        object.__setattr__(self, "alternatives", alternatives)
        if len(alternatives) < 2:
            _invariant("/alternatives", "at least two distinct alternatives are required")
        _text(self.declaration, "/declaration")

    def as_dict(self):
        return {
            "ambiguity_id": self.ambiguity_id,
            "field_paths": list(self.field_paths),
            "observation_ids": list(self.observation_ids),
            "alternatives": [item.as_dict() for item in self.alternatives],
            "declaration": self.declaration,
        }


@dataclass(frozen=True)
class L2ConflictRecord:
    conflict_id: str
    observation_ids: tuple
    comparability_reference: L2SourceRecord
    declaration: str
    declared_by: str
    declared_at: str
    source_references: tuple

    def __post_init__(self):
        _identifier(self.conflict_id, "/conflict_id")
        observations = _identifier_tuple(self.observation_ids, "/observation_ids")
        object.__setattr__(self, "observation_ids", observations)
        if len(observations) < 2:
            _invariant(
                "/observation_ids", "at least two distinct observations are required"
            )
        _record(self.comparability_reference, L2SourceRecord, "/comparability_reference")
        _text(self.declaration, "/declaration")
        _identifier(self.declared_by, "/declared_by")
        _timestamp(self.declared_at, "/declared_at")
        sources = _source_tuple(self.source_references, "/source_references")
        object.__setattr__(self, "source_references", sources)

    def as_dict(self):
        return {
            "conflict_id": self.conflict_id,
            "observation_ids": list(self.observation_ids),
            "comparability_reference": self.comparability_reference.as_dict(),
            "declaration": self.declaration,
            "declared_by": self.declared_by,
            "declared_at": self.declared_at,
            "source_references": [item.as_dict() for item in self.source_references],
        }


@dataclass(frozen=True)
class L2DescriptorReason:
    code: str
    field_paths: tuple
    observation_ids: tuple
    record_ids: tuple

    def __post_init__(self):
        _token(self.code, L2_REASON_CODES, "/code")
        paths = _pointer_tuple(self.field_paths, "/field_paths")
        object.__setattr__(self, "field_paths", paths)
        observations = _identifier_tuple(self.observation_ids, "/observation_ids")
        object.__setattr__(self, "observation_ids", observations)
        records = _identifier_tuple(self.record_ids, "/record_ids")
        object.__setattr__(self, "record_ids", records)

    def as_dict(self):
        return {
            "code": self.code,
            "field_paths": list(self.field_paths),
            "observation_ids": list(self.observation_ids),
            "record_ids": list(self.record_ids),
        }


@dataclass(frozen=True)
class L2DescriptorRecord:
    descriptor_id: str
    family: str
    scope_declaration: str | None
    definition: L2ObservableDefinition
    observations: tuple
    uncertainties: tuple
    ambiguities: tuple
    conflicts: tuple
    missing_declarations: tuple

    def __post_init__(self):
        _identifier(self.descriptor_id, "/descriptor_id")
        _token(self.family, LAYER_2B_FAMILIES, "/family")
        _opt_text(self.scope_declaration, "/scope_declaration")
        _record(self.definition, L2ObservableDefinition, "/definition")
        for name, element in (
            ("observations", L2DescriptorObservation),
            ("uncertainties", L2UncertaintyRecord),
            ("ambiguities", L2AmbiguityRecord),
            ("conflicts", L2ConflictRecord),
            ("missing_declarations", L2MissingDeclaration),
        ):
            items = _record_tuple(getattr(self, name), element, "/" + name)
            object.__setattr__(self, name, items)

    def as_dict(self):
        """Constructor fields only; the document appends conditions and reasons."""
        return {
            "descriptor_id": self.descriptor_id,
            "family": self.family,
            "scope_declaration": self.scope_declaration,
            "definition": self.definition.as_dict(),
            "observations": [item.as_dict() for item in self.observations],
            "uncertainties": [item.as_dict() for item in self.uncertainties],
            "ambiguities": [item.as_dict() for item in self.ambiguities],
            "conflicts": [item.as_dict() for item in self.conflicts],
            "missing_declarations": [
                item.as_dict() for item in self.missing_declarations
            ],
        }


@dataclass(frozen=True)
class L2FamilyAvailability:
    family: str
    descriptor_ids: tuple
    absence_reason: str | None

    def __post_init__(self):
        _token(self.family, LAYER_2B_FAMILIES, "/family")
        identifiers = _identifier_tuple(self.descriptor_ids, "/descriptor_ids")
        object.__setattr__(self, "descriptor_ids", identifiers)
        _opt_text(self.absence_reason, "/absence_reason")
        if len(identifiers) == 0 and self.absence_reason is None:
            _invariant("/absence_reason", "an empty descriptor tuple requires a reason")
        if len(identifiers) > 0 and self.absence_reason is not None:
            _invariant(
                "/absence_reason", "a non-empty descriptor tuple requires a null reason"
            )

    def as_dict(self):
        return {
            "family": self.family,
            "descriptor_ids": list(self.descriptor_ids),
            "absence_reason": self.absence_reason,
        }


# ================================================================================
# Collective scope records
# ================================================================================


@dataclass(frozen=True)
class L2LocalDocumentReference:
    """Names a Layer 2A document revision. Its contents are never loaded."""

    document_id: str
    revision: str
    reference: L2ImmutableReference

    def __post_init__(self):
        _identifier(self.document_id, "/document_id")
        _identifier(self.revision, "/revision")
        _record(self.reference, L2ImmutableReference, "/reference")

    def as_dict(self):
        return {
            "document_id": self.document_id,
            "revision": self.revision,
            "reference": self.reference.as_dict(),
        }


@dataclass(frozen=True)
class L2JointFrame:
    """A caller assertion. It establishes no coordinate reconciliation."""

    frame_id: str
    frame_kind: str
    pose_ids: tuple
    declaration: str
    source_reference: L2SourceRecord | None

    def __post_init__(self):
        _identifier(self.frame_id, "/frame_id")
        _token(self.frame_kind, L2_FRAME_KINDS, "/frame_kind")
        poses = _identifier_tuple(self.pose_ids, "/pose_ids")
        object.__setattr__(self, "pose_ids", poses)
        _text(self.declaration, "/declaration")
        _opt_record(self.source_reference, L2SourceRecord, "/source_reference")

    def as_dict(self):
        return {
            "frame_id": self.frame_id,
            "frame_kind": self.frame_kind,
            "pose_ids": list(self.pose_ids),
            "declaration": self.declaration,
            "source_reference": (
                None if self.source_reference is None else self.source_reference.as_dict()
            ),
        }


@dataclass(frozen=True)
class L2AssemblyElement:
    element_id: str
    kind: str
    identity_reference: L2ImmutableReference | None
    construct_id: str | None
    construct_version: str | None
    mapping_state: str
    mapping_alternatives: tuple
    representation_declaration: str | None

    def __post_init__(self):
        _identifier(self.element_id, "/element_id")
        _token(self.kind, L2_ELEMENT_KINDS, "/kind")
        _opt_record(self.identity_reference, L2ImmutableReference, "/identity_reference")
        _opt_identifier(self.construct_id, "/construct_id")
        _opt_identifier(self.construct_version, "/construct_version")
        _token(self.mapping_state, L2_INFORMATION_STATES, "/mapping_state")
        alternatives = _record_tuple(
            self.mapping_alternatives, L2MappingAlternative, "/mapping_alternatives"
        )
        object.__setattr__(self, "mapping_alternatives", alternatives)
        _check_mapping_cardinality(
            self.mapping_state, alternatives, "/mapping_alternatives"
        )
        _opt_text(self.representation_declaration, "/representation_declaration")

    def as_dict(self):
        return {
            "element_id": self.element_id,
            "kind": self.kind,
            "identity_reference": (
                None
                if self.identity_reference is None
                else self.identity_reference.as_dict()
            ),
            "construct_id": self.construct_id,
            "construct_version": self.construct_version,
            "mapping_state": self.mapping_state,
            "mapping_alternatives": [
                item.as_dict() for item in self.mapping_alternatives
            ],
            "representation_declaration": self.representation_declaration,
        }


@dataclass(frozen=True)
class L2Connection:
    """Sites and connectivity are declared, never inferred."""

    connection_id: str
    first_subject_id: str
    first_site_declaration: str | None
    second_subject_id: str
    second_site_declaration: str | None
    connection_declaration: str | None
    source_reference: L2SourceRecord | None

    def __post_init__(self):
        _identifier(self.connection_id, "/connection_id")
        _identifier(self.first_subject_id, "/first_subject_id")
        _opt_text(self.first_site_declaration, "/first_site_declaration")
        _identifier(self.second_subject_id, "/second_subject_id")
        _opt_text(self.second_site_declaration, "/second_site_declaration")
        _opt_text(self.connection_declaration, "/connection_declaration")
        _opt_record(self.source_reference, L2SourceRecord, "/source_reference")

    def endpoints(self):
        """The ordered endpoint/site declaration. Reversed order is not normalized."""
        return (
            self.first_subject_id,
            self.first_site_declaration,
            self.second_subject_id,
            self.second_site_declaration,
        )

    def as_dict(self):
        return {
            "connection_id": self.connection_id,
            "first_subject_id": self.first_subject_id,
            "first_site_declaration": self.first_site_declaration,
            "second_subject_id": self.second_subject_id,
            "second_site_declaration": self.second_site_declaration,
            "connection_declaration": self.connection_declaration,
            "source_reference": (
                None if self.source_reference is None else self.source_reference.as_dict()
            ),
        }


@dataclass(frozen=True)
class L2LocalAssociation:
    """One local-association position. It never creates a collective frame."""

    slot_id: str
    binder_participant_id: str | None
    target_participant_id: str | None
    candidate_id: str | None
    scenario_id: str | None
    pose_association_reference: L2AssociationReference | None
    local_document_reference: L2LocalDocumentReference | None
    missing_reason: str | None

    def __post_init__(self):
        _token(self.slot_id, L2_SLOT_IDS, "/slot_id")
        _opt_identifier(self.binder_participant_id, "/binder_participant_id")
        _opt_identifier(self.target_participant_id, "/target_participant_id")
        _opt_identifier(self.candidate_id, "/candidate_id")
        _opt_identifier(self.scenario_id, "/scenario_id")
        _opt_record(
            self.pose_association_reference,
            L2AssociationReference,
            "/pose_association_reference",
        )
        _opt_record(
            self.local_document_reference,
            L2LocalDocumentReference,
            "/local_document_reference",
        )
        _opt_text(self.missing_reason, "/missing_reason")
        absent = [
            name
            for name in _LOCAL_ASSOCIATION_OPTIONAL
            if getattr(self, name) is None
        ]
        if absent and self.missing_reason is None:
            _structural(
                "/missing_reason",
                "an absent identity/reference field requires a missing reason",
            )
        if not absent and self.missing_reason is not None:
            _structural(
                "/missing_reason",
                "a complete local association requires a null missing reason",
            )

    def as_dict(self):
        return {
            "slot_id": self.slot_id,
            "binder_participant_id": self.binder_participant_id,
            "target_participant_id": self.target_participant_id,
            "candidate_id": self.candidate_id,
            "scenario_id": self.scenario_id,
            "pose_association_reference": (
                None
                if self.pose_association_reference is None
                else self.pose_association_reference.as_dict()
            ),
            "local_document_reference": (
                None
                if self.local_document_reference is None
                else self.local_document_reference.as_dict()
            ),
            "missing_reason": self.missing_reason,
        }


@dataclass(frozen=True)
class L2CollectiveScope:
    participants: tuple
    local_associations: tuple
    assembly_elements: tuple
    connections: tuple
    joint_frame: L2JointFrame | None
    target_site_declaration: str | None
    assembly_task_declaration: str | None
    context_declarations: tuple
    missing_declarations: tuple

    def __post_init__(self):
        for name, element in (
            ("participants", L2MolecularParticipant),
            ("local_associations", L2LocalAssociation),
            ("assembly_elements", L2AssemblyElement),
            ("connections", L2Connection),
        ):
            items = _record_tuple(getattr(self, name), element, "/" + name)
            object.__setattr__(self, name, items)
        _opt_record(self.joint_frame, L2JointFrame, "/joint_frame")
        _opt_text(self.target_site_declaration, "/target_site_declaration")
        _opt_text(self.assembly_task_declaration, "/assembly_task_declaration")
        contexts = _record_tuple(
            self.context_declarations, L2ContextDeclaration, "/context_declarations"
        )
        object.__setattr__(self, "context_declarations", contexts)
        missing = _record_tuple(
            self.missing_declarations, L2MissingDeclaration, "/missing_declarations"
        )
        object.__setattr__(self, "missing_declarations", missing)

    def as_dict(self):
        return {
            "participants": [item.as_dict() for item in self.participants],
            "local_associations": [
                item.as_dict() for item in self.local_associations
            ],
            "assembly_elements": [item.as_dict() for item in self.assembly_elements],
            "connections": [item.as_dict() for item in self.connections],
            "joint_frame": (
                None if self.joint_frame is None else self.joint_frame.as_dict()
            ),
            "target_site_declaration": self.target_site_declaration,
            "assembly_task_declaration": self.assembly_task_declaration,
            "context_declarations": [
                item.as_dict() for item in self.context_declarations
            ],
            "missing_declarations": [
                item.as_dict() for item in self.missing_declarations
            ],
        }


# ================================================================================
# Canonical bytes
# ================================================================================


def _canonical_bytes(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _reject_number(_value):
    _structural("", "JSON numeric primitives are not used in this document")


def _object_pairs(pairs):
    seen = set()
    for key, _value in pairs:
        if key in seen:
            _structural("", "duplicate JSON object key: {0}".format(key))
        seen.add(key)
    return dict(pairs)


def _unique(values):
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


# ================================================================================
# The public document
# ================================================================================

_TOP_LEVEL_KEYS = (
    "document_type",
    "document_id",
    "revision",
    "declared_by",
    "declared_at",
    "source_references",
    "candidate_anchor",
    "scope",
    "poses",
    "family_availability",
    "descriptors",
    "missing_declarations",
    "non_claim",
)

_DESCRIPTOR_REQUIRED = (("scope_declaration", "/scope_declaration"),)
_DEFINITION_REQUIRED = (
    ("definition_reference", "/definition/definition_reference"),
    ("selection_declaration", "/definition/selection_declaration"),
    ("limitation", "/definition/limitation"),
)
_METHOD_REQUIRED = (
    ("reference", "/definition/method/reference"),
    ("representation", "/definition/method/representation"),
    ("run_reference", "/definition/method/run_reference"),
)
_POSE_REQUIRED = (
    "model_id",
    "conformer_id",
    "frame_id",
    "source_reference",
    "run_reference",
    "method_reference",
)

#: The collective scope declarations a provided collective observation requires.
_COLLECTIVE_SCOPE_REQUIRED = (
    "joint_frame",
    "participants",
    "assembly_elements",
    "connections",
)


@dataclass(frozen=True)
class Layer2BDescriptorInput:
    """One immutable ``layer_2b_descriptor_input/1`` document."""

    document_id: str
    revision: str
    declared_by: str
    declared_at: str
    source_references: tuple
    candidate_anchor: L2CandidateAnchor
    scope: L2CollectiveScope
    poses: tuple
    family_availability: tuple
    descriptors: tuple
    missing_declarations: tuple
    document_type: str = field(init=False, default=LAYER_2B_DOCUMENT_TYPE)
    non_claim: str = field(init=False, default=LAYER_2B_NON_CLAIM)
    descriptor_conditions: tuple = field(init=False, default=())
    descriptor_reasons: tuple = field(init=False, default=())

    def __post_init__(self):
        self._structural_phase()
        self._reference_phase()
        self._identity_phase()
        self._cardinality_phase()
        self._family_phase()
        self._derived_phase()

    # -- phase 1: structural traversal in declared field order ---------------------

    def _structural_phase(self):
        _identifier(self.document_id, "/document_id")
        _identifier(self.revision, "/revision")
        _identifier(self.declared_by, "/declared_by")
        _timestamp(self.declared_at, "/declared_at")
        sources = _source_tuple(self.source_references, "/source_references")
        object.__setattr__(self, "source_references", sources)
        _record(self.candidate_anchor, L2CandidateAnchor, "/candidate_anchor")
        _record(self.scope, L2CollectiveScope, "/scope")
        poses = _record_tuple(self.poses, L2PoseRecord, "/poses")
        object.__setattr__(self, "poses", poses)
        availability = _record_tuple(
            self.family_availability, L2FamilyAvailability, "/family_availability"
        )
        object.__setattr__(self, "family_availability", availability)
        descriptors = _record_tuple(self.descriptors, L2DescriptorRecord, "/descriptors")
        object.__setattr__(self, "descriptors", descriptors)
        missing = _record_tuple(
            self.missing_declarations, L2MissingDeclaration, "/missing_declarations"
        )
        object.__setattr__(self, "missing_declarations", missing)

    # -- phase 2: internal reference resolution ------------------------------------

    def _reference_phase(self):
        subjects = {}
        for collection in ("participants", "assembly_elements"):
            key = "participant_id" if collection == "participants" else "element_id"
            for position, item in enumerate(getattr(self.scope, collection)):
                identifier = getattr(item, key)
                if identifier in subjects:
                    _reference_error(
                        "/scope/{0}/{1}/{2}".format(collection, position, key),
                        "participant and assembly-element identifiers share one "
                        "document-wide namespace",
                    )
                subjects[identifier] = (collection, position)
        object.__setattr__(self, "_subject_index", subjects)

        poses = {}
        for position, pose in enumerate(self.poses):
            if pose.pose_id in poses:
                _reference_error(
                    "/poses/{0}/pose_id".format(position),
                    "pose identifiers must be unique",
                )
            poses[pose.pose_id] = position
        object.__setattr__(self, "_pose_index", poses)

        participants = {
            item.participant_id: position
            for position, item in enumerate(self.scope.participants)
        }
        object.__setattr__(self, "_participant_index", participants)

        # Only an unresolvable identifier is a reference fault here. A role
        # disagreement is retained, never repaired, and is reported by the derived
        # phase as an unresolved scope declaration.
        for position, association in enumerate(self.scope.local_associations):
            prefix = "/scope/local_associations/{0}".format(position)
            for name in ("binder_participant_id", "target_participant_id"):
                value = getattr(association, name)
                if value is None:
                    continue
                if value not in participants:
                    _reference_error(
                        prefix + "/" + name,
                        "identifier does not resolve to a participant",
                    )

        for collection in ("participants", "assembly_elements"):
            for position, item in enumerate(getattr(self.scope, collection)):
                for offset, alternative in enumerate(item.mapping_alternatives):
                    if alternative.pose_id is None:
                        continue
                    if alternative.pose_id not in poses:
                        _reference_error(
                            "/scope/{0}/{1}/mapping_alternatives/{2}/pose_id".format(
                                collection, position, offset
                            ),
                            "identifier does not resolve to a pose",
                        )

        for position, connection in enumerate(self.scope.connections):
            for name in ("first_subject_id", "second_subject_id"):
                if getattr(connection, name) not in subjects:
                    _reference_error(
                        "/scope/connections/{0}/{1}".format(position, name),
                        "identifier resolves only to a participant or assembly element",
                    )

        if self.scope.joint_frame is not None:
            for offset, pose_id in enumerate(self.scope.joint_frame.pose_ids):
                if pose_id not in poses:
                    _reference_error(
                        "/scope/joint_frame/pose_ids/{0}".format(offset),
                        "identifier does not resolve to a pose",
                    )

        for index, descriptor in enumerate(self.descriptors):
            base = "/descriptors/{0}".format(index)
            local = set()
            for position, observation in enumerate(descriptor.observations):
                local.add(observation.observation_id)
                if observation.pose_id is not None and observation.pose_id not in poses:
                    _reference_error(
                        "{0}/observations/{1}/pose_id".format(base, position),
                        "identifier does not resolve to a pose",
                    )
            for position, subject in enumerate(descriptor.definition.subject_ids):
                if subject not in subjects:
                    _reference_error(
                        "{0}/definition/subject_ids/{1}".format(base, position),
                        "subject identifier resolves only to a declared participant "
                        "or assembly element",
                    )
            for name in ("uncertainties", "ambiguities", "conflicts"):
                for position, record in enumerate(getattr(descriptor, name)):
                    for offset, observation_id in enumerate(record.observation_ids):
                        if observation_id not in local:
                            _reference_error(
                                "{0}/{1}/{2}/observation_ids/{3}".format(
                                    base, name, position, offset
                                ),
                                "identifier does not resolve within this descriptor",
                            )

        known = {item.descriptor_id for item in self.descriptors}
        for position, availability in enumerate(self.family_availability):
            for offset, descriptor_id in enumerate(availability.descriptor_ids):
                if descriptor_id not in known:
                    _reference_error(
                        "/family_availability/{0}/descriptor_ids/{1}".format(
                            position, offset
                        ),
                        "identifier does not resolve to a descriptor",
                    )

    # -- phase 3: identity agreement -----------------------------------------------

    def _identity_phase(self):
        admission = self.candidate_anchor.admission_reference
        if admission is not None:
            if self.candidate_anchor.candidate_id is None:
                _reference_error(
                    "/candidate_anchor/candidate_id",
                    "an admission reference requires a candidate identifier",
                )
            if self.candidate_anchor.candidate_id != admission.candidate_id:
                _reference_error(
                    "/candidate_anchor/candidate_id",
                    "candidate identity disagrees with the admission reference",
                )
        for position, association in enumerate(self.scope.local_associations):
            for name in ("candidate_id", "scenario_id"):
                value = getattr(association, name)
                if value is None:
                    continue
                if value != getattr(self.candidate_anchor, name):
                    _reference_error(
                        "/scope/local_associations/{0}/{1}".format(position, name),
                        "a non-null identifier must equal the collective anchor",
                    )
        for index, descriptor in enumerate(self.descriptors):
            for offset, observation in enumerate(descriptor.observations):
                if observation.pose_id is None:
                    continue
                field_path = "/descriptors/{0}/observations/{1}/pose_id".format(index, offset)
                for subject in descriptor.definition.subject_ids:
                    collection, position = self._subject_index[subject]
                    item = getattr(self.scope, collection)[position]
                    if item.mapping_state != "SUPPLIED":
                        continue
                    mapped_pose = item.mapping_alternatives[0].pose_id
                    if mapped_pose is not None and mapped_pose != observation.pose_id:
                        _reference_error(
                            field_path,
                            "observation pose disagrees with a supplied subject mapping",
                        )
                frame = self.scope.joint_frame
                if frame is None:
                    continue
                if frame.pose_ids and observation.pose_id not in frame.pose_ids:
                    _reference_error(field_path, "observation pose is outside the declared joint frame")
                pose_position = self._pose_index[observation.pose_id]
                pose = self.poses[pose_position]
                if pose.frame_id is not None and pose.frame_id != frame.frame_id:
                    _reference_error(
                        "/poses/{0}/frame_id".format(pose_position),
                        "observation pose frame disagrees with the declared joint frame",
                    )

    # -- phase 4: cardinality, ordering and duplicates -------------------------------

    def _cardinality_phase(self):
        associations = self.scope.local_associations
        if len(associations) != len(L2_SLOT_IDS):
            _invariant(
                "/scope/local_associations",
                "exactly three local-association records are required",
            )
        for position, association in enumerate(associations):
            if association.slot_id != L2_SLOT_IDS[position]:
                _invariant(
                    "/scope/local_associations/{0}/slot_id".format(position),
                    "local associations must follow slot_1, slot_2, slot_3 order",
                )

        seen_binders = set()
        for position, association in enumerate(associations):
            value = association.binder_participant_id
            if value is None:
                continue
            if value in seen_binders:
                _invariant(
                    "/scope/local_associations/{0}/binder_participant_id".format(
                        position
                    ),
                    "binder identifiers across positions must be distinct",
                )
            seen_binders.add(value)
        for position, participant in enumerate(self.scope.participants):
            if participant.role == "BINDER" and participant.participant_id not in seen_binders:
                _invariant(
                    "/scope/participants/{0}/participant_id".format(position),
                    "every binder participant must be referenced by exactly one "
                    "local-association position",
                )

        for name, key in (
            ("context_declarations", "context_id"),
            ("connections", "connection_id"),
        ):
            seen = set()
            for position, record in enumerate(getattr(self.scope, name)):
                identifier = getattr(record, key)
                if identifier in seen:
                    _invariant(
                        "/scope/{0}/{1}/{2}".format(name, position, key),
                        "identifiers must be unique within their record collection",
                    )
                seen.add(identifier)

        seen_endpoints = set()
        for position, connection in enumerate(self.scope.connections):
            endpoints = connection.endpoints()
            if endpoints in seen_endpoints:
                _invariant(
                    "/scope/connections/{0}".format(position),
                    "a connection may not repeat an ordered endpoint/site declaration",
                )
            seen_endpoints.add(endpoints)

        seen_descriptors = set()
        for index, descriptor in enumerate(self.descriptors):
            if descriptor.descriptor_id in seen_descriptors:
                _invariant(
                    "/descriptors/{0}/descriptor_id".format(index),
                    "descriptor identifiers must be unique document-wide",
                )
            seen_descriptors.add(descriptor.descriptor_id)
            self._descriptor_cardinality(index, descriptor)

        self._scope_duplication()
        self._role_agreement()

    def _role_agreement(self):
        """Retain a role disagreement only when the caller explicitly names it."""
        recorded = {
            record.field
            for record in (*self.missing_declarations, *self.scope.missing_declarations)
        }
        for position, association in enumerate(self.scope.local_associations):
            for name, role in (
                ("binder_participant_id", "BINDER"),
                ("target_participant_id", "RECEPTOR"),
            ):
                value = getattr(association, name)
                if value is None:
                    continue
                pointer = "/scope/local_associations/{0}/{1}".format(position, name)
                participant = self.scope.participants[self._participant_index[value]]
                if participant.role == role or pointer in recorded:
                    continue
                _invariant(
                    pointer,
                    "the named participant does not carry the {0} role and no unresolved "
                    "declaration names {1}".format(role, pointer),
                )

    def _descriptor_cardinality(self, index, descriptor):
        base = "/descriptors/{0}".format(index)
        namespace = set()
        for name, key in (
            ("observations", "observation_id"),
            ("uncertainties", "uncertainty_id"),
            ("ambiguities", "ambiguity_id"),
            ("conflicts", "conflict_id"),
        ):
            for position, record in enumerate(getattr(descriptor, name)):
                identifier = getattr(record, key)
                if identifier in namespace:
                    _invariant(
                        "{0}/{1}/{2}/{3}".format(base, name, position, key),
                        "descriptor record identifiers share one namespace",
                    )
                namespace.add(identifier)

        kinds = tuple(item.kind for item in descriptor.uncertainties)
        if kinds != L2_UNCERTAINTY_KINDS:
            _invariant(
                base + "/uncertainties",
                "exactly one uncertainty record per kind is required, "
                "in L2_UNCERTAINTY_KINDS order",
            )

        seen = set()
        for position, conflict in enumerate(descriptor.conflicts):
            key = (frozenset(conflict.observation_ids), conflict.declaration)
            if key in seen:
                _invariant(
                    "{0}/conflicts/{1}".format(base, position),
                    "conflicts addressing the same observations must differ in "
                    "their declarations",
                )
            seen.add(key)

    def _scope_duplication(self):
        seen = {}
        for index, descriptor in enumerate(self.descriptors):
            definition = descriptor.definition
            key = (
                descriptor.family,
                definition.definition_reference,
                definition.subject_ids,
                definition.selection_declaration,
                definition.method,
                definition.conditions_profile,
                definition.reference_state,
            )
            if key in seen:
                _invariant(
                    "/descriptors/{0}/definition".format(index),
                    "a descriptor may not duplicate the complete declared "
                    "observable scope of descriptor {0}".format(seen[key]),
                )
            seen[key] = index

    # -- phase 5: family checks -------------------------------------------------------

    def _family_phase(self):
        if len(self.family_availability) != len(LAYER_2B_FAMILIES):
            _invariant(
                "/family_availability",
                "exactly three availability records are required",
            )
        for position, availability in enumerate(self.family_availability):
            if availability.family != LAYER_2B_FAMILIES[position]:
                _invariant(
                    "/family_availability/{0}/family".format(position),
                    "availability records must follow LAYER_2B_FAMILIES order",
                )
            expected = tuple(
                descriptor.descriptor_id
                for descriptor in self.descriptors
                if descriptor.family == availability.family
            )
            if availability.descriptor_ids != expected:
                _invariant(
                    "/family_availability/{0}/descriptor_ids".format(position),
                    "descriptor identifiers must be exactly this family's "
                    "descriptors, in descriptor-array order",
                )

        for index, descriptor in enumerate(self.descriptors):
            base = "/descriptors/{0}".format(index)
            definition = descriptor.definition
            for position, observation in enumerate(descriptor.observations):
                if observation.value is None:
                    continue
                if (
                    descriptor.family in DIRECTIONAL_FAMILIES
                    and observation.value.kind != "NUMERIC"
                ):
                    _invariant(
                        "{0}/observations/{1}/value/kind".format(base, position),
                        "a directional family permits only numeric values",
                    )
                if observation.value.kind == "NUMERIC":
                    for name in ("unit_class", "unit_symbol"):
                        if getattr(definition, name) is None:
                            _invariant(
                                "{0}/definition/{1}".format(base, name),
                                "a numeric value requires a non-null " + name,
                            )
                else:
                    for name in ("unit_class", "unit_symbol"):
                        if getattr(definition, name) is not None:
                            _invariant(
                                "{0}/definition/{1}".format(base, name),
                                "a categorical value requires a null " + name,
                            )
            if descriptor.family == "COLLECTIVE_DEFORMATION_RESTRAINT_BURDEN":
                if definition.conditions_required is not True:
                    _invariant(
                        base + "/definition/conditions_required",
                        "the deformation/restraint family requires "
                        "conditions_required to be true",
                    )
                if (
                    definition.reference_state.kind
                    not in COLLECTIVE_DEFORMATION_REFERENCE_STATE_KINDS
                ):
                    _invariant(
                        base + "/definition/reference_state/kind",
                        "the deformation/restraint family restricts the "
                        "reference-state kind",
                    )

    # -- phase 6: derived conditions and reasons ---------------------------------------

    def _derived_phase(self):
        conditions = []
        reasons = []
        for index, descriptor in enumerate(self.descriptors):
            derived_conditions, derived_reasons = self._derive_descriptor(
                index, descriptor
            )
            conditions.append(derived_conditions)
            reasons.append(derived_reasons)
        object.__setattr__(self, "descriptor_conditions", tuple(conditions))
        object.__setattr__(self, "descriptor_reasons", tuple(reasons))

    def _shared_gaps(self, index, descriptor):
        """Declarations a provided observation requires that are null or unresolved."""
        base = "/descriptors/{0}".format(index)
        gaps = []
        ambiguous = []

        for name, suffix in _DESCRIPTOR_REQUIRED:
            if getattr(descriptor, name) is None:
                gaps.append(base + suffix)
        definition = descriptor.definition
        for name, suffix in _DEFINITION_REQUIRED:
            if getattr(definition, name) is None:
                gaps.append(base + suffix)
        for name, suffix in _METHOD_REQUIRED:
            if getattr(definition.method, name) is None:
                gaps.append(base + suffix)
        if definition.conditions_required and definition.conditions_profile.state != "SUPPLIED":
            gaps.append(base + "/definition/conditions_profile")
        reference_kind = definition.reference_state.kind
        if reference_kind == "UNAVAILABLE" or (
            reference_kind == "NOT_APPLICABLE"
            and descriptor.family != "COLLECTIVE_ANCHOR_LINKER_CONFIGURATION"
        ):
            gaps.append(base + "/definition/reference_state")

        for subject in definition.subject_ids:
            collection, position = self._subject_index[subject]
            item = getattr(self.scope, collection)[position]
            prefix = "/scope/{0}/{1}".format(collection, position)
            for name in ("identity_reference", "construct_id", "construct_version"):
                if getattr(item, name) is None:
                    gaps.append(prefix + "/" + name)
            if item.mapping_state == "AMBIGUOUS":
                ambiguous.append(prefix + "/mapping_state")
            elif item.mapping_state != "SUPPLIED":
                gaps.append(prefix + "/mapping_state")
            else:
                alternative = item.mapping_alternatives[0]
                if alternative.pose_id is None:
                    gaps.append(prefix + "/mapping_alternatives/0/pose_id")
                if len(alternative.chain_instances) == 0:
                    gaps.append(prefix + "/mapping_alternatives/0/chain_instances")
                for offset, instance in enumerate(alternative.chain_instances):
                    for name in ("identifier_namespace", "chain_id"):
                        if getattr(instance, name) is None:
                            gaps.append(
                                "{0}/mapping_alternatives/0/chain_instances/{1}/{2}".format(
                                    prefix, offset, name
                                )
                            )
                    if instance.residue_addressing_reference is None:
                        gaps.append(
                            "{0}/mapping_alternatives/0/chain_instances/{1}"
                            "/residue_addressing_reference".format(prefix, offset)
                        )

        # The collective joint frame, participants, anchors/linkers and connections
        # supply the relevant scope declarations; local associations never substitute.
        for name in _COLLECTIVE_SCOPE_REQUIRED:
            value = getattr(self.scope, name)
            if value is None or (name != "joint_frame" and len(value) == 0):
                gaps.append("/scope/" + name)
        if self.scope.joint_frame is not None and not self.scope.joint_frame.pose_ids:
            gaps.append("/scope/joint_frame/pose_ids")

        # A local-association role disagreement is an unresolved scope declaration:
        # it is retained verbatim, blocks provided-content qualification, and never
        # triggers role inference.
        for position, association in enumerate(self.scope.local_associations):
            prefix = "/scope/local_associations/{0}".format(position)
            for name, role in (
                ("binder_participant_id", "BINDER"),
                ("target_participant_id", "RECEPTOR"),
            ):
                value = getattr(association, name)
                if value is None:
                    continue
                declared = self.scope.participants[self._participant_index[value]]
                if declared.role != role:
                    gaps.append(prefix + "/" + name)

        # An L2MissingDeclaration applies to the record scope that stores it; its
        # pointer is carried verbatim as a diagnostic locator and never dereferenced.
        for record in self.missing_declarations:
            gaps.append(record.field)
        for record in self.scope.missing_declarations:
            gaps.append(record.field)
        for record in descriptor.missing_declarations:
            gaps.append(record.field)

        return gaps, ambiguous

    def _derive_descriptor(self, index, descriptor):
        base = "/descriptors/{0}".format(index)
        shared_gaps, ambiguous_paths = self._shared_gaps(index, descriptor)
        mapping_ambiguous = bool(ambiguous_paths)

        ambiguity_records = []
        ambiguity_observations = []
        descriptor_wide_ambiguity = False
        for position, ambiguity in enumerate(descriptor.ambiguities):
            ambiguous_paths.append("{0}/ambiguities/{1}".format(base, position))
            ambiguity_records.append(ambiguity.ambiguity_id)
            if len(ambiguity.observation_ids) == 0:
                descriptor_wide_ambiguity = True
            ambiguity_observations.extend(ambiguity.observation_ids)
        named_ambiguous = set(ambiguity_observations)

        value_paths = []
        value_observations = []
        missing_paths = list(shared_gaps)
        missing_observations = []
        qualifying = []
        any_value = False

        for position, observation in enumerate(descriptor.observations):
            prefix = "{0}/observations/{1}".format(base, position)
            own = []
            if observation.value is None:
                value_paths.append(prefix + "/value")
                value_observations.append(observation.observation_id)
            else:
                any_value = True
            if observation.pose_id is None:
                own.append(prefix + "/pose_id")
            if observation.source_reference is None:
                own.append(prefix + "/source_reference")
            for record in observation.missing_declarations:
                own.append(record.field)
            if observation.pose_id is not None:
                pose_position = self._pose_index[observation.pose_id]
                pose = self.poses[pose_position]
                pose_prefix = "/poses/{0}".format(pose_position)
                for name in _POSE_REQUIRED:
                    if getattr(pose, name) is None:
                        own.append(pose_prefix + "/" + name)

            blocked_by_ambiguity = (
                descriptor_wide_ambiguity
                or mapping_ambiguous
                or observation.observation_id in named_ambiguous
            )
            if own:
                missing_paths.extend(own)
                missing_observations.append(observation.observation_id)
            if (
                observation.value is not None
                and not own
                and not shared_gaps
                and not blocked_by_ambiguity
            ):
                qualifying.append(observation.observation_id)

        reasons = []

        if value_paths or not any_value:
            paths = value_paths if value_paths else [base + "/observations"]
            reasons.append(
                L2DescriptorReason(
                    code="EVIDENCE_NOT_SUPPLIED",
                    field_paths=tuple(sorted(_unique(paths))),
                    observation_ids=tuple(
                        self._in_observation_order(descriptor, value_observations)
                    ),
                    record_ids=(),
                )
            )

        if missing_paths:
            reasons.append(
                L2DescriptorReason(
                    code="DECLARATION_MISSING",
                    field_paths=tuple(sorted(_unique(missing_paths))),
                    observation_ids=tuple(
                        self._in_observation_order(descriptor, missing_observations)
                    ),
                    record_ids=(),
                )
            )

        if ambiguous_paths:
            reasons.append(
                L2DescriptorReason(
                    code="DECLARATION_AMBIGUOUS",
                    field_paths=tuple(sorted(_unique(ambiguous_paths))),
                    observation_ids=tuple(
                        self._in_observation_order(descriptor, ambiguity_observations)
                    ),
                    record_ids=tuple(_unique(ambiguity_records)),
                )
            )

        conflict_paths = []
        conflict_records = []
        conflict_observations = []
        for position, conflict in enumerate(descriptor.conflicts):
            supported = [
                identifier
                for identifier in conflict.observation_ids
                if identifier in qualifying
            ]
            if len(supported) < 2:
                _invariant(
                    "{0}/conflicts/{1}/observation_ids".format(base, position),
                    "a conflict must name at least two qualifying observations",
                )
            conflict_paths.append("{0}/conflicts/{1}".format(base, position))
            conflict_records.append(conflict.conflict_id)
            conflict_observations.extend(conflict.observation_ids)
        if conflict_paths:
            reasons.append(
                L2DescriptorReason(
                    code="OBSERVATIONS_CONFLICT",
                    field_paths=tuple(sorted(_unique(conflict_paths))),
                    observation_ids=tuple(
                        self._in_observation_order(descriptor, conflict_observations)
                    ),
                    record_ids=tuple(_unique(conflict_records)),
                )
            )

        reasons.sort(key=lambda item: L2_REASON_CODES.index(item.code))

        conditions = ["PROVIDED" if qualifying else "UNAVAILABLE"]
        if ambiguous_paths:
            conditions.append("AMBIGUOUS")
        if descriptor.conflicts:
            conditions.append("CONTRADICTORY")
        conditions.sort(key=L2_CONDITIONS.index)
        return tuple(conditions), tuple(reasons)

    @staticmethod
    def _in_observation_order(descriptor, identifiers):
        order = {
            observation.observation_id: position
            for position, observation in enumerate(descriptor.observations)
        }
        unique = _unique(identifiers)
        unique.sort(key=lambda item: order[item])
        return unique

    # -- serialization -----------------------------------------------------------------

    def as_dict(self):
        """A fresh detached structure on every call, in canonical emission order."""
        descriptors = []
        for index, descriptor in enumerate(self.descriptors):
            payload = descriptor.as_dict()
            payload["conditions"] = list(self.descriptor_conditions[index])
            payload["reasons"] = [
                reason.as_dict() for reason in self.descriptor_reasons[index]
            ]
            descriptors.append(payload)
        return {
            "document_type": self.document_type,
            "document_id": self.document_id,
            "revision": self.revision,
            "declared_by": self.declared_by,
            "declared_at": self.declared_at,
            "source_references": [item.as_dict() for item in self.source_references],
            "candidate_anchor": self.candidate_anchor.as_dict(),
            "scope": self.scope.as_dict(),
            "poses": [item.as_dict() for item in self.poses],
            "family_availability": [
                item.as_dict() for item in self.family_availability
            ],
            "descriptors": descriptors,
            "missing_declarations": [
                item.as_dict() for item in self.missing_declarations
            ],
            "non_claim": self.non_claim,
        }

    def to_json_bytes(self):
        return _canonical_bytes(self.as_dict())

    # -- loading --------------------------------------------------------------------------

    @classmethod
    def from_dict(cls, mapping):
        _keys(mapping, _TOP_LEVEL_KEYS, "")
        if mapping["document_type"] != LAYER_2B_DOCUMENT_TYPE:
            _structural("/document_type", "the document type constant was modified")
        if mapping["non_claim"] != LAYER_2B_NON_CLAIM:
            _structural("/non_claim", "the non-claim constant was modified")

        descriptors_raw = _array(mapping["descriptors"], "/descriptors")
        document = _at(
            "",
            cls,
            document_id=mapping["document_id"],
            revision=mapping["revision"],
            declared_by=mapping["declared_by"],
            declared_at=mapping["declared_at"],
            source_references=_build_sources(
                mapping["source_references"], "/source_references"
            ),
            candidate_anchor=_build_candidate_anchor(
                mapping["candidate_anchor"], "/candidate_anchor"
            ),
            scope=_build_collective_scope(mapping["scope"], "/scope"),
            poses=tuple(
                _build_pose(item, "/poses/{0}".format(position))
                for position, item in enumerate(_array(mapping["poses"], "/poses"))
            ),
            family_availability=tuple(
                _build_availability(item, "/family_availability/{0}".format(position))
                for position, item in enumerate(
                    _array(mapping["family_availability"], "/family_availability")
                )
            ),
            descriptors=tuple(
                _build_descriptor(item, "/descriptors/{0}".format(position))
                for position, item in enumerate(descriptors_raw)
            ),
            missing_declarations=_build_missing(
                mapping["missing_declarations"], "/missing_declarations"
            ),
        )

        for index, raw in enumerate(descriptors_raw):
            base = "/descriptors/{0}".format(index)
            supplied_conditions = tuple(_array(raw["conditions"], base + "/conditions"))
            if supplied_conditions != document.descriptor_conditions[index]:
                _invariant(
                    base + "/conditions",
                    "serialized conditions differ from the derived conditions",
                )
            supplied_reasons = tuple(
                _build_reason(item, "{0}/reasons/{1}".format(base, position))
                for position, item in enumerate(_array(raw["reasons"], base + "/reasons"))
            )
            if supplied_reasons != document.descriptor_reasons[index]:
                _invariant(
                    base + "/reasons",
                    "serialized reasons differ from the derived reasons",
                )
        return document

    @classmethod
    def from_json_bytes(cls, data):
        if not isinstance(data, (bytes, bytearray)):
            _structural("", "canonical input must be bytes")
        data = bytes(data)
        if data.startswith(b"\xef\xbb\xbf"):
            _fail("NON_CANONICAL_BYTES", "", "canonical bytes carry no byte order mark")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            _structural("", "canonical bytes must decode as UTF-8")
        try:
            decoded = json.loads(
                text,
                object_pairs_hook=_object_pairs,
                parse_float=_reject_number,
                parse_int=_reject_number,
                parse_constant=_reject_number,
            )
        except Layer2DescriptorInputError:
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


# ================================================================================
# Decoded-document builders
# ================================================================================


def _keys(value, expected, path):
    if not isinstance(value, dict):
        _structural(path, "value must be a JSON object")
    supplied = set(value)
    allowed = set(expected)
    unknown = sorted(supplied - allowed)
    if unknown:
        _structural("{0}/{1}".format(path, unknown[0]), "unknown field: " + unknown[0])
    missing = sorted(allowed - supplied)
    if missing:
        _structural("{0}/{1}".format(path, missing[0]), "missing field: " + missing[0])
    return value


def _array(value, path):
    if not isinstance(value, list):
        _structural(path, "value must be a JSON array")
    return value


def _build_reference(raw, path):
    if raw is None:
        return None
    _keys(raw, ("namespace", "identifier", "revision", "snapshot_reference"), path)
    return _at(
        path,
        L2ImmutableReference,
        namespace=raw["namespace"],
        identifier=raw["identifier"],
        revision=raw["revision"],
        snapshot_reference=raw["snapshot_reference"],
    )


def _build_source(raw, path):
    if raw is None:
        return None
    _keys(raw, ("reference", "locator"), path)
    return _at(
        path,
        L2SourceRecord,
        reference=_build_reference(raw["reference"], path + "/reference"),
        locator=raw["locator"],
    )


def _build_sources(raw, path):
    return tuple(
        _build_source(item, "{0}/{1}".format(path, position))
        for position, item in enumerate(_array(raw, path))
    )


def _build_anchor(raw, path):
    if raw is None:
        _structural(path, "an artifact anchor is required")
    _keys(raw, ("kind", "algorithm", "digest", "snapshot_reference"), path)
    return _at(
        path,
        L2ArtifactAnchor,
        kind=raw["kind"],
        algorithm=raw["algorithm"],
        digest=raw["digest"],
        snapshot_reference=_build_reference(
            raw["snapshot_reference"], path + "/snapshot_reference"
        ),
    )


def _build_association(raw, path):
    if raw is None:
        return None
    _keys(raw, ("association_id", "revision", "reference"), path)
    return _at(
        path,
        L2AssociationReference,
        association_id=raw["association_id"],
        revision=raw["revision"],
        reference=_build_reference(raw["reference"], path + "/reference"),
    )


def _build_admission(raw, path):
    if raw is None:
        return None
    _keys(
        raw,
        (
            "candidate_id",
            "slot_binding_hash",
            "state_result_id",
            "ineligibility_reason",
            "certificate_present",
            "absent_keys",
        ),
        path,
    )
    return _at(
        path,
        L2AdmissionReference,
        candidate_id=raw["candidate_id"],
        slot_binding_hash=raw["slot_binding_hash"],
        state_result_id=raw["state_result_id"],
        ineligibility_reason=raw["ineligibility_reason"],
        certificate_present=raw["certificate_present"],
        absent_keys=tuple(_array(raw["absent_keys"], path + "/absent_keys")),
    )


def _build_candidate_anchor(raw, path):
    _keys(
        raw,
        (
            "candidate_id",
            "scenario_id",
            "evaluation_run_ref",
            "batch_report_reference",
            "priority_report_reference",
            "scenario_comparison_reference",
            "admission_reference",
        ),
        path,
    )
    return _at(
        path,
        L2CandidateAnchor,
        candidate_id=raw["candidate_id"],
        scenario_id=raw["scenario_id"],
        evaluation_run_ref=raw["evaluation_run_ref"],
        batch_report_reference=_build_source(
            raw["batch_report_reference"], path + "/batch_report_reference"
        ),
        priority_report_reference=_build_source(
            raw["priority_report_reference"], path + "/priority_report_reference"
        ),
        scenario_comparison_reference=_build_source(
            raw["scenario_comparison_reference"],
            path + "/scenario_comparison_reference",
        ),
        admission_reference=_build_admission(
            raw["admission_reference"], path + "/admission_reference"
        ),
    )


def _build_pose(raw, path):
    _keys(
        raw,
        (
            "pose_id",
            "artifact_anchor",
            "locator",
            "model_id",
            "conformer_id",
            "frame_id",
            "association_reference",
            "source_reference",
            "run_reference",
            "method_reference",
        ),
        path,
    )
    return _at(
        path,
        L2PoseRecord,
        pose_id=raw["pose_id"],
        artifact_anchor=_build_anchor(raw["artifact_anchor"], path + "/artifact_anchor"),
        locator=raw["locator"],
        model_id=raw["model_id"],
        conformer_id=raw["conformer_id"],
        frame_id=raw["frame_id"],
        association_reference=_build_association(
            raw["association_reference"], path + "/association_reference"
        ),
        source_reference=_build_source(
            raw["source_reference"], path + "/source_reference"
        ),
        run_reference=_build_reference(raw["run_reference"], path + "/run_reference"),
        method_reference=_build_reference(
            raw["method_reference"], path + "/method_reference"
        ),
    )


def _build_chain_instance(raw, path):
    _keys(
        raw,
        (
            "identifier_namespace",
            "chain_id",
            "instance_id",
            "residue_addressing_reference",
            "selection_declaration",
        ),
        path,
    )
    return _at(
        path,
        L2ChainInstance,
        identifier_namespace=raw["identifier_namespace"],
        chain_id=raw["chain_id"],
        instance_id=raw["instance_id"],
        residue_addressing_reference=_build_source(
            raw["residue_addressing_reference"], path + "/residue_addressing_reference"
        ),
        selection_declaration=raw["selection_declaration"],
    )


def _build_mapping_alternative(raw, path):
    _keys(raw, ("pose_id", "chain_instances", "source_reference"), path)
    return _at(
        path,
        L2MappingAlternative,
        pose_id=raw["pose_id"],
        chain_instances=tuple(
            _build_chain_instance(item, "{0}/chain_instances/{1}".format(path, position))
            for position, item in enumerate(
                _array(raw["chain_instances"], path + "/chain_instances")
            )
        ),
        source_reference=_build_source(
            raw["source_reference"], path + "/source_reference"
        ),
    )


def _build_participant(raw, path):
    _keys(
        raw,
        (
            "participant_id",
            "role",
            "identity_reference",
            "construct_id",
            "construct_version",
            "mapping_state",
            "mapping_alternatives",
        ),
        path,
    )
    return _at(
        path,
        L2MolecularParticipant,
        participant_id=raw["participant_id"],
        role=raw["role"],
        identity_reference=_build_reference(
            raw["identity_reference"], path + "/identity_reference"
        ),
        construct_id=raw["construct_id"],
        construct_version=raw["construct_version"],
        mapping_state=raw["mapping_state"],
        mapping_alternatives=tuple(
            _build_mapping_alternative(
                item, "{0}/mapping_alternatives/{1}".format(path, position)
            )
            for position, item in enumerate(
                _array(raw["mapping_alternatives"], path + "/mapping_alternatives")
            )
        ),
    )


def _build_context(raw, path):
    _keys(
        raw,
        (
            "context_id",
            "subject_declaration",
            "treatment",
            "declaration",
            "source_reference",
        ),
        path,
    )
    return _at(
        path,
        L2ContextDeclaration,
        context_id=raw["context_id"],
        subject_declaration=raw["subject_declaration"],
        treatment=raw["treatment"],
        declaration=raw["declaration"],
        source_reference=_build_source(
            raw["source_reference"], path + "/source_reference"
        ),
    )


def _build_missing(raw, path):
    built = []
    for position, item in enumerate(_array(raw, path)):
        item_path = "{0}/{1}".format(path, position)
        _keys(item, ("field", "reason"), item_path)
        built.append(
            _at(item_path, L2MissingDeclaration, field=item["field"], reason=item["reason"])
        )
    return tuple(built)


def _build_profile(raw, path):
    _keys(raw, ("state", "reference", "reason"), path)
    return _at(
        path,
        L2ConditionsProfileReference,
        state=raw["state"],
        reference=_build_reference(raw["reference"], path + "/reference"),
        reason=raw["reason"],
    )


def _build_method(raw, path):
    _keys(raw, ("reference", "parameters", "representation", "run_reference"), path)
    parameters = []
    for position, item in enumerate(_array(raw["parameters"], path + "/parameters")):
        item_path = "{0}/parameters/{1}".format(path, position)
        _keys(item, ("name", "value"), item_path)
        parameters.append(
            _at(item_path, L2NamedDeclaration, name=item["name"], value=item["value"])
        )
    return _at(
        path,
        L2MethodDeclaration,
        reference=_build_reference(raw["reference"], path + "/reference"),
        parameters=tuple(parameters),
        representation=raw["representation"],
        run_reference=_build_reference(raw["run_reference"], path + "/run_reference"),
    )


def _build_reference_state(raw, path):
    _keys(raw, ("kind", "references", "declaration"), path)
    return _at(
        path,
        L2ReferenceState,
        kind=raw["kind"],
        references=_build_sources(raw["references"], path + "/references"),
        declaration=raw["declaration"],
    )


def _build_definition(raw, path):
    _keys(
        raw,
        (
            "definition_reference",
            "observable_name",
            "subject_ids",
            "selection_declaration",
            "unit_class",
            "unit_symbol",
            "conditions_required",
            "method",
            "conditions_profile",
            "reference_state",
            "comparability_reference",
            "limitation",
        ),
        path,
    )
    return _at(
        path,
        L2ObservableDefinition,
        definition_reference=_build_reference(
            raw["definition_reference"], path + "/definition_reference"
        ),
        observable_name=raw["observable_name"],
        subject_ids=tuple(_array(raw["subject_ids"], path + "/subject_ids")),
        selection_declaration=raw["selection_declaration"],
        unit_class=raw["unit_class"],
        unit_symbol=raw["unit_symbol"],
        conditions_required=raw["conditions_required"],
        method=_build_method(raw["method"], path + "/method"),
        conditions_profile=_build_profile(
            raw["conditions_profile"], path + "/conditions_profile"
        ),
        reference_state=_build_reference_state(
            raw["reference_state"], path + "/reference_state"
        ),
        comparability_reference=_build_source(
            raw["comparability_reference"], path + "/comparability_reference"
        ),
        limitation=raw["limitation"],
    )


def _build_value(raw, path):
    if raw is None:
        return None
    _keys(raw, ("kind", "number", "category"), path)
    return _at(
        path,
        L2DescriptorValue,
        kind=raw["kind"],
        number=raw["number"],
        category=raw["category"],
    )


def _build_observation(raw, path):
    _keys(
        raw,
        (
            "observation_id",
            "pose_id",
            "sample_id",
            "replicate_id",
            "source_reference",
            "value",
            "missing_declarations",
        ),
        path,
    )
    return _at(
        path,
        L2DescriptorObservation,
        observation_id=raw["observation_id"],
        pose_id=raw["pose_id"],
        sample_id=raw["sample_id"],
        replicate_id=raw["replicate_id"],
        source_reference=_build_source(
            raw["source_reference"], path + "/source_reference"
        ),
        value=_build_value(raw["value"], path + "/value"),
        missing_declarations=_build_missing(
            raw["missing_declarations"], path + "/missing_declarations"
        ),
    )


def _build_uncertainty(raw, path):
    _keys(
        raw,
        (
            "uncertainty_id",
            "kind",
            "state",
            "observation_ids",
            "declaration",
            "source_references",
        ),
        path,
    )
    return _at(
        path,
        L2UncertaintyRecord,
        uncertainty_id=raw["uncertainty_id"],
        kind=raw["kind"],
        state=raw["state"],
        observation_ids=tuple(_array(raw["observation_ids"], path + "/observation_ids")),
        declaration=raw["declaration"],
        source_references=_build_sources(
            raw["source_references"], path + "/source_references"
        ),
    )


def _build_ambiguity(raw, path):
    _keys(
        raw,
        ("ambiguity_id", "field_paths", "observation_ids", "alternatives", "declaration"),
        path,
    )
    alternatives = []
    for position, item in enumerate(_array(raw["alternatives"], path + "/alternatives")):
        item_path = "{0}/alternatives/{1}".format(path, position)
        _keys(item, ("declaration", "source_references"), item_path)
        alternatives.append(
            _at(
                item_path,
                L2AmbiguityAlternative,
                declaration=item["declaration"],
                source_references=_build_sources(
                    item["source_references"], item_path + "/source_references"
                ),
            )
        )
    return _at(
        path,
        L2AmbiguityRecord,
        ambiguity_id=raw["ambiguity_id"],
        field_paths=tuple(_array(raw["field_paths"], path + "/field_paths")),
        observation_ids=tuple(_array(raw["observation_ids"], path + "/observation_ids")),
        alternatives=tuple(alternatives),
        declaration=raw["declaration"],
    )


def _build_conflict(raw, path):
    _keys(
        raw,
        (
            "conflict_id",
            "observation_ids",
            "comparability_reference",
            "declaration",
            "declared_by",
            "declared_at",
            "source_references",
        ),
        path,
    )
    return _at(
        path,
        L2ConflictRecord,
        conflict_id=raw["conflict_id"],
        observation_ids=tuple(_array(raw["observation_ids"], path + "/observation_ids")),
        comparability_reference=_build_source(
            raw["comparability_reference"], path + "/comparability_reference"
        ),
        declaration=raw["declaration"],
        declared_by=raw["declared_by"],
        declared_at=raw["declared_at"],
        source_references=_build_sources(
            raw["source_references"], path + "/source_references"
        ),
    )


def _build_descriptor(raw, path):
    _keys(
        raw,
        (
            "descriptor_id",
            "family",
            "scope_declaration",
            "definition",
            "observations",
            "uncertainties",
            "ambiguities",
            "conflicts",
            "missing_declarations",
            "conditions",
            "reasons",
        ),
        path,
    )
    return _at(
        path,
        L2DescriptorRecord,
        descriptor_id=raw["descriptor_id"],
        family=raw["family"],
        scope_declaration=raw["scope_declaration"],
        definition=_build_definition(raw["definition"], path + "/definition"),
        observations=tuple(
            _build_observation(item, "{0}/observations/{1}".format(path, position))
            for position, item in enumerate(
                _array(raw["observations"], path + "/observations")
            )
        ),
        uncertainties=tuple(
            _build_uncertainty(item, "{0}/uncertainties/{1}".format(path, position))
            for position, item in enumerate(
                _array(raw["uncertainties"], path + "/uncertainties")
            )
        ),
        ambiguities=tuple(
            _build_ambiguity(item, "{0}/ambiguities/{1}".format(path, position))
            for position, item in enumerate(
                _array(raw["ambiguities"], path + "/ambiguities")
            )
        ),
        conflicts=tuple(
            _build_conflict(item, "{0}/conflicts/{1}".format(path, position))
            for position, item in enumerate(_array(raw["conflicts"], path + "/conflicts"))
        ),
        missing_declarations=_build_missing(
            raw["missing_declarations"], path + "/missing_declarations"
        ),
    )


def _build_availability(raw, path):
    _keys(raw, ("family", "descriptor_ids", "absence_reason"), path)
    return _at(
        path,
        L2FamilyAvailability,
        family=raw["family"],
        descriptor_ids=tuple(_array(raw["descriptor_ids"], path + "/descriptor_ids")),
        absence_reason=raw["absence_reason"],
    )


def _build_reason(raw, path):
    _keys(raw, ("code", "field_paths", "observation_ids", "record_ids"), path)
    return _at(
        path,
        L2DescriptorReason,
        code=raw["code"],
        field_paths=tuple(_array(raw["field_paths"], path + "/field_paths")),
        observation_ids=tuple(_array(raw["observation_ids"], path + "/observation_ids")),
        record_ids=tuple(_array(raw["record_ids"], path + "/record_ids")),
    )


def _build_local_document_reference(raw, path):
    if raw is None:
        return None
    _keys(raw, ("document_id", "revision", "reference"), path)
    return _at(
        path,
        L2LocalDocumentReference,
        document_id=raw["document_id"],
        revision=raw["revision"],
        reference=_build_reference(raw["reference"], path + "/reference"),
    )


def _build_joint_frame(raw, path):
    if raw is None:
        return None
    _keys(raw, ("frame_id", "frame_kind", "pose_ids", "declaration", "source_reference"), path)
    return _at(
        path,
        L2JointFrame,
        frame_id=raw["frame_id"],
        frame_kind=raw["frame_kind"],
        pose_ids=tuple(_array(raw["pose_ids"], path + "/pose_ids")),
        declaration=raw["declaration"],
        source_reference=_build_source(
            raw["source_reference"], path + "/source_reference"
        ),
    )


def _build_assembly_element(raw, path):
    _keys(
        raw,
        (
            "element_id",
            "kind",
            "identity_reference",
            "construct_id",
            "construct_version",
            "mapping_state",
            "mapping_alternatives",
            "representation_declaration",
        ),
        path,
    )
    return _at(
        path,
        L2AssemblyElement,
        element_id=raw["element_id"],
        kind=raw["kind"],
        identity_reference=_build_reference(
            raw["identity_reference"], path + "/identity_reference"
        ),
        construct_id=raw["construct_id"],
        construct_version=raw["construct_version"],
        mapping_state=raw["mapping_state"],
        mapping_alternatives=tuple(
            _build_mapping_alternative(
                item, "{0}/mapping_alternatives/{1}".format(path, position)
            )
            for position, item in enumerate(
                _array(raw["mapping_alternatives"], path + "/mapping_alternatives")
            )
        ),
        representation_declaration=raw["representation_declaration"],
    )


def _build_connection(raw, path):
    _keys(
        raw,
        (
            "connection_id",
            "first_subject_id",
            "first_site_declaration",
            "second_subject_id",
            "second_site_declaration",
            "connection_declaration",
            "source_reference",
        ),
        path,
    )
    return _at(
        path,
        L2Connection,
        connection_id=raw["connection_id"],
        first_subject_id=raw["first_subject_id"],
        first_site_declaration=raw["first_site_declaration"],
        second_subject_id=raw["second_subject_id"],
        second_site_declaration=raw["second_site_declaration"],
        connection_declaration=raw["connection_declaration"],
        source_reference=_build_source(
            raw["source_reference"], path + "/source_reference"
        ),
    )


def _build_local_association(raw, path):
    _keys(
        raw,
        (
            "slot_id",
            "binder_participant_id",
            "target_participant_id",
            "candidate_id",
            "scenario_id",
            "pose_association_reference",
            "local_document_reference",
            "missing_reason",
        ),
        path,
    )
    return _at(
        path,
        L2LocalAssociation,
        slot_id=raw["slot_id"],
        binder_participant_id=raw["binder_participant_id"],
        target_participant_id=raw["target_participant_id"],
        candidate_id=raw["candidate_id"],
        scenario_id=raw["scenario_id"],
        pose_association_reference=_build_association(
            raw["pose_association_reference"], path + "/pose_association_reference"
        ),
        local_document_reference=_build_local_document_reference(
            raw["local_document_reference"], path + "/local_document_reference"
        ),
        missing_reason=raw["missing_reason"],
    )


def _build_collective_scope(raw, path):
    _keys(
        raw,
        (
            "participants",
            "local_associations",
            "assembly_elements",
            "connections",
            "joint_frame",
            "target_site_declaration",
            "assembly_task_declaration",
            "context_declarations",
            "missing_declarations",
        ),
        path,
    )

    def collection(name, builder):
        return tuple(
            builder(item, "{0}/{1}/{2}".format(path, name, position))
            for position, item in enumerate(_array(raw[name], "{0}/{1}".format(path, name)))
        )

    return _at(
        path,
        L2CollectiveScope,
        participants=collection("participants", _build_participant),
        local_associations=collection("local_associations", _build_local_association),
        assembly_elements=collection("assembly_elements", _build_assembly_element),
        connections=collection("connections", _build_connection),
        joint_frame=_build_joint_frame(raw["joint_frame"], path + "/joint_frame"),
        target_site_declaration=raw["target_site_declaration"],
        assembly_task_declaration=raw["assembly_task_declaration"],
        context_declarations=collection("context_declarations", _build_context),
        missing_declarations=_build_missing(
            raw["missing_declarations"], path + "/missing_declarations"
        ),
    )
