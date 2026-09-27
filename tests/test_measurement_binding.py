"""Synthetic contract tests for measurement_binding; only export tests write temporary files.

The fixtures are candidate_evidence exports whose producer already declares the two card
F02 pair scalars with their required units. Nothing here converts, reconstructs or infers
a distance or a segment count.
"""
import builtins
from copy import deepcopy
import io
import math
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from structure_audit import measurement_binding as mb
from structure_audit.evidence import CandidateEvidence
from structure_audit.linked_transfer import link_transfer
from structure_audit.measurement_binding import (
    BoundMeasurement, MeasurementBinding, MeasurementBindingError,
    bind_pointwise_measurement, bound_candidate_evidence, load_measurement_binding,
)
from structure_audit.provenance import hash_config, hash_file, write_json_new
from structure_audit.quantity_summary import summarize_quantity
from structure_audit.validation import validate_named

FIXTURES = (Path(__file__).parent / "fixtures" / "measurement_binding").resolve()
LIST, SINGLE = "candidate_evidence_list_v1", "candidate_evidence_v1"
DIST, SEG = "syn-pair:/distance_nm", "syn-pair:/segment_count"
BINDING = {"distance_nm": {"metric_name": DIST, "category": "declared_geometry", "scale": None},
           "segment_count": {"metric_name": SEG, "category": "declared_span_composition",
                             "scale": None}}
DECLARATION = {"pair_id": "syn-pair-a", "context": "complex",
               "category": "derived_measurement", "scale": None}
PARAMETERS = {"profile_id": "syn-profile", "profile_version": "1",
              "values": {"c": {"unit": "nm^2", "value": 4.0},
                         "eta": {"unit": "dimensionless", "value": 1.0},
                         "kappa": {"unit": "U*nm^3", "value": 2.0}}}
ACTIVATION = {"opt_in": True, "lane": "experimental",
              "formulation_id": "pointwise_measurement_v1", "formulation_version": "astra-F02/1"}
RUN = {"pipeline_run_id": "syn-run-1", "execution_id": "syn-exec-1"}


def selection(name="pair_producer.json", *, layout=LIST, root=FIXTURES, artifact_id="syn-producer",
              sha256=None):
    path = Path(root) / name
    return {"artifact_id": artifact_id, "path": str(path),
            "sha256": sha256 or hash_file(path), "layout": layout}


def selector(candidate="syn-pair-a", target="syn-target", conformer=None):
    return {"candidate_id": candidate, "target_id": target, "conformer_id": conformer}


def bind(**over):
    payload = {"selector": selector(), "binding": deepcopy(BINDING),
               "declaration": deepcopy(DECLARATION), "parameters": deepcopy(PARAMETERS),
               "activation": deepcopy(ACTIVATION), "run": deepcopy(RUN)}
    payload.update(over)
    if "selection" not in payload:  # built lazily: no default must open a file for a caller
        payload["selection"] = selection()
    return bind_pointwise_measurement(**payload)


def card_f02(d, n, c, eta, kappa):
    """Card F02 written out independently of the modules under test."""
    m = c * (n ** eta)
    return kappa * ((3 / (2 * math.pi * m)) ** (3 / 2)) * math.exp(-(3 * d ** 2) / (2 * m))


class Contract(unittest.TestCase):
    def error(self, code, **over):
        with self.assertRaises(MeasurementBindingError) as caught:
            bind(**over)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        self.assertEqual(caught.exception.diagnostics[0]["code"], code)
        return caught.exception


class Temp(Contract):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()


