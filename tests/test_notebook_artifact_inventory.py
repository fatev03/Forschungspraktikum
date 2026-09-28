"""Contract tests for notebook_artifact_inventory; the layer itself reads and writes nothing.

Every item, reference and metadata value here is synthetic text. No real artifact, notebook
or committed fixture is opened, and the layer is never given a path to resolve.

The load-bearing test is PriorityReportUnchanged: the real CandidatePriorityReport's
canonical bytes are pinned to a digest taken before this module existed. It exists to fail
loudly if this collection surface is ever wired into the priority layer.

Run: PYTHONPATH=src python -m pytest tests/test_notebook_artifact_inventory.py
"""
import ast
import builtins
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import FrozenInstanceError
import glob as glob_module
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from structure_audit import notebook_artifact_inventory as nai
from structure_audit.notebook_artifact_inventory import (
    COLLECTION_STATUS, FORBIDDEN_FIELD_SUBSTRINGS, HANDOFF_DOCUMENT_TYPE, HANDOFF_FIELDS,
    HANDOFF_KIND, HANDOFF_TARGET_SEAM, INVENTORY_DOCUMENT_TYPE, INVENTORY_FIELDS,
    INVENTORY_NON_CLAIM, ITEM_FIELDS, MAX_REFERENCE_LENGTH, REFUSAL_REASONS,
    SELECTION_DOCUMENT_TYPE, SELECTION_FIELDS, ArtifactHandoff, ArtifactInventory,
    ArtifactSelection, NotebookArtifactInventoryError, build_handoff_manifest,
    collect_artifact_inventory, notebook_cell_sources, render_inventory_lines,
    render_selection_lines, select_inventory_items,
)

ROOT = Path(__file__).resolve().parents[1]
GOTNE_SOURCE = ROOT / "avidity_sim" / "files"
GOTNE_TESTS = ROOT / "avidity_sim" / "tests"

#: Taken from the real kernel before this module existed. Any change to the priority
#: layer's serialization, or any interference from this layer, changes it.
PRIORITY_REPORT_SHA256 = "9a69e77ae1dc2c4c74d615fd21cdb551f00348001ec099a94201ffdb06603a8e"
PRIORITY_REPORT_BYTES = 3742

#: Broader than the module's runtime guard: it also names domain terms, so a later edit
#: cannot introduce a domain-shaped field name either.
NEVER_A_MINTED_FIELD = FORBIDDEN_FIELD_SUBSTRINGS + (
    "auto", "best", "top", "prefer", "favor", "threshold", "pass_fail", "verdict",
    "binding", "affinity", "avidity", "residue", "epitope", "conform", "access",
    "expression", "plddt", "iptm", "ipae", "rmsd", "occupan", "abundance",
)

ITEMS = [
    {"item_id": "run-b", "reference": "external_artifacts/run-b/output",
     "declared_metadata": {"declared_by": "producer-x", "nested": {"k": [1, 2, None]}}},
    {"item_id": "run-a", "reference": " run-a  with spaces / and ünïcode ",
     "declared_metadata": {}},
    {"item_id": "run.c-1", "reference": "run-c", "declared_metadata": {"n": 0, "f": 1.5}},
]


def inventory(items=None):
    return collect_artifact_inventory(deepcopy(ITEMS if items is None else items))


def selection(ids=("run-a", "run-b"), inv=None):
    inv = inventory() if inv is None else inv
    return select_inventory_items(inv, list(ids))


def minted_keys(value, *, inside_metadata=False):
    """Every key this layer mints. declared_metadata values are the caller's verbatim
    text, so they are collected as a boundary and never descended into."""
    names = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if not inside_metadata:
                names.add(key)
            names |= minted_keys(child, inside_metadata=inside_metadata or key == "declared_metadata")
    elif isinstance(value, list):
        for child in value:
            names |= minted_keys(child, inside_metadata=inside_metadata)
    return names


