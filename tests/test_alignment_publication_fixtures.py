"""Pins the committed alignment_publication fixture pack and its notebook-facing runtime binding.

The pack under tests/fixtures/alignment_publication is synthetic and repository-owned. A
consumer injects exactly two runtime fields, artifact.path and config.allowed_input_roots;
every other request field, the declared content hash and every reference id is committed.
Public APIs only; the only files written are copies inside a temporary directory.
"""
import hashlib
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import tempfile
import unittest

from structure_audit.alignment_publication import (
    publish_alignment_evidence, publish_alignment_handoff, verify_alignment_handoff,
)
from structure_audit.validation import read_json

PACK = (Path(__file__).parent / "fixtures" / "alignment_publication").resolve()
PACK_FILES = ["references.json", "requests.json", "source.a3m"]
CASE_ORDER = ["available", "unavailable", "unsupported", "rejected"]
SET_ORDER = ["ready", "blocked"]
RUNTIME_FIELDS = {"artifact": {"path"}, "config": {"allowed_input_roots"}}
EXPECTED = {  # case -> (envelope status, reason, reader code)
    "available": ("AVAILABLE", None, None),
    "unavailable": ("UNAVAILABLE", "SOURCE_UNREADABLE", "artifact_read_error"),
    "unsupported": ("UNSUPPORTED", "SOURCE_LAYOUT_UNSUPPORTED", "profile_mismatch"),
    "rejected": ("REJECTED", "SOURCE_SELECTION_REJECTED", "malformed_occurrence_identity"),
}


def cases(root=PACK):
    return read_json(root / "requests.json")["cases"]


def reference_sets(root=PACK):
    return {entry["name"]: entry["references"] for entry in read_json(root / "references.json")["sets"]}


def bind(case, root=PACK):
    """The notebook-facing binding: inject the two runtime fields and nothing else."""
    return {"artifact": {**case["artifact"], "path": str(root / case["source_file"])},
            "config": {**case["config"], "allowed_input_roots": [str(root)]}}


def envelopes(root=PACK):
    return {case["name"]: publish_alignment_evidence(**bind(case, root)) for case in cases(root)}


def handoff(envelope, references):
    return publish_alignment_handoff(envelope=envelope, expected_envelope_id=envelope.envelope_id,
                                     references=references)


def walk(node, keys, strings):
    if isinstance(node, dict):
        keys.update(node)
        for value in node.values():
            walk(value, keys, strings)
    elif isinstance(node, list):
        for value in node:
            walk(value, keys, strings)
    elif isinstance(node, str):
        strings.append(node)
    return keys, strings


def pack_digests(root=PACK):
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in PACK_FILES}


def outcome(envelope):
    data = envelope.to_dict()
    return data["status"], data["reason"], (data["reader_diagnostic"] or {}).get("code")


