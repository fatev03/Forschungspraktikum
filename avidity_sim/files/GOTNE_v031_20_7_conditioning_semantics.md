# §20.7 (new) — Conditioning semantics for supplied evaluation states

Proposed clarification entry for the GOTNE v0.3.1 decision record.
Introduces no geometric, physical, biological, kinetic, thermodynamic,
probabilistic or experimental mechanism.

---

## 0. Numbering note (read first)

§20.7 is **referenced but never defined** in the material this entry was written
against. The D-record Addendum A enumerates §17.1, §17.2, §17.4, §17.6, §18.2,
§18.4, §18.5.1, §19.2.1, §19.3.1, §10.7, §20.5, §20.6, §11.8, §11.6, §13, §12 —
the highest `§20.x` is **§20.6**. `GOTNE_v031_phase2_semantic_closure.md` §2
nevertheless states that "§20.7'nin mevcut gövdesi (sequential engagement
semantics, conditional reachability, order-policy tanımları) değişmez" and
appends **§20.7.3 (N0)**, **§20.7.4 (N1–N7)** and **§20.7.5 (N8–N17)** to it.

This entry supplies that missing parent body. Accordingly:

- it occupies **§20.7, §20.7.1 and §20.7.2 only**;
- **§20.7.3, §20.7.4 and §20.7.5 remain owned by the closure document** and are
  neither restated nor amended here;
- normative statements here are numbered **C1…C16** because **N0–N17 are already
  allocated** by §20.7.3–§20.7.5.

The substantive content of "sequential engagement semantics, conditional
reachability, order-policy definitions" that the closure document attributes to
§20.7 in fact lives in **§20.5** (chain closure, per D6) and **§20.6** (`R_union`,
per D8). This entry cross-references both and replaces neither. **[PV1]**

---

## 1. Chosen rule

An evaluation state `S` is a **caller-supplied conditioning declaration**, not a
model output, not an observation, and not a claim about the world. Everything
Phase 2 produces is conditional on `S` exactly as supplied.

The contract is currently silent on three points, and this entry closes them and
nothing else:

1. **Immutability.** Nothing states that evaluation may not alter `S`. D6 places
   `assignments` inside `upstream_state`, but no rule requires that mapping to
   equal what the caller passed. An implementation could normalize, reorder,
   complete or repair `S` and still satisfy every existing clause.
2. **Layer separation.** `phase2-spec-corrections.md` M10 records that
   "L2 admissibility" is *not defined in the files read*, although §20.7.3 N0 and
   the Phase 2 contract both rely on the term. The four layers are used
   throughout but never named as a set, and the **non-implications between them**
   are stated only for the `VALID` verdict (N0, N3, N17), not as a chain.
3. **Interpretation of runtime text.** N0/N3/N17 forbid *reading* a result as a
   real-world outcome. Nothing forbids Phase 2 from *emitting* text that invites
   that reading.

The chosen rule is therefore: **fix `S` as immutable conditioning input, name the
four layers, and state the non-implication chain between them as normative.**
No new mechanism, no new field, no new API.

---

## 2. Normative wording

### §20.7 (v0.3.1) Conditioning semantics for supplied evaluation states

> An evaluation state `S` is a caller-supplied conditioning declaration. Every
> Phase 2 result is a statement about `S` under the declared configuration and
> policy, and carries no content beyond that. The scope of a `VALID` verdict is
> fixed by §20.7.3 N0 and is not widened by anything in this section.

---

### §20.7.1 (new) Conditioning input

