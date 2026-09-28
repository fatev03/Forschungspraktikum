"""Caller-declared pose association document (contract ``caller_pose_association/1``).

Standard library only. This module holds one immutable document shape and nothing
else. It opens no file, resolves no locator, parses no artifact, computes and
recomputes no hash, inspects no coordinate, reads no clock or environment, calls no
provider, starts no subprocess and reaches no network. There is no loader that
discovers anything: every value reaches a record because a caller passed it, and the
only derived field is ``diagnostics``, which is a mechanical restatement of the
structural declarations already present in the document.

Every field name, vocabulary token, classification and text below is opaque
serialized data defined externally. This module neither assigns nor interprets
meaning for any of them. It checks shape, cardinality, spelling and internal
reference consistency, and it refuses what it cannot represent exactly.

WHAT THIS MODULE DOES NOT DO

  Nothing here infers, repairs, resolves, selects, merges, transforms or normalizes a
  caller value. Identifiers and texts are carried verbatim: never trimmed, case
  folded, Unicode normalized, sorted, parsed, dereferenced or compared for anything
  beyond exact equality where the contract calls for exact equality. Two references
  written in different forms are never treated as equivalent. A hash spelling that is
  not exactly the accepted spelling is refused rather than rewritten.

PUBLIC SURFACE

  The frozen record classes, the closed vocabularies, the fixed strings, and one
  exception type. The only operations are record construction, ``as_dict()``,
  ``to_json_bytes()``, and loading through ``CallerPoseAssociation.from_dict`` and
  ``CallerPoseAssociation.from_json_bytes``. There is no other public operation.

ERRORS

  ``CallerPoseAssociationError(ValueError)`` with ``.code`` drawn from ``ERROR_CODES``,
  ``.reason`` and an optional ``.field_path``. No partial document is ever issued.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json

# --------------------------------------------------------------------------------
# Fixed strings
# --------------------------------------------------------------------------------

#: Emitted verbatim in every serialized document; any other spelling is refused.
DOCUMENT_TYPE = "caller_pose_association/1"

#: Emitted verbatim in every serialized document; any other spelling is refused.
NON_CLAIM = (
    "This record preserves a caller-declared molecular-role and joint-pose "
    "association, not biological validation. A common coordinate file is not a "
    "verified bound complex. Roles and mappings are declared, not inferred. No "
    "binding, docking validity, biological identity, experimental relevance, "
    "residue contact, interface quality, affinity, thermodynamic, avidity, "
    "compatibility or ranking claim follows."
)

# --------------------------------------------------------------------------------
# Closed vocabularies. Unknown tokens are structurally refused.
# --------------------------------------------------------------------------------

ROLES = ("BINDER", "RECEPTOR", "LIGAND", "CONTEXT")
FRAME_KINDS = ("CALLER_DECLARED_ARTIFACT_MODEL_FRAME",)
INFORMATION_STATES = ("SUPPLIED", "ABSENT", "AMBIGUOUS")
CONDITIONS_PROFILE_STATES = ("SUPPLIED", "UNAVAILABLE")
ARTIFACT_ANCHOR_KINDS = ("CONTENT_HASH", "IMMUTABLE_SNAPSHOT")

#: Frozen diagnostic emission order. Index in this tuple is the sole ordering key.
DIAGNOSTIC_CODES = (
    "IMMUTABLE_ARTIFACT_REFERENCE_MISSING",
    "PARTICIPANT_ROLE_MISSING",
    "PARTICIPANT_CHAIN_MISSING",
    "DUPLICATE_PARTICIPANT_ROLE",
    "SHARED_FRAME_MISSING",
    "SHARED_FRAME_MISMATCH",
    "CHAIN_MAPPING_ABSENT",
    "CHAIN_MAPPING_AMBIGUOUS",
    "RESIDUE_ADDRESSING_ABSENT",
    "RESIDUE_ADDRESSING_AMBIGUOUS",
    "MODEL_RUN_METHOD_REFERENCE_ABSENT",
    "CONDITION_PROFILE_UNAVAILABLE",
    "ARTIFACT_ASSOCIATION_CONFLICT",
    "DECLARATION_MISSING",
    "DECLARATION_INCONSISTENT",
)

_DIAGNOSTIC_ORDER = {code: index for index, code in enumerate(DIAGNOSTIC_CODES)}

#: The one diagnostic code that is only ever a refusal and never an issued document.
REFUSAL_ONLY_DIAGNOSTIC_CODE = "IMMUTABLE_ARTIFACT_REFERENCE_MISSING"

#: Closed structural-error vocabulary carried by the single exception type.
ERROR_CODES = ("STRUCTURAL_INVALID", REFUSAL_ONLY_DIAGNOSTIC_CODE)

#: The only content-hash spelling this contract accepts; nothing else is normalized.
CONTENT_HASH_ALGORITHM = "sha256"
CONTENT_HASH_DIGEST_LENGTH = 64

_HEX_DIGITS = frozenset("0123456789abcdef")


# --------------------------------------------------------------------------------
# Single exception type
# --------------------------------------------------------------------------------


class CallerPoseAssociationError(ValueError):
    """The only error this module raises. ``code`` is closed to ``ERROR_CODES``."""

    __slots__ = ("code", "reason", "field_path")

    def __init__(self, reason, field_path=None, code="STRUCTURAL_INVALID"):
        if code not in ERROR_CODES:
            raise AssertionError("error code outside the closed vocabulary")
        location = field_path if field_path else "<document>"
        super().__init__("{0} at {1}: {2}".format(code, location, reason))
        self.code = code
        self.reason = reason
        self.field_path = field_path


def _raise(reason, field_path=None, code="STRUCTURAL_INVALID"):
    raise CallerPoseAssociationError(reason, field_path, code)


def _construct(path, factory, **kwargs):
    """Build a record, re-raising its relative field path under ``path``."""
    try:
        return factory(**kwargs)
    except CallerPoseAssociationError as err:
        raise CallerPoseAssociationError(
            err.reason, path + (err.field_path or ""), err.code
        ) from None


# --------------------------------------------------------------------------------
# Canonical primitives
# --------------------------------------------------------------------------------


def _is_control(character):
    point = ord(character)
    return point < 0x20 or 0x7F <= point <= 0x9F


def _identifier(value, path):
    """Non-empty Unicode, no control characters, no leading/trailing whitespace."""
    if not isinstance(value, str):
        _raise("identifier must be a string", path)
    if value == "":
        _raise("identifier must not be empty", path)
    for character in value:
        if _is_control(character):
            _raise("identifier must not contain control characters", path)
    if value != value.strip():
        _raise("identifier must not have leading or trailing whitespace", path)
    return value


def _optional_identifier(value, path):
    if value is None:
        return None
    return _identifier(value, path)


def _text(value, path):
    """Non-empty caller text, preserved literally."""
    if not isinstance(value, str):
        _raise("text must be a string", path)
    if value == "":
        _raise("text must not be empty; absence is expressed as null", path)
    return value


def _optional_text(value, path):
    if value is None:
        return None
    return _text(value, path)


def _token(value, allowed, path):
    if not isinstance(value, str):
        _raise("token must be a string", path)
    if value not in allowed:
        _raise("token outside the closed vocabulary", path)
    return value


def _pointer(value, path):
    if not isinstance(value, str):
        _raise("JSON Pointer must be a string", path)
    if value == "":
        _raise("JSON Pointer must name a field", path)
    if not value.startswith("/"):
        _raise("JSON Pointer must begin with '/'", path)
    for character in value:
        if _is_control(character):
            _raise("JSON Pointer must not contain control characters", path)
    return value


def _conflict_pointer(value, path):
    """A conflict field path: the empty root pointer, or '/'-led with ~0/~1 escapes."""
    if not isinstance(value, str):
        _raise("JSON Pointer must be a string", path)
    for character in value:
        if _is_control(character):
            _raise("JSON Pointer must not contain control characters", path)
    if value != "" and not value.startswith("/"):
        _raise("a non-empty JSON Pointer must begin with '/'", path)
    index = 0
    while index < len(value):
        if value[index] != "~":
            index += 1
            continue
        if index + 1 >= len(value) or value[index + 1] not in ("0", "1"):
            _raise(
                "'~' must occur only as the escape sequence ~0 or ~1", path
            )
        index += 2
    return value


_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_leap_year(year):
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _digits(value):
    for character in value:
        if character < "0" or character > "9":
            return False
    return bool(value)


def _timestamp(value, path):
    """Exactly ``YYYY-MM-DDTHH:mm:ssZ``, valid UTC calendar time, whole seconds."""
    if not isinstance(value, str):
        _raise("timestamp must be a string", path)
    if len(value) != 20:
        _raise("timestamp must be exactly YYYY-MM-DDTHH:mm:ssZ", path)
    if value[4] != "-" or value[7] != "-" or value[10] != "T":
        _raise("timestamp must be exactly YYYY-MM-DDTHH:mm:ssZ", path)
    if value[13] != ":" or value[16] != ":" or value[19] != "Z":
        _raise("timestamp must be exactly YYYY-MM-DDTHH:mm:ssZ", path)
    parts = (value[0:4], value[5:7], value[8:10], value[11:13], value[14:16], value[17:19])
    for part in parts:
        if not _digits(part):
            _raise("timestamp must be exactly YYYY-MM-DDTHH:mm:ssZ", path)
    year, month, day, hour, minute, second = (int(part) for part in parts)
    if month < 1 or month > 12:
        _raise("timestamp month is not a calendar month", path)
    limit = _DAYS_IN_MONTH[month - 1]
    if month == 2 and _is_leap_year(year):
        limit = 29
    if day < 1 or day > limit:
        _raise("timestamp day is not a calendar day of that month", path)
    if hour > 23:
        _raise("timestamp hour is out of range", path)
    if minute > 59:
        _raise("timestamp minute is out of range", path)
    if second > 59:
        _raise("timestamp second is out of range; whole seconds only", path)
    return value


def _sequence(value, path):
    if isinstance(value, (str, bytes, bytearray, dict)):
        _raise("value must be an array", path)
    if not isinstance(value, (list, tuple)):
        _raise("value must be an array", path)
    return tuple(value)


def _record(value, expected, path):
    if not isinstance(value, expected):
        _raise("value must be a {0} record".format(expected.__name__), path)
    return value


def _optional_record(value, expected, path):
    if value is None:
        return None
    return _record(value, expected, path)


def _elements(values, expected, path):
    for index, item in enumerate(values):
        _record(item, expected, "{0}/{1}".format(path, index))
    return values


# --------------------------------------------------------------------------------
# Reference primitives
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class ImmutableReference:
    """``namespace``, ``identifier``, ``revision``, ``snapshot_reference``."""

    namespace: str
    identifier: str
    revision: str | None
    snapshot_reference: str | None

    def __post_init__(self):
        _identifier(self.namespace, "/namespace")
        _identifier(self.identifier, "/identifier")
        _optional_identifier(self.revision, "/revision")
        _optional_identifier(self.snapshot_reference, "/snapshot_reference")
        if self.revision is None and self.snapshot_reference is None:
            _raise(
                "at least one of revision or snapshot_reference must be supplied",
                "/revision",
            )

    def as_dict(self):
        return {
            "namespace": self.namespace,
            "identifier": self.identifier,
            "revision": self.revision,
            "snapshot_reference": self.snapshot_reference,
        }


@dataclass(frozen=True)
class ArtifactAnchor:
    """``kind``, ``algorithm``, ``digest``, ``snapshot_reference``."""

    kind: str
    algorithm: str | None
    digest: str | None
    snapshot_reference: ImmutableReference | None

    def __post_init__(self):
        _token(self.kind, ARTIFACT_ANCHOR_KINDS, "/kind")
        if self.kind == "CONTENT_HASH":
            if self.snapshot_reference is not None:
                _raise(
                    "CONTENT_HASH anchor must not carry a snapshot_reference",
                    "/snapshot_reference",
                )
            if self.algorithm != CONTENT_HASH_ALGORITHM:
                _raise(
                    "CONTENT_HASH anchor accepts only the sha256 spelling",
                    "/algorithm",
                )
            if not isinstance(self.digest, str):
                _raise("CONTENT_HASH anchor requires a digest string", "/digest")
            if len(self.digest) != CONTENT_HASH_DIGEST_LENGTH:
                _raise(
                    "digest must be exactly 64 characters", "/digest"
                )
            for character in self.digest:
                if character not in _HEX_DIGITS:
                    _raise(
                        "digest must be lowercase hexadecimal; no spelling is "
                        "normalized",
                        "/digest",
                    )
        else:
            if self.algorithm is not None:
                _raise(
                    "IMMUTABLE_SNAPSHOT anchor must not carry an algorithm",
                    "/algorithm",
                )
            if self.digest is not None:
                _raise(
                    "IMMUTABLE_SNAPSHOT anchor must not carry a digest", "/digest"
                )
            if self.snapshot_reference is None:
                _raise(
                    "IMMUTABLE_SNAPSHOT anchor requires a snapshot_reference",
                    "/snapshot_reference",
                )
            _record(
                self.snapshot_reference, ImmutableReference, "/snapshot_reference"
            )

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
class ArtifactModelScope:
    """``artifact_anchor``, ``model_id``. Compared by declared fields only."""

    artifact_anchor: ArtifactAnchor
    model_id: str | None

    def __post_init__(self):
        _record(self.artifact_anchor, ArtifactAnchor, "/artifact_anchor")
        _optional_identifier(self.model_id, "/model_id")

    def as_dict(self):
        return {
            "artifact_anchor": self.artifact_anchor.as_dict(),
            "model_id": self.model_id,
        }


# --------------------------------------------------------------------------------
# Artifact and provenance
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Artifact:
    """``anchor``, ``locator``, ``selected_model``. The locator is never resolved."""

    anchor: ArtifactAnchor
    locator: str | None
    selected_model: str | None

    def __post_init__(self):
        if self.anchor is None:
            _raise(
                "artifact anchor is mandatory",
                "/anchor",
                REFUSAL_ONLY_DIAGNOSTIC_CODE,
            )
        _record(self.anchor, ArtifactAnchor, "/anchor")
        _optional_text(self.locator, "/locator")
        _optional_text(self.selected_model, "/selected_model")

    def as_dict(self):
        return {
            "anchor": self.anchor.as_dict(),
            "locator": self.locator,
            "selected_model": self.selected_model,
        }


@dataclass(frozen=True)
class Provenance:
    """``source_reference``, ``run_reference``, ``method_reference``."""

    source_reference: ImmutableReference | None
    run_reference: ImmutableReference | None
    method_reference: ImmutableReference | None

    def __post_init__(self):
        _optional_record(self.source_reference, ImmutableReference, "/source_reference")
        _optional_record(self.run_reference, ImmutableReference, "/run_reference")
        _optional_record(self.method_reference, ImmutableReference, "/method_reference")

    def as_dict(self):
        return {
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


# --------------------------------------------------------------------------------
# Subset declarations and chain primitives
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class SubsetDeclaration:
    """``declaration``, ``reference``. Subset text is never parsed or expanded."""

    declaration: str
    reference: ImmutableReference | None

    def __post_init__(self):
        _text(self.declaration, "/declaration")
        _optional_record(self.reference, ImmutableReference, "/reference")

    def as_dict(self):
        return {
            "declaration": self.declaration,
            "reference": None if self.reference is None else self.reference.as_dict(),
        }


@dataclass(frozen=True)
class ChainEntry:
    """``identifier_namespace``, ``chain_id``, ``instance_id``, ``residue_subset``."""

    identifier_namespace: str | None
    chain_id: str | None
    instance_id: str | None
    residue_subset: SubsetDeclaration | None

    def __post_init__(self):
        _optional_identifier(self.identifier_namespace, "/identifier_namespace")
        _optional_identifier(self.chain_id, "/chain_id")
        _optional_identifier(self.instance_id, "/instance_id")
        _optional_record(self.residue_subset, SubsetDeclaration, "/residue_subset")

    def as_dict(self):
        return {
            "identifier_namespace": self.identifier_namespace,
            "chain_id": self.chain_id,
            "instance_id": self.instance_id,
            "residue_subset": (
                None if self.residue_subset is None else self.residue_subset.as_dict()
            ),
        }


@dataclass(frozen=True)
class ChainInstance:
    """``identifier_namespace``, ``chain_id``, ``instance_id``."""

    identifier_namespace: str | None
    chain_id: str | None
    instance_id: str | None

    def __post_init__(self):
        _optional_identifier(self.identifier_namespace, "/identifier_namespace")
        _optional_identifier(self.chain_id, "/chain_id")
        _optional_identifier(self.instance_id, "/instance_id")

    def as_dict(self):
        return {
            "identifier_namespace": self.identifier_namespace,
            "chain_id": self.chain_id,
            "instance_id": self.instance_id,
        }


def _refuse_repeated(entries, path):
    seen = set()
    for index, entry in enumerate(entries):
        if entry in seen:
            _raise(
                "exact repeated chain/instance entry within one alternative",
                "{0}/{1}".format(path, index),
            )
        seen.add(entry)


# --------------------------------------------------------------------------------
# Mapping and addressing values
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainMappingValue:
    """``scope``, ``chains``."""

    scope: ArtifactModelScope
    chains: tuple

    def __post_init__(self):
        _record(self.scope, ArtifactModelScope, "/scope")
        chains = _sequence(self.chains, "/chains")
        _elements(chains, ChainEntry, "/chains")
        _refuse_repeated(chains, "/chains")
        object.__setattr__(self, "chains", chains)

    def as_dict(self):
        return {
            "scope": self.scope.as_dict(),
            "chains": [entry.as_dict() for entry in self.chains],
        }


@dataclass(frozen=True)
class ExternalMapping:
    """``reference``, ``direction``. The direction is never interpreted."""

    reference: ImmutableReference
    direction: str

    def __post_init__(self):
        if self.reference is None:
            _raise("external mapping requires a reference", "/reference")
        _record(self.reference, ImmutableReference, "/reference")
        _text(self.direction, "/direction")

    def as_dict(self):
        return {"reference": self.reference.as_dict(), "direction": self.direction}


@dataclass(frozen=True)
class ResidueAddressingValue:
    """``scope``, ``chain_instances``, four convention fields, subset and mapping."""

    scope: ArtifactModelScope
    chain_instances: tuple
    scheme: str | None
    namespace: str | None
    residue_identifier_convention: str | None
    insertion_code_convention: str | None
    residue_subset: SubsetDeclaration | None
    external_mapping: ExternalMapping | None

    def __post_init__(self):
        _record(self.scope, ArtifactModelScope, "/scope")
        instances = _sequence(self.chain_instances, "/chain_instances")
        _elements(instances, ChainInstance, "/chain_instances")
        _refuse_repeated(instances, "/chain_instances")
        object.__setattr__(self, "chain_instances", instances)
        _optional_text(self.scheme, "/scheme")
        _optional_text(self.namespace, "/namespace")
        _optional_text(
            self.residue_identifier_convention, "/residue_identifier_convention"
        )
        _optional_text(self.insertion_code_convention, "/insertion_code_convention")
        _optional_record(self.residue_subset, SubsetDeclaration, "/residue_subset")
        _optional_record(self.external_mapping, ExternalMapping, "/external_mapping")

    def as_dict(self):
        return {
            "scope": self.scope.as_dict(),
            "chain_instances": [item.as_dict() for item in self.chain_instances],
            "scheme": self.scheme,
            "namespace": self.namespace,
            "residue_identifier_convention": self.residue_identifier_convention,
            "insertion_code_convention": self.insertion_code_convention,
            "residue_subset": (
                None if self.residue_subset is None else self.residue_subset.as_dict()
            ),
            "external_mapping": (
                None if self.external_mapping is None else self.external_mapping.as_dict()
            ),
        }


#: The residue-addressing convention fields whose null means "not supplied".
RESIDUE_ADDRESSING_CONVENTION_FIELDS = (
    "scheme",
    "namespace",
    "residue_identifier_convention",
    "insertion_code_convention",
)


# --------------------------------------------------------------------------------
# Information records
# --------------------------------------------------------------------------------


def _check_state_cardinality(state, alternatives, path):
    if state == "SUPPLIED":
        if len(alternatives) != 1:
            _raise("SUPPLIED requires exactly one alternative", path + "/alternatives")
    elif state == "ABSENT":
        if len(alternatives) != 0:
            _raise("ABSENT requires no alternatives", path + "/alternatives")
    else:
        distinct = []
        for alternative in alternatives:
            if alternative.value not in distinct:
                distinct.append(alternative.value)
        if len(distinct) < 2:
            _raise(
                "AMBIGUOUS requires at least two distinct alternatives; repeated "
                "citations of one value do not establish ambiguity",
                path + "/alternatives",
            )


@dataclass(frozen=True)
class ChainMappingAlternative:
    """``value``, ``source_reference``."""

    value: ChainMappingValue
    source_reference: ImmutableReference | None

    def __post_init__(self):
        _record(self.value, ChainMappingValue, "/value")
        _optional_record(self.source_reference, ImmutableReference, "/source_reference")

    def as_dict(self):
        return {
            "value": self.value.as_dict(),
            "source_reference": (
                None if self.source_reference is None else self.source_reference.as_dict()
            ),
        }


@dataclass(frozen=True)
class ResidueAddressingAlternative:
    """``value``, ``source_reference``."""

    value: ResidueAddressingValue
    source_reference: ImmutableReference | None

    def __post_init__(self):
        _record(self.value, ResidueAddressingValue, "/value")
        _optional_record(self.source_reference, ImmutableReference, "/source_reference")

    def as_dict(self):
        return {
            "value": self.value.as_dict(),
            "source_reference": (
                None if self.source_reference is None else self.source_reference.as_dict()
            ),
        }


@dataclass(frozen=True)
class ChainMapping:
    """``state``, ``alternatives``."""

    state: str
    alternatives: tuple

    def __post_init__(self):
        _token(self.state, INFORMATION_STATES, "/state")
        alternatives = _sequence(self.alternatives, "/alternatives")
        _elements(alternatives, ChainMappingAlternative, "/alternatives")
        object.__setattr__(self, "alternatives", alternatives)
        _check_state_cardinality(self.state, alternatives, "")

    def as_dict(self):
        return {
            "state": self.state,
            "alternatives": [item.as_dict() for item in self.alternatives],
        }


@dataclass(frozen=True)
class ResidueAddressing:
    """``state``, ``alternatives``."""

    state: str
    alternatives: tuple

    def __post_init__(self):
        _token(self.state, INFORMATION_STATES, "/state")
        alternatives = _sequence(self.alternatives, "/alternatives")
        _elements(alternatives, ResidueAddressingAlternative, "/alternatives")
        object.__setattr__(self, "alternatives", alternatives)
        _check_state_cardinality(self.state, alternatives, "")

    def as_dict(self):
        return {
            "state": self.state,
            "alternatives": [item.as_dict() for item in self.alternatives],
        }


# --------------------------------------------------------------------------------
# Participants, pose pair, joint frame, conditions profile
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Participant:
    """One caller-ordered participant declaration."""

    participant_id: str
    role: str | None
    identity_reference: ImmutableReference | None
    construct_id: str | None
    construct_version: str | None
    chain_mapping: ChainMapping
    residue_addressing: ResidueAddressing

    def __post_init__(self):
        _identifier(self.participant_id, "/participant_id")
        if self.role is not None:
            _token(self.role, ROLES, "/role")
        _optional_record(
            self.identity_reference, ImmutableReference, "/identity_reference"
        )
        _optional_identifier(self.construct_id, "/construct_id")
        _optional_identifier(self.construct_version, "/construct_version")
        _record(self.chain_mapping, ChainMapping, "/chain_mapping")
        _record(self.residue_addressing, ResidueAddressing, "/residue_addressing")

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
            "chain_mapping": self.chain_mapping.as_dict(),
            "residue_addressing": self.residue_addressing.as_dict(),
        }


@dataclass(frozen=True)
class PosePair:
    """``binder_participant_id``, ``receptor_participant_id``."""

    binder_participant_id: str | None
    receptor_participant_id: str | None

    def __post_init__(self):
        _optional_identifier(self.binder_participant_id, "/binder_participant_id")
        _optional_identifier(self.receptor_participant_id, "/receptor_participant_id")

    def as_dict(self):
        return {
            "binder_participant_id": self.binder_participant_id,
            "receptor_participant_id": self.receptor_participant_id,
        }


@dataclass(frozen=True)
class JointFrame:
    """``frame_id``, ``frame_kind``, ``scope``."""

    frame_id: str
    frame_kind: str
    scope: ArtifactModelScope

    def __post_init__(self):
        _identifier(self.frame_id, "/frame_id")
        _token(self.frame_kind, FRAME_KINDS, "/frame_kind")
        _record(self.scope, ArtifactModelScope, "/scope")

    def as_dict(self):
        return {
            "frame_id": self.frame_id,
            "frame_kind": self.frame_kind,
            "scope": self.scope.as_dict(),
        }


@dataclass(frozen=True)
class ConditionsProfile:
    """``state``, ``reference``, ``reason``."""

    state: str
    reference: ImmutableReference | None
    reason: str | None

    def __post_init__(self):
        _token(self.state, CONDITIONS_PROFILE_STATES, "/state")
        _optional_record(self.reference, ImmutableReference, "/reference")
        _optional_text(self.reason, "/reason")
        if self.state == "SUPPLIED":
            if self.reference is None:
                _raise("SUPPLIED requires a reference", "/reference")
            if self.reason is not None:
                _raise("SUPPLIED requires reason to be null", "/reason")
        else:
            if self.reference is not None:
                _raise("UNAVAILABLE requires reference to be null", "/reference")
            if self.reason is None:
                _raise("UNAVAILABLE requires a reason", "/reason")

    def as_dict(self):
        return {
            "state": self.state,
            "reference": None if self.reference is None else self.reference.as_dict(),
            "reason": self.reason,
        }


# --------------------------------------------------------------------------------
# Association conflicts
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class AssociationReference:
    """``association_id``, ``revision``, ``document_reference``."""

    association_id: str
    revision: str
    document_reference: ImmutableReference

    def __post_init__(self):
        _identifier(self.association_id, "/association_id")
        _identifier(self.revision, "/revision")
        if self.document_reference is None:
            _raise("document_reference is mandatory", "/document_reference")
        _record(self.document_reference, ImmutableReference, "/document_reference")

    def as_dict(self):
        return {
            "association_id": self.association_id,
            "revision": self.revision,
            "document_reference": self.document_reference.as_dict(),
        }


@dataclass(frozen=True)
class AssociationConflict:
    """One caller-declared conflict. Nothing here derives a conflict."""

    conflict_id: str
    scope: ArtifactModelScope
    association_references: tuple
    field_paths: tuple
    statement: str
    declared_by: str
    declared_at: str
    source_references: tuple

    def __post_init__(self):
        _identifier(self.conflict_id, "/conflict_id")
        _record(self.scope, ArtifactModelScope, "/scope")

        references = _sequence(self.association_references, "/association_references")
        _elements(references, AssociationReference, "/association_references")
        if len(references) < 2:
            _raise(
                "association_references requires at least two distinct records",
                "/association_references",
            )
        distinct = []
        for reference in references:
            if reference not in distinct:
                distinct.append(reference)
        if len(distinct) < 2:
            _raise(
                "association_references requires at least two distinct records",
                "/association_references",
            )
        object.__setattr__(self, "association_references", references)

        paths = _sequence(self.field_paths, "/field_paths")
        if len(paths) == 0:
            _raise("field_paths must name at least one field", "/field_paths")
        for index, pointer in enumerate(paths):
            _conflict_pointer(pointer, "/field_paths/{0}".format(index))
        object.__setattr__(self, "field_paths", paths)

        _text(self.statement, "/statement")
        _identifier(self.declared_by, "/declared_by")
        _timestamp(self.declared_at, "/declared_at")

        sources = _sequence(self.source_references, "/source_references")
        _elements(sources, ImmutableReference, "/source_references")
        object.__setattr__(self, "source_references", sources)

    def as_dict(self):
        return {
            "conflict_id": self.conflict_id,
            "scope": self.scope.as_dict(),
            "association_references": [
                item.as_dict() for item in self.association_references
            ],
            "field_paths": list(self.field_paths),
            "statement": self.statement,
            "declared_by": self.declared_by,
            "declared_at": self.declared_at,
            "source_references": [item.as_dict() for item in self.source_references],
        }


# --------------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Diagnostic:
    """``code``, ``field_paths``, ``participant_ids``, ``conflict_ids``."""

    code: str
    field_paths: tuple
    participant_ids: tuple
    conflict_ids: tuple

    def __post_init__(self):
        _token(self.code, DIAGNOSTIC_CODES, "/code")
        paths = _sequence(self.field_paths, "/field_paths")
        if len(paths) == 0:
            _raise("field_paths must identify at least one location", "/field_paths")
        for index, pointer in enumerate(paths):
            _pointer(pointer, "/field_paths/{0}".format(index))
        object.__setattr__(self, "field_paths", paths)
        for name in ("participant_ids", "conflict_ids"):
            values = _sequence(getattr(self, name), "/" + name)
            for index, value in enumerate(values):
                _identifier(value, "/{0}/{1}".format(name, index))
            object.__setattr__(self, name, values)

    def as_dict(self):
        return {
            "code": self.code,
            "field_paths": list(self.field_paths),
            "participant_ids": list(self.participant_ids),
            "conflict_ids": list(self.conflict_ids),
        }


class _Accumulator:
    """Collects affected locations per diagnostic code. Holds no caller container."""

    def __init__(self):
        self._paths = {}
        self._participants = {}
        self._conflicts = {}

    def add(self, code, field_path, participant_id=None, conflict_id=None):
        self._paths.setdefault(code, []).append(field_path)
        if participant_id is not None:
            self._participants.setdefault(code, []).append(participant_id)
        if conflict_id is not None:
            self._conflicts.setdefault(code, []).append(conflict_id)

    def finalize(self, participant_order, conflict_order):
        diagnostics = []
        for code in DIAGNOSTIC_CODES:
            if code not in self._paths:
                continue
            paths = sorted(_unique(self._paths[code]))
            participants = _unique(self._participants.get(code, ()))
            participants.sort(key=participant_order.__getitem__)
            conflicts = _unique(self._conflicts.get(code, ()))
            conflicts.sort(key=conflict_order.__getitem__)
            diagnostics.append(
                Diagnostic(
                    code=code,
                    field_paths=tuple(paths),
                    participant_ids=tuple(participants),
                    conflict_ids=tuple(conflicts),
                )
            )
        diagnostics.sort(key=lambda item: _DIAGNOSTIC_ORDER[item.code])
        return tuple(diagnostics)


def _unique(values):
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _scope_fields(scope):
    return (scope.artifact_anchor, scope.model_id)


def _derive_diagnostics(document):
    """Mechanically restate the structural declarations already in the document."""
    accumulator = _Accumulator()
    participants = document.participants
    participant_order = {
        participant.participant_id: index
        for index, participant in enumerate(participants)
    }
    conflict_order = {
        conflict.conflict_id: index
        for index, conflict in enumerate(document.association_conflicts)
    }

    artifact = document.artifact
    provenance = document.provenance
    pose_pair = document.pose_pair
    joint_frame = document.joint_frame

    document_scope = (artifact.anchor, artifact.selected_model)
    if joint_frame is None:
        accumulator.add("SHARED_FRAME_MISSING", "/joint_frame")
        reference_scope = document_scope
    else:
        reference_scope = _scope_fields(joint_frame.scope)
        if reference_scope != document_scope:
            accumulator.add("SHARED_FRAME_MISMATCH", "/joint_frame/scope")

    declared_roles = []
    for index, participant in enumerate(participants):
        base = "/participants/{0}".format(index)
        identifier = participant.participant_id

        if participant.role is None:
            accumulator.add("PARTICIPANT_ROLE_MISSING", base + "/role", identifier)
        else:
            declared_roles.append((participant.role, index, identifier))

        if participant.identity_reference is None:
            accumulator.add(
                "DECLARATION_MISSING", base + "/identity_reference", identifier
            )
        if participant.construct_id is None:
            accumulator.add("DECLARATION_MISSING", base + "/construct_id", identifier)
        if participant.construct_version is None:
            accumulator.add(
                "DECLARATION_MISSING", base + "/construct_version", identifier
            )

        mapping = participant.chain_mapping
        if mapping.state == "ABSENT":
            accumulator.add("CHAIN_MAPPING_ABSENT", base + "/chain_mapping", identifier)
        elif mapping.state == "AMBIGUOUS":
            accumulator.add(
                "CHAIN_MAPPING_AMBIGUOUS", base + "/chain_mapping", identifier
            )
        for position, alternative in enumerate(mapping.alternatives):
            value = alternative.value
            value_base = "{0}/chain_mapping/alternatives/{1}/value".format(base, position)
            if _scope_fields(value.scope) != reference_scope:
                accumulator.add(
                    "SHARED_FRAME_MISMATCH", value_base + "/scope", identifier
                )
            chains_base = value_base + "/chains"
            if len(value.chains) == 0:
                accumulator.add("PARTICIPANT_CHAIN_MISSING", chains_base, identifier)
            for offset, entry in enumerate(value.chains):
                if entry.identifier_namespace is None:
                    accumulator.add(
                        "PARTICIPANT_CHAIN_MISSING",
                        "{0}/{1}/identifier_namespace".format(chains_base, offset),
                        identifier,
                    )
                if entry.chain_id is None:
                    accumulator.add(
                        "PARTICIPANT_CHAIN_MISSING",
                        "{0}/{1}/chain_id".format(chains_base, offset),
                        identifier,
                    )

        addressing = participant.residue_addressing
        if addressing.state == "ABSENT":
            accumulator.add(
                "RESIDUE_ADDRESSING_ABSENT", base + "/residue_addressing", identifier
            )
        elif addressing.state == "AMBIGUOUS":
            accumulator.add(
                "RESIDUE_ADDRESSING_AMBIGUOUS", base + "/residue_addressing", identifier
            )
        for position, alternative in enumerate(addressing.alternatives):
            value = alternative.value
            value_base = "{0}/residue_addressing/alternatives/{1}/value".format(
                base, position
            )
            if _scope_fields(value.scope) != reference_scope:
                accumulator.add(
                    "SHARED_FRAME_MISMATCH", value_base + "/scope", identifier
                )
            instances_base = value_base + "/chain_instances"
            if len(value.chain_instances) == 0:
                accumulator.add("PARTICIPANT_CHAIN_MISSING", instances_base, identifier)
            for offset, instance in enumerate(value.chain_instances):
                if instance.identifier_namespace is None:
                    accumulator.add(
                        "PARTICIPANT_CHAIN_MISSING",
                        "{0}/{1}/identifier_namespace".format(instances_base, offset),
                        identifier,
                    )
                if instance.chain_id is None:
                    accumulator.add(
                        "PARTICIPANT_CHAIN_MISSING",
                        "{0}/{1}/chain_id".format(instances_base, offset),
                        identifier,
                    )
            for name in RESIDUE_ADDRESSING_CONVENTION_FIELDS:
                if getattr(value, name) is None:
                    accumulator.add(
                        "RESIDUE_ADDRESSING_ABSENT",
                        "{0}/{1}".format(value_base, name),
                        identifier,
                    )

    counts = {}
    for role, _position, _member in declared_roles:
        counts[role] = counts.get(role, 0) + 1
    for role, position, member in declared_roles:
        if counts[role] > 1:
            accumulator.add(
                "DUPLICATE_PARTICIPANT_ROLE",
                "/participants/{0}/role".format(position),
                member,
            )
    for required in ("BINDER", "RECEPTOR"):
        if counts.get(required, 0) == 0:
            accumulator.add("PARTICIPANT_ROLE_MISSING", "/participants")

    if artifact.locator is None:
        accumulator.add("DECLARATION_MISSING", "/artifact/locator")
    if artifact.selected_model is None:
        accumulator.add(
            "MODEL_RUN_METHOD_REFERENCE_ABSENT", "/artifact/selected_model"
        )
    if provenance.source_reference is None:
        accumulator.add("DECLARATION_MISSING", "/provenance/source_reference")
    if provenance.run_reference is None:
        accumulator.add(
            "MODEL_RUN_METHOD_REFERENCE_ABSENT", "/provenance/run_reference"
        )
    if provenance.method_reference is None:
        accumulator.add(
            "MODEL_RUN_METHOD_REFERENCE_ABSENT", "/provenance/method_reference"
        )

    for name, required_role in (
        ("binder_participant_id", "BINDER"),
        ("receptor_participant_id", "RECEPTOR"),
    ):
        referenced = getattr(pose_pair, name)
        path = "/pose_pair/" + name
        if referenced is None:
            accumulator.add("DECLARATION_MISSING", path)
            continue
        participant = participants[participant_order[referenced]]
        if participant.role != required_role:
            accumulator.add("DECLARATION_INCONSISTENT", path, referenced)

    if document.conditions_profile.state == "UNAVAILABLE":
        accumulator.add("CONDITION_PROFILE_UNAVAILABLE", "/conditions_profile")

    for index, conflict in enumerate(document.association_conflicts):
        accumulator.add(
            "ARTIFACT_ASSOCIATION_CONFLICT",
            "/association_conflicts/{0}".format(index),
            conflict_id=conflict.conflict_id,
        )

    return accumulator.finalize(participant_order, conflict_order)


# --------------------------------------------------------------------------------
# Canonical bytes
# --------------------------------------------------------------------------------


def _canonical_bytes(value):
    """UTF-8, recursively key-sorted, compact, no trailing newline, no BOM."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _reject_number(_value):
    _raise("no numeric primitive occurs in this document shape")