class Binding(Contract):
    def test_binds_a_declared_pair_and_computes_card_f02(self):
        out = bind()
        self.assertIsInstance(out, BoundMeasurement)
        self.assertEqual(out.measurement.status, "COMPUTED")
        self.assertEqual(out.measurement.to_dict()["outputs"]["ceff_m"]["value"],
                         card_f02(3.0, 9.0, 4.0, 1.0, 2.0))
        self.assertEqual(out.measurement.to_dict()["outputs"]["arm_reach_nm"]["value"], 6.0)
        data = out.binding.to_dict()
        self.assertEqual(data["schema_version"], "measurement_binding/1")
        self.assertEqual(data["measurement"]["result_id"], out.measurement.result_id)
        self.assertEqual(data["measurement"]["status"], "COMPUTED")
        validate_named(data, "measurement_binding")

    def test_bound_inputs_carry_the_declared_values_and_their_locators(self):
        bound = bind().binding.to_dict()["bound_inputs"]
        self.assertEqual(bound["distance_nm"]["bound_value"], 3.0)
        self.assertEqual(bound["distance_nm"]["declared_unit"], "nm")
        self.assertEqual(bound["distance_nm"]["required_unit"], "nm")
        self.assertEqual(bound["distance_nm"]["quantity_definition_id"], "distance_nm")
        self.assertEqual(bound["distance_nm"]["metric_name"], DIST)
        self.assertEqual(bound["distance_nm"]["metric_index"], 0)
        self.assertEqual(bound["distance_nm"]["upstream_source"],
                         {"path": "/synthetic/producer-pair/pairs.json", "sha256": "b" * 64, "row": 7})
        self.assertEqual(bound["segment_count"]["bound_value"], 9.0)
        self.assertEqual(bound["segment_count"]["declared_unit"], "dimensionless")
        self.assertEqual(bound["segment_count"]["quantity_definition_id"],
                         "segment_count_dimensionless")
        for entry in bound.values():
            self.assertEqual(entry["availability"], "AVAILABLE")
            self.assertIsNone(entry["unavailable_reason"])

    def test_single_record_layout_binds(self):
        out = bind(selection=selection("pair_producer_single.json", layout=SINGLE),
                   selector=selector("syn-pair-single"))
        self.assertEqual(out.measurement.status, "COMPUTED")
        self.assertEqual(out.binding.to_dict()["payload"]["record_count"], 1)
        self.assertEqual(out.binding.to_dict()["payload"]["record_index"], 0)

    def test_boundary_zero_distance_binds_and_computes(self):
        out = bind(selector=selector("syn-pair-d"))
        self.assertEqual(out.measurement.status, "COMPUTED")
        self.assertEqual(out.measurement.to_dict()["outputs"]["ceff_m"]["value"],
                         card_f02(0.0, 1.0, 4.0, 1.0, 2.0))

    def test_the_measurement_formula_is_not_touched_by_this_layer(self):
        """The bound result equals the frozen layer called directly on the same envelope."""
        from structure_audit.pointwise_measurement import measure_pointwise
        out = bind()
        request = out.binding.to_dict()["measurement_request"]
        self.assertEqual(measure_pointwise(**deepcopy(request)).to_json_bytes(),
                         out.measurement.to_json_bytes())


