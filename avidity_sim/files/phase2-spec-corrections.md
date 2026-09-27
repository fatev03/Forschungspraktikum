# Phase 2 spec corrections

Sources compared: code in this folder (authoritative for current contracts),
`GOTNE_v031_phase2_semantic_closure.md` ("closure doc"), `pasted_text_1790107971.txt`
("D-record"). BLOCKING = must be decided before Phase 2 code. Nothing below is
implemented.

## 1. Recorded correction: exactness is not provenance

- Exactness values are exactly the members of `status.Exactness`:
  `EXACT`, `APPROXIMATE`, `BOUND`, `UNDEFINED`.
- `ANALYTIC_APPROXIMATION` is a `status.Provenance` member (§6.3). It is provenance,
  not exactness, and must never appear as an exactness value.
- A serialized StateCertificate must carry exactness and provenance as separate fields:
  - exactness under one key holding only an `Exactness` value. Recommended key:
    `exact_or_approximate`, the name `EvaluationResult.as_dict()` already uses;
  - provenance in the `ProvenanceRecord.as_dict()` shape:
    `worst_label`, `contributing_labels`, `method_id`, `method_version`,
    `declared_assumptions`.
- Current code does not cross-check the pair. Phase 1c pairs `EXACT` with
  `EXACT_STRUCTURAL_VETO` and `UNDEFINED` with `NOT_COMPUTED`. `ProvenanceRecord` does not
  type-check `worst_label` or require it to appear in `contributing_labels`.

## 2. StateCertificate against current result/status contracts

| Topic | Current code | Spec texts | Status |
|---|---|---|---|
| Result type | `EvaluationResult`, `object_kind` a plain `str`, only `"CONFIG"` produced | D-record: `StateResult` = `EvaluationResult` with `object_kind="STATE"` | consistent; no new result class |
| Certificate shape | none | no serialized shape given in either text | OPEN: field list |
| Issuing statuses | n/a | D-record: `VALID` or `APPROXIMATION_REQUIRED`; closure doc: none on `DEGENERATE` | OPEN: Phase 2 has no source of `APPROXIMATION_REQUIRED` (spacer guard is Phase 4); allow or exclude it |
| Link to its STATE result | `result_id: Optional[str] = None`; `make_config_result` never sets it | D-record example `"st-0007"` (looks like a counter) | BLOCKING: deterministic id rule; a counter conflicts with the no-global-state and seed-stability rules |
| Exactness of successful STATE | §10.8 guard ("no numeric payload cannot claim EXACT") applies only when `object_kind == "CONFIG"` | closure doc N5: must be `UNDEFINED` | OPEN: extend the guard to STATE in `status.py`, or enforce only in the builder |
| Provenance of successful STATE | n/a | not specified | OPEN (`NOT_COMPUTED` would match Phase 1c) |
| Chain-closure veto STATE | `UNREACHABLE` is in `VETO_SET`; pattern gives zeros, density null, `zeroed=True` | D-record: `EXACT`, `EXACT_GEOMETRIC_VETO` | consistent |
| `method_version` | `METHOD_VERSION = "0.3.1"` | D-record example `"1.0.0"` with `method_id "chain_closure"` | OPEN: which value Phase 2 results carry |

## 3. Other concrete schema mismatches

M1 (BLOCKING). `vetoing_state_result_id` location. Closure doc N7 and T79 #10: key inside
`upstream_state`. D-record D6: `quantities` of an INFO diagnostic with code
`STATE_VETO_PROPAGATED` (prose also says `diagnostics.vetoing_state_result_id`). One carrier
must be chosen; MNH26 audits depend on it.

M2. `upstream_state` is stored and serialized as given. Unlike `values`, `units`,
`value_intervals` and `quantities`, it is not copied, not made read-only, not key-checked
and not checked for JSON safety. D-record puts `hash` and `assignments` in it; closure doc
adds `vetoing_state_result_id`. No schema for it exists.

M3. `closure_pairs` representation. T83 asserts `closure_pairs == [("D1", "D3")]` (tuples);
after `json.dumps` the value becomes `[["D1","D3"]]`. `DiagnosticRecord.quantities` is only
shallow read-only, so a list value stays mutable. Fix one in-memory and one serialized form.