> **C1.** `S` is supplied by the caller. Evaluation **MUST NOT** mutate, complete,
> repair, reorder, infer, normalize or replace `S`, in whole or in any part.
> Absent declarations remain absent; they **MUST NOT** be defaulted to `ENGAGED`,
> to `UNENGAGED`, or to any other label.
>
> **C2.** The labels and target assignments in `S` are conditioning inputs only.
> They are **not** assertions that the declared assignments occur, are
> simultaneous, are attainable, or are observed.
>
> **C3.** Every result whose evaluation was conditioned on `S` **MUST** preserve
> `S` exactly in its upstream-state provenance — in the existing
> `upstream_state.assignments` mapping of §10.7 / D6, or in that mapping's
> existing equivalent for the result kind. "Exactly" is REQUIRED to mean: the same
> module identifiers, the same labels and the same target identifiers as supplied,
> with no addition, no removal and no substitution. Order-insensitive comparison
> is permitted; content-altering canonicalization is not.
>
> **C4.** Where a result kind derives `upstream_state.hash` (§10.7 / D6), that
> hash **MUST** be taken over the supplied `S`, not over any internal working
> copy. An implementation that builds a working copy **MUST** treat it as
> non-authoritative and **MUST NOT** serialize it in place of `S`. **[PV1]**
>
> **C5.** The system has **no temporal variable in this phase**. `S` declares no
> ordering in time. Engagement order under §20.6 `R_union` is a *constraint
> relation on admissible declarations*, not a sequence of events, not a pathway,
> and not a kinetic schedule. No Phase 2 output **MAY** be expressed as, or
> labelled with, a time, a rate, a duration, a step index or an event sequence.

---

### §20.7.2 (new) Layer separation and non-implication

> **C6.** Four layers are distinguished. The names are normative; the behaviour of
> each layer is defined by the sections cited and is unchanged here. **[PV1]**
>
> | Layer | Content | Defined by |
> |---|---|---|
> | **L1** | structural declaration order of modules on the cassette | Phase 1c structural configuration validation |
> | **L2** | admissibility of `S`: down-closure of its `ENGAGED` set under `R_union = R_policy ∪ R_requires` | §20.6 (D8) |
> | **L3** | deterministic, state-conditioned closure feasibility for consecutive declared entries, over the existing effective-anchor and contour-budget contract | §20.5 (D6), §18.2, §20.7.4, §20.7.5 |
> | **L4** | later conditional quantitative evaluation under an eligible state | Phase 4; Phase 5 where selected by policy |
>
> Phase 1c owns L1. Phase 2 owns L2 and L3. Phase 2 **MUST NOT** enter L4.
>
> **C7 (non-implication chain).** Each of the following **MUST** hold:
> - L1 **MUST NOT** imply L2: structural succession on the cassette does not make
>   a state admissible.
> - L1 **MUST NOT** imply L3: structural succession does not imply closure
>   feasibility.
> - L2 **MUST NOT** imply L3: admissibility does not imply closure feasibility.
> - L3 **MUST NOT** imply any non-veto L4 result: a passed closure check
>   establishes only the absence of a deterministic veto at L3.
>
> **C8.** A passed closure check **MUST NOT** be labelled, logged, serialized or
> documented as a real-world event, an experimental outcome, an observation, a
> persistence claim, a simultaneity claim or a temporal sequence. This restates no
> more than §20.7.3 N0 and §20.7.5 N17 and extends them to no new verdict.
>
> **C9.** A failed closure check **MUST NOT** be labelled as a real-world
> impossibility. It asserts only that the declared conditioning is vetoed by the
> deterministic closure predicate under the declared configuration and policy.
>
> **C10 (consecutive-pair rule, by reference).** Pair selection is defined by
> §20.5 and constrained by §20.7.4 N1–N2 and §20.7.5 N8. It is restated here only
> as worked examples, which are normative as examples and introduce no new rule:
>
> - `S = {D1@T1}` — no closure pair is evaluated solely because `D1` is declared.
>   Per §20.7.4 N2, `chain_closure_feasible` **MUST NOT** be invoked.
> - `S = {D1@T1, D2@T2}` — the `D1`–`D2` consecutive pair is evaluated, and only
>   after L2 admissibility passes.
> - `S = {D1@T1, D2@T2, D3@T3}` — `D1`–`D2` and `D2`–`D3` are evaluated, and only
>   those. `D1`–`D3` **MUST NOT** be evaluated directly, because `D2` is declared
>   between them.
> - `S = {D1@T1, D3@T3}` with `D2` not declared — admissibility is decided solely
>   by §20.6 `R_union` under the declared `engagement_order_policy`. If admissible,
>   pair selection follows the existing definition of consecutive **declared**
>   modules, which yields `(D1, D3)` per §20.7.5 N8. Physical-path membership for
>   the §18.2 budget is unaffected, per §20.7.5 N9–N11.
>
> **C11 (result semantics).** A non-veto Phase 2 state result is an
> **eligibility / admissibility certificate only**. Its canonical numerical
> prediction fields **MUST** follow the existing null / exactness contract of
> §10.1, §3.6, §10.7 and §10.8 as applied by `apply_status_field_pattern`, and as
> already fixed for the empty-pair case by §20.7.4 N5. No new numeric encoding of
> closure success **MAY** be introduced: closure outcome **MUST NOT** be recorded
> as `1.0`, `0.0`, a flag inside `values`, a `value_intervals` entry, a score, a
> weight, or any other member of `CANONICAL_VALUE_FIELDS`.
>
> **C12.** Veto and degenerate field patterns remain governed by §10.1, §3.6,
> §10.7 and §10.8. This section **MUST NOT** be read as altering any of them.
>
> **C13.** No new probability, kinetics or occupancy API **MAY** be created.
>
> **C14 (semantic rule on runtime text).** Newly introduced Phase 2 runtime text —
> diagnostic `message`, `remediation`, and any new `code` literal — **MUST NOT**
> characterize structural or geometric output as a real-world experimental,
> kinetic or biological outcome. This is a semantic obligation on the author of
> the text. It is **REQUIRED** to be enforced by review against the fixed reason
> and code sets, **not** by a global substring ban and **not** by a lexical
> scanner over the source tree. **[PV1]**

