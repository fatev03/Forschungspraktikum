"""Synthetic contract tests for value_flow_demo_export; only export tests write temporary files.

Every transfer here is built from the existing closed-producer fixtures under
tests/fixtures/value_flow_transfer. No expected number is written by hand: each is read back
from the envelope or the receipt, which are the only sources the summary may copy from.
"""
from copy import deepcopy
import dataclasses
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from structure_audit import value_flow_demo_export as demo
from structure_audit.provenance import hash_config
from structure_audit.validation import validate_named
from structure_audit.value_flow_demo_export import (
    ValueFlowDemoSummary, ValueFlowDemoSummaryError, build_demo_summary,
    load_value_flow_demo_summary, summarize_outcome,
)
from structure_audit.value_flow_transfer import ValueFlowTransferError, transfer_value_flow

FIXTURES = (Path(__file__).parent / "fixtures" / "value_flow_transfer").resolve()
IDENTITY_FIELDS = ("quantity_id", "quantity_definition_id", "context", "category", "unit", "scale")
CONSUMER = {"consumer_id": "syn-consumer", "export_id": "syn-export-1"}


def digest_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def document(name):
    return json.loads((FIXTURES / name).read_bytes())


def outcome_for(name="producer_computed.json", *, references=True, result_id=None):
    source, path = document(name), FIXTURES / name
    reference = FIXTURES / "f01_distance.json"
    return transfer_value_flow(
        producer={"producer_id": "syn-producer", "path": str(path),
                  "sha256": digest_of(path), "layout": "pointwise_measurement_v1"},
        expected={"producer_result_id": result_id or source["result_id"],
                  "configuration": {"profile_id": "syn-profile", "profile_version": "1"},
                  "quantities": {n: {k: source["outputs"][n][k] for k in IDENTITY_FIELDS}
                                 for n in ("ceff_m", "arm_reach_nm")}},
        measurement_references=[{
            "reference_id": "ref-f01", "kind": "f01_coordinate_distance_v1",
            "path": str(reference), "sha256": digest_of(reference),
            "result_id": document("f01_distance.json")["result_id"],
            "quantity_definition_id": "distance_nm"}] if references else [],
        consumer=deepcopy(CONSUMER))


ACCEPTED_OUTCOME = None
UNAVAILABLE_OUTCOME = None
REJECTED_OUTCOME = None


def setUpModule():
    global ACCEPTED_OUTCOME, UNAVAILABLE_OUTCOME, REJECTED_OUTCOME
    ACCEPTED_OUTCOME = outcome_for()
    UNAVAILABLE_OUTCOME = outcome_for("producer_unavailable.json", references=False)
    REJECTED_OUTCOME = outcome_for("producer_rejected.json", references=False)


def numbers_in(node, found=None):
    """Every numeric leaf of a JSON value, as a multiset-free set of exact values."""
    found = set() if found is None else found
    if isinstance(node, dict):
        for item in node.values():
            numbers_in(item, found)
    elif isinstance(node, list):
        for item in node:
            numbers_in(item, found)
    elif type(node) in (int, float) and type(node) is not bool:
        found.add(node)
    return found


def strings_in(node, found=None):
    found = [] if found is None else found
    if isinstance(node, dict):
        for item in node.values():
            strings_in(item, found)
    elif isinstance(node, list):
        for item in node:
            strings_in(item, found)
    elif isinstance(node, str):
        found.append(node)
    return found


