"""Identity-checked transfer of one CEFF_M / ARM_REACH_NM value pair (contracts
value_flow_envelope/1 and value_flow_receipt/1).

Standard library plus existing structure_audit helpers; no import-time I/O. This layer
performs no arithmetic. It reads explicitly selected producer documents through their own
public verifying loaders, compares declared identities with observed identities, and
carries the two already-computed values unchanged. It defines no formula, threshold,
fallback, inferred default or ordering, and it never recomputes or substitutes a value.

WHAT GAP THIS CLOSES

  pointwise_measurement produces ceff_m and arm_reach_nm together in one result document,
  and f01_coordinate_admission produces the distance_nm that result consumed. Nothing
  carried the pair across a producer/consumer boundary as one atomic envelope with its
  result identity, its coefficient-profile identity and its upstream deterministic
  measurement reference. linked_transfer moves a single scalar out of a candidate_evidence
  or quantity_summary artifact and cannot read either document layout; it is unchanged and
  is not used here.

INPUTS (JSON data; a malformed outer request raises ValueFlowTransferError CONTRACT_INVALID
and yields no receipt, because the expected identity itself is malformed)
  producer = {producer_id, path, sha256, layout}
      One explicitly selected producer document. path is the absolute canonical path of a
      regular file; sha256 is the declared SHA-256 of its bytes. layout is declared, never
      sniffed, and must be "pointwise_measurement_v1".
  expected = {producer_result_id, configuration, quantities}
      producer_result_id is the result identity the consumer requires. configuration is
      {profile_id, profile_version}, the coefficient-profile identity the consumer
      requires. quantities is {ceff_m: identity, arm_reach_nm: identity} with each identity
      {quantity_id, quantity_definition_id, context, category, unit, scale}.
  measurement_references = [] or [{reference_id, kind, path, sha256, result_id,
                                   quantity_definition_id}]
      Explicitly selected deterministic measurements the producer consumed. kind is
      declared, never sniffed, and must be "f01_coordinate_distance_v1". Each reference is
      verified against its own document and its value is compared with the producer's
      recorded input of the same quantity definition. Comparison only: nothing is derived.
  consumer = {consumer_id, export_id}
      The consumer-side use event and the export it feeds.

VERIFICATION ORDER (the first failure stops; later stages are NOT_REACHED)
  1 PRODUCER_PATH            absolute canonical path of a regular file, no symlink alias
  2 PRODUCER_BYTES           SHA-256 of the bytes read equals producer.sha256
  3 PRODUCER_DOCUMENT        strict JSON, declared layout, and the producer's own verifying
                             loader re-derives the document
  4 PRODUCER_IDENTITY        observed result_id equals expected.producer_result_id
  5 CONFIGURATION_IDENTITY   observed coefficient-profile id and version equal the
                             expectation, and the configuration hash is recorded
  6 MEASUREMENT_REFERENCES   every declared reference verifies, its result_id matches, and
                             its value equals the producer's recorded input of the same
                             quantity definition
  7 QUANTITY_IDENTITY        both output identities equal the declared expectations
  8 VALUE_ADMISSION          the producer's own status decides the outcome
  Both producer and reference files are re-hashed after stage 8; a difference is
  ARTIFACT_CHANGED. No identity is ever substituted, defaulted or inferred.

OUTCOMES (exactly three, and the producer's own status decides between them)
  ACCEPTED     the producer status is COMPUTED and both values are finite
  UNAVAILABLE  the producer status is UNAVAILABLE; the producer's reason is carried
  REJECTED     any verification stage failed, or the producer status is REJECTED
  An envelope exists exactly when the outcome is not REJECTED. Every call yields a receipt.

OUTPUT
  transfer_value_flow returns ValueFlowOutcome(envelope, receipt). Both documents are
  canonical JSON (provenance.canonical_json); their ids are the SHA-256 of the canonical
  JSON without the id field. The envelope is immutable after construction and carries no
  filesystem path, so it is location independent; the receipt records the selected paths as
  supplied and carries the producer -> envelope -> consumer -> export chain. from_dict and
  the strict loaders re-derive every derived field and id and reject any difference.

ERRORS
  ValueFlowTransferError(ValueError) with .code and .diagnostics; no partial transfer.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Optional

from . import f01_coordinate_admission as f01
from . import pointwise_measurement as pointwise
from .provenance import canonical_json, hash_config, hash_file
from .validation import validate_named

ENVELOPE_VERSION = "value_flow_envelope/1"
RECEIPT_VERSION = "value_flow_receipt/1"
PRODUCER_LAYOUT = "pointwise_measurement_v1"
REFERENCE_KIND = "f01_coordinate_distance_v1"
VALUE_NAMES = ("arm_reach_nm", "ceff_m")

ACCEPTED, UNAVAILABLE, REJECTED = "ACCEPTED", "UNAVAILABLE", "REJECTED"
OUTCOMES = (ACCEPTED, UNAVAILABLE, REJECTED)
PASSED, FAILED, NOT_REACHED = "PASSED", "FAILED", "NOT_REACHED"

STAGES = ("PRODUCER_PATH", "PRODUCER_BYTES", "PRODUCER_DOCUMENT", "PRODUCER_IDENTITY",
          "CONFIGURATION_IDENTITY", "MEASUREMENT_REFERENCES", "QUANTITY_IDENTITY",
          "VALUE_ADMISSION")
REASONS = (
    "PRODUCER_PATH_INVALID", "PRODUCER_BYTES_MISMATCH", "PRODUCER_DOCUMENT_INVALID",
    "PRODUCER_LAYOUT_MISMATCH", "PRODUCER_RESULT_ID_MISMATCH", "CONFIGURATION_IDENTITY_MISMATCH",
    "MEASUREMENT_REFERENCE_PATH_INVALID", "MEASUREMENT_REFERENCE_BYTES_MISMATCH",
    "MEASUREMENT_REFERENCE_DOCUMENT_INVALID", "MEASUREMENT_REFERENCE_ID_MISMATCH",
    "MEASUREMENT_REFERENCE_VALUE_MISSING", "MEASUREMENT_REFERENCE_VALUE_MISMATCH",
    "QUANTITY_IDENTITY_MISMATCH", "VALUE_MISSING", "VALUE_NOT_FINITE",
    "PRODUCER_VALUE_UNAVAILABLE", "PRODUCER_VALUE_REJECTED", "ARTIFACT_CHANGED",
)
_STAGE_OF = {
    "PRODUCER_PATH_INVALID": "PRODUCER_PATH",
    "PRODUCER_BYTES_MISMATCH": "PRODUCER_BYTES", "ARTIFACT_CHANGED": "PRODUCER_BYTES",
    "PRODUCER_DOCUMENT_INVALID": "PRODUCER_DOCUMENT", "PRODUCER_LAYOUT_MISMATCH": "PRODUCER_DOCUMENT",
    "PRODUCER_RESULT_ID_MISMATCH": "PRODUCER_IDENTITY",
    "CONFIGURATION_IDENTITY_MISMATCH": "CONFIGURATION_IDENTITY",
    "MEASUREMENT_REFERENCE_PATH_INVALID": "MEASUREMENT_REFERENCES",
    "MEASUREMENT_REFERENCE_BYTES_MISMATCH": "MEASUREMENT_REFERENCES",
    "MEASUREMENT_REFERENCE_DOCUMENT_INVALID": "MEASUREMENT_REFERENCES",
    "MEASUREMENT_REFERENCE_ID_MISMATCH": "MEASUREMENT_REFERENCES",
    "MEASUREMENT_REFERENCE_VALUE_MISSING": "MEASUREMENT_REFERENCES",
    "MEASUREMENT_REFERENCE_VALUE_MISMATCH": "MEASUREMENT_REFERENCES",
    "QUANTITY_IDENTITY_MISMATCH": "QUANTITY_IDENTITY",
    "VALUE_MISSING": "VALUE_ADMISSION", "VALUE_NOT_FINITE": "VALUE_ADMISSION",
    "PRODUCER_VALUE_UNAVAILABLE": "VALUE_ADMISSION", "PRODUCER_VALUE_REJECTED": "VALUE_ADMISSION",
}

_PRODUCER_FIELDS = ("producer_id", "path", "sha256", "layout")
_EXPECTED_FIELDS = ("producer_result_id", "configuration", "quantities")
_CONFIGURATION_FIELDS = ("profile_id", "profile_version")
_IDENTITY_FIELDS = ("quantity_id", "quantity_definition_id", "context", "category", "unit", "scale")
_REFERENCE_FIELDS = ("reference_id", "kind", "path", "sha256", "result_id", "quantity_definition_id")
_CONSUMER_FIELDS = ("consumer_id", "export_id")
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
_HEX64 = re.compile(r"[a-f0-9]{64}")

_RULES = {
    "arithmetic": "none; both values are carried unchanged and no formula, threshold or default exists here",
    "authority": "the producer document decides the status; this layer only compares identities",
    "immutability": "the envelope is frozen after construction and is returned only as a deep copy",
    "outcomes": "ACCEPTED, UNAVAILABLE and REJECTED remain distinct; no outcome is coerced into another",
    "pairing": "ceff_m and arm_reach_nm travel as one atomic pair from one producer result",
    "references": "a declared measurement reference is verified and value-compared, never derived",
    "selection": "explicitly selected producer and reference documents only; no discovery or latest-output lookup",
    "identity": "envelope_id and receipt_id are the SHA-256 of the canonical JSON without that field",
}


class ValueFlowTransferError(ValueError):
    """Malformed contract or document. Never used for a transfer outcome."""

    def __init__(self, code, message):
        self.code = code
        self.diagnostics = [{"severity": "error", "code": code, "message": message}]
        super().__init__(f"{code}: {message}")


class _Rejected(Exception):
    def __init__(self, reason, detail):
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail = reason, detail


class _Unavailable(Exception):
    def __init__(self, reason, detail):
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail = reason, detail


def _contract(message):
    return ValueFlowTransferError("CONTRACT_INVALID", message)


def _invalid(kind, message):
    return ValueFlowTransferError(kind, message)


def _exact(obj, names, what, code="CONTRACT_INVALID"):
    if not isinstance(obj, dict) or set(obj) != set(names):
        raise ValueFlowTransferError(code, f"{what} must have exactly the fields {sorted(names)}")


def _label(value, what, code="CONTRACT_INVALID"):
    if type(value) is not str or _LABEL.fullmatch(value) is None:
        raise ValueFlowTransferError(code, f"{what} must match [A-Za-z0-9][A-Za-z0-9_.-]{{0,99}}")
    return value


def _text(value, what, *, nullable=False, code="CONTRACT_INVALID"):
    if nullable and value is None:
        return None
    if type(value) is not str or not value.strip():
        raise ValueFlowTransferError(code, f"{what} must be nonempty text{' or null' if nullable else ''}")
    return value


def _digest(value, what, code="CONTRACT_INVALID"):
    if type(value) is not str or _HEX64.fullmatch(value) is None:
        raise ValueFlowTransferError(code, f"{what} must be 64 lowercase hexadecimal characters")
    return value


def _identity(identity, what, code="CONTRACT_INVALID"):
    _exact(identity, _IDENTITY_FIELDS, what, code)
    for key in ("quantity_id", "quantity_definition_id", "context", "category", "unit"):
        _text(identity[key], f"{what}.{key}", code=code)
    _text(identity["scale"], f"{what}.scale", nullable=True, code=code)
    return {key: identity[key] for key in _IDENTITY_FIELDS}


# ---------------------------------------------------------------------------
# Outer request
# ---------------------------------------------------------------------------
def _producer_request(producer, code="CONTRACT_INVALID"):
    _exact(producer, _PRODUCER_FIELDS, "producer", code)
    _label(producer["producer_id"], "producer.producer_id", code)
    _digest(producer["sha256"], "producer.sha256", code)
    _text(producer["path"], "producer.path", code=code)
    if producer["layout"] != PRODUCER_LAYOUT:
        raise ValueFlowTransferError(code, f"producer.layout must be exactly {PRODUCER_LAYOUT!r}")
    return {key: producer[key] for key in _PRODUCER_FIELDS}


def _expected_request(expected, code="CONTRACT_INVALID"):
    _exact(expected, _EXPECTED_FIELDS, "expected", code)
    _digest(expected["producer_result_id"], "expected.producer_result_id", code)
    _exact(expected["configuration"], _CONFIGURATION_FIELDS, "expected.configuration", code)
    for key in _CONFIGURATION_FIELDS:
        _label(expected["configuration"][key], f"expected.configuration.{key}", code)
    _exact(expected["quantities"], VALUE_NAMES, "expected.quantities", code)
    return {"producer_result_id": expected["producer_result_id"],
            "configuration": {k: expected["configuration"][k] for k in _CONFIGURATION_FIELDS},
            "quantities": {name: _identity(expected["quantities"][name],
                                           f"expected.quantities.{name}", code)
                           for name in VALUE_NAMES}}


def _reference_request(references, code="CONTRACT_INVALID"):
    if not isinstance(references, list):
        raise ValueFlowTransferError(code, "measurement_references must be a list")
    out = []
    for index, reference in enumerate(references):
        what = f"measurement_references[{index}]"
        _exact(reference, _REFERENCE_FIELDS, what, code)
        _label(reference["reference_id"], f"{what}.reference_id", code)
        _digest(reference["sha256"], f"{what}.sha256", code)
        _digest(reference["result_id"], f"{what}.result_id", code)
        _text(reference["path"], f"{what}.path", code=code)
        _text(reference["quantity_definition_id"], f"{what}.quantity_definition_id", code=code)
        if reference["kind"] != REFERENCE_KIND:
            raise ValueFlowTransferError(code, f"{what}.kind must be exactly {REFERENCE_KIND!r}")
        out.append({key: reference[key] for key in _REFERENCE_FIELDS})
    ids = [r["reference_id"] for r in out]
    if len(set(ids)) != len(ids):
        raise ValueFlowTransferError(code, "measurement_references reference_id must be unique")
    return sorted(out, key=lambda r: r["reference_id"])


def _consumer_request(consumer, code="CONTRACT_INVALID"):
    _exact(consumer, _CONSUMER_FIELDS, "consumer", code)
    for key in _CONSUMER_FIELDS:
        _label(consumer[key], f"consumer.{key}", code)
    return {key: consumer[key] for key in _CONSUMER_FIELDS}


# ---------------------------------------------------------------------------
# Selected-document reading
# ---------------------------------------------------------------------------
def _read(raw, path_reason, bytes_reason, sha256, what):
    path = Path(raw)
    if not path.is_absolute() or os.path.abspath(raw) != raw or path.resolve() != path:
        raise _Rejected(path_reason, f"{what}: path must be absolute and canonical, without symlink alias")
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        raise _Rejected(path_reason, f"{what}: path is not readable ({exc.strerror})") from None
    if not stat.S_ISREG(mode):
        raise _Rejected(path_reason, f"{what}: path must name a regular file")
    data = path.read_bytes()
    observed = hashlib.sha256(data).hexdigest()
    if observed != sha256:
        raise _Rejected(bytes_reason, f"{what}: bytes do not match the declared sha256")
    return path, data


def _strict_json(data, reason, what):
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
        return json.loads(data.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise _Rejected(reason, f"{what}: {exc}") from None


def _producer_document(data, what):
    document = _strict_json(data, "PRODUCER_DOCUMENT_INVALID", what)
    if not isinstance(document, dict) or document.get("schema_version") != pointwise.SCHEMA_VERSION:
        raise _Rejected("PRODUCER_LAYOUT_MISMATCH",
                        f"{what}: declared layout {PRODUCER_LAYOUT!r} requires schema_version "
                        f"{pointwise.SCHEMA_VERSION!r}")
    try:
        return pointwise.PointwiseMeasurement.from_dict(document).to_dict()
    except pointwise.PointwiseMeasurementError as exc:
        raise _Rejected("PRODUCER_DOCUMENT_INVALID", f"{what}: {exc}") from None


def _reference_document(data, what):
    document = _strict_json(data, "MEASUREMENT_REFERENCE_DOCUMENT_INVALID", what)
    if not isinstance(document, dict) or document.get("schema_version") != f01.SCHEMA_VERSION:
        raise _Rejected("MEASUREMENT_REFERENCE_DOCUMENT_INVALID",
                        f"{what}: declared kind {REFERENCE_KIND!r} requires schema_version "
                        f"{f01.SCHEMA_VERSION!r}")
    try:
        return f01.F01CoordinateDistance.from_dict(document).to_dict()
    except f01.F01CoordinateAdmissionError as exc:
        raise _Rejected("MEASUREMENT_REFERENCE_DOCUMENT_INVALID", f"{what}: {exc}") from None


# ---------------------------------------------------------------------------
# Verification stages
# ---------------------------------------------------------------------------
def _check(name, expected, observed, matched):
    return {"name": name, "expected": expected, "observed": observed,
            "result": PASSED if matched else FAILED}


def _stage_producer_identity(expected, document, checks):
    observed = document["result_id"]
    checks.append(_check("producer_result_id", expected["producer_result_id"], observed,
                         observed == expected["producer_result_id"]))
    if observed != expected["producer_result_id"]:
        raise _Rejected("PRODUCER_RESULT_ID_MISMATCH",
                        "the producer document does not carry the expected result identity")


def _stage_configuration(expected, document, checks):
    parameters = document["parameters"]
    for key in _CONFIGURATION_FIELDS:
        observed = parameters[key]
        checks.append(_check(f"configuration.{key}", expected["configuration"][key], observed,
                             observed == expected["configuration"][key]))
        if observed != expected["configuration"][key]:
            raise _Rejected("CONFIGURATION_IDENTITY_MISMATCH",
                            f"the producer coefficient profile {key} is {observed!r}, "
                            f"expected {expected['configuration'][key]!r}")
    return hash_config(parameters)


def _stage_references(references, document, checks):
    """Each reference must verify and agree with the producer's recorded input value."""
    carried, loaded = [], []
    for reference in references:
        what = f"measurement reference {reference['reference_id']}"
        path, data = _read(reference["path"], "MEASUREMENT_REFERENCE_PATH_INVALID",
                           "MEASUREMENT_REFERENCE_BYTES_MISMATCH", reference["sha256"], what)
        referenced = _reference_document(data, what)
        loaded.append((path, reference))
        observed_id = referenced["result_id"]
        checks.append(_check(f"reference.{reference['reference_id']}.result_id",
                             reference["result_id"], observed_id,
                             observed_id == reference["result_id"]))
        if observed_id != reference["result_id"]:
            raise _Rejected("MEASUREMENT_REFERENCE_ID_MISMATCH",
                            f"{what}: the document result identity does not match the declaration")
        definition = reference["quantity_definition_id"]
        metric = referenced["output_metric"]
        if metric["quantity_definition_id"] != definition or metric["value"] is None:
            raise _Rejected("MEASUREMENT_REFERENCE_VALUE_MISSING",
                            f"{what}: no available {definition!r} value to compare")
        consumed = [entry for entry in document["inputs"].values()
                    if entry["quantity_definition_id"] == definition]
        if len(consumed) != 1 or consumed[0]["value"] is None:
            raise _Rejected("MEASUREMENT_REFERENCE_VALUE_MISSING",
                            f"{what}: the producer records no single available {definition!r} input")
        observed_value, expected_value = consumed[0]["value"], metric["value"]
        matched = (canonical_json(observed_value) == canonical_json(expected_value)
                   and metric["unit"] == consumed[0]["unit"])
        checks.append(_check(f"reference.{reference['reference_id']}.{definition}",
                             expected_value, observed_value, matched))
        if not matched:
            raise _Rejected("MEASUREMENT_REFERENCE_VALUE_MISMATCH",
                            f"{what}: the producer consumed {observed_value!r} {consumed[0]['unit']!r} "
                            f"while the reference carries {expected_value!r} {metric['unit']!r}")
        carried.append({"reference_id": reference["reference_id"], "kind": reference["kind"],
                        "result_id": observed_id, "artifact_sha256": reference["sha256"],
                        "quantity_definition_id": definition, "unit": metric["unit"],
                        "value": expected_value})
    return carried, loaded


