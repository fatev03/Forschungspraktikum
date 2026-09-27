"""Opt-in nm-only coordinate admission and F01 point distance (contract f01_coordinate_distance/1).

Implements exactly amendment F01-coordinate-admission-v1 over the authoritative card F01
of the Astra formulation. Standard library plus the existing structure reader and the
existing validation helper; no import-time I/O. Exactly one file is opened: the explicitly
selected artifact. Nothing is discovered, globbed, converted, executed or fetched, no
directory is scanned, no latest model is chosen and no new coordinate parser exists here.

TWO STAGES ONLY

  1 coordinate admission   an explicit caller declaration admits source coordinates that
                           are already declared to be in nm; the admission is an identity
                           operation, never a conversion
  2 F01 point distance     d = sqrt((x1-y1)^2 + (x2-y2)^2 + (x3-y3)^2), evaluated with
                           math.dist (scaled, correction-compensated Euclidean norm)

Span limits, the permitted-span predicate, element spans, tolerance, aggregation, F02
invocation, probability, ranking, scoring and optimization are outside this module.

UNIT POLICY (amendment section 3, decision A: nm-only identity admission)

  Only source coordinates explicitly declared in nm are admitted. No Angstrom-to-nanometre
  conversion exists here, and no other source-unit token is accepted. Unit, frame, profile,
  conversion and point identity are never inferred from parser behaviour, filenames,
  project documentation, model metadata or environment. A declaration is required even when
  a caller states elsewhere that coordinates are in nm. frame_id is opaque: equality is
  exact string equality, and equal coordinate values never establish frame equality. The
  declaration is a caller assertion preserved in provenance, not a fact this module proves.

SELECTED ARTIFACT LAYOUT

  layout "structure_v1", read by the existing structures.read_structure. Chosen over
  af3_native_v1 because it returns binary64 coordinate triples directly (no coordinate
  token re-parsing), exposes the documented stable Atom locator including altloc and
  segment, covers .pdb/.cif/.mmcif through one reader, and re-hashes the file across its
  own read. Locator profile "structure_atom_locator/1" is the existing parser locator,
  preserved verbatim: model_id, chain_id, segment, group, residue_id, insertion_code,
  residue_name, atom_name, altloc. Each endpoint locator must resolve to exactly one atom;
  no first match, no latest model, no partial identity, no alias.

CANONICALIZATION PROFILE coordinate-json-v1 (amendment section 1)

  UTF-8 JSON, no insignificant whitespace, no byte-order mark. Object keys sorted by
  Unicode code point; array order preserved. No Unicode normalization. Quote and backslash
  escaped; every C0 control character as lowercase \\u00xx; all other characters emitted as
  UTF-8. Integers in decimal with no leading zeros. Floats rendered with 17 significant
  decimal digits, trailing fractional zeros removed, lowercase exponent with no plus sign
  and no redundant leading zeros. Negative zero serializes as 0, a serialization rule and
  not a coordinate correction. NaN, infinity, duplicate object keys and unsupported value
  types are rejected. A hash field never includes itself, and every digest is taken over a
  distinct object-kind tag and the canonicalization version followed by the canonical bytes,
  so declaration, trace, mapping, configuration and result identities cannot collide.

PATH EXCLUSION

  selected_path and every other execution-only value live in .execution_metadata, outside
  the canonical document. They never influence the result identity, the declaration digest,
  the normalization-trace digest, the mapping digest or the payload digest. Endpoint
  locators are record selectors, never filesystem paths.

FIRST-FAILURE ORDER (endpoint x is inspected before endpoint y at every endpoint stage)

  INPUT_CONTRACT_INVALID raises F01CoordinateAdmissionError and yields no document:
  malformed outer request, missing required non-declaration field, unusable artifact path,
  unsupported canonicalization or invalid configuration-provenance pairing. Every later
  failure yields a canonical REJECTED document with a null output value, one primary
  diagnostic carrying endpoint and field location, and a checks array in which the failing
  stage is FAILED and every later stage is NOT_REACHED. In order:

      COORDINATE_DECLARATION_MISSING      declaration absent or null
      COORDINATE_DECLARATION_INVALID      malformed shape, unknown field, omitted general
                                          required field, empty identifier, invalid
                                          declaration hash, or one declaration ID reused
                                          with changed declaration content
      ARTIFACT_IDENTITY_MISMATCH          artifact bytes, declared scope, selected artifact,
                                          declared layout or selected model identity disagree
      COORDINATE_FRAME_MISSING            frame ID or kind absent, null or empty
      COORDINATE_UNIT_UNSUPPORTED         source or output unit absent or outside {nm}
      COORDINATE_UNIT_PROFILE_UNKNOWN     profile ID or version not the authorized pair
      COORDINATE_PROFILE_INCONSISTENT     incorrect frame_kind, conversion-object mismatch,
                                          or inconsistency with the authorized profile
      COORDINATE_CONVERSION_REPEATED      a prior normalization or conversion pass is
                                          declared at the source-admission boundary
      POINT_SELECTOR_NOT_FOUND            locator resolves to no atom
      POINT_SELECTOR_AMBIGUOUS            locator resolves to more than one atom
      COORDINATE_FRAME_MISMATCH           endpoint frame identities differ from each other
                                          or from the declaration
      COORDINATE_NONFINITE                component not a finite binary64 float
      NORMALIZATION_TRACE_INVALID         trace missing, inconsistent, hash-invalid, source
                                          and normalized triples differ, or pass/count/
                                          profile fields disagree
      DISTANCE_NONFINITE                  finite admitted coordinates give an
                                          unrepresentable distance

  Statuses are only COMPUTED and REJECTED. UNAVAILABLE is not part of this contract.

OUTPUT

  admit_and_measure_distance returns F01CoordinateDistance. to_dict() conforms to
  schemas/f01_coordinate_distance.schema.json and to_json_bytes() is its canonical
  coordinate-json-v1 bytes, the exclusive canonical exporter. The document carries the
  normalized request and the artifact observation as its only seeds; the declaration
  digest, endpoint records, normalization traces and their digests, the endpoint mapping
  and its digest, the payload and its digest, the output metric, the checks array, the
  status, the diagnostic and result_id are all derived from those seeds. Constructing an
  F01CoordinateDistance (from_dict, load_f01_coordinate_distance) re-derives every one of
  them and rejects any difference (RESULT_INVALID). to_candidate_evidence_metric converts a
  COMPUTED result into one metric mapping for an existing CandidateEvidence record;
  CandidateEvidence and its schema are unchanged.

ERRORS
  F01CoordinateAdmissionError(ValueError) with .code and .diagnostics.
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

from .structures import read_structure, StructureFormatError, UnsupportedFormat
from .validation import validate, validate_named

SCHEMA_VERSION = "f01_coordinate_distance/1"
INPUT_CONTRACT_ID = "F01-coordinate-admission-v1"
FORMULATION_ID = "deterministic_geometry_v1"
FORMULATION_VERSION = "1"
EQUATION = "d = sqrt((x1-y1)**2 + (x2-y2)**2 + (x3-y3)**2)"
CANONICALIZATION_VERSION = "coordinate-json-v1"
LANE = "experimental"

LAYOUT = "structure_v1"
LOCATOR_PROFILE_ID = "structure_atom_locator"
LOCATOR_PROFILE_VERSION = "1"
NORMALIZATION_PROFILE_ID = "coordinate-nm-identity"
NORMALIZATION_PROFILE_VERSION = "1"
COORDINATE_UNIT = "nm"
FRAME_KIND = "cartesian_3d"
CONVERSION = {"applied": False, "factor": 1, "formula": "x_nm = x_source"}
OPERATION = "identity_admission"
QUANTITY_ID = "distance_nm"

COMPUTED, REJECTED = "COMPUTED", "REJECTED"
PASSED, FAILED, NOT_REACHED = "PASSED", "FAILED", "NOT_REACHED"
ENDPOINTS = ("x", "y")

CHECK_ORDER = (
    "COORDINATE_DECLARATION_MISSING",
    "COORDINATE_DECLARATION_INVALID",
    "ARTIFACT_IDENTITY_MISMATCH",
    "COORDINATE_FRAME_MISSING",
    "COORDINATE_UNIT_UNSUPPORTED",
    "COORDINATE_UNIT_PROFILE_UNKNOWN",
    "COORDINATE_PROFILE_INCONSISTENT",
    "COORDINATE_CONVERSION_REPEATED",
    "POINT_SELECTOR_NOT_FOUND",
    "POINT_SELECTOR_AMBIGUOUS",
    "COORDINATE_FRAME_MISMATCH",
    "COORDINATE_NONFINITE",
    "NORMALIZATION_TRACE_INVALID",
    "DISTANCE_NONFINITE",
)

# The declaration vocabulary of amendment section 1. General fields are checked at
# COORDINATE_DECLARATION_INVALID; frame, unit and profile fields have their own stages.
_DECLARATION_FIELDS = ("coordinate_declaration_id", "scope", "coordinate_unit", "source_unit",
                       "frame_id", "frame_kind", "normalization_profile_id",
                       "normalization_profile_version", "conversion", "canonicalization_version")
_SCOPE_FIELDS = ("artifact_id", "artifact_sha256", "selected_model_id")
_CONVERSION_FIELDS = ("applied", "factor", "formula")
_GENERAL_DECLARATION_FIELDS = ("coordinate_declaration_id", "scope", "canonicalization_version")

_ARTIFACT_FIELDS = ("artifact_id", "path", "expected_sha256", "layout", "selected_model_id")
_ENDPOINT_FIELDS = ("point_id", "frame_id", "frame_kind", "locator")
_LOCATOR_FIELDS = ("model_id", "chain_id", "segment", "group", "residue_id",
                   "insertion_code", "residue_name", "atom_name", "altloc")
_LOCATOR_PROFILE_FIELDS = ("profile_id", "profile_version")
_SOURCE_ADMISSION_FIELDS = ("prior_normalization_pass_count", "prior_conversion_count")
_PRIOR_BINDING_FIELDS = ("coordinate_declaration_id", "coordinate_declaration_sha256")
_OUTPUT_DECLARATION_FIELDS = ("context", "category", "scale")
_ACTIVATION_FIELDS = ("opt_in", "lane", "input_contract_id")
_DECLARED_CONFIGURATION = ("producer_configuration", "producer_configuration_hash")
_UNDECLARED_CONFIGURATION = ("producer_configuration_hash", "producer_configuration_missing_reason")
_NOT_DECLARED = "not_declared"

_HEX64 = re.compile(r"[a-f0-9]{64}")
_EXPONENT = re.compile(r"e([+-])0*(\d+)$")

_RULES = {
    "admission": "nm-only identity admission; no length conversion exists in this module",
    "declaration": "an explicit caller declaration is required even for coordinates asserted elsewhere to be in nm",
    "frame": "frame_id and frame_kind are opaque; equality is exact string equality and is never inferred from values",
    "inference": "unit, frame, profile, conversion and point identity are never taken from parser behaviour, filenames, documentation, model metadata or environment",
    "locator": "each endpoint locator resolves to exactly one atom; no first match, latest model, partial identity or alias",
    "parser": "the existing structures.read_structure is reused; this module defines no coordinate parser",
    "path": "selected_path and execution metadata are outside the canonical document and every digest",
    "reading": "the selected artifact is the only file opened; it is hashed before endpoint evaluation and re-hashed before return",
    "identity": "result_id = coordinate-json-v1 digest of the canonical document without result_id",
    "scope": "two stages only, coordinate admission and the F01 point distance; no span limits, predicate or aggregation",
}


class F01CoordinateAdmissionError(ValueError):
    """Malformed outer request or invalid document. Never used for an admission outcome."""

    def __init__(self, code, message):
        self.code = code
        self.diagnostics = [{"severity": "error", "code": code, "message": message}]
        super().__init__(f"{code}: {message}")


class _Rejected(Exception):
    """One recorded admission failure: its stage code and its precise location."""

    def __init__(self, code, detail, *, endpoint=None, field=None):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.endpoint, self.field = code, detail, endpoint, field


def _contract(message):
    return F01CoordinateAdmissionError("INPUT_CONTRACT_INVALID", message)


def _invalid(message):
    return F01CoordinateAdmissionError("RESULT_INVALID", message)


# ---------------------------------------------------------------------------
# coordinate-json-v1
# ---------------------------------------------------------------------------
def _number_token(value):
    """A binary64 value under the coordinate-json-v1 number rule."""
    if value != value or value in (math.inf, -math.inf):
        raise _contract("coordinate-json-v1 rejects NaN and infinity")
    if value == 0.0:
        return "0"  # negative zero serializes as 0: a serialization rule, not a correction
    token = "%.17g" % value
    if "e" in token:
        mantissa, _, exponent = token.partition("e")
        if "." in mantissa:
            mantissa = mantissa.rstrip("0").rstrip(".")
        sign = "-" if exponent.startswith("-") else ""
        token = f"{mantissa}e{sign}{exponent.lstrip('+-').lstrip('0') or '0'}"
    elif "." in token:
        token = token.rstrip("0").rstrip(".")
    return token


def _string_token(value):
    out = ['"']
    for character in value:
        if character == '"':
            out.append('\\"')
        elif character == "\\":
            out.append("\\\\")
        elif ord(character) < 0x20:
            out.append("\\u%04x" % ord(character))
        else:
            out.append(character)
    out.append('"')
    return "".join(out)


def _canonical(value):
    if value is None:
        return "null"
    if type(value) is bool:
        return "true" if value else "false"
    if type(value) is int:
        return str(value)
    if type(value) is float:
        return _number_token(value)
    if type(value) is str:
        return _string_token(value)
    if type(value) is list:
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if type(value) is dict:
        for key in value:
            if type(key) is not str:
                raise _contract("coordinate-json-v1 object keys must be strings")
        return "{" + ",".join(f"{_string_token(k)}:{_canonical(value[k])}"
                              for k in sorted(value)) + "}"
    raise _contract(f"coordinate-json-v1 rejects the value type {type(value).__name__}")


def coordinate_json(value):
    """The canonical coordinate-json-v1 bytes of a JSON value.

    coordinate-json-v1 emits UTF-8, and a Python string may hold code points UTF-8 cannot
    represent, such as a lone UTF-16 surrogate. That is malformed outer input, so the
    encoding is guarded and reported as this module's own contract failure rather than as
    a bare UnicodeEncodeError.
    """
    try:
        return _canonical(value).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _contract(
            "coordinate-json-v1 emits UTF-8; the request carries text that UTF-8 cannot "
            f"encode (U+{ord(exc.object[exc.start]):04X}), such as a lone UTF-16 surrogate"
        ) from None


def coordinate_digest(kind, value):
    """SHA-256 over an object-kind tag, the canonicalization version and the canonical bytes."""
    tagged = kind.encode("utf-8") + b"\x1f" + CANONICALIZATION_VERSION.encode("utf-8") + b"\x1f"
    return hashlib.sha256(tagged + coordinate_json(value)).hexdigest()


def _strict_load(data, where):
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
        raise _invalid(f"{where}: {exc}") from None


# ---------------------------------------------------------------------------
# INPUT_CONTRACT_INVALID: the outer request, which yields no document
# ---------------------------------------------------------------------------
def _exact(obj, names, what):
    if not isinstance(obj, dict) or set(obj) != set(names):
        raise _contract(f"{what} must have exactly the fields {sorted(names)}")


def _nonempty(value, what):
    if type(value) is not str or not value:
        raise _contract(f"{what} must be a nonempty string")
    return value


def _metric_contexts():
    schema = json.loads((Path(__file__).parent / "schemas" / "candidate_evidence.schema.json")
                        .read_text(encoding="utf-8"))
    return tuple(schema["properties"]["metrics"]["items"]["properties"]["context"]["enum"])


def _activation(activation):
    _exact(activation, _ACTIVATION_FIELDS, "activation")
    expected = {"opt_in": True, "lane": LANE, "input_contract_id": INPUT_CONTRACT_ID}
    for key, want in expected.items():
        if type(activation[key]) is not type(want) or activation[key] != want:
            raise _contract(f"activation.{key} must be exactly {want!r}; "
                            "this layer is never entered implicitly")
    return {"opt_in": True, "lane": LANE}


def _artifact_request(artifact):
    _exact(artifact, _ARTIFACT_FIELDS, "artifact")
    _nonempty(artifact["artifact_id"], "artifact.artifact_id")
    _nonempty(artifact["selected_model_id"], "artifact.selected_model_id")
    if artifact["layout"] != LAYOUT:
        raise _contract(f"artifact.layout must be exactly {LAYOUT!r}")
    if type(artifact["expected_sha256"]) is not str or _HEX64.fullmatch(artifact["expected_sha256"]) is None:
        raise _contract("artifact.expected_sha256 must be 64 lowercase hexadecimal characters")
    raw = artifact["path"]
    if type(raw) is not str or not raw:
        raise _contract("artifact.path must be a nonempty string")
    path = Path(raw)
    if not path.is_absolute() or os.path.abspath(raw) != raw or path.resolve() != path:
        raise _contract("artifact.path must be absolute and canonical, without symlink alias")
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        raise _contract(f"artifact.path is not readable ({exc.strerror})") from None
    if not stat.S_ISREG(mode):
        raise _contract("artifact.path must name a regular file")
    return path, {key: artifact[key] for key in _ARTIFACT_FIELDS if key != "path"}


def _endpoint_request(endpoints):
    _exact(endpoints, ENDPOINTS, "endpoints")
    result = {}
    for name in ENDPOINTS:
        endpoint = endpoints[name]
        _exact(endpoint, _ENDPOINT_FIELDS, f"endpoints.{name}")
        _nonempty(endpoint["point_id"], f"endpoints.{name}.point_id")
        for key in ("frame_id", "frame_kind"):
            if endpoint[key] is not None and type(endpoint[key]) is not str:
                raise _contract(f"endpoints.{name}.{key} must be a string or null")
        locator = endpoint["locator"]
        _exact(locator, _LOCATOR_FIELDS, f"endpoints.{name}.locator")
        for key in ("segment", "residue_id"):
            if type(locator[key]) is not int or type(locator[key]) is bool:
                raise _contract(f"endpoints.{name}.locator.{key} must be an integer")
        for key in set(_LOCATOR_FIELDS) - {"segment", "residue_id"}:
            if type(locator[key]) is not str:
                raise _contract(f"endpoints.{name}.locator.{key} must be a string")
        result[name] = {"point_id": endpoint["point_id"], "frame_id": endpoint["frame_id"],
                        "frame_kind": endpoint["frame_kind"],
                        "locator": {key: locator[key] for key in _LOCATOR_FIELDS}}
    return result


def _configuration_request(producer_configuration):
    if not isinstance(producer_configuration, dict):
        raise _contract("producer_configuration must be an object")
    keys = set(producer_configuration)
    if keys == set(_UNDECLARED_CONFIGURATION):
        if (producer_configuration["producer_configuration_hash"] is not None
                or producer_configuration["producer_configuration_missing_reason"] != _NOT_DECLARED):
            raise _contract("an undeclared producer configuration is exactly "
                            f"{{'producer_configuration_hash': None, "
                            f"'producer_configuration_missing_reason': {_NOT_DECLARED!r}}}")
        return {"producer_configuration": None, "producer_configuration_hash": None,
                "producer_configuration_missing_reason": _NOT_DECLARED}
    if keys != set(_DECLARED_CONFIGURATION):
        raise _contract("producer_configuration must be either a snapshot with its matching "
                        "hash or the exact undeclared pairing")
    snapshot = producer_configuration["producer_configuration"]
    if not isinstance(snapshot, dict):
        raise _contract("producer_configuration.producer_configuration must be an object")
    declared = producer_configuration["producer_configuration_hash"]
    if type(declared) is not str or _HEX64.fullmatch(declared) is None:
        raise _contract("producer_configuration.producer_configuration_hash must be 64 "
                        "lowercase hexadecimal characters")
    if coordinate_digest("producer_configuration", snapshot) != declared:
        raise _contract("producer_configuration.producer_configuration_hash does not match "
                        "the canonical snapshot")
    return {"producer_configuration": deepcopy(snapshot), "producer_configuration_hash": declared,
            "producer_configuration_missing_reason": None}


def _prior_binding_request(prior_declaration_binding):
    if prior_declaration_binding is None:
        return None
    _exact(prior_declaration_binding, _PRIOR_BINDING_FIELDS, "prior_declaration_binding")
    _nonempty(prior_declaration_binding["coordinate_declaration_id"],
              "prior_declaration_binding.coordinate_declaration_id")
    digest = prior_declaration_binding["coordinate_declaration_sha256"]
    if type(digest) is not str or _HEX64.fullmatch(digest) is None:
        raise _contract("prior_declaration_binding.coordinate_declaration_sha256 must be 64 "
                        "lowercase hexadecimal characters")
    return {key: prior_declaration_binding[key] for key in _PRIOR_BINDING_FIELDS}


def _request(*, artifact, coordinate_declaration, endpoints, locator_profile, source_admission,
             output_declaration, producer_configuration, activation, prior_declaration_binding):
    """The normalized, path-free outer request. Anything wrong here raises."""
    checked_activation = _activation(activation)
    path, artifact_identity = _artifact_request(artifact)
    _exact(locator_profile, _LOCATOR_PROFILE_FIELDS, "locator_profile")
    if (locator_profile["profile_id"] != LOCATOR_PROFILE_ID
            or locator_profile["profile_version"] != LOCATOR_PROFILE_VERSION):
        raise _contract(f"locator_profile must be exactly {LOCATOR_PROFILE_ID!r}/"
                        f"{LOCATOR_PROFILE_VERSION!r}")
    _exact(source_admission, _SOURCE_ADMISSION_FIELDS, "source_admission")
    for key in _SOURCE_ADMISSION_FIELDS:
        if type(source_admission[key]) is not int or type(source_admission[key]) is bool or source_admission[key] < 0:
            raise _contract(f"source_admission.{key} must be an integer >= 0")
    _exact(output_declaration, _OUTPUT_DECLARATION_FIELDS, "output_declaration")
    if output_declaration["context"] not in _metric_contexts():
        raise _contract(f"output_declaration.context must be one of {list(_metric_contexts())}")
    _nonempty(output_declaration["category"], "output_declaration.category")
    if output_declaration["scale"] is not None:
        _nonempty(output_declaration["scale"], "output_declaration.scale")
    if coordinate_declaration is not None and not isinstance(coordinate_declaration, dict):
        raise _contract("coordinate_declaration must be an object or null")
    request = {
        "activation": checked_activation,
        "artifact": artifact_identity,
        "coordinate_declaration": deepcopy(coordinate_declaration),
        "endpoints": _endpoint_request(endpoints),
        "locator_profile": {key: locator_profile[key] for key in _LOCATOR_PROFILE_FIELDS},
        "source_admission": {key: source_admission[key] for key in _SOURCE_ADMISSION_FIELDS},
        "output_declaration": {key: output_declaration[key] for key in _OUTPUT_DECLARATION_FIELDS},
        "producer_configuration": _configuration_request(producer_configuration),
        "prior_declaration_binding": _prior_binding_request(prior_declaration_binding),
    }
    coordinate_json(request)  # the request itself must be canonically serializable
    return path, request


# ---------------------------------------------------------------------------
# Admission stages, in the closed first-failure order
# ---------------------------------------------------------------------------
def _stage_declaration_missing(declaration):
    if declaration is None:
        raise _Rejected("COORDINATE_DECLARATION_MISSING",
                        "the coordinate declaration is absent; source coordinates are never "
                        "admitted without one", field="coordinate_declaration")


def _stage_declaration_invalid(declaration, prior_binding):
    """General declaration validity. Frame, unit and profile fields have their own later
    stages, so their omission is deferred; every other defect is rejected here. A
    declaration that cannot be serialized under coordinate-json-v1 never reaches this
    stage: it fails the outer contract, because it cannot be recorded as a seed."""
    where = "coordinate_declaration"
    deferred = {"frame_id", "frame_kind", "coordinate_unit", "source_unit",
                "normalization_profile_id", "normalization_profile_version", "conversion"}
    unknown = sorted(set(declaration) - set(_DECLARATION_FIELDS))
    if unknown:
        raise _Rejected("COORDINATE_DECLARATION_INVALID",
                        f"unknown declaration field(s) {unknown}", field=where)
    absent = set(_DECLARATION_FIELDS) - set(declaration)
    general_absent = sorted(absent - deferred)
    if general_absent:
        raise _Rejected("COORDINATE_DECLARATION_INVALID",
                        f"omitted general required field(s) {general_absent}", field=where)
    for key in _GENERAL_DECLARATION_FIELDS:
        if key == "scope":
            continue
        if type(declaration[key]) is not str or not declaration[key]:
            raise _Rejected("COORDINATE_DECLARATION_INVALID",
                            f"{key} must be a nonempty string", field=f"{where}.{key}")
    if declaration["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise _Rejected("COORDINATE_DECLARATION_INVALID",
                        f"canonicalization_version must be {CANONICALIZATION_VERSION!r}",
                        field=f"{where}.canonicalization_version")
    scope = declaration["scope"]
    if not isinstance(scope, dict) or set(scope) != set(_SCOPE_FIELDS):
        raise _Rejected("COORDINATE_DECLARATION_INVALID",
                        f"scope must have exactly the fields {sorted(_SCOPE_FIELDS)}",
                        field=f"{where}.scope")
    for key in ("artifact_id", "selected_model_id"):
        if type(scope[key]) is not str or not scope[key]:
            raise _Rejected("COORDINATE_DECLARATION_INVALID",
                            f"scope.{key} must be a nonempty string", field=f"{where}.scope.{key}")
    if type(scope["artifact_sha256"]) is not str or _HEX64.fullmatch(scope["artifact_sha256"]) is None:
        raise _Rejected("COORDINATE_DECLARATION_INVALID",
                        "scope.artifact_sha256 must be 64 lowercase hexadecimal characters",
                        field=f"{where}.scope.artifact_sha256")
    if absent:
        return None  # a deferred field is missing; its own stage rejects the declaration
    digest = coordinate_digest("coordinate_declaration", declaration)
    if prior_binding is not None:
        if prior_binding["coordinate_declaration_id"] != declaration["coordinate_declaration_id"]:
            raise _Rejected("COORDINATE_DECLARATION_INVALID",
                            "prior_declaration_binding names a different declaration ID than the "
                            "submitted declaration", field="prior_declaration_binding")
        if prior_binding["coordinate_declaration_sha256"] != digest:
            raise _Rejected("COORDINATE_DECLARATION_INVALID",
                            "this declaration ID is already bound to different declaration content",
                            field=f"{where}.coordinate_declaration_id")
    return digest


def _stage_artifact_identity(request, observation):
    where, artifact, scope = "artifact", request["artifact"], request["coordinate_declaration"]["scope"]
    if observation["read_status"] != "PARSED":
        raise _Rejected("ARTIFACT_IDENTITY_MISMATCH",
                        f"the selected artifact does not present layout {LAYOUT!r}: "
                        f"{observation['read_status']}", field=where)
    if observation["observed_artifact_sha256"] != artifact["expected_sha256"]:
        raise _Rejected("ARTIFACT_IDENTITY_MISMATCH",
                        "the artifact bytes do not match artifact.expected_sha256",
                        field=f"{where}.expected_sha256")
    if scope["artifact_sha256"] != observation["observed_artifact_sha256"]:
        raise _Rejected("ARTIFACT_IDENTITY_MISMATCH",
                        "the declaration scope hash does not match the artifact bytes",
                        field="coordinate_declaration.scope.artifact_sha256")
    if scope["artifact_id"] != artifact["artifact_id"]:
        raise _Rejected("ARTIFACT_IDENTITY_MISMATCH",
                        "the declaration scope artifact_id does not match the selected artifact",
                        field="coordinate_declaration.scope.artifact_id")
    if scope["selected_model_id"] != artifact["selected_model_id"]:
        raise _Rejected("ARTIFACT_IDENTITY_MISMATCH",
                        "the declaration scope selected_model_id does not match the request",
                        field="coordinate_declaration.scope.selected_model_id")
    if observation["observed_model_id"] != artifact["selected_model_id"]:
        raise _Rejected("ARTIFACT_IDENTITY_MISMATCH",
                        "the parsed selected model identity does not match the request",
                        field=f"{where}.selected_model_id")
    for name in ENDPOINTS:
        declared_model = request["endpoints"][name]["locator"]["model_id"]
        if declared_model != artifact["selected_model_id"]:
            raise _Rejected("ARTIFACT_IDENTITY_MISMATCH",
                            "the endpoint locator model_id does not match the selected model",
                            endpoint=name, field=f"endpoints.{name}.locator.model_id")


def _stage_frame_missing(request):
    declaration = request["coordinate_declaration"]
    for key in ("frame_id", "frame_kind"):
        if type(declaration.get(key)) is not str or not declaration[key]:
            raise _Rejected("COORDINATE_FRAME_MISSING", f"declaration {key} is absent, null or empty",
                            field=f"coordinate_declaration.{key}")
    for name in ENDPOINTS:
        for key in ("frame_id", "frame_kind"):
            if type(request["endpoints"][name][key]) is not str or not request["endpoints"][name][key]:
                raise _Rejected("COORDINATE_FRAME_MISSING", f"endpoint {key} is absent, null or empty",
                                endpoint=name, field=f"endpoints.{name}.{key}")


def _stage_unit_unsupported(declaration):
    for key in ("coordinate_unit", "source_unit"):
        value = declaration.get(key)
        if value != COORDINATE_UNIT:
            raise _Rejected("COORDINATE_UNIT_UNSUPPORTED",
                            f"{key} is {value!r}; only {COORDINATE_UNIT!r} is admitted and no "
                            "length conversion exists in this module",
                            field=f"coordinate_declaration.{key}")


def _stage_profile_unknown(declaration):
    pairs = (("normalization_profile_id", NORMALIZATION_PROFILE_ID),
             ("normalization_profile_version", NORMALIZATION_PROFILE_VERSION))
    for key, want in pairs:
        if declaration.get(key) != want:
            raise _Rejected("COORDINATE_UNIT_PROFILE_UNKNOWN",
                            f"{key} is {declaration.get(key)!r}, required {want!r}",
                            field=f"coordinate_declaration.{key}")


def _stage_profile_inconsistent(declaration):
    if declaration.get("frame_kind") != FRAME_KIND:
        raise _Rejected("COORDINATE_PROFILE_INCONSISTENT",
                        f"frame_kind is {declaration.get('frame_kind')!r}, required {FRAME_KIND!r}",
                        field="coordinate_declaration.frame_kind")
    conversion = declaration.get("conversion")
    if not isinstance(conversion, dict) or set(conversion) != set(_CONVERSION_FIELDS):
        raise _Rejected("COORDINATE_PROFILE_INCONSISTENT",
                        f"conversion must have exactly the fields {sorted(_CONVERSION_FIELDS)}",
                        field="coordinate_declaration.conversion")
    for key, want in CONVERSION.items():
        got = conversion[key]
        if type(got) is not type(want) or got != want:
            raise _Rejected("COORDINATE_PROFILE_INCONSISTENT",
                            f"conversion.{key} is {got!r}; the authorized identity profile "
                            f"requires {want!r}", field=f"coordinate_declaration.conversion.{key}")


def _stage_conversion_repeated(request):
    admission = request["source_admission"]
    for key in _SOURCE_ADMISSION_FIELDS:
        if admission[key] != 0:
            raise _Rejected("COORDINATE_CONVERSION_REPEATED",
                            f"the source record declares {key}={admission[key]}; admission "
                            "operates on source coordinates only",
                            field=f"source_admission.{key}")


def _stage_selectors(request, observation):
    for name in ENDPOINTS:
        if observation["resolution"][name]["match_count"] == 0:
            raise _Rejected("POINT_SELECTOR_NOT_FOUND",
                            "the endpoint locator resolves to no atom in the selected model",
                            endpoint=name, field=f"endpoints.{name}.locator")
    for name in ENDPOINTS:
        count = observation["resolution"][name]["match_count"]
        if count > 1:
            raise _Rejected("POINT_SELECTOR_AMBIGUOUS",
                            f"the endpoint locator resolves to {count} atoms in the selected model",
                            endpoint=name, field=f"endpoints.{name}.locator")


def _stage_frame_mismatch(request):
    """Both endpoints are compared with the single declaration frame, so endpoint frame
    equality follows transitively: they cannot differ from each other while both match it."""
    declaration = request["coordinate_declaration"]
    for name in ENDPOINTS:
        for key in ("frame_id", "frame_kind"):
            if request["endpoints"][name][key] != declaration[key]:
                raise _Rejected("COORDINATE_FRAME_MISMATCH",
                                f"endpoint {key} differs from the declaration; no transform or "
                                "equivalence inference is permitted",
                                endpoint=name, field=f"endpoints.{name}.{key}")


def _component(value):
    """One coordinate component as a finite binary64 float, or None.

    A JSON number reloaded from a canonical document may be an int; it is admitted only
    when it has an exact binary64 value. Booleans and numeric strings are rejected: the
    exact type tests below exclude bool, because type(True) is bool and not int.
    """
    if type(value) is int:
        try:
            number = float(value)
        except OverflowError:
            return None
        return number if int(number) == value else None
    if type(value) is float and math.isfinite(value):
        return value
    return None


def _stage_nonfinite(observation):
    """Returns the admitted triples; nothing is scaled, rounded, clipped or repaired."""
    triples = {}
    for name in ENDPOINTS:
        triple = observation["resolution"][name]["source_coordinates"]
        if not isinstance(triple, list) or len(triple) != 3:
            raise _Rejected("COORDINATE_NONFINITE", "the coordinate triple is malformed",
                            endpoint=name, field=f"endpoints.{name}.coordinates_nm")
        admitted = []
        for axis, component in enumerate(triple):
            number = _component(component)
            if number is None:
                raise _Rejected("COORDINATE_NONFINITE",
                                f"component {axis} is not a finite binary64 float",
                                endpoint=name, field=f"endpoints.{name}.coordinates_nm[{axis}]")
            admitted.append(number)
        triples[name] = admitted
    return triples


def _trace(request, observation, name, declaration_digest, triple):
    declaration = request["coordinate_declaration"]
    return {"artifact_id": request["artifact"]["artifact_id"],
            "artifact_sha256": observation["observed_artifact_sha256"],
            "selected_model_id": request["artifact"]["selected_model_id"],
            "endpoint_locator": deepcopy(request["endpoints"][name]["locator"]),
            "coordinate_declaration_id": declaration["coordinate_declaration_id"],
            "coordinate_declaration_sha256": declaration_digest,
            "normalization_profile_id": NORMALIZATION_PROFILE_ID,
            "normalization_profile_version": NORMALIZATION_PROFILE_VERSION,
            "source_unit": COORDINATE_UNIT, "target_unit": COORDINATE_UNIT,
            "source_coordinates": list(triple), "normalized_coordinates": list(triple),
            "operation": OPERATION, "normalization_pass_count": 1, "conversion_count": 0,
            "conversion_applied": CONVERSION["applied"], "factor": CONVERSION["factor"],
            "formula": CONVERSION["formula"],
            "canonicalization_version": CANONICALIZATION_VERSION}


def _endpoint_record(request, observation, name, declaration_digest, triple):
    declaration = request["coordinate_declaration"]
    trace = _trace(request, observation, name, declaration_digest, triple)
    return {"point_id": request["endpoints"][name]["point_id"],
            "coordinates_nm": list(trace["normalized_coordinates"]),
            "coordinate_unit": COORDINATE_UNIT,
            "frame_id": declaration["frame_id"], "frame_kind": declaration["frame_kind"],
            "artifact_id": request["artifact"]["artifact_id"],
            "artifact_sha256": observation["observed_artifact_sha256"],
            "selected_model_id": request["artifact"]["selected_model_id"],
            "endpoint_locator": deepcopy(request["endpoints"][name]["locator"]),
            "coordinate_declaration_id": declaration["coordinate_declaration_id"],
            "coordinate_declaration_sha256": declaration_digest,
            "normalization_profile_id": NORMALIZATION_PROFILE_ID,
            "normalization_profile_version": NORMALIZATION_PROFILE_VERSION,
            "normalization_trace": trace,
            "normalization_trace_sha256": coordinate_digest("normalization_trace", trace)}


def _stage_trace_invalid(records, declaration_digest):
    """Verify each admission trace against the authorized identity profile."""
    for name in ENDPOINTS:
        record, where = records[name], f"endpoints.{name}.normalization_trace"
        trace = record["normalization_trace"]
        if coordinate_digest("normalization_trace", trace) != record["normalization_trace_sha256"]:
            raise _Rejected("NORMALIZATION_TRACE_INVALID", "the trace digest does not match the trace",
                            endpoint=name, field=f"endpoints.{name}.normalization_trace_sha256")
        if coordinate_json(trace["source_coordinates"]) != coordinate_json(trace["normalized_coordinates"]):
            raise _Rejected("NORMALIZATION_TRACE_INVALID",
                            "source and normalized coordinates are not identical under "
                            f"{CANONICALIZATION_VERSION}", endpoint=name, field=f"{where}.normalized_coordinates")
        if coordinate_json(trace["normalized_coordinates"]) != coordinate_json(record["coordinates_nm"]):
            raise _Rejected("NORMALIZATION_TRACE_INVALID",
                            "the endpoint coordinates do not match the trace",
                            endpoint=name, field=f"endpoints.{name}.coordinates_nm")
        expected = {"source_unit": COORDINATE_UNIT, "target_unit": COORDINATE_UNIT,
                    "operation": OPERATION, "normalization_pass_count": 1, "conversion_count": 0,
                    "conversion_applied": CONVERSION["applied"], "factor": CONVERSION["factor"],
                    "formula": CONVERSION["formula"],
                    "normalization_profile_id": NORMALIZATION_PROFILE_ID,
                    "normalization_profile_version": NORMALIZATION_PROFILE_VERSION,
                    "canonicalization_version": CANONICALIZATION_VERSION,
                    "coordinate_declaration_sha256": declaration_digest}
        for key, want in expected.items():
            if type(trace[key]) is not type(want) or trace[key] != want:
                raise _Rejected("NORMALIZATION_TRACE_INVALID",
                                f"{key} is {trace[key]!r}, required {want!r}",
                                endpoint=name, field=f"{where}.{key}")


def _stage_distance(records):
    x = records["x"]["coordinates_nm"]
    y = records["y"]["coordinates_nm"]
    distance = math.dist(x, y)  # scaled, correction-compensated Euclidean norm
    if not math.isfinite(distance) or distance < 0.0:
        raise _Rejected("DISTANCE_NONFINITE",
                        "the admitted finite coordinates give an unrepresentable distance",
                        field="payload.distance_nm")
    return distance


# ---------------------------------------------------------------------------
# Derivation: request + observation -> the complete canonical document
# ---------------------------------------------------------------------------
def _mapping(request, records):
    entry = ("point_id", "artifact_id", "artifact_sha256", "selected_model_id",
             "endpoint_locator", "coordinate_declaration_sha256")
    return {"order": list(ENDPOINTS),
            **{name: {key: deepcopy(records[name][key]) for key in entry} for name in ENDPOINTS}}


def _pipeline(request, observation):
    """Run the closed first-failure order. Returns (records, distance, declaration_digest)."""
    _stage_declaration_missing(request["coordinate_declaration"])
    digest = _stage_declaration_invalid(request["coordinate_declaration"],
                                        request["prior_declaration_binding"])
    _stage_artifact_identity(request, observation)
    _stage_frame_missing(request)
    _stage_unit_unsupported(request["coordinate_declaration"])
    _stage_profile_unknown(request["coordinate_declaration"])
    _stage_profile_inconsistent(request["coordinate_declaration"])
    _stage_conversion_repeated(request)
    _stage_selectors(request, observation)
    _stage_frame_mismatch(request)
    triples = _stage_nonfinite(observation)
    records = {name: _endpoint_record(request, observation, name, digest, triples[name])
               for name in ENDPOINTS}
    _stage_trace_invalid(records, digest)
    return records, _stage_distance(records), digest


def _assemble(request, observation):
    """The complete document for one (request, observation); everything else is derived here,
    for new and reloaded results alike."""
    try:
        records, distance, digest = _pipeline(request, observation)
        status, failure = COMPUTED, None
    except _Rejected as rejected:
        records, distance, digest = None, None, None
        status, failure = REJECTED, rejected
    reached = True
    checks = []
    for code in CHECK_ORDER:
        if failure is not None and code == failure.code:
            checks.append({"code": code, "result": FAILED})
            reached = False
        else:
            checks.append({"code": code, "result": PASSED if reached else NOT_REACHED})
    configuration = request["producer_configuration"]
    mapping = None if records is None else _mapping(request, records)
    payload = {
        "formulation_id": FORMULATION_ID, "formulation_version": FORMULATION_VERSION,
        "coordinate_declaration": deepcopy(request["coordinate_declaration"]) if digest else None,
        "coordinate_declaration_sha256": digest,
        "endpoints": {name: (None if records is None else deepcopy(records[name])) for name in ENDPOINTS},
        "endpoint_mapping": mapping,
        "endpoint_mapping_sha256": None if mapping is None else coordinate_digest("endpoint_mapping", mapping),
        "producer_configuration": deepcopy(configuration["producer_configuration"]),
        "producer_configuration_hash": configuration["producer_configuration_hash"],
        "producer_configuration_missing_reason": configuration["producer_configuration_missing_reason"],
        "distance_nm": distance, "unit": COORDINATE_UNIT,
    }
    document = {
        "schema_version": SCHEMA_VERSION,
        "input_contract_id": INPUT_CONTRACT_ID,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "formulation": {"formulation_id": FORMULATION_ID, "formulation_version": FORMULATION_VERSION,
                        "equation": EQUATION},
        "activation": deepcopy(request["activation"]),
        "request": deepcopy(request),
        "observation": deepcopy(observation),
        "payload": payload,
        "payload_sha256": coordinate_digest("result_payload", payload),
        "output_metric": {
            "quantity_id": QUANTITY_ID, "quantity_definition_id": QUANTITY_ID,
            "context": request["output_declaration"]["context"],
            "category": request["output_declaration"]["category"],
            "scale": request["output_declaration"]["scale"],
            "unit": COORDINATE_UNIT, "value": distance,
        },
        "checks": checks,
        "status": status,
        "diagnostic": None if failure is None else {
            "code": failure.code, "endpoint": failure.endpoint,
            "field": failure.field, "detail": failure.detail},
        "rules": dict(_RULES),
    }
    document["result_id"] = coordinate_digest("f01_coordinate_distance_result", document)
    return document


def _verified(data):
    try:
        validate_named(data, "f01_coordinate_distance")
    except ValueError as exc:
        raise _invalid(str(exc)) from None
    try:
        rebuilt = _assemble(data["request"], data["observation"])
    except F01CoordinateAdmissionError as exc:
        raise _invalid(f"the recorded seeds are not admissible: {exc}") from None
    if coordinate_json(rebuilt) != coordinate_json(data):
        differing = sorted(k for k in rebuilt if coordinate_json(rebuilt[k]) != coordinate_json(data[k]))
        raise _invalid(f"fields differ from their re-derivation: {differing}")
    return rebuilt


@dataclass(frozen=True)
class F01CoordinateDistance:
    """A verified f01_coordinate_distance/1 document for exactly one endpoint pair.

    data is location independent. execution_metadata holds selected_path and any other
    execution-only value; it is outside every digest and is not exported by to_json_bytes.
    """

    data: dict
    execution_metadata: dict = None

    def __post_init__(self):
        object.__setattr__(self, "data", _verified(self.data))
        object.__setattr__(self, "execution_metadata", deepcopy(self.execution_metadata or {}))

    @classmethod
    def from_dict(cls, data, execution_metadata=None):
        return cls(data, execution_metadata)

    @property
    def result_id(self):
        return self.data["result_id"]

    @property
    def status(self):
        return self.data["status"]

    @property
    def distance_nm(self):
        return self.data["payload"]["distance_nm"]

    def to_dict(self):
        return deepcopy(self.data)

    def to_json_bytes(self):
        """The exclusive canonical exporter: coordinate-json-v1 bytes of the document."""
        return coordinate_json(self.data)


# ---------------------------------------------------------------------------
# Artifact observation: the only file this module opens
# ---------------------------------------------------------------------------
def _matches(atom, locator):
    return (atom.model_id == locator["model_id"] and atom.chain_id == locator["chain_id"]
            and atom.segment == locator["segment"] and atom.group == locator["group"]
            and atom.residue_id == locator["residue_id"]
            and atom.insertion_code == locator["insertion_code"]
            and atom.residue_name == locator["residue_name"]
            and atom.atom_name == locator["atom_name"] and atom.altloc == locator["altloc"])


def _recordable(value):
    """A parsed component as a JSON number, or an exact token when it has none.

    coordinate-json-v1 rejects NaN and infinity, so a non-finite parsed component is
    recorded as its token and is rejected at COORDINATE_NONFINITE. No value is coerced.
    """
    if math.isnan(value):
        return "nan"
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    return float(value)


def _observe(path, request):
    """Read and hash the selected artifact once, then resolve both endpoint locators."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    observation = {"observed_artifact_sha256": digest, "observed_model_id": None,
                   "read_status": "PARSED",
                   "resolution": {name: {"match_count": 0, "source_coordinates": None}
                                  for name in ENDPOINTS}}
    try:
        structure = read_structure(path, model_id=request["artifact"]["selected_model_id"])
    except UnsupportedFormat:
        observation["read_status"] = "LAYOUT_UNSUPPORTED"
        return observation
    except StructureFormatError:
        observation["read_status"] = "LAYOUT_MALFORMED"
        return observation
    except ValueError:
        observation["read_status"] = "MODEL_NOT_PRESENT"
        return observation
    observation["observed_model_id"] = structure.model_id
    for name in ENDPOINTS:
        locator = request["endpoints"][name]["locator"]
        found = [atom for atom in structure.atoms if _matches(atom, locator)]
        observation["resolution"][name]["match_count"] = len(found)
        if len(found) == 1:
            observation["resolution"][name]["source_coordinates"] = [_recordable(v) for v in found[0].xyz]
    return observation


