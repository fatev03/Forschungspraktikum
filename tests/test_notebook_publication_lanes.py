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



CHECKOUT_CELL_ID = "colab-repo-00-checkout-main"
CHECKOUT_URL = "https://github.com/fatev03/Forschungspraktikum.git"
CHECKOUT_BRANCH = "main"
CHECKOUT_PATH = "/content/Forschungspraktikum"
# The eight triage-profile cells are pinned by exact source hash: they must stay byte-for-byte.
TRIAGE_CELL_SHA256 = {
    "triage-profile-00-disclaimer": "5e4ca60827afcccb5e3958a206d6fdcade9ab048fe1babdbd170c715075f3f29",
    "triage-profile-00-assignment": "6d471c6d11d0e632cb0a4c6608a5fdc148c65bf916d0cbc0545903b1d7df2a48",
    "triage-profile-00-section": "6eca1ab992009618dd0b0160052b03317707bdc539f44f18737a4f017775c7a1",
    "triage-profile-01-load": "a795d1279ad9e5bf23a77c0dc27c5500db21c223e0f5225d296e1410c0027306",
    "triage-profile-02-inventory": "10f19ce41ec12b5e24bb206b5ff94a65b9719c60d3f479c460220e52c4579ed4",
    "triage-profile-03-top-candidates": "90eaa4dc1cb35f0285b242970f467bf298202eb7e301cda40718457eab0df9c2",
    "triage-profile-04-dimensions": "0089b53c92ffbf4bf01b9c807ec8ba35396712de68f6baf90abd6f8d73fe4233",
    "triage-profile-05-sources": "02cec459151be899597c3bc34ee96421170cb402063248fe68cc966a8d9984ba",
}
# Operations the checkout cell must not contain. Git-history mutations are matched as quoted
# subcommand arguments so the clone's --branch / --single-branch flags do not trip them.
FORBIDDEN_CHECKOUT_OPS = (
    ("package install", re.compile(r"""\b(?:pip3?|apt(?:-get)?|conda|mamba|poetry)\b|uv\s+pip|!\s*pip""")),
    ("drive mount", re.compile(r"""drive\.mount|google\.colab\s+import\s+drive""")),
    ("git history mutation",
     re.compile(r"""['"](?:commit|push|branch|stash|tag|remote|rebase|reset|clean|cherry-pick|pull)['"]|--force|force-with-lease""")),
    ("source edit", re.compile(r"""\bsed\s+-i\b|open\([^\n]*['"][wa]""")),
    ("provider or docking",
     re.compile(r"""(?i)\b(?:rfdiffusion|run_inference|run_diffusion|colabdesign|pyrosetta|rosetta|autodock|vina|boltz|alphafold|af3)\b""")),
    ("artifact generation", re.compile(r"""files\.(?:download|upload)|\.pdb\b|\.cif\b|outputs/""")),
)


class ColabCheckoutCell(unittest.TestCase):
    """Pins colab-repo-00-checkout-main: the portability cell that makes this repository
    available on branch main before the Section 5 value-flow cells, and pins that the eight
    triage-profile cells and the existing cell order are unchanged by its insertion."""

    def cells(self):
        return notebook_cells()

    def checkout_cell(self, cells):
        found = [c for c in cells if cell_id(c) == CHECKOUT_CELL_ID]
        self.assertEqual(len(found), 1, f"{CHECKOUT_CELL_ID} must appear exactly once")
        return found[0]

    def test_checkout_cell_exists_once_is_code_and_precedes_vf_demo_01_load(self):
        cells = self.cells()
        cell = self.checkout_cell(cells)
        self.assertEqual(cell["cell_type"], "code", "checkout cell must be a code cell")
        ids = [cell_id(c) for c in cells]
        self.assertLess(ids.index(CHECKOUT_CELL_ID), ids.index("vf-demo-01-load"),
                        "checkout cell must precede vf-demo-01-load")

    def test_checkout_cell_is_before_the_pinned_section_anchor(self):
        # Sitting before the SECTION anchor keeps SECTION/PRE_TAIL/TAIL contiguous and in order.
        cells = self.cells()
        ids = [cell_id(c) for c in cells]
        self.assertLess(ids.index(CHECKOUT_CELL_ID), ids.index(SECTION_ANCHOR),
                        "checkout cell must sit before the value-flow section, not inside it")

    def test_checkout_cell_targets_the_repository_url_and_branch_main(self):
        source = source_of(self.checkout_cell(self.cells()))
        self.assertIn(CHECKOUT_URL, source, "checkout cell must target the repository URL")
        self.assertIn('"main"', source, "checkout cell must name branch main as a literal")
        self.assertIn("--branch", source, "checkout cell must clone with an explicit --branch")
        self.assertNotIn("--depth", source, "checkout cell must not pin history depth")

    def test_checkout_cell_defines_the_checkout_location_and_vf_repo_root(self):
        source = source_of(self.checkout_cell(self.cells()))
        self.assertIn(CHECKOUT_PATH, source, "checkout cell must use the /content checkout path")
        self.assertIn("VF_REPO_ROOT", source, "checkout cell must set VF_REPO_ROOT")
        self.assertIn("os.chdir", source, "checkout cell must change into the checkout root")
        self.assertIn("--ff-only", source, "checkout cell must update fast-forward-only")

    def test_checkout_cell_pins_no_commit_sha(self):
        source = source_of(self.checkout_cell(self.cells()))
        self.assertIsNone(HEX64.search(source), "checkout cell must not pin a commit SHA")

    def test_checkout_cell_contains_no_forbidden_operation(self):
        source = source_of(self.checkout_cell(self.cells()))
        for label, pattern in FORBIDDEN_CHECKOUT_OPS:
            with self.subTest(op=label):
                self.assertIsNone(pattern.search(source), f"checkout cell contains a {label} operation")

    def test_checkout_cell_is_valid_python(self):
        ast.parse(source_of(self.checkout_cell(self.cells())))

    def test_triage_profile_cells_are_unchanged_byte_for_byte(self):
        import hashlib
        by_id = {cell_id(c): c for c in self.cells()}
        for cid, expected in TRIAGE_CELL_SHA256.items():
            with self.subTest(cell=cid):
                self.assertIn(cid, by_id, f"{cid} missing from the notebook")
                digest = hashlib.sha256(source_of(by_id[cid]).encode("utf-8")).hexdigest()
                self.assertEqual(digest, expected, f"{cid} source changed")


if __name__ == "__main__":
    unittest.main()
