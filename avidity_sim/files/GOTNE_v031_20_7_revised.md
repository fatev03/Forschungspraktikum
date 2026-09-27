# Phase ownership note

| Phase | Owns | Never performs |
|---|---|---|
| **1c** | structural, topology, policy, identity and configuration validation | geometry; numerical computation |
| **2** | supplied-state admissibility; effective-anchor propagation; contour-budget evaluation; shielding-ancestor and unresolved-upstream detection where already defined; deterministic chain-closure veto; `StateResult` construction; `StateCertificate` gating | density, capture integral, conditional probability, effective local concentration, joint score, survival correction, pose marginalization, steric survival, shell-bound interval, kinetic quantity, thermodynamic quantity, biological outcome |
| **4** | first phase permitted to perform composite density and pose marginalization | — |
| **5** | first phase permitted to construct `EXCLUDED_SHELL_BOUND` / obstacle-aware interval outputs where policy selects them | — |

§20.7 adds no phase and moves no boundary. It states the semantics under which
the Phase 2 boundary is read. D6, D8, §20.5, §20.6, §10.7 and §10.8 are
unmodified; `StateResult`, `StateCertificate`, `evaluate_state`, `evaluate_node`
and `chain_closure_feasible` remain authoritative.

**Placement.** §20.7 is referenced by the Phase 2 semantic-closure addendum but
is not defined in the D-record, whose Addendum A enumerates up to §20.6. This
entry supplies that parent body and occupies §20.7 only. §20.7.3 (N0), §20.7.4
(N1–N7) and §20.7.5 (N8–N17) remain owned by the addendum and are unchanged.
Clauses are numbered C1–C30 because N0–N17 are allocated.

---

# 20.7 Sequential engagement semantics and conditional reachability

## Chosen rule

An engagement state is a caller-supplied conditioning declaration, not a
time-evolving physical event. Four layers are distinguished — structural
declaration order, admissible engagement order, deterministic state-conditioned
reachability, and later conditional quantitative evaluation — and the
implications between them run one way only.

The record states the last non-implication for the `VALID` verdict alone
(§20.7.3 N0, §20.7.5 N17) and never states the chain. "L2 admissibility" is
referenced by the Phase 2 contract but is nowhere defined as one of a named set.
Three points are closed here because the pre-existing contract is silent:

1. **Immutability of the supplied state.** No rule prevents evaluation from
   normalizing, completing or repairing it.
2. **Layer separation and the non-implication chain.**
3. **Semantic overclaim in emitted runtime text.** N0 and N17 constrain how a
   result is *read*; nothing constrains what Phase 2 *emits*.

Pair selection remains §20.5; admissibility remains §20.6; field patterns remain
§10.1 / §3.6 / §10.7 / §10.8; empty pair sets remain §20.7.4; unengaged
intervening modules remain §20.7.5.

## Normative wording

### C1 — Conditioning input

> **C1.1.** *"An engagement state is a conditioning declaration, not a claim that
> all declared engagements coexist kinetically for any specified residence
> time."*
>
> **C1.2.** *"A supplied engagement state MUST NOT be mutated, completed,
> repaired, relabeled, or assigned substitute targets during evaluation."*
> Absent declarations remain absent and **MUST NOT** be defaulted to any label.
>
> **C1.3.** *"Every result is conditional on S and is interpreted only under the
> declared configuration, method, assumptions, tolerances, and provenance
> recorded in that result."*
>
> **C1.4.** Every result conditioned on `S` **MUST** preserve `S` exactly in
> `upstream_state.assignments` (§10.7): the same module identifiers, labels and
> target identifiers as supplied, with no addition, removal or substitution.
> Order-insensitive comparison is permitted; content-altering canonicalization is
> not. **[PV1]**
>
> **C1.5.** GOTNE has no temporal variable in this phase. Engagement order under
> §20.6 is a constraint relation on admissible declarations, not a sequence of
> events and not a schedule.

### C2 — The four layers

