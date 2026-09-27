# Phase 2 Pre-Implementation Resolution

Revision 3 (final). Status: decision record, pre-code, all decisions approved. No source, test or export changes are made by this document.
Base: Phase 1c v0.3.1 (`__init__.__version__ = "0.3.1-phase1c"`, `status.METHOD_VERSION = "0.3.1"`).

Revision 3 records: approval of AP-1..AP-12, AP-14..AP-21 and AP-23..AP-27; AP-13 approved as
amended (derived rigid span); AP-22 approved with clarification (placement convention only); owner
resolutions of OQ-1..OQ-9. No decision remains open.

Amendment A1 (owner ruling, after seam 3): the T83 #5 budget-path invariant is corrected in K.
AP-18 and N10 are unchanged; the shielding ancestor is state-dependent.

Amendment A2 (owner rulings, before the final seam):
1. OQ-4: an UNENGAGED assignment is equivalent to omission inside or outside the cassette. Only an
   ENGAGED assignment naming a module outside the cassette is `STATE_INPUT_INVALID`. This keeps H
   (equal `result_id` implies equal `as_dict()`) consistent with AP-27.
2. `evaluate_state` raises `ValueError` and issues no result for a cfg without canonical identity
   (`config_identity_hash` fails), since a STATE result must carry a `result_id` (C).
3. T83 #11 excludes only Phase-5-style downstream numeric records for the intervening module
   (at-risk weight, occupancy, survival, obstacle); span-accounting and path-membership records
   (budget elements, `DERIVED_RIGID_SPAN` element ids) are permitted.
4. Migration Step 2 (`status.py`, `identity.py`, the shared `R_union` helper) lands with the final seam.
Implementation defaults accepted with A2: `unresolved_upstream_ids` of a node are the modules strictly
between its shielding ancestor and the node, and of a STATE result the union over its ENGAGED modules;
the STRICT_PROXIMAL_TO_DISTAL `R_policy` orders every proximal module before every distal one;
STATE `declared_assumptions` are the config's policy assumptions (without the Phase 1c
geometry-presence line) plus `pose_placement` and `rigid_span_basis` when used.

Sources, with the short names used below:

| Short name | File |
|---|---|
| code | `status.py`, `cassette_schema.py`, `cassette_topology.py`, `identity.py`, `mode_applicability.py`, `__init__.py` (source of truth for existing behaviour) |
| tests | `test_cassette_topology.py`, `test_phase1c_closure.py`, `test_phase1c_remediation.py` |
| plan / mapping / corrections | `phase2-plan.md`, `phase2-name-mapping.md`, `phase2-spec-corrections.md` |
| closure doc | `GOTNE_v031_phase2_semantic_closure.md` (§20.7.3 N0, §20.7.4 N1-N7, §20.7.5 N8-N17, §3 T79/T83, §4) |
| D-record | `pasted_text_1790107971.txt` (D1-D10, Part 2 addendum, Part 3 phase plan) |
| owner rulings | the revision-2 approvals and OQ resolutions from the specification owner |

