"""GOTNE Phase 2 candidate batch (v0.3.1): sequential ordered-slot orchestration.

SCOPE (cassette-slots specification, candidate triage)
------------------------------------------------------
Caller-side orchestration above the kernel, never inside it. This module calls
the existing seams and the unchanged Phase 2 chain in their published order and
arranges what they return; it evaluates no geometry, decides no veto and
computes no identity of its own. Every identifier it reports is copied from the
producer that minted it.

Unlike cassette_slots and cassette_slot_ledger, this module does import the
evaluation chain -- that is its purpose. It MUST NOT import any Phase 4 or
Phase 5 module: composite_density, so3_grids, pose_marginalization,
shell_bounds or intervals.

CANDIDATE DECLARATIONS
----------------------
A candidate is a caller-supplied CandidateDeclaration carrying a candidate_id,
a CassetteSlotBinding and the Phase 2 inputs the kernel already requires. The
policy is declared explicitly rather than read off cfg, so nothing here is
inferred. Declarations are never synthesized, repaired, completed, normalized,
sorted, pooled, deduplicated or defaulted, and caller sequence order is the
report order. Duplicate candidate ids are refused before any candidate is
evaluated, so a batch either evaluates every candidate or none.

Evaluation is sequential and single-threaded by construction: one candidate is
finished before the next begins, in the order supplied.

PER-CANDIDATE PATH
------------------
  1 validate_slot_binding      config-relative admissibility of the binding
  2 project_engagement_state   the ordinary EngagementState the kernel takes
  3 evaluate_state             unchanged, four-argument
  4 issue_state_certificate    only for a VALID state
  5 evaluate_node              only for the ENGAGED slots of a certified state
  6 build_slot_ledger          the existing caller-side artefact
Steps 1-3 are the pre-evaluation boundary. A refusal there is contract-invalid:
it yields a DeclarationRefusal and no EvaluationResult is ever fabricated for
it. From step 4 on, an exception is a contract violation of the kernel itself
and propagates; it is not converted into a refusal record, because doing so
would silently absorb a defect the caller must see.

FAILURE CLASSES
---------------
The four classes stay separable across the batch. A DeclarationRefusal carries
CONTRACT_INVALID; every other class is carried by the SlotLedger rows, which
hold the INFEASIBLE, UNREACHABLE and UNEVALUABLE outcomes of the kernel. No
candidate is omitted from the report because it was refused or vetoed.

READING
-------
The report ranks, scores, counts, summarizes and prioritizes nothing. It is a
fixed-order collection of per-candidate records; any ordering a reader wants
beyond the caller's own sequence is outside this module. A non-vetoed entry
carries exactly the scope of §20.7.3 N0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Sequence, Tuple

from .cassette_closure import evaluate_state
from .cassette_node import evaluate_node
from .cassette_schema import CassetteConfig, CassettePolicy
from .cassette_slot_ledger import FailureClass, SlotLedger, build_slot_ledger
from .cassette_slots import (
    CassetteSlotBinding,
    project_engagement_state,
    slot_binding_hash,
    validate_slot_binding,
)
from .cassette_state import EngagementLabel, EvaluationContext, issue_state_certificate
from .status import Status

__all__ = [
    "BATCH_DOCUMENT_TYPE",
    "RefusalStage",
    "EntryKind",
    "CandidateDeclaration",
    "DeclarationRefusal",
    "CandidateEntry",
    "CandidateBatchReport",
    "evaluate_candidate_batch",
]

BATCH_DOCUMENT_TYPE = "cassette_candidate_batch/1"


class RefusalStage(str, Enum):
    """Where a declaration was refused, before any result object existed."""

    SLOT_BINDING = "SLOT_BINDING"
    PROJECTION = "PROJECTION"
    STATE_ENTRY = "STATE_ENTRY"


class EntryKind(str, Enum):
    """Whether an entry carries a ledger or a refusal. Never inferred from a null."""

    EVALUATED = "EVALUATED"
    DECLARATION_REFUSED = "DECLARATION_REFUSED"


def _require_identifier(value: object, what: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{what} must be a plain str, got {type(value).__qualname__}")
    if value == "":
        raise ValueError(f"{what} must be non-empty")


@dataclass(frozen=True)
class CandidateDeclaration:
    """One independent candidate. Every Phase 2 input is declared, not inferred."""

    candidate_id: str
    binding: CassetteSlotBinding
    cfg: CassetteConfig
    policy: CassettePolicy
    context: EvaluationContext

    def __post_init__(self) -> None:
        _require_identifier(self.candidate_id, "CandidateDeclaration.candidate_id")
        for name, cls in (
            ("binding", CassetteSlotBinding),
            ("cfg", CassetteConfig),
            ("policy", CassettePolicy),
            ("context", EvaluationContext),
        ):
            value = getattr(self, name)
            if not isinstance(value, cls):
                raise TypeError(
                    f"CandidateDeclaration.{name} must be a {cls.__name__}, "
                    f"got {type(value).__qualname__}"
                )


@dataclass(frozen=True)
class DeclarationRefusal:
    """A pre-evaluation refusal. No EvaluationResult exists for this candidate."""

    candidate_id: str
    stage: RefusalStage
    error_class: str
    detail: str

    @property
    def failure_class(self) -> FailureClass:
        return FailureClass.CONTRACT_INVALID

    def as_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "stage": self.stage.value,
            "error_class": self.error_class,
            "detail": self.detail,
            "failure_class": self.failure_class.value,
        }


@dataclass(frozen=True)
class CandidateEntry:
    """One candidate's outcome. Exactly one of ledger and refusal is set."""

    candidate_id: str
    slot_binding_hash: str
    entry_kind: EntryKind
    ledger: Optional[SlotLedger]
    refusal: Optional[DeclarationRefusal]

    def __post_init__(self) -> None:
        evaluated = self.entry_kind is EntryKind.EVALUATED
        if evaluated != (self.ledger is not None) or evaluated == (self.refusal is not None):
            raise ValueError(
                f"an {EntryKind.EVALUATED.value} entry carries a ledger and no refusal; a "
                f"{EntryKind.DECLARATION_REFUSED.value} entry carries a refusal and no ledger"
            )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "slot_binding_hash": self.slot_binding_hash,
            "entry_kind": self.entry_kind.value,
            "ledger": None if self.ledger is None else self.ledger.as_dict(),
            "refusal": None if self.refusal is None else self.refusal.as_dict(),
        }


