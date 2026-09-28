"""Contract tests for candidate_combinations_table; the layer computes no order of its own.

Two kinds of source are used. The synthetic documents below are hand-written to the source
contracts' shapes and let every refusal path be exercised. The conformance tests additionally
build a REAL cassette_candidate_priority/1 report from the real kernel and assert that the
table's row order equals that report's own array order, so the ordering guarantee is checked
against the producer rather than against a fixture that could drift.

The load-bearing test is PriorityReportUnchanged: the real report's canonical bytes are
pinned to the digest taken before either of these surfaces existed.

Run: PYTHONPATH=src python -m pytest tests/test_candidate_combinations_table.py
"""
import ast
import builtins
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import FrozenInstanceError
import functools
import glob as glob_module
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from structure_audit import candidate_combinations_table as cct
from structure_audit.candidate_combinations_table import (
    COMBINATION_ABSENCE_REASONS, COMBINATION_CARRIED_FIELDS, COMBINATION_NOT_DECLARED,
    EXCLUDED_CARRIED_FIELDS, FORBIDDEN_MINTED_SUBSTRINGS, MANIFEST_NOT_SUPPLIED,
    RANKED_CARRIED_FIELDS, REFUSAL_REASONS, ROW_EXCLUDED, ROW_FIELDS, ROW_RANKED,
    SOURCE_MANIFEST_DOCUMENT_TYPE, SOURCE_PRIORITY_DOCUMENT_TYPE, SOURCE_VOCABULARY_NAMES,
    TABLE_DOCUMENT_TYPE, TABLE_FIELDS, TABLE_KIND, TABLE_NON_CLAIM, WINDOW_FIELDS,
    CandidateCombinationsTable, CandidateCombinationsTableError, build_combinations_table,
    notebook_cell_sources, render_table_lines,
)

ROOT = Path(__file__).resolve().parents[1]
GOTNE_SOURCE = ROOT / "avidity_sim" / "files"
GOTNE_TESTS = ROOT / "avidity_sim" / "tests"

#: Taken from the real kernel before the collection, table and pack surfaces existed.
PRIORITY_REPORT_SHA256 = "9a69e77ae1dc2c4c74d615fd21cdb551f00348001ec099a94201ffdb06603a8e"
PRIORITY_REPORT_BYTES = 3742

NEVER_A_MINTED_FIELD = FORBIDDEN_MINTED_SUBSTRINGS + (
    "threshold", "promote", "demote", "select", "filter", "binding", "affinity", "avidity",
    "residue", "epitope", "occupan", "expression", "plddt", "iptm", "rmsd",
)


def member(candidate_id, tier, coverage="ABSENT"):
    return {"candidate_id": candidate_id, "slot_binding_hash": "h-" + candidate_id,
            "state_result_id": "r-" + candidate_id, "certificate_present": True,
            "geometry_tier": tier, "evidence_coverage": coverage, "evidence": None,
            "tier_basis": []}


def priority_document(groups=None, excluded=None):
    """A synthetic cassette_candidate_priority/1 document, shaped to that contract."""
    t1, t3 = "T1_ENGAGED_SLOTS_FULLY_RESOLVED", "T3_NO_RESOLVED_ENGAGED_SLOT"
    groups = [
        {"rank": 1, "geometry_tier": t1,
         "members": [member("zeta", t1, "CANDIDATE"), member("alpha", t1)]},
        {"rank": 2, "geometry_tier": t3, "members": [member("mid", t3)]},
    ] if groups is None else groups
    excluded = [
        {"candidate_id": "vetoed", "slot_binding_hash": "h-vetoed",
         "ineligibility_reason": "SLOT_VETOED", "state_status": "VALID",
         "state_status_reason": None, "vetoed_slots": ["slot_2"], "refusal_stage": None,
         "refusal_error_class": None, "refusal_detail": None},
        {"candidate_id": "refused", "slot_binding_hash": "h-refused",
         "ineligibility_reason": "DECLARATION_REFUSED", "state_status": None,
         "state_status_reason": None, "vetoed_slots": [], "refusal_stage": "SLOT_BINDING",
         "refusal_error_class": "ValueError", "refusal_detail": "d"},
    ] if excluded is None else excluded
    ranked = [m["candidate_id"] for g in groups for m in g["members"]]
    return {"document_type": SOURCE_PRIORITY_DOCUMENT_TYPE, "non_claim": "source text",
            "candidate_order": ranked + [e["candidate_id"] for e in excluded],
            "groups": groups, "excluded": excluded}


def combination(candidate_id, labels=("A", "B", None)):
    return {"candidate_id": candidate_id,
            "choices": [{"presence": "UNENGAGED" if label is None else "CANDIDATE",
                         "label": label} for label in labels]}