def admit_and_measure_distance(*, artifact, coordinate_declaration, endpoints, locator_profile,
                               source_admission, output_declaration, producer_configuration,
                               activation, prior_declaration_binding=None):
    """Admit nm coordinates from one selected artifact and evaluate the F01 point distance.

    prior_declaration_binding is the caller's explicit assertion that one
    coordinate_declaration_id is already bound to one declaration digest, so that reusing
    that ID with changed content is rejected. It is a recorded request seed, never module
    state; null asserts that no prior binding is being claimed.
    """
    path, request = _request(artifact=artifact, coordinate_declaration=coordinate_declaration,
                             endpoints=endpoints, locator_profile=locator_profile,
                             source_admission=source_admission,
                             output_declaration=output_declaration,
                             producer_configuration=producer_configuration, activation=activation,
                             prior_declaration_binding=prior_declaration_binding)
    observation = _observe(path, request)
    if hashlib.sha256(path.read_bytes()).hexdigest() != observation["observed_artifact_sha256"]:
        # The artifact identity was not stable across the operation, so the stage-3
        # assertion is retroactively false and the whole admission is rejected there.
        observation = {**observation, "read_status": "BYTES_CHANGED_DURING_ADMISSION",
                       "observed_model_id": None,
                       "resolution": {name: {"match_count": 0, "source_coordinates": None}
                                      for name in ENDPOINTS}}
    document = _assemble(request, observation)
    return F01CoordinateDistance(document, {"selected_path": str(path)})