Precedence used to resolve conflicts: owner rulings > code > closure doc > D-record, except where the
closure doc itself states it leaves a D-record decision unchanged (closure doc header: "D6 / D8 /
§18.2 / §20.5 / §20.6 / §10.7 ... değiştirilmemiştir").

Phase 2 boundary (binding for every item below): Phase 2 is a deterministic state-admissibility and
geometric-veto layer. A closure-feasible state is a state the Phase 2 span model does not veto. It is
not a prediction of any kind (closure doc N0, N3, N17).

---

## Decisions Requiring Approval

| ID | Decision | Status | Affected code/tests |
|---|---|---|---|
| AP-1 | Replace `PurityTests.test_no_phase2_symbols_leak` with an exact allowlist test; add `__all__` | APPROVED | `__init__.py`, `test_cassette_topology.py` |
| AP-2 | Export allowlist content | APPROVED; list extended by AP-20 and AP-25 (see Canonical API Surface) | `__init__.py` |
| AP-3 | Modules `cassette_state/frames/budget/closure/node.py`; `evaluate_state` in `cassette_closure.py` | APPROVED | new modules |
| AP-4 | `status.make_result` builder; `make_config_result` as byte-identical wrapper; `OBJECT_KINDS` | APPROVED | `status.py` |
| AP-5 | Payload-free results are `UNDEFINED` for every object kind; veto-label cross-checks | APPROVED | `status.py`, `ResultIntegrity` |
| AP-6 | Id-based `chain_closure_feasible`; names `module_id`, `state_certificate` | APPROVED; signature extended by AP-20 | spec text, spies |
| AP-7 | Public `issue_state_certificate`, `propagate_state_veto` | APPROVED; `issue_state_certificate` extended by AP-20 | `cassette_state.py`, `cassette_node.py` |
| AP-8 | `vetoing_state_result_id` only in `STATE_VETO_PROPAGATED` | APPROVED | closure doc N7, T79 #10 |
| AP-9 | Deterministic `result_id`; `identity.state_identity_hash`, `identity.result_identity` | APPROVED; components extended by AP-20, state hash normalized by AP-27 | `identity.py` |
| AP-10 | State-time `ENGAGEMENT_ORDER_VIOLATION` = `INFEASIBLE`, `EXACT`, `EXACT_STRUCTURAL_VETO`, propagated | APPROVED | `cassette_closure.py`, T83 B |
| AP-11 | Deep-frozen `upstream_state`; key `state_hash` | APPROVED; snapshot gains `context_hash` (AP-20) | `status.py` |
| AP-12 | `closure_pairs` canonical forms; T83 #1 and #15 rewrites | APPROVED | T83 |
| AP-13 | Rigid spacer span derived from `entry_offset`/`exit_offset` | APPROVED AS AMENDED: reported as `derived_rigid_span_nm`, recorded in `declared_assumptions`, never presented as an established body extent, override path through a future context attachment (K) | `cassette_budget.py`, T57/T58/T77 |
| AP-14 | `SPAN_INTERVAL_INVALID` admitted | APPROVED | `StateReason` |
| AP-15 | Non-failure STATE reason `STATE_NOT_VETOED` | APPROVED | `StateReason`, T79 #12 |
| AP-16 | `evaluate_state` composes the Phase 1c config result with the §17.8 rule | APPROVED | `cassette_closure.py` |
| AP-17 | `policy` MUST equal `cfg.policy`, else `ValueError` | APPROVED | all functions taking `policy` |
| AP-18 | Shielding ancestor = nearest ENGAGED proximal module, else ROOT | APPROVED | `cassette_frames.py` |
| AP-19 | `__version__ = "0.3.1-phase2"`; `METHOD_VERSION` stays `"0.3.1"` | APPROVED | `__init__.py` |
| AP-20 | Required last parameter `context: EvaluationContext` on `cassette_effective_anchor`, `chain_closure_feasible`, `evaluate_state`, `issue_state_certificate`; `evaluate_node` reads the context from the certificate; `context_hash` enters `result_id` and `upstream_state` | APPROVED | four signatures, `identity.py`, `status.py` snapshot |
| AP-21 | `NumericalTolerances` defaults `eps_len_nm = 1e-9`, `eps_rotation = 1e-9` | APPROVED (confirmed) | `cassette_state.py` |
| AP-22 | Engaged-pose placement convention: module frame rotated by the target orientation and translated so the capture reference point (`capture_offset_vec`) lies on the target site; under `ORIENTATION_MARGINALIZED` pose-dependent predicates are `UNDETERMINED` even if an orientation is supplied | APPROVED WITH CLARIFICATION: a placement convention from target-site frame data to module-frame coordinates only; it MUST NOT be read as a unique physical bound pose; a supplied orientation is context data, not a conditioned bound pose (E) | `cassette_frames.py`, `cassette_closure.py`, `cassette_node.py` |
| AP-23 | `STATE_INPUT_INVALID` and `GEOMETRY_INPUT_INVALID` are `INFEASIBLE` structural vetoes | APPROVED | `StateReason`, `evaluate_state`, `evaluate_node` |
| AP-24 | `evaluate_node` accepts only cassette module ids ENGAGED in the certificate state; `CONTOUR_BUDGET_VIOLATED` (`UNREACHABLE`, `EXACT_GEOMETRIC_VETO`); `NODE_NOT_VETOED` | APPROVED | `cassette_node.py` |
| AP-25 | `FIXED_RIGID`: `NOT_EVALUATED` / `JUNCTION_GEOMETRY_UNSUPPORTED` wherever junction-dependent geometry is needed; direct calls raise `UnsupportedGeometryError` | APPROVED | `cassette_budget.py`, `cassette_closure.py`, `cassette_node.py` |
| AP-26 | Closure gate uses `closure_span_budget` (no capture offset); node gate uses `cassette_contour_budget` (capture offset once); T83 #14 spies both | APPROVED | `cassette_budget.py`, T83 |
| AP-27 | `state_identity_hash` covers only ENGAGED `(module_id, target_id)` pairs; explicit UNENGAGED and omission hash identically | APPROVED | `identity.py` |

---

## Resolved Contract

### A. Public exports and the blocking test (AP-1, AP-2 approved)

**Chosen rule.** Replace the negative test with an exact allowlist; the package gains `__all__`.
Conflict: `test_cassette_topology.py::PurityTests.test_no_phase2_symbols_leak` asserts
`not hasattr(gotne, n)` for `evaluate_node`, `evaluate_state`, `cassette_effective_anchor`,
`cassette_contour_budget`, `compute_conditional_density`; `__init__.py` has no `__all__` (39 names).

**Normative wording.**
- The package MUST define `__all__`; public non-module package attributes MUST equal `set(__all__)`, which MUST equal the allowlist in "Canonical API Surface".
- The package MUST NOT expose, as attribute or importable submodule: `compute_conditional_density`, `composite_second_moment`, `so3_grid`, `compute_pose_marginalized`, `at_risk_region`, `at_risk_capture_weight`, `compute_shell_bound`, `evaluate_path`, `evaluate_network`, `composite_density`, `so3_grids`, `pose_marginalization`, `shell_bounds`, `intervals`.
- The 39 Phase 1c exports MUST remain, as identical objects.

**Schema/API impact.** `__init__.py` only.
**Validation/runtime behavior.** None at runtime.
**Test impact.** L1-L3 replace the leak test; `test_phase1c_modules_import_no_numerics` unchanged.

### B. Module/function name collisions (AP-3 approved)

**Chosen rule.** Acyclic chain `cassette_state` → `cassette_frames` → `cassette_budget` →
`cassette_closure` → `cassette_node`; no module name equals a public name.
Conflicts: closure doc §4.1 `evaluate_node.py` vs function `evaluate_node`; `evaluate_state` in
`cassette_state.py` would cycle with frames/budget/closure.

**Normative wording.**
- No Phase 2 module name MAY equal a name in `__all__`. A module MUST NOT import a later module in the chain.
- Cross-module calls to spy targets MUST use module attribute access; same-module calls use the module global (as `cassette_topology.validate_cassette_config` does via `globals()`).
- Canonical spy paths: `gotne.cassette_closure.chain_closure_feasible`, `gotne.cassette_budget.cassette_contour_budget`, `gotne.cassette_budget.closure_span_budget`, `gotne.cassette_frames.cassette_effective_anchor`.

**Schema/API impact.** Five modules; no `closure.py`, no `evaluate_node.py`, no sixth module.
**Validation/runtime behavior.** None.
**Test impact.** L4, L5.

### C. StateResult representation (AP-4 approved)

**Chosen rule.** STATE results are `EvaluationResult` with `object_kind == "STATE"`; NODE results use
`"NODE"`. `status.make_result` is the general builder; `make_config_result` wraps it.

**Normative wording.**
- `status.OBJECT_KINDS = ("CONFIG", "STATE", "NODE")`; `__post_init__` MUST reject other kinds.
- Values come only from `apply_status_field_pattern`; invariants live only in `EvaluationResult.__post_init__`. The builder MUST NOT zero or null anything itself.
- Direct construction and `dataclasses.replace` REMAIN legal.
- `make_config_result` output (`as_dict()`) MUST be unchanged for every input.
- CONFIG MUST have `upstream_state is None`, `result_id is None`, `numerical_tolerance_used is None`. STATE and NODE MUST have non-None `upstream_state`, `result_id` and `numerical_tolerance_used`.

```text
make_result(
    object_kind: str, object_id: str, status: Status, status_reason: str,
    diagnostics: Sequence[DiagnosticRecord], *,
    method_id: str,
    veto_provenance: Optional[Provenance] = None,
    declared_assumptions: Sequence[str] = (),
    method_version: str = METHOD_VERSION,
    upstream_state: Optional[Mapping[str, Any]] = None,
    numerical_tolerance_used: Optional[Mapping[str, Any]] = None,
    result_id: Optional[str] = None,
) -> EvaluationResult
```

| Status class | values | exactness | provenance |
|---|---|---|---|
| `VETO_SET` | pattern (zeros, density null) | `EXACT` | `veto_provenance`, required: `EXACT_STRUCTURAL_VETO` or `EXACT_GEOMETRIC_VETO` |
| `UNKNOWN_SET`, `VALID` | all null | `UNDEFINED` | `NOT_COMPUTED`; `veto_provenance` MUST be None |
| `APPROXIMATION_REQUIRED` | builder raises `ValueError` | | |

No `values` or `value_intervals` argument exists; `value_intervals` is always `{}`.

**Schema/API impact.** `status.py`: `OBJECT_KINDS`, `make_result`, wrapper, `__post_init__` checks.
**Validation/runtime behavior.** Construction-time `ValueError`/`TypeError`.
**Test impact.** L7, `test_object_kind_closed_set`, `test_builder_rejects_values_and_approximation_required`.

### D. Exactness and state payloads (AP-5 approved)

**Chosen rule.** A result has a payload iff a canonical value field is non-null or a `value_intervals`
entry is populated. Payload-free results are `UNDEFINED`. Veto labels and veto statuses imply each
other. Conflict: `EvaluationResult.__post_init__` applies the §10.8 guard only to `object_kind == "CONFIG"`.

**Normative wording.**
- A result without payload MUST be `UNDEFINED`, for every object kind.
- A `VETO_SET` result MAY be `EXACT`; if so, `worst_label` MUST be `EXACT_STRUCTURAL_VETO` or `EXACT_GEOMETRIC_VETO`. These labels MUST NOT appear outside `VETO_SET`.
- Structural vetoes (Phase 1c; `ENGAGEMENT_ORDER_VIOLATION`, `STATE_INPUT_INVALID`, `GEOMETRY_INPUT_INVALID`, `SPAN_INTERVAL_INVALID`) use `EXACT_STRUCTURAL_VETO`. Geometric vetoes (`CHAIN_CLOSURE_VIOLATED`, `CONTOUR_BUDGET_VIOLATED`) use `EXACT_GEOMETRIC_VETO`.
- Non-veto Phase 2 results MUST NOT encode feasibility, spans or distances in canonical value fields.
- `Exactness.BOUND`, `Exactness.APPROXIMATE`, `Provenance.BOUND_ONLY`, `Provenance.ANALYTIC_APPROXIMATION` MUST NOT appear in Phase 2 results.

**Schema/API impact.** `__post_init__` only; all Phase 1c producers already comply.
**Validation/runtime behavior.** `ValueError` at construction.
**Test impact.** L6; existing `ResultIntegrity` cases unchanged.

### E. Canonical names, signatures and types (AP-6, AP-7, AP-17, AP-18, AP-20, AP-27 approved; AP-22 approved with clarification)

**Chosen rule.** One spelling set: `module_id`, `node_id`, `state`, `cfg`, `policy`, `context`,
`state_certificate`, `state_result`, `upstream_module_id`, `downstream_module_id`. Public functions take
identifiers, never indices. Module cassette index 1-based, segment index 0-based (Phase 1c P1:
`enumerate(ordered, start=1)`; `TetherSpec.cassette_index` "0 .. N-1").

**Normative wording.**
- Public functions MUST identify modules only by `str` identifier. Indices MAY appear only in diagnostics (`module_cassette_index`, `segment_cassette_index`) and internal ordering; the bare key `cassette_index` MUST NOT be used in Phase 2 diagnostics.
- `chain_closure_feasible` MUST be called only with a pair produced by closure-pair selection for `state`; any other pair MUST raise `ValueError` and MUST NOT be repaired or synthesized (closure doc N2).
- `policy` MUST equal `cfg.policy` (else `ValueError`). Wrong argument types raise `TypeError` (§9.2).
- `context` MUST be an `EvaluationContext`; it has no default, so geometry cannot run without it.
- Shielding ancestor of `D_j`: ENGAGED module with the largest module cassette index `< j`, else ROOT.
- Engaged-pose placement convention (AP-22): for ENGAGED module `D` at target `T` with orientation `R` and site `p`, a module-frame offset `v` is placed at `R·v + t` with `t = p − R·capture_offset_vec_D`. This is only a convention for mapping target-site frame data into module-frame coordinates. It MUST NOT be interpreted, reported or documented as a unique physical bound pose, and diagnostics MUST NOT call the placed frame a "bound pose". `declared_assumptions` MUST include `pose_placement=CAPTURE_POINT_ON_TARGET_SITE` whenever the convention is applied.
- Under `POSE_REQUIRED`, `R` MUST be supplied (else `GEOMETRY_INPUT_INVALID`). Under `ORIENTATION_MARGINALIZED`, every pose-dependent predicate MUST return `Tri.UNDETERMINED` even when `TargetGeometry.orientation` is supplied: a supplied orientation is context data, not a conditioned bound pose, and Phase 2 does not marginalize (closure doc §5).
- Multiple ENGAGED modules MAY reference the same `target_id` (OQ-9). No uniqueness rule exists in v1.
- Effective anchor point: ROOT → root `AnchorSpec.position`; module ancestor → `R·exit_offset + t` of that ancestor.

| Name | Module | Definition |
|---|---|---|
| `Vec3` | `cassette_state` | alias `Tuple[float, float, float]` (moved here to keep the chain acyclic) |
| `Rotation3` | `cassette_state` | alias `Tuple[Vec3, Vec3, Vec3]`, row-major |
| `EngagementLabel` | `cassette_state` | `str` Enum: `ENGAGED`, `UNENGAGED` (OQ-1 ruling) |
| `ModuleAssignment` | `cassette_state` | frozen: `module_id: str`, `label: EngagementLabel`, `target_id: Optional[str]` |
| `EngagementState` | `cassette_state` | frozen: `assignments: Tuple[ModuleAssignment, ...]`, sorted by `module_id` |
| `TargetGeometry`, `TargetContext`, `NumericalTolerances`, `EvaluationContext` | `cassette_state` | see "Canonical API Surface" |
| `StateReason`, `StateCode` | `cassette_state` | see F |
| `UnsupportedGeometryError` | `cassette_state` | subclass of `ValueError` (AP-25) |
| `StateCertificate` | `cassette_state` | frozen: `state_result`, `state`, `context`, `config_identity_hash`, `context_hash` |
| `ROOT`, `EffectiveAnchor` | `cassette_frames` | singleton sentinel (never equal to a `str`); NamedTuple `(point: Vec3, ancestor: Union[str, Root], ancestor_module_cassette_index: int)`, ROOT index 0 |
| `SpanBasis`, `BudgetElementKind`, `BudgetElement`, `BudgetBreakdown` | `cassette_budget` | see K |
| `Tri` | `cassette_closure` | `str` Enum `TRUE`, `FALSE`, `UNDETERMINED`; `__bool__` MUST raise `TypeError` |
| `NodeReason` | `cassette_node` | see F |

`StateCertificate.__post_init__` MUST require: `state_result.object_kind == "STATE"`, status `VALID`,
non-None `result_id`, `upstream_state["state_hash"] == state_identity_hash(state)`,
`upstream_state["context_hash"] == context_identity_hash(context) == context_hash`. Serialized form:

```json
{ "state_result_id": "st-<64 hex>", "state_hash": "<64 hex>", "context_hash": "<64 hex>",
  "config_identity_hash": "<64 hex>", "topology_mode": "LINEAR_ORDERED_CASSETTE",
  "status": "VALID", "exact_or_approximate": "UNDEFINED",
  "provenance": { "worst_label": "NOT_COMPUTED", "contributing_labels": ["NOT_COMPUTED"],
                  "method_id": "evaluate_state", "method_version": "0.3.1",
                  "declared_assumptions": ["..."] },
  "numerical_tolerance_used": { "eps_len_nm": 1e-9, "eps_rotation": 1e-9 } }
```

**Schema/API impact.** See "Canonical API Surface".
**Validation/runtime behavior.** As stated.
**Test impact.** `test_signatures_exact`, `test_tri_not_truthy`, `test_closure_rejects_non_pair`,
`test_policy_mismatch_raises`, `test_certificate_integrity`, `test_context_required`.

### F. Reasons, codes and semantic separation (AP-14, AP-15, AP-23, AP-24, AP-25 approved)

**Chosen rule.** Config-time and state-time checks keep distinct reasons and codes; policy values are
never reasons. Conflicts: `Reason.ORDER = "ENGAGEMENT_ORDER_CONSTRAINTS_UNSATISFIABLE"` and
`Code.ENGAGEMENT_ORDER_CONFLICT` (config time) vs `ENGAGEMENT_ORDER_VIOLATION` (state time);
`UnresolvedUpstreamPolicy.SELF_AVOIDANCE_IGNORED` vs D-record Part 3 reason list.

**Normative wording.**
- P2 satisfiability MUST pass before state down-closure runs; neither reuses the other's reason or codes.
- `StateReason` MUST be exactly: `STATE_INPUT_INVALID`, `ENGAGEMENT_ORDER_VIOLATION`, `JUNCTION_GEOMETRY_UNSUPPORTED`, `GEOMETRY_INPUT_INVALID`, `SPAN_INTERVAL_INVALID`, `ENGAGED_POSE_UNDERDETERMINED`, `CHAIN_CLOSURE_VIOLATED`, `STATE_NOT_VETOED`.
- `NodeReason` MUST be exactly: `CONTOUR_BUDGET_VIOLATED`, `NODE_NOT_VETOED`. NODE results reuse `StateReason` values for the failures they share (`GEOMETRY_INPUT_INVALID`, `SPAN_INTERVAL_INVALID`, `ENGAGED_POSE_UNDERDETERMINED`, `JUNCTION_GEOMETRY_UNSUPPORTED`) and copy the vetoing state's reason when propagated.
- `SELF_AVOIDANCE_IGNORED` and `SHELL_BOUND` MUST NOT be reasons or codes in Phase 2; `SELF_AVOIDANCE_IGNORED` MAY appear only as the value of quantity `unresolved_upstream_policy`.
- `CHAIN_CLOSURE_VIOLATED` and `ENGAGEMENT_ORDER_VIOLATION` MUST NOT share status, provenance or code.
- Order diagnostic message MUST read "engaged set is not down-closed under R_union", quantities `module_id`, `missing_predecessors`, `engagement_order_policy`.
- `R_union` MUST be built with the edge semantics of `validate_cassette_order_constraints` (`REQUIRES(from_node, to_node)`: `from_node` precedes `to_node`, D-record T70), via one shared private helper extracted without semantic change.

Status table (every row via `make_result`):

| Reason | Status | Exactness / provenance | Certificate | Propagated |
|---|---|---|---|---|
| `STATE_INPUT_INVALID` | `INFEASIBLE` | `EXACT` / `EXACT_STRUCTURAL_VETO` | no | yes |
| `ENGAGEMENT_ORDER_VIOLATION` | `INFEASIBLE` | `EXACT` / `EXACT_STRUCTURAL_VETO` | no | yes |
| `GEOMETRY_INPUT_INVALID` | `INFEASIBLE` | `EXACT` / `EXACT_STRUCTURAL_VETO` | no | yes |
| `SPAN_INTERVAL_INVALID` | `INFEASIBLE` | `EXACT` / `EXACT_STRUCTURAL_VETO` | no | yes |
| `CHAIN_CLOSURE_VIOLATED` | `UNREACHABLE` | `EXACT` / `EXACT_GEOMETRIC_VETO` | no | yes |
| `CONTOUR_BUDGET_VIOLATED` (NODE) | `UNREACHABLE` | `EXACT` / `EXACT_GEOMETRIC_VETO` | n/a | n/a |
| `ENGAGED_POSE_UNDERDETERMINED` | `DEGENERATE` | `UNDEFINED` / `NOT_COMPUTED` | no | no |
| `JUNCTION_GEOMETRY_UNSUPPORTED` | `NOT_EVALUATED` | `UNDEFINED` / `NOT_COMPUTED` | no | no |
| `STATE_NOT_VETOED` / `NODE_NOT_VETOED` | `VALID` | `UNDEFINED` / `NOT_COMPUTED` | yes (STATE) | n/a |

`StateCode` (closed): ERROR codes equal to the seven failure values of `StateReason` plus `CONTOUR_BUDGET_VIOLATED`;
INFO codes `CLOSURE_SWEEP`, `UNRESOLVED_UPSTREAM`, `CONTOUR_BUDGET`, `SHIELDING_ANCESTOR`,
`DERIVED_RIGID_SPAN`, `STATE_VETO_PROPAGATED`. `Code.CHECK_SKIPPED` is reused.

**Schema/API impact.** `StateReason`, `StateCode`, `NodeReason`. Phase 1c `Reason`/`Code` unchanged.
**Validation/runtime behavior.** See I.
**Test impact.** `test_reasons_closed_sets`, `test_reason_strings_disjoint_from_phase1c` (no value equals a
`Reason` value or an `UnresolvedUpstreamPolicy` value), `test_no_shell_bound_or_self_avoidance_reason`.

### G. State propagation reference (AP-7, AP-8 approved)

**Chosen rule.** `upstream_state` is the frozen snapshot of the conditioning input;
`vetoing_state_result_id` lives only in one `STATE_VETO_PROPAGATED` diagnostic.

**Normative wording.**
- `upstream_state` MUST contain exactly `state_hash`, `context_hash`, `assignments`; never result metadata.
- A NODE result under a vetoed STATE MUST carry exactly one `STATE_VETO_PROPAGATED` with quantities `vetoing_state_result_id`, `vetoing_status`, `vetoing_status_reason` (MNH26), copy the state's status, reason, exactness and `worst_label`, and carry the same `upstream_state`.
- Propagation applies only to `VETO_SET` STATE results. `UNKNOWN_SET` STATE results produce no NODE result in Phase 2.
- `propagate_state_veto` accepts any module id of the cassette (else `ValueError`); `evaluate_node` keeps its certificate-only signature.

```json
{ "code": "STATE_VETO_PROPAGATED", "severity": "INFO",
  "message": "conditioning state was vetoed; node not evaluated",
  "quantities": { "vetoing_state_result_id": "st-<64 hex>", "vetoing_status": "UNREACHABLE",
                  "vetoing_status_reason": "CHAIN_CLOSURE_VIOLATED" },
  "remediation": null }
```

**Schema/API impact.** `cassette_node.propagate_state_veto`; no new `EvaluationResult` field.
**Validation/runtime behavior.** `ValueError` if `state_result` is not a `VETO_SET` STATE result or its
`result_id` differs from the recomputed value.
**Test impact.** T79 #10 rewritten (no propagation diagnostic, no key anywhere); T50;
`test_vetoing_id_not_in_upstream_state`; `test_single_propagation_diagnostic`.

### H. Deterministic result_id (AP-9, AP-20, AP-27 approved)

**Chosen rule.** `prefix-sha256` over domain-separated canonical identity inputs via `identity._digest`
(which prepends `CANONICAL_FORM_VERSION`). No counter, clock, randomness or truncation.

**Normative wording.**
- STATE: `result_identity("STATE", [config_identity_hash(cfg), state_identity_hash(state), context_identity_hash(context), METHOD_VERSION, method_id, cfg.policy.topology_mode])`, prefix `st`.
- NODE: same components plus `node_id` after the state hash, prefix `nd`.
- `state_identity_hash(state)` MUST hash only the ENGAGED `(module_id, target_id)` pairs in ascending `module_id` (AP-27); explicit UNENGAGED entries and omitted modules MUST hash identically.
- `context_identity_hash(context)` MUST hash targets and tolerances; `tolerance_identity_hash(tolerances)` is the value for `cache_key(..., tolerance_hash, ...)`. Neither MAY change `config_identity_hash`.
- Full 64-hex digest with prefix. CONFIG keeps `result_id = None`. STATE `object_id = "S:" + state_hash`.
- Equal `result_id` MUST imply equal `as_dict()`; a detected mismatch MUST raise `RuntimeError`.
- `supersedes` stays None.

**Schema/API impact.** `identity.py`: `state_identity_hash`, `context_identity_hash`,
`tolerance_identity_hash`, `result_identity`. `cache_key` unchanged (still no `shielding_ancestor`, MNH28).
**Validation/runtime behavior.** Pure hashing; order-, thread- and process-independent.
**Test impact.** L8, `test_unengaged_normalization`, `test_context_changes_result_id_not_config_hash`.

### I. Evaluation order and state-time order violation (AP-10, AP-16, AP-23, AP-25 approved)

**Chosen rule.** `evaluate_state` runs these stages in fixed order; a stage runs only if every earlier
stage passed, and each stage not run is recorded as `CHECK_SKIPPED` (Phase 1c convention):

1. Entry checks: types (`TypeError`), `policy == cfg.policy`, `context` present (`ValueError`/`TypeError`).
2. Phase 1c `validate_cassette_config`; non-VALID composed by §17.8 (`cassette_topology._compose` rule). Non-cassette mode yields `NOT_EVALUATED` / `CASSETTE_VALIDATION_NOT_APPLICABLE`.
3. State input (OQ-4) → `STATE_INPUT_INVALID`.
4. Down-closure under `R_union` → `ENGAGEMENT_ORDER_VIOLATION`.
5. Closure-pair selection (pure, no geometry).
6. Junction support: `FIXED_RIGID` with at least one pair → `JUNCTION_GEOMETRY_UNSUPPORTED` (OQ-7).
7. Geometry input (OQ-5) → `GEOMETRY_INPUT_INVALID`.
8. Span intervals of every pair's closure span → `SPAN_INTERVAL_INVALID`.
9. Closure sweep over every pair in increasing upstream index, complete diagnosis; `FALSE` → `CHAIN_CLOSURE_VIOLATED`, `UNDETERMINED` → `ENGAGED_POSE_UNDERDETERMINED`; mixed outcomes resolved by §3.3 `precedence` unchanged.
10. Result; `STATE_NOT_VETOED` if nothing fired.

**Normative wording.**
- Stages 3-4 MUST NOT call any geometry function. Stages 5-8 MUST NOT call `chain_closure_feasible`.
- After an order violation, no pair selection, closure, budget or anchor function MAY run; the result MUST carry `CHECK_SKIPPED` (`check="closure sweep"`, `because="state is not down-closed under R_union"`) and no `closure_pairs` quantity (closure doc N16).
- An inadmissible state MUST NOT be `VALID` or `APPROXIMATION_REQUIRED`.
- With zero pairs the sweep counts as run: `CLOSURE_SWEEP` with `closure_pairs: []`, `closure_predicate_invocations: 0` (closure doc N4); stage 6 does not fire.

**Schema/API impact.** None beyond F.
**Validation/runtime behavior.** As listed.
**Test impact.** T83 policy B #12-#16 (`INFEASIBLE`, all spies 0, `CHECK_SKIPPED`); L12; `test_stage_order`.

### J. Serialization and immutable state handling (AP-11, AP-12, AP-19, AP-20 approved)

**Chosen rule.** Every Phase 2 mapping is frozen at construction and thawed to plain JSON types by
`as_dict()`; tuples in memory, lists in JSON. Conflicts: `EvaluationResult` stores `upstream_state` as
given; `DiagnosticRecord.quantities` is shallow read-only; T83 #1 compares with a list of tuples;
D-record D6(3) uses `method_version "1.0.0"` while `METHOD_VERSION = "0.3.1"`.

**Normative wording.**
- `upstream_state` MUST be deep-copied and deep-frozen; leaves `str`, `int`, `bool`, `None`, finite `float`; else `TypeError`. Shape: `{"state_hash", "context_hash", "assignments": {module_id: {"label", "target_id"}}}` listing every declared assignment. Target coordinates MUST NOT be copied into it.
- `numerical_tolerance_used` on STATE/NODE MUST equal `context.tolerances` as `{"eps_len_nm": float, "eps_rotation": float}`, frozen, present even when a stage short-circuits.
- Phase 2 quantities MUST be built frozen and JSON-safe; `DiagnosticRecord` is unchanged.
- `closure_pairs`: tuple of `(upstream_module_id, downstream_module_id)` in memory, list of 2-element lists in JSON.
- `json.dumps(result.as_dict(), sort_keys=True, allow_nan=False)` MUST succeed for every Phase 2 result.
- `method_version` MUST equal `status.METHOD_VERSION` everywhere, including spec examples.

**Schema/API impact.** `status.py` `upstream_state` and `numerical_tolerance_used` freezing; D-record
D6(3) example corrected (`hash` → `state_hash`, adds `context_hash`, `"1.0.0"` → `"0.3.1"`).
**Validation/runtime behavior.** Construction-time `TypeError`.
**Test impact.** L9, L10, L11, `test_numerical_tolerance_used_reported`.

### K. Contour-budget spacer span provenance (AP-13 approved as amended; AP-26 approved)

**Chosen rule.** For Phase 2 v1 the rigid span of an intervening module `D_i` is *derived*:
`derived_rigid_span_nm = ‖exit_offset_i − entry_offset_i‖`. It is a provisional modelling quantity
computed from declared offsets. It is not an experimentally established body extent. Capture offset
`c_j = ‖capture_offset_vec_j − entry_offset_j‖`. Segments use `TetherSpec.L_min` / `L`.

Two element sets (OQ-3 ruling):

| Function | Measures | Elements |
|---|---|---|
| `closure_span_budget(upstream_module_id, downstream_module_id, state, cfg)` | exit reference of `D_i` to entry reference of `D_j` | segments `σ_i..σ_{j-1}`, spans `B_{i+1}..B_{j-1}`; no capture offset |
| `cassette_contour_budget(module_id, state, cfg)` | effective anchor of `D_j` to target site | segments `σ_k..σ_{j-1}`, spans `B_{k+1}..B_{j-1}`, capture offset of `D_j` exactly once |

**Normative wording.**
- The closure gate MUST NOT include any capture offset. Within any single gate the capture offset MUST appear at most once; Phase 4 MUST NOT re-add it to a quantity that already contains it.
- No element MAY be omitted on engagement grounds (closure doc N9, N10).
- Path membership (amendment A1). The shielding ancestor `k` of `D_j` is state-dependent (AP-18).
  Once `k` is chosen, the NODE element set MUST be the full physical path from `k` to `D_j`:
  every segment `σ_k..σ_{j-1}`, the span of every module strictly between `k` and `D_j`, and the
  capture offset of `D_j`, regardless of those modules' labels. NODE budgets of `D_j` MUST be equal
  across states that select the same `k`; they MAY differ across states that select different
  ancestors, and no test MAY require equality there. The CLOSURE element set of a pair `(D_i, D_j)`
  depends only on the pair.
- SPAN elements MUST carry `span_basis = "DERIVED_FROM_ENTRY_EXIT_OFFSETS"` and `derived_rigid_span_nm`, with `a_nm = b_nm = derived_rigid_span_nm`. Their diagnostic text MUST say "derived from declared entry/exit offsets (provisional)" and MUST NOT use the words "measured", "physical extent" or "body size".
- Whenever at least one derived span is used, `declared_assumptions` MUST include `rigid_span_basis=DERIVED_FROM_ENTRY_EXIT_OFFSETS` and an INFO `DERIVED_RIGID_SPAN` diagnostic MUST list the element ids.
- Override path: `SpanBasis` is an Enum with one v1 member. A future structural-envelope attachment MUST arrive as a new optional field of `EvaluationContext` (so it changes `context_hash` and `result_id`), MUST NOT be added to `CassetteConfig` or any `*Spec`, and MUST NOT change `config_identity_hash`. Adding it requires a new `SpanBasis` member and a spec change.
- `D_max = Σ b_e`; `D_min = max(0, max_e (a_e − Σ_{f≠e} b_f))`; `D_min > D_max` is MNH22 and MUST raise `RuntimeError`; `a_e > b_e` → `SPAN_INTERVAL_INVALID`.
- `element_id` = `source_id` + `.seg` / `.span` / `.capture`; `dominating_element_id` = argmax element id or null, ties to the first element in path order.
- The ancestor is serialized as a tagged object, never a bare string.

```json
{ "budget_kind": "NODE", "module_id": "D3", "includes_capture_offset": true,
  "shielding_ancestor": { "kind": "MODULE", "id": "D1", "module_cassette_index": 1 },
  "elements": [
    { "element_id": "s1.seg", "kind": "SEGMENT", "source_id": "s1", "source_fields": ["L_min", "L"],
      "segment_cassette_index": 1, "a_nm": 0.0, "b_nm": 1.0 },
    { "element_id": "D2.span", "kind": "SPAN", "source_id": "D2", "source_fields": ["entry_offset", "exit_offset"],
      "module_cassette_index": 2, "span_basis": "DERIVED_FROM_ENTRY_EXIT_OFFSETS",
      "derived_rigid_span_nm": 1.2, "a_nm": 1.2, "b_nm": 1.2 },
    { "element_id": "s2.seg", "kind": "SEGMENT", "source_id": "s2", "source_fields": ["L_min", "L"],
      "segment_cassette_index": 2, "a_nm": 0.0, "b_nm": 1.0 },
    { "element_id": "D3.capture", "kind": "CAPTURE_OFFSET", "source_id": "D3",
      "source_fields": ["entry_offset", "capture_offset_vec"], "module_cassette_index": 3, "a_nm": 0.6, "b_nm": 0.6 } ],
  "D_max_nm": 3.8, "D_min_nm": 0.0, "dominating_element_id": null, "folding_unobstructed": true }
```

A closure span has `"budget_kind": "CLOSURE"`, `"includes_capture_offset": false`,
`upstream_module_id`/`downstream_module_id` instead of `module_id`/`shielding_ancestor`. Numbers are
illustrative. `BudgetElementKind` members are `SEGMENT`, `SPAN`, `CAPTURE_OFFSET` (renamed from
`SPACER` so the kind name does not imply a declared body).

**Schema/API impact.** `cassette_budget`: `SpanBasis`, `BudgetElementKind`, `BudgetElement`,
`BudgetBreakdown`, `closure_span_budget` (module-level, not exported); no `cassette_schema` change.
**Validation/runtime behavior.** Missing/non-finite sources → `GEOMETRY_INPUT_INVALID` (OQ-5).
**Test impact.** T57 (`"D1.span"`, `D_min = 17.3`), T58, T77 (`[e for e in elements if e.kind == "SPAN"] == []`,
`shielding_ancestor["kind"] == "ROOT"`), T83 #5 (amendment A1: NODE budget element ids equal against a
control state that selects the same shielding ancestor, e.g. D2 explicitly UNENGAGED; no equality
across states that change the ancestor),
T83 #14 (both budget spies 0), `test_closure_span_excludes_capture_offset`,
`test_derived_span_assumption_recorded`, `test_element_ids_unique_with_hostile_identifiers`.

