# StateResult `result_id` — deterministic identity contract

Normative closure for the accepted M1/M5/M10 amendment. **Proposal only.** No
code, test, notebook or source-of-truth file is modified.

Scope: auditability and serialization. Nothing else.

---

## 1. Existing identity mechanisms

From `identity.py` and `status.py`.

| Mechanism | Signature / value | Purpose |
|---|---|---|
| `CANONICAL_FORM_VERSION` | `"gotne-canon-2"` | prefixed into every digest; a bump makes old digests non-comparable |
| `canonical_form(obj)` | type-tagged injective projection | `["tag", …payload]` for every value |
| `noncanonical_values(obj)` | `List[(path, type_name)]` | admissibility gate sharing every branch with `canonical_form` |
| `CanonicalizationError` | `TypeError` subclass | raised for any type without a canonical form |
| `_json(payload)` | `json.dumps(..., sort_keys=True, separators=(",",":"), allow_nan=False)` | the single serialization form |
| `_digest(payload)` | `sha256(_json([CANONICAL_FORM_VERSION, payload]))`, hex | **private** |
| `config_identity_hash(cfg)` | `_digest(canonical_form(cfg))` | the `geometry_hash` of §11.8, includes `topology_mode` (D10) |
| `cache_key(...)` | 7 required, type-checked components | §11.8; `shielding_ancestor` deliberately absent (MNH28) |
| `EvaluationResult.result_id` | `Optional[str] = None` | field exists; `make_config_result` never sets it |

Properties already guaranteed by `canonical_form`, which this contract inherits
rather than re-establishes:

- `dict` items are canonicalized then **sorted** by their canonical key, so
  insertion order cannot reach a digest;
- `Enum` is tagged before `str`, so a str-Enum member and a same-text plain
  string are distinct (MNH21);
- `bool` is tagged before `int`; `float` uses `.hex()`, exact and finite-safe;
- dataclass fields are sorted by name and the type `__qualname__` is part of the
  identity;
- there is **no `repr()`/`str()` fallback** — an unsupported type raises rather
  than admitting a memory address or a `PYTHONHASHSEED`-dependent string. The
  docstring names T78 determinism as the reason.

### 1.1 Findings

**F1. A `StateResult` has no identifier today.** `result_id` defaults to `None`
and nothing assigns it. D6's serialized example shows `"st-0007"`, which reads as
a counter; a counter depends on process-local evaluation order and is therefore
excluded by the determinism rules.

**F2. `state_hash` is required but does not exist.** `cache_key` takes a
`state_hash` parameter and D6's `upstream_state` example carries `"hash": "…"`,
but no function produces either. This is the same gap recorded as an open item in
the spec-corrections note. The `result_id` rule needs it, so this contract
defines it once and both callers use it.

**F3. `_digest` is private.** A `result_id` rule that reuses it needs a public
entry point in the same module. Adding one is smaller than duplicating the digest
construction at a call site.

---

## 2. Chosen `result_id` contract

### 2.1 New pure helpers in `identity.py` **[PV1]**

```python
def state_identity_hash(state) -> str:
    """Canonical identity of a caller-supplied evaluation state.
    Fills the state_hash component of cache_key (§11.8) and the
    upstream_state["hash"] field of §10.7 / D6."""
    return _digest(canonical_form(state))


def result_identity_hash(components: Sequence[Any]) -> str:
    """Public digest over an already-ordered component list."""
    return _digest([canonical_form(c) for c in components])
```

Both are pure: canonical projection plus `hashlib`, no geometry, no numerics,
consistent with the module's stated purity contract.

### 2.2 The identifier

```
result_id = "st-" + result_identity_hash(COMPONENTS)[:32]
```

The `st-` prefix preserves the shape of D6's example while replacing its counter.
Truncation to 32 hex characters (128 bits) keeps the field readable; collision
resistance at this length is far beyond the number of states any evaluation
enumerates.

