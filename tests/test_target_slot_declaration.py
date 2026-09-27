"""Synthetic contract tests for target_slot_declaration; the layer itself writes nothing.

The declaration carries no path and no environment value, so its canonical bytes are
pinned by a committed golden. The three conformance probes at the end assert that the
current single-target paths still behave as the readiness audit recorded them; they read
committed fixtures only and pin nothing about how those modules are implemented.
"""
import builtins
from contextlib import ExitStack
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from structure_audit import target_slot_declaration as tsd
from structure_audit.f01_coordinate_admission import ENDPOINTS, load_f01_coordinate_distance
from structure_audit.linked_transfer import link_transfer
from structure_audit.provenance import hash_file
from structure_audit.quantity_summary import QuantitySummaryError, summarize_quantity
from structure_audit.target_slot_declaration import (
    ABSENCE_REASONS, DOCUMENT_TYPE, EXECUTION_STATUS, TARGET_SLOTS, TargetSlotDeclaration,
    TargetSlotDeclarationError, declare_target_slots,
)

FIXTURES = (Path(__file__).parent / "fixtures" / "target_slot_declaration").resolve()
QS = (Path(__file__).parent / "fixtures" / "quantity_summary").resolve()
VF = (Path(__file__).parent / "fixtures" / "value_flow_transfer").resolve()
GOLDEN = FIXTURES / "declaration_complete.golden.json"

COMPLETE = {"slot_1": {"reference_id": "ref-alpha"},
            "slot_2": {"absence_reason": "NO_REFERENCE_SUPPLIED"},
            "slot_3": {"reference_id": "ref-gamma"}}


def declare(**changes):
    return declare_target_slots({**deepcopy(COMPLETE), **changes})


def document(**changes):
    return {**declare().to_dict(), **changes}


class Declaration(unittest.TestCase):
    def test_complete_declaration_has_the_fixed_named_slot_shape(self):
        data = declare().to_dict()
        self.assertEqual(sorted(data), sorted(tsd.DOCUMENT_FIELDS))
        self.assertEqual((data["document_type"], data["order"], data["execution_status"]),
                         (DOCUMENT_TYPE, ["slot_1", "slot_2", "slot_3"], EXECUTION_STATUS))
        self.assertEqual(data["slot_1"], {"slot": "slot_1", "presence": "REFERENCED",
                                          "reference_id": "ref-alpha", "absence_reason": None})
        for name in TARGET_SLOTS:
            with self.subTest(slot=name):
                self.assertEqual(sorted(data[name]), sorted(tsd.SLOT_FIELDS))
                self.assertEqual(data[name]["slot"], name, "a slot must name its own key")

    def test_order_is_the_constant_and_the_request_order_is_never_read(self):
        reversed_request = {name: COMPLETE[name] for name in reversed(TARGET_SLOTS)}
        self.assertEqual(list(reversed_request), list(reversed(TARGET_SLOTS)))
        self.assertEqual(declare_target_slots(reversed_request).to_json_bytes(),
                         declare().to_json_bytes())
        self.assertEqual(declare().order, list(TARGET_SLOTS))

    def test_explicit_absence_stays_in_place_with_its_reason(self):
        for reason in ABSENCE_REASONS:
            with self.subTest(reason=reason):
                data = declare(slot_2={"absence_reason": reason}).to_dict()
                self.assertIn("slot_2", data, "an absent slot never loses its key")
                self.assertEqual(data["slot_2"], {"slot": "slot_2", "presence": "ABSENT",
                                                  "reference_id": None, "absence_reason": reason})
                self.assertEqual(data["order"], list(TARGET_SLOTS), "absence never shortens order")

    def test_every_slot_may_be_absent_and_none_is_selected(self):
        absent = {name: {"absence_reason": "NO_REFERENCE_SUPPLIED"} for name in TARGET_SLOTS}
        data = declare_target_slots(absent).to_dict()
        self.assertEqual([data[name]["presence"] for name in TARGET_SLOTS], ["ABSENT"] * 3)
        self.assertEqual([data[name]["reference_id"] for name in TARGET_SLOTS], [None] * 3)

    def test_canonical_output_is_deterministic_and_matches_the_golden(self):
        first, second = declare().to_json_bytes(), declare().to_json_bytes()
        self.assertEqual(first, second)
        self.assertEqual(TargetSlotDeclaration.from_dict(declare().to_dict()).to_json_bytes(), first)
        self.assertEqual(TargetSlotDeclaration(first).to_json_bytes(), first)
        self.assertEqual(first + b"\n", GOLDEN.read_bytes())

    def test_slots_are_reachable_only_by_name(self):
        declaration = declare()
        self.assertEqual(declaration.slot("slot_3")["reference_id"], "ref-gamma")
        with self.assertRaises(TargetSlotDeclarationError) as caught:
            declaration.slot(0)
        self.assertEqual(caught.exception.code, "DECLARATION_INVALID")


