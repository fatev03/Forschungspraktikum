# Literature Evidence Matrix

Historical source summaries are retained as reference/provenance. This patch did
not re-read the PDFs or use external source code to implement model/inference
integration. The role/priority labels below describe earlier research context;
they are not runtime dependencies or instructions to run tools.

| Source | Role | Transferable component | Main limitation | Recommended priority |
|---|---|---|---|---|
| MSA Pairformer | Evolution-aware feature model | Receptor-side MSA embeddings and contact priors | No justified natural coevolution for designed candidates | High |
| RFdiffusion | Backbone generator | Standardized backbone artifact/provenance inputs | Does not validate binding or design sequence | Medium |
| ProteinMPNN / existing sequence-design tool | Inverse folding | Candidate sequence generation and sequence score capture | Sequence score is not affinity | High |
| AlphaFlow / ESMFlow | Ensemble sampler | Target conformer sampling and ensemble summaries | Not kinetics, affinity, or Boltzmann-distribution proof | Medium |
| PoseBusters | Pose validator | Protein-small-molecule chemical/clash checks | Not for protein-protein interfaces | Conditional |
| MVsim | Multivalent kinetic simulator | C_eff and kinetic avidity sensitivity concepts | MATLAB; parameters require external evidence | Medium |
| PathFold | Folding-path inference | Exploratory intermediate-structure analysis | C-alpha, requires prior states, not equilibrium ensembles | Low |
| BindCraft | Binder-design pipeline | Candidate score table and multi-filter provenance | Confidence scores do not establish affinity | High |
| PXDesign | Generator/filter suite | Target-index validation and separate generation/selection records | Heavy environment; fixed thresholds are not universal | Medium |
| Mosaic | Composite-objective framework | Pluggable score-component architecture | Experimental/tuning-heavy; not a low-risk dependency | Low |

## Next-stage read-only review order

Paths below are relative to `literature/`. Existence was checked from local file
and directory listings only on 2026-09-14. Read the PDF first, then the paired
folder's README and output/schema code. Record source/version and exact field
definitions, not universal score thresholds. This list schedules no execution,
downloads, code copying, inference integration or scientific experiments.

| Order | Local PDF | External repository folder | Review purpose |
|---|---|---|---|
| 1 | `One-shot design BindCraft/Pacesa et al. - 2025 - One-shot design of functional protein binders with BindCraft.pdf` | `One-shot design BindCraft/BindCraft-main/` | Candidate identifiers, orthogonal metrics, provenance fields |
| 2 | `improving de novo binder design/Bennett et al. - 2023 - Improving de novo protein binder design with deep learning.pdf` | `improving de novo binder design/dl_binder_design-main/` | Supplied monomer/complex confidence outputs and residue indexing |
| 3 | `PXDesign/PXDesign Fast, Modular, and Accurate De Novo Design of Protein Binders.pdf`; then `PXDesign/PXDesign-main/assets/technical_report.pdf` | `PXDesign/PXDesign-main/` | Modular output contracts and target-index bookkeeping |
| 4 | `posebuster/posebuster.pdf` | `posebuster/posebusters-main/` | Geometry-check contracts and protein-small-molecule scope boundary |
| 5 | `alpha flow/esmflow meets alpha flow.pdf` | `alpha flow/alphaflow-master/` | Ensemble/conformer identity and supplied artifact provenance |
| 6 | `msa pairformer/2025.08.02.668173v1.full.pdf` | `msa pairformer/MSA_Pairformer-main/` | Receptor feature provenance; avoid unsupported candidate coevolution claims |
| 7 | `rfdiffusion/Watson et al. - 2023 - De novo design of protein structure and function with RFdiffusion.pdf` | No local RFdiffusion repository folder found in the listed literature directories | Historical backbone-output identity conventions only |
| 8 | `pathfold/pathfold.pdf` | No paired repository folder found | Prior-state/conformer requirements; provenance context |
| 9 | `design of drug-binding proteins/Fry et al. - 2026 - Zero-shot design of drug-binding proteins via neural iterative selection−expansion.pdf` | `design of drug-binding proteins/LASErMPNN-main/` | Supplied sequence-score/checkpoint metadata, context only |
| 10 | No matching local PDF established for Mosaic | `mosaic/mosaic-main/` | Inspect README references before pairing any paper; retain independent metric dimensions |
| 11 | `mvsim designing multivalent interactions/Bruncsics et al. - 2022 - MVsim is a toolset for quantifying and designing multivalent interactions.pdf` | `mvsim designing multivalent interactions/MVsim-1.1/` | Historical parameter/source provenance; outside current checks |
| 12 | `multivalent binding with ligands/Tan und Meyer - 2021 - A general model of multivalent binding with ligands of heterotypic subunits and multiple surface rec.pdf` | `multivalent binding with ligands/valentBind-main/` | Same boundary: parameter provenance, no new simulation |

Only after that order, if a separately scoped provenance review needs them:
`Dependence of Avidity on Linker Length for a Bivalent Ligand-Receptor System/Mack et al. - 2012 - Dependence of Avidity on Linker Length for a Bivalent Ligand–Bivalent Receptor Model System.pdf`,
then `linker dependent stab and avidity/De Queiroz et al. - 2025 - Linker-dependent modulation of anti-CD22 scFv antibody stability and avidity Combined structural an.pdf`,
then `Kinetic Superselectivity in Multivalent Binding/Ravnik et al. - 2026 - Kinetic Superselectivity in Multivalent Binding.pdf`.
No paired source repository folders were found for these in the shallow listing.

Keep `alpha flow/s41467-023-37139-y.pdf` separate: the historical handoff identifies
it as chemistry automation, not the protein ensemble AlphaFlow project. No
matching-paper relationship is asserted here for the separate atomistic-design,
TCR, kinetic-proofreading or receptor-availability PDFs; they are deferred from
this output-bookkeeping review.