### L. Phase separation test plan

| # | Test | Asserts |
|---|---|---|
| L1 | `test_public_api_allowlist` | public non-module attributes == `set(__all__)` == allowlist |
| L2 | `test_forbidden_future_names_absent` | no Phase 4/5 name, `evaluate_path`, `evaluate_network` or forbidden submodule |
| L3 | `test_phase1c_exports_preserved` | 39 Phase 1c names present, identical objects |
| L4 | `test_module_names_do_not_shadow_functions` | no module basename in `__all__`; submodules import as modules |
| L5 | `test_spy_paths_intercept_calls` | patched `chain_closure_feasible`, `closure_span_budget`, `cassette_contour_budget`, `cassette_effective_anchor` observe calls |
| L6 | `test_payload_free_results_undefined` | CONFIG/STATE/NODE all-null with `EXACT`/`APPROXIMATE`/`BOUND` raise; veto label rules |
| L7 | `test_make_config_result_golden` | Phase 1c `as_dict` unchanged on every validator path |
| L8 | `test_result_id_deterministic_across_seeds` | stable across `PYTHONHASHSEED` and call order; changes with config, state, context, node |
| L9 | `test_upstream_state_immutable_and_detached` | caller mutation has no effect; writes rejected; `as_dict` returns copies |
| L10 | `test_closure_pairs_canonical_forms` | tuple in memory, list in JSON, empty `[]`, present when sweep ran |
| L11 | `test_method_version_consistency` | every Phase 2 result uses `METHOD_VERSION` |
| L12 | `test_order_violation_short_circuits_all_geometry` | STRICT, `S = {D1, D3}`: `INFEASIBLE` / `ENGAGEMENT_ORDER_VIOLATION`, all geometry spies 0 |
| L13 | `test_phase2_import_boundary_static` / `_dynamic` | AST scan with transitive `gotne.*` closure; `sys.modules` and `sys.meta_path` trap (closure doc §4.6) |
| L14 | `test_phase2_never_emits_payload` | non-veto fields null, `value_intervals == {}`, no `BOUND_ONLY`/`ANALYTIC_APPROXIMATION`/`BOUND`/`APPROXIMATE`, no `SHELL_BOUND` in JSON |
| L15 | `test_context_objects_immutable_and_validated` | `TargetGeometry`/`NumericalTolerances` reject non-finite, bad rotations, non-positive tolerances at construction |
| L16 | `test_missing_target_blocks_geometry` | ENGAGED `target_id` absent from context → `GEOMETRY_INPUT_INVALID`, geometry spies 0 |
| L17 | `test_fixed_rigid_not_evaluated` | `FIXED_RIGID` with a pair → `NOT_EVALUATED` / `JUNCTION_GEOMETRY_UNSUPPORTED`; direct calls raise `UnsupportedGeometryError`; never equal to the `FREE_SWIVEL` result |
| L18 | `test_state_input_invalid_contract` | each OQ-4 trigger → `STATE_INPUT_INVALID`, complete diagnosis, geometry spies 0 |
| L19 | `test_shared_target_id_permitted` | two ENGAGED modules with one `target_id`: no `STATE_INPUT_INVALID`, no `GEOMETRY_INPUT_INVALID`, no ERROR or WARN diagnostic about sharing |
| L20 | `test_orientation_ignored_under_marginalized` | `ORIENTATION_MARGINALIZED` with orientations supplied: pose-dependent pairs `UNDETERMINED` → `DEGENERATE` / `ENGAGED_POSE_UNDERDETERMINED`; no text "bound pose" in `as_dict` JSON |