def _stage_quantity_identity(expected, document, checks):
    for name in VALUE_NAMES:
        output = document["outputs"][name]
        declared = expected["quantities"][name]
        observed = {key: output[key] for key in _IDENTITY_FIELDS}
        matched = observed == declared
        checks.append(_check(f"quantity.{name}", declared, observed, matched))
        if not matched:
            raise _Rejected("QUANTITY_IDENTITY_MISMATCH",
                            f"the {name} identity carried by the producer differs from the expectation")


def _stage_value_admission(document, checks):
    status = document["status"]
    primary = document["diagnostics"][0] if document["diagnostics"] else None
    detail = None if primary is None else f"{primary['code']}: {primary['message']}"
    checks.append(_check("producer_status", pointwise.COMPUTED, status, status == pointwise.COMPUTED))
    if status == pointwise.UNAVAILABLE:
        raise _Unavailable("PRODUCER_VALUE_UNAVAILABLE",
                           detail or "the producer declares the value pair unavailable")
    if status == pointwise.REJECTED:
        raise _Rejected("PRODUCER_VALUE_REJECTED", detail or "the producer rejected the value pair")
    values = {}
    for name in VALUE_NAMES:
        output = document["outputs"][name]
        if output["value"] is None:
            raise _Rejected("VALUE_MISSING", f"the producer carries no {name} value")
        if type(output["value"]) is not float:
            raise _Rejected("VALUE_NOT_FINITE", f"the {name} value is not a binary64 number")
        values[name] = {**{key: output[key] for key in _IDENTITY_FIELDS}, "value": output["value"]}
    return values


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
def _checks_list(failed_stage):
    """Stages before the failure PASSED, the failing stage FAILED, every later stage
    NOT_REACHED. With no failure every stage is PASSED."""
    out, reached = [], True
    for stage in STAGES:
        if failed_stage is not None and stage == failed_stage:
            out.append({"stage": stage, "result": FAILED})
            reached = False
        else:
            out.append({"stage": stage, "result": PASSED if reached else NOT_REACHED})
    return out