`COMPONENTS` is an **ordered** list, exactly:

| # | Component | Value |
|---|---|---|
| 1 | object kind | `"STATE"` |
| 2 | canonical configuration identity | `config_identity_hash(cfg)` |
| 3 | canonical supplied state | `state_identity_hash(S)` |
| 4 | method version | `METHOD_VERSION` |
| 5 | evaluation stage | `"L2_ADMISSIBILITY"` or `"L3_CLOSURE"` |
| 6 | status | `status.value` |
| 7 | reason | `status_reason` |
| 8 | declared assumptions | the declared sequence, in declared order |
| 9 | tolerance | `tolerance_hash` when stage is `L3_CLOSURE`, otherwise `None` |

Ordered, not a mapping: the list is fixed-length and positional, so no sort rule
is needed and no component can be silently dropped.

### 2.3 Why each exclusion holds structurally

| Excluded input | Why it cannot reach the digest |
|---|---|
| process-local object identity, memory address | `canonical_form` has no `repr`/`str` fallback; an unsupported object raises |
| wall-clock time, random data | not a component; no clock or RNG is read |
| unordered map insertion order | `canonical_form` sorts `dict` items by canonical key |
| formatted diagnostic text | `diagnostics` is not a component |
| downstream result requests | components are fixed at the moment the state result is produced |
| circular dependency on an output field | `result_id` itself, `values`, `value_intervals`, `units`, `zeroed_due_to_status` and `nulled_due_to_status` are all excluded |

`values` and the two flags are excluded for a second reason: they are a pure
function of `status` via `apply_status_field_pattern`, so including them would
add no discrimination while creating a construction-order dependency.

### 2.4 Two decisions that are genuinely new **[PV1]**

**Stage is a component.** The same state under the same configuration can fail at
L2 or be evaluated at L3. Without stage, an `INFEASIBLE` /
`ENGAGEMENT_ORDER_VIOLATION` result and a hypothetical L3 result with the same
status text would be indistinguishable. Stage makes the L2/L3 separation of
§20.7.2 C6–C7 visible in the identifier.

**Tolerance participates only at L3.** An L2 admissibility verdict never consults
a numerical tolerance. Including `tolerance_hash` unconditionally would change the
identifier of an order violation whenever an unrelated tolerance changed, which
would break repeatability for a verdict whose inputs did not change. At L3 the
tolerance is a real input to the §20.5 predicate (`eps_len`) and MUST participate.

---

## 3. Exact normative insertion text

New subsection, appended after §20.7.2.5. Clause numbering continues from C34.

