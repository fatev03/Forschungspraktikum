"""Pins the publication-lanes section of diffusion_fixed.ipynb; the notebook is only read.

The value-flow and publication-lanes code cells run unmodified, in notebook order, in one
namespace inside one fresh isolated interpreter (sys.executable -I -B) whose working
directory is the repository root. Only the acceptance-visible structure is pinned: cell
ids and types, the six passed checks and the ledger's lane/document/status order. Ids,
byte lengths and path text are not pinned.
"""
import ast
import functools
import json
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import unittest

from structure_audit.alignment_publication import CARRIED_FIELDS

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "diffusion_fixed.ipynb"
TAIL = (("vf-demo-00-section", "markdown"), ("vf-demo-01-load", "code"), ("vf-demo-02-transfer", "code"),
        ("vf-demo-03-assert", "code"), ("pub-lanes-00-section", "markdown"),
        ("pub-lanes-01-inputs", "code"), ("pub-lanes-02-envelopes", "code"),
        ("pub-lanes-03-handoffs", "code"), ("pub-lanes-04-ledger-section", "markdown"),
        ("pub-lanes-04-ledger", "code"), ("pub-lanes-05-checks", "code"))
EXECUTED_PREFIXES = ("vf-demo-", "pub-lanes-")
CHECKS = ["repeated serialization", "reload and reserialize", "handoff linkage",
          "distinct status categories", "blocked and unavailable states", "no absolute runtime path"]
LEDGER_HEADER = ["lane", "document", "status", "reason", "id", "bytes"]
LEDGER = ([("value-flow", "value_flow_demo_summary/1", s) for s in ("ACCEPTED", "UNAVAILABLE", "REJECTED")]
          + [("alignment", "alignment_evidence_envelope/1", s)
             for s in ("AVAILABLE", "UNAVAILABLE", "UNSUPPORTED", "REJECTED")]
          + [("alignment", "alignment_handoff_record/1", s) for s in ("READY", "BLOCKED", "UNAVAILABLE")])
HEX64 = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])")
MARK = "::notebook-runner::"

# Runs inside the subprocess: executes each (cell id, source) pair unmodified in one namespace
# and reports, around every cell, which top-level names that cell introduced.
RUNNER = r'''
import json, sys
MARK = "::notebook-runner::"
sys.stdout.reconfigure(encoding="utf-8")
namespace = {"__name__": "__main__"}
for cell_id, source in json.loads(sys.stdin.buffer.read().decode("utf-8")):
    before = set(namespace)
    print(MARK + json.dumps({"start": cell_id}), flush=True)
    exec(compile(source, cell_id, "exec"), namespace)
    print(MARK + json.dumps({"end": cell_id, "new_names": sorted(set(namespace) - before)}), flush=True)
'''


def notebook_cells():
    return json.loads(NOTEBOOK.read_bytes())["cells"]


def cell_id(cell):
    return cell.get("metadata", {}).get("id")


def source_of(cell):
    return "".join(cell["source"])


def executed_cells():
    return [(cell_id(c), source_of(c)) for c in notebook_cells()
            if c["cell_type"] == "code" and str(cell_id(c)).startswith(EXECUTED_PREFIXES)]


@functools.lru_cache(maxsize=None)
def run_section():
    """One fresh isolated interpreter per test process; returns
    (returncode, stderr, {cell id: output lines}, {cell id: new names})."""
    completed = subprocess.run([sys.executable, "-I", "-B", "-c", RUNNER], cwd=ROOT,
                               input=json.dumps(executed_cells()).encode("ascii"),
                               capture_output=True, timeout=300)
    output, new_names, current = {}, {}, None
    for line in completed.stdout.decode("utf-8").splitlines():
        if line.startswith(MARK):
            event = json.loads(line[len(MARK):])
            if "start" in event:
                current = event["start"]
                output[current] = []
            else:
                new_names[event["end"]] = event["new_names"]
        elif current is not None:
            output[current].append(line)
    return completed.returncode, completed.stderr.decode("utf-8", "replace"), output, new_names