class RejectedRequests(unittest.TestCase):
    """Builder-side failures; every one is CONTRACT_INVALID and yields no declaration."""

    def contract(self, slots, *, slot=None, field=None):
        with self.assertRaises(TargetSlotDeclarationError) as caught:
            declare_target_slots(slots)
        exc = caught.exception
        self.assertEqual(exc.code, "CONTRACT_INVALID", str(exc))
        self.assertEqual(exc.diagnostics[0]["code"], "CONTRACT_INVALID")
        self.assertEqual((exc.slot, exc.field), (slot, field), str(exc))
        return exc

    def test_missing_shortened_and_unknown_slot_names_are_rejected(self):
        self.contract({name: COMPLETE[name] for name in ("slot_1", "slot_2")})
        self.contract({})
        self.contract({**COMPLETE, "slot_0": {"reference_id": "ref-zero"}})
        self.contract({**COMPLETE, "slot_4": {"reference_id": "ref-four"}})
        self.contract({"slot_1": COMPLETE["slot_1"], "slot_2": COMPLETE["slot_2"],
                       "SLOT_3": COMPLETE["slot_3"]})

    def test_a_collection_is_not_a_slot_mapping(self):
        for slots in ([COMPLETE[name] for name in TARGET_SLOTS], (), "slot_1", None):
            with self.subTest(slots=type(slots).__name__):
                self.contract(slots)

    def test_a_slot_request_declares_exactly_one_field(self):
        self.contract({**COMPLETE, "slot_1": {}}, slot="slot_1")
        self.contract({**COMPLETE, "slot_1": {"reference_id": "ref-alpha",
                                              "absence_reason": "NO_REFERENCE_SUPPLIED"}},
                      slot="slot_1")
        self.contract({**COMPLETE, "slot_1": {"presence": "REFERENCED"}}, slot="slot_1")
        self.contract({**COMPLETE, "slot_1": {"slot": "slot_1"}}, slot="slot_1")
        self.contract({**COMPLETE, "slot_1": "ref-alpha"}, slot="slot_1")

    def test_a_caller_cannot_supply_order_presence_or_execution_status(self):
        # There is no argument for them: every such key is an unknown slot or slot field.
        self.contract({**COMPLETE, "order": ["slot_3", "slot_2", "slot_1"]})
        self.contract({**COMPLETE, "execution_status": "EXECUTABLE"})
        self.contract({**COMPLETE, "slot_2": {"presence": "REFERENCED"}}, slot="slot_2")

    def test_reference_identifiers_must_be_opaque_labels(self):
        for bad in ("", "-leading", "has space", "a/b", "x" * 101, 1, None, True, ["ref"]):
            with self.subTest(reference_id=repr(bad)):
                self.contract({**COMPLETE, "slot_1": {"reference_id": bad}},
                              slot="slot_1", field="reference_id")

    def test_absence_reasons_are_closed(self):
        for bad in ("", "unknown", "no_reference_supplied", None, 0, True):
            with self.subTest(absence_reason=repr(bad)):
                self.contract({**COMPLETE, "slot_2": {"absence_reason": bad}},
                              slot="slot_2", field="absence_reason")


