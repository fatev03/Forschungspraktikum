# Computational Structural-Bioinformatics Handoff

## Current patch status — receptor MSA audit — 2026-09-16

Implemented only the independent `receptor_msa_audit_adapter`, synthetic tests,
and this handoff update. Public names are available directly from
`structure_audit.receptor_msa_audit_adapter`:

```python
from structure_audit.receptor_msa_audit_adapter import (
    audit_receptor_msa, ReceptorMSAAuditResult, ReceptorMSAAuditError,
)
result = audit_receptor_msa(
    artifact=artifact, binding=binding, manifest=manifest, config=config,
)
audit = result.to_dict()  # Detached strict JSON; no output file is written.
```

The complete exact-field contract is in the module docstring. Package `__init__`
exports, `docs/API.md`, all Paket 1 schemas/APIs, existing adapters and tests,
CheckReport bridge, notebook and external repositories are unchanged. No network,
inference, Pairformer/PyTorch/third-party imports, search, MMseqs2, hhfilter,
pairing, subsampling/cropping, dependency download, subprocess or environment
mutation is performed by the adapter. No CandidateEvidence, CheckReport, ranking,
affinity, coevolution or biological-success result is produced. No Pairformer TXT,
pickle, tensor, embedding or other model-output import exists.

### Explicit inputs and parsing

One `artifact` object identifies one uncompressed local receptor alignment by
canonical absolute path, byte SHA-256, artifact/source-run IDs and declared format.
Producer and generation details are inert, caller-supplied declarations, or null
with explicit missing reasons. Paths must remain under explicit allowed roots;
patterns, relative paths, symlink aliases/escapes, directories and suffix/format
conflicts are errors. No artifact registry scan or secondary data-file read occurs.

Explicit versioned profiles are `aligned_fasta_v1` (.fa/.fas/.fasta) and
`a3m_match_columns_v1` (.a3m). FASTA rejects lowercase, dot and star. A3M removes
only standard-AA lowercase insertions and dot insertion padding in non-query
rows, with per-token transformation records and insertion anchors. Every star,
query insertion, lowercase unknown and unsupported token is fatal. No automatic
uppercase conversion occurs. Uppercase X/B/Z/J/U/O are only accepted through an
explicit unknown-token list and retain policy; their original identities survive.

Headers retain complete descriptions and unique explicit record IDs. Query is
looked up by supplied `query_record_id`, never assumed to be first. UTF-8 and
LF/CRLF, wrapped sequence lines and missing final newline are supported; blank
lines, sequence whitespace, control characters, comments and empty records are
not silently repaired. Raw fragments/line endings, record order, tokens, physical
locators and raw-to-parsed-to-query-sequence positions are retained. A3M raw
offsets are row-local, not shared alignment columns. Parsed rows must be rectangular.

### Query, map and provenance

Binding requires receptor target/chain/segment/model identity, explicit uppercase
AA20 query sequence/hash, complete column map, complete sequence map, canonical
default-altloc-A residue-map snapshot and their hashes. Sequence positions are
one-based; raw row/token, parsed column and canonical residue indices are zero-based;
physical line/character locations are one-based. These bases are explicit config.
Author numbering, insertion codes, label identities and map source references
remain unchanged. Query-gap columns have null sequence position with `query_gap`.
Missing structural positions require explicit null indices and nonempty reasons;
wrong/reused/out-of-range indices, chain/model conflicts or residue mismatches fail.

Only the alignment data file is opened. The existing packaged run-manifest schema
is read by its validator. Structural source bytes are NOT reopened: map status is
`supplied_map_consistency_verified`, not structure verification. The map source's
artifact/hash/run/model reference is retained as a supplied declaration. No fake
Structure, automatic alignment, structure loading or residue-map repair is used.

The existing manifest must validate schema, UTC timestamp, canonical run/output
paths and config hash. Its `config.receptor_msa_audit_adapter` must equal exactly
`{config, artifact_sha256: hash_config(artifact), binding_sha256: hash_config(binding)}`.
The alignment must match exactly one manifest input path/hash. Other inputs are
preserved but not opened. Caller owns manifest creation; no make_manifest/git or
output allocation occurs. The audit retains all snapshots, exact config/profile,
query/map/binding hashes, input byte hash, import/source run IDs and canonical
`hash_config(manifest)`. Input bytes are hashed before parsing, and path/hash are
rechecked after assembling and validating the result, immediately before return.

### Statistics and unavailable values

Input depth, unique-row count and duplicate count include every input record;
duplicates use exact parsed token strings, preserving distinctions among unknown
symbols. Duplicate count is depth minus unique count. Statistics apply explicit
query inclusion, then `keep`, `count_once`, or `error` duplicate policy. `error`
rejects any input duplicates, including duplicates of an excluded query.
`count_once` uses the first eligible raw row per group as statistical representative;
all raw records/group membership remain in the audit. Statistical contribution
count is separately labeled; no filtered/subsampled alignment file is produced.

