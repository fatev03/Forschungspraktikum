"""Opt-in pointwise evaluation of Astra card F02 for one declared pair (contract pointwise_measurement/1).

Standard library plus existing structure_audit helpers; no import-time I/O. Nothing is
discovered, read, written, executed or fetched: this layer is a pure function of its
payload. It writes no frozen-core field, forms no ordering over pairs and produces no
aggregate: the two declared arithmetic means of card F02 are outside this contract.

SELECTED FORMULATION (astra math formulation, section 3, card F02,
formulation_id pointwise_measurement_v1), evaluated for a single index i:

    m = c * n**eta                                        nm^2
    g = (3 / (2*pi*m))**1.5 * exp(-3 * d**2 / (2*m))      nm^-3
    q = kappa * g                                         U
    r = sqrt(m)                                           nm

with d the explicit pair distance (nm), n > 0 dimensionless, c in nm^2, eta
dimensionless and kappa in U*nm^3. U is the abstract concentration-like unit of the
Astra quantity dictionary (section 2). q is the dictionary quantity pointwise_scalar_u
(U, finite >= 0), carried here under the contract label ceff_m; r is reach_rms_nm
(nm, finite > 0), carried under the contract label arm_reach_nm. g is spatial_density
(nm^-3). m has no dictionary entry and is recorded as a layer-local intermediate.

INPUTS (JSON data; a malformed envelope raises PointwiseMeasurementError and no result
exists, because the declaration that a result would be attached to is itself malformed)
  activation  = {opt_in, lane, formulation_id, formulation_version}
      Exactly opt_in True, lane "experimental", formulation_id "pointwise_measurement_v1"
      and formulation_version "astra-F02/1". Any other value raises ACTIVATION_REQUIRED:
      this layer is never entered implicitly.
  declaration = {pair_id, context, category, scale}
      The output quantity identity the caller declares. category must be
      "derived_measurement" and scale must be null; context is a candidate_evidence
      metric context. Card F02 fixes no metric context, so the context is required
      explicitly and is never inferred.
  inputs      = {distance_nm: record, segment_count: record}, exactly these two
      record = {quantity_definition_id, unit, availability, unavailable_reason, value}
      distance_nm  : quantity_definition_id "distance_nm", unit "nm", finite >= 0
      segment_count: quantity_definition_id "segment_count_dimensionless",
                     unit "dimensionless", finite > 0
      availability is AVAILABLE (value supplied) or UNAVAILABLE (value null and
      unavailable_reason nonempty). Units are compared, never converted: card F02
      defines no conversion rule for these quantities.
  parameters  = {profile_id, profile_version, values: {c, eta, kappa}}
      values[name] = {unit, value}; units exactly "nm^2", "dimensionless", "U*nm^3".
      Every coefficient is explicit in the payload. Nothing is read from a module
      global, environment variable, notebook state, random source or default.
  provenance  = {pipeline_run_id, execution_id, method_id, method_version,
                 canonicalization_version, source, model}
      method_id, method_version and canonicalization_version are compared with this
      layer's own identities. source is the candidate_evidence metric source shape
      {path, sha256, row}; model is {model_id, checkpoint_id, seed}.

SUPPLIED NUMBERS
  Each supplied number is normalized once to (value, value_token): a finite int or
  float with an exact binary64 value keeps that value and a null token; anything else
  keeps a null value and an exact token (nan, inf, -inf,
  integer_not_exactly_representable, non_numeric:<type>). The token is the recorded
  reason; no value is coerced to zero, NaN, infinity or a fallback.

EVALUATION ORDER (the first failure decides the status; no later stage runs)
  1 identity      declaration category/scale/context and every input
                  quantity_definition_id and unit; parameter units
  2 availability  any input declared UNAVAILABLE
  3 domain        every supplied number finite and inside its declared domain
  4 arithmetic    m, then r, then g, then q, each guarded for overflow, underflow
                  and output domain before the next stage
  Identity precedes availability: an unavailable input still declares an identity.
  A quantity that is strictly positive in exact arithmetic but evaluates to 0.0 is
  reported as ARITHMETIC_UNDERFLOW, never carried as zero.

OUTPUT
  measure_pointwise returns a PointwiseMeasurement whose to_dict() conforms to
  schemas/pointwise_measurement.schema.json and whose to_json_bytes() is
  provenance.canonical_json of it. status is COMPUTED, UNAVAILABLE (a declared input
  is unavailable upstream) or REJECTED (malformed number, identity mismatch,
  incompatible unit, domain violation, non-finite value or arithmetic failure).
  Values exist only when status is COMPUTED; otherwise every value is null and the
  reason is carried in diagnostics and in each output's missing_reason. result_id is
  the SHA-256 of the canonical JSON of the document without result_id. No path,
  timestamp, environment value or call order enters the document. Constructing a
  PointwiseMeasurement (from_dict, load_pointwise_measurement) re-derives every
  intermediate, output, status, diagnostic and result_id from the recorded inputs and
  parameters and rejects any difference (RESULT_INVALID).

  to_candidate_evidence_metric(result, quantity_id) returns one metric mapping for an
  existing CandidateEvidence record. CandidateEvidence and its schema are unchanged.

ERRORS
  PointwiseMeasurementError(ValueError) with .code and .diagnostics; no partial result.
"""
from copy import deepcopy
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re