class RejectedDocuments(unittest.TestCase):
    """Document-side failures; every one is DECLARATION_INVALID and re-derives nothing.

    Two gates share the work and the tests follow that split. The closed schema rejects
    the shape and every fixed single-value enum, reporting the offending JSON path. The
    module rejects what the schema subset cannot express -- the derived order and the
    presence/reference/reason agreement -- reporting a slot and field locator.
    """

    def invalid(self, data):
        with self.assertRaises(TargetSlotDeclarationError) as caught:
            TargetSlotDeclaration.from_dict(data)
        exc = caught.exception
        self.assertEqual(exc.code, "DECLARATION_INVALID", str(exc))
        self.assertEqual(exc.diagnostics[0]["code"], "DECLARATION_INVALID")
        return exc

    def schema_rejected(self, data, path):
        exc = self.invalid(data)
        self.assertTrue(str(exc).startswith(f"DECLARATION_INVALID: {path}"), str(exc))
        return exc

    def module_rejected(self, data, *, slot=None, field=None):
        exc = self.invalid(data)
        self.assertEqual((exc.slot, exc.field), (slot, field), str(exc))
        return exc

    def test_a_permuted_shortened_or_padded_order_is_rejected(self):
        for order in (["slot_3", "slot_2", "slot_1"], ["slot_2", "slot_1", "slot_3"],
                      ["slot_1", "slot_2"], [], ["slot_1", "slot_2", "slot_3", "slot_1"],
                      ["slot_1", "slot_1", "slot_1"]):
            with self.subTest(order=order):
                self.module_rejected(document(order=order), field="order")

    def test_execution_status_cannot_be_changed(self):
        for status in ("EXECUTABLE", "DECLARED_EXECUTABLE", "", EXECUTION_STATUS.lower()):
            with self.subTest(execution_status=status):
                self.schema_rejected(document(execution_status=status), "$.execution_status")

    def test_document_type_is_fixed(self):
        self.schema_rejected(document(document_type="target_slot_declaration/2"), "$.document_type")

    def test_missing_and_extra_properties_are_rejected(self):
        for field in tsd.DOCUMENT_FIELDS:
            with self.subTest(missing=field):
                self.schema_rejected({k: v for k, v in declare().to_dict().items() if k != field},
                                     f"$.{field}")
        self.schema_rejected(document(slot_4={"slot": "slot_4", "presence": "ABSENT",
                                             "reference_id": None,
                                             "absence_reason": "NO_REFERENCE_SUPPLIED"}),
                             "$.slot_4")
        self.schema_rejected(document(note="extra"), "$.note")
        self.schema_rejected(document(slot_1={**declare().to_dict()["slot_1"], "rank": 1}),
                             "$.slot_1.rank")

    def test_a_slot_record_must_name_its_own_key(self):
        swapped = declare().to_dict()
        swapped["slot_1"] = {**swapped["slot_1"], "slot": "slot_2"}
        self.schema_rejected(swapped, "$.slot_1.slot")

    def test_presence_reference_and_reason_must_agree(self):
        base = declare().to_dict()
        self.module_rejected(document(slot_1={**base["slot_1"], "reference_id": None}),
                             slot="slot_1", field="reference_id")
        self.module_rejected(document(slot_2={**base["slot_2"], "reference_id": "ref-beta"}),
                             slot="slot_2", field="reference_id")
        self.module_rejected(document(slot_1={**base["slot_1"],
                                              "absence_reason": "NO_REFERENCE_SUPPLIED"}),
                             slot="slot_1", field="absence_reason")
        self.module_rejected(document(slot_2={**base["slot_2"], "absence_reason": None}),
                             slot="slot_2", field="absence_reason")

    def test_a_slot_is_never_a_list_or_a_bare_identifier(self):
        for value in (["ref-alpha"], "ref-alpha", None):
            with self.subTest(slot_1=value):
                self.schema_rejected(document(slot_1=value), "$.slot_1")

    def test_non_canonical_bytes_and_non_json_input_are_rejected(self):
        canonical = declare().to_json_bytes()
        for raw in (b" " + canonical, canonical + b"\n", b"{}", b"not json", b"\xff\xfe",
                    canonical.replace(b'"order"', b'"Order"')):
            with self.subTest(raw=raw[:24]):
                with self.assertRaises(TargetSlotDeclarationError) as caught:
                    TargetSlotDeclaration(raw)
                self.assertEqual(caught.exception.code, "DECLARATION_INVALID")
        with self.assertRaises(TargetSlotDeclarationError):
            TargetSlotDeclaration(canonical.decode())


