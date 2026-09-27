# Phase 2 name mapping

"Prompt" = names in `GOTNE_v031_phase2_semantic_closure.md` §4/§5 and the D-record phase
plan (`pasted_text_1790107971.txt`). "Actual" = what exists in this folder.

## 1. Paths and modules

| Prompt | Actual | Recommended canonical |
|---|---|---|
| `gotne/<module>.py` | Snapshot is flat; modules use relative imports (`from .status import ...`) and tests import them as `gotne.*` from `<root>/gotne/`. | Place Phase 2 modules beside `status.py` in the `gotne` package. |
| `tests/test_phase2_*.py` | Tests sit flat here; they expect `<root>/tests/`. | Put them beside the existing test modules in `tests/`. |
| `gotne/cassette_state.py` | absent | keep `cassette_state.py` |
| `gotne/cassette_frames.py` | absent | keep `cassette_frames.py` |
| `gotne/cassette_budget.py` | absent | keep `cassette_budget.py` |
| `gotne/closure.py` | absent | `cassette_closure.py` (matches the `cassette_*` prefix). Contract rename, needs sign-off. |
| `gotne/evaluate_node.py` | absent | `cassette_node.py`. See collision C1. Contract rename, needs sign-off. |

## 2. Functions and parameters

| Prompt | Actual | Recommended |
|---|---|---|
| `cassette_effective_anchor(module_id, ...)` (closure doc) vs `(mod_id, ...)` (D-record) | absent | `module_id` |
| `cassette_contour_budget(module_id, ...)` vs `(mod_id, ...)` | absent | `module_id` |
| `evaluate_node(node_id, state_certificate, ...)` vs `(node_id, state_cert: StateCertificate, ...)` | absent | `state_certificate` |
| `chain_closure_feasible(i, j, state, cfg, policy) -> Tri` | `Tri` undefined | define `Tri` in `cassette_closure.py`; members are an open question |
| `-> BudgetBreakdown`, `-> (Vec3, ancestor_id_or_ROOT, index)` | undefined | `BudgetBreakdown`, `BudgetElement`, `EffectiveAnchor` (NamedTuple), `ROOT` sentinel |
| `make_config_result(...)` as the builder | exists in `status.py`, hard-codes `object_kind="CONFIG"`, not in `status.__all__` | add a generic builder next to it; do not reuse the CONFIG one for STATE/NODE |
| reason literals as module-level `Final[str]` in `cassette_state.py` | Phase 1c convention is a plain `Reason` class of `str` constants in `cassette_topology.py` | `class StateReason` in `cassette_state.py` with exactly the three members; do not extend Phase 1c `Reason` |

## 3. Types

| Prompt | Actual | Recommended |
|---|---|---|
| `StateResult` | no class; D-record defines it as `EvaluationResult` with `object_kind="STATE"` | no new class; at most `StateResult = EvaluationResult` alias |
| `StateCertificate` | absent | new frozen dataclass in `cassette_state.py` |
| `object_kind` "STATE", "NODE" | plain `str` field; only "CONFIG" produced; no constants | `ObjectKind` str constants in `status.py`; keep the field a plain `str` (as_dict and Phase 1c tests rely on it) |
| `vetoing_state_result_id` | not defined anywhere | key string constant, location per corrections doc |

## 4. Existing types to reuse (do not duplicate)

`Status`, `Severity`, `Exactness`, `Provenance`, `ProvenanceRecord`, `DiagnosticRecord`,
`EvaluationResult`, `apply_status_field_pattern`, `precedence`, `STATUS_RANK`, `VETO_SET`,
`UNKNOWN_SET`, `CANONICAL_VALUE_FIELDS`, `CANONICAL_UNITS`, `METHOD_VERSION` (status.py);
`MISSING`/`Missing`, `TopologyMode`, `JunctionModel`, `EngagementOrderPolicy`,
`UnresolvedUpstreamPolicy`, `EngagedPoseResolution`, `DepEdge`, `DepEdgeKind`, all
`*Spec`, `CassettePolicy`, `CassetteConfig` (cassette_schema.py);
`validate_cassette_config`, `Code.CHECK_SKIPPED`, `Code.MODE_NOT_APPLICABLE`
(cassette_topology.py); `canonical_form`, `config_identity_hash`, `cache_key`
(identity.py). Test fixtures `base_policy`, `ref_cassette_3`, `CassetteTestCase`
(test_cassette_topology.py).
Private helpers `_safe`, `_err`, `_info`, `_skipped`, `_assumptions`, `_require_schema`
in cassette_topology.py are the serializer and diagnostic conventions; promote or mirror
them, do not import private names across modules.

Not exported from the package `__init__` today: `ProvenanceRecord`, `precedence`,
`VETO_SET`, `UNKNOWN_SET`, `canonical_form`, `make_config_result`.

## 5. Collisions and migration risks

- C1. Module `evaluate_node.py` plus `from .evaluate_node import evaluate_node` in
  `__init__` rebinds `gotne.evaluate_node` to the function. `import gotne.evaluate_node as m`
  and `mock.patch("gotne.evaluate_node.<name>")` then resolve against the function, which
  breaks the T79/T83 spies.
- C2. `PurityTests.test_no_phase2_symbols_leak` forbids package attributes
  `evaluate_node`, `evaluate_state`, `cassette_effective_anchor`, `cassette_contour_budget`,
  `compute_conditional_density`. Exporting Phase 2 names fails it; amending an existing test
  needs approval.
- C3. Three near-identical order names with different meanings:
  `Reason.ORDER = "ENGAGEMENT_ORDER_CONSTRAINTS_UNSATISFIABLE"` (config time),
  `Code.ENGAGEMENT_ORDER_CONFLICT` (config diagnostic), `ENGAGEMENT_ORDER_VIOLATION`
  (state time, new).
- C4. D-record lists `SELF_AVOIDANCE_IGNORED` as a fourth Phase 2 reason; that string is
  already the value of `UnresolvedUpstreamPolicy.SELF_AVOIDANCE_IGNORED`, and the closure
  doc allows only three reasons.
- C5. Import cycle: frames/budget/closure need state types from `cassette_state.py`, while
  `evaluate_state` in `cassette_state.py` needs them. Either move `evaluate_state` to its own
  module or keep state types in a module the others import without a cycle. Decision needed.
- C6. The Phase 1c purity regex bans `math` only for the five Phase 1c files; Phase 2
  geometry may import `math`. The import-boundary test must not reuse that regex blindly.