def refusal(callable_, *args):
    try:
        callable_(*args)
    except NotebookArtifactInventoryError as exc:
        return exc
    raise AssertionError("expected a refusal")


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------
class Determinism(unittest.TestCase):
    def test_identical_declared_inputs_give_identical_inventory_bytes(self):
        self.assertEqual(inventory().to_json_bytes(), inventory().to_json_bytes())

    def test_identical_declared_inputs_give_identical_selection_and_handoff_bytes(self):
        first, second = inventory(), inventory()
        self.assertEqual(selection(inv=first).to_json_bytes(),
                         selection(inv=second).to_json_bytes())
        self.assertEqual(build_handoff_manifest(first, selection(inv=first)).to_json_bytes(),
                         build_handoff_manifest(second, selection(inv=second)).to_json_bytes())

    def test_repeated_serialization_of_one_document_is_stable(self):
        built = inventory()
        self.assertEqual(built.to_json_bytes(), built.to_json_bytes())
        self.assertEqual(built.digest, hashlib.sha256(built.to_json_bytes()).hexdigest())

    def test_item_key_insertion_order_never_changes_the_output(self):
        reordered = [{name: item[name] for name in reversed(ITEM_FIELDS)} for item in ITEMS]
        self.assertEqual(inventory(reordered).to_json_bytes(), inventory().to_json_bytes())

    def test_a_document_reloads_from_its_own_bytes(self):
        for built, cls in ((inventory(), ArtifactInventory), (selection(), ArtifactSelection)):
            with self.subTest(document=built.document_type):
                self.assertEqual(cls(built.to_json_bytes()).to_json_bytes(),
                                 built.to_json_bytes())
        inv = inventory()
        handoff = build_handoff_manifest(inv, selection(inv=inv))
        self.assertEqual(ArtifactHandoff(handoff.to_json_bytes()).to_json_bytes(),
                         handoff.to_json_bytes())

    def test_non_canonical_bytes_are_refused_rather_than_recanonicalized(self):
        data = inventory().to_dict()
        loose = json.dumps(data, indent=2).encode("utf-8")
        self.assertEqual(refusal(ArtifactInventory, loose).reason, "NOT_CANONICAL_BYTES")

    def test_a_duplicate_json_key_is_not_a_document(self):
        raw = inventory().to_json_bytes().replace(b'"order":', b'"order":[],"order":', 1)
        self.assertEqual(refusal(ArtifactInventory, raw).reason, "DUPLICATE_JSON_KEY")


# --------------------------------------------------------------------------
# Order and enumeration
# --------------------------------------------------------------------------
class Order(unittest.TestCase):
    def test_inventory_keeps_the_supplied_order_exactly(self):
        self.assertEqual(inventory().order, ["run-b", "run-a", "run.c-1"])

    def test_inventory_order_is_not_sorted_by_identifier_reference_or_metadata(self):
        built = inventory()
        self.assertNotEqual(built.order, sorted(built.order))
        self.assertEqual(built.order, [item["item_id"] for item in ITEMS])

    def test_selection_preserves_the_user_supplied_order_exactly(self):
        for order in (["run-a", "run-b"], ["run-b", "run-a"], ["run.c-1", "run-a", "run-b"]):
            with self.subTest(order=order):
                self.assertEqual(select_inventory_items(inventory(), order).selected_order,
                                 order)

    def test_selection_order_is_not_re_projected_onto_inventory_order(self):
        # Inventory order is run-b, run-a; the caller asked for the reverse and keeps it.
        self.assertEqual(selection(["run-a", "run-b"]).selected_order, ["run-a", "run-b"])

    def test_selected_items_follow_the_selected_order(self):
        built = selection(["run.c-1", "run-b"])
        self.assertEqual([item["item_id"] for item in built.items], ["run.c-1", "run-b"])

    def test_the_order_array_is_re_derived_and_a_supplied_order_is_never_trusted(self):
        data = inventory().to_dict()
        data["order"] = sorted(data["order"])
        self.assertEqual(refusal(ArtifactInventory.from_dict, data).reason, "ORDER_NOT_DERIVED")

    def test_an_empty_inventory_is_valid_and_names_its_own_emptiness(self):
        built = collect_artifact_inventory([])
        self.assertEqual((built.order, built.items), ([], []))
        self.assertIn("No artifact reference supplied.", render_inventory_lines(built))


