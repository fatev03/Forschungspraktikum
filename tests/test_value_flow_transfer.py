"""Synthetic contract tests for value_flow_transfer; only export tests write temporary files.

Every fixture is a real producer document written by the closed layers themselves:
producer_*.json by pointwise_measurement, f01_distance.json by f01_coordinate_admission.
No value in this suite is recomputed; the expected numbers are read from the producer
documents, which are the calculation authority.
"""
from copy import deepcopy
import dataclasses
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from structure_audit import value_flow_transfer as vft
from structure_audit.value_flow_transfer import (
    ValueFlowEnvelope, ValueFlowOutcome, ValueFlowReceipt, ValueFlowTransferError,
    load_value_flow_envelope, load_value_flow_receipt, transfer_value_flow,
)
from structure_audit.validation import validate_named

FIXTURES = (Path(__file__).parent / "fixtures" / "value_flow_transfer").resolve()
IDENTITY_FIELDS = ("quantity_id", "quantity_definition_id", "context", "category", "unit", "scale")
CONSUMER = {"consumer_id": "syn-consumer", "export_id": "syn-export-1"}


def digest_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def document(name, root=FIXTURES):
    return json.loads((Path(root) / name).read_bytes())


def producer(name="producer_computed.json", *, root=FIXTURES, producer_id="syn-producer",
             sha256=None, layout="pointwise_measurement_v1"):
    path = Path(root) / name
    return {"producer_id": producer_id, "path": str(path),
            "sha256": sha256 or digest_of(path), "layout": layout}


def quantities(name="producer_computed.json", root=FIXTURES):
    outputs = document(name, root)["outputs"]
    return {n: {k: outputs[n][k] for k in IDENTITY_FIELDS} for n in ("ceff_m", "arm_reach_nm")}


def expected(name="producer_computed.json", *, root=FIXTURES, result_id=None,
             profile_id="syn-profile", profile_version="1", identities=None):
    return {"producer_result_id": result_id or document(name, root)["result_id"],
            "configuration": {"profile_id": profile_id, "profile_version": profile_version},
            "quantities": identities or quantities(name, root)}


def reference(*, root=FIXTURES, reference_id="ref-f01", sha256=None, result_id=None,
              definition="distance_nm", name="f01_distance.json"):
    path = Path(root) / name
    return {"reference_id": reference_id, "kind": "f01_coordinate_distance_v1",
            "path": str(path), "sha256": sha256 or digest_of(path),
            "result_id": result_id or document(name, root)["result_id"],
            "quantity_definition_id": definition}


def transfer(**over):
    payload = {"consumer": deepcopy(CONSUMER)}
    payload.update(over)
    if "producer" not in payload:
        payload["producer"] = producer()
    if "expected" not in payload:
        payload["expected"] = expected()
    if "measurement_references" not in payload:
        payload["measurement_references"] = [reference()]
    return transfer_value_flow(**payload)


class Contract(unittest.TestCase):
    def rejected(self, reason, *, stage=None, **over):
        outcome = transfer(**over)
        receipt = outcome.receipt.to_dict()
        self.assertEqual(receipt["outcome"], "REJECTED", receipt)
        self.assertEqual(receipt["reason"], reason, receipt)
        self.assertIsNone(outcome.envelope)
        self.assertIsNone(receipt["chain"]["envelope_id"])
        self.assertTrue(receipt["detail"])
        failing = [c for c in receipt["checks"] if c["result"] == "FAILED"]
        self.assertEqual(len(failing), 1, receipt["checks"])
        if stage is not None:
            self.assertEqual(failing[0]["stage"], stage, receipt["checks"])
        index = [c["stage"] for c in receipt["checks"]].index(failing[0]["stage"])
        results = [c["result"] for c in receipt["checks"]]
        self.assertEqual(results[:index], ["PASSED"] * index)
        self.assertEqual(results[index + 1:], ["NOT_REACHED"] * (len(results) - index - 1))
        return outcome

    def error(self, code, **over):
        with self.assertRaises(ValueFlowTransferError) as caught:
            transfer(**over)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        self.assertEqual(caught.exception.diagnostics[0]["code"], code)
        return caught.exception