class Accepted(unittest.TestCase):
    def setUp(self):
        self.outcome = ACCEPTED_OUTCOME
        self.summary = summarize_outcome(self.outcome)
        self.data = self.summary.to_dict()

    def test_accepted_transfer_summary(self):
        self.assertEqual(self.data["schema_version"], "value_flow_demo_summary/1")
        self.assertEqual(self.summary.outcome, "ACCEPTED")
        self.assertEqual(self.data["status"], {"outcome": "ACCEPTED", "reason": None, "detail": None})
        self.assertEqual(self.data["sources"], {
            "envelope_contract": "value_flow_envelope/1",
            "receipt_contract": "value_flow_receipt/1",
            "receipt_id": self.outcome.receipt.receipt_id})
        validate_named(self.data, "value_flow_demo_summary")

    def test_accepted_summary_carries_the_full_identity_chain(self):
        envelope, receipt = self.outcome.envelope.to_dict(), self.outcome.receipt.to_dict()
        self.assertEqual(self.data["identity_chain"], {
            "producer_result_id": receipt["chain"]["producer_result_id"],
            "envelope_id": envelope["envelope_id"],
            "consumer_id": "syn-consumer", "export_id": "syn-export-1",
            "f01_reference_result_ids": [envelope["measurement_references"][0]["result_id"]],
            "profile_id": envelope["configuration"]["profile_id"],
            "profile_version": envelope["configuration"]["profile_version"],
            "configuration_hash": envelope["configuration"]["configuration_hash"]})
        self.assertEqual(self.data["identity_chain"]["f01_reference_result_ids"],
                         [document("f01_distance.json")["result_id"]])

    def test_accepted_summary_carries_both_quantities_and_the_reference(self):
        envelope = self.outcome.envelope.to_dict()
        for name in ("ceff_m", "arm_reach_nm"):
            with self.subTest(name=name):
                self.assertEqual(self.data["quantities"][name],
                                 {**{k: envelope["values"][name][k] for k in IDENTITY_FIELDS},
                                  "value": envelope["values"][name]["value"]})
        self.assertEqual(self.data["quantities"]["referenced_distance_nm"], [
            {k: envelope["measurement_references"][0][k] for k in
             ("reference_id", "kind", "result_id", "quantity_definition_id", "unit", "value")}])

    def test_accepted_summary_carries_the_ordered_integrity_view(self):
        envelope, receipt = self.outcome.envelope.to_dict(), self.outcome.receipt.to_dict()
        self.assertEqual(self.data["integrity"]["stage_checks"], receipt["checks"])
        self.assertEqual(self.data["integrity"]["identity_checks"], envelope["identity_checks"])
        self.assertEqual(self.data["integrity"]["expected"], receipt["expected"])
        self.assertEqual(self.data["integrity"]["observed"], receipt["observed"])
        self.assertEqual([c["result"] for c in self.data["integrity"]["stage_checks"]],
                         ["PASSED"] * len(receipt["checks"]))

    def test_render_lines_is_derived_and_never_part_of_the_document(self):
        lines = self.summary.render_lines()
        self.assertIsInstance(lines, list)
        self.assertTrue(all(isinstance(line, str) for line in lines))
        self.assertIn(f"outcome         ACCEPTED", "\n".join(lines))
        self.assertNotIn("render", json.dumps(self.data["quantities"]))
        before = self.summary.to_json_bytes()
        self.summary.render_lines()
        self.assertEqual(self.summary.to_json_bytes(), before)


class Unavailable(unittest.TestCase):
    def setUp(self):
        self.outcome = UNAVAILABLE_OUTCOME
        self.summary = summarize_outcome(self.outcome)
        self.data = self.summary.to_dict()

    def test_unavailable_transfer_summary(self):
        self.assertEqual(self.summary.outcome, "UNAVAILABLE")
        self.assertEqual(self.data["status"]["reason"], "PRODUCER_VALUE_UNAVAILABLE")
        self.assertIn("INPUT_UNAVAILABLE", self.data["status"]["detail"])
        self.assertIsNone(self.data["quantities"]["ceff_m"])
        self.assertIsNone(self.data["quantities"]["arm_reach_nm"])
        self.assertEqual(self.data["quantities"]["referenced_distance_nm"], [])
        self.assertIsNotNone(self.data["identity_chain"]["envelope_id"])
        self.assertIsNotNone(self.data["integrity"]["identity_checks"])
        self.assertEqual(self.data["sources"]["envelope_contract"], "value_flow_envelope/1")
        validate_named(self.data, "value_flow_demo_summary")

    def test_unavailable_summary_states_no_value_and_invents_none(self):
        self.assertNotIn(None, [self.data["status"]["reason"]])
        rendered = "\n".join(self.summary.render_lines())
        self.assertIn("ceff_m           not carried", rendered)
        self.assertIn("arm_reach_nm     not carried", rendered)
        self.assertNotIn("0.0", rendered.split("stage checks")[0])


