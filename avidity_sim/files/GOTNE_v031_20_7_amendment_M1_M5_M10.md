# §20.7 amendment proposal — resolution of M1, M5, M10 and test-ID allocation

Targeted amendment to the proposed §20.7 entry. **Proposal only.** No
source-of-truth file, code, test or notebook is modified by this document.

Authority order used throughout: **code in `gotne/` > D-record
(`pasted_text_1790107971.txt`) > Phase 2 semantic-closure addendum
(`GOTNE_v031_phase2_semantic_closure.md`) > prior §20.7 draft.**

Identifier spellings below are taken verbatim from `status.py`,
`cassette_schema.py` and the normative documents.

---

## 1. Conflict map

### 1.1 M1 — veto-reference carrier

| Source | Location asserted | Authority |
|---|---|---|
| D-record D6, Propagation prose | `diagnostics.vetoing_state_result_id` | D-record |
| D-record D6, serialized NODE example | `diagnostics[0].quantities["vetoing_state_result_id"]`, code `STATE_VETO_PROPAGATED`, severity `INFO` | D-record, concrete |
| D-record §11.6 MNH26 / §13 audit L18 | phrased over *node results*, carrier unnamed | D-record |
| Addendum §20.7.4 **N7** | `upstream_state["vetoing_state_result_id"]` | addendum |
| Addendum T79 assertion #10 | asserts absence from `upstream_state` | addendum |
| Prior §20.7 draft C16 | deliberately agnostic | draft |

**Direct contradiction.** N7 and D6 name different carriers for the same
identifier. Two carriers make MNH26 and audit L18 unenforceable: an auditor
cannot know where to look, and a producer can satisfy one reading while
violating the other.

Code evidence bearing on the choice:

- `EvaluationResult.upstream_state: Optional[Mapping[str, Any]]` is stored
  **raw**. `__post_init__` copies and freezes `values`, `value_intervals`,
  `units` and `diagnostics`; it does **not** touch `upstream_state`. `as_dict()`
  passes it through by reference. It is not key-checked, not JSON-safety-checked
  and not made read-only. (This is `phase2-spec-corrections.md` **M2**, confirmed
  against `status.py`.)
- `DiagnosticRecord.__post_init__` **does** wrap `quantities` with `_read_only`.
- Proposed §20.7.1 **C3** requires `upstream_state` to preserve the supplied `S`
  *exactly*. A system-generated key inside the same mapping makes "exactly"
  ambiguous and forces an exception list into the immutability check.

### 1.2 M5 — `ENGAGEMENT_ORDER_VIOLATION` result contract

| Item | State of the record |
|---|---|
| Reason literal | fixed: `ENGAGEMENT_ORDER_VIOLATION` (D-record Phase 2 contract; addendum §4) |
| Where decided | fixed: per-state down-closure under `R_union`, Phase 2 (D8 §20.6 item 4, "D1.c2") |
| Control-flow precedence | fixed: precedes the closure sweep (addendum N16) |
| `status` | **absent** |
| value / interval / units pattern | **absent** |
| `exact_or_approximate` | **absent** |
| `provenance` | **absent** |
| Certificate behavior | implied by §10.7 but never stated |
| Propagation behavior | **absent**; D6 propagation is scoped to *closure*-vetoed states |
| Diagnostic code | **absent** |

D8 §20.6 defines "D1.c2" only as a pointer; no such clause appears in the
material read. The result is currently unconstructible: `EvaluationResult`
`__post_init__` requires a `Status`, an `Exactness` and a `ProvenanceRecord`, and
enforces the §10.1 pattern against the chosen status. Without a status the field
pattern is undetermined and the result cannot be audited.

**No existing rule mandates that an order violation share a status with a closure
violation.** D6 binds `UNREACHABLE` to the geometric closure predicate only.

### 1.3 M10 — non-boolean closure outcome

| Source | Statement |
|---|---|
| D-record Phase 2 API | `chain_closure_feasible(i, j, state, cfg, policy) -> Tri` |
| Code | `Tri` **does not exist** anywhere in `gotne/` |
| Addendum §4 | non-decisive outcome ⇒ `DEGENERATE` / `ENGAGED_POSE_UNDERDETERMINED`, no `StateCertificate` |
| Addendum readiness audit item 4 | `ENGAGED_POSE_UNDERDETERMINED` pairs with `DEGENERATE` and `nulled_due_to_status=True` |
| Prior §20.7 draft C16 | refers to "the non-decisive member" without naming it |