M4. Skipped sweep. T83 #15 allows `closure_pairs` to be "absent or CHECK_SKIPPED"; N4
forbids encoding meaning by absence. Phase 1c convention is an INFO `CHECK_SKIPPED` record.
OPEN: pick one.

M5 (BLOCKING). `ENGAGEMENT_ORDER_VIOLATION` has no specified status (veto, unknown or
`INFEASIBLE`) and no provenance label. T83 #16 only asks for consistency with whatever
status is chosen.

M6. Reason set. D-record: four Phase 2 reasons including `SELF_AVOIDANCE_IGNORED`, and a
validation order ending in `SELF_AVOIDANCE_IGNORED`/`SHELL_BOUND` escalations. Closure doc:
exactly three reasons, `SHELL_BOUND` forbidden. `SELF_AVOIDANCE_IGNORED` also equals the value
of `UnresolvedUpstreamPolicy.SELF_AVOIDANCE_IGNORED`. Assumed: closure doc governs; confirm.

M7. Mandatory diagnostics. D-record requires `shielding_ancestor`, `upstream_resolution`,
`unresolved_upstream_ids`, `contour_budget_breakdown`. `upstream_resolution` is undefined.
Closure doc T83 #11 says the only intervening-module-related record is the three N14 keys,
while the breakdown's `elements` carry `source_id`s on that module's span. OPEN: whether
breakdown elements count as "related records".

M8. Index bases. Module `cassette_index` is 1-based (validator uses `enumerate(..., start=1)`;
fixtures use 1..3). Tether `cassette_index` is 0-based (schema comment "0 .. N-1").
`chain_closure_feasible(i, j, ...)` does not say whether `i`, `j` are module ids or indices,
nor which base.

M9. Spacer span. The §18.2 element table uses rigid spacer spans `λ_i` and ids like
`"D1.span"`, but `ModuleSpec` has no spacer field. The derivation from `entry_offset` /
`exit_offset` / `capture_offset_vec` is not in the files read. OPEN; element id naming is
also unspecified.

M10. Undefined types in signatures: `Tri` (members unknown), `BudgetBreakdown`, `Vec3`,
`ROOT`, the state object itself (D-record example shows `{label, target_id}` per module),
"L2 admissibility" (not defined in the files read), and `state_hash` (needed by `cache_key`,
no function exists).

M11. Redundant `policy` argument. `chain_closure_feasible`, `evaluate_state` and
`evaluate_node` take `policy` although `cfg.policy` exists. Behaviour when they differ is
unspecified.

M12. Phase 1c gate reuse. For a non-cassette `TopologyMode`, Phase 1c returns
`NOT_EVALUATED` / `CASSETTE_VALIDATION_NOT_APPLICABLE`. What `evaluate_state` returns when
the mode is not cassette or `validate_cassette_config` is not `VALID` is unspecified.

M13. Serialized examples in the D-record are partial. The STATE example omits `units` and
`numerical_tolerance_used`; the NODE example omits `exact_or_approximate`, `provenance`,
`value_intervals`, `units`, `upstream_state`, `result_id`, `supersedes`.
`EvaluationResult.as_dict()` always emits all 16 keys and is the governing shape.

M14. JSON safety of geometric quantities. Phase 1c tests serialize with `allow_nan=False`.
Phase 2 diagnostics carry floats (`D_min_nm`, `required_span_nm`); handling of non-finite
values is unspecified.

## 4. Open questions (summary)

1. Carrier of `vetoing_state_result_id` (M1).
2. Deterministic `result_id` rule for STATE results (section 2).
3. Status and provenance of `ENGAGEMENT_ORDER_VIOLATION` (M5).
4. StateCertificate field list and whether `APPROXIMATION_REQUIRED` may issue one.
5. Whether the §10.8 exactness guard extends to STATE.
6. `Tri` members, `i`/`j` type and index base, spacer derivation, state schema.
7. `method_version` value for Phase 2 results.
8. Approval to amend `test_no_phase2_symbols_leak`, and the module renames in the name mapping.