Summary contains pooled AA/gap/unknown counts and fractions. Each column contains
counts, configured gap/unknown fractions, AA20 frequencies and Shannon entropy.
Denominators, alphabet, log base (2 or e), query inclusion and duplicate policy
are mandatory config; V1 explicitly requires no pseudocount and excludes gaps and
unknowns from frequency/entropy. No implicit defaults or sequence weighting.
Row query coverage is valid AA at query-residue columns divided by query length.
Summary query coverage counts positions with at least one contributing valid AA.
This is separate from structure-map coverage and does not certify alignment quality.

All-gap/no-valid-AA columns have null derived metrics with `all_gap` or
`no_valid_amino_acids`, including fractions; raw counts remain. No contributing
rows yields `no_contributing_rows`; a zero pooled denominator yields
`zero_denominator`. Valid homogeneous columns have entropy zero. Summary fractions
pool all contributing cells, including unavailable columns; no pooled entropy or
composite score is computed. Depth/unique counts are not N_eff, effective sequence
number, evolutionary population, or evidence of natural-homolog quality.

### Result and failure behavior

`ReceptorMSAAuditResult` has `summary`, `rows`, `columns`, `diagnostics`, `audit`;
it is not a candidate iterable. Strict plain JSON is checked before copying input,
including rejecting custom object/subclass hooks and non-finite/cyclic data.
`to_dict()` yields detached finite JSON. Import changes neither inputs nor files.

Warnings: `incomplete_provenance`, `missing_residue_mapping`, `duplicate_rows`,
`unavailable_column_metrics`. Expected absence is explicit null/reason, not success
on invalid data. Fatal exceptions carry `.diagnostics` with severity/code/message,
artifact/binding IDs and available row/line/character/column/sequence/map locators.
Codes include `invalid_contract`, `unsupported_config`, `parsing_profile_mismatch`,
`unsafe_path`, `unsupported_format`, `manifest_contract`, `manifest_artifact_mismatch`,
`artifact_read_error`, `stale_artifact_hash`, `alignment_parse_error`, `invalid_token`,
`duplicate_identity`, `duplicate_policy_violation`, `ragged_alignment`,
`query_mismatch`, `chain_binding`, `residue_map_mismatch`,
`sequence_mapping_mismatch`, `column_mapping_mismatch`. No partial result/rows/
metrics are attached to exceptions, including a late token error or file mutation.

### Verification and synthetic example

Pre-change baseline: **204 tests passed**. Targeted suite: **47 tests passed**.
Full regression: **251 tests passed** (204 existing + 47 new).
Commands below set only interpreter module-search paths, not environment variables:

```sh
python3 -B -c 'import sys, unittest; sys.path[:0] = ["src", "tests"]; result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover("tests", pattern="test_receptor_msa_audit_adapter.py")); sys.exit(not result.wasSuccessful())'
python3 -B -c 'import sys, unittest; sys.path[:0] = ["src", "tests"]; result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover("tests")); sys.exit(not result.wasSuccessful())'
```

`synthetic_msa_contract(root)` in the new test module creates exactly one toy FASTA
in a caller-created temporary directory and supplies an in-memory map/manifest.
It is test scaffolding, not public API. Its five rows have width four; query is
second, depth=5, unique=4, duplicates=1, query length=3 and coverage=1.0.
The first column A,A,C,-,X gives gap=0.2, unknown=0.2, valid-AA frequencies
A=2/3 and C=1/3, entropy=0.9182958340544896 bits. The next column is all-gap;
derived metrics are null with `all_gap`. Four warnings preserve two unavailable
source declarations, duplicate rows and the all-gap column. This is bookkeeping
validation, not biological evidence.

Tests cover FASTA/A3M raw identities, insertions/padding, non-first query, explicit
mapping/bases, missing residues, duplicate policies, both denominator choices/log
bases, unknown tokens, null/zero boundaries, stale hashes, late failure, invalid
contracts and paths, deterministic detached JSON and caller immutability. A guard
loads the new module afresh and audits under blocked writes, network, subprocess,
discovery, environment mutation and third-party imports; reads are restricted to
the module source, packaged manifest schema and explicit alignment artifact.

Known limits: one receptor/chain binding and one alignment; full query identity
requires AA20; conservative FASTA/A3M profiles only; no A2M/Stockholm/general parser.
Map/source/producer truth and biological identity remain supplied, not independently
proven. Raw per-token audit is held in memory without a large-file streaming mode.
Trusted-root before/after checks do not defend against hostile transient filesystem
replacement. No downstream integration, persistence/export or real-target validation.