from .provenance import canonical_json, hash_config
from .validation import validate, validate_named

SCHEMA_VERSION = "pointwise_measurement/1"
FORMULATION_ID = "pointwise_measurement_v1"
FORMULATION_VERSION = "astra-F02/1"
SOURCE_CARD = "astra math formulation, section 3, card F02"
EVALUATION_FORM = "direct"
CANONICALIZATION_VERSION = "structure_audit.provenance.canonical_json/1"
LANE = "experimental"
CATEGORY = "derived_measurement"

COMPUTED, UNAVAILABLE, REJECTED = "COMPUTED", "UNAVAILABLE", "REJECTED"
STATUSES = (COMPUTED, UNAVAILABLE, REJECTED)
AVAILABLE = "AVAILABLE"
AVAILABILITIES = (AVAILABLE, UNAVAILABLE)

EQUATIONS = {
    "mean_square_span_nm2": "m = c * n**eta",
    "spatial_density_nm3_inverse": "g = (3 / (2*pi*m))**1.5 * exp(-3 * d**2 / (2*m))",
    "ceff_m": "q = kappa * g",
    "arm_reach_nm": "r = sqrt(m)",
}
ASSUMPTIONS = {
    "activation": "experimental lane only; explicit opt-in per call; no frozen-core field is written",
    "aggregation": "none; the two arithmetic means of card F02 are outside this contract",
    "arithmetic": "IEEE-754 binary64; math.pow, math.exp and math.sqrt of the host C library",
    "evaluation_form": "the direct expression of card F02; the logarithmic form is not used",
    "identity": "result_id = SHA-256 of the canonical JSON of the document without result_id",
    "membership": "exactly one explicitly declared pair; no pair is discovered, ordered or combined",
    "parameters": "c, eta and kappa are explicit in the payload; no global, environment or default value",
    "underflow": "a quantity strictly positive in exact arithmetic that evaluates to 0.0 is rejected, not carried",
    "units": "declared units are compared, never converted; card F02 defines no conversion rule",
}

# name -> (quantity_definition_id, unit, domain text, predicate)
INPUT_SPEC = {
    "distance_nm": ("distance_nm", "nm", "finite, >= 0", lambda v: v >= 0.0),
    "segment_count": ("segment_count_dimensionless", "dimensionless", "finite, > 0", lambda v: v > 0.0),
}
PARAMETER_UNITS = {"c": "nm^2", "eta": "dimensionless", "kappa": "U*nm^3"}
# contract label -> (astra quantity_definition_id, unit, domain text)
OUTPUT_SPEC = {
    "arm_reach_nm": ("reach_rms_nm", "nm", "finite, > 0"),
    "ceff_m": ("pointwise_scalar_u", "U", "finite, >= 0"),
}
INTERMEDIATE_SPEC = {
    "mean_square_span_nm2": ("mean_square_span_nm2", "nm^2"),
    "spatial_density_nm3_inverse": ("spatial_density", "nm^-3"),
}

