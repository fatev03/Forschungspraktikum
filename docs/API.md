# Offline utility API (0.1.0)

Runtime: Python 3.10+, standard library only. CLI and tests work with
`PYTHONPATH=src`; no package installation, kernel changes or notebook execution.
Imports perform no I/O except when callers explicitly invoke a function.

## Structures and canonical residue identity

```python
from structure_audit import read_structure, canonical_residue_map

structure = read_structure("tests/fixtures/minimal.cif")
rows = canonical_residue_map(structure, altloc="A")
```

`read_structure(path, model_id=None)` accepts local, uncompressed PDB/mmCIF.
Multiple models require an explicit `model_id`; model identifiers remain strings.
The object retains all selected-model atom records, source lines, SHA-256 and
parser warnings. No atom is repaired, coordinate replaced, chain renamed or
residue renumbered. Duplicate atoms and repeated residue occurrences are retained
and cause the integrity check to fail. Contiguous conflicting residue names are
unsupported microheterogeneity. Identical contiguous residue records cannot be
distinguished from duplicate atom rows; they are reported as duplicate atoms.

Each canonical row contains `residue_index` (zero-based, file/model-specific),
`model_id`, `chain_id`, `segment`, `record_group`, `residue_id` (signed integer),
`insertion_code`, `residue_name`, `label_chain_id`, `label_seq_id`, `source_lines`,
`atom_names`, `selected_altloc`, `missing_backbone_atoms`, `warnings`.
Author identifiers are canonical; label identifiers are retained separately.
PDB blank chain/insertion identifiers become empty strings, never guessed IDs.
`TER` increments a segment. HETATM rows remain in the map but are excluded from
polymer backbone and coarse clash checks, including modified amino acids encoded
as HETATM. This exclusion is part of the fixed check scope.

Atom selection uses shared blank-altloc atoms plus exactly the configured altloc
(default `A`). A missing conformer does not fall back to B/highest occupancy.
Competing shared/selected-altloc atom names or duplicate names are unavailable
and explicitly warned. Raw alternatives remain in `Structure.atoms`.

### Supported mmCIF contract

One CIF 1.1 `data_` block, one `_atom_site` loop; quoted values, comments,
semicolon multiline metadata, unrelated scalar/loop metadata are lexed. Atom
table values can span physical lines; source line numbers are retained.
All fields below must exist:

```
group_PDB auth_asym_id auth_seq_id auth_comp_id auth_atom_id
label_asym_id label_seq_id label_comp_id label_atom_id label_alt_id
pdbx_PDB_ins_code Cartn_x Cartn_y Cartn_z type_symbol
```

Author/label component and atom names must agree; chain aliases must be one-to-one
within a model. `auth_seq_id` must be an integer. `label_seq_id` is required and
known for ATOM, nullable for HETATM. Unknown author IDs are unsupported.
Unquoted `.`/`?` are accepted as absent altloc/insertion/occupancy where allowed;
quoted placeholder-like identities are explicitly unsupported. Missing
`pdbx_PDB_model_num` means a single model `1`; a present but unknown model ID is
unsupported. Occupancy is optional and never inferred; missing occupancy excludes
that atom from clashes with a warning.

CIF 2.0, multiple data blocks/atom loops, save frames/stop directives, mixed atom
loop categories, scalar atom tables, unknown required identities, incompatible
auth/label naming, alias collisions and microheterogeneity raise
`UnsupportedFormat` (`unsupported / needs external dependency`). This is a
conservative contract, not a complete CIF parser. Malformed numeric values,
truncation and loop-width errors raise `StructureFormatError`. No alternate parser
or network lookup is attempted. A broader format needs separately scoped work
with an external parser and fixtures.

PDB REMARK 465/470 presence is reported as an unparsed missing-data annotation.
Neither those annotations nor mmCIF sequence metadata are automatically interpreted
as complete polymer sequences. Supply explicit expected residues/mappings.

## Supplied sequence-to-structure mapping

`validate_sequence_mapping(structure, supplied_sequence, entries)` validates every
position of one supplied uppercase standard-amino-acid sequence. It does not
generate a sequence or perform alignment. The sequence hash elsewhere uses exact
text; this mapping API intentionally has a stricter alphabet contract.

Each entry must contain exactly:

```
sequence_position: one-based integer
residue_index: canonical-table index, or null
reason: string or null (nonempty for a null residue_index)
```

Return statuses: `matched`, `mismatch`, `missing_or_unmapped`. Mapping must cover
all supplied positions exactly once, without reusing an observed residue. No
assumption is made that residue number equals sequence position. Nonstandard
residues, HETATM mapping, duplicate unresolved residue identities or ambiguous
sequence formats raise an explicit unsupported error. The caller supplies chain
association through the chosen canonical indices; alignment ambiguity is never
resolved automatically. Persist the source hash/model with the table and mapping;
indices from another structure are not interchangeable.

## Quality checks

`structure_integrity_check(structure, config=None)` and
`coarse_steric_clash_check(structure, config=None)` return `CheckResult` with
`check`, `status`, `metrics`, `configuration`, `messages`, `provenance`, `category`.
Use `.to_dict()` for strict JSON. Both carry utility/check version, source hash,
selected model, effective configuration and the category
`format/geometric plausibility only`.