def _envelope_document(producer, configuration_hash, observed, values, references,
                       identity_checks, outcome, reason):
    document = {
        "schema_version": ENVELOPE_VERSION,
        "producer": {"producer_id": producer["producer_id"], "layout": producer["layout"],
                     "artifact_sha256": producer["sha256"], "result_id": observed["result_id"],
                     "method_id": observed["method_id"], "method_version": observed["method_version"],
                     "pipeline_run_id": observed["pipeline_run_id"],
                     "execution_id": observed["execution_id"]},
        "configuration": {"profile_id": observed["profile_id"],
                          "profile_version": observed["profile_version"],
                          "configuration_hash": configuration_hash},
        "values": deepcopy(values),
        "measurement_references": deepcopy(references),
        "identity_checks": deepcopy(identity_checks),
        "status": outcome,
        "reason": reason,
        "rules": dict(_RULES),
    }
    document["envelope_id"] = hash_config(document)
    validate_named(document, "value_flow_envelope")
    return document


def _receipt_document(consumer, producer, expected, observed, checks, outcome, reason, detail,
                      envelope_id, references):
    document = {
        "schema_version": RECEIPT_VERSION,
        "consumer": deepcopy(consumer),
        "selected_producer_path": producer["path"],
        "selected_reference_paths": [{"reference_id": r["reference_id"], "path": r["path"]}
                                     for r in references],
        "expected": deepcopy(expected),
        "observed": deepcopy(observed),
        "checks": deepcopy(checks),
        "outcome": outcome,
        "reason": reason,
        "detail": detail,
        "chain": {"producer_result_id": observed["result_id"], "envelope_id": envelope_id,
                  "consumer_id": consumer["consumer_id"], "export_id": consumer["export_id"]},
    }
    document["receipt_id"] = hash_config(document)
    validate_named(document, "value_flow_receipt")
    return document