_ACTIVATION_FIELDS = ("opt_in", "lane", "formulation_id", "formulation_version")
_DECLARATION_FIELDS = ("pair_id", "context", "category", "scale")
_INPUT_FIELDS = ("quantity_definition_id", "unit", "availability", "unavailable_reason", "value")
_STORED_INPUT_FIELDS = (*_INPUT_FIELDS, "value_token")
_PARAMETER_FIELDS = ("profile_id", "profile_version", "values")
_PROVENANCE_FIELDS = ("pipeline_run_id", "execution_id", "method_id", "method_version",
                      "canonicalization_version", "source", "model")
_SOURCE_FIELDS = ("path", "sha256", "row")
_MODEL_FIELDS = ("model_id", "checkpoint_id", "seed")
_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
_HEX64 = re.compile(r"[a-f0-9]{64}")

_TOKEN_CODE = {
    "nan": "INPUT_NOT_FINITE",
    "inf": "INPUT_NOT_FINITE",
    "-inf": "INPUT_NOT_FINITE",
    "integer_not_exactly_representable": "INPUT_NOT_EXACTLY_REPRESENTABLE",
}


class PointwiseMeasurementError(ValueError):
    """Malformed envelope or document. Never used for a measurement outcome."""

    def __init__(self, code, message):
        self.code = code
        self.diagnostics = [{"severity": "error", "code": code, "message": message}]
        super().__init__(f"{code}: {message}")


class _Outcome(Exception):
    """One recorded non-COMPUTED outcome; carries the status and its single reason."""

    def __init__(self, status, code, message):
        super().__init__(f"{code}: {message}")
        self.status, self.code, self.message = status, code, message


def _reject(code, message):
    return _Outcome(REJECTED, code, message)


def _exact_fields(obj, names, what, code="CONTRACT_INVALID"):
    if not isinstance(obj, dict) or set(obj) != set(names):
        raise PointwiseMeasurementError(code, f"{what} must have exactly the fields {sorted(names)}")


def _label(value, what, code="CONTRACT_INVALID"):
    if type(value) is not str or _LABEL.fullmatch(value) is None:
        raise PointwiseMeasurementError(code, f"{what} must match [A-Za-z0-9][A-Za-z0-9_.-]{{0,99}}")
    return value


def _text(value, what, *, nullable=False, code="CONTRACT_INVALID"):
    if nullable and value is None:
        return None
    if type(value) is not str or not value.strip():
        raise PointwiseMeasurementError(code, f"{what} must be nonempty text{' or null' if nullable else ''}")
    return value


def _metric_contexts():
    schema = json.loads((Path(__file__).parent / "schemas" / "candidate_evidence.schema.json")
                        .read_text(encoding="utf-8"))
    return tuple(schema["properties"]["metrics"]["items"]["properties"]["context"]["enum"])


def _metric_schema():
    schema = json.loads((Path(__file__).parent / "schemas" / "candidate_evidence.schema.json")
                        .read_text(encoding="utf-8"))
    return schema["properties"]["metrics"]["items"]


def _supplied(raw, what, code="CONTRACT_INVALID"):
    """Normalize one supplied number to (value, value_token); never coerce a value."""
    if type(raw) is bool:
        return None, "non_numeric:bool"
    if type(raw) is int:
        try:
            number = float(raw)
        except OverflowError:
            return None, "integer_not_exactly_representable"
        return (number, None) if int(number) == raw else (None, "integer_not_exactly_representable")
    if type(raw) is float:
        if math.isnan(raw):
            return None, "nan"
        if math.isinf(raw):
            return None, "inf" if raw > 0 else "-inf"
        return raw, None
    name = type(raw).__name__
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,63}", name) is None:
        raise PointwiseMeasurementError(code, f"{what} has an unrepresentable type name")
    return None, f"non_numeric:{name}"