Integrity configuration: `altloc="A"`, `max_peptide_cn_distance=2.0` Angstrom,
`expected_residues=[]`. Expected identities have exactly `chain_id`, `residue_id`,
`insertion_code` and apply to the selected model. Missing N/CA/C/O atoms, explicit
expected residue absences, possible numbering gaps, unassessable neighbor bonds,
nonmonotonic numbering and C-N separations above the threshold are warnings.
Explicit TER boundaries are reported separately, never bridged. Duplicate IDs or
non-finite coordinates fail. Without an expected inventory the check warns that
absolute completeness is unknown. No polymer records is also a warning.

Clash configuration: `altloc="A"`, `cutoff_angstrom=2.0`, `scope="interchain"`,
`fail_at_count=null`, `max_reported_pairs=100`. Only selected polymer ATOM heavy
atoms with a supplied element and positive finite occupancy are eligible. Unknown
element/occupancy, non-finite coordinates and unresolved selected atoms make the
result partial and warn. Models and alternate conformers are never compared to
one another. Same-residue pairs are excluded; `nonlocal` additionally includes
same-chain pairs but excludes consecutive observed residues within each segment.
There is no inferred covalent topology. Interchain covalent bonds may be flagged.
H/D atoms are excluded. Contacts use strict `distance < cutoff`.

A cell list counts nearby contacts; displayed pairs are capped but total count is
not capped. `nearby_pair_comparisons` counts only spatial-neighbor comparisons,
not every possible pair. No eligible pairs yields a warning. Contacts warn by
default; `fail_at_count` provides a caller-selected failure threshold. This is not
an empirical protein acceptance criterion. `pass` applies only to the configured
geometry scope; it does not certify a complete structure or biological validity.

## Evidence and notebook adapters

`CandidateEvidence(candidate_id, sequence_hash, target_id, conformer_id, metrics,
provenance, warnings, missing_values)` serializes with `.to_dict()`. Unknown
sequence/target/conformer identities require entries in `missing_values`.
Provenance uses `model_id`, `checkpoint_id`, `seed`, each nullable. Target/conformer
IDs are caller-supplied identifiers, not assigned biological roles by the package.

Metrics contain `name`, `raw_value`, numeric `value` or null, `context` (`monomer`,
`complex`, `counter_screen`, `unassigned`), `category`, nullable `unit` and `scale`,
`source` (path/hash/row), `provenance`, `missing_reason`. Missing or nonscalar
metrics have null numeric values with reasons; raw JSON objects and CSV strings
remain intact. Non-finite scalar Python values become explicit raw string tokens;
strict JSON input rejects NaN/Infinity. Duplicate metric names within a context
are rejected; separate records are needed for distinct counter-screen identities.
No final score is computed.

`import_mpnn_csv(path, target_id=..., conformer_id=..., chain_roles=...,
provenance=..., metric_contexts=..., candidate_prefix="candidate")` reads all
provided CSV rows. `chain_roles` explicitly labels each slash-separated sequence
chain `target` or `candidate`. Hashing joins the exact supplied candidate-chain
text with `/`; the original CSV hash retains whole-input provenance.
`metric_contexts` must provide the context of `mpnn`, `plddt`, `i_ptm`, `i_pae`,
`rmsd`. Unknown columns are preserved in an `unassigned` raw-object metric.
No model mode, chain role, units, confidence scale or best row is inferred.

`import_boltz_confidence(path, provenance=...)` reads an explicitly supplied JSON
object; known confidence keys are labeled `model_confidence`, other keys
`unclassified_supplied`. Nested pair-chain metrics retain their raw object and
are not silently reduced to a scalar. Callers attach these to the explicitly
identified candidate. Both adapters reference source files; neither writes them.

`filter_candidates(candidates, rules, missing="exclude")` returns per-candidate
accept/reject decisions and reasons. Each rule has `context`, `name`, and `min`
and/or `max`; bounds are inclusive and supplied by the caller. Missing policies:
`exclude`, `include` (with explicit reason), `error`. There is no default ranking,
aggregation, calibration or Pareto optimization. Independent dimensions remain
available for a future explicit Pareto analysis.

## dl_binder_design score output adapter

`import_dl_binder_sc(path, *, bindings, manifest, config, provenance)` is exported
from `structure_audit` and `structure_audit.dl_binder_output_adapter`. It returns
`list[CandidateEvidence]` under the unchanged candidate-evidence schema 1.0.
This is a text-output adapter, not an upstream integration. It has no filesystem
writes, network access, subprocess calls, or inference imports.

The input is an explicitly supplied UTF-8 (optional BOM) `.sc` file with
whitespace-separated `SCORE:` header/data rows. Empty lines and `#` comments are
allowed. A header must contain exactly one `description` and at least one known
AF2 score field. Columns are addressed by name, including when reordered or when
a repeated header changes order. Duplicate headers fields, duplicate tags, row
width mismatches, missing tags, headerless records and non-SCORE data are errors.
`description` is a reserved header token and cannot be a data tag. Placeholder
tags (`nan`, `NA`, `N/A`, `none`, `null`, `.`, `-`, case insensitive) are rejected.
The `__dl_binder_import__` column name is reserved for adapter audit metadata.
An empty/header-only file is an error. Silent files and `.trb` are unsupported;
no conversion or pickle deserialization is attempted.

