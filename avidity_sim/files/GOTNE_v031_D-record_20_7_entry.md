# 20.7 Sequential engagement semantics and conditional reachability

Decision-record entry for GOTNE v0.3.1. Written before Phase 2 implementation.

**Placement.** §20.7 is referenced by `GOTNE_v031_phase2_semantic_closure.md` §2
but is not defined in the D-record, whose Addendum A enumerates up to §20.6. This
entry supplies the missing parent body. It occupies **§20.7, §20.7.1 and
§20.7.2** only. **§20.7.3 (N0), §20.7.4 (N1–N7) and §20.7.5 (N8–N17) remain owned
by the addendum** and are neither restated nor amended here, with the single
exception recorded in §3.6 below. Clauses here are numbered **C1–C28** because
N0–N17 are already allocated.

**Relation to D6 and D8.** Neither is modified. §20.5 remains the definition of
chain closure and of consecutive-engaged-pair selection; §20.6 remains the
definition of `R_union` and down-closure. This entry states the semantics under
which both are read, and adds nothing to either.

---

## 1. Chosen rule

An engagement state is a **caller-supplied conditioning declaration**. Every
Phase 2 output is conditional on it and carries no content beyond that.

Four layers are distinguished, and the implications between them are one-way.
Structural declaration order does not establish admissibility; admissibility does
not establish geometric reachability; geometric reachability does not establish
any quantitative or real-world claim. The record currently states the last of
these only for the `VALID` verdict (§20.7.3 N0, §20.7.5 N17) and never states the
chain. The layers themselves are used throughout Phase 2 — "L2 admissibility" is
referenced by the Phase 2 contract — but are nowhere defined as a set.

Three points are closed here because the contract is silent, not because a
decision is being revised:

1. **Immutability.** No rule prevents evaluation from normalizing, completing or
   repairing the supplied state. D6 places `assignments` inside `upstream_state`
   but does not require that mapping to equal what the caller passed.
2. **Layer separation and the non-implication chain.**
3. **Interpretation of emitted text.** N0 and N17 constrain how a result is
   *read*. Nothing constrains what Phase 2 *emits*.

Everything else is delegated: pair selection to §20.5, admissibility to §20.6,
field patterns to §10.1 / §3.6 / §10.7 / §10.8, empty pair sets to §20.7.4,
unengaged intervening modules to §20.7.5.

---

## 2. Normative wording

### §20.7 Sequential engagement semantics and conditional reachability

> **C1.** An engagement state `S` is supplied by the caller. Every Phase 2 result
> is a statement about `S` under the declared configuration and policy.
>
> **C2.** *"An engagement state is a conditioning declaration, not a claim that
> all declared engagements coexist kinetically for any specified residence
> time."*
>
> **C3.** *"A supplied engagement state MUST NOT be mutated, completed, repaired,
> relabeled, or assigned substitute targets during evaluation."* Absent
> declarations remain absent and **MUST NOT** be defaulted to any label.
>
> **C4.** Every result conditioned on `S` **MUST** preserve `S` exactly in
> `upstream_state.assignments` (§10.7): the same module identifiers, labels and
> target identifiers as supplied, with no addition, removal or substitution.
> Order-insensitive comparison is permitted; content-altering canonicalization is
> not. **[PV1]**
>
> **C5.** GOTNE has no temporal variable in this phase. Engagement order under
> §20.6 is a constraint relation on admissible declarations, not a sequence of
> events and not a schedule. No Phase 2 output **MAY** be expressed as a time, a
> rate, a duration, a step index or an event sequence.

### §20.7.1 The four layers

