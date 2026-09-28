"""Contract tests for structure_artifact_pack; the pack is a reference list, not a result.

Every reference here is synthetic text. No real artifact is opened, and the layer is never
given a path to resolve: the whole point of the tests below is that a reference goes in and
comes out unchanged, having been read by nothing.

Run: PYTHONPATH=src python -m pytest tests/test_structure_artifact_pack.py
"""
import ast
import builtins
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import FrozenInstanceError
import glob as glob_module
import io
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from structure_audit import structure_artifact_pack as sap
from structure_audit.notebook_artifact_inventory import (
    INVENTORY_DOCUMENT_TYPE, SELECTION_DOCUMENT_TYPE, ArtifactInventory, ArtifactSelection,
    collect_artifact_inventory, select_inventory_items,
)
from structure_audit.structure_artifact_pack import (
    FORBIDDEN_MINTED_SUBSTRINGS, INSPECTION_KIND, PACK_DISPLAY_DISCLAIMER,
    PACK_DOCUMENT_TYPE, PACK_FIELDS, PACK_ITEM_FIELDS, PACK_NON_CLAIM, REFUSAL_REASONS,
    SOURCE_DOCUMENT_TYPES, StructureArtifactPack, StructureArtifactPackError,
    build_artifact_pack, notebook_cell_sources, render_pack_lines,
)

ROOT = Path(__file__).resolve().parents[1]
GOTNE_SOURCE = ROOT / "avidity_sim" / "files"

#: Command verbs an inspection-tool script would carry. None may appear in any output,
#: because emitting one would assert what a reference names.
TOOL_COMMANDS = (
    "load", "fetch", "cmd.", "pymol", "chimera", "vmd", "save", "png", "ray", "show",
    "hide", "select ", "align", "super", "cealign", "fit", "orient", "zoom", "color",
    "set_view", "create", "sculpt", "minimize", "dock", ".pse", "run ",
)

ITEMS = [
    {"item_id": "run-b", "reference": "external_artifacts/run-b/model.cif",
     "declared_metadata": {"declared_by": "producer-x", "nested": {"k": [1, 2, None]}}},
    {"item_id": "run-a", "reference": " run-a  with spaces / and ünïcode ",
     "declared_metadata": {}},
    {"item_id": "run.c-1", "reference": "run-c", "declared_metadata": {"n": 0, "f": 1.5}},
]


def inventory(items=None):
    return collect_artifact_inventory(deepcopy(ITEMS if items is None else items))


def selection(ids=("run.c-1", "run-b"), inv=None):
    inv = inventory() if inv is None else inv
    return select_inventory_items(inv, list(ids))


def pack(source=None):
    return build_artifact_pack(selection() if source is None else source)


def minted_keys(value, *, verbatim=False):
    """Every name this layer mints. declared_metadata is a boundary, never descended into."""
    names = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if not verbatim:
                names.add(key)
            names |= minted_keys(child, verbatim=verbatim or key == "declared_metadata")
    elif isinstance(value, list):
        for child in value:
            names |= minted_keys(child, verbatim=verbatim)
    return names


def refusal(callable_, *args, **kwargs):
    try:
        callable_(*args, **kwargs)
    except StructureArtifactPackError as exc:
        return exc
    raise AssertionError("expected a refusal")


