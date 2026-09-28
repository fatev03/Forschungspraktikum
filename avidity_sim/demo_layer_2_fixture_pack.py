"""Frozen synthetic/demo-only Layer 2 fixture pack for the Section 8 ``synthetic-near`` cohort.

SYNTHETIC DEMO ONLY — NON-BIOLOGICAL. Every Layer 2 value here is a manually invented
stand-in for a computational descriptor. Nothing was simulated, computed, measured or
read from a provider, no coordinate file, artifact digest, provider run, real chain or
real residue is referenced, and no biological, binding, affinity, avidity, thermodynamic,
compatibility, safety or success claim is made or implied. Missing evidence is not
negative evidence.

This module builds the nine Layer 2A documents, the three Layer 2B documents and the one
cohort declaration that make the published triage-profile notebook cells runnable, and
then builds the profile through the existing public entry point. It evaluates no Layer 1
outcome: every candidate, scenario, run, slot-binding, state-result, admission and
exclusion identity is copied from the finished report handed to it. It lives outside the
kernel package, opens no file, resolves no locator, reads no clock or environment, starts
no subprocess and reaches no network.
"""
from __future__ import annotations

from dataclasses import dataclass

from gotne import layer_2a_descriptor_input as local_contract
from gotne import layer_2b_descriptor_input as collective_contract
from gotne.layer_2_initial_triage_profile import (
    TRIAGE_CONVENTION_VERSION,
    TRIAGE_DIMENSIONS,
    TriageCandidateInput,
    TriageCohortDeclaration,
    TriageDimensionDirection,
    TriageLocalInput,
    build_initial_triage_profile,
)

__all__ = [
    "SCENARIO_ID",
    "EVALUATION_RUN_REF",
    "CANDIDATE_SLOT_BINDINGS",
    "SLOT_MODULES",
    "COHORT_TASK_SCOPE",
    "TARGET_SYSTEM_IDENTITY",
    "UNCERTAINTY_DECLARATION",
    "FIXTURE_SOURCE_WORDING",
    "SYNTHETIC_NOTICE",
    "Layer2FixturePack",
    "build_layer_2_fixture_pack",
    "build_synthetic_triage_profile",
]

# --------------------------------------------------------------------------------
# Frozen identities, copied from the existing Section 8 synthetic demonstration
# --------------------------------------------------------------------------------

SCENARIO_ID = "synthetic-near"
EVALUATION_RUN_REF = "synthetic-near-run"
SLOT_IDS = ("slot_1", "slot_2", "slot_3")
SLOT_MODULES = {"slot_1": "D1", "slot_2": "D2", "slot_3": "D3"}
CANDIDATE_SLOT_BINDINGS = {
    "z-stable": ("start", "middle", "end"),
    "a-context-sensitive": ("start", "moving", "end"),
    "m-excluded": ("start", "far", "end"),
}
POPULATED_CANDIDATES = ("z-stable", "a-context-sensitive")
DECLARATION_ONLY_CANDIDATES = ("m-excluded",)
CASSETTE_ID = "cas1"
ANCHOR_ID = "a0"
LINKER_IDS = ("s0", "s1", "s2")

TARGET_SYSTEM_IDENTITY = "synthetic-near-target-system"
COHORT_TASK_SCOPE = (
    "Synthetic demo only: cas1 with D1-D2-D3, anchor a0, and linkers s0-s1-s2."
)

# --------------------------------------------------------------------------------
# Frozen fixture wording
# --------------------------------------------------------------------------------

DECLARED_BY = "synthetic-demo-fixture"
DECLARED_AT = "2026-01-01T00:00:00Z"
REVISION = "synthetic-rev-1"
NAMESPACE = "synthetic-fixture"

UNCERTAINTY_DECLARATION = "Synthetic fixture only; uncertainty has not been evaluated."
FIXTURE_SOURCE_WORDING = (
    "Synthetic stand-in for declared computational evidence; manually assigned, not "
    "computed or measured."
)
SYNTHETIC_NOTICE = (
    "SYNTHETIC DEMO ONLY — NON-BIOLOGICAL. Layer 2 values are manually invented "
    "stand-ins for computational descriptors, not simulation results or measurements."
)
CONDITIONS_CONVENTION = (
    "Length-unit and fixed-reference conventions only: lengths are declared in nm "
    "against a fixed synthetic reference."
)
CONDITIONS_OMISSION = (
    "No solvent, membrane, protonation, temperature-dependent or force-field "
    "calculation was performed."
)
CONDITIONS_COMPLETENESS = (
    "Supplied content qualifies fixture completeness only and does not authenticate a "
    "calculation."
)

