"""Phase 2 slot ledger: cassette_slot_ledger (cassette-slots specification).

Covers the caller-side triage artefact only: fixed row order over SLOT_IDS,
explicit rows for UNENGAGED slots, the STATE/NODE field mapping, the four
failure classes, canonical serialization and read-only behaviour. The ledger
evaluates nothing, so every STATE and NODE result here comes from the real
kernel and is compared against itself before and after arrangement.

Fixture outcomes, from the budget fixture with identity orientations:
NEAR gives a VALID state whose D1 node is INFEASIBLE / GEOMETRY_INPUT_INVALID
(its ancestor is ROOT and the root anchor declares no position) while D2 and D3
are VALID; FAR gives UNREACHABLE / CHAIN_CLOSURE_VIOLATED and no certificate.

Run: python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys
import unittest
from dataclasses import FrozenInstanceError

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from gotne.cassette_closure import evaluate_state  # noqa: E402
from gotne.cassette_node import evaluate_node  # noqa: E402
from gotne.cassette_slot_ledger import (  # noqa: E402
    LEDGER_DOCUMENT_TYPE,
    FailureClass,
    NodePresence,
    SlotLedger,
    SlotLedgerRow,
    build_slot_ledger,
    classify_failure,
)
from gotne.cassette_slots import (  # noqa: E402
    SLOT_IDS,
    CassetteSlotBinding,
    SlotAssignment,
    SlotId,
    project_engagement_state,
    slot_binding_hash,
)
from gotne.cassette_state import (  # noqa: E402
    EngagementLabel,
    EvaluationContext,
    TargetContext,
    TargetGeometry,
    issue_state_certificate,
)
from gotne.identity import canonical_form  # noqa: E402
from gotne.status import Status  # noqa: E402
from test_phase2_cassette_budget import budget_cfg  # noqa: E402

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT_DIR / "gotne"
CHAIN_MODULES = ("cassette_frames", "cassette_budget", "cassette_closure", "cassette_node")
#: The caller-side seams. Everything else in the package sits below them and may
#: not import them; among themselves the batch seam may import the ledger seam.
CALLER_SIDE_SEAMS = (
    "cassette_slot_ledger",
    "cassette_candidate_batch",
    "cassette_candidate_priority",
    "demo_candidate_manifest",
)
IDENTITY_R = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
NEAR = {"t1": (0.0, 0.0, 0.0), "t2": (2.0, 0.0, 0.0), "t3": (4.0, 0.0, 0.0)}
FAR = {"t1": (0.0, 0.0, 0.0), "t2": (200.0, 0.0, 0.0), "t3": (400.0, 0.0, 0.0)}

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


def context(sites=None):
    sites = NEAR if sites is None else sites
    return EvaluationContext(
        TargetContext(tuple((t, TargetGeometry(site, IDENTITY_R)) for t, site in sites.items()))
    )


def evaluated(b, sites=None, nodes=("D1", "D2", "D3")):
    """(cfg, state_result, node_results, certificate|None) from the real kernel."""
    cfg, ctx = budget_cfg(), context(sites)
    state = project_engagement_state(b)
    state_result = evaluate_state(state, cfg, cfg.policy, ctx)
    if state_result.status is not Status.VALID:
        return cfg, state_result, (), None
    certificate = issue_state_certificate(state_result, state, cfg, cfg.policy, ctx)
    node_results = tuple(evaluate_node(m, certificate, cfg, cfg.policy) for m in nodes)
    return cfg, state_result, node_results, certificate


# --------------------------------------------------------------------------
# Row order and retention
# --------------------------------------------------------------------------
class RowOrder(unittest.TestCase):
    def test_exactly_three_rows_in_slot_id_order(self):
        b = binding()
        cfg, state_result, node_results, certificate = evaluated(b)
        ledger = build_slot_ledger(b, cfg, state_result, node_results, certificate)
        self.assertEqual(len(ledger.rows), 3)
        self.assertEqual([r.slot for r in ledger.rows], list(SLOT_IDS))
        self.assertEqual([r.module_id for r in ledger.rows], ["D1", "D2", "D3"])
        self.assertEqual([r.cassette_index for r in ledger.rows], [1, 2, 3])
        self.assertEqual(ledger.as_dict()["order"], ["slot_1", "slot_2", "slot_3"])

    def test_row_order_does_not_follow_status_or_reason(self):
        # D1 is INFEASIBLE while D2 and D3 are VALID; the failing row stays first.
        b = binding()
        cfg, state_result, node_results, certificate = evaluated(b)
        ledger = build_slot_ledger(b, cfg, state_result, node_results, certificate)
        classes = [r.failure_class for r in ledger.rows]
        self.assertEqual(
            classes,
            [
                FailureClass.INFEASIBLE_DECLARED_INPUT,
                FailureClass.NOT_VETOED,
                FailureClass.NOT_VETOED,
            ],
        )
        self.assertEqual([r.slot for r in ledger.rows], list(SLOT_IDS), "order is unchanged")

    def test_row_order_is_the_binding_not_the_projected_state(self):
        b = binding(modules=("D3", "D2", "D1"), t1="t3", t3="t1")
        projected = project_engagement_state(b)
        self.assertEqual(
            [a.module_id for a in projected.assignments], ["D1", "D2", "D3"], "state is id-sorted"
        )
        cfg, state_result, node_results, certificate = evaluated(b)
        ledger = build_slot_ledger(b, cfg, state_result, node_results, certificate)
        self.assertEqual([r.module_id for r in ledger.rows], ["D3", "D2", "D1"])
        self.assertEqual([r.cassette_index for r in ledger.rows], [3, 2, 1])

    def test_unengaged_slot_keeps_an_explicit_row(self):
        b = binding(t2=None)
        cfg, state_result, node_results, certificate = evaluated(b, nodes=("D1", "D3"))
        ledger = build_slot_ledger(b, cfg, state_result, node_results, certificate)
        self.assertEqual(len(ledger.rows), 3, "an UNENGAGED slot is never omitted")
        row = ledger.rows[1]
        self.assertEqual((row.slot, row.module_id, row.label), (SlotId.SLOT_2, "D2", UNENGAGED))
        self.assertIsNone(row.target_id)
        self.assertIs(row.node_presence, NodePresence.ABSENT_UNENGAGED)
        self.assertEqual(
            (row.node_object_id, row.node_result_id, row.node_status, row.node_status_reason),
            (None, None, None, None),
        )

    def test_an_engaged_slot_without_a_node_result_is_named_not_omitted(self):
        b = binding()
        cfg, state_result, node_results, certificate = evaluated(b, nodes=("D1", "D2"))
        ledger = build_slot_ledger(b, cfg, state_result, node_results, certificate)
        self.assertEqual(len(ledger.rows), 3)
        self.assertIs(ledger.rows[2].node_presence, NodePresence.ABSENT_NOT_SUPPLIED)
        self.assertIs(ledger.rows[2].label, ENGAGED)

    def test_a_ledger_cannot_be_built_out_of_slot_order(self):
        b = binding()
        cfg, state_result, node_results, certificate = evaluated(b)
        ledger = build_slot_ledger(b, cfg, state_result, node_results, certificate)
        with self.assertRaises(ValueError):
            SlotLedger(
                rows=tuple(reversed(ledger.rows)),
                slot_binding_hash=ledger.slot_binding_hash,
                state_result_id=ledger.state_result_id,
                config_identity_hash=ledger.config_identity_hash,
                context_hash=ledger.context_hash,
                certificate_present=ledger.certificate_present,
            )
        with self.assertRaises(ValueError):
            SlotLedger(ledger.rows[:2], "h", None, None, None, False)


# --------------------------------------------------------------------------
# Field mapping and failure classes
# --------------------------------------------------------------------------
class FieldMapping(unittest.TestCase):
    def test_state_and_node_fields_are_copied_verbatim(self):
        b = binding()
        cfg, state_result, node_results, certificate = evaluated(b)
        ledger = build_slot_ledger(b, cfg, state_result, node_results, certificate)
        by_module = {n.object_id: n for n in node_results}
        for row in ledger.rows:
            with self.subTest(slot=row.slot.value):
                self.assertEqual(row.state_result_id, state_result.result_id)
                self.assertIs(row.state_status, state_result.status)
                self.assertEqual(row.state_status_reason, state_result.status_reason)
                node = by_module[row.module_id]
                self.assertIs(row.node_presence, NodePresence.PRESENT)
                self.assertEqual(row.node_object_id, node.object_id)
                self.assertEqual(row.node_result_id, node.result_id)
                self.assertIs(row.node_status, node.status)
                self.assertEqual(row.node_status_reason, node.status_reason)

    def test_header_carries_the_binding_identities(self):
        b = binding()
        cfg, state_result, node_results, certificate = evaluated(b)
        ledger = build_slot_ledger(b, cfg, state_result, node_results, certificate)
        self.assertEqual(ledger.slot_binding_hash, slot_binding_hash(b))
        self.assertEqual(ledger.state_result_id, state_result.result_id)
        self.assertEqual(ledger.config_identity_hash, certificate.config_identity_hash)
        self.assertEqual(ledger.context_hash, certificate.context_hash)
        self.assertTrue(ledger.certificate_present)

    def test_without_a_certificate_the_hashes_are_explicitly_absent(self):
        b = binding()
        cfg, state_result, node_results, certificate = evaluated(b, sites=FAR)
        self.assertIs(state_result.status, Status.UNREACHABLE)
        self.assertIsNone(certificate)
        ledger = build_slot_ledger(b, cfg, state_result, node_results, certificate)
        data = ledger.as_dict()
        self.assertFalse(ledger.certificate_present)
        self.assertIsNone(data["config_identity_hash"])
        self.assertIsNone(data["context_hash"])
        self.assertIn("config_identity_hash", data, "absence is a null, never a missing key")
        self.assertIn("context_hash", data)
        self.assertEqual(
            [r.failure_class for r in ledger.rows],
            [FailureClass.UNREACHABLE_GEOMETRIC_VETO] * 3,
        )

    def test_the_four_failure_classes_stay_separable(self):
        self.assertIs(classify_failure(Status.VALID), FailureClass.NOT_VETOED)
        self.assertIs(
            classify_failure(Status.INFEASIBLE), FailureClass.INFEASIBLE_DECLARED_INPUT
        )
        self.assertIs(
            classify_failure(Status.UNREACHABLE), FailureClass.UNREACHABLE_GEOMETRIC_VETO
        )
        self.assertIs(classify_failure(Status.DEGENERATE), FailureClass.UNEVALUABLE)
        self.assertIs(classify_failure(Status.NOT_EVALUATED), FailureClass.UNEVALUABLE)
        self.assertEqual(len(set(FailureClass)), 5, "four classes plus the non-vetoed case")

    def test_a_status_phase2_has_no_source_for_is_refused(self):
        for status in (Status.BLOCKED, Status.NUMERIC_FAILURE, Status.APPROXIMATION_REQUIRED):
            with self.subTest(status=status.value):
                with self.assertRaises(ValueError):
                    classify_failure(status)
        with self.assertRaises(TypeError):
            classify_failure("VALID")

    def test_contract_invalid_is_declared_but_never_produced_from_a_result(self):
        self.assertIn(FailureClass.CONTRACT_INVALID, set(FailureClass))
        self.assertNotIn(FailureClass.CONTRACT_INVALID, set(classify_failure(s) for s in (
            Status.VALID, Status.INFEASIBLE, Status.UNREACHABLE,
            Status.DEGENERATE, Status.NOT_EVALUATED,
        )))


class BuilderRefusals(unittest.TestCase):
    def setUp(self):
        self.binding = binding()
        self.cfg, self.state, self.nodes, self.cert = evaluated(self.binding)

    def test_argument_types(self):
        with self.assertRaises(TypeError):
            build_slot_ledger(self.binding.ordered_assignments(), self.cfg, self.state)
        with self.assertRaises(TypeError):
            build_slot_ledger(self.binding, None, self.state)
        with self.assertRaises(TypeError):
            build_slot_ledger(self.binding, self.cfg, self.cert)
        with self.assertRaises(TypeError):
            build_slot_ledger(self.binding, self.cfg, self.state, node_results=self.nodes[0])
        with self.assertRaises(TypeError):
            build_slot_ledger(self.binding, self.cfg, self.state, self.nodes, certificate=object())

    def test_object_kinds_and_node_membership(self):
        with self.assertRaises(ValueError):
            build_slot_ledger(self.binding, self.cfg, self.nodes[0])  # a NODE as the STATE
        with self.assertRaises(ValueError):
            build_slot_ledger(self.binding, self.cfg, self.state, (self.state,))  # STATE as a node
        with self.assertRaises(ValueError):
            build_slot_ledger(self.binding, self.cfg, self.state, self.nodes + self.nodes[:1])
        with self.assertRaises(ValueError):
            build_slot_ledger(self.binding, self.cfg, self.state, (self.nodes[0], self.nodes[0]))

    def test_a_certificate_must_belong_to_the_state_result(self):
        other_cfg, other_state, _, other_cert = evaluated(binding(t2=None), nodes=("D1",))
        self.assertNotEqual(other_state.result_id, self.state.result_id)
        with self.assertRaises(ValueError):
            build_slot_ledger(self.binding, self.cfg, self.state, self.nodes, other_cert)

    def test_a_module_outside_the_cassette_is_refused(self):
        stray = binding(modules=("D1", "D2", "DX"))
        with self.assertRaises(ValueError):
            build_slot_ledger(stray, self.cfg, self.state)


# --------------------------------------------------------------------------
# Serialization and read-only behaviour
# --------------------------------------------------------------------------
class Serialization(unittest.TestCase):
    def test_canonical_bytes_are_deterministic_and_keep_row_order(self):
        b = binding()
        cfg, state_result, node_results, certificate = evaluated(b)
        first = build_slot_ledger(b, cfg, state_result, node_results, certificate)
        second = build_slot_ledger(b, cfg, state_result, node_results, certificate)
        self.assertEqual(first.to_json_bytes(), second.to_json_bytes())
        data = json.loads(first.to_json_bytes())
        self.assertEqual(data["document_type"], LEDGER_DOCUMENT_TYPE)
        self.assertEqual([r["slot"] for r in data["rows"]], ["slot_1", "slot_2", "slot_3"])
        self.assertEqual(data["order"], [s.value for s in SLOT_IDS])
        # sort_keys touches object keys only, never the rows array.
        self.assertEqual(list(data["rows"][0]), sorted(data["rows"][0]))

    def test_every_required_row_field_is_present(self):
        b = binding(t2=None)
        cfg, state_result, node_results, certificate = evaluated(b, nodes=("D1", "D3"))
        row = build_slot_ledger(b, cfg, state_result, node_results, certificate).rows[0].as_dict()
        self.assertEqual(
            sorted(row),
            sorted(
                [
                    "slot", "module_id", "label", "target_id", "cassette_index",
                    "failure_class", "state_result_id", "state_status", "state_status_reason",
                    "node_presence", "node_object_id", "node_result_id", "node_status",
                    "node_status_reason",
                ]
            ),
        )

    def test_rows_and_ledger_are_frozen(self):
        b = binding()
        cfg, state_result, node_results, certificate = evaluated(b)
        ledger = build_slot_ledger(b, cfg, state_result, node_results, certificate)
        with self.assertRaises(FrozenInstanceError):
            ledger.state_result_id = "x"
        with self.assertRaises(FrozenInstanceError):
            ledger.rows[0].module_id = "x"
        self.assertIsInstance(ledger.rows[0], SlotLedgerRow)


class ReadOnly(unittest.TestCase):
    def test_building_mutates_no_input_and_changes_no_identifier(self):
        b = binding()
        cfg, state_result, node_results, certificate = evaluated(b)
        before = {
            "binding": canonical_form(b),
            "cfg": canonical_form(cfg),
            "state": json.dumps(state_result.as_dict(), sort_keys=True, allow_nan=False),
            "nodes": [json.dumps(n.as_dict(), sort_keys=True, allow_nan=False) for n in node_results],
        }
        state_id, node_ids = state_result.result_id, [n.result_id for n in node_results]
        binding_hash = slot_binding_hash(b)

        build_slot_ledger(b, cfg, state_result, node_results, certificate)

        self.assertEqual(canonical_form(b), before["binding"])
        self.assertEqual(canonical_form(cfg), before["cfg"])
        self.assertEqual(
            json.dumps(state_result.as_dict(), sort_keys=True, allow_nan=False), before["state"]
        )
        self.assertEqual(
            [json.dumps(n.as_dict(), sort_keys=True, allow_nan=False) for n in node_results],
            before["nodes"],
        )
        self.assertEqual(state_result.result_id, state_id)
        self.assertEqual([n.result_id for n in node_results], node_ids)
        self.assertEqual(slot_binding_hash(b), binding_hash)
        self.assertEqual(certificate.config_identity_hash, certificate.config_identity_hash)


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
                if node.level:
                    if node.module:
                        names.add(node.module.split(".")[-1])
                    names.update(a.name for a in node.names)
                elif node.module and node.module.startswith("gotne"):
                    names.add(node.module.split(".")[-1])
                    names.update(a.name for a in node.names)
        return names

    def test_static_closure_reaches_no_chain_module(self):
        seen, queue = set(), ["cassette_slot_ledger"]
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
        self.assertIn("cassette_slots", seen, "the closure scan actually walked the sources")

    def test_no_module_below_the_ledger_imports_a_caller_side_seam(self):
        """The evaluation chain carries no upward dependency.

        Every package module except the declared caller-side seams -- the whole
        chain, the layers under it, cassette_slots and __init__, which would be
        exporting a seam -- must import neither the ledger nor the batch nor the
        priority layer. The sweep stays over the whole directory, so a module
        added later is covered without editing this test; only the declared
        seams in CALLER_SIDE_SEAMS are exempt, and each one is exempt because a
        sibling test pins the edge it is allowed to carry. Scenario comparison
        has only the two reporting edges checked below; it is not broadly
        exempt from this sweep. The priority boundary pins their exact symbols.
        """
        swept = []
        for path in sorted(PACKAGE_DIR.glob("*.py")):
            if path.stem in CALLER_SIDE_SEAMS:
                continue
            swept.append(path.stem)
            imported = self._imported_gotne_modules(path.read_text())
            for seam in CALLER_SIDE_SEAMS:
                if path.stem == "cassette_scenario_comparison" and seam in (
                    "cassette_candidate_batch", "cassette_candidate_priority"
                ):
                    continue
                self.assertNotIn(seam, imported, f"{path.stem} imports {seam}")
        for name in CHAIN_MODULES + ("cassette_slots", "cassette_state", "__init__"):
            self.assertIn(name, swept, "the sweep must cover the chain and the layers below it")

    def test_the_batch_seam_may_import_the_ledger_seam(self):
        """The one exempt edge, pinned so the exemption cannot go stale.

        cassette_candidate_batch is required to construct the existing SlotLedger,
        so it is excluded from the sweep above for a reason this asserts.
        """
        imported = self._imported_gotne_modules(
            (PACKAGE_DIR / "cassette_candidate_batch.py").read_text()
        )
        self.assertIn("cassette_slot_ledger", imported)
        self.assertNotIn(
            "cassette_candidate_batch",
            self._imported_gotne_modules((PACKAGE_DIR / "cassette_slot_ledger.py").read_text()),
            "the dependency between the seams runs one way only",
        )


if __name__ == "__main__":
    unittest.main()