class ValidTransfer(Contract):
    def test_a_valid_pair_is_accepted_and_carried_unchanged(self):
        outcome = transfer()
        self.assertIsInstance(outcome, ValueFlowOutcome)
        self.assertEqual(outcome.receipt.outcome, "ACCEPTED")
        self.assertEqual(outcome.envelope.status, "ACCEPTED")
        source = document("producer_computed.json")["outputs"]
        self.assertEqual(outcome.envelope.value("ceff_m"), source["ceff_m"]["value"])
        self.assertEqual(outcome.envelope.value("arm_reach_nm"), source["arm_reach_nm"]["value"])
        data = outcome.envelope.to_dict()
        for name in ("ceff_m", "arm_reach_nm"):
            with self.subTest(name=name):
                self.assertEqual({k: data["values"][name][k] for k in IDENTITY_FIELDS},
                                 {k: source[name][k] for k in IDENTITY_FIELDS})
        validate_named(data, "value_flow_envelope")
        validate_named(outcome.receipt.to_dict(), "value_flow_receipt")

    def test_the_envelope_carries_producer_and_configuration_identity(self):
        data = transfer().envelope.to_dict()
        source = document("producer_computed.json")
        self.assertEqual(data["producer"], {
            "producer_id": "syn-producer", "layout": "pointwise_measurement_v1",
            "artifact_sha256": digest_of(FIXTURES / "producer_computed.json"),
            "result_id": source["result_id"],
            "method_id": source["provenance"]["method_id"],
            "method_version": source["provenance"]["method_version"],
            "pipeline_run_id": source["provenance"]["pipeline_run_id"],
            "execution_id": source["provenance"]["execution_id"]})
        self.assertEqual(data["configuration"]["profile_id"], "syn-profile")
        self.assertEqual(data["configuration"]["profile_version"], "1")
        self.assertEqual(data["configuration"]["configuration_hash"],
                         vft.hash_config(source["parameters"]))

    def test_the_envelope_carries_the_verified_measurement_reference(self):
        data = transfer().envelope.to_dict()
        source = document("f01_distance.json")
        self.assertEqual(data["measurement_references"], [{
            "reference_id": "ref-f01", "kind": "f01_coordinate_distance_v1",
            "result_id": source["result_id"],
            "artifact_sha256": digest_of(FIXTURES / "f01_distance.json"),
            "quantity_definition_id": "distance_nm", "unit": "nm",
            "value": source["output_metric"]["value"]}])
        self.assertEqual(source["output_metric"]["value"],
                         document("producer_computed.json")["inputs"]["distance_nm"]["value"])

    def test_the_receipt_carries_the_producer_envelope_consumer_export_chain(self):
        outcome = transfer()
        receipt = outcome.receipt.to_dict()
        self.assertEqual(receipt["chain"], {
            "producer_result_id": document("producer_computed.json")["result_id"],
            "envelope_id": outcome.envelope.envelope_id,
            "consumer_id": "syn-consumer", "export_id": "syn-export-1"})
        self.assertEqual(receipt["selected_producer_path"], str(FIXTURES / "producer_computed.json"))
        self.assertEqual(receipt["selected_reference_paths"],
                         [{"reference_id": "ref-f01", "path": str(FIXTURES / "f01_distance.json")}])
        self.assertEqual([c["result"] for c in receipt["checks"]], ["PASSED"] * len(vft.STAGES))

    def test_a_transfer_without_a_measurement_reference_is_accepted(self):
        outcome = transfer(measurement_references=[])
        self.assertEqual(outcome.receipt.outcome, "ACCEPTED")
        self.assertEqual(outcome.envelope.to_dict()["measurement_references"], [])

    def test_the_envelope_carries_no_filesystem_path(self):
        data = transfer().envelope.to_dict()
        found = []

        def walk(node, where):
            if isinstance(node, dict):
                for key, item in node.items():
                    walk(item, f"{where}.{key}")
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    walk(item, f"{where}[{index}]")
            elif isinstance(node, str) and node.startswith("/"):
                found.append(f"{where}={node}")

        walk(data, "$")
        self.assertEqual(found, [])
        self.assertNotIn(str(FIXTURES), json.dumps(data))

    def test_this_layer_adds_no_arithmetic(self):
        """Every carried number is present verbatim in the producer or reference document."""
        data = transfer().envelope.to_dict()
        producer_doc = document("producer_computed.json")
        reference_doc = document("f01_distance.json")
        carried = {data["values"]["ceff_m"]["value"], data["values"]["arm_reach_nm"]["value"],
                   data["measurement_references"][0]["value"]}
        available = {producer_doc["outputs"]["ceff_m"]["value"],
                     producer_doc["outputs"]["arm_reach_nm"]["value"],
                     reference_doc["output_metric"]["value"]}
        self.assertEqual(carried, available)