class Availability(Contract):
    def test_absent_declared_metric_is_unavailable(self):
        out = bind(selector=selector("syn-pair-c"))
        self.assertEqual(out.measurement.status, "UNAVAILABLE")
        entry = out.binding.to_dict()["bound_inputs"]["distance_nm"]
        self.assertEqual(entry["availability"], "UNAVAILABLE")
        self.assertTrue(entry["unavailable_reason"].startswith("METRIC_ABSENT:"))
        self.assertIsNone(entry["bound_value"])
        self.assertIsNone(entry["declared_unit"])
        self.assertIsNone(out.measurement.to_dict()["outputs"]["ceff_m"]["value"])

    def test_null_metric_value_is_unavailable_with_the_producer_reason(self):
        out = bind(selector=selector("syn-pair-b"))
        self.assertEqual(out.measurement.status, "UNAVAILABLE")
        entry = out.binding.to_dict()["bound_inputs"]["distance_nm"]
        self.assertEqual(entry["unavailable_reason"],
                         "VALUE_UNAVAILABLE: upstream geometry report absent")
        self.assertEqual(entry["metric_index"], 0)
        self.assertIsNone(entry["bound_value"])

    def test_a_declared_metric_name_that_is_absent_is_unavailable_not_invented(self):
        binding = deepcopy(BINDING)
        binding["distance_nm"]["metric_name"] = "syn-pair:/not_exported"
        out = bind(binding=binding)
        self.assertEqual(out.measurement.status, "UNAVAILABLE")
        self.assertIsNone(out.binding.to_dict()["bound_inputs"]["distance_nm"]["bound_value"])

    def test_out_of_domain_and_inexact_values_reach_the_frozen_rejection(self):
        for candidate, code in (("syn-pair-e", "INPUT_DOMAIN_VIOLATION"),
                                ("syn-pair-f", "INPUT_NOT_EXACTLY_REPRESENTABLE")):
            with self.subTest(candidate=candidate):
                out = bind(selector=selector(candidate))
                self.assertEqual(out.measurement.status, "REJECTED")
                self.assertEqual(out.measurement.to_dict()["diagnostics"][0]["code"], code)
                self.assertIsNone(out.measurement.to_dict()["outputs"]["ceff_m"]["value"])

    def test_an_exact_integer_metric_value_binds(self):
        out = bind(selector=selector("syn-pair-f"))
        self.assertEqual(out.binding.to_dict()["bound_inputs"]["distance_nm"]["bound_value"], 3)
        self.assertEqual(out.binding.to_dict()["bound_inputs"]["segment_count"]["bound_value"],
                         2 ** 53 + 1)


class Selection(Temp):
    def test_wrong_artifact_hash_is_rejected(self):
        self.error("ARTIFACT_HASH_MISMATCH", selection=selection(sha256="0" * 64))

    def test_malformed_sha256_is_refused(self):
        self.error("CONTRACT_INVALID", selection=selection(sha256="not-a-digest"))

    def test_unsupported_layout_is_refused(self):
        self.error("CONTRACT_INVALID", selection=selection(layout="quantity_summary_v1"))
        self.error("CONTRACT_INVALID", selection=selection(layout="pointwise_measurement_v1"))

    def test_declared_layout_must_match_the_observed_json_form(self):
        self.error("ARTIFACT_LAYOUT_MISMATCH", selection=selection(layout=SINGLE))
        self.error("ARTIFACT_LAYOUT_MISMATCH",
                   selection=selection("pair_producer_single.json", layout=LIST),
                   selector=selector("syn-pair-single"))

    def test_path_must_be_absolute_canonical_and_a_regular_file(self):
        alias = self.root / "alias.json"
        alias.symlink_to(FIXTURES / "pair_producer.json")
        for path in (str(alias), "pair_producer.json", str(self.root),
                     str(self.root / "missing.json")):
            with self.subTest(path=path):
                self.error("ARTIFACT_PATH_INVALID",
                           selection={**selection(), "path": path})

    def test_selector_not_found(self):
        self.error("SELECTOR_NOT_FOUND", selector=selector("syn-pair-absent"))
        self.error("SELECTOR_NOT_FOUND", selector=selector("syn-pair-a", target="other"))
        self.error("SELECTOR_NOT_FOUND", selector=selector("syn-pair-a", conformer="c1"))

    def test_selector_ambiguous(self):
        exc = self.error("SELECTOR_AMBIGUOUS",
                         selection=selection("pair_producer_ambiguous.json"))
        self.assertIn("2 records", str(exc))

    def test_artifact_changed_before_return(self):
        with patch.object(mb, "hash_file", return_value="0" * 64):
            self.error("ARTIFACT_CHANGED")

    def test_malformed_artifact_is_refused(self):
        for name, raw, code in (("bad.json", b"{", "ARTIFACT_PARSE_ERROR"),
                                ("dup.json", b'{"a": 1, "a": 2}', "ARTIFACT_PARSE_ERROR"),
                                ("nan.json", b'[{"v": NaN}]', "ARTIFACT_PARSE_ERROR"),
                                ("shape.json", b'[{"candidate_id": "x"}]', "ARTIFACT_RECORD_INVALID")):
            with self.subTest(name=name):
                path = self.root / name
                path.write_bytes(raw)
                self.error(code, selection=selection(name, root=self.root))


