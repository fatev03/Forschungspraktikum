"""GOTNE Phase 2 frames (v0.3.1): shielding ancestor and effective anchor.

SCOPE (Phase 2 decision record, revision 3)
-------------------------------------------
Second link of the acyclic Phase 2 chain
    cassette_state -> cassette_frames -> cassette_budget -> cassette_closure -> cassette_node
It finds the shielding ancestor of a module (AP-18) and the point that
ancestor fixes (E). It evaluates no budget, closure or node predicate, and it
is junction-independent, so it also runs under FIXED_RIGID (OQ-7).

PLACEMENT CONVENTION (AP-22)
----------------------------
For an ENGAGED module D at target T with site p and orientation R, a
module-frame offset v is placed at R.v + t, with t = p - R.capture_offset_vec_D.
This only maps target-site frame data into module-frame coordinates; it does
not assert a unique physical configuration of D. EffectiveAnchor reports
pose_placement=CAPTURE_POINT_ON_TARGET_SITE in declared_assumptions whenever
the convention was applied.

Under ORIENTATION_MARGINALIZED a supplied orientation is context data only.
Phase 2 does not marginalize, so an anchor point that would need R is
undetermined (point None), whether or not an orientation is present.

Inputs come only from state, cfg and context. Target geometry comes only from
context.targets. Wrong argument types raise TypeError; anything that makes the
anchor ill-defined raises ValueError, and no anchor is returned.

May import: cassette_schema, status, identity, cassette_topology,
cassette_state, math.
"""

from __future__ import annotations

import math
from typing import List, NamedTuple, Optional, Sequence, Tuple, Union

from . import cassette_state, cassette_topology
from .cassette_schema import CassetteConfig, EngagedPoseResolution, Missing
from .cassette_state import EngagementState, EvaluationContext, Rotation3, StateReason, Vec3
from .status import Status

__all__ = ["ROOT", "EffectiveAnchor", "cassette_effective_anchor"]

#: AP-22: declared whenever the placement convention is applied.
POSE_PLACEMENT_ASSUMPTION = "pose_placement=CAPTURE_POINT_ON_TARGET_SITE"


class Root:
    """Singleton sentinel for the root anchor as shielding ancestor. It is
    never equal to a str, so it cannot collide with a module identifier."""

    _instance: Optional["Root"] = None

    def __new__(cls) -> "Root":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "ROOT"

    def __reduce__(self) -> str:
        # copy and pickle resolve to the module global, keeping the singleton.
        return "ROOT"


ROOT = Root()


class EffectiveAnchor(NamedTuple):
    """Decision record E. The ancestor and its index are always determined;
    ROOT has module cassette index 0. point is None iff it would need an
    orientation Phase 2 does not condition on (ORIENTATION_MARGINALIZED)."""

    point: Optional[Vec3]
    ancestor: Union[str, Root]
    ancestor_module_cassette_index: int

    @property
    def declared_assumptions(self) -> Tuple[str, ...]:
        """AP-22: the placement convention was applied iff the point was
        placed from a module ancestor's target-site data."""
        if self.ancestor is ROOT or self.point is None:
            return ()
        return (POSE_PLACEMENT_ASSUMPTION,)


# --------------------------------------------------------------------------
# Small pure helpers
# --------------------------------------------------------------------------
def _vector(value: object) -> Tuple[Optional[Vec3], Optional[str]]:
    """(vector, None) for three finite reals, else (None, OQ-5 defect)."""
    if isinstance(value, Missing):
        return None, "MISSING"
    if value is None:
        return None, "NULL"
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None, "MALFORMED"
    components = []
    for component in value:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            return None, "MALFORMED"
        try:
            number = float(component)
        except OverflowError:
            return None, "NON_FINITE"
        if not math.isfinite(number):
            return None, "NON_FINITE"
        components.append(number)
    return (components[0], components[1], components[2]), None


def _rotate(rotation: Rotation3, v: Vec3) -> Vec3:
    return (
        rotation[0][0] * v[0] + rotation[0][1] * v[1] + rotation[0][2] * v[2],
        rotation[1][0] * v[0] + rotation[1][1] * v[1] + rotation[1][2] * v[2],
        rotation[2][0] * v[0] + rotation[2][1] * v[1] + rotation[2][2] * v[2],
    )


def _place(offset: Vec3, site: Vec3, rotation: Rotation3, capture: Vec3) -> Vec3:
    """AP-22: R.offset + t with t = site - R.capture, in that order."""
    rotated_capture = _rotate(rotation, capture)
    t = (site[0] - rotated_capture[0], site[1] - rotated_capture[1], site[2] - rotated_capture[2])
    rotated = _rotate(rotation, offset)
    return (rotated[0] + t[0], rotated[1] + t[1], rotated[2] + t[2])


def _reject(defects: Sequence[Tuple[str, str, str]]) -> None:
    listed = ", ".join(f"{source_id}.{field}={defect}" for source_id, field, defect in defects)
    raise ValueError(f"{StateReason.GEOMETRY_INPUT_INVALID}: {listed}")


def _shielding_ancestor(
    module_id: str, state: EngagementState, ordered: Sequence[str]
) -> Tuple[Union[str, Root], int]:
    """AP-18: the ENGAGED module with the largest module cassette index below
    module_id, with that index, else (ROOT, 0). ordered is the cassette's
    ordered_modules and must contain module_id."""
    engaged = {a.module_id for a in state.engaged_assignments()}
    index = ordered.index(module_id) + 1
    k = next((i for i in range(index - 1, 0, -1) if ordered[i - 1] in engaged), 0)
    return (ROOT, 0) if k == 0 else (ordered[k - 1], k)