class Unavailable(Contract):
    def test_an_unavailable_producer_pair_stays_unavailable(self):
        outcome = transfer(producer=producer("producer_unavailable.json"),
                           expected=expected("producer_unavailable.json"),
                           measurement_references=[])
        self.assertEqual(outcome.receipt.outcome, "UNAVAILABLE")
        self.assertIsNotNone(outcome.envelope)
        self.assertEqual(outcome.envelope.status, "UNAVAILABLE")
        self.assertEqual(outcome.envelope.to_dict()["reason"], "PRODUCER_VALUE_UNAVAILABLE")
        self.assertEqual(outcome.envelope.to_dict()["values"], {})
        self.assertIsNone(outcome.envelope.value("ceff_m"))
        self.assertIsNone(outcome.envelope.value("arm_reach_nm"))
        receipt = outcome.receipt.to_dict()
        self.assertEqual(receipt["reason"], "PRODUCER_VALUE_UNAVAILABLE")
        self.assertIn("INPUT_UNAVAILABLE", receipt["detail"])
        self.assertEqual(receipt["chain"]["envelope_id"], outcome.envelope.envelope_id)

    def test_unavailable_is_distinct_from_rejected_and_accepted(self):
        outcomes = {
            "ACCEPTED": transfer().receipt.outcome,
            "UNAVAILABLE": transfer(producer=producer("producer_unavailable.json"),
                                    expected=expected("producer_unavailable.json"),
                                    measurement_references=[]).receipt.outcome,
            "REJECTED": transfer(producer=producer("producer_rejected.json"),
                                 expected=expected("producer_rejected.json"),
                                 measurement_references=[]).receipt.outcome}
        self.assertEqual(outcomes, {"ACCEPTED": "ACCEPTED", "UNAVAILABLE": "UNAVAILABLE",
                                    "REJECTED": "REJECTED"})
        self.assertEqual(set(vft.OUTCOMES), {"ACCEPTED", "UNAVAILABLE", "REJECTED"})


class InvalidValue(Contract):
    def test_a_producer_that_rejected_its_own_pair_is_rejected_here(self):
        outcome = self.rejected("PRODUCER_VALUE_REJECTED", stage="VALUE_ADMISSION",
                                producer=producer("producer_rejected.json"),
                                expected=expected("producer_rejected.json"),
                                measurement_references=[])
        self.assertIn("INPUT_DOMAIN_VIOLATION", outcome.receipt.to_dict()["detail"])

    def test_a_null_or_non_binary64_value_is_never_carried(self):
        """The producer contract already guarantees finite values; the guard is kept explicit."""
        source = document("producer_computed.json")
        for name, mutation, reason in (("ceff_m", None, "VALUE_MISSING"),
                                       ("arm_reach_nm", None, "VALUE_MISSING"),
                                       ("ceff_m", "6", "VALUE_NOT_FINITE"),
                                       ("arm_reach_nm", 6, "VALUE_NOT_FINITE")):
            with self.subTest(name=name, value=repr(mutation)):
                doctored = deepcopy(source)
                doctored["outputs"][name]["value"] = mutation
                with self.assertRaises(Exception) as caught:
                    vft._stage_value_admission(doctored, [])
                self.assertEqual(caught.exception.reason, reason)