def _verified(data, name, code):
    try:
        validate_named(data, name)
    except ValueError as exc:
        raise _invalid(code, str(exc)) from None
    identity = "envelope_id" if name == "value_flow_envelope" else "receipt_id"
    rebuilt = {k: v for k, v in data.items() if k != identity}
    if hash_config(rebuilt) != data[identity]:
        raise _invalid(code, f"{identity} does not match the canonical document")
    if data.get("rules") is not None and name == "value_flow_envelope" and data["rules"] != _RULES:
        raise _invalid(code, "rules differ from the contract's own text")
    return deepcopy(data)


@dataclass(frozen=True)
class ValueFlowEnvelope:
    """An immutable value_flow_envelope/1 document for one CEFF_M / ARM_REACH_NM pair."""

    data: dict

    def __post_init__(self):
        object.__setattr__(self, "data", _verified(self.data, "value_flow_envelope", "ENVELOPE_INVALID"))

    @classmethod
    def from_dict(cls, data):
        return cls(data)

    @property
    def envelope_id(self):
        return self.data["envelope_id"]

    @property
    def status(self):
        return self.data["status"]

    def value(self, name):
        """The carried value, or None when the pair is UNAVAILABLE. Never recomputed."""
        if name not in VALUE_NAMES:
            raise _contract(f"name must be one of {sorted(VALUE_NAMES)}")
        carried = self.data["values"].get(name)
        return None if carried is None else carried["value"]

    def to_dict(self):
        return deepcopy(self.data)

    def to_json_bytes(self):
        return canonical_json(self.data)