class Rejected(unittest.TestCase):
    def setUp(self):
        self.outcome = REJECTED_OUTCOME
        self.summary = summarize_outcome(self.outcome)
        self.data = self.summary.to_dict()

    def test_rejected_transfer_summary(self):
        self.assertIsNone(self.outcome.envelope)
        self.assertEqual(self.summary.outcome, "REJECTED")
        self.assertEqual(self.data["status"]["reason"], "PRODUCER_VALUE_REJECTED")
        self.assertIn("INPUT_DOMAIN_VIOLATION", self.data["status"]["detail"])
        self.assertIsNone(self.data["identity_chain"]["envelope_id"])
        self.assertIsNone(self.data["identity_chain"]["profile_id"])
        self.assertIsNone(self.data["identity_chain"]["configuration_hash"])
        self.assertIsNone(self.data["integrity"]["identity_checks"])
        self.assertIsNone(self.data["sources"]["envelope_contract"])
        self.assertIsNone(self.data["quantities"]["ceff_m"])
        self.assertIsNone(self.data["quantities"]["arm_reach_nm"])
        self.assertEqual(self.data["quantities"]["referenced_distance_nm"], [])
        validate_named(self.data, "value_flow_demo_summary")

    def test_rejected_summary_still_carries_the_receipt_integrity_view(self):
        receipt = self.outcome.receipt.to_dict()
        self.assertEqual(self.data["integrity"]["stage_checks"], receipt["checks"])
        self.assertEqual([c["result"] for c in self.data["integrity"]["stage_checks"]][-1], "FAILED")
        self.assertEqual(self.data["integrity"]["observed"]["status"], "REJECTED")
        self.assertEqual(self.data["identity_chain"]["producer_result_id"],
                         document("producer_rejected.json")["result_id"])

    def test_the_three_outcomes_stay_distinct(self):
        outcomes = {summarize_outcome(o).outcome for o in
                    (ACCEPTED_OUTCOME, UNAVAILABLE_OUTCOME, REJECTED_OUTCOME)}
        self.assertEqual(outcomes, {"ACCEPTED", "UNAVAILABLE", "REJECTED"})

    def test_a_rejected_identity_mismatch_is_summarized_without_new_claims(self):
        mismatch = outcome_for(result_id="0" * 64)
        data = summarize_outcome(mismatch).to_dict()
        self.assertEqual(data["status"]["reason"], "PRODUCER_RESULT_ID_MISMATCH")
        self.assertEqual(data["integrity"]["expected"]["producer_result_id"], "0" * 64)
        self.assertEqual(data["integrity"]["observed"]["result_id"],
                         document("producer_computed.json")["result_id"])


class NoArithmetic(unittest.TestCase):
    def test_no_arithmetic_every_number_is_verbatim_from_a_source_document(self):
        for label, outcome in (("ACCEPTED", ACCEPTED_OUTCOME), ("UNAVAILABLE", UNAVAILABLE_OUTCOME),
                               ("REJECTED", REJECTED_OUTCOME)):
            with self.subTest(label=label):
                data = summarize_outcome(outcome).to_dict()
                available = numbers_in(outcome.receipt.to_dict())
                if outcome.envelope is not None:
                    available |= numbers_in(outcome.envelope.to_dict())
                self.assertTrue(numbers_in(data) <= available,
                                sorted(numbers_in(data) - available))

    def test_no_arithmetic_every_string_is_verbatim_or_a_declared_constant(self):
        constants = ({"value_flow_demo_summary/1", "value_flow_envelope/1", "value_flow_receipt/1"}
                     | set(demo._RULES.values()))
        for label, outcome in (("ACCEPTED", ACCEPTED_OUTCOME), ("REJECTED", REJECTED_OUTCOME)):
            with self.subTest(label=label):
                summary = summarize_outcome(outcome)
                data = summary.to_dict()
                available = set(strings_in(outcome.receipt.to_dict())) | constants
                if outcome.envelope is not None:
                    available |= set(strings_in(outcome.envelope.to_dict()))
                available.add(data["summary_id"])
                invented = [s for s in strings_in(data) if s not in available]
                self.assertEqual(invented, [], invented)

    def test_the_summary_carries_no_filesystem_path(self):
        for label, outcome in (("ACCEPTED", ACCEPTED_OUTCOME), ("REJECTED", REJECTED_OUTCOME)):
            with self.subTest(label=label):
                data = summarize_outcome(outcome).to_dict()
                receipt = outcome.receipt.to_dict()
                self.assertNotIn("selected_producer_path", json.dumps(data))
                self.assertNotIn("selected_reference_paths", json.dumps(data))
                self.assertNotIn(receipt["selected_producer_path"], json.dumps(data))
                self.assertEqual([s for s in strings_in(data) if s.startswith("/")], [])
                self.assertNotIn(str(FIXTURES), json.dumps(data))