Exact next implementation task: audit one explicitly user-supplied local receptor
FASTA/A3M artifact with its complete query/map/binding/config/manifest contract,
read-only, and report descriptive statistics and identity diagnostics without
inference, source changes or downstream evidence/report integration.

## Previous patch record — supplied conformer outputs — 2026-09-16

The receptor-MSA status above supersedes the next task in this historical record;
the conformer adapter and all Paket 1 contracts remain unchanged.

Implemented only `supplied_conformer_output_adapter` as an independent read-only
import module. New public names are available directly from
`structure_audit.supplied_conformer_output_adapter`:

```python
from structure_audit.supplied_conformer_output_adapter import (
    import_supplied_conformers, ConformerImportResult, ConformerImportError,
)
result = import_supplied_conformers(
    artifacts=artifacts, bindings=bindings, manifest=manifest, config=config,
)
audit = result.to_dict()  # Detached strict JSON value; does not write a file.
```

The package's existing `__init__` exports, `docs/API.md`, all three Paket 1 schemas,
the CheckReport bridge, existing adapters, filters and check APIs are unchanged.
No CandidateEvidence, candidate sequence, pLDDT/B-factor metric, MSA function,
Pairformer TXT import or new report integration is produced. The adapter neither
runs checks nor exports files. It uses the Python standard library and existing
structure/map/hash/manifest-validation utilities. No upstream imports, network,
inference, subprocess calls, dependency downloads or environment changes occur.
The notebook and external repositories were not modified or executed.

### Exact version-1 import contract

All inputs are plain JSON-compatible data, validated before copying; non-JSON
objects cannot execute custom deepcopy hooks. Unknown top-level fields in the
objects described below are rejected. The module docstring also documents the
complete input shape.

- `config` has exactly `version="1.0"`, `allowed_input_roots` (nonempty list of
  unique existing canonical absolute directories), and `altloc="A"`.
- `artifacts` is a nonempty dictionary keyed by explicit nonempty artifact IDs.
  Each value has exactly `kind` (`pdb` or `mmcif`), `path`, `sha256`,
  `source_run_id`, `producer`, `generation`, `conversion`. Suffixes are `.pdb`,
  `.cif` or `.mmcif`, consistent with kind; compressed input is unsupported.
  A file is registered once and may have several distinct model bindings.
- Paths must be exact canonical absolute paths beneath the configured roots.
  Patterns, traversal, symlink aliases/escapes, directories and missing files are
  rejected. There is no directory scan, glob, basename fallback or first/best
  model selection. All registered artifacts must be bound.
- `producer` has exactly nullable `name`, `version`, `model_id`, `checkpoint_id`,
  `seed`, plus `missing_reasons`: an object covering exactly the null fields with
  nonempty explanations. Supplied seeds are nonnegative integers. Any model/
  checkpoint/seed triple not entirely null must match `manifest.supplied_models`.
  Producer history is always `caller_supplied_not_verified`, even if known fields
  are populated and local artifact identity verifies.
- `generation` and `conversion` each have exactly `details` and `missing_reason`.
  Details are a nonempty JSON object with null reason, or null with a nonempty
  reason. These are retained as inert caller declarations, not interpreted as
  executable configuration or verified producer history. For example, callers
  may retain model variant, steps/tmax, resampling/template settings and requested
  sample counts in generation details, and source hash/tool/version/description
  in conversion details. Referenced paths/hashes inside details are NOT opened or
  independently checked. No default model settings or conversion history are
  inferred from filenames or file extensions.
- `bindings` is a nonempty list. Each entry has exactly `binding_id`,
  `artifact_id`, `ensemble_id`, `sample_id`, `target_id`, `model_id`,
  `selection_reason`, `residue_map`, `residue_map_sha256`, `chains`. Identity and
  selection-reason fields are nonempty strings. Structural `model_id` is distinct
  from producer model identity. Binding IDs, `(ensemble_id, sample_id)`,
  `(source_run_id, target_id, sample_id)` and `(artifact_id, model_id)` must each
  be unique. One ensemble must declare one target ID. Samples from different
  targets may use the same source sample label; equal bytes do not merge samples.
- `chains` lists every observed polymer ATOM chain/segment once, in observed
  order. Each entry has exactly `chain_id`, `segment`, `role="target"`, `sequence`,
  `sequence_sha256`, `entries`, `missing_reason`. Blank PDB chain IDs are preserved.
  Supply a nonnegative integer segment. Sequence/hash/entries must either all be
  null with a nonempty reason, or hold a supplied uppercase standard-AA sequence,
  its exact-text hash and existing `validate_sequence_mapping` entries, with null
  missing_reason. This is optional target-sequence verification, not assignment
  or generation of a candidate sequence.
