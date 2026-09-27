"""GOTNE Phase 2 slots (v0.3.1): the ordered three-slot binding seam.

SCOPE (cassette-slots specification)
------------------------------------
A sibling of the chain head, never a link in it. The acyclic Phase 2 chain
    cassette_state -> cassette_frames -> cassette_budget -> cassette_closure -> cassette_node
is untouched: nothing here is an argument to any of the five fixed Phase 2
signatures, and no chain module imports this one. The seam sits upstream of
stage 1 of evaluate_state. It declares an ordered slot binding, validates it,
and projects it to an ordinary EngagementState which the unchanged kernel then
evaluates.

ORDERED SLOTS
-------------
CassetteSlotBinding has exactly three named fields, slot_1, slot_2 and slot_3.
There is no sequence field, so there is no position to sort, pool, deduplicate,
shorten or pad, and arity three is fixed by the type rather than by a length
check. Each SlotAssignment restates its own slot, and a value whose slot
differs from its field name is refused. Slot identity is the name; slot order
is SLOT_IDS. slot_1 is not a default, primary, preferred or fallback slot, and
no slot is filled when a caller declares none.

CONSTRUCTION IS CONFIG-FREE
---------------------------
Like EngagementState, a binding does not know a cassette. Whether a module_id
belongs to the cassette is config-relative and is checked by
validate_slot_binding, not at construction (OQ-4). Wrong types raise
TypeError; declared values outside their domain raise ValueError. Nothing is
sorted, completed, repaired or defaulted at any point.

PROJECTION AND C1-C4
--------------------
project_engagement_state emits one explicit ModuleAssignment per slot,
including UNENGAGED ones, so nothing is defaulted. EngagementState then stores
its assignments ascending by module_id, so the projection loses slot order by
design; that loss is why a caller retains the binding rather than recovering it
from a state or a result. C1-C4 are untouched, because the projection happens
before evaluation and the kernel still receives an EngagementState it does not
mutate, complete, repair, reorder, infer, normalize or replace.

IDENTITY
--------
slot_binding_hash is a domain-separated digest over the same canonical form the
rest of the package uses. It participates in neither state_identity_hash nor
context_identity_hash: both feed result_identity, so a new component there
would change every existing STATE and NODE result_id. state_identity_hash
(AP-27) hashes only the ENGAGED (module_id, target_id) pairs in ascending
module_id, so slot order and slot-level UNENGAGED declarations are outside the
hashed projection by existing design. Two distinct bindings that project to the
same ENGAGED pair set therefore share a result_id, which is correct: the
kernel's verdict does not depend on slot order.

May import: cassette_schema, cassette_state, cassette_topology, identity,
status. It MUST NOT import cassette_frames, cassette_budget, cassette_closure
or cassette_node.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from . import cassette_topology
from .cassette_schema import CassetteConfig
from .cassette_state import EngagementLabel, EngagementState, ModuleAssignment, StateReason
from .identity import CANONICAL_FORM_VERSION, canonical_form
from .status import Status

__all__ = [
    "SlotId",
    "SLOT_IDS",
    "SlotAssignment",
    "CassetteSlotBinding",
    "project_engagement_state",
    "validate_slot_binding",
    "slot_binding_hash",
]

#: Domain separation tag; never a result_identity prefix.
SLOT_BINDING_OBJECT_KIND = "slot_binding_identity"


class SlotId(str, Enum):
    """Exactly three named slot identities. Order is SLOT_IDS, never a list
    position. A member's value is also its field name on CassetteSlotBinding."""

    SLOT_1 = "slot_1"
    SLOT_2 = "slot_2"
    SLOT_3 = "slot_3"


#: The declared slot order. Nothing derives an order from any other source.
SLOT_IDS: Tuple[SlotId, SlotId, SlotId] = (SlotId.SLOT_1, SlotId.SLOT_2, SlotId.SLOT_3)


def _require_identifier(value: object, what: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{what} must be a plain str, got {type(value).__qualname__}")
    if value == "":
        raise ValueError(f"{what} must be non-empty")


def _ident_ok(value: object) -> bool:
    return type(value) is str and value != ""


@dataclass(frozen=True)
class SlotAssignment:
    """One named slot. label/target_id agreement follows OQ-1 exactly as
    ModuleAssignment does: ENGAGED requires a non-empty plain str target_id,
    UNENGAGED requires None. Cassette membership is not checked here."""

    slot: SlotId
    module_id: str
    label: EngagementLabel
    target_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.slot, SlotId):
            raise TypeError(
                f"SlotAssignment.slot must be a SlotId, got {type(self.slot).__qualname__}"
            )
        _require_identifier(self.module_id, "SlotAssignment.module_id")
        if not isinstance(self.label, EngagementLabel):
            raise TypeError(
                "SlotAssignment.label must be an EngagementLabel, got "
                f"{type(self.label).__qualname__}"
            )
        # ValueError for every bad ENGAGED target, including a non-str: this
        # mirrors ModuleAssignment exactly, so the projection cannot widen or
        # narrow what OQ-1 already refuses.
        if self.label is EngagementLabel.ENGAGED and not _ident_ok(self.target_id):
            raise ValueError(
                f"ENGAGED slot {self.slot.value!r} requires a non-empty plain str target_id"
            )
        if self.label is EngagementLabel.UNENGAGED and self.target_id is not None:
            raise ValueError(f"UNENGAGED slot {self.slot.value!r} must have target_id None")


