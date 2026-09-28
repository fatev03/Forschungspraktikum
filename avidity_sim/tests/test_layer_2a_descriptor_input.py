"""Contract tests for ``layer_2a_descriptor_input/1``.

The module under test is loaded directly from its file so that no package
initializer runs and no project module is imported on its behalf.

Run: python3 -B -m unittest discover -s tests -t tests \
         -p 'test_layer_2a_descriptor_input.py' -v
"""
from __future__ import annotations

import ast
import builtins
import copy
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import types
import unittest
from dataclasses import FrozenInstanceError, replace

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT_DIR / "files"
MODULE_NAME = "layer_2a_descriptor_input"
MODULE_PATH = PACKAGE_DIR / (MODULE_NAME + ".py")


def _load_module():
    spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


m = _load_module()
Error = m.Layer2DescriptorInputError

STAMP = "2026-09-28T09:15:00Z"
DIGEST = "a" * 64


def canon(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


# ================================================================================
# Builders
# ================================================================================


def ref(identifier="r-1", revision="v1", snapshot=None, namespace="ns"):
    return m.L2ImmutableReference(
        namespace=namespace,
        identifier=identifier,
        revision=revision,
        snapshot_reference=snapshot,
    )


def src(identifier="s-1", locator="opaque"):
    return m.L2SourceRecord(reference=ref(identifier), locator=locator)


def anchor(digest=DIGEST):
    return m.L2ArtifactAnchor(
        kind="CONTENT_HASH", algorithm="sha256", digest=digest, snapshot_reference=None
    )


def snapshot_anchor():
    return m.L2ArtifactAnchor(
        kind="IMMUTABLE_SNAPSHOT",
        algorithm=None,
        digest=None,
        snapshot_reference=ref("snap", None, "snap-token"),
    )


def association(association_id="assoc-1"):
    return m.L2AssociationReference(
        association_id=association_id, revision="rev-1", reference=ref("doc-1")
    )


def admission(candidate_id="cand-1", absent=("state_result_id",)):
    return m.L2AdmissionReference(
        candidate_id=candidate_id,
        slot_binding_hash="hash-1",
        state_result_id=None,
        ineligibility_reason=None,
        certificate_present=True,
        absent_keys=tuple(absent),
    )


def candidate_anchor(**overrides):
    payload = dict(
        candidate_id="cand-1",
        scenario_id="scen-1",
        evaluation_run_ref="run-1",
        batch_report_reference=src("batch"),
        priority_report_reference=src("priority"),
        scenario_comparison_reference=src("comparison"),
        admission_reference=admission(),
    )
    payload.update(overrides)
    return m.L2CandidateAnchor(**payload)


def pose(pose_id="pose_1", **overrides):
    payload = dict(
        pose_id=pose_id,
        artifact_anchor=anchor(),
        locator="opaque-locator",
        model_id="model-1",
        conformer_id="conformer-1",
        frame_id="frame-1",
        association_reference=association(),
        source_reference=src("pose-source"),
        run_reference=ref("pose-run"),
        method_reference=ref("pose-method"),
    )
    payload.update(overrides)
    return m.L2PoseRecord(**payload)


def chain_instance(chain_id="A", addressing=True):
    return m.L2ChainInstance(
        identifier_namespace="auth",
        chain_id=chain_id,
        instance_id="1",
        residue_addressing_reference=src("addressing") if addressing else None,
        selection_declaration="1-40",
    )


def mapping_alternative(chain_id="A", addressing=True, pose_id="pose_1"):
    return m.L2MappingAlternative(
        pose_id=pose_id,
        chain_instances=(chain_instance(chain_id, addressing),),
        source_reference=src("mapping"),
    )


def participant(participant_id="p_binder", role="BINDER", **overrides):
    payload = dict(
        participant_id=participant_id,
        role=role,
        identity_reference=ref("identity-" + participant_id),
        construct_id="construct-" + participant_id,
        construct_version="v1",
        mapping_state="SUPPLIED",
        mapping_alternatives=(mapping_alternative(),),
    )
    payload.update(overrides)
    return m.L2MolecularParticipant(**payload)


def context(context_id="ctx-1"):
    return m.L2ContextDeclaration(
        context_id=context_id,
        subject_declaration="subject text",
        treatment="REPRESENTED",
        declaration="context text",
        source_reference=src("context"),
    )


def missing(field_path="/scope", reason="unresolved"):
    return m.L2MissingDeclaration(field=field_path, reason=reason)


def scope(**overrides):
    payload = dict(
        slot_id="slot_1",
        binder_participant_id="p_binder",
        target_participant_id="p_target",
        participants=(
            participant("p_binder", "BINDER"),
            participant("p_target", "RECEPTOR"),
        ),
        association_reference=association(),
        target_site_declaration="site text",
        context_declarations=(context(),),
        missing_declarations=(),
    )
    payload.update(overrides)
    return m.L2LocalScope(**payload)


def method(**overrides):
    payload = dict(
        reference=ref("method"),
        parameters=(m.L2NamedDeclaration(name="tolerance", value="declared"),),
        representation="representation text",
        run_reference=ref("method-run"),
    )
    payload.update(overrides)
    return m.L2MethodDeclaration(**payload)


def profile(state="SUPPLIED"):
    if state == "SUPPLIED":
        return m.L2ConditionsProfileReference(
            state="SUPPLIED", reference=ref("profile"), reason=None
        )
    return m.L2ConditionsProfileReference(
        state="UNAVAILABLE", reference=None, reason="not supplied"
    )


def reference_state(kind="ISOLATED_FROZEN"):
    if kind in ("NOT_APPLICABLE", "UNAVAILABLE"):
        return m.L2ReferenceState(kind=kind, references=(), declaration="explained")
    return m.L2ReferenceState(
        kind=kind, references=(src("reference-state"),), declaration="explained"
    )


def definition(**overrides):
    payload = dict(
        definition_reference=ref("definition"),
        observable_name="observable",
        subject_ids=("p_binder", "p_target"),
        selection_declaration="selection text",
        unit_class="LENGTH",
        unit_symbol="unit",
        conditions_required=True,
        method=method(),
        conditions_profile=profile(),
        reference_state=reference_state(),
        comparability_reference=src("comparability"),
        limitation="limitation text",
    )
    payload.update(overrides)
    return m.L2ObservableDefinition(**payload)


def value(number="1.5"):
    return m.L2DescriptorValue(kind="NUMERIC", number=number, category=None)


def observation(observation_id="o1", **overrides):
    payload = dict(
        observation_id=observation_id,
        pose_id="pose_1",
        sample_id="sample-1",
        replicate_id="replicate-1",
        source_reference=src("observation"),
        value=value(),
        missing_declarations=(),
    )
    payload.update(overrides)
    return m.L2DescriptorObservation(**payload)


def uncertainties(prefix="u"):
    return tuple(
        m.L2UncertaintyRecord(
            uncertainty_id="{0}{1}".format(prefix, position),
            kind=kind,
            state="UNKNOWN",
            observation_ids=(),
            declaration="not quantified",
            source_references=(),
        )
        for position, kind in enumerate(m.L2_UNCERTAINTY_KINDS)
    )


def ambiguity(ambiguity_id="a1", observation_ids=()):
    return m.L2AmbiguityRecord(
        ambiguity_id=ambiguity_id,
        field_paths=("/descriptors/0/observations/0/value",),
        observation_ids=tuple(observation_ids),
        alternatives=(
            m.L2AmbiguityAlternative(declaration="first", source_references=(src("x"),)),
            m.L2AmbiguityAlternative(declaration="second", source_references=()),
        ),
        declaration="ambiguity text",
    )


def conflict(conflict_id="c1", observation_ids=("o1", "o2"), declaration="conflict text"):
    return m.L2ConflictRecord(
        conflict_id=conflict_id,
        observation_ids=tuple(observation_ids),
        comparability_reference=src("conflict-comparability"),
        declaration=declaration,
        declared_by="party-1",
        declared_at=STAMP,
        source_references=(src("conflict-source"),),
    )


def descriptor(descriptor_id="d1", family="LOCAL_OVERLAP", prefix="u", **overrides):
    payload = dict(
        descriptor_id=descriptor_id,
        family=family,
        scope_declaration="scope text",
        definition=definition(),
        observations=(observation(),),
        uncertainties=uncertainties(prefix),
        ambiguities=(),
        conflicts=(),
        missing_declarations=(),
    )
    payload.update(overrides)
    return m.L2DescriptorRecord(**payload)


def availability(family, descriptor_ids, absence_reason=None):
    return m.L2FamilyAvailability(
        family=family,
        descriptor_ids=tuple(descriptor_ids),
        absence_reason=absence_reason,
    )


DEFORMATION = "LOCAL_ISOLATED_REFERENCE_DEFORMATION_BURDEN"


def document(**overrides):
    descriptors = overrides.pop(
        "descriptors",
        (
            descriptor("d1", "LOCAL_OVERLAP", "u"),
            descriptor(
                "d2",
                DEFORMATION,
                "w",
                definition=definition(reference_state=reference_state("ISOLATED_RELAXED")),
                observations=(observation("o2"),),
            ),
        ),
    )
    default_availability = tuple(
        availability(
            family,
            tuple(d.descriptor_id for d in descriptors if d.family == family),
            None
            if any(d.family == family for d in descriptors)
            else "no descriptor supplied",
        )
        for family in m.LAYER_2A_FAMILIES
    )
    payload = dict(
        document_id="doc-1",
        revision="rev-1",
        declared_by="party-1",
        declared_at=STAMP,
        source_references=(src("document"),),
        candidate_anchor=candidate_anchor(),
        scope=scope(),
        poses=(pose(),),
        family_availability=default_availability,
        descriptors=descriptors,
        missing_declarations=(),
    )
    payload.update(overrides)
    return m.Layer2ADescriptorInput(**payload)


def limited_document():
    """One document exercising every condition and every reason code."""
    rich = descriptor(
        "d_all",
        "LOCAL_OVERLAP",
        "u",
        observations=(observation("o1"), observation("o2"), observation("o3")),
        ambiguities=(ambiguity("a1", ("o3",)),),
        conflicts=(conflict("c1", ("o1", "o2")),),
    )
    gap = descriptor(
        "d_gap",
        DEFORMATION,
        "w",
        scope_declaration=None,
        definition=definition(
            limitation=None,
            conditions_profile=profile("UNAVAILABLE"),
            reference_state=reference_state("UNAVAILABLE"),
        ),
        observations=(
            observation("g1", pose_id=None, source_reference=None, value=None),
        ),
    )
    return document(descriptors=(rich, gap))


def conditions_of(doc, index):
    return doc.descriptor_conditions[index]


def reasons_of(doc, index):
    return {reason.code: reason for reason in doc.descriptor_reasons[index]}


# ================================================================================
# 1. Happy path and canonical serialization
# ================================================================================


class HappyPath(unittest.TestCase):
    def test_a_fully_declared_document_is_provided_with_no_reasons(self):
        doc = document()
        self.assertEqual(conditions_of(doc, 0), ("PROVIDED",))
        self.assertEqual(conditions_of(doc, 1), ("PROVIDED",))
        self.assertEqual(doc.descriptor_reasons[0], ())
        self.assertEqual(doc.descriptor_reasons[1], ())

    def test_document_constants_are_derived_not_supplied(self):
        doc = document()
        self.assertEqual(doc.document_type, m.LAYER_2A_DOCUMENT_TYPE)
        self.assertEqual(doc.non_claim, m.LAYER_2A_NON_CLAIM)
        with self.assertRaises(TypeError):
            m.Layer2ADescriptorInput(
                document_id="d",
                revision="r",
                declared_by="p",
                declared_at=STAMP,
                source_references=(),
                candidate_anchor=candidate_anchor(),
                scope=scope(),
                poses=(pose(),),
                family_availability=(),
                descriptors=(),
                missing_declarations=(),
                document_type="other",
            )

    def test_top_level_emission_order(self):
        self.assertEqual(
            list(document().as_dict()),
            [
                "document_type",
                "document_id",
                "revision",
                "declared_by",
                "declared_at",
                "source_references",
                "candidate_anchor",
                "scope",
                "poses",
                "family_availability",
                "descriptors",
                "missing_declarations",
                "non_claim",
            ],
        )

    def test_descriptor_emission_appends_conditions_and_reasons(self):
        payload = document().as_dict()["descriptors"][0]
        self.assertEqual(list(payload)[-2:], ["conditions", "reasons"])

    def test_canonical_bytes_are_stable_and_compact(self):
        first = document().to_json_bytes()
        for _ in range(4):
            self.assertEqual(document().to_json_bytes(), first)
        self.assertEqual(first, canon(json.loads(first.decode("utf-8"))))
        self.assertFalse(first.endswith(b"\n"))
        self.assertFalse(first.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\\/", first)

    def test_object_keys_are_recursively_sorted(self):
        decoded = json.loads(limited_document().to_json_bytes().decode("utf-8"))

        def walk(node):
            if isinstance(node, dict):
                self.assertEqual(list(node), sorted(node))
                for item in node.values():
                    walk(item)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(decoded)

    def test_no_json_numeric_primitive_is_emitted(self):
        decoded = json.loads(limited_document().to_json_bytes().decode("utf-8"))

        def walk(node):
            if isinstance(node, dict):
                for item in node.values():
                    walk(item)
            elif isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, bool):
                pass  # booleans are a declared primitive; ints and floats are not
            else:
                self.assertNotIsInstance(node, (int, float))

        walk(decoded)

    def test_round_trip_from_dict_and_from_bytes(self):
        for build in (document, limited_document):
            with self.subTest(fixture=build.__name__):
                doc = build()
                self.assertEqual(m.Layer2ADescriptorInput.from_dict(doc.as_dict()), doc)
                reloaded = m.Layer2ADescriptorInput.from_json_bytes(doc.to_json_bytes())
                self.assertEqual(reloaded, doc)
                self.assertEqual(reloaded.to_json_bytes(), doc.to_json_bytes())

    def test_bytes_are_stable_across_fresh_processes_and_hash_seeds(self):
        data = limited_document().to_json_bytes()
        script = (
            "import importlib.util, sys\n"
            "spec = importlib.util.spec_from_file_location({0!r}, {1!r})\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "sys.modules[spec.name] = module\n"
            "spec.loader.exec_module(module)\n"
            "payload = sys.stdin.buffer.read()\n"
            "doc = module.Layer2ADescriptorInput.from_json_bytes(payload)\n"
            "sys.stdout.write(doc.to_json_bytes().hex())\n"
        ).format(MODULE_NAME, str(MODULE_PATH))
        for seed in ("0", "1", "12345"):
            with self.subTest(seed=seed):
                environment = dict(os.environ)
                environment["PYTHONHASHSEED"] = seed
                done = subprocess.run(
                    [sys.executable, "-B", "-c", script],
                    input=data,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=environment,
                    check=False,
                )
                self.assertEqual(
                    done.returncode, 0, done.stderr.decode("utf-8", "replace")
                )
                self.assertEqual(done.stdout.decode("ascii"), data.hex())


# ================================================================================
# 2. Derived conditions and reasons
# ================================================================================


class DerivedConditionsAndReasons(unittest.TestCase):
    def setUp(self):
        self.doc = limited_document()

    def test_every_condition_token_is_exercised(self):
        self.assertEqual(
            conditions_of(self.doc, 0), ("PROVIDED", "AMBIGUOUS", "CONTRADICTORY")
        )
        self.assertEqual(conditions_of(self.doc, 1), ("UNAVAILABLE",))
        emitted = set(conditions_of(self.doc, 0)) | set(conditions_of(self.doc, 1))
        self.assertEqual(emitted, set(m.L2_CONDITIONS))

    def test_conditions_follow_vocabulary_order(self):
        for index in range(len(self.doc.descriptors)):
            tokens = list(conditions_of(self.doc, index))
            self.assertEqual(
                tokens, sorted(tokens, key=m.L2_CONDITIONS.index), tokens
            )

    def test_every_reason_code_is_exercised_in_vocabulary_order(self):
        rich = [reason.code for reason in self.doc.descriptor_reasons[0]]
        gap = [reason.code for reason in self.doc.descriptor_reasons[1]]
        self.assertEqual(rich, ["DECLARATION_AMBIGUOUS", "OBSERVATIONS_CONFLICT"])
        self.assertEqual(gap, ["EVIDENCE_NOT_SUPPLIED", "DECLARATION_MISSING"])
        self.assertEqual(set(rich) | set(gap), set(m.L2_REASON_CODES))
        for codes in (rich, gap):
            self.assertEqual(codes, sorted(codes, key=m.L2_REASON_CODES.index))

    def test_at_most_one_reason_per_code(self):
        for index in range(len(self.doc.descriptors)):
            codes = [reason.code for reason in self.doc.descriptor_reasons[index]]
            self.assertEqual(len(codes), len(set(codes)))

    def test_reason_field_paths_are_lexically_sorted_and_unique(self):
        for index in range(len(self.doc.descriptors)):
            for reason in self.doc.descriptor_reasons[index]:
                paths = list(reason.field_paths)
                self.assertTrue(paths, reason.code)
                self.assertEqual(paths, sorted(paths), reason.code)
                self.assertEqual(len(paths), len(set(paths)), reason.code)

    def test_ambiguity_reason_names_its_records_and_observations(self):
        reason = reasons_of(self.doc, 0)["DECLARATION_AMBIGUOUS"]
        self.assertEqual(list(reason.field_paths), ["/descriptors/0/ambiguities/0"])
        self.assertEqual(list(reason.observation_ids), ["o3"])
        self.assertEqual(list(reason.record_ids), ["a1"])

    def test_conflict_reason_names_its_records_and_observations(self):
        reason = reasons_of(self.doc, 0)["OBSERVATIONS_CONFLICT"]
        self.assertEqual(list(reason.field_paths), ["/descriptors/0/conflicts/0"])
        self.assertEqual(list(reason.observation_ids), ["o1", "o2"])
        self.assertEqual(list(reason.record_ids), ["c1"])

    def test_evidence_reason_names_the_valueless_observations(self):
        reason = reasons_of(self.doc, 1)["EVIDENCE_NOT_SUPPLIED"]
        self.assertEqual(
            list(reason.field_paths), ["/descriptors/1/observations/0/value"]
        )
        self.assertEqual(list(reason.observation_ids), ["g1"])
        self.assertEqual(list(reason.record_ids), [])

    def test_declaration_missing_collects_every_unresolved_location(self):
        reason = reasons_of(self.doc, 1)["DECLARATION_MISSING"]
        self.assertEqual(
            list(reason.field_paths),
            [
                "/descriptors/1/definition/conditions_profile",
                "/descriptors/1/definition/limitation",
                "/descriptors/1/definition/reference_state",
                "/descriptors/1/observations/0/pose_id",
                "/descriptors/1/observations/0/source_reference",
                "/descriptors/1/scope_declaration",
            ],
        )
        self.assertEqual(list(reason.observation_ids), ["g1"])

    def test_observation_identifiers_retain_observation_array_order(self):
        rich = descriptor(
            "d_all",
            "LOCAL_OVERLAP",
            "u",
            observations=(observation("o1"), observation("o2"), observation("o3")),
            conflicts=(conflict("c1", ("o3", "o1")),),
        )
        doc = document(descriptors=(rich,))
        reason = reasons_of(doc, 0)["OBSERVATIONS_CONFLICT"]
        self.assertEqual(list(reason.observation_ids), ["o1", "o3"])

    def test_a_descriptor_without_observations_is_unavailable(self):
        doc = document(descriptors=(descriptor("d1", "LOCAL_OVERLAP", "u", observations=()),))
        self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
        reason = reasons_of(doc, 0)["EVIDENCE_NOT_SUPPLIED"]
        self.assertEqual(list(reason.field_paths), ["/descriptors/0/observations"])
        self.assertEqual(list(reason.observation_ids), [])

    def test_unknown_uncertainty_alone_does_not_remove_provided_content(self):
        doc = document()
        self.assertEqual(conditions_of(doc, 0), ("PROVIDED",))
        self.assertTrue(
            all(item.state == "UNKNOWN" for item in doc.descriptors[0].uncertainties)
        )

    def test_an_ambiguous_subject_mapping_blocks_qualification(self):
        blurred = participant(
            "p_binder",
            "BINDER",
            mapping_state="AMBIGUOUS",
            mapping_alternatives=(
                mapping_alternative("A"),
                mapping_alternative("B"),
            ),
        )
        doc = document(
            scope=scope(participants=(blurred, participant("p_target", "RECEPTOR")))
        )
        self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE", "AMBIGUOUS"))
        reason = reasons_of(doc, 0)["DECLARATION_AMBIGUOUS"]
        self.assertEqual(
            list(reason.field_paths), ["/scope/participants/0/mapping_state"]
        )

    def test_role_disagreement_without_an_explicit_declaration_is_refused(self):
        with self.assertRaises(Error) as caught:
            document(
                scope=scope(
                    participants=(
                        participant("p_binder", "LIGAND"),
                        participant("p_target", "RECEPTOR"),
                    )
                )
            )
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/scope/binder_participant_id")

    def test_role_disagreement_with_an_explicit_declaration_is_retained(self):
        doc = document(
            scope=scope(
                participants=(
                    participant("p_binder", "LIGAND"),
                    participant("p_target", "RECEPTOR"),
                ),
                missing_declarations=(
                    missing("/scope/binder_participant_id", "role unresolved"),
                ),
            )
        )
        self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
        self.assertIn(
            "/scope/binder_participant_id",
            reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths,
        )
        self.assertEqual(doc.scope.participants[0].role, "LIGAND")

    def test_a_document_level_declaration_records_role_disagreement_too(self):
        doc = document(
            scope=scope(
                participants=(
                    participant("p_binder", "BINDER"),
                    participant("p_target", "LIGAND"),
                )
            ),
            missing_declarations=(
                missing("/scope/target_participant_id", "role unresolved"),
            ),
        )
        self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
        self.assertEqual(doc.scope.participants[1].role, "LIGAND")

    def test_a_scope_relative_pointer_does_not_record_role_disagreement(self):
        with self.assertRaises(Error) as caught:
            document(
                scope=scope(
                    participants=(
                        participant("p_binder", "LIGAND"),
                        participant("p_target", "RECEPTOR"),
                    ),
                    missing_declarations=(
                        missing("/binder_participant_id", "role unresolved"),
                    ),
                )
            )
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/scope/binder_participant_id")

    def test_a_document_level_missing_declaration_blocks_qualification(self):
        doc = document(missing_declarations=(missing("/scope", "unresolved"),))
        self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
        self.assertIn(
            "/scope",
            reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths,
        )

    def test_supplied_derived_conditions_must_agree(self):
        payload = limited_document().as_dict()
        payload["descriptors"][0]["conditions"] = ["PROVIDED"]
        with self.assertRaises(Error) as caught:
            m.Layer2ADescriptorInput.from_dict(payload)
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/descriptors/0/conditions")
        self.assertEqual(caught.exception.index, 0)

    def test_supplied_derived_reasons_must_agree(self):
        payload = limited_document().as_dict()
        payload["descriptors"][1]["reasons"][0]["field_paths"] = ["/descriptors/1"]
        with self.assertRaises(Error) as caught:
            m.Layer2ADescriptorInput.from_dict(payload)
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/descriptors/1/reasons")

    def test_a_conflict_without_two_qualifying_observations_is_refused(self):
        rich = descriptor(
            "d_all",
            "LOCAL_OVERLAP",
            "u",
            observations=(observation("o1"), observation("o2", value=None)),
            conflicts=(conflict("c1", ("o1", "o2")),),
        )
        with self.assertRaises(Error) as caught:
            document(descriptors=(rich,))
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(
            caught.exception.field, "/descriptors/0/conflicts/0/observation_ids"
        )


# ================================================================================
# 3. Primitive spellings
# ================================================================================


class Primitives(unittest.TestCase):
    def test_identifier_spelling(self):
        for value_text in ("", " x", "x ", "a\u0000b"):
            with self.subTest(value=repr(value_text)):
                with self.assertRaises(Error) as caught:
                    ref(identifier=value_text)
                self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")
                self.assertEqual(caught.exception.field, "/identifier")

    def test_identifiers_are_not_normalized(self):
        self.assertEqual(ref(identifier="MiXeD").identifier, "MiXeD")

    def test_pointer_spelling(self):
        m.L2MissingDeclaration(field="", reason="root")
        m.L2MissingDeclaration(field="/a~0b/c~1d", reason="escaped")
        for bad in ("relative", "/a~", "/a~2", "~0"):
            with self.subTest(value=bad):
                with self.assertRaises(Error) as caught:
                    m.L2MissingDeclaration(field=bad, reason="x")
                self.assertEqual(caught.exception.field, "/field")

    def test_timestamp_spelling(self):
        for bad in (
            "2026-09-28T09:15:00",
            "2026-09-28T09:15:00.5Z",
            "2026-09-28T09:15:00+00:00",
            "2026-02-30T00:00:00Z",
            "2026-13-01T00:00:00Z",
            "2026-09-28T24:00:00Z",
        ):
            with self.subTest(value=bad):
                with self.assertRaises(Error) as caught:
                    m.L2ConflictRecord(
                        conflict_id="c",
                        observation_ids=("o1", "o2"),
                        comparability_reference=src(),
                        declaration="d",
                        declared_by="p",
                        declared_at=bad,
                        source_references=(),
                    )
                self.assertEqual(caught.exception.field, "/declared_at")
        self.assertEqual(
            m.L2ConflictRecord(
                conflict_id="c",
                observation_ids=("o1", "o2"),
                comparability_reference=src(),
                declaration="d",
                declared_by="p",
                declared_at="0000-02-29T00:00:00Z",
                source_references=(),
            ).declared_at,
            "0000-02-29T00:00:00Z",
        )

    def test_decimal_spelling_accepts_exact_finite_decimals(self):
        for good in ("0", "-1", "1.5", "0.125", "-0.5", "1234567890123456789"):
            with self.subTest(value=good):
                self.assertEqual(value(good).number, good)

    def test_decimal_spelling_refuses_noncanonical_forms(self):
        for bad in (
            "",
            "+1",
            "01",
            "1.",
            "1.10",
            "1.0",
            "-0",
            "-0.0",
            "1e5",
            " 1",
            "NaN",
            "Infinity",
            ".5",
        ):
            with self.subTest(value=bad):
                with self.assertRaises(Error) as caught:
                    value(bad)
                self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")
                self.assertEqual(caught.exception.field, "/number")

    def test_boolean_must_be_a_real_boolean(self):
        with self.assertRaises(Error) as caught:
            definition(conditions_required=1)
        self.assertEqual(caught.exception.field, "/conditions_required")

    def test_content_hash_anchor_spelling(self):
        for bad in ("A" * 64, "a" * 63, "g" * 64):
            with self.subTest(digest=bad[:2] + str(len(bad))):
                with self.assertRaises(Error) as caught:
                    anchor(bad)
                self.assertEqual(caught.exception.field, "/digest")
        with self.assertRaises(Error) as caught:
            m.L2ArtifactAnchor(
                kind="CONTENT_HASH",
                algorithm="sha512",
                digest=DIGEST,
                snapshot_reference=None,
            )
        self.assertEqual(caught.exception.field, "/algorithm")

    def test_immutable_snapshot_anchor_spelling(self):
        self.assertEqual(snapshot_anchor().kind, "IMMUTABLE_SNAPSHOT")
        with self.assertRaises(Error) as caught:
            m.L2ArtifactAnchor(
                kind="IMMUTABLE_SNAPSHOT",
                algorithm="sha256",
                digest=None,
                snapshot_reference=ref(),
            )
        self.assertEqual(caught.exception.field, "/algorithm")
        with self.assertRaises(Error) as caught:
            m.L2ArtifactAnchor(
                kind="IMMUTABLE_SNAPSHOT",
                algorithm=None,
                digest=None,
                snapshot_reference=None,
            )
        self.assertEqual(caught.exception.field, "/snapshot_reference")

    def test_an_immutable_reference_needs_a_revision_or_snapshot(self):
        with self.assertRaises(Error) as caught:
            m.L2ImmutableReference(
                namespace="ns", identifier="id", revision=None, snapshot_reference=None
            )
        self.assertEqual(caught.exception.field, "/revision")

    def test_an_unknown_vocabulary_token_is_refused(self):
        with self.assertRaises(Error) as caught:
            participant(role="COFACTOR")
        self.assertEqual(caught.exception.field, "/role")


# ================================================================================
# 4. State and cardinality invariants
# ================================================================================


class StateCardinality(unittest.TestCase):
    def test_mapping_state_cardinality(self):
        self.assertEqual(len(participant().mapping_alternatives), 1)
        with self.assertRaises(Error):
            participant(mapping_state="SUPPLIED", mapping_alternatives=())
        with self.assertRaises(Error):
            participant(
                mapping_state="ABSENT", mapping_alternatives=(mapping_alternative(),)
            )
        with self.assertRaises(Error) as caught:
            participant(
                mapping_state="AMBIGUOUS", mapping_alternatives=(mapping_alternative(),)
            )
        self.assertEqual(caught.exception.field, "/mapping_alternatives")
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")

    def test_duplicate_mapping_alternatives_are_refused(self):
        with self.assertRaises(Error) as caught:
            participant(
                mapping_state="AMBIGUOUS",
                mapping_alternatives=(mapping_alternative(), mapping_alternative()),
            )
        self.assertEqual(caught.exception.field, "/mapping_alternatives/1")
        self.assertEqual(caught.exception.index, 1)
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")

    def test_conditions_profile_agreement(self):
        with self.assertRaises(Error) as caught:
            m.L2ConditionsProfileReference(state="SUPPLIED", reference=None, reason=None)
        self.assertEqual(caught.exception.field, "/reference")
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        with self.assertRaises(Error) as caught:
            m.L2ConditionsProfileReference(
                state="SUPPLIED", reference=ref(), reason="why"
            )
        self.assertEqual(caught.exception.field, "/reason")
        with self.assertRaises(Error) as caught:
            m.L2ConditionsProfileReference(
                state="UNAVAILABLE", reference=None, reason=None
            )
        self.assertEqual(caught.exception.field, "/reason")
        with self.assertRaises(Error) as caught:
            m.L2ConditionsProfileReference(
                state="UNAVAILABLE", reference=ref(), reason="why"
            )
        self.assertEqual(caught.exception.field, "/reference")

    def test_reference_state_agreement(self):
        with self.assertRaises(Error) as caught:
            m.L2ReferenceState(
                kind="NOT_APPLICABLE", references=(src(),), declaration="d"
            )
        self.assertEqual(caught.exception.field, "/references")
        with self.assertRaises(Error) as caught:
            m.L2ReferenceState(kind="ISOLATED_FROZEN", references=(), declaration="d")
        self.assertEqual(caught.exception.field, "/references")

    def test_uncertainty_state_agreement(self):
        with self.assertRaises(Error) as caught:
            m.L2UncertaintyRecord(
                uncertainty_id="u",
                kind="METHOD",
                state="DECLARED",
                observation_ids=(),
                declaration="d",
                source_references=(),
            )
        self.assertEqual(caught.exception.field, "/source_references")

    def test_every_uncertainty_kind_has_exactly_one_record_in_order(self):
        doc = document()
        self.assertEqual(
            tuple(item.kind for item in doc.descriptors[0].uncertainties),
            m.L2_UNCERTAINTY_KINDS,
        )
        reordered = list(uncertainties("u"))
        reordered[0], reordered[1] = reordered[1], reordered[0]
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor("d1", "LOCAL_OVERLAP", "u", uncertainties=tuple(reordered)),
                )
            )
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/descriptors/0/uncertainties")
        with self.assertRaises(Error):
            document(
                descriptors=(
                    descriptor(
                        "d1", "LOCAL_OVERLAP", "u", uncertainties=uncertainties("u")[:5]
                    ),
                )
            )

    def test_ambiguity_cardinality(self):
        with self.assertRaises(Error) as caught:
            m.L2AmbiguityRecord(
                ambiguity_id="a",
                field_paths=(),
                observation_ids=(),
                alternatives=(
                    m.L2AmbiguityAlternative(declaration="x", source_references=()),
                    m.L2AmbiguityAlternative(declaration="y", source_references=()),
                ),
                declaration="d",
            )
        self.assertEqual(caught.exception.field, "/field_paths")
        with self.assertRaises(Error) as caught:
            m.L2AmbiguityRecord(
                ambiguity_id="a",
                field_paths=("/x",),
                observation_ids=(),
                alternatives=(
                    m.L2AmbiguityAlternative(declaration="x", source_references=()),
                ),
                declaration="d",
            )
        self.assertEqual(caught.exception.field, "/alternatives")

    def test_conflict_requires_two_distinct_observations(self):
        with self.assertRaises(Error) as caught:
            conflict(observation_ids=("o1",))
        self.assertEqual(caught.exception.field, "/observation_ids")
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        with self.assertRaises(Error) as caught:
            conflict(observation_ids=("o1", "o1"))
        self.assertEqual(caught.exception.field, "/observation_ids/1")

    def test_conflicts_on_the_same_observations_must_differ_in_declaration(self):
        rich = descriptor(
            "d_all",
            "LOCAL_OVERLAP",
            "u",
            observations=(observation("o1"), observation("o2")),
            conflicts=(
                conflict("c1", ("o1", "o2"), "same"),
                conflict("c2", ("o2", "o1"), "same"),
            ),
        )
        with self.assertRaises(Error) as caught:
            document(descriptors=(rich,))
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/descriptors/0/conflicts/1")

    def test_admission_absent_keys_order_and_nullity(self):
        self.assertEqual(admission().absent_keys, ("state_result_id",))
        with self.assertRaises(Error) as caught:
            admission(absent=("ineligibility_reason", "state_result_id"))
        self.assertEqual(caught.exception.field, "/absent_keys/1")
        with self.assertRaises(Error) as caught:
            admission(absent=("certificate_present",))
        self.assertEqual(caught.exception.field, "/certificate_present")
        with self.assertRaises(Error) as caught:
            admission(absent=("not_a_field",))
        self.assertEqual(caught.exception.field, "/absent_keys/0")

    def test_method_parameter_names_are_unique(self):
        with self.assertRaises(Error) as caught:
            method(
                parameters=(
                    m.L2NamedDeclaration(name="a", value="1"),
                    m.L2NamedDeclaration(name="a", value="2"),
                )
            )
        self.assertEqual(caught.exception.field, "/parameters/1/name")

    def test_identifier_arrays_refuse_exact_duplicates(self):
        with self.assertRaises(Error) as caught:
            definition(subject_ids=("p_binder", "p_binder"))
        self.assertEqual(caught.exception.field, "/subject_ids/1")

    def test_source_reference_arrays_refuse_exact_duplicates(self):
        with self.assertRaises(Error) as caught:
            m.L2ReferenceState(
                kind="ISOLATED_FROZEN", references=(src(), src()), declaration="d"
            )
        self.assertEqual(caught.exception.field, "/references/1")

    def test_at_most_one_binder_and_one_receptor(self):
        with self.assertRaises(Error) as caught:
            document(
                scope=scope(
                    binder_participant_id="p_binder",
                    target_participant_id="p_target",
                    participants=(
                        participant("p_binder", "BINDER"),
                        participant("p_target", "RECEPTOR"),
                        participant("p_extra", "BINDER"),
                    ),
                )
            )
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/scope/participants")

    def test_optional_contextual_participants_are_permitted(self):
        doc = document(
            scope=scope(
                participants=(
                    participant("p_binder", "BINDER"),
                    participant("p_target", "RECEPTOR"),
                    participant("p_ctx", "CONTEXT"),
                )
            )
        )
        self.assertEqual(len(doc.scope.participants), 3)

    def test_a_descriptor_may_not_duplicate_a_complete_observable_scope(self):
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor("d1", "LOCAL_OVERLAP", "u"),
                    descriptor("d2", "LOCAL_OVERLAP", "w"),
                )
            )
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/descriptors/1/definition")

    def test_descriptors_may_share_a_family_with_different_scopes(self):
        doc = document(
            descriptors=(
                descriptor("d1", "LOCAL_OVERLAP", "u"),
                descriptor(
                    "d2",
                    "LOCAL_OVERLAP",
                    "w",
                    definition=definition(selection_declaration="other selection"),
                ),
            )
        )
        self.assertEqual(
            doc.family_availability[0].descriptor_ids, ("d1", "d2")
        )