def _activation(activation):
    _exact_fields(activation, _ACTIVATION_FIELDS, "activation", "ACTIVATION_REQUIRED")
    expected = {"opt_in": True, "lane": LANE, "formulation_id": FORMULATION_ID,
                "formulation_version": FORMULATION_VERSION}
    for key, want in expected.items():
        got = activation[key]
        if type(got) is not type(want) or got != want:
            raise PointwiseMeasurementError(
                "ACTIVATION_REQUIRED",
                f"activation.{key} must be exactly {want!r}; this layer is never entered implicitly")
    return {"opt_in": True, "lane": LANE}


def _declaration(declaration, code="CONTRACT_INVALID"):
    _exact_fields(declaration, _DECLARATION_FIELDS, "declaration", code)
    _label(declaration["pair_id"], "declaration.pair_id", code)
    _text(declaration["context"], "declaration.context", code=code)
    _text(declaration["category"], "declaration.category", code=code)
    _text(declaration["scale"], "declaration.scale", nullable=True, code=code)
    return {key: declaration[key] for key in _DECLARATION_FIELDS}


def _inputs(inputs, code="CONTRACT_INVALID"):
    _exact_fields(inputs, INPUT_SPEC, "inputs", code)
    normalized = {}
    for name in sorted(INPUT_SPEC):
        record = inputs[name]
        _exact_fields(record, _INPUT_FIELDS, f"inputs.{name}", code)
        _text(record["quantity_definition_id"], f"inputs.{name}.quantity_definition_id", code=code)
        _text(record["unit"], f"inputs.{name}.unit", code=code)
        if record["availability"] not in AVAILABILITIES:
            raise PointwiseMeasurementError(code, f"inputs.{name}.availability must be one of {list(AVAILABILITIES)}")
        _text(record["unavailable_reason"], f"inputs.{name}.unavailable_reason", nullable=True, code=code)
        if record["availability"] == UNAVAILABLE:
            if record["value"] is not None or record["unavailable_reason"] is None:
                raise PointwiseMeasurementError(
                    code, f"inputs.{name}: an unavailable input carries a null value and a reason")
            value, token = None, None
        else:
            if record["unavailable_reason"] is not None:
                raise PointwiseMeasurementError(
                    code, f"inputs.{name}: an available input carries no unavailable_reason")
            value, token = _supplied(record["value"], f"inputs.{name}.value", code)
        normalized[name] = {"quantity_definition_id": record["quantity_definition_id"],
                            "unit": record["unit"], "availability": record["availability"],
                            "unavailable_reason": record["unavailable_reason"],
                            "value": value, "value_token": token}
    return normalized


def _parameters(parameters, code="CONTRACT_INVALID"):
    _exact_fields(parameters, _PARAMETER_FIELDS, "parameters", code)
    _label(parameters["profile_id"], "parameters.profile_id", code)
    _label(parameters["profile_version"], "parameters.profile_version", code)
    _exact_fields(parameters["values"], PARAMETER_UNITS, "parameters.values", code)
    values = {}
    for name in sorted(PARAMETER_UNITS):
        entry = parameters["values"][name]
        _exact_fields(entry, ("unit", "value"), f"parameters.values.{name}", code)
        _text(entry["unit"], f"parameters.values.{name}.unit", code=code)
        value, token = _supplied(entry["value"], f"parameters.values.{name}.value", code)
        values[name] = {"unit": entry["unit"], "value": value, "value_token": token}
    return {"profile_id": parameters["profile_id"], "profile_version": parameters["profile_version"],
            "values": values}


