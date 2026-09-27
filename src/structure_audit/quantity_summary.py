"""Deterministic finite-sample summary of one declared scalar quantity (contract quantity_summary/1).

Standard library plus existing structure_audit helpers; no import-time I/O. Nothing is
discovered, written, executed or fetched. The caller selects every producer artifact
and exports the result (for example with provenance.write_json_new).

INPUTS (JSON data; missing or unexpected fields raise CONTRACT_INVALID)
  quantity = {quantity_id, context, category, unit, scale}
      The declared quantity definition, in CandidateEvidence metric vocabulary.
      quantity_id is a caller label matching [A-Za-z0-9][A-Za-z0-9_.-]{0,99};
      context is a candidate_evidence metric context; category is nonempty text;
      unit and scale are nonempty text or null. null is a declared value that
      matches only null; nothing is inferred.
  artifacts = [{artifact_id, path, sha256, layout, metric_name}, ...]   (nonempty)
      One entry per explicitly selected producer export. path is the absolute
      canonical path of a regular file (no relative part, no symlink alias);
      sha256 is the declared SHA-256 of its bytes. layout is declared, never sniffed:
          candidate_evidence_v1        one serialized CandidateEvidence record
          candidate_evidence_list_v1   a JSON array of serialized CandidateEvidence records
      metric_name names the metric that holds the quantity in this artifact's
      records; the metric is selected by (quantity.context, metric_name).
      artifact_id, path and sha256 must each be unique (ARTIFACT_DUPLICATE).

INGESTION
  Bytes are read once, hashed and compared with sha256, then parsed strictly
  (UTF-8, no duplicate keys, no NaN/Infinity). Every record must pass the
  candidate_evidence schema and the CandidateEvidence invariants. A
  (candidate_id, target_id, conformer_id) triple may occur once in the whole
  selection (DUPLICATE_OBSERVATION). Every file is re-hashed before return.

COMPATIBILITY (checked for every selected metric before any statistic)
  The metric's category, unit and scale must equal the declaration, whether or
  not its value is available; otherwise QUANTITY_DEFINITION_INCOMPATIBLE is
  raised and no summary exists.

PER-RECORD OUTCOME
  accepted                           finite numeric value, carried as float
  METRIC_ABSENT                      no metric (quantity.context, metric_name)
  VALUE_UNAVAILABLE                  metric value null; detail = producer missing_reason
  INTEGER_NOT_EXACTLY_REPRESENTABLE  integer value without an exact float

STATISTICS (accepted values only; min/median/max/mean are null when none is accepted)
  count; min; max; median over values ordered by (value, value_id): the middle
  value for odd count, lower/2 + upper/2 for even count; mean = math.fsum(values)
  / count, MEAN_NOT_FINITE when that is not finite.

OUTPUT
  QuantitySummary.to_dict() conforms to schemas/quantity_summary.schema.json;
  to_json_bytes() is provenance.canonical_json of it. producer_artifacts are
  ordered by artifact_id and values by (artifact_id, record_index). summary_id is
  the SHA-256 of the canonical JSON of the document without summary_id. Selection
  paths, timestamps, environment and call order never enter the document: equal
  artifact bytes and equal declarations give equal bytes on every runtime.
  Constructing a QuantitySummary (from_dict, load_quantity_summary) re-derives
  every derived field and summary_id and rejects any difference (SUMMARY_INVALID).

ERRORS
  QuantitySummaryError(ValueError) with .code and .diagnostics; no partial summary.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from .evidence import CandidateEvidence
from .provenance import canonical_json, hash_config, hash_file
from .validation import validate_named

SCHEMA_VERSION = "quantity_summary/1"
LAYOUTS = ("candidate_evidence_v1", "candidate_evidence_list_v1")
ACCEPTED, EXCLUDED = "accepted", "excluded"
EXCLUSION_REASONS = ("METRIC_ABSENT", "VALUE_UNAVAILABLE", "INTEGER_NOT_EXACTLY_REPRESENTABLE")
SUMMARIZED, NO_ACCEPTED_VALUES = "SUMMARIZED", "NO_ACCEPTED_VALUES"
_QUANTITY_FIELDS = ("quantity_id", "context", "category", "unit", "scale")
_SELECTION_FIELDS = ("artifact_id", "path", "sha256", "layout", "metric_name")
_DEFINITION_FIELDS = ("category", "unit", "scale")
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
_HEX64 = re.compile(r"[a-f0-9]{64}")
_RULES = {
    "selection": "explicitly selected producer artifacts only; no discovery, glob, default or latest-output lookup",
    "compatibility": "each selected metric's category, unit and scale equal the declared quantity; null matches only null",
    "ordering": "producer_artifacts by artifact_id; values by (artifact_id, record_index); call order is ignored",
    "statistics": "count, min, median, max and mean over accepted values only; null when no value is accepted",
    "median": "values ordered by (value, value_id); middle value for odd count, lower/2 + upper/2 for even count",
    "mean": "math.fsum(values) / count",
    "identity": "summary_id = SHA-256 of the canonical JSON of the document without summary_id",
}


class QuantitySummaryError(ValueError):
    """Invalid contract, artifact or document. No normal or partial summary exists."""

    def __init__(self, code, message):
        self.code = code
        self.diagnostics = [{"severity": "error", "code": code, "message": message}]
        super().__init__(f"{code}: {message}")


def _exact_fields(obj, names, what, code="CONTRACT_INVALID"):
    if not isinstance(obj, dict) or set(obj) != set(names):
        raise QuantitySummaryError(code, f"{what} must have exactly the fields {sorted(names)}")


def _label(value, what, code="CONTRACT_INVALID"):
    if type(value) is not str or _LABEL.fullmatch(value) is None:
        raise QuantitySummaryError(code, f"{what} must match [A-Za-z0-9][A-Za-z0-9_.-]{{0,99}}")
    return value


def _text(value, what, *, nullable=False, code="CONTRACT_INVALID"):
    if nullable and value is None:
        return None
    if type(value) is not str or not value.strip():
        raise QuantitySummaryError(code, f"{what} must be nonempty text{' or null' if nullable else ''}")
    return value


def _metric_contexts():
    schema = json.loads((Path(__file__).parent / "schemas" / "candidate_evidence.schema.json")
                        .read_text(encoding="utf-8"))
    return tuple(schema["properties"]["metrics"]["items"]["properties"]["context"]["enum"])


def _quantity(quantity, code="CONTRACT_INVALID"):
    _exact_fields(quantity, _QUANTITY_FIELDS, "quantity", code)
    _label(quantity["quantity_id"], "quantity.quantity_id", code)
    if type(quantity["context"]) is not str or quantity["context"] not in _metric_contexts():
        raise QuantitySummaryError(code, f"quantity.context must be one of {list(_metric_contexts())}")
    _text(quantity["category"], "quantity.category", code=code)
    for key in ("unit", "scale"):
        _text(quantity[key], f"quantity.{key}", nullable=True, code=code)
    return {key: quantity[key] for key in _QUANTITY_FIELDS}


def _selections(artifacts):
    if not isinstance(artifacts, list) or not artifacts:
        raise QuantitySummaryError("CONTRACT_INVALID", "artifacts must be a nonempty list of explicit selections")
    selections = []
    for i, entry in enumerate(artifacts):
        _exact_fields(entry, _SELECTION_FIELDS, f"artifacts[{i}]")
        _label(entry["artifact_id"], f"artifacts[{i}].artifact_id")
        if type(entry["sha256"]) is not str or _HEX64.fullmatch(entry["sha256"]) is None:
            raise QuantitySummaryError("CONTRACT_INVALID", f"artifacts[{i}].sha256 must be a lowercase SHA-256")
        if type(entry["layout"]) is not str or entry["layout"] not in LAYOUTS:
            raise QuantitySummaryError("CONTRACT_INVALID", f"artifacts[{i}].layout must be one of {list(LAYOUTS)}")
        _text(entry["metric_name"], f"artifacts[{i}].metric_name")
        if type(entry["path"]) is not str:
            raise QuantitySummaryError("CONTRACT_INVALID", f"artifacts[{i}].path must be text")
        selections.append({key: entry[key] for key in _SELECTION_FIELDS})
    for key in ("artifact_id", "path", "sha256"):
        values = [s[key] for s in selections]
        repeated = sorted({v for v in values if values.count(v) > 1})
        if repeated:
            raise QuantitySummaryError("ARTIFACT_DUPLICATE", f"{key} selected more than once: {repeated}")
    return sorted(selections, key=lambda s: s["artifact_id"])


def _read_artifact(selection):
    aid, raw = selection["artifact_id"], selection["path"]
    path = Path(raw)
    if not path.is_absolute() or os.path.abspath(raw) != raw or path.resolve() != path:
        raise QuantitySummaryError("ARTIFACT_PATH_INVALID",
                                   f"{aid}: path must be absolute and canonical, without symlink alias")
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        raise QuantitySummaryError("ARTIFACT_PATH_INVALID", f"{aid}: {exc.strerror}") from None
    if not stat.S_ISREG(mode):
        raise QuantitySummaryError("ARTIFACT_PATH_INVALID", f"{aid}: not a regular file")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != selection["sha256"]:
        raise QuantitySummaryError("ARTIFACT_HASH_MISMATCH", f"{aid}: bytes do not match the declared sha256")
    return path, data


def _strict_json(data, where, code):
    """Same strictness as validation.read_json, applied to bytes already hashed."""
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
        raise QuantitySummaryError(code, f"{where}: {exc}") from None


def _records(document, selection):
    aid = selection["artifact_id"]
    if selection["layout"] == "candidate_evidence_v1":
        if not isinstance(document, dict):
            raise QuantitySummaryError("ARTIFACT_LAYOUT_MISMATCH", f"{aid}: candidate_evidence_v1 needs one JSON object")
        records = [document]
    else:
        if not isinstance(document, list):
            raise QuantitySummaryError("ARTIFACT_LAYOUT_MISMATCH", f"{aid}: candidate_evidence_list_v1 needs a JSON array")
        records = document
    for index, record in enumerate(records):
        try:
            validate_named(record, "candidate_evidence")
            CandidateEvidence(**record).to_dict()
        except (TypeError, ValueError) as exc:
            raise QuantitySummaryError("ARTIFACT_RECORD_INVALID", f"{aid} record {index}: {exc}") from None
    return records


def _value_record(selection, index, record, quantity):
    aid, name, context = selection["artifact_id"], selection["metric_name"], quantity["context"]
    base = {"value_id": f"{aid}#{index}", "artifact_id": aid, "record_index": index,
            "candidate_id": record["candidate_id"], "target_id": record["target_id"],
            "conformer_id": record["conformer_id"], "metric_name": name}
    matches = [(i, m) for i, m in enumerate(record["metrics"]) if m["context"] == context and m["name"] == name]
    if not matches:
        elsewhere = sorted({m["context"] for m in record["metrics"] if m["name"] == name})
        detail = f"no metric ({context!r}, {name!r})" + (f"; name present in contexts {elsewhere}" if elsewhere else "")
        return {**base, "metric_index": None, "source": None, "producer_provenance": None,
                "status": EXCLUDED, "value": None, "exclusion_reason": "METRIC_ABSENT", "exclusion_detail": detail}
    (metric_index, metric), = matches  # CandidateEvidence invariants forbid a repeated (context, name)
    for key in _DEFINITION_FIELDS:
        if metric[key] != quantity[key]:
            raise QuantitySummaryError(
                "QUANTITY_DEFINITION_INCOMPATIBLE",
                f"{aid} record {index} metric {name!r}: {key} is {metric[key]!r}, declared {quantity[key]!r}")
    record_value = {**base, "metric_index": metric_index, "source": deepcopy(metric["source"]),
                    "producer_provenance": deepcopy(metric["provenance"])}
    value = metric["value"]
    if value is None:
        return {**record_value, "status": EXCLUDED, "value": None,
                "exclusion_reason": "VALUE_UNAVAILABLE", "exclusion_detail": metric["missing_reason"]}
    try:
        number = float(value)
        exact = type(value) is float or int(number) == value
    except OverflowError:
        exact = False
    if not exact:
        return {**record_value, "status": EXCLUDED, "value": None,
                "exclusion_reason": "INTEGER_NOT_EXACTLY_REPRESENTABLE",
                "exclusion_detail": f"integer {value} has no exact binary64 value"}
    return {**record_value, "status": ACCEPTED, "value": number, "exclusion_reason": None, "exclusion_detail": None}


def _statistics(accepted):
    if not accepted:
        return {"status": NO_ACCEPTED_VALUES, "count": 0, "min": None, "median": None, "max": None, "mean": None}
    values = [v["value"] for v in sorted(accepted, key=lambda v: (v["value"], v["value_id"]))]
    count, middle = len(values), len(values) // 2
    median = values[middle] if count % 2 else values[middle - 1] / 2 + values[middle] / 2
    try:
        mean = math.fsum(values) / count
    except OverflowError:
        mean = math.inf
    if not math.isfinite(mean):
        raise QuantitySummaryError("MEAN_NOT_FINITE", "the mean of the accepted values is not a finite binary64 value")
    return {"status": SUMMARIZED, "count": count, "min": values[0], "median": median, "max": values[-1], "mean": mean}


def _invalid(message):
    return QuantitySummaryError("SUMMARY_INVALID", message)


def _assemble(quantity, artifacts, values):
    """The complete document for (quantity, producer_artifacts, values); every
    other field is derived here, for new and reloaded summaries alike."""
    ids = [a["artifact_id"] for a in artifacts]
    hashes = [a["sha256"] for a in artifacts]
    if ids != sorted(set(ids)) or len(set(hashes)) != len(hashes):
        raise _invalid("producer_artifacts must be unique and ordered by artifact_id")
    for a in artifacts:
        _label(a["artifact_id"], "producer_artifacts.artifact_id", "SUMMARY_INVALID")
        if _HEX64.fullmatch(a["sha256"]) is None:
            raise _invalid("producer_artifacts.sha256 must be a lowercase SHA-256")
    expected = [(a["artifact_id"], i, a["metric_name"]) for a in artifacts for i in range(a["record_count"])]
    if [(v["artifact_id"], v["record_index"], v["metric_name"]) for v in values] != expected:
        raise _invalid("values must list every record of every artifact, ordered by (artifact_id, record_index)")
    for v in values:
        absent = v["exclusion_reason"] == "METRIC_ABSENT"
        accepted = v["status"] == ACCEPTED
        if (v["value_id"] != f"{v['artifact_id']}#{v['record_index']}"
                or accepted != (v["exclusion_reason"] is None) or accepted != (v["exclusion_detail"] is None)
                or absent != (v["metric_index"] is None) or absent != (v["source"] is None)
                or absent != (v["producer_provenance"] is None)
                or (accepted and not (type(v["value"]) is float and math.isfinite(v["value"])))
                or (not accepted and v["value"] is not None)):
            raise _invalid(f"value record {v['value_id']!r} is internally inconsistent")
    triples = [(v["candidate_id"], v["target_id"], v["conformer_id"]) for v in values]
    repeated = sorted({t for t in triples if triples.count(t) > 1}, key=repr)
    if repeated:
        raise QuantitySummaryError("DUPLICATE_OBSERVATION",
                                   f"(candidate_id, target_id, conformer_id) selected more than once: {repeated}")
    accepted = [v for v in values if v["status"] == ACCEPTED]
    document = {
        "schema_version": SCHEMA_VERSION,
        "quantity": deepcopy(quantity),
        "producer_artifacts": deepcopy(artifacts),
        "values": deepcopy(values),
        "availability": {
            "total_records": len(values),
            "accepted_count": len(accepted),
            "excluded_count": len(values) - len(accepted),
            "exclusion_reason_counts": {r: sum(v["exclusion_reason"] == r for v in values) for r in EXCLUSION_REASONS},
        },
        "statistics": _statistics(accepted),
        "rules": dict(_RULES),
    }
    document["summary_id"] = hash_config(document)
    validate_named(document, "quantity_summary")
    return document


def _verified(data):
    try:
        validate_named(data, "quantity_summary")
    except ValueError as exc:
        raise _invalid(str(exc)) from None
    rebuilt = _assemble(_quantity(data["quantity"], "SUMMARY_INVALID"), data["producer_artifacts"], data["values"])
    if canonical_json(rebuilt) != canonical_json(data):
        differing = sorted(k for k in rebuilt if canonical_json(rebuilt[k]) != canonical_json(data[k]))
        raise _invalid(f"fields differ from their re-derivation: {differing}")
    return rebuilt


@dataclass(frozen=True)
class QuantitySummary:
    """A verified quantity_summary/1 document; deliberately not a candidate iterable."""

    data: dict

    def __post_init__(self):
        object.__setattr__(self, "data", _verified(self.data))

    @classmethod
    def from_dict(cls, data):
        return cls(data)

    @property
    def summary_id(self):
        return self.data["summary_id"]

    def to_dict(self):
        return deepcopy(self.data)

    def to_json_bytes(self):
        return canonical_json(self.data)


def summarize_quantity(*, quantity, artifacts):
    """Summary of the declared quantity over the explicitly selected producer artifacts."""
    declared = _quantity(quantity)
    selections = _selections(artifacts)
    loaded, entries, values = [], [], []
    for selection in selections:
        path, data = _read_artifact(selection)
        records = _records(_strict_json(data, selection["artifact_id"], "ARTIFACT_PARSE_ERROR"), selection)
        loaded.append((path, selection))
        entries.append({"artifact_id": selection["artifact_id"], "sha256": selection["sha256"],
                        "layout": selection["layout"], "metric_name": selection["metric_name"],
                        "record_count": len(records)})
        values.extend(_value_record(selection, i, record, declared) for i, record in enumerate(records))
    summary = QuantitySummary(_assemble(declared, entries, values))
    for path, selection in loaded:
        if hash_file(path) != selection["sha256"]:
            raise QuantitySummaryError("ARTIFACT_CHANGED", f"{selection['artifact_id']}: bytes changed during summary")
    return summary


def load_quantity_summary(path):
    """Strictly parse and verify an exported summary (e.g. written by write_json_new)."""
    return QuantitySummary.from_dict(_strict_json(Path(path).read_bytes(), str(path), "SUMMARY_INVALID"))