> **C2.1 Structural declaration order.** Cassette indices, declared topology and
> structural order describe only the declared cassette arrangement. They **MUST
> NOT** be interpreted as geometric reachability, target proximity, temporal
> sequence, or biological event. *"Topological succession MUST NOT be interpreted
> as geometric reachability."*
>
> **C2.2 Admissible engagement order.** The `ENGAGED` set of a supplied state
> **MUST** be down-closed under `R_union = R_policy ∪ R_requires`, using §20.6.
> Failure remains `ENGAGEMENT_ORDER_VIOLATION` and is distinct from closure
> failure. Admissibility **MUST NOT** be interpreted as geometric reachability.
>
> **C2.3 Deterministic state-conditioned reachability.** For an admissible state,
> Phase 2 **MAY** evaluate closure only for consecutive `ENGAGED` modules using
> the existing effective-anchor, contour-budget, junction-model and tolerance
> contracts. The result is only whether the supplied consecutive target
> assignments are vetoed or not vetoed by the Phase 2 span model.
>
> **C2.4 Later conditional quantitative evaluation.** A state not vetoed by
> Phase 2 **MAY** proceed to Phase 4 composite density and pose marginalization,
> and to Phase 5 shell-bound / obstacle-aware interval construction where
> selected by policy. Such quantities are model-defined conditional geometric
> outputs with their own provenance and approximation contracts. A Phase 2
> success **MUST NOT** imply that later calculations have been run, or that their
> output will be nonzero.

### C3 — Non-implication

> **C3.1.** *"Geometric reachability MUST NOT be interpreted as nonzero binding
> probability, successful binding, affinity, or kinetic persistence."*
>
> **C3.2.** Closure feasibility **MUST NOT** be interpreted as a nonzero density,
> a positive capture integral, a `VALID` node status, or any non-veto downstream
> quantitative outcome under the declared model.
>
> **C3.3.** *"A closure-feasible StateResult certifies only that the declared
> consecutive engaged assignments are not vetoed by the Phase 2 span model."*
>
> **C3.4.** *"A Phase 2 success is an admissibility certificate, not a binding
> prediction."*

### C4 — Field pattern for a non-veto STATE result

> **C4.1.** *"No Phase 2 result may populate conditional_probability,
> effective_local_concentration, capture_integral, survival_correction, or
> joint_score with a non-veto numerical estimate."*
>
> **C4.2.** No numerical encoding of closure success **MAY** be invented. The
> outcome **MUST NOT** be recorded as `1.0`, `0.0`, a flag inside `values`, a
> `value_intervals` entry, a score or a weight.
>
> **C4.3.** For a non-veto Phase 2 `StateResult` that has passed deterministic
> closure, the canonical downstream numerical prediction fields remain
> unpopulated according to the existing §10.1 / §3.6 field-pattern contract, as
> produced by `apply_status_field_pattern` and never written by hand. §20.7.4 N5
> already fixes the empty-pair instance of this.
>
> **C4.4 — PV1-Exactness-State.** *"When Phase 2 introduces objectkind STATE, a
> non-veto StateResult whose canonical numerical prediction fields are all
> unpopulated MUST carry exact_or_approximate = UNDEFINED. This extension applies
> to STATE results only and does not retroactively alter Phase 1c CONFIG-result
> behavior."* **[PV1]**
>
> **C4.5.** Veto and `DEGENERATE` results **MUST** continue to use the
> already-authoritative field patterns. No new zero/null representation is
> created by this entry.
>
> **C4.6 — Scope of C4.1 and C4.3.** The phrase "all canonical numerical
> prediction fields unpopulated" applies **only** to the relevant non-veto
> Phase 2 STATE result. It does **not** apply to veto results and **does not
> contradict the D6 veto examples**, in which probability-like and measure-like
> fields carry `0.0` and density-like fields are null under the §10.1 veto
> pattern.
>
> **C4.7.** A status-imposed `0.0` in a veto result is **not a calculated
> physical quantity**. It is the §10.1 veto field pattern applied to a result
> whose evaluation was refused. It **MUST NOT** be read, reported or propagated
> as a computed value, a measurement, or an estimate of zero.

### C5 — Control flow and failure separation

> **C5.1.** *"An inadmissible state MUST NOT enter the chain-closure sweep."*
> On an order violation, `chain_closure_feasible` and `cassette_contour_budget`
> **MUST NOT** be invoked and no closure-pair set is produced (§20.7.5 N16).
>
> **C5.2.** *"A closure-infeasible state MUST veto downstream numerical
> evaluation under the existing D6 propagation contract."*
>
> **C5.3.** `ENGAGEMENT_ORDER_VIOLATION` is a different failure type from closure
> failure. Its propagation is **not** derived from D6, which governs
> closure-failure propagation only. An inadmissible state cannot issue a
> `StateCertificate`, and `evaluate_node` may be signature-level unavailable for
> it under the existing contract.
>
> **C5.4 — PV1-Order-Violation-Propagation.** *"If a Phase 2 node, path, or
> network result is requested under an inadmissible supplied engagement state,
> the propagation behavior is a pending extension. Until ratified, the
> implementation MUST NOT fabricate a node, path, or network result merely to
> imitate D6 closure-veto propagation."* **[PV1, pending]**
>
> **C5.5.** Whether such a result, once ratified, carries a reference to the
> originating `StateResult` identifier is a **possible future extension only**.
> This entry does not claim that any such reference already applies to
> order-violation results. D6's own propagation contract for closure-vetoed
> states is unaffected and unmodified.

