"""Demo candidate manifest: demo_candidate_manifest.

Covers the intake/declaration seam only: the record and its closed refusals, the
lossless mapping to public CandidateDeclaration objects, the explicit
non-refusals, determinism, canonical serialization and the import boundary.

The mapping is checked against the real public path end to end:

  declare_candidate_manifest -> to_candidate_declarations
    -> evaluate_candidate_batch -> evaluate_candidate_priority

The fixture declares a root anchor position, as the priority tests do, because
the shared budget fixture leaves AnchorSpec.position MISSING and the first
ENGAGED module's node gate then reads an invalid input.

Run: python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError, replace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from gotne import EvaluationContext, TargetContext, TargetGeometry  # noqa: E402
from gotne.cassette_candidate_batch import (  # noqa: E402
    CandidateDeclaration,
    evaluate_candidate_batch,
)
from gotne.cassette_candidate_priority import (  # noqa: E402
    KNOWN_PROVIDERS,
    evaluate_candidate_priority,
)
from gotne.cassette_slots import SLOT_IDS, SlotId, validate_slot_binding  # noqa: E402
from gotne.cassette_state import EngagementLabel  # noqa: E402
from gotne.demo_candidate_manifest import (  # noqa: E402
    CONTRACT_INVALID,
    MANIFEST_DOCUMENT_TYPE,
    MANIFEST_INVALID,
    MANIFEST_NON_CLAIM,
    MAX_ANNOTATION_LENGTH,
    REFUSAL_REASONS,
    Combination,
    CombinationSource,
    DemoCandidateManifest,
    DemoCandidateManifestError,
    Presence,
    SlotCandidates,
    SlotChoice,
    cartesian_combinations,
    declare_candidate_manifest,
    to_candidate_declarations,
)
from gotne.identity import canonical_form  # noqa: E402
from test_phase2_cassette_budget import budget_cfg  # noqa: E402

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT_DIR / "gotne"
MODULE = "demo_candidate_manifest"
PHASE45 = ("composite_density", "so3_grids", "pose_marginalization", "shell_bounds", "intervals")
CHAIN_MODULES = ("cassette_frames", "cassette_budget", "cassette_closure", "cassette_node")
FORBIDDEN_SEAMS = ("cassette_slot_ledger", "cassette_candidate_priority")
EXTERNAL_INTAKE = (
    "structure_audit",
    "demo_external_reference",
    "af3_red_adapter",
    "af3_native_bridge",
    "declared_geometry_input",
    "f01_coordinate_admission",
    "structures",
)
IO_MODULES = ("os", "io", "pathlib", "subprocess", "socket", "urllib", "shutil", "tempfile")

ROOT_POSITION = (0.0, 0.0, 0.0)
IDENTITY_R = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
#: Four declared target sites the caller supplies. The manifest never builds or
#: reads these; tB and tC are the two that close the chain from tA.
SITES = {
    "tA": (0.0, 0.0, 0.0),
    "tB": (2.0, 0.0, 0.0),
    "tC": (4.0, 0.0, 0.0),
    "tD": (200.0, 0.0, 0.0),
}

CANDIDATE = Presence.CANDIDATE
UNENGAGED = Presence.UNENGAGED
DECLARED = CombinationSource.DECLARED_LIST
PRODUCT = CombinationSource.CARTESIAN_PRODUCT


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
def rooted_cfg(policy=None):
    cfg = budget_cfg(policy)
    return replace(cfg, anchors=tuple(replace(a, position=ROOT_POSITION) for a in cfg.anchors))


def context():
    return EvaluationContext(
        TargetContext(tuple((t, TargetGeometry(site, IDENTITY_R)) for t, site in SITES.items()))
    )


#: Fixture 1 of the contract: two candidates in slot_1, one in slot_2, two in
#: slot_3, declared in a deliberately non-alphabetical order.
SLOTS_212 = {"slot_1": ("tA", "tD"), "slot_2": ("tB",), "slot_3": ("tC", "tA")}


def manifest(
    *,
    scenario_id="demo.s1",
    primary_context_ref="ctx.primary",
    slots=None,
    source=PRODUCT,
    max_combinations=8,
    combinations=None,
    prefix="cand",
    annotation="declared by hand for the demo",
):
    return declare_candidate_manifest(
        scenario_id=scenario_id,
        primary_context_ref=primary_context_ref,
        slots=SLOTS_212 if slots is None else slots,
        combination_source=source,
        max_combinations=max_combinations,
        combinations=combinations,
        candidate_id_prefix=prefix if source is PRODUCT else None,
        source_annotation=annotation,
    )


def combo(candidate_id, *labels):
    """One combination; None declares UNENGAGED for that slot."""
    return Combination(
        candidate_id,
        tuple(
            SlotChoice(UNENGAGED, None) if label is None else SlotChoice(CANDIDATE, label)
            for label in labels
        ),
    )


def declared(*combinations, slots=None, max_combinations=8, annotation="subset"):
    return manifest(
        slots=slots,
        source=DECLARED,
        max_combinations=max_combinations,
        combinations=tuple(combinations),
        annotation=annotation,
    )


def refusal(case, reason, code=CONTRACT_INVALID):
    """Assert one closed refusal and that no manifest was produced."""
    with case.assertRaises(DemoCandidateManifestError) as caught:
        yield_value = None  # noqa: F841
    return caught


# --------------------------------------------------------------------------
# Scope and non-claim
# --------------------------------------------------------------------------
class NonClaim(unittest.TestCase):
    def test_the_statement_names_every_prohibited_claim(self):
        for term in (
            "sequence quality",
            "structure",
            "affinity",
            "binding",
            "avidity magnitude",
            "expression",
            "specificity",
            "activity",
            "accessibility",
            "safety",
            "probability",
            "biological performance",
            "experimental outcome",
            "opaque identifier",
            "never parsed",
        ):
            with self.subTest(term=term):
                self.assertIn(term, MANIFEST_NON_CLAIM)

    def test_the_document_carries_the_statement_verbatim(self):
        document = manifest().as_dict()
        self.assertEqual(document["non_claim"], MANIFEST_NON_CLAIM)
        self.assertEqual(manifest().non_claim, MANIFEST_NON_CLAIM)
        self.assertEqual(json.loads(manifest().to_json_bytes())["non_claim"], MANIFEST_NON_CLAIM)

    def test_an_altered_statement_is_refused_on_reload(self):
        document = manifest().as_dict()
        document["non_claim"] = "trust me"
        with self.assertRaises(DemoCandidateManifestError) as caught:
            DemoCandidateManifest.from_dict(document)
        self.assertEqual(caught.exception.reason, "NON_CLAIM_ALTERED")
        self.assertEqual(caught.exception.code, MANIFEST_INVALID)


# --------------------------------------------------------------------------
# Fixture 1: the 2/1/2 manifest and the product rule
# --------------------------------------------------------------------------
class ProductRule(unittest.TestCase):
    def test_the_product_cardinality_is_four(self):
        built = manifest()
        self.assertEqual(len(built.combinations), 4)
        self.assertEqual([r.slot for r in built.slots], list(SLOT_IDS))
        self.assertEqual([len(r.candidates) for r in built.slots], [2, 1, 2])

    def test_odometer_order_with_slot_1_most_significant(self):
        built = manifest()
        self.assertEqual(
            [tuple(c.label for c in combination.choices) for combination in built.combinations],
            [("tA", "tB", "tC"), ("tA", "tB", "tA"), ("tD", "tB", "tC"), ("tD", "tB", "tA")],
            "slot_1 is the most significant position; slot_3 varies fastest",
        )
        self.assertEqual(
            [combination.candidate_id for combination in built.combinations],
            ["cand-0", "cand-1", "cand-2", "cand-3"],
        )

    def test_the_product_emits_only_candidate_choices(self):
        for combination in manifest().combinations:
            for choice in combination.choices:
                self.assertIs(choice.presence, CANDIDATE)
                self.assertIsNotNone(choice.label)

    def test_candidate_order_inside_a_slot_is_the_callers_order(self):
        reversed_slots = {"slot_1": ("tD", "tA"), "slot_2": ("tB",), "slot_3": ("tC", "tA")}
        built = manifest(slots=reversed_slots)
        self.assertEqual(built.slots[0].candidates, ("tD", "tA"))
        self.assertEqual(
            [c.choices[0].label for c in built.combinations], ["tD", "tD", "tA", "tA"]
        )

    def test_the_helper_and_the_manifest_agree(self):
        built = manifest()
        direct = cartesian_combinations(built.slots, "cand", 8)
        self.assertEqual(
            [c.as_dict() for c in built.combinations], [c.as_dict() for c in direct]
        )


# --------------------------------------------------------------------------
# Fixture 2: a caller-selected subset through the real public path
# --------------------------------------------------------------------------
class DeclaredSubset(unittest.TestCase):
    def setUp(self):
        # Two of the four product combinations, in non-product, non-alphabetical order.
        self.built = declared(combo("zebra", "tD", "tB", "tC"), combo("alpha", "tA", "tB", "tC"))
        self.cfg, self.ctx = rooted_cfg(), context()
        self.declarations = to_candidate_declarations(self.built, self.cfg, self.ctx)

    def test_declaration_order_is_the_declared_combination_order(self):
        self.assertEqual([d.candidate_id for d in self.declarations], ["zebra", "alpha"])
        ids = [d.candidate_id for d in self.declarations]
        self.assertNotEqual(ids, sorted(ids), "the fixture order must not be alphabetical")

    def test_the_batch_preserves_the_manifest_order(self):
        report = evaluate_candidate_batch(list(self.declarations))
        self.assertEqual(report.as_dict()["candidate_order"], ["zebra", "alpha"])

    def test_the_priority_report_preserves_it_within_its_group(self):
        report = evaluate_candidate_priority(
            evaluate_candidate_batch(list(self.declarations)),
            evidence={},
            providers=KNOWN_PROVIDERS,
        )
        ranked = [m.candidate_id for g in report.groups for m in g.members]
        excluded = [e.candidate_id for e in report.excluded]
        self.assertEqual(sorted(ranked + excluded), ["alpha", "zebra"])
        # tD sits far from tA, so "zebra" is excluded and "alpha" is ranked. The
        # kernel decides that, not the manifest.
        self.assertEqual(ranked, ["alpha"])
        self.assertEqual(excluded, ["zebra"])
        self.assertIsNotNone(report.excluded[0].state_status_reason)

    def test_a_declared_list_needs_no_prefix_and_refuses_one(self):
        with self.assertRaises(DemoCandidateManifestError) as caught:
            declare_candidate_manifest(
                scenario_id="s",
                primary_context_ref="c",
                slots=SLOTS_212,
                combination_source=DECLARED,
                max_combinations=4,
                combinations=(combo("a", "tA", "tB", "tC"),),
                candidate_id_prefix="cand",
                source_annotation="",
            )
        self.assertEqual(caught.exception.reason, "COMBINATION_SOURCE_AMBIGUOUS")


# --------------------------------------------------------------------------
# Fixture 3: annotation inertness
# --------------------------------------------------------------------------
class AnnotationIsInert(unittest.TestCase):
    def _pair(self):
        shape = (combo("zebra", "tD", "tB", "tC"), combo("alpha", "tA", "tB", "tC"))
        return (
            declared(*shape, annotation="from a hand-written list"),
            declared(*shape, annotation="from a completely different note"),
        )

    def test_the_documents_differ_only_in_the_annotation(self):
        first, second = self._pair()
        a, b = first.as_dict(), second.as_dict()
        self.assertNotEqual(a["source_annotation"], b["source_annotation"])
        a.pop("source_annotation")
        b.pop("source_annotation")
        self.assertEqual(a, b)

    def test_the_emitted_declarations_are_byte_identical(self):
        first, second = self._pair()
        cfg, ctx = rooted_cfg(), context()
        one = to_candidate_declarations(first, cfg, ctx)
        two = to_candidate_declarations(second, cfg, ctx)
        self.assertEqual(
            [canonical_form(d.binding) for d in one], [canonical_form(d.binding) for d in two]
        )
        self.assertEqual([d.candidate_id for d in one], [d.candidate_id for d in two])
        self.assertEqual(
            evaluate_candidate_batch(list(one)).to_json_bytes(),
            evaluate_candidate_batch(list(two)).to_json_bytes(),
            "the annotation never reaches a declaration",
        )

    def test_the_annotation_appears_in_no_declaration_field(self):
        built = declared(combo("a", "tA", "tB", "tC"), annotation="SECRET-ANNOTATION-TOKEN")
        declarations = to_candidate_declarations(built, rooted_cfg(), context())
        rendered = json.dumps(
            [
                {
                    "candidate_id": d.candidate_id,
                    "binding": str(canonical_form(d.binding)),
                }
                for d in declarations
            ]
        )
        self.assertNotIn("SECRET-ANNOTATION-TOKEN", rendered)
        self.assertIn("SECRET-ANNOTATION-TOKEN", built.as_dict()["source_annotation"])

    def test_the_annotation_is_bounded_and_must_be_text(self):
        declared(combo("a", "tA", "tB", "tC"), annotation="x" * MAX_ANNOTATION_LENGTH)
        for bad in ("x" * (MAX_ANNOTATION_LENGTH + 1), None, 7, ["note"]):
            with self.subTest(annotation=type(bad).__name__):
                with self.assertRaises(DemoCandidateManifestError) as caught:
                    declared(combo("a", "tA", "tB", "tC"), annotation=bad)
                self.assertEqual(caught.exception.reason, "MALFORMED_DOCUMENT")


# --------------------------------------------------------------------------
# Fixture 4: mapping fidelity
# --------------------------------------------------------------------------
class MappingFidelity(unittest.TestCase):
    def setUp(self):
        self.cfg, self.ctx = rooted_cfg(), context()
        self.modules = tuple(self.cfg.cassettes[0].ordered_modules)

    def test_the_label_becomes_target_id_and_module_id_comes_from_cfg(self):
        built = declared(combo("a", "tA", "tB", "tC"), combo("b", "tA", "tB", None))
        for declaration, combination in zip(
            to_candidate_declarations(built, self.cfg, self.ctx), built.combinations
        ):
            with self.subTest(candidate=declaration.candidate_id):
                assignments = declaration.binding.ordered_assignments()
                self.assertEqual([a.slot for a in assignments], list(SLOT_IDS))
                self.assertEqual([a.module_id for a in assignments], list(self.modules))
                for assignment, choice in zip(assignments, combination.choices):
                    if choice.presence is CANDIDATE:
                        self.assertIs(assignment.label, EngagementLabel.ENGAGED)
                        self.assertEqual(assignment.target_id, choice.label)
                    else:
                        self.assertIs(assignment.label, EngagementLabel.UNENGAGED)
                        self.assertIsNone(assignment.target_id)

    def test_no_manifest_field_names_a_module(self):
        document = manifest().as_dict()
        self.assertNotIn("module_id", json.dumps(document))
        for name in self.modules:
            self.assertNotIn(name, json.dumps(document), "a manifest declares no module id")

    def test_policy_is_cfg_policy(self):
        built = declared(combo("a", "tA", "tB", "tC"))
        declaration = to_candidate_declarations(built, self.cfg, self.ctx)[0]
        self.assertIs(declaration.policy, self.cfg.policy)
        self.assertIs(declaration.cfg, self.cfg)
        self.assertIs(declaration.context, self.ctx)

    def test_the_emitted_binding_passes_validate_slot_binding_unchanged(self):
        built = declared(combo("a", "tA", "tB", "tC"))
        declaration = to_candidate_declarations(built, self.cfg, self.ctx)[0]
        self.assertIsNone(validate_slot_binding(declaration.binding, self.cfg))
        source = (PACKAGE_DIR / f"{MODULE}.py").read_text()
        self.assertNotIn(
            "validate_slot_binding(", source, "the manifest never calls the validator itself"
        )

    def test_the_mapping_returns_a_tuple_of_public_declarations(self):
        declarations = to_candidate_declarations(manifest(), self.cfg, self.ctx)
        self.assertIsInstance(declarations, tuple)
        self.assertEqual(len(declarations), 4)
        for declaration in declarations:
            self.assertIsInstance(declaration, CandidateDeclaration)

    def test_the_mapping_refuses_a_bad_argument_or_cassette_arity(self):
        built = manifest()
        for args, reason in (
            ((built.as_dict(), self.cfg, self.ctx), "MALFORMED_DOCUMENT"),
            ((built, self.cfg.policy, self.ctx), "CASSETTE_ARITY_UNSUPPORTED"),
            ((built, self.cfg, self.cfg), "MALFORMED_DOCUMENT"),
        ):
            with self.subTest(reason=reason):
                with self.assertRaises(DemoCandidateManifestError) as caught:
                    to_candidate_declarations(*args)
                self.assertEqual(caught.exception.reason, reason)
        two_modules = replace(
            self.cfg,
            cassettes=(replace(self.cfg.cassettes[0], ordered_modules=("D1", "D2")),),
        )
        with self.assertRaises(DemoCandidateManifestError) as caught:
            to_candidate_declarations(built, two_modules, self.ctx)
        self.assertEqual(caught.exception.reason, "CASSETTE_ARITY_UNSUPPORTED")
        no_cassette = replace(self.cfg, cassettes=())
        with self.assertRaises(DemoCandidateManifestError) as caught:
            to_candidate_declarations(built, no_cassette, self.ctx)
        self.assertEqual(caught.exception.reason, "CASSETTE_ARITY_UNSUPPORTED")


# --------------------------------------------------------------------------
# Fixture 5: every closed refusal
# --------------------------------------------------------------------------
class Refusals(unittest.TestCase):
    def _reason(self, call):
        with self.assertRaises(DemoCandidateManifestError) as caught:
            call()
        self.assertIn(caught.exception.reason, REFUSAL_REASONS)
        self.assertIn(caught.exception.code, (CONTRACT_INVALID, MANIFEST_INVALID))
        self.assertEqual(len(caught.exception.diagnostics), 1)
        return caught.exception.reason

    def test_invalid_label(self):
        for slots in (
            {"slot_1": ("",), "slot_2": ("tB",), "slot_3": ("tC",)},
            {"slot_1": ("_leading",), "slot_2": ("tB",), "slot_3": ("tC",)},
            {"slot_1": ("x" * 101,), "slot_2": ("tB",), "slot_3": ("tC",)},
            {"slot_1": (None,), "slot_2": ("tB",), "slot_3": ("tC",)},
        ):
            with self.subTest(slots=slots["slot_1"]):
                self.assertEqual(
                    self._reason(lambda s=slots: manifest(slots=s, max_combinations=4)),
                    "INVALID_LABEL",
                )
        self.assertEqual(
            self._reason(lambda: manifest(scenario_id="")), "INVALID_LABEL"
        )
        self.assertEqual(
            self._reason(lambda: manifest(primary_context_ref="!bad")), "INVALID_LABEL"
        )
        self.assertEqual(self._reason(lambda: manifest(prefix="")), "INVALID_LABEL")

    def test_empty_slot_candidate_list(self):
        self.assertEqual(
            self._reason(
                lambda: manifest(slots={"slot_1": (), "slot_2": ("tB",), "slot_3": ("tC",)})
            ),
            "EMPTY_SLOT_CANDIDATE_LIST",
        )

    def test_duplicate_candidate_label_within_a_slot(self):
        self.assertEqual(
            self._reason(
                lambda: manifest(
                    slots={"slot_1": ("tA", "tA"), "slot_2": ("tB",), "slot_3": ("tC",)}
                )
            ),
            "DUPLICATE_CANDIDATE_LABEL",
        )

    def test_missing_slot_and_unknown_slot_name(self):
        self.assertEqual(
            self._reason(lambda: manifest(slots={"slot_1": ("tA",), "slot_2": ("tB",)})),
            "MISSING_SLOT",
        )
        self.assertEqual(
            self._reason(
                lambda: manifest(
                    slots={"slot_1": ("tA",), "slot_2": ("tB",), "slot_3": ("tC",), "slot_4": ("tD",)}
                )
            ),
            "UNKNOWN_FIELD",
        )
        self.assertEqual(self._reason(lambda: manifest(slots=["tA"])), "MISSING_SLOT")

    def test_slot_record_misnamed_and_duplicate_slot(self):
        good = manifest()
        self.assertEqual(
            self._reason(lambda: replace(good, slots=(good.slots[1], good.slots[0], good.slots[2]))),
            "SLOT_RECORD_MISNAMED",
        )
        self.assertEqual(
            self._reason(lambda: replace(good, slots=(good.slots[0], good.slots[0], good.slots[2]))),
            "DUPLICATE_SLOT",
        )
        document = good.as_dict()
        document["slots"][0]["slot"] = "slot_9"
        self.assertEqual(
            self._reason(lambda: DemoCandidateManifest.from_dict(document)),
            "SLOT_RECORD_MISNAMED",
        )

    def test_choice_presence_inconsistent(self):
        self.assertEqual(self._reason(lambda: SlotChoice(CANDIDATE, None)), "CHOICE_PRESENCE_INCONSISTENT")
        self.assertEqual(self._reason(lambda: SlotChoice(UNENGAGED, "tA")), "CHOICE_PRESENCE_INCONSISTENT")
        self.assertEqual(self._reason(lambda: SlotChoice("CANDIDATE", "tA")), "CHOICE_PRESENCE_INCONSISTENT")
        self.assertEqual(
            self._reason(lambda: Combination("a", (SlotChoice(CANDIDATE, "tA"),))),
            "CHOICE_PRESENCE_INCONSISTENT",
        )
        self.assertEqual(
            self._reason(lambda: Combination("a", ("tA", "tB", "tC"))),
            "CHOICE_PRESENCE_INCONSISTENT",
        )

    def test_undeclared_candidate_reference(self):
        self.assertEqual(
            self._reason(lambda: declared(combo("a", "tZZ", "tB", "tC"))),
            "UNDECLARED_CANDIDATE_REFERENCE",
        )
        # tC is declared, but in slot_3, not slot_2: slots are not interchangeable.
        self.assertEqual(
            self._reason(lambda: declared(combo("a", "tA", "tC", "tC"))),
            "UNDECLARED_CANDIDATE_REFERENCE",
        )

    def test_duplicate_combination_is_refused_not_deduplicated(self):
        self.assertEqual(
            self._reason(
                lambda: declared(combo("a", "tA", "tB", "tC"), combo("b", "tA", "tB", "tC"))
            ),
            "DUPLICATE_COMBINATION",
        )

    def test_empty_combination_list(self):
        self.assertEqual(self._reason(lambda: declared()), "EMPTY_COMBINATION_LIST")
        self.assertEqual(
            self._reason(
                lambda: declare_candidate_manifest(
                    scenario_id="s",
                    primary_context_ref="c",
                    slots=SLOTS_212,
                    combination_source=DECLARED,
                    combinations=None,
                    candidate_id_prefix=None,
                    max_combinations=4,
                    source_annotation="",
                )
            ),
            "COMBINATION_SOURCE_AMBIGUOUS",
        )

    def test_duplicate_candidate_id(self):
        self.assertEqual(
            self._reason(
                lambda: declared(combo("same", "tA", "tB", "tC"), combo("same", "tD", "tB", "tC"))
            ),
            "DUPLICATE_CANDIDATE_ID",
        )

    def test_combination_source_ambiguous(self):
        self.assertEqual(
            self._reason(
                lambda: manifest(source=PRODUCT, combinations=(combo("a", "tA", "tB", "tC"),))
            ),
            "COMBINATION_SOURCE_AMBIGUOUS",
        )
        self.assertEqual(
            self._reason(lambda: manifest(source="CARTESIAN_PRODUCT")),
            "COMBINATION_SOURCE_AMBIGUOUS",
        )
        document = manifest().as_dict()
        document["combination_source"] = "SOMETHING_ELSE"
        self.assertEqual(
            self._reason(lambda: DemoCandidateManifest.from_dict(document)),
            "COMBINATION_SOURCE_AMBIGUOUS",
        )

    def test_max_combinations_overflow_and_shape(self):
        self.assertEqual(self._reason(lambda: manifest(max_combinations=3)), "MAX_COMBINATIONS_EXCEEDED")
        self.assertEqual(
            self._reason(
                lambda: declared(
                    combo("a", "tA", "tB", "tC"),
                    combo("b", "tD", "tB", "tC"),
                    max_combinations=1,
                )
            ),
            "MAX_COMBINATIONS_EXCEEDED",
        )
        for bad in (0, -1, True, 2.0, "4"):
            with self.subTest(max_combinations=bad):
                self.assertEqual(
                    self._reason(lambda b=bad: manifest(max_combinations=b)),
                    "MAX_COMBINATIONS_EXCEEDED",
                )

    def test_unknown_field_and_malformed_document(self):
        document = manifest().as_dict()
        document["extra"] = 1
        self.assertEqual(
            self._reason(lambda: DemoCandidateManifest.from_dict(document)), "UNKNOWN_FIELD"
        )
        short = manifest().as_dict()
        short.pop("scenario_id")
        self.assertEqual(
            self._reason(lambda: DemoCandidateManifest.from_dict(short)), "MALFORMED_DOCUMENT"
        )
        for bad in (None, [], "manifest", 7):
            with self.subTest(document=type(bad).__name__):
                self.assertEqual(
                    self._reason(lambda b=bad: DemoCandidateManifest.from_dict(b)),
                    "MALFORMED_DOCUMENT",
                )
        wrong_type = manifest().as_dict()
        wrong_type["document_type"] = "demo_candidate_manifest/2"
        self.assertEqual(
            self._reason(lambda: DemoCandidateManifest.from_dict(wrong_type)),
            "MALFORMED_DOCUMENT",
        )
        wrong_order = manifest().as_dict()
        wrong_order["order"] = ["slot_3", "slot_2", "slot_1"]
        self.assertEqual(
            self._reason(lambda: DemoCandidateManifest.from_dict(wrong_order)),
            "MALFORMED_DOCUMENT",
        )

    def test_duplicate_json_key_and_non_canonical_bytes(self):
        raw = manifest().to_json_bytes()
        self.assertEqual(
            self._reason(
                lambda: DemoCandidateManifest.from_json_bytes(
                    raw.replace(b'"scenario_id":', b'"scenario_id":"x","scenario_id":', 1)
                )
            ),
            "DUPLICATE_JSON_KEY",
        )
        self.assertEqual(
            self._reason(lambda: DemoCandidateManifest.from_json_bytes(b" " + raw)),
            "NOT_CANONICAL_BYTES",
        )
        self.assertEqual(
            self._reason(lambda: DemoCandidateManifest.from_json_bytes(b"{")),
            "MALFORMED_DOCUMENT",
        )
        self.assertEqual(
            self._reason(lambda: DemoCandidateManifest.from_json_bytes("text")),
            "MALFORMED_DOCUMENT",
        )

    def test_a_product_document_whose_list_was_edited_is_refused(self):
        document = manifest().as_dict()
        document["combinations"] = document["combinations"][:2]
        self.assertEqual(
            self._reason(lambda: DemoCandidateManifest.from_dict(document)), "MALFORMED_DOCUMENT"
        )
        reordered = manifest().as_dict()
        reordered["combinations"] = list(reversed(reordered["combinations"]))
        self.assertEqual(
            self._reason(lambda: DemoCandidateManifest.from_dict(reordered)), "MALFORMED_DOCUMENT"
        )

    def test_every_closed_reason_is_reachable_or_named(self):
        self.assertEqual(len(REFUSAL_REASONS), len(set(REFUSAL_REASONS)))
        self.assertIn("CASSETTE_ARITY_UNSUPPORTED", REFUSAL_REASONS)

    def test_the_error_carries_code_reason_slot_and_field(self):
        with self.assertRaises(DemoCandidateManifestError) as caught:
            manifest(slots={"slot_1": ("tA", "tA"), "slot_2": ("tB",), "slot_3": ("tC",)})
        error = caught.exception
        self.assertEqual((error.code, error.reason), (CONTRACT_INVALID, "DUPLICATE_CANDIDATE_LABEL"))
        self.assertEqual(error.slot, "slot_1")
        self.assertEqual(error.field, "candidates")
        self.assertEqual(error.diagnostics[0]["severity"], "error")


# --------------------------------------------------------------------------
# Fixture 6: the explicit non-refusals
# --------------------------------------------------------------------------
class NonRefusals(unittest.TestCase):
    def test_a_label_repeated_across_slots_is_permitted(self):
        built = manifest(slots={"slot_1": ("tA",), "slot_2": ("tA",), "slot_3": ("tA",)}, max_combinations=1)
        self.assertEqual(len(built.combinations), 1)
        declarations = to_candidate_declarations(built, rooted_cfg(), context())
        targets = [a.target_id for a in declarations[0].binding.ordered_assignments()]
        self.assertEqual(targets, ["tA", "tA", "tA"], "OQ-9 permits a repeated target_id")
        self.assertIsNone(validate_slot_binding(declarations[0].binding, rooted_cfg()))

    def test_an_all_unengaged_combination_is_permitted(self):
        built = declared(combo("none", None, None, None))
        declarations = to_candidate_declarations(built, rooted_cfg(), context())
        assignments = declarations[0].binding.ordered_assignments()
        self.assertTrue(all(a.label is EngagementLabel.UNENGAGED for a in assignments))
        self.assertTrue(all(a.target_id is None for a in assignments))
        report = evaluate_candidate_priority(
            evaluate_candidate_batch(list(declarations)), evidence={}, providers=KNOWN_PROVIDERS
        )
        self.assertEqual(report.excluded, ())
        self.assertEqual(len(report.groups), 1)

    def test_a_label_with_no_target_is_not_refused_here(self):
        built = declared(combo("ghost", "tA", "tB", "tC"), slots={"slot_1": ("tA",), "slot_2": ("tB",), "slot_3": ("tC", "tGHOST")})
        extra = declared(
            combo("ghost", "tA", "tB", "tGHOST"),
            slots={"slot_1": ("tA",), "slot_2": ("tB",), "slot_3": ("tC", "tGHOST")},
        )
        # The manifest accepts it: tGHOST is a declared label, and the manifest
        # never inspects context.targets.
        declarations = to_candidate_declarations(extra, rooted_cfg(), context())
        self.assertEqual(declarations[0].binding.slot_3.target_id, "tGHOST")
        report = evaluate_candidate_priority(
            evaluate_candidate_batch(list(declarations)), evidence={}, providers=KNOWN_PROVIDERS
        )
        self.assertEqual(len(report.excluded), 1, "the kernel decides, not the manifest")
        self.assertEqual(report.excluded[0].candidate_id, "ghost")
        self.assertIsNotNone(report.excluded[0].state_status_reason)
        self.assertIsNotNone(built)

    def test_the_manifest_never_reads_context_targets(self):
        # Checked over the AST, not the text: the docstring names context.targets
        # in prose precisely to say it is never inspected.
        tree = ast.parse((PACKAGE_DIR / f"{MODULE}.py").read_text())
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        for forbidden in ("targets", "lookup", "tolerances", "site_nm", "orientation"):
            with self.subTest(attribute=forbidden):
                self.assertNotIn(forbidden, attributes, f"{MODULE} reads .{forbidden}")
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for constructor in ("TargetContext", "TargetGeometry", "EvaluationContext"):
            with self.subTest(constructor=constructor):
                self.assertNotIn(constructor, called, f"{MODULE} constructs a {constructor}")


# --------------------------------------------------------------------------
# Fixture 7: bound enforcement
# --------------------------------------------------------------------------
class Bounds(unittest.TestCase):
    def test_the_bound_is_checked_before_any_combination_is_built(self):
        with self.assertRaises(DemoCandidateManifestError) as caught:
            manifest(max_combinations=3)
        self.assertEqual(caught.exception.reason, "MAX_COMBINATIONS_EXCEEDED")
        self.assertEqual(caught.exception.field, "max_combinations")

    def test_the_exact_bound_succeeds(self):
        built = manifest(max_combinations=4)
        self.assertEqual(len(built.combinations), 4)

    def test_nothing_is_truncated_or_sampled(self):
        built = manifest(max_combinations=100)
        self.assertEqual(len(built.combinations), 4, "the product is exact, never padded")


# --------------------------------------------------------------------------
# Fixture 8: determinism, immutability, canonical bytes
# --------------------------------------------------------------------------
class Serialization(unittest.TestCase):
    def test_canonical_bytes_are_deterministic_and_round_trip(self):
        first, second = manifest().to_json_bytes(), manifest().to_json_bytes()
        self.assertEqual(first, second)
        reloaded = DemoCandidateManifest.from_json_bytes(first)
        self.assertEqual(reloaded.to_json_bytes(), first)
        data = json.loads(first)
        self.assertEqual(data["document_type"], MANIFEST_DOCUMENT_TYPE)
        self.assertEqual(list(data), sorted(data), "sort_keys orders object keys")
        self.assertEqual(data["order"], ["slot_1", "slot_2", "slot_3"])
        self.assertEqual(
            [c["candidate_id"] for c in data["combinations"]],
            ["cand-0", "cand-1", "cand-2", "cand-3"],
            "arrays keep the order they were built in",
        )

    def test_an_unengaged_choice_round_trips_as_an_explicit_null(self):
        built = declared(combo("mixed", "tA", None, "tC"), combo("none", None, None, None))
        data = json.loads(built.to_json_bytes())
        choices = data["combinations"][0]["choices"]
        self.assertEqual([c["presence"] for c in choices], ["CANDIDATE", "UNENGAGED", "CANDIDATE"])
        self.assertIsNone(choices[1]["label"], "absence is an explicit null, never an empty label")
        self.assertNotIn('"label":""', built.to_json_bytes().decode("utf-8"))
        reloaded = DemoCandidateManifest.from_json_bytes(built.to_json_bytes())
        self.assertEqual(reloaded.to_json_bytes(), built.to_json_bytes())
        self.assertIs(reloaded.combinations[0].choices[1].presence, UNENGAGED)
        self.assertIsNone(reloaded.combinations[0].choices[1].label)

    def test_a_document_encoding_absence_as_an_empty_label_is_refused(self):
        document = declared(combo("mixed", "tA", None, "tC")).as_dict()
        document["combinations"][0]["choices"][1]["label"] = ""
        with self.assertRaises(DemoCandidateManifestError) as caught:
            DemoCandidateManifest.from_dict(document)
        self.assertEqual(caught.exception.reason, "CHOICE_PRESENCE_INCONSISTENT")

    def test_the_document_carries_exactly_the_declared_keys(self):
        self.assertEqual(
            set(json.loads(manifest().to_json_bytes())),
            {
                "document_type",
                "non_claim",
                "scenario_id",
                "primary_context_ref",
                "order",
                "slots",
                "combination_source",
                "max_combinations",
                "candidate_id_prefix",
                "combinations",
                "source_annotation",
            },
        )

    def test_arrays_are_not_sorted_by_label_or_id(self):
        built = declared(combo("zebra", "tD", "tB", "tC"), combo("alpha", "tA", "tB", "tC"))
        ids = [c["candidate_id"] for c in built.as_dict()["combinations"]]
        self.assertEqual(ids, ["zebra", "alpha"])
        self.assertNotEqual(ids, sorted(ids))
        self.assertEqual(built.as_dict()["slots"][0]["candidates"], ["tA", "tD"])

    def test_records_are_frozen_and_as_dict_is_fresh(self):
        built = manifest()
        with self.assertRaises(FrozenInstanceError):
            built.scenario_id = "x"
        with self.assertRaises(FrozenInstanceError):
            built.slots[0].candidates = ()
        with self.assertRaises(FrozenInstanceError):
            built.combinations[0].candidate_id = "x"
        with self.assertRaises(FrozenInstanceError):
            built.combinations[0].choices[0].label = "x"
        first, second = built.as_dict(), built.as_dict()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        first["combinations"].clear()
        first["slots"][0]["candidates"].append("ghost")
        self.assertEqual(built.as_dict(), second)

    def test_every_container_is_a_tuple(self):
        built = manifest()
        self.assertIsInstance(built.slots, tuple)
        self.assertIsInstance(built.slots[0].candidates, tuple)
        self.assertIsInstance(built.combinations, tuple)
        self.assertIsInstance(built.combinations[0].choices, tuple)

    def test_the_slot_accessor_is_named_not_positional(self):
        built = manifest()
        self.assertIs(built.slot("slot_2"), built.slots[1])
        self.assertIs(built.slot(SlotId.SLOT_3), built.slots[2])
        with self.assertRaises(DemoCandidateManifestError) as caught:
            built.slot("slot_9")
        self.assertEqual(caught.exception.reason, "MISSING_SLOT")

    def test_canonical_bytes_are_stable_across_pythonhashseed(self):
        program = (
            "import sys\n"
            f"sys.path.insert(0, {str(ROOT_DIR)!r})\n"
            f"sys.path.insert(0, {str(ROOT_DIR / 'tests')!r})\n"
            "from test_phase2_demo_candidate_manifest import manifest\n"
            "sys.stdout.write(manifest().to_json_bytes().hex())\n"
        )
        digests = set()
        for seed in ("0", "1", "12345"):
            completed = subprocess.run(
                [sys.executable, "-B", "-c", program],
                capture_output=True,
                text=True,
                timeout=300,
                env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            )
            self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
            digests.add(completed.stdout)
        self.assertEqual(len(digests), 1, "manifest bytes differ across PYTHONHASHSEED")

    def test_no_nan_or_infinity_can_enter_the_document(self):
        text = manifest().to_json_bytes().decode("utf-8")
        for token in ("NaN", "Infinity", "-Infinity"):
            self.assertNotIn(token, text)


# --------------------------------------------------------------------------
# Fixture 9: static import isolation
# --------------------------------------------------------------------------
class ImportBoundary(unittest.TestCase):
    def _imported(self, source):
        names = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[-1] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    if node.module:
                        names.add(node.module.split(".")[-1])
                    names.update(a.name for a in node.names)
                elif node.module and node.module.startswith("gotne"):
                    names.add(node.module.split(".")[-1])
                    names.update(a.name for a in node.names)
        return names

    def test_direct_imports_are_the_declared_set_only(self):
        imported = self._imported((PACKAGE_DIR / f"{MODULE}.py").read_text())
        for forbidden in (
            CHAIN_MODULES + PHASE45 + FORBIDDEN_SEAMS + EXTERNAL_INTAKE + IO_MODULES
        ):
            with self.subTest(module=forbidden):
                self.assertNotIn(forbidden, imported, f"{MODULE} imports {forbidden}")
        for allowed in (
            "cassette_candidate_batch",
            "cassette_slots",
            "cassette_state",
            "cassette_schema",
        ):
            with self.subTest(module=allowed):
                self.assertIn(allowed, imported)

    def test_static_closure_reaches_no_phase4_or_phase5_module(self):
        seen, queue = set(), [MODULE]
        while queue:
            name = queue.pop()
            if name in seen:
                continue
            path = PACKAGE_DIR / f"{name}.py"
            if not path.is_file():
                continue
            seen.add(name)
            for imported in self._imported(path.read_text()):
                self.assertNotIn(imported, PHASE45, f"{name} reaches {imported}")
                queue.append(imported)
        self.assertIn("cassette_candidate_batch", seen, "the scan walked into the consumed seam")

    def test_no_existing_module_imports_the_manifest(self):
        for path in sorted(PACKAGE_DIR.glob("*.py")):
            if path.stem == MODULE:
                continue
            with self.subTest(module=path.stem):
                self.assertNotIn(
                    MODULE, self._imported(path.read_text()), f"{path.stem} imports {MODULE}"
                )

    def test_the_package_surface_is_unchanged(self):
        import gotne

        self.assertNotIn(MODULE, gotne.__all__)
        for name in ("DemoCandidateManifest", "declare_candidate_manifest", "SlotChoice"):
            self.assertNotIn(name, gotne.__all__, "the manifest is reachable by submodule only")

    def test_the_manifest_calls_no_evaluation_entry_point(self):
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
            "validate_slot_binding",
            "project_engagement_state",
            "open",
        ):
            with self.subTest(entry_point=entry_point):
                self.assertNotIn(entry_point, called, f"{MODULE} calls {entry_point}")

    def test_the_module_declares_no_ranking_or_numeric_criterion(self):
        source = (PACKAGE_DIR / f"{MODULE}.py").read_text()
        for banned in (
            "threshold",
            "weight",
            "probability",
            "score",
            "confidence",
            "fitted",
            "rank",
            "affinity",
            "binding affinity",
        ):
            with self.subTest(term=banned):
                self.assertNotIn(f"{banned} =", source.lower(), f"the module assigns a {banned}")
        numeric = []
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name) and t.id.isupper()]
            if names and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, float):
                    numeric.extend(names)
        self.assertEqual(numeric, [], f"float constants declared: {numeric}")

    def test_the_module_sorts_nothing_it_orders_by(self):
        source = (PACKAGE_DIR / f"{MODULE}.py").read_text()
        # sorted() appears only in refusal messages over set differences, never
        # over slots, candidates or combinations.
        for line in source.splitlines():
            if "sorted(" not in line:
                continue
            with self.subTest(line=line.strip()[:70]):
                self.assertNotIn("candidates", line)
                self.assertNotIn("combinations", line)
                self.assertNotIn("choices", line)


if __name__ == "__main__":
    unittest.main()