> **C6.** The following names are normative. The behaviour of each layer is
> defined by the sections cited and is unchanged here. **[PV1]**
>
> | Layer | Content | Defined by | Owner |
> |---|---|---|---|
> | **A** | structural declaration order: cassette indices, declared topology | Phase 1c structural validation | Phase 1c |
> | **B** | admissible engagement order: down-closure of the `ENGAGED` set under `R_union = R_policy ∪ R_requires` | §20.6 (D8) | Phase 2 |
> | **C** | deterministic state-conditioned reachability for consecutive `ENGAGED` modules, over the existing effective-anchor, contour-budget, junction-model and tolerance contracts | §20.5 (D6), §18.2 | Phase 2 |
> | **D** | later conditional quantitative evaluation | Phase 4; Phase 5 where policy requires | Phase 4 / 5 |
>
> **C7.** Layer A describes only the declared cassette arrangement.
> *"Topological succession MUST NOT be interpreted as geometric reachability."*
> It **MUST NOT** be interpreted as target proximity, as a temporal engagement
> sequence, or as any real-world event.
>
> **C8.** Layer B admissibility **MUST NOT** be interpreted as geometric
> reachability. Failure remains `ENGAGEMENT_ORDER_VIOLATION` and is distinct from
> geometric closure failure.
>
> **C9.** *"Geometric reachability MUST NOT be interpreted as nonzero binding
> probability, successful binding, affinity, or kinetic persistence."*
>
> **C10.** Layer D outputs are model-defined conditional geometric quantities
> with their own provenance and approximation contracts. They **MUST NOT** be
> retroactively implied by a Phase 2 success.

### §20.7.2 Conditional reachability at Layer C

> **C11.** For an admissible state, Phase 2 **MAY** evaluate chain closure only
> for consecutive `ENGAGED` modules, as defined by §20.5. The outcome is only
> whether the declared consecutive assignments are vetoed or not vetoed by the
> Phase 2 span model.
>
> **C12.** *"A closure-feasible StateResult certifies only that the declared
> consecutive engaged assignments are not vetoed by the Phase 2 span model."*
>
> **C13.** *"A Phase 2 success is an admissibility certificate, not a binding
> prediction."*
>
> **C14.** Layer C **MUST NOT** compute density, probability, capture integral,
> effective local concentration, joint score, affinity, kinetic persistence, or
> any downstream numerical estimate.
>
> **C15.** *"No Phase 2 result may populate conditional_probability,
> effective_local_concentration, capture_integral, survival_correction, or
> joint_score with a non-veto numerical estimate."* For a non-veto Phase 2
> `StateResult` these five canonical fields remain unpopulated under the existing
> field-pattern and exactness contract of §10.1, §3.6, §10.7 and §10.8, as
> applied by `apply_status_field_pattern` and as already fixed for the empty-pair
> case by §20.7.4 N5. No new numeric encoding of closure success **MAY** be
> introduced: the outcome **MUST NOT** be recorded as `1.0`, `0.0`, a flag inside
> `values`, a `value_intervals` entry, a score or a weight.

### §20.7.2.1 Control flow and failure separation

> **C16.** *"An inadmissible state MUST NOT enter the chain-closure sweep."*
> Layer B precedes Layer C unconditionally. On an order violation
> `chain_closure_feasible` and `cassette_contour_budget` **MUST NOT** be invoked
> and no closure-pair set is produced (§20.7.5 N16).
>
> **C17.** *"A closure-infeasible state MUST veto downstream numerical evaluation
> under the existing D6 propagation contract."*
>
> **C18.** *"A non-boolean / underdetermined chain-closure outcome MUST NOT be
> treated as closure-feasible, MUST NOT produce VALID merely by coercion, and
> MUST follow the existing ENGAGED_POSE_UNDERDETERMINED handling where
> applicable."* It **MUST NOT** be converted by `bool()`, by truthiness, by
> `== True`, by a default value, by an `or` fallback, or by suppressing an
> exception raised while computing it.
>
> **C19.** The three Phase 2 reasons are distinct and **MUST NOT** be merged or
> aliased:
>
> | Reason | Layer | Meaning |
> |---|---|---|
> | `ENGAGEMENT_ORDER_VIOLATION` | B | `S` not down-closed under `R_union` (§20.6) |
> | `CHAIN_CLOSURE_VIOLATED` | C | a consecutive pair vetoed by the §20.5 predicate |
> | `ENGAGED_POSE_UNDERDETERMINED` | C | the predicate did not conclude |

### §20.7.2.2 Worked examples

