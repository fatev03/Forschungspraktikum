"""Demo-facing export of one completed value-flow transfer (contract value_flow_demo_summary/1).

Standard library plus existing structure_audit helpers; no import-time I/O. This module is a
presentation adapter. It reads one verified value_flow_envelope/1 and its
value_flow_receipt/1 and copies selected fields into one stable summary document. It opens
no file, performs no arithmetic, and defines no acceptance rule, identity rule, threshold,
fallback, default or ordering. Every value it shows is already present in the envelope or
the receipt; nothing is recomputed, rounded, reformatted or combined.

WHAT IT MAKES VISIBLE

    f01_coordinate_distance/1 result reference
      -> pointwise_measurement/1 producer result
        -> value_flow_envelope/1
          -> value_flow_receipt/1
            -> value_flow_demo_summary/1

  The summary states the outcome the receipt already recorded, the identity chain the two
  documents already carry, the quantities the envelope already carries, and the ordered
  check outcomes both documents already recorded. It states nothing else.

INPUTS
  envelope  a ValueFlowEnvelope, or None exactly when the receipt outcome is REJECTED
  receipt   a ValueFlowReceipt
  The pairing invariant is not restated here: the two are handed to the existing
  ValueFlowOutcome, which is the sole authority on whether they describe one use event.

OUTCOMES
  ACCEPTED, UNAVAILABLE and REJECTED are carried through unchanged and stay distinct. The
  summary never promotes one into another and never supplies a value the envelope withheld.

EXCLUDED BY CONTRACT
  selected_producer_path, selected_reference_paths and every other filesystem path;
  notebook state; timestamps; environment values; and any numeric result not already
  present in a source document. A summary is therefore location independent.

OUTPUT
  build_demo_summary returns ValueFlowDemoSummary. to_dict() conforms to
  schemas/value_flow_demo_summary.schema.json and to_json_bytes() is its canonical JSON
  (provenance.canonical_json). summary_id is the SHA-256 of the canonical JSON without
  summary_id. The object is immutable and every read returns a deep copy. from_dict and
  load_value_flow_demo_summary re-verify summary_id, the contract's own rule text and the
  document's internal consistency, and reject any difference. render_lines() returns
  plain text for display; it is derived from the document at call time and is never part
  of it, so it cannot influence summary_id.

ERRORS
  ValueFlowDemoSummaryError(ValueError) with .code and .diagnostics.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path

from .provenance import canonical_json, hash_config
from .validation import validate_named
from .value_flow_transfer import (
    ACCEPTED, REJECTED, UNAVAILABLE, VALUE_NAMES, ValueFlowEnvelope, ValueFlowOutcome,
    ValueFlowReceipt,
)

SCHEMA_VERSION = "value_flow_demo_summary/1"
ENVELOPE_CONTRACT = "value_flow_envelope/1"
RECEIPT_CONTRACT = "value_flow_receipt/1"
_IDENTITY_FIELDS = ("quantity_id", "quantity_definition_id", "context", "category", "unit", "scale")
_REFERENCE_FIELDS = ("reference_id", "kind", "result_id", "quantity_definition_id", "unit", "value")

_RULES = {
    "arithmetic": "none; every value is copied verbatim from the envelope or the receipt",
    "authority": "the receipt states the outcome and the envelope states the values; this module adds neither",
    "exclusions": "no filesystem path, notebook state, timestamp or environment value enters the document",
    "immutability": "the summary is frozen after construction and is returned only as a deep copy",
    "outcomes": "ACCEPTED, UNAVAILABLE and REJECTED are carried through unchanged and stay distinct",
    "identity": "summary_id is the SHA-256 of the canonical JSON of the document without summary_id",
    "rendering": "render_lines derives display text at call time and is never part of the document",
}


class ValueFlowDemoSummaryError(ValueError):
    """Malformed input or document. No partial summary exists."""

    def __init__(self, code, message):
        self.code = code
        self.diagnostics = [{"severity": "error", "code": code, "message": message}]
        super().__init__(f"{code}: {message}")


def _contract(message):
    return ValueFlowDemoSummaryError("CONTRACT_INVALID", message)


def _invalid(message):
    return ValueFlowDemoSummaryError("SUMMARY_INVALID", message)


def _carried_value(envelope_data, name):
    """The envelope's entry for one output name, or None when it carries none."""
    if envelope_data is None:
        return None
    carried = envelope_data["values"].get(name)
    if carried is None:
        return None
    return {**{key: carried[key] for key in _IDENTITY_FIELDS}, "value": carried["value"]}


