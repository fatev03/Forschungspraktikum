# Colab: External AF3-ReD Output Audit

Open [`af3_red_colab.ipynb`](af3_red_colab.ipynb) in Colab using **File → Open notebook → Upload**, or select this path from your repository in Colab's GitHub tab. Choose a CPU runtime. Python 3.10+ and the standard library are sufficient; no package installation is needed for the native profile.

This is a separate entry point from `diffusion_fixed.ipynb`. It **does not run AF3-ReD inference**. It inventories and audits existing outputs read-only. **`admitted` means mapping preparation only.** It does not modify CIFs, inputs, outputs, or core manifests.

## Cell order and user flow

1. Execute the five embedded adapter cells and the explicit native bridge cell. Their sources are identical to the repository modules; local `src` imports are unnecessary.
2. Enter `OUTPUT_ROOT`, an existing absolute canonical directory accessible to the runtime, and explicitly choose `strict` or `af3_native_v1`. Empty defaults perform no file reads. The notebook neither downloads data nor mounts Drive.
3. Execute the inventory cell. Inspect artifact IDs, SHA-256 values, roles, statuses and reasons. The display limit only limits printed rows; `inventory["artifacts"]` retains every artifact. No coordinates are read at this stage.
4. Enter `SELECTED_ARTIFACT_ID`, `ARTIFACT_SHA256`, `TARGET_ID`, and `MODEL_ID`. Enter native `AUTH_ASYM_ID` / `LABEL_ASYM_ID`, or strict `STRICT_AUTH_CHAIN_ID` / `STRICT_SEGMENT`, leaving the other profile's fields empty. These are explicit user decisions, not inferred mappings.
5. Execute readiness, then the narrow contract check. Inspect `selection_result` and its `read_provenance`, plus the printed run provenance and missing metadata. Inventory remains the original unbound manifest; the selected result is separate. Both stay in memory.

After changing output root or profile, rerun inventory and enter a new explicit binding. After changing any binding field, rerun readiness. Changing the root may change artifact IDs. For another receptor, repeat this flow with its own root and explicit target ID; no receptor identity is derived from filenames or CIF fields.

## Reader and metadata limits

The `af3_native_v1` bridge is embedded and works standalone. The `strict` path retains the existing strict API. To perform strict coordinate reading, explicitly assign the existing, unchanged `structure_audit.structures.read_structure` to `STRICT_READER` in the optional configuration cell when that package is already available. Without it, strict inventory still works, and a selected native-layout sample remains `candidate` with `structure_reader_required`. There is no reader fallback or alternate strict implementation.

Run discovery requires one run-local `*_data.json` anchor. A folder without anchors produces diagnostics, not a successful real-output validation. The optional `af3red_adapter_metadata.json` is the adapter's **assumed schema**, not an upstream AF3-ReD file. This notebook does not generate it or derive missing metadata from directory names. A successful native read can therefore remain `candidate`. Root copies retain their separate role and cannot become independent samples.

Inference, GPU setup, model downloads, ranking, ligand validation, CIF repair, label-to-author copying, implicit receptor/segment/residue mapping, binder generation, sequence design, and geometry/core integration are intentionally unsupported. Notebook outputs may contain the paths and identifiers you supplied; clear outputs before sharing.

## Local smoke-check

From the repository root:

```sh
python3 -B examples/smoke_af3_red_colab.py
```

The check executes notebook cells without local `structure_audit` imports, checks embedded-source parity, and exercises empty defaults, inventory, native readiness, strict-without-reader behavior, wrong/stale bindings and read-only behavior. Synthetic files are created only by the smoke harness in a temporary directory. No real artifact, golden baseline, parser, or main notebook is modified. This is notebook validation, not another real-run golden validation.

## Optional external-reference presentation (after existing outputs)

When the repository package is already importable, compose **already-produced** display
lines with the supplied historical runtime observation below. This example is not a
notebook cell addition. `existing_summary_lines` must already contain the caller's
candidate, geometry and/or state/avidity output lines; this seam runs none of those paths
and establishes no relationship between their results and the external reference.

```python
from structure_audit.demo_external_reference import ExternalStructureReference, build_demo_report

reference = ExternalStructureReference(
    provider="af3-red", profile="af3_native_v1",
    artifact_id="5b4690580b352de100439cc68cb460847c4f4729c3b9151ca6ba739f8ce2aad7",
    observed_sha256="58f38cc8f279fb827851c27ff735bdc4b310ca22276a6a2cf8ebbb2414a882ed",
    source_status="candidate", read_completed=True, execution_state="completed",
    validation_status="passed_with_nonfatal_observations",
    non_admission_reasons=(
        "af3red_execution_declaration_missing", "bias_sigma_unknown", "bias_weight_unknown",
    ),
)
report = build_demo_report(existing_summary_lines, reference)
print("\n".join(report.render_lines()))
presentation = report.to_dict()  # fresh in-memory snapshot; never a core summary
```

Omit the second argument (or pass `None`) when no reference is supplied/available;
the existing lines still render normally. No files are accessed, hashes checked or
metadata completed. Runtime validation remains separate from scientific validation;
the source status stays `candidate`. Existing summary documents and their identities
are unchanged.