def load_f01_coordinate_distance(path):
    """Strictly parse and verify an exported canonical result."""
    return F01CoordinateDistance.from_dict(_strict_load(Path(path).read_bytes(), str(path)))


def to_candidate_evidence_metric(result, *, source_path):
    """One metric mapping for an existing CandidateEvidence record; only for COMPUTED.

    source_path is supplied by the caller because the canonical document is location
    independent. The producer provenance triple is null by construction: this producer
    evaluates a closed geometric expression and runs no model.
    """
    if not isinstance(result, F01CoordinateDistance):
        raise _contract("result must be a verified F01CoordinateDistance")
    if result.status != COMPUTED:
        raise _contract(f"only a {COMPUTED} result converts to a metric; this result is "
                        f"{result.status}")
    _nonempty(source_path, "source_path")
    data = result.to_dict()
    metric = {"name": data["output_metric"]["quantity_id"],
              "raw_value": data["output_metric"]["value"], "value": data["output_metric"]["value"],
              "context": data["output_metric"]["context"], "category": data["output_metric"]["category"],
              "unit": data["output_metric"]["unit"], "scale": data["output_metric"]["scale"],
              "source": {"path": source_path,
                         "sha256": data["payload"]["endpoints"]["x"]["artifact_sha256"], "row": None},
              "provenance": {"model_id": None, "checkpoint_id": None, "seed": None},
              "missing_reason": None}
    schema = json.loads((Path(__file__).parent / "schemas" / "candidate_evidence.schema.json")
                        .read_text(encoding="utf-8"))
    validate(metric, schema["properties"]["metrics"]["items"])
    return metric