- `entries` uses the unchanged mapping contract: one-based sequence positions,
  zero-based canonical residue indices, null indices with missing reasons.
  Wrong-chain mappings, residue reuse, invalid position coverage and sequence
  mismatches are fatal. Missing/unmapped positions and observed residues outside
  the supplied mapping are retained as partial mappings with diagnostics.

The default-altloc-A canonical map and its hash must equal those re-read for the
explicit file/model. Author numbering, insertion codes, segment boundaries,
mmCIF label identifiers, source lines, atom names and missing-backbone information
are preserved. Duplicate atom/residue identities and non-finite coordinates in a
selected model are fatal. HETATM rows remain visible but are excluded from target
sequence/chain coverage. Ambiguous altloc selection is not repaired; map warnings
remain visible. These checks validate import identity, not geometric plausibility.

The supplied manifest must satisfy the existing schema, UTC timestamp, canonical
run/output path containment and config hash. Its config must include exactly this
adapter attestation value (other manifest config namespaces remain allowed):

```python
manifest["config"]["supplied_conformer_output_adapter"] = {
    "config": config,
    "artifacts_sha256": hash_config(artifacts),
    "bindings_sha256": hash_config(bindings),
}
```

Each artifact must match exactly one manifest `input_files` path/hash entry. Extra
manifest input entries are retained but not opened. Manifest creation is caller
owned: this importer never invokes `make_manifest`, git or output allocation.
Finalize the manifest before importing; the recorded manifest SHA-256 is
`hash_config(manifest)`, not the byte hash of a later serialization. Registered
paths and hashes are checked again before returning, including after all samples
have been assembled. Caller-owned contracts and source files are not modified.

### Audit result, diagnostics and failure behavior

`ConformerImportResult` contains `samples`, `diagnostics`, `audit`. It is not
iterable as candidates. Each sample retains its explicit IDs, artifact/producer/
generation/conversion snapshot, structural model, selection reason, canonical
map/hash, chain/sequence mapping statuses, parser warnings, binding hash, import
run ID and manifest hash. The audit retains the exact config, artifacts, bindings,
manifest and limitations. Status `verified_local` means only byte/map/binding
consistency; it is not an inference, geometry, biological or candidate success.

Warnings include `sequence_not_supplied`, `partial_sequence_mapping`,
`structure_parser_warning`, `residue_scope_warning`, `incomplete_provenance`.
Diagnostics contain severity, code, message, artifact ID, binding ID and locator
(line/index/object or null). Missing producer fields retain individual reasons.

All contract, parsing, identity and file-change errors raise `ConformerImportError`
with error diagnostics and no partial result/sample list, including failures in a
late binding. Representative codes are `invalid_contract`, `unsupported_config`,
`unsafe_path`, `manifest_contract`, `manifest_artifact_mismatch`,
`manifest_producer_mismatch`, `duplicate_identity`, `target_conflict`,
`unbound_artifact`, `artifact_read_error`, `stale_artifact_hash`,
`structure_parse_error`, `unsupported_format`, `residue_map_mismatch`,
`chain_binding`, `sequence_binding`, `sequence_mismatch`,
`ambiguous_structure_identity`, `nonfinite_coordinates`.

Unpadded `MODEL 0` (and the same native `MODEL <integer>` form for other indices)
raises `native_alphaflow_model_header` with the physical line. It is never silently
fixed. A model number zero in the standard fixed-width PDB field is distinct and
remains supported by the existing reader. No renumbering is performed.

### Verification and synthetic example

Pre-change baseline: **166 tests passed**. Targeted adapter suite: **38 tests
passed**. Full regression: **204 tests passed** (all 166 existing + 38 new).

```sh
PYTHONPATH=src python3 -B -m unittest discover -s tests -p 'test_supplied_conformer_output_adapter.py' -q
PYTHONPATH=src python3 -B -m unittest discover -s tests -q
```

Tests construct minimal synthetic PDB/mmCIF fixtures in temporary directories;
no real target data or external source code is used. They cover explicit multiple
models, auth/label identities, insertion codes, blank chain/TER, default-altloc
behavior, missing atoms/mappings, unknown producer history, HETATM scope, native
headers, stale maps/bytes, wrong roles/sequences/models, duplicate IDs, unsafe
paths, manifest failures, late mutation, strict JSON and unchanged B-factor-free
maps. A guarded test blocks writes, discovery, network, subprocess, model imports,
environment mutation and check execution during import. Existing tests are
unchanged; their fixture/output writes remain confined to their temporary dirs.

For a runnable synthetic example with `PYTHONPATH=src:tests`, create an empty
temporary directory, call `synthetic_conformer_contract(root)` from
`test_supplied_conformer_output_adapter`, then pass its returned dictionary as
keyword arguments to `import_supplied_conformers`. The helper, not the importer,
writes the two explicitly named fixture files. No import output directory exists.