### Configuration and explicit binding

Required config fields are `profile="dl_binder_design_sc_v1"` and
`prediction_mode="complex"` or `"monomer"`. Optional fields default to null:
`initial_guess` (boolean), `recycles` (nonnegative integer), `upstream_snapshot`
(nonempty caller-supplied identifier). Other fields are rejected. The profile is
an explicit interpretation of the inspected format, not automatic producer
identification. One call handles one prediction mode. Unknown producer metadata
stays null and is marked caller-supplied/not-verified.

`manifest` is an existing `make_manifest`-compatible dictionary. Its
`config["dl_binder_output_adapter"]` must equal the supplied config and its
config hash must validate. The `.sc` and each referenced PDB must appear exactly
once as canonical absolute paths in `input_files`, with matching hashes. Only
these explicitly consumed input files are read. `provenance` uses the existing
`model_id`, `checkpoint_id`, `seed` contract and must match an entry in
`manifest["supplied_models"]`; an empty list also permits all three values null.
Finalize the manifest before importing: metadata hashes the exact supplied
manifest dictionary with `hash_config`, not the bytes of a later JSON file.

`bindings` maps every exact `description` tag to exactly these fields:

- `candidate_id`: unique nonempty caller-assigned identifier.
- `target_id`, `conformer_id`: nonempty strings or null, with missing reasons
  supplied by the adapter for null values.
- `pdb_path`: explicit local path string to the existing **prediction output**
  PDB; the adapter does not infer a filename from a tag.
- `pdb_model_id`: explicit model ID string, separate from the inference model ID.
- `residue_map`: existing in-memory rows from `canonical_residue_map(structure)`
  with default altloc A. The adapter checks exact agreement with the selected
  PDB/model; it does not repair, renumber or align it.
- `chain_roles`: ordered objects with exactly `chain_id`, `segment`, `role`.
  The complex profile requires first polymer chain/segment `candidate`, then
  `target`; monomer mode requires one `candidate` output chain/segment. Polymer
  ATOM records only; ambiguous duplicate residue identities are rejected.

The binding key set must equal the file's data tag set: no implicit subset
selection, dropped rows or partial return. Multiple tags may not silently collapse
into one candidate ID. Chain-role checks enforce the upstream binder-first
convention and structural identity; they cannot prove the biological identity of
a mislabeled target or that caller-supplied PDB/score files belong together.

### Metric semantics, missing values and quarantine

Original score names and string tokens are retained. Known fields are
`plddt_total`, `plddt_binder`, `plddt_target`, `pae_binder`, `pae_target`,
`pae_interaction`, `binder_aligned_rmsd`, `target_aligned_rmsd`, and `time`.
pLDDT uses the profile's 0-100 scale without conversion; PAE/RMSD use Angstrom;
time uses seconds. Known score values must be finite/nonnegative; pLDDT above
100 is unusable. Unavailable known columns still produce a record with raw/null
value and `missing_column`. Missing tokens and non-finite tokens, including
overflow such as `1e999`, retain their exact text with null numeric value.

Binder confidence, intra-binder PAE and binder-aligned binder CA RMSD use the
existing `monomer` context. Target confidence/PAE, bidirectionally averaged
`pae_interaction` and target-aligned **binder** CA RMSD use `complex` context.
`plddt_total` uses the explicit prediction mode; `time` is `unassigned`.
Every field's audit metadata additionally stores `prediction_context`: binder
metrics extracted from a complex prediction are not independent monomer
predictions. RMSDs refer to upstream initial coordinates, not experimental truth.

For this profile, **both RMSDs in monomer mode always have `value=null`,
`category="unsupported_semantics"` and an explicit `missing_reason` mentioning
the upstream `binderlen=-1` target-mask limitation**, even if their raw numeric
tokens are finite or zero. Complex-only fields in monomer mode and unknown
columns are also quarantined; unknown numeric fields are never clean metrics.
The adapter does not repair upstream calculations or compute replacement RMSDs.

The reserved `__dl_binder_import__` metric has `context="unassigned"`,
`category="import_metadata"`, null numeric value and a raw JSON object containing
the exact description/tag, ordered header and header line, raw data line/columns,
per-field status/raw status/reason/prediction context, binding/PDB/map references,
map and binding hashes, effective configuration/hash, adapter version, and run
manifest identity/hash. The map preserves model, chain, segment, author numbering,
insertion code and canonical indices. Metric source path/hash/line and the
original model/checkpoint/seed fields remain in their existing schema locations.
No schema or quality-check API changes are required.

No supplied full sequence is present in this contract, so `sequence_hash` stays
null with an explicit explanation; PDB ATOM records are not promoted to a full
candidate sequence. Existing `filter_candidates` sees quarantined metrics as
missing: default `exclude` rejects, `error` raises, and explicit `include` retains
the candidate with its existing missing-data reason. No final score is generated.

### Offline example with synthetic fixtures

This example is run from the project root, using only the included synthetic
score/config/PDB fixtures. In a real import, supply the already-established map
and role assignment instead of creating fixture bookkeeping. Plan all output
paths before creating the manifest so its hash remains stable.