def _provenance(provenance, code="CONTRACT_INVALID"):
    _exact_fields(provenance, _PROVENANCE_FIELDS, "provenance", code)
    _label(provenance["pipeline_run_id"], "provenance.pipeline_run_id", code)
    _label(provenance["execution_id"], "provenance.execution_id", code)
    for key, want in (("method_id", FORMULATION_ID), ("method_version", FORMULATION_VERSION),
                      ("canonicalization_version", CANONICALIZATION_VERSION)):
        if provenance[key] != want:
            raise PointwiseMeasurementError(code, f"provenance.{key} must be exactly {want!r}")
    source = provenance["source"]
    _exact_fields(source, _SOURCE_FIELDS, "provenance.source", code)
    _text(source["path"], "provenance.source.path", code=code)
    if type(source["sha256"]) is not str or _HEX64.fullmatch(source["sha256"]) is None:
        raise PointwiseMeasurementError(code, "provenance.source.sha256 must be a lowercase SHA-256")
    if not (source["row"] is None or (type(source["row"]) is int and source["row"] >= 1)):
        raise PointwiseMeasurementError(code, "provenance.source.row must be an integer >= 1 or null")
    model = provenance["model"]
    _exact_fields(model, _MODEL_FIELDS, "provenance.model", code)
    for key in ("model_id", "checkpoint_id"):
        _text(model[key], f"provenance.model.{key}", nullable=True, code=code)
    if not (model["seed"] is None or (type(model["seed"]) is int and model["seed"] >= 0)):
        raise PointwiseMeasurementError(code, "provenance.model.seed must be an integer >= 0 or null")
    return {"pipeline_run_id": provenance["pipeline_run_id"], "execution_id": provenance["execution_id"],
            "method_id": provenance["method_id"], "method_version": provenance["method_version"],
            "canonicalization_version": provenance["canonicalization_version"],
            "source": {key: source[key] for key in _SOURCE_FIELDS},
            "model": {key: model[key] for key in _MODEL_FIELDS}}


def _check_identity(declaration, inputs, parameters):
    """Stage 1. Declared quantity identities and units; nothing is converted."""
    if declaration["category"] != CATEGORY:
        raise _reject("QUANTITY_IDENTITY_MISMATCH",
                      f"declaration.category is {declaration['category']!r}, required {CATEGORY!r}")
    if declaration["scale"] is not None:
        raise _reject("QUANTITY_IDENTITY_MISMATCH",
                      f"declaration.scale is {declaration['scale']!r}, required null: the outputs are unscaled")
    if declaration["context"] not in _metric_contexts():
        raise _reject("QUANTITY_IDENTITY_MISMATCH",
                      f"declaration.context is {declaration['context']!r}, "
                      f"required one of {list(_metric_contexts())}")
    for name in sorted(INPUT_SPEC):
        definition_id, unit, _, _ = INPUT_SPEC[name]
        record = inputs[name]
        if record["quantity_definition_id"] != definition_id:
            raise _reject("QUANTITY_IDENTITY_MISMATCH",
                          f"inputs.{name}.quantity_definition_id is {record['quantity_definition_id']!r}, "
                          f"required {definition_id!r}")
        if record["unit"] != unit:
            raise _reject("UNIT_INCOMPATIBLE",
                          f"inputs.{name}.unit is {record['unit']!r}, required {unit!r}; "
                          "card F02 defines no conversion for this quantity")
    for name in sorted(PARAMETER_UNITS):
        unit = parameters["values"][name]["unit"]
        if unit != PARAMETER_UNITS[name]:
            raise _reject("UNIT_INCOMPATIBLE",
                          f"parameters.values.{name}.unit is {unit!r}, required {PARAMETER_UNITS[name]!r}")


def _check_availability(inputs):
    """Stage 2. A declared but unavailable upstream input, after its identity is checked."""
    for name in sorted(INPUT_SPEC):
        if inputs[name]["availability"] == UNAVAILABLE:
            raise _Outcome(UNAVAILABLE, "INPUT_UNAVAILABLE",
                           f"inputs.{name} is declared unavailable upstream: "
                           f"{inputs[name]['unavailable_reason']}")