> These are normative as examples. They introduce no rule beyond §20.5 and
> §20.6.
>
> **C20.** `S = {D1@T1}`. A conditioning state containing one declared
> assignment. No closure pair exists, so per §20.7.4 N1–N2 the sweep completes
> over an empty domain and `chain_closure_feasible` **MUST NOT** be invoked. The
> result **MUST NOT** emit a `D2` or `D3` numerical prediction, and **MUST NOT**
> assert that `D2` or `D3` is reachable, engaged, nearby or persistent.
>
> **C21.** `S = {D1@T1, D2@T2}`. Order-admissibility under §20.6 is checked
> first. If admissible, closure is evaluated for the consecutive pair `D1`–`D2`
> only. On failure the existing closure-veto behaviour of D6 applies and
> downstream numerical evaluation is not entered. On success no numeric score is
> emitted (C15).
>
> **C22.** `S = {D1@T1, D2@T2, D3@T3}`. Only `D1`–`D2` and `D2`–`D3` are
> evaluated. `D1`–`D3` **MUST NOT** be evaluated as a direct closure pair while
> `D2` is `ENGAGED` between them.
>
> **C23.** `S = {D1@T1, D3@T3}` with `D2` not `ENGAGED`. Acceptance or rejection
> follows the existing `R_union` down-closure rule first. If admissible,
> consecutive-pair selection follows the formal definition of §20.5 as applied by
> §20.7.5 N8, **not** an informal assumption about adjacency in raw cassette
> index. Physical-path membership for the §18.2 budget is unaffected (§20.7.5
> N9–N11). No new order policy is introduced by this entry.

### §20.7.2.3 Emitted text

> **C24.** Phase 2 diagnostics, result labels and remediation text **MUST NOT**
> characterize a structural or geometric result as an experimentally observed
> biological outcome, a kinetic event, an affinity estimate, a residence-time
> estimate, or a claim of simultaneous real-world occupancy. This is a semantic
> obligation on the author of the text, enforced by review against the fixed
> reason and diagnostic-code sets. It is **not** a global substring filter and
> **not** a prohibited-word annex. **[PV1]**

### §20.7.2.4 Phase boundary

> **C25.** Phase 2 **MUST NOT** compute a density, a conditional probability, a
> local concentration, a capture integral, a pose marginalization, a survival
> term, a shell-bound interval, or any new score.
>
> **C26.** Phase 2 **MAY** preserve declared unresolved-upstream policy as
> diagnostics within the three-key limit of §20.7.5 N14, without performing any
> later-phase computation.
>
> **C27.** A `SHELL_BOUND` reason, a `BOUND_ONLY` provenance label, an at-risk
> weight, or any `value_intervals` entry **MUST NOT** be emitted as a Phase 2
> result (§20.7.5 N15).
>
> **C28.** A Phase 2 non-veto result **MAY** later be passed to Phase 4
> conditional density and pose-marginalization machinery and, where policy
> requires, to Phase 5 shell-bound interval machinery. Those outputs carry their
> own provenance and approximation contracts and are not implied by C12.

---

## 3. Schema / API impact

**None to existing shapes.**

| Concept | Impact |
|---|---|
| `StateResult`, `StateCertificate` | preserved |
| `evaluate_state`, `evaluate_node`, `chain_closure_feasible` | signatures preserved |
| `cassette_effective_anchor`, `cassette_contour_budget` | preserved |
| `EvaluationResult` field set | unchanged; no new top-level field |
| `CANONICAL_VALUE_FIELDS` | unchanged, five members |
| `Status`, `Exactness`, `Provenance` | no new member |
| `status_reason` set | unchanged, the three reasons of C19 |
| Diagnostic codes | no new code introduced by this entry |

No probability API, no kinetic API, no new scientific or mechanistic parameter.
Existing diagnostics, status reasons and provenance fields are reused throughout.

### 3.1 The one semantic annotation

C4 requires `upstream_state.assignments` to be derived from the supplied `S`.
This is an obligation on the producer, not a shape change. It does not resolve
the open question of a schema for `upstream_state`, and does not depend on it.

### 3.2 PV1-E — order-violation propagation to node / path / network

**This does not follow from D6 and is identified here as a minimal extension, not
as an implication.** **[PV1]**

D6's propagation clause is scoped to *closure*-violating states, and MNH26 is
worded the same way. An order-violating state is different in kind: it yields no
`StateCertificate`, so `evaluate_node` cannot be invoked for it — a
signature-level impossibility per D6 (4). Consequently **no node result exists
and no propagation record is emitted at node level.**