```python
from pathlib import Path
from structure_audit import (
    read_structure, canonical_residue_map, import_dl_binder_sc,
    structure_integrity_check, coarse_steric_clash_check,
)
from structure_audit.provenance import (
    create_run_directory, make_manifest, write_manifest, write_json_new,
)
from structure_audit.validation import read_json

root = Path.cwd()
fixtures = root / "tests" / "fixtures"
score = fixtures / "dl_binder.sc"
pdb = fixtures / "minimal.pdb"
structure = read_structure(pdb, model_id="1")
config = read_json(fixtures / "dl_binder_config.json")
provenance = {"model_id": "synthetic-only", "checkpoint_id": None, "seed": None}
bindings = {"synthetic_complex": {
    "candidate_id": "fixture-1", "target_id": "fixture-target",
    "conformer_id": "fixture-conformer", "pdb_path": str(pdb.resolve()),
    "pdb_model_id": "1", "residue_map": canonical_residue_map(structure),
    "chain_roles": [
        {"chain_id": "A", "segment": 0, "role": "candidate"},
        {"chain_id": "B", "segment": 0, "role": "target"},
    ],
}}
run = create_run_directory(root / "work" / "dl_binder_example", "fixture")
outputs = [str(run / name) for name in (
    "candidate_evidence.json", "checks.json", "manifest.json")]
manifest = make_manifest(
    run, {"dl_binder_output_adapter": config}, [score, pdb], project_root=root,
    supplied_models=[provenance], output_paths=outputs,
)
candidates = import_dl_binder_sc(
    score, bindings=bindings, manifest=manifest, config=config, provenance=provenance,
)
write_json_new(run / "candidate_evidence.json", [c.to_dict() for c in candidates])
write_json_new(run / "checks.json", [check.to_dict() for check in (
    structure_integrity_check(structure), coarse_steric_clash_check(structure))])
write_manifest(run / "manifest.json", manifest)
```

Result: `pae_interaction` raw `"8.500"` becomes complex value `8.5` Angstrom;
`binder_aligned_rmsd` raw `"0.250"` is the monomer-shape dimension, while
`target_aligned_rmsd` raw `"7.250"` is the complex-placement dimension. `extra`
stays raw `"opaque"` with null/quarantined interpretation. This fixture is not
evidence for a protein. The one-residue monomer boundary fixture in the tests
demonstrates that finite RMSDs are still quarantined in monomer mode.

Identity, mapping, schema/config and malformed-row errors raise before returning
any candidate list. Filesystem/structure-parser errors propagate. Input hashes
are checked again before return. The function cannot leave partial output files
because it writes none. Scientific incompleteness is carried as nulls/reasons;
it is not mistaken for successful inference or biological validation.

## Explicit notebook output adapter (contract 1.0)

Public exports from `structure_audit` and `structure_audit.notebook_output_adapter`:

- `import_notebook_outputs(*, artifacts, bindings, manifest, config)` returns
  `NotebookImportResult(candidates, quarantined, diagnostics)`.
- `NotebookImportResult.to_dict()` serializes both lists as existing schema-1.0
  CandidateEvidence objects. Pass **only `result.candidates`** to the unchanged
  `filter_candidates` API. The result itself is deliberately not iterable.
- Fatal errors raise `NotebookImportError(ValueError)` with `.diagnostics`:
  `severity`, `code`, `message`, `artifact_id`, `candidate_id`, `locator`. No
  partial result or candidate list is returned, even for a late binding failure.

This adapter reads only explicitly registered local files and performs no writes,
network calls, directory discovery, model imports or notebook execution. It does
not infer filenames, select a first/best result or automatically bind by basename.
The older CSV/JSON helpers and dl_binder adapter remain unchanged.

### Artifact registry and producer contract

`artifacts` is a nonempty dictionary keyed by simple IDs matching
`[A-Za-z][A-Za-z0-9_-]*`. Each artifact has `kind`, `path`, `sha256`; `kind` is
`mpnn_csv`, `boltz_json`, `pdb`, or `notebook`. Paths must be exact absolute local
file paths with the corresponding `.csv`, `.json`, `.pdb`, or `.ipynb` suffix.
Patterns are rejected. Same basenames in distinct explicit paths are allowed.
Every registered artifact must be consumed by an explicit binding/reference.

Every non-notebook artifact additionally requires these exact fields:

- `source_run_id`: nonempty caller-supplied upstream run identifier, distinct
  from the bookkeeping manifest run ID.
- `origin`: `design`, `demo`, `unknown`, or `origin_conflict`.
- `fallback_used`: boolean or null; null means not supplied, not confirmed false.
- `producer`: exactly `name`, `version`, `model_id`, `checkpoint_id`, `seed`,
  `status`. Metadata is nullable; seed is a nonnegative integer when supplied.
  Status is `caller_supplied` or `unknown`; unknown requires all metadata null.
  The adapter does not allow a claim of independently verified producer history.
  The artifact producer metadata is retained on each field; it is not inferred
  from column names. Mixed upstream producers need separately attested artifacts.