def _object_pairs(pairs):
    seen = set()
    for key, _value in pairs:
        if key in seen:
            _raise("duplicate JSON object key: {0}".format(key))
        seen.add(key)
    return dict(pairs)


# --------------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------------

_TOP_LEVEL_KEYS = (
    "document_type",
    "association_id",
    "revision",
    "declared_by",
    "declared_at",
    "artifact",
    "provenance",
    "participants",
    "pose_pair",
    "joint_frame",
    "conditions_profile",
    "association_conflicts",
    "diagnostics",
    "non_claim",
)


@dataclass(frozen=True)
class CallerPoseAssociation:
    """One immutable ``caller_pose_association/1`` document."""

    association_id: str
    revision: str
    declared_by: str
    declared_at: str
    artifact: Artifact
    provenance: Provenance
    participants: tuple
    pose_pair: PosePair
    joint_frame: JointFrame | None
    conditions_profile: ConditionsProfile
    association_conflicts: tuple
    document_type: str = field(init=False, default=DOCUMENT_TYPE)
    non_claim: str = field(init=False, default=NON_CLAIM)
    diagnostics: tuple = field(init=False, default=())

    def __post_init__(self):
        _identifier(self.association_id, "/association_id")
        _identifier(self.revision, "/revision")
        _identifier(self.declared_by, "/declared_by")
        _timestamp(self.declared_at, "/declared_at")

        if self.artifact is None:
            _raise(
                "artifact anchor is mandatory",
                "/artifact/anchor",
                REFUSAL_ONLY_DIAGNOSTIC_CODE,
            )
        _record(self.artifact, Artifact, "/artifact")
        _record(self.provenance, Provenance, "/provenance")

        participants = _sequence(self.participants, "/participants")
        _elements(participants, Participant, "/participants")
        seen_participants = set()
        for index, participant in enumerate(participants):
            if participant.participant_id in seen_participants:
                _raise(
                    "duplicate participant_id",
                    "/participants/{0}/participant_id".format(index),
                )
            seen_participants.add(participant.participant_id)
        object.__setattr__(self, "participants", participants)

        _record(self.pose_pair, PosePair, "/pose_pair")
        for name in ("binder_participant_id", "receptor_participant_id"):
            referenced = getattr(self.pose_pair, name)
            if referenced is not None and referenced not in seen_participants:
                _raise(
                    "pose_pair references an absent participant",
                    "/pose_pair/" + name,
                )

        _optional_record(self.joint_frame, JointFrame, "/joint_frame")
        _record(self.conditions_profile, ConditionsProfile, "/conditions_profile")

        conflicts = _sequence(self.association_conflicts, "/association_conflicts")
        _elements(conflicts, AssociationConflict, "/association_conflicts")
        seen_conflicts = set()
        for index, conflict in enumerate(conflicts):
            if conflict.conflict_id in seen_conflicts:
                _raise(
                    "duplicate conflict_id",
                    "/association_conflicts/{0}/conflict_id".format(index),
                )
            seen_conflicts.add(conflict.conflict_id)
        object.__setattr__(self, "association_conflicts", conflicts)

        object.__setattr__(self, "diagnostics", _derive_diagnostics(self))

    # -- serialization ------------------------------------------------------------

    def as_dict(self):
        """A fresh nested structure on every call, in canonical emission order."""
        return {
            "document_type": self.document_type,
            "association_id": self.association_id,
            "revision": self.revision,
            "declared_by": self.declared_by,
            "declared_at": self.declared_at,
            "artifact": self.artifact.as_dict(),
            "provenance": self.provenance.as_dict(),
            "participants": [item.as_dict() for item in self.participants],
            "pose_pair": self.pose_pair.as_dict(),
            "joint_frame": (
                None if self.joint_frame is None else self.joint_frame.as_dict()
            ),
            "conditions_profile": self.conditions_profile.as_dict(),
            "association_conflicts": [
                item.as_dict() for item in self.association_conflicts
            ],
            "diagnostics": [item.as_dict() for item in self.diagnostics],
            "non_claim": self.non_claim,
        }

    def to_json_bytes(self):
        return _canonical_bytes(self.as_dict())

    # -- loading ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, mapping):
        """Rebuild from a decoded document, re-deriving and re-checking diagnostics."""
        _mapping_keys(mapping, _TOP_LEVEL_KEYS, "")

        if mapping["document_type"] != DOCUMENT_TYPE:
            _raise("document_type is fixed and was modified", "/document_type")
        if mapping["non_claim"] != NON_CLAIM:
            _raise("non_claim is fixed and was modified", "/non_claim")

        artifact_raw = mapping["artifact"]
        if artifact_raw is None:
            _raise(
                "artifact anchor is mandatory",
                "/artifact/anchor",
                REFUSAL_ONLY_DIAGNOSTIC_CODE,
            )

        document = _construct(
            "",
            cls,
            association_id=mapping["association_id"],
            revision=mapping["revision"],
            declared_by=mapping["declared_by"],
            declared_at=mapping["declared_at"],
            artifact=_build_artifact(artifact_raw, "/artifact"),
            provenance=_build_provenance(mapping["provenance"], "/provenance"),
            participants=_build_participants(mapping["participants"], "/participants"),
            pose_pair=_build_pose_pair(mapping["pose_pair"], "/pose_pair"),
            joint_frame=_build_joint_frame(mapping["joint_frame"], "/joint_frame"),
            conditions_profile=_build_conditions_profile(
                mapping["conditions_profile"], "/conditions_profile"
            ),
            association_conflicts=_build_conflicts(
                mapping["association_conflicts"], "/association_conflicts"
            ),
        )

        supplied = _build_diagnostics(mapping["diagnostics"], "/diagnostics")
        if supplied != document.diagnostics:
            _raise(
                "serialized diagnostics differ from the diagnostics derived from the "
                "structural declarations",
                "/diagnostics",
            )
        return document

    @classmethod
    def from_json_bytes(cls, data):
        """Load canonical bytes. Noncanonical bytes are refused, never rewritten."""
        if not isinstance(data, (bytes, bytearray)):
            _raise("canonical input must be bytes")
        data = bytes(data)
        if data.startswith(b"\xef\xbb\xbf"):
            _raise("canonical bytes carry no byte order mark")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            _raise("canonical bytes must decode as UTF-8")
        try:
            decoded = json.loads(
                text,
                object_pairs_hook=_object_pairs,
                parse_float=_reject_number,
                parse_int=_reject_number,
                parse_constant=_reject_number,
            )
        except CallerPoseAssociationError:
            raise
        except ValueError:
            _raise("canonical bytes must be a single JSON document")
        document = cls.from_dict(decoded)
        if document.to_json_bytes() != data:
            _raise("input is not the exact canonical serialization of this document")
        return document


