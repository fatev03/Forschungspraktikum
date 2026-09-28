"""Contract tests for ``layer_2b_descriptor_input/1``.

The module under test is loaded directly from its file so that no package
initializer runs and no project module is imported on its behalf.

Run: python3 -B -m unittest discover -s tests -t tests \
         -p 'test_layer_2b_descriptor_input.py' -v
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
MODULE_NAME = "layer_2b_descriptor_input"
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

INTERFERENCE = "COLLECTIVE_INTERFERENCE"
BURDEN = "COLLECTIVE_DEFORMATION_RESTRAINT_BURDEN"
CONFIGURATION = "COLLECTIVE_ANCHOR_LINKER_CONFIGURATION"


def canon(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


# ================================================================================
# Builders
# ================================================================================


def ref(identifier="r-1", revision="v1", snapshot=None):
    return m.L2ImmutableReference(
        namespace="ns",
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


def association(association_id="assoc-1"):
    return m.L2AssociationReference(
        association_id=association_id, revision="rev-1", reference=ref("assoc-doc")
    )


def local_document(document_id="local-1"):
    return m.L2LocalDocumentReference(
        document_id=document_id, revision="rev-1", reference=ref("local-doc")
    )


def admission(candidate_id="cand-1"):
    return m.L2AdmissionReference(
        candidate_id=candidate_id,
        slot_binding_hash="hash-1",
        state_result_id=None,
        ineligibility_reason=None,
        certificate_present=True,
        absent_keys=("state_result_id",),
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


def mapping_alternative(chain_id="A", addressing=True):
    return m.L2MappingAlternative(
        pose_id="pose_1",
        chain_instances=(chain_instance(chain_id, addressing),),
        source_reference=src("mapping"),
    )


def participant(participant_id="b1", role="BINDER", **overrides):
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


def element(element_id="a1", kind="ANCHOR", **overrides):
    payload = dict(
        element_id=element_id,
        kind=kind,
        identity_reference=ref("identity-" + element_id),
        construct_id="construct-" + element_id,
        construct_version="v1",
        mapping_state="SUPPLIED",
        mapping_alternatives=(mapping_alternative(),),
        representation_declaration="representation",
    )
    payload.update(overrides)
    return m.L2AssemblyElement(**payload)


def connection(connection_id="k1", first="a1", second="l1", first_site="site-a"):
    return m.L2Connection(
        connection_id=connection_id,
        first_subject_id=first,
        first_site_declaration=first_site,
        second_subject_id=second,
        second_site_declaration="site-b",
        connection_declaration="connection text",
        source_reference=src("connection"),
    )


def joint_frame(pose_ids=("pose_1",)):
    return m.L2JointFrame(
        frame_id="frame-1",
        frame_kind="CALLER_DECLARED_ARTIFACT_MODEL_FRAME",
        pose_ids=tuple(pose_ids),
        declaration="joint frame text",
        source_reference=src("frame"),
    )


def local_association(slot_id="slot_1", binder="b1", **overrides):
    payload = dict(
        slot_id=slot_id,
        binder_participant_id=binder,
        target_participant_id="t1",
        candidate_id="cand-1",
        scenario_id="scen-1",
        pose_association_reference=association(),
        local_document_reference=local_document(),
        missing_reason=None,
    )
    payload.update(overrides)
    return m.L2LocalAssociation(**payload)


def context(context_id="ctx-1"):
    return m.L2ContextDeclaration(
        context_id=context_id,
        subject_declaration="subject text",
        treatment="REPRESENTED",
        declaration="context text",
        source_reference=src("context"),
    )


def missing(field_path="/scope/assembly_task_declaration", reason="unresolved"):
    return m.L2MissingDeclaration(field=field_path, reason=reason)


def scope(**overrides):
    payload = dict(
        participants=(
            participant("b1", "BINDER"),
            participant("b2", "BINDER"),
            participant("b3", "BINDER"),
            participant("t1", "RECEPTOR"),
        ),
        local_associations=(
            local_association("slot_1", "b1"),
            local_association("slot_2", "b2"),
            local_association("slot_3", "b3"),
        ),
        assembly_elements=(element("a1", "ANCHOR"), element("l1", "LINKER")),
        connections=(connection(),),
        joint_frame=joint_frame(),
        target_site_declaration="site text",
        assembly_task_declaration="task text",
        context_declarations=(context(),),
        missing_declarations=(),
    )
    payload.update(overrides)
    return m.L2CollectiveScope(**payload)


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


def reference_state(kind="ASSEMBLY_REFERENCE"):
    if kind in ("NOT_APPLICABLE", "UNAVAILABLE"):
        return m.L2ReferenceState(kind=kind, references=(), declaration="explained")
    return m.L2ReferenceState(
        kind=kind, references=(src("reference-state"),), declaration="explained"
    )


def definition(subjects=("b1", "t1"), numeric=True, **overrides):
    payload = dict(
        definition_reference=ref("definition"),
        observable_name="observable",
        subject_ids=tuple(subjects),
        selection_declaration="selection text",
        unit_class="LENGTH" if numeric else None,
        unit_symbol="unit" if numeric else None,
        conditions_required=True,
        method=method(),
        conditions_profile=profile(),
        reference_state=reference_state(),
        comparability_reference=src("comparability"),
        limitation="limitation text",
    )
    payload.update(overrides)
    return m.L2ObservableDefinition(**payload)


def numeric_value(number="1.5"):
    return m.L2DescriptorValue(kind="NUMERIC", number=number, category=None)


def categorical_value(category="declared-shape"):
    return m.L2DescriptorValue(kind="CATEGORICAL", number=None, category=category)


def observation(observation_id="o1", **overrides):
    payload = dict(
        observation_id=observation_id,
        pose_id="pose_1",
        sample_id="sample-1",
        replicate_id="replicate-1",
        source_reference=src("observation"),
        value=numeric_value(),
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


def descriptor(descriptor_id="d1", family=INTERFERENCE, prefix="u", **overrides):
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
        family=family, descriptor_ids=tuple(descriptor_ids), absence_reason=absence_reason
    )


def availability_for(descriptors):
    records = []
    for family in m.LAYER_2B_FAMILIES:
        ids = tuple(d.descriptor_id for d in descriptors if d.family == family)
        records.append(
            availability(family, ids, None if ids else "no descriptor supplied")
        )
    return tuple(records)


def default_descriptors():
    return (
        descriptor("d1", INTERFERENCE, "u"),
        descriptor(
            "d2",
            BURDEN,
            "w",
            definition=definition(selection_declaration="burden selection"),
            observations=(observation("o2"),),
        ),
        descriptor(
            "d3",
            CONFIGURATION,
            "x",
            definition=definition(subjects=("a1", "l1"), numeric=False),
            observations=(observation("o3", value=categorical_value()),),
        ),
    )


def document(**overrides):
    descriptors = overrides.pop("descriptors", default_descriptors())
    payload = dict(
        document_id="doc-1",
        revision="rev-1",
        declared_by="party-1",
        declared_at=STAMP,
        source_references=(src("document"),),
        candidate_anchor=candidate_anchor(),
        scope=scope(),
        poses=(pose(),),
        family_availability=availability_for(descriptors),
        descriptors=descriptors,
        missing_declarations=(),
    )
    payload.update(overrides)
    return m.Layer2BDescriptorInput(**payload)


def limited_document():
    """One document exercising every condition and every reason code."""
    rich = descriptor(
        "d_all",
        INTERFERENCE,
        "u",
        observations=(observation("o1"), observation("o2"), observation("o3")),
        ambiguities=(ambiguity("a1", ("o3",)),),
        conflicts=(conflict("c1", ("o1", "o2")),),
    )
    gap = descriptor(
        "d_gap",
        BURDEN,
        "w",
        scope_declaration=None,
        definition=definition(
            selection_declaration="burden selection",
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
        for index in range(3):
            self.assertEqual(conditions_of(doc, index), ("PROVIDED",), index)
            self.assertEqual(doc.descriptor_reasons[index], (), index)

    def test_document_constants_are_derived(self):
        doc = document()
        self.assertEqual(doc.document_type, "layer_2b_descriptor_input/1")
        self.assertEqual(doc.non_claim, m.LAYER_2B_NON_CLAIM)
        self.assertIn("three-binder", doc.non_claim)

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

    def test_collective_scope_emission_order(self):
        self.assertEqual(
            list(document().as_dict()["scope"]),
            [
                "participants",
                "local_associations",
                "assembly_elements",
                "connections",
                "joint_frame",
                "target_site_declaration",
                "assembly_task_declaration",
                "context_declarations",
                "missing_declarations",
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
                pass
            else:
                self.assertNotIsInstance(node, (int, float))

        walk(decoded)

    def test_round_trip_from_dict_and_from_bytes(self):
        for build in (document, limited_document):
            with self.subTest(fixture=build.__name__):
                doc = build()
                self.assertEqual(m.Layer2BDescriptorInput.from_dict(doc.as_dict()), doc)
                reloaded = m.Layer2BDescriptorInput.from_json_bytes(doc.to_json_bytes())
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
            "doc = module.Layer2BDescriptorInput.from_json_bytes(payload)\n"
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
# 2. Collective invariants
# ================================================================================


class CollectiveInvariants(unittest.TestCase):
    def test_exactly_three_local_associations(self):
        for count in (2, 4):
            with self.subTest(count=count):
                associations = tuple(
                    local_association(m.L2_SLOT_IDS[position % 3], "b1")
                    for position in range(count)
                )
                with self.assertRaises(Error) as caught:
                    document(scope=scope(local_associations=associations))
                self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
                self.assertEqual(caught.exception.field, "/scope/local_associations")

    def test_local_associations_follow_slot_order(self):
        with self.assertRaises(Error) as caught:
            document(
                scope=scope(
                    local_associations=(
                        local_association("slot_2", "b1"),
                        local_association("slot_1", "b2"),
                        local_association("slot_3", "b3"),
                    )
                )
            )
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(
            caught.exception.field, "/scope/local_associations/0/slot_id"
        )
        self.assertEqual(caught.exception.index, 0)

    def test_binder_identifiers_across_positions_are_distinct(self):
        with self.assertRaises(Error) as caught:
            document(
                scope=scope(
                    participants=(
                        participant("b1", "BINDER"),
                        participant("t1", "RECEPTOR"),
                    ),
                    local_associations=(
                        local_association("slot_1", "b1"),
                        local_association("slot_2", "b1"),
                        local_association("slot_3", "b1"),
                    ),
                )
            )
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(
            caught.exception.field,
            "/scope/local_associations/1/binder_participant_id",
        )

    def test_no_unassigned_binder_participant_remains(self):
        with self.assertRaises(Error) as caught:
            document(
                scope=scope(
                    participants=(
                        participant("b1", "BINDER"),
                        participant("b2", "BINDER"),
                        participant("b3", "BINDER"),
                        participant("b4", "BINDER"),
                        participant("t1", "RECEPTOR"),
                    )
                )
            )
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(
            caught.exception.field, "/scope/participants/3/participant_id"
        )

    def test_a_missing_local_document_keeps_its_association_position(self):
        doc = document(
            scope=scope(
                participants=(
                    participant("b1", "BINDER"),
                    participant("b2", "BINDER"),
                    participant("t1", "RECEPTOR"),
                ),
                local_associations=(
                    local_association("slot_1", "b1"),
                    local_association("slot_2", "b2"),
                    local_association(
                        "slot_3",
                        None,
                        target_participant_id=None,
                        candidate_id=None,
                        scenario_id=None,
                        pose_association_reference=None,
                        local_document_reference=None,
                        missing_reason="no local document supplied",
                    ),
                ),
            )
        )
        self.assertEqual(len(doc.scope.local_associations), 3)
        self.assertEqual(doc.scope.local_associations[2].slot_id, "slot_3")

    def test_a_shared_target_may_repeat_across_positions(self):
        doc = document()
        targets = [a.target_participant_id for a in doc.scope.local_associations]
        self.assertEqual(targets, ["t1", "t1", "t1"])

    def test_a_role_disagreement_is_retained_and_blocks_qualification(self):
        binder_mismatch = document(
            scope=scope(
                missing_declarations=(
                    missing("/scope/local_associations/0/binder_participant_id", "role unresolved"),
                ),
                participants=(
                    participant("b1", "LIGAND"),
                    participant("b2", "BINDER"),
                    participant("b3", "BINDER"),
                    participant("t1", "RECEPTOR"),
                )
            ),
            descriptors=(descriptor("d1", INTERFERENCE, "u"),),
        )
        self.assertEqual(conditions_of(binder_mismatch, 0), ("UNAVAILABLE",))
        self.assertIn(
            "/scope/local_associations/0/binder_participant_id",
            reasons_of(binder_mismatch, 0)["DECLARATION_MISSING"].field_paths,
        )
        # The declaration is retained verbatim; no role is inferred or repaired.
        self.assertEqual(binder_mismatch.scope.participants[0].role, "LIGAND")
        self.assertEqual(
            binder_mismatch.scope.local_associations[0].binder_participant_id, "b1"
        )

        target_mismatch = document(
            scope=scope(
                missing_declarations=(
                    missing("/scope/local_associations/0/target_participant_id", "role unresolved"),
                ),
                local_associations=(
                    local_association("slot_1", "b1", target_participant_id="b2"),
                    local_association("slot_2", "b2"),
                    local_association("slot_3", "b3"),
                )
            ),
            descriptors=(descriptor("d1", INTERFERENCE, "u"),),
        )
        self.assertEqual(conditions_of(target_mismatch, 0), ("UNAVAILABLE",))
        self.assertIn(
            "/scope/local_associations/0/target_participant_id",
            reasons_of(target_mismatch, 0)["DECLARATION_MISSING"].field_paths,
        )

    def test_an_unresolvable_local_association_participant_is_still_refused(self):
        for name in ("binder_participant_id", "target_participant_id"):
            with self.subTest(field=name):
                override = {name: "absent"}
                if name == "binder_participant_id":
                    # b1 would otherwise become an unreferenced binder participant.
                    override["binder_participant_id"] = "absent"
                with self.assertRaises(Error) as caught:
                    document(
                        scope=scope(
                            local_associations=(
                                local_association("slot_1", "b1", **override),
                                local_association("slot_2", "b2"),
                                local_association("slot_3", "b3"),
                            )
                        )
                    )
                self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
                self.assertEqual(
                    caught.exception.field,
                    "/scope/local_associations/0/" + name,
                )

    def test_local_association_candidate_and_scenario_must_equal_the_anchor(self):
        for name in ("candidate_id", "scenario_id"):
            with self.subTest(field=name):
                with self.assertRaises(Error) as caught:
                    document(
                        scope=scope(
                            local_associations=(
                                local_association("slot_1", "b1", **{name: "other"}),
                                local_association("slot_2", "b2"),
                                local_association("slot_3", "b3"),
                            )
                        )
                    )
                self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
                self.assertEqual(
                    caught.exception.field,
                    "/scope/local_associations/0/" + name,
                )

    def test_missing_reason_is_required_exactly_when_a_field_is_absent(self):
        for name in m._LOCAL_ASSOCIATION_OPTIONAL:
            with self.subTest(field=name):
                with self.assertRaises(Error) as caught:
                    local_association("slot_1", "b1", **{name: None})
                self.assertEqual(caught.exception.field, "/missing_reason")
        with self.assertRaises(Error) as caught:
            local_association("slot_1", "b1", missing_reason="not needed")
        self.assertEqual(caught.exception.field, "/missing_reason")

    def test_participants_and_assembly_elements_share_one_namespace(self):
        with self.assertRaises(Error) as caught:
            document(
                scope=scope(
                    assembly_elements=(element("b1", "ANCHOR"), element("l1", "LINKER"))
                )
            )
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
        self.assertEqual(
            caught.exception.field, "/scope/assembly_elements/0/element_id"
        )

    def test_connection_subjects_resolve_to_participants_or_elements(self):
        doc = document(
            scope=scope(connections=(connection("k1", first="b1", second="a1"),))
        )
        self.assertEqual(doc.scope.connections[0].first_subject_id, "b1")
        with self.assertRaises(Error) as caught:
            document(scope=scope(connections=(connection("k1", first="absent"),)))
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
        self.assertEqual(
            caught.exception.field, "/scope/connections/0/first_subject_id"
        )

    def test_a_repeated_ordered_endpoint_declaration_is_refused(self):
        with self.assertRaises(Error) as caught:
            document(
                scope=scope(
                    connections=(connection("k1"), connection("k2"))
                )
            )
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/scope/connections/1")

    def test_reversed_endpoint_order_is_preserved_not_normalized(self):
        doc = document(
            scope=scope(
                connections=(
                    connection("k1", first="a1", second="l1"),
                    connection("k2", first="l1", second="a1"),
                )
            )
        )
        self.assertEqual(doc.scope.connections[0].first_subject_id, "a1")
        self.assertEqual(doc.scope.connections[1].first_subject_id, "l1")

    def test_joint_frame_pose_identifiers_resolve_and_are_unique(self):
        with self.assertRaises(Error) as caught:
            document(scope=scope(joint_frame=joint_frame(("absent",))))
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
        self.assertEqual(caught.exception.field, "/scope/joint_frame/pose_ids/0")
        with self.assertRaises(Error) as caught:
            joint_frame(("pose_1", "pose_1"))
        self.assertEqual(caught.exception.field, "/pose_ids/1")

    def test_a_local_association_never_creates_a_collective_frame(self):
        doc = document(scope=scope(joint_frame=None))
        self.assertIsNone(doc.scope.joint_frame)
        for index in range(3):
            self.assertEqual(conditions_of(doc, index), ("UNAVAILABLE",))
            self.assertIn(
                "/scope/joint_frame",
                reasons_of(doc, index)["DECLARATION_MISSING"].field_paths,
            )

    def test_an_external_local_document_is_not_loaded(self):
        doc = document()
        reference = doc.scope.local_associations[0].local_document_reference
        self.assertEqual(reference.document_id, "local-1")
        self.assertEqual(m.LOCAL_DOCUMENT_TYPE, "layer_2a_descriptor_input/1")
        self.assertFalse(hasattr(reference, "load"))


# ================================================================================
# 3. Collective families and availability
# ================================================================================


class CollectiveFamilies(unittest.TestCase):
    def test_only_the_three_collective_families_exist(self):
        self.assertEqual(
            m.LAYER_2B_FAMILIES, (INTERFERENCE, BURDEN, CONFIGURATION)
        )
        self.assertFalse(hasattr(m, "L2_LOCAL_FAMILIES"))
        self.assertFalse(hasattr(m, "Layer2ADescriptorInput"))
        self.assertFalse(hasattr(m, "L2LocalScope"))

    def test_a_local_family_token_is_refused(self):
        for token in ("LOCAL_OVERLAP", "LOCAL_ISOLATED_REFERENCE_DEFORMATION_BURDEN"):
            with self.subTest(token=token):
                with self.assertRaises(Error) as caught:
                    descriptor("d1", token, "u")
                self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")
                self.assertEqual(caught.exception.field, "/family")
                with self.assertRaises(Error):
                    availability(token, ())

    def test_exactly_three_availability_records_in_family_order(self):
        doc = document()
        self.assertEqual(
            tuple(item.family for item in doc.family_availability), m.LAYER_2B_FAMILIES
        )
        with self.assertRaises(Error) as caught:
            document(family_availability=availability_for(default_descriptors())[:2])
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/family_availability")

    def test_availability_order_is_not_repaired(self):
        records = availability_for(default_descriptors())
        with self.assertRaises(Error) as caught:
            document(family_availability=(records[1], records[0], records[2]))
        self.assertEqual(caught.exception.field, "/family_availability/0/family")

    def test_the_configuration_family_always_has_an_availability_record(self):
        doc = document(descriptors=(descriptor("d1", INTERFERENCE, "u"),))
        families = [item.family for item in doc.family_availability]
        self.assertIn(CONFIGURATION, families)
        record = doc.family_availability[families.index(CONFIGURATION)]
        self.assertEqual(record.descriptor_ids, ())
        self.assertEqual(record.absence_reason, "no descriptor supplied")

    def test_listing_assembly_elements_does_not_supply_configuration_observations(self):
        doc = document(descriptors=(descriptor("d1", INTERFERENCE, "u"),))
        self.assertEqual(len(doc.scope.assembly_elements), 2)
        self.assertEqual(doc.family_availability[2].descriptor_ids, ())

    def test_availability_lists_exactly_its_family_in_descriptor_order(self):
        descriptors = default_descriptors()
        records = list(availability_for(descriptors))
        records[0] = availability(INTERFERENCE, (), "declared absent")
        with self.assertRaises(Error) as caught:
            document(descriptors=descriptors, family_availability=tuple(records))
        self.assertEqual(
            caught.exception.field, "/family_availability/0/descriptor_ids"
        )

    def test_directional_families_permit_only_numeric_values(self):
        for family, prefix in ((INTERFERENCE, "u"), (BURDEN, "w")):
            with self.subTest(family=family):
                bad = descriptor(
                    "d1",
                    family,
                    prefix,
                    definition=definition(numeric=False),
                    observations=(observation("o1", value=categorical_value()),),
                )
                with self.assertRaises(Error) as caught:
                    document(descriptors=(bad,))
                self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
                self.assertEqual(
                    caught.exception.field,
                    "/descriptors/0/observations/0/value/kind",
                )

    def test_the_configuration_family_permits_numeric_or_categorical_values(self):
        categorical = descriptor(
            "d3",
            CONFIGURATION,
            "x",
            definition=definition(subjects=("a1", "l1"), numeric=False),
            observations=(observation("o1", value=categorical_value()),),
        )
        numeric = descriptor(
            "d3",
            CONFIGURATION,
            "x",
            definition=definition(subjects=("a1", "l1")),
            observations=(observation("o1"),),
        )
        for candidate in (categorical, numeric):
            with self.subTest(kind=candidate.observations[0].value.kind):
                doc = document(descriptors=(candidate,))
                self.assertEqual(conditions_of(doc, 0), ("PROVIDED",))

    def test_numeric_values_require_units_and_categorical_values_forbid_them(self):
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor("d1", INTERFERENCE, "u", definition=definition(unit_class=None)),
                )
            )
        self.assertEqual(
            caught.exception.field, "/descriptors/0/definition/unit_class"
        )
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor(
                        "d3",
                        CONFIGURATION,
                        "x",
                        definition=definition(subjects=("a1", "l1")),
                        observations=(observation("o1", value=categorical_value()),),
                    ),
                )
            )
        self.assertEqual(
            caught.exception.field, "/descriptors/0/definition/unit_class"
        )

    def test_the_burden_family_requires_conditions_and_a_collective_reference_state(self):
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor(
                        "d2", BURDEN, "w", definition=definition(conditions_required=False)
                    ),
                )
            )
        self.assertEqual(
            caught.exception.field, "/descriptors/0/definition/conditions_required"
        )
        for kind in ("ISOLATED_FROZEN", "ISOLATED_RELAXED", "NOT_APPLICABLE"):
            with self.subTest(kind=kind):
                with self.assertRaises(Error) as caught:
                    document(
                        descriptors=(
                            descriptor(
                                "d2",
                                BURDEN,
                                "w",
                                definition=definition(
                                    reference_state=reference_state(kind)
                                ),
                            ),
                        )
                    )
                self.assertEqual(
                    caught.exception.field,
                    "/descriptors/0/definition/reference_state/kind",
                )
        for kind in m.COLLECTIVE_DEFORMATION_REFERENCE_STATE_KINDS:
            with self.subTest(accepted=kind):
                document(
                    descriptors=(
                        descriptor(
                            "d2",
                            BURDEN,
                            "w",
                            definition=definition(reference_state=reference_state(kind)),
                        ),
                    )
                )


# ================================================================================
# 4. Derived conditions and reasons
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

    def test_every_reason_code_is_exercised_in_vocabulary_order(self):
        rich = [reason.code for reason in self.doc.descriptor_reasons[0]]
        gap = [reason.code for reason in self.doc.descriptor_reasons[1]]
        self.assertEqual(rich, ["DECLARATION_AMBIGUOUS", "OBSERVATIONS_CONFLICT"])
        self.assertEqual(gap, ["EVIDENCE_NOT_SUPPLIED", "DECLARATION_MISSING"])
        self.assertEqual(set(rich) | set(gap), set(m.L2_REASON_CODES))
        for codes in (rich, gap):
            self.assertEqual(codes, sorted(codes, key=m.L2_REASON_CODES.index))

    def test_reason_field_paths_are_lexically_sorted_and_unique(self):
        for index in range(len(self.doc.descriptors)):
            for reason in self.doc.descriptor_reasons[index]:
                paths = list(reason.field_paths)
                self.assertTrue(paths, reason.code)
                self.assertEqual(paths, sorted(paths), reason.code)
                self.assertEqual(len(paths), len(set(paths)), reason.code)

    def test_evidence_not_supplied_names_the_valueless_observations(self):
        reason = reasons_of(self.doc, 1)["EVIDENCE_NOT_SUPPLIED"]
        self.assertEqual(
            list(reason.field_paths), ["/descriptors/1/observations/0/value"]
        )
        self.assertEqual(list(reason.observation_ids), ["g1"])
        self.assertEqual(list(reason.record_ids), [])

    def test_evidence_not_supplied_keeps_observation_array_order(self):
        doc = document(
            descriptors=(
                descriptor(
                    "d1",
                    INTERFERENCE,
                    "u",
                    observations=(
                        observation("x1", value=None),
                        observation("x2", value=None),
                    ),
                ),
            )
        )
        reason = reasons_of(doc, 0)["EVIDENCE_NOT_SUPPLIED"]
        self.assertEqual(list(reason.observation_ids), ["x1", "x2"])
        self.assertEqual(list(reason.record_ids), [])

    def test_evidence_not_supplied_uses_the_observations_array_when_empty(self):
        doc = document(
            descriptors=(descriptor("d1", INTERFERENCE, "u", observations=()),)
        )
        reason = reasons_of(doc, 0)["EVIDENCE_NOT_SUPPLIED"]
        self.assertEqual(list(reason.field_paths), ["/descriptors/0/observations"])
        self.assertEqual(list(reason.observation_ids), [])

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
        self.assertEqual(list(reason.record_ids), [])

    def test_declaration_missing_carries_missing_declaration_pointers_verbatim(self):
        doc = document(
            missing_declarations=(missing("/candidate_anchor/scenario_id", "unresolved"),),
            scope=scope(missing_declarations=(missing("/scope/joint_frame", "unclear"),)),
            descriptors=(
                descriptor(
                    "d1",
                    INTERFERENCE,
                    "u",
                    missing_declarations=(missing("/descriptors/0/definition", "open"),),
                    observations=(
                        observation(
                            "o1",
                            missing_declarations=(missing("/~0odd/~1path", "locator"),),
                        ),
                    ),
                ),
            ),
        )
        paths = list(reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths)
        for pointer in (
            "/candidate_anchor/scenario_id",
            "/scope/joint_frame",
            "/descriptors/0/definition",
        ):
            self.assertIn(pointer, paths)
        self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))

    def test_a_missing_declaration_pointer_is_not_dereferenced(self):
        doc = document(
            descriptors=(
                descriptor(
                    "d1",
                    INTERFERENCE,
                    "u",
                    missing_declarations=(missing("/nowhere/at/all", "opaque"),),
                ),
            )
        )
        self.assertIn(
            "/nowhere/at/all",
            reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths,
        )
        self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))

    def test_ambiguity_reason_names_records_in_ambiguity_array_order(self):
        reason = reasons_of(self.doc, 0)["DECLARATION_AMBIGUOUS"]
        self.assertEqual(list(reason.field_paths), ["/descriptors/0/ambiguities/0"])
        self.assertEqual(list(reason.observation_ids), ["o3"])
        self.assertEqual(list(reason.record_ids), ["a1"])

    def test_conflict_reason_names_records_in_conflict_array_order(self):
        reason = reasons_of(self.doc, 0)["OBSERVATIONS_CONFLICT"]
        self.assertEqual(list(reason.field_paths), ["/descriptors/0/conflicts/0"])
        self.assertEqual(list(reason.observation_ids), ["o1", "o2"])
        self.assertEqual(list(reason.record_ids), ["c1"])

    def test_observation_identifiers_retain_observation_array_order(self):
        rich = descriptor(
            "d_all",
            INTERFERENCE,
            "u",
            observations=(observation("o1"), observation("o2"), observation("o3")),
            conflicts=(conflict("c1", ("o3", "o1")),),
        )
        doc = document(descriptors=(rich,))
        self.assertEqual(
            list(reasons_of(doc, 0)["OBSERVATIONS_CONFLICT"].observation_ids),
            ["o1", "o3"],
        )

    def test_an_ambiguous_subject_mapping_blocks_qualification(self):
        blurred = element(
            "a1",
            "ANCHOR",
            mapping_state="AMBIGUOUS",
            mapping_alternatives=(mapping_alternative("A"), mapping_alternative("B")),
        )
        doc = document(
            scope=scope(assembly_elements=(blurred, element("l1", "LINKER"))),
            descriptors=(
                descriptor(
                    "d3",
                    CONFIGURATION,
                    "x",
                    definition=definition(subjects=("a1", "l1"), numeric=False),
                    observations=(observation("o1", value=categorical_value()),),
                ),
            ),
        )
        self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE", "AMBIGUOUS"))
        self.assertEqual(
            list(reasons_of(doc, 0)["DECLARATION_AMBIGUOUS"].field_paths),
            ["/scope/assembly_elements/0/mapping_state"],
        )

    def test_collective_scope_declarations_are_required_for_provided_content(self):
        cases = {
            # Emptying the elements also removes the endpoints of the default
            # connection, so this case re-points that connection at participants.
            "/scope/assembly_elements": dict(
                assembly_elements=(),
                connections=(connection("k1", first="b1", second="t1"),),
            ),
            "/scope/connections": dict(connections=()),
            "/scope/joint_frame": dict(joint_frame=None),
        }
        for expected, override in cases.items():
            with self.subTest(path=expected):
                doc = document(
                    scope=scope(**override),
                    descriptors=(descriptor("d1", INTERFERENCE, "u"),),
                )
                self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
                self.assertIn(
                    expected, reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths
                )

    def test_supplied_derived_conditions_and_reasons_must_agree(self):
        payload = limited_document().as_dict()
        payload["descriptors"][0]["conditions"] = ["PROVIDED"]
        with self.assertRaises(Error) as caught:
            m.Layer2BDescriptorInput.from_dict(payload)
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/descriptors/0/conditions")

        payload = limited_document().as_dict()
        payload["descriptors"][1]["reasons"][0]["field_paths"] = ["/descriptors/1"]
        with self.assertRaises(Error) as caught:
            m.Layer2BDescriptorInput.from_dict(payload)
        self.assertEqual(caught.exception.field, "/descriptors/1/reasons")

    def test_a_conflict_without_two_qualifying_observations_is_refused(self):
        rich = descriptor(
            "d_all",
            INTERFERENCE,
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

    def test_unknown_uncertainty_alone_does_not_remove_provided_content(self):
        doc = document()
        self.assertEqual(conditions_of(doc, 0), ("PROVIDED",))
        self.assertTrue(
            all(item.state == "UNKNOWN" for item in doc.descriptors[0].uncertainties)
        )


# ================================================================================
# 5. Shared primitives and cardinality carried into 2B
# ================================================================================


class SharedPrimitivesAndCardinality(unittest.TestCase):
    def test_identifier_pointer_timestamp_and_decimal_spellings(self):
        with self.assertRaises(Error) as caught:
            ref(identifier=" x")
        self.assertEqual(caught.exception.field, "/identifier")
        m.L2MissingDeclaration(field="", reason="root")
        m.L2MissingDeclaration(field="/a~0b/c~1d", reason="escaped")
        for bad in ("relative", "/a~", "/a~2"):
            with self.subTest(pointer=bad):
                with self.assertRaises(Error):
                    m.L2MissingDeclaration(field=bad, reason="x")
        for bad in ("", "+1", "01", "1.0", "-0", "1e5", ".5"):
            with self.subTest(decimal=bad):
                with self.assertRaises(Error) as caught:
                    numeric_value(bad)
                self.assertEqual(caught.exception.field, "/number")
        with self.assertRaises(Error) as caught:
            m.L2ConflictRecord(
                conflict_id="c",
                observation_ids=("o1", "o2"),
                comparability_reference=src(),
                declaration="d",
                declared_by="p",
                declared_at="2026-02-30T00:00:00Z",
                source_references=(),
            )
        self.assertEqual(caught.exception.field, "/declared_at")

    def test_artifact_anchor_spellings(self):
        for bad in ("A" * 64, "a" * 63):
            with self.subTest(digest=len(bad)):
                with self.assertRaises(Error) as caught:
                    anchor(bad)
                self.assertEqual(caught.exception.field, "/digest")
        self.assertEqual(
            m.L2ArtifactAnchor(
                kind="IMMUTABLE_SNAPSHOT",
                algorithm=None,
                digest=None,
                snapshot_reference=ref(),
            ).kind,
            "IMMUTABLE_SNAPSHOT",
        )

    def test_mapping_state_cardinality_on_participants_and_elements(self):
        for factory in (participant, element):
            with self.subTest(record=factory.__name__):
                with self.assertRaises(Error):
                    factory(mapping_state="SUPPLIED", mapping_alternatives=())
                with self.assertRaises(Error):
                    factory(
                        mapping_state="ABSENT",
                        mapping_alternatives=(mapping_alternative(),),
                    )
                with self.assertRaises(Error) as caught:
                    factory(
                        mapping_state="AMBIGUOUS",
                        mapping_alternatives=(mapping_alternative(),),
                    )
                self.assertEqual(caught.exception.field, "/mapping_alternatives")

    def test_profile_reference_state_and_uncertainty_agreement(self):
        with self.assertRaises(Error) as caught:
            m.L2ConditionsProfileReference(state="SUPPLIED", reference=None, reason=None)
        self.assertEqual(caught.exception.field, "/reference")
        with self.assertRaises(Error) as caught:
            m.L2ReferenceState(kind="UNAVAILABLE", references=(src(),), declaration="d")
        self.assertEqual(caught.exception.field, "/references")
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
        reordered = list(uncertainties("u"))
        reordered[0], reordered[1] = reordered[1], reordered[0]
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor("d1", INTERFERENCE, "u", uncertainties=tuple(reordered)),
                )
            )
        self.assertEqual(caught.exception.code, "INVARIANT_INVALID")
        self.assertEqual(caught.exception.field, "/descriptors/0/uncertainties")

    def test_descriptor_identifiers_and_namespaces(self):
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor("d1", INTERFERENCE, "u"),
                    descriptor(
                        "d1",
                        BURDEN,
                        "w",
                        definition=definition(selection_declaration="other"),
                    ),
                )
            )
        self.assertEqual(caught.exception.field, "/descriptors/1/descriptor_id")
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor("d1", INTERFERENCE, "u", ambiguities=(ambiguity("o1", ()),)),
                )
            )
        self.assertEqual(
            caught.exception.field, "/descriptors/0/ambiguities/0/ambiguity_id"
        )

    def test_a_descriptor_may_not_duplicate_a_complete_observable_scope(self):
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor("d1", INTERFERENCE, "u"),
                    descriptor("d2", INTERFERENCE, "w"),
                )
            )
        self.assertEqual(caught.exception.field, "/descriptors/1/definition")

    def test_conflicts_on_the_same_observations_must_differ_in_declaration(self):
        rich = descriptor(
            "d_all",
            INTERFERENCE,
            "u",
            observations=(observation("o1"), observation("o2")),
            conflicts=(
                conflict("c1", ("o1", "o2"), "same"),
                conflict("c2", ("o2", "o1"), "same"),
            ),
        )
        with self.assertRaises(Error) as caught:
            document(descriptors=(rich,))
        self.assertEqual(caught.exception.field, "/descriptors/0/conflicts/1")

    def test_admission_candidate_identity_must_agree(self):
        with self.assertRaises(Error) as caught:
            document(candidate_anchor=candidate_anchor(candidate_id="other"))
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
        self.assertEqual(caught.exception.field, "/candidate_anchor/candidate_id")

    def test_dangling_references_are_refused(self):
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor(
                        "d1",
                        INTERFERENCE,
                        "u",
                        observations=(observation("o1", pose_id="absent"),),
                    ),
                )
            )
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
        self.assertEqual(
            caught.exception.field, "/descriptors/0/observations/0/pose_id"
        )
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(
                    descriptor(
                        "d1",
                        INTERFERENCE,
                        "u",
                        definition=definition(subjects=("absent",)),
                    ),
                )
            )
        self.assertEqual(
            caught.exception.field, "/descriptors/0/definition/subject_ids/0"
        )

    def test_a_descriptor_subject_may_be_an_assembly_element(self):
        doc = document(
            descriptors=(
                descriptor(
                    "d3",
                    CONFIGURATION,
                    "x",
                    definition=definition(subjects=("a1", "l1"), numeric=False),
                    observations=(observation("o1", value=categorical_value()),),
                ),
            )
        )
        self.assertEqual(conditions_of(doc, 0), ("PROVIDED",))


# ================================================================================
# 6. Loading refusals
# ================================================================================


class LoadingRefusals(unittest.TestCase):
    def setUp(self):
        self.payload = document().as_dict()

    def load(self, payload):
        return m.Layer2BDescriptorInput.from_json_bytes(canon(payload))

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
            "/scope/local_associations/0/surprise": (
                lambda p: p["scope"]["local_associations"][0].__setitem__("surprise", "x")
            ),
            "/scope/joint_frame/surprise": (
                lambda p: p["scope"]["joint_frame"].__setitem__("surprise", "x")
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
            self.load(
                self.mutated(lambda p: p["scope"].pop("assembly_task_declaration"))
            )
        self.assertEqual(caught.exception.field, "/scope/assembly_task_declaration")

    def test_duplicate_json_keys_are_refused_at_every_depth(self):
        text = canon(self.payload).decode("utf-8")
        for needle, injected in (
            ('"document_id":"doc-1"', '"document_id":"doc-1","document_id":"x"'),
            ('"slot_id":"slot_1"', '"slot_id":"slot_1","slot_id":"slot_2"'),
        ):
            with self.subTest(needle=needle):
                with self.assertRaises(Error) as caught:
                    m.Layer2BDescriptorInput.from_json_bytes(
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
            m.Layer2BDescriptorInput.from_json_bytes(text.encode("utf-8"))
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
                    m.Layer2BDescriptorInput.from_json_bytes(data)
                self.assertEqual(caught.exception.code, "NON_CANONICAL_BYTES")

    def test_a_structural_fault_outranks_noncanonical_bytes(self):
        payload = self.mutated(lambda p: p.__setitem__("document_id", ""))
        data = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
        with self.assertRaises(Error) as caught:
            m.Layer2BDescriptorInput.from_json_bytes(data)
        self.assertEqual(caught.exception.code, "STRUCTURAL_INVALID")

    def test_the_error_exposes_code_field_index_and_message(self):
        with self.assertRaises(Error) as caught:
            self.load(
                self.mutated(
                    lambda p: p["scope"]["connections"][0].__setitem__(
                        "first_subject_id", "absent"
                    )
                )
            )
        error = caught.exception
        self.assertEqual(error.code, "REFERENCE_INVALID")
        self.assertEqual(error.field, "/scope/connections/0/first_subject_id")
        self.assertEqual(error.index, 0)
        self.assertIsInstance(error.message, str)
        self.assertIn(error.code, m.L2_ERROR_CODES)

    def test_the_index_is_the_outermost_array_position(self):
        with self.assertRaises(Error) as caught:
            document(
                scope=scope(
                    local_associations=(
                        local_association("slot_1", "b1"),
                        local_association("slot_2", "b2", candidate_id="other"),
                        local_association("slot_3", "b3"),
                    )
                )
            )
        self.assertEqual(
            caught.exception.field, "/scope/local_associations/1/candidate_id"
        )
        self.assertEqual(caught.exception.index, 1)

    def test_a_root_level_fault_has_a_null_index(self):
        with self.assertRaises(Error) as caught:
            m.Layer2BDescriptorInput.from_json_bytes(b"not json")
        self.assertEqual(caught.exception.field, "")
        self.assertIsNone(caught.exception.index)


# ================================================================================
# 7. Detachment and immutability
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
        self.assertIsNot(
            first["scope"]["local_associations"], second["scope"]["local_associations"]
        )
        self.assertIsNot(first["scope"]["joint_frame"], second["scope"]["joint_frame"])

    def test_mutating_a_returned_structure_cannot_reach_the_document(self):
        baseline = self.doc.to_json_bytes()
        payload = self.doc.as_dict()
        payload["descriptors"].append({"injected": True})
        payload["scope"]["local_associations"].clear()
        payload["scope"]["joint_frame"]["pose_ids"].clear()
        payload["descriptors"][0]["conditions"].clear()
        self.assertEqual(self.doc.to_json_bytes(), baseline)
        self.assertEqual(len(self.doc.scope.local_associations), 3)

    def test_every_stored_collection_is_a_tuple(self):
        self.assertIsInstance(self.doc.descriptors, tuple)
        self.assertIsInstance(self.doc.poses, tuple)
        self.assertIsInstance(self.doc.family_availability, tuple)
        self.assertIsInstance(self.doc.descriptor_conditions, tuple)
        self.assertIsInstance(self.doc.scope.local_associations, tuple)
        self.assertIsInstance(self.doc.scope.assembly_elements, tuple)
        self.assertIsInstance(self.doc.scope.connections, tuple)
        self.assertIsInstance(self.doc.scope.joint_frame.pose_ids, tuple)

    def test_a_caller_list_is_copied_rather_than_retained(self):
        connections = [connection("k1")]
        collective = scope(connections=connections)
        connections.append(connection("k2", first_site="other"))
        self.assertEqual(len(collective.connections), 1)

    def test_records_are_frozen(self):
        with self.assertRaises(FrozenInstanceError):
            self.doc.document_id = "other"
        with self.assertRaises(FrozenInstanceError):
            self.doc.descriptor_conditions = ()
        with self.assertRaises(FrozenInstanceError):
            self.doc.scope.local_associations[0].slot_id = "slot_2"


# ================================================================================
# 8. Static and runtime isolation
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
            "caller_pose_association", "layer_2a_descriptor_input",
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

    def test_the_layer_2a_module_is_not_imported(self):
        self.assertNotIn("layer_2a_descriptor_input", self.source.replace(
            m.LOCAL_DOCUMENT_TYPE, ""
        ).replace("layer_2a_descriptor_input/1", ""))

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
            name for name, obj in vars(m).items() if isinstance(obj, types.ModuleType)
        }
        self.assertEqual(modules, {"json"})

    def test_no_file_is_opened_at_runtime(self):
        original = builtins.open

        def refuse(*args, **kwargs):
            raise AssertionError("the module opened a file")

        builtins.open = refuse
        try:
            doc = limited_document()
            data = doc.to_json_bytes()
            reloaded = m.Layer2BDescriptorInput.from_json_bytes(data)
            self.assertEqual(reloaded, doc)
            with self.assertRaises(Error):
                m.Layer2BDescriptorInput.from_json_bytes(data + b"\n")
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
        for banned in ("gotne", "avidity", "structure_audit", "files.", "layer_2a"):
            self.assertNotIn(banned, added)


class CoordinatedSemanticAlignment(unittest.TestCase):
    COLLECTIVE = True

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
        if name == "target_participant_id":
            target = replace(original.participants[-1], participant_id="unresolved-target", role="LIGAND")
            first = replace(original.local_associations[0], target_participant_id=target.participant_id)
            return replace(
                original, participants=original.participants + (target,),
                local_associations=(first,) + original.local_associations[1:],
            ), "/scope/local_associations/0/target_participant_id"
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


class CollectiveAlignment(unittest.TestCase):
    assert_wire = CoordinatedSemanticAlignment.assert_wire

    def configuration(self, **overrides):
        payload = dict(
            family=CONFIGURATION,
            definition=definition(
                subjects=("a1", "l1"), numeric=False,
                reference_state=reference_state("NOT_APPLICABLE"),
            ),
            observations=(observation(value=categorical_value()),),
        )
        payload.update(overrides)
        return descriptor(**payload)

    def test_justified_configuration_nonapplicability_removes_only_reference_gap(self):
        for declaration in ("caller justification", "uninterpreted physical assertion"):
            with self.subTest(declaration=declaration):
                first = self.configuration()
                first = replace(first, definition=replace(
                    first.definition,
                    reference_state=replace(
                        first.definition.reference_state, declaration=declaration
                    ),
                ))
                doc = document(descriptors=(first,))
                self.assertEqual(conditions_of(doc, 0), ("PROVIDED",))
                self.assertEqual(doc.descriptor_reasons[0], ())
                self.assertEqual(doc.descriptors[0], first)
                self.assertEqual(
                    tuple(u.state for u in doc.descriptors[0].uncertainties),
                    ("UNKNOWN",) * len(m.L2_UNCERTAINTY_KINDS),
                )
                self.assert_wire(doc)

    def test_configuration_nonapplicability_never_supplies_missing_evidence(self):
        first = self.configuration(observations=(observation(value=None),))
        doc = document(descriptors=(first,))
        self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
        self.assertEqual([r.code for r in doc.descriptor_reasons[0]], ["EVIDENCE_NOT_SUPPLIED"])
        self.assert_wire(doc)

    def test_configuration_nonapplicability_preserves_other_qualification_gaps(self):
        cases = (
            ({"scope": replace(scope(), joint_frame=None)}, "/scope/joint_frame"),
            ({"scope": replace(scope(), missing_declarations=(
                missing("/scope/context_declarations", "context unresolved"),
            ))}, "/scope/context_declarations"),
            ({"scope": replace(scope(), connections=())}, "/scope/connections"),
            ({"poses": (pose(frame_id=None),)}, "/poses/0/frame_id"),
        )
        for changes, pointer in cases:
            with self.subTest(pointer=pointer):
                doc = document(descriptors=(self.configuration(),), **changes)
                self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
                self.assertIn(pointer, reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths)
                self.assertNotIn(
                    "/descriptors/0/definition/reference_state",
                    reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths,
                )
                self.assert_wire(doc)

    def test_configuration_nonapplicability_preserves_ambiguity_and_conflict(self):
        ambiguous = document(descriptors=(self.configuration(ambiguities=(ambiguity(),)),))
        self.assertEqual(conditions_of(ambiguous, 0), ("UNAVAILABLE", "AMBIGUOUS"))
        self.assert_wire(ambiguous)
        observations = (
            observation("o1", value=categorical_value("first")),
            observation("o2", value=categorical_value("second")),
        )
        contradictory = document(descriptors=(self.configuration(
            observations=observations, conflicts=(conflict(),),
        ),))
        self.assertEqual(conditions_of(contradictory, 0), ("PROVIDED", "CONTRADICTORY"))
        self.assertEqual(contradictory.descriptors[0].conflicts, (conflict(),))
        self.assert_wire(contradictory)

    def test_configuration_permission_does_not_qualify_other_families(self):
        first = self.configuration()
        second = descriptor(
            descriptor_id="second", prefix="v",
            definition=definition(reference_state=reference_state("NOT_APPLICABLE")),
        )
        doc = document(descriptors=(first, second))
        self.assertEqual(conditions_of(doc, 0), ("PROVIDED",))
        self.assertEqual(conditions_of(doc, 1), ("UNAVAILABLE",))
        self.assert_wire(doc)

    def test_observation_outside_nonempty_joint_frame_is_refused(self):
        with self.assertRaises(Error) as caught:
            document(
                descriptors=(descriptor(),), poses=(pose(), pose("pose_2")),
                scope=replace(scope(), joint_frame=joint_frame(("pose_2",))),
            )
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
        self.assertEqual(caught.exception.field, "/descriptors/0/observations/0/pose_id")

    def test_explicit_joint_frame_identifier_mismatch_is_refused(self):
        with self.assertRaises(Error) as caught:
            document(descriptors=(descriptor(),), poses=(pose(frame_id="other-frame"),))
        self.assertEqual(caught.exception.code, "REFERENCE_INVALID")
        self.assertEqual(caught.exception.field, "/poses/0/frame_id")

    def test_missing_joint_frame_membership_and_pose_frame_are_retained(self):
        for changes, pointer in (
            ({"scope": replace(scope(), joint_frame=None)}, "/scope/joint_frame"),
            ({"scope": replace(scope(), joint_frame=joint_frame(()))}, "/scope/joint_frame/pose_ids"),
            ({"poses": (pose(frame_id=None),)}, "/poses/0/frame_id"),
        ):
            with self.subTest(pointer=pointer):
                doc = document(descriptors=(descriptor(),), **changes)
                self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
                self.assertIn(pointer, reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths)
                self.assert_wire(doc)

    def test_configuration_element_mapping_gaps_are_retained(self):
        for name in ("identifier_namespace", "chain_id"):
            with self.subTest(field=name):
                chain = replace(chain_instance(), **{name: None})
                alternative = replace(mapping_alternative(), chain_instances=(chain,))
                changed = replace(scope().assembly_elements[0], mapping_alternatives=(alternative,))
                declared_scope = replace(
                    scope(), assembly_elements=(changed,) + scope().assembly_elements[1:]
                )
                doc = document(scope=declared_scope, descriptors=(self.configuration(),))
                self.assertEqual(conditions_of(doc, 0), ("UNAVAILABLE",))
                self.assertIn(
                    "/scope/assembly_elements/0/mapping_alternatives/0/chain_instances/0/" + name,
                    reasons_of(doc, 0)["DECLARATION_MISSING"].field_paths,
                )
                self.assert_wire(doc)


if __name__ == "__main__":
    unittest.main()