The example yields three separate locally verified samples: PDB model `1`, PDB
model `2`, and explicitly selected mmCIF model `9` (model `7` is not selected).
Each has two mapped glycine residues. Seven warnings survive: three model-selection
parser warnings, three incomplete-provenance warnings and one missing-backbone
scope warning. There is no CandidateEvidence or CheckReport result.

### Known limits and next task

The reader's conservative PDB/mmCIF subset is unchanged. No general mmCIF parser,
native AlphaFlow header conversion or B-factor import is provided. Only selected
models are audited; omitted artifacts/samples cannot be detected. Supplied target
IDs, generation settings, conversion history and biological sameness across
samples are not independently proven. Each map is file/model specific; no
cross-sample alignment, correspondence inference or variation metric is computed.
Roots are trusted; hostile concurrent file replacement beyond before/after path
and hash checks is outside scope. Results are in-memory JSON-compatible audit
objects without a new persistent schema or bridge integration.

Samples represent variation only among the supplied structural samples. No
equilibrium population, free-energy distribution, kinetic pathway, affinity or
biological-success claim is made.

Exact next implementation task: implement a separate read-only receptor-side MSA
quality/conservation/variability adapter using explicit supplied query/column
bindings and synthetic tests, without inference, pairing, candidate evidence or
changes to existing schemas/APIs/CheckReport. This next task is not implemented
or authorized to start by the current patch.

## Previous patch record — check/report bridge — 2026-09-16

The conformer status above supersedes the next task in the historical records
below; Paket 1 implementations and their contracts remain unchanged.

Implemented only `check_report_bridge`: `build_check_report(*, evidence_batches,
check_records, bindings, manifests, config)` returns `CheckReport`; invalid global
contracts raise `CheckReportError` with diagnostics. The new standalone report
schema preserves original CandidateEvidence, check, manifest and binding snapshots.
Existing adapters, evidence/manifest schemas, filters, checks and reporting APIs
remain unchanged. See `API.md` for the exact version-1 input/report contract.

The bridge relates explicitly supplied results; it does not run checks or models.
Explicit evidence/run/sample/PDB/model/chain-role/map bindings are verified with
source and bridge manifest hashes. Only exact PDB references beneath configured
local input roots are opened; no directory discovery, glob, basename fallback,
dynamic import or shell command configuration exists. Expected and observed check
versions/config hashes are separate. Check-specific altloc map hashes do not
replace the adapter's default-altloc-A map hash. Producer declarations are retained,
including when artifact identity fails, without becoming independently verified.

Raw values, directed/nested JSON, missing/NaN reasons, per-field provenance,
monomer/complex contexts and original quarantine records survive unchanged.
Design entries are separate from demo/unknown/origin_conflict audit entries.
The dl_binder output lacks origin: default unknown, with explicit manifest-bound
caller declarations supported. Notebook origin/quarantine cannot be upgraded.
Individual raw-only/quarantined fields remain separate even when a geometric
check passes. No candidate-level success status, final score, affinity,
specificity, uptake, delivery or biological-success result is produced.

Independent pass/warn/fail/missing/not_run/error/unsupported rows preserve other
checks and evidence. Invalid associations or stale/missing PDBs remain error audit
records; duplicate/global contract, manifest or path/config failures instead
raise with no normal/partial report. Build is read-only; optional export uses the
existing exclusive-write APIs and a new run directory. Source manifests remain
immutable. PoseBusters is an architecture-only modular reporting reference, not
a protein-protein binding validator, dependency or copied implementation.

Verification: **166 tests passed** (all 131 previous tests plus 35 bridge tests).
Commands: `PYTHONPATH=src python3 -B -m unittest discover -s tests -v` and
`PYTHONPATH=src python3 -B -m unittest discover -s tests -p 'test_check_report_bridge.py' -v`.
Synthetic/local tests cover both actual adapters and existing geometric checks,
multiple samples, seven statuses, origin conflicts and unknown origins, raw-only
and monomer sentinel quarantine, stale maps/bytes, wrong model/role/sample/context,
separate expected/observed versions/configs, mutation during build, unsafe paths,
blocked network/process/discovery/write/check execution, and exclusive report
round-trip. Notebook and all external repositories were neither modified nor run;
no network, inference, dependency download, environment change or biological data
was used.

Known limits: source evidence/check metrics and producer history are supplied
snapshots, not independently recomputed. Only bound PDB bytes/maps are reverified;
CSV/SC/JSON/notebook input files are not reopened. Caller-omitted candidates cannot
be detected. Complete adapter audit metadata and an explicit binding per evidence
are required; only existing adapter/check version 1.0 contracts are supported.
Input roots are trusted, no symlink aliases are accepted, and hostile concurrent
filesystem changes beyond before/after hash checks are outside scope. Expected
check configurations must be fully explicit; no automatic default inference.

