"""Synthetic contract tests for pointwise_measurement; only export tests write temporary files.

Every expected number is an independent evaluation of card F02 written out in the test,
not a value copied from the implementation.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import tempfile
import unittest

from structure_audit import pointwise_measurement as pm
from structure_audit.evidence import CandidateEvidence
from structure_audit.pointwise_measurement import (
    PointwiseMeasurement, PointwiseMeasurementError, load_pointwise_measurement,
    measure_pointwise, to_candidate_evidence_metric,
)
from structure_audit.provenance import canonical_json, hash_config, write_json_new
from structure_audit.validation import validate_named

SHA = "a" * 64
ACTIVATION = {"opt_in": True, "lane": "experimental",
              "formulation_id": "pointwise_measurement_v1", "formulation_version": "astra-F02/1"}
DECLARATION = {"pair_id": "syn-pair-1", "context": "complex", "category": "derived_measurement", "scale": None}
PROVENANCE = {"pipeline_run_id": "syn-run-1", "execution_id": "syn-exec-1",
              "method_id": "pointwise_measurement_v1", "method_version": "astra-F02/1",
              "canonicalization_version": "structure_audit.provenance.canonical_json/1",
              "source": {"path": "/synthetic/producer/pairs.json", "sha256": SHA, "row": 1},
              "model": {"model_id": None, "checkpoint_id": None, "seed": None}}


def inputs(distance=3.0, segments=9.0, **over):
    record = {"distance_nm": {"quantity_definition_id": "distance_nm", "unit": "nm",
                              "availability": "AVAILABLE", "unavailable_reason": None, "value": distance},
              "segment_count": {"quantity_definition_id": "segment_count_dimensionless",
                                "unit": "dimensionless", "availability": "AVAILABLE",
                                "unavailable_reason": None, "value": segments}}
    for dotted, value in over.items():
        name, field = dotted.split(".")
        record[name][field] = value
    return record


def parameters(c=4.0, eta=1.0, kappa=2.0, **over):
    values = {"c": {"unit": "nm^2", "value": c}, "eta": {"unit": "dimensionless", "value": eta},
              "kappa": {"unit": "U*nm^3", "value": kappa}}
    for dotted, value in over.items():
        name, field = dotted.split(".")
        values[name][field] = value
    return {"profile_id": "syn-profile", "profile_version": "1", "values": values}


def measure(**over):
    payload = {"activation": deepcopy(ACTIVATION), "declaration": deepcopy(DECLARATION),
               "inputs": inputs(), "parameters": parameters(), "provenance": deepcopy(PROVENANCE)}
    payload.update(over)
    return measure_pointwise(**payload)


def card_f02(d, n, c, eta, kappa):
    """Card F02 written out independently of the module under test."""
    m = c * (n ** eta)
    return {"m": m, "r": math.sqrt(m),
            "g": ((3 / (2 * math.pi * m)) ** (3 / 2)) * math.exp(-(3 * d ** 2) / (2 * m)),
            "q": kappa * ((3 / (2 * math.pi * m)) ** (3 / 2)) * math.exp(-(3 * d ** 2) / (2 * m))}


class Contract(unittest.TestCase):
    def reject(self, code, **over):
        result = measure(**over)
        self.assertEqual(result.status, "REJECTED", result.to_dict()["diagnostics"])
        self.assertEqual(result.to_dict()["diagnostics"][0]["code"], code, result.to_dict()["diagnostics"])
        return result

    def error(self, code, **over):
        with self.assertRaises(PointwiseMeasurementError) as caught:
            measure(**over)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        self.assertEqual(caught.exception.diagnostics[0]["code"], code)
        return caught.exception

    def no_value_is_carried(self, result):
        data = result.to_dict()
        self.assertNotEqual(data["status"], "COMPUTED")
        for name, output in data["outputs"].items():
            self.assertIsNone(output["value"], name)
            self.assertTrue(output["missing_reason"])
        for name, entry in data["intermediates"].items():
            self.assertIsNone(entry["value"], name)
        self.assertEqual(len(data["diagnostics"]), 1)


class Computation(Contract):
    def test_computes_card_f02_at_one_pair(self):
        expected = card_f02(3.0, 9.0, 4.0, 1.0, 2.0)
        data = measure().to_dict()
        self.assertEqual(data["status"], "COMPUTED")
        self.assertEqual(data["diagnostics"], [])
        self.assertEqual(data["schema_version"], "pointwise_measurement/1")
        self.assertEqual(data["formulation"]["formulation_id"], "pointwise_measurement_v1")
        self.assertEqual(data["formulation"]["formulation_version"], "astra-F02/1")
        self.assertEqual(data["formulation"]["evaluation_form"], "direct")
        self.assertEqual(data["intermediates"]["mean_square_span_nm2"]["value"], expected["m"])
        self.assertEqual(data["intermediates"]["mean_square_span_nm2"]["unit"], "nm^2")
        self.assertEqual(data["intermediates"]["spatial_density_nm3_inverse"]["value"], expected["g"])
        self.assertEqual(data["intermediates"]["spatial_density_nm3_inverse"]["unit"], "nm^-3")
        self.assertEqual(data["outputs"]["ceff_m"]["value"], expected["q"])
        self.assertEqual(data["outputs"]["arm_reach_nm"]["value"], expected["r"])
        self.assertEqual(data["outputs"]["arm_reach_nm"]["value"], 6.0)

    def test_output_quantity_identities_follow_the_dictionary(self):
        outputs = measure().to_dict()["outputs"]
        self.assertEqual(outputs["ceff_m"]["quantity_definition_id"], "pointwise_scalar_u")
        self.assertEqual(outputs["ceff_m"]["unit"], "U")
        self.assertEqual(outputs["ceff_m"]["domain"], "finite, >= 0")
        self.assertEqual(outputs["arm_reach_nm"]["quantity_definition_id"], "reach_rms_nm")
        self.assertEqual(outputs["arm_reach_nm"]["unit"], "nm")
        self.assertEqual(outputs["arm_reach_nm"]["domain"], "finite, > 0")
        for output in outputs.values():
            self.assertEqual(output["category"], "derived_measurement")
            self.assertIsNone(output["scale"])
            self.assertEqual(output["context"], "complex")
            self.assertIsNone(output["missing_reason"])

    def test_boundary_zero_distance_is_computed(self):
        expected = card_f02(0.0, 9.0, 4.0, 1.0, 2.0)
        data = measure(inputs=inputs(distance=0.0)).to_dict()
        self.assertEqual(data["status"], "COMPUTED")
        self.assertEqual(data["outputs"]["ceff_m"]["value"], expected["q"])
        self.assertEqual(data["outputs"]["arm_reach_nm"]["value"], 6.0)

    def test_boundary_small_positive_reach_is_computed(self):
        """reach_rms_nm has the strict dictionary domain > 0; a reach far below 1 nm stays admissible."""
        expected = card_f02(0.0, 1.0, 1e-200, 1.0, 1e-200)
        data = measure(inputs=inputs(distance=0.0, segments=1.0),
                       parameters=parameters(c=1e-200, kappa=1e-200)).to_dict()
        self.assertEqual(data["status"], "COMPUTED")
        self.assertEqual(data["outputs"]["arm_reach_nm"]["value"], 1e-100)
        self.assertGreater(data["outputs"]["arm_reach_nm"]["value"], 0.0)
        self.assertEqual(data["outputs"]["ceff_m"]["value"], expected["q"])

    def test_parameters_come_only_from_the_payload(self):
        """A different declared coefficient profile gives a different value; nothing is defaulted."""
        first = measure().to_dict()["outputs"]["ceff_m"]["value"]
        second = measure(parameters=parameters(c=4.0, eta=1.0, kappa=5.0)).to_dict()["outputs"]["ceff_m"]["value"]
        self.assertEqual(second, first / 2.0 * 5.0)

    def test_the_document_is_one_pair_with_no_aggregate(self):
        data = measure().to_dict()
        self.assertEqual(set(data), {"schema_version", "result_id", "formulation", "activation",
                                     "declaration", "inputs", "parameters", "intermediates",
                                     "outputs", "provenance", "assumptions", "status", "diagnostics"})
        self.assertEqual(set(data["outputs"]), {"ceff_m", "arm_reach_nm"})
        self.assertEqual(set(data["intermediates"]), {"mean_square_span_nm2", "spatial_density_nm3_inverse"})
        self.assertEqual(data["declaration"]["pair_id"], "syn-pair-1")
        self.assertEqual(data["assumptions"]["aggregation"],
                         "none; the two arithmetic means of card F02 are outside this contract")


class Availability(Contract):
    def test_unavailable_declared_input_is_unavailable(self):
        for name in ("distance_nm", "segment_count"):
            with self.subTest(name=name):
                result = measure(inputs=inputs(**{f"{name}.availability": "UNAVAILABLE",
                                                  f"{name}.value": None,
                                                  f"{name}.unavailable_reason": "upstream pair record absent"}))
                self.assertEqual(result.status, "UNAVAILABLE")
                diagnostic = result.to_dict()["diagnostics"][0]
                self.assertEqual(diagnostic["code"], "INPUT_UNAVAILABLE")
                self.assertIn("upstream pair record absent", diagnostic["message"])
                self.no_value_is_carried(result)

    def test_identity_is_checked_before_availability(self):
        result = measure(inputs=inputs(**{"distance_nm.unit": "angstrom",
                                          "distance_nm.availability": "UNAVAILABLE",
                                          "distance_nm.value": None,
                                          "distance_nm.unavailable_reason": "absent"}))
        self.assertEqual(result.status, "REJECTED")
        self.assertEqual(result.to_dict()["diagnostics"][0]["code"], "UNIT_INCOMPATIBLE")

    def test_unavailable_input_needs_a_reason_and_a_null_value(self):
        self.error("CONTRACT_INVALID", inputs=inputs(**{"distance_nm.availability": "UNAVAILABLE"}))
        self.error("CONTRACT_INVALID", inputs=inputs(**{"distance_nm.availability": "UNAVAILABLE",
                                                        "distance_nm.value": None}))
        self.error("CONTRACT_INVALID", inputs=inputs(**{"distance_nm.unavailable_reason": "set anyway"}))


class Identity(Contract):
    def test_incompatible_input_unit_is_rejected(self):
        for name, unit in (("distance_nm", "angstrom"), ("segment_count", "nm")):
            with self.subTest(name=name):
                result = self.reject("UNIT_INCOMPATIBLE", inputs=inputs(**{f"{name}.unit": unit}))
                self.assertIn("no conversion", result.to_dict()["diagnostics"][0]["message"])
                self.no_value_is_carried(result)

    def test_incompatible_parameter_unit_is_rejected(self):
        for name, unit in (("c", "nm"), ("eta", "nm^2"), ("kappa", "U")):
            with self.subTest(name=name):
                self.reject("UNIT_INCOMPATIBLE", parameters=parameters(**{f"{name}.unit": unit}))

    def test_incompatible_input_quantity_definition_is_rejected(self):
        for name, definition in (("distance_nm", "reach_rms_nm"), ("segment_count", "distance_nm")):
            with self.subTest(name=name):
                self.reject("QUANTITY_IDENTITY_MISMATCH",
                            inputs=inputs(**{f"{name}.quantity_definition_id": definition}))

    def test_incompatible_context_category_or_scale_is_rejected(self):
        for field, value in (("context", "unmapped_context"), ("category", "model_confidence"),
                             ("scale", "0-1")):
            with self.subTest(field=field):
                result = self.reject("QUANTITY_IDENTITY_MISMATCH",
                                     declaration={**DECLARATION, field: value})
                self.no_value_is_carried(result)

    def test_every_candidate_evidence_context_is_accepted_when_declared(self):
        schema = json.loads((Path(pm.__file__).parent / "schemas" / "candidate_evidence.schema.json")
                            .read_text(encoding="utf-8"))
        for context in schema["properties"]["metrics"]["items"]["properties"]["context"]["enum"]:
            with self.subTest(context=context):
                result = measure(declaration={**DECLARATION, "context": context})
                self.assertEqual(result.status, "COMPUTED")
                self.assertEqual(result.to_dict()["outputs"]["ceff_m"]["context"], context)


class Domain(Contract):
    def test_negative_or_zero_reach_is_rejected(self):
        for c in (-4.0, -1e-12, 0.0):
            with self.subTest(c=c):
                result = self.reject("REACH_DOMAIN_VIOLATION", parameters=parameters(c=c))
                self.assertIn("m > 0", result.to_dict()["diagnostics"][0]["message"])
                self.no_value_is_carried(result)

    def test_input_domain_violation_is_rejected(self):
        self.reject("INPUT_DOMAIN_VIOLATION", inputs=inputs(distance=-1e-9))
        self.reject("INPUT_DOMAIN_VIOLATION", inputs=inputs(segments=0.0))
        self.reject("INPUT_DOMAIN_VIOLATION", inputs=inputs(segments=-2.0))

    def test_negative_output_value_is_rejected(self):
        result = self.reject("OUTPUT_DOMAIN_VIOLATION", parameters=parameters(kappa=-2.0))
        self.assertIn(">= 0", result.to_dict()["diagnostics"][0]["message"])

    def test_non_finite_input_is_rejected(self):
        for raw in (float("nan"), float("inf"), float("-inf")):
            for name in ("distance_nm", "segment_count"):
                with self.subTest(raw=repr(raw), name=name):
                    result = self.reject("INPUT_NOT_FINITE", inputs=inputs(**{f"{name}.value": raw}))
                    self.no_value_is_carried(result)
        for name in ("c", "eta", "kappa"):
            with self.subTest(name=name):
                self.reject("INPUT_NOT_FINITE", parameters=parameters(**{f"{name}.value": float("nan")}))

    def test_non_numeric_input_is_rejected(self):
        for raw, code in (("3.0", "INPUT_NOT_NUMERIC"), (True, "INPUT_NOT_NUMERIC"),
                          (None, "INPUT_NOT_NUMERIC"), (10 ** 400, "INPUT_NOT_EXACTLY_REPRESENTABLE"),
                          (2 ** 53 + 1, "INPUT_NOT_EXACTLY_REPRESENTABLE")):
            with self.subTest(raw=type(raw).__name__):
                result = self.reject(code, inputs=inputs(**{"distance_nm.value": raw}))
                self.assertIsNone(result.to_dict()["inputs"]["distance_nm"]["value"])
                self.assertIsNotNone(result.to_dict()["inputs"]["distance_nm"]["value_token"])

    def test_integer_input_with_an_exact_value_is_accepted(self):
        expected = card_f02(3.0, 9.0, 4.0, 1.0, 2.0)
        data = measure(inputs=inputs(distance=3, segments=9)).to_dict()
        self.assertEqual(data["status"], "COMPUTED")
        self.assertEqual(data["outputs"]["ceff_m"]["value"], expected["q"])
        self.assertEqual(data["inputs"]["distance_nm"]["value"], 3.0)


class Arithmetic(Contract):
    # The expected term names the guard that must fire: a later guard reporting the same
    # code is a different failure and does not satisfy the case.
    CASES = (
        ("power_overflow", {"segments": 10.0}, {"eta": 400.0}, "ARITHMETIC_OVERFLOW", "n**eta"),
        ("span_overflow", {"segments": 1.0}, {"c": 1e308, "eta": 1.0}, "ARITHMETIC_OVERFLOW", "2*pi*m"),
        ("base_overflow", {"distance": 0.0, "segments": 1.0}, {"c": 5e-324},
         "ARITHMETIC_OVERFLOW", "3 / (2*pi*m) is"),
        ("prefactor_overflow", {"distance": 0.0, "segments": 1.0}, {"c": 1e-300},
         "ARITHMETIC_OVERFLOW", "(3 / (2*pi*m))**1.5"),
        ("prefactor_underflow", {"distance": 0.0, "segments": 1.0}, {"c": 2.86e307},
         "ARITHMETIC_UNDERFLOW", "(3 / (2*pi*m))**1.5"),
        ("squared_distance_overflow", {"distance": 1e200}, {}, "ARITHMETIC_OVERFLOW", "d**2"),
        ("decay_underflow", {"distance": 1000.0}, {}, "ARITHMETIC_UNDERFLOW", "exp(-3 * d**2 / (2*m))"),
        ("product_overflow", {"distance": 0.0, "segments": 1.0}, {"c": 1e-200, "kappa": 1e100},
         "ARITHMETIC_OVERFLOW", "q = kappa * g"),
        ("span_underflow", {"segments": 1e-300}, {"eta": 4.0}, "ARITHMETIC_UNDERFLOW", "n**eta"),
    )

    def test_arithmetic_failures_are_rejected_by_the_guard_that_owns_them(self):
        for label, input_over, parameter_over, code, term in self.CASES:
            with self.subTest(label=label):
                result = self.reject(code, inputs=inputs(**input_over), parameters=parameters(**parameter_over))
                message = result.to_dict()["diagnostics"][0]["message"]
                self.assertTrue(message.startswith(term), f"{label}: {message}")
                self.no_value_is_carried(result)

    def test_every_arithmetic_case_is_distinct(self):
        self.assertEqual(len({label for label, *_ in self.CASES}), len(self.CASES))
        self.assertEqual(len({(code, term) for *_, code, term in self.CASES}), len(self.CASES))
        self.assertEqual({code for *_, code, _ in self.CASES},
                         {"ARITHMETIC_OVERFLOW", "ARITHMETIC_UNDERFLOW"})


class Activation(Contract):
    def test_activation_is_required_exactly(self):
        for field, value in (("opt_in", False), ("opt_in", "true"), ("lane", "baseline"),
                             ("formulation_id", "deterministic_geometry_v1"),
                             ("formulation_version", "astra-F02/2")):
            with self.subTest(field=field, value=value):
                self.error("ACTIVATION_REQUIRED", activation={**ACTIVATION, field: value})

    def test_missing_activation_field_is_refused(self):
        for field in ACTIVATION:
            with self.subTest(field=field):
                self.error("ACTIVATION_REQUIRED",
                           activation={k: v for k, v in ACTIVATION.items() if k != field})

    def test_activation_is_recorded_without_the_derived_identities(self):
        self.assertEqual(measure().to_dict()["activation"], {"opt_in": True, "lane": "experimental"})


class Envelope(Contract):
    def test_every_field_is_required(self):
        for block, template in (("declaration", DECLARATION), ("provenance", PROVENANCE)):
            for field in template:
                with self.subTest(block=block, field=field):
                    self.error("CONTRACT_INVALID",
                               **{block: {k: v for k, v in template.items() if k != field}})
        for name in ("distance_nm", "segment_count"):
            with self.subTest(block="inputs", name=name):
                self.error("CONTRACT_INVALID", inputs={k: v for k, v in inputs().items() if k != name})
        for name in ("c", "eta", "kappa"):
            with self.subTest(block="parameters", name=name):
                payload = parameters()
                payload["values"].pop(name)
                self.error("CONTRACT_INVALID", parameters=payload)

    def test_unexpected_field_is_refused(self):
        self.error("CONTRACT_INVALID", declaration={**DECLARATION, "extra": 1})
        self.error("CONTRACT_INVALID", inputs={**inputs(), "reach_nm": inputs()["distance_nm"]})

    def test_provenance_identities_are_compared(self):
        for field in ("method_id", "method_version", "canonicalization_version"):
            with self.subTest(field=field):
                self.error("CONTRACT_INVALID", provenance={**PROVENANCE, field: "other"})

    def test_document_carries_no_timestamp_or_selection_path(self):
        text = canonical_json(measure().to_dict()).decode("utf-8")
        self.assertNotIn("timestamp", text)
        paths = re.findall(r'"(/[^"]*)"', text)
        self.assertEqual(paths, [PROVENANCE["source"]["path"]])

    def test_public_vocabulary_is_clean(self):
        forbidden = ("probability", "affinity", "occupancy", "ranking", "score", "binding", "prediction")
        for path in (Path(pm.__file__), Path(pm.__file__).parent / "schemas" / "pointwise_measurement.schema.json"):
            text = path.read_text(encoding="utf-8").lower()
            for token in forbidden:
                with self.subTest(path=path.name, token=token):
                    self.assertNotIn(token, text)


class Serialization(Contract):
    def test_identical_payloads_are_byte_identical(self):
        self.assertEqual(measure().to_json_bytes(), measure().to_json_bytes())
        self.assertEqual(measure().result_id, measure().result_id)

    def test_different_payloads_have_different_identities(self):
        other = measure(parameters=parameters(kappa=3.0))
        self.assertNotEqual(measure().result_id, other.result_id)
        self.assertNotEqual(measure().to_json_bytes(), other.to_json_bytes())

    def test_rejected_and_unavailable_results_serialize(self):
        rejected = measure(parameters=parameters(c=-4.0))
        unavailable = measure(inputs=inputs(**{"distance_nm.availability": "UNAVAILABLE",
                                               "distance_nm.value": None,
                                               "distance_nm.unavailable_reason": "absent"}))
        for result in (rejected, unavailable):
            with self.subTest(status=result.status):
                reloaded = PointwiseMeasurement.from_dict(json.loads(result.to_json_bytes()))
                self.assertEqual(reloaded.to_json_bytes(), result.to_json_bytes())

    def test_export_reload_reserialize_is_stable(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve() / "result.json"
            original = measure()
            write_json_new(path, original.to_dict())
            reloaded = load_pointwise_measurement(path)
            self.assertEqual(reloaded.to_json_bytes(), original.to_json_bytes())
            self.assertEqual(reloaded.result_id, original.result_id)
            again = Path(temp).resolve() / "again.json"
            write_json_new(again, reloaded.to_dict())
            self.assertEqual(again.read_bytes(), path.read_bytes())

    def test_document_matches_its_schema(self):
        validate_named(measure().to_dict(), "pointwise_measurement")

    def test_canonical_json_refuses_a_non_finite_number(self):
        for value in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(value=repr(value)):
                data = measure().to_dict()
                data["outputs"]["ceff_m"]["value"] = value
                with self.assertRaises(ValueError):
                    canonical_json(data)


class Integrity(Contract):
    def tampered(self, mutate):
        data = measure().to_dict()
        mutate(data)
        with self.assertRaises(PointwiseMeasurementError) as caught:
            PointwiseMeasurement.from_dict(data)
        self.assertEqual(caught.exception.code, "RESULT_INVALID", str(caught.exception))

    def test_tampered_result_id_is_rejected(self):
        self.tampered(lambda d: d.update(result_id="0" * 64))

    def test_tampered_output_value_is_rejected(self):
        self.tampered(lambda d: d["outputs"]["ceff_m"].update(value=0.5))
        self.tampered(lambda d: d["outputs"]["arm_reach_nm"].update(value=7.0))

    def test_tampered_intermediate_is_rejected(self):
        self.tampered(lambda d: d["intermediates"]["mean_square_span_nm2"].update(value=49.0))

    def test_tampered_status_or_diagnostics_are_rejected(self):
        self.tampered(lambda d: d.update(status="UNAVAILABLE"))
        self.tampered(lambda d: d["diagnostics"].append(
            {"severity": "error", "code": "X", "message": "invented"}))

    def test_tampered_declaration_parameter_or_provenance_is_rejected(self):
        self.tampered(lambda d: d["declaration"].update(context="monomer"))
        self.tampered(lambda d: d["parameters"]["values"]["kappa"].update(value=3.0))
        self.tampered(lambda d: d["provenance"].update(execution_id="syn-exec-2"))

    def test_tampered_input_or_parameter_record_shape_is_rejected(self):
        """A recorded number is either a value or a reason token, never both, and never both
        unavailable and present."""
        self.tampered(lambda d: d["inputs"]["distance_nm"].update(value_token="nan"))
        self.tampered(lambda d: d["parameters"]["values"]["c"].update(value_token="inf"))
        self.tampered(lambda d: d["inputs"]["segment_count"].update(
            availability="UNAVAILABLE", unavailable_reason="claimed absent"))

    def test_a_self_consistent_value_beside_its_reason_token_is_rejected(self):
        """The re-derivation reproduces such a document unchanged, so the record-shape rule,
        not the comparison, has to reject it."""
        for mutate in (lambda d: d["inputs"]["distance_nm"].update(value=3.0),
                       lambda d: d["parameters"]["values"]["c"].update(value=4.0)):
            with self.subTest():
                data = measure(inputs=inputs(**{"distance_nm.value": float("nan")}),
                               parameters=parameters(c=float("nan"))).to_dict()
                self.assertEqual(data["status"], "REJECTED")
                mutate(data)
                data.pop("result_id")
                data["result_id"] = hash_config(data)
                with self.assertRaises(PointwiseMeasurementError) as caught:
                    PointwiseMeasurement.from_dict(data)
                self.assertEqual(caught.exception.code, "RESULT_INVALID", str(caught.exception))

    def test_tampered_formulation_or_assumptions_are_rejected(self):
        self.tampered(lambda d: d["formulation"].update(evaluation_form="direct", source_card="elsewhere"))
        self.tampered(lambda d: d["assumptions"].update(aggregation="declared means included"))

    def test_consistent_relabelling_of_a_rejected_result_is_rejected(self):
        """A rejected result cannot be turned into a computed one by editing the outcome fields."""
        data = measure(parameters=parameters(c=-4.0)).to_dict()
        data["status"] = "COMPUTED"
        data["diagnostics"] = []
        data["outputs"]["arm_reach_nm"]["value"] = 6.0
        data["outputs"]["arm_reach_nm"]["missing_reason"] = None
        data.pop("result_id")
        data["result_id"] = "0" * 64
        with self.assertRaises(PointwiseMeasurementError) as caught:
            PointwiseMeasurement.from_dict(data)
        self.assertEqual(caught.exception.code, "RESULT_INVALID")

    def test_reload_rejects_a_document_that_is_not_this_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp).resolve() / "other.json"
            path.write_bytes(b'{"schema_version": "quantity_summary/1"}')
            with self.assertRaises(PointwiseMeasurementError) as caught:
                load_pointwise_measurement(path)
            self.assertEqual(caught.exception.code, "RESULT_INVALID")


class EvidenceConversion(Contract):
    def test_converts_a_computed_result_to_one_metric_record(self):
        expected = card_f02(3.0, 9.0, 4.0, 1.0, 2.0)
        result = measure()
        metric = to_candidate_evidence_metric(result, "ceff_m")
        self.assertEqual(metric, {
            "name": "ceff_m", "raw_value": expected["q"], "value": expected["q"],
            "context": "complex", "category": "derived_measurement", "unit": "U", "scale": None,
            "source": {"path": "/synthetic/producer/pairs.json", "sha256": SHA, "row": 1},
            "provenance": {"model_id": None, "checkpoint_id": None, "seed": None},
            "missing_reason": None})
        record = CandidateEvidence(candidate_id="syn-candidate", sequence_hash=None, target_id="syn-target",
                                   conformer_id=None, metrics=[metric],
                                   missing_values={"sequence_hash": "synthetic fixture",
                                                   "conformer_id": "synthetic fixture"})
        self.assertEqual(record.to_dict()["metrics"][0], metric)

    def test_both_outputs_convert_and_stay_separate(self):
        result = measure()
        metrics = [to_candidate_evidence_metric(result, name) for name in ("ceff_m", "arm_reach_nm")]
        self.assertEqual([m["unit"] for m in metrics], ["U", "nm"])
        record = CandidateEvidence(candidate_id="syn-candidate", sequence_hash=None, target_id=None,
                                   conformer_id=None, metrics=metrics,
                                   missing_values={"sequence_hash": "synthetic fixture",
                                                   "target_id": "synthetic fixture",
                                                   "conformer_id": "synthetic fixture"})
        self.assertEqual(len(record.to_dict()["metrics"]), 2)

    def test_a_non_computed_result_converts_with_its_reason_and_no_value(self):
        for over, status, code in (
                (dict(parameters=parameters(c=-4.0)), "REJECTED", "REACH_DOMAIN_VIOLATION"),
                (dict(inputs=inputs(**{"segment_count.availability": "UNAVAILABLE",
                                       "segment_count.value": None,
                                       "segment_count.unavailable_reason": "absent"})),
                 "UNAVAILABLE", "INPUT_UNAVAILABLE")):
            with self.subTest(status=status):
                result = measure(**over)
                self.assertEqual(result.status, status)
                metric = to_candidate_evidence_metric(result, "ceff_m")
                self.assertIsNone(metric["value"])
                self.assertIsNone(metric["raw_value"])
                diagnostic = result.to_dict()["diagnostics"][0]
                self.assertEqual(diagnostic["code"], code)
                self.assertEqual(metric["missing_reason"], f"{code}: {diagnostic['message']}")
                CandidateEvidence(candidate_id="c", sequence_hash=None, target_id=None, conformer_id=None,
                                  metrics=[metric],
                                  missing_values={"sequence_hash": "s", "target_id": "t",
                                                  "conformer_id": "c"}).to_dict()

    def test_conversion_refuses_an_unknown_quantity_or_an_unverified_result(self):
        with self.assertRaises(PointwiseMeasurementError) as caught:
            to_candidate_evidence_metric(measure(), "spatial_density")
        self.assertEqual(caught.exception.code, "CONTRACT_INVALID")
        with self.assertRaises(PointwiseMeasurementError) as caught:
            to_candidate_evidence_metric(measure().to_dict(), "ceff_m")
        self.assertEqual(caught.exception.code, "CONTRACT_INVALID")


if __name__ == "__main__":
    unittest.main()