`Tri`'s members, its base class and its truthiness are all unspecified. Under the
package's prevailing `class X(str, Enum)` pattern, **every member would be
truthy**, so `if chain_closure_feasible(...)` would silently pass on both the
false and the non-decisive outcome. `status.py` already records this hazard class
in `apply_status_field_pattern`: *"A str-Enum member compares equal to its text,
so a plain string would otherwise select a branch by accident, and garbage would
pass through."* A `str, Enum` member spelled `INFEASIBLE` would additionally
compare equal to `Status.INFEASIBLE`.

### 1.4 Test-ID allocation

Census over the D-record, the addendum, `phase2-*.md` and `test_*.py`:

| Quantity | Value |
|---|---|
| **Maximum allocated test ID** | **T83** |
| D-record | T29, T34–T78 (contiguous) |
| Addendum | T79, T83 |
| Code (`test_*.py`) | T0, T12, and a subset of T34–T78 |
| Unaccounted inside range | **T80, T81, T82** — no definition in any material read |
| Below T34 | T1–T33 belong to the base spec test section; T0, T12, T29 observed; not in scope |
| **Next safe contiguous range** | **T84 onward** |
| Prior draft's proposed T85–T90 | **no collision**, but orphans T84 and is not the next contiguous block |

`T1` and `T3` appearing in the addendum are **target identifiers** in
`S = {D1@T1, D3@T3}`, not test identifiers. They are excluded from the census.

The addendum's jump from T79 to T83 indicates T80–T82 were allocated in material
not provided. They are therefore treated as **taken**, not as free gaps.

---

## 2. Chosen resolution

### A. M1 — canonical carrier

**Resolved: the `STATE_VETO_PROPAGATED` diagnostic is the single canonical
carrier.** `upstream_state` carries the immutable caller-supplied state and
nothing else. **No compatibility alias is permitted.**

```
diagnostics[ code == "STATE_VETO_PROPAGATED" ].quantities["vetoing_state_result_id"]
```

Justification, in descending weight:

1. **The D-record specifies it twice**, once in prose and once in a concrete
   serialized NODE example carrying code `STATE_VETO_PROPAGATED` and severity
   `INFO`. The addendum's N7 is the only source asserting `upstream_state`, and
   the addendum is lower authority.
2. **`upstream_state` is the weakest container in the result object.** It is the
   one mapping `__post_init__` neither copies, freezes, key-checks nor
   JSON-checks. An audited identifier that MNH26 and audit L18 depend on must not
   live in the only unvalidated field. `DiagnosticRecord.quantities` is frozen by
   `_read_only` at construction.
3. **It keeps C3 checkable.** Immutability of `S` is verified by comparing
   `upstream_state["assignments"]` against the supplied state. Mixing
   system-generated keys into that mapping forces an exception list and weakens
   the check to "equal except for keys we happen to know about".
4. **Separation of kinds.** `upstream_state` answers *what was assumed*;
   diagnostics answer *what the evaluator concluded*. The veto reference is a
   conclusion.

No alias, because an alias reintroduces exactly the ambiguity MNH26 needs
removed, and because a producer writing both could let them diverge.

**Consequence:** addendum **N7** contains a direct contradiction and requires a
one-line correction (§3.1). Addendum **T79 assertion #10** tests the superseded
carrier and requires a one-line correction (§4.1). No other addendum text is
touched.

### B. M5 — `ENGAGEMENT_ORDER_VIOLATION` result contract

**Resolved: `Status.INFEASIBLE`, distinct from the closure violation's
`Status.UNREACHABLE`.** **[PV1]**

Justification:

1. **D8 precedent.** §20.6 already classifies order-constraint failure as
   `INFEASIBLE` at configuration time
   (`ENGAGEMENT_ORDER_CONSTRAINTS_UNSATISFIABLE`). The per-state down-closure
   failure is the same kind of failure — combinatorial admissibility under
   `R_union` — evaluated one layer later. Using the same status keeps the kind
   visible.
2. **`UNREACHABLE` is bound to geometry.** D6 assigns it to the §20.5 closure
   predicate. Reusing it for an order failure would erase the L2/L3 distinction
   that §20.7.2 C6–C7 exists to make, and would make `CHAIN_CLOSURE_VIOLATED` and
   `ENGAGEMENT_ORDER_VIOLATION` indistinguishable by status.