@dataclass(frozen=True)
class ValueFlowReceipt:
    """A verified value_flow_receipt/1 document: one consumer-side use event."""

    data: dict

    def __post_init__(self):
        object.__setattr__(self, "data", _verified(self.data, "value_flow_receipt", "RECEIPT_INVALID"))

    @classmethod
    def from_dict(cls, data):
        return cls(data)

    @property
    def receipt_id(self):
        return self.data["receipt_id"]

    @property
    def outcome(self):
        return self.data["outcome"]

    def to_dict(self):
        return deepcopy(self.data)

    def to_json_bytes(self):
        return canonical_json(self.data)


@dataclass(frozen=True)
class ValueFlowOutcome:
    """One use event: its receipt and, unless REJECTED, its envelope."""

    envelope: Optional[ValueFlowEnvelope]
    receipt: ValueFlowReceipt

    def __post_init__(self):
        if not isinstance(self.receipt, ValueFlowReceipt):
            raise _contract("receipt must be a ValueFlowReceipt")
        if self.envelope is not None and not isinstance(self.envelope, ValueFlowEnvelope):
            raise _contract("envelope must be a ValueFlowEnvelope or None")
        if (self.envelope is None) != (self.receipt.outcome == REJECTED):
            raise _contract("an envelope exists exactly when the outcome is not REJECTED")
        if self.envelope is not None:
            linked = (self.receipt.data["chain"]["envelope_id"] == self.envelope.envelope_id
                      and self.receipt.data["outcome"] == self.envelope.status
                      and self.receipt.data["reason"] == self.envelope.data["reason"])
            if not linked:
                raise _contract("receipt and envelope do not describe the same use event")