LOCAL_FAMILY = "LOCAL_ISOLATED_REFERENCE_DEFORMATION_BURDEN"
LOCAL_ABSENT_FAMILY = "LOCAL_OVERLAP"
COLLECTIVE_FAMILY = "COLLECTIVE_INTERFERENCE"
COLLECTIVE_ABSENT_FAMILIES = (
    "COLLECTIVE_DEFORMATION_RESTRAINT_BURDEN",
    "COLLECTIVE_ANCHOR_LINKER_CONFIGURATION",
)
FIXTURE_VALUE = "1"
UNIT_CLASS = "LENGTH"
UNIT_SYMBOL = "nm"

LOCAL_OBSERVABLE_NAME = "synthetic local isolated-reference deformation burden stand-in"
LOCAL_DEFINITION_ID = "synthetic-local-deformation-burden-definition"
COLLECTIVE_OBSERVABLE_NAME = "synthetic collective interference stand-in"
COLLECTIVE_DEFINITION_ID = "synthetic-collective-interference-definition"

_NO_LOCAL_DESCRIPTOR = (
    "Synthetic fixture declares no descriptor for this family; missing evidence is not "
    "negative evidence."
)
_NO_LAYER_2_EVIDENCE = (
    "Synthetic exclusion demonstration: no Layer 2 descriptor is supplied for this "
    "candidate; missing evidence is not negative evidence."
)


# --------------------------------------------------------------------------------
# Small shared builders
# --------------------------------------------------------------------------------


def _reference(contract, identifier):
    return contract.L2ImmutableReference(
        namespace=NAMESPACE, identifier=identifier, revision=REVISION, snapshot_reference=None
    )


def _source(contract, identifier):
    """A fixture source record. The locator stays null: nothing is ever opened."""
    return contract.L2SourceRecord(reference=_reference(contract, identifier), locator=None)


def _snapshot_anchor(contract, identifier):
    """An immutable-snapshot anchor. No digest is invented and no hash is computed."""
    return contract.L2ArtifactAnchor(
        kind="IMMUTABLE_SNAPSHOT",
        algorithm=None,
        digest=None,
        snapshot_reference=_reference(contract, identifier),
    )


def _association(contract, candidate_id, slot_id):
    return contract.L2AssociationReference(
        association_id="synthetic-association-{0}-{1}".format(candidate_id, slot_id),
        revision=REVISION,
        reference=_reference(contract, "synthetic-pose-association-{0}-{1}".format(candidate_id, slot_id)),
    )


def _method(contract, identifier):
    return contract.L2MethodDeclaration(
        reference=_reference(contract, identifier),
        parameters=(
            contract.L2NamedDeclaration(name="conditions_convention", value=CONDITIONS_CONVENTION),
            contract.L2NamedDeclaration(name="conditions_omission", value=CONDITIONS_OMISSION),
            contract.L2NamedDeclaration(name="fixture_completeness", value=CONDITIONS_COMPLETENESS),
        ),
        representation=FIXTURE_SOURCE_WORDING,
        run_reference=_reference(contract, identifier + "-run"),
    )


def _conditions_profile(contract):
    return contract.L2ConditionsProfileReference(
        state="SUPPLIED",
        reference=_reference(contract, "synthetic-conditions-profile"),
        reason=None,
    )


def _uncertainties(contract, prefix):
    return tuple(
        contract.L2UncertaintyRecord(
            uncertainty_id="{0}-uncertainty-{1}".format(prefix, kind.lower()),
            kind=kind,
            state="UNKNOWN",
            observation_ids=(),
            declaration=UNCERTAINTY_DECLARATION,
            source_references=(),
        )
        for kind in contract.L2_UNCERTAINTY_KINDS
    )


def _context_declaration(contract, context_id):
    return contract.L2ContextDeclaration(
        context_id=context_id,
        subject_declaration="Synthetic fixture environment; no real system is described.",
        treatment="OMITTED",
        declaration=CONDITIONS_OMISSION + " " + CONDITIONS_COMPLETENESS,
        source_reference=_source(contract, "synthetic-context-source"),
    )


