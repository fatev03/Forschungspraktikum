"""Deterministic presentation tests; no real artifact or frozen fixture is read."""
from contextlib import ExitStack
from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import patch

from structure_audit.demo_external_reference import (
    ExternalStructureReference, build_demo_report,
)


def supplied_record():
    return {
        "provider": "af3-red",
        "profile": "af3_native_v1",
        "artifact_id": "5b4690580b352de100439cc68cb460847c4f4729c3b9151ca6ba739f8ce2aad7",
        "observed_sha256": "58f38cc8f279fb827851c27ff735bdc4b310ca22276a6a2cf8ebbb2414a882ed",
        "source_status": "candidate",
        "read_completed": True,
        "execution_state": "completed",
        "validation_status": "passed_with_nonfatal_observations",
        "non_admission_reasons": ["af3red_execution_declaration_missing",
                                  "bias_sigma_unknown", "bias_weight_unknown"],
    }


class ExternalReferenceTests(unittest.TestCase):
    def setUp(self):
        self.data = supplied_record()
        self.reference = ExternalStructureReference(**self.data)
        self.lines = [" candidate output  ", "", "geometry\tunchanged", "state/avidity\noutput"]

    def test_exact_stored_fields_and_presentation_shape(self):
        report = build_demo_report(self.lines, self.reference)
        self.assertEqual(self.reference.to_dict(), self.data)
        self.assertEqual(report.to_dict(), {
            "existing_summary_lines": self.lines,
            "external_structure_reference": self.data,
        })

    def test_exact_rendered_provenance_and_reason_order(self):
        self.assertEqual(build_demo_report([], self.reference).render_lines(), [
            "External structure reference — separate provenance; no admission.",
            "provider: af3-red",
            "profile: af3_native_v1",
            "artifact_id: 5b4690580b352de100439cc68cb460847c4f4729c3b9151ca6ba739f8ce2aad7",
            "observed_sha256: 58f38cc8f279fb827851c27ff735bdc4b310ca22276a6a2cf8ebbb2414a882ed",
            "source_status: candidate",
            "read_completed: true",
            "execution_state: completed",
            "runtime validation status: passed_with_nonfatal_observations",
            "non_admission_reasons:",
            "  - af3red_execution_declaration_missing",
            "  - bias_sigma_unknown",
            "  - bias_weight_unknown",
        ])

    def test_successful_runtime_never_promotes_source_status(self):
        report = build_demo_report(["existing outcome: ACCEPTED"], self.reference)
        self.assertEqual(report.to_dict()["external_structure_reference"]["source_status"], "candidate")
        self.assertIn("source_status: candidate", report.render_lines())
        self.assertNotIn("source_status: admitted", report.render_lines())
        self.assertEqual(set(report.to_dict()), {"existing_summary_lines", "external_structure_reference"})
        self.assertEqual(set(report.to_dict()["external_structure_reference"]), set(self.data))

    def test_existing_lines_preserved_verbatim_and_in_order(self):
        for reference in (self.reference, None):
            with self.subTest(reference=reference):
                self.assertEqual(build_demo_report(self.lines, reference).render_lines()[:4], self.lines)

    def test_absent_or_unavailable_record_is_nonblocking(self):
        for report in (build_demo_report(self.lines), build_demo_report(self.lines, None)):
            self.assertEqual(report.to_dict()["external_structure_reference"], None)
            self.assertEqual(report.render_lines(), self.lines + [
                "External structure reference not supplied/available"])

    def test_repeated_rendering_is_identical(self):
        report = build_demo_report(self.lines, self.reference)
        self.assertEqual(report.render_lines(), report.render_lines())
        self.assertEqual(report.to_dict(), build_demo_report(self.lines, self.reference).to_dict())

    def test_record_and_report_assignments_are_frozen(self):
        report = build_demo_report(self.lines, self.reference)
        for obj, name, value in ((self.reference, "source_status", "admitted"),
                                 (self.reference, "non_admission_reasons", ()),
                                 (report, "external_structure_reference", None),
                                 (report, "existing_summary_lines", ())):
            with self.subTest(name=name), self.assertRaises(FrozenInstanceError):
                setattr(obj, name, value)
        with self.assertRaises(TypeError):
            self.reference.non_admission_reasons[0] = "changed"
        self.assertEqual(self.reference.to_dict(), self.data)

    def test_mutating_inputs_or_return_values_cannot_change_snapshot(self):
        report = build_demo_report(self.lines, self.reference)
        before = report.to_dict()
        rendered = report.render_lines()
        self.data["non_admission_reasons"].clear()
        self.lines.clear()
        exported = report.to_dict()
        exported["external_structure_reference"]["source_status"] = "admitted"
        exported["external_structure_reference"]["non_admission_reasons"].clear()
        exported["existing_summary_lines"].clear()
        report.render_lines().clear()
        self.assertEqual(report.to_dict(), before)
        self.assertEqual(report.render_lines(), rendered)

    def test_no_metadata_normalization_or_completion(self):
        self.data["non_admission_reasons"] = ["bias_weight_unknown", " x ", "bias_weight_unknown"]
        self.data["artifact_id"] = " caller-supplied ID "
        reference = ExternalStructureReference(**self.data)
        self.assertEqual(reference.to_dict(), self.data)
        self.assertEqual(build_demo_report([], reference).render_lines()[-3:], [
            "  - bias_weight_unknown", "  -  x ", "  - bias_weight_unknown"])

    def test_rejects_mutable_or_callback_inputs_without_invoking_them(self):
        callback = unittest.mock.Mock(side_effect=AssertionError("callback invoked"))
        for lines in (callback, "not a list", [42]):
            with self.subTest(lines=lines), self.assertRaises(TypeError):
                build_demo_report(lines)
        with self.assertRaises(TypeError):
            build_demo_report([], callback)
        for name, value in (("provider", []), ("read_completed", "true"),
                            ("non_admission_reasons", callback)):
            with self.subTest(name=name), self.assertRaises(TypeError):
                ExternalStructureReference(**{**self.data, name: value})
        callback.assert_not_called()

    def test_no_io_hashing_adapter_or_reader_calls(self):
        # Resolve patch targets before installing guards; module loading is test setup.
        targets = (
            "structure_audit.af3_red_adapter.discover_red_runs",
            "structure_audit.af3_red_adapter.discover_structure_files",
            "structure_audit.af3_red_adapter.build_red_manifest",
            "structure_audit.af3_red_adapter.validate_basic_mapping_readiness",
            "structure_audit.af3_native_bridge.read_af3_native_cif",
            "structure_audit.structures.read_structure",
            "urllib.request.urlopen", "socket.socket", "subprocess.Popen",
            "hashlib.sha256", "builtins.open", "io.open", "os.stat", "os.scandir",
        )
        guards = [patch(target, side_effect=AssertionError(target)) for target in targets]
        for guard in guards:
            guard.get_original()
        with ExitStack() as stack:
            mocks = [stack.enter_context(guard) for guard in guards]
            reference = ExternalStructureReference(**self.data)
            for supplied in (reference, None):
                report = build_demo_report(self.lines, supplied)
                report.to_dict()
                report.render_lines()
            for mock in mocks:
                mock.assert_not_called()