def manifest_document(combinations=None):
    """A synthetic demo_candidate_manifest/1 document, shaped to that contract."""
    return {"document_type": SOURCE_MANIFEST_DOCUMENT_TYPE, "non_claim": "source text",
            "scenario_id": "s1", "primary_context_ref": "c1",
            "order": ["slot_1", "slot_2", "slot_3"], "slots": [],
            "combination_source": "DECLARED_LIST", "max_combinations": 27,
            "candidate_id_prefix": None, "source_annotation": "",
            "combinations": [combination("zeta"), combination("vetoed", ("Z", "Y", "X"))]
            if combinations is None else combinations}


def table(priority=None, *, manifest=None, row_limit=None):
    return build_combinations_table(
        priority_document() if priority is None else priority,
        manifest_document=manifest, row_limit=row_limit)


def source_row_order(document):
    """The source's own order, recomputed from the raw document by this test alone."""
    return ([m["candidate_id"] for g in document["groups"] for m in g["members"]]
            + [e["candidate_id"] for e in document["excluded"]])


def minted_keys(value, *, verbatim=False):
    """Every name this layer mints. Carried subtrees are a boundary, never descended into."""
    names = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if not verbatim:
                names.add(key)
            names |= minted_keys(child, verbatim=verbatim or key in ("carried", "combination"))
    elif isinstance(value, list):
        for child in value:
            names |= minted_keys(child, verbatim=verbatim)
    return names


def refusal(callable_, *args, **kwargs):
    try:
        callable_(*args, **kwargs)
    except CandidateCombinationsTableError as exc:
        return exc
    raise AssertionError("expected a refusal")


# --------------------------------------------------------------------------
# The real report: one probe serves every conformance test
# --------------------------------------------------------------------------
PROBE = r'''
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "tests"))
sys.path.insert(0, sys.argv[2])
# Imported first and deliberately: neither new surface may influence the priority layer.
import structure_audit.candidate_combinations_table  # noqa: F401
import structure_audit.structure_artifact_pack  # noqa: F401
from test_phase2_cassette_candidate_priority import (
    T1_D, T3_D, VETOED_D, UNREACHABLE_D, INFEASIBLE_D, evidence_record, priority_of,
)
report = priority_of(
    [T1_D(), T3_D(), VETOED_D(), UNREACHABLE_D(), INFEASIBLE_D()],
    evidence={"t1": evidence_record()},
)
payload = report.to_json_bytes()
print(json.dumps({"length": len(payload),
                  "sha256": hashlib.sha256(payload).hexdigest(),
                  "document": report.as_dict()}))
'''


@functools.lru_cache(maxsize=None)
def real_report():
    """(length, sha256, document) from the real kernel, or None when it is unavailable.

    The kernel package is not importable at the repository's current layout, so the probe runs
    against a throwaway staging copy outside the repository. Nothing in the repository is
    created, moved or modified.
    """
    if not (GOTNE_SOURCE / "cassette_candidate_priority.py").is_file():
        return None
    if not (GOTNE_TESTS / "test_phase2_cassette_candidate_priority.py").is_file():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "stage"
        (stage / "tests").mkdir(parents=True)
        shutil.copytree(GOTNE_SOURCE, stage / "gotne",
                        ignore=shutil.ignore_patterns("__pycache__", "test_*.py"))
        for source in (*GOTNE_TESTS.glob("test_*.py"), *GOTNE_SOURCE.glob("test_*.py")):
            shutil.copy2(source, stage / "tests" / source.name)
        completed = subprocess.run(
            [sys.executable, "-B", "-c", PROBE, str(stage),
             str(Path(cct.__file__).parents[1])],
            capture_output=True, text=True, timeout=300)
    if completed.returncode != 0:
        raise AssertionError("the priority probe failed:\n" + completed.stderr[-2000:])
    payload = json.loads(completed.stdout)
    return payload["length"], payload["sha256"], payload["document"]


def require_real_report(test):
    result = real_report()
    if result is None:
        test.skipTest("the priority layer or its fixtures are not present in this checkout")
    return result