---

### §20.7.2.1 Failure separation

> **C15.** The three Phase 2 reasons are distinct and **MUST NOT** be merged,
> aliased or substituted for one another. Their spelling is the existing
> underscore form fixed by the Phase 2 contract and by
> `GOTNE_v031_phase2_semantic_closure.md` §4:
>
> | Reason | Layer | Meaning |
> |---|---|---|
> | `ENGAGEMENT_ORDER_VIOLATION` | L2 | `S` is not down-closed under `R_union` (§20.6, D8) |
> | `CHAIN_CLOSURE_VIOLATED` | L3 | a consecutive declared pair is vetoed by the closure predicate (§20.5, D6) |
> | `ENGAGED_POSE_UNDERDETERMINED` | L3 | the closure predicate did not return a decisive result |
>
> **C16.** Control flow and propagation:
>
> - An `ENGAGEMENT_ORDER_VIOLATION` **MUST** prevent entry into the closure sweep.
>   L2 precedes L3 unconditionally. This is the general form of §20.7.5 N16 and of
>   the Phase 2 validation order; neither is amended.
> - A `CHAIN_CLOSURE_VIOLATED` **MUST** veto downstream numerical evaluation using
>   the existing `StateResult` propagation semantics of §10.7 / D6. No new
>   propagation channel is introduced.
> - A non-decisive closure result — the non-boolean member of the existing `Tri`
>   return type of `chain_closure_feasible` — **MUST** yield
>   `ENGAGED_POSE_UNDERDETERMINED`. It **MUST NOT** be treated as success, **MUST
>   NOT** be coerced to a boolean, and **MUST NOT** yield `VALID` by fallback,
>   by default-value, or by exception suppression. Per the Phase 2 contract no
>   `StateCertificate` is issued in this case.

---

### §20.7.2.2 Phase boundary

> **C17.** Phase 2 **MUST NOT** compute a density, a conditional probability, a
> local concentration, a capture integral, a pose marginalization, a survival
> term, a shell-bound interval, or any new score. This restates the existing
> Phase 2 non-goals and adds nothing.
>
> **C18.** Phase 2 **MAY** preserve declared unresolved-upstream policy as
> diagnostics, within the exact three-key limit of §20.7.5 N14, without performing
> any later-phase computation.
>
> **C19.** Phase 5-only shell-bound interval semantics — a `SHELL_BOUND` reason, a
> `BOUND_ONLY` provenance label, an at-risk weight, or any `value_intervals`
> entry — **MUST NOT** be emitted as a Phase 2 result (§20.7.5 N15).