- `notebook_ref`: null with an explicit unknown audit status, or exactly
  `artifact_id`, `cell_index`, `cell_source_sha256`, `role`. The referenced artifact
  must be a registered notebook. Index is zero-based; role is `producer` or
  `consumer`. The cell hash is SHA-256 of UTF-8 cell source (join source arrays
  without inserting separators). Notebook file hash and cell hash are verified;
  cell ID is retained if present. Execution remains `not_verified`: referencing
  a consumer cell is not evidence that it generated the external output.

PDB and Boltz artifacts also require a nonempty string `sample_id`. All model
provenance triples that are not entirely null must appear in the manifest's
`supplied_models`. Different artifacts can carry different models/checkpoints/seeds;
CandidateEvidence's aggregate producer is deliberately all null.

### Configuration, binding and manifest

Config has exactly `version="1.0"`, `sequence_roles`, `metric_contexts`,
`plddt_profiles`. The first two dictionaries must cover every CSV artifact ID:

- `sequence_roles[id]`: ordered `target`/`candidate` roles for the slash-delimited
  CSV sequence chains, including at least one candidate.
- `metric_contexts[id]`: explicit existing-schema contexts for all five columns
  `mpnn`, `plddt`, `i_ptm`, `i_pae`, `rmsd`.
- `plddt_profiles[id]`: optional entry per CSV/Boltz artifact, exactly `profile`,
  `producer_name`, `producer_version`. Name/version must match the declared
  producer. Supported profiles are `plddt_0_1_to_0_100_v1` (multiply by 100) and
  `plddt_0_100_v1` (retain scale). An empty dictionary means no normalization.

`bindings` is a nonempty list. Each candidate binding has exactly `candidate_id`,
`source_run_id`, `csv_artifact`, `design`, `n`, `target_id`, `conformer_id`, `pdb`,
`boltz`, `boltz_missing_reason`. Target/conformer IDs are nonempty strings or null.
Candidate IDs must be unique. `design`/`n` select exact digit strings in the named
CSV: no integer coercion, prefix matching or inference from filenames. CSV columns
`design`, `n`, `seq` are mandatory; headers must be unique. Every data row must
have exactly one binding, and repeated design/n pairs in a CSV are errors.
Reordered columns, quoted fields and multiline values are supported. CSV raw
values, original column order, physical start/end lines, logical record number and
raw record (including embedded CRLF) are retained.

Each `pdb` binding has exactly `artifact_id`, `model_id`, `residue_map`, `chains`.
The selected PDB model and current default-altloc-A canonical map must match
exactly. `chains` follows the CSV sequence order; each entry has exactly
`sequence_index` (zero-based), `chain_id`, `segment`, `role`, `entries`. `entries`
uses the existing explicit `validate_sequence_mapping` contract (one-based
sequence position, canonical residue index, reason). Version 1 requires all
positions matched, no reused residues, and every PDB residue mapped as polymer
ATOM. It does not align sequences, repair maps, accept HETATM or infer roles.
The CSV PDB's run/sample must match `source_run_id`/`n`.

`boltz` lists zero or more explicit prediction bindings with exactly
`artifact_id`, `source_run_id`, `sample_id`, `pdb`, `chain_key_map`. The JSON and PDB
registry run/sample identities must agree with this binding. Boltz sample IDs
are independent of CSV `n`. Duplicate JSON binding or run/sample within a
candidate is rejected. `chain_key_map` bijectively maps JSON string chain keys to
all zero-based CSV sequence indices. Every `pair_chains_iptm` key and partner must
be present in that map. A missing run is represented by `boltz=[]` and a nonempty
`boltz_missing_reason`; a listed but missing JSON is fatal. When predictions are
listed, the missing reason must be null.

The existing run manifest schema is used without extension. The exact
`manifest.config["notebook_output_adapter"]` value must be:

```python
{"config": config,
 "artifacts_sha256": hash_config(artifacts),
 "bindings_sha256": hash_config(bindings)}
```

The manifest config hash must validate. Each artifact must match exactly one
canonical absolute input path/hash entry; multiple explicit artifact IDs for the
same file share that entry. All inputs are hashed again before return. Finalize
manifest outputs and other metadata before import: the audit records
`hash_config(manifest)`, not a later manifest serialization's byte hash.

### Raw evidence, origin quarantine and diagnostics

Metric names are namespaced as `artifact_id:/path`, using JSON Pointer escaping
(`~0`, `~1`). CSV pointers name columns. Boltz JSON containers and every nested
leaf/array element are preserved; directed pair values remain separate, never
averaged. Unknown fields remain raw-only. Missing known columns/top-level fields
produce explicit null/reason records. JSON duplicate keys, malformed objects,
bare NaN/Infinity and numeric overflow are fatal. String `"nan"`, JSON null and
absent fields retain their different raw states and reasons.

Without an explicit matching profile, pLDDT has `value=null`, `scale=null` and
`missing_reason="plddt_profile_not_supplied"`; its raw value survives. Out-of-range
values are unavailable rather than clipped. CSV RMSD is always raw-only because
atom selection/alignment semantics are not verified. The adapter does not replace
or reinterpret the existing dl_binder monomer RMSD quarantine. Contexts remain
separate; monomer-context evidence from a complex prediction is not independent
monomer inference. Boltz `confidence_score` is a supplied model confidence field,
not a new aggregate or measured affinity, specificity, uptake or biological success.