class Isolation(unittest.TestCase):
    def test_declaring_opens_no_file_outside_the_contract_schema(self):
        opened, real = [], builtins.open

        def record(target, *args, **kwargs):
            if not isinstance(target, int):
                opened.append(os.fspath(target))
            return real(target, *args, **kwargs)

        with patch.object(builtins, "open", record), patch.object(io, "open", record):
            declare()
        schemas = Path(tsd.__file__).resolve().parent / "schemas"
        self.assertEqual({Path(p).resolve() for p in opened
                          if Path(p).resolve().parent != schemas}, set())

    def test_declaring_performs_no_write_subprocess_or_directory_scan(self):
        with ExitStack() as stack:
            for owner, names in ((subprocess, ("Popen", "run")),
                                 (os, ("listdir", "scandir", "walk", "remove")),
                                 (Path, ("write_bytes", "write_text", "mkdir", "unlink",
                                         "glob", "rglob"))):
                for name in names:
                    stack.enter_context(patch.object(owner, name,
                                                     side_effect=AssertionError("forbidden IO: " + name)))
            declaration = declare()
        self.assertEqual(declaration.execution_status, EXECUTION_STATUS)


class ConformanceProbes(unittest.TestCase):
    """The three current-behaviour facts a later ordered-slot phase must not silently break."""

    QUANTITY = {"quantity_id": "syn-iptm", "context": "complex", "category": "model_confidence",
                "unit": None, "scale": "0-1"}

    def test_quantity_summary_duplicate_identity_stays_hashable_for_scalar_target_id(self):
        # The duplicate check builds a set of (candidate_id, target_id, conformer_id) tuples, so
        # the current scalar target_id must stay hashable for DUPLICATE_OBSERVATION to exist. The
        # second artifact carries the same record in the list layout: different bytes, same triple.
        record = json.loads((QS / "producer_b.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            again = Path(tmp).resolve() / "producer_b_again.json"
            again.write_text(json.dumps([record]))
            artifacts = [
                {"artifact_id": "producer-b", "path": str(QS / "producer_b.json"),
                 "sha256": hash_file(QS / "producer_b.json"),
                 "layout": "candidate_evidence_v1", "metric_name": "syn-b:/iptm"},
                {"artifact_id": "producer-b-again", "path": str(again), "sha256": hash_file(again),
                 "layout": "candidate_evidence_list_v1", "metric_name": "syn-b:/iptm"},
            ]
            with self.assertRaises(QuantitySummaryError) as caught:
                summarize_quantity(quantity=deepcopy(self.QUANTITY), artifacts=artifacts)
        self.assertEqual(caught.exception.code, "DUPLICATE_OBSERVATION")

    def test_null_target_id_is_an_exact_selector_value_not_a_wildcard(self):
        path = QS / "producer_a.json"
        selection = {"artifact_id": "producer-a", "path": str(path), "sha256": hash_file(path),
                     "layout": "candidate_evidence_list_v1"}

        def transfer(target_id):
            request = {"consumer_id": "consumer-1", "quantity": deepcopy(self.QUANTITY),
                       "item": {"metric_name": "syn-a:/iptm", "candidate_id": "syn-a2",
                                "target_id": target_id, "conformer_id": None}}
            return link_transfer(selection=dict(selection), request=request).receipt.data

        self.assertEqual(transfer("syn-target")["outcome"], "ADMITTED")
        rejected = transfer(None)
        self.assertEqual((rejected["outcome"], rejected["failure"]["class"]),
                         ("REJECTED", "SELECTOR_NOT_FOUND"))

    def test_endpoint_mapping_order_is_still_the_endpoint_constant(self):
        reference = load_f01_coordinate_distance(VF / "f01_distance.json")
        self.assertEqual(reference.status, "COMPUTED")
        mapping = reference.to_dict()["payload"]["endpoint_mapping"]
        self.assertEqual(mapping["order"], list(ENDPOINTS))
        self.assertEqual(sorted(mapping), sorted(["order", *ENDPOINTS]))


if __name__ == "__main__":
    unittest.main()