---

## 3. Schema / API impact

**None.** This entry is schema- and API-neutral by construction.

| Concept | Impact |
|---|---|
| `StateResult`, `StateCertificate` | unchanged |
| `evaluate_state`, `evaluate_node`, `chain_closure_feasible` | signatures unchanged |
| `cassette_effective_anchor`, `cassette_contour_budget` | unchanged |
| `EvaluationResult` field set | unchanged; **no** new top-level field |
| `CANONICAL_VALUE_FIELDS` | unchanged, five members |
| `Status`, `Exactness`, `Provenance` members | unchanged |
| `status_reason` set | unchanged, the three reasons of C15 |
| Diagnostic codes | no new code introduced by this entry |

The only semantic annotation this entry attaches to an existing concept is C3/C4:
`upstream_state.assignments` and `upstream_state.hash` are **REQUIRED** to be
derived from the supplied `S`. That is an obligation on the producer, not a shape
change. It does not resolve **M2** (no schema exists for `upstream_state`), and
does not depend on its resolution.

### Deliberately not resolved here

This entry **MUST NOT** be read as settling any of the following, which remain
open in `phase2-spec-corrections.md`:

- **M1 (BLOCKING)** — carrier of `vetoing_state_result_id`: §20.7.4 N7 places it
  inside `upstream_state`; D6 places it in the `quantities` of a
  `STATE_VETO_PROPAGATED` INFO diagnostic. C16 says only that the **existing**
  propagation semantics are used, whichever carrier is chosen.
- **M5 (BLOCKING)** — the status class and provenance label of
  `ENGAGEMENT_ORDER_VIOLATION`. C15 fixes its layer and meaning; C16 fixes its
  control-flow precedence. Neither requires the status class, and neither
  supplies it.
- **M4** — whether a skipped sweep is recorded as absent or as `CHECK_SKIPPED`.
- **M10** — the members of `Tri`. C16 refers to "the non-decisive member" without
  naming it.
- The §10.8 exactness guard's extension to `object_kind == "STATE"`.

---

## 4. Validation / runtime behavior

**V1.** Layer order is L1 → L2 → L3, and is unconditional. Phase 1c
configuration validation precedes state-schema validation, which precedes L2
admissibility, which precedes the L3 closure sweep. This is the existing Phase 2
validation order; this entry restates its first three steps only to anchor C16.

**V2.** On an L2 failure, the closure sweep does not run:
`chain_closure_feasible` and `cassette_contour_budget` are not invoked and no
closure-pair set is produced (§20.7.5 N16).

**V3.** On an L3 veto, downstream numerical evaluation is vetoed through the
existing `StateResult` propagation of §10.7 / D6.

**V4.** On a non-decisive L3 result, the state result carries
`ENGAGED_POSE_UNDERDETERMINED` under the existing unknown-class field pattern and
issues no `StateCertificate`.

**V5.** In every branch above, the supplied `S` is serialized unchanged in
upstream-state provenance (C3), including branches that terminate early. An early
return **MUST NOT** omit or abbreviate it.

**V6.** Determinism is unaffected: C1–C5 remove a source of implementation
freedom and add no state, no ordering dependence and no import-time effect.

---

## 5. Tests

Six tests. All belong in `tests/test_phase2_state.py`, are `unittest`-style, use
the existing fixture approach, and import no Phase 4 or Phase 5 module.

> **Test-ID caveat.** The identifiers below are proposed as **T85–T90**. The
> material this entry was written against shows T34–T56, T57–T78 (D-record) and
> T79, T83 (closure doc); T80–T82 and T84 are unaccounted for. The block **MUST**
> be confirmed against the full T-list before adoption. **[PV1]**

### T85 — Supplied state is not mutated

