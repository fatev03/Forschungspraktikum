"""Mode applicability registry (audit item L11, test T55).

Base-suite tests that assume a topology LINEAR_ORDERED_CASSETTE forbids must be
reported as MODE_NOT_APPLICABLE. They must NOT be silently skipped and must NOT
be reported as PASS: a skipped test and a passing test are different claims, and
only the explicit marker records that the invariant was never exercised.

PURE: registry lookup only.
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping, Tuple

from .cassette_schema import TopologyMode

__all__ = [
    "ModeApplicability",
    "MODE_INCOMPATIBLE_BASE_TESTS",
    "mode_applicability",
    "applicability_marker",
]


class ModeApplicability(str, Enum):
    APPLICABLE = "APPLICABLE"
    MODE_NOT_APPLICABLE = "MODE_NOT_APPLICABLE"


#: test_id -> (mode it is incompatible with, reason)
MODE_INCOMPATIBLE_BASE_TESTS: Mapping[str, Tuple[TopologyMode, str]] = {
    # T12 exercises multiple independent surface anchors, which C1 forbids.
    "T12": (
        TopologyMode.LINEAR_ORDERED_CASSETTE,
        "base test assumes multiple surface anchors; invariant C1 permits exactly one",
    ),
}


def mode_applicability(test_id: str, mode: TopologyMode) -> ModeApplicability:
    if not isinstance(mode, TopologyMode):
        # A plain string would fail the identity check below and silently
        # report APPLICABLE for a mode-incompatible test.
        raise TypeError(f"mode must be a TopologyMode member, got {type(mode).__qualname__}")
    entry = MODE_INCOMPATIBLE_BASE_TESTS.get(test_id)
    if entry is not None and entry[0] is mode:
        return ModeApplicability.MODE_NOT_APPLICABLE
    return ModeApplicability.APPLICABLE


def applicability_marker(test_id: str, mode: TopologyMode) -> str:
    """Human-readable marker for the test harness report. Never the string
    'PASS' or 'SKIP'."""
    verdict = mode_applicability(test_id, mode)
    if verdict is ModeApplicability.APPLICABLE:
        return f"{test_id}: APPLICABLE under {mode.value}"
    reason = MODE_INCOMPATIBLE_BASE_TESTS[test_id][1]
    return f"{test_id}: MODE_NOT_APPLICABLE under {mode.value} ({reason})"