def absolute_path_literals(source):
    """String literals (including f-string fragments) naming an absolute filesystem path.

    A JSON Pointer declared by alignment_publication.CARRIED_FIELDS is a contract key, not a path.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for token in node.value.split():
                token = token.strip("'\"()[]{},")
                if token in CARRIED_FIELDS:
                    continue
                if (re.match(r"/[^/\s]", token) or token.startswith("\\\\")
                        or (PureWindowsPath(token).drive and PureWindowsPath(token).root)):
                    found.append(token)
    return found


class NotebookTailStructure(unittest.TestCase):
    def test_notebook_tail_has_the_eleven_section_cells_in_order(self):
        tail = notebook_cells()[-len(TAIL):]
        self.assertEqual([cell_id(c) for c in tail], [expected for expected, _ in TAIL])

    def test_section_cells_keep_their_types_and_carry_no_outputs(self):
        for cell, (expected_id, expected_type) in zip(notebook_cells()[-len(TAIL):], TAIL):
            with self.subTest(cell=expected_id):
                self.assertEqual(cell["cell_type"], expected_type, f"{expected_id}: cell type changed")
                self.assertIsNone(cell.get("execution_count"), f"{expected_id}: execution_count is not null")
                if expected_type == "code":
                    self.assertIn("execution_count", cell, f"{expected_id}: execution_count field missing")
                    self.assertEqual(cell["outputs"], [], f"{expected_id}: saved outputs present")


class ExecutedSection(unittest.TestCase):
    """Shared access to the single fresh-interpreter run; defines no tests itself."""

    @classmethod
    def setUpClass(cls):
        cls.returncode, cls.stderr, cls.output, cls.new_names = run_section()

    def require_success(self):
        self.assertEqual(self.returncode, 0, "section failed in the fresh interpreter:\n" + self.stderr[-3000:])


class FreshInterpreterExecution(ExecutedSection):
    def test_section_runs_in_a_fresh_isolated_interpreter(self):
        self.require_success()
        self.assertEqual(list(self.output), [cid for cid, _ in executed_cells()],
                         "not every executed cell ran, or cells ran out of notebook order")

    def test_acceptance_cell_prints_the_six_passed_checks(self):
        self.require_success()
        lines = self.output["pub-lanes-05-checks"]
        matches = [re.fullmatch(r"check (.+?) +passed", line) for line in lines]
        self.assertTrue(all(matches), f"pub-lanes-05-checks printed a non-check line: {lines}")
        self.assertEqual([m.group(1) for m in matches], CHECKS)

    def test_ledger_prints_ten_rows_in_fixed_lane_and_status_order(self):
        self.require_success()
        lines = self.output["pub-lanes-04-ledger"]
        self.assertEqual(lines[0].split(), LEDGER_HEADER, "pub-lanes-04-ledger: header changed")
        rows = [tuple(line.split()[:3]) for line in lines[1:]]
        self.assertEqual(rows, LEDGER, "pub-lanes-04-ledger: lane, document or status order changed")


class PublicationLanesHygiene(ExecutedSection):
    def test_publication_lanes_cells_introduce_only_al_prefixed_names(self):
        self.require_success()
        for cid, names in self.new_names.items():
            if not cid.startswith("pub-lanes-"):
                continue
            with self.subTest(cell=cid):
                offending = [n for n in names if not n.startswith("al_")
                             and not (n.startswith("__") and n.endswith("__"))]
                self.assertEqual(offending, [], f"{cid} introduced names without the al_ prefix")

    def test_publication_lanes_cells_contain_no_absolute_path_or_hex_literal(self):
        cells = [(cid, source) for cid, source in executed_cells() if cid.startswith("pub-lanes-")]
        self.assertTrue(cells, "no pub-lanes- code cells found")
        for cid, source in cells:
            with self.subTest(cell=cid):
                self.assertEqual(absolute_path_literals(source), [], f"{cid}: absolute path literal")
                self.assertIsNone(HEX64.search(source), f"{cid}: 64-character hexadecimal literal")
                for text in (str(ROOT), str(Path.home())):
                    self.assertNotIn(text, source, f"{cid}: environment path text")


if __name__ == "__main__":
    unittest.main()