Precondition: baseline measured in the real `<root>/gotne` + `<root>/tests` layout (plan §0).

---

## Canonical API Surface

Modules (package `gotne`):

| Module | Contents | May import |
|---|---|---|
| `cassette_state.py` | `Vec3`, `Rotation3`, `EngagementLabel`, `ModuleAssignment`, `EngagementState`, `TargetGeometry`, `TargetContext`, `NumericalTolerances`, `EvaluationContext`, `StateReason`, `StateCode`, `UnsupportedGeometryError`, `StateCertificate`, `issue_state_certificate`, private input/down-closure helpers | schema, status, identity, topology (shared `R_union` helper), `math` |
| `cassette_frames.py` | `ROOT`, `EffectiveAnchor`, `cassette_effective_anchor` | + `cassette_state` |
| `cassette_budget.py` | `SpanBasis`, `BudgetElementKind`, `BudgetElement`, `BudgetBreakdown`, `cassette_contour_budget`, `closure_span_budget` | + `cassette_frames` |
| `cassette_closure.py` | `Tri`, closure-pair selection, `chain_closure_feasible`, `evaluate_state` | + `cassette_budget` |
| `cassette_node.py` | `NodeReason`, `evaluate_node`, `propagate_state_veto` | + `cassette_closure` |

State and data types (frozen dataclasses unless noted, validated in `__post_init__`, canonicalizable
by `identity.canonical_form`):