Exact next implementation task: perform a read-only end-to-end contract audit of
one explicitly supplied local source-package-1 output bundle (adapter evidence,
check records, PDB/maps and manifests), recording identity/provenance discrepancies
without inference, source changes or biological-success claims.

## Previous patch record — notebook outputs — 2026-09-15

The current bridge status above supersedes the next task in the historical records
below; earlier adapter implementations and scientific limitations remain unchanged.

## Notebook output patch status — 2026-09-15

Implemented only `notebook_output_adapter`, using the existing CandidateEvidence,
manifest, sequence/residue-map and quality-check APIs. New public exports:
`import_notebook_outputs(*, artifacts, bindings, manifest, config)`,
`NotebookImportResult`, and `NotebookImportError`. See `API.md` for contract 1.0
and a runnable synthetic example. The existing dl_binder adapter, old tests,
schemas and filter implementations are unchanged.

Imports require explicit absolute artifact paths/hashes, source run IDs,
candidate/design/n bindings, independent Boltz sample IDs, PDB model/maps,
sequence roles and chain-key mappings. Manifest config hashes bind the complete
registry and bindings. No glob, scan, basename fallback or best-result selection
is implemented. Parsing/identity errors raise diagnostics without partial
candidate lists. The adapter writes no files and rechecks hashes before return.

Raw CSV values and physical/logical record locators, nested JSON containers and
leaves, directed chain-pair values, PDB references, per-field producer/model/seed,
notebook file/cell hashes and verification states remain in the existing schema.
The reserved `__notebook_import__` raw-object metric carries extended audit
metadata. Producer/run/origin declarations are caller supplied; local consistency
and cell source hashes do not prove upstream execution or biological identity.

`design` enters `result.candidates`; `demo`, `unknown` and `origin_conflict` enter
`result.quarantined`. Design plus demo, or design with declared fallback use,
becomes conflict. Quarantine nulls numeric values and preserves previous
missing/NaN/raw-only status and reason. Only the design list is intended for
existing filters, which do not independently enforce origins. pLDDT requires a
producer-bound scale profile; without one it remains raw-only. CSV RMSD remains
raw-only because alignment/atom semantics are not verified. Monomer and complex
contexts remain separate. No final affinity/success score or protein-protein
binding validator is added.

Verification: **131 tests passed** (all 89 pre-existing tests + 42 new notebook
adapter tests). Commands:
`PYTHONPATH=src python3 -B -m unittest discover -s tests -v` and
`PYTHONPATH=src python3 -B -m unittest discover -s tests -p 'test_notebook_output_adapter.py' -v`.
Tests cover explicit multi-sample import, schema/filter/check integration, column
reordering, multiline/CRLF records, nested/directional JSON, missing/NaN values,
all origins/fallback quarantine, duplicate identities, missing JSON, stale
hashes/cells/maps, wrong chain roles, distinct producer metadata, late failures,
strict JSON parsing, and blocked network/discovery/subprocess/write operations.
Fixtures are six synthetic local files, including a non-executable synthetic
notebook; they contain no real biological target or cell-surface data.

The real notebook was neither run nor changed. No RFdiffusion, Boltz,
dl_binder_design or other external repository was changed. No network,
inference, dependency download or environment change was used.

Known limits: v1 requires full matched polymer ATOM sequence maps at default
altloc A; HETATM, partial mappings, silent files and mmCIF artifacts are outside
this adapter contract. Metadata is artifact-producer scoped, not inferred from
mixed-producer columns. Saved notebook output text is not mined for artifacts or
fallback history. Mixed origins quarantine the entire candidate; the caller can
still bypass the intended result list using the unchanged legacy filter API.
Synthetic fixtures validate bookkeeping only, not a real model export.

Exact next implementation task: validate one explicitly supplied local notebook
output bundle against this contract, using its caller-approved CSV/JSON/PDB
bindings and producer metadata; record import discrepancies without inference,
network access or notebook/upstream changes.

## Previous patch record — dl_binder outputs — 2026-09-15

The current notebook-output status above supersedes the next task in this
historical record; its dl_binder implementation and limitations remain unchanged.

## dl_binder patch status — 2026-09-15

Implemented only the read-only `dl_binder_output_adapter` next task. The public
`import_dl_binder_sc(path, *, bindings, manifest, config, provenance)` returns
existing schema-1.0 `CandidateEvidence` objects from explicitly supplied local
AF2 `.sc` records and prediction-output PDB references. The implementation uses
only the Python standard library and existing structure/map/manifest APIs.
Existing schemas, filters and quality-check APIs are unchanged. The notebook,
RFdiffusion and dl_binder_design upstream repositories were not modified. No
inference, network access, dependency downloads or environment changes occurred.