# --------------------------------------------------------------------------
# Ordering is read, never computed
# --------------------------------------------------------------------------
class OrderingPreserved(unittest.TestCase):
    def test_ranked_rows_follow_the_sources_group_and_member_order(self):
        document = priority_document()
        built = table(document)
        self.assertEqual([row["candidate_id"] for row in built.ranked_rows()],
                         ["zeta", "alpha", "mid"])

    def test_row_order_equals_the_sources_own_order_exactly(self):
        document = priority_document()
        self.assertEqual(table(document).row_order, source_row_order(document))

    def test_rows_are_not_sorted_by_identifier_or_any_carried_value(self):
        order = table().row_order
        self.assertNotEqual(order, sorted(order), "rows are not sorted by candidate_id")
        # zeta precedes alpha because the source listed it first, not because of its id.
        self.assertLess(order.index("zeta"), order.index("alpha"))

    def test_reversing_the_sources_members_reverses_the_rows(self):
        """The only thing that moves a row is the source moving it."""
        document = priority_document()
        forward = table(document).row_order
        document["groups"][0]["members"].reverse()
        self.assertEqual(table(document).row_order[:2], list(reversed(forward[:2])))

    def test_no_carried_value_changes_the_row_order(self):
        """Rewriting every carried value, leaving the arrays alone, moves nothing."""
        document = priority_document()
        before = table(document).row_order
        for group in document["groups"]:
            group["rank"] = 99
            for entry in group["members"]:
                entry["evidence_coverage"] = "REJECTED"
                entry["certificate_present"] = False
        for entry in document["excluded"]:
            entry["ineligibility_reason"] = "LEDGER_ABSENT"
        self.assertEqual(table(document).row_order, before)

    def test_excluded_rows_follow_the_sources_own_excluded_order(self):
        built = table()
        self.assertEqual([row["candidate_id"] for row in built.excluded_rows()],
                         ["vetoed", "refused"])

    def test_every_ranked_row_precedes_every_excluded_row_and_none_is_interleaved(self):
        kinds = [row["row_kind"] for row in table().rows]
        self.assertEqual(kinds, [ROW_RANKED] * 3 + [ROW_EXCLUDED] * 2)

    def test_an_interleaved_document_is_refused_rather_than_reordered(self):
        data = table().to_dict()
        data["rows"] = [data["rows"][0], data["rows"][3], data["rows"][1]]
        data["row_order"] = [row["candidate_id"] for row in data["rows"]]
        self.assertEqual(refusal(CandidateCombinationsTable.from_dict, data).reason,
                         "MALFORMED_DOCUMENT")

    def test_a_supplied_row_order_is_never_trusted(self):
        data = table().to_dict()
        data["row_order"] = sorted(data["row_order"])
        self.assertEqual(refusal(CandidateCombinationsTable.from_dict, data).reason,
                         "ROW_ORDER_NOT_DERIVED")

    def test_no_candidate_is_dropped_merged_or_duplicated(self):
        document = priority_document()
        built = table(document)
        self.assertEqual(sorted(built.row_order), sorted(document["candidate_order"]))
        self.assertEqual(len(set(built.row_order)), len(built.row_order))

    def test_a_source_reporting_one_candidate_twice_is_refused(self):
        document = priority_document()
        document["excluded"].append(deepcopy(document["excluded"][0]))
        document["candidate_order"].append("vetoed")
        exc = refusal(build_combinations_table, document)
        self.assertEqual((exc.reason, exc.candidate_id),
                         ("DUPLICATE_CANDIDATE_ID", "vetoed"))

    def test_the_layer_re_derives_none_of_the_sources_own_invariants(self):
        """A source with non-contiguous ranks and reversed tiers is restated, not corrected.

        Rank contiguity and tier order belong to the priority layer. Re-checking them here
        would be a second implementation of ranking, so a table restates what it is given.
        """
        t1, t3 = "T1_ENGAGED_SLOTS_FULLY_RESOLVED", "T3_NO_RESOLVED_ENGAGED_SLOT"
        odd = priority_document(groups=[
            {"rank": 7, "geometry_tier": t3, "members": [member("first", t3)]},
            {"rank": 3, "geometry_tier": t1, "members": [member("second", t1)]},
        ], excluded=[])
        built = table(odd)
        self.assertEqual(built.row_order, ["first", "second"])
        self.assertEqual([row["carried"]["rank"] for row in built.ranked_rows()], [7, 3])


# --------------------------------------------------------------------------
# Conformance against the real producer
# --------------------------------------------------------------------------
class RealReportConformance(unittest.TestCase):
    def test_the_real_report_shape_is_accepted_unchanged(self):
        _, _, document = require_real_report(self)
        built = table(document)
        self.assertEqual(built.document_type, TABLE_DOCUMENT_TYPE)
        self.assertEqual(sorted(built.row_order), sorted(document["candidate_order"]))

    def test_the_real_reports_own_order_is_preserved_exactly(self):
        _, _, document = require_real_report(self)
        self.assertEqual(table(document).row_order, source_row_order(document))

    def test_every_carried_value_matches_the_real_report_verbatim(self):
        _, _, document = require_real_report(self)
        built = table(document)
        for group in document["groups"]:
            for source in group["members"]:
                row = next(r for r in built.rows
                           if r["candidate_id"] == source["candidate_id"])
                for name in RANKED_CARRIED_FIELDS:
                    with self.subTest(candidate=source["candidate_id"], field=name):
                        expected = group[name] if name == "rank" else source[name]
                        self.assertEqual(row["carried"][name], expected)
        for source in document["excluded"]:
            row = next(r for r in built.rows if r["candidate_id"] == source["candidate_id"])
            for name in EXCLUDED_CARRIED_FIELDS:
                with self.subTest(candidate=source["candidate_id"], field=name):
                    self.assertEqual(row["carried"][name], source[name])

    def test_a_window_over_the_real_report_takes_its_leading_rows(self):
        _, _, document = require_real_report(self)
        full = table(document).ranked_rows()
        for limit in range(len(full) + 1):
            with self.subTest(row_limit=limit):
                windowed = table(document, row_limit=limit).ranked_rows()
                self.assertEqual(windowed, full[:limit])

    def test_building_a_table_does_not_mutate_the_real_report_document(self):
        _, _, document = require_real_report(self)
        before = deepcopy(document)
        table(document, manifest=manifest_document(), row_limit=1)
        self.assertEqual(document, before)


