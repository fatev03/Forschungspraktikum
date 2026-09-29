"""Phase 2 evidence completeness: cassette_evidence_completeness.

Covers the descriptive layer only: the five states and their fixed precedence,
the guarantee that missing or unsupported evidence is never coerced into a pass,
the separation and immutability of the admission reference, the inertness of the
record with respect to eligibility, determinism, and the import boundary that
keeps the module free of every gotne import.

The load-bearing test is NoPromotion: a COMPLETE record built for a vetoed
candidate leaves the real CandidatePriorityReport byte-identical. It exists to
fail loudly if this layer is ever wired into the priority layer.

Kernel outcomes come from the real kernel through the priority test's fixtures.

Run: python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from gotne import cassette_evidence_completeness as completeness  # noqa: E402
from gotne.cassette_evidence_completeness import (  # noqa: E402
    ADMISSION_REFERENCE_KEYS,
    COMPLETENESS_DISPLAY_DISCLAIMER,
    COMPLETENESS_DOCUMENT_TYPE,
    COMPLETENESS_NON_CLAIM,
    DECLARED_SOURCE_STATUS,
    EMPTINESS_CHECKED_FIELDS,
    EVIDENCE_DOCUMENT_KEYS,
    QC_RESULT_FIELDS,
    REQUIRED_ADMISSION_KEYS,
    STATE_PRECEDENCE,
    AdmissionReference,
    CompletenessReason,
    CompletenessState,
    Declared,
    DigestForm,
    EvidenceCompletenessRecord,
    EvidenceDimensions,
    QcResultAvailability,
    ReadCompletion,
    ReasonCode,
    Recognition,
    build_evidence_completeness,
    completeness_state,
    render_lines,
)
from gotne.cassette_candidate_priority import (  # noqa: E402
    AF3_RED_PROVIDER,
    KNOWN_PROVIDERS,
)
from test_phase2_cassette_candidate_priority import (  # noqa: E402
    NOTEBOOK_ARTIFACT_ID,
    NOTEBOOK_SHA256,
    T1_D,
    VETOED_D,
    evidence_record,
    priority_of,
)

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT_DIR / "gotne"
MODULE = "cassette_evidence_completeness"
PROVIDERS = KNOWN_PROVIDERS
CALLER_SIDE_SEAMS = (
    "cassette_slot_ledger",
    "cassette_candidate_batch",
    "cassette_candidate_priority",
    "demo_candidate_manifest",
    "cassette_scenario_comparison",
)
CHAIN_MODULES = ("cassette_frames", "cassette_budget", "cassette_closure", "cassette_node")
PHASE45 = ("composite_density", "so3_grids", "pose_marginalization", "shell_bounds", "intervals")
EXTERNAL_INTAKE = (
    "structure_audit",
    "demo_external_reference",
    "af3_red_adapter",
    "af3_native_bridge",
    "f01_coordinate_admission",
    "structures",
)
IO_MODULES = ("os", "io", "pathlib", "subprocess", "socket", "urllib", "shutil", "tempfile")

#: Anchors are projections of a serialized member or excluded entry. Projecting
#: them explicitly is the point: the copy is visible at the call site.
MEMBER_ANCHOR = {
    "candidate_id": "t1",
    "slot_binding_hash": "b" * 8,
    "state_result_id": "st-" + "a" * 64,
    "certificate_present": True,
}
EXCLUDED_ANCHOR = {
    "candidate_id": "vetoed",
    "slot_binding_hash": "c" * 8,
    "ineligibility_reason": "SLOT_VETOED",
}


#: None is a meaningful argument here -- it is the undeclared-document case --
#: so "not supplied" needs its own sentinel.
_UNSET = object()


def document(**overrides):
    """The notebook's serialized evidence document, with per-field overrides."""
    fields = evidence_record().as_dict()
    fields.update(overrides)
    return fields


def record(anchor=_UNSET, doc=_UNSET, *, providers=PROVIDERS):
    return build_evidence_completeness(
        MEMBER_ANCHOR if anchor is _UNSET else anchor,
        document() if doc is _UNSET else doc,
        providers=providers,
    )


def anchor_of(entry_document):
    """Project a serialized member or excluded entry onto the copied key set."""
    return {
        key: entry_document[key] for key in ADMISSION_REFERENCE_KEYS if key in entry_document
    }


