"""Offline utilities for supplied outputs; importing this package has no side effects."""

__version__ = "0.1.0"

from .structures import read_structure, UnsupportedFormat, StructureFormatError
from .mapping import canonical_residue_map, validate_sequence_mapping
from .checks import structure_integrity_check, coarse_steric_clash_check
from .provenance import hash_file, hash_config, create_run_directory, write_manifest
from .evidence import CandidateEvidence, filter_candidates
from .dl_binder_output_adapter import import_dl_binder_sc
from .notebook_output_adapter import import_notebook_outputs, NotebookImportResult, NotebookImportError
from .check_report_bridge import build_check_report, CheckReport, CheckReportError

__all__ = [
    "read_structure", "UnsupportedFormat", "StructureFormatError",
    "canonical_residue_map", "validate_sequence_mapping",
    "structure_integrity_check", "coarse_steric_clash_check",
    "hash_file", "hash_config", "create_run_directory", "write_manifest",
    "CandidateEvidence", "filter_candidates",
    "import_dl_binder_sc",
    "import_notebook_outputs", "NotebookImportResult", "NotebookImportError",
    "build_check_report", "CheckReport", "CheckReportError",
]