# --------------------------------------------------------------------------
# Manual selection
# --------------------------------------------------------------------------
class ManualSelection(unittest.TestCase):
    def test_an_empty_selection_is_valid(self):
        built = select_inventory_items(inventory(), [])
        self.assertIsInstance(built, ArtifactSelection)
        self.assertEqual((built.selected_order, built.items), ([], []))

    def test_an_empty_selection_is_not_read_as_every_item(self):
        built = select_inventory_items(inventory(), [])
        self.assertEqual(built.items, [])
        self.assertTrue(any("does not mean every item" in line
                            for line in render_selection_lines(built)))

    def test_an_empty_selection_hands_off_as_an_explicitly_empty_handoff(self):
        inv = inventory()
        handoff = build_handoff_manifest(inv, select_inventory_items(inv, []))
        self.assertEqual((handoff.selected_order, handoff.items), ([], []))
        self.assertEqual(handoff.target_seam, HANDOFF_TARGET_SEAM)

    def test_a_duplicate_selected_identifier_is_refused_never_deduplicated(self):
        exc = refusal(select_inventory_items, inventory(), ["run-a", "run-a"])
        self.assertEqual((exc.code, exc.reason, exc.item_id),
                         ("CONTRACT_INVALID", "DUPLICATE_SELECTED_ID", "run-a"))

    def test_an_unknown_selected_identifier_is_refused_never_dropped(self):
        exc = refusal(select_inventory_items, inventory(), ["run-a", "run-zzz"])
        self.assertEqual((exc.code, exc.reason, exc.item_id),
                         ("CONTRACT_INVALID", "UNKNOWN_ITEM_ID", "run-zzz"))

    def test_an_unknown_identifier_is_never_matched_loosely_to_a_near_neighbour(self):
        for near in ("RUN-A", "run-a1", "run_a", "run.a"):
            with self.subTest(identifier=near):
                self.assertEqual(
                    refusal(select_inventory_items, inventory(), [near]).reason,
                    "UNKNOWN_ITEM_ID")

    def test_one_bad_identifier_refuses_the_whole_selection(self):
        refusal(select_inventory_items, inventory(), ["run-a", "run-b", "missing"])
        # Nothing partial survives: a fresh valid call is unaffected by the refused one.
        self.assertEqual(selection(["run-a", "run-b"]).selected_order, ["run-a", "run-b"])

    def test_a_duplicate_declared_item_is_refused_never_deduplicated(self):
        exc = refusal(collect_artifact_inventory, [ITEMS[0], deepcopy(ITEMS[0])])
        self.assertEqual((exc.code, exc.reason, exc.item_id),
                         ("CONTRACT_INVALID", "DUPLICATE_ITEM_ID", "run-b"))

    def test_nothing_is_selected_without_an_explicit_identifier(self):
        self.assertEqual(select_inventory_items(inventory(), ()).selected_order, [])
        for bad in (None, "run-a", {"run-a": True}, 0):
            with self.subTest(item_ids=bad):
                refusal(select_inventory_items, inventory(), bad)

    def test_a_selection_from_another_inventory_is_refused_rather_than_trusted(self):
        other = inventory([ITEMS[0]])
        exc = refusal(build_handoff_manifest, other, selection())
        self.assertEqual((exc.code, exc.reason), ("CONTRACT_INVALID",
                                                 "SELECTION_INVENTORY_MISMATCH"))

    def test_every_refusal_reason_is_a_declared_member(self):
        for reason in ("DUPLICATE_SELECTED_ID", "UNKNOWN_ITEM_ID", "DUPLICATE_ITEM_ID",
                       "SELECTION_INVENTORY_MISMATCH", "ORDER_NOT_DERIVED",
                       "NOT_CANONICAL_BYTES", "DUPLICATE_JSON_KEY", "NON_CLAIM_ALTERED"):
            with self.subTest(reason=reason):
                self.assertIn(reason, REFUSAL_REASONS)