# ================================================================================
# 5. Local-family enforcement and availability
# ================================================================================


class LocalFamilyEnforcement(unittest.TestCase):
    def test_only_the_two_local_families_exist(self):
        self.assertEqual(
            m.LAYER_2A_FAMILIES,
            ("LOCAL_OVERLAP", "LOCAL_ISOLATED_REFERENCE_DEFORMATION_BURDEN"),
        )
        self.assertFalse(hasattr(m, "L2_COLLECTIVE_FAMILIES"))
        self.assertFalse(hasattr(m, "Layer2BDescriptorInput"))
        self.assertFalse(hasattr(m, "L2CollectiveScope"))

    def test_a_collective_family_token_is_refused(self):
        for token in (
            "COLLECTIVE_INTERFERENCE",
            "COLLECTIVE_DEFORMATION_RESTRAINT_BURDEN",
            "COLLECTIVE_ANCHOR_LINKER_CONFIGURATION",
        ):
            with self.subTest(token=token):
                with self.assertRaises(Error) as caught:
                    descriptor("d1", token, "u")
                self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")
                self.assertEqual(caught.exception.field, "/family")
                with self.assertRaises(Error):
                    availability(token, ())

    def test_exactly_two_availability_records_in_family_order(self):
        doc = document()
        self.assertEqual(
            tuple(item.family for item in doc.family_availability), m.LAYER_2A_FAMILIES
        )
        with self.assertRaises(Error) as caught:
            document(family_availability=(availability("LOCAL_OVERLAP", ("d1",)),))
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/family_availability")

    def test_availability_order_is_not_repaired(self):
        with self.assertRaises(Error) as caught:
            document(
                family_availability=(
                    availability(DEFORMATION, ("d2",)),
                    availability("LOCAL_OVERLAP", ("d1",)),
                )
            )
        self.assertEqual(caught.exception.field, "/family_availability/0/family")
        self.assertEqual(caught.exception.index, 0)

    def test_availability_lists_exactly_its_family_in_descriptor_order(self):
        with self.assertRaises(Error) as caught:
            document(
                family_availability=(
                    availability("LOCAL_OVERLAP", (), "declared absent"),
                    availability(DEFORMATION, ("d2",)),
                )
            )
        self.assertEqual(caught.exception.field, "/family_availability/0/descriptor_ids")

    def test_an_empty_family_requires_a_reason(self):
        doc = document(descriptors=(descriptor("d1", "LOCAL_OVERLAP", "u"),))
        self.assertEqual(doc.family_availability[1].descriptor_ids, ())
        self.assertEqual(
            doc.family_availability[1].absence_reason, "no descriptor supplied"
        )
        with self.assertRaises(Error) as caught:
            availability("LOCAL_OVERLAP", ())
        self.assertEqual(caught.exception.field, "/absence_reason")
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        with self.assertRaises(Error) as caught:
            availability("LOCAL_OVERLAP", ("d1",), "reason")
        self.assertEqual(caught.exception.field, "/absence_reason")

    def test_local_family_permits_only_numeric_values(self):
        categorical = observation(
            "o1", value=m.L2DescriptorValue(kind="CATEGORICAL", number=None, category="x")
        )
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor("d1", "LOCAL_OVERLAP", "u", observations=(categorical,)),
                )
            )
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(
            caught.exception.field, "/descriptors/0/observations/0/value/kind"
        )

    def test_a_numeric_value_requires_unit_class_and_symbol(self):
        for name in ("unit_class", "unit_symbol"):
            with self.subTest(field=name):
                with self.assertRaises(Error) as caught:
                    document(
                        descriptors=(
                            descriptor(
                                "d1",
                                "LOCAL_OVERLAP",
                                "u",
                                definition=definition(**{name: None}),
                            ),
                        )
                    )
                self.assertEqual(
                    caught.exception.field, "/descriptors/0/definition/" + name
                )

    def test_the_deformation_family_requires_conditions_and_a_local_reference_state(self):
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor(
                        "d2",
                        DEFORMATION,
                        "w",
                        definition=definition(conditions_required=False),
                    ),
                )
            )
        self.assertEqual(
            caught.exception.field, "/descriptors/0/definition/conditions_required"
        )
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor(
                        "d2",
                        DEFORMATION,
                        "w",
                        definition=definition(
                            reference_state=reference_state("ASSEMBLY_REFERENCE")
                        ),
                    ),
                )
            )
        self.assertEqual(
            caught.exception.field, "/descriptors/0/definition/reference_state/kind"
        )