def _number(entry, what, domain=None, domain_text=None):
    """Stage 3 for one supplied number: representable, finite, inside its domain."""
    if entry["value_token"] is not None:
        code = _TOKEN_CODE.get(entry["value_token"], "INPUT_NOT_NUMERIC")
        raise _reject(code, f"{what} is not a finite binary64 number: {entry['value_token']}")
    value = entry["value"]
    if domain is not None and not domain(value):
        raise _reject("INPUT_DOMAIN_VIOLATION", f"{what} is {value!r}, required {domain_text}")
    return value


def _guard(value, what):
    """One arithmetic step: no overflow, and no strictly positive quantity carried as zero."""
    if not math.isfinite(value):
        raise _reject("ARITHMETIC_OVERFLOW", f"{what} is not a finite binary64 value")
    if value == 0.0:
        raise _reject("ARITHMETIC_UNDERFLOW",
                      f"{what} underflowed to zero; it is strictly positive in exact arithmetic")
    return value


def _evaluate(inputs, parameters):
    """Stages 3 and 4. Returns (intermediates, outputs) for card F02 at one index."""
    d = _number(inputs["distance_nm"], "inputs.distance_nm.value",
                INPUT_SPEC["distance_nm"][3], INPUT_SPEC["distance_nm"][2])
    n = _number(inputs["segment_count"], "inputs.segment_count.value",
                INPUT_SPEC["segment_count"][3], INPUT_SPEC["segment_count"][2])
    c = _number(parameters["values"]["c"], "parameters.values.c.value")
    eta = _number(parameters["values"]["eta"], "parameters.values.eta.value")
    kappa = _number(parameters["values"]["kappa"], "parameters.values.kappa.value")

    try:
        span_factor = math.pow(n, eta)  # n > 0, so the exact value is strictly positive
    except OverflowError:
        raise _reject("ARITHMETIC_OVERFLOW", "n**eta is not a finite binary64 value") from None
    _guard(span_factor, "n**eta")
    m = c * span_factor
    if not math.isfinite(m):
        raise _reject("ARITHMETIC_OVERFLOW", "m = c * n**eta is not a finite binary64 value")
    if c > 0.0 and m == 0.0:
        raise _reject("ARITHMETIC_UNDERFLOW", "m = c * n**eta underflowed to zero with c > 0")
    if m <= 0.0:
        raise _reject("REACH_DOMAIN_VIOLATION",
                      f"m = c * n**eta is {m!r}; reach_rms_nm = sqrt(m) requires m > 0 "
                      "(dictionary domain: finite, > 0)")
    # m > 0 and the guard together give reach_rms_nm its dictionary domain: finite and > 0.
    r = _guard(math.sqrt(m), "r = sqrt(m)")

    # m > 0 makes the density denominator defined; it may still leave binary64 range.
    denominator = _guard(2.0 * math.pi * m, "2*pi*m")
    base = _guard(3.0 / denominator, "3 / (2*pi*m)")
    try:
        prefactor = math.pow(base, 1.5)
    except OverflowError:
        raise _reject("ARITHMETIC_OVERFLOW", "(3 / (2*pi*m))**1.5 is not a finite binary64 value") from None
    _guard(prefactor, "(3 / (2*pi*m))**1.5")
    squared = d * d
    if not math.isfinite(squared):
        raise _reject("ARITHMETIC_OVERFLOW", "d**2 is not a finite binary64 value")
    exponent = -3.0 * squared / (2.0 * m)
    if not math.isfinite(exponent):
        raise _reject("ARITHMETIC_OVERFLOW", "-3 * d**2 / (2*m) is not a finite binary64 value")
    decay = _guard(math.exp(exponent), "exp(-3 * d**2 / (2*m))")
    g = prefactor * decay
    if not math.isfinite(g):
        raise _reject("ARITHMETIC_OVERFLOW", "g is not a finite binary64 value")
    if g == 0.0:
        raise _reject("ARITHMETIC_UNDERFLOW", "g underflowed to zero; it is strictly positive in exact arithmetic")

    q = kappa * g
    if not math.isfinite(q):
        raise _reject("ARITHMETIC_OVERFLOW", "q = kappa * g is not a finite binary64 value")
    if kappa > 0.0 and q == 0.0:
        raise _reject("ARITHMETIC_UNDERFLOW", "q = kappa * g underflowed to zero with kappa > 0")
    if q < 0.0:
        raise _reject("OUTPUT_DOMAIN_VIOLATION",
                      f"q = kappa * g is {q!r}; pointwise_scalar_u requires a finite value >= 0")
    return {"mean_square_span_nm2": m, "spatial_density_nm3_inverse": g}, {"arm_reach_nm": r, "ceff_m": q}