class Identity(Contract):
    def test_incompatible_unit_is_refused(self):
        exc = self.error("QUANTITY_DEFINITION_INCOMPATIBLE",
                         selection=selection("pair_producer_angstrom.json"))
        self.assertIn("angstrom", str(exc))

    def test_incompatible_declared_category_or_scale_is_refused(self):
        for name, field, value in (("distance_nm", "category", "model_confidence"),
                                   ("distance_nm", "scale", "0-1"),
                                   ("segment_count", "category", "declared_geometry")):
            with self.subTest(name=name, field=field):
                binding = deepcopy(BINDING)
                binding[name][field] = value
                self.error("QUANTITY_DEFINITION_INCOMPATIBLE", binding=binding)

    def test_context_is_part_of_the_metric_locator(self):
        out = bind(declaration={**DECLARATION, "context": "monomer"})
        self.assertEqual(out.measurement.status, "UNAVAILABLE")
        for entry in out.binding.to_dict()["bound_inputs"].values():
            self.assertTrue(entry["unavailable_reason"].startswith("METRIC_ABSENT:"))

    def test_conflicting_upstream_sources_are_refused(self):
        self.error("SOURCE_IDENTITY_CONFLICT",
                   selection=selection("pair_producer_source_conflict.json"))

    def test_declaration_and_activation_are_checked_by_the_frozen_layer(self):
        self.error("CONTRACT_INVALID", declaration={**DECLARATION, "extra": 1})
        self.error("ACTIVATION_REQUIRED", activation={**ACTIVATION, "opt_in": False})
        self.error("ACTIVATION_REQUIRED", activation={**ACTIVATION, "lane": "baseline"})

    def test_a_declaration_the_frozen_layer_rejects_yields_a_rejected_measurement(self):
        out = bind(declaration={**DECLARATION, "category": "model_confidence"})
        self.assertEqual(out.measurement.status, "REJECTED")
        self.assertEqual(out.measurement.to_dict()["diagnostics"][0]["code"],
                         "QUANTITY_IDENTITY_MISMATCH")


class Envelope(Contract):
    def test_every_block_field_is_required(self):
        for block, template in (("selection", selection()), ("selector", selector()),
                                ("run", RUN)):
            for field in template:
                with self.subTest(block=block, field=field):
                    self.error("CONTRACT_INVALID",
                               **{block: {k: v for k, v in template.items() if k != field}})
        for name in ("distance_nm", "segment_count"):
            with self.subTest(block="binding", name=name):
                self.error("CONTRACT_INVALID",
                           binding={k: v for k, v in BINDING.items() if k != name})
            for field in ("metric_name", "category", "scale"):
                with self.subTest(block="binding", name=name, field=field):
                    binding = deepcopy(BINDING)
                    binding[name].pop(field)
                    self.error("CONTRACT_INVALID", binding=binding)

    def test_unexpected_field_is_refused(self):
        self.error("CONTRACT_INVALID", selector={**selector(), "extra": 1})
        self.error("CONTRACT_INVALID", run={**RUN, "timestamp": "now"})

    def test_run_identities_are_declared_never_derived(self):
        first = bind().binding.to_dict()
        second = bind(run={"pipeline_run_id": "syn-run-2", "execution_id": "syn-exec-2"}).binding.to_dict()
        self.assertNotEqual(first["binding_id"], second["binding_id"])
        self.assertEqual(first["provenance"]["payload_sha256"], second["provenance"]["payload_sha256"])
        self.assertEqual(first["provenance"]["mapping_hash"], second["provenance"]["mapping_hash"])