# --------------------------------------------------------------------------------
# Decoded-document builders. Each checks its own key set at its own depth.
# --------------------------------------------------------------------------------


def _mapping_keys(value, expected, path):
    if not isinstance(value, dict):
        _raise("value must be a JSON object", path if path else None)
    supplied = set(value)
    allowed = set(expected)
    unknown = sorted(supplied - allowed)
    if unknown:
        _raise(
            "unknown field: {0}".format(unknown[0]),
            "{0}/{1}".format(path, unknown[0]),
        )
    missing = sorted(allowed - supplied)
    if missing:
        _raise(
            "missing field: {0}".format(missing[0]),
            "{0}/{1}".format(path, missing[0]),
        )
    return value


def _array(value, path):
    if not isinstance(value, list):
        _raise("value must be a JSON array", path)
    return value


def _build_reference(raw, path):
    if raw is None:
        return None
    _mapping_keys(raw, ("namespace", "identifier", "revision", "snapshot_reference"), path)
    return _construct(
        path,
        ImmutableReference,
        namespace=raw["namespace"],
        identifier=raw["identifier"],
        revision=raw["revision"],
        snapshot_reference=raw["snapshot_reference"],
    )


def _build_anchor(raw, path):
    if raw is None:
        _raise(
            "artifact anchor is mandatory", path, REFUSAL_ONLY_DIAGNOSTIC_CODE
        )
    _mapping_keys(raw, ("kind", "algorithm", "digest", "snapshot_reference"), path)
    return _construct(
        path,
        ArtifactAnchor,
        kind=raw["kind"],
        algorithm=raw["algorithm"],
        digest=raw["digest"],
        snapshot_reference=_build_reference(
            raw["snapshot_reference"], path + "/snapshot_reference"
        ),
    )