# --------------------------------------------------------------------------
# Verbatim carriage
# --------------------------------------------------------------------------
class Verbatim(unittest.TestCase):
    def test_references_are_carried_character_for_character(self):
        built = inventory()
        self.assertEqual([item["reference"] for item in built.items],
                         [item["reference"] for item in ITEMS])

    def test_declared_metadata_is_carried_verbatim_through_every_document(self):
        inv = inventory()
        sel = select_inventory_items(inv, ["run-b"])
        handoff = build_handoff_manifest(inv, sel)
        for document in (inv, sel, handoff):
            with self.subTest(document=document.document_type):
                carried = next(item for item in document.items if item["item_id"] == "run-b")
                self.assertEqual(carried["declared_metadata"], ITEMS[0]["declared_metadata"])

    def test_a_judgement_shaped_metadata_key_is_carried_and_never_acted_on(self):
        declared = {"score": 0.99, "rank": 1, "recommendation": "use", "eligible": True}
        supplied = [{"item_id": "x", "reference": "r-x", "declared_metadata": declared},
                    {"item_id": "y", "reference": "r-y", "declared_metadata": {}}]
        built = collect_artifact_inventory(deepcopy(supplied))
        self.assertEqual(built.order, ["x", "y"], "metadata never reorders an inventory")
        self.assertEqual(built.items[0]["declared_metadata"], declared)
        self.assertEqual(minted_keys(built.to_dict()) & set(declared), set(),
                         "caller metadata keys are never promoted to minted fields")

    def test_an_empty_declared_metadata_object_is_never_filled_in(self):
        self.assertEqual(inventory().items[1]["declared_metadata"], {})

    def test_the_non_claim_is_emitted_verbatim_in_every_document(self):
        inv = inventory()
        sel = selection(inv=inv)
        for document in (inv, sel, build_handoff_manifest(inv, sel)):
            with self.subTest(document=document.document_type):
                self.assertEqual(document.non_claim, INVENTORY_NON_CLAIM)

    def test_an_altered_non_claim_is_refused(self):
        data = inventory().to_dict()
        data["non_claim"] = INVENTORY_NON_CLAIM.replace("not evaluation", "evaluation")
        self.assertEqual(refusal(ArtifactInventory.from_dict, data).reason, "NON_CLAIM_ALTERED")

    def test_a_reference_is_never_rewritten_to_make_it_acceptable(self):
        exc = refusal(collect_artifact_inventory,
                      [{"item_id": "x", "reference": "bad\nref", "declared_metadata": {}}])
        self.assertEqual((exc.reason, exc.field), ("INVALID_REFERENCE", "reference"))
        self.assertEqual(
            refusal(collect_artifact_inventory,
                    [{"item_id": "x", "reference": "r" * (MAX_REFERENCE_LENGTH + 1),
                      "declared_metadata": {}}]).reason,
            "INVALID_REFERENCE")

    def test_an_item_declares_exactly_the_three_fields(self):
        base = {"item_id": "x", "reference": "r", "declared_metadata": {}}
        self.assertEqual(refusal(collect_artifact_inventory, [{**base, "extra": 1}]).reason,
                         "UNKNOWN_FIELD")
        for name in ITEM_FIELDS:
            with self.subTest(field=name):
                partial = {k: v for k, v in base.items() if k != name}
                self.assertEqual(
                    refusal(collect_artifact_inventory, [partial]).reason, "MISSING_FIELD")