> **§20.7.2.6 (new) Deterministic `StateResult` identity**
>
> **C35.** Every `StateResult` **MUST** carry a non-null `result_id`. **[PV1]**
>
> **C36.** `result_id` **MUST** equal `"st-"` followed by the first 32 hexadecimal
> characters of `result_identity_hash(C)`, where `C` is the ordered component list
> of §2.2: object kind, `config_identity_hash(cfg)`, `state_identity_hash(S)`,
> `METHOD_VERSION`, evaluation stage, `status.value`, `status_reason`, declared
> assumptions in declared order, and `tolerance_hash` when the evaluation stage is
> `L3_CLOSURE` or `None` otherwise. **[PV1]**
>
> **C37.** `result_id` **MUST NOT** depend on process-local object identity, a
> memory address, wall-clock time, random data, mapping insertion order, formatted
> diagnostic text, any downstream result request, or any field of the result that
> is itself derived from `result_id`. Components **MUST** be passed through
> `canonical_form`, whose absent `repr`/`str` fallback makes the first two
> structurally unreachable.
>
> **C38.** `diagnostics`, `values`, `value_intervals`, `units`,
> `zeroed_due_to_status` and `nulled_due_to_status` **MUST NOT** be components.
> The four value-shaped fields are determined by `status` through
> `apply_status_field_pattern` and carry no independent identity.
>
> **C39.** Two `StateResult` objects **MUST** share a `result_id` if and only if
> all nine components are equal. A producer **MUST NOT** introduce a counter, a
> sequence number, an evaluation index or any other process-order-dependent term.
>
> **C40 (M1 integration).** Restating §20.7.2.3 C20–C22 against C35–C39:
> - `upstream_state` **MUST** contain only the immutable caller-supplied state —
>   its `assignments`, and its `hash` computed as `state_identity_hash(S)`. It
>   **MUST NOT** contain `vetoing_state_result_id`.
> - The `quantities` mapping of the `STATE_VETO_PROPAGATED` diagnostic **MUST**
>   contain the canonical `vetoing_state_result_id`.
> - No compatibility alias is permitted, in any field.
> - A propagated result **MUST** copy the source `StateResult.result_id` **string
>   exactly**. It **MUST NOT** recompute the identifier, re-derive it from the
>   state, reformat it, change its case, strip or add the `st-` prefix, or
>   truncate it further. **[PV1]**
>
> **C41.** A `CANONICAL_FORM_VERSION` bump changes every `result_id`. Identifiers
> **MUST NOT** be compared across canonical-form versions, and **MUST NOT** be
> persisted as stable references outside a single canonical-form version.
>
> **C42.** This section grants no caching, deduplication or storage behavior. A
> shared `result_id` **MUST NOT** be used to skip an evaluation, reuse a prior
> result, or index any store. `cache_key` (§11.8) remains the only cache identity
> and is unchanged.

---

## 4. Serialization and determinism requirements

**S1.** `result_id` is a plain `str`. `EvaluationResult.as_dict()` already emits
it unchanged under the key `result_id`; no serializer change is required.

**S2.** The digest is taken over `_json`'s existing form — `sort_keys=True`,
`separators=(",",":")`, `allow_nan=False` — prefixed by
`CANONICAL_FORM_VERSION`. No second serialization form is introduced.

**S3.** `allow_nan=False` means a non-finite float anywhere in a component raises
rather than producing `NaN` in the digest input. This is the intended behavior:
a non-finite tolerance or assumption is a defect, not an identity.

**S4.** `declared_assumptions` is a `Sequence` and `canonical_form` preserves
sequence order, so the declared order **is** semantic. A producer **MUST** emit
it deterministically. Two otherwise identical results whose assumptions differ
only in order will receive different identifiers; this is accepted rather than
hidden by sorting, because assumption order is producer-controlled and a silent
sort would mask a nondeterministic producer. **[PV1]**

**S5.** JSON round-trip is exact: the identifier contains only `[0-9a-f-]` after
the `st-` prefix, so no escaping, normalization or precision loss applies.

**S6.** Repeatability is required across processes and across interpreter
restarts, not merely within one run. `canonical_form`'s prohibition on
`repr`-derived strings is what makes this hold under `PYTHONHASHSEED`
randomization.

---

## 5. Test revisions

The T84–T89 block is revised and extended to T91. **All identifiers in this block
remain provisional** until the complete §12 registry is available; the maximum
identifier observed in the material read is T83, and T80–T82 are presumed
allocated in material not provided.

### 5.1 Revisions to the accepted block

**T84** (canonical veto carrier) — assertion 2 is now writable and is tightened:

> 2. `diagnostic.quantities["vetoing_state_result_id"]` **is the same string
>    object value** as `state_result.result_id`, compared with `==` against the
>    originating result's field, not against a recomputed digest.
> 2b. The propagated value is byte-identical: same case, same `st-` prefix, same
>    length. The test asserts `== state_result.result_id` and additionally that no
>    transformation was applied by comparing against
>    `state_result.as_dict()["result_id"]`.

**T85, T86, T88** — add one assertion each: `result.result_id` is a non-empty
`str` matching `^st-[0-9a-f]{32}$` (C35, C36).

**T87, T89** — unchanged.

### 5.2 T90 — identifier determinism and repeatability