Exact description/tag bindings, binder-first chain/segment roles, canonical
residue maps and manifest input/config hashes are validated. Reordered columns
and repeated headers are supported; duplicate or missing tags and stale or
incorrect mappings are rejected. Raw column names, tokens, ordered headers,
source lines, model/checkpoint/seed provenance and missing/non-finite states are
preserved. The reserved `__dl_binder_import__` raw-object metric carries the
extended import audit within the existing schema. See `API.md` for the complete
contract and runnable synthetic-fixture example.

Monomer and complex evidence remain separate. Complex-run binder confidence or
binder-aligned RMSD is not independent monomer inference. Both monomer-mode RMSDs
are quarantined with `value=null`, `category=unsupported_semantics` and the
upstream `binderlen=-1` mask limitation in `missing_reason`; the raw token remains
available. Complex-only monomer fields and unknown columns are also quarantined.
Existing filters treat these values as missing, including their explicit
include/exclude/error policies. No final affinity/success score is computed.

Verification on local Python 3.11.4: the pre-change suite passed 65 tests. The new
adapter suite passes 24 tests, including reordered columns, duplicate tags, NaN,
missing tags, wrong roles, monomer sentinel/RMSD boundaries, stale maps, manifest
mismatches, unknown producer metadata and no-write/no-network/no-inference
operation. Full regression: **89 tests passed** (65 existing + 24 adapter tests).
Commands: `PYTHONPATH=src python3 -B -m unittest discover -s tests -v` and
`PYTHONPATH=src python3 -B -m unittest discover -s tests -p 'test_dl_binder_output_adapter.py' -v`.

Known limits: one explicit prediction mode per import; complex outputs must have
two ordered polymer chains/segments and monomer outputs one. Map comparison uses
the existing default-altloc-A canonical table. Silent/TRB input and sequence
inference are unsupported; sequence_hash remains null with a reason. The adapter
does not prove biological target identity or that caller-bound artifacts share
an upstream run. Producer settings and snapshot IDs are caller supplied, not
independently verified. All examples/tests are synthetic, not a real campaign.

Exact next implementation task: validate this adapter against one explicitly
supplied real dl_binder_design `.sc`/prediction-PDB pair, its canonical residue-map
and documented run metadata; record discrepancies as regression fixtures without
running inference or changing upstream code.

## Previous patch record — 2026-09-14

The sections below are historical context; the current status above supersedes
their proposed next stage and next implementation task.

## Current patch status — 2026-09-14

The current task is an **offline input/output bookkeeping and audit layer** for
user-supplied structures and model outputs. `src/structure_audit` is implemented
with Python's standard library; it has no model/inference integration. The
notebook and its saved outputs are unchanged. No dependencies/weights were
downloaded, no environment was changed, and no external repository was copied or
modified. Historical literature observations below are reference/provenance,
not instructions to execute upstream code or claims reverified by this patch.

New APIs cover strict PDB/mmCIF atom-table reading, canonical residue records,
explicit supplied-sequence mapping, manifest/hash/versioned directories,
candidate evidence and explicit CSV/JSON adapters, independent configurable
filters, and two checks: `structure_integrity_check` and
`coarse_steric_clash_check`. Both are labeled **format/geometric plausibility
only**, with metrics, configuration, status, messages and versioned provenance.
See `API.md` and the root `README.md` for executable examples.

The project root has no `.git`; manifests record unknown git provenance with a
warning. The versioned run helper never overwrites prior result files. Supplied
model/checkpoint IDs and seeds are metadata only; they are not downloaded or run.

Verification: `PYTHONPATH=src python3 -B -m unittest discover -s tests -v`:
**65 tests passed** on local Python 3.11.4. PDB and mmCIF CLI fixture smoke tests
both generated manifests, check reports and residue maps successfully.
The suite covers insertion codes, missing atoms/residues, multiple chains/models,
alternate locations, duplicate IDs, TER/geometric breaks, deliberate clashes,
strict mmCIF errors, explicit mapping, raw/missing metric values, filtering,
SHA-256, manifest validation and concurrent versioned-directory allocation.
Detailed verification is also recorded in the delivered patch review;
the synthetic fixtures are not evidence for a real protein.

Known limits: mmCIF supports a conservative documented atom-table subset;
ambiguous identities/formats raise **unsupported / needs external dependency**.
No silent parser fallback or automatic alignment. Numbering gaps alone are not
proof of missing residues. HETATM residues are preserved but excluded from polymer
checks. Clash counts do not model covalent topology/radii and are not binding,
affinity or function predictions. Full residue completeness needs an explicit
expected inventory; missing context yields warnings rather than success.