*Covers C1, C3, C4.* Fixture: valid three-module `LINEAR_ORDERED_CASSETTE`,
`S = {D1@T1, D2@T2}`, `ANY_ORDER`.

1. A deep copy of `S` is taken before the call.
2. After `evaluate_state`, `S` compares equal to the copy — same module ids, same
   labels, same target ids, nothing added or removed.
3. If the state object is mutable, its identity and its container lengths are
   unchanged.
4. `result.upstream_state["assignments"]` reproduces the supplied assignments
   exactly; no module absent from `S` appears in it.
5. Parametrized over all four branches of §4 (L2 failure, L3 veto, non-decisive
   L3, success): assertion 4 holds in every branch, per V5.

### T86 — No defaulting of absent declarations

*Covers C1.* `S = {D1@T1, D3@T3}` with `D2` not declared, `ANY_ORDER`.

1. `result.upstream_state["assignments"]` contains keys for `D1` and `D3` only.
2. No `D2` entry appears with `UNENGAGED`, `ENGAGED`, `None` or any other label.
3. `closure_pairs == [("D1", "D3")]` — the absent module produced no synthesized
   declaration and no intermediate pair (cross-check against §20.7.5 N8).

### T87 — Order violation precedes the closure sweep

*Covers C16, V2.* Same `S = {D1@T1, D3@T3}`, but
`EngagementOrderPolicy.STRICT_PROXIMAL_TO_DISTAL`.

1. `result.status_reason == "ENGAGEMENT_ORDER_VIOLATION"`.
2. `chain_closure_feasible` spy call count is `0`.
3. `cassette_contour_budget` spy call count is `0`.
4. Control-flow ordering is proven, not merely co-observed: the spies record a
   monotonic call sequence, and the assertion is that the sequence contains no
   entry after the admissibility check returned.

This test overlaps T83 Policy B by construction. It **MUST** be written as a
reference to T83's fixture rather than a second copy of it; if T83 is adopted
first, T87 reduces to assertion 4 only.

### T88 — Consecutive-pair selection over three declared modules

*Covers C10.* `S = {D1@T1, D2@T2, D3@T3}`, `ANY_ORDER`.

1. `closure_pairs == [("D1", "D2"), ("D2", "D3")]` — exact equality, in
   increasing index order per §20.5.
2. `("D1", "D3")` does not appear.
3. `closure_predicate_invocations == 2`, and the spy count is `2`.
4. The two invocations carry the pairs of assertion 1 and no others.

### T89 — Non-decisive closure result is not success

*Covers C16, V4.* `chain_closure_feasible` is patched to return the non-decisive
member of `Tri` for one pair.

1. `result.status` is not `Status.VALID`.
2. `result.status_reason == "ENGAGED_POSE_UNDERDETERMINED"`.
3. No `StateCertificate` is issued.
4. The unknown-class field pattern applies: the five canonical fields are null and
   `nulled_due_to_status is True`, exactly as `apply_status_field_pattern`
   produces it for the chosen status — the test asserts equality with that
   function's output rather than hard-coding the pattern.
5. Negative control: the non-decisive value is not coerced. The test asserts the
   result differs from the result obtained when the predicate returns the
   decisive-true member.

### T90 — No new numerical payload

*Covers C11, C13, C17, C19.* Parametrized over the success branch and the L3-veto
branch.

1. `set(result.values.keys()) == set(CANONICAL_VALUE_FIELDS)` — no field added.
2. `dict(result.value_intervals) == {}`.
3. No diagnostic `quantities` key matches probability, density, concentration,
   capture, survival, occupancy, rate, weight or interval semantics, checked
   against an explicit allow-list of the keys Phase 2 is permitted to emit —
   `closure_pairs`, `closure_predicate_invocations`, `shielding_ancestor`,
   `unresolved_upstream_ids`, `unresolved_upstream_policy`,
   `downstream_numerical_evaluation_deferred`, `contour_budget_breakdown`,
   `upstream`, `downstream`, `required_span_nm`, `D_min_nm`, `D_max_nm`, and the
   `vetoing_state_result_id` carrier once M1 is settled. An unlisted key fails the
   test. **[PV1]**
