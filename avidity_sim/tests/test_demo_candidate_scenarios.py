"""Fixed synthetic facade; public GOTNE paths, with no test-helper inputs."""

import ast
import builtins
import importlib.abc
import io
import os
import pathlib
import socket
import sys
import unittest
from contextlib import ExitStack
from dataclasses import FrozenInstanceError, fields
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import demo_candidate_scenarios as demo
import gotne
from gotne.cassette_candidate_priority import (
    EvidenceCoverage, GeometryTier, IneligibilityReason, KNOWN_PROVIDERS,
    PRIORITY_DISPLAY_DISCLAIMER, PRIORITY_NON_CLAIM, render_lines as priority_lines,
)
from gotne.cassette_scenario_comparison import render_lines as comparison_lines
from gotne.cassette_slots import SLOT_IDS
from gotne.demo_candidate_manifest import CombinationSource, Presence


def documents(result):
    """Observe existing serializations without creating a demo status/identity."""
    return (
        tuple(m.to_json_bytes() for m in result.manifests),
        tuple(b.to_json_bytes() for b in result.batch_reports),
        tuple(p.to_json_bytes() for p in result.priority_reports),
        tuple(s.as_dict() for s in result.scenarios),
        result.comparison.as_dict(),
    )


class SyntheticFacade(unittest.TestCase):
    def test_repeated_results_and_rendering_are_identical(self):
        first, second = demo.build_synthetic_demo(), demo.build_synthetic_demo()
        self.assertEqual(documents(first), documents(second))
        self.assertEqual(first.config, second.config)
        self.assertEqual(first.contexts, second.contexts)
        self.assertEqual(demo.render_lines(first), demo.render_lines(first))
        self.assertEqual(demo.render_lines(first), demo.render_lines(second))

    def test_exact_public_path_and_original_report_objects(self):
        events = []

        def observe(name, function):
            def call(*args, **kwargs):
                value = function(*args, **kwargs)
                events.append((name, args, kwargs, value))
                return value
            return call

        functions = ("declare_candidate_manifest", "to_candidate_declarations",
                     "evaluate_candidate_batch", "evaluate_candidate_priority", "compare_scenarios")
        with ExitStack() as stack:
            for name in functions:
                stack.enter_context(patch.object(demo, name, side_effect=observe(name, getattr(demo, name))))
            result = demo.build_synthetic_demo()
        self.assertEqual([e[0] for e in events], list(functions[:4]) * 2 + ["compare_scenarios"])
        for index in range(2):
            manifest, declarations, batch, priority = events[index * 4:index * 4 + 4]
            self.assertIs(manifest[3], result.manifests[index])
            self.assertIs(declarations[1][0], result.manifests[index])
            self.assertIs(declarations[1][1], result.config)
            self.assertIs(declarations[1][2], result.contexts[index])
            self.assertIs(declarations[3], result.candidate_declarations[index])
            self.assertIs(batch[1][0], result.candidate_declarations[index])
            self.assertIs(batch[3], result.batch_reports[index])
            self.assertIs(priority[1][0], result.batch_reports[index])
            self.assertIs(priority[3], result.priority_reports[index])
            self.assertEqual(priority[2], {"evidence": {}, "providers": KNOWN_PROVIDERS})
            snapshot = result.scenarios[index].as_dict()
            self.assertEqual(snapshot["batch_report"], result.batch_reports[index].as_dict())
            self.assertEqual(snapshot["priority_report"], result.priority_reports[index].as_dict())
        self.assertEqual(events[-1][1][0], result.scenarios)
        self.assertIs(events[-1][3], result.comparison)

    def test_fixed_candidate_and_slot_identities_are_preserved(self):
        result = demo.build_synthetic_demo()
        expected_ids = ("z-stable", "a-context-sensitive", "m-excluded")
        expected_targets = (("start", "middle", "end"), ("start", "moving", "end"), ("start", "far", "end"))
        bindings = []
        for manifest, declarations, batch, priority in zip(result.manifests, result.candidate_declarations,
                                                          result.batch_reports, result.priority_reports):
            self.assertIs(manifest.combination_source, CombinationSource.DECLARED_LIST)
            self.assertEqual(tuple(c.candidate_id for c in manifest.combinations), expected_ids)
            self.assertEqual(tuple(c.candidate_id for c in declarations), expected_ids)
            self.assertEqual(tuple(e.candidate_id for e in batch.entries), expected_ids)
            self.assertEqual(priority.candidate_order, expected_ids)
            for candidate, targets in zip(declarations, expected_targets):
                slots = candidate.binding.ordered_assignments()
                self.assertEqual(tuple(s.slot for s in slots), SLOT_IDS)
                self.assertEqual(tuple(s.module_id for s in slots), ("D1", "D2", "D3"))
                self.assertEqual(tuple(s.target_id for s in slots), targets)
            by_id = {m.candidate_id: m for g in priority.groups for m in g.members}
            by_id.update({e.candidate_id: e for e in priority.excluded})
            for entry in batch.entries:
                self.assertEqual(entry.slot_binding_hash, entry.ledger.slot_binding_hash)
                self.assertEqual(entry.slot_binding_hash, by_id[entry.candidate_id].slot_binding_hash)
            bindings.append(tuple(e.slot_binding_hash for e in batch.entries))
        self.assertEqual(bindings[0], bindings[1])
        self.assertEqual(tuple(d.binding for d in result.candidate_declarations[0]),
                         tuple(d.binding for d in result.candidate_declarations[1]))

    def test_two_explicit_contexts_and_run_links(self):
        result = demo.build_synthetic_demo()
        self.assertEqual(tuple(s.scenario_id for s in result.scenarios), ("synthetic-near", "synthetic-shifted"))
        context_hashes = []
        for context, manifest, scenario, declarations, batch in zip(result.contexts, result.manifests,
                result.scenarios, result.candidate_declarations, result.batch_reports):
            self.assertEqual(manifest.scenario_id, scenario.scenario_id)
            self.assertEqual(manifest.primary_context_ref, scenario.evaluation_run_ref)
            for candidate in declarations:
                self.assertIs(candidate.context, context)
            context_hashes.append(batch.entries[0].ledger.context_hash)
        first, second = (dict(ctx.targets.targets) for ctx in result.contexts)
        self.assertEqual(first["moving"].site_nm, (2.0, 0.0, 0.0))
        self.assertEqual(second["moving"].site_nm, (200.0, 0.0, 0.0))
        for label in ("start", "middle", "far", "end"):
            self.assertEqual(first[label], second[label])
        self.assertIsNotNone(context_hashes[0])
        self.assertNotEqual(context_hashes[0], context_hashes[1])
        self.assertNotEqual(result.scenarios[0].evaluation_run_ref, result.scenarios[1].evaluation_run_ref)

    def test_consistently_ranked_changed_and_excluded_cases(self):
        result = demo.build_synthetic_demo()
        near, shifted = result.priority_reports
        self.assertEqual([m.candidate_id for m in near.groups[0].members], ["z-stable", "a-context-sensitive"])
        self.assertEqual([m.candidate_id for m in shifted.groups[0].members], ["z-stable"])
        for priority in result.priority_reports:
            self.assertEqual(priority.groups[0].rank, 1)
            self.assertIs(priority.groups[0].geometry_tier, GeometryTier.T1_ENGAGED_SLOTS_FULLY_RESOLVED)
            for excluded in priority.excluded:
                self.assertIs(excluded.ineligibility_reason, IneligibilityReason.STATE_NOT_VALID)
                self.assertEqual(excluded.state_status_reason, "CHAIN_CLOSURE_VIOLATED")
        self.assertEqual([e.candidate_id for e in near.excluded], ["m-excluded"])
        self.assertEqual([e.candidate_id for e in shifted.excluded], ["a-context-sensitive", "m-excluded"])
        comparison = result.comparison.as_dict()
        self.assertEqual(comparison["ordering_stability"], "UNSTABLE")
        self.assertTrue(comparison["eligibility_changed"])
        self.assertFalse(comparison["stable_top"])
        self.assertEqual(comparison["diagnostics"], [])
        self.assertEqual(comparison["movements"][1]["changes"][0]["kinds"], ["BECAME_EXCLUDED"])
        self.assertEqual(comparison["movements"][2]["changes"][0]["kinds"], ["REMAINED_EXCLUDED"])

    def test_existing_rendered_blocks_and_disclaimers_are_verbatim(self):
        result = demo.build_synthetic_demo()
        lines = demo.render_lines(result)
        text = "\n".join(lines)
        for priority in result.priority_reports:
            self.assertIn("\n".join(priority_lines(priority)), text)
        self.assertIn("\n".join(comparison_lines(result.comparison)), text)
        self.assertEqual(text.count(PRIORITY_NON_CLAIM), 3)
        self.assertEqual(text.count(PRIORITY_DISPLAY_DISCLAIMER), 3)
        self.assertIn(result.comparison.as_dict()["conclusion"], text)
        self.assertIn("excluded  m-excluded", text)
        self.assertIn("no scientific validity or biological prediction claim", text)

    def test_returned_components_are_immutable_and_renderer_does_not_mutate(self):
        result = demo.build_synthetic_demo()
        before = documents(result)
        targets = ((result, "config"), (result.config, "id"), (result.contexts[0], "targets"),
                   (result.manifests[0], "scenario_id"), (result.candidate_declarations[0][0], "candidate_id"),
                   (result.batch_reports[0], "entries"), (result.batch_reports[0].entries[0].ledger, "rows"),
                   (result.priority_reports[0], "groups"), (result.scenarios[0], "scenario_id"),
                   (result.comparison, "_document"))
        for target, attribute in targets:
            with self.subTest(attribute=attribute), self.assertRaises(FrozenInstanceError):
                setattr(target, attribute, None)
        for attribute in ("contexts", "manifests", "candidate_declarations", "batch_reports", "priority_reports", "scenarios"):
            self.assertIsInstance(getattr(result, attribute), tuple)
        result.manifests[0].as_dict()["combinations"].clear()
        result.batch_reports[0].as_dict()["entries"].clear()
        result.priority_reports[0].as_dict()["groups"].clear()
        result.comparison.as_dict()["movements"].clear()
        demo.render_lines(result).clear()
        self.assertEqual(before, documents(result))
        self.assertFalse({"status", "acceptance", "admission", "score", "rank"} & {f.name for f in fields(result)})

    def test_no_io_provider_reader_or_external_intake_invocation(self):
        class ForbidExternalImports(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path, target=None):
                if fullname.split(".")[0] in {"structure_audit", "alphafold3", "af3_red", "requests"}:
                    raise AssertionError(f"external import: {fullname}")
                return None

        guard = ForbidExternalImports()
        sys.meta_path.insert(0, guard)
        try:
            with ExitStack() as stack:
                for owner, name in ((builtins, "open"), (io, "open"), (socket, "socket"),
                                    (os, "listdir"), (os, "scandir")):
                    stack.enter_context(patch.object(owner, name, side_effect=AssertionError(f"forbidden I/O: {name}")))
                result = demo.build_synthetic_demo()
                demo.render_lines(result)
        finally:
            sys.meta_path.remove(guard)
        for priority in result.priority_reports:
            for group in priority.groups:
                for member in group.members:
                    self.assertIs(member.evidence_coverage, EvidenceCoverage.ABSENT)
                    self.assertIsNone(member.evidence)

    def test_static_public_only_imports_and_no_direct_evaluation_or_hashing(self):
        source = pathlib.Path(demo.__file__).read_text()
        tree = ast.parse(source)
        allowed = {"dataclasses", "gotne.cassette_candidate_batch", "gotne.cassette_candidate_priority",
                   "gotne.cassette_scenario_comparison", "gotne.cassette_schema", "gotne.cassette_state",
                   "gotne.demo_candidate_manifest"}
        forbidden_calls = {"evaluate_state", "evaluate_node", "issue_state_certificate", "geometry_tier",
            "ineligibility_reason", "classify_evidence", "slot_binding_hash", "hash", "sha256", "open",
            "CandidateBatchReport", "CandidatePriorityReport", "ScenarioComparisonReport", "build_slot_ledger",
            "sorted", "sort", "setattr", "read_text", "write_text"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.fail("Use explicit public constructors/functions only.")
            elif isinstance(node, ast.ImportFrom):
                self.assertIn(node.module, allowed)
                self.assertTrue(all(not alias.name.startswith("_") for alias in node.names))
            elif isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                self.assertNotIn(name, forbidden_calls)
        for name in demo.__all__:
            self.assertTrue(hasattr(demo, name))

    def test_facade_is_outside_kernel_and_has_no_upstream_importers(self):
        package_dir = pathlib.Path(gotne.__file__).parent.resolve()
        self.assertNotEqual(pathlib.Path(demo.__file__).resolve().parent, package_dir)
        for path in package_dir.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""] + [alias.name for alias in node.names]
                else:
                    continue
                self.assertTrue(all(name.split(".")[-1] != "demo_candidate_scenarios" for name in names), path.name)


if __name__ == "__main__":
    unittest.main()