def _chain_instance(contract, chain_id):
    return contract.L2ChainInstance(
        identifier_namespace="synthetic-toy-chains",
        chain_id=chain_id,
        instance_id="1",
        residue_addressing_reference=_source(contract, "synthetic-residue-addressing"),
        selection_declaration="Toy fixture residues; no real residue numbering is used.",
    )


def _mapping(contract, pose_id, chain_id):
    return contract.L2MappingAlternative(
        pose_id=pose_id,
        chain_instances=(_chain_instance(contract, chain_id),),
        source_reference=_source(contract, "synthetic-mapping-source"),
    )


def _pose(contract, pose_id, candidate_id, slot_id, association):
    return contract.L2PoseRecord(
        pose_id=pose_id,
        artifact_anchor=_snapshot_anchor(contract, "synthetic-artifact-" + pose_id),
        locator=None,
        model_id="synthetic-model-1",
        conformer_id="synthetic-conformer-1",
        frame_id="synthetic-frame-1",
        association_reference=association,
        source_reference=_source(contract, "synthetic-pose-source"),
        run_reference=_reference(contract, "synthetic-fixture-run"),
        method_reference=_reference(contract, "synthetic-fixture-method"),
    )


def _value(contract):
    return contract.L2DescriptorValue(kind="NUMERIC", number=FIXTURE_VALUE, category=None)


# --------------------------------------------------------------------------------
# Layer 1 identity copying
# --------------------------------------------------------------------------------


def _priority_mapping(source):
    """The finished ``synthetic-near`` priority report, as its own serialized mapping.

    ``source`` is the finished demo result, one priority report, or its mapping. No
    Layer 1 evaluation happens here and no upstream object is mutated.
    """
    if isinstance(source, dict):
        mapping = source
    elif hasattr(source, "priority_reports") and hasattr(source, "scenarios"):
        position = None
        for index, scenario in enumerate(source.scenarios):
            if getattr(scenario, "scenario_id", None) == SCENARIO_ID:
                position = index
        if position is None:
            raise ValueError("the supplied demo result declares no {0!r} scenario".format(SCENARIO_ID))
        mapping = source.priority_reports[position].as_dict()
    elif hasattr(source, "as_dict"):
        mapping = source.as_dict()
    else:
        raise TypeError("a finished demo result, priority report or its mapping is required")
    if mapping.get("document_type") != "cassette_candidate_priority/1":
        raise ValueError("a cassette_candidate_priority/1 document is required")
    return mapping


def _layer1_identities(mapping):
    """Candidate identity data copied verbatim from the finished report."""
    identities = {}
    for group in mapping["groups"]:
        for member in group["members"]:
            identities[member["candidate_id"]] = {
                "disposition": "RANKED",
                "slot_binding_hash": member["slot_binding_hash"],
                "state_result_id": member["state_result_id"],
                "certificate_present": member["certificate_present"],
                "ineligibility_reason": None,
            }
    for entry in mapping["excluded"]:
        identities[entry["candidate_id"]] = {
            "disposition": "EXCLUDED",
            "slot_binding_hash": entry["slot_binding_hash"],
            "state_result_id": None,
            "certificate_present": None,
            "ineligibility_reason": entry["ineligibility_reason"],
        }
    return identities


def _admission(contract, candidate_id, identity):
    absent = tuple(
        name
        for name in ("state_result_id", "ineligibility_reason", "certificate_present")
        if identity[name] is None
    )
    return contract.L2AdmissionReference(
        candidate_id=candidate_id,
        slot_binding_hash=identity["slot_binding_hash"],
        state_result_id=identity["state_result_id"],
        ineligibility_reason=identity["ineligibility_reason"],
        certificate_present=identity["certificate_present"],
        absent_keys=absent,
    )


def _candidate_anchor(contract, candidate_id, identity):
    return contract.L2CandidateAnchor(
        candidate_id=candidate_id,
        scenario_id=SCENARIO_ID,
        evaluation_run_ref=EVALUATION_RUN_REF,
        batch_report_reference=_source(contract, "synthetic-batch-report"),
        priority_report_reference=_source(contract, "synthetic-priority-report"),
        scenario_comparison_reference=_source(contract, "synthetic-scenario-comparison"),
        admission_reference=_admission(contract, candidate_id, identity),
    )