def _tagged_ancestor(ancestor: Union[str, Root], index: int) -> dict:
    """Decision record K: the ancestor serialized as a tagged object, never a
    bare string, so ROOT cannot collide with a module id."""
    if ancestor is ROOT:
        return {"kind": "ROOT", "id": None, "module_cassette_index": 0}
    return {"kind": "MODULE", "id": ancestor, "module_cassette_index": index}


def _anchor_input_defects(
    ancestor: Union[str, Root],
    state: EngagementState,
    cfg: CassetteConfig,
    context: EvaluationContext,
) -> List[Tuple[str, str, str]]:
    """OQ-5 (source_id, field, defect) for the inputs an effective anchor with
    this shielding ancestor reads: the root position; or, under POSE_REQUIRED,
    the ancestor's orientation, exit_offset and capture_offset_vec. An absent
    ancestor target is reported by the caller, not here."""
    if ancestor is ROOT:
        root_id = cfg.cassettes[0].root_anchor_id
        root = next(a for a in cfg.anchors if a.id == root_id)
        _, defect = _vector(root.position)
        return [] if defect is None else [(root_id, "position", defect)]
    if cfg.policy.engaged_pose_resolution is EngagedPoseResolution.ORIENTATION_MARGINALIZED:
        return []
    target_id = next(a.target_id for a in state.engaged_assignments() if a.module_id == ancestor)
    geometry = context.targets.lookup(target_id)
    spec = next(m for m in cfg.modules if m.id == ancestor)
    defects: List[Tuple[str, str, str]] = []
    if geometry is not None and geometry.orientation is None:
        defects.append((target_id, "orientation", "ORIENTATION_REQUIRED"))
    for name in ("exit_offset", "capture_offset_vec"):
        _, defect = _vector(getattr(spec, name))
        if defect is not None:
            defects.append((ancestor, name, defect))
    return defects


# --------------------------------------------------------------------------
# Effective anchor
# --------------------------------------------------------------------------
def cassette_effective_anchor(
    module_id: str,
    state: EngagementState,
    cfg: CassetteConfig,
    context: EvaluationContext,
) -> EffectiveAnchor:
    """AP-18 / E. The shielding ancestor of module_id is the ENGAGED module
    with the largest module cassette index below it, else ROOT.

    ROOT fixes the root AnchorSpec.position. A module ancestor fixes its
    exit_offset placed by the AP-22 convention under POSE_REQUIRED; under
    ORIENTATION_MARGINALIZED its point is None.

    Raises ValueError when cfg is not VALID under Phase 1c, module_id is not
    in the cassette, an ENGAGED assignment names a module outside it (OQ-4), an ENGAGED
    target_id is absent from context (OQ-1), or an input the anchor needs is
    missing or malformed (OQ-5)."""
    if type(module_id) is not str:
        raise TypeError(f"module_id must be a plain str, got {type(module_id).__qualname__}")
    for name, value, cls in (
        ("state", state, EngagementState),
        ("cfg", cfg, CassetteConfig),
        ("context", context, EvaluationContext),
    ):
        if not isinstance(value, cls):
            raise TypeError(f"{name} must be a {cls.__name__}, got {type(value).__qualname__}")
    config_result = cassette_topology.validate_cassette_config(cfg)
    if config_result.status is not Status.VALID:
        raise ValueError(
            f"cfg is {config_result.status.value} ({config_result.status_reason}) under Phase 1c; "
            "no anchor is defined"
        )
    ordered = tuple(cfg.cassettes[0].ordered_modules)
    if module_id not in ordered:
        raise ValueError(f"module {module_id!r} is not in the cassette")
    unknown = cassette_state._unknown_module_ids(state, cfg)
    if unknown:
        raise ValueError(
            f"{StateReason.STATE_INPUT_INVALID}: modules not in the cassette: {list(unknown)}"
        )
    missing = cassette_state._missing_targets(state, context)
    if missing:
        _reject([(a.module_id, "target_id", "TARGET_NOT_IN_CONTEXT") for a in missing])

    ancestor, ancestor_index = _shielding_ancestor(module_id, state, ordered)
    defects = _anchor_input_defects(ancestor, state, cfg, context)
    if defects:
        _reject(defects)
    if ancestor is ROOT:
        root = next(a for a in cfg.anchors if a.id == cfg.cassettes[0].root_anchor_id)
        position, _ = _vector(root.position)
        return EffectiveAnchor(position, ROOT, 0)

    if cfg.policy.engaged_pose_resolution is EngagedPoseResolution.ORIENTATION_MARGINALIZED:
        return EffectiveAnchor(None, ancestor, ancestor_index)

    target_id = next(a.target_id for a in state.engaged_assignments() if a.module_id == ancestor)
    geometry = context.targets.lookup(target_id)
    spec = next(m for m in cfg.modules if m.id == ancestor)
    exit_offset, _ = _vector(spec.exit_offset)
    capture, _ = _vector(spec.capture_offset_vec)
    point = _place(exit_offset, geometry.site_nm, geometry.orientation, capture)
    if not all(math.isfinite(x) for x in point):
        _reject([(ancestor, "placed_exit_offset", "NON_FINITE")])
    return EffectiveAnchor(point, ancestor, ancestor_index)