# --------------------------------------------------------------------------
# No judgement is minted
# --------------------------------------------------------------------------
class NoMintedJudgement(unittest.TestCase):
    def test_no_document_mints_a_score_rank_or_eligibility_field(self):
        inv = inventory()
        sel = selection(inv=inv)
        for document in (inv, sel, build_handoff_manifest(inv, sel)):
            names = minted_keys(document.to_dict())
            for name in sorted(names):
                for forbidden in NEVER_A_MINTED_FIELD:
                    with self.subTest(document=document.document_type, field=name):
                        self.assertNotIn(forbidden, name.lower())

    def test_the_declared_field_tuples_are_the_whole_minted_surface(self):
        inv = inventory()
        sel = selection(inv=inv)
        handoff = build_handoff_manifest(inv, sel)
        for document, fields in ((inv, INVENTORY_FIELDS), (sel, SELECTION_FIELDS),
                                 (handoff, HANDOFF_FIELDS)):
            with self.subTest(document=document.document_type):
                self.assertEqual(sorted(document.to_dict()), sorted(fields))
                self.assertEqual(minted_keys(document.to_dict()),
                                 set(fields) | set(ITEM_FIELDS))

    def test_collection_status_is_the_only_status_and_is_fixed_and_non_evaluative(self):
        inv = inventory()
        self.assertEqual(inv.collection_status, COLLECTION_STATUS)
        self.assertEqual(COLLECTION_STATUS, "COLLECTED_NOT_EVALUATED")
        self.assertEqual([name for name in minted_keys(inv.to_dict()) if "status" in name],
                         ["collection_status"])

    def test_no_argument_can_change_a_fixed_field(self):
        inv = inventory()
        handoff = build_handoff_manifest(inv, selection(inv=inv))
        for field, expected in (("collection_status", COLLECTION_STATUS),
                                ("handoff_kind", HANDOFF_KIND),
                                ("target_seam", HANDOFF_TARGET_SEAM)):
            with self.subTest(field=field):
                data = handoff.to_dict()
                data[field] = "SOMETHING_ELSE"
                refusal(ArtifactHandoff.from_dict, data)
                self.assertEqual(handoff.to_dict()[field], expected)

    def test_the_minted_field_guard_fires_on_a_judgement_shaped_field_name(self):
        data = inventory().to_dict()
        data["ranking"] = []
        exc = refusal(ArtifactInventory.from_dict, data)
        self.assertIn(exc.reason, ("UNKNOWN_FIELD", "MINTED_FIELD_FORBIDDEN"))
        item = dict(inventory().items[0])
        item["quality_score"] = 1
        self.assertEqual(refusal(collect_artifact_inventory, [item]).reason, "UNKNOWN_FIELD")

    def test_no_public_object_offers_a_way_to_reach_a_judgement(self):
        exported = set(nai.__all__)
        for verb in ("rank", "score", "sort", "filter", "recommend", "admit", "veto",
                     "prioriti", "evaluate", "top", "best", "auto"):
            with self.subTest(verb=verb):
                self.assertEqual([name for name in exported if verb in name.lower()], [])

    def test_the_document_types_name_collection_not_evaluation(self):
        self.assertEqual(
            (INVENTORY_DOCUMENT_TYPE, SELECTION_DOCUMENT_TYPE, HANDOFF_DOCUMENT_TYPE),
            ("notebook_artifact_inventory/1", "notebook_artifact_selection/1",
             "notebook_artifact_handoff/1"))