# --------------------------------------------------------------------------
# Display window
# --------------------------------------------------------------------------
class DisplayWindow(unittest.TestCase):
    def test_no_declared_limit_shows_every_ranked_row(self):
        built = table()
        self.assertEqual(built.display_window,
                         {"declared_row_limit": None, "ranked_rows_in_source": 3,
                          "ranked_rows_shown": 3, "truncated": False})

    def test_a_window_takes_the_leading_rows_and_never_reorders(self):
        full = [row["candidate_id"] for row in table().ranked_rows()]
        for limit in range(len(full) + 1):
            with self.subTest(row_limit=limit):
                shown = [row["candidate_id"] for row in table(row_limit=limit).ranked_rows()]
                self.assertEqual(shown, full[:limit])

    def test_a_window_states_its_own_incompleteness(self):
        window = table(row_limit=1).display_window
        self.assertEqual((window["ranked_rows_shown"], window["ranked_rows_in_source"],
                          window["truncated"]), (1, 3, True))

    def test_a_window_never_hides_an_excluded_candidate(self):
        for limit in (0, 1, 2, 3, None):
            with self.subTest(row_limit=limit):
                built = table(row_limit=limit)
                self.assertEqual([row["candidate_id"] for row in built.excluded_rows()],
                                 ["vetoed", "refused"])

    def test_a_limit_past_the_source_reaches_no_further_than_the_source(self):
        window = table(row_limit=99).display_window
        self.assertEqual((window["ranked_rows_shown"], window["truncated"]), (3, False))

    def test_a_limit_that_is_not_a_non_negative_int_is_refused(self):
        for bad in (-1, 1.0, True, "1", [], object()):
            with self.subTest(row_limit=bad):
                self.assertEqual(refusal(build_combinations_table, priority_document(),
                                         row_limit=bad).reason, "INVALID_ROW_LIMIT")

    def test_a_window_that_does_not_re_derive_is_refused(self):
        data = table(row_limit=1).to_dict()
        data["display_window"]["truncated"] = False
        self.assertEqual(refusal(CandidateCombinationsTable.from_dict, data).reason,
                         "WINDOW_NOT_DERIVED")
        data = table().to_dict()
        data["display_window"]["ranked_rows_in_source"] = 99
        self.assertEqual(refusal(CandidateCombinationsTable.from_dict, data).reason,
                         "WINDOW_NOT_DERIVED")

    def test_a_window_is_never_inferred_from_the_source(self):
        self.assertIsNone(table().display_window["declared_row_limit"])