### C6 — Non-boolean closure outcome

> **C6.1.** *"A non-boolean chain-closure outcome MUST NOT be coerced to TRUE,
> MUST NOT issue a StateCertificate, and MUST NOT yield VALID solely through
> truthiness, fallback conversion, or absence of a FALSE result."*
>
> **C6.2.** It **MUST NOT** be converted by `bool()`, by truthiness testing, by
> `== True`, by `is not FALSE`, by a default value, by an `or` fallback, or by
> suppressing an exception raised while computing it. Every call site **MUST**
> dispatch exhaustively over the outcome domain.
>
> **C6.3.** Where the existing contract already assigns
> `ENGAGED_POSE_UNDERDETERMINED` to an undetermined engaged pose, that handling
> applies unchanged. This entry introduces no status, assigns no status to the
> non-boolean closure outcome, and does not settle whether the closure
> predicate's non-boolean return is exactly that condition. The precise return
> domain of `chain_closure_feasible` and its binding to a reason string are
> proposed separately and are **not** adopted here. C6.1 holds regardless of how
> that is resolved.

### C7 — Emitted runtime text

> **C7.1.** *"Phase 2 diagnostics, result labels, and remediation text MUST NOT
> characterize a structural or geometric result as an experimentally observed
> biological outcome, kinetic event, affinity estimate, residence-time estimate,
> or claim of simultaneous real-world occupancy."* **[PV1]**
>
> **C7.2.** C7.1 is a **semantic-overclaim prohibition, not a lexical filter.**
> It applies only to newly introduced user-facing runtime diagnostic,
> result-label and remediation text in cassette-mode Phase 2 evaluation.
>
> **C7.3.** C7.1 does **not** prohibit ordinary technical discussion in the
> decision record, documentation, identifiers, source comments, test labels, or
> audit notes. No forbidden-word list, substring ban, annex, text-scanning audit
> item or text-scanning must-never-happen rule is created by this entry, and none
> **MAY** be derived from it.

### C8 — Phase 2 / Phase 5 shell-bound boundary

> **C8.1.** Phase 2 **MAY** detect and record unresolved upstream bodies, or the
> applicable unresolved-upstream policy, where existing contracts permit.
>
> **C8.2.** Phase 2 **MUST NOT** emit `SHELL_BOUND` as an evaluation status or
> reason merely because an unresolved upstream body exists.
>
> **C8.3.** Phase 2 **MUST NOT** emit `BOUND_ONLY` provenance.
>
> **C8.4.** Phase 2 **MUST NOT** construct lower/upper probability or
> accessibility intervals, and **MUST NOT** assemble shell-bound interval
> results.
>
> **C8.5.** `SHELL_BOUND` status and reason semantics, and obstacle-aware
> interval construction, belong only to Phase 5.
>
> **C8.6.** Where Phase 2 records this condition, it uses narrow diagnostic
> terminology only — `unresolved_upstream_ids`, `unresolved_upstream_policy`,
> `downstream_numerical_evaluation_deferred` — within the three-key limit of
> §20.7.5 N14. These diagnostics describe **deferred applicability only**, never
> a completed Phase 5 calculation.

### C9 — Normative examples

