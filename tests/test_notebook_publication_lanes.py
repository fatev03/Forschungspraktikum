"""Pins the publication-lanes section of diffusion_fixed.ipynb; the notebook is only read.

The pinned structure has three parts, contiguous and in this order. SECTION is the
eleven-cell value-flow and publication-lanes block; it is located by its unique
``vf-demo-00-section`` anchor and pinned as a contiguous, in-order run, because it sits in
the middle of the notebook and later sections are inserted after it. PRE_TAIL is the
read-only collection, artifact-pack and combinations-table block, whose cell ids and sources
are owned by the three structure_audit modules that publish them. TAIL is the notebook's
actual final block — the optional external-reference section, the synthetic scenario
demonstration with the import-only kernel-bootstrap cell that opens it, and the original
Colab appendix — which is intentional published content and is pinned at the notebook end.
PRE_TAIL begins immediately after SECTION and TAIL immediately after PRE_TAIL.

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
SECTION = (("vf-demo-00-section", "markdown"), ("vf-demo-01-load", "code"), ("vf-demo-02-transfer", "code"),
           ("vf-demo-03-assert", "code"), ("pub-lanes-00-section", "markdown"),
           ("pub-lanes-01-inputs", "code"), ("pub-lanes-02-envelopes", "code"),
           ("pub-lanes-03-handoffs", "code"), ("pub-lanes-04-ledger-section", "markdown"),
           ("pub-lanes-04-ledger", "code"), ("pub-lanes-05-checks", "code"))
SECTION_ANCHOR = SECTION[0][0]
PRE_TAIL = (("artifact-inventory-00-section", "markdown"), ("artifact-inventory-01-collect", "code"),
            ("artifact-inventory-02-select", "code"), ("artifact-pack-00-section", "markdown"),
            ("artifact-pack-01-render", "code"), ("combinations-table-00-section", "markdown"),
            ("combinations-table-00-input-unavailable", "markdown"),
            ("combinations-table-01-render", "code"))
TAIL = (("vf-external-reference-section", "markdown"), ("vf-external-reference-demo", "code"),
        ("synthetic-demo-scope", "markdown"),
        ("synthetic-demo-00-kernel-bootstrap", "code"), ("synthetic-demo-run", "code"),
        ("synthetic-demo-declarations", "code"), ("synthetic-demo-priority-disclaimer", "markdown"),
        ("synthetic-demo-priority", "code"), ("synthetic-demo-comparison", "code"),
        ("synthetic-demo-conclusion-nonclaim", "markdown"), ("synthetic-demo-conclusion", "code"),
        ("triage-profile-00-disclaimer", "markdown"),
        ("triage-profile-00-assignment", "code"),
        ("triage-profile-00-section", "markdown"), ("triage-profile-01-load", "code"),
        ("triage-profile-02-inventory", "code"), ("triage-profile-03-top-candidates", "code"),
        ("triage-profile-04-dimensions", "code"), ("triage-profile-05-sources", "code"),
        ("DKQXlWEjIOsf", "markdown"))
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


def anchor_indices(cells, target_id):
    """Every index carrying target_id; the tests assert it is unique before slicing."""
    return [index for index, cell in enumerate(cells) if cell_id(cell) == target_id]


def identity_of(cell):
    return (cell_id(cell), cell["cell_type"])


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
    def section_start(self, cells):
        """Index of SECTION's first cell, asserting the anchor identifies exactly one cell."""
        starts = anchor_indices(cells, SECTION_ANCHOR)
        self.assertEqual(len(starts), 1, f"{SECTION_ANCHOR} is not a unique anchor: {starts}")
        return starts[0]

    def test_every_notebook_cell_id_is_present_and_unique(self):
        ids = [cell_id(c) for c in notebook_cells()]
        self.assertNotIn(None, ids, "a notebook cell carries no metadata id")
        duplicates = sorted({cid for cid in ids if ids.count(cid) > 1})
        self.assertEqual(duplicates, [], "duplicate notebook cell ids")

    def test_the_section_block_is_anchored_contiguous_and_in_order(self):
        cells = notebook_cells()
        start = self.section_start(cells)
        block = cells[start:start + len(SECTION)]
        self.assertEqual([identity_of(c) for c in block], list(SECTION),
                         "the publication-lanes block changed at its anchor")

    def test_the_read_only_block_sits_between_the_section_and_the_tail(self):
        cells = notebook_cells()
        start = self.section_start(cells) + len(SECTION)
        block = cells[start:start + len(PRE_TAIL)]
        self.assertEqual([identity_of(c) for c in block], list(PRE_TAIL),
                         "the read-only collection, pack and table block changed")

    def test_the_notebook_ends_with_the_pinned_publication_tail(self):
        cells = notebook_cells()
        self.assertEqual([identity_of(c) for c in cells[-len(TAIL):]], list(TAIL),
                         "the notebook's final cells are no longer the pinned publication tail")
        self.assertEqual(self.section_start(cells) + len(SECTION) + len(PRE_TAIL),
                         len(cells) - len(TAIL),
                         "the three pinned blocks are no longer contiguous in order")

    def test_pinned_cells_keep_their_types_and_carry_no_outputs(self):
        cells = notebook_cells()
        start = self.section_start(cells)
        pinned = (list(zip(cells[start:start + len(SECTION)], SECTION))
                  + list(zip(cells[start + len(SECTION):], PRE_TAIL))
                  + list(zip(cells[-len(TAIL):], TAIL)))
        for cell, (expected_id, expected_type) in pinned:
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