# --------------------------------------------------------------------------
# Non-claim
# --------------------------------------------------------------------------
class NonClaim(unittest.TestCase):
    def test_the_statement_names_every_prohibited_claim(self):
        for term in (
            "affinity",
            "KD",
            "kinetics",
            "occupancy",
            "avidity magnitude",
            "binding probability",
            "efficacy",
            "safety",
            "specificity",
            "experimental success",
            "receptor biology",
            "expression",
            "glycosylation",
        ):
            with self.subTest(term=term):
                self.assertIn(term, COMPLETENESS_NON_CLAIM)

    def test_the_statement_bounds_what_complete_means(self):
        for phrase in (
            "COMPLETE means only that the declared fields were present and well formed",
            "Evidence availability is not evidence quality",
            "not biologically, structurally or functionally equivalent",
            "confers no eligibility",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, COMPLETENESS_NON_CLAIM)

    def test_the_document_carries_the_statement_verbatim(self):
        self.assertEqual(record().as_dict()["non_claim"], COMPLETENESS_NON_CLAIM)
        self.assertEqual(record().non_claim, COMPLETENESS_NON_CLAIM)
        self.assertEqual(record().as_dict()["document_type"], COMPLETENESS_DOCUMENT_TYPE)

    def test_rendering_puts_the_statement_and_disclaimer_first(self):
        lines = render_lines(record())
        self.assertEqual(lines[: len(COMPLETENESS_NON_CLAIM.split("\n"))],
                         COMPLETENESS_NON_CLAIM.split("\n"))
        self.assertIn(COMPLETENESS_DISPLAY_DISCLAIMER, lines)

    def test_rendering_refuses_a_non_record(self):
        for value in (None, {}, "record", record().as_dict()):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(TypeError):
                    render_lines(value)


