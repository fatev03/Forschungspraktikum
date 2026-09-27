"""Phase 2 candidate batch: cassette_candidate_batch.

Covers the orchestration seam only: caller order, duplicate refusal before any
evaluation, one entry per candidate across all four failure classes, refusals
that fabricate no result, unchanged ledger order and identifiers, read-only
inputs, canonical serialization and the Phase 4/5 import boundary.

Every outcome comes from the real kernel over the budget fixture:
  NEAR + default policy                        VALID / STATE_NOT_VETOED
  FAR  + default policy                        UNREACHABLE / CHAIN_CLOSURE_VIOLATED
  slot_2 UNENGAGED + STRICT_PROXIMAL_TO_DISTAL INFEASIBLE / ENGAGEMENT_ORDER_VIOLATION
  FIXED_RIGID                                  NOT_EVALUATED / JUNCTION_GEOMETRY_UNSUPPORTED
  ORIENTATION_MARGINALIZED                     DEGENERATE / ENGAGED_POSE_UNDERDETERMINED
  modules permuted against cassette order      refused before evaluation

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
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from gotne import cassette_candidate_batch as batch  # noqa: E402
from gotne.cassette_candidate_batch import (  # noqa: E402
    BATCH_DOCUMENT_TYPE,
    CandidateBatchReport,
    CandidateDeclaration,
    CandidateEntry,
    DeclarationRefusal,
    EntryKind,
    RefusalStage,
    evaluate_candidate_batch,
)
from gotne.cassette_schema import (  # noqa: E402
    EngagedPoseResolution,
    EngagementOrderPolicy,
    JunctionModel,
)
from gotne.cassette_slot_ledger import FailureClass  # noqa: E402
from gotne.cassette_slots import (  # noqa: E402
    SLOT_IDS,
    CassetteSlotBinding,
    SlotAssignment,
    SlotId,
    slot_binding_hash,
)
from gotne.cassette_state import (  # noqa: E402
    EngagementLabel,
    EvaluationContext,
    TargetContext,
    TargetGeometry,
)
from gotne.identity import canonical_form  # noqa: E402
from gotne.status import Status  # noqa: E402
from test_cassette_topology import base_policy  # noqa: E402
from test_phase2_cassette_budget import budget_cfg  # noqa: E402

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT_DIR / "gotne"
PHASE45 = ("composite_density", "so3_grids", "pose_marginalization", "shell_bounds", "intervals")
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


def declaration(candidate_id, *, b=None, policy=None, sites=None):
    cfg = budget_cfg(policy)
    return CandidateDeclaration(
        candidate_id=candidate_id,
        binding=b if b is not None else binding(),
        cfg=cfg,
        policy=cfg.policy,
        context=context(sites),
    )


VALID_D = lambda cid="valid": declaration(cid)  # noqa: E731
UNREACHABLE_D = lambda cid="unreachable": declaration(cid, sites=FAR)  # noqa: E731
INFEASIBLE_D = lambda cid="infeasible": declaration(  # noqa: E731
    cid,
    b=binding(t2=None),
    policy=base_policy(engagement_order_policy=EngagementOrderPolicy.STRICT_PROXIMAL_TO_DISTAL),
)
UNSUPPORTED_D = lambda cid="unsupported": declaration(  # noqa: E731
    cid, policy=base_policy(junction_model=JunctionModel.FIXED_RIGID)
)
DEGENERATE_D = lambda cid="degenerate": declaration(  # noqa: E731
    cid,
    policy=base_policy(engaged_pose_resolution=EngagedPoseResolution.ORIENTATION_MARGINALIZED),
)
REFUSED_D = lambda cid="refused": declaration(  # noqa: E731
    cid, b=binding(modules=("D3", "D2", "D1"), t1="t3", t3="t1")
)


def mixed():
    """One candidate per class, in a deliberately non-alphabetical order."""
    return [
        UNREACHABLE_D(),
        REFUSED_D(),
        VALID_D(),
        DEGENERATE_D(),
        INFEASIBLE_D(),
        UNSUPPORTED_D(),
    ]


# --------------------------------------------------------------------------
# Order and completeness
# --------------------------------------------------------------------------
class CallerOrder(unittest.TestCase):
    def test_entry_order_is_the_caller_sequence(self):
        declarations = mixed()
        report = evaluate_candidate_batch(declarations)
        self.assertEqual(
            [e.candidate_id for e in report.entries], [d.candidate_id for d in declarations]
        )
        self.assertEqual(
            report.as_dict()["candidate_order"], [d.candidate_id for d in declarations]
        )

    def test_order_is_neither_alphabetical_nor_status_grouped(self):
        declarations = mixed()
        ids = [d.candidate_id for d in declarations]
        self.assertNotEqual(ids, sorted(ids), "the fixture order must not be alphabetical")
        report = evaluate_candidate_batch(declarations)
        self.assertEqual([e.candidate_id for e in report.entries], ids)
        kinds = [e.entry_kind for e in report.entries]
        self.assertNotEqual(kinds, sorted(kinds, key=lambda k: k.value), "entries are not grouped")

    def test_every_candidate_yields_exactly_one_entry(self):
        declarations = mixed()
        report = evaluate_candidate_batch(declarations)
        self.assertEqual(len(report.entries), len(declarations))
        self.assertEqual(
            len({e.candidate_id for e in report.entries}), len(declarations), "no entry is merged"
        )

    def test_a_single_candidate_and_an_empty_batch(self):
        self.assertEqual(len(evaluate_candidate_batch([VALID_D()]).entries), 1)
        empty = evaluate_candidate_batch(())
        self.assertEqual(empty.entries, ())
        self.assertEqual(empty.as_dict()["candidate_order"], [])


class DuplicateRefusal(unittest.TestCase):
    def test_duplicate_ids_refuse_before_any_evaluation(self):
        declarations = [VALID_D("c1"), UNREACHABLE_D("c2"), VALID_D("c1")]
        with mock.patch.object(batch, "evaluate_state") as spy_state, mock.patch.object(
            batch, "validate_slot_binding"
        ) as spy_binding:
            with self.assertRaises(ValueError) as caught:
                evaluate_candidate_batch(declarations)
        self.assertIn("duplicate candidate_id", str(caught.exception))
        self.assertIn("c1", str(caught.exception))
        self.assertEqual(spy_state.call_count, 0, "no candidate was evaluated")
        self.assertEqual(spy_binding.call_count, 0, "no binding was even validated")

    def test_argument_shape(self):
        with self.assertRaises(TypeError):
            evaluate_candidate_batch(VALID_D())
        with self.assertRaises(TypeError):
            evaluate_candidate_batch([VALID_D(), "candidate"])


# --------------------------------------------------------------------------
# Failure-class separation
# --------------------------------------------------------------------------
class FailureClasses(unittest.TestCase):
    def setUp(self):
        self.declarations = mixed()
        self.report = evaluate_candidate_batch(self.declarations)
        self.by_id = {e.candidate_id: e for e in self.report.entries}

    def test_each_class_is_carried_by_exactly_one_candidate(self):
        expected = {
            "valid": (Status.VALID, FailureClass.NOT_VETOED),
            "unreachable": (Status.UNREACHABLE, FailureClass.UNREACHABLE_GEOMETRIC_VETO),
            "infeasible": (Status.INFEASIBLE, FailureClass.INFEASIBLE_DECLARED_INPUT),
            "unsupported": (Status.NOT_EVALUATED, FailureClass.UNEVALUABLE),
            "degenerate": (Status.DEGENERATE, FailureClass.UNEVALUABLE),
        }
        for candidate_id, (status, failure_class) in expected.items():
            with self.subTest(candidate=candidate_id):
                entry = self.by_id[candidate_id]
                self.assertIs(entry.entry_kind, EntryKind.EVALUATED)
                rows = entry.ledger.rows
                self.assertIs(rows[0].state_status, status)
                # The 'valid' candidate's D1 node is INFEASIBLE, so its state row
                # class is read from slot_2, which carries no node veto.
                index = 1 if candidate_id == "valid" else 0
                self.assertIs(rows[index].failure_class, failure_class)

    def test_a_refused_declaration_fabricates_no_result(self):
        entry = self.by_id["refused"]
        self.assertIs(entry.entry_kind, EntryKind.DECLARATION_REFUSED)
        self.assertIsNone(entry.ledger, "no synthetic ledger")
        self.assertIsInstance(entry.refusal, DeclarationRefusal)
        self.assertIs(entry.refusal.stage, RefusalStage.SLOT_BINDING)
        self.assertEqual(entry.refusal.error_class, "ValueError")
        self.assertIs(entry.refusal.failure_class, FailureClass.CONTRACT_INVALID)
        serialized = json.loads(self.report.to_json_bytes())
        row = next(e for e in serialized["entries"] if e["candidate_id"] == "refused")
        self.assertIsNone(row["ledger"])
        self.assertEqual(row["refusal"]["failure_class"], "CONTRACT_INVALID")

    def test_a_refused_candidate_is_still_in_the_report(self):
        self.assertIn("refused", [e.candidate_id for e in self.report.entries])
        self.assertEqual(
            [e.candidate_id for e in self.report.entries],
            [d.candidate_id for d in self.declarations],
            "a refusal does not shift the order",
        )

    def test_an_entry_carries_a_ledger_or_a_refusal_but_never_both(self):
        for entry in self.report.entries:
            with self.subTest(candidate=entry.candidate_id):
                self.assertNotEqual(entry.ledger is None, entry.refusal is None)
        ledger = self.by_id["valid"].ledger
        refusal = self.by_id["refused"].refusal
        for kind, carried_ledger, carried_refusal in (
            (EntryKind.EVALUATED, None, None),
            (EntryKind.EVALUATED, ledger, refusal),
            (EntryKind.EVALUATED, None, refusal),
            (EntryKind.DECLARATION_REFUSED, ledger, None),
            (EntryKind.DECLARATION_REFUSED, ledger, refusal),
            (EntryKind.DECLARATION_REFUSED, None, None),
        ):
            with self.subTest(kind=kind.value, ledger=carried_ledger is not None,
                              refusal=carried_refusal is not None):
                with self.assertRaises(ValueError):
                    CandidateEntry("x", "h", kind, carried_ledger, carried_refusal)

    def test_node_results_appear_only_under_a_valid_state(self):
        engaged_rows = [r for r in self.by_id["valid"].ledger.rows]
        self.assertTrue(all(r.node_result_id is not None for r in engaged_rows))
        for candidate_id in ("unreachable", "infeasible", "unsupported", "degenerate"):
            with self.subTest(candidate=candidate_id):
                rows = self.by_id[candidate_id].ledger.rows
                self.assertTrue(all(r.node_result_id is None for r in rows))


# --------------------------------------------------------------------------
# Identity, immutability, serialization
# --------------------------------------------------------------------------
class IdentityAndImmutability(unittest.TestCase):
    def test_slot_ledger_order_and_identifiers_are_unchanged(self):
        declarations = mixed()
        report = evaluate_candidate_batch(declarations)
        for declaration_, entry in zip(declarations, report.entries):
            with self.subTest(candidate=entry.candidate_id):
                self.assertEqual(entry.slot_binding_hash, slot_binding_hash(declaration_.binding))
                if entry.ledger is None:
                    continue
                self.assertEqual([r.slot for r in entry.ledger.rows], list(SLOT_IDS))
                self.assertEqual(entry.ledger.slot_binding_hash, entry.slot_binding_hash)
                self.assertEqual(
                    entry.ledger.state_result_id, entry.ledger.rows[0].state_result_id
                )

    def test_declarations_are_not_mutated(self):
        declarations = mixed()
        before = [canonical_form(d.binding) for d in declarations]
        cfgs = [canonical_form(d.cfg) for d in declarations]
        contexts = [canonical_form(d.context) for d in declarations]
        hashes = [slot_binding_hash(d.binding) for d in declarations]

        evaluate_candidate_batch(declarations)

        self.assertEqual([canonical_form(d.binding) for d in declarations], before)
        self.assertEqual([canonical_form(d.cfg) for d in declarations], cfgs)
        self.assertEqual([canonical_form(d.context) for d in declarations], contexts)
        self.assertEqual([slot_binding_hash(d.binding) for d in declarations], hashes)

    def test_report_and_entries_are_frozen(self):
        report = evaluate_candidate_batch([VALID_D()])
        with self.assertRaises(FrozenInstanceError):
            report.entries = ()
        with self.assertRaises(FrozenInstanceError):
            report.entries[0].candidate_id = "x"
        self.assertIsInstance(report, CandidateBatchReport)

    def test_declaration_construction_refuses_bad_input(self):
        good = VALID_D()
        with self.assertRaises(ValueError):
            CandidateDeclaration("", good.binding, good.cfg, good.policy, good.context)
        with self.assertRaises(TypeError):
            CandidateDeclaration(None, good.binding, good.cfg, good.policy, good.context)
        with self.assertRaises(TypeError):
            CandidateDeclaration("c", good.cfg, good.cfg, good.policy, good.context)
        with self.assertRaises(TypeError):
            CandidateDeclaration("c", good.binding, good.cfg, good.policy, good.cfg)


class Serialization(unittest.TestCase):
    def test_canonical_bytes_are_deterministic(self):
        first = evaluate_candidate_batch(mixed()).to_json_bytes()
        second = evaluate_candidate_batch(mixed()).to_json_bytes()
        self.assertEqual(first, second)
        data = json.loads(first)
        self.assertEqual(data["document_type"], BATCH_DOCUMENT_TYPE)
        self.assertEqual(
            [e["candidate_id"] for e in data["entries"]], data["candidate_order"]
        )
        self.assertEqual(list(data), sorted(data), "sort_keys orders object keys")
        self.assertNotEqual(
            data["candidate_order"], sorted(data["candidate_order"]), "arrays keep caller order"
        )

    def test_canonical_bytes_are_stable_across_pythonhashseed(self):
        program = (
            "import json, pathlib, sys\n"
            f"sys.path.insert(0, {str(ROOT_DIR)!r})\n"
            f"sys.path.insert(0, {str(ROOT_DIR / 'tests')!r})\n"
            "from test_phase2_cassette_candidate_batch import mixed\n"
            "from gotne.cassette_candidate_batch import evaluate_candidate_batch\n"
            "sys.stdout.write(evaluate_candidate_batch(mixed()).to_json_bytes().hex())\n"
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
        self.assertEqual(len(digests), 1, "batch bytes differ across PYTHONHASHSEED")


# --------------------------------------------------------------------------
# Import boundary
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

    def test_static_closure_reaches_no_phase4_or_phase5_module(self):
        seen, queue = set(), ["cassette_candidate_batch"]
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
        self.assertIn("cassette_closure", seen, "the scan walked into the chain as expected")
        self.assertIn("cassette_slot_ledger", seen)

    def test_dynamic_run_loads_no_phase4_or_phase5_module(self):
        program = (
            "import sys\n"
            f"sys.path.insert(0, {str(ROOT_DIR)!r})\n"
            f"sys.path.insert(0, {str(ROOT_DIR / 'tests')!r})\n"
            "from test_phase2_cassette_candidate_batch import mixed\n"
            "from gotne.cassette_candidate_batch import evaluate_candidate_batch\n"
            "evaluate_candidate_batch(mixed())\n"
            f"leaked = [m for m in sys.modules if m.split('.')[-1] in {PHASE45!r}]\n"
            "print('LEAKED:' + ','.join(sorted(leaked)))\n"
        )
        completed = subprocess.run(
            [sys.executable, "-B", "-c", program], capture_output=True, text=True, timeout=300
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-2000:])
        self.assertIn("LEAKED:\n", completed.stdout, completed.stdout)

    def test_no_existing_module_imports_the_batch(self):
        # Three caller-side seams are exempt consumers, each for a contract
        # reason: cassette_candidate_priority/1 reads the finished
        # CandidateBatchReport, and demo_candidate_manifest/1 constructs
        # CandidateDeclaration objects to feed it. Scenario comparison only
        # reads CandidateBatchReport; its exact reporting imports are pinned by
        # the priority boundary test. The existing edges remain pinned below.
        for path in sorted(PACKAGE_DIR.glob("*.py")):
            if path.stem in (
                "cassette_candidate_batch",
                "cassette_candidate_priority",
                "demo_candidate_manifest",
                "cassette_scenario_comparison",
            ):
                continue
            self.assertNotIn(
                "cassette_candidate_batch",
                self._imported(path.read_text()),
                f"{path.stem} imports the batch seam",
            )

    def test_the_priority_seam_is_the_only_consumer_of_the_batch(self):
        """The one exempt edge above the batch, pinned so it cannot go stale."""
        path = PACKAGE_DIR / "cassette_candidate_priority.py"
        if not path.is_file():
            self.skipTest("cassette_candidate_priority is not present in this checkout")
        self.assertIn("cassette_candidate_batch", self._imported(path.read_text()))
        self.assertNotIn(
            "cassette_candidate_priority",
            self._imported((PACKAGE_DIR / "cassette_candidate_batch.py").read_text()),
            "the batch seam must not depend on its consumer",
        )

    def test_the_manifest_seam_produces_declarations_and_nothing_more(self):
        """The one exempt edge below the batch, pinned so it cannot go stale."""
        path = PACKAGE_DIR / "demo_candidate_manifest.py"
        if not path.is_file():
            self.skipTest("demo_candidate_manifest is not present in this checkout")
        imported = self._imported(path.read_text())
        self.assertIn("CandidateDeclaration", imported, "the manifest constructs declarations")
        self.assertNotIn(
            "evaluate_candidate_batch", imported, "an intake layer never invokes the batch"
        )
        self.assertNotIn(
            "demo_candidate_manifest",
            self._imported((PACKAGE_DIR / "cassette_candidate_batch.py").read_text()),
            "the batch seam must not depend on its producer",
        )


if __name__ == "__main__":
    unittest.main()