Next stage (not performed): inspect references in the numbered order appended to
`literature_evidence_matrix.md`. Start with BindCraft, `dl_binder_design`, PXDesign
and PoseBusters for output-field definitions and validation boundaries; then
review ensemble/conformer identity sources. Inspect the listed PDF first and only
then the paired repository's README/output-schema code, read-only. The later
sequence/generation and multivalent references are provenance context, not an
authorization to add inference or biological predictions. No PDFs or external
source contents were opened for this patch; only their filenames/directories
were listed. Existing provenance summaries are retained below.

## 1. Project purpose

This is a new, separate computational structural-bioinformatics project. Its scope is candidate-protein structural analysis, sequence/design outputs, geometry and confidence checks, and abstract multivalent-binding simulations. It is **not** the `apex` repository and is not the Cell Surface Universe project. Treat structural predictions and all model scores as computational evidence only, never as experimental affinity, specificity, expression, internalization, or delivery evidence.

## 2. Repository inventory and apparent pipeline stages

The working materials are `/Users/fatihyigitevyapan/Desktop/Forschungspraktikum/diffusion_fixed.ipynb` and `/Users/fatihyigitevyapan/Desktop/Forschungspraktikum/literature/`. The notebook is Colab-oriented (20 cells): RFdiffusion backbone generation; ProteinMPNN sequence design; AlphaFold validation; optional Boltz-2 complex prediction; interface/geometry calculations; effective-concentration/avidity and multivalent-selectivity calculations. It uses mutable installs and contains demo fallbacks.

## 3. Literature/repository sources inspected

Inspected PDFs/source snapshots include MSA Pairformer, RFdiffusion, BindCraft, PXDesign, AlphaFlow/ESMFlow, PathFold, PoseBusters, MVsim, valentBind, Mosaic, `dl_binder_design`, LASErMPNN/NISE, and papers on linker-dependent avidity, kinetic superselectivity, kinetic proofreading, TCR modeling, and multivalent receptor availability. `s41467-023-37139-y` is a chemistry-automation project called AlphaFlow; it is unrelated to the protein-ensemble AlphaFlow/ESMFlow work.

## 4. Most relevant transferable components

- MSA Pairformer: receptor-side MSA embeddings/contact features.
- RFdiffusion + ProteinMPNN: candidate backbone and sequence generation inputs/outputs.
- BindCraft/PXDesign/`dl_binder_design`: provenance-rich candidate tables and orthogonal structure-confidence/geometry filters.
- AlphaFlow/ESMFlow: target conformational ensembles.
- PoseBusters: protein-small-molecule pose validity only.
- valentBind/MVsim: abstract equilibrium and kinetic multivalent models.

## 5. Key assumptions, missing inputs, and ambiguities

Missing: target structures/sequences, chain and residue-index conventions, interface/hotspot definitions, candidate sequence set, intended output schema, benchmark set, and receptor-density/monovalent-affinity/linker parameters. It is unclear which notebook cells are required versus demonstrations, whether the objective is protein-protein or protein-small-molecule binding, and which score(s) may drive ranking. MSA Pairformer can support receptor-side features; newly designed candidates should not be assigned natural coevolution without evidence.

## 6. Top five risks or misuse concerns

1. Treating pLDDT, ipTM, PAE, docking, or energy scores as measured affinity/specificity.
2. Converting uncertain structural outputs into delivery, internalization, or expression claims.
3. Reusing demo inputs/fallback paths as real project data.
4. Mixing the unrelated chemistry-automation AlphaFlow with protein-ensemble AlphaFlow/ESMFlow.
5. Running large model/environment downloads before documenting dependencies, compute, expected artifacts, and version provenance.

## 7. Verified observations versus tentative interpretations

Verified: the notebook stages above; listed local PDFs/snapshots; AlphaFlow naming collision; source README-described inputs/outputs; no root-level `external_projects/` directory. Tentative: suitability of any upstream tool for this workflow, score thresholds, and whether ensemble or multivalent modules should be included. Local binary-PDF text extraction was unavailable; paper summaries were cross-checked with matching primary records and supplied READMEs.

## 8. Previous recommended task (superseded by the current patch)

The previous recommendation was a standalone input/output and provenance schema.
The current patch now supplies this schema and a tested offline implementation.
The next task is the read-only reference review described above, followed by
validation against explicitly supplied real artifacts if separately requested.

## 9. Minimal files needed in the next chat

- `docs/HANDOFF.md`
- `docs/literature_evidence_matrix.md`
- Root file list for `Forschungspraktikum`
- Directory listings only for the actual project’s `src/`, `tests/`, `configs/`, and `docs/` if they exist
- `README.md` only if it exists and is needed
- `diffusion_fixed.ipynb` only when notebook-specific review is requested

## 10. Files that should NOT be reloaded unless specifically needed

Do not preload PDFs, large PDB/trajectory folders, model weights, full upstream source snapshots, generated results, or unrelated `2026-07-28_Cell_Surface_Universe/`. Do not reload the unrelated `apex` repository.