class Provenance(Contract):
    def test_available_and_unavailable_fields_are_explicit(self):
        provenance = bind().binding.to_dict()["provenance"]
        unavailable = {"producer_result_id", "producer_config_hash", "runtime_versions"}
        for field, entry in provenance.items():
            with self.subTest(field=field):
                self.assertEqual(set(entry), {"value", "unavailable_reason"})
                if field in unavailable:
                    self.assertIsNone(entry["value"])
                    self.assertTrue(entry["unavailable_reason"])
                else:
                    self.assertIsNotNone(entry["value"])
                    self.assertIsNone(entry["unavailable_reason"])

    def test_content_hashes_are_the_hashes_of_what_they_name(self):
        data = bind().binding.to_dict()
        self.assertEqual(data["provenance"]["mapping_hash"]["value"], hash_config(data["mapping"]))
        self.assertEqual(data["provenance"]["payload_sha256"]["value"], hash_config(data["payload"]))
        binding = deepcopy(BINDING)
        binding["distance_nm"]["metric_name"] = "syn-pair:/other_distance_nm"
        other = bind(binding=binding).binding.to_dict()
        self.assertNotEqual(other["provenance"]["mapping_hash"]["value"],
                            data["provenance"]["mapping_hash"]["value"])
        self.assertNotEqual(other["provenance"]["payload_sha256"]["value"],
                            data["provenance"]["payload_sha256"]["value"])

    def test_content_identities_are_recorded(self):
        data = bind().binding.to_dict()
        provenance = data["provenance"]
        self.assertEqual(provenance["artifact_sha256"]["value"], selection()["sha256"])
        self.assertEqual(provenance["artifact_id"]["value"], "syn-producer")
        self.assertEqual(provenance["source_hash"]["value"], "b" * 64)
        self.assertEqual(provenance["source"]["value"]["row"], 7)
        self.assertEqual(provenance["measurement_method_id"]["value"], "pointwise_measurement_v1")
        self.assertEqual(provenance["measurement_method_version"]["value"], "astra-F02/1")
        self.assertEqual(provenance["method_id"]["value"], "candidate_evidence_pair_binding")

    def test_upstream_source_is_unavailable_when_no_metric_declares_one(self):
        provenance = bind(selector=selector("syn-pair-c"),
                          binding={**deepcopy(BINDING),
                                   "segment_count": {"metric_name": "syn-pair:/absent",
                                                     "category": "declared_span_composition",
                                                     "scale": None}}).binding.to_dict()["provenance"]
        for field in ("source", "source_hash"):
            with self.subTest(field=field):
                self.assertIsNone(provenance[field]["value"])
                self.assertEqual(provenance[field]["unavailable_reason"],
                                 "no bound metric declares an upstream source")

    def test_producer_model_provenance_is_carried_into_the_measurement(self):
        model = bind().binding.to_dict()["measurement_request"]["provenance"]["model"]
        self.assertEqual(model, {"model_id": "synthetic-geometry-report",
                                 "checkpoint_id": None, "seed": 0})

    def test_the_measurement_source_is_the_hashed_artifact(self):
        data = bind().binding.to_dict()
        source = data["measurement_request"]["provenance"]["source"]
        self.assertEqual(source, {"path": selection()["path"],
                                  "sha256": selection()["sha256"], "row": None})


class Reading(Temp):
    def recorded(self, call):
        opened = []

        def record(target, *args, **kwargs):
            opened.append(os.fspath(target) if not isinstance(target, int) else target)
            return self.real(target, *args, **kwargs)

        self.real = builtins.open
        with patch.object(builtins, "open", record), patch.object(io, "open", record):
            result = call()
        schemas = Path(mb.__file__).resolve().parent / "schemas"
        outside = [p for p in opened
                   if isinstance(p, str) and Path(p).resolve().parent != schemas]
        return result, opened, outside

    def test_only_the_selected_file_is_opened(self):
        shutil.copy(FIXTURES / "pair_producer.json", self.root / "pair_producer.json")
        decoy = self.root / "decoy.json"
        shutil.copy(FIXTURES / "pair_producer_single.json", decoy)
        chosen = selection(root=self.root)
        result, opened, outside = self.recorded(lambda: bind(selection=chosen))
        self.assertEqual(result.measurement.status, "COMPUTED")
        self.assertEqual(sorted({Path(p).resolve() for p in outside}),
                         [Path(chosen["path"]).resolve()])
        self.assertNotIn(str(decoy), opened)
        self.assertGreaterEqual(sum(p == chosen["path"] for p in opened), 2)  # read, then re-hash