def _document(envelope_data, receipt_data):
    """The summary for one use event. Every field is copied; none is derived or combined."""
    references = [] if envelope_data is None else envelope_data["measurement_references"]
    configuration = None if envelope_data is None else envelope_data["configuration"]
    document = {
        "schema_version": SCHEMA_VERSION,
        "sources": {"envelope_contract": None if envelope_data is None else ENVELOPE_CONTRACT,
                    "receipt_contract": RECEIPT_CONTRACT,
                    "receipt_id": receipt_data["receipt_id"]},
        "status": {"outcome": receipt_data["outcome"], "reason": receipt_data["reason"],
                   "detail": receipt_data["detail"]},
        "identity_chain": {
            "producer_result_id": receipt_data["chain"]["producer_result_id"],
            "envelope_id": receipt_data["chain"]["envelope_id"],
            "consumer_id": receipt_data["chain"]["consumer_id"],
            "export_id": receipt_data["chain"]["export_id"],
            "f01_reference_result_ids": [r["result_id"] for r in references],
            "profile_id": None if configuration is None else configuration["profile_id"],
            "profile_version": None if configuration is None else configuration["profile_version"],
            "configuration_hash": None if configuration is None else configuration["configuration_hash"],
        },
        "quantities": {
            **{name: _carried_value(envelope_data, name) for name in VALUE_NAMES},
            "referenced_distance_nm": [{key: r[key] for key in _REFERENCE_FIELDS} for r in references],
        },
        "integrity": {
            "stage_checks": deepcopy(receipt_data["checks"]),
            "identity_checks": None if envelope_data is None else deepcopy(envelope_data["identity_checks"]),
            "expected": deepcopy(receipt_data["expected"]),
            "observed": deepcopy(receipt_data["observed"]),
        },
        "rules": dict(_RULES),
    }
    document["summary_id"] = hash_config(document)
    validate_named(document, "value_flow_demo_summary")
    return document


def _verified(data):
    """Re-verify identity, the contract's rule text and the document's internal consistency.

    The consistency conditions restate what value_flow_envelope/1 and value_flow_receipt/1
    already guarantee; no new acceptance rule is introduced here.
    """
    try:
        validate_named(data, "value_flow_demo_summary")
    except ValueError as exc:
        raise _invalid(str(exc)) from None
    without = {key: value for key, value in data.items() if key != "summary_id"}
    if hash_config(without) != data["summary_id"]:
        raise _invalid("summary_id does not match the canonical document")
    if data["rules"] != _RULES:
        raise _invalid("rules differ from the contract's own text")
    outcome = data["status"]["outcome"]
    rejected = outcome == REJECTED
    chain, quantities, integrity = data["identity_chain"], data["quantities"], data["integrity"]
    if rejected != (chain["envelope_id"] is None):
        raise _invalid("an envelope identity exists exactly when the outcome is not REJECTED")
    if rejected != (integrity["identity_checks"] is None):
        raise _invalid("envelope identity checks exist exactly when the outcome is not REJECTED")
    if rejected != (data["sources"]["envelope_contract"] is None):
        raise _invalid("an envelope contract is named exactly when the outcome is not REJECTED")
    for name in VALUE_NAMES:
        carried = quantities[name]
        if (outcome == ACCEPTED) != (carried is not None):
            raise _invalid(f"{name} is carried exactly when the outcome is ACCEPTED")
        if carried is not None and type(carried["value"]) is not float:
            raise _invalid(f"{name} must carry a binary64 value")
    if (outcome == ACCEPTED) != (data["status"]["reason"] is None):
        raise _invalid("a reason is recorded exactly when the outcome is not ACCEPTED")
    if rejected and quantities["referenced_distance_nm"]:
        raise _invalid("a REJECTED summary carries no measurement reference")
    if [r["result_id"] for r in quantities["referenced_distance_nm"]] != chain["f01_reference_result_ids"]:
        raise _invalid("the referenced result identities disagree with the identity chain")
    return deepcopy(data)


