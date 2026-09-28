"""Contract tests for ``caller_pose_association/1``.

The module under test is loaded directly from its file so that no package
initializer runs and no project module is imported on its behalf; the isolation
test then reflects the module's own import list and nothing else.

Run: python -m unittest tests.test_caller_pose_association -v
"""
from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT_DIR / "files"
MODULE_NAME = "caller_pose_association"
MODULE_PATH = PACKAGE_DIR / (MODULE_NAME + ".py")


def _load_module():
    spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    # Registered before execution so dataclasses can resolve this module's own
    # postponed annotations; no package initializer is involved either way.
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


cpa = _load_module()

Error = cpa.CallerPoseAssociationError

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
STAMP = "2026-09-28T09:15:00Z"


def canon(value):
    """The same canonical spelling the module emits."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


# --------------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------------


def reference(identifier="ref-1", revision="rev-1", snapshot=None, namespace="ns"):
    return cpa.ImmutableReference(
        namespace=namespace,
        identifier=identifier,
        revision=revision,
        snapshot_reference=snapshot,
    )


def hash_anchor(digest=DIGEST_A):
    return cpa.ArtifactAnchor(
        kind="CONTENT_HASH", algorithm="sha256", digest=digest, snapshot_reference=None
    )


def snapshot_anchor():
    return cpa.ArtifactAnchor(
        kind="IMMUTABLE_SNAPSHOT",
        algorithm=None,
        digest=None,
        snapshot_reference=reference("snap-1", None, "snapshot-token"),
    )


def scope(anchor=None, model_id="model-1"):
    return cpa.ArtifactModelScope(
        artifact_anchor=hash_anchor() if anchor is None else anchor, model_id=model_id
    )


def subset(text="1-40"):
    return cpa.SubsetDeclaration(declaration=text, reference=reference("subset-src"))


def chain_entry(namespace="auth", chain_id="A", instance_id="1", with_subset=True):
    return cpa.ChainEntry(
        identifier_namespace=namespace,
        chain_id=chain_id,
        instance_id=instance_id,
        residue_subset=subset() if with_subset else None,
    )


def chain_instance(namespace="auth", chain_id="A", instance_id="1"):
    return cpa.ChainInstance(
        identifier_namespace=namespace, chain_id=chain_id, instance_id=instance_id
    )


def chain_value(entries=None, value_scope=None):
    return cpa.ChainMappingValue(
        scope=scope() if value_scope is None else value_scope,
        chains=(chain_entry(),) if entries is None else tuple(entries),
    )


def residue_value(value_scope=None, scheme="scheme-1", instances=None):
    return cpa.ResidueAddressingValue(
        scope=scope() if value_scope is None else value_scope,
        chain_instances=(chain_instance(),) if instances is None else tuple(instances),
        scheme=scheme,
        namespace="residue-ns",
        residue_identifier_convention="convention-1",
        insertion_code_convention="none-declared",
        residue_subset=subset("10-20"),
        external_mapping=cpa.ExternalMapping(
            reference=reference("mapping-src"), direction="left-to-right"
        ),
    )


def chain_mapping(state="SUPPLIED", values=None, sources=None):
    values = (chain_value(),) if values is None else tuple(values)
    sources = (None,) * len(values) if sources is None else tuple(sources)
    return cpa.ChainMapping(
        state=state,
        alternatives=tuple(
            cpa.ChainMappingAlternative(value=item, source_reference=source)
            for item, source in zip(values, sources)
        ),
    )


def residue_addressing(state="SUPPLIED", values=None):
    values = (residue_value(),) if values is None else tuple(values)
    return cpa.ResidueAddressing(
        state=state,
        alternatives=tuple(
            cpa.ResidueAddressingAlternative(value=item, source_reference=None)
            for item in values
        ),
    )


def participant(
    participant_id="p1",
    role="BINDER",
    identity=True,
    construct=True,
    mapping=None,
    addressing=None,
):
    return cpa.Participant(
        participant_id=participant_id,
        role=role,
        identity_reference=reference("identity-" + participant_id) if identity else None,
        construct_id="construct-" + participant_id if construct else None,
        construct_version="v1" if construct else None,
        chain_mapping=chain_mapping() if mapping is None else mapping,
        residue_addressing=residue_addressing() if addressing is None else addressing,
    )


def conflict(conflict_id="c1", field_paths=("/participants/0/role",)):
    return cpa.AssociationConflict(
        conflict_id=conflict_id,
        scope=cpa.ArtifactModelScope(artifact_anchor=snapshot_anchor(), model_id=None),
        association_references=(
            cpa.AssociationReference(
                association_id="assoc-a",
                revision="r1",
                document_reference=reference("doc-a"),
            ),
            cpa.AssociationReference(
                association_id="assoc-b",
                revision="r2",
                document_reference=reference("doc-b"),
            ),
        ),
        field_paths=tuple(field_paths),
        statement="declared incompatibility",
        declared_by="party-1",
        declared_at=STAMP,
        source_references=(reference("conflict-src"),),
    )


def complete_document(conflicts=(), **overrides):
    payload = dict(
        association_id="assoc-1",
        revision="rev-a",
        declared_by="party-1",
        declared_at=STAMP,
        artifact=cpa.Artifact(
            anchor=hash_anchor(), locator="opaque-locator", selected_model="model-1"
        ),
        provenance=cpa.Provenance(
            source_reference=reference("source"),
            run_reference=reference("run"),
            method_reference=reference("method"),
        ),
        participants=(
            participant("p1", "BINDER"),
            participant("p2", "RECEPTOR"),
        ),
        pose_pair=cpa.PosePair(
            binder_participant_id="p1", receptor_participant_id="p2"
        ),
        joint_frame=cpa.JointFrame(
            frame_id="frame-1",
            frame_kind="CALLER_DECLARED_ARTIFACT_MODEL_FRAME",
            scope=scope(),
        ),
        conditions_profile=cpa.ConditionsProfile(
            state="SUPPLIED", reference=reference("profile"), reason=None
        ),
        association_conflicts=tuple(conflicts),
    )
    payload.update(overrides)
    return cpa.CallerPoseAssociation(**payload)


def limited_document():
    """One serializable document exercising every non-refusal diagnostic code."""
    matching = scope(model_id=None)
    mismatching = scope(model_id="other-model")

    p1 = cpa.Participant(
        participant_id="p1",
        role="LIGAND",
        identity_reference=None,
        construct_id=None,
        construct_version=None,
        chain_mapping=chain_mapping(
            "SUPPLIED", values=(chain_value(entries=(), value_scope=mismatching),)
        ),
        residue_addressing=cpa.ResidueAddressing(state="ABSENT", alternatives=()),
    )
    p2 = cpa.Participant(
        participant_id="p2",
        role="LIGAND",
        identity_reference=reference("identity-p2"),
        construct_id="construct-p2",
        construct_version="v1",
        chain_mapping=cpa.ChainMapping(state="ABSENT", alternatives=()),
        residue_addressing=residue_addressing(
            "AMBIGUOUS",
            values=(
                residue_value(value_scope=matching),
                residue_value(
                    value_scope=matching, instances=(chain_instance(chain_id="B"),)
                ),
            ),
        ),
    )
    p3 = cpa.Participant(
        participant_id="p3",
        role=None,
        identity_reference=reference("identity-p3"),
        construct_id="construct-p3",
        construct_version="v1",
        chain_mapping=chain_mapping(
            "AMBIGUOUS",
            values=(
                chain_value(value_scope=matching),
                chain_value(
                    entries=(chain_entry(chain_id="B"),), value_scope=matching
                ),
            ),
        ),
        residue_addressing=residue_addressing(
            "SUPPLIED", values=(residue_value(value_scope=matching, scheme=None),)
        ),
    )
    return cpa.CallerPoseAssociation(
        association_id="assoc-limited",
        revision="rev-a",
        declared_by="party-1",
        declared_at=STAMP,
        artifact=cpa.Artifact(anchor=hash_anchor(), locator=None, selected_model=None),
        provenance=cpa.Provenance(
            source_reference=None, run_reference=None, method_reference=None
        ),
        participants=(p1, p2, p3),
        pose_pair=cpa.PosePair(
            binder_participant_id="p1", receptor_participant_id=None
        ),
        joint_frame=None,
        conditions_profile=cpa.ConditionsProfile(
            state="UNAVAILABLE", reference=None, reason="not supplied by the caller"
        ),
        association_conflicts=(conflict("c1"), conflict("c2")),
    )


def codes(document):
    return [item.code for item in document.diagnostics]


def diagnostic(document, code):
    for item in document.diagnostics:
        if item.code == code:
            return item
    raise AssertionError("diagnostic {0} was not emitted".format(code))


# --------------------------------------------------------------------------------
# 1. Fully populated valid document
# --------------------------------------------------------------------------------


class FullyPopulatedDocument(unittest.TestCase):
    def test_a_complete_document_carries_no_diagnostic(self):
        document = complete_document()
        self.assertEqual(document.diagnostics, ())

    def test_every_nested_record_form_round_trips(self):
        document = complete_document(conflicts=(conflict(),))
        self.assertEqual(codes(document), ["ARTIFACT_ASSOCIATION_CONFLICT"])

        payload = document.as_dict()
        self.assertEqual(payload["document_type"], "caller_pose_association/1")
        self.assertEqual(payload["non_claim"], cpa.NON_CLAIM)
        self.assertEqual(
            list(payload),
            [
                "document_type",
                "association_id",
                "revision",
                "declared_by",
                "declared_at",
                "artifact",
                "provenance",
                "participants",
                "pose_pair",
                "joint_frame",
                "conditions_profile",
                "association_conflicts",
                "diagnostics",
                "non_claim",
            ],
        )
        self.assertEqual(
            payload["association_conflicts"][0]["scope"]["artifact_anchor"]["kind"],
            "IMMUTABLE_SNAPSHOT",
        )
        self.assertEqual(payload["artifact"]["anchor"]["kind"], "CONTENT_HASH")
        self.assertIsNotNone(
            payload["participants"][0]["residue_addressing"]["alternatives"][0]["value"][
                "external_mapping"
            ]
        )

        reloaded = cpa.CallerPoseAssociation.from_json_bytes(document.to_json_bytes())
        self.assertEqual(reloaded, document)
        self.assertEqual(reloaded.to_json_bytes(), document.to_json_bytes())

    def test_fixed_strings_are_emitted_verbatim(self):
        text = complete_document().to_json_bytes().decode("utf-8")
        self.assertIn('"document_type":"caller_pose_association/1"', text)
        self.assertIn(cpa.NON_CLAIM, text)


# --------------------------------------------------------------------------------
# 2. Serializable limited document: every diagnostic category and every ordering
# --------------------------------------------------------------------------------


class LimitedDocumentDiagnostics(unittest.TestCase):
    def setUp(self):
        self.document = limited_document()

    def test_every_non_refusal_code_is_emitted_in_frozen_order(self):
        expected = [
            "PARTICIPANT_ROLE_MISSING",
            "PARTICIPANT_CHAIN_MISSING",
            "DUPLICATE_PARTICIPANT_ROLE",
            "SHARED_FRAME_MISSING",
            "SHARED_FRAME_MISMATCH",
            "CHAIN_MAPPING_ABSENT",
            "CHAIN_MAPPING_AMBIGUOUS",
            "RESIDUE_ADDRESSING_ABSENT",
            "RESIDUE_ADDRESSING_AMBIGUOUS",
            "MODEL_RUN_METHOD_REFERENCE_ABSENT",
            "CONDITION_PROFILE_UNAVAILABLE",
            "ARTIFACT_ASSOCIATION_CONFLICT",
            "DECLARATION_MISSING",
            "DECLARATION_INCONSISTENT",
        ]
        self.assertEqual(codes(self.document), expected)
        self.assertEqual(
            set(cpa.DIAGNOSTIC_CODES) - set(expected),
            {cpa.REFUSAL_ONLY_DIAGNOSTIC_CODE},
        )

    def test_at_most_one_diagnostic_per_code(self):
        emitted = codes(self.document)
        self.assertEqual(len(emitted), len(set(emitted)))

    def test_field_paths_are_lexically_sorted_and_de_duplicated(self):
        for item in self.document.diagnostics:
            paths = list(item.field_paths)
            self.assertTrue(paths, item.code)
            self.assertEqual(paths, sorted(paths), item.code)
            self.assertEqual(len(paths), len(set(paths)), item.code)

    def test_a_repeated_location_is_emitted_once(self):
        # BINDER and RECEPTOR are both absent; both add "/participants".
        item = diagnostic(self.document, "PARTICIPANT_ROLE_MISSING")
        self.assertEqual(
            list(item.field_paths), ["/participants", "/participants/2/role"]
        )
        self.assertEqual(list(item.participant_ids), ["p3"])

    def test_a_repeated_participant_is_emitted_once_in_source_order(self):
        item = diagnostic(self.document, "DECLARATION_MISSING")
        self.assertEqual(
            list(item.field_paths),
            [
                "/artifact/locator",
                "/participants/0/construct_id",
                "/participants/0/construct_version",
                "/participants/0/identity_reference",
                "/pose_pair/receptor_participant_id",
                "/provenance/source_reference",
            ],
        )
        self.assertEqual(list(item.participant_ids), ["p1"])

    def test_participant_identifiers_retain_participants_array_order(self):
        order = [item.participant_id for item in self.document.participants]
        for item in self.document.diagnostics:
            listed = list(item.participant_ids)
            self.assertEqual(len(listed), len(set(listed)), item.code)
            self.assertEqual(
                listed, [name for name in order if name in listed], item.code
            )
        self.assertEqual(
            list(diagnostic(self.document, "RESIDUE_ADDRESSING_ABSENT").participant_ids),
            ["p1", "p3"],
        )

    def test_conflict_identifiers_retain_conflicts_array_order(self):
        item = diagnostic(self.document, "ARTIFACT_ASSOCIATION_CONFLICT")
        self.assertEqual(
            list(item.field_paths), ["/association_conflicts/0", "/association_conflicts/1"]
        )
        self.assertEqual(list(item.conflict_ids), ["c1", "c2"])
        self.assertEqual(list(item.participant_ids), [])

    def test_specific_locations_are_exact(self):
        self.assertEqual(
            list(diagnostic(self.document, "PARTICIPANT_CHAIN_MISSING").field_paths),
            ["/participants/0/chain_mapping/alternatives/0/value/chains"],
        )
        self.assertEqual(
            list(diagnostic(self.document, "SHARED_FRAME_MISMATCH").field_paths),
            ["/participants/0/chain_mapping/alternatives/0/value/scope"],
        )
        self.assertEqual(
            list(diagnostic(self.document, "SHARED_FRAME_MISSING").field_paths),
            ["/joint_frame"],
        )
        self.assertEqual(
            list(diagnostic(self.document, "DUPLICATE_PARTICIPANT_ROLE").field_paths),
            ["/participants/0/role", "/participants/1/role"],
        )
        self.assertEqual(
            list(
                diagnostic(
                    self.document, "MODEL_RUN_METHOD_REFERENCE_ABSENT"
                ).field_paths
            ),
            [
                "/artifact/selected_model",
                "/provenance/method_reference",
                "/provenance/run_reference",
            ],
        )
        self.assertEqual(
            list(diagnostic(self.document, "RESIDUE_ADDRESSING_ABSENT").field_paths),
            [
                "/participants/0/residue_addressing",
                "/participants/2/residue_addressing/alternatives/0/value/scheme",
            ],
        )
        self.assertEqual(
            list(diagnostic(self.document, "DECLARATION_INCONSISTENT").field_paths),
            ["/pose_pair/binder_participant_id"],
        )

    def test_the_limited_document_round_trips(self):
        data = self.document.to_json_bytes()
        self.assertEqual(cpa.CallerPoseAssociation.from_json_bytes(data), self.document)


# --------------------------------------------------------------------------------
# 3. Issuance-blocking refusals
# --------------------------------------------------------------------------------


class IssuanceBlockingRefusals(unittest.TestCase):
    def setUp(self):
        self.payload = complete_document(conflicts=(conflict(),)).as_dict()

    def load(self, payload):
        return cpa.CallerPoseAssociation.from_json_bytes(canon(payload))

    def mutated(self, mutate):
        payload = copy.deepcopy(self.payload)
        mutate(payload)
        return payload

    def test_the_baseline_payload_loads(self):
        self.assertIsNotNone(self.load(self.payload))

    def test_missing_anchor_is_a_refusal_naming_the_refusal_diagnostic(self):
        def drop(payload):
            payload["artifact"]["anchor"] = None

        with self.assertRaises(Error) as caught:
            self.load(self.mutated(drop))
        self.assertEqual(caught.exception.code, "IMMUTABLE_ARTIFACT_REFERENCE_MISSING")
        self.assertEqual(caught.exception.field_path, "/artifact/anchor")
        self.assertIn(caught.exception.code, cpa.ERROR_CODES)

    def test_malformed_anchor_combination_is_refused(self):
        def mix(payload):
            payload["artifact"]["anchor"]["snapshot_reference"] = {
                "namespace": "ns",
                "identifier": "snap",
                "revision": "r",
                "snapshot_reference": None,
            }

        with self.assertRaises(Error) as caught:
            self.load(self.mutated(mix))
        self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")
        self.assertEqual(
            caught.exception.field_path, "/artifact/anchor/snapshot_reference"
        )

    def test_invalid_hash_spelling_is_refused_and_never_normalized(self):
        for digest in ("A" * 64, "a" * 63, "a" * 65, "g" * 64):
            with self.subTest(digest=digest[:3] + str(len(digest))):
                payload = self.mutated(
                    lambda item, value=digest: item["artifact"]["anchor"].__setitem__(
                        "digest", value
                    )
                )
                with self.assertRaises(Error) as caught:
                    self.load(payload)
                self.assertEqual(caught.exception.field_path, "/artifact/anchor/digest")

    def test_unsupported_hash_algorithm_is_refused(self):
        def rename(payload):
            payload["artifact"]["anchor"]["algorithm"] = "sha512"

        with self.assertRaises(Error) as caught:
            self.load(self.mutated(rename))
        self.assertEqual(caught.exception.field_path, "/artifact/anchor/algorithm")

    def test_duplicate_participant_identifier_is_refused(self):
        def duplicate(payload):
            payload["participants"][1]["participant_id"] = "p1"

        with self.assertRaises(Error) as caught:
            self.load(self.mutated(duplicate))
        self.assertEqual(
            caught.exception.field_path, "/participants/1/participant_id"
        )

    def test_duplicate_conflict_identifier_is_refused(self):
        payload = complete_document(conflicts=(conflict("c1"), conflict("c2"))).as_dict()
        payload["association_conflicts"][1]["conflict_id"] = "c1"
        with self.assertRaises(Error) as caught:
            self.load(payload)
        self.assertEqual(
            caught.exception.field_path, "/association_conflicts/1/conflict_id"
        )

    def test_dangling_pose_pair_reference_is_refused(self):
        def dangle(payload):
            payload["pose_pair"]["binder_participant_id"] = "absent"

        with self.assertRaises(Error) as caught:
            self.load(self.mutated(dangle))
        self.assertEqual(
            caught.exception.field_path, "/pose_pair/binder_participant_id"
        )

    def test_malformed_timestamps_are_refused(self):
        for stamp in (
            "2026-09-28T09:15:00",
            "2026-09-28T09:15:00.500Z",
            "2026-09-28T09:15:00+00:00",
            "2026-02-30T09:15:00Z",
            "2026-13-01T09:15:00Z",
            "2026-09-28T24:00:00Z",
            "2026-09-28T09:15:60Z",
            "2026-9-28T09:15:00Z",
        ):
            with self.subTest(stamp=stamp):
                payload = self.mutated(
                    lambda item, value=stamp: item.__setitem__("declared_at", value)
                )
                with self.assertRaises(Error) as caught:
                    self.load(payload)
                self.assertEqual(caught.exception.field_path, "/declared_at")

    def test_a_leap_day_is_accepted_and_a_non_leap_day_is_refused(self):
        accepted = self.mutated(
            lambda item: item.__setitem__("declared_at", "2024-02-29T00:00:00Z")
        )
        self.assertIsNotNone(self.load(accepted))
        refused = self.mutated(
            lambda item: item.__setitem__("declared_at", "2026-02-29T00:00:00Z")
        )
        with self.assertRaises(Error):
            self.load(refused)

    def test_state_and_alternative_cardinality_mismatch_is_refused(self):
        def empty_supplied(payload):
            payload["participants"][0]["chain_mapping"]["alternatives"] = []

        with self.assertRaises(Error) as caught:
            self.load(self.mutated(empty_supplied))
        self.assertEqual(
            caught.exception.field_path,
            "/participants/0/chain_mapping/alternatives",
        )

    def test_unknown_field_is_refused_at_every_depth(self):
        cases = {
            "/surprise": lambda payload: payload.__setitem__("surprise", "x"),
            "/artifact/surprise": lambda payload: payload["artifact"].__setitem__(
                "surprise", "x"
            ),
            "/participants/0/chain_mapping/alternatives/0/value/chains/0/surprise": (
                lambda payload: payload["participants"][0]["chain_mapping"][
                    "alternatives"
                ][0]["value"]["chains"][0].__setitem__("surprise", "x")
            ),
        }
        for expected, mutate in cases.items():
            with self.subTest(path=expected):
                with self.assertRaises(Error) as caught:
                    self.load(self.mutated(mutate))
                self.assertEqual(caught.exception.field_path, expected)

    def test_missing_field_is_refused(self):
        def drop(payload):
            del payload["artifact"]["locator"]

        with self.assertRaises(Error) as caught:
            self.load(self.mutated(drop))
        self.assertEqual(caught.exception.field_path, "/artifact/locator")

    def test_duplicate_json_object_keys_are_refused_at_every_depth(self):
        text = canon(self.payload).decode("utf-8")
        shallow = text.replace(
            '"association_id":"assoc-1"',
            '"association_id":"assoc-1","association_id":"assoc-2"',
            1,
        )
        with self.assertRaises(Error) as caught:
            cpa.CallerPoseAssociation.from_json_bytes(shallow.encode("utf-8"))
        self.assertIn("duplicate JSON object key", caught.exception.reason)

        deep = text.replace('"kind":"CONTENT_HASH"', '"kind":"CONTENT_HASH","kind":"x"', 1)
        with self.assertRaises(Error) as caught:
            cpa.CallerPoseAssociation.from_json_bytes(deep.encode("utf-8"))
        self.assertIn("duplicate JSON object key", caught.exception.reason)

    def test_modifying_a_fixed_string_is_refused(self):
        for key in ("document_type", "non_claim"):
            with self.subTest(key=key):
                payload = self.mutated(
                    lambda item, name=key: item.__setitem__(
                        name, item[name] + " (amended)"
                    )
                )
                with self.assertRaises(Error) as caught:
                    self.load(payload)
                self.assertEqual(caught.exception.field_path, "/" + key)

    def test_altered_derived_diagnostics_are_refused(self):
        mutations = (
            ("dropped", lambda payload: payload.__setitem__("diagnostics", [])),
            (
                "replaced_path",
                lambda payload: payload["diagnostics"][0].__setitem__(
                    "field_paths", ["/artifact/locator"]
                ),
            ),
            (
                "extra_code",
                lambda payload: payload["diagnostics"].append(
                    {
                        "code": "DECLARATION_MISSING",
                        "field_paths": ["/artifact/locator"],
                        "participant_ids": [],
                        "conflict_ids": [],
                    }
                ),
            ),
            (
                "altered_participants",
                lambda payload: payload["diagnostics"][0].__setitem__(
                    "participant_ids", ["p1"]
                ),
            ),
        )
        for name, mutate in mutations:
            with self.subTest(case=name):
                with self.assertRaises(Error) as caught:
                    self.load(self.mutated(mutate))
                self.assertEqual(caught.exception.field_path, "/diagnostics")

    def test_reordered_derived_field_paths_are_refused(self):
        payload = limited_document().as_dict()
        first = payload["diagnostics"][0]
        self.assertEqual(len(first["field_paths"]), 2)
        first["field_paths"] = list(reversed(first["field_paths"]))
        with self.assertRaises(Error) as caught:
            self.load(payload)
        self.assertEqual(caught.exception.field_path, "/diagnostics")

    def test_reordered_derived_participant_ids_are_refused(self):
        payload = limited_document().as_dict()
        touched = False
        for item in payload["diagnostics"]:
            if item["code"] == "RESIDUE_ADDRESSING_ABSENT":
                self.assertEqual(item["participant_ids"], ["p1", "p3"])
                item["participant_ids"] = ["p3", "p1"]
                touched = True
        self.assertTrue(touched)
        with self.assertRaises(Error) as caught:
            self.load(payload)
        self.assertEqual(caught.exception.field_path, "/diagnostics")

    def test_noncanonical_bytes_are_refused_rather_than_rewritten(self):
        payload = self.payload
        variants = {
            "indented": json.dumps(payload, sort_keys=True, indent=2).encode("utf-8"),
            "spaced": json.dumps(
                payload, sort_keys=True, separators=(", ", ": ")
            ).encode("utf-8"),
            "unsorted": json.dumps(
                payload, sort_keys=False, separators=(",", ":")
            ).encode("utf-8"),
            "trailing_newline": canon(payload) + b"\n",
            "byte_order_mark": b"\xef\xbb\xbf" + canon(payload),
            "escaped_slash": canon(payload).replace(b"/1", b"\\/1", 1),
        }
        for name, data in variants.items():
            with self.subTest(variant=name):
                with self.assertRaises(Error):
                    cpa.CallerPoseAssociation.from_json_bytes(data)

    def test_a_numeric_primitive_is_refused(self):
        text = canon(self.payload).decode("utf-8").replace('"model-1"', "1", 1)
        with self.assertRaises(Error):
            cpa.CallerPoseAssociation.from_json_bytes(text.encode("utf-8"))

    def test_identifier_spelling_is_never_repaired(self):
        for value in ("", " assoc-1", "assoc-1 ", "assoc\u00001"):
            with self.subTest(value=repr(value)):
                payload = self.mutated(
                    lambda item, text=value: item.__setitem__("association_id", text)
                )
                with self.assertRaises(Error) as caught:
                    self.load(payload)
                self.assertEqual(caught.exception.field_path, "/association_id")


# --------------------------------------------------------------------------------
# 4. Information-record cardinality
# --------------------------------------------------------------------------------


class InformationRecordCardinality(unittest.TestCase):
    def test_supplied_requires_exactly_one_alternative(self):
        self.assertEqual(len(chain_mapping("SUPPLIED").alternatives), 1)
        with self.assertRaises(Error):
            cpa.ChainMapping(state="SUPPLIED", alternatives=())
        with self.assertRaises(Error):
            chain_mapping(
                "SUPPLIED",
                values=(chain_value(), chain_value(entries=(chain_entry("auth", "B"),))),
            )

    def test_absent_requires_no_alternative(self):
        self.assertEqual(cpa.ResidueAddressing(state="ABSENT", alternatives=()).alternatives, ())
        with self.assertRaises(Error):
            residue_addressing("ABSENT")

    def test_ambiguous_requires_two_distinct_values(self):
        distinct = chain_mapping(
            "AMBIGUOUS",
            values=(chain_value(), chain_value(entries=(chain_entry("auth", "B"),))),
        )
        self.assertEqual(len(distinct.alternatives), 2)
        with self.assertRaises(Error):
            chain_mapping("AMBIGUOUS", values=(chain_value(),))

    def test_repeated_citations_of_one_value_do_not_establish_ambiguity(self):
        with self.assertRaises(Error) as caught:
            chain_mapping(
                "AMBIGUOUS",
                values=(chain_value(), chain_value()),
                sources=(reference("src-a"), reference("src-b")),
            )
        self.assertIn("distinct", caught.exception.reason)

    def test_ambiguous_retains_caller_order(self):
        first = chain_value()
        second = chain_value(entries=(chain_entry("auth", "B"),))
        mapping = chain_mapping("AMBIGUOUS", values=(second, first))
        self.assertEqual(
            [item.value for item in mapping.alternatives], [second, first]
        )

    def test_exact_repeated_chain_entries_are_refused(self):
        with self.assertRaises(Error) as caught:
            cpa.ChainMappingValue(scope=scope(), chains=(chain_entry(), chain_entry()))
        self.assertEqual(caught.exception.field_path, "/chains/1")
        with self.assertRaises(Error):
            cpa.ResidueAddressingValue(
                scope=scope(),
                chain_instances=(chain_instance(), chain_instance()),
                scheme="s",
                namespace="n",
                residue_identifier_convention="c",
                insertion_code_convention="i",
                residue_subset=None,
                external_mapping=None,
            )

    def test_an_unknown_state_token_is_refused(self):
        with self.assertRaises(Error) as caught:
            cpa.ChainMapping(state="MAYBE", alternatives=())
        self.assertEqual(caught.exception.field_path, "/state")


# --------------------------------------------------------------------------------
# 5. Conditions-profile agreement
# --------------------------------------------------------------------------------


class ConditionsProfileAgreement(unittest.TestCase):
    def test_supplied_requires_a_reference_and_a_null_reason(self):
        profile = cpa.ConditionsProfile(
            state="SUPPLIED", reference=reference("profile"), reason=None
        )
        self.assertIsNone(profile.reason)
        with self.assertRaises(Error) as caught:
            cpa.ConditionsProfile(state="SUPPLIED", reference=None, reason=None)
        self.assertEqual(caught.exception.field_path, "/reference")
        with self.assertRaises(Error) as caught:
            cpa.ConditionsProfile(
                state="SUPPLIED", reference=reference("profile"), reason="why"
            )
        self.assertEqual(caught.exception.field_path, "/reason")

    def test_unavailable_requires_a_reason_and_a_null_reference(self):
        profile = cpa.ConditionsProfile(
            state="UNAVAILABLE", reference=None, reason="not supplied"
        )
        self.assertIsNone(profile.reference)
        with self.assertRaises(Error) as caught:
            cpa.ConditionsProfile(state="UNAVAILABLE", reference=None, reason=None)
        self.assertEqual(caught.exception.field_path, "/reason")
        with self.assertRaises(Error) as caught:
            cpa.ConditionsProfile(
                state="UNAVAILABLE", reference=reference("profile"), reason="why"
            )
        self.assertEqual(caught.exception.field_path, "/reference")

    def test_an_empty_reason_is_not_an_absence(self):
        with self.assertRaises(Error):
            cpa.ConditionsProfile(state="UNAVAILABLE", reference=None, reason="")

    def test_only_unavailable_raises_the_profile_diagnostic(self):
        supplied = complete_document()
        self.assertNotIn("CONDITION_PROFILE_UNAVAILABLE", codes(supplied))
        unavailable = complete_document(
            conditions_profile=cpa.ConditionsProfile(
                state="UNAVAILABLE", reference=None, reason="not supplied"
            )
        )
        self.assertEqual(codes(unavailable), ["CONDITION_PROFILE_UNAVAILABLE"])
        self.assertEqual(
            list(diagnostic(unavailable, "CONDITION_PROFILE_UNAVAILABLE").field_paths),
            ["/conditions_profile"],
        )


# --------------------------------------------------------------------------------
# 6. Participant-role multiplicity and pose-pair consistency
# --------------------------------------------------------------------------------


class ParticipantRolesAndPosePair(unittest.TestCase):
    def test_one_binder_and_one_receptor_raise_no_role_diagnostic(self):
        document = complete_document()
        self.assertNotIn("PARTICIPANT_ROLE_MISSING", codes(document))
        self.assertNotIn("DUPLICATE_PARTICIPANT_ROLE", codes(document))

    def test_a_duplicated_optional_role_is_reported_and_never_resolved(self):
        document = complete_document(
            participants=(
                participant("p1", "BINDER"),
                participant("p2", "RECEPTOR"),
                participant("p3", "CONTEXT"),
                participant("p4", "CONTEXT"),
            )
        )
        item = diagnostic(document, "DUPLICATE_PARTICIPANT_ROLE")
        self.assertEqual(
            list(item.field_paths), ["/participants/2/role", "/participants/3/role"]
        )
        self.assertEqual(list(item.participant_ids), ["p3", "p4"])
        # Both participants survive; the implementation selects neither.
        self.assertEqual(
            [item.participant_id for item in document.participants],
            ["p1", "p2", "p3", "p4"],
        )

    def test_a_missing_required_role_is_reported_against_the_array(self):
        document = complete_document(
            participants=(participant("p1", "BINDER"), participant("p2", "CONTEXT")),
            pose_pair=cpa.PosePair(
                binder_participant_id="p1", receptor_participant_id=None
            ),
        )
        self.assertEqual(
            list(diagnostic(document, "PARTICIPANT_ROLE_MISSING").field_paths),
            ["/participants"],
        )

    def test_an_empty_participant_array_is_serializable(self):
        document = complete_document(
            participants=(),
            pose_pair=cpa.PosePair(
                binder_participant_id=None, receptor_participant_id=None
            ),
        )
        self.assertEqual(
            list(diagnostic(document, "PARTICIPANT_ROLE_MISSING").field_paths),
            ["/participants"],
        )
        self.assertEqual(
            cpa.CallerPoseAssociation.from_json_bytes(document.to_json_bytes()),
            document,
        )

    def test_pose_pair_role_disagreement_is_reported_and_never_repaired(self):
        document = complete_document(
            participants=(
                participant("p1", "BINDER"),
                participant("p2", "RECEPTOR"),
                participant("p3", "LIGAND"),
            ),
            pose_pair=cpa.PosePair(
                binder_participant_id="p3", receptor_participant_id="p2"
            ),
        )
        item = diagnostic(document, "DECLARATION_INCONSISTENT")
        self.assertEqual(list(item.field_paths), ["/pose_pair/binder_participant_id"])
        self.assertEqual(list(item.participant_ids), ["p3"])
        self.assertEqual(document.pose_pair.binder_participant_id, "p3")

    def test_a_null_role_on_the_referenced_participant_disagrees(self):
        document = complete_document(
            participants=(
                participant("p1", None),
                participant("p2", "RECEPTOR"),
            ),
            pose_pair=cpa.PosePair(
                binder_participant_id="p1", receptor_participant_id="p2"
            ),
        )
        self.assertIn("DECLARATION_INCONSISTENT", codes(document))
        self.assertIn("PARTICIPANT_ROLE_MISSING", codes(document))

    def test_an_unknown_role_token_is_refused(self):
        with self.assertRaises(Error) as caught:
            participant("p1", "COFACTOR")
        self.assertEqual(caught.exception.field_path, "/role")


# --------------------------------------------------------------------------------
# 7. Scope mismatch and provenance diagnostics
# --------------------------------------------------------------------------------


class ScopeAndProvenance(unittest.TestCase):
    def test_a_matching_joint_frame_raises_no_mismatch(self):
        document = complete_document()
        self.assertNotIn("SHARED_FRAME_MISMATCH", codes(document))
        self.assertNotIn("SHARED_FRAME_MISSING", codes(document))

    def test_joint_frame_scope_must_match_the_selected_artifact_model(self):
        document = complete_document(
            joint_frame=cpa.JointFrame(
                frame_id="frame-1",
                frame_kind="CALLER_DECLARED_ARTIFACT_MODEL_FRAME",
                scope=scope(model_id="other-model"),
            )
        )
        item = diagnostic(document, "SHARED_FRAME_MISMATCH")
        self.assertIn("/joint_frame/scope", item.field_paths)

    def test_a_different_anchor_form_is_never_treated_as_equivalent(self):
        document = complete_document(
            joint_frame=cpa.JointFrame(
                frame_id="frame-1",
                frame_kind="CALLER_DECLARED_ARTIFACT_MODEL_FRAME",
                scope=cpa.ArtifactModelScope(
                    artifact_anchor=snapshot_anchor(), model_id="model-1"
                ),
            )
        )
        self.assertIn("SHARED_FRAME_MISMATCH", codes(document))

    def test_a_mapping_scope_mismatch_names_the_mapping_location(self):
        document = complete_document(
            participants=(
                participant(
                    "p1",
                    "BINDER",
                    mapping=chain_mapping(
                        values=(chain_value(value_scope=scope(model_id="other")),)
                    ),
                ),
                participant("p2", "RECEPTOR"),
            )
        )
        item = diagnostic(document, "SHARED_FRAME_MISMATCH")
        self.assertEqual(
            list(item.field_paths),
            ["/participants/0/chain_mapping/alternatives/0/value/scope"],
        )
        self.assertEqual(list(item.participant_ids), ["p1"])

    def test_a_mismatch_is_retained_not_reconciled(self):
        document = complete_document(
            participants=(
                participant(
                    "p1",
                    "BINDER",
                    mapping=chain_mapping(
                        values=(chain_value(value_scope=scope(model_id="other")),)
                    ),
                ),
                participant("p2", "RECEPTOR"),
            )
        )
        stored = document.participants[0].chain_mapping.alternatives[0].value.scope
        self.assertEqual(stored.model_id, "other")

    def test_an_absent_joint_frame_is_reported_and_scopes_fall_back(self):
        document = complete_document(joint_frame=None)
        self.assertEqual(
            list(diagnostic(document, "SHARED_FRAME_MISSING").field_paths),
            ["/joint_frame"],
        )
        self.assertNotIn("SHARED_FRAME_MISMATCH", codes(document))

    def test_absent_provenance_uses_the_dedicated_and_general_codes(self):
        document = complete_document(
            provenance=cpa.Provenance(
                source_reference=None, run_reference=None, method_reference=None
            )
        )
        self.assertEqual(
            list(
                diagnostic(document, "MODEL_RUN_METHOD_REFERENCE_ABSENT").field_paths
            ),
            ["/provenance/method_reference", "/provenance/run_reference"],
        )
        self.assertEqual(
            list(diagnostic(document, "DECLARATION_MISSING").field_paths),
            ["/provenance/source_reference"],
        )

    def test_a_malformed_provenance_reference_is_refused(self):
        with self.assertRaises(Error) as caught:
            cpa.ImmutableReference(
                namespace="ns", identifier="id", revision=None, snapshot_reference=None
            )
        self.assertEqual(caught.exception.field_path, "/revision")

    def test_an_absent_selected_model_uses_the_dedicated_code(self):
        document = complete_document(
            artifact=cpa.Artifact(
                anchor=hash_anchor(), locator="opaque-locator", selected_model=None
            ),
            joint_frame=cpa.JointFrame(
                frame_id="frame-1",
                frame_kind="CALLER_DECLARED_ARTIFACT_MODEL_FRAME",
                scope=scope(model_id=None),
            ),
            participants=(
                participant(
                    "p1",
                    "BINDER",
                    mapping=chain_mapping(values=(chain_value(value_scope=scope(model_id=None)),)),
                    addressing=residue_addressing(
                        values=(residue_value(value_scope=scope(model_id=None)),)
                    ),
                ),
                participant(
                    "p2",
                    "RECEPTOR",
                    mapping=chain_mapping(values=(chain_value(value_scope=scope(model_id=None)),)),
                    addressing=residue_addressing(
                        values=(residue_value(value_scope=scope(model_id=None)),)
                    ),
                ),
            ),
        )
        self.assertEqual(
            list(
                diagnostic(document, "MODEL_RUN_METHOD_REFERENCE_ABSENT").field_paths
            ),
            ["/artifact/selected_model"],
        )
        self.assertNotIn("SHARED_FRAME_MISMATCH", codes(document))


# --------------------------------------------------------------------------------
# 7b. Conflict field-path pointer spelling
# --------------------------------------------------------------------------------


class ConflictFieldPointers(unittest.TestCase):
    def round_trip(self, pointers):
        document = complete_document(conflicts=(conflict("c1", pointers),))
        reloaded = cpa.CallerPoseAssociation.from_json_bytes(document.to_json_bytes())
        self.assertEqual(reloaded, document)
        self.assertEqual(
            list(reloaded.association_conflicts[0].field_paths), list(pointers)
        )
        return reloaded

    def test_the_root_pointer_serializes_and_round_trips(self):
        reloaded = self.round_trip(("",))
        self.assertEqual(list(reloaded.association_conflicts[0].field_paths), [""])

    def test_escape_sequences_serialize_and_round_trip(self):
        self.round_trip(("/a~0b/c~1d", "/~0", "/~1", "/plain"))

    def test_caller_order_of_pointers_is_preserved(self):
        reloaded = self.round_trip(("/b", "", "/a~1z"))
        self.assertEqual(
            list(reloaded.association_conflicts[0].field_paths), ["/b", "", "/a~1z"]
        )

    def test_a_non_empty_pointer_must_begin_with_a_slash(self):
        for value in ("participants", "a/b", "~0", " /a"):
            with self.subTest(value=value):
                with self.assertRaises(Error) as caught:
                    conflict("c1", (value,))
                self.assertEqual(caught.exception.field_path, "/field_paths/0")

    def test_malformed_escape_usage_is_refused(self):
        for value in ("/~", "/~2", "/a~", "/a~b", "/a~~0", "/~0~", "/~ 0"):
            with self.subTest(value=value):
                with self.assertRaises(Error) as caught:
                    conflict("c1", (value,))
                self.assertEqual(caught.exception.field_path, "/field_paths/0")
                self.assertIn("~0 or ~1", caught.exception.reason)

    def test_a_bare_tilde_is_refused(self):
        with self.assertRaises(Error) as caught:
            conflict("c1", ("~",))
        self.assertEqual(caught.exception.field_path, "/field_paths/0")

    def test_the_refusal_names_the_offending_index(self):
        with self.assertRaises(Error) as caught:
            conflict("c1", ("/ok", "", "/bad~"))
        self.assertEqual(caught.exception.field_path, "/field_paths/2")

    def test_a_malformed_pointer_is_refused_when_loading(self):
        payload = complete_document(conflicts=(conflict(),)).as_dict()
        payload["association_conflicts"][0]["field_paths"] = ["/bad~2"]
        with self.assertRaises(Error) as caught:
            cpa.CallerPoseAssociation.from_json_bytes(canon(payload))
        self.assertEqual(
            caught.exception.field_path, "/association_conflicts/0/field_paths/0"
        )

    def test_an_empty_field_paths_array_is_still_refused(self):
        with self.assertRaises(Error) as caught:
            conflict("c1", ())
        self.assertEqual(caught.exception.field_path, "/field_paths")

    def test_diagnostic_field_paths_are_unchanged_by_this_clarification(self):
        with self.assertRaises(Error) as caught:
            cpa.Diagnostic(
                code="DECLARATION_MISSING",
                field_paths=("",),
                participant_ids=(),
                conflict_ids=(),
            )
        self.assertEqual(caught.exception.field_path, "/field_paths/0")


# --------------------------------------------------------------------------------
# 8. Deterministic canonical bytes
# --------------------------------------------------------------------------------


class DeterministicBytes(unittest.TestCase):
    def test_repeated_construction_produces_identical_bytes(self):
        first = limited_document().to_json_bytes()
        for _ in range(5):
            self.assertEqual(limited_document().to_json_bytes(), first)
        document = limited_document()
        self.assertEqual(document.to_json_bytes(), document.to_json_bytes())

    def test_canonical_bytes_carry_no_insignificant_whitespace(self):
        data = limited_document().to_json_bytes()
        # Re-emitting the decoded content in the canonical spelling reproduces the
        # same bytes, so the emitted form is compact, sorted and unpadded.
        self.assertEqual(data, canon(json.loads(data.decode("utf-8"))))
        self.assertFalse(data.endswith(b"\n"))
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\n", data)
        self.assertNotIn(b"\t", data)
        self.assertNotIn(b"\\/", data)

    def test_object_keys_are_recursively_sorted(self):
        decoded = json.loads(limited_document().to_json_bytes().decode("utf-8"))

        def walk(node):
            if isinstance(node, dict):
                keys = list(node)
                self.assertEqual(keys, sorted(keys))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(decoded)

    def test_bytes_are_stable_across_fresh_processes_and_hash_seeds(self):
        data = limited_document().to_json_bytes()
        script = (
            "import importlib.util, sys\n"
            "spec = importlib.util.spec_from_file_location({0!r}, {1!r})\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "sys.modules[spec.name] = module\n"
            "spec.loader.exec_module(module)\n"
            "payload = sys.stdin.buffer.read()\n"
            "document = module.CallerPoseAssociation.from_json_bytes(payload)\n"
            "sys.stdout.write(document.to_json_bytes().hex())\n"
        ).format(MODULE_NAME, str(MODULE_PATH))
        for seed in ("0", "1", "12345"):
            with self.subTest(seed=seed):
                environment = dict(os.environ)
                environment["PYTHONHASHSEED"] = seed
                completed = subprocess.run(
                    [sys.executable, "-B", "-c", script],
                    input=data,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=environment,
                    check=False,
                )
                self.assertEqual(
                    completed.returncode, 0, completed.stderr.decode("utf-8", "replace")
                )
                self.assertEqual(completed.stdout.decode("ascii"), data.hex())


# --------------------------------------------------------------------------------
# 9. Fresh containers and immutable storage
# --------------------------------------------------------------------------------


class FreshContainersAndImmutability(unittest.TestCase):
    def setUp(self):
        self.document = limited_document()

    def test_as_dict_returns_a_new_structure_every_call(self):
        first = self.document.as_dict()
        second = self.document.as_dict()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertIsNot(first["participants"], second["participants"])
        self.assertIsNot(first["participants"][0], second["participants"][0])
        self.assertIsNot(first["artifact"]["anchor"], second["artifact"]["anchor"])
        self.assertIsNot(first["diagnostics"][0], second["diagnostics"][0])

    def test_mutating_a_returned_structure_cannot_reach_the_document(self):
        baseline = self.document.to_json_bytes()
        payload = self.document.as_dict()
        payload["participants"].append({"injected": True})
        payload["artifact"]["locator"] = "rewritten"
        payload["diagnostics"].clear()
        self.assertEqual(self.document.to_json_bytes(), baseline)
        self.assertEqual(len(self.document.as_dict()["participants"]), 3)

    def test_every_stored_sequence_is_a_tuple(self):
        self.assertIsInstance(self.document.participants, tuple)
        self.assertIsInstance(self.document.association_conflicts, tuple)
        self.assertIsInstance(self.document.diagnostics, tuple)
        self.assertIsInstance(self.document.diagnostics[0].field_paths, tuple)
        self.assertIsInstance(self.document.diagnostics[0].participant_ids, tuple)
        self.assertIsInstance(self.document.association_conflicts[0].field_paths, tuple)
        mapping = self.document.participants[2].chain_mapping
        self.assertIsInstance(mapping.alternatives, tuple)
        self.assertIsInstance(mapping.alternatives[0].value.chains, tuple)

    def test_a_caller_list_is_copied_rather_than_retained(self):
        chains = [chain_entry()]
        value = cpa.ChainMappingValue(scope=scope(), chains=chains)
        chains.append(chain_entry("auth", "B"))
        self.assertEqual(len(value.chains), 1)

    def test_records_are_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.document.association_id = "other"
        with self.assertRaises(FrozenInstanceError):
            self.document.diagnostics = ()
        with self.assertRaises(FrozenInstanceError):
            self.document.participants[0].role = "BINDER"

    def test_diagnostics_are_not_caller_supplied(self):
        with self.assertRaises(TypeError):
            cpa.CallerPoseAssociation(
                association_id="a",
                revision="r",
                declared_by="d",
                declared_at=STAMP,
                artifact=cpa.Artifact(
                    anchor=hash_anchor(), locator=None, selected_model=None
                ),
                provenance=cpa.Provenance(None, None, None),
                participants=(),
                pose_pair=cpa.PosePair(None, None),
                joint_frame=None,
                conditions_profile=cpa.ConditionsProfile(
                    state="UNAVAILABLE", reference=None, reason="none"
                ),
                association_conflicts=(),
                diagnostics=(),
            )


# --------------------------------------------------------------------------------
# 10. Static import isolation
# --------------------------------------------------------------------------------


class StaticImportIsolation(unittest.TestCase):
    ALLOWED_IMPORTS = frozenset({"__future__", "dataclasses", "json"})
    FORBIDDEN_ROOTS = frozenset(
        {
            "os",
            "sys",
            "io",
            "pathlib",
            "shutil",
            "tempfile",
            "glob",
            "subprocess",
            "multiprocessing",
            "threading",
            "socket",
            "ssl",
            "urllib",
            "http",
            "requests",
            "time",
            "datetime",
            "calendar",
            "random",
            "secrets",
            "uuid",
            "hashlib",
            "hmac",
            "importlib",
            "pickle",
            "ast",
            "re",
            "csv",
            "sqlite3",
            "logging",
            "argparse",
            "platform",
            "getpass",
            "numpy",
            "pandas",
            "scipy",
            "Bio",
            "nbformat",
            "gotne",
            "avidity",
            "structure_audit",
            "files",
        }
    )

    def setUp(self):
        self.source = MODULE_PATH.read_text(encoding="utf-8")
        self.tree = ast.parse(self.source)

    def test_only_the_allowed_standard_library_modules_are_imported(self):
        roots = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    self.fail("the module performs a relative (project) import")
                roots.add((node.module or "").split(".")[0])
        self.assertEqual(roots, set(self.ALLOWED_IMPORTS))
        self.assertEqual(roots & self.FORBIDDEN_ROOTS, set())

    def test_every_import_is_at_module_level(self):
        top_level = set()
        for node in self.tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                top_level.add(node)
        nested = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.Import, ast.ImportFrom)) and node not in top_level
        ]
        self.assertEqual(nested, [], "the module imports inside a function or class")

    def test_no_dynamic_import_or_execution_entry_point_is_called(self):
        banned = {
            "open",
            "eval",
            "exec",
            "compile",
            "input",
            "__import__",
            "globals",
            "locals",
            "vars",
        }
        called = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called.add(node.func.id)
        self.assertEqual(called & banned, set())

    def test_no_filesystem_clock_process_or_network_name_appears(self):
        attributes = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Attribute):
                attributes.add(node.attr)
        for banned in (
            "read_text",
            "read_bytes",
            "write_text",
            "write_bytes",
            "environ",
            "getenv",
            "now",
            "utcnow",
            "time",
            "monotonic",
            "run",
            "Popen",
            "urlopen",
            "connect",
            "sha256",
            "load",
            "dump",
        ):
            with self.subTest(name=banned):
                self.assertNotIn(banned, attributes)

    def test_the_module_only_uses_json_for_serialization(self):
        json_attributes = set()
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "json"
            ):
                json_attributes.add(node.attr)
        self.assertEqual(json_attributes, {"dumps", "loads"})

    def test_importing_the_module_runs_no_package_initializer(self):
        script = (
            "import importlib.util, sys\n"
            "before = set(sys.modules)\n"
            "spec = importlib.util.spec_from_file_location({0!r}, {1!r})\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "sys.modules[spec.name] = module\n"
            "spec.loader.exec_module(module)\n"
            "added = sorted(set(sys.modules) - before)\n"
            "sys.stdout.write(repr(added))\n"
        ).format(MODULE_NAME, str(MODULE_PATH))
        completed = subprocess.run(
            [sys.executable, "-B", "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(
            completed.returncode, 0, completed.stderr.decode("utf-8", "replace")
        )
        added = completed.stdout.decode("utf-8")
        for banned in ("gotne", "avidity", "structure_audit", "files."):
            self.assertNotIn(banned, added)


if __name__ == "__main__":
    unittest.main()