> **C9.1.** `S = {D1@T1}`. A conditioning state containing only a declared
> D1-to-T1 assignment. It does not emit a `D2` or `D3` numerical prediction, and
> does not assert `D2` or `D3` reachability, engagement, proximity, or
> persistence. No closure pair exists, so per §20.7.4 N1–N2 the sweep completes
> over an empty domain and `chain_closure_feasible` is not invoked.
>
> **C9.2.** `S = {D1@T1, D2@T2}`. Existing order-admissibility checks run first.
> If admissible, closure is evaluated only for `D1`–`D2`. If closure fails, the
> existing closure-veto behaviour applies and downstream numerical evaluation is
> not entered. If closure passes, no numeric success score is emitted in Phase 2.
>
> **C9.3.** `S = {D1@T1, D2@T2, D3@T3}`. Only `D1`–`D2` and `D2`–`D3` are
> evaluated. `D1`–`D3` **MUST NOT** be evaluated as a direct closure pair while
> `D2` is `ENGAGED`.
>
> **C9.4.** `S = {D1@T1, D3@T3}` with `D2` not `ENGAGED`. Acceptance or rejection
> first follows the existing `R_union` down-closure rule. If admissible under
> existing policy, closure-pair selection follows the existing formal
> "consecutive `ENGAGED` modules" definition. No new order policy is introduced,
> and raw cassette adjacency **MUST NOT** be assumed by default. Physical-path
> membership for the contour budget is unaffected (§20.7.5 N9–N11).

## Schema / API impact

**No change to any existing shape.**

| Concept | Impact |
|---|---|
| `StateResult`, `StateCertificate` | preserved |
| `evaluate_state`, `evaluate_node`, `chain_closure_feasible` | signatures preserved |
| `cassette_effective_anchor`, `cassette_contour_budget` | preserved |
| `EvaluationResult` field set | unchanged; no new top-level field |
| canonical value fields | unchanged, five members |
| status taxonomy, exactness, provenance | no new member |
| reason strings | no new reason introduced by this entry |
| diagnostic codes | no new code introduced by this entry |
| result-id rules, zero/null conventions, cache-key contract | unchanged |

No probability API. No kinetic API. No new scientific or mechanistic parameter.
Existing diagnostics, reasons and provenance fields are reused throughout.

**The two PV1 items with schema-adjacent effect:**

- **C4.4 PV1-Exactness-State** constrains `exact_or_approximate` for non-veto
  STATE results only. It adds no field and does not alter CONFIG-result
  behaviour, where the existing §10.8 guard applies unchanged.
- **C1.4** requires `upstream_state.assignments` to be derived from the supplied
  state. This is an obligation on the producer, not a shape change. It neither
  resolves nor depends on the open question of a schema for `upstream_state`.

**C5.4 PV1-Order-Violation-Propagation is pending**, not adopted. No schema
follows from it until ratified.

**Separately proposed, not adopted here, and not relied upon:** the canonical
veto-reference carrier for closure propagation; the `ENGAGEMENT_ORDER_VIOLATION`
result contract; the closure-predicate return domain; and the deterministic
`StateResult` identifier rule. C5.2, C5.5 and C6.3 are written so that they hold
under any resolution of those.

## Validation / runtime behavior

**V1.** Layer order is C2.1 → C2.2 → C2.3, unconditionally: Phase 1c
configuration validation, then state-schema validation, then admissibility, then
the closure sweep. This is the existing Phase 2 validation order.

**V2.** On an admissibility failure the sweep does not run; the closure predicate
and the contour budget are not invoked and no closure-pair set is produced
(C5.1).

**V3.** On a closure veto, downstream numerical evaluation is vetoed through the
existing D6 propagation contract (C5.2). The veto field pattern is the existing
§10.1 one, and its zeros are not computed quantities (C4.7).

**V4.** On a non-boolean closure outcome, no `StateCertificate` is issued and
`VALID` is not reachable by coercion (C6.1–C6.2).

**V5.** On a non-veto result, a `StateCertificate` is issued per §10.7, the five
canonical fields remain unpopulated, and `exact_or_approximate` is `UNDEFINED`
per C4.4.

**V6.** In every branch, including early returns, the supplied state is
serialized unchanged in `upstream_state` (C1.4).

**V7.** No Phase 4 or Phase 5 module is imported or invoked during Phase 2
(§20.7.4 N6, C8).

**V8.** Determinism is unaffected. These clauses remove implementation freedom
and add no state, no ordering dependence and no import-time effect.

## Tests

Identifiers remain temporary alphabetical **T-a … T-j** until the authoritative
base-spec test ledger is available. All live in the Phase 2 state test module
except T-h, and none imports a Phase 4 or Phase 5 module. **No test in this
entry performs substring matching over source or emitted text.**

**T-a.** `S = {D1@T1}`, admissible. No probability and no numerical prediction:
all five canonical fields `None`; `value_intervals` empty; `closure_pairs`
present and `[]`; closure-predicate invocations `0` and the spy count `0`; no
diagnostic asserts `D2` or `D3` reachability, engagement, proximity or
persistence, checked against the emitted-key allow-list.