class Serialization(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def test_stable_canonical_serialization(self):
        for label, outcome in (("ACCEPTED", ACCEPTED_OUTCOME), ("UNAVAILABLE", UNAVAILABLE_OUTCOME),
                               ("REJECTED", REJECTED_OUTCOME)):
            with self.subTest(label=label):
                first, second = summarize_outcome(outcome), summarize_outcome(outcome)
                self.assertEqual(first.to_json_bytes(), second.to_json_bytes())
                self.assertEqual(first.summary_id, second.summary_id)
                without = {k: v for k, v in first.to_dict().items() if k != "summary_id"}
                self.assertEqual(first.summary_id, hash_config(without))

    def test_distinct_transfers_have_distinct_summary_ids(self):
        ids = {summarize_outcome(o).summary_id for o in
               (ACCEPTED_OUTCOME, UNAVAILABLE_OUTCOME, REJECTED_OUTCOME)}
        self.assertEqual(len(ids), 3)

    def test_export_reload_reserialize_is_stable(self):
        for label, outcome in (("ACCEPTED", ACCEPTED_OUTCOME), ("UNAVAILABLE", UNAVAILABLE_OUTCOME),
                               ("REJECTED", REJECTED_OUTCOME)):
            with self.subTest(label=label):
                summary = summarize_outcome(outcome)
                path = self.root / f"{label}.json"
                path.write_bytes(summary.to_json_bytes())
                back = load_value_flow_demo_summary(path)
                self.assertEqual(back.to_json_bytes(), summary.to_json_bytes())
                self.assertEqual(back.summary_id, summary.summary_id)
                self.assertEqual(back.outcome, summary.outcome)
                again = self.root / f"{label}_again.json"
                again.write_bytes(back.to_json_bytes())
                self.assertEqual(again.read_bytes(), path.read_bytes())

    def test_loader_refuses_a_document_of_another_contract(self):
        path = self.root / "other.json"
        path.write_bytes(b'{"schema_version": "value_flow_envelope/1"}')
        with self.assertRaises(ValueFlowDemoSummaryError) as caught:
            load_value_flow_demo_summary(path)
        self.assertEqual(caught.exception.code, "SUMMARY_INVALID")

    def test_loader_refuses_duplicate_keys(self):
        path = self.root / "dup.json"
        path.write_bytes(b'{"a": 1, "a": 2}')
        with self.assertRaises(ValueFlowDemoSummaryError):
            load_value_flow_demo_summary(path)


class Tampering(unittest.TestCase):
    def tampered(self, outcome, mutate):
        data = summarize_outcome(outcome).to_dict()
        mutate(data)
        with self.assertRaises(ValueFlowDemoSummaryError) as caught:
            ValueFlowDemoSummary.from_dict(data)
        self.assertEqual(caught.exception.code, "SUMMARY_INVALID", str(caught.exception))
        return caught.exception

    def test_tamper_rejection_for_every_material_field(self):
        cases = (
            ("summary_id", lambda d: d.update(summary_id="0" * 64)),
            ("ceff_m value", lambda d: d["quantities"]["ceff_m"].update(value=99.0)),
            ("arm_reach_nm value", lambda d: d["quantities"]["arm_reach_nm"].update(value=99.0)),
            ("reference value", lambda d: d["quantities"]["referenced_distance_nm"][0].update(value=9.0)),
            ("producer_result_id", lambda d: d["identity_chain"].update(producer_result_id="0" * 64)),
            ("envelope_id", lambda d: d["identity_chain"].update(envelope_id="0" * 64)),
            ("configuration_hash", lambda d: d["identity_chain"].update(configuration_hash="0" * 64)),
            ("receipt_id", lambda d: d["sources"].update(receipt_id="0" * 64)),
            ("stage check", lambda d: d["integrity"]["stage_checks"][0].update(result="FAILED")),
            ("identity check", lambda d: d["integrity"]["identity_checks"][0].update(result="FAILED")),
            ("observed", lambda d: d["integrity"]["observed"].update(status="UNAVAILABLE")),
            ("rules", lambda d: d["rules"].update(arithmetic="derived")),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                self.tampered(ACCEPTED_OUTCOME, mutate)

    def test_a_consistently_rehashed_relabelling_is_still_refused(self):
        """Re-hashing after an edit cannot turn a REJECTED summary into an ACCEPTED one."""
        data = summarize_outcome(REJECTED_OUTCOME).to_dict()
        data["status"] = {"outcome": "ACCEPTED", "reason": None, "detail": None}
        without = {k: v for k, v in data.items() if k != "summary_id"}
        data["summary_id"] = hash_config(without)
        with self.assertRaises(ValueFlowDemoSummaryError) as caught:
            ValueFlowDemoSummary.from_dict(data)
        self.assertEqual(caught.exception.code, "SUMMARY_INVALID")

    def test_a_value_cannot_be_supplied_where_the_source_withheld_one(self):
        data = summarize_outcome(UNAVAILABLE_OUTCOME).to_dict()
        accepted = summarize_outcome(ACCEPTED_OUTCOME).to_dict()
        data["quantities"]["ceff_m"] = deepcopy(accepted["quantities"]["ceff_m"])
        without = {k: v for k, v in data.items() if k != "summary_id"}
        data["summary_id"] = hash_config(without)
        with self.assertRaises(ValueFlowDemoSummaryError) as caught:
            ValueFlowDemoSummary.from_dict(data)
        self.assertEqual(caught.exception.code, "SUMMARY_INVALID")

    def test_reference_identities_must_agree_with_the_identity_chain(self):
        data = summarize_outcome(ACCEPTED_OUTCOME).to_dict()
        data["identity_chain"]["f01_reference_result_ids"] = ["1" * 64]
        without = {k: v for k, v in data.items() if k != "summary_id"}
        data["summary_id"] = hash_config(without)
        with self.assertRaises(ValueFlowDemoSummaryError):
            ValueFlowDemoSummary.from_dict(data)


class Immutability(unittest.TestCase):
    def test_immutable_result_object(self):
        summary = summarize_outcome(ACCEPTED_OUTCOME)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            summary.data = {}
        with self.assertRaises(dataclasses.FrozenInstanceError):
            del summary.data

    def test_defensive_copies_on_every_read(self):
        summary = summarize_outcome(ACCEPTED_OUTCOME)
        snapshot = summary.to_json_bytes()
        first = summary.to_dict()
        first["status"]["outcome"] = "REJECTED"
        first["quantities"]["ceff_m"]["value"] = 99.0
        first["integrity"]["stage_checks"].clear()
        first["identity_chain"]["envelope_id"] = "0" * 64
        self.assertEqual(summary.to_json_bytes(), snapshot)
        self.assertEqual(summary.outcome, "ACCEPTED")
        self.assertIsNot(summary.to_dict(), summary.to_dict())
        self.assertIsNot(summary.to_dict()["quantities"], summary.to_dict()["quantities"])

    def test_mutating_the_source_documents_cannot_reach_a_built_summary(self):
        envelope, receipt = ACCEPTED_OUTCOME.envelope, ACCEPTED_OUTCOME.receipt
        summary = build_demo_summary(envelope=envelope, receipt=receipt)
        snapshot = summary.to_json_bytes()
        envelope.to_dict()["values"]["ceff_m"]["value"] = 99.0
        receipt.to_dict()["outcome"] = "REJECTED"
        self.assertEqual(summary.to_json_bytes(), snapshot)


class OuterContract(unittest.TestCase):
    def test_the_pairing_invariant_is_delegated_not_restated(self):
        """A mispaired envelope and receipt are refused by the transfer contract itself, so the
        transfer contract's own error type surfaces: this module restates no identity rule."""
        for envelope, receipt in ((None, ACCEPTED_OUTCOME.receipt),
                                  (ACCEPTED_OUTCOME.envelope, REJECTED_OUTCOME.receipt),
                                  (ACCEPTED_OUTCOME.envelope, UNAVAILABLE_OUTCOME.receipt)):
            with self.subTest(envelope=envelope is not None):
                with self.assertRaises(ValueFlowTransferError) as caught:
                    build_demo_summary(envelope=envelope, receipt=receipt)
                self.assertEqual(caught.exception.code, "CONTRACT_INVALID")
                self.assertNotIsInstance(caught.exception, ValueFlowDemoSummaryError)

    def test_malformed_arguments_are_refused(self):
        for envelope, receipt in ((ACCEPTED_OUTCOME.envelope, ACCEPTED_OUTCOME.envelope),
                                  (ACCEPTED_OUTCOME.receipt, ACCEPTED_OUTCOME.receipt),
                                  (ACCEPTED_OUTCOME.envelope.to_dict(), ACCEPTED_OUTCOME.receipt),
                                  (None, None)):
            with self.subTest(types=(type(envelope).__name__, type(receipt).__name__)):
                with self.assertRaises(ValueFlowDemoSummaryError) as caught:
                    build_demo_summary(envelope=envelope, receipt=receipt)
                self.assertEqual(caught.exception.code, "CONTRACT_INVALID")

    def test_summarize_outcome_requires_a_value_flow_outcome(self):
        with self.assertRaises(ValueFlowDemoSummaryError) as caught:
            summarize_outcome(ACCEPTED_OUTCOME.receipt)
        self.assertEqual(caught.exception.code, "CONTRACT_INVALID")

    def test_both_entry_points_agree(self):
        self.assertEqual(summarize_outcome(ACCEPTED_OUTCOME).to_json_bytes(),
                         build_demo_summary(envelope=ACCEPTED_OUTCOME.envelope,
                                            receipt=ACCEPTED_OUTCOME.receipt).to_json_bytes())


if __name__ == "__main__":
    unittest.main()