# --------------------------------------------------------------------------
# Combinations
# --------------------------------------------------------------------------
class Combinations(unittest.TestCase):
    def test_a_declared_combination_is_carried_verbatim(self):
        built = table(manifest=manifest_document())
        row = next(r for r in built.rows if r["candidate_id"] == "zeta")
        self.assertEqual(row["combination"], combination("zeta"))
        self.assertIsNone(row["combination_absence"])

    def test_an_undeclared_candidate_carries_a_named_absence_not_a_guess(self):
        built = table(manifest=manifest_document())
        row = next(r for r in built.rows if r["candidate_id"] == "alpha")
        self.assertEqual((row["combination"], row["combination_absence"]),
                         (None, COMBINATION_NOT_DECLARED))

    def test_no_manifest_is_a_distinct_named_absence(self):
        absences = {row["combination_absence"] for row in table().rows}
        self.assertEqual(absences, {MANIFEST_NOT_SUPPLIED})
        self.assertNotEqual(MANIFEST_NOT_SUPPLIED, COMBINATION_NOT_DECLARED)
        for reason in (MANIFEST_NOT_SUPPLIED, COMBINATION_NOT_DECLARED):
            with self.subTest(reason=reason):
                self.assertIn(reason, COMBINATION_ABSENCE_REASONS)

    def test_matching_is_exact_and_never_loose(self):
        for near in ("ZETA", "zeta1", "zet", "zeta.1"):
            with self.subTest(candidate_id=near):
                built = table(manifest=manifest_document([combination(near)]))
                row = next(r for r in built.rows if r["candidate_id"] == "zeta")
                self.assertEqual(row["combination_absence"], COMBINATION_NOT_DECLARED)

    def test_a_combination_carries_exactly_the_fixed_pointer_set(self):
        built = table(manifest=manifest_document())
        row = next(r for r in built.rows if r["candidate_id"] == "zeta")
        self.assertEqual(sorted(row["combination"]), sorted(COMBINATION_CARRIED_FIELDS))

    def test_a_manifest_declaring_one_candidate_twice_is_refused(self):
        exc = refusal(build_combinations_table, priority_document(),
                      manifest_document=manifest_document(
                          [combination("zeta"), combination("zeta", ("C", "D", "E"))]))
        self.assertEqual((exc.reason, exc.candidate_id),
                         ("DUPLICATE_CANDIDATE_ID", "zeta"))

    def test_a_combination_is_carried_for_an_excluded_row_too(self):
        built = table(manifest=manifest_document())
        row = next(r for r in built.excluded_rows() if r["candidate_id"] == "vetoed")
        self.assertEqual(row["combination"], combination("vetoed", ("Z", "Y", "X")))

    def test_an_unnamed_absence_is_refused(self):
        data = table(manifest=manifest_document()).to_dict()
        for row in data["rows"]:
            row["combination"], row["combination_absence"] = None, None
        self.assertEqual(refusal(CandidateCombinationsTable.from_dict, data).reason,
                         "MALFORMED_DOCUMENT")

    def test_an_unknown_absence_token_is_refused(self):
        data = table().to_dict()
        data["rows"][0]["combination_absence"] = "PROBABLY_FINE"
        self.assertEqual(refusal(CandidateCombinationsTable.from_dict, data).reason,
                         "MALFORMED_DOCUMENT")


# --------------------------------------------------------------------------
# No judgement is minted
# --------------------------------------------------------------------------
class NoMintedJudgement(unittest.TestCase):
    def test_no_minted_name_is_a_ranking_scoring_or_eligibility_field(self):
        built = table(manifest=manifest_document(), row_limit=2)
        for name in sorted(minted_keys(built.to_dict())):
            if name in SOURCE_VOCABULARY_NAMES:
                continue
            for forbidden in NEVER_A_MINTED_FIELD:
                with self.subTest(field=name, forbidden=forbidden):
                    self.assertNotIn(forbidden, name.lower())

    def test_the_source_vocabulary_allowlist_is_closed_and_exhaustive(self):
        self.assertEqual(SOURCE_VOCABULARY_NAMES,
                         ("ranked_rows_in_source", "ranked_rows_shown"))
        for name in SOURCE_VOCABULARY_NAMES:
            with self.subTest(name=name):
                self.assertIn(name, WINDOW_FIELDS)

    def test_a_new_judgement_shaped_minted_name_still_fails(self):
        data = table().to_dict()
        for name in ("composite_score", "recommended_rank", "eligibility"):
            with self.subTest(field=name):
                payload = dict(data)
                payload[name] = 1
                self.assertIn(refusal(CandidateCombinationsTable.from_dict, payload).reason,
                              ("UNKNOWN_FIELD", "MINTED_FIELD_FORBIDDEN"))

    def test_the_declared_field_tuples_are_the_whole_minted_surface(self):
        built = table(manifest=manifest_document())
        self.assertEqual(sorted(built.to_dict()), sorted(TABLE_FIELDS))
        self.assertEqual(minted_keys(built.to_dict()),
                         set(TABLE_FIELDS) | set(ROW_FIELDS) | set(WINDOW_FIELDS))

    def test_the_carried_pointer_sets_are_fixed_and_not_caller_chosen(self):
        built = table()
        for row in built.ranked_rows():
            self.assertEqual(sorted(row["carried"]), sorted(RANKED_CARRIED_FIELDS))
        for row in built.excluded_rows():
            self.assertEqual(sorted(row["carried"]), sorted(EXCLUDED_CARRIED_FIELDS))
        data = built.to_dict()
        data["rows"][0]["carried"]["extra"] = 1
        self.assertEqual(refusal(CandidateCombinationsTable.from_dict, data).reason,
                         "MALFORMED_DOCUMENT")

    def test_no_public_object_offers_a_way_to_reach_a_judgement(self):
        exported = set(cct.__all__)
        for verb in ("sort", "filter", "recommend", "admit", "veto", "evaluate", "promote",
                     "shortlist", "score"):
            with self.subTest(verb=verb):
                self.assertEqual([name for name in exported if verb in name.lower()], [])

    def test_table_kind_is_fixed_and_says_restatement(self):
        built = table()
        self.assertEqual((built.table_kind, TABLE_KIND), (TABLE_KIND,
                                                          "DESCRIPTIVE_RESTATEMENT"))
        data = built.to_dict()
        data["table_kind"] = "EVALUATION"
        refusal(CandidateCombinationsTable.from_dict, data)

    def test_the_non_claim_is_emitted_verbatim_and_an_alteration_is_refused(self):
        self.assertEqual(table().non_claim, TABLE_NON_CLAIM)
        data = table().to_dict()
        data["non_claim"] = TABLE_NON_CLAIM.replace("computes no order", "computes an order")
        self.assertEqual(refusal(CandidateCombinationsTable.from_dict, data).reason,
                         "NON_CLAIM_ALTERED")

    def test_the_non_claim_names_the_boundaries_it_has_to_name(self):
        for phrase in ("computes no order", "mints no value", "or recommends",
                       "not a selection, a shortlist or a recommendation",
                       "Equal rank means equal tier", "display cut", "carried unchanged"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, TABLE_NON_CLAIM)