3. **`BLOCKED` denotes obstruction**, which is not evaluated at L2.
4. **`STATUS_RANK` orders it correctly.** `INFEASIBLE` is rank 2, `UNREACHABLE`
   rank 4. Under `precedence()` an inadmissible state dominates a geometric
   verdict that was never computed. The reverse assignment would let a
   never-evaluated geometric outcome outrank a definite admissibility failure.

Both statuses are in `VETO_SET`, so both receive the same §10.1 field pattern.
The statuses differ; the payload shape does not.

### C. M10 — `Tri` and `UNDERDETERMINED`

**Resolved: define `Tri` as a plain `Enum` — not `str, Enum` — with exactly three
members `TRUE`, `FALSE`, `UNDERDETERMINED`, and a `__bool__` that raises.**
**[PV1]**

Justification:

1. `Tri` is the D-record's own name for the return type; no new identifier is
   introduced.
2. **Plain `Enum`, not `str, Enum`.** Under the package's prevailing pattern a
   member would compare equal to its text and to any same-text member of
   `Status`, `Exactness` or `Provenance`. `status.py` already documents this as a
   silent-failure class.
3. **`__bool__` raises `TypeError`.** Every `str, Enum` member is truthy, so
   `if chain_closure_feasible(...)` would pass on `FALSE`. Raising converts the
   silent failure into a loud one at the exact line that commits it. This is the
   structural form of the coercion prohibition, not a review convention.
4. **Member names `TRUE` / `FALSE`**, not `FEASIBLE` / `INFEASIBLE`: the latter
   would collide textually with `Status.INFEASIBLE`.

`UNDERDETERMINED` maps to the already-fixed
`DEGENERATE` / `ENGAGED_POSE_UNDERDETERMINED` contract; that pairing is
cross-referenced, not re-decided.

### D. Test IDs

**Resolved: allocate `T84`–`T89`.** Contiguous, immediately after the maximum
allocated `T83`, no collision. `T80`–`T82` are left unallocated because they are
referenced by absence in the addendum's numbering and are presumed taken. The
prior draft's `T85`–`T90` is withdrawn. **[PV1]**

---

## 3. Exact normative replacement text

### 3.1 Correction to addendum §20.7.4 N7 — one line

The addendum is preserved in full except for the second sentence of N7.

> **Replace**, in `GOTNE_v031_phase2_semantic_closure.md` §20.7.4 N7:
>
> *"When a veto* is *produced elsewhere in Phase 2, its identifier **MUST** be
> carried in the existing `upstream_state` mapping under the key
> `vetoing_state_result_id`; Phase 2 **MUST NOT** add a new top-level field to
> `EvaluationResult` for this purpose."*
>
> **with:**
>
> > When a veto *is* produced elsewhere in Phase 2, its identifier **MUST** be
> > carried in the `quantities` mapping of the `STATE_VETO_PROPAGATED`
> > diagnostic under the key `vetoing_state_result_id`, per §20.7.2.3 C20. Phase 2
> > **MUST NOT** add a new top-level field to `EvaluationResult` for this purpose,
> > and **MUST NOT** place the identifier in `upstream_state`.

N1–N6 and N8–N17 are unchanged. N0 is unchanged.

### 3.2 New subsection §20.7.2.3 — propagation carrier

> **§20.7.2.3 (new) Canonical veto reference**
>
> **C20.** When a Phase 2 veto is propagated to a downstream result, the
> identifier of the vetoing `StateResult` **MUST** appear in exactly one
> location: the `quantities` mapping of a `DiagnosticRecord` whose `code` is
> `"STATE_VETO_PROPAGATED"`, under the key `vetoing_state_result_id`. Its
> `severity` **MUST** be `Severity.INFO`, per D6. **[PV1]**
>
> **C21.** `upstream_state` **MUST NOT** contain `vetoing_state_result_id` or any
> other evaluator-generated key. It carries the immutable caller-supplied state
> and its derived `hash` only, per §20.7.1 C3–C4. No compatibility alias for the
> veto reference is permitted, in `upstream_state` or in any other field.
>
> **C22.** MNH26 is **REQUIRED** to be read against C20: a node result under a
> closure-vetoed state that lacks the `STATE_VETO_PROPAGATED` diagnostic, or whose
> diagnostic lacks the key, is an MNH26 violation. Audit item L18 checks the same
> location.