# --------------------------------------------------------------------------------
# Layer 2A documents
# --------------------------------------------------------------------------------


def _binder_id(module_id):
    return "synthetic-binder-" + module_id


def _target_id(binding):
    return "synthetic-target-" + binding


def _local_document(candidate_id, slot_id, binding, identity, populated):
    contract = local_contract
    module_id = SLOT_MODULES[slot_id]
    binder_id = _binder_id(module_id)
    target_id = _target_id(binding)
    association = _association(contract, candidate_id, slot_id)
    pose_id = "synthetic-pose-{0}-{1}".format(candidate_id, slot_id)

    if populated:
        mappings = (_mapping(contract, pose_id, "T1"),)
        binder_mappings = (_mapping(contract, pose_id, "B1"),)
        state = "SUPPLIED"
        poses = (_pose(contract, pose_id, candidate_id, slot_id, association),)
    else:
        mappings = ()
        binder_mappings = ()
        state = "ABSENT"
        poses = ()

    participants = (
        contract.L2MolecularParticipant(
            participant_id=binder_id,
            role="BINDER",
            identity_reference=_reference(contract, "synthetic-identity-" + binder_id),
            construct_id="synthetic-construct-" + module_id,
            construct_version=REVISION,
            mapping_state=state,
            mapping_alternatives=binder_mappings,
        ),
        contract.L2MolecularParticipant(
            participant_id=target_id,
            role="RECEPTOR",
            identity_reference=_reference(contract, "synthetic-identity-" + target_id),
            construct_id="synthetic-construct-" + binding,
            construct_version=REVISION,
            mapping_state=state,
            mapping_alternatives=mappings,
        ),
    )

    scope = contract.L2LocalScope(
        slot_id=slot_id,
        binder_participant_id=binder_id,
        target_participant_id=target_id,
        participants=participants,
        association_reference=association,
        target_site_declaration=binding,
        context_declarations=(_context_declaration(contract, "synthetic-context-" + slot_id),),
        missing_declarations=(),
    )

    descriptors = ()
    if populated:
        descriptor_id = "synthetic-local-descriptor-{0}-{1}".format(candidate_id, slot_id)
        definition = contract.L2ObservableDefinition(
            definition_reference=_reference(contract, LOCAL_DEFINITION_ID),
            observable_name=LOCAL_OBSERVABLE_NAME,
            subject_ids=(binder_id, target_id),
            selection_declaration="Toy fixture selection: the whole declared synthetic pair.",
            unit_class=UNIT_CLASS,
            unit_symbol=UNIT_SYMBOL,
            conditions_required=True,
            method=_method(contract, "synthetic-local-method"),
            conditions_profile=_conditions_profile(contract),
            reference_state=contract.L2ReferenceState(
                kind="ISOLATED_FROZEN",
                references=(_source(contract, "synthetic-isolated-frozen-reference"),),
                declaration=(
                    "Synthetic isolated frozen reference; no relaxation, sampling or "
                    "calculation was performed."
                ),
            ),
            comparability_reference=_source(contract, "synthetic-comparability-declaration"),
            limitation=(
                "Synthetic fixture value; it supports contract display only and states "
                "nothing about any real system."
            ),
        )
        observation = contract.L2DescriptorObservation(
            observation_id="synthetic-local-observation-{0}-{1}".format(candidate_id, slot_id),
            pose_id=pose_id,
            sample_id="synthetic-sample-1",
            replicate_id=None,
            source_reference=_source(contract, "synthetic-observation-source"),
            value=_value(contract),
            missing_declarations=(),
        )
        descriptors = (
            contract.L2DescriptorRecord(
                descriptor_id=descriptor_id,
                family=LOCAL_FAMILY,
                scope_declaration=(
                    "Synthetic local scope for slot {0} bound to module {1}.".format(
                        slot_id, module_id
                    )
                ),
                definition=definition,
                observations=(observation,),
                uncertainties=_uncertainties(contract, descriptor_id),
                ambiguities=(),
                conflicts=(),
                missing_declarations=(),
            ),
        )

    availability = (
        contract.L2FamilyAvailability(
            family=LOCAL_ABSENT_FAMILY,
            descriptor_ids=(),
            absence_reason=_NO_LOCAL_DESCRIPTOR if populated else _NO_LAYER_2_EVIDENCE,
        ),
        contract.L2FamilyAvailability(
            family=LOCAL_FAMILY,
            descriptor_ids=tuple(item.descriptor_id for item in descriptors),
            absence_reason=None if descriptors else _NO_LAYER_2_EVIDENCE,
        ),
    )

    return contract.Layer2ADescriptorInput(
        document_id="synthetic-2a-{0}-{1}".format(candidate_id, slot_id),
        revision=REVISION,
        declared_by=DECLARED_BY,
        declared_at=DECLARED_AT,
        source_references=(_source(contract, "synthetic-fixture-provenance"),),
        candidate_anchor=_candidate_anchor(contract, candidate_id, identity),
        scope=scope,
        poses=poses,
        family_availability=availability,
        descriptors=descriptors,
        missing_declarations=(),
    )