# ================================================================================
# 6. Internal reference resolution and identity
# ================================================================================


class ReferencesAndIdentity(unittest.TestCase):
    def test_a_dangling_pose_reference_is_refused(self):
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor(
                        "d1",
                        "LOCAL_OVERLAP",
                        "u",
                        observations=(observation("o1", pose_id="absent"),),
                    ),
                )
            )
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
        self.assertEqual(caught.exception.field, "/descriptors/0/observations/0/pose_id")

    def test_a_dangling_subject_reference_is_refused(self):
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor(
                        "d1",
                        "LOCAL_OVERLAP",
                        "u",
                        definition=definition(subject_ids=("absent",)),
                    ),
                )
            )
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
        self.assertEqual(
            caught.exception.field, "/descriptors/0/definition/subject_ids/0"
        )

    def test_a_dangling_observation_reference_is_refused(self):
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor(
                        "d1",
                        "LOCAL_OVERLAP",
                        "u",
                        ambiguities=(ambiguity("a1", ("absent",)),),
                    ),
                )
            )
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
        self.assertEqual(
            caught.exception.field, "/descriptors/0/ambiguities/0/observation_ids/0"
        )

    def test_a_dangling_scope_participant_reference_is_refused(self):
        with self.assertRaises(Error) as caught:
            document(scope=scope(binder_participant_id="absent"))
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
        self.assertEqual(caught.exception.field, "/scope/binder_participant_id")

    def test_duplicate_participant_identifiers_are_refused(self):
        with self.assertRaises(Error) as caught:
            document(
                scope=scope(
                    participants=(
                        participant("p_binder", "BINDER"),
                        participant("p_binder", "RECEPTOR"),
                    ),
                    target_participant_id="p_binder",
                )
            )
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
        self.assertEqual(
            caught.exception.field, "/scope/participants/1/participant_id"
        )

    def test_duplicate_descriptor_identifiers_are_refused(self):
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor("d1", "LOCAL_OVERLAP", "u"),
                    descriptor(
                        "d1",
                        DEFORMATION,
                        "w",
                        definition=definition(
                            reference_state=reference_state("ISOLATED_RELAXED")
                        ),
                    ),
                )
            )
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/descriptors/1/descriptor_id")

    def test_descriptor_record_identifiers_share_one_namespace(self):
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor(
                        "d1",
                        "LOCAL_OVERLAP",
                        "u",
                        ambiguities=(ambiguity("o1", ()),),
                    ),
                )
            )
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(
            caught.exception.field, "/descriptors/0/ambiguities/0/ambiguity_id"
        )

    def test_admission_candidate_identity_must_agree(self):
        with self.assertRaises(Error) as caught:
            document(
                candidate_anchor=candidate_anchor(
                    candidate_id="other", admission_reference=admission("cand-1")
                )
            )
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
        self.assertEqual(caught.exception.field, "/candidate_anchor/candidate_id")
        with self.assertRaises(Error) as caught:
            document(
                candidate_anchor=candidate_anchor(
                    candidate_id=None, admission_reference=admission("cand-1")
                )
            )
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")

    def test_pose_association_must_equal_the_scope_association(self):
        with self.assertRaises(Error) as caught:
            document(poses=(pose(association_reference=association("other")),))
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
        self.assertEqual(caught.exception.field, "/poses/0/association_reference")

    def test_a_null_candidate_reference_remains_serializable(self):
        doc = document(
            candidate_anchor=candidate_anchor(
                candidate_id=None,
                scenario_id=None,
                admission_reference=None,
                batch_report_reference=None,
                priority_report_reference=None,
                scenario_comparison_reference=None,
                evaluation_run_ref=None,
            )
        )
        self.assertIsNone(doc.candidate_anchor.candidate_id)
        self.assertEqual(
            m.Layer2ADescriptorInput.from_json_bytes(doc.to_json_bytes()), doc
        )