# --------------------------------------------------------------------------
# States
# --------------------------------------------------------------------------
class States(unittest.TestCase):
    def test_the_vocabulary_is_closed_and_is_exactly_the_five_states(self):
        self.assertEqual(
            {state.value for state in CompletenessState},
            {"COMPLETE", "INCOMPLETE", "UNAVAILABLE", "UNSUPPORTED", "INVALID"},
        )
        self.assertEqual(len(STATE_PRECEDENCE), len(CompletenessState))
        self.assertEqual(set(STATE_PRECEDENCE), set(CompletenessState))

    def test_precedence_is_the_declared_rule_order(self):
        self.assertEqual(
            [state.value for state in STATE_PRECEDENCE],
            ["UNAVAILABLE", "INVALID", "UNSUPPORTED", "INCOMPLETE", "COMPLETE"],
        )

    def test_unavailable_only_for_an_undeclared_document(self):
        self.assertIs(completeness_state(None, providers=PROVIDERS),
                      CompletenessState.UNAVAILABLE)
        self.assertEqual(
            record(doc=None).reasons,
            (CompletenessReason(ReasonCode.DOCUMENT_ABSENT, None),),
        )

    def test_invalid_for_a_non_mapping(self):
        for value in ("a string", 7, [], (), True):
            with self.subTest(value=repr(value)):
                self.assertIs(completeness_state(value, providers=PROVIDERS),
                              CompletenessState.INVALID)

    def test_invalid_for_every_missing_key(self):
        for key in EVIDENCE_DOCUMENT_KEYS:
            with self.subTest(key=key):
                doc = document()
                del doc[key]
                result = record(doc=doc)
                self.assertIs(result.state, CompletenessState.INVALID)
                self.assertIn(
                    CompletenessReason(ReasonCode.DOCUMENT_KEY_MISSING, key), result.reasons
                )

    def test_invalid_for_a_key_outside_the_closed_set(self):
        result = record(doc=document(extra_field="anything"))
        self.assertIs(result.state, CompletenessState.INVALID)
        self.assertIn(
            CompletenessReason(ReasonCode.DOCUMENT_KEY_UNKNOWN, "extra_field"), result.reasons
        )

    def test_invalid_for_every_wrong_field_type(self):
        for key in EVIDENCE_DOCUMENT_KEYS:
            wrong = 7 if key != "read_completed" else "true"
            with self.subTest(key=key):
                result = record(doc=document(**{key: wrong}))
                self.assertIs(result.state, CompletenessState.INVALID)
                self.assertIn(
                    CompletenessReason(ReasonCode.DOCUMENT_FIELD_TYPE, key), result.reasons
                )

    def test_a_non_string_inside_non_admission_reasons_is_invalid(self):
        result = record(doc=document(non_admission_reasons=["ok", 7]))
        self.assertIs(result.state, CompletenessState.INVALID)
        self.assertIn(
            CompletenessReason(ReasonCode.DOCUMENT_FIELD_TYPE, "non_admission_reasons"),
            result.reasons,
        )

    def test_unsupported_for_a_provider_outside_the_allowlist(self):
        result = record(doc=document(provider="some-other-provider"))
        self.assertIs(result.state, CompletenessState.UNSUPPORTED)
        self.assertIn(
            CompletenessReason(ReasonCode.PROVIDER_NOT_DECLARED, "provider"), result.reasons
        )

    def test_unsupported_for_a_source_status_outside_the_vocabulary(self):
        for token in ("supported", "SUPPORTED", "", "approved"):
            with self.subTest(token=token):
                result = record(doc=document(source_status=token))
                self.assertIs(result.state, CompletenessState.UNSUPPORTED)
                self.assertIn(
                    CompletenessReason(ReasonCode.SOURCE_STATUS_NOT_DECLARED, "source_status"),
                    result.reasons,
                )

    def test_every_declared_source_status_is_assessable(self):
        for token in DECLARED_SOURCE_STATUS:
            with self.subTest(token=token):
                self.assertIs(
                    completeness_state(document(source_status=token), providers=PROVIDERS),
                    CompletenessState.COMPLETE,
                )

    def test_incomplete_for_every_empty_checked_field(self):
        for key in EMPTINESS_CHECKED_FIELDS:
            with self.subTest(key=key):
                result = record(doc=document(**{key: ""}))
                self.assertIs(result.state, CompletenessState.INCOMPLETE)
                self.assertIn(
                    CompletenessReason(ReasonCode.FIELD_EMPTY, key), result.reasons
                )

    def test_incomplete_for_a_malformed_digest(self):
        for digest in ("NOT-A-DIGEST-!!", "abc", NOTEBOOK_SHA256.upper(), "z" * 64):
            with self.subTest(digest=digest):
                result = record(doc=document(observed_sha256=digest))
                self.assertIs(result.state, CompletenessState.INCOMPLETE)
                self.assertIn(
                    CompletenessReason(ReasonCode.DIGEST_MALFORMED, "observed_sha256"),
                    result.reasons,
                )
                self.assertIs(result.dimensions.digest_form, DigestForm.MALFORMED)

    def test_an_empty_digest_is_reported_once_as_empty_and_never_as_well_formed(self):
        result = record(doc=document(observed_sha256=""))
        self.assertIs(result.state, CompletenessState.INCOMPLETE)
        self.assertIs(result.dimensions.digest_form, DigestForm.NOT_ASSESSED)
        self.assertEqual(
            [r for r in result.reasons if r.field == "observed_sha256"],
            [CompletenessReason(ReasonCode.FIELD_EMPTY, "observed_sha256")],
        )

    def test_complete_for_the_well_formed_notebook_document(self):
        result = record()
        self.assertIs(result.state, CompletenessState.COMPLETE)
        self.assertEqual(result.reasons, ())
        self.assertIs(result.dimensions.digest_form, DigestForm.WELL_FORMED)
        self.assertEqual(
            result.dimensions.field_presence,
            tuple((name, Declared.PRESENT) for name in EMPTINESS_CHECKED_FIELDS),
        )

    def test_the_classifier_is_total_over_every_single_field_override(self):
        seen = set()
        for key in EVIDENCE_DOCUMENT_KEYS:
            for value in ("", "x", 7, True, [], ["r"]):
                doc = document(**{key: value})
                seen.add(completeness_state(doc, providers=PROVIDERS))
        self.assertTrue(seen.issubset(set(CompletenessState)))
        self.assertEqual(seen, set(CompletenessState) - {CompletenessState.UNAVAILABLE})

    def test_only_complete_carries_no_reason(self):
        for doc in (None, "x", document(profile=""), document(provider="other"), document()):
            result = record(doc=doc)
            with self.subTest(state=result.state.value):
                self.assertEqual(result.reasons == (),
                                 result.state is CompletenessState.COMPLETE)