4. No diagnostic carries a `SHELL_BOUND` reason or a `BOUND_ONLY` provenance
   label.
5. Closure success is not numerically encoded: in the success branch every
   canonical field is null, and no `values` entry equals `1.0` or `0.0`.

Assertion 3 is the machine-checkable half of C14. The semantic half — that
message text does not characterize geometry as a real-world outcome — is a review
obligation and is deliberately **not** automated, per C14.

---

## 6. Explicit non-goals

This entry does **not**:

1. introduce any geometric, physical, biological, kinetic, thermodynamic,
   probabilistic or experimental mechanism;
2. restate, amend, replace or reinterpret **D6** or **D8**, or §20.5, §20.6,
   §18.2, §10.1, §3.6, §10.7 or §10.8;
3. modify §20.7.3 (N0), §20.7.4 (N1–N7) or §20.7.5 (N8–N17), which remain owned by
   `GOTNE_v031_phase2_semantic_closure.md`;
4. change any public API signature, `EvaluationResult` field, enum member,
   `status_reason` literal, diagnostic code or `CANONICAL_VALUE_FIELDS` entry;
5. add a probability, kinetics, occupancy or interval API;
6. add a global substring ban or a lexical scanner;
7. resolve **M1**, **M5**, **M4**, **M10**, the `StateCertificate` field list, the
   deterministic `result_id` rule, the `method_version` value, or the §10.8
   guard's extension to `STATE`;
8. define a temporal, sequential or kinetic reading of engagement order;
9. alter Phase 1c's ownership of structural configuration validation, Phase 4's
   ownership of composite quantities and pose marginalization, or Phase 5's
   ownership of obstacle-aware shell-bound intervals;
10. constitute a claim about binding, affinity, occupancy or any observable
    quantity.

---

## Change rationale

**Why this entry exists.** §20.7 is a dangling forward reference: the closure
document appends §20.7.3–§20.7.5 to a parent body that the decision record never
defines. Everything those subsections rely on — that `S` is a conditioning
declaration, that admissibility precedes closure, that closure feasibility is not
an outcome claim — is currently either implicit or scattered across D6, D8 and the
Phase 2 implementation prompt. This entry writes that parent body down and stops
there.

**What is genuinely new.** Three things, each marked **[PV1]** where it is an
implementation choice rather than a statement of existing intent:

1. **Immutability of `S` (C1–C4).** Previously unstated. Without it an
   implementation may normalize or complete `S` and still satisfy every existing
   clause, which would make `upstream_state` an unreliable audit record and would
   silently break the conditioning semantics the whole phase rests on.
2. **Named layers L1–L4 and the non-implication chain (C6–C7).** M10 records that
   "L2 admissibility" is used but undefined. The existing non-implication rules
   (N0, N3, N17) constrain how a `VALID` verdict is *read*; they do not state the
   chain L1 ↛ L2 ↛ L3 ↛ L4. Naming the layers makes the phase boundary checkable
   rather than conventional.
3. **C14, a semantic rule in place of a lexical one.** A substring ban over the
   source tree would be brittle, would fire on legitimate prose in docstrings and
   comments, and would give false assurance. The obligation is placed on the
   author and on review, with only the machine-checkable part — the diagnostic
   key allow-list in T90 — automated.

**What is deliberately only cross-referenced.** Pair selection (§20.5), empty pair
sets (§20.7.4), unengaged intervening modules (§20.7.5), down-closure (§20.6) and
the field patterns (§10.1, §3.6, §10.7, §10.8). C10's worked examples are the one
place this entry repeats existing content, and they are marked as examples rather
than as a rule so that §20.5 remains the single definition.

**What it does not settle.** M1 and M5 are BLOCKING and remain open; C16 is
written so that it holds under either resolution of M1 and does not require M5.
The T85–T90 identifier block needs confirmation against the full T-list.