class Serialization(Temp):
    def test_identical_selections_are_byte_identical(self):
        self.assertEqual(bind().binding.to_json_bytes(), bind().binding.to_json_bytes())
        self.assertEqual(bind().binding.binding_id, bind().binding.binding_id)

    def test_export_reload_reserialize_is_stable(self):
        original = bind().binding
        path = self.root / "binding.json"
        write_json_new(path, original.to_dict())
        reloaded = load_measurement_binding(path)
        self.assertEqual(reloaded.to_json_bytes(), original.to_json_bytes())
        self.assertEqual(reloaded.binding_id, original.binding_id)
        self.assertEqual(reloaded.measurement.to_json_bytes(),
                         bind().measurement.to_json_bytes())
        again = self.root / "again.json"
        write_json_new(again, reloaded.to_dict())
        self.assertEqual(again.read_bytes(), path.read_bytes())

    def test_content_identity_is_location_independent(self):
        """Moving the artifact changes the selection identity, not the bound content."""
        shutil.copy(FIXTURES / "pair_producer.json", self.root / "pair_producer.json")
        moved = bind(selection=selection(root=self.root)).binding.to_dict()
        here = bind().binding.to_dict()
        self.assertNotEqual(moved["binding_id"], here["binding_id"])
        for field in ("payload_sha256", "mapping_hash", "artifact_sha256", "source_hash"):
            with self.subTest(field=field):
                self.assertEqual(moved["provenance"][field], here["provenance"][field])

    def test_tampering_is_rejected(self):
        for mutate in (lambda d: d.update(binding_id="0" * 64),
                       lambda d: d["bound_inputs"]["distance_nm"].update(bound_value=7.0),
                       lambda d: d["payload"]["metrics"]["distance_nm"].update(value=7.0),
                       lambda d: d["measurement"].update(result_id="0" * 64),
                       lambda d: d["measurement"].update(status="REJECTED"),
                       lambda d: d["provenance"]["payload_sha256"].update(value="0" * 64),
                       lambda d: d["provenance"]["producer_result_id"].update(value="invented"),
                       lambda d: d["measurement_request"]["parameters"]["values"]["kappa"]
                                  .update(value=3.0),
                       lambda d: d["mapping"]["required_units"].update(distance_nm="angstrom"),
                       lambda d: d["producer"].update(artifact_sha256="0" * 64)):
            with self.subTest():
                data = bind().binding.to_dict()
                mutate(data)
                with self.assertRaises(MeasurementBindingError) as caught:
                    MeasurementBinding.from_dict(data)
                self.assertEqual(caught.exception.code, "BINDING_INVALID", str(caught.exception))

    def test_reload_refuses_a_document_that_is_not_this_contract(self):
        path = self.root / "other.json"
        path.write_bytes(b'{"schema_version": "quantity_summary/1"}')
        with self.assertRaises(MeasurementBindingError) as caught:
            load_measurement_binding(path)
        self.assertEqual(caught.exception.code, "BINDING_INVALID")