def transfer_value_flow(*, producer, expected, measurement_references, consumer):
    """Verify one selected producer result and carry its CEFF_M / ARM_REACH_NM pair."""
    producer = _producer_request(producer)
    expected = _expected_request(expected)
    references = _reference_request(measurement_references)
    consumer = _consumer_request(consumer)

    observed = {"result_id": None, "method_id": None, "method_version": None,
                "pipeline_run_id": None, "execution_id": None, "profile_id": None,
                "profile_version": None, "status": None}
    identity_checks = []
    outcome, reason, detail = ACCEPTED, None, None
    values, carried, configuration_hash, failed_stage = None, [], None, None
    try:
        path, data = _read(producer["path"], "PRODUCER_PATH_INVALID", "PRODUCER_BYTES_MISMATCH",
                           producer["sha256"], "producer")
        document = _producer_document(data, "producer")
        observed.update(result_id=document["result_id"], status=document["status"],
                        method_id=document["provenance"]["method_id"],
                        method_version=document["provenance"]["method_version"],
                        pipeline_run_id=document["provenance"]["pipeline_run_id"],
                        execution_id=document["provenance"]["execution_id"],
                        profile_id=document["parameters"]["profile_id"],
                        profile_version=document["parameters"]["profile_version"])
        _stage_producer_identity(expected, document, identity_checks)
        configuration_hash = _stage_configuration(expected, document, identity_checks)
        carried, loaded = _stage_references(references, document, identity_checks)
        _stage_quantity_identity(expected, document, identity_checks)
        values = _stage_value_admission(document, identity_checks)
        for selected, reference in [(path, producer)] + loaded:
            if hash_file(selected) != reference["sha256"]:
                raise _Rejected("ARTIFACT_CHANGED",
                                f"{reference.get('reference_id', 'producer')}: bytes changed "
                                "during verification")
    except _Unavailable as unavailable:
        outcome, reason, detail = UNAVAILABLE, unavailable.reason, unavailable.detail
        failed_stage = _STAGE_OF[unavailable.reason]
        values = {}
    except _Rejected as rejected:
        outcome, reason, detail = REJECTED, rejected.reason, rejected.detail
        failed_stage = _STAGE_OF[rejected.reason]
    checks = _checks_list(failed_stage)
    envelope = None
    if outcome != REJECTED:
        envelope = ValueFlowEnvelope(_envelope_document(
            producer, configuration_hash, observed, values, carried, identity_checks,
            outcome, reason))
    receipt = ValueFlowReceipt(_receipt_document(
        consumer, producer, expected, observed, checks, outcome, reason, detail,
        None if envelope is None else envelope.envelope_id, references))
    return ValueFlowOutcome(envelope, receipt)


def _load(path, cls, code):
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
        data = json.loads(Path(path).read_bytes().decode("utf-8"),
                          object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise _invalid(code, f"{path}: {exc}") from None
    return cls.from_dict(data)


def load_value_flow_envelope(path):
    """Strictly parse and verify an exported value_flow_envelope/1 document."""
    return _load(path, ValueFlowEnvelope, "ENVELOPE_INVALID")


def load_value_flow_receipt(path):
    """Strictly parse and verify an exported value_flow_receipt/1 document."""
    return _load(path, ValueFlowReceipt, "RECEIPT_INVALID")
