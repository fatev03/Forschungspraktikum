"""GOTNE Phase 2 budget (v0.3.1): §18.2 span accounting over cassette paths.

SCOPE (Phase 2 decision record, revision 3)
-------------------------------------------
Third link of the acyclic Phase 2 chain
    cassette_state -> cassette_frames -> cassette_budget -> cassette_closure -> cassette_node
Two element sets, kept apart (OQ-3, AP-26):

  cassette_contour_budget(module_id, ...)   node gate: shielding ancestor k of
      D_j to the target site of D_j. Segments s_k..s_{j-1}, spans of
      D_{k+1}..D_{j-1}, and the capture offset of D_j exactly once.
  closure_span_budget(upstream, downstream, ...)   closure gate: exit reference
      of D_i to entry reference of D_j for a consecutive closure pair. Segments
      s_i..s_{j-1} and spans of D_{i+1}..D_{j-1}. No capture offset.

Engagement selects the shielding ancestor (AP-18) and nothing else: no element
of the physical path is dropped because a module is UNENGAGED (N9, N10).

Arithmetic (§18.2, D1), over span intervals [a_e, b_e]:
    D_max = sum b_e
    D_min = max(0, max_e (a_e - sum_{f != e} b_f))
Segment intervals are [L_min, L]. A rigid span is a provisional modelling
quantity, ||exit_offset - entry_offset|| of an intervening module, with basis
SpanBasis.DERIVED_FROM_ENTRY_EXIT_OFFSETS; it is computed from declared offsets
and is not an independently declared input. The capture offset is
||capture_offset_vec - entry_offset|| of D_j.

Only FREE_SWIVEL has a span model. Under FIXED_RIGID both functions raise
UnsupportedGeometryError; the FREE_SWIVEL rule is never reused (OQ-7). No
placement, target geometry or effective anchor is used here.

Wrong argument types raise TypeError. Other failures raise ValueError naming
the StateReason, with every defect listed; no breakdown is returned.

May import: cassette_schema, status, identity, cassette_topology,
cassette_state, cassette_frames, math.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from . import cassette_frames, cassette_state, cassette_topology
from .cassette_frames import ROOT, Root
from .cassette_schema import CassetteConfig, JunctionModel, Missing, ModuleSpec, TetherSpec
from .cassette_state import (
    EngagementLabel,
    EngagementState,
    StateReason,
    UnsupportedGeometryError,
)
from .status import Status

__all__ = [
    "SpanBasis",
    "BudgetElementKind",
    "BudgetElement",
    "BudgetBreakdown",
    "cassette_contour_budget",
    "closure_span_budget",
]

#: K: declared whenever a derived rigid span enters a budget.
RIGID_SPAN_ASSUMPTION = "rigid_span_basis=DERIVED_FROM_ENTRY_EXIT_OFFSETS"


class SpanBasis(str, Enum):
    """K: how a rigid span was obtained. One v1 member. A structural-envelope
    override needs a new member, a new optional EvaluationContext field and a
    spec change; it never enters CassetteConfig."""

    DERIVED_FROM_ENTRY_EXIT_OFFSETS = "DERIVED_FROM_ENTRY_EXIT_OFFSETS"


class BudgetElementKind(str, Enum):
    SEGMENT = "SEGMENT"
    SPAN = "SPAN"
    CAPTURE_OFFSET = "CAPTURE_OFFSET"


#: kind -> (element_id suffix, source_fields, serialized index key)
_KIND_LAYOUT: Dict[BudgetElementKind, Tuple[str, Tuple[str, ...], str]] = {
    BudgetElementKind.SEGMENT: (".seg", ("L_min", "L"), "segment_cassette_index"),
    BudgetElementKind.SPAN: (".span", ("entry_offset", "exit_offset"), "module_cassette_index"),
    BudgetElementKind.CAPTURE_OFFSET: (
        ".capture",
        ("entry_offset", "capture_offset_vec"),
        "module_cassette_index",
    ),
}


def _finite_nonnegative(value: object) -> bool:
    return type(value) is float and math.isfinite(value) and value >= 0.0


@dataclass(frozen=True)
class BudgetElement:
    """One element of a path, with span interval [a_nm, b_nm]. index is the
    segment cassette index (0-based) for SEGMENT, else the module cassette
    index (1-based)."""

    element_id: str
    kind: BudgetElementKind
    source_id: str
    source_fields: Tuple[str, ...]
    index: int
    a_nm: float
    b_nm: float
    span_basis: Optional[SpanBasis] = None
    derived_rigid_span_nm: Optional[float] = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, BudgetElementKind):
            raise TypeError(f"kind must be a BudgetElementKind, got {type(self.kind).__qualname__}")
        suffix, source_fields, _ = _KIND_LAYOUT[self.kind]
        if type(self.source_id) is not str or self.element_id != self.source_id + suffix:
            raise ValueError(f"element_id must be source_id + {suffix!r}")
        if tuple(self.source_fields) != source_fields:
            raise ValueError(f"{self.kind.value} source_fields must be {source_fields}")
        object.__setattr__(self, "source_fields", source_fields)
        minimum_index = 0 if self.kind is BudgetElementKind.SEGMENT else 1
        if type(self.index) is not int or self.index < minimum_index:
            raise ValueError(f"{self.kind.value} index must be an int >= {minimum_index}")
        if not (_finite_nonnegative(self.a_nm) and _finite_nonnegative(self.b_nm)):
            raise ValueError("a_nm and b_nm must be finite, non-negative floats")
        if self.a_nm > self.b_nm:
            raise ValueError(
                f"{StateReason.SPAN_INTERVAL_INVALID}: a_nm > b_nm for {self.element_id}"
            )
        if self.kind is BudgetElementKind.SPAN:
            if self.span_basis is not SpanBasis.DERIVED_FROM_ENTRY_EXIT_OFFSETS:
                raise ValueError(
                    "a SPAN element must carry span_basis DERIVED_FROM_ENTRY_EXIT_OFFSETS"
                )
            if not (self.derived_rigid_span_nm == self.a_nm == self.b_nm):
                raise ValueError("a SPAN element needs a_nm == b_nm == derived_rigid_span_nm")
        elif self.span_basis is not None or self.derived_rigid_span_nm is not None:
            raise ValueError(f"a {self.kind.value} element carries no span basis")
        if self.kind is BudgetElementKind.CAPTURE_OFFSET and self.a_nm != self.b_nm:
            raise ValueError("a CAPTURE_OFFSET element needs a_nm == b_nm")

    def as_dict(self) -> Dict[str, Any]:
        _, _, index_key = _KIND_LAYOUT[self.kind]
        out: Dict[str, Any] = {
            "element_id": self.element_id,
            "kind": self.kind.value,
            "source_id": self.source_id,
            "source_fields": list(self.source_fields),
            index_key: self.index,
        }
        if self.kind is BudgetElementKind.SPAN:
            out["span_basis"] = self.span_basis.value
            out["derived_rigid_span_nm"] = self.derived_rigid_span_nm
        out["a_nm"] = self.a_nm
        out["b_nm"] = self.b_nm
        return out


def _bounds(elements: Sequence[BudgetElement]) -> Tuple[float, float, Optional[str]]:
    """§18.2: (D_max, D_min, dominating element id). The dominating element is
    the first in path order with the largest positive a_e - sum_{f != e} b_f."""
    b = [e.b_nm for e in elements]
    try:
        d_max = math.fsum(b)
        excesses = [e.a_nm - math.fsum(b[:i] + b[i + 1 :]) for i, e in enumerate(elements)]
    except OverflowError:
        raise ValueError(f"{StateReason.GEOMETRY_INPUT_INVALID}: span sum is not finite") from None
    best = max(range(len(elements)), key=lambda i: (excesses[i], -i))
    d_min = max(0.0, excesses[best])
    if d_min > d_max:  # MNH22: impossible when every a_e <= b_e
        raise RuntimeError(f"MNH22: D_min {d_min!r} > D_max {d_max!r}")
    dominating = elements[best].element_id if excesses[best] > 0.0 else None
    return d_max, d_min, dominating


@dataclass(frozen=True)
class BudgetBreakdown:
    """K. A NODE budget names module_id and its shielding ancestor and ends
    with exactly one CAPTURE_OFFSET element; a CLOSURE budget names the pair
    and has none. D_max_nm, D_min_nm, dominating_element_id,
    folding_unobstructed and includes_capture_offset are computed from the
    elements, never supplied."""

    budget_kind: str
    elements: Tuple[BudgetElement, ...]
    module_id: Optional[str] = None
    shielding_ancestor: Union[str, Root, None] = None
    shielding_ancestor_module_cassette_index: Optional[int] = None
    upstream_module_id: Optional[str] = None
    downstream_module_id: Optional[str] = None
    D_max_nm: float = field(init=False)
    D_min_nm: float = field(init=False)
    dominating_element_id: Optional[str] = field(init=False)
    folding_unobstructed: bool = field(init=False)
    includes_capture_offset: bool = field(init=False)

    def __post_init__(self) -> None:
        if self.budget_kind not in ("NODE", "CLOSURE"):
            raise ValueError("budget_kind must be NODE or CLOSURE")
        if not isinstance(self.elements, (list, tuple)) or not self.elements:
            raise ValueError("elements must be a non-empty list or tuple")
        elements = tuple(self.elements)
        if not all(isinstance(e, BudgetElement) for e in elements):
            raise TypeError("elements must be BudgetElement instances")
        if len({e.element_id for e in elements}) != len(elements):
            raise ValueError("element_id values must be unique")
        captures = [i for i, e in enumerate(elements) if e.kind is BudgetElementKind.CAPTURE_OFFSET]
        node = self.budget_kind == "NODE"
        if node:
            if captures != [len(elements) - 1] or elements[-1].source_id != self.module_id:
                raise ValueError(
                    "a NODE budget ends with the capture offset of module_id, exactly once"
                )
            ancestor = self.shielding_ancestor
            index = self.shielding_ancestor_module_cassette_index
            if type(self.module_id) is not str or not (
                (ancestor is ROOT and index == 0)
                or (type(ancestor) is str and type(index) is int and index >= 1)
            ):
                raise ValueError(
                    "a NODE budget needs module_id and a shielding ancestor with its index"
                )
            if self.upstream_module_id is not None or self.downstream_module_id is not None:
                raise ValueError("a NODE budget names no closure pair")
        else:
            if captures:
                raise ValueError("a CLOSURE budget never includes a capture offset")
            if not (type(self.upstream_module_id) is type(self.downstream_module_id) is str):
                raise ValueError(
                    "a CLOSURE budget needs upstream_module_id and downstream_module_id"
                )
            if (
                self.module_id is not None
                or self.shielding_ancestor is not None
                or self.shielding_ancestor_module_cassette_index is not None
            ):
                raise ValueError("a CLOSURE budget names no module_id or shielding ancestor")
        d_max, d_min, dominating = _bounds(elements)
        object.__setattr__(self, "elements", elements)
        object.__setattr__(self, "D_max_nm", d_max)
        object.__setattr__(self, "D_min_nm", d_min)
        object.__setattr__(self, "dominating_element_id", dominating)
        object.__setattr__(self, "folding_unobstructed", dominating is None)
        object.__setattr__(self, "includes_capture_offset", node)

    @property
    def declared_assumptions(self) -> Tuple[str, ...]:
        """K: rigid_span_basis is declared iff a derived span was used."""
        if any(e.kind is BudgetElementKind.SPAN for e in self.elements):
            return (RIGID_SPAN_ASSUMPTION,)
        return ()

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"budget_kind": self.budget_kind}
        if self.budget_kind == "NODE":
            out["module_id"] = self.module_id
            out["includes_capture_offset"] = True
            out["shielding_ancestor"] = cassette_frames._tagged_ancestor(
                self.shielding_ancestor, self.shielding_ancestor_module_cassette_index
            )
        else:
            out["upstream_module_id"] = self.upstream_module_id
            out["downstream_module_id"] = self.downstream_module_id
            out["includes_capture_offset"] = False
        out["elements"] = [e.as_dict() for e in self.elements]
        out["D_max_nm"] = self.D_max_nm
        out["D_min_nm"] = self.D_min_nm
        out["dominating_element_id"] = self.dominating_element_id
        out["folding_unobstructed"] = self.folding_unobstructed
        return out


# --------------------------------------------------------------------------
# Input reading. Each reader returns the element, or None after recording
# (source_id, field, defect) triples: GEOMETRY_INPUT_INVALID defects in
# geometry, SPAN_INTERVAL_INVALID defects in intervals.
# --------------------------------------------------------------------------
Defects = List[Tuple[str, str, str]]


def _length(value: object) -> Tuple[Optional[float], Optional[str]]:
    """(length, None) for a finite real >= 0, else (None, OQ-5 defect)."""
    if isinstance(value, Missing):
        return None, "MISSING"
    if value is None:
        return None, "NULL"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, "MALFORMED"
    try:
        number = float(value)
    except OverflowError:
        return None, "NON_FINITE"
    if not math.isfinite(number):
        return None, "NON_FINITE"
    if number < 0.0:
        return None, "NEGATIVE"
    return number, None


def _distance(
    spec: ModuleSpec, to_field: str, geometry: Defects
) -> Optional[float]:
    """||spec.<to_field> - spec.entry_offset||, or None after recording defects."""
    entry, entry_defect = cassette_frames._vector(spec.entry_offset)
    target, target_defect = cassette_frames._vector(getattr(spec, to_field))
    if entry_defect is not None:
        geometry.append((spec.id, "entry_offset", entry_defect))
    if target_defect is not None:
        geometry.append((spec.id, to_field, target_defect))
    if entry is None or target is None:
        return None
    distance = math.dist(target, entry)
    if not math.isfinite(distance):
        geometry.append((spec.id, to_field, "NON_FINITE"))
        return None
    return distance


def _segment(
    tether: TetherSpec, index: int, geometry: Defects, intervals: Defects
) -> Optional[BudgetElement]:
    lower, lower_defect = _length(tether.L_min)
    upper, upper_defect = _length(tether.L)
    if lower_defect is not None:
        geometry.append((tether.id, "L_min", lower_defect))
    if upper_defect is not None:
        geometry.append((tether.id, "L", upper_defect))
    if lower is None or upper is None:
        return None
    if lower > upper:
        intervals.append((tether.id, "L_min", "L_MIN_EXCEEDS_L"))
        return None
    return BudgetElement(
        element_id=tether.id + ".seg",
        kind=BudgetElementKind.SEGMENT,
        source_id=tether.id,
        source_fields=("L_min", "L"),
        index=index,
        a_nm=lower,
        b_nm=upper,
    )


def _span(spec: ModuleSpec, index: int, geometry: Defects) -> Optional[BudgetElement]:
    span = _distance(spec, "exit_offset", geometry)
    if span is None:
        return None
    return BudgetElement(
        element_id=spec.id + ".span",
        kind=BudgetElementKind.SPAN,
        source_id=spec.id,
        source_fields=("entry_offset", "exit_offset"),
        index=index,
        a_nm=span,
        b_nm=span,
        span_basis=SpanBasis.DERIVED_FROM_ENTRY_EXIT_OFFSETS,
        derived_rigid_span_nm=span,
    )


def _capture(spec: ModuleSpec, index: int, geometry: Defects) -> Optional[BudgetElement]:
    offset = _distance(spec, "capture_offset_vec", geometry)
    if offset is None:
        return None
    return BudgetElement(
        element_id=spec.id + ".capture",
        kind=BudgetElementKind.CAPTURE_OFFSET,
        source_id=spec.id,
        source_fields=("entry_offset", "capture_offset_vec"),
        index=index,
        a_nm=offset,
        b_nm=offset,
    )


def _path(
    k: int,
    j: int,
    cfg: CassetteConfig,
    ordered: Sequence[str],
    geometry: Defects,
    intervals: Defects,
) -> List[Optional[BudgetElement]]:
    """Elements between node index k (0 = root anchor) and module index j, in
    path order: s_k, span D_{k+1}, s_{k+1}, ..., span D_{j-1}, s_{j-1}."""
    segments = cfg.cassettes[0].ordered_segments
    tethers = {t.id: t for t in cfg.tethers}
    modules = {m.id: m for m in cfg.modules}
    elements: List[Optional[BudgetElement]] = []
    for i in range(k, j):
        if i > k:
            elements.append(_span(modules[ordered[i - 1]], i, geometry))
        elements.append(_segment(tethers[segments[i]], i, geometry, intervals))
    return elements


def _raise_defects(geometry: Defects, intervals: Defects) -> None:
    """Stage order of evaluate_state: geometry input (7) before span intervals (8)."""
    for reason, defects in (
        (StateReason.GEOMETRY_INPUT_INVALID, geometry),
        (StateReason.SPAN_INTERVAL_INVALID, intervals),
    ):
        if defects:
            listed = ", ".join(f"{source}.{name}={defect}" for source, name, defect in defects)
            raise ValueError(f"{reason}: {listed}")


# --------------------------------------------------------------------------
# Entry checks
# --------------------------------------------------------------------------
def _ordered_modules(module_ids: Sequence[object], state: object, cfg: object) -> Tuple[str, ...]:
    for module_id in module_ids:
        if type(module_id) is not str:
            raise TypeError(f"module ids must be plain str, got {type(module_id).__qualname__}")
    if not isinstance(state, EngagementState):
        raise TypeError(f"state must be an EngagementState, got {type(state).__qualname__}")
    if not isinstance(cfg, CassetteConfig):
        raise TypeError(f"cfg must be a CassetteConfig, got {type(cfg).__qualname__}")
    config_result = cassette_topology.validate_cassette_config(cfg)
    if config_result.status is not Status.VALID:
        raise ValueError(
            f"cfg is {config_result.status.value} ({config_result.status_reason}) under Phase 1c; "
            "no budget is defined"
        )
    ordered = tuple(cfg.cassettes[0].ordered_modules)
    for module_id in module_ids:
        if module_id not in ordered:
            raise ValueError(f"module {module_id!r} is not in the cassette")
    unknown = cassette_state._unknown_module_ids(state, cfg)
    if unknown:
        raise ValueError(
            f"{StateReason.STATE_INPUT_INVALID}: modules not in the cassette: {list(unknown)}"
        )
    return ordered


def _require_free_swivel(cfg: CassetteConfig) -> None:
    """OQ-7 / AP-25: only FREE_SWIVEL has a Phase 2 span model."""
    model = cfg.policy.junction_model
    if model is not JunctionModel.FREE_SWIVEL:
        raise UnsupportedGeometryError(
            f"{StateReason.JUNCTION_GEOMETRY_UNSUPPORTED}: {model.value} has no Phase 2 "
            "span model; "
            "the FREE_SWIVEL rule is not reused"
        )


# --------------------------------------------------------------------------
# Budgets
# --------------------------------------------------------------------------
def cassette_contour_budget(
    module_id: str, state: EngagementState, cfg: CassetteConfig
) -> BudgetBreakdown:
    """Node-gate budget of the ENGAGED module module_id: from its shielding
    ancestor (AP-18) to its target site, with its capture offset exactly once.

    Raises ValueError when cfg is not VALID under Phase 1c, module_id is not
    an ENGAGED module of the cassette, an ENGAGED assignment names a module
    outside it, or an
    input on the path is invalid (GEOMETRY_INPUT_INVALID, then
    SPAN_INTERVAL_INVALID); UnsupportedGeometryError unless FREE_SWIVEL."""
    ordered = _ordered_modules((module_id,), state, cfg)
    if state.label_of(module_id) is not EngagementLabel.ENGAGED:
        raise ValueError(
            f"module {module_id!r} is not ENGAGED; the node budget ends at a target site"
        )
    _require_free_swivel(cfg)
    ancestor, k = cassette_frames._shielding_ancestor(module_id, state, ordered)
    j = ordered.index(module_id) + 1
    geometry: Defects = []
    intervals: Defects = []
    elements = _path(k, j, cfg, ordered, geometry, intervals)
    elements.append(_capture(next(m for m in cfg.modules if m.id == module_id), j, geometry))
    _raise_defects(geometry, intervals)
    return BudgetBreakdown(
        budget_kind="NODE",
        elements=tuple(elements),
        module_id=module_id,
        shielding_ancestor=ancestor,
        shielding_ancestor_module_cassette_index=k,
    )


def closure_span_budget(
    upstream_module_id: str,
    downstream_module_id: str,
    state: EngagementState,
    cfg: CassetteConfig,
) -> BudgetBreakdown:
    """Closure-gate budget from the exit reference of upstream_module_id to the
    entry reference of downstream_module_id. The pair must be consecutive
    ENGAGED modules of state; any other pair raises ValueError and is never
    repaired (N2). Never includes a capture offset.

    Raises as cassette_contour_budget does for cfg, state and path inputs."""
    ordered = _ordered_modules((upstream_module_id, downstream_module_id), state, cfg)
    i = ordered.index(upstream_module_id) + 1
    j = ordered.index(downstream_module_id) + 1
    engaged = {a.module_id for a in state.engaged_assignments()}
    if not (
        i < j
        and upstream_module_id in engaged
        and downstream_module_id in engaged
        and not any(ordered[m - 1] in engaged for m in range(i + 1, j))
    ):
        raise ValueError(
            f"({upstream_module_id!r}, {downstream_module_id!r}) is not a consecutive "
            "ENGAGED pair of state"
        )
    _require_free_swivel(cfg)
    geometry: Defects = []
    intervals: Defects = []
    elements = _path(i, j, cfg, ordered, geometry, intervals)
    _raise_defects(geometry, intervals)
    return BudgetBreakdown(
        budget_kind="CLOSURE",
        elements=tuple(elements),
        upstream_module_id=upstream_module_id,
        downstream_module_id=downstream_module_id,
    )
