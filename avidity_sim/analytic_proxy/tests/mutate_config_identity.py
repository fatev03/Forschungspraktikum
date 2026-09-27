"""Mutation check for the configuration-identity contract of core.py.

Development tool only. Each mutant is one exact source substitution in a
temporary copy of the package; the focused suite must fail on every mutant.
A pattern that no longer occurs exactly once is reported as STALE, so the
check cannot pass silently after core.py changes. Standard library only.

    python -m analytic_proxy.tests.mutate_config_identity

Exit status 0 iff the unmutated copy passes and every mutant is killed.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

PACKAGE = pathlib.Path(__file__).resolve().parents[1]

#: (group, label, original text, mutated text); each original occurs once in core.py.
MUTANTS = (
    # certificate-hash trust
    ("trust", "certificate-only candidate takes the hash",
     "config_identity_hash = None\n",
     'config_identity_hash = cert["config_identity_hash"] if cert is not None else None\n'),
    ("trust", "result_id not compared before the hash is taken",
     'for key in ("result_id", "state_hash", "context_hash", "phase2_status"):',
     'for key in ("state_hash", "context_hash", "phase2_status"):'),
    ("trust", "mismatching certificate accepted",
     'raise ValueError(f"certificate does not match its STATE result: {key} differs")',
     "break"),
    ("trust", "StateInput hash invariant disabled",
     "if (self.config_identity_hash is not None) != (self.has_state_result and self.has_certificate):",
     "if False:"),
    ("trust", "StateInput hash format unchecked",
     '_hex64(self.config_identity_hash, "config_identity_hash")',
     "pass"),
    ("trust", "StateInput.as_dict omits the hash",
     '"config_identity_hash": self.config_identity_hash,\n',
     ""),
    # eligible-only mismatch detection
    ("eligible-only", "eligible_states compares all candidates",
     "_config_identity_validation(eligible)\n    return tuple(eligible), tuple(exclusions)",
     "_config_identity_validation(list(candidates))\n    return tuple(eligible), tuple(exclusions)"),
    ("eligible-only", "summary provenance computed over all candidates",
     "config_hashes = _config_identity_validation(eligible)",
     "config_hashes = _config_identity_validation(list(candidates))"),
    ("eligible-only", "mismatch detection disabled",
     "if len(hashes) > 1:",
     "if len(hashes) > 2:"),
    ("eligible-only", "unavailable value compared as a value",
     "known = [c.config_identity_hash for c in eligible if c.config_identity_hash is not None]",
     "known = [c.config_identity_hash for c in eligible]"),
    # partial / unavailable status
    ("status", "partial availability reported as validated",
     "if len(known) < len(eligible):",
     "if len(known) < 0:"),
    ("status", "all unavailable reported as partial",
     "if not known:",
     "if not known and False:"),
    ("status", "no eligible state reported as validated",
     'return ScenarioSummary.CONFIG_IDENTITY_VALIDATION_NOT_PERFORMED, "no eligible state", hashes',
     'return ScenarioSummary.CONFIG_IDENTITY_VALIDATED, "no eligible state", hashes'),
    ("status", "partial reported as not performed",
     "ScenarioSummary.CONFIG_IDENTITY_VALIDATION_PARTIAL,\n",
     "ScenarioSummary.CONFIG_IDENTITY_VALIDATION_NOT_PERFORMED,\n"),
    ("status", "full availability reported as partial",
     "ScenarioSummary.CONFIG_IDENTITY_VALIDATED,\n        f\"config_identity_hash is available and equal for all",
     "ScenarioSummary.CONFIG_IDENTITY_VALIDATION_PARTIAL,\n        f\"config_identity_hash is available and equal for all"),
    # provenance
    ("provenance", "status field omitted",
     '"config_identity_validation_status": config_status,\n',
     ""),
    ("provenance", "status and reason swapped",
     '"config_identity_validation_status": config_status,\n        "config_identity_validation_reason": config_reason,',
     '"config_identity_validation_status": config_reason,\n        "config_identity_validation_reason": config_status,'),
    ("provenance", "hash list includes excluded candidates",
     '"eligible_config_identity_hashes": config_hashes,',
     '"eligible_config_identity_hashes": tuple(sorted({c.config_identity_hash for c in candidates'
     ' if c.config_identity_hash is not None})),'),
    ("provenance", "status / hash-list consistency unchecked",
     "if len(hashes) != (1 if performed else 0) or (performed and self.eligible_count == 0):",
     "if False:"),
    ("provenance", "hash list not stored as a tuple",
     'provenance["eligible_config_identity_hashes"] = hashes',
     "pass"),
    ("provenance", "status wire value changed",
     'CONFIG_IDENTITY_VALIDATION_PARTIAL: ClassVar[str] = "CONFIG_IDENTITY_VALIDATION_PARTIAL"',
     'CONFIG_IDENTITY_VALIDATION_PARTIAL: ClassVar[str] = "PARTIAL"'),
    ("provenance", "schema version not advanced",
     'SCHEMA_VERSION = "analytic_proxy.scenario_summary/2"',
     'SCHEMA_VERSION = "analytic_proxy.scenario_summary/1"'),
)


def _suite_passes(root: pathlib.Path) -> bool:
    command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "analytic_proxy/tests", "-t", "."]
    return subprocess.run(command, cwd=root, capture_output=True, text=True).returncode == 0


def main() -> int:
    with tempfile.TemporaryDirectory() as scratch:
        root = pathlib.Path(scratch)
        shutil.copytree(PACKAGE, root / "analytic_proxy", ignore=shutil.ignore_patterns("__pycache__"))
        core = root / "analytic_proxy" / "core.py"
        source = core.read_text(encoding="utf-8")
        if not _suite_passes(root):
            print("BASELINE FAILED: the unmutated copy does not pass the focused suite")
            return 1
        failures = 0
        for group, label, original, mutated in MUTANTS:
            if source.count(original) != 1:
                verdict, failures = "STALE", failures + 1
            else:
                core.write_text(source.replace(original, mutated), encoding="utf-8")
                killed = not _suite_passes(root)
                verdict, failures = ("killed", failures) if killed else ("SURVIVED", failures + 1)
            print(f"{verdict:8} {group:13} {label}")
        core.write_text(source, encoding="utf-8")
    print(f"{len(MUTANTS) - failures}/{len(MUTANTS)} mutants killed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