# --------------------------------------------------------------------------
# Missing is never coerced
# --------------------------------------------------------------------------
class MissingIsNeverCoerced(unittest.TestCase):
    def test_no_state_is_none_or_boolean(self):
        for doc in (None, "x", document(profile=""), document(provider="other"), document()):
            state = completeness_state(doc, providers=PROVIDERS)
            with self.subTest(state=state.value):
                self.assertIsInstance(state, CompletenessState)
                self.assertNotIsInstance(state, bool)

    def test_unavailable_invalid_and_unsupported_are_not_complete(self):
        for doc in (None, "x", {}, document(provider="other"), document(source_status="")):
            with self.subTest(doc=repr(doc)[:40]):
                self.assertIsNot(
                    completeness_state(doc, providers=PROVIDERS), CompletenessState.COMPLETE
                )

    def test_unsupported_is_not_folded_into_incomplete(self):
        self.assertIs(
            completeness_state(document(provider="other"), providers=PROVIDERS),
            CompletenessState.UNSUPPORTED,
        )

    def test_an_unsupported_document_leaves_completeness_not_assessed(self):
        dimensions = record(doc=document(provider="other")).dimensions
        self.assertEqual(
            dimensions.field_presence,
            tuple((name, Declared.NOT_ASSESSED) for name in EMPTINESS_CHECKED_FIELDS),
        )
        self.assertIs(dimensions.digest_form, DigestForm.NOT_ASSESSED)
        self.assertIs(dimensions.qc_result_availability, QcResultAvailability.NOT_ASSESSED)

    def test_an_absent_document_is_carried_as_null_not_as_an_empty_document(self):
        result = record(doc=None)
        self.assertIsNone(result.evidence_document)
        self.assertIsNone(result.as_dict()["evidence_document"])
        self.assertIs(result.dimensions.read_completion, ReadCompletion.NOT_ASSESSED)

    def test_absent_qc_results_are_reported_absent_never_available(self):
        doc = document(execution_state="", validation_status="")
        self.assertIs(
            record(doc=doc).dimensions.qc_result_availability, QcResultAvailability.ABSENT
        )
        one = document(validation_status="")
        self.assertIs(
            record(doc=one).dimensions.qc_result_availability, QcResultAvailability.PARTIAL
        )
        self.assertEqual(len(QC_RESULT_FIELDS), 2)


# --------------------------------------------------------------------------
# Availability is not quality
# --------------------------------------------------------------------------
class AvailabilityIsNotQuality(unittest.TestCase):
    def test_a_declared_incomplete_read_never_lowers_the_state(self):
        result = record(doc=document(read_completed=False))
        self.assertIs(result.state, CompletenessState.COMPLETE)
        self.assertIs(result.dimensions.read_completion, ReadCompletion.DECLARED_FALSE)

    def test_non_admission_reasons_never_lower_the_state(self):
        loud = document(non_admission_reasons=["a", "b", "c", "d"])
        self.assertIs(completeness_state(loud, providers=PROVIDERS), CompletenessState.COMPLETE)
        self.assertEqual(
            record(doc=loud).dimensions.non_admission_reasons, ("a", "b", "c", "d")
        )

    def test_what_a_qc_value_says_is_never_read(self):
        for value in ("passed", "failed", "catastrophic_failure", "unknown"):
            with self.subTest(value=value):
                result = record(doc=document(validation_status=value))
                self.assertIs(result.state, CompletenessState.COMPLETE)
                self.assertIs(
                    result.dimensions.qc_result_availability, QcResultAvailability.AVAILABLE
                )

    def test_a_rejected_source_status_is_assessable_and_not_a_lower_state(self):
        result = record(doc=document(source_status="rejected"))
        self.assertIs(result.state, CompletenessState.COMPLETE)
        self.assertIs(result.dimensions.source_status_recognition, Recognition.DECLARED)

    def test_recognition_is_membership_not_ranking(self):
        self.assertEqual(
            {value.value for value in Recognition},
            {"DECLARED", "NOT_DECLARED", "NOT_ASSESSED"},
        )