```text
Vec3      = Tuple[float, float, float]                      # cassette_state, alias
Rotation3 = Tuple[Vec3, Vec3, Vec3]                         # cassette_state, alias, row-major

EngagementLabel(str, Enum): ENGAGED, UNENGAGED
ModuleAssignment(module_id: str, label: EngagementLabel, target_id: Optional[str] = None)
    ENGAGED requires non-empty plain str target_id; UNENGAGED requires None; else ValueError
EngagementState(assignments: Tuple[ModuleAssignment, ...] = ())
    sorted by module_id; duplicate module_id -> ValueError; omitted modules are UNENGAGED
    several ENGAGED assignments MAY share one target_id (OQ-9)

StateReason: STATE_INPUT_INVALID, ENGAGEMENT_ORDER_VIOLATION, JUNCTION_GEOMETRY_UNSUPPORTED,
             GEOMETRY_INPUT_INVALID, SPAN_INTERVAL_INVALID, ENGAGED_POSE_UNDERDETERMINED,
             CHAIN_CLOSURE_VIOLATED, STATE_NOT_VETOED                     # cassette_state
NodeReason:  CONTOUR_BUDGET_VIOLATED, NODE_NOT_VETOED                     # cassette_node
StateCode:   the failure reasons above as ERROR codes; INFO CLOSURE_SWEEP, UNRESOLVED_UPSTREAM,
             CONTOUR_BUDGET, SHIELDING_ANCESTOR, DERIVED_RIGID_SPAN, STATE_VETO_PROPAGATED
UnsupportedGeometryError(ValueError)                                      # cassette_state

StateCertificate(state_result, state, context, config_identity_hash, context_hash)   # cassette_state
ROOT (singleton sentinel); EffectiveAnchor(point: Vec3, ancestor: str | ROOT,
      ancestor_module_cassette_index: int)                                 # cassette_frames
SpanBasis(str, Enum): DERIVED_FROM_ENTRY_EXIT_OFFSETS                       # cassette_budget
BudgetElementKind(str, Enum): SEGMENT, SPAN, CAPTURE_OFFSET
BudgetElement(element_id, kind, source_id, source_fields, index, a_nm, b_nm,
              span_basis: Optional[SpanBasis], derived_rigid_span_nm: Optional[float])
BudgetBreakdown(budget_kind: "NODE" | "CLOSURE", elements, D_max_nm, D_min_nm,
                dominating_element_id, folding_unobstructed, includes_capture_offset, ...)  # see K
Tri(str, Enum): TRUE, FALSE, UNDETERMINED; __bool__ raises TypeError        # cassette_closure
```

