"""Read-only publication of one verified alignment reader result (contracts
alignment_evidence_envelope/1 and alignment_handoff_record/1).

Standard library plus existing structure_audit helpers; no import-time I/O. This layer
reads one source artifact only through the public verifying reader
colabfold_a3m_lossless.parse_colabfold_a3m, in reader-only mode, and publishes what that
reader returned. It opens no source file itself, performs no arithmetic, and defines no
threshold, fallback, default, normalization, ordering of source content or inferred value.

WHAT IT PUBLISHES

    source artifact (declared by the caller)
      -> parse_colabfold_a3m        the reader verifies path, bytes, declared layout, content
        -> alignment_evidence_envelope/1   what the reader returned, or why it returned nothing
          -> alignment_handoff_record/1    which source-declared components a consumer may use

INPUTS
  publish_alignment_evidence(*, artifact, config)
      artifact and config are the reader's own request objects, passed to it unchanged. This
      layer requires only what the envelope itself records: artifact.artifact_id (nonempty
      text), artifact.sha256 (64 lowercase hex), the declared layout
      artifact.{format, source_kind, source_kind_status} and
      config.{profile_id, profile_version, profile_selection} (nonempty text each), and
      reader-only mode (metrics_enabled and binding_enabled absent or False, metric_policy
      absent or null). Every other judgement belongs to the reader. A request this layer
      cannot record raises CONTRACT_INVALID and the reader is not called.
  publish_alignment_handoff(*, envelope, expected_envelope_id, references)
      envelope is an AlignmentEvidenceEnvelope; expected_envelope_id must equal its
      envelope_id, otherwise IDENTITY_MISMATCH. references is a nonempty list of unique
      {component_kind, component_id}; component_kind is "record_occurrence" (an entry of the
      source's /occurrence_mapping) or "selected_occurrence" (the source's
      /query/selected_occurrence). Every declared reference is required.

ENVELOPE STATUS (the reader decides; this layer classifies the reader's closed code)
  AVAILABLE    the reader returned a result; source_fields carries it
  UNAVAILABLE  SOURCE_UNREADABLE          the reader could not read the artifact
  UNSUPPORTED  SOURCE_LAYOUT_UNSUPPORTED  declared layout or content outside the profile
  REJECTED     SOURCE_CONTENT_HASH_MISMATCH, SOURCE_MALFORMED, SOURCE_SELECTION_REJECTED,
               SOURCE_REQUEST_REJECTED, or READER_CODE_UNRECOGNIZED (fail closed)
  Without a result the reader's diagnostic code, locator and details are carried verbatim;
  its free-text message is not, because it can embed a filesystem path.

SOURCE FIELDS
  source_fields maps each JSON Pointer in CARRIED_FIELDS to the value at that pointer in the
  reader result's to_dict(), unchanged. The pointer set is fixed by this contract, never
  chosen by the caller. Not carried: /artifact/snapshot/path,
  /configuration/allowed_input_roots and /contract_hashes (location-bearing),
  /artifact/raw_bytes_base64 (the carried fragments hold the same bytes), and the metric and
  binding stage fields (disabled by construction). The envelope is location independent.

HANDOFF STATUS
  READY        envelope AVAILABLE and every reference resolves to a source-declared component
  BLOCKED      envelope AVAILABLE and at least one reference is absent (REQUIRED_REFERENCE_ABSENT)
  UNAVAILABLE, UNSUPPORTED, REJECTED
               the envelope status and reason carried unchanged; references NOT_EVALUATED
  A resolved reference copies the source's own /occurrence_mapping entry verbatim. No other
  source value enters the handoff record.

OUTPUT
  Both documents are canonical JSON (provenance.canonical_json); envelope_id and handoff_id
  are the SHA-256 of the canonical JSON without that field. Each object holds only its
  canonical bytes, so it has no mutable state, and every to_dict() is a new copy. from_dict
  and the strict loaders re-verify schema, identity, the contract's own rule text and
  status/reason consistency; for an AVAILABLE envelope they also confirm that the carried
  fragments reconstruct bytes with the carried content hash and size.
  verify_alignment_handoff re-derives a handoff record from its envelope. A consistently
  re-hashed edit is a different document with a different identity: pinning the expected
  envelope_id is what refuses it.

ERRORS
  AlignmentPublicationError(ValueError) with .code and .diagnostics; codes CONTRACT_INVALID,
  ENVELOPE_INVALID, HANDOFF_INVALID and IDENTITY_MISMATCH. No partial document exists.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .colabfold_a3m_lossless import (
    ColabFoldA3MError, ColabFoldA3MReaderResult, ColabFoldA3MResult, parse_colabfold_a3m,
)
from .provenance import canonical_json, hash_config
from .validation import validate_named

ENVELOPE_VERSION = "alignment_evidence_envelope/1"
HANDOFF_VERSION = "alignment_handoff_record/1"
READER = {"module": "structure_audit.colabfold_a3m_lossless", "entry_point": "parse_colabfold_a3m",
          "result_type": "ColabFoldA3MReaderResult"}

AVAILABLE, UNAVAILABLE, UNSUPPORTED, REJECTED = "AVAILABLE", "UNAVAILABLE", "UNSUPPORTED", "REJECTED"
READY, BLOCKED = "READY", "BLOCKED"
PRESENT, ABSENT, NOT_EVALUATED = "PRESENT", "ABSENT", "NOT_EVALUATED"
COMPONENT_KINDS = ("record_occurrence", "selected_occurrence")
REFERENCE_ABSENT = "REQUIRED_REFERENCE_ABSENT"

CARRIED_FIELDS = (
    "/status", "/artifact/snapshot/artifact_id", "/artifact/snapshot/format",
    "/artifact/snapshot/source_kind", "/artifact/snapshot/source_kind_status",
    "/artifact/raw_sha256", "/artifact/size_bytes", "/reconstructed_sha256", "/profile",
    "/position_bases", "/configuration/query_gap_policy", "/configuration/lowercase_x_policy",
    "/configuration/unknown_tokens", "/configuration/unknown_policy",
    "/effective_execution_gates", "/raw_preamble", "/records", "/occurrence_mapping", "/query",
    "/inventory", "/raw_id_duplicate_summary", "/sequence_duplicate_summary",
    "/unknown_token_summary", "/insertion_transform_summary", "/provenance_snapshot",
    "/diagnostics", "/limitations",
)
_ARTIFACT_LAYOUT = ("format", "source_kind", "source_kind_status")
_CONFIG_LAYOUT = ("profile_id", "profile_version", "profile_selection")
_DIAGNOSTIC_FIELDS = ("code", "locator", "details")
_HEX64 = re.compile(r"[a-f0-9]{64}")

# The reader's closed diagnostic codes. Metric and binding stage codes cannot occur in
# reader-only mode; they are listed so that the table covers every code the reader emits.
_READER_CODES = {
    "artifact_read_error": (UNAVAILABLE, "SOURCE_UNREADABLE"),
    **dict.fromkeys(("unsupported_config", "profile_mismatch", "unsupported_format",
                     "preamble_profile_mismatch", "unsupported_token",
                     "uppercase_unknown_without_policy"),
                    (UNSUPPORTED, "SOURCE_LAYOUT_UNSUPPORTED")),
    "artifact_hash_mismatch": (REJECTED, "SOURCE_CONTENT_HASH_MISMATCH"),
    **dict.fromkeys(("alignment_parse_error", "invalid_query_token", "ragged_rows",
                     "lossless_reconstruction_failure", "result_validation_error"),
                    (REJECTED, "SOURCE_MALFORMED")),
    **dict.fromkeys(("invalid_query_selector", "ambiguous_query_occurrence",
                     "malformed_occurrence_identity", "query_mismatch"),
                    (REJECTED, "SOURCE_SELECTION_REJECTED")),
    **dict.fromkeys(("invalid_contract", "unsafe_artifact_path", "query_binding_unresolved",
                     "statistics_error", "sequence_duplicate_policy_violation"),
                    (REJECTED, "SOURCE_REQUEST_REJECTED")),
}
_UNRECOGNIZED = (REJECTED, "READER_CODE_UNRECOGNIZED")

_ENVELOPE_RULES = {
    "arithmetic": "none; every source field is copied verbatim from the verified reader result",
    "authority": "the reader decides availability, layout support and content; this layer only classifies the reader's closed code",
    "exclusions": "no filesystem path, allowed root, path-bearing contract hash, raw byte copy or free-text reader message enters the document",
    "identity": "envelope_id is the SHA-256 of the canonical JSON of the document without envelope_id",
    "immutability": "the envelope holds only its canonical bytes; every read returns a new copy",
    "mode": "reader-only results only; metric and binding stages are outside this contract",
    "statuses": "AVAILABLE, UNAVAILABLE, UNSUPPORTED and REJECTED stay distinct; no status is coerced into another",
}
_HANDOFF_RULES = {
    "blocking": "an AVAILABLE envelope with any absent reference yields BLOCKED; nothing is substituted",
    "identity": "handoff_id is the SHA-256 of the canonical JSON of the document without handoff_id",
    "immutability": "the record holds only its canonical bytes; every read returns a new copy",
    "payload": "a resolved reference copies the source's own occurrence locator verbatim; no other source value enters the record",
    "propagation": "a non-AVAILABLE envelope status and reason are carried unchanged and every reference is NOT_EVALUATED",
    "references": "every declared reference is required and resolves only to a component the source itself declares",
}


class AlignmentPublicationError(ValueError):
    """Malformed request or document, or an identity mismatch. No partial document exists."""

    def __init__(self, code, message):
        self.code = code
        self.diagnostics = [{"severity": "error", "code": code, "message": message}]
        super().__init__(f"{code}: {message}")


def _contract(message):
    return AlignmentPublicationError("CONTRACT_INVALID", message)


def _text(value, what):
    if type(value) is not str or not value.strip():
        raise _contract(f"{what} must be nonempty text")


def _digest(value, what):
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise _contract(f"{what} must be 64 lowercase hexadecimal characters")


def _resolve(document, pointer):
    """The value at one JSON Pointer; CARRIED_FIELDS tokens contain neither '~' nor '/'."""
    value = document
    for token in pointer.split("/")[1:]:
        value = value[token]
    return value


def _classify(code):
    return _READER_CODES.get(code, _UNRECOGNIZED)


def _strict(raw, code, where):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def constant(token):
        raise ValueError(f"non-finite JSON token {token}")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise AlignmentPublicationError(code, f"{where}: {exc}") from None


def _canonical_bytes(data, code):
    try:
        return canonical_json(data)
    except (TypeError, ValueError) as exc:
        raise AlignmentPublicationError(code, f"not a JSON document: {exc}") from None


def _identified(document, identity_field):
    document[identity_field] = hash_config(document)
    return document


def _check_identity(data, identity_field, rules, code):
    without = {key: value for key, value in data.items() if key != identity_field}
    if hash_config(without) != data[identity_field]:
        raise AlignmentPublicationError(code, f"{identity_field} does not match the canonical document")
    if data["rules"] != rules:
        raise AlignmentPublicationError(code, "rules differ from the contract's own text")


# ---------------------------------------------------------------------------
# Evidence envelope
# ---------------------------------------------------------------------------
def _envelope_invalid(message):
    return AlignmentPublicationError("ENVELOPE_INVALID", message)


def _check_carried(source, fields):
    """Restate what the reader already guaranteed; no new acceptance rule is introduced."""
    layout = source["declared_layout"]
    declared = {"/status": "parsed", "/artifact/snapshot/artifact_id": source["artifact_id"],
                "/artifact/raw_sha256": source["declared_sha256"],
                "/profile": {key: layout[key] for key in _CONFIG_LAYOUT},
                **{f"/artifact/snapshot/{key}": layout[key] for key in _ARTIFACT_LAYOUT}}
    for pointer, value in declared.items():
        if canonical_json(fields[pointer]) != canonical_json(value):
            raise _envelope_invalid(f"source_fields {pointer} disagrees with the declared source")
    try:
        rebuilt = ColabFoldA3MResult({"raw_preamble": fields["/raw_preamble"],
                                      "records": fields["/records"]}).reconstruct_bytes()
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise _envelope_invalid(f"carried fragments do not reconstruct: {exc}") from None
    digest = hashlib.sha256(rebuilt).hexdigest()
    size = fields["/artifact/size_bytes"]
    if (digest != fields["/artifact/raw_sha256"] or digest != fields["/reconstructed_sha256"]
            or type(size) is not int or size != len(rebuilt)):
        raise _envelope_invalid("carried fragments do not reconstruct the carried content hash and size")


def _verified_envelope(data):
    try:
        validate_named(data, "alignment_evidence_envelope")
    except ValueError as exc:
        raise _envelope_invalid(str(exc)) from None
    _check_identity(data, "envelope_id", _ENVELOPE_RULES, "ENVELOPE_INVALID")
    status, reason = data["status"], data["reason"]
    diagnostic, fields = data["reader_diagnostic"], data["source_fields"]
    if status == AVAILABLE:
        if reason is not None or diagnostic is not None or fields is None:
            raise _envelope_invalid("an AVAILABLE envelope carries source fields and no reason or diagnostic")
        _check_carried(data["source"], fields)
    else:
        if fields is not None or diagnostic is None:
            raise _envelope_invalid("a non-AVAILABLE envelope carries a reader diagnostic and no source fields")
        if (status, reason) != _classify(diagnostic["code"]):
            raise _envelope_invalid("status and reason differ from the classification of the reader code")


@dataclass(frozen=True)
class AlignmentEvidenceEnvelope:
    """An immutable alignment_evidence_envelope/1 document, held only as canonical bytes."""

    json_bytes: bytes

    def __post_init__(self):
        if type(self.json_bytes) is not bytes:
            raise _envelope_invalid("json_bytes must be bytes")
        data = _strict(self.json_bytes, "ENVELOPE_INVALID", "envelope")
        _verified_envelope(data)
        if canonical_json(data) != self.json_bytes:
            raise _envelope_invalid("bytes are not the canonical serialization of the document")

    @classmethod
    def from_dict(cls, data):
        return cls(_canonical_bytes(data, "ENVELOPE_INVALID"))

    @property
    def envelope_id(self):
        return self.to_dict()["envelope_id"]

    @property
    def status(self):
        return self.to_dict()["status"]

    @property
    def reason(self):
        return self.to_dict()["reason"]

    def to_dict(self):
        return json.loads(self.json_bytes)

    def to_json_bytes(self):
        return self.json_bytes


def _source_request(artifact, config):
    if type(artifact) is not dict or type(config) is not dict:
        raise _contract("artifact and config must be JSON objects")
    _text(artifact.get("artifact_id"), "artifact.artifact_id")
    _digest(artifact.get("sha256"), "artifact.sha256")
    for key in _ARTIFACT_LAYOUT:
        _text(artifact.get(key), f"artifact.{key}")
    for key in _CONFIG_LAYOUT:
        _text(config.get(key), f"config.{key}")
    if (config.get("metrics_enabled", False) is not False or config.get("binding_enabled", False) is not False
            or config.get("metric_policy") is not None):
        raise _contract("only reader-only mode is published; metric and binding stages must stay disabled")
    return {"artifact_id": artifact["artifact_id"], "declared_sha256": artifact["sha256"],
            "declared_layout": {**{key: artifact[key] for key in _ARTIFACT_LAYOUT},
                                **{key: config[key] for key in _CONFIG_LAYOUT}}}


def _envelope_document(source, status, reason, diagnostic, fields):
    return _identified({"schema_version": ENVELOPE_VERSION, "source": source, "reader": dict(READER),
                        "status": status, "reason": reason, "reader_diagnostic": diagnostic,
                        "source_fields": fields, "rules": dict(_ENVELOPE_RULES)}, "envelope_id")


def publish_alignment_evidence(*, artifact, config):
    """Read one declared source artifact through the reader and publish one evidence envelope."""
    source = _source_request(artifact, config)
    try:
        result = parse_colabfold_a3m(artifact=artifact, config=config)
    except ColabFoldA3MError as exc:
        diagnostic = {key: deepcopy(exc.diagnostics[0][key]) for key in _DIAGNOSTIC_FIELDS}
        status, reason = _classify(diagnostic["code"])
        return AlignmentEvidenceEnvelope.from_dict(
            _envelope_document(source, status, reason, diagnostic, None))
    if not isinstance(result, ColabFoldA3MReaderResult):
        raise _contract("the reader did not return a reader-only result")
    data = result.to_dict()
    fields = {pointer: _resolve(data, pointer) for pointer in CARRIED_FIELDS}
    return AlignmentEvidenceEnvelope.from_dict(_envelope_document(source, AVAILABLE, None, None, fields))


# ---------------------------------------------------------------------------
# Consumer handoff record
# ---------------------------------------------------------------------------
def _handoff_invalid(message):
    return AlignmentPublicationError("HANDOFF_INVALID", message)


def _verified_handoff(data):
    try:
        validate_named(data, "alignment_handoff_record")
    except ValueError as exc:
        raise _handoff_invalid(str(exc)) from None
    _check_identity(data, "handoff_id", _HANDOFF_RULES, "HANDOFF_INVALID")
    status, reason, references = data["status"], data["reason"], data["references"]
    keys = [(r["component_kind"], r["component_id"]) for r in references]
    if not keys or keys != sorted(set(keys)):
        raise _handoff_invalid("references must be nonempty, unique and ordered by (component_kind, component_id)")
    resolutions = [r["resolution"] for r in references]
    if status == READY:
        valid = reason is None and set(resolutions) == {PRESENT}
    elif status == BLOCKED:
        valid = reason == REFERENCE_ABSENT and ABSENT in resolutions and NOT_EVALUATED not in resolutions
    else:
        valid = ((status, reason) in set(_READER_CODES.values()) | {_UNRECOGNIZED}
                 and set(resolutions) == {NOT_EVALUATED})
    if not valid:
        raise _handoff_invalid("status, reason and reference resolutions are inconsistent")
    for reference in references:
        locator = reference["source_locator"]
        if (reference["resolution"] == PRESENT) != (locator is not None):
            raise _handoff_invalid("a source locator is carried exactly when a reference is PRESENT")
        if locator is not None and locator.get("record_occurrence_id") != reference["component_id"]:
            raise _handoff_invalid("a source locator must name its own component")


@dataclass(frozen=True)
class AlignmentHandoffRecord:
    """An immutable alignment_handoff_record/1 document, held only as canonical bytes."""

    json_bytes: bytes

    def __post_init__(self):
        if type(self.json_bytes) is not bytes:
            raise _handoff_invalid("json_bytes must be bytes")
        data = _strict(self.json_bytes, "HANDOFF_INVALID", "handoff record")
        _verified_handoff(data)
        if canonical_json(data) != self.json_bytes:
            raise _handoff_invalid("bytes are not the canonical serialization of the document")

    @classmethod
    def from_dict(cls, data):
        return cls(_canonical_bytes(data, "HANDOFF_INVALID"))

    @property
    def handoff_id(self):
        return self.to_dict()["handoff_id"]

    @property
    def envelope_id(self):
        return self.to_dict()["envelope_id"]

    @property
    def status(self):
        return self.to_dict()["status"]

    def to_dict(self):
        return json.loads(self.json_bytes)

    def to_json_bytes(self):
        return self.json_bytes


def _reference_request(references):
    if type(references) is not list or not references:
        raise _contract("references must be a nonempty list")
    requested = []
    for index, reference in enumerate(references):
        what = f"references[{index}]"
        if type(reference) is not dict or set(reference) != {"component_kind", "component_id"}:
            raise _contract(f"{what} must have exactly the fields ['component_id', 'component_kind']")
        if reference["component_kind"] not in COMPONENT_KINDS:
            raise _contract(f"{what}.component_kind must be one of {list(COMPONENT_KINDS)}")
        _text(reference["component_id"], f"{what}.component_id")
        requested.append((reference["component_kind"], reference["component_id"]))
    if len(set(requested)) != len(requested):
        raise _contract("references must be unique")
    return sorted(requested)


def _source_locator(fields, kind, component_id):
    """The source's own locator entry for one declared component, or None when absent."""
    if kind == "selected_occurrence" and component_id != fields["/query"]["selected_occurrence"]:
        return None
    matches = [entry for entry in fields["/occurrence_mapping"]
               if entry["record_occurrence_id"] == component_id]
    return matches[0] if len(matches) == 1 else None