def _build_scope(raw, path):
    _mapping_keys(raw, ("artifact_anchor", "model_id"), path)
    return _construct(
        path,
        ArtifactModelScope,
        artifact_anchor=_build_anchor(raw["artifact_anchor"], path + "/artifact_anchor"),
        model_id=raw["model_id"],
    )


def _build_artifact(raw, path):
    _mapping_keys(raw, ("anchor", "locator", "selected_model"), path)
    return _construct(
        path,
        Artifact,
        anchor=_build_anchor(raw["anchor"], path + "/anchor"),
        locator=raw["locator"],
        selected_model=raw["selected_model"],
    )


def _build_provenance(raw, path):
    _mapping_keys(raw, ("source_reference", "run_reference", "method_reference"), path)
    return _construct(
        path,
        Provenance,
        source_reference=_build_reference(
            raw["source_reference"], path + "/source_reference"
        ),
        run_reference=_build_reference(raw["run_reference"], path + "/run_reference"),
        method_reference=_build_reference(
            raw["method_reference"], path + "/method_reference"
        ),
    )


def _build_subset(raw, path):
    if raw is None:
        return None
    _mapping_keys(raw, ("declaration", "reference"), path)
    return _construct(
        path,
        SubsetDeclaration,
        declaration=raw["declaration"],
        reference=_build_reference(raw["reference"], path + "/reference"),
    )