The reserved `__notebook_import__` raw-object metric stores the binding and hash,
CSV record, per-field source hash and locator, original name, producer metadata,
notebook reference and verification status, declared origin/fallback, transform
profile, PDB/map audit, consumed artifacts, config/hash, exact manifest hash and
missing Boltz reason. Extended provenance stays inside the existing schema.
`sequence_hash` hashes the exact CSV candidate-role sequences joined by `/`.

Candidate origin is conservative across all bound CSV/JSON/PDB artifacts:
explicit conflict, design+demo, or design with `fallback_used=true` becomes
`origin_conflict`; otherwise unknown wins over demo, and demo over design.
Only design enters `result.candidates`. Other origins enter `result.quarantined`;
all numeric values become null with `category="quarantined_origin"`. Raw fields,
previous status/reason, and declared origin remain in the audit. Filtering must
use the design list: the legacy filter has no origin policy and cannot stop a
caller deliberately passing quarantined records with empty rules or missing=include.

Nonfatal missing/raw-only/out-of-range/quarantined fields produce warning
`diagnostics` with candidate, artifact and field locator. Fatal contract, parse,
hash, chain-role, map and identity errors raise `NotebookImportError` with the
first explicit error diagnostic. There is no partial candidate return or adapter
output to roll back. Local consistency cannot independently establish producer
history, biological identity, undetected caller mislabeling, or actual fallback
execution. The fallback flag is an explicit attestation, not a notebook-text heuristic.

### Runnable synthetic example

From the project root, run with `PYTHONPATH=src:tests python3 -B`. The helper is
fixture scaffolding, not a public library API; production callers supply their
own explicit records. It reads only the six listed synthetic fixture files and
never executes even the synthetic notebook. The real notebook is not read.

```python
from pathlib import Path
from test_notebook_output_adapter import synthetic_contract
from structure_audit import import_notebook_outputs, filter_candidates
from structure_audit.provenance import (
    create_run_directory, make_manifest, write_json_new, write_manifest,
)

root = Path.cwd()
args = synthetic_contract(root / "tests/fixtures/notebook_outputs")
run = create_run_directory(root / "work/notebook_example", "synthetic")
args["manifest"] = make_manifest(
    run, args["manifest"]["config"],
    [item["path"] for item in args["manifest"]["input_files"]],
    project_root=root, supplied_models=args["manifest"]["supplied_models"],
    output_paths=[str(run / name) for name in ("result.json", "manifest.json")],
    warnings=["Synthetic bookkeeping example only; no inference"],
)
result = import_notebook_outputs(**args)
write_json_new(run / "result.json", result.to_dict())
write_manifest(run / "manifest.json", args["manifest"])
decisions = filter_candidates(result.candidates, [
    {"context": "complex", "name": "csv:/plddt", "min": 90},
])
assert [d["accepted"] for d in decisions] == [True, False]
```

Result: two design candidates; the first retains two distinct Boltz samples,
the second explicitly records no generated Boltz output. CSV pLDDT raw `"0.913"`
becomes 91.3 only through its explicit synthetic profile. Directed values 0.4 and
0.6 remain distinct. This is an import/regression fixture, not protein evidence.

## Check/report bridge (contract 1.0)

`build_check_report(*, evidence_batches, check_records, bindings, manifests, config)`
returns `CheckReport`; `.to_dict()` produces the separate `check_report` schema.
`CheckReportError(ValueError)` carries `.diagnostics` for invalid global contracts.
All three are exported from `structure_audit` and `structure_audit.check_report_bridge`.
The bridge reads explicit local PDB references to verify identity/maps. It does not
execute checks, invoke adapters, rerun inference, write files, execute a notebook,
fetch resources or discover files. Existing evidence/manifest schemas and all old
adapter/check/filter/reporting APIs are unchanged.

### Explicit inputs

All contracts are JSON data, except existing concrete CandidateEvidence and
CheckResult objects may appear where their serialized dictionaries are accepted.
No dynamic serialization hooks, executable module names, shell commands, callables
or external loaders are configured. Unexpected fields are rejected.

`evidence_batches` is a nonempty list. Each batch has exactly:

- `batch_id`: unique nonempty string.
- `adapter`: `dl_binder_output_adapter` or `notebook_output_adapter`.
- `adapter_version`: `1.0`.
- `manifest_id`: key of the source import manifest in `manifests`.
- `candidates`, `quarantined`: dictionaries mapping globally unique `evidence_id`
  strings to CandidateEvidence objects/dictionaries. For notebook imports include
  both result lists; do not flatten quarantine into the candidate list.
- `diagnostics`: the original adapter diagnostics list (empty when none).

A candidate ID is scoped to the exact source import manifest hash. Equal names
in different source runs remain separate, with distinct evidence IDs. Duplicate
IDs within the same source manifest are rejected. Entire original records,
including nested metrics, null/NaN tokens, field provenance, notebook cell
references, prediction contexts, warnings and quarantine reasons are retained.
The bridge cannot detect a caller omitting evidence before supplying a batch.

