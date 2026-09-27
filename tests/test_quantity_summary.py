"""Synthetic contract tests for quantity_summary; only fixture setup writes temporary files."""
import builtins
from contextlib import ExitStack
from copy import deepcopy
import glob
import io
from itertools import permutations
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

from structure_audit import quantity_summary as qs
from structure_audit.provenance import canonical_json, hash_config, hash_file, write_json_new
from structure_audit.quantity_summary import (
    QuantitySummary, QuantitySummaryError, load_quantity_summary, summarize_quantity,
)

FIXTURES = (Path(__file__).parent / "fixtures" / "quantity_summary").resolve()
SCHEMAS = Path(qs.__file__).resolve().parent / "schemas"
LIST, SINGLE = "candidate_evidence_list_v1", "candidate_evidence_v1"
QUANTITY = {"quantity_id": "syn-iptm", "context": "complex", "category": "model_confidence",
            "unit": None, "scale": "0-1"}
SELECT = {
    "A": ("producer-a", "producer_a.json", LIST, "syn-a:/iptm"),
    "B": ("producer-b", "producer_b.json", SINGLE, "syn-b:/iptm"),
    "C": ("producer-c", "producer_c.json", LIST, "syn-c:/iptm"),
    "D": ("producer-d", "producer_d_scale_0_100.json", SINGLE, "syn-d:/iptm"),
}
PROV = {"model_id": "synthetic-model", "checkpoint_id": None, "seed": 0}


def selection(key, root=FIXTURES):
    artifact_id, name, layout, metric_name = SELECT[key]
    path = root / name
    return {"artifact_id": artifact_id, "path": str(path), "sha256": hash_file(path),
            "layout": layout, "metric_name": metric_name}


def summarize(*keys, root=FIXTURES, quantity=QUANTITY):
    return summarize_quantity(quantity=deepcopy(quantity), artifacts=[selection(k, root) for k in keys])