# --------------------------------------------------------------------------------
# Layer 2B documents
# --------------------------------------------------------------------------------


def _collective_document(candidate_id, bindings, identity, local_documents, populated):
    contract = collective_contract
    pose_id = "synthetic-collective-pose-" + candidate_id
    binders = tuple(_binder_id(SLOT_MODULES[slot]) for slot in SLOT_IDS)
    targets = tuple(_target_id(binding) for binding in bindings)

    state = "SUPPLIED" if populated else "ABSENT"

    def mappings(chain_id):
        return (_mapping(contract, pose_id, chain_id),) if populated else ()

    participants = tuple(
        contract.L2MolecularParticipant(
            participant_id=binder_id,
            role="BINDER",
            identity_reference=_reference(contract, "synthetic-identity-" + binder_id),
            construct_id="synthetic-construct-" + SLOT_MODULES[slot],
            construct_version=REVISION,
            mapping_state=state,
            mapping_alternatives=mappings("B" + str(position + 1)),
        )
        for position, (slot, binder_id) in enumerate(zip(SLOT_IDS, binders))
    ) + tuple(
        contract.L2MolecularParticipant(
            participant_id=target_id,
            role="RECEPTOR",
            identity_reference=_reference(contract, "synthetic-identity-" + target_id),
            construct_id="synthetic-construct-" + binding,
            construct_version=REVISION,
            mapping_state=state,
            mapping_alternatives=mappings("T" + str(position + 1)),
        )
        for position, (binding, target_id) in enumerate(zip(bindings, targets))
    )

    associations = tuple(
        contract.L2LocalAssociation(
            slot_id=slot,
            binder_participant_id=binders[position],
            target_participant_id=targets[position],
            candidate_id=candidate_id,
            scenario_id=SCENARIO_ID,
            pose_association_reference=_association(contract, candidate_id, slot),
            local_document_reference=contract.L2LocalDocumentReference(
                document_id=local_documents[position].document_id,
                revision=local_documents[position].revision,
                reference=_reference(contract, "synthetic-local-document-" + local_documents[position].document_id),
            ),
            missing_reason=None,
        )
        for position, slot in enumerate(SLOT_IDS)
    )

    elements = tuple(
        contract.L2AssemblyElement(
            element_id=element_id,
            kind=kind,
            identity_reference=_reference(contract, "synthetic-identity-" + element_id),
            construct_id="synthetic-construct-" + element_id,
            construct_version=REVISION,
            mapping_state=state,
            mapping_alternatives=mappings("E" + element_id),
            representation_declaration=(
                "Synthetic toy {0} element; no real chemistry is described.".format(kind.lower())
            ),
        )
        for element_id, kind in ((ANCHOR_ID, "ANCHOR"),) + tuple(
            (linker, "LINKER") for linker in LINKER_IDS
        )
    )

    chain = (ANCHOR_ID, LINKER_IDS[0], binders[0], LINKER_IDS[1], binders[1], LINKER_IDS[2], binders[2])
    connections = tuple(
        contract.L2Connection(
            connection_id="synthetic-connection-{0}".format(position),
            first_subject_id=first,
            first_site_declaration="Synthetic toy site on " + first,
            second_subject_id=second,
            second_site_declaration="Synthetic toy site on " + second,
            connection_declaration=(
                "Declared synthetic coupling a0-s0-D1-s1-D2-s2-D3; no bond, contact or "
                "interaction is asserted."
            ),
            source_reference=_source(contract, "synthetic-connection-source"),
        )
        for position, (first, second) in enumerate(zip(chain, chain[1:]))
    )

    joint_frame = None
    poses = ()
    if populated:
        poses = (
            contract.L2PoseRecord(
                pose_id=pose_id,
                artifact_anchor=_snapshot_anchor(contract, "synthetic-artifact-" + pose_id),
                locator=None,
                model_id="synthetic-collective-model-1",
                conformer_id="synthetic-collective-conformer-1",
                frame_id="synthetic-collective-frame-1",
                association_reference=None,
                source_reference=_source(contract, "synthetic-collective-pose-source"),
                run_reference=_reference(contract, "synthetic-fixture-run"),
                method_reference=_reference(contract, "synthetic-fixture-method"),
            ),
        )
        joint_frame = contract.L2JointFrame(
            frame_id="synthetic-collective-frame-1",
            frame_kind="CALLER_DECLARED_ARTIFACT_MODEL_FRAME",
            pose_ids=(pose_id,),
            declaration=(
                "Separately declared synthetic collective frame; it is not derived from "
                "the three local poses and reconciles no coordinates."
            ),
            source_reference=_source(contract, "synthetic-joint-frame-source"),
        )

    scope = contract.L2CollectiveScope(
        participants=participants,
        local_associations=associations,
        assembly_elements=elements,
        connections=connections,
        joint_frame=joint_frame,
        target_site_declaration=TARGET_SYSTEM_IDENTITY,
        assembly_task_declaration=COHORT_TASK_SCOPE,
        context_declarations=(_context_declaration(contract, "synthetic-collective-context"),),
        missing_declarations=(),
    )

    descriptors = ()
    if populated:
        descriptor_id = "synthetic-collective-descriptor-" + candidate_id
        definition = contract.L2ObservableDefinition(
            definition_reference=_reference(contract, COLLECTIVE_DEFINITION_ID),
            observable_name=COLLECTIVE_OBSERVABLE_NAME,
            subject_ids=binders + targets + (ANCHOR_ID,) + LINKER_IDS,
            selection_declaration=(
                "Toy fixture selection: the declared coupled binders, targets, anchor "
                "and linkers."
            ),
            unit_class=UNIT_CLASS,
            unit_symbol=UNIT_SYMBOL,
            conditions_required=True,
            method=_method(contract, "synthetic-collective-method"),
            conditions_profile=_conditions_profile(contract),
            reference_state=contract.L2ReferenceState(
                kind="ASSEMBLY_REFERENCE",
                references=(_source(contract, "synthetic-assembly-reference"),),
                declaration=(
                    "Synthetic declared assembly reference; no assembly was built, "
                    "sampled or minimized."
                ),
            ),
            comparability_reference=_source(contract, "synthetic-comparability-declaration"),
            limitation=(
                "Synthetic fixture value; it supports contract display only and states "
                "nothing about any real system."
            ),
        )
        observation = contract.L2DescriptorObservation(
            observation_id="synthetic-collective-observation-" + candidate_id,
            pose_id=pose_id,
            sample_id="synthetic-sample-1",
            replicate_id=None,
            source_reference=_source(contract, "synthetic-observation-source"),
            value=_value(contract),
            missing_declarations=(),
        )
        descriptors = (
            contract.L2DescriptorRecord(
                descriptor_id=descriptor_id,
                family=COLLECTIVE_FAMILY,
                scope_declaration=(
                    "Synthetic collective scope for {0} with anchor {1} and linkers "
                    "{2}.".format(CASSETTE_ID, ANCHOR_ID, "-".join(LINKER_IDS))
                ),
                definition=definition,
                observations=(observation,),
                uncertainties=_uncertainties(contract, descriptor_id),
                ambiguities=(),
                conflicts=(),
                missing_declarations=(),
            ),
        )

    availability = (
        contract.L2FamilyAvailability(
            family=COLLECTIVE_FAMILY,
            descriptor_ids=tuple(item.descriptor_id for item in descriptors),
            absence_reason=None if descriptors else _NO_LAYER_2_EVIDENCE,
        ),
    ) + tuple(
        contract.L2FamilyAvailability(
            family=family,
            descriptor_ids=(),
            absence_reason=_NO_LOCAL_DESCRIPTOR if populated else _NO_LAYER_2_EVIDENCE,
        )
        for family in COLLECTIVE_ABSENT_FAMILIES
    )

    return contract.Layer2BDescriptorInput(
        document_id="synthetic-2b-" + candidate_id,
        revision=REVISION,
        declared_by=DECLARED_BY,
        declared_at=DECLARED_AT,
        source_references=(_source(contract, "synthetic-fixture-provenance"),),
        candidate_anchor=_candidate_anchor(contract, candidate_id, identity),
        scope=scope,
        poses=poses,
        family_availability=availability,
        descriptors=descriptors,
        missing_declarations=(),
    )