class IdentityMismatch(Contract):
    def test_producer_result_identity_mismatch(self):
        self.rejected("PRODUCER_RESULT_ID_MISMATCH", stage="PRODUCER_IDENTITY",
                      expected=expected(result_id="0" * 64))

    def test_a_different_producer_result_is_rejected_against_the_declared_identity(self):
        self.rejected("PRODUCER_RESULT_ID_MISMATCH", stage="PRODUCER_IDENTITY",
                      producer=producer("producer_other_distance.json"))

    def test_configuration_identity_mismatch(self):
        for field, value in (("profile_id", "syn-profile-alt"), ("profile_version", "2")):
            with self.subTest(field=field):
                self.rejected("CONFIGURATION_IDENTITY_MISMATCH", stage="CONFIGURATION_IDENTITY",
                              expected=expected(**{field: value}))

    def test_a_producer_built_under_another_configuration_is_rejected(self):
        name = "producer_other_profile.json"
        self.rejected("CONFIGURATION_IDENTITY_MISMATCH", stage="CONFIGURATION_IDENTITY",
                      producer=producer(name), expected=expected(name))

    def test_quantity_identity_mismatch(self):
        for name, field, value in (("ceff_m", "unit", "nm"),
                                   ("arm_reach_nm", "quantity_definition_id", "distance_nm"),
                                   ("ceff_m", "context", "monomer"),
                                   ("arm_reach_nm", "scale", "0-1")):
            with self.subTest(name=name, field=field):
                identities = quantities()
                identities[name][field] = value
                self.rejected("QUANTITY_IDENTITY_MISMATCH", stage="QUANTITY_IDENTITY",
                              expected=expected(identities=identities))

    def test_measurement_reference_identity_mismatch(self):
        self.rejected("MEASUREMENT_REFERENCE_ID_MISMATCH", stage="MEASUREMENT_REFERENCES",
                      measurement_references=[reference(result_id="0" * 64)])

    def test_a_contradictory_measurement_reference_value_is_rejected(self):
        name = "producer_other_distance.json"
        outcome = self.rejected("MEASUREMENT_REFERENCE_VALUE_MISMATCH",
                                stage="MEASUREMENT_REFERENCES",
                                producer=producer(name), expected=expected(name))
        detail = outcome.receipt.to_dict()["detail"]
        self.assertIn("7.0", detail)
        self.assertIn("5.0", detail)

    def test_a_reference_quantity_the_producer_did_not_consume_is_missing(self):
        self.rejected("MEASUREMENT_REFERENCE_VALUE_MISSING", stage="MEASUREMENT_REFERENCES",
                      measurement_references=[reference(definition="reach_rms_nm")])

    def test_observed_identities_are_recorded_beside_the_expected_ones(self):
        receipt = transfer(expected=expected(result_id="0" * 64)).receipt.to_dict()
        self.assertEqual(receipt["expected"]["producer_result_id"], "0" * 64)
        self.assertEqual(receipt["observed"]["result_id"],
                         document("producer_computed.json")["result_id"])
        self.assertEqual(receipt["observed"]["status"], "COMPUTED")


class Selection(Contract):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def test_producer_bytes_mismatch(self):
        self.rejected("PRODUCER_BYTES_MISMATCH", stage="PRODUCER_BYTES",
                      producer=producer(sha256="0" * 64))

    def test_reference_bytes_mismatch(self):
        self.rejected("MEASUREMENT_REFERENCE_BYTES_MISMATCH", stage="MEASUREMENT_REFERENCES",
                      measurement_references=[reference(sha256="0" * 64)])

    def test_producer_path_must_be_absolute_canonical_and_a_regular_file(self):
        alias = self.root / "alias.json"
        alias.symlink_to(FIXTURES / "producer_computed.json")
        for path in ("producer_computed.json", str(alias), str(self.root),
                     str(self.root / "missing.json")):
            with self.subTest(path=path):
                self.rejected("PRODUCER_PATH_INVALID", stage="PRODUCER_PATH",
                              producer={**producer(), "path": path})

    def test_a_document_of_another_contract_is_refused(self):
        self.rejected("PRODUCER_LAYOUT_MISMATCH", stage="PRODUCER_DOCUMENT",
                      producer=producer("f01_distance.json"),
                      expected=expected(result_id="0" * 64))

    def test_a_malformed_or_tampered_producer_document_is_refused(self):
        source = document("producer_computed.json")
        tampered = deepcopy(source)
        tampered["outputs"]["ceff_m"]["value"] = 9.0
        for name, raw in (("broken.json", b"{"),
                          ("dup.json", b'{"a": 1, "a": 2}'),
                          ("tampered.json", json.dumps(tampered).encode())):
            with self.subTest(name=name):
                path = self.root / name
                path.write_bytes(raw)
                self.rejected("PRODUCER_DOCUMENT_INVALID", stage="PRODUCER_DOCUMENT",
                              producer=producer(name, root=self.root),
                              expected=expected(result_id="0" * 64))

    def test_artifact_changed_before_return(self):
        for name in ("producer_computed.json", "f01_distance.json"):
            shutil.copy(FIXTURES / name, self.root / name)
        chosen, ref = producer(root=self.root), reference(root=self.root)
        real = vft.hash_file
        with patch.object(vft, "hash_file", lambda p: "0" * 64):
            self.rejected("ARTIFACT_CHANGED", stage="PRODUCER_BYTES",
                          producer=chosen, expected=expected(root=self.root),
                          measurement_references=[ref])
        self.assertIs(vft.hash_file, real)


