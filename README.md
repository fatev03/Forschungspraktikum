# Structure Audit

Offline utilities for organizing **user-supplied** protein structure/model outputs.
All checks report **format/geometric plausibility only**. The package does not
predict binding, affinity, biological function, or experimental outcomes.

The existing `diffusion_fixed.ipynb` is unchanged. It is a Colab workflow with
installation, inference, demo fallback and overwrite behavior; it is not required
to use these utilities. Nothing in `literature/` is imported, copied or executed.

## Minimal usage (no installation)

From this project root, with an existing Python 3.10+ interpreter:

```sh
PYTHONPATH=src python3 -B -m structure_audit tests/fixtures/minimal.pdb \
  --config configs/minimal.json --output-root audit_runs \
  --project-root . --run-id fixture

PYTHONPATH=src python3 -B -m unittest discover -s tests -v
```

Substitute an explicit local `.pdb`, `.cif` or `.mmcif` path for real supplied
inputs. The example uses tiny synthetic atom coordinates, not a designed protein.
Do not use the fixture report as scientific evidence. No downloads or environment
changes are needed. `pyproject.toml` describes optional packaging; running a
package build/install is not part of this workflow.

Each invocation allocates `audit_runs/fixture/v0001`, then `v0002`, and writes
`manifest.json`, `checks.json`, and `residue_map.csv`. Existing output files are
never overwritten. `completed` means report generation completed, even if a
check reports `warn` or `fail`. The example warns that absolute residue
completeness is unknown because no expected residue list was supplied.

Use [API documentation](docs/API.md) for schemas, explicit sequence mapping,
CSV/JSON adapters and filtering. See [handoff](docs/HANDOFF.md) for scope,
verification and the next-stage reading order. Existing directory inventory
documents describe the **pre-patch snapshot**, not the current package tree.

## Limitations

The mmCIF reader deliberately supports a strict atom-table subset. Ambiguous or
unsupported syntax/identity mappings raise `UnsupportedFormat` with
`unsupported / needs external dependency`; nothing installs a parser or falls
back to guessed identifiers. See the exact contract in `docs/API.md`.

Coarse clashes use a configurable distance cutoff, not covalent topology,
van der Waals radii, energies, or a calibrated structural quality score.
Missing residues require an explicit expected inventory or supplied mapping;
author-number gaps alone do not prove missing residues. Upstream model seeds,
versions, metric units and scales are never guessed.