*Covers C35–C39, S6.* No geometry beyond the existing fixtures.

1. **Repeatability.** The same state is evaluated three times through freshly
   constructed inputs; all three `result_id` values are equal.
2. **Cross-process repeatability.** The component list is rebuilt and hashed in a
   subprocess launched with a different `PYTHONHASHSEED`; the value matches.
3. **No construction-order dependence.** Evaluating state `A` then `B`, and `B`
   then `A`, yields the same pair of identifiers.
4. **No memory-address dependence.** Two independently constructed but equal
   configuration objects with different `id()` produce the same identifier.
5. **Mapping order irrelevance.** Two supplied states whose assignment mappings
   are built in different key insertion orders produce the same
   `state_identity_hash` and the same `result_id`.
6. **Diagnostic text irrelevance.** Patching the diagnostic `message` and
   `remediation` strings leaves `result_id` unchanged.
7. **No circularity.** Computing the identifier does not read `result_id`,
   `values`, `value_intervals`, `units`, or either status flag — asserted by
   building the component list from a configuration/state/status triple alone,
   with no `EvaluationResult` in scope.

### 5.3 T91 — distinctness and serialization

*Covers C39, C41, S1, S5.*

1. **Status distinctness.** Two results identical except for `status` have
   different identifiers.
2. **Reason distinctness.** Identical except for `status_reason` — different.
3. **State distinctness.** `S = {D1@T1, D2@T2}` vs `S = {D1@T1, D2@T2b}` —
   different.
4. **Configuration distinctness.** Two configurations differing only in
   `topology_mode` — different, inherited from D10 via `config_identity_hash`.
5. **Stage distinctness.** The same state, status and reason recorded at
   `L2_ADMISSIBILITY` vs `L3_CLOSURE` — different.
6. **Tolerance participation is stage-gated.** Changing `tolerance_hash` leaves an
   `L2_ADMISSIBILITY` identifier unchanged and changes an `L3_CLOSURE` identifier.
7. **Assumption order.** Two results whose `declared_assumptions` differ only in
   order have different identifiers (S4, asserted as the specified behavior, not
   as an accident).
8. **JSON exactness.** `json.loads(json.dumps(result.as_dict(), allow_nan=False))
   ["result_id"] == result.result_id`.
9. **Format.** Matches `^st-[0-9a-f]{32}$`.
10. **Pairwise uniqueness.** Across a fixture set of semantically distinct state
    results, all identifiers are pairwise distinct.

---

## 6. Compatibility / non-goals

### Compatible by construction

- `EvaluationResult` is unchanged: `result_id: Optional[str] = None` already
  exists. C35 constrains `object_kind == "STATE"` producers only.
- Phase 1c `CONFIG` results are unaffected. `make_config_result` continues to
  leave `result_id` as `None`; no existing test that inspects a CONFIG result
  changes.
- `__post_init__` is unchanged. It does not validate `result_id`, so no new
  construction-time rejection is introduced.
- `cache_key` is unchanged. `state_identity_hash` supplies the `state_hash`
  argument it already declares.
- `CANONICAL_FORM_VERSION` is not bumped by this proposal.
- Two additions to `identity.py`, both pure and both in the module's existing
  style: `state_identity_hash` and `result_identity_hash`.

### Explicit non-goals

This contract does **not** introduce caching, deduplication, memoization,
external storage, a database, an index, a registry, or any persistence; does not
make `result_id` a cache key or permit skipping an evaluation; does not add
probability, kinetics, temporal persistence, biological interpretation, numerical
scoring, or any geometry; does not alter `upstream_state`'s handling in
`__post_init__` (the M2 hardening remains open); does not resolve the remaining
deferred items M3, M4, M8, M9, M11, M12, M13, M14, the `StateCertificate` field
list, or the extension of the §10.8 exactness guard to `object_kind == "STATE"`;
and does not confirm the T84–T91 allocation, which stays provisional pending the
§12 registry.