Where `evaluate_path` or `evaluate_network` enumerate states internally and must
account for a state they skipped, the minimal extension is: such a result **MUST**
record the skipped state's `StateResult` identifier using the same carrier as the
closure case, and **MUST NOT** invent a second carrier or a second diagnostic
code. Whether path- and network-level results are produced at all in Phase 2 is
out of scope for this entry.

### 3.3 Field pattern preserved

For a non-veto Phase 2 `StateResult` the five canonical fields remain
unpopulated per §10.1, §3.6, §10.7 and §10.8; the pattern is produced by
`apply_status_field_pattern`, never written by hand. §20.7.4 N5 already fixes the
empty-pair instance of this. No replacement values are invented here.

### 3.4 Dependencies on separately proposed amendments

This entry is consistent with, and depends on, three items proposed separately
and not restated here: the canonical veto-reference carrier; the
`ENGAGEMENT_ORDER_VIOLATION` result contract; and the closure-predicate return
type with its underdetermined member. C17, C18 and C19 are written so that they
hold under those proposals without embedding them.

### 3.5 Diagnostic and label discipline

C24 is enforced by review. The machine-checkable half is the diagnostic-key
allow-list asserted in test **T-h** of §5, which is a structural check on emitted
keys, not a scan of source text.

### 3.6 Single cross-reference correction

`GOTNE_v031_phase2_semantic_closure.md` §2 states that §20.7's existing body
covers "sequential engagement semantics, conditional reachability, order-policy
definitions". That body did not exist; the order-policy definitions it refers to
are in §20.6. Once this entry is adopted the reference resolves, and the
addendum's sentence **MAY** be left as written. No addendum clause changes.

---

## 4. Validation / runtime behavior

**V1. Layer order is A → B → C, unconditionally.** Phase 1c configuration
validation, then state-schema validation, then Layer B admissibility, then the
Layer C closure sweep. This is the existing Phase 2 validation order.

**V2. On a Layer B failure** the sweep does not run: `chain_closure_feasible` and
`cassette_contour_budget` are not invoked, and no closure-pair set is produced
(C16, §20.7.5 N16).

**V3. On a Layer C veto** downstream numerical evaluation is vetoed through the
existing `StateResult` propagation of §10.7 / D6 (C17).

**V4. On an underdetermined Layer C outcome** the existing
`ENGAGED_POSE_UNDERDETERMINED` handling applies and no `StateCertificate` is
issued (C18).

**V5. On a non-veto result** a `StateCertificate` is issued per §10.7 and the
five canonical fields remain unpopulated (C15).

**V6.** In every branch, including early returns, the supplied `S` is serialized
unchanged in `upstream_state` (C4).

**V7. Determinism is unaffected.** C1–C28 remove implementation freedom and add
no state, no ordering dependence and no import-time effect.

**V8. Phase boundary at runtime.** No Phase 4 or Phase 5 module is imported or
invoked during Phase 2 (C25, §20.7.4 N6).

---

## 5. Tests

Concrete tests, one per requirement. Identifiers are given as **T-a … T-j** and
**remain provisional**: the maximum allocated identifier observed is T83, T80–T82
appear allocated in material not available, and the base-spec §12 registry has
not been read. The block **MUST** be renumbered against that registry before
adoption.

All live in `tests/test_phase2_state.py` except T-i, and none import a Phase 4 or
Phase 5 module.

**T-a — single-declaration state emits no prediction.** `S = {D1@T1}`,
`ANY_ORDER`. Asserts: status is not a failure reason; `closure_pairs` is present
and equals `[]`; `closure_predicate_invocations == 0` and the
`chain_closure_feasible` spy count is `0`; all five canonical fields are `None`;
`value_intervals` is empty; no diagnostic mentions `D2` or `D3` as reachable,
engaged, nearby or persistent, checked against the emitted-key allow-list.

**T-b — closure-feasible state asserts nothing further.** `S = {D1@T1, D2@T2}`,
admissible, closure passes. Asserts: the five canonical fields are `None` and
both status flags are `False`, compared component-wise against
`apply_status_field_pattern` output rather than hard-coded; no `values` entry
equals `1.0` or `0.0`; `value_intervals` is empty; no provenance label implies a
computed quantity.