class Downstream(Temp):
    def evidence_artifact(self, out, name="derived.json", quantity_ids=("ceff_m", "arm_reach_nm")):
        record = bound_candidate_evidence(out, list(quantity_ids))
        path = self.root / name
        write_json_new(path, record.to_dict())
        return record, path

    def test_conversion_to_one_candidate_evidence_record(self):
        out = bind()
        record, _ = self.evidence_artifact(out)
        self.assertIsInstance(record, CandidateEvidence)
        data = record.to_dict()
        self.assertEqual(data["candidate_id"], "syn-pair-a")
        self.assertEqual(data["target_id"], "syn-target")
        self.assertEqual([m["name"] for m in data["metrics"]], ["ceff_m", "arm_reach_nm"])
        self.assertEqual(data["metrics"][0]["value"], card_f02(3.0, 9.0, 4.0, 1.0, 2.0))
        self.assertEqual(data["metrics"][0]["unit"], "U")
        self.assertEqual(data["metrics"][1]["unit"], "nm")
        self.assertEqual(data["provenance"], {"model_id": "synthetic-geometry-report",
                                              "checkpoint_id": None, "seed": 0})
        self.assertIn(out.binding.binding_id, data["warnings"][0])

    def test_quantity_summary_reads_the_derived_artifact_with_no_special_case(self):
        out = bind()
        _, path = self.evidence_artifact(out)
        summary = summarize_quantity(
            quantity={"quantity_id": "ceff_m", "context": "complex",
                      "category": "derived_measurement", "unit": "U", "scale": None},
            artifacts=[{"artifact_id": "derived", "path": str(path), "sha256": hash_file(path),
                        "layout": "candidate_evidence_v1", "metric_name": "ceff_m"}])
        statistics = summary.to_dict()["statistics"]
        self.assertEqual(statistics["status"], "SUMMARIZED")
        self.assertEqual(statistics["count"], 1)
        self.assertEqual(statistics["min"], card_f02(3.0, 9.0, 4.0, 1.0, 2.0))
        self.assertEqual(statistics["min"], statistics["max"])

    def test_linked_transfer_reads_the_derived_artifact_with_no_special_case(self):
        out = bind()
        _, path = self.evidence_artifact(out)
        outcome = link_transfer(
            selection={"artifact_id": "derived", "path": str(path), "sha256": hash_file(path),
                       "layout": "candidate_evidence_v1"},
            request={"consumer_id": "syn-consumer",
                     "quantity": {"quantity_id": "arm_reach_nm", "context": "complex",
                                  "category": "derived_measurement", "unit": "nm", "scale": None},
                     "item": {"metric_name": "arm_reach_nm", "candidate_id": "syn-pair-a",
                              "target_id": "syn-target", "conformer_id": None}})
        self.assertIsNotNone(outcome.transfer)
        self.assertEqual(outcome.receipt.to_dict()["outcome"], "ADMITTED")
        self.assertEqual(outcome.transfer.to_dict()["payload"]["value"], 6.0)

    def test_an_unavailable_measurement_exports_its_reason(self):
        out = bind(selector=selector("syn-pair-c"))
        record, path = self.evidence_artifact(out, "unavailable.json", ("ceff_m",))
        metric = record.to_dict()["metrics"][0]
        self.assertIsNone(metric["value"])
        self.assertTrue(metric["missing_reason"].startswith("INPUT_UNAVAILABLE:"))
        summary = summarize_quantity(
            quantity={"quantity_id": "ceff_m", "context": "complex",
                      "category": "derived_measurement", "unit": "U", "scale": None},
            artifacts=[{"artifact_id": "derived", "path": str(path), "sha256": hash_file(path),
                        "layout": "candidate_evidence_v1", "metric_name": "ceff_m"}])
        data = summary.to_dict()
        self.assertEqual(data["statistics"]["status"], "NO_ACCEPTED_VALUES")
        self.assertEqual(data["values"][0]["exclusion_reason"], "VALUE_UNAVAILABLE")

    def test_conversion_refuses_an_unknown_output_or_a_non_binding(self):
        out = bind()
        for quantity_ids in (["spatial_density"], [], ["ceff_m", "ceff_m"], "ceff_m"):
            with self.subTest(quantity_ids=quantity_ids):
                with self.assertRaises(MeasurementBindingError):
                    bound_candidate_evidence(out, quantity_ids)
        with self.assertRaises(MeasurementBindingError):
            bound_candidate_evidence(out.binding, ["ceff_m"])


if __name__ == "__main__":
    unittest.main()