def _build_chain_entry(raw, path):
    _mapping_keys(
        raw, ("identifier_namespace", "chain_id", "instance_id", "residue_subset"), path
    )
    return _construct(
        path,
        ChainEntry,
        identifier_namespace=raw["identifier_namespace"],
        chain_id=raw["chain_id"],
        instance_id=raw["instance_id"],
        residue_subset=_build_subset(raw["residue_subset"], path + "/residue_subset"),
    )


def _build_chain_instance(raw, path):
    _mapping_keys(raw, ("identifier_namespace", "chain_id", "instance_id"), path)
    return _construct(
        path,
        ChainInstance,
        identifier_namespace=raw["identifier_namespace"],
        chain_id=raw["chain_id"],
        instance_id=raw["instance_id"],
    )


def _build_chain_mapping_value(raw, path):
    _mapping_keys(raw, ("scope", "chains"), path)
    chains = _array(raw["chains"], path + "/chains")
    return _construct(
        path,
        ChainMappingValue,
        scope=_build_scope(raw["scope"], path + "/scope"),
        chains=tuple(
            _build_chain_entry(item, "{0}/chains/{1}".format(path, index))
            for index, item in enumerate(chains)
        ),
    )


def _build_external_mapping(raw, path):
    if raw is None:
        return None
    _mapping_keys(raw, ("reference", "direction"), path)
    return _construct(
        path,
        ExternalMapping,
        reference=_build_reference(raw["reference"], path + "/reference"),
        direction=raw["direction"],
    )


