# Phase 2 plan (seam 1: planning only)

Base: Phase 1c v0.3.1 (`__version__ = "0.3.1-phase1c"`, `METHOD_VERSION = "0.3.1"`).
Inputs read: `status.py`, `cassette_schema.py`, `cassette_topology.py`, `identity.py`,
`mode_applicability.py`, `__init__.py`, the three test modules,
`GOTNE_v031_phase2_semantic_closure.md` (called "closure doc" below) and
`pasted_text_1790107971.txt` (decision record D1..D10 and phase plan, called "D-record").
No code was changed and no tests were run.

## 0. Preconditions

1. The snapshot folder is flat, but every test imports `gotne.*` and reads
   `<root>/gotne/*.py` and `<root>/tests/`. Measure the baseline
   (`python -m pytest`, collected/passed) in the real repo layout before any patch.
   The closure doc reports 141 collected / 139 passed for this snapshot; not re-measured here.
2. Resolve the items marked BLOCKING in `phase2-spec-corrections.md`.
3. Get approval for the one existing-test change listed in section 2.

## 1. Implementation order

Each step is one self-contained patch, tests run after each.

1. `status.py` (minimal diff): add object-kind constants and a generic result
   builder for `STATE` / `NODE` results. `make_config_result` stays byte-identical in
   behaviour. No new `EvaluationResult` fields.
2. `cassette_state.py`: state schema, Phase 2 reason constants, `StateCertificate`,
   L2 admissibility, down-closure check under `R_union = R_policy ∪ R_requires`.
3. `cassette_budget.py`: `BudgetElement`, `BudgetBreakdown`, `cassette_contour_budget`
   (element set over the full physical path; D_min / D_max per D1).
4. `cassette_frames.py`: `cassette_effective_anchor`, shielding ancestor lookup.
5. `cassette_closure.py` (prompt name `closure.py`): consecutive-engaged-pair selection,
   `chain_closure_feasible`.
6. `evaluate_state` (in `cassette_state.py`, see import-cycle note in the name mapping):
   Phase 1c gate, admissibility, order check, closure sweep, certificate issue.
7. `cassette_node.py` (prompt name `evaluate_node.py`): `evaluate_node`, veto propagation.
8. `__init__.py` exports and version bump; amend the Phase 1c leak test (section 2).

## 2. Files

| Action | File |
|---|---|
| add | `cassette_state.py`, `cassette_budget.py`, `cassette_frames.py`, `cassette_closure.py`, `cassette_node.py` |
| add (later seam) | `test_phase2_state.py`, `test_phase2_import_boundary.py` (in the `tests/` dir) |
| change | `status.py` (builder, object-kind constants; STATE exactness guard only if decided) |
| change | `__init__.py` (exports, `__version__`) |
| change, needs approval | `test_cassette_topology.py::PurityTests.test_no_phase2_symbols_leak` asserts the package does NOT export `evaluate_node`, `evaluate_state`, `cassette_effective_anchor`, `cassette_contour_budget`. Exporting them breaks it. |
| unchanged | `cassette_schema.py`, `cassette_topology.py`, `identity.py`, `mode_applicability.py` |
| open | `identity.py` may need a `state_hash` function for `cache_key`; not specified. |

## 3. Public API to introduce

Positional order is fixed by the contract; parameter spellings differ between the two
spec texts (see name mapping). Proposed:

```python
cassette_effective_anchor(module_id, state, cfg) -> EffectiveAnchor   # (point, ancestor_id | ROOT, index)
cassette_contour_budget(module_id, state, cfg) -> BudgetBreakdown
chain_closure_feasible(i, j, state, cfg, policy) -> Tri
evaluate_state(state, cfg, policy) -> EvaluationResult                # object_kind "STATE"
evaluate_node(node_id, state_certificate, cfg, policy) -> EvaluationResult  # object_kind "NODE"
```

New types (names provisional): `EngagementState`, `StateCertificate`, `BudgetElement`,
`BudgetBreakdown`, `EffectiveAnchor`, `Tri`, sentinel `ROOT`.
New reason constants (exactly three): `CHAIN_CLOSURE_VIOLATED`,
`ENGAGED_POSE_UNDERDETERMINED`, `ENGAGEMENT_ORDER_VIOLATION`.
New diagnostic codes (from D-record/closure doc): `STATE_VETO_PROPAGATED`, plus one INFO
code for the closure-sweep record (name not specified).

## 4. Invariants

- Every result is built through `apply_status_field_pattern`; no local zeroing/nulling.
- `EvaluationResult` field set unchanged; `vetoing_state_result_id` travels inside an
  existing mapping (which one is BLOCKING, see corrections).
- Phase 1c `validate_cassette_config` runs first; order admissibility runs before any closure
  or budget call.
- Closure pairs are drawn only from engaged modules, in increasing index.
- Empty pair set: sweep counts as run, `closure_pairs: []` and
  `closure_predicate_invocations: 0` present, predicate never called.
- Budget element identity set does not depend on engagement labels.
- `unresolved_upstream_ids` never feeds the budget; under `EXCLUDED_SHELL_BOUND` only the
  three permitted keys are reported.
- Successful STATE: five canonical fields `None`, `value_intervals == {}`, `UNDEFINED`,
  both flags false.
- Chain-closure veto STATE: `UNREACHABLE` / `CHAIN_CLOSURE_VIOLATED`, `EXACT`, provenance
  `EXACT_GEOMETRIC_VETO`.
- Exactness and provenance are separate fields and never substitute for each other.
- Phase 2 never emits `Exactness.BOUND`, `Provenance.BOUND_ONLY`, a `SHELL_BOUND` reason,
  or any `value_intervals` entry.
- A `StateCertificate` exists only for an admissible, non-vetoed STATE result.
- Every NODE result under a vetoed state carries `vetoing_state_result_id` (MNH26).
- `as_dict()` output is JSON-serializable with `sort_keys=True, allow_nan=False` and stable
  across `PYTHONHASHSEED`; no global counters, no import-time side effects.
- No import of `composite_density`, `so3_grids`, `pose_marginalization`, `shell_bounds`,
  `intervals`, directly or transitively.

## 5. Test categories

1. Regression gate against the measured baseline.
2. Entry contract: schema `TypeError` vs structured result for declared input.
3. State admissibility and down-closure per order policy.
4. Pair selection (including T83 policy A/B).
5. Budget arithmetic (T57, T58) and path-membership invariance (T83).
6. Closure veto and propagation (T50, T66, MNH26).
7. Empty pair set (T79) with call-counting spy.
8. Field pattern, exactness, provenance per status.
9. Serialization: JSON round trip, seed stability, key presence.
10. Import boundary: static AST scan and dynamic `sys.modules` / `sys.meta_path` trap.

## 6. Non-goals for this phase

No probability, density, capture integral, local concentration, survival correction,
pose marginalization, interval, shell-bound quantity, kinetic quantity or at-risk weight.
No `evaluate_path` / `evaluate_network`. No caching implementation. No `GENERAL_DAG`
support. No change to Phase 1c validators, reasons or codes. No new canonical value field,
no new `EvaluationResult` field, no new model parameter.