# --------------------------------------------------------------------------
# Equal state is not equivalence
# --------------------------------------------------------------------------
class EqualStateIsNotEquivalence(unittest.TestCase):
    def test_two_complete_records_stay_distinguishable_in_payload(self):
        first = record(doc=document(artifact_id="artifact-one"))
        second = record(doc=document(artifact_id="artifact-two"))
        self.assertIs(first.state, second.state)
        self.assertNotEqual(first.to_json_bytes(), second.to_json_bytes())
        self.assertNotEqual(
            first.evidence_document["artifact_id"], second.evidence_document["artifact_id"]
        )

    def test_the_module_exposes_no_comparison_or_ordering_entry_point(self):
        for name in dir(completeness):
            with self.subTest(name=name):
                for banned in ("compare", "rank", "score", "sort", "order", "prioriti", "best"):
                    self.assertNotIn(banned, name.lower())

    def test_the_document_carries_no_rank_score_order_or_eligibility_key(self):
        def keys(node):
            found = set()
            if isinstance(node, dict):
                for key, value in node.items():
                    found.add(key)
                    found |= keys(value)
            elif isinstance(node, list):
                for item in node:
                    found |= keys(item)
            return found

        present = keys(record().as_dict())
        for banned in (
            "rank",
            "score",
            "order",
            "priority",
            "tier",
            "eligible",
            "eligibility",
            "promoted",
            "accepted",
            "weight",
            "confidence",
        ):
            with self.subTest(key=banned):
                self.assertNotIn(banned, {key.lower() for key in present})


# --------------------------------------------------------------------------
# Admission stays immutable and separate
# --------------------------------------------------------------------------
class AdmissionIsImmutableAndSeparate(unittest.TestCase):
    def test_the_anchor_is_a_separate_sub_object(self):
        payload = record().as_dict()
        self.assertEqual(
            sorted(payload),
            ["admission_reference", "completeness", "document_type", "evidence_document",
             "non_claim"],
        )
        self.assertEqual(sorted(payload["completeness"]), ["dimensions", "reasons", "state"])

    def test_every_anchor_field_is_copied_verbatim(self):
        anchor = record(anchor=MEMBER_ANCHOR).admission_reference
        self.assertEqual(anchor.candidate_id, MEMBER_ANCHOR["candidate_id"])
        self.assertEqual(anchor.slot_binding_hash, MEMBER_ANCHOR["slot_binding_hash"])
        self.assertEqual(anchor.state_result_id, MEMBER_ANCHOR["state_result_id"])
        self.assertIs(anchor.certificate_present, True)

    def test_an_absent_optional_key_is_named_not_invented(self):
        anchor = record(anchor=MEMBER_ANCHOR).admission_reference
        self.assertEqual(anchor.absent_keys, ("ineligibility_reason",))
        self.assertIsNone(anchor.ineligibility_reason)

    def test_a_vetoed_anchor_is_carried_and_never_cleared(self):
        result = record(anchor=EXCLUDED_ANCHOR)
        self.assertEqual(result.admission_reference.ineligibility_reason, "SLOT_VETOED")
        self.assertIs(result.state, CompletenessState.COMPLETE)
        self.assertEqual(
            result.as_dict()["admission_reference"]["ineligibility_reason"], "SLOT_VETOED"
        )

    def test_a_missing_required_key_yields_no_record(self):
        for key in REQUIRED_ADMISSION_KEYS:
            anchor = dict(MEMBER_ANCHOR)
            del anchor[key]
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    record(anchor=anchor)

    def test_an_empty_or_non_string_required_key_yields_no_record(self):
        for value in ("", 7, None):
            with self.subTest(value=repr(value)):
                with self.assertRaises(ValueError):
                    record(anchor={**MEMBER_ANCHOR, "candidate_id": value})

    def test_a_non_mapping_anchor_is_refused(self):
        for value in (None, "t1", 7, ["t1"]):
            with self.subTest(value=repr(value)):
                with self.assertRaises(TypeError):
                    record(anchor=value)

    def test_an_unprojected_excluded_entry_is_refused_rather_than_trimmed(self):
        report = priority_of([VETOED_D()])
        entry = report.as_dict()["excluded"][0]
        with self.assertRaises(ValueError):
            record(anchor=entry)
        projected = anchor_of(entry)
        self.assertEqual(
            record(anchor=projected).admission_reference.ineligibility_reason, "SLOT_VETOED"
        )

    def test_a_real_member_and_excluded_entry_both_project_cleanly(self):
        report = priority_of([T1_D(), VETOED_D()])
        payload = report.as_dict()
        member = payload["groups"][0]["members"][0]
        excluded = payload["excluded"][0]
        for entry in (member, excluded):
            with self.subTest(candidate=entry["candidate_id"]):
                built = record(anchor=anchor_of(entry))
                self.assertEqual(built.admission_reference.candidate_id, entry["candidate_id"])
                self.assertEqual(
                    built.admission_reference.slot_binding_hash, entry["slot_binding_hash"]
                )

    def test_the_anchor_mapping_is_not_mutated(self):
        anchor = dict(MEMBER_ANCHOR)
        snapshot = json.dumps(anchor, sort_keys=True)
        record(anchor=anchor)
        self.assertEqual(json.dumps(anchor, sort_keys=True), snapshot)

    def test_the_evidence_document_is_not_mutated(self):
        doc = document()
        snapshot = json.dumps(doc, sort_keys=True)
        record(doc=doc)
        self.assertEqual(json.dumps(doc, sort_keys=True), snapshot)

    def test_the_carried_document_is_a_fresh_container(self):
        doc = document()
        result = record(doc=doc)
        result.evidence_document["artifact_id"] = "mutated"
        self.assertEqual(doc["artifact_id"], NOTEBOOK_ARTIFACT_ID)
        self.assertEqual(result.as_dict()["evidence_document"]["artifact_id"], "mutated")