def record(candidate, value, *, missing=None, name="syn-t:/iptm", scale="0-1", unit=None,
           category="model_confidence", context="complex"):
    metric = {"name": name, "raw_value": value, "value": value, "context": context, "category": category,
              "unit": unit, "scale": scale, "source": {"path": "/synthetic/producer-t/values.json",
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

    def artifact(self, name, document=None, *, raw=None, layout=LIST, metric_name="syn-t:/iptm", artifact_id=None):
        path = self.root / name
        path.write_bytes(raw if raw is not None else json.dumps(document).encode("utf-8"))
        return {"artifact_id": artifact_id or name.split(".")[0], "path": str(path), "sha256": hash_file(path),
                "layout": layout, "metric_name": metric_name}

    def error(self, code, *, quantity=QUANTITY, artifacts):
        with self.assertRaises(QuantitySummaryError) as caught:
            summarize_quantity(quantity=deepcopy(quantity), artifacts=artifacts)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        self.assertEqual(caught.exception.diagnostics[0]["code"], code)
        return caught.exception


# --------------------------------------------------------------------------
# Summaries
# --------------------------------------------------------------------------
class Summaries(Temp):
    def test_compatible_multi_value_summary(self):
        data = summarize("B", "A").to_dict()
        self.assertEqual(data["statistics"], {"status": "SUMMARIZED", "count": 3, "min": 0.55, "median": 0.62,
                                              "max": 0.71, "mean": math.fsum([0.62, 0.71, 0.55]) / 3})
        self.assertEqual(data["availability"], {"total_records": 3, "accepted_count": 3, "excluded_count": 0,
                                                "exclusion_reason_counts": {"METRIC_ABSENT": 0, "VALUE_UNAVAILABLE": 0,
                                                                            "INTEGER_NOT_EXACTLY_REPRESENTABLE": 0}})
        self.assertEqual([a["artifact_id"] for a in data["producer_artifacts"]], ["producer-a", "producer-b"])
        self.assertEqual([v["value_id"] for v in data["values"]], ["producer-a#0", "producer-a#1", "producer-b#0"])
        self.assertTrue(all(type(v["value"]) is float and v["status"] == "accepted" for v in data["values"]))

    def test_singleton_summary(self):
        data = summarize("B").to_dict()
        self.assertEqual(data["statistics"], {"status": "SUMMARIZED", "count": 1, "min": 0.55, "median": 0.55,
                                              "max": 0.55, "mean": 0.55})
        (value,) = data["values"]
        self.assertEqual((value["candidate_id"], value["metric_index"], value["producer_provenance"]),
                         ("syn-b1", 0, PROV))
        self.assertEqual(data["producer_artifacts"][0]["layout"], SINGLE)

    def test_unavailable_values_are_excluded_with_exact_reasons(self):
        data = summarize("C").to_dict()
        outcome = {v["candidate_id"]: (v["status"], v["exclusion_reason"], v["exclusion_detail"]) for v in data["values"]}
        self.assertEqual(outcome, {
            "syn-c1": ("excluded", "METRIC_ABSENT",
                       "no metric ('complex', 'syn-c:/iptm'); name present in contexts ['monomer']"),
            "syn-c2": ("excluded", "VALUE_UNAVAILABLE", "missing_value"),
            "syn-c3": ("accepted", None, None),
        })
        absent = data["values"][0]
        self.assertEqual((absent["metric_index"], absent["source"], absent["producer_provenance"]), (None, None, None))
        self.assertEqual(data["values"][1]["source"]["path"], "/synthetic/producer-c/confidence.json")
        self.assertEqual(data["availability"]["exclusion_reason_counts"],
                         {"METRIC_ABSENT": 1, "VALUE_UNAVAILABLE": 1, "INTEGER_NOT_EXACTLY_REPRESENTABLE": 0})
        self.assertEqual((data["statistics"]["count"], data["statistics"]["mean"]), (1, 0.8))

    def test_no_accepted_values(self):
        art = self.artifact("none.json", [record("t1", None, missing="missing_value"),
                                          record("t2", None, missing="non_finite_token")])
        data = summarize_quantity(quantity=QUANTITY, artifacts=[art]).to_dict()
        self.assertEqual(data["statistics"], {"status": "NO_ACCEPTED_VALUES", "count": 0, "min": None,
                                              "median": None, "max": None, "mean": None})
        self.assertEqual(data["availability"]["excluded_count"], 2)
        self.assertEqual([v["exclusion_detail"] for v in data["values"]], ["missing_value", "non_finite_token"])

    def test_mixed_admissible_and_excluded_inputs_match_golden(self):
        summary = summarize("A", "B", "C")
        self.assertEqual(summary.to_json_bytes() + b"\n", (FIXTURES / "summary_abc.golden.json").read_bytes())
        data = summary.to_dict()
        self.assertEqual(data["statistics"], {"status": "SUMMARIZED", "count": 4, "min": 0.55,
                                              "median": 0.62 / 2 + 0.71 / 2, "max": 0.8,
                                              "mean": math.fsum([0.62, 0.71, 0.55, 0.8]) / 4})
        self.assertEqual({k: data["availability"][k] for k in ("total_records", "accepted_count", "excluded_count")},
                         {"total_records": 6, "accepted_count": 4, "excluded_count": 2})
        self.assertEqual([(v["value_id"], v["status"]) for v in data["values"]],
                         [("producer-a#0", "accepted"), ("producer-a#1", "accepted"), ("producer-b#0", "accepted"),
                          ("producer-c#0", "excluded"), ("producer-c#1", "excluded"), ("producer-c#2", "accepted")])

    def test_even_count_median_and_integer_values(self):
        art = self.artifact("ints.json", [record("t1", 10), record("t2", 1), record("t3", 3.0), record("t4", 2),
                                          record("t5", 2 ** 53 + 1), record("t6", 10 ** 400)])
        data = summarize_quantity(quantity=QUANTITY, artifacts=[art]).to_dict()
        self.assertEqual(data["statistics"], {"status": "SUMMARIZED", "count": 4, "min": 1.0, "median": 2.5,
                                              "max": 10.0, "mean": 4.0})
        self.assertTrue(all(type(v["value"]) is float for v in data["values"] if v["status"] == "accepted"))
        self.assertEqual([v["exclusion_reason"] for v in data["values"][4:]],
                         ["INTEGER_NOT_EXACTLY_REPRESENTABLE"] * 2)

    def test_mean_not_finite_is_rejected(self):
        art = self.artifact("huge.json", [record("t1", 1.5e308), record("t2", 1.5e308)])
        self.error("MEAN_NOT_FINITE", artifacts=[art])


# --------------------------------------------------------------------------
# Quantity-definition compatibility
# --------------------------------------------------------------------------
class Compatibility(Temp):
    def test_incompatible_scale_is_rejected(self):
        exc = self.error("QUANTITY_DEFINITION_INCOMPATIBLE", artifacts=[selection("A"), selection("D")])
        self.assertIn("scale is '0-100', declared '0-1'", str(exc))

    def test_declared_definition_must_match_exactly(self):
        for key, declared in (("unit", "1"), ("scale", None), ("category", "sequence_model_score")):
            with self.subTest(key=key):
                self.error("QUANTITY_DEFINITION_INCOMPATIBLE", quantity=dict(QUANTITY, **{key: declared}),
                           artifacts=[selection("A")])

    def test_definition_is_checked_even_when_the_value_is_unavailable(self):
        art = self.artifact("mismatch.json", [record("t1", 0.5), record("t2", None, missing="missing_value", unit="nm")])
        self.error("QUANTITY_DEFINITION_INCOMPATIBLE", artifacts=[art])


# --------------------------------------------------------------------------
# Explicit selection and ingestion
# --------------------------------------------------------------------------
class Selection(Temp):
    def test_contract_errors(self):
        good = selection("A")
        quantities = [{k: v for k, v in QUANTITY.items() if k != "unit"}, dict(QUANTITY, extra=1),
                      dict(QUANTITY, context="dimer"), dict(QUANTITY, quantity_id="bad id"),
                      dict(QUANTITY, unit=""), dict(QUANTITY, category=None), []]
        for quantity in quantities:
            with self.subTest(quantity=quantity):
                self.error("CONTRACT_INVALID", quantity=quantity, artifacts=[good])
        artifacts = [[], good, [{k: v for k, v in good.items() if k != "layout"}], [dict(good, extra=1)],
                     [dict(good, sha256=good["sha256"].upper())], [dict(good, layout="latest")],
                     [dict(good, metric_name="")], [dict(good, path=Path(good["path"]))]]
        for artifact_list in artifacts:
            with self.subTest(artifacts=artifact_list):
                self.error("CONTRACT_INVALID", artifacts=artifact_list)

    def test_duplicate_selection(self):
        copy = self.root / "copy_of_a.json"
        shutil.copyfile(FIXTURES / "producer_a.json", copy)
        a = selection("A")
        for other in (dict(selection("B"), artifact_id="producer-a"), dict(a, artifact_id="again"),
                      dict(a, artifact_id="copy", path=str(copy))):
            with self.subTest(other=other["artifact_id"]):
                self.error("ARTIFACT_DUPLICATE", artifacts=[a, other])

    def test_paths_must_be_explicit_canonical_regular_files(self):
        a = selection("A")
        link = self.root / "link.json"
        link.symlink_to(FIXTURES / "producer_a.json")
        (self.root / "sub").mkdir()
        for path in ("producer_a.json", str(self.root / "sub" / ".." / "link.json"), str(link),
                     str(self.root / "sub"), str(self.root / "missing.json")):
            with self.subTest(path=path):
                self.error("ARTIFACT_PATH_INVALID", artifacts=[dict(a, path=path)])

    def test_hash_layout_parse_and_record_errors(self):
        self.error("ARTIFACT_HASH_MISMATCH", artifacts=[dict(selection("A"), sha256="0" * 64)])
        self.error("ARTIFACT_LAYOUT_MISMATCH", artifacts=[dict(selection("A"), layout=SINGLE)])
        self.error("ARTIFACT_LAYOUT_MISMATCH", artifacts=[dict(selection("B"), layout=LIST)])
        for name, raw in (("dup.json", b'{"a": 1, "a": 2}'), ("nan.json", b'[{"value": NaN}]'),
                          ("utf.json", b'\xff\xfe[]'), ("trunc.json", b'[{')):
            with self.subTest(case=name):
                self.error("ARTIFACT_PARSE_ERROR", artifacts=[self.artifact(name, raw=raw)])
        broken = record("t1", 0.5)
        del broken["warnings"]
        no_reason = record("t1", None)
        for name, document in (("schema.json", [broken]), ("reason.json", [no_reason]),
                               ("inf.json", None), ("extra.json", [dict(record("t1", 0.5), extra=1)])):
            raw = b'[' + json.dumps(record("t1", 0.5)).replace("0.5", "1e400").encode() + b']' if document is None else None
            with self.subTest(case=name):
                self.error("ARTIFACT_RECORD_INVALID", artifacts=[self.artifact(name, document, raw=raw)])

    def test_duplicate_observation_across_artifacts(self):
        again = json.loads((FIXTURES / "producer_b.json").read_text())
        art = self.artifact("b_again.json", [again], metric_name="syn-b:/iptm")
        exc = self.error("DUPLICATE_OBSERVATION", artifacts=[selection("B"), art])
        self.assertIn("syn-b1", str(exc))

    def test_artifact_changed_before_return(self):
        with patch.object(qs, "hash_file", return_value="0" * 64):
            self.error("ARTIFACT_CHANGED", artifacts=[selection("A")])


# --------------------------------------------------------------------------
# Determinism, canonical serialization and reload
# --------------------------------------------------------------------------
class Serialization(Temp):
    def test_selection_order_and_location_do_not_change_bytes(self):
        expected = summarize("A", "B", "C").to_json_bytes()
        for order in permutations("ABC"):
            self.assertEqual(summarize(*order).to_json_bytes(), expected)
        moved = self.root / "moved"
        shutil.copytree(FIXTURES, moved)
        self.assertEqual(summarize("C", "A", "B", root=moved).to_json_bytes(), expected)
        for root in (str(FIXTURES), str(moved)):
            self.assertNotIn(root.encode(), expected)

    def test_export_reload_reserialize_is_stable(self):
        summary = summarize("A", "B", "C")
        path = self.root / "summary.json"
        write_json_new(path, summary.to_dict())
        data = path.read_bytes()
        self.assertEqual(data, summary.to_json_bytes() + b"\n")
        reloaded = load_quantity_summary(path)
        self.assertEqual(reloaded, summary)
        self.assertEqual(reloaded.to_json_bytes() + b"\n", data)
        again = QuantitySummary.from_dict(json.loads(reloaded.to_json_bytes()))
        self.assertEqual(again.to_json_bytes(), reloaded.to_json_bytes())
        body = {k: v for k, v in again.to_dict().items() if k != "summary_id"}
        self.assertEqual(again.summary_id, hash_config(body))
        with self.assertRaises(FileExistsError):
            write_json_new(path, summary.to_dict())

    def test_reload_rejects_altered_documents(self):
        original = summarize("A", "B", "C").to_dict()

        def altered(change):
            data = deepcopy(original)
            change(data)
            return data

        cases = {
            "mean": lambda d: d["statistics"].update(mean=0.5),
            "integer statistic": lambda d: d["statistics"].update(count=4.0),
            "accepted value": lambda d: d["values"][0].update(value=0.99),
            "value as integer": lambda d: d["values"][0].update(value=1),
            "summary_id": lambda d: d.update(summary_id="0" * 64),
            "value order": lambda d: d["values"].reverse(),
            "dropped value": lambda d: d["values"].pop(),
            "reason on accepted": lambda d: d["values"][0].update(exclusion_reason="METRIC_ABSENT"),
            "reason count": lambda d: d["availability"]["exclusion_reason_counts"].update(METRIC_ABSENT=0),
            "rule text": lambda d: d["rules"].update(mean="arithmetic mean"),
            "extra field": lambda d: d.update(generated_at="2026-09-25"),
            "quantity unit": lambda d: d["quantity"].update(unit=""),
            "record count": lambda d: d["producer_artifacts"][0].update(record_count=3),
        }
        for label, change in cases.items():
            with self.subTest(case=label), self.assertRaises(QuantitySummaryError) as caught:
                QuantitySummary.from_dict(altered(change))
            self.assertEqual(caught.exception.code, "SUMMARY_INVALID", label)
        path = self.root / "bad.json"
        path.write_bytes(b'{"schema_version": "quantity_summary/1", "schema_version": "x"}')
        with self.assertRaises(QuantitySummaryError) as caught:
            load_quantity_summary(path)
        self.assertEqual(caught.exception.code, "SUMMARY_INVALID")

    def test_canonical_json_round_trip(self):
        summary = summarize("C", "A")
        data = json.loads(summary.to_json_bytes())
        self.assertEqual(canonical_json(data), summary.to_json_bytes())
        self.assertEqual(QuantitySummary.from_dict(data).to_dict(), data)


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------
class Isolation(Temp):
    def test_reads_only_selected_artifacts_and_schemas(self):
        artifacts = [selection(k) for k in "ABC"]
        allowed = {Path(a["path"]) for a in artifacts} | {SCHEMAS / "candidate_evidence.schema.json",
                                                          SCHEMAS / "quantity_summary.schema.json"}
        expected = summarize("A", "B", "C").to_json_bytes()
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
                              (glob, "iglob"), (Path, "glob"), (Path, "rglob"), (Path, "iterdir"), (Path, "mkdir"),
                              (Path, "unlink"), (Path, "rename"), (Path, "replace"), (Path, "touch")):
                stack.enter_context(patch.object(obj, attr, side_effect=AssertionError(f"Forbidden {attr}")))
            stack.enter_context(patch.object(builtins, "open", side_effect=readonly(original_open)))
            stack.enter_context(patch.object(io, "open", side_effect=readonly(original_io)))
            result = summarize_quantity(quantity=deepcopy(QUANTITY), artifacts=deepcopy(artifacts))
        self.assertEqual(result.to_json_bytes(), expected)
        self.assertEqual(dict(os.environ), environ)

    def test_inputs_not_mutated(self):
        quantity, artifacts = deepcopy(QUANTITY), [selection(k) for k in "CBA"]
        snapshot = deepcopy((quantity, artifacts))
        summary = summarize_quantity(quantity=quantity, artifacts=artifacts)
        self.assertEqual((quantity, artifacts), snapshot)
        exported = summary.to_dict()
        exported["statistics"]["mean"] = 0.0
        self.assertNotEqual(summary.to_dict()["statistics"]["mean"], 0.0)

    def test_vocabulary_matches_candidate_evidence_and_summary_schemas(self):
        evidence = json.loads((SCHEMAS / "candidate_evidence.schema.json").read_text())
        summary = json.loads((SCHEMAS / "quantity_summary.schema.json").read_text())
        contexts = evidence["properties"]["metrics"]["items"]["properties"]["context"]["enum"]
        self.assertEqual(summary["properties"]["quantity"]["properties"]["context"]["enum"], contexts)
        reasons = summary["properties"]["values"]["items"]["properties"]["exclusion_reason"]["enum"]
        self.assertEqual(reasons, [None, *qs.EXCLUSION_REASONS])
        self.assertEqual(summary["properties"]["producer_artifacts"]["items"]["properties"]["layout"]["enum"],
                         list(qs.LAYOUTS))


if __name__ == "__main__":
    unittest.main()