`bindings` is an explicit list, with at least one binding per evidence. Each has
exactly `binding_id`, `evidence_id`, `artifact`, `prediction_context`,
`origin_declaration`, `checks`. No score/name/sequence/hash-only join is performed;
sharing PDB bytes does not merge candidates or Boltz samples. Bind only the
artifacts intentionally in scope; the bridge does not choose a representative.

`artifact` has exactly `artifact_id`, `path`, `sha256`, `model_id`, `source_run_id`,
`sample_id`, `residue_map`, `residue_map_sha256`, `chain_roles`. Path is canonical,
absolute and local. The map/hash must equal the adapter's default-altloc-A table
and the explicitly parsed model. Ordered roles use `chain_id`, `segment`, `role`.
For notebook outputs use the exact PDB artifact ID/run/sample and roles in the
adapter audit. For dl_binder use `artifact_id="prediction_pdb"` and null upstream
`source_run_id`/`sample_id`, which that adapter does not attest. Import manifest
run ID is separate and always retained.

`prediction_context` is `monomer`, `complex`, `counter_screen`, or `unassigned`.
For dl_binder it must equal prediction_mode; bound Boltz PDBs require `complex`.
Other notebook PDB contexts are explicit caller declarations, not inferred from
individual metric contexts. Existing monomer-context metrics within complex
predictions never become independent monomer predictions.

`origin_declaration` is null or exactly `origin`, `reason` with a nonempty reason.
Origins are `design`, `demo`, `unknown`, `origin_conflict`. Notebook source origin
is authoritative for routing: any conflicting declaration becomes origin_conflict.
The dl_binder adapter has no origin field: absent declaration yields unknown;
an explicit declaration is recorded as caller-supplied, never independently
verified. Different declarations for one evidence ID conflict. Quarantined group
membership or quarantined_origin metrics cannot be promoted to design.

Each entry in `checks` has exactly `check_id`, `check`, `check_version`,
`configuration`, `config_sha256`, `record_id`, `not_run_reason`.
Check IDs are globally unique; supported names are only
`structure_integrity_check` and `coarse_steric_clash_check`. Version 1.0 is
supported. Configuration must include the complete effective fields documented
under Quality checks (no omitted defaults); its canonical hash is required.
Expected residue identities, positive distances/counts, altloc and clash scope
are type-checked without executing a check. `record_id` is a nonempty string or
null. `not_run_reason` is nonempty only when record_id is null.

`check_records` maps record IDs to exactly `manifest_id`, `status`, `reason`,
`result`. Completed pass/warn/fail records require an existing CheckResult or its
dictionary and null reason; messages remain in the result. Missing/not_run/error/
unsupported states require null result and a nonempty reason. A declared record
ID absent from this dictionary becomes missing. Each supplied record must have
exactly one binding; unreferenced or reused records are a contract error. To
intentionally associate equal results with multiple candidates, supply distinct
explicit records. The bridge validates supplied check identity/provenance, not
its numerical truth. Supplied metrics are never recomputed or calibrated.

`config` has exactly `version="1.0"`, `bridge_manifest_id`, `allowed_input_roots`.
Input roots must be explicitly supplied existing canonical absolute directories;
no directory scan occurs. Artifact paths must be beneath these roots. Patterns,
relative paths, `..` traversal and symlink aliases/escapes are rejected before
artifact reads. No configurable Python import, shell, URL or discovery facility
exists. Config only describes data and the fixed check identities.

### Manifest binding

`manifests` is a dictionary of existing schema-1.0 run manifests keyed by explicit
IDs. Supply source import manifests, source check manifests, and a separate bridge
manifest. All config hashes and UTC timestamps are validated; run/output paths
must be canonical with outputs confined to the corresponding run directory.
No source manifest is changed. Each bound PDB must match exactly one path/hash
entry in its import and supplied check manifests. Distinct import/check/bridge
run identities remain separate.

The bridge manifest's `config.check_report_bridge` must contain exactly:

- `config`: the bridge config above.
- `evidence_batches_sha256`: `hash_config` of the serialized batches.
- `check_records_sha256`: `hash_config` of the serialized records.
- `bindings_sha256`: `hash_config(bindings)`.
- `source_manifests_sha256`: `hash_config` of all manifest entries except the
  bridge manifest, preserving their explicit registry keys.

Finalize the bridge manifest before building. The report stores
`hash_config(bridge_manifest)`, not the byte hash of a later JSON serialization.
Artifact hashes are rechecked before return. Original CSV/SC/JSON/notebook source
files are not reopened: their evidence provenance is preserved as a supplied
snapshot. Only explicit bound structure bytes/maps are locally reverified.

### Report, status and error behavior

The versioned report contains `candidate_reports`, `audit`, `bindings`,
`diagnostics`, and `snapshots`. Snapshots preserve all evidence batches, check
records, source/bridge manifests and bindings. Candidate entries refer to exact
evidence IDs/hashes; metric references use the original list index plus name and
context, avoiding lossy flattening or renaming.

Only design evidence enters candidate_reports. Demo/unknown/conflicting or
quarantined evidence remains visible under `audit.quarantined_evidence`.
Raw-only, missing and quarantined metrics have separate `audit.metrics` references
and retain their original values/reasons in snapshots. Even on a design candidate,
monomer RMSD unsupported_semantics never enters the clean metric reference list.
A geometrical pass does not lift an origin or metric quarantine.