def _assemble(activation, declaration, inputs, parameters, provenance):
    """The complete document for one normalized envelope; every other field is derived
    here, for new and reloaded results alike."""
    try:
        _check_identity(declaration, inputs, parameters)
        _check_availability(inputs)
        intermediates, outputs = _evaluate(inputs, parameters)
        status, diagnostics, missing = COMPUTED, [], None
    except _Outcome as outcome:
        intermediates = {name: None for name in INTERMEDIATE_SPEC}
        outputs = {name: None for name in OUTPUT_SPEC}
        status = outcome.status
        diagnostics = [{"severity": "error", "code": outcome.code, "message": outcome.message}]
        missing = f"{outcome.code}: {outcome.message}"
    document = {
        "schema_version": SCHEMA_VERSION,
        "formulation": {"formulation_id": FORMULATION_ID, "formulation_version": FORMULATION_VERSION,
                        "source_card": SOURCE_CARD, "evaluation_form": EVALUATION_FORM,
                        "equations": dict(EQUATIONS)},
        "activation": deepcopy(activation),
        "declaration": deepcopy(declaration),
        "inputs": deepcopy(inputs),
        "parameters": deepcopy(parameters),
        "intermediates": {name: {"quantity_definition_id": INTERMEDIATE_SPEC[name][0],
                                 "unit": INTERMEDIATE_SPEC[name][1], "value": intermediates[name]}
                          for name in sorted(INTERMEDIATE_SPEC)},
        "outputs": {name: {"quantity_id": name, "quantity_definition_id": OUTPUT_SPEC[name][0],
                           "context": declaration["context"], "category": declaration["category"],
                           "unit": OUTPUT_SPEC[name][1], "scale": declaration["scale"],
                           "domain": OUTPUT_SPEC[name][2], "value": outputs[name],
                           "missing_reason": missing}
                    for name in sorted(OUTPUT_SPEC)},
        "provenance": deepcopy(provenance),
        "assumptions": dict(ASSUMPTIONS),
        "status": status,
        "diagnostics": diagnostics,
    }
    document["result_id"] = hash_config(document)
    return document  # _verified is the single schema gate; every construction path passes through it


def _invalid(message):
    return PointwiseMeasurementError("RESULT_INVALID", message)


def _stored_activation(activation):
    """Re-validate the recorded activation; the fixed formulation identities are derived."""
    _exact_fields(activation, ("opt_in", "lane"), "activation", "RESULT_INVALID")
    if activation["opt_in"] is not True or activation["lane"] != LANE:
        raise _invalid("activation must record opt_in true in the experimental lane")
    return {"opt_in": True, "lane": LANE}


def _stored_inputs(inputs):
    """Re-validate the recorded input records without re-normalizing a supplied number."""
    _exact_fields(inputs, INPUT_SPEC, "inputs", "RESULT_INVALID")
    for name in sorted(INPUT_SPEC):
        record = inputs[name]
        _exact_fields(record, _STORED_INPUT_FIELDS, f"inputs.{name}", "RESULT_INVALID")
        if record["value"] is not None and record["value_token"] is not None:
            raise _invalid(f"inputs.{name} carries both a value and a token")
        if record["availability"] == UNAVAILABLE and (record["value"] is not None
                                                      or record["value_token"] is not None):
            raise _invalid(f"inputs.{name} is unavailable and cannot carry a value")
    return deepcopy(inputs)


