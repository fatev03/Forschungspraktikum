"""Synthetic contract tests for alignment_publication; source bytes are written to temporary directories.

No expected source value is written by hand: every one is read back from
parse_colabfold_a3m, the only reader the publication layer may use.
"""
import ast
from copy import deepcopy
import dataclasses
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from structure_audit import alignment_publication as publication
from structure_audit import colabfold_a3m_lossless as reader
from structure_audit.alignment_publication import (
    CARRIED_FIELDS, AlignmentEvidenceEnvelope, AlignmentHandoffRecord, AlignmentPublicationError,
    load_alignment_evidence_envelope, load_alignment_handoff_record, publish_alignment_evidence,
    publish_alignment_handoff, verify_alignment_handoff,
)
from structure_audit.colabfold_a3m_lossless import ColabFoldA3MError, parse_colabfold_a3m
from structure_audit.provenance import canonical_json, hash_config
from structure_audit.validation import validate_named

RAW = b"#opaque\n>r1 first\nxA.-cCggGx\n>r2 selected\nA-\nCG\n>r1 again\nA-CG\n>r3\nC-X-\n"
SELECTED = "record:1@header_line:4"
FIRST = "record:0@header_line:2"
MISSING = "record:9@header_line:99"
PRODUCER_FIELDS = ("name", "version", "database", "database_version", "search_settings")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def request(root, raw=RAW, *, write=True, selector=None, **config_changes):
    """A reader request for one synthetic source file; the declared hash covers the written bytes."""
    path = root / "source.a3m"
    if write:
        path.write_bytes(raw)
    artifact = {"artifact_id": "syn-alignment", "path": str(path), "sha256": sha(raw), "format": "a3m",
                "source_kind": "caller_declared_colabfold_mmseqs2_style_a3m",
                "source_kind_status": "caller_supplied_not_verified",
                "producer": {**dict.fromkeys(PRODUCER_FIELDS),
                             "missing_reasons": dict.fromkeys(PRODUCER_FIELDS, "not declared")},
                "provenance": {"details": None, "missing_reason": "not declared"}}
    config = {"profile_id": "colabfold_a3m_lossless_v1", "profile_version": "1.0",
              "profile_selection": "explicit_only", "allowed_input_roots": [str(root)],
              "expected_artifact_sha256": sha(raw),
              "query_selector": selector or {"record_occurrence_id": SELECTED},
              "canonical_query_sequence": "ACG", "canonical_query_sequence_sha256": sha(b"ACG"),
              "query_gap_policy": "preserve_and_map_to_null",
              "lowercase_x_policy": dict(reader.LOWERCASE_X_POLICY),
              "unknown_tokens": ["X"], "unknown_policy": "retain_as_unknown"}
    config.update(config_changes)
    return {"artifact": artifact, "config": config}


def resolve(document, pointer):
    for token in pointer.split("/")[1:]:
        document = document[token]
    return document


def leaves(node, kind):
    """Every string (kind=str) or number (kind=int) leaf of a JSON value."""
    if isinstance(node, dict):
        return [leaf for item in node.values() for leaf in leaves(item, kind)]
    if isinstance(node, list):
        return [leaf for item in node for leaf in leaves(item, kind)]
    if kind is str:
        return [node] if isinstance(node, str) else []
    return [node] if type(node) in (int, float) else []


def rehash(data, identity):
    data[identity] = hash_config({k: v for k, v in data.items() if k != identity})
    return data