**T-b.** `S = {D1@T1, D2@T2}`, closure feasible. No claim of successful binding,
nonzero probability, affinity or persistence: the five canonical fields and both
status flags compared component-wise against `apply_status_field_pattern` output
rather than hard-coded; no `values` entry equals `1.0` or `0.0`;
`exact_or_approximate is UNDEFINED` (C4.4); `value_intervals` empty; no
provenance label implying a computed quantity.

**T-c.** Same state, closure infeasible. Vetoed before any later machinery: veto
status and closure reason; the §10.1 veto pattern via
`apply_status_field_pattern`; a trap finder on the import path for the Phase 4/5
module names was never triggered; none of those names in `sys.modules` after the
call; no density, capture, marginalization, survival or interval function
entered, asserted by method-trace.

**T-d.** `S = {D1@T1, D2@T2, D3@T3}`. Exactly `[("D1","D2"), ("D2","D3")]` by
equality, in increasing index order; `("D1","D3")` absent; invocations `== 2`
with the spy recording exactly those two pairs.

**T-e.** Two fixtures, one per failure type. The results differ in status **and**
in reason; for the order violation the closure-predicate and contour-budget spies
are both `0`, and the recorded call sequence contains no entry after
admissibility returned.

**T-f.** Predicate patched to return the non-boolean outcome. Status is not
`VALID`; no `StateCertificate` is issued; three-way distinctness — the result
differs from both the feasible and the infeasible outcome, so no collapse
occurred; coercion is impossible, asserted by the outcome domain rejecting
`bool()` rather than by inspecting a status string. The test does **not** assert
a particular reason string, because C6.3 leaves that binding unsettled.

**T-g.** Parametrized over the non-veto and veto branches. Canonical fields
unpopulated for the non-veto STATE result; in the veto branch values and flags
equal `apply_status_field_pattern` output exactly, so zeroing and nulling occur
only where the existing pattern requires them, consistent with the D6 veto
examples (C4.6).

**T-h.** Static and dynamic import-boundary test. Static: an AST pass over the
five Phase 2 modules and their transitive package import closure finds no
reference to the Phase 4 density / pose-marginalization modules or the Phase 5
shell-bound interval modules. Dynamic: after `evaluate_state` and
`evaluate_node`, none is in `sys.modules` and the trap finder was never
triggered. Additionally every emitted diagnostic key is a member of the Phase 2
allow-list — closure-pair and invocation keys, shielding-ancestor, the three
unresolved-upstream keys, the contour-budget breakdown, and the pair endpoint and
span quantities. This is a structural check on emitted keys, not a text scan.

**T-i.** A deep copy of the supplied state is taken before the call. The state
equals the copy afterwards; container lengths and identity unchanged if mutable;
`upstream_state.assignments` reproduces the supplied assignments exactly and
contains no key absent from the state. Parametrized over all branches of the
validation order, so early returns are covered (C1.4, V6).

**T-j.** **Conditional on ratification.** If and only if
PV1-Order-Violation-Propagation (C5.4) is later adopted, the propagated result
refers exactly to the originating `StateResult` identifier: equality against the
originating result's field, not a recomputation, and byte-identical in the
serialized form. Until ratification this test asserts the negative of C5.4 — that
no node, path or network result is fabricated under an inadmissible state.

## Explicit non-goals

This entry introduces none of the following and **MUST NOT** be read as implying
any of them:

1. **No conformational coupling model.**
2. **No induced-fit model.**
3. **No `k_on` / `k_off`, residence-time, dwell-time, rebinding, or temporal
   sequential-dynamics model.**
4. **No affinity, avidity, potency, efficacy, uptake, delivery, or
   biological-performance prediction.**
5. **No density, probability, capture integral, pose marginalization, survival
   correction, or shell-bound interval computation in Phase 2.**
6. **No modification of D6, D8, §20.5, §20.6, §10.7, §10.8, the core geometry
   equations, the status taxonomy, or the base-state schema.**

Additionally: no new probability or kinetic API; no new scientific or mechanistic
parameter; no new geometry; no global text substring filter, forbidden-word list,
annex, text-scanning audit item or text-scanning must-never-happen rule; no new
status or reason string; no new numeric encoding of closure success; no change to
Phase 1c's ownership of structural validation, Phase 4's ownership of composite
density and pose marginalization, or Phase 5's ownership of obstacle-aware
shell-bound intervals.