def _build_residue_addressing_value(raw, path):
    _mapping_keys(
        raw,
        (
            "scope",
            "chain_instances",
            "scheme",
            "namespace",
            "residue_identifier_convention",
            "insertion_code_convention",
            "residue_subset",
            "external_mapping",
        ),
        path,
    )
    instances = _array(raw["chain_instances"], path + "/chain_instances")
    return _construct(
        path,
        ResidueAddressingValue,
        scope=_build_scope(raw["scope"], path + "/scope"),
        chain_instances=tuple(
            _build_chain_instance(item, "{0}/chain_instances/{1}".format(path, index))
            for index, item in enumerate(instances)
        ),
        scheme=raw["scheme"],
        namespace=raw["namespace"],
        residue_identifier_convention=raw["residue_identifier_convention"],
        insertion_code_convention=raw["insertion_code_convention"],
        residue_subset=_build_subset(raw["residue_subset"], path + "/residue_subset"),
        external_mapping=_build_external_mapping(
            raw["external_mapping"], path + "/external_mapping"
        ),
    )


def _build_information(raw, path, alternative_type, value_builder):
    _mapping_keys(raw, ("state", "alternatives"), path)
    alternatives = _array(raw["alternatives"], path + "/alternatives")
    built = []
    for index, item in enumerate(alternatives):
        item_path = "{0}/alternatives/{1}".format(path, index)
        _mapping_keys(item, ("value", "source_reference"), item_path)
        built.append(
            _construct(
                item_path,
                alternative_type,
                value=value_builder(item["value"], item_path + "/value"),
                source_reference=_build_reference(
                    item["source_reference"], item_path + "/source_reference"
                ),
            )
        )
    return raw["state"], tuple(built)


