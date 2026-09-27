# repo_specific_first_pass_map

Observed local facts are separated below from proposed classifications. All classifications are provisional; no external source is qualified or enabled by this report. Source IDs resolve in local_source_registry.md and baseline_manifest.json.

## AlphaFlow — R-ALPHAFLOW

**Observed/documented:** local README identifies AlphaFlow and ESMFlow together and documents conformer generation, model families, MSA/template requirements and sampling settings. The repository has no observed Git metadata. Code/checkpoint/ensemble versions are separate identities.

**Proposed:** adapter; L2; adapter-mediated supplied-conformer import first. Preserve source run, ensemble/sample IDs, coordinate frame, units, sequence/chain/residue maps, checkpoint and generation settings. Whole inference integration is deferred.

**Forbidden:** defining sample equilibrium weights without evidence; substituting conformer confidence for core probability; changing geometry or derived fields.

**Main risk/gate:** sample semantics and mapping errors. Require a byte-identified artifact, full binding/provenance contract, rejection fixtures and an authorized mapping into the located kernel contract.

## ESMFlow — C-ESMFLOW

**Observed/documented:** a named model family in the AlphaFlow README with local alphaflow/model/esmfold.py and a documented esmfold mode. It is not a separately discovered repository.

**Proposed:** adapter; L2; its own model/output profile linked to R-ALPHAFLOW.

**Forbidden:** treating ESMFlow and AlphaFlow checkpoints, sample distributions or settings as interchangeable; emitting core outcomes.

**Main risk/gate:** shared source identity can obscure distinct producer semantics. Require exact selected model/checkpoint and explicit artifact mapping; validate separately from AlphaFlow.

## PoseBusters — R-POSE

**Observed/documented:** README examples concern generated molecule poses, ligands and protein-ligand inputs. Local source/tests exist; no checks were run.

**Proposed:** QC_audit; L3; reference-only initially, partial extraction only after exact applicability is established.

**Forbidden:** protein-protein/tether validity claims by analogy; clearing a core veto or overwriting core status.

**Main risk/gate:** artifact-type mismatch. Review one named check, required chemical topology, units, unsupported cases and known pass/fail fixtures before active use.

## PathFold — C-PATHFOLD and linked paper/data records

**Observed:** the local paper identifies PathFold and DOI 10.64898/2026.08.26.747321. Opening pages describe sequence-driven folding-path generation. Three postprocessing collections contain PDB files. No paired implementation repository was located.

**Proposed:** future_extension; L2 only in the separate experimental lane; current use reference-only/deferred.

**Forbidden:** treating filename step/epoch labels as verified producer settings, physical time or equilibrium probability; feeding unqualified outputs into baseline geometry.

**Main risk/gate:** producer lineage, representation, indexing and path-step semantics remain unresolved. Establish the exact producer and output contract before even a source-specific import is promoted. The historical prior-state requirement is not supported by the inspected opening pages.

## MSA Pairformer — R-MSA

**Observed/documented:** README describes embeddings, contacts and variant scoring; pyproject declares msa-pairformer 1.0.2. A separately registered local v1 preprint is present. potts_diffpalm_utils.py contains an insertion-removal helper that removes lowercase characters, dot and star; this is not the existing strict local A3M parser contract.

**Proposed:** adapter; L2; explicitly mapped receptor feature artifacts. No inference is part of Phase 1.

**Forbidden:** importing unverified pairing/co-evolution assumptions, silent token deletion, or promoting embeddings/contact scores to core probabilities/statuses.

**Main risk/gate:** raw-to-parsed-to-query-to-structure mapping, mask behavior, checkpoint identity and pairing justification. Resolve the two local license files' component coverage. The stricter existing local parser must not be weakened to mimic an upstream helper.

## Potts — R-POTTS; distinct C-MSA-POTTS-UTILS

**Observed/documented:** PottsMPNN README describes sequence generation and mutation-energy prediction and links Zenodo DOI 10.5281/zenodo.18274667. Checkpoints, examples and optimization scripts are present. ITERATIVE_OPTIMIZATION.md describes a separate AF3/ipSAE/PISA loop. Local history does not establish which additions are upstream or locally modified. MSA Pairformer also has Potts/DIFFPALM-named utilities; those are not evidence of the same source identity.

**Proposed:** scoring_ranking; L5, with any sequence-proposal output separately adapted at L2; adapter-mediated later. MSA pairing utilities remain reference-only in this task.

**Forbidden:** executing/importing the optimization loop as a kernel; translating model energies or sequence scores into core outcomes; redesigning geometry under the scoring interface.

**Main risk/gate:** score meaning, chain partitions, fixed positions/gaps, checkpoint lineage and local modifications. Begin, if later justified, with a fixed mutation-score artifact and explicit wildtype/mutant position mapping; no sequence/model execution now.

## ProteinMPNN — C-MPNN-MOSAIC, C-MPNN-BC2, C-MPNN-DL

**Observed/documented:** no standalone ProteinMPNN checkout was found. Mosaic contains derived model code and weights with a specific NOTICE; BC2 contains a JAX/Haiku integration and 12 .npz files documented as ProteinMPNN/HyperMPNN variants; dl_binder_design contains a wrapper and instructs cloning ProteinMPNN into an absent mpnn_fr/ProteinMPNN directory. Potts-compatible weights are not automatically original ProteinMPNN checkpoints. Each file is separately registered.

**Proposed:** sequence-space proposal/scoring candidates only; L2 artifact adapters or L5 auxiliary scores. Prefer evidence import over whole-package reuse. Do not assume these implementations are equivalent.

**Forbidden:** writing geometry outcomes, core probabilities or core-derived fields; silently replacing checkpoint families or alphabets.

**Main risk/gate:** provenance of ports/re-serialization, amino-acid alphabets, chain/fixed-position masks, score normalization and checkpoint compatibility. A selected implementation needs its own exact profile and sequence-score fixture.

## BindCraft2 — R-BC2; legacy BindCraft — R-BINDCRAFT

**Observed:** current BC2 README title is BC2 and explicitly identifies PacesaLab/BindCraft2. LICENSE names BindCraft2. pyproject declares package bindcraft version 1.0.1; commit/tag remain unknown. The older BindCraft directory and its license are separate sources.

**Documented/observed patterns:** BC2 describes layered presets and campaign resume. Output docs identify stage tables and campaign metadata. Static source inspection finds partial-file replacement and folder locking in campaign_output.py; this is not crash/restart validation. settings.py imports scientific modules and reads defaults at import time.

**Proposed:** orchestration; L1/L6, with L5/L7 presentation references; workflow-pattern reference and later selective reimplementation. Do not directly import the whole resolver.

**Forbidden:** adopting BC2's internal core/default.json as the ordered-geometry core; importing its loss/filter/ranking defaults, scientific statuses, adaptive settings or model substitutions.

**Main risk/gate:** apparent workflow utilities carry scientific dependencies and different semantics. Isolate a small preset-resolution specification, resolve selected-source version and extraction conditions, and validate precedence/locked fields independently. Full campaign and restart code is not a first component.