Context types:

```text
TargetGeometry(site_nm: Vec3, orientation: Optional[Rotation3] = None)
    site_nm: three finite real numbers (bool rejected), else ValueError
    orientation: None, or orthonormal with det +1 within eps_rotation of NumericalTolerances() defaults
                 (re-checked against the context's own tolerances in EvaluationContext), else ValueError
    orientation is context data used only by the AP-22 placement convention under POSE_REQUIRED;
    it is never a conditioned bound pose and is ignored by pose-dependent predicates under
    ORIENTATION_MARGINALIZED

TargetContext(targets: Tuple[Tuple[str, TargetGeometry], ...] = ())
    normalized to ascending target_id; ids non-empty plain str; duplicate target_id entries -> ValueError
    stored as a tuple (not a dict/MappingProxyType) so identity._canon accepts it
    lookup(target_id) -> Optional[TargetGeometry]
    one entry may be referenced by any number of ENGAGED assignments

NumericalTolerances(eps_len_nm: float = 1e-9, eps_rotation: float = 1e-9)
    each finite real and > 0, else ValueError
    as_dict() -> {"eps_len_nm": ..., "eps_rotation": ...}

EvaluationContext(targets: TargetContext, tolerances: NumericalTolerances = NumericalTolerances())
    targets has no default: an empty TargetContext must be passed explicitly
    re-validates every orientation against tolerances.eps_rotation
```