@dataclass(frozen=True)
class CassetteSlotBinding:
    """Exactly three ordered, non-interchangeable named slots. There is no
    sequence field: the three names are the arity and the order."""

    slot_1: SlotAssignment
    slot_2: SlotAssignment
    slot_3: SlotAssignment

    def __post_init__(self) -> None:
        for slot_id in SLOT_IDS:
            assignment = getattr(self, slot_id.value)
            if not isinstance(assignment, SlotAssignment):
                raise TypeError(
                    f"CassetteSlotBinding.{slot_id.value} must be a SlotAssignment, got "
                    f"{type(assignment).__qualname__}"
                )
            if assignment.slot is not slot_id:
                raise ValueError(
                    f"CassetteSlotBinding.{slot_id.value} carries slot "
                    f"{assignment.slot.value!r}; a slot record must name its own field"
                )
        module_ids = [getattr(self, slot_id.value).module_id for slot_id in SLOT_IDS]
        duplicates = sorted({m for m in module_ids if module_ids.count(m) > 1})
        if duplicates:
            raise ValueError(f"duplicate module_id across slots: {duplicates}")

    def ordered_assignments(self) -> Tuple[SlotAssignment, ...]:
        """The three assignments in SLOT_IDS order. Derived, never stored."""
        return tuple(getattr(self, slot_id.value) for slot_id in SLOT_IDS)


def project_engagement_state(binding: CassetteSlotBinding) -> EngagementState:
    """The EngagementState this binding declares. Pure; reads no config.

    One explicit ModuleAssignment per slot, including UNENGAGED ones, so no
    module is defaulted. EngagementState stores them ascending by module_id,
    so slot order does not survive the projection.
    """
    if not isinstance(binding, CassetteSlotBinding):
        raise TypeError(
            f"binding must be a CassetteSlotBinding, got {type(binding).__qualname__}"
        )
    return EngagementState(
        tuple(
            ModuleAssignment(a.module_id, a.label, a.target_id)
            for a in binding.ordered_assignments()
        )
    )


def validate_slot_binding(binding: CassetteSlotBinding, cfg: CassetteConfig) -> None:
    """Config-relative admissibility of the slot binding. Returns None.

    Raises ValueError when cfg is not VALID under Phase 1c, when the cassette
    does not have exactly three ordered modules, or when slot k does not name
    the module at cassette position k.

    It deliberately checks nothing else. A repeated target_id stays permitted
    (OQ-9), and every remaining defect -- an ENGAGED target absent from the
    context, down-closure under R_union, and the geometric gates -- belongs to
    the unchanged stages of evaluate_state and is not pre-empted here.
    """
    if not isinstance(binding, CassetteSlotBinding):
        raise TypeError(
            f"binding must be a CassetteSlotBinding, got {type(binding).__qualname__}"
        )
    if not isinstance(cfg, CassetteConfig):
        raise TypeError(f"cfg must be a CassetteConfig, got {type(cfg).__qualname__}")
    config_result = cassette_topology.validate_cassette_config(cfg)
    if config_result.status is not Status.VALID:
        raise ValueError(
            f"cfg is {config_result.status.value} ({config_result.status_reason}) under Phase 1c; "
            "no slot binding is defined"
        )
    ordered = tuple(cfg.cassettes[0].ordered_modules)
    if len(ordered) != len(SLOT_IDS):
        raise ValueError(
            f"{StateReason.STATE_INPUT_INVALID}: a slot binding requires exactly "
            f"{len(SLOT_IDS)} ordered modules, cassette has {len(ordered)}"
        )
    mismatched = [
        (slot_id.value, getattr(binding, slot_id.value).module_id, ordered[index])
        for index, slot_id in enumerate(SLOT_IDS)
        if getattr(binding, slot_id.value).module_id != ordered[index]
    ]
    if mismatched:
        raise ValueError(
            f"{StateReason.STATE_INPUT_INVALID}: slot k must name the module at cassette "
            f"position k; (slot, declared, expected) {mismatched}"
        )


def slot_binding_hash(binding: CassetteSlotBinding) -> str:
    """A domain-separated digest over the canonical form of the binding.

    Mirrors identity._digest deliberately rather than importing it, so this
    module depends on no private name. The shape must stay identical to the
    other domain-separated digests; tests pin that agreement.
    """
    if not isinstance(binding, CassetteSlotBinding):
        raise TypeError(
            f"binding must be a CassetteSlotBinding, got {type(binding).__qualname__}"
        )
    payload = [SLOT_BINDING_OBJECT_KIND, canonical_form(binding)]
    text = json.dumps(
        [CANONICAL_FORM_VERSION, payload],
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