# ================================================================================
# 7. Loading refusals
# ================================================================================


class LoadingRefusals(unittest.TestCase):
    def setUp(self):
        self.payload = document().as_dict()

    def load(self, payload):
        return m.Layer2ADescriptorInput.from_json_bytes(canon(payload))

    def mutated(self, mutate):
        payload = copy.deepcopy(self.payload)
        mutate(payload)
        return payload

    def test_the_baseline_payload_loads(self):
        self.assertIsNotNone(self.load(self.payload))

    def test_unknown_fields_are_refused_at_every_depth(self):
        cases = {
            "/surprise": lambda p: p.__setitem__("surprise", "x"),
            "/scope/surprise": lambda p: p["scope"].__setitem__("surprise", "x"),
            "/descriptors/0/definition/method/surprise": (
                lambda p: p["descriptors"][0]["definition"]["method"].__setitem__(
                    "surprise", "x"
                )
            ),
        }
        for expected, mutate in cases.items():
            with self.subTest(path=expected):
                with self.assertRaises(Error) as caught:
                    self.load(self.mutated(mutate))
                self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")
                self.assertEqual(caught.exception.field, expected)

    def test_missing_keys_are_not_filled(self):
        with self.assertRaises(Error) as caught:
            self.load(self.mutated(lambda p: p["scope"].pop("target_site_declaration")))
        self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")
        self.assertEqual(caught.exception.field, "/scope/target_site_declaration")

    def test_duplicate_json_keys_are_refused_at_every_depth(self):
        text = canon(self.payload).decode("utf-8")
        for needle, injected in (
            ('"document_id":"doc-1"', '"document_id":"doc-1","document_id":"x"'),
            ('"slot_id":"slot_1"', '"slot_id":"slot_1","slot_id":"slot_2"'),
        ):
            with self.subTest(needle=needle):
                with self.assertRaises(Error) as caught:
                    m.Layer2ADescriptorInput.from_json_bytes(
                        text.replace(needle, injected, 1).encode("utf-8")
                    )
                self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")
                self.assertIn("duplicate JSON object key", caught.exception.message)

    def test_modified_document_constants_are_refused(self):
        for key in ("document_type", "non_claim"):
            with self.subTest(key=key):
                with self.assertRaises(Error) as caught:
                    self.load(
                        self.mutated(
                            lambda p, name=key: p.__setitem__(name, p[name] + "!")
                        )
                    )
                self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")
                self.assertEqual(caught.exception.field, "/" + key)

    def test_a_json_numeric_primitive_is_refused(self):
        text = canon(self.payload).decode("utf-8").replace('"1.5"', "1.5", 1)
        with self.assertRaises(Error) as caught:
            m.Layer2ADescriptorInput.from_json_bytes(text.encode("utf-8"))
        self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")

    def test_noncanonical_bytes_are_refused_after_validation(self):
        variants = {
            "indented": json.dumps(self.payload, sort_keys=True, indent=2).encode("utf-8"),
            "spaced": json.dumps(
                self.payload, sort_keys=True, separators=(", ", ": ")
            ).encode("utf-8"),
            "unsorted": json.dumps(
                self.payload, sort_keys=False, separators=(",", ":")
            ).encode("utf-8"),
            "trailing_newline": canon(self.payload) + b"\n",
            "byte_order_mark": b"\xef\xbb\xbf" + canon(self.payload),
        }
        for name, data in variants.items():
            with self.subTest(variant=name):
                with self.assertRaises(Error) as caught:
                    m.Layer2ADescriptorInput.from_json_bytes(data)
                self.assertEqual(caught.exception.code, "NON_CANONICAL_BYTES")

    def test_a_structural_fault_outranks_noncanonical_bytes(self):
        payload = self.mutated(lambda p: p.__setitem__("document_id", ""))
        data = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
        with self.assertRaises(Error) as caught:
            m.Layer2ADescriptorInput.from_json_bytes(data)
        self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")

    def test_the_error_exposes_code_field_index_and_message(self):
        with self.assertRaises(Error) as caught:
            self.load(
                self.mutated(
                    lambda p: p["descriptors"][0]["observations"][0].__setitem__(
                        "pose_id", "absent"
                    )
                )
            )
        error = caught.exception
        self.assertEqual(error.code, "REFERENCE_INVALID")
        self.assertEqual(error.field, "/descriptors/0/observations/0/pose_id")
        self.assertEqual(error.index, 0)
        self.assertIsInstance(error.message, str)
        self.assertIn(error.code, m.L2_ERROR_CODES)

    def test_the_index_is_the_outermost_array_position(self):
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor("d1", "LOCAL_OVERLAP", "u"),
                    descriptor(
                        "d2",
                        DEFORMATION,
                        "w",
                        definition=definition(
                            reference_state=reference_state("ISOLATED_RELAXED")
                        ),
                        observations=(observation("o2", pose_id="absent"),),
                    ),
                )
            )
        self.assertEqual(caught.exception.field, "/descriptors/1/observations/0/pose_id")
        self.assertEqual(caught.exception.index, 1)

    def test_a_root_level_fault_has_a_null_index(self):
        with self.assertRaises(Error) as caught:
            m.Layer2ADescriptorInput.from_json_bytes(b"not json")
        self.assertEqual(caught.exception.field, "")
        self.assertIsNone(caught.exception.index)