# --------------------------------------------------------------------------
# Determinism and immutability
# --------------------------------------------------------------------------
class Determinism(unittest.TestCase):
    def test_identical_sources_give_identical_bytes(self):
        self.assertEqual(table(manifest=manifest_document()).to_json_bytes(),
                         table(manifest=manifest_document()).to_json_bytes())

    def test_a_mapping_and_its_bytes_give_identical_tables(self):
        document = priority_document()
        raw = json.dumps(document).encode("utf-8")
        self.assertEqual(build_combinations_table(raw).to_json_bytes(),
                         table(document).to_json_bytes())

    def test_source_key_insertion_order_never_changes_the_output(self):
        document = priority_document()
        reordered = {key: document[key] for key in reversed(list(document))}
        self.assertEqual(table(reordered).to_json_bytes(), table(document).to_json_bytes())

    def test_a_table_reloads_from_its_own_bytes(self):
        built = table(manifest=manifest_document(), row_limit=2)
        self.assertEqual(CandidateCombinationsTable(built.to_json_bytes()).to_json_bytes(),
                         built.to_json_bytes())

    def test_non_canonical_bytes_are_refused_rather_than_recanonicalized(self):
        loose = json.dumps(table().to_dict(), indent=2).encode("utf-8")
        self.assertEqual(refusal(CandidateCombinationsTable, loose).reason,
                         "NOT_CANONICAL_BYTES")

    def test_a_duplicate_json_key_is_not_a_document(self):
        raw = table().to_json_bytes().replace(b'"rows":', b'"rows":[],"rows":', 1)
        self.assertEqual(refusal(CandidateCombinationsTable, raw).reason,
                         "DUPLICATE_JSON_KEY")

    def test_building_does_not_mutate_the_source_documents(self):
        priority, manifest = priority_document(), manifest_document()
        before = (deepcopy(priority), deepcopy(manifest))
        build_combinations_table(priority, manifest_document=manifest, row_limit=1)
        self.assertEqual((priority, manifest), before)

    def test_mutating_the_sources_afterwards_never_changes_the_table(self):
        priority = priority_document()
        built = table(priority)
        pinned = built.to_json_bytes()
        priority["groups"][0]["members"][0]["candidate_id"] = "rewritten"
        priority["excluded"].clear()
        self.assertEqual(built.to_json_bytes(), pinned)

    def test_mutating_a_returned_view_never_reaches_the_document(self):
        built = table()
        pinned = built.to_json_bytes()
        built.rows.clear()
        built.row_order.append("late")
        built.display_window["truncated"] = True
        self.assertEqual(built.to_json_bytes(), pinned)

    def test_the_document_is_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            table().json_bytes = b"{}"

    def test_rendering_returns_fresh_lines(self):
        built = table()
        pinned = render_table_lines(built)
        render_table_lines(built).clear()
        self.assertEqual(render_table_lines(built), pinned)

    def test_every_declared_refusal_reason_is_a_member(self):
        for reason in ("SOURCE_DOCUMENT_TYPE_UNEXPECTED", "SOURCE_FIELD_ABSENT",
                       "INVALID_ROW_LIMIT", "ROW_ORDER_NOT_DERIVED", "WINDOW_NOT_DERIVED",
                       "DUPLICATE_CANDIDATE_ID", "NON_CLAIM_ALTERED"):
            with self.subTest(reason=reason):
                self.assertIn(reason, REFUSAL_REASONS)


