"""analytic_proxy: conditional weights and normalized scenario fractions over
serialized GOTNE Phase 2 states.

An isolated, standard-library-only prototype. It consumes public, serialized
Phase 2 outputs plus caller-supplied scenario factors, and produces scenario
summaries. It is not a predictor of any physical, chemical or biological
quantity, and it re-derives no Phase 2 decision. See core.py for the contract.
"""

from .core import (
    SCHEMA_VERSION,
    ExclusionRecord,
    ScenarioParameters,
    ScenarioSummary,
    StateInput,
    StateWeight,
    compute_state_weights,
    eligible_states,
    normalize_weights,
    summarize_scenario,
)

__all__ = [
    "SCHEMA_VERSION",
    "ScenarioParameters",
    "StateInput",
    "ExclusionRecord",
    "StateWeight",
    "ScenarioSummary",
    "eligible_states",
    "compute_state_weights",
    "normalize_weights",
    "summarize_scenario",
]