**T-c — closure-infeasible state is vetoed before any later machinery.** Same
state, closure fails. Asserts: the veto status and `CHAIN_CLOSURE_VIOLATED`
reason; the §10.1 veto field pattern via `apply_status_field_pattern`; a trap
finder on `sys.meta_path` for the five Phase 4/5 module names was never
triggered; none of those names is in `sys.modules` after the call; no density,
capture, marginalization, survival or interval function was entered, asserted by
method-trace.

**T-d — three-module state evaluates two pairs.** `S = {D1@T1, D2@T2, D3@T3}`.
Asserts: `closure_pairs == [("D1","D2"), ("D2","D3")]` by exact equality, in
increasing index order; `("D1","D3")` absent; predicate invocations `== 2` and
the spy recorded exactly those two pairs.

**T-e — order violation and closure violation are distinct.** Two fixtures
producing each failure. Asserts: the two results differ in `status` **and** in
`status_reason`; the order-violation result's provenance label is not the
geometric-veto label; for the order violation the `chain_closure_feasible` and
`cassette_contour_budget` spies are both `0` and the call sequence contains no
entry after admissibility returned.

**T-f — underdetermined outcome is not coerced.** Predicate patched to return the
underdetermined member. Asserts: status is not `VALID`; reason is
`ENGAGED_POSE_UNDERDETERMINED`; the unknown-class field pattern applies,
component-wise against `apply_status_field_pattern`; no `StateCertificate` is
issued; three-way distinctness — the result differs from both the feasible and
the infeasible outcome, so no collapse occurred; `bool()` on the outcome raises
rather than silently succeeding.

**T-g — prohibited fields unpopulated except under a veto pattern.**
Parametrized over the non-veto branch and the veto branch. Asserts:
`set(result.values) == set(CANONICAL_VALUE_FIELDS)`; in the non-veto branch all
five are `None` with both flags `False`; in the veto branch the values and flags
equal `apply_status_field_pattern` output exactly, so zeroing/nulling occurs only
where the existing pattern requires it.

**T-h — no Phase 4 or Phase 5 calculation is entered.** Static and dynamic, in
`tests/test_phase2_import_boundary.py`. Static: `ast` over the five Phase 2
modules and their transitive `gotne.*` import closure finds no reference to the
five forbidden modules. Dynamic: after `evaluate_state` and `evaluate_node`, none
of the five is in `sys.modules`, and a trap finder was never triggered.
Additionally: every diagnostic `quantities` key emitted across all branches is a
member of the Phase 2 allow-list — the closure-pair and invocation keys, the
shielding-ancestor key, the three unresolved-upstream keys, the contour-budget
breakdown, the pair endpoints and span quantities, and the veto reference. An
unlisted key fails. This is the machine-checkable half of C24.

**T-i — supplied state unchanged.** *(`tests/test_phase2_state.py`.)* A deep copy
of `S` is taken before the call. Asserts: `S` equals the copy after evaluation;
container lengths and identity unchanged if mutable;
`upstream_state["assignments"]` reproduces the supplied assignments exactly and
contains no key absent from `S`; parametrized over all four branches of §4, so
early returns are covered (C4, V6).

**T-j — propagated diagnostic carries the vetoing identifier exactly.** A
closure-vetoed state evaluated through the path that produces a propagated
result. Asserts: exactly one propagation diagnostic exists with the expected code
and severity; its veto-reference value equals the originating `StateResult`
identifier by `==`, not by recomputation; the value is byte-identical, compared
also against the originating result's serialized form; the identifier appears as
a key exactly once across the serialized result, walked structurally rather than
by substring match; `upstream_state["assignments"]` still equals `S` exactly.

---

## 6. Explicit non-goals

This entry introduces none of the following, and **MUST NOT** be read as
implying any of them:

1. **No conformational coupling model.**
2. **No induced-fit model.**
3. **No `k_on` / `k_off`, residence-time, dwell-time, rebinding, or temporal
   sequential-dynamics model.**
4. **No affinity, avidity, potency, efficacy, uptake, delivery, or
   biological-performance prediction.**
5. **No density, probability, capture integral, pose marginalization, survival
   correction, or shell-bound interval computation in Phase 2.**
