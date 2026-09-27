"""Synthetic contract tests for linked_transfer; only fixture setup writes temporary files."""
import builtins
from contextlib import ExitStack
from copy import deepcopy
import glob
import io
import json
import math
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from structure_audit import linked_transfer as lt
from structure_audit.linked_transfer import (
    LinkedTransfer, LinkedTransferError, TransferOutcome, TransferReceipt,
    link_transfer, load_linked_transfer, load_transfer_receipt,
)
from structure_audit.provenance import hash_config, hash_file, write_json_new
from structure_audit.quantity_summary import summarize_quantity

QS = (Path(__file__).parent / "fixtures" / "quantity_summary").resolve()
LT = (Path(__file__).parent / "fixtures" / "linked_transfer").resolve()
SCHEMAS = Path(lt.__file__).resolve().parent / "schemas"
LIST, SINGLE, SUMMARY = "candidate_evidence_list_v1", "candidate_evidence_v1", "quantity_summary_v1"
QUANTITY = {"quantity_id": "syn-iptm", "context": "complex", "category": "model_confidence",
            "unit": None, "scale": "0-1"}
PROV = {"model_id": "synthetic-model", "checkpoint_id": None, "seed": 0}


def selection(name, layout, *, root=QS, artifact_id="producer"):
    path = root / name
    return {"artifact_id": artifact_id, "path": str(path), "sha256": hash_file(path), "layout": layout}


def evidence_request(metric, candidate, *, target="syn-target", conformer=None, **quantity):
    return {"consumer_id": "consumer-1", "quantity": dict(QUANTITY, **quantity),
            "item": {"metric_name": metric, "candidate_id": candidate, "target_id": target, "conformer_id": conformer}}


def summary_request(statistic, **quantity):
    return {"consumer_id": "consumer-1", "quantity": dict(QUANTITY, **quantity), "item": {"statistic": statistic}}


def link(sel, req):
    return link_transfer(selection=deepcopy(sel), request=deepcopy(req))


A2 = (lambda: selection("producer_a.json", LIST, artifact_id="producer-a"), evidence_request("syn-a:/iptm", "syn-a2"))
MEDIAN = (lambda: selection("summary_abc.golden.json", SUMMARY, artifact_id="summary-abc"), summary_request("median"))


def record(candidate, value, *, missing=None, name="syn-t:/iptm"):
    metric = {"name": name, "raw_value": value, "value": value, "context": "complex", "category": "model_confidence",
              "unit": None, "scale": "0-1", "source": {"path": "/synthetic/producer-t/values.json",
                                                        "sha256": "1" * 64, "row": None},
              "provenance": dict(PROV), "missing_reason": missing}
    return {"schema_version": "1.0", "candidate_id": candidate, "sequence_hash": None, "target_id": "syn-target",
            "conformer_id": None, "metrics": [metric], "provenance": dict(PROV), "warnings": [],
            "missing_values": {"sequence_hash": "synthetic fixture", "conformer_id": "synthetic fixture"}}