def _build_participant(raw, path):
    _mapping_keys(
        raw,
        (
            "participant_id",
            "role",
            "identity_reference",
            "construct_id",
            "construct_version",
            "chain_mapping",
            "residue_addressing",
        ),
        path,
    )
    mapping_state, mapping_alternatives = _build_information(
        raw["chain_mapping"],
        path + "/chain_mapping",
        ChainMappingAlternative,
        _build_chain_mapping_value,
    )
    addressing_state, addressing_alternatives = _build_information(
        raw["residue_addressing"],
        path + "/residue_addressing",
        ResidueAddressingAlternative,
        _build_residue_addressing_value,
    )
    return _construct(
        path,
        Participant,
        participant_id=raw["participant_id"],
        role=raw["role"],
        identity_reference=_build_reference(
            raw["identity_reference"], path + "/identity_reference"
        ),
        construct_id=raw["construct_id"],
        construct_version=raw["construct_version"],
        chain_mapping=_construct(
            path + "/chain_mapping",
            ChainMapping,
            state=mapping_state,
            alternatives=mapping_alternatives,
        ),
        residue_addressing=_construct(
            path + "/residue_addressing",
            ResidueAddressing,
            state=addressing_state,
            alternatives=addressing_alternatives,
        ),
    )


def _build_participants(raw, path):
    items = _array(raw, path)
    return tuple(
        _build_participant(item, "{0}/{1}".format(path, index))
        for index, item in enumerate(items)
    )