# --------------------------------------------------------------------------
# No promotion
# --------------------------------------------------------------------------
class NoPromotion(unittest.TestCase):
    def test_a_complete_record_leaves_the_priority_report_byte_identical(self):
        declarations = [T1_D(), VETOED_D()]
        before = priority_of(declarations).to_json_bytes()
        built = [
            record(anchor=anchor_of(entry))
            for entry in priority_of(declarations).as_dict()["excluded"]
        ]
        self.assertTrue(built)
        self.assertIs(built[0].state, CompletenessState.COMPLETE)
        after = priority_of(declarations).to_json_bytes()
        self.assertEqual(before, after)

    def test_a_vetoed_candidate_stays_excluded_whatever_its_completeness_state(self):
        for doc in (None, "x", document(profile=""), document(provider="other"), document()):
            report = priority_of([VETOED_D()])
            built = record(anchor=anchor_of(report.as_dict()["excluded"][0]), doc=doc)
            with self.subTest(state=built.state.value):
                payload = report.as_dict()
                self.assertEqual(payload["groups"], [])
                self.assertEqual(payload["excluded"][0]["ineligibility_reason"], "SLOT_VETOED")
                self.assertEqual(built.admission_reference.ineligibility_reason, "SLOT_VETOED")

    def test_the_record_exposes_no_way_to_reach_an_admission_decision(self):
        built = record()
        for name in ("eligible", "promote", "admit", "veto", "exclude"):
            with self.subTest(name=name):
                self.assertFalse(
                    any(name in attr.lower() for attr in dir(built) if not attr.startswith("_")),
                    f"the record exposes an attribute suggesting {name}",
                )

    def test_the_priority_layer_does_not_import_this_module(self):
        for path in sorted(PACKAGE_DIR.glob("*.py")):
            if path.stem == MODULE:
                continue
            with self.subTest(module=path.stem):
                self.assertNotIn(MODULE, _imported(path.read_text()),
                                 f"{path.stem} imports {MODULE}")


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------
class Determinism(unittest.TestCase):
    def test_identical_declared_inputs_give_identical_bytes(self):
        self.assertEqual(record().to_json_bytes(), record().to_json_bytes())

    def test_key_insertion_order_never_changes_the_output(self):
        doc = document()
        reordered = {key: doc[key] for key in reversed(EVIDENCE_DOCUMENT_KEYS)}
        self.assertEqual(
            record(doc=doc).to_json_bytes(), record(doc=reordered).to_json_bytes()
        )

    def test_reasons_are_emitted_in_declared_field_order(self):
        blanked = document(profile="", artifact_id="", validation_status="")
        self.assertEqual(
            [reason.field for reason in record(doc=blanked).reasons],
            [name for name in EMPTINESS_CHECKED_FIELDS
             if name in ("profile", "artifact_id", "validation_status")],
        )

    def test_unknown_keys_are_reported_in_sorted_order(self):
        doc = document()
        doc["zeta"] = 1
        doc["alpha"] = 1
        self.assertEqual(
            [r.field for r in record(doc=doc).reasons
             if r.code is ReasonCode.DOCUMENT_KEY_UNKNOWN],
            ["alpha", "zeta"],
        )

    def test_canonical_bytes_are_stable_across_pythonhashseed(self):
        program = (
            "import json, pathlib, sys\n"
            f"sys.path.insert(0, {str(ROOT_DIR)!r})\n"
            f"sys.path.insert(0, {str(pathlib.Path(__file__).resolve().parent)!r})\n"
            "from gotne.cassette_evidence_completeness import build_evidence_completeness\n"
            "from test_phase2_cassette_candidate_priority import evidence_record\n"
            "from gotne.cassette_candidate_priority import KNOWN_PROVIDERS\n"
            f"anchor = {MEMBER_ANCHOR!r}\n"
            "built = build_evidence_completeness(anchor, evidence_record().as_dict(),"
            " providers=KNOWN_PROVIDERS)\n"
            "sys.stdout.write(built.to_json_bytes().decode())\n"
        )
        outputs = set()
        for seed in ("0", "1", "12345"):
            completed = subprocess.run(
                [sys.executable, "-B", "-c", program],
                capture_output=True,
                text=True,
                timeout=300,
                env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
            outputs.add(completed.stdout)
        self.assertEqual(len(outputs), 1, "canonical bytes vary with PYTHONHASHSEED")

    def test_no_nan_or_infinity_can_enter_the_document(self):
        with self.assertRaises(ValueError):
            record(doc=document(profile=float("nan"))).to_json_bytes()


# --------------------------------------------------------------------------
# No ordering, no score
# --------------------------------------------------------------------------
class NoOrderingOrScore(unittest.TestCase):
    def test_the_module_declares_no_numeric_or_fitted_constant(self):
        source = (PACKAGE_DIR / f"{MODULE}.py").read_text()
        numeric = []
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name) and t.id.isupper()]
            if names and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, (int, float)) and not isinstance(
                    node.value.value, bool
                ):
                    numeric.extend(names)
        self.assertEqual(numeric, [], f"module-level numeric constants declared: {numeric}")
        for banned in ("threshold", "weight", "probability", "score", "confidence", "fitted"):
            with self.subTest(term=banned):
                self.assertNotIn(f"{banned} =", source.lower(), f"the module assigns a {banned}")

    def test_no_arithmetic_operator_touches_a_reported_value(self):
        source = (PACKAGE_DIR / f"{MODULE}.py").read_text()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.BinOp):
                self.assertIsInstance(
                    node.op, (ast.Add,), "only string and list joins use an operator"
                )

    def test_the_module_never_sorts_a_candidate_or_a_reported_value(self):
        source = (PACKAGE_DIR / f"{MODULE}.py").read_text()
        sorted_args = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "sorted"
        ]
        # sorted() appears only to make key-fault reporting deterministic.
        self.assertEqual(len(sorted_args), 2, "sorted() is used beyond deterministic key faults")

    def test_the_module_calls_no_evaluation_entry_point(self):
        source = (PACKAGE_DIR / f"{MODULE}.py").read_text()
        called = {
            node.func.id
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for entry_point in (
            "evaluate_state",
            "evaluate_node",
            "issue_state_certificate",
            "evaluate_candidate_batch",
            "evaluate_candidate_priority",
            "build_slot_ledger",
            "classify_evidence",
            "geometry_tier",
            "open",
        ):
            with self.subTest(entry_point=entry_point):
                self.assertNotIn(entry_point, called, f"{MODULE} calls {entry_point}")


# --------------------------------------------------------------------------
# Import boundary
# --------------------------------------------------------------------------
def _imported(source):
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[-1] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.module:
                    names.add(node.module.split(".")[-1])
                names.update(alias.name for alias in node.names)
            elif node.module and node.module.startswith("gotne"):
                names.add(node.module.split(".")[-1])
                names.update(alias.name for alias in node.names)
    return names


class ImportBoundary(unittest.TestCase):
    def setUp(self):
        self.source = (PACKAGE_DIR / f"{MODULE}.py").read_text()

    def test_the_module_imports_nothing_from_gotne(self):
        for node in ast.walk(ast.parse(self.source)):
            if isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "no relative import into the package")
                self.assertFalse(
                    (node.module or "").startswith("gotne"),
                    "the module consumes serialized documents, never gotne objects",
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(alias.name.split(".")[0] == "gotne")

    def test_the_module_avoids_the_chain_the_seams_the_intake_tree_and_io(self):
        imported = _imported(self.source)
        for forbidden in CALLER_SIDE_SEAMS + CHAIN_MODULES + PHASE45 + EXTERNAL_INTAKE + IO_MODULES:
            with self.subTest(module=forbidden):
                self.assertNotIn(forbidden, imported, f"{MODULE} imports {forbidden}")

    def test_the_declared_imports_are_exactly_the_standard_library_set(self):
        """Pin every import, not only the gotne-shaped ones _imported() sees."""
        modules = set()
        for node in ast.walk(ast.parse(self.source)):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                modules.add(node.module or "")
        self.assertEqual(
            modules, {"json", "re", "collections.abc", "dataclasses", "enum", "typing",
                      "__future__"},
        )

    def test_the_package_surface_is_unchanged(self):
        import gotne

        self.assertNotIn(MODULE, gotne.__all__)
        for name in ("EvidenceCompletenessRecord", "CompletenessState",
                     "build_evidence_completeness"):
            self.assertNotIn(name, gotne.__all__, "the layer is reachable by submodule only")

    def test_a_dynamic_run_loads_no_phase4_or_phase5_module(self):
        """Importing any submodule runs gotne/__init__, which imports the chain,
        so the chain is expected here. Phase 4 and Phase 5 must stay unreachable,
        and the static sweep above already pins this module's own imports."""
        program = (
            "import sys\n"
            f"sys.path.insert(0, {str(ROOT_DIR)!r})\n"
            "import gotne.cassette_evidence_completeness as m\n"
            f"leaked = [n for n in sys.modules if n.split('.')[-1] in {PHASE45!r}]\n"
            "sys.stdout.write('LEAKED:' + ','.join(sorted(leaked)))\n"
        )
        completed = subprocess.run(
            [sys.executable, "-B", "-c", program], capture_output=True, text=True, timeout=300
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        self.assertEqual(completed.stdout.strip(), "LEAKED:", completed.stdout)


# --------------------------------------------------------------------------
# Immutability
# --------------------------------------------------------------------------
class Immutability(unittest.TestCase):
    def test_records_are_frozen(self):
        built = record()
        for target, name in (
            (built, "state"),
            (built.admission_reference, "candidate_id"),
            (built.dimensions, "digest_form"),
            (built.reasons or (CompletenessReason(ReasonCode.FIELD_EMPTY, "profile"),), None),
        ):
            if name is None:
                continue
            with self.subTest(target=type(target).__name__):
                with self.assertRaises(FrozenInstanceError):
                    setattr(target, name, "mutated")

    def test_as_dict_returns_fresh_containers(self):
        built = record()
        first, second = built.as_dict(), built.as_dict()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        first["completeness"]["reasons"].append("injected")
        self.assertEqual(built.as_dict()["completeness"]["reasons"], [])

    def test_every_declared_container_is_a_tuple(self):
        built = record(doc=document(profile=""))
        self.assertIsInstance(built.reasons, tuple)
        self.assertIsInstance(built.dimensions.field_presence, tuple)
        self.assertIsInstance(built.dimensions.non_admission_reasons, tuple)
        self.assertIsInstance(built.admission_reference.absent_keys, tuple)

    def test_the_record_refuses_an_inconsistent_state_and_reason_pairing(self):
        built = record()
        with self.assertRaises(ValueError):
            EvidenceCompletenessRecord(
                admission_reference=built.admission_reference,
                state=CompletenessState.COMPLETE,
                dimensions=built.dimensions,
                reasons=(CompletenessReason(ReasonCode.FIELD_EMPTY, "profile"),),
                evidence_document=None,
            )
        with self.assertRaises(ValueError):
            EvidenceCompletenessRecord(
                admission_reference=built.admission_reference,
                state=CompletenessState.INCOMPLETE,
                dimensions=built.dimensions,
                reasons=(),
                evidence_document=None,
            )

    def test_providers_has_no_implicit_default(self):
        with self.assertRaises(TypeError):
            build_evidence_completeness(MEMBER_ANCHOR, document())
        for bad in ((), [], "af3-red", (""), None):
            with self.subTest(providers=repr(bad)):
                with self.assertRaises((TypeError, ValueError)):
                    build_evidence_completeness(MEMBER_ANCHOR, document(), providers=bad)

    def test_the_declared_provider_constant_is_accepted(self):
        self.assertIn(AF3_RED_PROVIDER, PROVIDERS)
        self.assertIs(
            completeness_state(document(), providers=(AF3_RED_PROVIDER,)),
            CompletenessState.COMPLETE,
        )


if __name__ == "__main__":
    unittest.main()