### 3.3 New subsection §20.7.2.4 — order-violation result contract

> **§20.7.2.4 (new) `ENGAGEMENT_ORDER_VIOLATION` result contract**
>
> **C23.** A state `S` whose `ENGAGED` set is not down-closed under
> `R_union = R_policy ∪ R_requires` (§20.6) yields a `StateResult` with exactly:
> **[PV1]**
>
> | Field | Value |
> |---|---|
> | `object_kind` | `"STATE"` |
> | `status` | `Status.INFEASIBLE` |
> | `status_reason` | `"ENGAGEMENT_ORDER_VIOLATION"` |
> | `values` | the `VETO_SET` branch of `apply_status_field_pattern` |
> | `zeroed_due_to_status` | `True` |
> | `nulled_due_to_status` | `False` |
> | `value_intervals` | `{}` |
> | `units` | the five `CANONICAL_UNITS` entries for `CANONICAL_VALUE_FIELDS` |
> | `exact_or_approximate` | `Exactness.EXACT` |
> | `provenance.worst_label` | `Provenance.EXACT_STRUCTURAL_VETO` |
> | `provenance.contributing_labels` | `(Provenance.EXACT_STRUCTURAL_VETO,)` |
> | `provenance.method_id` | `"evaluate_state"` |
> | `provenance.method_version` | `METHOD_VERSION` |
>
> The `values` mapping **MUST** be obtained by calling
> `apply_status_field_pattern(Status.INFEASIBLE)` and **MUST NOT** be written out
> by hand, per §20.7.2 C11 and §10.1 / §3.6.
>
> **C24.** `Exactness.EXACT` is REQUIRED here because exactness describes the
> payload, not the verdict: the payload is exactly zeroed. This follows the rule
> already implemented in `make_config_result` and already applied by D6 to the
> closure veto. `Provenance.EXACT_STRUCTURAL_VETO` is REQUIRED rather than
> `EXACT_GEOMETRIC_VETO` because down-closure is combinatorial and **no geometry
> is evaluated**; §20.7.2 C7 forbids reading an L2 verdict as an L3 one.
>
> **C25.** `Status.INFEASIBLE` is REQUIRED and **MUST NOT** be replaced by
> `Status.UNREACHABLE`. The two reasons **MUST** remain distinguishable by status
> as well as by `status_reason`.
>
> **C26.** Exactly one `DiagnosticRecord` is REQUIRED, with
> `code = "ENGAGEMENT_ORDER_VIOLATION"`, `severity = Severity.ERROR`, and
> `quantities` naming the declared module that lacks a required predecessor and
> the predecessor identifiers missing from `S` under `R_union`. The `quantities`
> mapping **MUST NOT** carry a numeric score, weight, count-derived ranking or any
> geometric quantity. **[PV1]**
>
> **C27.** No `StateCertificate` is issued: `Status.INFEASIBLE` is neither
> `VALID` nor `APPROXIMATION_REQUIRED` (§10.7).
>
> **C28.** Propagation differs from the closure case and **MUST NOT** be
> assimilated to it. Because no certificate exists, `evaluate_node` cannot be
> invoked for this state — a signature-level impossibility per D6 (4) — so **no
> node result is produced and no `STATE_VETO_PROPAGATED` diagnostic is emitted at
> node level**. MNH26 is scoped to closure-vetoed states and is not engaged. Where
> `evaluate_path` or `evaluate_network` enumerate states internally, any
> propagation record they emit **MUST** use the C20 carrier. **[PV1]**

### 3.4 New subsection §20.7.2.5 — non-decisive closure outcome