# --------------------------------------------------------------------------
# Reference-only
# --------------------------------------------------------------------------
class ReferenceOnly(unittest.TestCase):
    def test_references_are_carried_character_for_character(self):
        built = pack(inventory())
        self.assertEqual(built.references(), [item["reference"] for item in ITEMS])

    def test_declared_metadata_is_carried_verbatim(self):
        built = pack(inventory())
        self.assertEqual([item["declared_metadata"] for item in built.items],
                         [item["declared_metadata"] for item in ITEMS])

    def test_no_reference_is_opened_resolved_or_existence_checked(self):
        """Every reference below names nothing on disk, and the pack is built anyway."""
        absent = [{"item_id": "gone", "reference": "/definitely/not/here/x.cif",
                   "declared_metadata": {}},
                  {"item_id": "odd", "reference": "not even a path",
                   "declared_metadata": {}}]
        built = pack(inventory(absent))
        self.assertEqual(built.references(),
                         ["/definitely/not/here/x.cif", "not even a path"])

    def test_the_pack_emits_no_tool_command_script_or_session(self):
        """Swept over everything but the two denial texts, which name these verbs to deny them.

        The synthetic references carry no verb themselves, so any hit in the swept text would
        be this layer generating a tool instruction.
        """
        built = pack(inventory())
        data = built.to_dict()
        del data["non_claim"]
        swept = json.dumps(data).lower() + "\n" + "\n".join(
            line for line in render_pack_lines(built)
            if line != PACK_DISPLAY_DISCLAIMER).lower()
        for verb in TOOL_COMMANDS:
            with self.subTest(verb=verb):
                self.assertNotIn(verb, swept, f"the pack emits {verb!r}")

    def test_the_two_denial_texts_are_the_only_place_those_verbs_appear(self):
        """They appear there as denials, which is the point; nowhere else may carry them."""
        for verb in ("align", "superpos", "dock", "minimiz"):
            with self.subTest(verb=verb):
                self.assertIn(verb, PACK_NON_CLAIM.lower())

    def test_the_public_surface_offers_no_command_or_script_entry_point(self):
        exported = set(sap.__all__)
        for verb in ("load", "script", "session", "command", "pymol", "align", "super",
                     "open", "write", "save", "export"):
            with self.subTest(verb=verb):
                self.assertEqual([name for name in exported if verb in name.lower()], [])

    def test_references_are_returned_as_plain_text_in_document_order(self):
        built = pack()
        self.assertEqual(built.references(),
                         [item["reference"] for item in built.items])
        self.assertTrue(all(type(value) is str for value in built.references()))

    def test_nothing_is_paired_grouped_or_related_across_items(self):
        built = pack(inventory())
        for item in built.items:
            with self.subTest(item=item["item_id"]):
                self.assertEqual(sorted(item), sorted(PACK_ITEM_FIELDS))

    def test_the_pack_records_which_source_document_it_came_from(self):
        inv = inventory()
        sel = selection(inv=inv)
        self.assertEqual(build_artifact_pack(inv).source_document_type,
                         INVENTORY_DOCUMENT_TYPE)
        self.assertEqual(build_artifact_pack(sel).source_document_type,
                         SELECTION_DOCUMENT_TYPE)
        self.assertEqual(build_artifact_pack(inv).source_digest, inv.digest)
        self.assertEqual(build_artifact_pack(sel).source_digest, sel.digest)
        self.assertEqual(SOURCE_DOCUMENT_TYPES,
                         (INVENTORY_DOCUMENT_TYPE, SELECTION_DOCUMENT_TYPE))

    def test_only_a_collection_layer_document_is_accepted(self):
        for bad in (None, {}, "inventory", ITEMS, inventory().to_dict(),
                    inventory().to_json_bytes()):
            with self.subTest(source=type(bad).__qualname__):
                self.assertEqual(refusal(build_artifact_pack, bad).reason,
                                 "SOURCE_KIND_UNEXPECTED")

    def test_an_empty_pack_is_valid_and_names_its_own_emptiness(self):
        built = build_artifact_pack(collect_artifact_inventory([]))
        self.assertEqual((built.order, built.items, built.references()), ([], [], []))
        self.assertTrue(any("does not mean every artifact" in line
                            for line in render_pack_lines(built)))


# --------------------------------------------------------------------------
# Order comes from the source
# --------------------------------------------------------------------------
class OrderFromSource(unittest.TestCase):
    def test_pack_order_is_the_inventorys_own_order(self):
        inv = inventory()
        self.assertEqual(build_artifact_pack(inv).order, inv.order)

    def test_pack_order_is_the_selections_own_order(self):
        for ids in (["run-a", "run-b"], ["run-b", "run-a"], ["run.c-1", "run-a", "run-b"]):
            with self.subTest(ids=ids):
                sel = selection(ids)
                self.assertEqual(build_artifact_pack(sel).order, ids)

    def test_the_pack_never_sorts_by_identifier_reference_or_metadata(self):
        order = build_artifact_pack(inventory()).order
        self.assertNotEqual(order, sorted(order))
        self.assertEqual(order, [item["item_id"] for item in ITEMS])

    def test_a_supplied_order_is_never_trusted(self):
        data = pack(inventory()).to_dict()
        data["order"] = sorted(data["order"])
        self.assertEqual(refusal(StructureArtifactPack.from_dict, data).reason,
                         "ORDER_NOT_DERIVED")

    def test_nothing_is_added_removed_or_deduplicated(self):
        inv = inventory()
        built = build_artifact_pack(inv)
        self.assertEqual(built.order, inv.order)
        data = built.to_dict()
        data["items"].append(deepcopy(data["items"][0]))
        data["order"].append(data["items"][0]["item_id"])
        self.assertEqual(refusal(StructureArtifactPack.from_dict, data).reason,
                         "DUPLICATE_ITEM_ID")


