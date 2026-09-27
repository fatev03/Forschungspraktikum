"""GOTNE (v0.3.1): Phase 1c schema and pure structural validation for
LINEAR_ORDERED_CASSETTE, plus Phase 2: the deterministic state-admissibility
and geometric-veto layer (engagement state and context, effective anchors,
span budgets, chain closure, evaluate_state, the node gate and veto
propagation). Contains no probability, density or interval evaluation; a
VALID result is a state or node the Phase 2 checks do not veto, nothing more.
Phases 4 and 5 are not implemented here."""

__version__ = "0.3.1-phase2"

from .cassette_schema import (  # noqa: F401
    MISSING,
    AnchorSpec,
    CassetteConfig,
    CassettePolicy,
    CassetteSpec,
    CompositeDensityMethod,
    DepEdge,
    DepEdgeKind,
    EngagedPoseResolution,
    EngagementOrderPolicy,
    JunctionModel,
    ModuleSpec,
    TetherSpec,
    TopologyMode,
    UnresolvedUpstreamPolicy,
)
from .cassette_budget import (  # noqa: F401
    BudgetBreakdown,
    BudgetElement,
    BudgetElementKind,
    SpanBasis,
    cassette_contour_budget,
)
from .cassette_closure import (  # noqa: F401
    Tri,
    chain_closure_feasible,
    evaluate_state,
)
from .cassette_frames import (  # noqa: F401
    ROOT,
    EffectiveAnchor,
    cassette_effective_anchor,
)
from .cassette_node import (  # noqa: F401
    NodeReason,
    evaluate_node,
    propagate_state_veto,
)
from .cassette_state import (  # noqa: F401
    EngagementLabel,
    EngagementState,
    EvaluationContext,
    ModuleAssignment,
    NumericalTolerances,
    StateCertificate,
    StateReason,
    TargetContext,
    TargetGeometry,
    UnsupportedGeometryError,
    issue_state_certificate,
)
from .cassette_topology import (  # noqa: F401
    GEOMETRY_PRESENCE_ASSUMPTION,
    Code,
    Reason,
    validate_cassette_config,
    validate_cassette_identity_admissibility,
    validate_cassette_order_constraints,
    validate_cassette_policy_fields,
    validate_cassette_topology,
)
from .identity import (  # noqa: F401
    CANONICAL_FORM_VERSION,
    CanonicalizationError,
    cache_key,
    config_identity_hash,
    context_identity_hash,
    noncanonical_values,
    state_identity_hash,
)
from .mode_applicability import (  # noqa: F401
    ModeApplicability,
    applicability_marker,
    mode_applicability,
)
from .status import (  # noqa: F401
    METHOD_VERSION,
    DiagnosticRecord,
    EvaluationResult,
    Exactness,
    Provenance,
    Severity,
    Status,
    apply_status_field_pattern,
)

#: Decision record A (AP-1, AP-2): the exact package-level public surface, the
#: 39 Phase 1c names plus the 27 Phase 2 names of the allowlist. It is asserted by
#: PurityTests.test_public_api_allowlist. Helpers and later-seam APIs are
#: reachable only through their submodules.
__all__ = [
    # Phase 1c
    "MISSING",
    "AnchorSpec",
    "CassetteConfig",
    "CassettePolicy",
    "CassetteSpec",
    "CompositeDensityMethod",
    "DepEdge",
    "DepEdgeKind",
    "EngagedPoseResolution",
    "EngagementOrderPolicy",
    "JunctionModel",
    "ModuleSpec",
    "TetherSpec",
    "TopologyMode",
    "UnresolvedUpstreamPolicy",
    "GEOMETRY_PRESENCE_ASSUMPTION",
    "Code",
    "Reason",
    "validate_cassette_config",
    "validate_cassette_identity_admissibility",
    "validate_cassette_order_constraints",
    "validate_cassette_policy_fields",
    "validate_cassette_topology",
    "CANONICAL_FORM_VERSION",
    "CanonicalizationError",
    "cache_key",
    "config_identity_hash",
    "noncanonical_values",
    "ModeApplicability",
    "applicability_marker",
    "mode_applicability",
    "METHOD_VERSION",
    "DiagnosticRecord",
    "EvaluationResult",
    "Exactness",
    "Provenance",
    "Severity",
    "Status",
    "apply_status_field_pattern",
    # Phase 2, cassette_state
    "EngagementLabel",
    "ModuleAssignment",
    "EngagementState",
    "TargetGeometry",
    "TargetContext",
    "NumericalTolerances",
    "EvaluationContext",
    "StateReason",
    "StateCertificate",
    "UnsupportedGeometryError",
    "issue_state_certificate",
    "state_identity_hash",
    "context_identity_hash",
    # Phase 2, cassette_frames
    "ROOT",
    "EffectiveAnchor",
    "cassette_effective_anchor",
    # Phase 2, cassette_budget
    "SpanBasis",
    "BudgetElementKind",
    "BudgetElement",
    "BudgetBreakdown",
    "cassette_contour_budget",
    # Phase 2, cassette_closure
    "Tri",
    "chain_closure_feasible",
    "evaluate_state",
    # Phase 2, cassette_node
    "NodeReason",
    "evaluate_node",
    "propagate_state_veto",
]