class Envelope(Contract):
    def test_the_envelope_is_immutable_after_construction(self):
        outcome = transfer()
        envelope = outcome.envelope
        with self.assertRaises(dataclasses.FrozenInstanceError):
            envelope.data = {}
        with self.assertRaises(dataclasses.FrozenInstanceError):
            del envelope.data
        first = envelope.to_dict()
        first["values"]["ceff_m"]["value"] = 99.0
        first["producer"]["result_id"] = "0" * 64
        first["measurement_references"].clear()
        self.assertEqual(envelope.to_dict()["values"]["ceff_m"]["value"],
                         document("producer_computed.json")["outputs"]["ceff_m"]["value"])
        self.assertNotEqual(envelope.to_dict()["producer"]["result_id"], "0" * 64)
        self.assertEqual(len(envelope.to_dict()["measurement_references"]), 1)
        self.assertIsNot(envelope.to_dict(), envelope.to_dict())  # every read is a fresh copy

    def test_the_receipt_is_immutable_after_construction(self):
        receipt = transfer().receipt
        with self.assertRaises(dataclasses.FrozenInstanceError):
            receipt.data = {}
        snapshot = receipt.to_json_bytes()
        receipt.to_dict()["chain"]["envelope_id"] = "0" * 64
        self.assertEqual(receipt.to_json_bytes(), snapshot)

    def test_mutating_the_source_request_cannot_reach_a_built_envelope(self):
        chosen, declared, references = producer(), expected(), [reference()]
        outcome = transfer_value_flow(producer=chosen, expected=declared,
                                      measurement_references=references,
                                      consumer=deepcopy(CONSUMER))
        snapshot = outcome.envelope.to_json_bytes()
        chosen["producer_id"] = "mutated"
        declared["configuration"]["profile_id"] = "mutated"
        references[0]["reference_id"] = "mutated"
        self.assertEqual(outcome.envelope.to_json_bytes(), snapshot)

    def test_an_outcome_pairs_exactly_one_receipt_with_at_most_one_envelope(self):
        accepted = transfer()
        rejected = transfer(expected=expected(result_id="0" * 64))
        self.assertIsNotNone(accepted.envelope)
        self.assertIsNone(rejected.envelope)
        with self.assertRaises(ValueFlowTransferError):
            ValueFlowOutcome(None, accepted.receipt)
        with self.assertRaises(ValueFlowTransferError):
            ValueFlowOutcome(accepted.envelope, rejected.receipt)

    def test_value_lookup_refuses_an_unknown_name(self):
        with self.assertRaises(ValueFlowTransferError):
            transfer().envelope.value("spatial_density")


