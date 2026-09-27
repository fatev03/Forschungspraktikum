"""Linked producer -> consumer transfer of one scalar value with a canonical receipt.

Contracts linked_transfer/1 and transfer_receipt/1. Standard library plus existing
structure_audit helpers; no import-time I/O. Nothing is discovered, written, executed,
fetched or computed beyond verification: the value is copied from the producer artifact.

INPUTS (JSON data; missing or unexpected fields raise LinkedTransferError CONTRACT_INVALID,
and no receipt exists because the expected identity itself is malformed)
  selection = {artifact_id, path, sha256, layout}
      One explicitly selected producer artifact. layout is declared, never inferred:
          candidate_evidence_v1        one serialized CandidateEvidence record
          candidate_evidence_list_v1   a JSON array of serialized CandidateEvidence records
          quantity_summary_v1          one quantity_summary/1 document
  request = {consumer_id, quantity, item}
      consumer_id labels the consumer-side use event. quantity is
      {quantity_id, context, category, unit, scale} in quantity_summary vocabulary.
      item for a CandidateEvidence layout: {metric_name, candidate_id, target_id,
      conformer_id}; the triple selects exactly one record. item for
      quantity_summary_v1: {statistic} with statistic in min, median, max, mean.

VERIFICATION ORDER (the first failure stops; later checks are NOT_REACHED)
  1 PATH_FORM          absolute canonical path of a regular file, no symlink alias
  2 BYTES_HASH         SHA-256 of the bytes read equals selection.sha256
  3 LAYOUT             strict JSON; observed layout (JSON form and schema_version)
                       equals the declared layout; then the CandidateEvidence schema
                       and invariants, or full QuantitySummary re-derivation
  4 QUANTITY_IDENTITY  CandidateEvidence: the selector matches one record and the
                       metric (quantity.context, metric_name) has the declared
                       category, unit and scale (ABSENT when the record lacks it).
                       quantity_summary: the document's quantity equals the request
                       in all five fields.
  5 PAYLOAD            ADMITTED (finite value, as float), UNAVAILABLE or EXCLUDED
  The file is re-hashed after stage 5; a difference rejects with ARTIFACT_CHANGED.
  CandidateEvidence classification is quantity_summary's: VALUE_UNAVAILABLE carries
  the producer missing_reason; METRIC_ABSENT and INTEGER_NOT_EXACTLY_REPRESENTABLE
  are EXCLUDED. A null summary statistic is UNAVAILABLE with NO_ACCEPTED_VALUES.
  No value is coerced: a payload that is not ADMITTED carries value null.

OUTPUT
  link_transfer returns TransferOutcome(receipt, transfer). Every call yields one
  TransferReceipt; a LinkedTransfer exists exactly when the outcome is not REJECTED.
  Both documents are canonical JSON (provenance.canonical_json); their ids are the
  SHA-256 of the canonical JSON without the id field. The transfer document carries
  no selection path and is location-independent; the receipt records the selected
  path as supplied. No timestamp or environment value enters either document.
  from_dict / load_* re-derive every derived field and id and reject any difference.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import stat
from typing import Optional

from .provenance import canonical_json, hash_config, hash_file
from .quantity_summary import (  # shared ingestion and classification; quantity_summary is unchanged
    LAYOUTS as EVIDENCE_LAYOUTS, QuantitySummary, QuantitySummaryError,
    _label, _quantity, _records, _strict_json, _text, _value_record,
)
from .validation import validate_named

TRANSFER_VERSION, RECEIPT_VERSION = "linked_transfer/1", "transfer_receipt/1"
SUMMARY_LAYOUT = "quantity_summary_v1"
LAYOUTS = (*EVIDENCE_LAYOUTS, SUMMARY_LAYOUT)
STATISTICS = ("min", "median", "max", "mean")
CHECKS = ("PATH_FORM", "BYTES_HASH", "LAYOUT", "QUANTITY_IDENTITY", "PAYLOAD")
OUTCOMES = ("ADMITTED", "UNAVAILABLE", "EXCLUDED", "REJECTED")
FAILURE_STAGE = {
    "ARTIFACT_PATH_INVALID": "PATH_FORM",
    "ARTIFACT_HASH_MISMATCH": "BYTES_HASH", "ARTIFACT_CHANGED": "BYTES_HASH",
    "ARTIFACT_PARSE_ERROR": "LAYOUT", "ARTIFACT_LAYOUT_MISMATCH": "LAYOUT",
    "ARTIFACT_RECORD_INVALID": "LAYOUT", "SUMMARY_INVALID": "LAYOUT",
    "QUANTITY_IDENTITY_MISMATCH": "QUANTITY_IDENTITY", "SELECTOR_NOT_FOUND": "QUANTITY_IDENTITY",
    "SELECTOR_AMBIGUOUS": "QUANTITY_IDENTITY",
}
REASON_OUTCOME = {"VALUE_UNAVAILABLE": "UNAVAILABLE", "NO_ACCEPTED_VALUES": "UNAVAILABLE",
                  "METRIC_ABSENT": "EXCLUDED", "INTEGER_NOT_EXACTLY_REPRESENTABLE": "EXCLUDED"}
_ALLOWED_RESULTS = {"PATH_FORM": ("PASSED", "FAILED"),
                    "BYTES_HASH": ("PASSED", "FAILED", "NOT_REACHED"),
                    "LAYOUT": ("PASSED", "FAILED", "NOT_REACHED"),
                    "QUANTITY_IDENTITY": ("PASSED", "FAILED", "ABSENT", "NOT_REACHED"),
                    "PAYLOAD": ("ADMITTED", "UNAVAILABLE", "EXCLUDED", "NOT_REACHED")}
_HEX64 = re.compile(r"[a-f0-9]{64}")
_DEFINITION = ("context", "category", "unit", "scale")
_PRODUCER = ("artifact_id", "sha256", "layout")
_EVIDENCE_ITEM = ("metric_name", "candidate_id", "target_id", "conformer_id")
_EVIDENCE_LOCATOR = ("record_index", "candidate_id", "target_id", "conformer_id", "metric_name",
                     "metric_index", "source", "producer_provenance")
_SUMMARY_LOCATOR = ("summary_id", "quantity_id", "statistic", "statistics_status", "count")


class LinkedTransferError(ValueError):
    """Malformed contract or document. Never used for a verification outcome."""

    def __init__(self, code, message):
        self.code = code
        self.diagnostics = [{"severity": "error", "code": code, "message": message}]
        super().__init__(f"{code}: {message}")


class _Rejected(Exception):
    def __init__(self, failure_class, detail):
        super().__init__(detail)
        self.failure_class, self.detail = failure_class, detail


@contextmanager
def _as_transfer_error():
    try:
        yield
    except QuantitySummaryError as exc:
        raise LinkedTransferError(exc.code, exc.diagnostics[0]["message"]) from None


def _require(condition, code, message):
    if not condition:
        raise LinkedTransferError(code, message)


def _exact(obj, names, what, code):
    _require(isinstance(obj, dict) and set(obj) == set(names), code,
             f"{what} must have exactly the fields {sorted(names)}")


def _hex(value, what, code):
    _require(type(value) is str and _HEX64.fullmatch(value) is not None, code, f"{what} must be a lowercase SHA-256")


# --------------------------------------------------------------------------
# Contract
# --------------------------------------------------------------------------
def _selection(selection, code="CONTRACT_INVALID"):
    _exact(selection, ("artifact_id", "path", "sha256", "layout"), "selection", code)
    with _as_transfer_error():
        _label(selection["artifact_id"], "selection.artifact_id", code)
    _require(type(selection["path"]) is str, code, "selection.path must be text")
    _hex(selection["sha256"], "selection.sha256", code)
    _require(type(selection["layout"]) is str and selection["layout"] in LAYOUTS, code,
             f"selection.layout must be one of {list(LAYOUTS)}")
    return {key: selection[key] for key in ("artifact_id", "path", "sha256", "layout")}


def _request(request, layout, code="CONTRACT_INVALID"):
    _exact(request, ("consumer_id", "quantity", "item"), "request", code)
    with _as_transfer_error():
        _label(request["consumer_id"], "request.consumer_id", code)
        quantity = _quantity(request["quantity"], code)
        item = request["item"]
        if layout == SUMMARY_LAYOUT:
            _exact(item, ("statistic",), "request.item for quantity_summary_v1", code)
            _require(type(item["statistic"]) is str and item["statistic"] in STATISTICS, code,
                     f"request.item.statistic must be one of {list(STATISTICS)}")
        else:
            _exact(item, _EVIDENCE_ITEM, "request.item for a CandidateEvidence layout", code)
            _text(item["metric_name"], "request.item.metric_name", code=code)
            _text(item["candidate_id"], "request.item.candidate_id", code=code)
            for key in ("target_id", "conformer_id"):
                _require(item[key] is None or type(item[key]) is str, code, f"request.item.{key} must be text or null")
    return {"consumer_id": request["consumer_id"], "quantity": quantity, "item": dict(item)}


# --------------------------------------------------------------------------
# Verification stages
# --------------------------------------------------------------------------
def _path_and_bytes(selection, results, observed):
    raw = selection["path"]
    path = Path(raw)
    if not path.is_absolute() or os.path.abspath(raw) != raw or path.resolve() != path:
        raise _Rejected("ARTIFACT_PATH_INVALID", "path must be absolute and canonical, without symlink alias")
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise _Rejected("ARTIFACT_PATH_INVALID", "path is not a regular file")
        data = path.read_bytes()
    except OSError as exc:
        raise _Rejected("ARTIFACT_PATH_INVALID", f"path is not readable ({type(exc).__name__})") from None
    results["PATH_FORM"] = "PASSED"
    observed["sha256"] = hashlib.sha256(data).hexdigest()
    if observed["sha256"] != selection["sha256"]:
        raise _Rejected("ARTIFACT_HASH_MISMATCH", "bytes do not match the declared sha256")
    results["BYTES_HASH"] = "PASSED"
    return path, data


def _observed_layout(document):
    if isinstance(document, list):
        return "candidate_evidence_list_v1"
    if isinstance(document, dict) and document.get("schema_version") == "quantity_summary/1":
        return SUMMARY_LAYOUT
    if isinstance(document, dict) and document.get("schema_version") == "1.0":
        return "candidate_evidence_v1"
    return "UNRECOGNIZED"


def _layout(selection, data, results, observed):
    aid, layout = selection["artifact_id"], selection["layout"]
    try:
        document = _strict_json(data, aid, "ARTIFACT_PARSE_ERROR")
    except QuantitySummaryError as exc:
        observed["layout"] = "UNPARSEABLE"
        raise _Rejected("ARTIFACT_PARSE_ERROR", exc.diagnostics[0]["message"]) from None
    observed["layout"] = _observed_layout(document)
    if observed["layout"] != layout:
        raise _Rejected("ARTIFACT_LAYOUT_MISMATCH", f"declared {layout}, observed {observed['layout']}")
    try:
        if layout == SUMMARY_LAYOUT:
            content = QuantitySummary.from_dict(document)
        else:
            content = _records(document, {"artifact_id": aid, "layout": layout})
    except QuantitySummaryError as exc:
        failure = "SUMMARY_INVALID" if layout == SUMMARY_LAYOUT else "ARTIFACT_RECORD_INVALID"
        raise _Rejected(failure, exc.diagnostics[0]["message"]) from None
    results["LAYOUT"] = "PASSED"
    return content


def _evidence_quantity(selection, request, records, results):
    item, quantity = request["item"], request["quantity"]
    selector = (item["candidate_id"], item["target_id"], item["conformer_id"])
    matches = [i for i, r in enumerate(records) if (r["candidate_id"], r["target_id"], r["conformer_id"]) == selector]
    if not matches:
        raise _Rejected("SELECTOR_NOT_FOUND", f"no record has (candidate_id, target_id, conformer_id) {list(selector)}")
    if len(matches) > 1:
        raise _Rejected("SELECTOR_AMBIGUOUS", f"records {matches} share (candidate_id, target_id, conformer_id)")
    (index,) = matches
    try:
        value = _value_record({"artifact_id": selection["artifact_id"], "metric_name": item["metric_name"]},
                              index, records[index], quantity)
    except QuantitySummaryError as exc:
        raise _Rejected("QUANTITY_IDENTITY_MISMATCH", exc.diagnostics[0]["message"]) from None
    locator = {key: value[key] for key in _EVIDENCE_LOCATOR}
    if value["exclusion_reason"] == "METRIC_ABSENT":
        results["QUANTITY_IDENTITY"] = "ABSENT"
        definition = None
    else:
        results["QUANTITY_IDENTITY"] = "PASSED"
        metric = records[index]["metrics"][value["metric_index"]]
        definition = {key: metric[key] for key in _DEFINITION}
    if value["exclusion_reason"] is None:
        payload = {"status": "ADMITTED", "value": value["value"], "reason": None}
    else:
        reason = {"code": value["exclusion_reason"], "detail": value["exclusion_detail"]}
        payload = {"status": REASON_OUTCOME[reason["code"]], "value": None, "reason": reason}
    if definition is not None:
        results["PAYLOAD"] = payload["status"]
    return None, {"verified_definition": definition, "locator": locator}, payload


def _summary_quantity(request, summary, results):
    declared, observed = request["quantity"], summary.data["quantity"]
    differing = [key for key in declared if declared[key] != observed[key]]
    if differing:
        raise _Rejected("QUANTITY_IDENTITY_MISMATCH",
                        "; ".join(f"{k} is {observed[k]!r}, requested {declared[k]!r}" for k in differing))
    results["QUANTITY_IDENTITY"] = "PASSED"
    statistic, statistics = request["item"]["statistic"], summary.data["statistics"]
    locator = {"summary_id": summary.summary_id, "quantity_id": observed["quantity_id"], "statistic": statistic,
               "statistics_status": statistics["status"], "count": statistics["count"]}
    value = statistics[statistic]
    if value is None:
        availability = summary.data["availability"]
        payload = {"status": "UNAVAILABLE", "value": None, "reason": {
            "code": "NO_ACCEPTED_VALUES",
            "detail": f"summary has no accepted values; {availability['excluded_count']} of "
                      f"{availability['total_records']} records excluded"}}
    else:
        payload = {"status": "ADMITTED", "value": value, "reason": None}
    results["PAYLOAD"] = payload["status"]
    return (summary.summary_id,
            {"verified_definition": {key: observed[key] for key in _DEFINITION}, "locator": locator}, payload)


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------
def _check_list(results):
    return [{"check": check, "result": results.get(check, "NOT_REACHED")} for check in CHECKS]


def _derive(checks, code):
    """(outcome, failure stage) of an ordered check list; impossible sequences raise."""
    _require(isinstance(checks, list) and [c.get("check") if isinstance(c, dict) else None for c in checks]
             == list(CHECKS), code, f"checks must list {list(CHECKS)} in order")
    results = [c["result"] for c in checks]
    for check, result in zip(CHECKS, results):
        _require(result in _ALLOWED_RESULTS[check], code, f"{check} cannot be {result!r}")
    stop = next(i for i, result in enumerate(results) if result != "PASSED")
    _require(results[stop] != "NOT_REACHED" and all(r == "NOT_REACHED" for r in results[stop + 1:]), code,
             "checks must pass in order up to the first non-PASSED result and be NOT_REACHED after it")
    if results[stop] == "FAILED":
        return "REJECTED", CHECKS[stop]
    return ("EXCLUDED" if results[stop] == "ABSENT" else results[stop]), None


def _finish(document, name, id_key, code):
    document[id_key] = hash_config(document)
    try:
        validate_named(document, name)
    except ValueError as exc:
        raise LinkedTransferError(code, str(exc)) from None
    return document


def _transfer_document(request, producer, identity, payload, checks, code="TRANSFER_INVALID"):
    outcome, _ = _derive(checks, code)
    _require(outcome != "REJECTED", code, "a rejected verification has no transfer document")
    summary = producer["layout"] == SUMMARY_LAYOUT
    item, definition, locator = request["item"], identity["verified_definition"], identity["locator"]
    absent = checks[CHECKS.index("QUANTITY_IDENTITY")]["result"] == "ABSENT"
    _require((producer["summary_id"] is not None) == summary, code, "summary_id is given exactly for quantity_summary_v1")
    _require(absent == (definition is None), code, "verified_definition is null exactly when the metric is ABSENT")
    _require(definition is None or definition == {k: request["quantity"][k] for k in _DEFINITION}, code,
             "verified_definition must equal the requested definition")
    _require(isinstance(locator, dict) and set(locator) == set(_SUMMARY_LOCATOR if summary else _EVIDENCE_LOCATOR),
             code, "locator fields do not match the producer layout")
    if summary:
        _require(locator["summary_id"] == producer["summary_id"] and locator["statistic"] == item["statistic"]
                 and locator["quantity_id"] == request["quantity"]["quantity_id"]
                 and (locator["statistics_status"] == "SUMMARIZED") == (payload["status"] == "ADMITTED"),
                 code, "summary locator is inconsistent with the request or payload")
    else:
        _require(all(locator[k] == item[k] for k in _EVIDENCE_ITEM)
                 and all((locator[k] is None) == absent for k in ("metric_index", "source", "producer_provenance")),
                 code, "record locator is inconsistent with the request")
    status, value, reason = payload["status"], payload["value"], payload["reason"]
    _require(status == outcome and (status == "ADMITTED") == (reason is None), code,
             "payload status and reason must agree with the checks")
    if status == "ADMITTED":
        _require(type(value) is float and math.isfinite(value), code, "an ADMITTED value is a finite float")
    else:
        _require(value is None and isinstance(reason, dict) and REASON_OUTCOME.get(reason.get("code")) == status
                 and (reason["code"] == "NO_ACCEPTED_VALUES") == summary
                 and (reason["code"] == "METRIC_ABSENT") == absent,
                 code, "a payload that is not ADMITTED carries value null and a matching reason")
    document = {"schema_version": TRANSFER_VERSION, "consumer_request": deepcopy(request),
                "producer": deepcopy(producer), "quantity_identity": deepcopy(identity),
                "payload": deepcopy(payload), "checks": deepcopy(checks)}
    return _finish(document, "linked_transfer", "transfer_id", code)


def _receipt_document(request, selected_path, expected, observed, failure, carried_reason, checks, transfer_id,
                      code="RECEIPT_INVALID"):
    outcome, stage = _derive(checks, code)
    results = {c["check"]: c["result"] for c in checks}
    rejected = outcome == "REJECTED"
    _require(rejected == (failure is not None) == (transfer_id is None), code,
             "failure is given, and transfer_id is null, exactly for REJECTED")
    _require((outcome in ("UNAVAILABLE", "EXCLUDED")) == (carried_reason is not None)
             and (carried_reason is None or REASON_OUTCOME.get(carried_reason.get("code")) == outcome),
             code, "carried_reason is given exactly for UNAVAILABLE and EXCLUDED, with a matching code")
    if failure is not None:
        _require(isinstance(failure, dict) and FAILURE_STAGE.get(failure.get("class")) == stage, code,
                 "failure class does not belong to the failed check")
        failure = {"class": failure["class"], "stage": stage, "detail": failure["detail"]}
    hash_passed = results["BYTES_HASH"] == "PASSED"
    _require((results["PATH_FORM"] == "PASSED") == (observed["sha256"] is not None)
             and hash_passed == (observed["layout"] is not None)
             and hash_passed == (observed["sha256"] == expected["sha256"]),
             code, "observed identity is inconsistent with the checks")
    if results["LAYOUT"] in ("PASSED", "FAILED"):
        layout_mismatch = failure is not None and failure["class"] == "ARTIFACT_LAYOUT_MISMATCH"
        parse_error = failure is not None and failure["class"] == "ARTIFACT_PARSE_ERROR"
        _require((observed["layout"] == "UNPARSEABLE") == parse_error
                 and (observed["layout"] != expected["layout"]) == (layout_mismatch or parse_error),
                 code, "observed layout is inconsistent with the LAYOUT check")
    document = {
        "schema_version": RECEIPT_VERSION, "consumer_request": deepcopy(request), "selected_path": selected_path,
        "expected_producer": deepcopy(expected), "observed_producer": deepcopy(observed),
        "artifact_matched_selection": None if results["PATH_FORM"] != "PASSED"
        else hash_passed and results["LAYOUT"] == "PASSED",
        "quantity_identity_matched": {"PASSED": True, "FAILED": False}.get(results["QUANTITY_IDENTITY"]),
        "outcome": outcome, "failure": failure, "carried_reason": deepcopy(carried_reason),
        "checks": deepcopy(checks), "transfer_id": transfer_id,
    }
    return _finish(document, "transfer_receipt", "receipt_id", code)


def _verified(data, schema, code, rebuild):
    try:
        validate_named(data, schema)
    except ValueError as exc:
        raise LinkedTransferError(code, str(exc)) from None
    rebuilt = rebuild(data)
    if canonical_json(rebuilt) != canonical_json(data):
        differing = sorted(k for k in rebuilt if canonical_json(rebuilt[k]) != canonical_json(data[k]))
        raise LinkedTransferError(code, f"fields differ from their re-derivation: {differing}")
    return rebuilt


def _rebuild_transfer(data):
    code = "TRANSFER_INVALID"
    producer = data["producer"]
    _selection({"artifact_id": producer["artifact_id"], "path": "", "sha256": producer["sha256"],
                "layout": producer["layout"]}, code)
    _require(producer["summary_id"] is None or _HEX64.fullmatch(producer["summary_id"]) is not None, code,
             "producer.summary_id must be a lowercase SHA-256 or null")
    request = _request(data["consumer_request"], producer["layout"], code)
    return _transfer_document(request, producer, data["quantity_identity"], data["payload"], data["checks"], code)


def _rebuild_receipt(data):
    code = "RECEIPT_INVALID"
    expected = data["expected_producer"]
    _selection({"artifact_id": expected["artifact_id"], "path": data["selected_path"],
                "sha256": expected["sha256"], "layout": expected["layout"]}, code)
    request = _request(data["consumer_request"], expected["layout"], code)
    failure = data["failure"]
    return _receipt_document(request, data["selected_path"], expected, data["observed_producer"],
                             None if failure is None else {"class": failure["class"], "detail": failure["detail"]},
                             data["carried_reason"], data["checks"], data["transfer_id"], code)


@dataclass(frozen=True)
class LinkedTransfer:
    """A verified linked_transfer/1 document."""

    data: dict

    def __post_init__(self):
        object.__setattr__(self, "data", _verified(self.data, "linked_transfer", "TRANSFER_INVALID", _rebuild_transfer))

    @classmethod
    def from_dict(cls, data):
        return cls(data)

    @property
    def transfer_id(self):
        return self.data["transfer_id"]

    def to_dict(self):
        return deepcopy(self.data)

    def to_json_bytes(self):
        return canonical_json(self.data)


@dataclass(frozen=True)
class TransferReceipt:
    """A verified transfer_receipt/1 document."""

    data: dict

    def __post_init__(self):
        object.__setattr__(self, "data", _verified(self.data, "transfer_receipt", "RECEIPT_INVALID", _rebuild_receipt))

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
class TransferOutcome:
    """One consumer-side use event: its receipt and, unless REJECTED, its transfer."""

    receipt: TransferReceipt
    transfer: Optional[LinkedTransfer]

    def __post_init__(self):
        _require(isinstance(self.receipt, TransferReceipt)
                 and (self.transfer is None or isinstance(self.transfer, LinkedTransfer)), "LINK_INVALID",
                 "receipt must be a TransferReceipt and transfer a LinkedTransfer or None")
        r = self.receipt.data
        _require((self.transfer is None) == (r["outcome"] == "REJECTED"), "LINK_INVALID",
                 "a transfer exists exactly when the receipt is not REJECTED")
        if self.transfer is not None:
            t = self.transfer.data
            linked = (r["transfer_id"] == t["transfer_id"] and r["consumer_request"] == t["consumer_request"]
                      and r["checks"] == t["checks"] and r["outcome"] == t["payload"]["status"]
                      and r["carried_reason"] == t["payload"]["reason"]
                      and r["expected_producer"] == {k: t["producer"][k] for k in _PRODUCER})
            _require(linked, "LINK_INVALID", "receipt and transfer do not describe the same use event")


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------
def link_transfer(*, selection, request):
    """Verify one explicitly selected producer artifact for one consumer request."""
    selection = _selection(selection)
    request = _request(request, selection["layout"])
    expected = {key: selection[key] for key in _PRODUCER}
    results, observed = {}, {"sha256": None, "layout": None}
    failure = transfer = None
    try:
        path, data = _path_and_bytes(selection, results, observed)
        content = _layout(selection, data, results, observed)
        if selection["layout"] == SUMMARY_LAYOUT:
            summary_id, identity, payload = _summary_quantity(request, content, results)
        else:
            summary_id, identity, payload = _evidence_quantity(selection, request, content, results)
        rehashed = hash_file(path)
        if rehashed != selection["sha256"]:
            observed.update(sha256=rehashed, layout=None)
            raise _Rejected("ARTIFACT_CHANGED", "bytes changed during verification")
    except _Rejected as rejection:
        stage = FAILURE_STAGE[rejection.failure_class]
        results = {check: results[check] for check in CHECKS[:CHECKS.index(stage)]}
        results[stage] = "FAILED"
        failure = {"class": rejection.failure_class, "detail": rejection.detail}
    checks = _check_list(results)
    if failure is None:
        producer = {**expected, "summary_id": summary_id}
        transfer = LinkedTransfer(_transfer_document(request, producer, identity, payload, checks))
    receipt = TransferReceipt(_receipt_document(
        request, selection["path"], expected, observed, failure,
        None if transfer is None else transfer.data["payload"]["reason"], checks,
        None if transfer is None else transfer.transfer_id))
    return TransferOutcome(receipt, transfer)


def _load(path, cls, code):
    try:
        data = _strict_json(Path(path).read_bytes(), str(path), code)
    except QuantitySummaryError as exc:
        raise LinkedTransferError(code, exc.diagnostics[0]["message"]) from None
    return cls.from_dict(data)


def load_linked_transfer(path):
    """Strictly parse and verify an exported linked_transfer/1 document."""
    return _load(path, LinkedTransfer, "TRANSFER_INVALID")


def load_transfer_receipt(path):
    """Strictly parse and verify an exported transfer_receipt/1 document."""
    return _load(path, TransferReceipt, "RECEIPT_INVALID")