# ================================================================================
# 8. Detachment and immutability
# ================================================================================


class DetachmentAndImmutability(unittest.TestCase):
    def setUp(self):
        self.doc = limited_document()

    def test_as_dict_returns_a_fresh_structure_every_call(self):
        first = self.doc.as_dict()
        second = self.doc.as_dict()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertIsNot(first["descriptors"], second["descriptors"])
        self.assertIsNot(first["descriptors"][0], second["descriptors"][0])
        self.assertIsNot(first["scope"]["participants"], second["scope"]["participants"])

    def test_mutating_a_returned_structure_cannot_reach_the_document(self):
        baseline = self.doc.to_json_bytes()
        payload = self.doc.as_dict()
        payload["descriptors"].append({"injected": True})
        payload["scope"]["participants"].clear()
        payload["descriptors"][0]["conditions"].clear()
        self.assertEqual(self.doc.to_json_bytes(), baseline)
        self.assertEqual(len(self.doc.as_dict()["descriptors"]), 2)

    def test_every_stored_collection_is_a_tuple(self):
        self.assertIsInstance(self.doc.descriptors, tuple)
        self.assertIsInstance(self.doc.poses, tuple)
        self.assertIsInstance(self.doc.family_availability, tuple)
        self.assertIsInstance(self.doc.descriptor_conditions, tuple)
        self.assertIsInstance(self.doc.descriptor_reasons, tuple)
        self.assertIsInstance(self.doc.scope.participants, tuple)
        self.assertIsInstance(self.doc.descriptors[0].observations, tuple)
        self.assertIsInstance(
            self.doc.descriptors[0].definition.subject_ids, tuple
        )

    def test_a_caller_list_is_copied_rather_than_retained(self):
        instances = [chain_instance("A")]
        alternative = m.L2MappingAlternative(
            pose_id="pose_1", chain_instances=instances, source_reference=None
        )
        instances.append(chain_instance("B"))
        self.assertEqual(len(alternative.chain_instances), 1)

    def test_records_are_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.doc.document_id = "other"
        with self.assertRaises(FrozenInstanceError):
            self.doc.descriptor_conditions = ()
        with self.assertRaises(FrozenInstanceError):
            self.doc.descriptors[0].family = "LOCAL_OVERLAP"