@dataclass(frozen=True)
class CandidateBatchReport:
    """One entry per supplied candidate, in caller order. Nothing is summarized."""

    entries: Tuple[CandidateEntry, ...]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "document_type": BATCH_DOCUMENT_TYPE,
            "candidate_order": [entry.candidate_id for entry in self.entries],
            "entries": [entry.as_dict() for entry in self.entries],
        }

    def to_json_bytes(self) -> bytes:
        """Canonical bytes. sort_keys orders object keys only; the entries and
        candidate_order arrays keep the caller's sequence."""
        return json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")


def _refusal(candidate_id: str, stage: RefusalStage, exc: BaseException) -> DeclarationRefusal:
    return DeclarationRefusal(
        candidate_id=candidate_id,
        stage=stage,
        error_class=type(exc).__name__,
        detail=str(exc),
    )


def _evaluate_one(declaration: CandidateDeclaration) -> CandidateEntry:
    """One candidate, start to finish. Steps 1-3 may refuse; later steps may not."""
    binding, cfg = declaration.binding, declaration.cfg
    candidate_id = declaration.candidate_id
    digest = slot_binding_hash(binding)

    def refused(stage: RefusalStage, exc: BaseException) -> CandidateEntry:
        return CandidateEntry(
            candidate_id=candidate_id,
            slot_binding_hash=digest,
            entry_kind=EntryKind.DECLARATION_REFUSED,
            ledger=None,
            refusal=_refusal(candidate_id, stage, exc),
        )

    try:
        validate_slot_binding(binding, cfg)
    except (TypeError, ValueError) as exc:
        return refused(RefusalStage.SLOT_BINDING, exc)
    try:
        state = project_engagement_state(binding)
    except (TypeError, ValueError) as exc:
        return refused(RefusalStage.PROJECTION, exc)
    try:
        state_result = evaluate_state(state, cfg, declaration.policy, declaration.context)
    except (TypeError, ValueError) as exc:
        return refused(RefusalStage.STATE_ENTRY, exc)

    # Past the pre-evaluation boundary: an exception here is a kernel contract
    # violation and propagates rather than becoming a refusal record.
    if state_result.status is Status.VALID:
        certificate = issue_state_certificate(
            state_result, state, cfg, declaration.policy, declaration.context
        )
        node_results = tuple(
            evaluate_node(assignment.module_id, certificate, cfg, declaration.policy)
            for assignment in binding.ordered_assignments()
            if assignment.label is EngagementLabel.ENGAGED
        )
    else:
        certificate, node_results = None, ()

    return CandidateEntry(
        candidate_id=candidate_id,
        slot_binding_hash=digest,
        entry_kind=EntryKind.EVALUATED,
        ledger=build_slot_ledger(binding, cfg, state_result, node_results, certificate),
        refusal=None,
    )


def evaluate_candidate_batch(
    declarations: Sequence[CandidateDeclaration],
) -> CandidateBatchReport:
    """Evaluate every declaration, in the order supplied, and report all of them.

    Duplicate candidate ids are refused before the first candidate is touched.
    Every supplied candidate produces exactly one entry; none is omitted for
    being refused or vetoed, and none is ranked, scored, counted or reordered.
    """
    if not isinstance(declarations, (list, tuple)):
        raise TypeError(
            f"declarations must be a list or tuple, got {type(declarations).__qualname__}"
        )
    for position, declaration in enumerate(declarations):
        if not isinstance(declaration, CandidateDeclaration):
            raise TypeError(
                f"declarations[{position}] must be a CandidateDeclaration, "
                f"got {type(declaration).__qualname__}"
            )
    ids = [d.candidate_id for d in declarations]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate candidate_id: {duplicates}")
    # Sequential by construction: each candidate completes before the next starts.
    return CandidateBatchReport(tuple(_evaluate_one(d) for d in declarations))