class OuterContract(Contract):
    def test_every_request_field_is_required(self):
        for block, template in (("producer", producer()), ("consumer", CONSUMER)):
            for field in template:
                with self.subTest(block=block, field=field):
                    self.error("CONTRACT_INVALID",
                               **{block: {k: v for k, v in template.items() if k != field}})
        for field in ("producer_result_id", "configuration", "quantities"):
            with self.subTest(block="expected", field=field):
                self.error("CONTRACT_INVALID",
                           expected={k: v for k, v in expected().items() if k != field})
        for field in ("reference_id", "kind", "path", "sha256", "result_id",
                      "quantity_definition_id"):
            with self.subTest(block="reference", field=field):
                self.error("CONTRACT_INVALID", measurement_references=[
                    {k: v for k, v in reference().items() if k != field}])

    def test_unexpected_field_is_refused(self):
        self.error("CONTRACT_INVALID", consumer={**CONSUMER, "timestamp": "now"})
        self.error("CONTRACT_INVALID", expected={**expected(), "threshold": 1})

    def test_layout_and_reference_kind_are_pinned(self):
        self.error("CONTRACT_INVALID", producer=producer(layout="candidate_evidence_v1"))
        self.error("CONTRACT_INVALID",
                   measurement_references=[{**reference(), "kind": "structure_v1"}])

    def test_both_quantities_must_be_declared(self):
        self.error("CONTRACT_INVALID",
                   expected=expected(identities={"ceff_m": quantities()["ceff_m"]}))
        self.error("CONTRACT_INVALID", expected=expected(
            identities={**quantities(), "spatial_density": quantities()["ceff_m"]}))

    def test_malformed_identifiers_are_refused(self):
        self.error("CONTRACT_INVALID", expected=expected(result_id="not-a-digest"))
        self.error("CONTRACT_INVALID", producer=producer(sha256="0" * 63))
        self.error("CONTRACT_INVALID", consumer={**CONSUMER, "consumer_id": ""})
        self.error("CONTRACT_INVALID", measurement_references=[reference(), reference()])


class Serialization(Contract):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def test_identical_requests_are_byte_identical(self):
        self.assertEqual(transfer().envelope.to_json_bytes(), transfer().envelope.to_json_bytes())
        self.assertEqual(transfer().receipt.to_json_bytes(), transfer().receipt.to_json_bytes())

    def test_export_reload_reserialize_is_stable(self):
        outcome = transfer()
        for label, obj, loader in (("envelope", outcome.envelope, load_value_flow_envelope),
                                   ("receipt", outcome.receipt, load_value_flow_receipt)):
            with self.subTest(label=label):
                path = self.root / f"{label}.json"
                path.write_bytes(obj.to_json_bytes())
                back = loader(path)
                self.assertEqual(back.to_json_bytes(), obj.to_json_bytes())
                again = self.root / f"{label}_again.json"
                again.write_bytes(back.to_json_bytes())
                self.assertEqual(again.read_bytes(), path.read_bytes())

    def test_tampering_is_rejected(self):
        outcome = transfer()
        for label, cls, mutate in (
                ("envelope", ValueFlowEnvelope, lambda d: d.update(envelope_id="0" * 64)),
                ("envelope", ValueFlowEnvelope,
                 lambda d: d["values"]["ceff_m"].update(value=99.0)),
                ("envelope", ValueFlowEnvelope, lambda d: d.update(status="UNAVAILABLE")),
                ("envelope", ValueFlowEnvelope,
                 lambda d: d["configuration"].update(configuration_hash="0" * 64)),
                ("envelope", ValueFlowEnvelope,
                 lambda d: d["measurement_references"][0].update(value=9.0)),
                ("envelope", ValueFlowEnvelope, lambda d: d["rules"].update(arithmetic="derived")),
                ("receipt", ValueFlowReceipt, lambda d: d.update(receipt_id="0" * 64)),
                ("receipt", ValueFlowReceipt, lambda d: d.update(outcome="REJECTED")),
                ("receipt", ValueFlowReceipt, lambda d: d["chain"].update(envelope_id="0" * 64))):
            with self.subTest(label=label):
                data = (outcome.envelope if label == "envelope" else outcome.receipt).to_dict()
                mutate(data)
                with self.assertRaises(ValueFlowTransferError) as caught:
                    cls.from_dict(data)
                self.assertIn(caught.exception.code, ("ENVELOPE_INVALID", "RECEIPT_INVALID"))

    def test_loaders_refuse_a_document_of_another_contract(self):
        path = self.root / "other.json"
        path.write_bytes(b'{"schema_version": "linked_transfer/1"}')
        for loader in (load_value_flow_envelope, load_value_flow_receipt):
            with self.subTest(loader=loader.__name__):
                with self.assertRaises(ValueFlowTransferError):
                    loader(path)


if __name__ == "__main__":
    unittest.main()