# --------------------------------------------------------------------------
# Nothing upstream is mutated
# --------------------------------------------------------------------------
class NoUpstreamMutation(unittest.TestCase):
    def test_collecting_does_not_mutate_the_supplied_items(self):
        supplied = deepcopy(ITEMS)
        before = deepcopy(supplied)
        collect_artifact_inventory(supplied)
        self.assertEqual(supplied, before)

    def test_mutating_the_supplied_items_afterwards_never_changes_the_document(self):
        supplied = deepcopy(ITEMS)
        built = collect_artifact_inventory(supplied)
        pinned = built.to_json_bytes()
        supplied[0]["reference"] = "rewritten"
        supplied[0]["declared_metadata"]["nested"]["k"].append("added")
        supplied.append({"item_id": "late", "reference": "r", "declared_metadata": {}})
        self.assertEqual(built.to_json_bytes(), pinned)
        self.assertEqual(built.items[0]["reference"], ITEMS[0]["reference"])

    def test_selecting_does_not_mutate_the_inventory_or_the_identifier_list(self):
        inv = inventory()
        pinned = inv.to_json_bytes()
        ids = ["run-a", "run-b"]
        before = list(ids)
        select_inventory_items(inv, ids)
        self.assertEqual((inv.to_json_bytes(), ids), (pinned, before))

    def test_handing_off_does_not_mutate_the_inventory_or_the_selection(self):
        inv = inventory()
        sel = selection(inv=inv)
        pinned = (inv.to_json_bytes(), sel.to_json_bytes())
        build_handoff_manifest(inv, sel)
        self.assertEqual((inv.to_json_bytes(), sel.to_json_bytes()), pinned)

    def test_mutating_a_returned_view_never_reaches_the_document(self):
        built = inventory()
        pinned = built.to_json_bytes()
        view = built.items
        view[0]["reference"] = "rewritten"
        view.clear()
        built.to_dict()["order"].clear()
        built.order.append("late")
        self.assertEqual(built.to_json_bytes(), pinned)
        self.assertEqual(built.items[0]["reference"], ITEMS[0]["reference"])

    def test_mutating_rendered_lines_never_reaches_the_document(self):
        built = inventory()
        pinned = render_inventory_lines(built)
        render_inventory_lines(built).clear()
        self.assertEqual(render_inventory_lines(built), pinned)

    def test_the_documents_are_immutable(self):
        for document in (inventory(), selection()):
            with self.subTest(document=document.document_type):
                with self.assertRaises(FrozenInstanceError):
                    document.json_bytes = b"{}"