# ================================================================================
# 9. Static and runtime isolation
# ================================================================================


class Isolation(unittest.TestCase):
    ALLOWED_IMPORTS = frozenset({"__future__", "dataclasses", "json"})
    FORBIDDEN_ROOTS = frozenset(
        {
            "os", "sys", "io", "pathlib", "shutil", "tempfile", "glob", "subprocess",
            "multiprocessing", "threading", "socket", "ssl", "urllib", "http",
            "requests", "time", "datetime", "calendar", "random", "secrets", "uuid",
            "hashlib", "hmac", "importlib", "pickle", "ast", "re", "csv", "sqlite3",
            "logging", "argparse", "platform", "getpass", "numpy", "pandas", "scipy",
            "Bio", "nbformat", "gotne", "avidity", "structure_audit", "files",
            "caller_pose_association",
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
        top_level = {
            node for node in self.tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
        }
        nested = [
            node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.Import, ast.ImportFrom)) and node not in top_level
        ]
        self.assertEqual(nested, [])

    def test_no_dynamic_import_or_execution_entry_point(self):
        banned = {"open", "eval", "exec", "compile", "input", "__import__"}
        called = {
            node.func.id
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertEqual(called & banned, set())

    def test_no_filesystem_clock_process_or_network_attribute_appears(self):
        attributes = {
            node.attr for node in ast.walk(self.tree) if isinstance(node, ast.Attribute)
        }
        for banned in (
            "read_text", "read_bytes", "write_text", "write_bytes", "environ",
            "getenv", "now", "utcnow", "monotonic", "run", "Popen", "urlopen",
            "connect", "sha256", "load", "dump",
        ):
            with self.subTest(name=banned):
                self.assertNotIn(banned, attributes)

    def test_the_module_only_uses_json_for_serialization(self):
        used = {
            node.attr
            for node in ast.walk(self.tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "json"
        }
        self.assertEqual(used, {"dumps", "loads"})

    def test_the_module_namespace_holds_no_module_other_than_json(self):
        modules = {
            name: obj
            for name, obj in vars(m).items()
            if isinstance(obj, types.ModuleType)
        }
        self.assertEqual(set(modules), {"json"})

    def test_no_file_is_opened_at_runtime(self):
        original = builtins.open

        def refuse(*args, **kwargs):
            raise AssertionError("the module opened a file")

        builtins.open = refuse
        try:
            doc = limited_document()
            data = doc.to_json_bytes()
            reloaded = m.Layer2ADescriptorInput.from_json_bytes(data)
            self.assertEqual(reloaded, doc)
            with self.assertRaises(Error):
                m.Layer2ADescriptorInput.from_json_bytes(data + b"\n")
        finally:
            builtins.open = original

    def test_importing_the_module_runs_no_package_initializer(self):
        script = (
            "import importlib.util, sys\n"
            "before = set(sys.modules)\n"
            "spec = importlib.util.spec_from_file_location({0!r}, {1!r})\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "sys.modules[spec.name] = module\n"
            "spec.loader.exec_module(module)\n"
            "sys.stdout.write(repr(sorted(set(sys.modules) - before)))\n"
        ).format(MODULE_NAME, str(MODULE_PATH))
        done = subprocess.run(
            [sys.executable, "-B", "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        added = done.stdout.decode("utf-8")
        for banned in ("gotne", "avidity", "structure_audit", "files."):
            self.assertNotIn(banned, added)


# ================================================================================
# 10. Error-code classification
# ================================================================================


class ErrorCodeClassification(unittest.TestCase):
    """Cardinality, ordering, duplicate and pairing rules report INVARIANT_INVALID."""

    def assert_code(self, expected, call):
        with self.assertRaises(Error) as caught:
            call()
        self.assertEqual(caught.exception.code, expected)

    def test_record_level_cardinality_rules_are_invariant_faults(self):
        cases = {
            "minimum_alternatives": lambda: participant(
                mapping_state="AMBIGUOUS", mapping_alternatives=(mapping_alternative(),)
            ),
            "supplied_alternative_count": lambda: participant(
                mapping_state="SUPPLIED", mapping_alternatives=()
            ),
            "absent_alternative_count": lambda: participant(
                mapping_state="ABSENT", mapping_alternatives=(mapping_alternative(),)
            ),
            "duplicate_alternatives": lambda: participant(
                mapping_state="AMBIGUOUS",
                mapping_alternatives=(mapping_alternative(), mapping_alternative()),
            ),
            "duplicate_identifier_array": lambda: definition(
                subject_ids=("p_binder", "p_binder")
            ),
            "duplicate_source_array": lambda: m.L2ReferenceState(
                kind="ISOLATED_FROZEN",
                references=(src("same"), src("same")),
                declaration="explained",
            ),
            "reference_state_minimum": lambda: m.L2ReferenceState(
                kind="ISOLATED_FROZEN", references=(), declaration="explained"
            ),
            "reference_state_emptiness": lambda: m.L2ReferenceState(
                kind="UNAVAILABLE", references=(src("x"),), declaration="explained"
            ),
            "conditions_profile_pairing": lambda: m.L2ConditionsProfileReference(
                state="SUPPLIED", reference=None, reason=None
            ),
            "value_kind_pairing": lambda: m.L2DescriptorValue(
                kind="NUMERIC", number=None, category="text"
            ),
            "uncertainty_source_minimum": lambda: m.L2UncertaintyRecord(
                uncertainty_id="u",
                kind="METHOD",
                state="DECLARED",
                observation_ids=(),
                declaration="declared",
                source_references=(),
            ),
            "ambiguity_field_paths": lambda: m.L2AmbiguityRecord(
                ambiguity_id="a",
                field_paths=(),
                observation_ids=(),
                alternatives=(
                    m.L2AmbiguityAlternative(declaration="one", source_references=()),
                    m.L2AmbiguityAlternative(declaration="two", source_references=()),
                ),
                declaration="text",
            ),
            "ambiguity_alternatives": lambda: ambiguity_with_one_alternative(),
            "conflict_minimum": lambda: conflict("c", ("o1",)),
            "parameter_name_duplicates": lambda: method(
                parameters=(
                    m.L2NamedDeclaration(name="p", value="a"),
                    m.L2NamedDeclaration(name="p", value="b"),
                )
            ),
            "availability_empty_needs_reason": lambda: availability(
                "LOCAL_OVERLAP", ()
            ),
            "availability_listed_needs_null_reason": lambda: availability(
                "LOCAL_OVERLAP", ("d1",), "reason"
            ),
            "immutable_reference_minimum": lambda: m.L2ImmutableReference(
                namespace="ns", identifier="id", revision=None, snapshot_reference=None
            ),
            "anchor_kind_pairing": lambda: m.L2ArtifactAnchor(
                kind="CONTENT_HASH",
                algorithm="sha256",
                digest=DIGEST,
                snapshot_reference=ref("snap"),
            ),
            "absent_keys_order": lambda: admission(
                absent=("ineligibility_reason", "state_result_id")
            ),
            "absent_keys_nullity": lambda: m.L2AdmissionReference(
                candidate_id="cand-1",
                slot_binding_hash="hash-1",
                state_result_id=None,
                ineligibility_reason=None,
                certificate_present=True,
                absent_keys=("certificate_present",),
            ),
        }
        for name, call in cases.items():
            with self.subTest(rule=name):
                self.assert_code("INVARIANT_INVALID", call)

    def test_shape_and_spelling_rules_stay_structural_faults(self):
        cases = {
            "identifier_spelling": lambda: ref(identifier=" x"),
            "text_emptiness": lambda: missing("/scope", ""),
            "unknown_token": lambda: participant(role="ANTIBODY"),
            "timestamp_spelling": lambda: conflict_with_timestamp("2026-13-01T00:00:00Z"),
            "decimal_spelling": lambda: value("1e5"),
            "boolean_type": lambda: definition(conditions_required="true"),
            "pointer_spelling": lambda: missing("scope", "unresolved"),
            "wrong_record_type": lambda: definition(method=profile()),
            "not_an_array": lambda: definition(subject_ids="p_binder"),
            "content_hash_algorithm_spelling": lambda: m.L2ArtifactAnchor(
                kind="CONTENT_HASH",
                algorithm="SHA256",
                digest=DIGEST,
                snapshot_reference=None,
            ),
            "content_hash_digest_spelling": lambda: anchor(digest="A" * 64),
        }
        for name, call in cases.items():
            with self.subTest(rule=name):
                self.assert_code("STRUCTURAL_INVALID", call)


def ambiguity_with_one_alternative():
    return m.L2AmbiguityRecord(
        ambiguity_id="a",
        field_paths=("/descriptors/0/observations/0/value",),
        observation_ids=(),
        alternatives=(
            m.L2AmbiguityAlternative(declaration="only", source_references=()),
        ),
        declaration="text",
    )


def conflict_with_timestamp(stamp):
    return m.L2ConflictRecord(
        conflict_id="c",
        observation_ids=("o1", "o2"),
        comparability_reference=src(),
        declaration="text",
        declared_by="party",
        declared_at=stamp,
        source_references=(),
    )


# ================================================================================
# 11. Traversal precedence
# ================================================================================


class TraversalPrecedence(unittest.TestCase):
    """The first fault follows declared top-level field order, then nested order."""

    def setUp(self):
        self.payload = document().as_dict()

    def faulty(self, *mutations):
        payload = copy.deepcopy(self.payload)
        for mutate in mutations:
            mutate(payload)
        return payload

    def first_fault(self, payload):
        with self.assertRaises(Error) as caught:
            m.Layer2ADescriptorInput.from_dict(payload)
        return caught.exception

    def test_a_scalar_fault_precedes_a_later_nested_fault(self):
        error = self.first_fault(
            self.faulty(
                lambda p: p.__setitem__("document_id", ""),
                lambda p: p["scope"].__setitem__("slot_id", "slot_9"),
                lambda p: p["descriptors"][0].__setitem__("family", "COLLECTIVE_INTERFERENCE"),
            )
        )
        self.assertEqual(error.field, "/document_id")

    def test_the_document_type_constant_precedes_every_other_fault(self):
        error = self.first_fault(
            self.faulty(
                lambda p: p.__setitem__("document_type", "layer_2b_descriptor_input/1"),
                lambda p: p.__setitem__("document_id", ""),
            )
        )
        self.assertEqual(error.field, "/document_type")

    def test_scalars_are_reported_in_their_declared_order(self):
        for earlier, later in (
            ("document_id", "revision"),
            ("revision", "declared_by"),
            ("declared_by", "declared_at"),
        ):
            with self.subTest(earlier=earlier, later=later):
                error = self.first_fault(
                    self.faulty(
                        lambda p, key=earlier: p.__setitem__(key, ""),
                        lambda p, key=later: p.__setitem__(
                            key, "" if key != "declared_at" else "not-a-timestamp"
                        ),
                    )
                )
                self.assertEqual(error.field, "/" + earlier)

    def test_a_timestamp_fault_precedes_a_nested_scope_fault(self):
        error = self.first_fault(
            self.faulty(
                lambda p: p.__setitem__("declared_at", "2026-13-01T00:00:00Z"),
                lambda p: p["scope"].__setitem__("slot_id", "slot_9"),
            )
        )
        self.assertEqual(error.field, "/declared_at")

    def test_nested_fields_keep_their_declared_order(self):
        error = self.first_fault(
            self.faulty(
                lambda p: p["scope"].__setitem__("slot_id", "slot_9"),
                lambda p: p["descriptors"][0].__setitem__("descriptor_id", ""),
            )
        )
        self.assertEqual(error.field, "/scope/slot_id")

    def test_a_valid_document_with_a_byte_order_mark_is_noncanonical(self):
        data = b"\xef\xbb\xbf" + canon(self.payload)
        with self.assertRaises(Error) as caught:
            m.Layer2ADescriptorInput.from_json_bytes(data)
        self.assertEqual(caught.exception.code, "NON_CANONICAL_BYTES")

    def test_a_byte_order_mark_does_not_hide_a_structural_fault(self):
        payload = self.faulty(lambda p: p.__setitem__("document_id", ""))
        data = b"\xef\xbb\xbf" + canon(payload)
        with self.assertRaises(Error) as caught:
            m.Layer2ADescriptorInput.from_json_bytes(data)
        self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")
        self.assertEqual(caught.exception.field, "/document_id")

    def test_a_byte_order_mark_does_not_hide_an_invariant_fault(self):
        payload = self.faulty(
            lambda p: p["family_availability"][0].__setitem__("descriptor_ids", [])
        )
        data = b"\xef\xbb\xbf" + canon(payload)
        with self.assertRaises(Error) as caught:
            m.Layer2ADescriptorInput.from_json_bytes(data)
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")


# ================================================================================
# 12. Applicability of missing declarations and mixed value availability
# ================================================================================


class ApplicabilityAndMixedValues(unittest.TestCase):
    def test_a_descriptor_declaration_does_not_block_a_sibling_descriptor(self):
        flagged = descriptor(
            "d1",
            "LOCAL_OVERLAP",
            "u",
            missing_declarations=(
                missing("/descriptors/0/scope_declaration", "unresolved"),
            ),
        )
        clean = descriptor(
            "d2",
            DEFORMATION,
            "w",
            definition=definition(reference_state=reference_state("ISOLATED_RELAXED")),
            observations=(observation("o2"),),
        )
        doc = document(descriptors=(flagged, clean))
        self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
        self.assertEqual(conditions_of(doc, 1), ("PROVIDED",))
        self.assertNotIn("DECLARATION_MISSING", reasons_of(doc, 1))

    def test_an_observation_declaration_does_not_block_a_sibling_observation(self):
        mixed = descriptor(
            "d1",
            "LOCAL_OVERLAP",
            "u",
            observations=(
                observation(
                    "o1",
                    missing_declarations=(
                        missing("/descriptors/0/observations/0/pose_id", "unresolved"),
                    ),
                ),
                observation("o2"),
            ),
        )
        doc = document(descriptors=(mixed,))
        self.assertEqual(conditions_of(doc, 0), ("PROVIDED",))
        reason = reasons_of(doc, 0)["DECLARATION_MISSING"]
        self.assertEqual(list(reason.observation_ids), ["o1"])

    def test_a_valueless_observation_does_not_hide_a_valued_sibling(self):
        mixed = descriptor(
            "d1",
            "LOCAL_OVERLAP",
            "u",
            observations=(
                observation("o1"),
                observation("o2", value=None),
                observation("o3"),
            ),
        )
        doc = document(descriptors=(mixed,))
        self.assertEqual(conditions_of(doc, 0), ("PROVIDED",))
        codes = [reason.code for reason in doc.descriptor_reasons[0]]
        self.assertEqual(codes, ["EVIDENCE_NOT_SUPPLIED"])
        reason = reasons_of(doc, 0)["EVIDENCE_NOT_SUPPLIED"]
        self.assertEqual(list(reason.observation_ids), ["o2"])
        self.assertEqual(
            list(reason.field_paths), ["/descriptors/0/observations/1/value"]
        )
        self.assertEqual(list(reason.record_ids), [])

    def test_valueless_observations_are_named_in_observation_array_order(self):
        mixed = descriptor(
            "d1",
            "LOCAL_OVERLAP",
            "u",
            observations=(
                observation("o1", value=None),
                observation("o2"),
                observation("o3", value=None),
            ),
        )
        doc = document(descriptors=(mixed,))
        reason = reasons_of(doc, 0)["EVIDENCE_NOT_SUPPLIED"]
        self.assertEqual(list(reason.observation_ids), ["o1", "o3"])
        self.assertEqual(
            list(reason.field_paths),
            [
                "/descriptors/0/observations/0/value",
                "/descriptors/0/observations/2/value",
            ],
        )

    def test_a_mixed_descriptor_round_trips_with_its_derived_reason(self):
        mixed = descriptor(
            "d1",
            "LOCAL_OVERLAP",
            "u",
            observations=(observation("o1"), observation("o2", value=None)),
        )
        doc = document(descriptors=(mixed,))
        again = m.Layer2ADescriptorInput.from_json_bytes(doc.to_json_bytes())
        self.assertEqual(again.to_json_bytes(), doc.to_json_bytes())
        self.assertEqual(again.descriptor_conditions, doc.descriptor_conditions)
        self.assertEqual(again.descriptor_reasons, doc.descriptor_reasons)


class CoordinatedSemanticAlignment(unittest.TestCase):
    COLLECTIVE = False

    def one(self, **overrides):
        return document(descriptors=(descriptor(),), **overrides)

    def assert_wire(self, doc):
        cls = type(doc)
        self.assertEqual(cls.from_json_bytes(doc.to_json_bytes()).to_json_bytes(), doc.to_json_bytes())
        self.assertEqual(cls.from_dict(doc.as_dict()).as_dict(), doc.as_dict())
        payload = doc.as_dict()
        payload["descriptors"][0]["reasons"].append({
            "code": "DECLARATION_MISSING", "field_paths": ["/unasserted"],
            "observation_ids": [], "record_ids": [],
        })
        with self.assertRaises(Error) as caught:
            cls.from_json_bytes(canon(payload))
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/descriptors/0/reasons")
        payload = doc.as_dict()
        payload["descriptors"][0]["conditions"] = (
            ["UNAVAILABLE"] if "PROVIDED" in conditions_of(doc, 0) else ["PROVIDED"]
        )
        with self.assertRaises(Error) as caught:
            cls.from_dict(payload)
        self.assertEqual(caught.exception.field, "/descriptors/0/conditions")

    def mapped_scope(self, alternative):
        original = scope()
        subjects = list(original.participants)
        subjects[0] = replace(subjects[0], mapping_alternatives=(alternative,))
        return replace(original, participants=tuple(subjects))

    def role_case(self, name):
        original = scope()
        if self.COLLECTIVE:
            identifier = getattr(original.local_associations[0], name)
            pointer = "/scope/local_associations/0/" + name
        else:
            identifier = getattr(original, name)
            pointer = "/scope/" + name
        subjects = tuple(
            replace(p, role="LIGAND") if p.participant_id == identifier else p
            for p in original.participants
        )
        return replace(original, participants=subjects), pointer

    def test_container_applicability_and_original_absolute_attribution(self):
        marker = missing("/descriptors/1/observations/0/value", "caller explanation")
        for container in ("document", "scope", "descriptor", "observation"):
            with self.subTest(container=container):
                first = descriptor(observations=(observation("z"), observation("a")))
                second = replace(
                    descriptor(), descriptor_id="second",
                    definition=replace(definition(), selection_declaration="second selection"),
                )
                kwargs = {}
                if container == "document":
                    kwargs["missing_declarations"] = (marker,)
                elif container == "scope":
                    kwargs["scope"] = replace(scope(), missing_declarations=(marker,))
                elif container == "descriptor":
                    first = replace(first, missing_declarations=(marker,))
                else:
                    first = replace(first, observations=(
                        replace(first.observations[0], missing_declarations=(marker,)),
                        first.observations[1],
                    ))
                doc = document(descriptors=(first, second), **kwargs)
                self.assertEqual(
                    conditions_of(doc, 0),
                    ("PROVIDED",) if container == "observation" else ("UNAVAILABLE",),
                )
                self.assertEqual(
                    conditions_of(doc, 1),
                    ("UNAVAILABLE",) if container in ("document", "scope") else ("PROVIDED",),
                )
                reason = reasons_of(doc, 0)["DECLARATION_MISSING"]
                self.assertEqual(reason.field_paths, (marker.field,))
                self.assertEqual(reason.observation_ids, ("z",) if container == "observation" else ())
                payload = doc.as_dict()
                locations = {
                    "document": payload,
                    "scope": payload["scope"],
                    "descriptor": payload["descriptors"][0],
                    "observation": payload["descriptors"][0]["observations"][0],
                }
                self.assertEqual(locations[container]["missing_declarations"], [marker.as_dict()])
                self.assert_wire(doc)

    def test_nonexistent_and_root_locators_are_retained_without_dependency_analysis(self):
        for pointer in ("", "/nowhere/~0at~1all"):
            with self.subTest(pointer=pointer):
                marker = missing(pointer, "opaque caller locator")
                doc = self.one(missing_declarations=(marker,))
                self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
                self.assertEqual(reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths, (pointer,))
                self.assertEqual(doc.missing_declarations, (marker,))
                self.assert_wire(doc)

    def test_missing_paths_are_unique_sorted_but_input_records_remain_distinct(self):
        markers = (missing("/z", "first"), missing("/a", "second"), missing("/z", "third"))
        doc = self.one(missing_declarations=markers)
        self.assertEqual(doc.missing_declarations, markers)
        self.assertEqual(reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths, ("/a", "/z"))
        self.assertEqual([r.code for r in doc.descriptor_reasons[0]], ["DECLARATION_MISSING"])
        self.assert_wire(doc)

    def test_mixed_values_have_one_evidence_reason_and_no_declaration_gap(self):
        observed = (observation("z", value=None), observation("a"), observation("b", value=None))
        doc = document(descriptors=(descriptor(observations=observed),))
        self.assertEqual(conditions_of(doc, 0), ("PROVIDED",))
        self.assertEqual([r.code for r in doc.descriptor_reasons[0]], ["EVIDENCE_NOT_SUPPLIED"])
        reason = reasons_of(doc, 0)["EVIDENCE_NOT_SUPPLIED"]
        self.assertEqual(reason.observation_ids, ("z", "b"))
        self.assertEqual(reason.field_paths, (
            "/descriptors/0/observations/0/value", "/descriptors/0/observations/2/value",
        ))
        self.assertEqual(reason.record_ids, ())
        self.assert_wire(doc)

    def test_all_valueless_and_empty_observations_remain_unavailable(self):
        for observed in ((), (observation("z", value=None), observation("a", value=None))):
            with self.subTest(count=len(observed)):
                doc = document(descriptors=(descriptor(observations=observed),))
                self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
                self.assertEqual([r.code for r in doc.descriptor_reasons[0]], ["EVIDENCE_NOT_SUPPLIED"])
                self.assertEqual(
                    reasons_of(doc, 0)["EVIDENCE_NOT_SUPPLIED"].observation_ids,
                    tuple(o.observation_id for o in observed),
                )
                self.assert_wire(doc)

    def test_role_disagreement_requires_exact_document_or_scope_declaration(self):
        for name in ("binder_participant_id", "target_participant_id"):
            for container in ("document", "scope"):
                with self.subTest(name=name, container=container):
                    declared_scope, pointer = self.role_case(name)
                    marker = missing(pointer, "explicit unresolved role")
                    kwargs = {"scope": declared_scope}
                    if container == "scope":
                        kwargs["scope"] = replace(declared_scope, missing_declarations=(marker,))
                    else:
                        kwargs["missing_declarations"] = (marker,)
                    doc = self.one(**kwargs)
                    self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
                    self.assertIn(pointer, reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths)
                    self.assertEqual(doc.scope.participants, declared_scope.participants)
                    self.assertEqual(
                        doc.missing_declarations + doc.scope.missing_declarations, (marker,)
                    )
                    self.assert_wire(doc)

    def test_unrecorded_relative_and_descriptor_only_role_declarations_are_refused(self):
        for name in ("binder_participant_id", "target_participant_id"):
            for form in ("absent", "relative", "descriptor"):
                with self.subTest(name=name, form=form):
                    declared_scope, pointer = self.role_case(name)
                    first = descriptor()
                    if form == "relative":
                        declared_scope = replace(
                            declared_scope, missing_declarations=(missing("/" + name),)
                        )
                    if form == "descriptor":
                        first = replace(first, missing_declarations=(missing(pointer),))
                    with self.assertRaises(Error) as caught:
                        document(scope=declared_scope, descriptors=(first,))
                    self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
                    self.assertEqual(caught.exception.field, pointer)

    def test_missing_namespace_and_chain_are_nonqualifying_and_not_repaired(self):
        for name in ("identifier_namespace", "chain_id"):
            with self.subTest(field=name):
                chain = replace(chain_instance(), **{name: None})
                alternative = replace(mapping_alternative(), chain_instances=(chain,))
                doc = self.one(scope=self.mapped_scope(alternative))
                self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
                self.assertEqual(doc.scope.participants[0].mapping_alternatives, (alternative,))
                self.assertIn(
                    "/scope/participants/0/mapping_alternatives/0/chain_instances/0/" + name,
                    reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths,
                )
                self.assert_wire(doc)

    def test_optional_instance_identifier_remains_optional(self):
        chain = replace(chain_instance(), instance_id=None)
        doc = self.one(scope=self.mapped_scope(
            replace(mapping_alternative(), chain_instances=(chain,))
        ))
        self.assertEqual(conditions_of(doc, 0), ("PROVIDED",))
        self.assert_wire(doc)

    def test_missing_mapping_pose_is_retained_as_nonqualifying(self):
        alternative = replace(mapping_alternative(), pose_id=None)
        doc = self.one(scope=self.mapped_scope(alternative))
        self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
        self.assertIn(
            "/scope/participants/0/mapping_alternatives/0/pose_id",
            reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths,
        )
        self.assert_wire(doc)

    def test_explicit_mapping_observation_pose_mismatches_are_refused(self):
        for mapped, observed in (("pose_1", "pose_2"), ("pose_2", "pose_1")):
            with self.subTest(mapped=mapped, observed=observed):
                alternative = replace(mapping_alternative(), pose_id=mapped)
                with self.assertRaises(Error) as caught:
                    document(
                        scope=self.mapped_scope(alternative), poses=(pose(), pose("pose_2")),
                        descriptors=(descriptor(observations=(observation(pose_id=observed),)),),
                    )
                self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
                self.assertEqual(caught.exception.field, "/descriptors/0/observations/0/pose_id")

    def test_missing_observation_pose_remains_nonqualifying(self):
        doc = document(descriptors=(descriptor(observations=(observation(pose_id=None),)),))
        self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
        self.assert_wire(doc)

    def test_unrelated_supplied_mapping_does_not_constrain_observation_pose(self):
        extra = participant(
            "unrelated", "CONTEXT",
            mapping_alternatives=(replace(mapping_alternative(), pose_id="pose_2"),),
        )
        declared_scope = replace(scope(), participants=scope().participants + (extra,))
        doc = self.one(scope=declared_scope, poses=(pose(), pose("pose_2")))
        self.assertEqual(conditions_of(doc, 0), ("PROVIDED",))
        self.assert_wire(doc)

    def test_ambiguous_mapping_is_retained_without_selecting_an_alternative(self):
        original = scope()
        changed = replace(
            original.participants[0], mapping_state="AMBIGUOUS",
            mapping_alternatives=(
                mapping_alternative(), replace(mapping_alternative(), pose_id="pose_2"),
            ),
        )
        declared_scope = replace(original, participants=(changed,) + original.participants[1:])
        doc = self.one(scope=declared_scope, poses=(pose(), pose("pose_2")))
        self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE", "AMBIGUOUS"))
        self.assertEqual(doc.scope.participants[0], changed)
        self.assert_wire(doc)

    def test_nonapplicable_overlap_or_interference_remains_blocking(self):
        doc = document(descriptors=(descriptor(
            definition=definition(reference_state=reference_state("NOT_APPLICABLE"))
        ),))
        self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
        self.assertIn(
            "/descriptors/0/definition/reference_state",
            reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths,
        )
        self.assert_wire(doc)

    def test_nonapplicable_deformation_is_still_refused(self):
        family = BURDEN if self.COLLECTIVE else DEFORMATION
        with self.assertRaises(Error) as caught:
            document(descriptors=(descriptor(
                family=family,
                definition=definition(reference_state=reference_state("NOT_APPLICABLE")),
            ),))
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/descriptors/0/definition/reference_state/kind")

    def test_shared_evidence_cardinality_errors_are_invariant_faults(self):
        cases = (
            lambda: replace(uncertainties("u")[0], state="DECLARED", source_references=()),
            lambda: replace(ambiguity(), field_paths=()),
            lambda: replace(ambiguity(), alternatives=ambiguity().alternatives[:1]),
            lambda: replace(ambiguity(), alternatives=(ambiguity().alternatives[0],) * 2),
            lambda: replace(conflict(), observation_ids=("o1",)),
            lambda: replace(conflict(), observation_ids=("o1", "o1")),
            lambda: m.L2ReferenceState(kind="UNAVAILABLE", references=(src(),), declaration="why"),
            lambda: m.L2ConditionsProfileReference(state="SUPPLIED", reference=None, reason=None),
            lambda: participant(
                mapping_state="SUPPLIED", mapping_alternatives=()
            ),
        )
        for index, call in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(Error) as caught:
                call()
            self.assertEqual(caught.exception.code, "INVARIANT_INVALID")

    def test_primitive_spelling_and_token_errors_remain_structural(self):
        for call in (
            lambda: missing("relative", "why"),
            lambda: participant(role="UNDECLARED_ROLE"),
            lambda: replace(uncertainties("u")[0], state="unknown"),
            lambda: m.L2ReferenceState(kind="NOT_APPLICABLE", references=(), declaration=""),
        ):
            with self.subTest(call=call), self.assertRaises(Error) as caught:
                call()
            self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")


if __name__ == "__main__":
    unittest.main()