def handoff_for(envelope, *ids, kind="record_occurrence"):
    return publish_alignment_handoff(
        envelope=envelope, expected_envelope_id=envelope.envelope_id,
        references=[{"component_kind": kind, "component_id": i} for i in ids])


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def publish(self, raw=RAW, **changes):
        return publish_alignment_evidence(**request(self.root, raw, **changes))

    def available(self):
        return self.publish()

    def refused(self, code, call, *args, **kwargs):
        with self.assertRaises(AlignmentPublicationError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        return caught.exception


class EvidencePublication(Base):
    def test_valid_evidence_publication(self):
        envelope = self.available()
        data = envelope.to_dict()
        validate_named(data, "alignment_evidence_envelope")
        self.assertEqual((data["status"], data["reason"], data["reader_diagnostic"]), ("AVAILABLE", None, None))
        declared = request(self.root)
        self.assertEqual(data["source"], {
            "artifact_id": "syn-alignment", "declared_sha256": sha(RAW),
            "declared_layout": {**{k: declared["artifact"][k] for k in ("format", "source_kind", "source_kind_status")},
                                **{k: declared["config"][k] for k in ("profile_id", "profile_version", "profile_selection")}}})
        self.assertEqual(data["reader"], publication.READER)
        self.assertEqual(sorted(data["source_fields"]), sorted(CARRIED_FIELDS))
        self.assertEqual(data["source_fields"]["/artifact/raw_sha256"], sha(RAW))

    def test_no_source_payload_is_invented_or_transformed(self):
        envelope = self.available().to_dict()
        source = parse_colabfold_a3m(**request(self.root)).to_dict()  # independent call, same public API
        for pointer in CARRIED_FIELDS:
            with self.subTest(pointer=pointer):
                self.assertEqual(canonical_json(envelope["source_fields"][pointer]),
                                 canonical_json(resolve(source, pointer)))
        declared = request(self.root)
        constants = ({publication.ENVELOPE_VERSION, "AVAILABLE"} | set(publication.READER.values())
                     | set(publication._ENVELOPE_RULES.values()) | {envelope["envelope_id"]})
        available = set(leaves(source, str)) | set(leaves(declared, str)) | constants
        self.assertEqual([s for s in leaves(envelope, str) if s not in available], [])
        self.assertTrue(set(leaves(envelope, int)) <= set(leaves(source, int)))

    def test_envelope_is_location_independent_and_carries_no_path(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        elsewhere = publish_alignment_evidence(**request(Path(other.name).resolve()))
        here = self.available()
        self.assertEqual(here.to_json_bytes(), elsewhere.to_json_bytes())
        self.assertNotIn(str(self.root).encode(), here.to_json_bytes())
        for pointer in ("/artifact/snapshot/path", "/configuration/allowed_input_roots",
                        "/contract_hashes", "/artifact/raw_bytes_base64"):
            self.assertNotIn(pointer, here.to_dict()["source_fields"])

    def test_repeated_publication_is_byte_identical(self):
        self.assertEqual(self.available().to_json_bytes(), self.available().to_json_bytes())

    def test_malformed_request_is_refused_before_the_reader_runs(self):
        def drop(key):
            return lambda r: r["artifact"].pop(key)
        cases = (("artifact_id", drop("artifact_id")), ("sha256", drop("sha256")),
                 ("short sha256", lambda r: r["artifact"].update(sha256="ab")),
                 ("layout type", lambda r: r["artifact"].update(format=3)),
                 ("profile", lambda r: r["config"].pop("profile_id")),
                 ("metrics", lambda r: r["config"].update(metrics_enabled=True)),
                 ("binding", lambda r: r["config"].update(binding_enabled=True)),
                 ("metric policy", lambda r: r["config"].update(metric_policy={"any": 1})),
                 ("truthy gate", lambda r: r["config"].update(metrics_enabled=0)))
        with patch.object(publication, "parse_colabfold_a3m", side_effect=AssertionError("reader called")):
            for label, mutate in cases:
                with self.subTest(label=label):
                    args = request(self.root)
                    mutate(args)
                    self.refused("CONTRACT_INVALID", publish_alignment_evidence, **args)
            self.refused("CONTRACT_INVALID", publish_alignment_evidence, artifact=[], config={})


class Propagation(Base):
    def assert_status(self, envelope, status, reason, code):
        data = envelope.to_dict()
        validate_named(data, "alignment_evidence_envelope")
        self.assertEqual((data["status"], data["reason"], data["reader_diagnostic"]["code"]),
                         (status, reason, code))
        self.assertIsNone(data["source_fields"])
        self.assertNotIn(str(self.root).encode(), envelope.to_json_bytes())
        return data

    def test_unavailable_source_is_propagated(self):
        self.assert_status(self.publish(write=False), "UNAVAILABLE", "SOURCE_UNREADABLE", "artifact_read_error")

    def test_unsupported_layout_is_propagated(self):
        data = self.assert_status(self.publish(profile_version="2.0"), "UNSUPPORTED",
                                  "SOURCE_LAYOUT_UNSUPPORTED", "profile_mismatch")
        self.assertEqual(data["source"]["declared_layout"]["profile_version"], "2.0")
        token = self.publish(b">r1\nA-CG\n>r2\nZ-CG\n", selector={"header_line": 1, "raw_header": ">r1"})
        data = self.assert_status(token, "UNSUPPORTED", "SOURCE_LAYOUT_UNSUPPORTED", "unsupported_token")
        self.assertEqual(data["reader_diagnostic"]["details"], {"token": "Z"})

    def test_malformed_source_is_rejected(self):
        selector = {"header_line": 1, "raw_header": ">r1"}
        for raw, code in ((b">r1\nA-CG\n\n>r2\nA-CG\n", "alignment_parse_error"),
                          (b">r1\nA-CG\n>r2\nA-C\n", "ragged_rows")):
            with self.subTest(code=code):
                self.assert_status(self.publish(raw, selector=selector), "REJECTED", "SOURCE_MALFORMED", code)

    def test_artifact_byte_hash_mismatch_is_rejected(self):
        args = request(self.root)
        (self.root / "source.a3m").write_bytes(RAW.replace(b"C-X-", b"C-A-"))
        data = self.assert_status(publish_alignment_evidence(**args), "REJECTED",
                                  "SOURCE_CONTENT_HASH_MISMATCH", "artifact_hash_mismatch")
        self.assertEqual(data["source"]["declared_sha256"], sha(RAW))
        declared = request(self.root)
        declared["config"]["expected_artifact_sha256"] = "0" * 64
        self.assert_status(publish_alignment_evidence(**declared), "REJECTED",
                           "SOURCE_CONTENT_HASH_MISMATCH", "artifact_hash_mismatch")

    def test_selection_identity_mismatch_is_rejected(self):
        self.assert_status(self.publish(selector={"record_occurrence_id": "record:2@header_line:4"}),
                           "REJECTED", "SOURCE_SELECTION_REJECTED", "malformed_occurrence_identity")

    def test_the_four_statuses_stay_distinct(self):
        envelopes = (self.available(), self.publish(profile_version="2.0"),
                     self.publish(selector={"record_occurrence_id": "record:2@header_line:4"}))
        missing = tempfile.TemporaryDirectory()
        self.addCleanup(missing.cleanup)
        envelopes += (publish_alignment_evidence(**request(Path(missing.name).resolve(), write=False)),)
        self.assertEqual([e.status for e in envelopes], ["AVAILABLE", "UNSUPPORTED", "REJECTED", "UNAVAILABLE"])
        self.assertEqual(len({e.envelope_id for e in envelopes}), 4)

    def test_every_reader_code_is_classified_and_unknown_codes_fail_closed(self):
        tree = ast.parse(Path(reader.__file__).read_text(encoding="utf-8"))
        codes = set()

        def constants(node):
            return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and type(n.value) is str}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and node.args and (
                    (isinstance(node.func, ast.Attribute) and node.func.attr == "fail")
                    or (isinstance(node.func, ast.Name) and node.func.id == "ColabFoldA3MError")):
                codes |= constants(node.args[0])
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    names = target.elts if isinstance(target, ast.Tuple) else [target]
                    values = node.value.elts if isinstance(node.value, ast.Tuple) else [node.value]
                    for name, value in zip(names, values):
                        if ((isinstance(name, ast.Attribute) and name.attr == "phase")
                                or (isinstance(name, ast.Name) and name.id == "code")):
                            codes |= constants(value)
        self.assertEqual(codes, set(publication._READER_CODES))
        with patch.object(publication, "parse_colabfold_a3m",
                          side_effect=ColabFoldA3MError("a_future_code", "not classified")):
            envelope = self.publish()
        self.assertEqual((envelope.status, envelope.reason), ("REJECTED", "READER_CODE_UNRECOGNIZED"))

    def test_schemas_agree_with_the_module_constants(self):
        root = Path(publication.__file__).parent / "schemas"
        envelope = json.loads((root / "alignment_evidence_envelope.schema.json").read_text())
        handoff = json.loads((root / "alignment_handoff_record.schema.json").read_text())
        self.assertEqual(envelope["properties"]["source_fields"]["required"], list(CARRIED_FIELDS))
        reasons = {r for _, r in publication._READER_CODES.values()} | {"READER_CODE_UNRECOGNIZED"}
        self.assertEqual(set(envelope["properties"]["reason"]["enum"]), {None} | reasons)
        self.assertEqual(set(handoff["properties"]["reason"]["enum"]), {None, "REQUIRED_REFERENCE_ABSENT"} | reasons)


class HandoffPublication(Base):
    def test_valid_handoff_publication(self):
        envelope = self.available()
        handoff = publish_alignment_handoff(
            envelope=envelope, expected_envelope_id=envelope.envelope_id,
            references=[{"component_kind": "selected_occurrence", "component_id": SELECTED},
                        {"component_kind": "record_occurrence", "component_id": FIRST}])
        data = handoff.to_dict()
        validate_named(data, "alignment_handoff_record")
        self.assertEqual((data["status"], data["reason"], data["envelope_id"]), ("READY", None, envelope.envelope_id))
        mapping = {e["record_occurrence_id"]: e for e in parse_colabfold_a3m(**request(self.root)).to_dict()["occurrence_mapping"]}
        self.assertEqual(data["references"], [
            {"component_kind": "record_occurrence", "component_id": FIRST, "resolution": "PRESENT",
             "source_locator": mapping[FIRST]},
            {"component_kind": "selected_occurrence", "component_id": SELECTED, "resolution": "PRESENT",
             "source_locator": mapping[SELECTED]}])
        verify_alignment_handoff(handoff, envelope)

    def test_blocked_handoff_when_required_references_are_absent(self):
        envelope = self.available()
        for handoff in (handoff_for(envelope, FIRST, MISSING),
                        handoff_for(envelope, FIRST, kind="selected_occurrence")):
            with self.subTest(references=[r["component_id"] for r in handoff.to_dict()["references"]]):
                data = handoff.to_dict()
                self.assertEqual((data["status"], data["reason"]), ("BLOCKED", "REQUIRED_REFERENCE_ABSENT"))
                absent = [r for r in data["references"] if r["resolution"] == "ABSENT"]
                self.assertEqual(len(absent), 1)
                self.assertIsNone(absent[0]["source_locator"])
                verify_alignment_handoff(handoff, envelope)

    def test_unavailable_unsupported_rejected_propagate_to_the_handoff(self):
        missing = tempfile.TemporaryDirectory()
        self.addCleanup(missing.cleanup)
        for envelope in (publish_alignment_evidence(**request(Path(missing.name).resolve(), write=False)),
                         self.publish(profile_version="2.0"),
                         self.publish(selector={"record_occurrence_id": "record:2@header_line:4"})):
            with self.subTest(status=envelope.status):
                data = handoff_for(envelope, SELECTED).to_dict()
                self.assertEqual((data["status"], data["reason"]), (envelope.status, envelope.reason))
                self.assertEqual([(r["resolution"], r["source_locator"]) for r in data["references"]],
                                 [("NOT_EVALUATED", None)])

    def test_identity_mismatch_is_refused(self):
        envelope, other = self.available(), self.publish(profile_version="2.0")
        self.refused("IDENTITY_MISMATCH", publish_alignment_handoff, envelope=envelope,
                     expected_envelope_id=other.envelope_id,
                     references=[{"component_kind": "record_occurrence", "component_id": FIRST}])
        self.refused("IDENTITY_MISMATCH", verify_alignment_handoff, handoff_for(envelope, FIRST), other)

    def test_malformed_references_are_refused(self):
        envelope = self.available()
        ref = {"component_kind": "record_occurrence", "component_id": FIRST}
        for label, references in (("empty", []), ("not a list", ref), ("duplicate", [ref, dict(ref)]),
                                  ("unknown kind", [dict(ref, component_kind="other_component")]),
                                  ("extra field", [dict(ref, required=True)]),
                                  ("empty id", [dict(ref, component_id=" ")])):
            with self.subTest(label=label):
                self.refused("CONTRACT_INVALID", publish_alignment_handoff, envelope=envelope,
                             expected_envelope_id=envelope.envelope_id, references=references)
        self.refused("CONTRACT_INVALID", publish_alignment_handoff, envelope=envelope.to_dict(),
                     expected_envelope_id=envelope.envelope_id, references=[ref])

    def test_reference_order_does_not_change_identity(self):
        envelope = self.available()
        self.assertEqual(handoff_for(envelope, FIRST, SELECTED).to_json_bytes(),
                         handoff_for(envelope, SELECTED, FIRST).to_json_bytes())

    def test_the_handoff_carries_no_other_source_payload(self):
        envelope = self.available()
        handoff = handoff_for(envelope, FIRST, MISSING).to_dict()
        mapping = parse_colabfold_a3m(**request(self.root)).to_dict()["occurrence_mapping"]
        available = (set(leaves(mapping, str)) | {FIRST, MISSING, envelope.envelope_id, handoff["handoff_id"]}
                     | {publication.HANDOFF_VERSION, "BLOCKED", "REQUIRED_REFERENCE_ABSENT", "PRESENT",
                        "ABSENT", "record_occurrence"} | set(publication._HANDOFF_RULES.values()))
        self.assertEqual([s for s in leaves(handoff, str) if s not in available], [])
        self.assertTrue(set(leaves(handoff, int)) <= set(leaves(mapping, int)))


class Serialization(Base):
    def documents(self):
        envelope = self.available()
        missing = tempfile.TemporaryDirectory()
        self.addCleanup(missing.cleanup)
        unavailable = publish_alignment_evidence(**request(Path(missing.name).resolve(), write=False))
        return {"envelope AVAILABLE": envelope, "envelope UNAVAILABLE": unavailable,
                "envelope UNSUPPORTED": self.publish(profile_version="2.0"),
                "envelope REJECTED": self.publish(selector={"record_occurrence_id": "record:2@header_line:4"}),
                "handoff READY": handoff_for(envelope, FIRST),
                "handoff BLOCKED": handoff_for(envelope, MISSING),
                "handoff UNAVAILABLE": handoff_for(unavailable, FIRST)}

    def test_canonical_export_reload_reserialize_is_stable(self):
        for label, document in self.documents().items():
            with self.subTest(label=label):
                loader = (load_alignment_evidence_envelope if isinstance(document, AlignmentEvidenceEnvelope)
                          else load_alignment_handoff_record)
                path = self.root / "export.json"
                path.write_bytes(document.to_json_bytes())
                back = loader(path)
                self.assertEqual(back.to_json_bytes(), document.to_json_bytes())
                self.assertEqual(back, document)
                path.write_bytes(back.to_json_bytes())
                self.assertEqual(loader(path).to_json_bytes(), document.to_json_bytes())

    def test_loaders_refuse_malformed_documents(self):
        for raw in (b'{"schema_version": "value_flow_envelope/1"}', b'{"a": 1, "a": 2}',
                    b'{"a": NaN}', b"\xff\xfe", b"[]"):
            with self.subTest(raw=raw):
                path = self.root / "bad.json"
                path.write_bytes(raw)
                self.refused("ENVELOPE_INVALID", load_alignment_evidence_envelope, path)
                self.refused("HANDOFF_INVALID", load_alignment_handoff_record, path)

    def test_non_canonical_bytes_are_refused_by_the_constructor(self):
        envelope = self.available()
        pretty = json.dumps(envelope.to_dict(), indent=1).encode()
        self.refused("ENVELOPE_INVALID", AlignmentEvidenceEnvelope, pretty)
        self.assertEqual(AlignmentEvidenceEnvelope.from_dict(json.loads(pretty)), envelope)


class Tampering(Base):
    def tampered(self, cls, code, document, mutate, identity=None):
        data = document.to_dict()
        mutate(data)
        if identity:
            rehash(data, identity)
        self.refused(code, cls.from_dict, data)

    def test_envelope_tamper_rejection_for_every_material_field(self):
        envelope = self.available()
        first_fragment = lambda d: d["source_fields"]["/records"][0]["sequence_fragments"][0]
        cases = (
            ("envelope_id", lambda d: d.update(envelope_id="0" * 64)),
            ("status", lambda d: d.update(status="REJECTED")),
            ("artifact_id", lambda d: d["source"].update(artifact_id="other")),
            ("declared_sha256", lambda d: d["source"].update(declared_sha256="0" * 64)),
            ("declared layout", lambda d: d["source"]["declared_layout"].update(profile_version="2.0")),
            ("reader", lambda d: d["reader"].update(entry_point="other")),
            ("content hash", lambda d: d["source_fields"].update({"/artifact/raw_sha256": "0" * 64})),
            ("fragment", lambda d: first_fragment(d).update(raw_fragment_bytes_base64="QUFB")),
            ("locator", lambda d: d["source_fields"]["/occurrence_mapping"][0].update(header_line=7)),
            ("extra field", lambda d: d["source_fields"].update({"/artifact/snapshot/path": "/x"})),
            ("rules", lambda d: d["rules"].update(arithmetic="derived")),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                self.tampered(AlignmentEvidenceEnvelope, "ENVELOPE_INVALID", envelope, mutate)

    def test_consistently_rehashed_envelope_edits_are_still_refused(self):
        envelope, rejected = self.available(), self.publish(selector={"record_occurrence_id": "record:2@header_line:4"})
        fragment = lambda d: d["source_fields"]["/records"][0]["sequence_fragments"][0]

        def all_hashes(d):
            forged = sha(b"forged")
            d["source"]["declared_sha256"] = forged
            d["source_fields"].update({"/artifact/raw_sha256": forged, "/reconstructed_sha256": forged})
        cases = (
            ("relabel AVAILABLE", envelope, lambda d: d.update(status="REJECTED", reason="SOURCE_MALFORMED")),
            ("relabel REJECTED", rejected, lambda d: d.update(status="UNSUPPORTED", reason="SOURCE_LAYOUT_UNSUPPORTED")),
            ("fragment bytes", envelope, lambda d: fragment(d).update(raw_fragment_bytes_base64="eEEuLWNDZ2dHeQo=")),
            ("declared hash", envelope, lambda d: d["source"].update(declared_sha256=sha(b"other"))),
            ("every hash", envelope, all_hashes),
            ("artifact id", envelope, lambda d: d["source"].update(artifact_id="other")),
            ("size", envelope, lambda d: d["source_fields"].update({"/artifact/size_bytes": 1})),
        )
        for label, document, mutate in cases:
            with self.subTest(label=label):
                self.tampered(AlignmentEvidenceEnvelope, "ENVELOPE_INVALID", document, mutate, "envelope_id")

    def test_a_rehashed_envelope_is_a_different_identity(self):
        envelope = self.available()
        data = envelope.to_dict()
        data["source_fields"]["/occurrence_mapping"][0]["header_line"] = 7
        forged = AlignmentEvidenceEnvelope.from_dict(rehash(data, "envelope_id"))
        self.assertNotEqual(forged.envelope_id, envelope.envelope_id)
        self.refused("IDENTITY_MISMATCH", publish_alignment_handoff, envelope=forged,
                     expected_envelope_id=envelope.envelope_id,
                     references=[{"component_kind": "record_occurrence", "component_id": FIRST}])

    def test_handoff_tamper_rejection_for_every_material_field(self):
        envelope = self.available()
        handoff = handoff_for(envelope, FIRST, MISSING)
        cases = (
            ("handoff_id", lambda d: d.update(handoff_id="0" * 64), None),
            ("status", lambda d: d.update(status="READY", reason=None), "handoff_id"),
            ("resolution", lambda d: d["references"][1].update(resolution="PRESENT"), "handoff_id"),
            ("locator identity", lambda d: d["references"][0]["source_locator"].update(record_occurrence_id=SELECTED), "handoff_id"),
            ("reason", lambda d: d.update(reason="SOURCE_MALFORMED"), "handoff_id"),
            ("order", lambda d: d["references"].reverse(), "handoff_id"),
            ("empty references", lambda d: d.update(references=[]), "handoff_id"),
            ("rules", lambda d: d["rules"].update(payload="any"), "handoff_id"),
        )
        for label, mutate, identity in cases:
            with self.subTest(label=label):
                self.tampered(AlignmentHandoffRecord, "HANDOFF_INVALID", handoff, mutate, identity)

    def test_rehashed_handoff_edits_fail_re_derivation(self):
        envelope = self.available()
        data = handoff_for(envelope, FIRST).to_dict()
        data["references"][0]["source_locator"]["header_line"] = 7
        forged = AlignmentHandoffRecord.from_dict(rehash(data, "handoff_id"))
        self.refused("HANDOFF_INVALID", verify_alignment_handoff, forged, envelope)
        data = handoff_for(envelope, FIRST).to_dict()
        data["envelope_id"] = "1" * 64
        self.refused("IDENTITY_MISMATCH", verify_alignment_handoff,
                     AlignmentHandoffRecord.from_dict(rehash(data, "handoff_id")), envelope)


class Immutability(Base):
    def test_result_objects_are_frozen_and_hold_only_canonical_bytes(self):
        envelope = self.available()
        handoff = handoff_for(envelope, FIRST)
        for document in (envelope, handoff):
            with self.subTest(type=type(document).__name__):
                self.assertEqual([f.name for f in dataclasses.fields(document)], ["json_bytes"])
                self.assertIs(type(document.json_bytes), bytes)
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    document.json_bytes = b"{}"
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    del document.json_bytes

    def test_defensive_copies_on_every_read(self):
        envelope = self.available()
        snapshot = envelope.to_json_bytes()
        first = envelope.to_dict()
        first["status"] = "REJECTED"
        first["source_fields"]["/records"].clear()
        first["source"]["artifact_id"] = "other"
        self.assertEqual(envelope.to_json_bytes(), snapshot)
        self.assertEqual(envelope.status, "AVAILABLE")
        self.assertIsNot(envelope.to_dict(), envelope.to_dict())
        self.assertIsNot(envelope.to_dict()["source_fields"], envelope.to_dict()["source_fields"])

    def test_mutating_the_inputs_cannot_reach_a_published_document(self):
        args = request(self.root)
        envelope = publish_alignment_evidence(**args)
        snapshot = envelope.to_json_bytes()
        args["artifact"]["artifact_id"] = "other"
        args["config"]["profile_version"] = "2.0"
        references = [{"component_kind": "record_occurrence", "component_id": FIRST}]
        handoff = publish_alignment_handoff(envelope=envelope, expected_envelope_id=envelope.envelope_id,
                                            references=references)
        before = handoff.to_json_bytes()
        references[0]["component_id"] = MISSING
        self.assertEqual(envelope.to_json_bytes(), snapshot)
        self.assertEqual(handoff.to_json_bytes(), before)


if __name__ == "__main__":
    unittest.main()