# --------------------------------------------------------------------------
# Isolation
# --------------------------------------------------------------------------
class Isolation(unittest.TestCase):
    def test_collecting_selecting_and_handing_off_open_no_file(self):
        opened, real = [], builtins.open

        def record(target, *args, **kwargs):
            if not isinstance(target, int):
                opened.append(os.fspath(target))
            return real(target, *args, **kwargs)

        with patch.object(builtins, "open", record), patch.object(io, "open", record):
            inv = inventory()
            sel = selection(inv=inv)
            build_handoff_manifest(inv, sel)
            render_inventory_lines(inv)
            render_selection_lines(sel)
            notebook_cell_sources()
        self.assertEqual(opened, [])

    def test_no_entry_point_writes_scans_or_starts_a_subprocess(self):
        with ExitStack() as stack:
            for owner, names in ((subprocess, ("Popen", "run", "check_output")),
                                 (os, ("listdir", "scandir", "walk", "remove", "mkdir")),
                                 (glob_module, ("glob", "iglob")),
                                 (Path, ("write_bytes", "write_text", "mkdir", "unlink",
                                         "rename", "replace", "touch", "glob", "rglob",
                                         "iterdir", "read_bytes", "read_text", "exists",
                                         "resolve", "stat"))):
                for name in names:
                    stack.enter_context(patch.object(
                        owner, name, side_effect=AssertionError("forbidden IO: " + name)))
            inv = inventory()
            sel = select_inventory_items(inv, ["run.c-1"])
            handoff = build_handoff_manifest(inv, sel)
            render_inventory_lines(inv)
            render_selection_lines(sel)
            cells = notebook_cell_sources()
        self.assertEqual(handoff.collection_status, COLLECTION_STATUS)
        self.assertEqual(len(cells), 3)

    def test_the_module_imports_only_the_standard_library_and_its_own_package(self):
        source = Path(nai.__file__).read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add("." * (node.level or 0) + (node.module or ""))
        self.assertEqual(imported, {"dataclasses", "hashlib", "json", "re", ".provenance"})

    def test_the_module_names_no_kernel_or_adapter_symbol(self):
        source = Path(nai.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        called = {node.func.id for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        for entry_point in ("evaluate_state", "evaluate_node", "issue_state_certificate",
                            "evaluate_candidate_batch", "evaluate_candidate_priority",
                            "declare_candidate_manifest", "to_candidate_declarations",
                            "import_notebook_outputs", "build_check_report",
                            "filter_candidates", "hash_file", "read_structure"):
            with self.subTest(entry_point=entry_point):
                self.assertNotIn(entry_point, called)

    def test_the_layer_is_reachable_by_submodule_only(self):
        import structure_audit

        self.assertNotIn("notebook_artifact_inventory", structure_audit.__all__)
        for name in ("collect_artifact_inventory", "ArtifactInventory",
                     "select_inventory_items"):
            with self.subTest(name=name):
                self.assertNotIn(name, structure_audit.__all__)

    def test_no_kernel_module_references_this_layer(self):
        if not GOTNE_SOURCE.is_dir():
            self.skipTest("the kernel package directory is not present in this checkout")
        for path in sorted(GOTNE_SOURCE.glob("*.py")):
            with self.subTest(module=path.stem):
                self.assertNotIn("notebook_artifact_inventory",
                                 path.read_text(encoding="utf-8"),
                                 f"{path.stem} references this collection layer")


# --------------------------------------------------------------------------
# Notebook surface
# --------------------------------------------------------------------------
class NotebookSurface(unittest.TestCase):
    def test_the_cells_are_returned_fresh_and_identically_on_every_call(self):
        self.assertEqual(notebook_cell_sources(), notebook_cell_sources())
        self.assertEqual([(cid, kind) for cid, kind, _ in notebook_cell_sources()],
                         [("artifact-inventory-00-section", "markdown"),
                          ("artifact-inventory-01-collect", "code"),
                          ("artifact-inventory-02-select", "code")])

    def test_returning_the_cells_opens_and_writes_no_notebook(self):
        notebook = ROOT / "diffusion_fixed.ipynb"
        before = notebook.stat().st_mtime_ns if notebook.is_file() else None
        notebook_cell_sources()
        self.assertEqual(notebook.stat().st_mtime_ns if notebook.is_file() else None, before)

    def test_every_code_cell_parses_and_imports_only_this_layer(self):
        for cell_id, kind, source in notebook_cell_sources():
            if kind != "code":
                continue
            with self.subTest(cell=cell_id):
                modules = set()
                for node in ast.walk(ast.parse(source)):
                    if isinstance(node, ast.Import):
                        modules |= {alias.name for alias in node.names}
                    elif isinstance(node, ast.ImportFrom):
                        modules.add(node.module)
                self.assertEqual(
                    modules, {"structure_audit.notebook_artifact_inventory"})

    def test_no_code_cell_reaches_an_evaluation_path_or_a_reader(self):
        """Swept over resolved identifiers, so a prose comment is never mistaken for code."""
        forbidden = {"open", "eval", "exec", "compile", "__import__", "Path", "read_text",
                     "read_bytes", "glob", "iglob", "rglob", "listdir", "scandir", "walk",
                     "urlopen", "Popen", "run", "import_notebook_outputs", "build_check_report",
                     "evaluate_candidate_batch", "evaluate_candidate_priority",
                     "declare_candidate_manifest", "to_candidate_declarations",
                     "evaluate_state", "evaluate_node", "issue_state_certificate"}
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

    def test_the_code_cells_run_in_order_in_one_namespace_without_touching_the_disk(self):
        namespace = {"__name__": "__main__"}
        printed = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(builtins, "print",
                                             lambda *a, **k: printed.append(" ".join(map(str, a)))))
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
        self.assertIsInstance(namespace["inventory"], ArtifactInventory)
        self.assertIsInstance(namespace["selection"], ArtifactSelection)
        self.assertIsInstance(namespace["handoff"], ArtifactHandoff)
        self.assertEqual(namespace["selection"].selected_order, [],
                         "the shipped cell selects nothing by default")
        self.assertTrue(any(HANDOFF_TARGET_SEAM in line for line in printed))

    def test_the_markdown_cell_carries_the_no_claim_boundary(self):
        text = next(source for _, kind, source in notebook_cell_sources()
                    if kind == "markdown")
        for phrase in ("not evaluation", "never opened", "verbatim", "may refuse"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)


# --------------------------------------------------------------------------
# The existing priority report is untouched
# --------------------------------------------------------------------------
PROBE = r'''
import hashlib, pathlib, sys
root = pathlib.Path(sys.argv[1])
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "tests"))
sys.path.insert(0, sys.argv[2])
# Imported first and deliberately: the collection layer must not be able to influence the
# priority layer's serialization in any way.
import structure_audit.notebook_artifact_inventory  # noqa: F401
from test_phase2_cassette_candidate_priority import (
    T1_D, T3_D, VETOED_D, UNREACHABLE_D, INFEASIBLE_D, evidence_record, priority_of,
)
payload = priority_of(
    [T1_D(), T3_D(), VETOED_D(), UNREACHABLE_D(), INFEASIBLE_D()],
    evidence={"t1": evidence_record()},
).to_json_bytes()
print(len(payload), hashlib.sha256(payload).hexdigest())
'''


class PriorityReportUnchanged(unittest.TestCase):
    """The load-bearing test: the real priority report's bytes are pinned.

    The kernel package is not importable at the repository's current layout (it lives in
    avidity_sim/files while its tests expect a sibling directory named gotne), so the probe
    runs against a throwaway staging copy outside the repository. Nothing in the repository
    is created, moved or modified.
    """

    def test_the_real_priority_report_serialization_is_byte_identical(self):
        if not (GOTNE_SOURCE / "cassette_candidate_priority.py").is_file():
            self.skipTest("the priority layer is not present in this checkout")
        if not (GOTNE_TESTS / "test_phase2_cassette_candidate_priority.py").is_file():
            self.skipTest("the priority layer's fixtures are not present in this checkout")
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / "stage"
            (stage / "tests").mkdir(parents=True)
            shutil.copytree(GOTNE_SOURCE, stage / "gotne",
                            ignore=shutil.ignore_patterns("__pycache__", "test_*.py"))
            for source in (*GOTNE_TESTS.glob("test_*.py"), *GOTNE_SOURCE.glob("test_*.py")):
                shutil.copy2(source, stage / "tests" / source.name)
            completed = subprocess.run(
                [sys.executable, "-B", "-c", PROBE, str(stage), str(Path(nai.__file__).parents[1])],
                capture_output=True, text=True, timeout=300)
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        self.assertEqual(completed.stdout.split(),
                         [str(PRIORITY_REPORT_BYTES), PRIORITY_REPORT_SHA256])

    def test_the_priority_layer_source_is_not_edited_by_this_change(self):
        if not (GOTNE_SOURCE / "cassette_candidate_priority.py").is_file():
            self.skipTest("the priority layer is not present in this checkout")
        completed = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain", "--",
             "avidity_sim/files/cassette_candidate_priority.py",
             "avidity_sim/files/cassette_candidate_batch.py",
             "avidity_sim/files/demo_candidate_manifest.py"],
            capture_output=True, text=True)
        if completed.returncode != 0:
            self.skipTest("git is not available for this checkout")
        self.assertEqual(completed.stdout.strip(), "",
                         "this change must not touch the existing candidate seams")


if __name__ == "__main__":
    unittest.main()