@dataclass(frozen=True)
class ValueFlowDemoSummary:
    """An immutable value_flow_demo_summary/1 document for one completed transfer."""

    data: dict

    def __post_init__(self):
        object.__setattr__(self, "data", _verified(self.data))

    @classmethod
    def from_dict(cls, data):
        return cls(data)

    @property
    def summary_id(self):
        return self.data["summary_id"]

    @property
    def outcome(self):
        return self.data["status"]["outcome"]

    def to_dict(self):
        return deepcopy(self.data)

    def to_json_bytes(self):
        return canonical_json(self.data)

    def render_lines(self):
        """Plain display text derived at call time; never part of the document."""
        data = self.data
        chain, quantities = data["identity_chain"], data["quantities"]
        lines = [f"contract        {data['schema_version']}",
                 f"summary_id      {data['summary_id']}",
                 f"outcome         {data['status']['outcome']}"]
        if data["status"]["reason"] is not None:
            lines.append(f"reason          {data['status']['reason']}")
        if data["status"]["detail"] is not None:
            lines.append(f"detail          {data['status']['detail']}")
        lines.append("identity chain")
        for label, key in (("producer result", "producer_result_id"), ("envelope", "envelope_id"),
                           ("consumer", "consumer_id"), ("export", "export_id"),
                           ("profile id", "profile_id"), ("profile version", "profile_version"),
                           ("configuration", "configuration_hash")):
            lines.append(f"  {label:<16} {chain[key]}")
        for result_id in chain["f01_reference_result_ids"]:
            lines.append(f"  {'f01 reference':<16} {result_id}")
        lines.append("quantities")
        for name in VALUE_NAMES:
            carried = quantities[name]
            lines.append(f"  {name:<16} not carried" if carried is None
                         else f"  {name:<16} {carried['value']!r} {carried['unit']} "
                              f"({carried['quantity_definition_id']})")
        for reference in quantities["referenced_distance_nm"]:
            lines.append(f"  {reference['quantity_definition_id']:<16} {reference['value']!r} "
                         f"{reference['unit']} (reference {reference['reference_id']})")
        lines.append("stage checks")
        for check in data["integrity"]["stage_checks"]:
            lines.append(f"  {check['stage']:<30} {check['result']}")
        if data["integrity"]["identity_checks"] is not None:
            lines.append("identity checks")
            for check in data["integrity"]["identity_checks"]:
                lines.append(f"  {check['name']:<30} {check['result']}")
        return lines


def build_demo_summary(*, envelope, receipt):
    """Summarize one completed transfer. envelope is None exactly when the outcome is REJECTED."""
    if not isinstance(receipt, ValueFlowReceipt):
        raise _contract("receipt must be a ValueFlowReceipt")
    if envelope is not None and not isinstance(envelope, ValueFlowEnvelope):
        raise _contract("envelope must be a ValueFlowEnvelope or None")
    ValueFlowOutcome(envelope, receipt)  # the existing pairing invariant is the sole authority
    return ValueFlowDemoSummary(_document(None if envelope is None else envelope.to_dict(),
                                          receipt.to_dict()))


def summarize_outcome(outcome):
    """Summarize a ValueFlowOutcome as returned by transfer_value_flow."""
    if not isinstance(outcome, ValueFlowOutcome):
        raise _contract("outcome must be a ValueFlowOutcome")
    return build_demo_summary(envelope=outcome.envelope, receipt=outcome.receipt)


def load_value_flow_demo_summary(path):
    """Strictly parse and verify an exported value_flow_demo_summary/1 document."""
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
        raise _invalid(f"{path}: {exc}") from None
    return ValueFlowDemoSummary.from_dict(data)