Each binding carries candidate/evidence IDs, bridge/import/source run references,
expected artifact/map hash, declared producer/model/checkpoint/seed, prediction
context, origin, identity status/reason and check rows. These parent fields apply
to every child check row. Declared producer metadata remains present when identity
fails, but is not certified by the bridge. Each check row preserves record ID,
expected `check_version`, configuration/hash, `observed_check_version`,
`observed_config_sha256`, `result_sha256`, raw/bridge status, source check manifest,
check-specific residue-map hash and verification state. Different configured
altlocs get separate map hashes; they never overwrite the adapter map hash.

Statuses are independent:

- pass/warn/fail retain the supplied completed result when identity/config match.
- missing means an expected result was not supplied; not_run requires an explicit
  caller reason. Neither means zero, pass or a successful evaluation.
- error includes a supplied check error or a local association/provenance failure.
- unsupported includes an unsupported check version or structure format.

Missing or stale PDBs, wrong chain/sample/model/map and malformed supplied check
results remain unresolved/error audit records. Unaffected evidence and checks
remain in the same report. Original check status and raw payload survive; a stale
input cannot leave its previously supplied pass as the bridge status. Late file
changes invalidate every affected binding. Global malformed contracts, duplicate
identities, unsafe config/paths or manifest-attestation failures instead raise
CheckReportError with no normal or partial report and no files written.

Export is caller-controlled through existing `create_run_directory`,
`write_json_new`, `write_manifest` functions. They retain exclusive-write behavior;
bridge build has no writer or subprocess side effect. A completed report/export
is bookkeeping completion, not a candidate success state. This bridge computes
no final score, affinity, specificity, uptake, delivery or biological-success
result. PoseBusters is only an architectural reference for modular checks and
reporting, not a protein-protein validator or a runtime dependency.

### Synthetic example

The test helper `bridge_fixture(root)` creates only explicitly named synthetic
fixtures in an empty, caller-created local directory and computes the existing
geometric checks there; it never runs a notebook or model. It is fixture
scaffolding, not a public library API. With `PYTHONPATH=src:tests`, import
`bridge_fixture` from `test_check_report_bridge`, build the contract in a temporary
directory, then pass its dictionary as keyword arguments to `build_check_report`.

The base fixture yields three design evidence entries (two notebook candidates
and one explicitly declared dl_binder candidate), four artifact bindings and eight
independent check rows: four integrity warnings and four clash passes. The first
notebook candidate retains two separate Boltz samples. All results are synthetic
format/geometry bookkeeping, not evidence for a biological target. Tests also
exercise all seven states, whole-record origin quarantine, actual monomer RMSD
quarantine and an actual geometric fail beside a preserved integrity pass.


## Manifest, report and schema APIs

Schemas: `src/structure_audit/schemas/run_manifest.schema.json` and
`candidate_evidence.schema.json`, JSON Schema draft 2020-12. Only JSON serialization
is implemented. `validation.validate_named(data, name)` validates the exact subset
used by these schemas; it is not a general JSON Schema engine. Unknown schema
keywords raise errors. Serialization rejects non-JSON objects and non-finite values.

`hash_file(path)` hashes bytes with SHA-256. `hash_config(config)` hashes sorted,
compact UTF-8 JSON (list order preserved; numeric spellings/types are not coerced).
`sequence_hash(text)` hashes exact supplied text. `create_run_directory(root,
run_id=None)` exclusively allocates `<root>/<run_id>/vNNNN`. If unspecified, ID
combines UTC timestamp and UUID. Repeated IDs allocate another version atomically.
Only safe run ID characters are permitted and symlink run parents are rejected.
Caller-supplied output roots are trusted; hostile concurrent filesystem mutation
is outside this local utility's threat model.

`make_manifest(run_dir, config, input_files, project_root=..., seed=None,
supplied_models=None, output_paths=None, status="completed", warnings=None)`
captures UTC timestamp, git commit/dirty flag (only for the explicitly supplied
project root), input hashes, config/hash, supplied upstream model IDs/seeds,
outputs, status, warnings and package version. A project without `.git` records
null git fields and a warning; no repository is initialized. Seed capture records
upstream provenance only and does not change global RNG state.

`write_manifest(path, manifest)` validates schema, config hash, UTC timestamp and
output containment, then writes exclusively. It does not recompute model results.
`write_json_new(path, data)` supports exclusive candidate/decision JSON export.

`audit_supplied_structure(input_path, output_root, config, project_root=...,
run_id=None)` runs both checks and writes the manifest, checks JSON and residue CSV.
The requested config is hashed; effective check defaults are also recorded in each
check result, alongside versions. Source hash consistency is checked between
parsing and writing. Check status is distinct from run status: successful report
generation is `completed` even when a check fails. Output exceptions leave a
`failure.json` marker in the newly allocated directory; an output failure may
leave partial files and is never relabeled as completed. Parse/config errors may
be raised before output allocation. CLI exit code is 0 for a completed report,
including warned/failed checks, and nonzero for execution/format errors.

This layer deliberately does not execute notebook cells, import inference
libraries, discover arbitrary result folders, fetch demos, select a "best" design,
estimate affinities, simulate multivalent binding or modify external projects.