def _stored_parameters(parameters):
    _exact_fields(parameters, _PARAMETER_FIELDS, "parameters", "RESULT_INVALID")
    _exact_fields(parameters["values"], PARAMETER_UNITS, "parameters.values", "RESULT_INVALID")
    for name in sorted(PARAMETER_UNITS):
        entry = parameters["values"][name]
        _exact_fields(entry, ("unit", "value", "value_token"), f"parameters.values.{name}", "RESULT_INVALID")
        if entry["value"] is not None and entry["value_token"] is not None:
            raise _invalid(f"parameters.values.{name} carries both a value and a token")
    return deepcopy(parameters)


def _verified(data):
    try:
        validate_named(data, "pointwise_measurement")
    except ValueError as exc:
        raise _invalid(str(exc)) from None
    rebuilt = _assemble(_stored_activation(data["activation"]),
                        _declaration(data["declaration"], "RESULT_INVALID"),
                        _stored_inputs(data["inputs"]),
                        _stored_parameters(data["parameters"]),
                        _provenance(data["provenance"], "RESULT_INVALID"))
    if canonical_json(rebuilt) != canonical_json(data):
        differing = sorted(k for k in rebuilt if canonical_json(rebuilt[k]) != canonical_json(data[k]))
        raise _invalid(f"fields differ from their re-derivation: {differing}")
    return rebuilt


@dataclass(frozen=True)
class PointwiseMeasurement:
    """A verified pointwise_measurement/1 document for exactly one declared pair."""

    data: dict

    def __post_init__(self):
        object.__setattr__(self, "data", _verified(self.data))

    @classmethod
    def from_dict(cls, data):
        return cls(data)

    @property
    def result_id(self):
        return self.data["result_id"]

    @property
    def status(self):
        return self.data["status"]

    def to_dict(self):
        return deepcopy(self.data)

    def to_json_bytes(self):
        return canonical_json(self.data)


def measure_pointwise(*, activation, declaration, inputs, parameters, provenance):
    """Evaluate card F02 at one explicitly declared pair. Pure; reads and writes nothing."""
    return PointwiseMeasurement(_assemble(_activation(activation), _declaration(declaration),
                                          _inputs(inputs), _parameters(parameters),
                                          _provenance(provenance)))


def load_pointwise_measurement(path):
    """Strictly parse and verify an exported result (e.g. written by write_json_new)."""
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
    return PointwiseMeasurement.from_dict(data)


def to_candidate_evidence_metric(result, quantity_id):
    """One metric mapping for an existing CandidateEvidence record; CandidateEvidence is unchanged."""
    if not isinstance(result, PointwiseMeasurement):
        raise PointwiseMeasurementError("CONTRACT_INVALID", "result must be a verified PointwiseMeasurement")
    if quantity_id not in OUTPUT_SPEC:
        raise PointwiseMeasurementError("CONTRACT_INVALID",
                                        f"quantity_id must be one of {sorted(OUTPUT_SPEC)}")
    data = result.to_dict()
    output = data["outputs"][quantity_id]
    metric = {"name": output["quantity_id"], "raw_value": output["value"], "value": output["value"],
              "context": output["context"], "category": output["category"], "unit": output["unit"],
              "scale": output["scale"], "source": deepcopy(data["provenance"]["source"]),
              "provenance": deepcopy(data["provenance"]["model"]),
              "missing_reason": output["missing_reason"]}
    if (metric["value"] is None) != (metric["missing_reason"] is not None):
        raise _invalid(f"outputs.{quantity_id}: a null value requires a missing_reason and no other value may carry one")
    validate(metric, _metric_schema())
    return metric
