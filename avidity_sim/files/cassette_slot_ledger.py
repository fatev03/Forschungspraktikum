"""GOTNE Phase 2 slot ledger (v0.3.1): the caller-side slot-triage artefact.

SCOPE (cassette-slots specification, Colab-visible triage artefacts)
--------------------------------------------------------------------
Caller-side only. This module reads finished Phase 2 results and the retained
CassetteSlotBinding and arranges them for triage. It evaluates nothing, vetoes
nothing, and is imported by no evaluation module. Like cassette_slots it is a
sibling of the chain, never a link in it: it may read cassette_schema,
cassette_slots, cassette_state and status, and it MUST NOT import
cassette_frames, cassette_budget, cassette_closure or cassette_node. The
EvaluationResult and StateCertificate it reads are unchanged, and no identifier
is recomputed: state_result_id, node_result_id, slot_binding_hash,
config_identity_hash and context_hash are copied verbatim from their producers.

ROW ORDER
---------
Exactly one row per slot, in SLOT_IDS order, always three rows. Order comes
from the binding, never from the projected EngagementState, which stores its
assignments ascending by module_id and therefore carries no slot order. Row
order never depends on status, reason or any other value, and rows are never
sorted, pooled, deduplicated or omitted. An UNENGAGED slot keeps its row with
node_presence ABSENT_UNENGAGED; absence is never encoded by a missing row.

FAILURE CLASSES
---------------
The four classes fixed by the Phase 2 contract stay separable. CONTRACT_INVALID
is declared here for completeness and is never returned by the classifier: a
contract-invalid call raises and yields no result object, so no row can exist
for it. The classifier is total over the statuses Phase 2 produces -- VALID,
INFEASIBLE, UNREACHABLE, DEGENERATE and NOT_EVALUATED -- and raises for
BLOCKED, NUMERIC_FAILURE and APPROXIMATION_REQUIRED rather than folding a
status Phase 2 has no source for into a neighbouring class.

READING
-------
A row records what was declared and what the deterministic Phase 2 checks
returned for it. NOT_VETOED carries exactly the scope of §20.7.3 N0: it is not
observed engagement, binding, occupancy, simultaneity, persistence or
probability, and a vetoed row is not a real-world impossibility (§20.7.2 C8,
C9). Nothing here ranks, scores, weights or orders candidates by value.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Sequence, Tuple

from .cassette_schema import CassetteConfig
from .cassette_slots import SLOT_IDS, CassetteSlotBinding, SlotId, slot_binding_hash
from .cassette_state import EngagementLabel, StateCertificate
from .status import EvaluationResult, Status

__all__ = [
    "LEDGER_DOCUMENT_TYPE",
    "FailureClass",
    "NodePresence",
    "SlotLedgerRow",
    "SlotLedger",
    "classify_failure",
    "build_slot_ledger",
]

LEDGER_DOCUMENT_TYPE = "cassette_slot_ledger/1"


class FailureClass(str, Enum):
    """The four Phase 2 classes plus the non-vetoed case, kept separable."""

    #: Declared for completeness; never returned, because a contract-invalid
    #: call raises and produces no result object to build a row from.
    CONTRACT_INVALID = "CONTRACT_INVALID"
    INFEASIBLE_DECLARED_INPUT = "INFEASIBLE_DECLARED_INPUT"
    UNREACHABLE_GEOMETRIC_VETO = "UNREACHABLE_GEOMETRIC_VETO"
    UNEVALUABLE = "UNEVALUABLE"
    NOT_VETOED = "NOT_VETOED"


class NodePresence(str, Enum):
    """Why a row does or does not carry node fields. Absence is always named."""

    PRESENT = "PRESENT"
    ABSENT_UNENGAGED = "ABSENT_UNENGAGED"
    ABSENT_NOT_SUPPLIED = "ABSENT_NOT_SUPPLIED"


#: Total over the statuses Phase 2 produces; anything else raises.
_CLASS_OF_STATUS = {
    Status.VALID: FailureClass.NOT_VETOED,
    Status.INFEASIBLE: FailureClass.INFEASIBLE_DECLARED_INPUT,
    Status.UNREACHABLE: FailureClass.UNREACHABLE_GEOMETRIC_VETO,
    Status.DEGENERATE: FailureClass.UNEVALUABLE,
    Status.NOT_EVALUATED: FailureClass.UNEVALUABLE,
}


def classify_failure(status: Status) -> FailureClass:
    """The failure class of a Phase 2 status. No fallback and no folding."""
    if not isinstance(status, Status):
        raise TypeError(f"status must be a Status, got {type(status).__qualname__}")
    if status not in _CLASS_OF_STATUS:
        raise ValueError(
            f"Phase 2 has no source for status {status.value}; it has no failure class here"
        )
    return _CLASS_OF_STATUS[status]


@dataclass(frozen=True)
class SlotLedgerRow:
    """One slot. Every field is copied from a declaration or a finished result."""

    slot: SlotId
    module_id: str
    label: EngagementLabel
    target_id: Optional[str]
    cassette_index: int
    failure_class: FailureClass
    state_result_id: Optional[str]
    state_status: Status
    state_status_reason: str
    node_presence: NodePresence
    node_object_id: Optional[str]
    node_result_id: Optional[str]
    node_status: Optional[Status]
    node_status_reason: Optional[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "slot": self.slot.value,
            "module_id": self.module_id,
            "label": self.label.value,
            "target_id": self.target_id,
            "cassette_index": self.cassette_index,
            "failure_class": self.failure_class.value,
            "state_result_id": self.state_result_id,
            "state_status": self.state_status.value,
            "state_status_reason": self.state_status_reason,
            "node_presence": self.node_presence.value,
            "node_object_id": self.node_object_id,
            "node_result_id": self.node_result_id,
            "node_status": None if self.node_status is None else self.node_status.value,
            "node_status_reason": self.node_status_reason,
        }


@dataclass(frozen=True)
class SlotLedger:
    """Exactly three rows in SLOT_IDS order, plus the per-binding identities."""

    rows: Tuple[SlotLedgerRow, ...]
    slot_binding_hash: str
    state_result_id: Optional[str]
    config_identity_hash: Optional[str]
    context_hash: Optional[str]
    certificate_present: bool

    def __post_init__(self) -> None:
        if tuple(row.slot for row in self.rows) != SLOT_IDS:
            raise ValueError(
                f"a ledger carries exactly one row per slot in {[s.value for s in SLOT_IDS]} order"
            )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "document_type": LEDGER_DOCUMENT_TYPE,
            "order": [s.value for s in SLOT_IDS],
            "slot_binding_hash": self.slot_binding_hash,
            "state_result_id": self.state_result_id,
            "config_identity_hash": self.config_identity_hash,
            "context_hash": self.context_hash,
            "certificate_present": self.certificate_present,
            "rows": [row.as_dict() for row in self.rows],
        }

    def to_json_bytes(self) -> bytes:
        """Canonical bytes. sort_keys orders object keys only; the rows array
        and the order array keep the slot order they were built in."""
        return json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")


def _node_index(
    node_results: Sequence[EvaluationResult], module_ids: Tuple[str, ...]
) -> Dict[str, EvaluationResult]:
    index: Dict[str, EvaluationResult] = {}
    for position, node in enumerate(node_results):
        if not isinstance(node, EvaluationResult):
            raise TypeError(
                f"node_results[{position}] must be an EvaluationResult, "
                f"got {type(node).__qualname__}"
            )
        if node.object_kind != "NODE":
            raise ValueError(
                f"node_results[{position}] has object_kind {node.object_kind!r}, expected 'NODE'"
            )
        if node.object_id not in module_ids:
            raise ValueError(
                f"node_results[{position}] names module {node.object_id!r}, which no slot binds"
            )
        if node.object_id in index:
            raise ValueError(f"two node results for module {node.object_id!r}")
        index[node.object_id] = node
    return index


def build_slot_ledger(
    binding: CassetteSlotBinding,
    cfg: CassetteConfig,
    state_result: EvaluationResult,
    node_results: Sequence[EvaluationResult] = (),
    certificate: Optional[StateCertificate] = None,
) -> SlotLedger:
    """Arrange finished Phase 2 results into one slot ledger. Pure and read-only.

    Slot order comes from ``binding``; ``cfg`` supplies each slot's 1-based
    cassette index. ``node_results`` holds zero to three NODE results, matched
    to slots by object_id. ``certificate``, when given, must belong to
    ``state_result`` and supplies config_identity_hash and context_hash.
    """
    if not isinstance(binding, CassetteSlotBinding):
        raise TypeError(f"binding must be a CassetteSlotBinding, got {type(binding).__qualname__}")
    if not isinstance(cfg, CassetteConfig):
        raise TypeError(f"cfg must be a CassetteConfig, got {type(cfg).__qualname__}")
    if not isinstance(state_result, EvaluationResult):
        raise TypeError(
            f"state_result must be an EvaluationResult, got {type(state_result).__qualname__}"
        )
    if state_result.object_kind != "STATE":
        raise ValueError(
            f"state_result has object_kind {state_result.object_kind!r}, expected 'STATE'"
        )
    if not isinstance(node_results, (list, tuple)):
        raise TypeError(
            f"node_results must be a list or tuple, got {type(node_results).__qualname__}"
        )
    if len(node_results) > len(SLOT_IDS):
        raise ValueError(
            f"at most {len(SLOT_IDS)} node results, got {len(node_results)}"
        )
    if certificate is not None:
        if not isinstance(certificate, StateCertificate):
            raise TypeError(
                f"certificate must be a StateCertificate, got {type(certificate).__qualname__}"
            )
        if certificate.state_result.result_id != state_result.result_id:
            raise ValueError("certificate does not belong to this state_result")

    assignments = binding.ordered_assignments()
    module_ids = tuple(a.module_id for a in assignments)
    ordered = tuple(cfg.cassettes[0].ordered_modules)
    missing = [m for m in module_ids if m not in ordered]
    if missing:
        raise ValueError(f"modules not in the cassette: {missing}")
    nodes = _node_index(node_results, module_ids)
    state_class = classify_failure(state_result.status)

    rows = []
    for assignment in assignments:
        node = nodes.get(assignment.module_id)
        if node is not None:
            presence = NodePresence.PRESENT
        elif assignment.label is EngagementLabel.UNENGAGED:
            presence = NodePresence.ABSENT_UNENGAGED
        else:
            presence = NodePresence.ABSENT_NOT_SUPPLIED
        rows.append(
            SlotLedgerRow(
                slot=assignment.slot,
                module_id=assignment.module_id,
                label=assignment.label,
                target_id=assignment.target_id,
                # 1-based, the convention of ModuleSpec.cassette_index and of
                # EffectiveAnchor.ancestor_module_cassette_index.
                cassette_index=ordered.index(assignment.module_id) + 1,
                # The row's class is the node's own when a node result exists,
                # otherwise the state's; neither is substituted for the other.
                failure_class=(
                    state_class if node is None else classify_failure(node.status)
                ),
                state_result_id=state_result.result_id,
                state_status=state_result.status,
                state_status_reason=state_result.status_reason,
                node_presence=presence,
                node_object_id=None if node is None else node.object_id,
                node_result_id=None if node is None else node.result_id,
                node_status=None if node is None else node.status,
                node_status_reason=None if node is None else node.status_reason,
            )
        )

    return SlotLedger(
        rows=tuple(rows),
        slot_binding_hash=slot_binding_hash(binding),
        state_result_id=state_result.result_id,
        config_identity_hash=None if certificate is None else certificate.config_identity_hash,
        context_hash=None if certificate is None else certificate.context_hash,
        certificate_present=certificate is not None,
    )