def publish_alignment_handoff(*, envelope, expected_envelope_id, references):
    """Publish one consumer handoff record for explicitly referenced source components."""
    if not isinstance(envelope, AlignmentEvidenceEnvelope):
        raise _contract("envelope must be an AlignmentEvidenceEnvelope")
    _digest(expected_envelope_id, "expected_envelope_id")
    requested = _reference_request(references)
    data = envelope.to_dict()
    if data["envelope_id"] != expected_envelope_id:
        raise AlignmentPublicationError("IDENTITY_MISMATCH",
                                        "the envelope does not carry the expected envelope_id")
    entries = []
    for kind, component_id in requested:
        locator = (None if data["status"] != AVAILABLE
                   else _source_locator(data["source_fields"], kind, component_id))
        resolution = (NOT_EVALUATED if data["status"] != AVAILABLE
                      else ABSENT if locator is None else PRESENT)
        entries.append({"component_kind": kind, "component_id": component_id,
                        "resolution": resolution, "source_locator": locator})
    if data["status"] != AVAILABLE:
        status, reason = data["status"], data["reason"]
    elif all(entry["resolution"] == PRESENT for entry in entries):
        status, reason = READY, None
    else:
        status, reason = BLOCKED, REFERENCE_ABSENT
    return AlignmentHandoffRecord.from_dict(_identified(
        {"schema_version": HANDOFF_VERSION, "envelope_id": data["envelope_id"], "status": status,
         "reason": reason, "references": entries, "rules": dict(_HANDOFF_RULES)}, "handoff_id"))