> **§20.7.2.5 (new) `Tri` and the `UNDERDETERMINED` outcome**
>
> **C29.** `chain_closure_feasible` returns `Tri`, defined as exactly:
> **[PV1]**
>
> ```python
> class Tri(Enum):
>     """§20.5 closure predicate outcome. Deliberately NOT a str-Enum."""
>     TRUE = "TRUE"
>     FALSE = "FALSE"
>     UNDERDETERMINED = "UNDERDETERMINED"
>
>     def __bool__(self) -> bool:
>         raise TypeError(
>             "Tri has no truth value; compare against Tri.TRUE / Tri.FALSE / "
>             "Tri.UNDERDETERMINED explicitly"
>         )
> ```
>
> The member set is closed. `Tri` **MUST NOT** subclass `str`, because a str-Enum
> member compares equal to its own text and to any same-text member of `Status`,
> `Exactness` or `Provenance`.
>
> **C30.** `Tri.UNDERDETERMINED` is returned when, and only when, the operands of
> the §20.5 predicate — `exit_world(D_i)` and `entry_world(D_j)` — are not
> single-valued under the declared configuration and the declared
> `EngagedPoseResolution`, and making them single-valued would require an
> operation reserved to Phase 4, such as the §18.5.1 Haar marginalization selected
> by `EngagedPoseResolution.ORIENTATION_MARGINALIZED`. Phase 2 **MUST NOT**
> perform that operation (§20.7.2.2 C17). Configuration-level omissions remain
> Phase 1c failures and **MUST NOT** reach this path. **[PV1]**
>
> **C31.** A returned `Tri.UNDERDETERMINED` yields a `StateResult` with exactly:
>
> | Field | Value |
> |---|---|
> | `status` | `Status.DEGENERATE` |
> | `status_reason` | `"ENGAGED_POSE_UNDERDETERMINED"` |
> | `values` | the `UNKNOWN_SET` branch of `apply_status_field_pattern` — all five null |
> | `zeroed_due_to_status` | `False` |
> | `nulled_due_to_status` | `True` |
> | `value_intervals` | `{}` |
> | `units` | the five `CANONICAL_UNITS` entries |
> | `exact_or_approximate` | `Exactness.UNDEFINED` |
> | `provenance.worst_label` | `Provenance.NOT_COMPUTED` |
> | `provenance.method_id` | `"evaluate_state"` |
> | `provenance.method_version` | `METHOD_VERSION` |
>
> The status/reason pairing restates the addendum §4 contract and readiness-audit
> item 4; the exactness and provenance pairing is new. **[PV1]**
>
> **C32.** One `DiagnosticRecord` is REQUIRED, with
> `code = "ENGAGED_POSE_UNDERDETERMINED"`, `severity = Severity.ERROR`, and
> `quantities` naming the pair `(D_i, D_j)`, which operand was not single-valued,
> and the declared `engaged_pose_resolution`. It **MUST NOT** carry a span, a
> distance, a bound, an interval or any other numeric geometric quantity, because
> the predicate did not conclude. **[PV1]**
>
> **C33.** No `StateCertificate` is issued, and no later numerical layer **MAY**
> be entered.
>
> **C34.** `Tri.UNDERDETERMINED` **MUST NOT** be coerced to `Tri.TRUE` or
> `Tri.FALSE`. Specifically it **MUST NOT** be converted by `bool()`, by
> truthiness testing, by `== True` / `== False`, by `is not Tri.FALSE`, by a
> default value, by an `or` fallback, or by suppressing an exception raised while
> computing it. Every call site **MUST** dispatch on all three members
> exhaustively.

### 3.5 Amendment to the prior draft's C16

> **Replace** the third bullet of §20.7.2.1 C16 with:
>
> > - A `Tri.UNDERDETERMINED` closure outcome **MUST** yield the result contract
> >   of §20.7.2.5 C31. It **MUST NOT** be treated as success and **MUST NOT**
> >   yield `VALID` by fallback, by default-value or by exception suppression, per
> >   C34.
>
> **Replace** the second bullet of C16 with:
>
> > - A `CHAIN_CLOSURE_VIOLATED` **MUST** veto downstream numerical evaluation
> >   using the existing `StateResult` propagation semantics of §10.7 / D6, with
> >   the veto reference carried per §20.7.2.3 C20.

§20.7.1 C1–C5 and §20.7.2 C6–C19 are otherwise unchanged. Both subsections remain
limited to conditioning semantics and deterministic Phase 2 behavior.

---

## 4. Consequential test plan

Allocated range **T84–T89**, in `tests/test_phase2_state.py` unless stated. None
import a Phase 4 or Phase 5 module.

### 4.1 Corrections to existing planned tests

**T79 assertion #10** — supersede. Replace *"`result.upstream_state` içinde
`vetoing_state_result_id` yok"* with:

> 10. No diagnostic has `code == "STATE_VETO_PROPAGATED"`, and no diagnostic
>     `quantities` mapping contains the key `vetoing_state_result_id` (no veto was
>     produced). Additionally `"vetoing_state_result_id" not in
>     (result.upstream_state or {})`, which under C21 must hold in **every**
>     result, vetoed or not.