# --------------------------------------------------------------------------------
# The fixture pack
# --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Layer2FixturePack:
    """The frozen synthetic Layer 2 inputs for one declared comparison cohort."""

    cohort: TriageCohortDeclaration
    candidates: tuple
    local_documents: tuple
    collective_documents: tuple
    layer1_identities: dict


def _cohort_declaration():
    directions = {
        "COLLECTIVE_INTERFERENCE": "LOWER_IS_PREFERRED",
        "COLLECTIVE_DEFORMATION_RESTRAINT_BURDEN": "NO_DIRECTION_DECLARED",
        LOCAL_FAMILY: "LOWER_IS_PREFERRED",
    }
    return TriageCohortDeclaration(
        target_system_identity=TARGET_SYSTEM_IDENTITY,
        layer1_comparison_basis=SCENARIO_ID,
        ordered_local_position_roles=SLOT_IDS,
        collective_task_scope_type=COHORT_TASK_SCOPE,
        triage_convention_version=TRIAGE_CONVENTION_VERSION,
        dimension_directions=tuple(
            TriageDimensionDirection(dimension=dimension, direction=directions[dimension])
            for dimension in TRIAGE_DIMENSIONS
        ),
    )


def build_layer_2_fixture_pack(source):
    """Build the frozen synthetic Layer 2 fixture pack for the ``synthetic-near`` cohort.

    ``source`` is the finished Section 8 demo result, its ``synthetic-near`` priority
    report or that report's mapping. Every Layer 1 identity is copied from it; none is
    reconstructed, and the supplied object is only read.
    """
    identities = _layer1_identities(_priority_mapping(source))
    missing = [name for name in CANDIDATE_SLOT_BINDINGS if name not in identities]
    if missing:
        raise ValueError("the finished report names no entry for: " + ", ".join(missing))

    candidates, local_documents, collective_documents = [], [], []
    for candidate_id, bindings in CANDIDATE_SLOT_BINDINGS.items():
        identity = identities[candidate_id]
        populated = candidate_id in POPULATED_CANDIDATES
        locals_ = tuple(
            _local_document(candidate_id, slot, binding, identity, populated)
            for slot, binding in zip(SLOT_IDS, bindings)
        )
        collective = _collective_document(candidate_id, bindings, identity, locals_, populated)
        local_documents.extend(locals_)
        collective_documents.append(collective)
        candidates.append(
            TriageCandidateInput(
                candidate_id=candidate_id,
                local_inputs=tuple(
                    TriageLocalInput(position_role=slot, document=document.as_dict())
                    for slot, document in zip(SLOT_IDS, locals_)
                ),
                collective_document=collective.as_dict(),
            )
        )
    return Layer2FixturePack(
        cohort=_cohort_declaration(),
        candidates=tuple(candidates),
        local_documents=tuple(local_documents),
        collective_documents=tuple(collective_documents),
        layer1_identities=dict(identities),
    )


def build_synthetic_triage_profile(source, *, pack=None):
    """Build the triage profile through the existing public comparator entry point."""
    pack = pack if pack is not None else build_layer_2_fixture_pack(source)
    return build_initial_triage_profile(
        profile_id="synthetic-near-triage-profile",
        revision=REVISION,
        declared_by=DECLARED_BY,
        declared_at=DECLARED_AT,
        cohort=pack.cohort,
        priority_document=_priority_mapping(source),
        candidates=pack.candidates,
    )