Public signatures:

```text
cassette_effective_anchor(module_id: str, state: EngagementState, cfg: CassetteConfig,
                          context: EvaluationContext) -> EffectiveAnchor
cassette_contour_budget(module_id: str, state: EngagementState, cfg: CassetteConfig) -> BudgetBreakdown
chain_closure_feasible(upstream_module_id: str, downstream_module_id: str, state: EngagementState,
                       cfg: CassetteConfig, policy: CassettePolicy, context: EvaluationContext) -> Tri
evaluate_state(state: EngagementState, cfg: CassetteConfig, policy: CassettePolicy,
               context: EvaluationContext) -> EvaluationResult                       # STATE
issue_state_certificate(state_result: EvaluationResult, state: EngagementState, cfg: CassetteConfig,
                        policy: CassettePolicy, context: EvaluationContext) -> StateCertificate
evaluate_node(node_id: str, state_certificate: StateCertificate, cfg: CassetteConfig,
              policy: CassettePolicy) -> EvaluationResult                              # NODE; context from certificate
propagate_state_veto(node_id: str, state_result: EvaluationResult, cfg: CassetteConfig,
                     policy: CassettePolicy) -> EvaluationResult                       # NODE
identity: state_identity_hash(state) -> str; context_identity_hash(context) -> str;
          tolerance_identity_hash(tolerances) -> str; result_identity(object_kind, components) -> str
status:   make_result(...) -> EvaluationResult   (see C)
module-level, not exported: cassette_budget.closure_span_budget(upstream_module_id, downstream_module_id,
          state, cfg) -> BudgetBreakdown
```

`context` is the last positional parameter wherever it appears. Positional order of the closure-doc
parameters is otherwise unchanged.

Export allowlist (`__all__`): the 39 Phase 1c names plus

```text
EngagementLabel, ModuleAssignment, EngagementState, TargetGeometry, TargetContext,
NumericalTolerances, EvaluationContext, StateReason, NodeReason, StateCertificate,
UnsupportedGeometryError, EffectiveAnchor, ROOT, SpanBasis, BudgetElementKind, BudgetElement,
BudgetBreakdown, Tri, cassette_effective_anchor, cassette_contour_budget, chain_closure_feasible,
evaluate_state, issue_state_certificate, evaluate_node, propagate_state_veto,
state_identity_hash, context_identity_hash
```

Not exported: `make_result`, `make_config_result`, `OBJECT_KINDS`, `StateCode`, `Vec3`, `Rotation3`,
`closure_span_budget`, `tolerance_identity_hash`, `result_identity`. Forbidden: list in A.

---

## Migration Plan

1. **Contract/spec changes.** Record AP-20..AP-27 decisions. Apply corrections to closure doc N7,
   §4.1, §4.2, §5, T79 #10 #12, T83 #1 #5 #12-#16; D-record D6(3) example, Part 3 API and reasons
   (remove `upstream_resolution`, `SELF_AVOIDANCE_IGNORED`, `SHELL_BOUND` from Phase 2), T77.
   Measure the baseline.
2. **Status/result model** (one patch each, Phase 1c suite green after each): `OBJECT_KINDS` and
   `make_result` with the L7 golden test first; payload/exactness rule (L6); freezing of
   `upstream_state` and `numerical_tolerance_used` (L9); identity functions (L8). Extract the `R_union`
   helper from `cassette_topology.py` with no semantic change.
3. **Module setup.** Five modules with types, constants, context objects (fully implemented, since they
   are pure data) and `NotImplementedError` stubs for public functions; `__all__`.
4. **Test migration.** Replace the leak test with L1-L3; add L4, L5, L10, L11, L13-L15 and the Phase 2
   test module skeleton with rewritten T79/T83. No other Phase 1c test changes.
5. **Implementation**, in chain order: `cassette_state` (input checks, down-closure, certificate) →
   `cassette_frames` → `cassette_budget` → `cassette_closure` → `cassette_node`.

---

## Rejected Alternatives

| Alternative | Reason |
|---|---|
| Counter-based `result_id` (`st-0007`) | Order- and process-dependent; breaks seed stability (`C1DiagnosticsSerializable`, T78) |
| `evaluate_node.py` with function `evaluate_node` | Package attribute rebinding breaks submodule import and `mock.patch` targets |
| `evaluate_state` in `cassette_state.py` | Import cycle (mapping C5) |
| Separate `StateResult` class | Duplicates §10.1 enforcement that `apply_status_field_pattern` and `__post_init__` centralize |
| Phase 2 probability/density/interval outputs, or encoding feasibility as `1.0` | Outside the boundary (closure doc §4.4, N5, N13, N15) |
| `vetoing_state_result_id` in `upstream_state`, or in both places | Mixes input with result metadata; two carriers can disagree |
| Order violation falling through to closure | Contradicts closure doc N16 |
| `UNREACHABLE` for order or input violations | Merges structural and geometric vetoes |
| `eps_len` or targets in `CassettePolicy`/`CassetteConfig` | Owner ruling; would change `config_identity_hash` |
| Target geometry inside `EngagementState` | State is the conditioning declaration hashed into `upstream_state`; coordinates would leak into it |
| Optional `context` with a default | Would allow geometry without declared targets |
| Capture offset in the closure gate | Owner ruling OQ-3; §20.5 measures exit to entry |
| `spacer_span` field on `ModuleSpec` | Changes Phase 1c schema and every config hash |
| Reusing the `FREE_SWIVEL` budget for `FIXED_RIGID` | Owner ruling OQ-7; silent model substitution (same class of error as MNH23) |
| Bare `"ROOT"` ancestor string | Collides with a legal module identifier |
| `Tri` without a `__bool__` guard | `FALSE` would be truthy |
| Keeping `upstream_resolution` as mandatory | No available text defines it (OQ-8) |
| Uniqueness constraint on `target_id` across ENGAGED modules | Owner ruling OQ-9; not a v1 validation rule |
| Treating a supplied orientation as the bound pose under `ORIENTATION_MARGINALIZED` | Owner clarification of AP-22; orientation is context data, not a conditioned pose |
| Changing `METHOD_VERSION` now | Breaks Phase 1c `"0.3.1"` assertions without a version policy |
| Deep-freezing `DiagnosticRecord.quantities` globally | Changes Phase 1c in-memory types |