**T83** — unchanged. Its Policy B assertions 12–16 are compatible with C23–C28;
assertion 16 becomes checkable once `Status.INFEASIBLE` is fixed.

### 4.2 T84 — canonical veto carrier, and only that carrier

*Covers C20, C21, C22.* Fixture: a state that fails the §20.5 closure predicate,
evaluated through the path that produces a propagated node result.

1. The node result has exactly one diagnostic with
   `code == "STATE_VETO_PROPAGATED"`, and its `severity is Severity.INFO`.
2. That diagnostic's `quantities["vetoing_state_result_id"]` equals the
   `result_id` of the vetoing `StateResult`.
3. `"vetoing_state_result_id" not in (node_result.upstream_state or {})`.
4. No other diagnostic on the node result carries the key.
5. Alias check: across `node_result.as_dict()`, the string
   `"vetoing_state_result_id"` occurs as a key exactly once. The test walks the
   serialized structure rather than substring-matching the JSON text.
6. `upstream_state["assignments"]` still equals the supplied `S` exactly (C3
   regression under propagation).

### 4.3 T85 — order-violation result contract

*Covers C23, C24, C25, C26, C27.* Fixture: `S = {D1@T1, D3@T3}`,
`EngagementOrderPolicy.STRICT_PROXIMAL_TO_DISTAL`.

1. `result.status is Status.INFEASIBLE` — and explicitly
   `result.status is not Status.UNREACHABLE`.
2. `result.status_reason == "ENGAGEMENT_ORDER_VIOLATION"`.
3. `result.values`, `result.zeroed_due_to_status` and
   `result.nulled_due_to_status` equal
   `apply_status_field_pattern(Status.INFEASIBLE)` component-wise. The expected
   pattern is **not** hard-coded.
4. `dict(result.value_intervals) == {}`.
5. `set(result.units) == set(CANONICAL_VALUE_FIELDS)` and each value equals
   `CANONICAL_UNITS[field]`.
6. `result.exact_or_approximate is Exactness.EXACT`.
7. `result.provenance.worst_label is Provenance.EXACT_STRUCTURAL_VETO`, and it is
   **not** `EXACT_GEOMETRIC_VETO`; `method_id == "evaluate_state"`;
   `method_version == METHOD_VERSION`.
8. Exactly one diagnostic, `code == "ENGAGEMENT_ORDER_VIOLATION"`,
   `severity is Severity.ERROR`; its `quantities` name the offending module and
   the missing predecessors and contain no float.
9. No `StateCertificate` is obtainable from the result.
10. `precedence(Status.INFEASIBLE, Status.UNREACHABLE) is Status.INFEASIBLE`
    (guards the rank argument in §2.B.4).

### 4.4 T86 — order violation emits no node-level propagation

*Covers C28.* Same fixture as T85.

1. `evaluate_node` cannot be called: constructing the call without a
   `StateCertificate` is a type error, asserted with `pytest.raises(TypeError)`
   or the `unittest` equivalent.
2. No `STATE_VETO_PROPAGATED` diagnostic exists anywhere in the state result.
3. Negative control against assimilation to the closure case: the state result's
   `status_reason` is not `"CHAIN_CLOSURE_VIOLATED"` and its provenance label is
   not `EXACT_GEOMETRIC_VETO`.

### 4.5 T87 — `Tri` cannot be coerced

*Covers C29, C34.* Pure unit test on the type; no fixture.

1. `set(Tri) == {Tri.TRUE, Tri.FALSE, Tri.UNDERDETERMINED}`.
2. `not issubclass(Tri, str)`.
3. `bool(m)` raises `TypeError` for every member `m`, including `Tri.TRUE`.
4. `if m:` raises `TypeError` for every member.
5. No member compares equal to any member of `Status`, `Exactness` or
   `Provenance`, nor to the plain strings `"TRUE"`, `"FALSE"`,
   `"UNDERDETERMINED"`.
6. `Tri.UNDERDETERMINED is not Tri.TRUE and Tri.UNDERDETERMINED is not Tri.FALSE`.

### 4.6 T88 — non-decisive outcome result contract

*Covers C30, C31, C32, C33.* `chain_closure_feasible` patched to return
`Tri.UNDERDETERMINED` for one pair.