---

# Implementation handoff

## Phase 2 modules that may be implemented now

| Module | Scope unblocked by this entry |
|---|---|
| `gotne/cassette_frames.py` | effective-anchor propagation |
| `gotne/cassette_budget.py` | contour budget over the full physical path, element membership insensitive to engagement (§20.7.5 N9–N11) |
| `gotne/cassette_state.py` | state schema; admissibility and down-closure under `R_union`; the reason constants as one central closed set; `StateResult` construction routed through `apply_status_field_pattern`; `StateCertificate` gating |
| `gotne/closure.py` | consecutive-engaged-pair selection per §20.5; the deterministic veto predicate; the empty-pair path of §20.7.4 |
| `gotne/evaluate_node.py` | node-level evaluation under a certificate; closure-veto propagation per D6 only |
| Phase 2 import-boundary test module | the static and dynamic checks of T-h |

Build order follows the data flow: frames → budget → state → closure →
evaluate_node.

## Modules that must not be implemented yet

Neither imported nor invoked by Phase 2 code or Phase 2 tests: the Phase 4
composite-density, SO(3)-grid and pose-marginalization modules, and the Phase 5
shell-bound and interval modules.

Also not to be written yet, because the governing decision is pending rather than
the phase: any node, path or network result produced under an inadmissible state
(C5.4); any shell-bound or interval assembly in Phase 2 (C8); any numeric
encoding of closure success (C4.2).

## Decisions pending PV1

| Item | Clause | State |
|---|---|---|
| Exactness of a non-veto STATE result | C4.4 | proposed in this entry, **[PV1]** |
| Immutability audit of `upstream_state.assignments` | C1.4 | proposed in this entry, **[PV1]** |
| Semantic-overclaim rule for runtime text | C7.1 | proposed in this entry, **[PV1]** |
| Order-violation propagation to node/path/network | C5.4 | **pending, not adopted** |
| Reference to the originating `StateResult` identifier in an order-violation propagation | C5.5 | possible future extension only |
| Closure-predicate return domain and its binding to a reason string | C6.3 | proposed separately, not adopted |
| `ENGAGEMENT_ORDER_VIOLATION` result contract (status, field pattern, exactness, provenance) | — | proposed separately, not adopted |
| Canonical veto-reference carrier for closure propagation | — | proposed separately, not adopted |
| Deterministic `StateResult` identifier rule | — | proposed separately, not adopted |
| `StateCertificate` serialized field list; whether `APPROXIMATION_REQUIRED` may issue one | — | open |
| `i` / `j` in the closure predicate: identifiers or indices, and which base | — | open; module and tether index bases differ |
| Rigid-spacer span derivation and element-id naming for the budget element table | — | open |
| Behaviour when the `policy` argument disagrees with `cfg.policy` | — | open |
| Return of `evaluate_state` for a non-cassette topology mode or a non-valid Phase 1c configuration | — | open |
| In-memory versus serialized form of the closure-pair list | — | open |
| Positive form for a skipped sweep (§20.7.4 N4 forbids encoding meaning by absence) | — | open |
| JSON safety of non-finite floats in geometric diagnostics | — | open |
| Test-identifier ledger | T-a…T-j | temporary until the base-spec ledger is available |

A measurement task, not a design task: fix the regression baseline in the real
repository layout once, and bind the no-regression gate to that number before the
first patch. The stated figure does not match the folder snapshot, and the
discrepancy is attributable to layout rather than logic.

## Why Phase 4 and Phase 5 must wait

**Phase 4** owns composite density and pose marginalization. The relevant point
for Phase 2 is that the marginalization selected by the orientation-marginalized
pose-resolution policy is precisely the operation that can leave a closure
operand not single-valued. Phase 2 must therefore **return** that condition
rather than resolve it; performing the marginalization to obtain a decisive
closure answer would move a Phase 4 computation into Phase 2 and would convert a
declared deferral into a fabricated result.

**Phase 5** owns `SHELL_BOUND` semantics and obstacle-aware interval
construction. Phase 2 can observe that an unresolved upstream body exists and
that a policy selects shell-bound treatment, but it cannot construct the bound.
Emitting `SHELL_BOUND`, `BOUND_ONLY` or any interval from Phase 2 would present a
deferred applicability as a completed calculation. Under that policy Phase 2
emits exactly the three diagnostic keys of §20.7.5 N14 and the deferral flag, and
nothing else (C8.6).
