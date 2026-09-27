"""Canonical identity hashing for GOTNE configs and cache keys.

Decision D10 (§11.8 v0.3): topology_mode is a first-class component of both the
config identity hash and the cache key. Two configs differing only in
topology_mode hash differently and share no cache entry. Shielding-based cache
sharing is PROHIBITED in v1; shielding_ancestor must never appear in a key
(MNH28), which is why this function does not accept it.

CANONICAL FORM (remediation B4)
-------------------------------
The projection is TYPE-TAGGED and therefore injective over the supported value
domain: every value becomes [tag, ...payload]. Consequences:
  - MISSING, None and the string "__MISSING__" are three distinct values (D7);
  - an Enum member and a plain string with the same text are distinct, so a
    config whose topology_mode is the string "LINEAR_ORDERED_CASSETTE" can never
    share an identity with a real cassette config (MNH21);
  - dataclass type names are part of the identity.
There is NO repr()/str() fallback. Unsupported types (unordered collections,
bytes, arbitrary objects) raise CanonicalizationError: a repr may embed a memory
address or depend on PYTHONHASHSEED, which silently breaks T78 determinism.

PHASE 2 STATE IDENTITY (decision record rev. 3, H / AP-20 / AP-27)
------------------------------------------------------------------
state_identity_hash, context_identity_hash and tolerance_identity_hash are
domain-separated digests over the same canonical form. None of them feeds
config_identity_hash. Their argument types live in cassette_state, which
imports this module, so they import it at call time.

PURE: canonical serialization plus hashlib. No geometry, no numerics.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any, List, Optional, Sequence, Tuple

from .cassette_schema import CassetteConfig, Missing, TopologyMode

__all__ = [
    "CANONICAL_FORM_VERSION",
    "CanonicalizationError",
    "canonical_form",
    "noncanonical_values",
    "config_identity_hash",
    "cache_key",
    "state_identity_hash",
    "context_identity_hash",
    "tolerance_identity_hash",
    "result_identity",
]

#: Bumped because the projection changed; old digests are not comparable.
CANONICAL_FORM_VERSION = "gotne-canon-2"


class CanonicalizationError(TypeError):
    """A value has no deterministic, injective canonical form."""


def _json(payload: Any) -> str:
    # No `default=`: anything that is not already canonical raises.
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


_INVALID = ["invalid"]  # placeholder used only while collecting failures


def _child(path: str, name: str) -> str:
    return name if not path else f"{path}.{name}"


def _canon(obj: Any, path: str, errors: Optional[List[Tuple[str, str]]]) -> Any:
    """THE canonicalizer. With errors=None it raises on the first value that
    has no canonical form; with a list it records (path, type name) for every
    such value and keeps going. Both modes share every branch, so the
    admissibility gate (P3) and config_identity_hash can never disagree."""
    if isinstance(obj, Missing):
        return ["missing"]
    if obj is None:
        return ["null"]
    if isinstance(obj, Enum):  # before str: str-Enums are str instances
        return ["enum", type(obj).__qualname__, _canon(obj.value, path, errors)]
    if isinstance(obj, bool):  # before int: bool is an int subclass
        return ["bool", obj]
    if isinstance(obj, int):
        return ["int", str(int(obj))]
    if isinstance(obj, float):
        return ["float", float(obj).hex()]  # exact, and finite-JSON-safe for nan/inf
    if isinstance(obj, str):
        return ["str", str.__str__(obj)]
    if is_dataclass(obj) and not isinstance(obj, type):
        return [
            "dataclass",
            type(obj).__qualname__,
            [
                [f.name, _canon(getattr(obj, f.name), _child(path, f.name), errors)]
                for f in sorted(fields(obj), key=lambda x: x.name)
            ],
        ]
    if isinstance(obj, dict):
        items = []
        for index, (k, v) in enumerate(obj.items()):
            key = _canon(k, f"{path}[key#{index}]", errors)
            if key is _INVALID:
                label = f"key#{index}"
            elif key[0] == "str":
                label = json.dumps(key[1])
            else:
                label = _json(key)
            items.append([key, _canon(v, f"{path}[{label}]", errors)])
        items.sort(key=lambda kv: _json(kv[0]))
        return ["dict", items]
    if isinstance(obj, (list, tuple)):
        return ["seq", [_canon(x, f"{path}[{i}]", errors) for i, x in enumerate(obj)]]
    type_name = type(obj).__qualname__
    if errors is None:
        raise CanonicalizationError(
            f"no canonical form for type {type_name} at {path or '<root>'}; "
            "declare the value as a sequence, mapping, scalar, enum or dataclass"
        )
    errors.append((path or "<root>", type_name))
    return _INVALID


def canonical_form(obj: Any) -> Any:
    """Deterministic, type-tagged, JSON-serializable projection. Raises
    CanonicalizationError for any type without a canonical form."""
    return _canon(obj, "", None)


def noncanonical_values(obj: Any) -> List[Tuple[str, str]]:
    """Every (path, type name) that canonical_form would reject, in
    deterministic traversal order. Empty iff canonical_form(obj) succeeds."""
    errors: List[Tuple[str, str]] = []
    _canon(obj, "", errors)
    return errors


def _digest(payload: Any) -> str:
    text = _json([CANONICAL_FORM_VERSION, payload])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def config_identity_hash(cfg: CassetteConfig) -> str:
    """geometry_hash in the sense of §11.8. Includes topology_mode."""
    return _digest(canonical_form(cfg))


def cache_key(
    node_id: str,
    state_hash: str,
    policy_hash: str,
    geometry_hash: str,
    tolerance_hash: str,
    method_version: str,
    topology_mode: TopologyMode,
) -> str:
    """§11.8 (v0.3). Every component is required and type-checked; nothing is
    coerced. shielding_ancestor is deliberately absent from the signature
    (MNH28)."""
    components = {
        "node_id": node_id,
        "state_hash": state_hash,
        "policy_hash": policy_hash,
        "geometry_hash": geometry_hash,
        "tolerance_hash": tolerance_hash,
        "method_version": method_version,
    }
    for name, value in components.items():
        if not isinstance(value, str) or isinstance(value, Enum):
            raise TypeError(f"cache_key component {name} must be str, got {type(value).__qualname__}")
    if not isinstance(topology_mode, TopologyMode):
        raise TypeError(
            "cache_key topology_mode must be a TopologyMode member, got "
            f"{type(topology_mode).__qualname__}"
        )
    return _digest([canonical_form(v) for v in components.values()] + [canonical_form(topology_mode)])


def state_identity_hash(state: Any) -> str:
    """AP-27. Hashes only the ENGAGED (module_id, target_id) pairs in ascending
    module_id, so an explicit UNENGAGED assignment and an omitted module hash
    identically. The state carries no coordinates."""
    from .cassette_state import EngagementState

    if not isinstance(state, EngagementState):
        raise TypeError(
            f"state_identity_hash expects an EngagementState, got {type(state).__qualname__}"
        )
    pairs = sorted((a.module_id, a.target_id) for a in state.engaged_assignments())
    return _digest(["state_identity", canonical_form(pairs)])


def context_identity_hash(context: Any) -> str:
    """AP-20. Hashes every target (id, site, orientation) and the tolerances."""
    from .cassette_state import EvaluationContext

    if not isinstance(context, EvaluationContext):
        raise TypeError(
            f"context_identity_hash expects an EvaluationContext, got {type(context).__qualname__}"
        )
    return _digest(["context_identity", canonical_form(context)])


def tolerance_identity_hash(tolerances: Any) -> str:
    """OQ-2. The tolerance_hash component of cache_key."""
    from .cassette_state import NumericalTolerances

    if not isinstance(tolerances, NumericalTolerances):
        raise TypeError(
            "tolerance_identity_hash expects a NumericalTolerances, got "
            f"{type(tolerances).__qualname__}"
        )
    return _digest(["tolerance_identity", canonical_form(tolerances)])


#: AP-9: result_id prefixes. CONFIG results keep result_id None.
_RESULT_PREFIX = {"STATE": "st", "NODE": "nd"}


def result_identity(object_kind: str, components: Sequence[Any]) -> str:
    """AP-9 / AP-20: "<prefix>-<64 hex>" over the canonical form of the
    ordered components. No counter, clock, randomness or truncation, so equal
    components give equal ids in every process."""
    if object_kind not in _RESULT_PREFIX:
        raise ValueError(f"result_identity covers STATE and NODE results, got {object_kind!r}")
    if not isinstance(components, (list, tuple)):
        raise TypeError("components must be a list or tuple")
    digest = _digest(["result_identity", object_kind, [canonical_form(c) for c in components]])
    return f"{_RESULT_PREFIX[object_kind]}-{digest}"