class Temp(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def write(self, name, document=None, *, raw=None, layout=LIST):
        path = self.root / name
        path.write_bytes(raw if raw is not None else json.dumps(document).encode("utf-8"))
        return {"artifact_id": "temp", "path": str(path), "sha256": hash_file(path), "layout": layout}

    def rejected(self, sel, req, failure_class, observed_layout=None):
        outcome = link(sel, req)
        receipt = outcome.receipt.data
        self.assertIsNone(outcome.transfer)
        self.assertEqual((receipt["outcome"], receipt["failure"]["class"], receipt["failure"]["stage"],
                          receipt["transfer_id"], receipt["carried_reason"]),
                         ("REJECTED", failure_class, lt.FAILURE_STAGE[failure_class], None, None), receipt["failure"])
        stage = lt.CHECKS.index(lt.FAILURE_STAGE[failure_class])
        self.assertEqual([c["result"] for c in receipt["checks"]],
                         ["PASSED"] * stage + ["FAILED"] + ["NOT_REACHED"] * (len(lt.CHECKS) - stage - 1))
        if observed_layout is not None:
            self.assertEqual(receipt["observed_producer"]["layout"], observed_layout)
        return receipt

    @staticmethod
    def checks(outcome):
        return [c["result"] for c in outcome.receipt.data["checks"]]


# --------------------------------------------------------------------------
# Valid linked transfers
# --------------------------------------------------------------------------
class ValidTransfers(Temp):
    def test_linked_transfer_from_candidate_evidence(self):
        outcome = link(A2[0](), A2[1])
        transfer, receipt = outcome.transfer.data, outcome.receipt.data
        self.assertEqual(outcome.transfer.to_json_bytes() + b"\n",
                         (LT / "transfer_candidate_evidence.golden.json").read_bytes())
        self.assertEqual(transfer["payload"], {"status": "ADMITTED", "value": 0.71, "reason": None})
        self.assertEqual(transfer["quantity_identity"]["verified_definition"],
                         {"context": "complex", "category": "model_confidence", "unit": None, "scale": "0-1"})
        locator = transfer["quantity_identity"]["locator"]
        self.assertEqual((locator["record_index"], locator["metric_index"], locator["source"]["path"]),
                         (1, 0, "/synthetic/producer-a/confidence.json"))
        self.assertEqual(transfer["producer"], {"artifact_id": "producer-a", "sha256": hash_file(QS / "producer_a.json"),
                                                "layout": LIST, "summary_id": None})
        self.assertEqual((receipt["outcome"], receipt["artifact_matched_selection"], receipt["quantity_identity_matched"],
                          receipt["transfer_id"], receipt["selected_path"]),
                         ("ADMITTED", True, True, outcome.transfer.transfer_id, str(QS / "producer_a.json")))
        self.assertEqual(receipt["observed_producer"], {"sha256": transfer["producer"]["sha256"], "layout": LIST})
        self.assertEqual(self.checks(outcome), ["PASSED"] * 4 + ["ADMITTED"])
        single = link(selection("producer_b.json", SINGLE), evidence_request("syn-b:/iptm", "syn-b1"))
        self.assertEqual(single.transfer.data["payload"]["value"], 0.55)

    def test_linked_transfer_from_quantity_summary(self):
        summary_id = json.loads((QS / "summary_abc.golden.json").read_text())["summary_id"]
        expected = {"min": 0.55, "median": 0.62 / 2 + 0.71 / 2, "max": 0.8,
                    "mean": math.fsum([0.62, 0.71, 0.55, 0.8]) / 4}
        for statistic, value in expected.items():
            with self.subTest(statistic=statistic):
                outcome = link(MEDIAN[0](), summary_request(statistic))
                data = outcome.transfer.data
                self.assertEqual(data["payload"], {"status": "ADMITTED", "value": value, "reason": None})
                self.assertEqual(data["producer"]["summary_id"], summary_id)
                self.assertEqual(data["quantity_identity"]["locator"],
                                 {"summary_id": summary_id, "quantity_id": "syn-iptm", "statistic": statistic,
                                  "statistics_status": "SUMMARIZED", "count": 4})
        median = link(*[MEDIAN[0](), MEDIAN[1]])
        self.assertEqual(median.transfer.to_json_bytes() + b"\n", (LT / "transfer_summary_median.golden.json").read_bytes())


# --------------------------------------------------------------------------
# Rejections
# --------------------------------------------------------------------------
class Rejections(Temp):
    def test_wrong_selected_artifact_hash(self):
        sel = dict(A2[0](), sha256="0" * 64)
        receipt = self.rejected(sel, A2[1], "ARTIFACT_HASH_MISMATCH")
        self.assertEqual(receipt["expected_producer"]["sha256"], "0" * 64)
        self.assertEqual(receipt["observed_producer"], {"sha256": hash_file(QS / "producer_a.json"), "layout": None})
        self.assertEqual((receipt["artifact_matched_selection"], receipt["quantity_identity_matched"]), (False, None))
        swapped = dict(A2[0](), path=str(QS / "producer_b.json"))
        self.rejected(swapped, A2[1], "ARTIFACT_HASH_MISMATCH")

    def test_wrong_artifact_layout_or_type(self):
        cases = (("producer_a.json", SUMMARY, LIST), ("summary_abc.golden.json", SINGLE, SUMMARY),
                 ("producer_b.json", LIST, SINGLE), ("producer_a.json", SINGLE, LIST))
        for name, declared, observed in cases:
            with self.subTest(name=name, declared=declared):
                req = summary_request("mean") if declared == SUMMARY else evidence_request("syn-a:/iptm", "syn-a2")
                receipt = self.rejected(selection(name, declared), req, "ARTIFACT_LAYOUT_MISMATCH", observed)
                self.assertFalse(receipt["artifact_matched_selection"])
        req = evidence_request("syn-t:/iptm", "t1")
        self.rejected(self.write("other.json", {"x": 1}, layout=SINGLE), req, "ARTIFACT_LAYOUT_MISMATCH", "UNRECOGNIZED")
        self.rejected(self.write("cut.json", raw=b"[{"), req, "ARTIFACT_PARSE_ERROR", "UNPARSEABLE")
        self.rejected(self.write("dup.json", raw=b'{"a": 1, "a": 2}', layout=SINGLE), req, "ARTIFACT_PARSE_ERROR")
        broken = record("t1", 0.5)
        del broken["warnings"]
        self.rejected(self.write("broken.json", [broken]), req, "ARTIFACT_RECORD_INVALID", LIST)
        tampered = json.loads((QS / "summary_abc.golden.json").read_text())
        tampered["statistics"]["mean"] = 0.9
        self.rejected(self.write("tampered.json", tampered, layout=SUMMARY), summary_request("mean"),
                      "SUMMARY_INVALID", SUMMARY)

    def test_quantity_identity_mismatch(self):
        for key, value in (("scale", "0-100"), ("unit", "1"), ("category", "sequence_model_score")):
            with self.subTest(key=key):
                receipt = self.rejected(A2[0](), evidence_request("syn-a:/iptm", "syn-a2", **{key: value}),
                                        "QUANTITY_IDENTITY_MISMATCH")
                self.assertEqual((receipt["artifact_matched_selection"], receipt["quantity_identity_matched"]),
                                 (True, False))
        receipt = self.rejected(selection("producer_d_scale_0_100.json", SINGLE),
                                evidence_request("syn-d:/iptm", "syn-d1"), "QUANTITY_IDENTITY_MISMATCH")
        self.assertIn("scale is '0-100', declared '0-1'", receipt["failure"]["detail"])
        for key, value in (("quantity_id", "other-quantity"), ("context", "monomer"), ("scale", None)):
            with self.subTest(summary_field=key):
                receipt = self.rejected(MEDIAN[0](), summary_request("median", **{key: value}),
                                        "QUANTITY_IDENTITY_MISMATCH")
                self.assertTrue(receipt["failure"]["detail"].startswith(f"{key} is "))

    def test_selector_must_identify_one_record(self):
        self.rejected(A2[0](), evidence_request("syn-a:/iptm", "syn-zz"), "SELECTOR_NOT_FOUND")
        self.rejected(A2[0](), evidence_request("syn-a:/iptm", "syn-a2", target=None), "SELECTOR_NOT_FOUND")
        twice = self.write("twice.json", [record("t1", 0.1), record("t1", 0.2)])
        self.rejected(twice, evidence_request("syn-t:/iptm", "t1"), "SELECTOR_AMBIGUOUS")

    def test_path_form(self):
        link_path = self.root / "alias.json"
        link_path.symlink_to(QS / "producer_a.json")
        (self.root / "sub").mkdir()
        for path in ("producer_a.json", str(self.root / "sub" / ".." / "alias.json"), str(link_path),
                     str(self.root / "sub"), str(self.root / "missing.json"), ""):
            with self.subTest(path=path):
                receipt = self.rejected(dict(A2[0](), path=path), A2[1], "ARTIFACT_PATH_INVALID")
                self.assertEqual((receipt["selected_path"], receipt["observed_producer"],
                                  receipt["artifact_matched_selection"]), (path, {"sha256": None, "layout": None}, None))

    def test_artifact_changed_during_verification(self):
        with patch.object(lt, "hash_file", return_value="f" * 64):
            receipt = self.rejected(A2[0](), A2[1], "ARTIFACT_CHANGED")
        self.assertEqual(receipt["observed_producer"], {"sha256": "f" * 64, "layout": None})

    def test_rejection_produces_canonical_failure_receipt(self):
        sel = dict(A2[0](), path="/synthetic/not-present/producer_a.json")
        outcome = link(sel, A2[1])
        self.assertEqual(outcome.receipt.to_json_bytes() + b"\n",
                         (LT / "receipt_rejected_missing_path.golden.json").read_bytes())
        self.assertEqual(outcome.receipt.data["failure"],
                         {"class": "ARTIFACT_PATH_INVALID", "stage": "PATH_FORM",
                          "detail": "path is not readable (FileNotFoundError)"})
        self.assertEqual(TransferOutcome(outcome.receipt, None), outcome)


# --------------------------------------------------------------------------
# Unavailable and excluded payloads
# --------------------------------------------------------------------------
class CarriedReasons(Temp):
    def test_unavailable_value_is_carried_through_not_coerced(self):
        outcome = link(selection("producer_c.json", LIST), evidence_request("syn-c:/iptm", "syn-c2"))
        payload = outcome.transfer.data["payload"]
        self.assertEqual(payload, {"status": "UNAVAILABLE", "value": None,
                                   "reason": {"code": "VALUE_UNAVAILABLE", "detail": "missing_value"}})
        self.assertIn(b'"value":null', outcome.transfer.to_json_bytes())
        self.assertEqual(outcome.receipt.data["carried_reason"], payload["reason"])
        self.assertEqual((outcome.receipt.data["outcome"], outcome.receipt.data["failure"]), ("UNAVAILABLE", None))
        self.assertEqual(self.checks(outcome), ["PASSED"] * 4 + ["UNAVAILABLE"])

        empty = self.write("nulls.json", [record("t1", None, missing="missing_value")])
        summary = summarize_quantity(quantity=QUANTITY, artifacts=[dict(empty, metric_name="syn-t:/iptm")])
        write_json_new(self.root / "empty_summary.json", summary.to_dict())
        sel = {"artifact_id": "empty-summary", "path": str(self.root / "empty_summary.json"),
               "sha256": hash_file(self.root / "empty_summary.json"), "layout": SUMMARY}
        for statistic in lt.STATISTICS:
            with self.subTest(statistic=statistic):
                data = link(sel, summary_request(statistic)).transfer.data
                self.assertEqual((data["payload"]["status"], data["payload"]["value"], data["payload"]["reason"]["code"]),
                                 ("UNAVAILABLE", None, "NO_ACCEPTED_VALUES"))
                self.assertEqual(data["quantity_identity"]["locator"]["statistics_status"], "NO_ACCEPTED_VALUES")

    def test_excluded_payload_receipts(self):
        absent = link(selection("producer_c.json", LIST), evidence_request("syn-c:/iptm", "syn-c1"))
        self.assertEqual(self.checks(absent), ["PASSED"] * 3 + ["ABSENT", "NOT_REACHED"])
        receipt = absent.receipt.data
        self.assertEqual((receipt["outcome"], receipt["quantity_identity_matched"], receipt["failure"],
                          receipt["carried_reason"]["code"]), ("EXCLUDED", None, None, "METRIC_ABSENT"))
        self.assertIn("name present in contexts ['monomer']", receipt["carried_reason"]["detail"])
        self.assertIsNone(absent.transfer.data["quantity_identity"]["verified_definition"])
        inexact = link(self.write("inexact.json", [record("t1", 2 ** 53 + 1)]), evidence_request("syn-t:/iptm", "t1"))
        self.assertEqual(self.checks(inexact), ["PASSED"] * 4 + ["EXCLUDED"])
        self.assertEqual((inexact.receipt.data["carried_reason"]["code"], inexact.transfer.data["payload"]["value"]),
                         ("INTEGER_NOT_EXACTLY_REPRESENTABLE", None))
        exact = link(self.write("exact.json", [record("t1", 3)]), evidence_request("syn-t:/iptm", "t1"))
        self.assertIs(type(exact.transfer.data["payload"]["value"]), float)


# --------------------------------------------------------------------------
# Serialization, reload and replay
# --------------------------------------------------------------------------
class Serialization(Temp):
    def outcomes(self):
        return {
            "admitted evidence": link(A2[0](), A2[1]),
            "admitted summary": link(MEDIAN[0](), MEDIAN[1]),
            "unavailable": link(selection("producer_c.json", LIST), evidence_request("syn-c:/iptm", "syn-c2")),
            "excluded": link(selection("producer_c.json", LIST), evidence_request("syn-c:/iptm", "syn-c1")),
            "rejected": link(dict(A2[0](), sha256="0" * 64), A2[1]),
        }

    def test_export_reload_reserialize_is_byte_stable(self):
        for label, outcome in self.outcomes().items():
            with self.subTest(outcome=label):
                folder = self.root / label.replace(" ", "_")
                folder.mkdir()
                write_json_new(folder / "receipt.json", outcome.receipt.to_dict())
                receipt = load_transfer_receipt(folder / "receipt.json")
                self.assertEqual(receipt.to_json_bytes() + b"\n", (folder / "receipt.json").read_bytes())
                self.assertEqual(TransferReceipt.from_dict(json.loads(receipt.to_json_bytes())), outcome.receipt)
                transfer = None
                if outcome.transfer is not None:
                    write_json_new(folder / "transfer.json", outcome.transfer.to_dict())
                    transfer = load_linked_transfer(folder / "transfer.json")
                    self.assertEqual(transfer.to_json_bytes() + b"\n", (folder / "transfer.json").read_bytes())
                    self.assertEqual(LinkedTransfer.from_dict(json.loads(transfer.to_json_bytes())), outcome.transfer)
                self.assertEqual(TransferOutcome(receipt, transfer), outcome)
                with self.assertRaises(FileExistsError):
                    write_json_new(folder / "receipt.json", outcome.receipt.to_dict())

    def test_replay_and_location_independence(self):
        first, second = link(A2[0](), A2[1]), link(A2[0](), A2[1])
        self.assertEqual((first.receipt.to_json_bytes(), first.transfer.to_json_bytes()),
                         (second.receipt.to_json_bytes(), second.transfer.to_json_bytes()))
        moved = self.root / "moved"
        shutil.copytree(QS, moved)
        elsewhere = link(selection("producer_a.json", LIST, root=moved, artifact_id="producer-a"), A2[1])
        self.assertEqual(elsewhere.transfer.to_json_bytes(), first.transfer.to_json_bytes())
        strip = lambda r: {k: v for k, v in r.data.items() if k not in ("selected_path", "receipt_id")}
        self.assertEqual(strip(elsewhere.receipt), strip(first.receipt))
        self.assertNotEqual(elsewhere.receipt.receipt_id, first.receipt.receipt_id)

    def test_reload_rejects_altered_documents(self):
        outcomes = self.outcomes()
        mismatch = link(A2[0](), evidence_request("syn-a:/iptm", "syn-a2", scale="0-100")).receipt.to_dict()
        docs = {"transfer": outcomes["admitted evidence"].transfer.to_dict(),
                "unavailable": outcomes["unavailable"].transfer.to_dict(),
                "absent": outcomes["excluded"].transfer.to_dict(),
                "receipt": outcomes["admitted evidence"].receipt.to_dict(),
                "rejected": outcomes["rejected"].receipt.to_dict(), "mismatch": mismatch}

        def expect_invalid(base, change, reseal):
            data = deepcopy(docs[base])
            change(data)
            cls, id_key, code = ((TransferReceipt, "receipt_id", "RECEIPT_INVALID")
                                 if base in ("receipt", "rejected", "mismatch")
                                 else (LinkedTransfer, "transfer_id", "TRANSFER_INVALID"))
            if reseal:  # a producer that recomputes the id: the invariants must still reject
                data[id_key] = hash_config({k: v for k, v in data.items() if k != id_key})
            with self.assertRaises(LinkedTransferError) as caught:
                cls.from_dict(data)
            self.assertEqual(caught.exception.code, code)

        integrity = {  # id left stale
            "value": ("transfer", lambda d: d["payload"].update(value=0.99)),
            "producer sha": ("transfer", lambda d: d["producer"].update(sha256="0" * 64)),
            "transfer_id": ("transfer", lambda d: d.update(transfer_id="0" * 64)),
            "selected path": ("receipt", lambda d: d.update(selected_path="/elsewhere/producer_a.json")),
            "receipt_id": ("receipt", lambda d: d.update(receipt_id="0" * 64)),
        }
        invariants = {  # id recomputed
            "value as integer": ("transfer", lambda d: d["payload"].update(value=1)),
            "status": ("transfer", lambda d: d["payload"].update(status="UNAVAILABLE")),
            "unavailable coerced to 0.0": ("unavailable", lambda d: d["payload"].update(value=0.0)),
            "reason dropped": ("unavailable", lambda d: d["payload"].update(reason=None)),
            "check order": ("transfer", lambda d: d["checks"].reverse()),
            "payload after ABSENT": ("absent", lambda d: d["checks"][4].update(result="EXCLUDED")),
            "definition": ("transfer", lambda d: d["quantity_identity"]["verified_definition"].update(scale="0-100")),
            "locator": ("transfer", lambda d: d["quantity_identity"]["locator"].update(candidate_id="syn-a1")),
            "summary_id on evidence": ("transfer", lambda d: d["producer"].update(summary_id="0" * 64)),
            "extra field": ("transfer", lambda d: d.update(recorded_at="2026-09-25")),
            "outcome": ("receipt", lambda d: d.update(outcome="EXCLUDED")),
            "matched flag": ("receipt", lambda d: d.update(artifact_matched_selection=False)),
            "identity flag": ("receipt", lambda d: d.update(quantity_identity_matched=None)),
            "observed sha": ("receipt", lambda d: d["observed_producer"].update(sha256="0" * 64)),
            "transfer link dropped": ("receipt", lambda d: d.update(transfer_id=None)),
            "failure stage": ("rejected", lambda d: d["failure"].update(stage="LAYOUT")),
            "failure class": ("rejected", lambda d: d["failure"].update(**{"class": "SUMMARY_INVALID"})),
            "failure dropped": ("rejected", lambda d: d.update(failure=None)),
            "observed equals expected": ("rejected", lambda d: d["observed_producer"].update(sha256="0" * 64)),
            "payload after FAILED": ("mismatch", lambda d: d["checks"][4].update(result="ADMITTED")),
        }
        for label, (base, change) in integrity.items():
            with self.subTest(integrity=label):
                expect_invalid(base, change, reseal=False)
        for label, (base, change) in invariants.items():
            for reseal in (False, True):
                with self.subTest(invariant=label, reseal=reseal):
                    expect_invalid(base, change, reseal)
        path = self.root / "bad.json"
        path.write_bytes(b'{"schema_version": "linked_transfer/1", "schema_version": "x"}')
        with self.assertRaises(LinkedTransferError):
            load_linked_transfer(path)

    def test_receipt_and_transfer_must_describe_one_event(self):
        outcomes = self.outcomes()
        pairs = ((outcomes["admitted evidence"].receipt, outcomes["admitted summary"].transfer),
                 (outcomes["rejected"].receipt, outcomes["admitted evidence"].transfer),
                 (outcomes["admitted evidence"].receipt, None),
                 (outcomes["admitted evidence"].receipt.to_dict(), outcomes["admitted evidence"].transfer))
        for receipt, transfer in pairs:
            with self.assertRaises(LinkedTransferError) as caught:
                TransferOutcome(receipt, transfer)
            self.assertEqual(caught.exception.code, "LINK_INVALID")


# --------------------------------------------------------------------------
# Contract and isolation
# --------------------------------------------------------------------------
class ContractAndIsolation(Temp):
    def test_malformed_contract_raises_without_receipt(self):
        sel, req = A2[0](), A2[1]
        selections = [dict(sel, extra=1), dict(sel, sha256="ABC"), dict(sel, layout="latest"), dict(sel, path=None),
                      dict(sel, artifact_id="bad id"), [sel]]
        for bad in selections:
            with self.subTest(selection=bad), self.assertRaises(LinkedTransferError) as caught:
                link_transfer(selection=bad, request=req)
            self.assertEqual(caught.exception.code, "CONTRACT_INVALID")
        requests = [dict(req, item={"statistic": "mean"}), dict(req, consumer_id=""),
                    dict(req, quantity={k: v for k, v in QUANTITY.items() if k != "unit"}),
                    dict(req, item=dict(req["item"], target_id=3)), dict(req, extra=1)]
        for bad in requests:
            with self.subTest(request=bad), self.assertRaises(LinkedTransferError) as caught:
                link_transfer(selection=sel, request=bad)
            self.assertEqual(caught.exception.code, "CONTRACT_INVALID")
        for statistic in ("count", "latest"):
            with self.assertRaises(LinkedTransferError):
                link_transfer(selection=MEDIAN[0](), request=summary_request(statistic))

    def test_reads_only_the_selected_artifact_and_schemas(self):
        schemas = {SCHEMAS / f"{n}.schema.json" for n in
                   ("candidate_evidence", "quantity_summary", "linked_transfer", "transfer_receipt")}
        for sel, req in ((A2[0](), A2[1]), (MEDIAN[0](), MEDIAN[1])):
            expected = link(sel, req)
            allowed = schemas | {Path(sel["path"])}
            environ = dict(os.environ)
            original_open, original_io = builtins.open, io.open

            def readonly(fn):
                def guarded(file, mode="r", *args, **kwargs):
                    if any(x in mode for x in "wax+"):
                        raise AssertionError("Unexpected write")
                    if Path(file) not in allowed:
                        raise AssertionError(f"Unexpected read: {file}")
                    return fn(file, mode, *args, **kwargs)
                return guarded

            with ExitStack() as stack:
                for obj, attr in ((socket, "socket"), (socket, "create_connection"), (subprocess, "Popen"),
                                  (os, "system"), (os, "listdir"), (os, "scandir"), (os, "walk"), (glob, "glob"),
                                  (glob, "iglob"), (Path, "glob"), (Path, "rglob"), (Path, "iterdir"),
                                  (Path, "mkdir"), (Path, "unlink"), (Path, "rename"), (Path, "touch")):
                    stack.enter_context(patch.object(obj, attr, side_effect=AssertionError(f"Forbidden {attr}")))
                stack.enter_context(patch.object(builtins, "open", side_effect=readonly(original_open)))
                stack.enter_context(patch.object(io, "open", side_effect=readonly(original_io)))
                result = link_transfer(selection=deepcopy(sel), request=deepcopy(req))
            self.assertEqual(result, expected)
            self.assertEqual(dict(os.environ), environ)

    def test_inputs_not_mutated(self):
        sel, req = A2[0](), A2[1]
        snapshot = deepcopy((sel, req))
        outcome = link_transfer(selection=sel, request=req)
        self.assertEqual((sel, req), snapshot)
        exported = outcome.transfer.to_dict()
        exported["payload"]["value"] = 0.0
        self.assertEqual(outcome.transfer.data["payload"]["value"], 0.71)

    def test_schema_vocabulary_matches_module(self):
        transfer = json.loads((SCHEMAS / "linked_transfer.schema.json").read_text())
        receipt = json.loads((SCHEMAS / "transfer_receipt.schema.json").read_text())
        self.assertEqual(transfer["properties"]["producer"]["properties"]["layout"]["enum"], list(lt.LAYOUTS))
        self.assertEqual(set(receipt["properties"]["failure"]["properties"]["class"]["enum"]), set(lt.FAILURE_STAGE))
        self.assertEqual(set(transfer["properties"]["payload"]["properties"]["reason"]["properties"]["code"]["enum"]),
                         set(lt.REASON_OUTCOME))
        self.assertEqual(receipt["properties"]["outcome"]["enum"], list(lt.OUTCOMES))
        self.assertEqual([c for c in transfer["properties"]["checks"]["items"]["properties"]["check"]["enum"]],
                         list(lt.CHECKS))


if __name__ == "__main__":
    unittest.main()