class PackLayout(unittest.TestCase):
    def test_pack_holds_exactly_the_three_committed_files(self):
        self.assertEqual(sorted(p.name for p in PACK.iterdir() if not p.name.startswith(".")), PACK_FILES)

    def test_fixture_order_is_stable_and_explicit(self):
        requests, references = read_json(PACK / "requests.json"), read_json(PACK / "references.json")
        self.assertEqual(list(requests), ["cases"])
        self.assertEqual(list(references), ["sets"])
        self.assertEqual([case["name"] for case in requests["cases"]], CASE_ORDER)
        self.assertEqual([entry["name"] for entry in references["sets"]], SET_ORDER)
        for case in requests["cases"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(list(case), ["name", "source_file", "artifact", "config"])
        for entry in references["sets"]:
            with self.subTest(set=entry["name"]):
                self.assertEqual(list(entry), ["name", "references"])
                self.assertTrue(entry["references"])

    def test_no_fixture_contains_an_absolute_path_or_a_runtime_field(self):
        for name in ("requests.json", "references.json"):
            with self.subTest(file=name):
                keys, strings = walk(read_json(PACK / name), set(), [])
                self.assertEqual(keys & {"path", "allowed_input_roots"}, set())
                for value in strings:
                    self.assertFalse(PurePosixPath(value).is_absolute(), value)
                    self.assertFalse(PureWindowsPath(value).is_absolute() or PureWindowsPath(value).drive, value)
                    self.assertNotIn("\\", value)
        for case in cases():
            with self.subTest(source_file=case["source_file"]):
                self.assertEqual(PurePosixPath(case["source_file"]).name, case["source_file"])
                self.assertEqual(PurePosixPath(case["source_file"]).suffix, ".a3m")

    def test_every_case_declares_the_committed_content_hash_of_the_source(self):
        digest = hashlib.sha256((PACK / "source.a3m").read_bytes()).hexdigest()
        for case in cases():
            with self.subTest(case=case["name"]):
                self.assertEqual(case["artifact"]["sha256"], digest)
                self.assertEqual(case["config"]["expected_artifact_sha256"], digest)
                self.assertEqual((PACK / case["source_file"]).is_file(), case["name"] != "unavailable")


class RuntimeBinding(unittest.TestCase):
    def test_binding_adds_exactly_the_two_runtime_fields(self):
        for case in cases():
            with self.subTest(case=case["name"]):
                bound = bind(case)
                for part, fields in RUNTIME_FIELDS.items():
                    self.assertEqual(set(bound[part]) - set(case[part]), fields)
                    self.assertEqual({k: v for k, v in bound[part].items() if k not in fields}, case[part])

    def test_each_runtime_injection_is_necessary(self):
        case = cases()[0]
        bound = bind(case)
        without_path = {"artifact": case["artifact"], "config": bound["config"]}
        without_roots = {"artifact": bound["artifact"], "config": case["config"]}
        relative = {"artifact": {**case["artifact"], "path": case["source_file"]}, "config": bound["config"]}
        for label, request, expected in (
                ("path", without_path, ("REJECTED", "SOURCE_REQUEST_REJECTED", "invalid_contract")),
                ("allowed roots", without_roots, ("UNSUPPORTED", "SOURCE_LAYOUT_UNSUPPORTED", "unsupported_config")),
                ("relative path", relative, ("REJECTED", "SOURCE_REQUEST_REJECTED", "unsafe_artifact_path"))):
            with self.subTest(missing=label):
                self.assertEqual(outcome(publish_alignment_evidence(**request)), expected)

    def test_binding_is_location_independent(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        copy = Path(temp.name).resolve() / "alignment_publication"
        shutil.copytree(PACK, copy)
        here, there = envelopes(), envelopes(copy)
        for name in CASE_ORDER:
            with self.subTest(case=name):
                self.assertEqual(here[name].to_json_bytes(), there[name].to_json_bytes())
                for root in (PACK, copy):
                    self.assertNotIn(str(root).encode(), here[name].to_json_bytes())
        for name, references in reference_sets().items():
            with self.subTest(set=name):
                self.assertEqual(handoff(here["available"], references).to_json_bytes(),
                                 handoff(there["available"], references).to_json_bytes())

    def test_publication_leaves_the_pack_unchanged(self):
        before = pack_digests()
        published = envelopes()
        for references in reference_sets().values():
            handoff(published["available"], references)
        self.assertEqual(pack_digests(), before)


class IntendedStatuses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.envelopes = envelopes()
        cls.sets = reference_sets()

    def test_the_four_request_cases_yield_the_four_intended_envelope_statuses(self):
        self.assertEqual(list(self.envelopes), CASE_ORDER)
        for name in CASE_ORDER:
            with self.subTest(case=name):
                self.assertEqual(outcome(self.envelopes[name]), EXPECTED[name])
        self.assertEqual(len({e.envelope_id for e in self.envelopes.values()}), 4)

    def test_the_two_reference_sets_yield_ready_and_blocked(self):
        available = self.envelopes["available"]
        ready, blocked = handoff(available, self.sets["ready"]), handoff(available, self.sets["blocked"])
        self.assertEqual((ready.status, ready.to_dict()["reason"]), ("READY", None))
        self.assertEqual((blocked.status, blocked.to_dict()["reason"]), ("BLOCKED", "REQUIRED_REFERENCE_ABSENT"))
        for record in (ready, blocked):
            verify_alignment_handoff(record, available)

    def test_blocked_absences_are_exactly_the_ids_the_source_does_not_declare(self):
        fields = self.envelopes["available"].to_dict()["source_fields"]
        declared = {entry["record_occurrence_id"] for entry in fields["/occurrence_mapping"]}
        self.assertTrue({r["component_id"] for r in self.sets["ready"]} <= declared)
        self.assertIn({"component_kind": "selected_occurrence",
                       "component_id": fields["/query"]["selected_occurrence"]}, self.sets["ready"])
        undeclared = {r["component_id"] for r in self.sets["blocked"]} - declared
        self.assertTrue(undeclared)
        references = handoff(self.envelopes["available"], self.sets["blocked"]).to_dict()["references"]
        self.assertEqual({r["component_id"] for r in references if r["resolution"] == "ABSENT"}, undeclared)

    def test_the_ready_set_on_the_unavailable_case_propagates_unavailable(self):
        record = handoff(self.envelopes["unavailable"], self.sets["ready"]).to_dict()
        self.assertEqual((record["status"], record["reason"]), ("UNAVAILABLE", "SOURCE_UNREADABLE"))
        self.assertEqual({r["resolution"] for r in record["references"]}, {"NOT_EVALUATED"})


if __name__ == "__main__":
    unittest.main()