# --------------------------------------------------------------------------
# Source refusals
# --------------------------------------------------------------------------
class SourceRefusals(unittest.TestCase):
    def test_a_document_of_another_contract_is_refused_never_adapted(self):
        for document in ({"document_type": "candidate_combinations_table/1"},
                         {"document_type": SOURCE_MANIFEST_DOCUMENT_TYPE}, {}):
            with self.subTest(document_type=document.get("document_type")):
                self.assertEqual(refusal(build_combinations_table, document).reason,
                                 "SOURCE_DOCUMENT_TYPE_UNEXPECTED")

    def test_a_manifest_in_the_priority_position_is_refused(self):
        self.assertEqual(
            refusal(build_combinations_table, priority_document(),
                    manifest_document=priority_document()).reason,
            "SOURCE_DOCUMENT_TYPE_UNEXPECTED")

    def test_an_absent_source_array_is_refused_never_treated_as_empty(self):
        for name in ("groups", "excluded"):
            with self.subTest(field=name):
                document = priority_document()
                del document[name]
                exc = refusal(build_combinations_table, document)
                self.assertEqual((exc.reason, exc.field), ("SOURCE_FIELD_ABSENT", name))

    def test_an_absent_carried_field_is_refused_never_defaulted(self):
        for name in RANKED_CARRIED_FIELDS:
            with self.subTest(field=name):
                document = priority_document()
                container = (document["groups"][0] if name == "rank"
                             else document["groups"][0]["members"][0])
                del container[name]
                exc = refusal(build_combinations_table, document)
                self.assertEqual((exc.reason, exc.field), ("SOURCE_FIELD_ABSENT", name))

    def test_a_malformed_source_shape_is_refused(self):
        document = priority_document()
        document["groups"] = {"rank": 1}
        self.assertEqual(refusal(build_combinations_table, document).reason,
                         "SOURCE_SHAPE_UNEXPECTED")
        self.assertEqual(refusal(build_combinations_table, b"not json").reason,
                         "SOURCE_SHAPE_UNEXPECTED")


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------
class Isolation(unittest.TestCase):
    def test_building_and_rendering_open_no_file(self):
        opened, real = [], builtins.open

        def record(target, *args, **kwargs):
            if not isinstance(target, int):
                opened.append(os.fspath(target))
            return real(target, *args, **kwargs)

        with patch.object(builtins, "open", record), patch.object(io, "open", record):
            built = table(manifest=manifest_document(), row_limit=1)
            render_table_lines(built)
            notebook_cell_sources()
        self.assertEqual(opened, [])

    def test_no_entry_point_writes_scans_or_starts_a_subprocess(self):
        with ExitStack() as stack:
            for owner, names in ((subprocess, ("Popen", "run", "check_output")),
                                 (os, ("listdir", "scandir", "walk", "remove", "mkdir")),
                                 (glob_module, ("glob", "iglob")),
                                 (Path, ("write_bytes", "write_text", "mkdir", "unlink",
                                         "glob", "rglob", "iterdir", "read_bytes",
                                         "read_text", "exists", "resolve", "stat"))):
                for name in names:
                    stack.enter_context(patch.object(
                        owner, name, side_effect=AssertionError("forbidden IO: " + name)))
            built = table(manifest=manifest_document())
            render_table_lines(built)
            cells = notebook_cell_sources()
        self.assertEqual(built.table_kind, TABLE_KIND)
        self.assertEqual(len(cells), 2)

    def test_the_module_imports_only_the_standard_library_and_its_own_package(self):
        imported = set()
        for node in ast.walk(ast.parse(Path(cct.__file__).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add("." * (node.level or 0) + (node.module or ""))
        self.assertEqual(imported, {"dataclasses", "hashlib", "json", ".provenance"})

    def test_the_module_names_no_producer_entry_point(self):
        tree = ast.parse(Path(cct.__file__).read_text(encoding="utf-8"))
        called = {node.func.id for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        for entry_point in ("evaluate_candidate_priority", "evaluate_candidate_batch",
                            "evaluate_state", "evaluate_node", "geometry_tier",
                            "classify_evidence", "declare_candidate_manifest",
                            "build_slot_ledger", "issue_state_certificate"):
            with self.subTest(entry_point=entry_point):
                self.assertNotIn(entry_point, called)

    def test_the_layer_is_reachable_by_submodule_only(self):
        import structure_audit

        self.assertNotIn("candidate_combinations_table", structure_audit.__all__)
        for name in ("build_combinations_table", "CandidateCombinationsTable"):
            with self.subTest(name=name):
                self.assertNotIn(name, structure_audit.__all__)

    def test_no_kernel_module_references_this_layer(self):
        if not GOTNE_SOURCE.is_dir():
            self.skipTest("the kernel package directory is not present in this checkout")
        for path in sorted(GOTNE_SOURCE.glob("*.py")):
            with self.subTest(module=path.stem):
                self.assertNotIn("candidate_combinations_table",
                                 path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Notebook surface
# --------------------------------------------------------------------------
class NotebookSurface(unittest.TestCase):
    def test_the_cells_are_returned_fresh_and_identically_on_every_call(self):
        self.assertEqual(notebook_cell_sources(), notebook_cell_sources())
        self.assertEqual([(cid, kind) for cid, kind, _ in notebook_cell_sources()],
                         [("combinations-table-00-section", "markdown"),
                          ("combinations-table-01-render", "code")])

    def test_returning_the_cells_opens_and_writes_no_notebook(self):
        notebook = ROOT / "diffusion_fixed.ipynb"
        before = notebook.stat().st_mtime_ns if notebook.is_file() else None
        notebook_cell_sources()
        self.assertEqual(notebook.stat().st_mtime_ns if notebook.is_file() else None, before)

    def test_every_code_cell_parses_and_imports_only_this_layer(self):
        for cell_id, kind, source in notebook_cell_sources():
            if kind != "code":
                continue
            modules = set()
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Import):
                    modules |= {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    modules.add(node.module)
            with self.subTest(cell=cell_id):
                self.assertEqual(modules,
                                 {"structure_audit.candidate_combinations_table"})

    def test_no_code_cell_reaches_a_producer_a_reader_or_the_disk(self):
        forbidden = {"open", "eval", "exec", "compile", "__import__", "Path", "read_text",
                     "read_bytes", "glob", "listdir", "walk", "urlopen", "Popen", "run",
                     "evaluate_candidate_priority", "evaluate_candidate_batch",
                     "evaluate_state", "evaluate_node", "declare_candidate_manifest",
                     "import_notebook_outputs", "sorted", "sort"}
        for cell_id, kind, source in notebook_cell_sources():
            if kind != "code":
                continue
            used = set()
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Name):
                    used.add(node.id)
                elif isinstance(node, ast.Attribute):
                    used.add(node.attr)
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    used |= {alias.asname or alias.name for alias in node.names}
            with self.subTest(cell=cell_id):
                self.assertEqual(used & forbidden, set())

    def test_the_code_cell_runs_against_supplied_documents_without_touching_the_disk(self):
        namespace = {"__name__": "__main__", "PRIORITY_DOCUMENT": priority_document(),
                     "MANIFEST_DOCUMENT": manifest_document()}
        printed = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(
                builtins, "print", lambda *a, **k: printed.append(" ".join(map(str, a)))))
            for owner, names in ((subprocess, ("Popen", "run")),
                                 (os, ("listdir", "scandir", "walk")),
                                 (Path, ("write_text", "write_bytes", "glob", "rglob",
                                         "read_text", "read_bytes"))):
                for name in names:
                    stack.enter_context(patch.object(
                        owner, name, side_effect=AssertionError("forbidden IO: " + name)))
            for cell_id, kind, source in notebook_cell_sources():
                if kind == "code":
                    exec(compile(source, cell_id, "exec"), namespace)
        self.assertIsInstance(namespace["table"], CandidateCombinationsTable)
        self.assertEqual(namespace["table"].row_order,
                         source_row_order(namespace["PRIORITY_DOCUMENT"]))
        self.assertTrue(any("Ranked rows" in line for line in printed))

    def test_the_markdown_cell_carries_the_no_claim_boundary(self):
        text = next(source for _, kind, source in notebook_cell_sources()
                    if kind == "markdown")
        for phrase in ("computes no order", "carried from the source", "never a selection",
                       "Equal rank means equal tier"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


# --------------------------------------------------------------------------
# The existing priority report is untouched
# --------------------------------------------------------------------------
class PriorityReportUnchanged(unittest.TestCase):
    """The load-bearing test: the real priority report's bytes are pinned.

    It fails loudly if either new surface is ever wired into the priority layer, or if the
    priority layer's serialization changes.
    """

    def test_the_real_priority_report_serialization_is_byte_identical(self):
        length, digest, _ = require_real_report(self)
        self.assertEqual((length, digest), (PRIORITY_REPORT_BYTES, PRIORITY_REPORT_SHA256))

    def test_restating_the_report_leaves_its_bytes_byte_identical(self):
        """Building a table from the report cannot change the report."""
        length, digest, document = require_real_report(self)
        table(document, manifest=manifest_document(), row_limit=1)
        again = json.dumps(document, sort_keys=True, separators=(",", ":"),
                           allow_nan=False).encode("utf-8")
        self.assertEqual((len(again), hashlib.sha256(again).hexdigest()),
                         (length, digest))

    def test_the_existing_candidate_seams_are_not_edited_by_this_change(self):
        if not (GOTNE_SOURCE / "cassette_candidate_priority.py").is_file():
            self.skipTest("the priority layer is not present in this checkout")
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain", "--",
             "avidity_sim/files/cassette_candidate_priority.py",
             "avidity_sim/files/cassette_candidate_batch.py",
             "avidity_sim/files/cassette_scenario_comparison.py",
             "avidity_sim/files/demo_candidate_manifest.py",
             "diffusion_fixed.ipynb"],
            capture_output=True, text=True)
        if completed.returncode != 0:
            self.skipTest("git is not available for this checkout")
        self.assertEqual(completed.stdout.strip(), "",
                         "this change must not touch the existing seams or the notebook")


if __name__ == "__main__":
    unittest.main()
