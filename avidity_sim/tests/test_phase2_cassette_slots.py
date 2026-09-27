"""Phase 2 slot seam: cassette_slots (cassette-slots specification).

Covers the ordered three-slot binding only: SlotId / SLOT_IDS, SlotAssignment,
CassetteSlotBinding, the projection to EngagementState, the config-relative
validator, slot_binding_hash, and the import boundary that keeps this module a
sibling of the chain head rather than a link in it.

The seam must change nothing downstream, so two tests pin non-change directly:
a projected state hashes exactly like an equivalent hand-built one, and an
evaluate_state run over a projected state is byte-identical to one over the
hand-built state.

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

from gotne import cassette_slots  # noqa: E402
from gotne.cassette_closure import evaluate_state  # noqa: E402
from gotne.cassette_schema import CassetteSpec, TetherSpec, TopologyMode  # noqa: E402
from gotne.cassette_slots import (  # noqa: E402
    SLOT_IDS,
    CassetteSlotBinding,
    SlotAssignment,
    SlotId,
    project_engagement_state,
    slot_binding_hash,
    validate_slot_binding,
)
from gotne.cassette_topology import validate_cassette_config  # noqa: E402
from gotne.cassette_state import (  # noqa: E402
    EngagementLabel,
    EngagementState,
    EvaluationContext,
    ModuleAssignment,
    TargetContext,
    TargetGeometry,
)
from gotne.identity import (  # noqa: E402
    CANONICAL_FORM_VERSION,
    canonical_form,
    state_identity_hash,
)
from gotne.status import Status  # noqa: E402
from test_cassette_topology import base_policy, module, ref_cassette_3  # noqa: E402
from test_phase2_cassette_budget import budget_cfg  # noqa: E402

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT_DIR / "gotne"
CHAIN_MODULES = ("cassette_frames", "cassette_budget", "cassette_closure", "cassette_node")
IDENTITY_R = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
SITES = {"t1": (0.0, 0.0, 0.0), "t2": (2.0, 0.0, 0.0), "t3": (4.0, 0.0, 0.0)}

ENGAGED = EngagementLabel.ENGAGED
UNENGAGED = EngagementLabel.UNENGAGED


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
def slot(slot_id, module_id, target_id=None):
    label = UNENGAGED if target_id is None else ENGAGED
    return SlotAssignment(slot_id, module_id, label, target_id)


def binding(*, t1="t1", t2="t2", t3="t3", modules=("D1", "D2", "D3")):
    return CassetteSlotBinding(
        slot(SlotId.SLOT_1, modules[0], t1),
        slot(SlotId.SLOT_2, modules[1], t2),
        slot(SlotId.SLOT_3, modules[2], t3),
    )


def context():
    return EvaluationContext(
        TargetContext(tuple((t, TargetGeometry(site, IDENTITY_R)) for t, site in SITES.items()))
    )


def ref_cassette_2():
    """REF-CASSETTE-3 shortened to a0 -> D1 -> D2; still valid under Phase 1c."""
    return replace(
        ref_cassette_3(),
        id="REF-CASSETTE-2",
        cassettes=(
            CassetteSpec(
                id="cas1",
                root_anchor_id="a0",
                ordered_modules=("D1", "D2"),
                ordered_segments=("s0", "s1"),
            ),
        ),
        modules=(module("D1", 1), module("D2", 2, terminal=True, exclusion_centre=(0.5, 0.0, 0.0))),
        tethers=(
            TetherSpec(id="s0", from_node="a0", to_node="D1", cassette_index=0),
            TetherSpec(id="s1", from_node="D1", to_node="D2", cassette_index=1),
        ),
    )


# --------------------------------------------------------------------------
# Slot identity and construction
# --------------------------------------------------------------------------
class SlotIdentity(unittest.TestCase):
    def test_exactly_three_ordered_slot_ids(self):
        self.assertEqual([s.value for s in SlotId], ["slot_1", "slot_2", "slot_3"])
        self.assertEqual(SLOT_IDS, (SlotId.SLOT_1, SlotId.SLOT_2, SlotId.SLOT_3))

    def test_binding_has_three_named_fields_and_no_sequence_field(self):
        from dataclasses import fields

        names = [f.name for f in fields(CassetteSlotBinding)]
        self.assertEqual(names, ["slot_1", "slot_2", "slot_3"])
        self.assertEqual(names, [s.value for s in SLOT_IDS], "field names are the slot names")
        for field in fields(CassetteSlotBinding):
            self.assertIs(field.type if not isinstance(field.type, str) else SlotAssignment,
                          SlotAssignment)

    def test_binding_and_assignment_are_frozen(self):
        b = binding()
        with self.assertRaises(FrozenInstanceError):
            b.slot_1 = b.slot_2
        with self.assertRaises(FrozenInstanceError):
            b.slot_1.module_id = "DX"

    def test_ordered_assignments_follow_slot_ids(self):
        b = binding()
        self.assertEqual([a.slot for a in b.ordered_assignments()], list(SLOT_IDS))
        self.assertEqual([a.module_id for a in b.ordered_assignments()], ["D1", "D2", "D3"])


class ConstructionRefusals(unittest.TestCase):
    """Every row here is contract-invalid: it raises and yields no object."""

    def test_wrong_outer_shape(self):
        three = binding().ordered_assignments()
        with self.assertRaises(TypeError):
            CassetteSlotBinding(list(three))  # a sequence is not a binding
        with self.assertRaises(TypeError):
            CassetteSlotBinding(*three[:2])  # arity is fixed by the type
        with self.assertRaises(TypeError):
            CassetteSlotBinding(three[0], three[1], "slot_3")

    def test_slot_field_name_mismatch(self):
        good = binding()
        with self.assertRaises(ValueError) as caught:
            CassetteSlotBinding(good.slot_2, good.slot_2, good.slot_3)
        self.assertIn("must name its own field", str(caught.exception))
        swapped = CassetteSlotBinding.__new__(CassetteSlotBinding)
        del swapped  # constructed only to show no bypass is offered below
        with self.assertRaises(ValueError):
            CassetteSlotBinding(good.slot_1, good.slot_3, good.slot_2)

    def test_label_and_target_agreement(self):
        with self.assertRaises(ValueError):
            SlotAssignment(SlotId.SLOT_1, "D1", ENGAGED, None)
        with self.assertRaises(ValueError):
            SlotAssignment(SlotId.SLOT_1, "D1", ENGAGED, "")
        with self.assertRaises(ValueError):
            SlotAssignment(SlotId.SLOT_1, "D1", UNENGAGED, "t1")

    def test_duplicate_module_id_across_slots(self):
        with self.assertRaises(ValueError) as caught:
            binding(modules=("D1", "D1", "D3"))
        self.assertIn("duplicate module_id", str(caught.exception))

    def test_empty_and_non_str_identifiers(self):
        with self.assertRaises(ValueError):
            SlotAssignment(SlotId.SLOT_1, "", ENGAGED, "t1")
        with self.assertRaises(TypeError):
            SlotAssignment(SlotId.SLOT_1, None, ENGAGED, "t1")
        with self.assertRaises(ValueError):
            SlotAssignment(SlotId.SLOT_1, "D1", ENGAGED, 1)
        with self.assertRaises(TypeError):
            SlotAssignment("slot_1", "D1", ENGAGED, "t1")
        with self.assertRaises(TypeError):
            SlotAssignment(SlotId.SLOT_1, "D1", "ENGAGED", "t1")

    def test_projection_and_hash_refuse_foreign_arguments(self):
        for call in (project_engagement_state, slot_binding_hash):
            with self.assertRaises(TypeError):
                call(binding().ordered_assignments())


# --------------------------------------------------------------------------
# Projection
# --------------------------------------------------------------------------
class Projection(unittest.TestCase):
    def test_every_slot_becomes_an_explicit_assignment(self):
        state = project_engagement_state(binding(t2=None))
        self.assertEqual(len(state.assignments), 3, "no slot is dropped")
        by_id = {a.module_id: a for a in state.assignments}
        self.assertEqual(by_id["D2"], ModuleAssignment("D2", UNENGAGED, None))
        self.assertEqual(by_id["D1"], ModuleAssignment("D1", ENGAGED, "t1"))
        self.assertIs(state.label_of("D2"), UNENGAGED)
        self.assertEqual([a.module_id for a in state.engaged_assignments()], ["D1", "D3"])

    def test_all_unengaged_projects_without_selecting_a_slot(self):
        state = project_engagement_state(binding(t1=None, t2=None, t3=None))
        self.assertEqual(state.engaged_assignments(), ())
        self.assertEqual([a.label for a in state.assignments], [UNENGAGED] * 3)

    def test_projection_loses_slot_order(self):
        # EngagementState stores ascending by module_id, so a binding whose slot
        # order disagrees with module order projects to the same stored order.
        reversed_modules = binding(modules=("D3", "D2", "D1"), t1="t3", t3="t1")
        state = project_engagement_state(reversed_modules)
        self.assertEqual([a.module_id for a in state.assignments], ["D1", "D2", "D3"])
        self.assertEqual(
            [a.slot.value for a in reversed_modules.ordered_assignments()],
            ["slot_1", "slot_2", "slot_3"],
            "the binding itself keeps its order",
        )
        self.assertFalse(hasattr(state, "slot_1"), "no slot survives into the state")


class NonChangeDownstream(unittest.TestCase):
    def test_state_identity_hash_matches_a_hand_built_state(self):
        projected = project_engagement_state(binding())
        hand_built = EngagementState(
            (
                ModuleAssignment("D1", ENGAGED, "t1"),
                ModuleAssignment("D2", ENGAGED, "t2"),
                ModuleAssignment("D3", ENGAGED, "t3"),
            )
        )
        self.assertEqual(state_identity_hash(projected), state_identity_hash(hand_built))
        # AP-27: an explicit UNENGAGED slot hashes like an omitted module.
        with_unengaged = project_engagement_state(binding(t2=None))
        omitted = EngagementState(
            (ModuleAssignment("D1", ENGAGED, "t1"), ModuleAssignment("D3", ENGAGED, "t3"))
        )
        self.assertEqual(state_identity_hash(with_unengaged), state_identity_hash(omitted))

    def test_evaluate_state_result_is_unchanged_through_the_projection(self):
        cfg, ctx = budget_cfg(), context()
        projected = project_engagement_state(binding())
        hand_built = EngagementState(
            (
                ModuleAssignment("D1", ENGAGED, "t1"),
                ModuleAssignment("D2", ENGAGED, "t2"),
                ModuleAssignment("D3", ENGAGED, "t3"),
            )
        )
        from_projection = evaluate_state(projected, cfg, cfg.policy, ctx)
        from_hand = evaluate_state(hand_built, cfg, cfg.policy, ctx)
        self.assertEqual(from_projection.result_id, from_hand.result_id)
        self.assertEqual(
            json.dumps(from_projection.as_dict(), sort_keys=True, allow_nan=False),
            json.dumps(from_hand.as_dict(), sort_keys=True, allow_nan=False),
        )


# --------------------------------------------------------------------------
# Config-relative validator
# --------------------------------------------------------------------------
class Validator(unittest.TestCase):
    def test_accepts_slot_k_bound_to_cassette_position_k(self):
        self.assertIsNone(validate_slot_binding(binding(), ref_cassette_3()))

    def test_rejects_a_permuted_module_order(self):
        with self.assertRaises(ValueError) as caught:
            validate_slot_binding(binding(modules=("D3", "D2", "D1")), ref_cassette_3())
        self.assertIn("position k", str(caught.exception))

    def test_rejects_a_module_outside_the_cassette(self):
        with self.assertRaises(ValueError):
            validate_slot_binding(binding(modules=("D1", "D2", "DX")), ref_cassette_3())

    def test_rejects_a_cassette_without_exactly_three_modules(self):
        two = ref_cassette_2()
        self.assertIs(
            validate_cassette_config(two).status, Status.VALID, "the 2-module fixture must be VALID"
        )
        with self.assertRaises(ValueError) as caught:
            validate_slot_binding(binding(), two)
        self.assertIn("exactly 3 ordered modules", str(caught.exception))

    def test_rejects_a_config_invalid_under_phase1c(self):
        from dataclasses import replace

        invalid = replace(ref_cassette_3(), policy=base_policy(topology_mode=TopologyMode.GENERAL_DAG))
        with self.assertRaises(ValueError) as caught:
            validate_slot_binding(binding(), invalid)
        self.assertIn("under Phase 1c", str(caught.exception))

    def test_repeated_target_id_remains_allowed(self):
        shared = binding(t1="t1", t2="t1", t3="t1")
        self.assertIsNone(validate_slot_binding(shared, ref_cassette_3()))
        state = project_engagement_state(shared)
        self.assertEqual([a.target_id for a in state.engaged_assignments()], ["t1", "t1", "t1"])

    def test_validator_refuses_foreign_arguments(self):
        with self.assertRaises(TypeError):
            validate_slot_binding(binding().ordered_assignments(), ref_cassette_3())
        with self.assertRaises(TypeError):
            validate_slot_binding(binding(), None)


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------
class SlotBindingHash(unittest.TestCase):
    def test_deterministic_and_slot_order_sensitive(self):
        self.assertEqual(slot_binding_hash(binding()), slot_binding_hash(binding()))
        self.assertEqual(len(slot_binding_hash(binding())), 64)
        permuted = binding(t1="t3", t3="t1")
        self.assertNotEqual(slot_binding_hash(binding()), slot_binding_hash(permuted))

    def test_shape_matches_the_package_digest_convention(self):
        import hashlib

        from gotne import identity

        b = binding()
        expected = identity._digest(["slot_binding_identity", canonical_form(b)])
        self.assertEqual(slot_binding_hash(b), expected)
        text = json.dumps(
            [CANONICAL_FORM_VERSION, ["slot_binding_identity", canonical_form(b)]],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        self.assertEqual(slot_binding_hash(b), hashlib.sha256(text.encode("utf-8")).hexdigest())


# --------------------------------------------------------------------------
# Import boundary
# --------------------------------------------------------------------------
class ImportBoundary(unittest.TestCase):
    def _imported_gotne_modules(self, source):
        names = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                names.update(a.name.split(".")[-1] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # relative: from . import x / from .x import y
                    if node.module:
                        names.add(node.module.split(".")[-1])
                    names.update(a.name for a in node.names)
                elif node.module and node.module.startswith("gotne"):
                    names.add(node.module.split(".")[-1])
                    names.update(a.name for a in node.names)
        return names

    def test_static_closure_reaches_no_chain_module(self):
        seen, queue = set(), ["cassette_slots"]
        while queue:
            name = queue.pop()
            if name in seen:
                continue
            path = PACKAGE_DIR / f"{name}.py"
            if not path.is_file():
                continue
            seen.add(name)
            for imported in self._imported_gotne_modules(path.read_text()):
                self.assertNotIn(
                    imported, CHAIN_MODULES, f"{name} reaches chain module {imported}"
                )
                queue.append(imported)
        self.assertIn("cassette_state", seen, "the closure scan actually walked the sources")

    def test_no_chain_module_imports_cassette_slots(self):
        for name in CHAIN_MODULES + ("cassette_state", "cassette_topology", "identity", "status"):
            source = (PACKAGE_DIR / f"{name}.py").read_text()
            self.assertNotIn(
                "cassette_slots", self._imported_gotne_modules(source), f"{name} imports the seam"
            )

    def test_not_exported_from_the_package_init(self):
        source = (PACKAGE_DIR / "__init__.py").read_text()
        self.assertNotIn("cassette_slots", self._imported_gotne_modules(source))

    def test_dynamic_import_pulls_in_no_chain_module(self):
        # gotne/__init__ imports the whole chain, so the package is loaded here
        # as a namespace stub: relative imports still resolve, __init__ never runs,
        # and a meta_path trap fails the test on any forbidden import.
        program = (
            "import importlib, importlib.abc, importlib.machinery, sys, types\n"
            f"root = {str(PACKAGE_DIR)!r}\n"
            f"forbidden = {[f'gotne.{m}' for m in CHAIN_MODULES]!r}\n"
            "pkg = types.ModuleType('gotne')\n"
            "pkg.__path__ = [root]\n"
            "pkg.__package__ = 'gotne'\n"
            "pkg.__spec__ = importlib.machinery.ModuleSpec('gotne', None, is_package=True)\n"
            "pkg.__spec__.submodule_search_locations = [root]\n"
            "sys.modules['gotne'] = pkg\n"
            "class Trap(importlib.abc.MetaPathFinder):\n"
            "    def find_spec(self, name, path=None, target=None):\n"
            "        if name in forbidden:\n"
            "            raise AssertionError('forbidden import: ' + name)\n"
            "        return None\n"
            "sys.meta_path.insert(0, Trap())\n"
            "importlib.import_module('gotne.cassette_slots')\n"
            "leaked = [m for m in forbidden if m in sys.modules]\n"
            "print('LEAKED:' + ','.join(leaked))\n"
        )
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-c", program],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        self.assertIn("LEAKED:\n", completed.stdout, completed.stdout)


if __name__ == "__main__":
    unittest.main()