# --------------------------------------------------------------------------
# No judgement is minted
# --------------------------------------------------------------------------
class NoMintedJudgement(unittest.TestCase):
    def test_no_minted_name_is_a_score_pose_complex_or_quality_field(self):
        built = pack(inventory())
        for name in sorted(minted_keys(built.to_dict())):
            for forbidden in FORBIDDEN_MINTED_SUBSTRINGS:
                with self.subTest(field=name, forbidden=forbidden):
                    self.assertNotIn(forbidden, name.lower())

    def test_the_declared_field_tuples_are_the_whole_minted_surface(self):
        built = pack(inventory())
        self.assertEqual(sorted(built.to_dict()), sorted(PACK_FIELDS))
        self.assertEqual(minted_keys(built.to_dict()),
                         set(PACK_FIELDS) | set(PACK_ITEM_FIELDS))

    def test_a_judgement_shaped_metadata_key_is_carried_and_never_acted_on(self):
        declared = {"score": 0.99, "best_pose": True, "bound_complex": "yes",
                    "rmsd": 1.2, "recommendation": "use"}
        supplied = [{"item_id": "x", "reference": "r-x", "declared_metadata": declared},
                    {"item_id": "y", "reference": "r-y", "declared_metadata": {}}]
        built = pack(inventory(supplied))
        self.assertEqual(built.order, ["x", "y"], "metadata never reorders a pack")
        self.assertEqual(built.items[0]["declared_metadata"], declared)
        self.assertEqual(minted_keys(built.to_dict()) & set(declared), set(),
                         "caller metadata keys are never promoted to minted fields")

    def test_a_new_judgement_shaped_minted_name_still_fails(self):
        data = pack().to_dict()
        for name in ("best_pose", "bound_complex", "interface_score", "alignment"):
            with self.subTest(field=name):
                payload = dict(data)
                payload[name] = 1
                self.assertIn(refusal(StructureArtifactPack.from_dict, payload).reason,
                              ("UNKNOWN_FIELD", "MINTED_FIELD_FORBIDDEN"))

    def test_inspection_kind_is_fixed_and_no_request_can_change_it(self):
        built = pack()
        self.assertEqual((built.inspection_kind, INSPECTION_KIND),
                         (INSPECTION_KIND, "REFERENCE_ONLY_INSPECTION"))
        data = built.to_dict()
        data["inspection_kind"] = "VALIDATED_COMPLEX"
        refusal(StructureArtifactPack.from_dict, data)
        self.assertEqual(built.inspection_kind, INSPECTION_KIND)

    def test_no_public_object_offers_a_way_to_reach_a_judgement(self):
        exported = set(sap.__all__)
        for verb in ("rank", "score", "sort", "filter", "recommend", "admit", "veto",
                     "evaluate", "validate", "best", "top", "auto"):
            with self.subTest(verb=verb):
                self.assertEqual([name for name in exported if verb in name.lower()], [])


# --------------------------------------------------------------------------
# Non-claim language
# --------------------------------------------------------------------------
class NonClaimLanguage(unittest.TestCase):
    def test_the_non_claim_denies_bound_complexes_best_poses_and_binding_proofs(self):
        for phrase in ("not validated bound complexes",
                       "not best or representative poses",
                       "binding, contact, affinity or avidity proofs",
                       "inspection references",
                       "never opened, resolved, dereferenced, existence-checked or read",
                       "no tool command, script, session",
                       "is not evidence about an item"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, PACK_NON_CLAIM)

    def test_the_display_disclaimer_denies_the_same_claims(self):
        for phrase in ("not validated bound complexes", "best poses", "binding proofs",
                       "carried verbatim", "No tool command or session is generated",
                       "not a preference"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, PACK_DISPLAY_DISCLAIMER)

    def test_the_non_claim_is_emitted_verbatim_and_an_alteration_is_refused(self):
        self.assertEqual(pack().non_claim, PACK_NON_CLAIM)
        data = pack().to_dict()
        data["non_claim"] = PACK_NON_CLAIM.replace("not validated", "validated")
        self.assertEqual(refusal(StructureArtifactPack.from_dict, data).reason,
                         "NON_CLAIM_ALTERED")

    def test_the_rendering_leads_with_the_disclaimer(self):
        self.assertEqual(render_pack_lines(pack())[0], PACK_DISPLAY_DISCLAIMER)

    def test_the_reference_block_asserts_nothing_about_what_a_reference_is(self):
        """The rows carry identifiers, references and metadata; no verdict of any kind."""
        rows = "\n".join(render_pack_lines(pack(inventory()))[7:]).lower()
        for claim in ("validated", "verified", "confirmed", "proven", "best pose",
                      "bound complex", "docked", "superposed", "refined", "structure"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, rows)