---

## Open Question Resolutions

| ID | Resolution | Status |
|---|---|---|
| OQ-1 | Labels are `ENGAGED`, `UNENGAGED` only. `ModuleAssignment` construction: `ENGAGED` requires a non-empty plain `str` `target_id`, `UNENGAGED` requires `target_id is None`, else `ValueError`. Modules absent from `assignments` are UNENGAGED. Target geometry comes only from `EvaluationContext.targets`; never from `CassetteConfig`. An ENGAGED `target_id` absent from the context yields `GEOMETRY_INPUT_INVALID` before any geometry function runs. Placement follows AP-22 (convention only, not a bound pose). | RESOLVED (AP-22, AP-27 approved) |
| OQ-2 | `NumericalTolerances` in `EvaluationContext`; not in `CassettePolicy`. Reported in `numerical_tolerance_used`; hashed into `context_hash`/`result_id` and `tolerance_hash`; never into `config_identity_hash`. Defaults `eps_len_nm = 1e-9`, `eps_rotation = 1e-9`. | RESOLVED (AP-21 confirmed) |
| OQ-3 | Closure gate: `D_min − eps_len_nm ≤ ‖entry_world(D_j) − exit_world(D_i)‖ ≤ D_max + eps_len_nm` over `closure_span_budget`, which excludes every capture offset. Capture offsets remain in `cassette_contour_budget` for the node gate, once, and are available to Phase 4 under the exactly-once rule. | RESOLVED (AP-26 approved) |
| OQ-4 | `STATE_INPUT_INVALID` (`INFEASIBLE`, structural veto), stage 3. Config-relative trigger, every occurrence reported (complete diagnosis): an ENGAGED assignment `module_id` that is not in the cassette's `ordered_modules` (amendment A2: an UNENGAGED one is omission); quantities `module_id`, `defect = "UNKNOWN_MODULE"`. Config-independent rules are enforced at construction and never reach evaluation: wrong types → `TypeError`; duplicate `module_id`, ENGAGED without `target_id`, UNENGAGED with `target_id` → `ValueError`. When stage 3 fires, stages 4-9 are `CHECK_SKIPPED` and no geometry function runs. A shared `target_id` is not a trigger. | RESOLVED (AP-23 approved) |
| OQ-5 | `GEOMETRY_INPUT_INVALID` (`INFEASIBLE`, structural veto). Scope: only inputs the running evaluation needs. Triggers: ENGAGED `target_id` not in context; `POSE_REQUIRED` with `orientation is None`; root `AnchorSpec.position`, `entry_offset`, `exit_offset` (non-terminal), `capture_offset_vec` (node gate) MISSING, None where a vector is required, not three finite reals, or bool; `TetherSpec.L`/`L_min` MISSING, non-finite or negative. `L_min > L` stays `SPAN_INTERVAL_INVALID`. Quantities: `source_id`, `field`, `defect` in {`MISSING`, `NULL`, `MALFORMED`, `NON_FINITE`, `NEGATIVE`, `TARGET_NOT_IN_CONTEXT`, `ORIENTATION_REQUIRED`}, rendered with the `_safe` convention. `evaluate_state` checks targets of every ENGAGED module plus inputs on closure paths; `evaluate_node` checks inputs on the node path. A `target_id` shared by several ENGAGED modules is not a trigger. | RESOLVED (AP-23 approved) |
| OQ-6 | `evaluate_node` accepts `node_id` only if it is in the certificate config's `ordered_modules` and ENGAGED in `state_certificate.state`, else `ValueError`; certificate/config mismatch (`config_identity_hash`) → `ValueError`. Gate: `d = ‖site(target of node) − effective_anchor.point‖`, veto iff `d < D_min − eps_len_nm` or `d > D_max + eps_len_nm` → `UNREACHABLE` / `CONTOUR_BUDGET_VIOLATED`, quantities `d_nm`, `D_min_nm`, `D_max_nm`, `eps_len_nm`, `side` (`BELOW_D_MIN`/`ABOVE_D_MAX`), plus `contour_budget_breakdown`. Otherwise `VALID` / `NODE_NOT_VETOED`, null payload. `propagate_state_veto` accepts any cassette module id. | RESOLVED (AP-24 approved) |
| OQ-7 | `FIXED_RIGID` never reuses `FREE_SWIVEL`. `evaluate_state` with at least one closure pair and `evaluate_node` (always, since the node gate is junction-dependent) return `NOT_EVALUATED` / `JUNCTION_GEOMETRY_UNSUPPORTED`, `UNDEFINED`, `NOT_COMPUTED`, no certificate, no propagation. Direct calls to `closure_span_budget`, `cassette_contour_budget`, `chain_closure_feasible` raise `UnsupportedGeometryError`. `cassette_effective_anchor` is junction-independent and works. A zero-pair state under `FIXED_RIGID` can still be `VALID` (no junction geometry was needed, closure doc N0 scope). | RESOLVED (AP-25 approved) |
| OQ-8 | `upstream_resolution` is removed from the required diagnostic contract. Required Phase 2 diagnostics: `CLOSURE_SWEEP` (when the sweep ran), `SHIELDING_ANCESTOR` and `CONTOUR_BUDGET` (node results), `UNRESOLVED_UPSTREAM` (`unresolved_upstream_ids`; under `EXCLUDED_SHELL_BOUND` also `unresolved_upstream_policy` and `downstream_numerical_evaluation_deferred`, closure doc N14), `DERIVED_RIGID_SPAN` (when used), `STATE_VETO_PROPAGATED` (when propagated). | RESOLVED |
| OQ-9 | Multiple ENGAGED modules MAY reference the same `target_id`. No uniqueness constraint exists in v1. Sharing MUST NOT produce `STATE_INPUT_INVALID`, `GEOMETRY_INPUT_INVALID`, or any ERROR/WARN diagnostic, and MUST NOT change status. A later version MAY add an INFO-only diagnostic; it MUST NOT become a validation rule in v1. Test L19. | RESOLVED (owner ruling) |

---

## Ready to Implement Checklist

Decisions (all closed):

- [x] AP-1..AP-12, AP-14..AP-21, AP-23..AP-27 approved.
- [x] AP-13 approved with the derived-rigid-span amendment (K).
- [x] AP-22 approved with the placement-convention clarification (E).
- [x] OQ-1..OQ-9 resolved; no open question remains.

Before any Phase 2 evaluation code:

- [ ] Spec texts corrected per Migration Plan step 1 (closure doc N7, §4.1, §4.2, §5, T79, T83; D-record D6(3), Part 3, T77), including the AP-22 wording that forbids "bound pose" language.
- [ ] Baseline test count measured in the real `gotne/` + `tests/` layout.
- [ ] Step 2 done: `make_result` + L7 golden test, payload/exactness rule (L6), frozen `upstream_state` and `numerical_tolerance_used` (L9), identity functions (L8), shared `R_union` helper; Phase 1c suite green at baseline after each patch.
- [ ] Step 3 done: five modules with types, context objects and stubs; `__all__` matches the allowlist.
- [ ] Step 4 done: leak test replaced by L1-L3; L4, L5, L10, L11, L13-L15, L19, L20 and the rewritten T79/T83 skeleton in place.
- [ ] Then implement in chain order: `cassette_state` → `cassette_frames` → `cassette_budget` → `cassette_closure` → `cassette_node`.