6. **No modification of D6, D8, the core geometry equations, the status taxonomy,
   or the base-state schema.** The only cross-reference correction is the
   non-substantive one recorded in §3.6.

Additionally: no new probability or kinetic API; no new scientific or mechanistic
parameter; no new geometry; no global text substring filter and no
prohibited-word annex; no change to Phase 1c's ownership of structural
validation, Phase 4's ownership of composite quantities and pose marginalization,
or Phase 5's ownership of obstacle-aware shell-bound intervals.

---

# Implementation handoff

## 1. Phase 2 modules that may now be implemented

| Module | Scope now unblocked |
|---|---|
| `gotne/cassette_state.py` | state schema; Layer B admissibility and down-closure under `R_union`; the three reason constants as one central closed set; `StateResult` construction routed through `apply_status_field_pattern`; `StateCertificate` issuance gating |
| `gotne/cassette_frames.py` | effective-anchor propagation |
| `gotne/cassette_budget.py` | §18.2 contour budget over the full physical path, with element membership insensitive to engagement (§20.7.5 N9–N11) |
| `gotne/closure.py` | consecutive-engaged-pair selection per §20.5; the deterministic veto predicate; the empty-pair path of §20.7.4 |
| `gotne/evaluate_node.py` | node-level evaluation under a certificate; closure-veto propagation per D6 |
| `tests/test_phase2_import_boundary.py` | the static and dynamic boundary checks of T-h |

Implementation order should follow the data flow: `cassette_frames` →
`cassette_budget` → `cassette_state` → `closure` → `evaluate_node`.

## 2. Modules and items that must not be implemented yet

**Forbidden outright in Phase 2** — neither imported nor invoked by Phase 2 code
or Phase 2 tests: `gotne/composite_density.py`, `gotne/so3_grids.py`,
`gotne/pose_marginalization.py`, `gotne/shell_bounds.py`, `gotne/intervals.py`.

**Blocked pending a decision, not pending a phase:**

- the `StateCertificate` serialized field list, and whether
  `APPROXIMATION_REQUIRED` may issue one — Phase 2 has no source of that status;
- the `ENGAGEMENT_ORDER_VIOLATION` result contract, the canonical veto-reference
  carrier, the closure-predicate return type, and the deterministic result
  identifier — all four are proposed separately and none is adopted;
- PV1-E path/network propagation for skipped order-violating states (§3.2);
- `i` / `j` in `chain_closure_feasible`: module identifiers or indices, and which
  base — module `cassette_index` is 1-based while tether `cassette_index` is
  0-based;
- rigid-spacer span derivation and element-id naming for the §18.2 element table;
- behaviour when the `policy` argument disagrees with `cfg.policy`;
- what `evaluate_state` returns for a non-cassette topology mode or a non-valid
  Phase 1c configuration;
- the in-memory versus serialized form of the closure-pair list;
- whether a skipped sweep is recorded as absent or as an explicit skip marker —
  §20.7.4 N4 forbids encoding meaning by absence but does not fix the positive
  form;
- JSON safety of non-finite floats in geometric diagnostics;
- the test-identifier block, pending the §12 registry.

**Measurement task, not a design task:** the regression baseline. The stated
"46 tests" figure does not match the folder snapshot, which collects 141 and
passes 139, with two failures attributable to layout rather than logic. Fix the
baseline in the real repository layout once, and bind the no-regression gate to
that number before the first patch.

## 3. Items that must wait for Phase 4 and Phase 5

**Phase 4.** Composite density; pose marginalization, including the §18.5.1 Haar
marginalization selected by the orientation-marginalized pose-resolution policy —
which is precisely the condition that makes a Layer C outcome underdetermined, so
Phase 2 must return that outcome rather than resolve it; the spacer-dominance
guard as it bears on approximation-required results; population of any canonical
value field.

**Phase 5.** Shell-bound and obstacle-aware interval construction under the
excluded-shell-bound policy; population of `value_intervals`; the `SHELL_BOUND`
reason; the `BOUND_ONLY` provenance label; at-risk weights. In Phase 2 the
excluded-shell-bound policy yields exactly the three diagnostic keys of §20.7.5
N14 and a deferral flag, and nothing else.