# --------------------------------------------------------------------------
# Determinism and immutability
# --------------------------------------------------------------------------
class Determinism(unittest.TestCase):
    def test_identical_sources_give_identical_bytes(self):
        self.assertEqual(pack(inventory()).to_json_bytes(),
                         pack(inventory()).to_json_bytes())

    def test_a_pack_from_an_identical_selection_is_byte_identical(self):
        self.assertEqual(pack(selection()).to_json_bytes(),
                         pack(selection()).to_json_bytes())

    def test_repeated_serialization_of_one_pack_is_stable(self):
        built = pack()
        self.assertEqual(built.to_json_bytes(), built.to_json_bytes())
        self.assertEqual(built.digest, built.digest)

    def test_item_key_insertion_order_never_changes_the_output(self):
        reordered = [{name: item[name] for name in reversed(PACK_ITEM_FIELDS)}
                     for item in ITEMS]
        self.assertEqual(pack(inventory(reordered)).to_json_bytes(),
                         pack(inventory()).to_json_bytes())

    def test_a_pack_reloads_from_its_own_bytes(self):
        built = pack(inventory())
        self.assertEqual(StructureArtifactPack(built.to_json_bytes()).to_json_bytes(),
                         built.to_json_bytes())

    def test_non_canonical_bytes_are_refused_rather_than_recanonicalized(self):
        loose = json.dumps(pack().to_dict(), indent=2).encode("utf-8")
        self.assertEqual(refusal(StructureArtifactPack, loose).reason, "NOT_CANONICAL_BYTES")

    def test_a_duplicate_json_key_is_not_a_document(self):
        raw = pack().to_json_bytes().replace(b'"order":', b'"order":[],"order":', 1)
        self.assertEqual(refusal(StructureArtifactPack, raw).reason, "DUPLICATE_JSON_KEY")

    def test_building_does_not_mutate_the_source_document(self):
        inv = inventory()
        sel = selection(inv=inv)
        pinned = (inv.to_json_bytes(), sel.to_json_bytes())
        build_artifact_pack(inv)
        build_artifact_pack(sel)
        self.assertEqual((inv.to_json_bytes(), sel.to_json_bytes()), pinned)

    def test_mutating_a_returned_view_never_reaches_the_document(self):
        built = pack(inventory())
        pinned = built.to_json_bytes()
        built.items.clear()
        built.order.append("late")
        built.references().clear()
        self.assertEqual(built.to_json_bytes(), pinned)

    def test_mutating_rendered_lines_never_reaches_the_document(self):
        built = pack()
        pinned = render_pack_lines(built)
        render_pack_lines(built).clear()
        self.assertEqual(render_pack_lines(built), pinned)

    def test_the_document_is_immutable(self):
        with self.assertRaises(FrozenInstanceError):
            pack().json_bytes = b"{}"

    def test_a_source_digest_that_does_not_match_its_shape_is_refused(self):
        data = pack().to_dict()
        data["source_digest"] = "not a digest"
        self.assertEqual(refusal(StructureArtifactPack.from_dict, data).reason,
                         "MALFORMED_DOCUMENT")

    def test_every_declared_refusal_reason_is_a_member(self):
        for reason in ("SOURCE_KIND_UNEXPECTED", "SOURCE_DOCUMENT_TYPE_UNEXPECTED",
                       "DUPLICATE_ITEM_ID", "ORDER_NOT_DERIVED", "NOT_CANONICAL_BYTES",
                       "NON_CLAIM_ALTERED", "MINTED_FIELD_FORBIDDEN"):
            with self.subTest(reason=reason):
                self.assertIn(reason, REFUSAL_REASONS)


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
            built = pack(inventory())
            render_pack_lines(built)
            built.references()
            notebook_cell_sources()
        self.assertEqual(opened, [])

    def test_no_entry_point_writes_scans_or_starts_a_subprocess(self):
        with ExitStack() as stack:
            for owner, names in ((subprocess, ("Popen", "run", "check_output")),
                                 (os, ("listdir", "scandir", "walk", "remove", "mkdir")),
                                 (glob_module, ("glob", "iglob")),
                                 (Path, ("write_bytes", "write_text", "mkdir", "unlink",
                                         "glob", "rglob", "iterdir", "read_bytes",
                                         "read_text", "exists", "resolve", "stat",
                                         "is_file", "is_dir"))):
                for name in names:
                    stack.enter_context(patch.object(
                        owner, name, side_effect=AssertionError("forbidden IO: " + name)))
            built = pack(inventory())
            render_pack_lines(built)
            references = built.references()
            cells = notebook_cell_sources()
        self.assertEqual(built.inspection_kind, INSPECTION_KIND)
        self.assertEqual(len(references), len(ITEMS))
        self.assertEqual(len(cells), 2)

    def test_the_module_imports_only_the_standard_library_and_its_own_package(self):
        imported = set()
        for node in ast.walk(ast.parse(Path(sap.__file__).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imported |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add("." * (node.level or 0) + (node.module or ""))
        self.assertEqual(imported, {"dataclasses", "hashlib", "json",
                                    ".notebook_artifact_inventory", ".provenance"})

    def test_the_module_names_no_reader_producer_or_tool_entry_point(self):
        tree = ast.parse(Path(sap.__file__).read_text(encoding="utf-8"))
        called = {node.func.id for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        for entry_point in ("read_structure", "hash_file", "import_notebook_outputs",
                            "build_check_report", "filter_candidates", "open",
                            "evaluate_candidate_priority", "structure_integrity_check",
                            "coarse_steric_clash_check", "canonical_residue_map"):
            with self.subTest(entry_point=entry_point):
                self.assertNotIn(entry_point, called)

    def test_the_layer_is_reachable_by_submodule_only(self):
        import structure_audit

        self.assertNotIn("structure_artifact_pack", structure_audit.__all__)
        for name in ("build_artifact_pack", "StructureArtifactPack"):
            with self.subTest(name=name):
                self.assertNotIn(name, structure_audit.__all__)

    def test_no_kernel_module_references_this_layer(self):
        if not GOTNE_SOURCE.is_dir():
            self.skipTest("the kernel package directory is not present in this checkout")
        for path in sorted(GOTNE_SOURCE.glob("*.py")):
            with self.subTest(module=path.stem):
                self.assertNotIn("structure_artifact_pack",
                                 path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Notebook surface
# --------------------------------------------------------------------------
class NotebookSurface(unittest.TestCase):
    def test_the_cells_are_returned_fresh_and_identically_on_every_call(self):
        self.assertEqual(notebook_cell_sources(), notebook_cell_sources())
        self.assertEqual([(cid, kind) for cid, kind, _ in notebook_cell_sources()],
                         [("artifact-pack-00-section", "markdown"),
                          ("artifact-pack-01-render", "code")])

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
                self.assertEqual(modules, {"structure_audit.structure_artifact_pack"})

    def test_no_code_cell_reaches_a_reader_a_tool_or_the_disk(self):
        forbidden = {"open", "eval", "exec", "compile", "__import__", "Path", "read_text",
                     "read_bytes", "glob", "listdir", "walk", "urlopen", "Popen", "run",
                     "read_structure", "hash_file", "import_notebook_outputs", "sorted",
                     "cmd", "pymol"}
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

    def test_the_code_cell_runs_against_a_supplied_selection_without_touching_the_disk(self):
        namespace = {"__name__": "__main__", "selection": selection()}
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
        self.assertIsInstance(namespace["pack"], StructureArtifactPack)
        self.assertEqual(namespace["pack"].order, namespace["selection"].selected_order)
        self.assertTrue(any("Inspection references" in line for line in printed))

    def test_the_markdown_cell_carries_the_no_claim_boundary(self):
        text = next(source for _, kind, source in notebook_cell_sources()
                    if kind == "markdown")
        for phrase in ("validated bound complexes", "representative poses",
                       "No tool command", "never opened", "not a preference",
                       "not** binding, contact, affinity or avidity proofs"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_the_two_notebook_surfaces_use_distinct_cell_ids(self):
        from structure_audit.candidate_combinations_table import (
            notebook_cell_sources as table_cells,
        )
        from structure_audit.notebook_artifact_inventory import (
            notebook_cell_sources as inventory_cells,
        )

        identifiers = [cid for cells in (notebook_cell_sources(), table_cells(),
                                         inventory_cells())
                       for cid, _, _ in cells]
        self.assertEqual(len(identifiers), len(set(identifiers)))


if __name__ == "__main__":
    unittest.main()
