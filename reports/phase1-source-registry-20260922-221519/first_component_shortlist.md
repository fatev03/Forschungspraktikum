# first_component_shortlist

These are candidates for a later qualification cycle, not implementation authorization. No tests or fixtures were executed in Phase 1. Historical test reports are not current qualification evidence. All three remain classified at most.

## 1. Supplied-conformer identity reader

- Source record: project record for src/structure_audit/supplied_conformer_output_adapter.py (exact ID/path/hash in manifest), linked to R-ALPHAFLOW/C-ESMFLOW as potential artifact providers.
- Proposed role: validate a supplied conformer artifact and its model/sample/chain/residue bindings at L2; return detached audit evidence. No core input derivation yet.
- Why first: the local module documents an explicit read-only contract and dedicated tests exist. It is a smaller surface than running either ensemble model.
- Minimum fixture: one tiny two-model PDB or supported mmCIF, explicit artifact hash, two sample bindings, chain/sequence/residue maps and matching manifest; variants with swapped identity, stale hash and missing mapping.
- Acceptance criteria: exact sample/model/chain/index preservation, no inferred units/frame, explicit unknown producer declarations, caller immutability, fatal invalid-binding behavior and no partial success. Existing tests must later be revalidated under authorization. Any actual core conversion additionally requires the missing specification and a field-by-field mapping.
- Disable/revert: remove the profile from selected inputs; preserve old run records and hashes. A required artifact remains unavailable rather than replaced with another producer.
- Authority isolation: the current contract emits an audit/import result, not a core probability, status or derived field.

## 2. Reader-only ColabFold-style A3M profile

- Source record: project record for src/structure_audit/colabfold_a3m_lossless.py; potential relationship to R-MSA is an input-format boundary, not evidence that Pairformer outputs are already supported.
- Proposed role: preserve query identity, raw alignment tokens, insertion anchors and mapping evidence at L2. Keep optional statistics and downstream binding disabled initially.
- Why first: explicit local parser profile, source-level contract and dedicated tests; avoids upstream model execution and the broader pairing/scoring interface.
- Minimum fixture: tiny A3M with a non-first selected query, insertion, gap, supported unknown token and explicit sequence/hash; rejection variants for incorrect query, unsupported star and stale hash.
- Acceptance criteria: raw-to-parsed-to-query mapping is lossless and explicit; no automatic query selection, uppercasing, pairing, weighting or model imports; unavailable evidence is not zero or success. Confirm exact fixture expectations from current module/tests before qualification.
- Disable/revert: omit this optional input/profile; record evidence as not evaluated. Do not substitute the upstream token-deletion helper.
- Authority isolation: parsing records only; neither MSA statistics nor feature tensors become core probability or geometry.

## 3. BC2 preset-precedence pattern

- Source record: R-BC2, with file records for README.md, docs/reference.md and bindcraft/settings.py.
- Proposed role: a later independently specified, small resolver for permitted non-core configuration at L1.
- Why first: precedence is explicitly documented locally. The useful idea can be evaluated without the design stack. Direct code extraction is not yet suitable because settings.py imports scientific modules and reads scientific defaults.
- Minimum fixture: synthetic baseline/task/campaign/override settings with one permitted key; unknown-key, precedence-conflict, inheritance-cycle and forbidden-core-field cases.
- Acceptance criteria: deterministic resolution and per-field provenance; fixed core-owned keys rejected; no JAX/AF imports, file discovery, model defaults or adaptive setting changes; selected source identity and applicable extraction conditions documented.
- Disable/revert: use an explicit fully resolved configuration with the same permitted field schema. No hidden fallback preset.
- Authority isolation: the missing core contract defines which fields may be set. BC2 never defines that allowlist.

No Potts/ProteinMPNN inference, PathFold output admission, whole PoseBusters execution, or campaign-restart extraction is shortlisted: each has a larger unresolved semantic or dependency surface.

- Exact shortlisted record: P-e0146326f925a73c — [/Users/fatihyigitevyapan/Desktop/Forschungspraktikum/src/structure_audit/supplied_conformer_output_adapter.py](</Users/fatihyigitevyapan/Desktop/Forschungspraktikum/src/structure_audit/supplied_conformer_output_adapter.py>) — SHA-256 732e55e7117653329519d04f9a3a732d2f7f1f37e6778825fd620dc025ea750a.

- Exact shortlisted record: P-657461cca3efc162 — [/Users/fatihyigitevyapan/Desktop/Forschungspraktikum/src/structure_audit/colabfold_a3m_lossless.py](</Users/fatihyigitevyapan/Desktop/Forschungspraktikum/src/structure_audit/colabfold_a3m_lossless.py>) — SHA-256 3e6765b973f8542cc78ebe54e9b7efd70eec324e07bf8d54372cdab0ec1f891b.
