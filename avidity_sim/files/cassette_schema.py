"""GOTNE cassette schema, Phase 1c structural subset.

PURE. No geometry, no numerics beyond scalar domain checks performed elsewhere.
Offset vectors are carried as opaque declared values: Phase 1c reads their
PRESENCE, never their components.

The three-valued domain {MISSING, None, value} is load-bearing (decision D7):
  MISSING -> the field was not declared at all
  None    -> the field was declared as explicit null
  value   -> the field was declared with content
A schema that collapses MISSING onto None cannot express invariant C10a.

Specification references: §17.1, §17.2, §17.6 (v0.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Sequence, Tuple, Union

__all__ = [
    "MISSING",
    "Missing",
    "Maybe",
    "TopologyMode",
    "JunctionModel",
    "EngagementOrderPolicy",
    "UnresolvedUpstreamPolicy",
    "EngagedPoseResolution",
    "CompositeDensityMethod",
    "DepEdgeKind",
    "SUPPORTED_JUNCTION_MODELS_V1",
    "AnchorSpec",
    "TetherSpec",
    "ModuleSpec",
    "DepEdge",
    "CassettePolicy",
    "CassetteSpec",
    "CassetteConfig",
]


class Missing:
    """Sentinel for 'field not declared'. Distinct from None."""

    _instance: Optional["Missing"] = None

    def __new__(cls) -> "Missing":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "MISSING"

    def __bool__(self) -> bool:
        return False


MISSING = Missing()

Maybe = Union[Any, Missing, None]


class TopologyMode(str, Enum):
    GENERAL_DAG = "GENERAL_DAG"
    LINEAR_ORDERED_CASSETTE = "LINEAR_ORDERED_CASSETTE"


class JunctionModel(str, Enum):
    FREE_SWIVEL = "FREE_SWIVEL"
    FIXED_RIGID = "FIXED_RIGID"
    RESTRICTED_CONE = "RESTRICTED_CONE"  # declared, not implemented in v1 (D2)


#: Decision D2. The rejection set is data, not a literal buried in a branch.
SUPPORTED_JUNCTION_MODELS_V1: Tuple[JunctionModel, ...] = (
    JunctionModel.FREE_SWIVEL,
    JunctionModel.FIXED_RIGID,
)


class EngagementOrderPolicy(str, Enum):
    STRICT_PROXIMAL_TO_DISTAL = "STRICT_PROXIMAL_TO_DISTAL"
    ANY_ORDER = "ANY_ORDER"
    EXPLICIT_PARTIAL_ORDER = "EXPLICIT_PARTIAL_ORDER"


class UnresolvedUpstreamPolicy(str, Enum):
    SELF_AVOIDANCE_IGNORED = "SELF_AVOIDANCE_IGNORED"
    EXCLUDED_SHELL_BOUND = "EXCLUDED_SHELL_BOUND"
    EXTERNAL_SAMPLED_CHAIN = "EXTERNAL_SAMPLED_CHAIN"


class EngagedPoseResolution(str, Enum):
    POSE_REQUIRED = "POSE_REQUIRED"
    ORIENTATION_MARGINALIZED = "ORIENTATION_MARGINALIZED"


class CompositeDensityMethod(str, Enum):
    GAUSSIAN_MOMENT_MATCH = "GAUSSIAN_MOMENT_MATCH"
    NUMERICAL_CONVOLUTION = "NUMERICAL_CONVOLUTION"
    EXTERNAL_SAMPLED = "EXTERNAL_SAMPLED"


class DepEdgeKind(str, Enum):
    REQUIRES = "REQUIRES"
    EXCLUDES = "EXCLUDES"
    INFLUENCES = "INFLUENCES"


@dataclass(frozen=True)
class AnchorSpec:
    id: str
    surface_id: Optional[str] = None
    # Geometry fields are declared but NEVER read in Phase 1c.
    position: Maybe = MISSING
    normal: Maybe = MISSING


@dataclass(frozen=True)
class TetherSpec:
    id: str
    from_node: str
    to_node: str
    cassette_index: Maybe = MISSING  # sigma index, 0 .. N-1
    L: Maybe = MISSING
    L_min: Maybe = MISSING
    b: Maybe = MISSING


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    cassette_id: Optional[str] = None
    cassette_index: Maybe = MISSING
    entry_offset: Maybe = MISSING
    exit_offset: Maybe = MISSING          # None == declared null == terminal
    capture_offset_vec: Maybe = MISSING
    exclusion_centre: Maybe = MISSING     # required explicitly for D_N (D7)
    rho: Maybe = MISSING
    unresolved_occupancy_fraction: Maybe = MISSING  # required under shell bound (D4)


@dataclass(frozen=True)
class DepEdge:
    from_node: str
    to_node: str
    kind: DepEdgeKind


@dataclass(frozen=True)
class CassettePolicy:
    """Cassette-mode policy. Every field is REQUIRED (MISSING is rejected) except
    tau_spacer and pose_marginalization_max_level, which are guard thresholds
    whose defaults are conservative (decisions D3 and D5)."""

    topology_mode: Maybe = MISSING
    junction_model: Maybe = MISSING
    engagement_order_policy: Maybe = MISSING
    unresolved_upstream_policy: Maybe = MISSING
    engaged_pose_resolution: Maybe = MISSING
    composite_density_method: Maybe = MISSING
    tau_spacer: float = 0.25
    pose_marginalization_max_level: int = 4


@dataclass(frozen=True)
class CassetteSpec:
    id: str
    root_anchor_id: str
    ordered_modules: Sequence[str] = ()
    ordered_segments: Sequence[str] = ()
    #: Required iff engagement_order_policy == EXPLICIT_PARTIAL_ORDER (D8).
    explicit_partial_order: Maybe = MISSING


@dataclass(frozen=True)
class CassetteConfig:
    id: str
    policy: CassettePolicy
    cassettes: Sequence[CassetteSpec] = ()
    anchors: Sequence[AnchorSpec] = ()
    modules: Sequence[ModuleSpec] = ()
    tethers: Sequence[TetherSpec] = ()
    dep_edges: Sequence[DepEdge] = field(default_factory=tuple)