def _build_pose_pair(raw, path):
    _mapping_keys(raw, ("binder_participant_id", "receptor_participant_id"), path)
    return _construct(
        path,
        PosePair,
        binder_participant_id=raw["binder_participant_id"],
        receptor_participant_id=raw["receptor_participant_id"],
    )


def _build_joint_frame(raw, path):
    if raw is None:
        return None
    _mapping_keys(raw, ("frame_id", "frame_kind", "scope"), path)
    return _construct(
        path,
        JointFrame,
        frame_id=raw["frame_id"],
        frame_kind=raw["frame_kind"],
        scope=_build_scope(raw["scope"], path + "/scope"),
    )


def _build_conditions_profile(raw, path):
    _mapping_keys(raw, ("state", "reference", "reason"), path)
    return _construct(
        path,
        ConditionsProfile,
        state=raw["state"],
        reference=_build_reference(raw["reference"], path + "/reference"),
        reason=raw["reason"],
    )


def _build_association_reference(raw, path):
    _mapping_keys(raw, ("association_id", "revision", "document_reference"), path)
    return _construct(
        path,
        AssociationReference,
        association_id=raw["association_id"],
        revision=raw["revision"],
        document_reference=_build_reference(
            raw["document_reference"], path + "/document_reference"
        ),
    )


def _build_conflicts(raw, path):
    items = _array(raw, path)
    built = []
    for index, item in enumerate(items):
        item_path = "{0}/{1}".format(path, index)
        _mapping_keys(
            item,
            (
                "conflict_id",
                "scope",
                "association_references",
                "field_paths",
                "statement",
                "declared_by",
                "declared_at",
                "source_references",
            ),
            item_path,
        )
        references = _array(
            item["association_references"], item_path + "/association_references"
        )
        sources = _array(item["source_references"], item_path + "/source_references")
        built.append(
            _construct(
                item_path,
                AssociationConflict,
                conflict_id=item["conflict_id"],
                scope=_build_scope(item["scope"], item_path + "/scope"),
                association_references=tuple(
                    _build_association_reference(
                        entry,
                        "{0}/association_references/{1}".format(item_path, position),
                    )
                    for position, entry in enumerate(references)
                ),
                field_paths=tuple(_array(item["field_paths"], item_path + "/field_paths")),
                statement=item["statement"],
                declared_by=item["declared_by"],
                declared_at=item["declared_at"],
                source_references=tuple(
                    _build_reference(
                        entry, "{0}/source_references/{1}".format(item_path, position)
                    )
                    for position, entry in enumerate(sources)
                ),
            )
        )
    return tuple(built)


def _build_diagnostics(raw, path):
    items = _array(raw, path)
    built = []
    for index, item in enumerate(items):
        item_path = "{0}/{1}".format(path, index)
        _mapping_keys(
            item, ("code", "field_paths", "participant_ids", "conflict_ids"), item_path
        )
        built.append(
            _construct(
                item_path,
                Diagnostic,
                code=item["code"],
                field_paths=tuple(_array(item["field_paths"], item_path + "/field_paths")),
                participant_ids=tuple(
                    _array(item["participant_ids"], item_path + "/participant_ids")
                ),
                conflict_ids=tuple(
                    _array(item["conflict_ids"], item_path + "/conflict_ids")
                ),
            )
        )
    return tuple(built)