def verify_alignment_handoff(handoff, envelope):
    """Re-derive a handoff record from its envelope; any difference is refused."""
    if not isinstance(handoff, AlignmentHandoffRecord) or not isinstance(envelope, AlignmentEvidenceEnvelope):
        raise _contract("handoff and envelope must be an AlignmentHandoffRecord and an AlignmentEvidenceEnvelope")
    data = handoff.to_dict()
    rebuilt = publish_alignment_handoff(
        envelope=envelope, expected_envelope_id=data["envelope_id"],
        references=[{"component_kind": r["component_kind"], "component_id": r["component_id"]}
                    for r in data["references"]])
    if rebuilt.to_json_bytes() != handoff.to_json_bytes():
        raise _handoff_invalid("the handoff record differs from its re-derivation from the envelope")


def load_alignment_evidence_envelope(path):
    """Strictly parse and verify an exported alignment_evidence_envelope/1 document."""
    return AlignmentEvidenceEnvelope.from_dict(_strict(Path(path).read_bytes(), "ENVELOPE_INVALID", str(path)))


def load_alignment_handoff_record(path):
    """Strictly parse and verify an exported alignment_handoff_record/1 document."""
    return AlignmentHandoffRecord.from_dict(_strict(Path(path).read_bytes(), "HANDOFF_INVALID", str(path)))
