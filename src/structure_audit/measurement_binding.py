"""Opt-in provenance binding of one explicitly selected producer record to one
pointwise_measurement call (contract measurement_binding/1).

Standard library plus existing structure_audit helpers; no import-time I/O. Exactly one
file is opened: the explicitly selected artifact. Nothing is discovered, globbed,
converted, executed or fetched, no directory is scanned and no latest output is looked
up. pointwise_measurement is called unchanged and is not re-implemented here: this layer
supplies its envelope and records where every number came from.

WHAT IS BOUND
  Card F02 needs two declared pair scalars: distance_nm (nm, finite >= 0) and
  segment_count (dimensionless, finite > 0). They are read from two explicitly named
  metrics of one explicitly selected CandidateEvidence record. No value is derived from
  coordinates, reconstructed geometry, an angstrom quantity, a confidence quantity or
  any other metric: the producer must already declare the two quantities with the
  required units. Units are compared, never converted.

INPUTS (JSON data; a malformed envelope raises MeasurementBindingError CONTRACT_INVALID)
  selection   = {artifact_id, path, sha256, layout}
      One explicitly selected producer export. path is the absolute canonical path of a
      regular file (no relative part, no symlink alias); sha256 is the declared SHA-256
      of its bytes. layout is declared, never sniffed:
          candidate_evidence_v1        one serialized CandidateEvidence record
          candidate_evidence_list_v1   a JSON array of serialized CandidateEvidence records
  selector    = {candidate_id, target_id, conformer_id}
      Selects exactly one record. No match is SELECTOR_NOT_FOUND, several is
      SELECTOR_AMBIGUOUS; neither falls back to a first or latest record.
  binding     = {distance_nm: entry, segment_count: entry}, exactly these two
      entry = {metric_name, category, scale}. The metric is selected by
      (declaration.context, metric_name). Its category, scale and unit must equal the
      declared category, the declared scale and the unit card F02 requires for that
      input, otherwise QUANTITY_DEFINITION_INCOMPATIBLE.
  declaration = the pointwise_measurement declaration {pair_id, context, category, scale}
  parameters  = the pointwise_measurement coefficient profile
  activation  = the pointwise_measurement activation; this layer never activates the
                experimental lane on its own
  run         = {pipeline_run_id, execution_id}
      Consumer-side execution identities. A CandidateEvidence export declares none, so
      these identify this execution and are never taken from a filename or environment.

ORDER (the first failure stops; no binding and no measurement exist)
  1 the selected path is absolute, canonical and a regular file
  2 the bytes are read once and hashed; the digest must equal selection.sha256
  3 strict JSON (UTF-8, no duplicate key, no NaN/Infinity); the observed layout must
    equal the declared layout; every record passes the candidate_evidence schema and
    the CandidateEvidence invariants
  4 the selector matches exactly one record
  5 each bound metric's category, unit and scale equal the declaration
  6 the pointwise envelope is built and measure_pointwise is called unchanged
  7 the file is re-hashed; a difference is ARTIFACT_CHANGED

AVAILABILITY OF A BOUND INPUT (the measurement, not this layer, judges the number)
  metric absent                -> UNAVAILABLE, reason METRIC_ABSENT
  metric value null            -> UNAVAILABLE, reason VALUE_UNAVAILABLE plus the
                                  producer missing_reason
  metric value present         -> AVAILABLE, carried verbatim; the frozen layer decides
                                  whether it is finite, exactly representable and inside
                                  its domain
  An unavailable input yields a measurement with status UNAVAILABLE; a malformed or
  out-of-domain number yields REJECTED. No value is invented, defaulted or coerced.

PROVENANCE
  Every Astra section 4 field is recorded as {value, unavailable_reason}. A field this
  artifact cannot honestly supply carries a null value and its reason; it is never
  inferred from a filename, the environment or another run. payload_sha256 and
  mapping_hash are SHA-256 of the canonical JSON of the bound payload and of the
  declared mapping. The measurement's own provenance.source is the selected artifact,
  whose bytes were hashed here; the producer-declared upstream source of the two metrics
  is preserved separately and is not re-opened or verified.

OUTPUT
  bind_pointwise_measurement returns BoundMeasurement(binding, measurement).
  binding.to_dict() conforms to schemas/measurement_binding.schema.json and
  to_json_bytes() is provenance.canonical_json of it; binding_id is the SHA-256 of the
  canonical JSON of the document without binding_id. Constructing a MeasurementBinding
  (from_dict, load_measurement_binding) re-derives the bound inputs, the provenance, the
  measurement request and binding_id, re-runs measure_pointwise on the recorded request
  and rejects any difference (BINDING_INVALID). The measurement document verifies itself.

  bound_candidate_evidence returns one CandidateEvidence carrying the measurement as
  metrics, with the selected record's identity. Writing it with provenance.write_json_new
  gives a candidate_evidence_v1 artifact that quantity_summary and linked_transfer accept
  with no special case; neither layer is changed.

ERRORS
  MeasurementBindingError(ValueError) with .code and .diagnostics; no partial binding.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import re

from . import pointwise_measurement as pointwise
from .evidence import CandidateEvidence
from .pointwise_measurement import measure_pointwise, to_candidate_evidence_metric
from .provenance import canonical_json, hash_config, hash_file
from .quantity_summary import (  # shared strict ingestion; quantity_summary is unchanged
    LAYOUTS, QuantitySummaryError, _label, _quantity, _read_artifact, _records,
    _strict_json, _text, _value_record,
)
from .validation import validate_named

SCHEMA_VERSION = "measurement_binding/1"
METHOD_ID = "candidate_evidence_pair_binding"
METHOD_VERSION = "measurement_binding/1"

INPUT_NAMES = tuple(sorted(pointwise.INPUT_SPEC))
REQUIRED_UNIT = {name: pointwise.INPUT_SPEC[name][1] for name in INPUT_NAMES}
QUANTITY_DEFINITION_ID = {name: pointwise.INPUT_SPEC[name][0] for name in INPUT_NAMES}

_SELECTION_FIELDS = ("artifact_id", "path", "sha256", "layout")
_SELECTOR_FIELDS = ("candidate_id", "target_id", "conformer_id")
_BINDING_ENTRY_FIELDS = ("metric_name", "category", "scale")
_RUN_FIELDS = ("pipeline_run_id", "execution_id")
_MODEL_FIELDS = ("model_id", "checkpoint_id", "seed")
_SOURCE_FIELDS = ("path", "sha256", "row")
_NULL_MODEL = {"model_id": None, "checkpoint_id": None, "seed": None}
_HEX64 = re.compile(r"[a-f0-9]{64}")
_CONFLICT_CODE = {"upstream_source": "SOURCE_IDENTITY_CONFLICT",
                  "producer_provenance": "PRODUCER_PROVENANCE_CONFLICT"}

_PROVENANCE_FIELDS = (
    "pipeline_run_id", "execution_id", "producer_result_id", "payload_sha256",
    "artifact_id", "artifact_sha256", "mapping_hash", "producer_config_hash",
    "source_hash", "source", "method_id", "method_version",
    "measurement_method_id", "measurement_method_version",
    "canonicalization_version", "runtime_versions",
)
_UNAVAILABLE = {
    "producer_result_id":
        "a candidate_evidence export declares no producer result identity",
    "producer_config_hash":
        "a candidate_evidence export declares no producer configuration",
    "runtime_versions":
        "a runtime version is an environment value and would break byte-stability",
}
_RULES = {
    "selection": "one explicitly selected producer artifact; no discovery, glob, default or latest-output lookup",
    "reading": "the selected file is the only file opened; its bytes are hashed once before and once after use",
    "compatibility": "each bound metric's category, unit and scale equal the declaration; units are compared, never converted",
    "derivation": "distance_nm and segment_count are read from declared metrics only; no coordinate, geometry or unit conversion",
    "availability": "an absent metric or a null metric value is an unavailable declared input, never a substituted value",
    "measurement": "measure_pointwise is called unchanged; this layer adds no arithmetic, aggregate or ordering",
    "provenance": "every section 4 field is {value, unavailable_reason}; an unsupplied field is null with its reason",
    "identity": "binding_id = SHA-256 of the canonical JSON of the document without binding_id",
}


class MeasurementBindingError(ValueError):
    """Malformed contract, artifact or document. No partial binding exists."""

    def __init__(self, code, message):
        self.code = code
        self.diagnostics = [{"severity": "error", "code": code, "message": message}]
        super().__init__(f"{code}: {message}")


@contextmanager
def _as_binding_error():
    try:
        yield
    except QuantitySummaryError as exc:
        raise MeasurementBindingError(exc.code, exc.diagnostics[0]["message"]) from None
    except pointwise.PointwiseMeasurementError as exc:
        raise MeasurementBindingError(exc.code, exc.diagnostics[0]["message"]) from None


def _exact_fields(obj, names, what, code="CONTRACT_INVALID"):
    if not isinstance(obj, dict) or set(obj) != set(names):
        raise MeasurementBindingError(code, f"{what} must have exactly the fields {sorted(names)}")


def _invalid(message):
    return MeasurementBindingError("BINDING_INVALID", message)


def _selection(selection, code="CONTRACT_INVALID"):
    _exact_fields(selection, _SELECTION_FIELDS, "selection", code)
    with _as_binding_error():
        _label(selection["artifact_id"], "selection.artifact_id", code)
        _text(selection["path"], "selection.path", code=code)
    if type(selection["sha256"]) is not str or _HEX64.fullmatch(selection["sha256"]) is None:
        raise MeasurementBindingError(code, "selection.sha256 must be a lowercase SHA-256")
    if selection["layout"] not in LAYOUTS:
        raise MeasurementBindingError(code, f"selection.layout must be one of {list(LAYOUTS)}")
    return {key: selection[key] for key in _SELECTION_FIELDS}


def _selector(selector, code="CONTRACT_INVALID"):
    _exact_fields(selector, _SELECTOR_FIELDS, "selector", code)
    with _as_binding_error():
        _text(selector["candidate_id"], "selector.candidate_id", code=code)
        for key in ("target_id", "conformer_id"):
            _text(selector[key], f"selector.{key}", nullable=True, code=code)
    return {key: selector[key] for key in _SELECTOR_FIELDS}


def _binding(binding, code="CONTRACT_INVALID"):
    _exact_fields(binding, INPUT_NAMES, "binding", code)
    entries = {}
    for name in INPUT_NAMES:
        entry = binding[name]
        _exact_fields(entry, _BINDING_ENTRY_FIELDS, f"binding.{name}", code)
        with _as_binding_error():
            _text(entry["metric_name"], f"binding.{name}.metric_name", code=code)
            _text(entry["category"], f"binding.{name}.category", code=code)
            _text(entry["scale"], f"binding.{name}.scale", nullable=True, code=code)
        entries[name] = {key: entry[key] for key in _BINDING_ENTRY_FIELDS}
    return entries


def _run(run, code="CONTRACT_INVALID"):
    _exact_fields(run, _RUN_FIELDS, "run", code)
    with _as_binding_error():
        for key in _RUN_FIELDS:
            _label(run[key], f"run.{key}", code)
    return {key: run[key] for key in _RUN_FIELDS}


def _mapping(selection, selector, binding, declaration, code="CONTRACT_INVALID"):
    """The declared field mapping; mapping_hash is the SHA-256 of its canonical JSON."""
    with _as_binding_error():
        checked = pointwise._declaration(declaration, code)
    return {"layout": selection["layout"], "selector": _selector(selector, code),
            "binding": _binding(binding, code), "declaration": checked,
            "required_units": dict(REQUIRED_UNIT),
            "quantity_definition_ids": dict(QUANTITY_DEFINITION_ID)}


def _select_record(records, selector, artifact_id):
    matches = [(index, record) for index, record in enumerate(records)
               if tuple(record[key] for key in _SELECTOR_FIELDS) == tuple(selector[key]
                                                                          for key in _SELECTOR_FIELDS)]
    triple = tuple(selector[key] for key in _SELECTOR_FIELDS)
    if not matches:
        raise MeasurementBindingError(
            "SELECTOR_NOT_FOUND", f"{artifact_id}: no record has (candidate_id, target_id, conformer_id) {triple}")
    if len(matches) > 1:
        raise MeasurementBindingError(
            "SELECTOR_AMBIGUOUS",
            f"{artifact_id}: {len(matches)} records have (candidate_id, target_id, conformer_id) {triple}")
    return matches[0]


def _payload(records, selection, mapping):
    """The exact subset of the artifact that flows into the measurement."""
    index, record = _select_record(records, mapping["selector"], selection["artifact_id"])
    metrics, located = {}, {}
    for name in INPUT_NAMES:
        entry = mapping["binding"][name]
        quantity = {"quantity_id": name, "context": mapping["declaration"]["context"],
                    "category": entry["category"], "unit": REQUIRED_UNIT[name],
                    "scale": entry["scale"]}
        with _as_binding_error():
            _quantity(quantity, "CONTRACT_INVALID")
            found = _value_record({"artifact_id": selection["artifact_id"],
                                   "metric_name": entry["metric_name"]}, index, record, quantity)
        located[name] = found
        metrics[name] = (None if found["metric_index"] is None
                         else deepcopy(record["metrics"][found["metric_index"]]))
    return {"record_index": index, "record_count": len(records),
            "record_identity": {key: record[key] for key in _SELECTOR_FIELDS},
            "metric_indices": {name: located[name]["metric_index"] for name in INPUT_NAMES},
            "absent_detail": {name: (located[name]["exclusion_detail"]
                                     if located[name]["exclusion_reason"] == "METRIC_ABSENT" else None)
                              for name in INPUT_NAMES},
            "metrics": metrics}


def _bound_inputs(mapping, payload):
    """Derived: one binding record per card F02 input. Pure in (mapping, payload)."""
    bound = {}
    for name in INPUT_NAMES:
        entry = mapping["binding"][name]
        metric = payload["metrics"][name]
        base = {"metric_name": entry["metric_name"],
                "metric_index": payload["metric_indices"][name],
                "quantity_definition_id": QUANTITY_DEFINITION_ID[name],
                "required_unit": REQUIRED_UNIT[name],
                "declared_category": entry["category"], "declared_scale": entry["scale"]}
        if metric is None:
            bound[name] = {**base, "declared_unit": None, "availability": pointwise.UNAVAILABLE,
                           "unavailable_reason": f"METRIC_ABSENT: {payload['absent_detail'][name]}",
                           "bound_value": None, "upstream_source": None, "producer_provenance": None}
            continue
        common = {**base, "declared_unit": metric["unit"],
                  "upstream_source": deepcopy(metric["source"]),
                  "producer_provenance": deepcopy(metric["provenance"])}
        if metric["value"] is None:
            bound[name] = {**common, "availability": pointwise.UNAVAILABLE,
                           "unavailable_reason": f"VALUE_UNAVAILABLE: {metric['missing_reason']}",
                           "bound_value": None}
        else:
            bound[name] = {**common, "availability": pointwise.AVAILABLE,
                           "unavailable_reason": None, "bound_value": metric["value"]}
    return bound


def _agreed(bound, key):
    """The single value the available bound inputs declare for key, or None when none does."""
    declared = [entry[key] for entry in bound.values() if entry[key] is not None]
    if not declared:
        return None
    first = canonical_json(declared[0])
    if any(canonical_json(other) != first for other in declared[1:]):
        raise MeasurementBindingError(
            _CONFLICT_CODE[key],
            f"the bound metrics declare different {key} values; one pair cannot carry two")
    return deepcopy(declared[0])


def _provenance(mapping, payload, producer, run, bound):
    """Derived: the Astra section 4 set, each field as {value, unavailable_reason}."""
    source = _agreed(bound, "upstream_source")
    available = {
        "pipeline_run_id": run["pipeline_run_id"], "execution_id": run["execution_id"],
        "payload_sha256": hash_config(payload), "artifact_id": producer["artifact_id"],
        "artifact_sha256": producer["artifact_sha256"], "mapping_hash": hash_config(mapping),
        "source_hash": None if source is None else source["sha256"],
        "source": source, "method_id": METHOD_ID, "method_version": METHOD_VERSION,
        "measurement_method_id": pointwise.FORMULATION_ID,
        "measurement_method_version": pointwise.FORMULATION_VERSION,
        "canonicalization_version": pointwise.CANONICALIZATION_VERSION,
    }
    absent = "no bound metric declares an upstream source"
    reasons = {**_UNAVAILABLE, "source": absent, "source_hash": absent}
    return {field: {"value": available.get(field),
                    "unavailable_reason": None if available.get(field) is not None else reasons[field]}
            for field in _PROVENANCE_FIELDS}


def _request(mapping, activation, parameters, provenance, bound, producer):
    """Derived: the exact keyword payload handed to the unchanged measure_pointwise."""
    inputs = {}
    for name in INPUT_NAMES:
        entry = bound[name]
        available = entry["availability"] == pointwise.AVAILABLE
        inputs[name] = {"quantity_definition_id": entry["quantity_definition_id"],
                        "unit": entry["declared_unit"] if available else entry["required_unit"],
                        "availability": entry["availability"],
                        "unavailable_reason": None if available else entry["unavailable_reason"],
                        "value": entry["bound_value"] if available else None}
    model = _agreed(bound, "producer_provenance") or dict(_NULL_MODEL)
    return {"activation": deepcopy(activation), "declaration": deepcopy(mapping["declaration"]),
            "inputs": inputs, "parameters": deepcopy(parameters),
            "provenance": {"pipeline_run_id": provenance["pipeline_run_id"]["value"],
                           "execution_id": provenance["execution_id"]["value"],
                           "method_id": pointwise.FORMULATION_ID,
                           "method_version": pointwise.FORMULATION_VERSION,
                           "canonicalization_version": pointwise.CANONICALIZATION_VERSION,
                           "source": {"path": producer["selected_path"],
                                      "sha256": producer["artifact_sha256"], "row": None},
                           "model": model}}


def _assemble(mapping, payload, producer, run, activation, parameters):
    """The complete document plus its measurement; every other field is derived here,
    for new and reloaded bindings alike."""
    bound = _bound_inputs(mapping, payload)
    provenance = _provenance(mapping, payload, producer, run, bound)
    request = _request(mapping, activation, parameters, provenance, bound, producer)
    with _as_binding_error():
        measurement = measure_pointwise(**deepcopy(request))
    document = {
        "schema_version": SCHEMA_VERSION,
        "mapping": deepcopy(mapping),
        "payload": deepcopy(payload),
        "producer": deepcopy(producer),
        "run": deepcopy(run),
        "measurement_activation": deepcopy(activation),
        "measurement_parameters": deepcopy(parameters),
        "bound_inputs": bound,
        "provenance": provenance,
        "measurement_request": request,
        "measurement": {"schema_version": measurement.to_dict()["schema_version"],
                        "result_id": measurement.result_id, "status": measurement.status},
        "rules": dict(_RULES),
    }
    document["binding_id"] = hash_config(document)
    return document, measurement


def _verified(data):
    try:
        validate_named(data, "measurement_binding")
    except ValueError as exc:
        raise _invalid(str(exc)) from None
    rebuilt, measurement = _assemble(
        _mapping({"layout": data["mapping"]["layout"]}, data["mapping"]["selector"],
                 data["mapping"]["binding"], data["mapping"]["declaration"], "BINDING_INVALID"),
        data["payload"], data["producer"], _run(data["run"], "BINDING_INVALID"),
        data["measurement_activation"], data["measurement_parameters"])
    if canonical_json(rebuilt) != canonical_json(data):
        differing = sorted(k for k in rebuilt if canonical_json(rebuilt[k]) != canonical_json(data[k]))
        raise _invalid(f"fields differ from their re-derivation: {differing}")
    return rebuilt, measurement


@dataclass(frozen=True)
class MeasurementBinding:
    """A verified measurement_binding/1 document for exactly one selected record."""

    data: dict

    def __post_init__(self):
        verified, measurement = _verified(self.data)
        object.__setattr__(self, "data", verified)
        object.__setattr__(self, "_measurement", measurement)

    @classmethod
    def from_dict(cls, data):
        return cls(data)

    @property
    def binding_id(self):
        return self.data["binding_id"]

    @property
    def measurement(self):
        """The measurement re-derived from the recorded request; its result_id is verified."""
        return self._measurement

    def to_dict(self):
        return deepcopy(self.data)

    def to_json_bytes(self):
        return canonical_json(self.data)


@dataclass(frozen=True)
class BoundMeasurement:
    """One binding document and the measurement produced by the unchanged frozen layer."""

    binding: MeasurementBinding
    measurement: pointwise.PointwiseMeasurement


def bind_pointwise_measurement(*, selection, selector, binding, declaration, parameters,
                               activation, run):
    """Bind one explicitly selected producer record to one pointwise_measurement call."""
    chosen = _selection(selection)
    mapping = _mapping(chosen, selector, binding, declaration)
    declared_run = _run(run)
    with _as_binding_error():
        path, data = _read_artifact(chosen)
        records = _records(_strict_json(data, chosen["artifact_id"], "ARTIFACT_PARSE_ERROR"), chosen)
    payload = _payload(records, chosen, mapping)
    producer = {"artifact_id": chosen["artifact_id"], "artifact_sha256": chosen["sha256"],
                "selected_path": chosen["path"]}
    document, _ = _assemble(mapping, payload, producer, declared_run, activation, parameters)
    if hash_file(path) != chosen["sha256"]:
        raise MeasurementBindingError("ARTIFACT_CHANGED",
                                      f"{chosen['artifact_id']}: bytes changed during binding")
    bound = MeasurementBinding(document)
    return BoundMeasurement(binding=bound, measurement=bound.measurement)


def load_measurement_binding(path):
    """Strictly parse and verify an exported binding (e.g. written by write_json_new)."""
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
    return MeasurementBinding.from_dict(data)


def bound_candidate_evidence(bound, quantity_ids):
    """One CandidateEvidence carrying the measurement, with the selected record's identity.

    Written with provenance.write_json_new this is a candidate_evidence_v1 artifact that
    quantity_summary and linked_transfer read with no special case.
    """
    if not isinstance(bound, BoundMeasurement):
        raise MeasurementBindingError("CONTRACT_INVALID", "bound must be a BoundMeasurement")
    if (not isinstance(quantity_ids, (list, tuple)) or not quantity_ids
            or len(set(quantity_ids)) != len(quantity_ids)):
        raise MeasurementBindingError("CONTRACT_INVALID",
                                      "quantity_ids must be a nonempty list of distinct output names")
    data = bound.binding.to_dict()
    identity = data["payload"]["record_identity"]
    with _as_binding_error():
        metrics = [to_candidate_evidence_metric(bound.measurement, name) for name in quantity_ids]
    missing = {"sequence_hash": "this layer binds declared scalars and reads no sequence"}
    for key in ("target_id", "conformer_id"):
        if identity[key] is None:
            missing[key] = f"the selected producer record declares a null {key}"
    return CandidateEvidence(
        candidate_id=identity["candidate_id"], sequence_hash=None, target_id=identity["target_id"],
        conformer_id=identity["conformer_id"], metrics=metrics,
        provenance=deepcopy(data["measurement_request"]["provenance"]["model"]),
        warnings=[f"derived measurement; binding_id {data['binding_id']}"],
        missing_values=missing)
