"""Phase 2, third seam: cassette_budget (decision record revision 3).

Covers SpanBasis, BudgetElementKind, BudgetElement, BudgetBreakdown,
cassette_contour_budget and closure_span_budget only: the two element sets
(OQ-3, AP-26), §18.2 arithmetic, derived rigid spans (AP-13 as amended), path
membership independent of engagement (N9, N10), fail-closed inputs (OQ-5) and
FIXED_RIGID refusal (OQ-7). Closure and node code does not exist yet.

Fixture lengths are binary-exact so budget sums compare with ==.

Run: python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import json
import math
import pathlib
import sys
import unittest
from dataclasses import FrozenInstanceError, replace
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from gotne import cassette_budget  # noqa: E402
from gotne.cassette_budget import (  # noqa: E402
    BudgetBreakdown,
    BudgetElement,
    BudgetElementKind,
    SpanBasis,
    cassette_contour_budget,
    closure_span_budget,
)
from gotne.cassette_frames import ROOT  # noqa: E402
from gotne.cassette_schema import MISSING, JunctionModel, TopologyMode  # noqa: E402
from gotne.cassette_state import EngagementState, UnsupportedGeometryError  # noqa: E402
from gotne.cassette_topology import validate_cassette_config  # noqa: E402
from gotne.status import Status  # noqa: E402
from test_cassette_topology import base_policy, module, ref_cassette_3  # noqa: E402
from test_phase2_cassette_state import engaged, imported_modules, unengaged  # noqa: E402

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
#: tether id -> (L_min, L)
LENGTHS = {"s0": (0.0, 2.0), "s1": (0.5, 1.5), "s2": (0.25, 1.0)}
SPAN = 1.25  # ||exit - entry|| of D1, D2
CAPTURE = 0.5  # ||capture - entry|| of every module
DERIVED = "rigid_span_basis=DERIVED_FROM_ENTRY_EXIT_OFFSETS"
FIXED_RIGID = base_policy(junction_model=JunctionModel.FIXED_RIGID)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
def budget_cfg(policy=None, modules=None, tethers=None):
    """REF-CASSETTE-3 with lengths and offsets; overrides keyed by id."""
    cfg = ref_cassette_3(policy=policy)
    modules, tethers = modules or {}, tethers or {}
    offsets = dict(entry_offset=(0.0, 0.0, 0.0), exit_offset=(SPAN, 0.0, 0.0), capture_offset_vec=(CAPTURE, 0.0, 0.0))
    terminal = dict(entry_offset=(0.0, 0.0, 0.0), capture_offset_vec=(CAPTURE, 0.0, 0.0), exclusion_centre=(0.5, 0.0, 0.0))
    return replace(
        cfg,
        modules=(
            module("D1", 1, **{**offsets, **modules.get("D1", {})}),
            module("D2", 2, **{**offsets, **modules.get("D2", {})}),
            module("D3", 3, terminal=True, **{**terminal, **modules.get("D3", {})}),
        ),
        tethers=tuple(
            replace(t, **{"L_min": LENGTHS[t.id][0], "L": LENGTHS[t.id][1], **tethers.get(t.id, {})})
            for t in cfg.tethers
        ),
    )


def state(*assignments):
    return EngagementState(assignments)


S13 = state(engaged("D1", "t1"), engaged("D3", "t3"))
S123 = state(engaged("D1", "t1"), engaged("D2", "t2"), engaged("D3", "t3"))


def ids(breakdown):
    return [e.element_id for e in breakdown.elements]


def element(kind, source_id, index, a, b=None, **extra):
    suffix, source_fields, _ = cassette_budget._KIND_LAYOUT[kind]
    return BudgetElement(source_id + suffix, kind, source_id, source_fields, index, a, a if b is None else b, **extra)


class FixtureSanity(unittest.TestCase):
    def test_fixtures_valid_under_phase1c(self):
        for cfg in (budget_cfg(), budget_cfg(FIXED_RIGID), budget_cfg(modules={"D3": {"capture_offset_vec": None}}),
                    budget_cfg(tethers={"s1": {"L": MISSING}}), budget_cfg(modules={"D2": {"entry_offset": MISSING}})):
            self.assertIs(validate_cassette_config(cfg).status, Status.VALID)


# --------------------------------------------------------------------------
# Types
# --------------------------------------------------------------------------
class BudgetTypes(unittest.TestCase):
    def test_enums(self):
        self.assertEqual([m.value for m in SpanBasis], ["DERIVED_FROM_ENTRY_EXIT_OFFSETS"])
        self.assertEqual([m.value for m in BudgetElementKind], ["SEGMENT", "SPAN", "CAPTURE_OFFSET"])

    def test_element_invariants(self):
        span = dict(span_basis=SpanBasis.DERIVED_FROM_ENTRY_EXIT_OFFSETS, derived_rigid_span_nm=1.0)
        good = element(BudgetElementKind.SEGMENT, "s1", 1, 0.5, 1.5)
        cases = {
            "wrong suffix": lambda: replace(good, element_id="s1.span"),
            "wrong source_fields": lambda: replace(good, source_fields=("L", "L_min")),
            "a > b": lambda: replace(good, a_nm=2.0),
            "negative": lambda: replace(good, a_nm=-0.5),
            "non-finite": lambda: replace(good, b_nm=math.inf),
            "int length": lambda: replace(good, b_nm=2),
            "segment with basis": lambda: replace(good, **span),
            "span without basis": lambda: element(BudgetElementKind.SPAN, "D2", 2, 1.0),
            "span derived mismatch": lambda: element(BudgetElementKind.SPAN, "D2", 2, 1.0, 1.0, span_basis=span["span_basis"],
                                                     derived_rigid_span_nm=1.5),
            "capture a != b": lambda: element(BudgetElementKind.CAPTURE_OFFSET, "D3", 3, 0.5, 0.75),
            "module index 0": lambda: element(BudgetElementKind.CAPTURE_OFFSET, "D3", 0, 0.5),
            "kind as string": lambda: replace(good, kind="SEGMENT"),
        }
        for label, build in cases.items():
            with self.subTest(case=label), self.assertRaises((ValueError, TypeError)):
                build()

    def test_breakdown_invariants(self):
        seg = element(BudgetElementKind.SEGMENT, "s2", 2, 0.25, 1.0)
        cap3 = element(BudgetElementKind.CAPTURE_OFFSET, "D3", 3, 0.5)
        cap2 = element(BudgetElementKind.CAPTURE_OFFSET, "D2", 2, 0.5)
        node = dict(module_id="D3", shielding_ancestor="D2", shielding_ancestor_module_cassette_index=2)
        pair = dict(upstream_module_id="D2", downstream_module_id="D3")
        BudgetBreakdown("NODE", (seg, cap3), **node)
        BudgetBreakdown("CLOSURE", (seg,), **pair)
        cases = {
            "node without capture": lambda: BudgetBreakdown("NODE", (seg,), **node),
            "node capture not last": lambda: BudgetBreakdown("NODE", (cap3, seg), **node),
            "node two captures": lambda: BudgetBreakdown("NODE", (cap2, seg, cap3), **node),
            "node capture of another module": lambda: BudgetBreakdown("NODE", (seg, cap2), **node),
            "closure with capture": lambda: BudgetBreakdown("CLOSURE", (seg, cap3), **pair),
            "closure naming a module": lambda: BudgetBreakdown("CLOSURE", (seg,), module_id="D3", **pair),
            "node naming a pair": lambda: BudgetBreakdown("NODE", (seg, cap3), **node, **pair),
            "node ancestor as bare ROOT string": lambda: BudgetBreakdown(
                "NODE", (seg, cap3), module_id="D3", shielding_ancestor="ROOT", shielding_ancestor_module_cassette_index=0),
            "unknown kind": lambda: BudgetBreakdown("PATH", (seg,), **pair),
            "empty": lambda: BudgetBreakdown("CLOSURE", (), **pair),
            "duplicate ids": lambda: BudgetBreakdown("CLOSURE", (seg, seg), **pair),
            "computed field supplied": lambda: BudgetBreakdown("CLOSURE", (seg,), D_max_nm=0.0, **pair),
        }
        for label, build in cases.items():
            with self.subTest(case=label), self.assertRaises((ValueError, TypeError)):
                build()

    def test_immutable(self):
        breakdown = cassette_contour_budget("D3", S13, budget_cfg())
        self.assertIsInstance(breakdown.elements, tuple)
        self.assertIsInstance(breakdown.elements[0].source_fields, tuple)
        for target, name in ((breakdown, "D_max_nm"), (breakdown, "elements"), (breakdown.elements[0], "a_nm")):
            with self.subTest(field=name), self.assertRaises(FrozenInstanceError):
                setattr(target, name, 0.0)

    def test_replace_recomputes_bounds(self):
        breakdown = closure_span_budget("D1", "D3", S13, budget_cfg())
        shorter = replace(breakdown, elements=breakdown.elements[:1])
        self.assertEqual(shorter.D_max_nm, 1.5)
        self.assertEqual(shorter.dominating_element_id, "s1.seg")


# --------------------------------------------------------------------------
# Node budget: capture offset exactly once
# --------------------------------------------------------------------------
class ContourBudget(unittest.TestCase):
    def test_path_through_unengaged_module(self):  # N9, N10
        breakdown = cassette_contour_budget("D3", S13, budget_cfg())
        self.assertEqual(ids(breakdown), ["s1.seg", "D2.span", "s2.seg", "D3.capture"])
        self.assertEqual([e.index for e in breakdown.elements], [1, 2, 2, 3])
        self.assertEqual([(e.a_nm, e.b_nm) for e in breakdown.elements],
                         [(0.5, 1.5), (SPAN, SPAN), (0.25, 1.0), (CAPTURE, CAPTURE)])
        self.assertEqual((breakdown.shielding_ancestor, breakdown.shielding_ancestor_module_cassette_index), ("D1", 1))
        self.assertEqual((breakdown.D_max_nm, breakdown.D_min_nm), (4.25, 0.0))
        self.assertIsNone(breakdown.dominating_element_id)
        self.assertTrue(breakdown.folding_unobstructed)
        self.assertTrue(breakdown.includes_capture_offset)

    def test_capture_offset_exactly_once_and_last(self):
        for st in (S13, S123, state(engaged("D1", "t1")), state(engaged("D2", "t1")), state(engaged("D3", "t1"))):
            for a in st.engaged_assignments():
                with self.subTest(state=[x.module_id for x in st.engaged_assignments()], module=a.module_id):
                    breakdown = cassette_contour_budget(a.module_id, st, budget_cfg())
                    captures = [e for e in breakdown.elements if e.kind is BudgetElementKind.CAPTURE_OFFSET]
                    self.assertEqual([e.element_id for e in captures], [a.module_id + ".capture"])
                    self.assertIs(breakdown.elements[-1], captures[0])

    def test_root_ancestor(self):  # T77 shape
        breakdown = cassette_contour_budget("D1", S13, budget_cfg())
        self.assertEqual(ids(breakdown), ["s0.seg", "D1.capture"])
        self.assertIs(breakdown.shielding_ancestor, ROOT)
        self.assertEqual([e for e in breakdown.elements if e.kind is BudgetElementKind.SPAN], [])
        self.assertEqual(breakdown.as_dict()["shielding_ancestor"], {"kind": "ROOT", "id": None, "module_cassette_index": 0})
        self.assertEqual(ids(cassette_contour_budget("D3", state(engaged("D3", "t3")), budget_cfg())),
                         ["s0.seg", "D1.span", "s1.seg", "D2.span", "s2.seg", "D3.capture"])

    def test_nearest_engaged_ancestor(self):  # AP-18
        breakdown = cassette_contour_budget("D3", S123, budget_cfg())
        self.assertEqual(ids(breakdown), ["s2.seg", "D3.capture"])
        self.assertEqual(breakdown.as_dict()["shielding_ancestor"], {"kind": "MODULE", "id": "D2", "module_cassette_index": 2})

    def test_explicit_unengaged_equals_omitted(self):
        explicit = state(engaged("D1", "t1"), unengaged("D2"), engaged("D3", "t3"))
        self.assertEqual(cassette_contour_budget("D3", explicit, budget_cfg()), cassette_contour_budget("D3", S13, budget_cfg()))

    def test_module_must_be_engaged(self):
        with self.assertRaisesRegex(ValueError, "not ENGAGED"):
            cassette_contour_budget("D2", S13, budget_cfg())


# --------------------------------------------------------------------------
# Path membership (decision record amendment A1): the ancestor is chosen by
# the state (AP-18); the chosen path is then complete (N10).
# --------------------------------------------------------------------------
ORDER = ("D1", "D2", "D3")
#: (ancestor index k, module index j) -> full physical path, written out by hand
NODE_PATHS = {
    (0, 1): ["s0.seg", "D1.capture"],
    (0, 2): ["s0.seg", "D1.span", "s1.seg", "D2.capture"],
    (0, 3): ["s0.seg", "D1.span", "s1.seg", "D2.span", "s2.seg", "D3.capture"],
    (1, 2): ["s1.seg", "D2.capture"],
    (1, 3): ["s1.seg", "D2.span", "s2.seg", "D3.capture"],
    (2, 3): ["s2.seg", "D3.capture"],
}
CLOSURE_PATHS = {(1, 2): ["s1.seg"], (1, 3): ["s1.seg", "D2.span", "s2.seg"], (2, 3): ["s2.seg"]}


def all_states():
    """Every engagement subset, twice: non-engaged modules omitted, and declared UNENGAGED."""
    for mask in range(8):
        chosen = [m for bit, m in enumerate(ORDER) if mask >> bit & 1]
        yield state(*(engaged(m, "t" + m[1]) for m in chosen))
        yield state(*(engaged(m, "t" + m[1]) if m in chosen else unengaged(m) for m in ORDER))


def engaged_indices(st):
    return sorted(ORDER.index(a.module_id) + 1 for a in st.engaged_assignments())


class PathMembership(unittest.TestCase):
    def test_node_budget_is_the_full_path_from_the_chosen_ancestor(self):
        groups = {}
        for st in all_states():
            indices = engaged_indices(st)
            for j in indices:
                k = max((i for i in indices if i < j), default=0)
                breakdown = cassette_contour_budget(ORDER[j - 1], st, budget_cfg())
                with self.subTest(state=[(a.module_id, a.label.value) for a in st.assignments], module=ORDER[j - 1]):
                    self.assertEqual(breakdown.shielding_ancestor_module_cassette_index, k)
                    self.assertEqual(ids(breakdown), NODE_PATHS[(k, j)])
                groups.setdefault((k, j), []).append(breakdown)
        self.assertEqual(set(groups), set(NODE_PATHS))
        for key, breakdowns in groups.items():
            with self.subTest(ancestor_and_module=key):
                self.assertTrue(all(b == breakdowns[0] for b in breakdowns))  # same ancestor, same budget

    def test_t83_5_control_state_must_select_the_same_ancestor(self):
        cfg = budget_cfg()
        base = cassette_contour_budget("D3", S13, cfg)
        same_ancestor = cassette_contour_budget("D3", state(engaged("D1", "t1"), unengaged("D2"), engaged("D3", "t3")), cfg)
        other_ancestor = cassette_contour_budget("D3", S123, cfg)
        self.assertEqual(ids(same_ancestor), ids(base))
        self.assertEqual((base.shielding_ancestor, other_ancestor.shielding_ancestor), ("D1", "D2"))
        self.assertEqual(ids(other_ancestor), NODE_PATHS[(2, 3)])  # AP-18: the path changes with the ancestor
        self.assertNotEqual(ids(other_ancestor), ids(base))

    def test_closure_budget_depends_only_on_the_pair(self):
        groups = {}
        for st in all_states():
            indices = engaged_indices(st)
            for i, j in zip(indices, indices[1:]):
                breakdown = closure_span_budget(ORDER[i - 1], ORDER[j - 1], st, budget_cfg())
                with self.subTest(state=[(a.module_id, a.label.value) for a in st.assignments], pair=(i, j)):
                    self.assertEqual(ids(breakdown), CLOSURE_PATHS[(i, j)])
                groups.setdefault((i, j), []).append(breakdown)
        self.assertEqual(set(groups), set(CLOSURE_PATHS))
        for key, breakdowns in groups.items():
            self.assertTrue(all(b == breakdowns[0] for b in breakdowns), key)


# --------------------------------------------------------------------------
# Closure span: no capture offset
# --------------------------------------------------------------------------
class ClosureSpan(unittest.TestCase):
    def test_exit_to_entry_without_capture(self):
        breakdown = closure_span_budget("D1", "D3", S13, budget_cfg())
        self.assertEqual(ids(breakdown), ["s1.seg", "D2.span", "s2.seg"])
        self.assertFalse(breakdown.includes_capture_offset)
        self.assertEqual([e for e in breakdown.elements if e.kind is BudgetElementKind.CAPTURE_OFFSET], [])
        self.assertEqual((breakdown.D_max_nm, breakdown.D_min_nm), (3.75, 0.0))
        data = breakdown.as_dict()
        self.assertEqual((data["upstream_module_id"], data["downstream_module_id"]), ("D1", "D3"))
        self.assertNotIn("shielding_ancestor", data)
        self.assertNotIn("module_id", data)

    def test_single_element_degenerates_to_its_interval(self):  # §18.2, |E| = 1
        breakdown = closure_span_budget("D1", "D2", S123, budget_cfg())
        self.assertEqual(ids(breakdown), ["s1.seg"])
        self.assertEqual((breakdown.D_min_nm, breakdown.D_max_nm), (0.5, 1.5))
        self.assertEqual(breakdown.dominating_element_id, "s1.seg")
        self.assertFalse(breakdown.folding_unobstructed)

    def test_only_consecutive_engaged_pairs(self):  # N2: never repaired
        for up, down, st in (("D3", "D1", S13), ("D1", "D1", S13), ("D1", "D3", S123), ("D1", "D2", S13),
                             ("D2", "D3", S13)):
            with self.subTest(pair=(up, down)), self.assertRaisesRegex(ValueError, "consecutive ENGAGED pair"):
                closure_span_budget(up, down, st, budget_cfg())
        with self.assertRaisesRegex(ValueError, "not in the cassette"):
            closure_span_budget("D1", "D9", S13, budget_cfg())

    def test_capture_inputs_not_read(self):
        cfg = budget_cfg(modules={"D3": {"capture_offset_vec": None}, "D1": {"capture_offset_vec": MISSING}})
        self.assertEqual(ids(closure_span_budget("D1", "D3", S13, cfg)), ["s1.seg", "D2.span", "s2.seg"])
        with self.assertRaisesRegex(ValueError, r"D3\.capture_offset_vec=NULL"):
            cassette_contour_budget("D3", S13, cfg)


class CaptureContribution(unittest.TestCase):
    def test_budgets_differ_by_exactly_the_capture_offset(self):
        for modules in ({}, {"D2": {"exit_offset": (5.0, 0.0, 0.0)}}, {"D3": {"capture_offset_vec": (0.0, 0.75, 0.0)}}):
            with self.subTest(modules=modules):
                cfg = budget_cfg(modules=modules)
                node = cassette_contour_budget("D3", S13, cfg)
                closure = closure_span_budget("D1", "D3", S13, cfg)
                self.assertEqual(node.elements[:-1], closure.elements)
                capture = node.elements[-1]
                self.assertIs(capture.kind, BudgetElementKind.CAPTURE_OFFSET)
                self.assertEqual(node.D_max_nm - closure.D_max_nm, capture.b_nm)


# --------------------------------------------------------------------------
# §18.2 arithmetic and derived rigid spans
# --------------------------------------------------------------------------
class Arithmetic(unittest.TestCase):
    def test_dominating_span(self):
        cfg = budget_cfg(modules={"D2": {"exit_offset": (5.0, 0.0, 0.0)}})
        node = cassette_contour_budget("D3", S13, cfg)
        self.assertEqual((node.D_max_nm, node.D_min_nm), (8.0, 2.0))  # 5 - (1.5 + 1.0 + 0.5)
        self.assertEqual(node.dominating_element_id, "D2.span")
        self.assertFalse(node.folding_unobstructed)
        closure = closure_span_budget("D1", "D3", S13, cfg)
        self.assertEqual((closure.D_max_nm, closure.D_min_nm), (7.5, 2.5))  # 5 - (1.5 + 1.0)

    def test_distances_measured_from_entry_offset(self):
        cfg = budget_cfg(modules={"D2": {"entry_offset": (1.0, 1.0, 1.0), "exit_offset": (4.0, 5.0, 1.0)},
                                  "D3": {"entry_offset": (1.0, 1.0, 1.0), "capture_offset_vec": (1.0, 1.0, 3.0)}})
        node = cassette_contour_budget("D3", S13, cfg)
        self.assertEqual([(e.element_id, e.b_nm) for e in node.elements if e.kind is not BudgetElementKind.SEGMENT],
                         [("D2.span", 5.0), ("D3.capture", 2.0)])

    def test_d_min_never_exceeds_d_max(self):
        for exit_x in (0.0, 0.25, 1.25, 2.75, 3.0, 40.0):
            cfg = budget_cfg(modules={"D1": {"exit_offset": (exit_x, 0.0, 0.0)}, "D2": {"exit_offset": (exit_x, 0.0, 0.0)}})
            for breakdown in (cassette_contour_budget("D3", state(engaged("D3", "t")), cfg),
                              closure_span_budget("D1", "D3", S13, cfg)):
                with self.subTest(exit_x=exit_x, kind=breakdown.budget_kind):
                    self.assertLessEqual(breakdown.D_min_nm, breakdown.D_max_nm)
                    self.assertEqual(breakdown.folding_unobstructed, breakdown.D_min_nm == 0.0)


class DerivedSpanProvenance(unittest.TestCase):
    def test_span_elements_carry_basis(self):
        breakdown = cassette_contour_budget("D3", S13, budget_cfg())
        (span,) = [e for e in breakdown.elements if e.kind is BudgetElementKind.SPAN]
        self.assertIs(span.span_basis, SpanBasis.DERIVED_FROM_ENTRY_EXIT_OFFSETS)
        self.assertEqual((span.derived_rigid_span_nm, span.a_nm, span.b_nm), (SPAN, SPAN, SPAN))
        self.assertEqual(span.source_fields, ("entry_offset", "exit_offset"))
        self.assertEqual(span.as_dict(), {
            "element_id": "D2.span", "kind": "SPAN", "source_id": "D2", "source_fields": ["entry_offset", "exit_offset"],
            "module_cassette_index": 2, "span_basis": "DERIVED_FROM_ENTRY_EXIT_OFFSETS", "derived_rigid_span_nm": SPAN,
            "a_nm": SPAN, "b_nm": SPAN})
        for other in breakdown.elements:
            if other is not span:
                self.assertIsNone(other.span_basis)
                self.assertNotIn("span_basis", other.as_dict())

    def test_declared_assumption_iff_derived_span_used(self):
        cfg = budget_cfg()
        self.assertEqual(cassette_contour_budget("D3", S13, cfg).declared_assumptions, (DERIVED,))
        self.assertEqual(closure_span_budget("D1", "D3", S13, cfg).declared_assumptions, (DERIVED,))
        self.assertEqual(cassette_contour_budget("D1", S13, cfg).declared_assumptions, ())
        self.assertEqual(closure_span_budget("D1", "D2", S123, cfg).declared_assumptions, ())

    def test_serialized_form_and_wording(self):
        data = cassette_contour_budget("D3", S13, budget_cfg()).as_dict()
        text = json.dumps(data, sort_keys=True, allow_nan=False)
        self.assertEqual(list(data), ["budget_kind", "module_id", "includes_capture_offset", "shielding_ancestor",
                                      "elements", "D_max_nm", "D_min_nm", "dominating_element_id", "folding_unobstructed"])
        self.assertEqual(data["elements"][0], {"element_id": "s1.seg", "kind": "SEGMENT", "source_id": "s1",
                                               "source_fields": ["L_min", "L"], "segment_cassette_index": 1,
                                               "a_nm": 0.5, "b_nm": 1.5})
        for word in ("measured", "physical extent", "body size"):
            self.assertNotIn(word, text)
            self.assertNotIn(word, cassette_budget.__doc__)


# --------------------------------------------------------------------------
# Inputs this seam reads
# --------------------------------------------------------------------------
class InputValidation(unittest.TestCase):
    def test_segment_length_defects(self):  # OQ-5
        for value, defect in ((MISSING, "MISSING"), (None, "NULL"), ("1", "MALFORMED"), (True, "MALFORMED"),
                              (math.nan, "NON_FINITE"), (math.inf, "NON_FINITE"), (10**400, "NON_FINITE"),
                              (-1.0, "NEGATIVE")):
            for field_name in ("L", "L_min"):
                cfg = budget_cfg(tethers={"s1": {field_name: value}})
                with self.subTest(field=field_name, value=value), \
                        self.assertRaisesRegex(ValueError, rf"^GEOMETRY_INPUT_INVALID: .*s1\.{field_name}={defect}"):
                    cassette_contour_budget("D3", S13, cfg)

    def test_span_interval_invalid(self):  # AP-14
        cfg = budget_cfg(tethers={"s2": {"L_min": 1.5, "L": 1.0}})
        for call in (lambda: cassette_contour_budget("D3", S13, cfg), lambda: closure_span_budget("D1", "D3", S13, cfg)):
            with self.assertRaisesRegex(ValueError, r"^SPAN_INTERVAL_INVALID: s2\.L_min=L_MIN_EXCEEDS_L"):
                call()

    def test_geometry_input_reported_before_span_interval(self):
        cfg = budget_cfg(tethers={"s2": {"L_min": 1.5, "L": 1.0}, "s1": {"L": MISSING}})
        with self.assertRaisesRegex(ValueError, "^GEOMETRY_INPUT_INVALID: s1.L=MISSING$"):
            closure_span_budget("D1", "D3", S13, cfg)

    def test_offset_defects_on_path(self):
        cases = (
            ({"D2": {"entry_offset": MISSING}}, r"D2\.entry_offset=MISSING"),
            ({"D2": {"exit_offset": (1.0, 0.0)}}, r"D2\.exit_offset=MALFORMED"),
            ({"D2": {"exit_offset": (math.inf, 0.0, 0.0)}}, r"D2\.exit_offset=NON_FINITE"),
            ({"D3": {"entry_offset": (True, 0.0, 0.0)}}, r"D3\.entry_offset=MALFORMED"),
            ({"D3": {"capture_offset_vec": (1.7e308, 1.7e308, 0.0)}}, r"D3\.capture_offset_vec=NON_FINITE"),
        )
        for modules, pattern in cases:
            with self.subTest(modules=modules), self.assertRaisesRegex(ValueError, "^GEOMETRY_INPUT_INVALID: .*" + pattern):
                cassette_contour_budget("D3", S13, budget_cfg(modules=modules))

    def test_every_defect_listed(self):
        cfg = budget_cfg(modules={"D2": {"entry_offset": None}, "D3": {"capture_offset_vec": MISSING}},
                         tethers={"s1": {"L_min": -1.0}, "s2": {"L": "x"}})
        with self.assertRaises(ValueError) as caught:
            cassette_contour_budget("D3", S13, cfg)
        self.assertEqual(str(caught.exception), "GEOMETRY_INPUT_INVALID: s1.L_min=NEGATIVE, D2.entry_offset=NULL, "
                                                "s2.L=MALFORMED, D3.capture_offset_vec=MISSING")

    def test_only_path_inputs_read(self):
        cfg = budget_cfg(tethers={"s0": {"L": MISSING}}, modules={"D1": {"exit_offset": (1.0, 0.0), "entry_offset": None}})
        self.assertEqual(ids(cassette_contour_budget("D3", S13, cfg)), ["s1.seg", "D2.span", "s2.seg", "D3.capture"])
        self.assertEqual(ids(closure_span_budget("D1", "D3", S13, cfg)), ["s1.seg", "D2.span", "s2.seg"])
        with self.assertRaisesRegex(ValueError, r"s0\.L=MISSING"):
            cassette_contour_budget("D1", S13, cfg)


class FixedRigid(unittest.TestCase):  # OQ-7, AP-25
    def test_direct_calls_raise_unsupported_geometry(self):
        for cfg in (budget_cfg(FIXED_RIGID), budget_cfg(FIXED_RIGID, tethers={"s1": {"L": MISSING}})):
            for call in (lambda: cassette_contour_budget("D3", S13, cfg), lambda: closure_span_budget("D1", "D3", S13, cfg)):
                with self.subTest(cfg=cfg.tethers[1].L), self.assertRaisesRegex(UnsupportedGeometryError,
                                                                                 "^JUNCTION_GEOMETRY_UNSUPPORTED: FIXED_RIGID"):
                    call()

    def test_argument_errors_precede_the_junction_check(self):
        cfg = budget_cfg(FIXED_RIGID)
        for call in (lambda: cassette_contour_budget("D9", S13, cfg), lambda: closure_span_budget("D3", "D1", S13, cfg)):
            with self.assertRaises(ValueError) as caught:
                call()
            self.assertNotIsInstance(caught.exception, UnsupportedGeometryError)


class EntryChecks(unittest.TestCase):
    def test_types(self):
        cfg = budget_cfg()
        for call in (lambda: cassette_contour_budget(3, S13, cfg), lambda: cassette_contour_budget("D3", S13.assignments, cfg),
                     lambda: cassette_contour_budget("D3", S13, cfg.cassettes), lambda: closure_span_budget("D1", None, S13, cfg),
                     lambda: closure_span_budget("D1", "D3", {}, cfg)):
            with self.assertRaises(TypeError):
                call()

    def test_config_and_state_must_fit(self):
        for cfg in (budget_cfg(base_policy(topology_mode=TopologyMode.GENERAL_DAG)), replace(budget_cfg(), cassettes=())):
            with self.subTest(cfg=cfg.policy.topology_mode), self.assertRaisesRegex(ValueError, "Phase 1c"):
                cassette_contour_budget("D3", S13, cfg)
        outside = state(engaged("D1", "t1"), engaged("D3", "t3"), engaged("D7", "t7"))
        for call in (lambda: cassette_contour_budget("D3", outside, budget_cfg()),
                     lambda: closure_span_budget("D1", "D3", outside, budget_cfg())):
            with self.assertRaisesRegex(ValueError, "^STATE_INPUT_INVALID.*D7"):
                call()


class Determinism(unittest.TestCase):
    def test_repeatable_and_declaration_order_free(self):
        permuted = state(engaged("D3", "t3"), engaged("D1", "t1"))
        for build in (lambda st: cassette_contour_budget("D3", st, budget_cfg()),
                      lambda st: closure_span_budget("D1", "D3", st, budget_cfg())):
            first, second, third = build(S13), build(S13), build(permuted)
            self.assertEqual(first, second)
            self.assertEqual(first, third)
            self.assertEqual(json.dumps(first.as_dict(), sort_keys=True), json.dumps(third.as_dict(), sort_keys=True))

    def test_no_placement_or_anchor(self):
        with mock.patch("gotne.cassette_frames.cassette_effective_anchor", side_effect=AssertionError("anchor called")):
            cassette_contour_budget("D3", S13, budget_cfg())
            closure_span_budget("D1", "D3", S13, budget_cfg())


# --------------------------------------------------------------------------
# Module surface and import boundary for this seam. The package-level export
# allowlist lives in test_cassette_topology.PurityTests (AP-1 / AP-2).
# --------------------------------------------------------------------------
class SeamBoundary(unittest.TestCase):
    def test_module_all(self):
        self.assertEqual(set(cassette_budget.__all__), {"SpanBasis", "BudgetElementKind", "BudgetElement",
                                                        "BudgetBreakdown", "cassette_contour_budget",
                                                        "closure_span_budget"})

    def test_cassette_budget_imports_only_permitted_modules(self):
        relative, absolute = imported_modules(ROOT_DIR / "gotne" / "cassette_budget.py")
        self.assertLessEqual(relative, {"cassette_schema", "cassette_state", "cassette_frames", "cassette_topology",
                                        "identity", "status"})
        self.assertLessEqual(absolute, {"__future__", "dataclasses", "enum", "math", "typing"})

    def test_earlier_modules_do_not_import_budget(self):
        for name in ("cassette_frames.py", "cassette_state.py", "identity.py", "status.py", "cassette_schema.py",
                     "cassette_topology.py"):
            relative, _ = imported_modules(ROOT_DIR / "gotne" / name)
            self.assertNotIn("cassette_budget", relative, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