1. `result.status is Status.DEGENERATE`.
2. `result.status_reason == "ENGAGED_POSE_UNDERDETERMINED"`.
3. `result.values`, `zeroed_due_to_status`, `nulled_due_to_status` equal
   `apply_status_field_pattern(Status.DEGENERATE)` component-wise; all five
   canonical fields are `None`.
4. `dict(result.value_intervals) == {}`.
5. `result.exact_or_approximate is Exactness.UNDEFINED`;
   `result.provenance.worst_label is Provenance.NOT_COMPUTED`.
6. One diagnostic, `code == "ENGAGED_POSE_UNDERDETERMINED"`,
   `severity is Severity.ERROR`; its `quantities` name the pair and the declared
   `engaged_pose_resolution`, and contain **no** float value.
7. No `StateCertificate` is issued.
8. Negative control: the result differs from the result obtained when the
   predicate returns `Tri.TRUE`, and from the result when it returns `Tri.FALSE`
   — three distinct outcomes, no collapse.
9. Phase 4/5 modules absent from `sys.modules` after the call.

### 4.7 T89 — exhaustive dispatch at every call site

*Covers C34.* Static test, in `tests/test_phase2_import_boundary.py` alongside
the existing static check.

1. Every call site of `chain_closure_feasible` in the five Phase 2 modules is
   located by `ast`.
2. For each, the enclosing statement is asserted **not** to be a bare truthiness
   test (`If`/`While`/`IfExp`/`Assert` whose test is the call itself or a
   `UnaryOp(Not)` over it), and not an operand of `BoolOp`.
3. The result is either compared against a `Tri` member or bound to a name that
   is subsequently compared against `Tri` members covering all three.

This is an AST structural check on Phase 2 call sites, **not** a lexical
substring ban and not a scan of the source tree for words.

---

## 5. Remaining non-blocking deferred items

Each is unresolved, non-blocking for §20.7, and unaffected by the resolutions
above.

| Ref | Item | Why non-blocking here |
|---|---|---|
| M2 | No schema for `upstream_state`; it is not copied, frozen, key-checked or JSON-checked | C21 now restricts its *contents*; hardening its *handling* is a separate change to `status.py` |
| M3 | `closure_pairs` in-memory form (tuples) vs serialized form (lists) | affects T83/T88 assertion style only |
| M4 | Skipped sweep recorded as absent vs `CHECK_SKIPPED` | N4 forbids encoding meaning by absence; the positive form is still open |
| M8 | `i`, `j` in `chain_closure_feasible`: module ids or indices, and which base (module `cassette_index` is 1-based, tether `cassette_index` 0-based) | C29 fixes the return type only |
| M9 | Rigid-spacer span derivation and element-id naming for §18.2 | untouched |
| M11 | Redundant `policy` argument vs `cfg.policy`; behavior when they differ | untouched |
| M12 | What `evaluate_state` returns for a non-cassette `TopologyMode` or a non-`VALID` Phase 1c config | untouched |
| M13 | D-record serialized examples omit fields that `as_dict()` always emits | C23 and C31 now fix `units` for two statuses; the examples remain partial |
| M14 | JSON safety of non-finite geometric floats in diagnostics | C26 and C32 forbid floats in those two diagnostics, narrowing but not closing it |
| — | `StateCertificate` field list; whether `APPROXIMATION_REQUIRED` may issue one | Phase 2 has no source of `APPROXIMATION_REQUIRED`; C27 and C33 only state when none is issued |
| — | Deterministic `result_id` rule for STATE results | C20 references `result_id`; its generation rule is open and BLOCKING for T84 assertion 2 |
| — | Whether the §10.8 exactness guard extends to `object_kind == "STATE"` | C24 sets `EXACT` with a zeroed payload, which the guard would permit; C31 sets `UNDEFINED`. Extending the guard would not invalidate either |
| — | `T80`–`T82` provenance | presumed allocated in material not provided; left unallocated |
| — | Confirmation of the `T84`–`T89` block against the full base-spec test list (T1–T33) | the base spec's §12 was not among the material read |

**One item is BLOCKING for the test plan but not for the normative text:** the
deterministic `result_id` rule. T84 asserts equality against the vetoing
`StateResult.result_id`; until that rule exists, `result_id` is `None` by default
in `EvaluationResult` and the assertion cannot be written. C20 is well-formed
regardless of how the identifier is generated.
