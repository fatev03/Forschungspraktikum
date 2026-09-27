"""Synthetic contract tests for f01_coordinate_admission.

Every fixture is a synthetic coordinate-bearing file written for this suite. No existing
AF3, PDB or CIF project artefact is used and no pre-existing coordinate file is asserted
to be in nm. Expected distances are derived independently of the module under test.
"""
import builtins
from copy import deepcopy
import hashlib
import io
import math
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from structure_audit import f01_coordinate_admission as f01
from structure_audit.evidence import CandidateEvidence
from structure_audit.f01_coordinate_admission import (
    F01CoordinateAdmissionError, F01CoordinateDistance, admit_and_measure_distance,
    coordinate_digest, coordinate_json, load_f01_coordinate_distance,
    to_candidate_evidence_metric,
)
from structure_audit.validation import validate_named

FIXTURES = (Path(__file__).parent / "fixtures" / "f01_coordinate_admission").resolve()
ACTIVATION = {"opt_in": True, "lane": "experimental",
              "input_contract_id": "F01-coordinate-admission-v1"}
LOCATOR_PROFILE = {"profile_id": "structure_atom_locator", "profile_version": "1"}
SOURCE_ADMISSION = {"prior_normalization_pass_count": 0, "prior_conversion_count": 0}
OUTPUT_DECLARATION = {"context": "complex", "category": "declared_geometry", "scale": None}
UNDECLARED_CONFIGURATION = {"producer_configuration_hash": None,
                            "producer_configuration_missing_reason": "not_declared"}
FRAME = "frame-01"


def digest_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def locator(atom_name, *, model="1", chain="A", segment=0, group="ATOM", residue_id=1,
            insertion_code="", residue_name="GLY", altloc=""):
    return {"model_id": model, "chain_id": chain, "segment": segment, "group": group,
            "residue_id": residue_id, "insertion_code": insertion_code,
            "residue_name": residue_name, "atom_name": atom_name, "altloc": altloc}


def artifact(name="pair_unit.pdb", *, root=FIXTURES, artifact_id="syn-artifact",
             sha256=None, layout="structure_v1", model="1"):
    path = Path(root) / name
    return {"artifact_id": artifact_id, "path": str(path),
            "expected_sha256": sha256 or digest_of(path), "layout": layout,
            "selected_model_id": model}


def declaration(*, artifact_id="syn-artifact", sha256=None, model="1", frame=FRAME,
                declaration_id="decl-01", root=FIXTURES, name="pair_unit.pdb", **over):
    value = {"coordinate_declaration_id": declaration_id,
             "scope": {"artifact_id": artifact_id,
                       "artifact_sha256": sha256 or digest_of(Path(root) / name),
                       "selected_model_id": model},
             "coordinate_unit": "nm", "source_unit": "nm", "frame_id": frame,
             "frame_kind": "cartesian_3d",
             "normalization_profile_id": "coordinate-nm-identity",
             "normalization_profile_version": "1",
             "conversion": {"applied": False, "factor": 1, "formula": "x_nm = x_source"},
             "canonicalization_version": "coordinate-json-v1"}
    for dotted, item in over.items():
        keys = dotted.split(".")
        target = value
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = item
    return value


def endpoints(x_atom="N", y_atom="CA", *, frame=FRAME, frame_kind="cartesian_3d", **over):
    value = {"x": {"point_id": "pt-x", "frame_id": frame, "frame_kind": frame_kind,
                   "locator": locator(x_atom)},
             "y": {"point_id": "pt-y", "frame_id": frame, "frame_kind": frame_kind,
                   "locator": locator(y_atom)}}
    for dotted, item in over.items():
        keys = dotted.split(".")
        target = value
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = item
    return value


def admit(**over):
    payload = {"endpoints": endpoints(), "locator_profile": deepcopy(LOCATOR_PROFILE),
               "source_admission": deepcopy(SOURCE_ADMISSION),
               "output_declaration": deepcopy(OUTPUT_DECLARATION),
               "producer_configuration": deepcopy(UNDECLARED_CONFIGURATION),
               "activation": deepcopy(ACTIVATION)}
    payload.update(over)
    # Built lazily so that no default opens a file a caller did not select.
    if "artifact" not in payload:
        payload["artifact"] = artifact()
    if "coordinate_declaration" not in payload:
        payload["coordinate_declaration"] = declaration()
    return admit_and_measure_distance(**payload)


class Contract(unittest.TestCase):
    def rejected(self, code, *, endpoint=None, field=None, **over):
        result = admit(**over)
        data = result.to_dict()
        self.assertEqual(data["status"], "REJECTED", data["diagnostic"])
        self.assertEqual(data["diagnostic"]["code"], code, data["diagnostic"])
        if endpoint is not None:
            self.assertEqual(data["diagnostic"]["endpoint"], endpoint, data["diagnostic"])
        if field is not None:
            self.assertEqual(data["diagnostic"]["field"], field, data["diagnostic"])
        self.assertIsNone(data["payload"]["distance_nm"])
        self.assertIsNone(data["output_metric"]["value"])
        self.assertIsNone(data["payload"]["endpoint_mapping"])
        self.assertIsNone(data["payload"]["endpoint_mapping_sha256"])
        for name in ("x", "y"):
            self.assertIsNone(data["payload"]["endpoints"][name])
        self.check_order(data, code)
        return result

    def check_order(self, data, failed_code):
        codes = [c["code"] for c in data["checks"]]
        self.assertEqual(tuple(codes), f01.CHECK_ORDER)
        results = [c["result"] for c in data["checks"]]
        index = codes.index(failed_code)
        self.assertEqual(results[:index], ["PASSED"] * index)
        self.assertEqual(results[index], "FAILED")
        self.assertEqual(results[index + 1:], ["NOT_REACHED"] * (len(codes) - index - 1))

    def error(self, code, **over):
        with self.assertRaises(F01CoordinateAdmissionError) as caught:
            admit(**over)
        self.assertEqual(caught.exception.code, code, str(caught.exception))
        self.assertEqual(caught.exception.diagnostics[0]["code"], code)
        return caught.exception


class Admission(Contract):
    def test_axis_aligned_pair_gives_exactly_five(self):
        result = admit()
        self.assertEqual(result.status, "COMPUTED")
        self.assertEqual(result.distance_nm, 5.0)
        data = result.to_dict()
        self.assertEqual(data["output_metric"], {
            "quantity_id": "distance_nm", "quantity_definition_id": "distance_nm",
            "context": "complex", "category": "declared_geometry", "scale": None,
            "unit": "nm", "value": 5.0})
        self.assertIsNone(data["diagnostic"])
        self.assertEqual([c["result"] for c in data["checks"]], ["PASSED"] * len(f01.CHECK_ORDER))
        validate_named(data, "f01_coordinate_distance")

    def test_non_axis_aligned_pair_matches_an_independent_evaluation(self):
        expected = math.sqrt((1.25 - -3.75) ** 2 + (-2.5 - 0.5) ** 2 + (0.75 - -1.25) ** 2)
        self.assertEqual(expected, math.sqrt(38.0))
        result = admit(artifact=artifact("pair_oblique.pdb"),
                       coordinate_declaration=declaration(name="pair_oblique.pdb"),
                       endpoints=endpoints(
                           **{"x.locator": locator("N", chain="B", residue_id=7, residue_name="ALA"),
                              "y.locator": locator("CA", chain="B", residue_id=8, residue_name="ALA")}))
        self.assertEqual(result.status, "COMPUTED")
        self.assertEqual(result.distance_nm, expected)

    def test_endpoint_records_and_traces_are_complete(self):
        data = admit().to_dict()
        for name, triple in (("x", [0.0, 0.0, 0.0]), ("y", [3.0, 4.0, 0.0])):
            with self.subTest(endpoint=name):
                record = data["payload"]["endpoints"][name]
                self.assertEqual(record["coordinates_nm"], triple)
                self.assertEqual(record["coordinate_unit"], "nm")
                self.assertEqual(record["frame_id"], FRAME)
                self.assertEqual(record["frame_kind"], "cartesian_3d")
                self.assertEqual(record["selected_model_id"], "1")
                self.assertEqual(record["normalization_profile_id"], "coordinate-nm-identity")
                self.assertEqual(record["normalization_profile_version"], "1")
                trace = record["normalization_trace"]
                self.assertEqual(trace["source_coordinates"], trace["normalized_coordinates"])
                self.assertEqual(trace["source_unit"], "nm")
                self.assertEqual(trace["target_unit"], "nm")
                self.assertEqual(trace["operation"], "identity_admission")
                self.assertEqual(trace["normalization_pass_count"], 1)
                self.assertEqual(trace["conversion_count"], 0)
                self.assertIs(trace["conversion_applied"], False)
                self.assertEqual(trace["factor"], 1)
                self.assertEqual(trace["formula"], "x_nm = x_source")
                self.assertEqual(record["normalization_trace_sha256"],
                                 coordinate_digest("normalization_trace", trace))

    def test_declared_digests_are_the_digests_of_what_they_name(self):
        data = admit().to_dict()
        payload = data["payload"]
        self.assertEqual(payload["coordinate_declaration_sha256"],
                         coordinate_digest("coordinate_declaration", payload["coordinate_declaration"]))
        self.assertEqual(payload["endpoint_mapping_sha256"],
                         coordinate_digest("endpoint_mapping", payload["endpoint_mapping"]))
        self.assertEqual(data["payload_sha256"], coordinate_digest("result_payload", payload))
        without = {k: v for k, v in data.items() if k != "result_id"}
        self.assertEqual(data["result_id"],
                         coordinate_digest("f01_coordinate_distance_result", without))
        self.assertEqual(payload["endpoint_mapping"]["order"], ["x", "y"])

    def test_a_declared_producer_configuration_is_carried_with_its_hash(self):
        snapshot = {"admission": "nm-identity", "reader": "structure_v1"}
        result = admit(producer_configuration={
            "producer_configuration": snapshot,
            "producer_configuration_hash": coordinate_digest("producer_configuration", snapshot)})
        payload = result.to_dict()["payload"]
        self.assertEqual(payload["producer_configuration"], snapshot)
        self.assertIsNone(payload["producer_configuration_missing_reason"])
        self.assertEqual(payload["producer_configuration_hash"],
                         coordinate_digest("producer_configuration", snapshot))

    def test_an_undeclared_producer_configuration_is_explicit(self):
        payload = admit().to_dict()["payload"]
        self.assertIsNone(payload["producer_configuration"])
        self.assertIsNone(payload["producer_configuration_hash"])
        self.assertEqual(payload["producer_configuration_missing_reason"], "not_declared")

    def test_the_module_produces_no_span_predicate_or_aggregate(self):
        data = admit().to_dict()
        text = coordinate_json(data).decode("utf-8").lower()
        for token in ("d_min", "d_max", "permitted", "tolerance", "span_element",
                      "probability", "rank", "score"):
            with self.subTest(token=token):
                self.assertNotIn(token, text)


class PathExclusion(Contract):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def test_changing_the_selected_path_changes_execution_metadata_only(self):
        shutil.copy(FIXTURES / "pair_unit.pdb", self.root / "pair_unit.pdb")
        here, moved = admit(), admit(artifact=artifact(root=self.root),
                                     coordinate_declaration=declaration(root=self.root))
        self.assertEqual(moved.result_id, here.result_id)
        self.assertEqual(moved.to_json_bytes(), here.to_json_bytes())
        self.assertNotEqual(moved.execution_metadata["selected_path"],
                            here.execution_metadata["selected_path"])
        self.assertEqual(moved.execution_metadata["selected_path"],
                         str(self.root / "pair_unit.pdb"))

    def test_no_path_enters_the_canonical_document_or_any_digest(self):
        data = admit().to_dict()
        paths = []

        def walk(node, where):
            if isinstance(node, dict):
                for key, item in node.items():
                    if key == "selected_path":
                        paths.append(f"{where}.{key}")
                    walk(item, f"{where}.{key}")
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    walk(item, f"{where}[{index}]")
            elif isinstance(node, str) and node.startswith("/"):
                paths.append(f"{where}={node}")

        walk({k: v for k, v in data.items() if k != "rules"}, "$")
        self.assertEqual(paths, [])
        self.assertNotIn(str(FIXTURES), admit().to_json_bytes().decode("utf-8"))

    def test_a_renamed_artifact_with_equal_bytes_keeps_the_result_identity(self):
        shutil.copy(FIXTURES / "pair_unit.pdb", self.root / "other_name.pdb")
        renamed = admit(artifact=artifact("other_name.pdb", root=self.root),
                        coordinate_declaration=declaration(root=self.root, name="other_name.pdb"))
        self.assertEqual(renamed.result_id, admit().result_id)


class Declaration(Contract):
    def test_missing_declaration(self):
        self.rejected("COORDINATE_DECLARATION_MISSING", field="coordinate_declaration",
                      coordinate_declaration=None)

    def test_unknown_declaration_field(self):
        value = declaration()
        value["coordinate_unit_hint"] = "nm"
        self.rejected("COORDINATE_DECLARATION_INVALID", coordinate_declaration=value)

    def test_omitted_general_required_field(self):
        for key in ("coordinate_declaration_id", "scope", "canonicalization_version"):
            with self.subTest(key=key):
                value = declaration()
                value.pop(key)
                self.rejected("COORDINATE_DECLARATION_INVALID", coordinate_declaration=value)

    def test_empty_or_wrong_general_identifiers(self):
        cases = (("coordinate_declaration_id", ""), ("coordinate_declaration_id", None),
                 ("canonicalization_version", ""), ("canonicalization_version", "coordinate-json-v2"),
                 ("scope.artifact_id", ""), ("scope.selected_model_id", ""),
                 ("scope.artifact_sha256", "not-a-digest"), ("scope.artifact_sha256", "A" * 64))
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.rejected("COORDINATE_DECLARATION_INVALID",
                              coordinate_declaration=declaration(**{field: value}))

    def test_scope_shape_is_closed(self):
        value = declaration()
        value["scope"]["extra"] = 1
        self.rejected("COORDINATE_DECLARATION_INVALID", coordinate_declaration=value)

    def test_one_declaration_id_with_changed_content_is_invalid(self):
        first = admit()
        bound = first.to_dict()["payload"]["coordinate_declaration_sha256"]
        changed = declaration(frame="frame-02")
        self.assertNotEqual(coordinate_digest("coordinate_declaration", changed), bound)
        result = admit(coordinate_declaration=changed,
                       endpoints=endpoints(frame="frame-02"),
                       prior_declaration_binding={"coordinate_declaration_id": "decl-01",
                                                  "coordinate_declaration_sha256": bound})
        self.assertEqual(result.to_dict()["diagnostic"]["code"], "COORDINATE_DECLARATION_INVALID")
        self.check_order(result.to_dict(), "COORDINATE_DECLARATION_INVALID")

    def test_the_same_declaration_id_with_identical_content_is_accepted(self):
        bound = admit().to_dict()["payload"]["coordinate_declaration_sha256"]
        self.assertEqual(admit(prior_declaration_binding={
            "coordinate_declaration_id": "decl-01",
            "coordinate_declaration_sha256": bound}).status, "COMPUTED")

    def test_a_prior_binding_for_another_declaration_id_is_invalid(self):
        bound = admit().to_dict()["payload"]["coordinate_declaration_sha256"]
        self.rejected("COORDINATE_DECLARATION_INVALID", field="prior_declaration_binding",
                      prior_declaration_binding={"coordinate_declaration_id": "decl-99",
                                                 "coordinate_declaration_sha256": bound})

    def test_a_malformed_prior_binding_fails_the_outer_contract(self):
        for value in ({"coordinate_declaration_id": "decl-01"},
                      {"coordinate_declaration_id": "", "coordinate_declaration_sha256": "a" * 64},
                      {"coordinate_declaration_id": "decl-01",
                       "coordinate_declaration_sha256": "nope"}):
            with self.subTest(keys=sorted(value)):
                self.error("INPUT_CONTRACT_INVALID", prior_declaration_binding=value)

    def test_a_declaration_is_required_even_for_coordinates_asserted_to_be_nm(self):
        self.rejected("COORDINATE_DECLARATION_MISSING", coordinate_declaration=None,
                      output_declaration={**OUTPUT_DECLARATION, "category": "already_nm_upstream"})


class Units(Contract):
    def test_angstrom_source_unit_is_unsupported(self):
        result = self.rejected("COORDINATE_UNIT_UNSUPPORTED",
                               field="coordinate_declaration.source_unit",
                               coordinate_declaration=declaration(source_unit="angstrom"))
        self.assertIn("no length conversion", result.to_dict()["diagnostic"]["detail"])

    def test_angstrom_output_unit_is_unsupported(self):
        self.rejected("COORDINATE_UNIT_UNSUPPORTED", field="coordinate_declaration.coordinate_unit",
                      coordinate_declaration=declaration(coordinate_unit="angstrom"))

    def test_aliases_and_case_variants_are_unsupported(self):
        for unit in ("NM", "nanometre", "nanometer", "Nm", " nm", "nm ", "A", "Å", ""):
            with self.subTest(unit=unit):
                self.rejected("COORDINATE_UNIT_UNSUPPORTED",
                              coordinate_declaration=declaration(source_unit=unit))

    def test_omitted_unit_fields_reach_their_own_stage(self):
        for key in ("coordinate_unit", "source_unit"):
            with self.subTest(key=key):
                value = declaration()
                value.pop(key)
                self.rejected("COORDINATE_UNIT_UNSUPPORTED", coordinate_declaration=value)


class Profile(Contract):
    def test_unknown_normalization_profile(self):
        for key, value in (("normalization_profile_id", "coordinate-angstrom-to-nm"),
                           ("normalization_profile_id", ""),
                           ("normalization_profile_version", "2"),
                           ("normalization_profile_version", 1)):
            with self.subTest(key=key, value=value):
                self.rejected("COORDINATE_UNIT_PROFILE_UNKNOWN",
                              field=f"coordinate_declaration.{key}",
                              coordinate_declaration=declaration(**{key: value}))

    def test_omitted_profile_fields_reach_their_own_stage(self):
        for key in ("normalization_profile_id", "normalization_profile_version"):
            with self.subTest(key=key):
                value = declaration()
                value.pop(key)
                self.rejected("COORDINATE_UNIT_PROFILE_UNKNOWN", coordinate_declaration=value)

    def test_unsupported_frame_kind_is_profile_inconsistent(self):
        self.rejected("COORDINATE_PROFILE_INCONSISTENT",
                      field="coordinate_declaration.frame_kind",
                      coordinate_declaration=declaration(frame_kind="cartesian_2d"))

    def test_conversion_object_mismatch_is_profile_inconsistent(self):
        cases = (("conversion.applied", True), ("conversion.factor", 10),
                 ("conversion.factor", 1.0), ("conversion.formula", "x_nm = 0.1 * x_source"),
                 ("conversion", {"applied": False, "factor": 1}),
                 ("conversion", {"applied": False, "factor": 1, "formula": "x_nm = x_source",
                                 "extra": 1}))
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.rejected("COORDINATE_PROFILE_INCONSISTENT",
                              coordinate_declaration=declaration(**{field: value}))

    def test_omitted_conversion_reaches_the_profile_stage(self):
        value = declaration()
        value.pop("conversion")
        self.rejected("COORDINATE_PROFILE_INCONSISTENT", coordinate_declaration=value)


class Frame(Contract):
    def test_missing_or_empty_declaration_frame(self):
        for key, value in (("frame_id", ""), ("frame_id", None), ("frame_kind", "")):
            with self.subTest(key=key, value=value):
                self.rejected("COORDINATE_FRAME_MISSING", field=f"coordinate_declaration.{key}",
                              coordinate_declaration=declaration(**{key: value}))
        for key in ("frame_id", "frame_kind"):
            with self.subTest(omitted=key):
                value = declaration()
                value.pop(key)
                self.rejected("COORDINATE_FRAME_MISSING", coordinate_declaration=value)

    def test_missing_or_empty_endpoint_frame(self):
        for name in ("x", "y"):
            for key in ("frame_id", "frame_kind"):
                for value in ("", None):
                    with self.subTest(endpoint=name, key=key, value=value):
                        self.rejected("COORDINATE_FRAME_MISSING", endpoint=name,
                                      field=f"endpoints.{name}.{key}",
                                      endpoints=endpoints(**{f"{name}.{key}": value}))

    def test_unequal_endpoint_frames_are_rejected(self):
        self.rejected("COORDINATE_FRAME_MISMATCH", endpoint="y", field="endpoints.y.frame_id",
                      endpoints=endpoints(**{"y.frame_id": "frame-02"}))
        self.rejected("COORDINATE_FRAME_MISMATCH", endpoint="x", field="endpoints.x.frame_id",
                      endpoints=endpoints(**{"x.frame_id": "frame-02"}))

    def test_equal_coordinates_do_not_establish_frame_equality(self):
        result = self.rejected("COORDINATE_FRAME_MISMATCH",
                               endpoints=endpoints("N", "N", **{"y.frame_id": "frame-02"}))
        self.assertIn("no transform or equivalence inference",
                      result.to_dict()["diagnostic"]["detail"])

    def test_endpoint_x_is_inspected_before_endpoint_y(self):
        both = endpoints(**{"x.frame_id": "", "y.frame_id": ""})
        self.rejected("COORDINATE_FRAME_MISSING", endpoint="x", endpoints=both)


class ArtifactIdentity(Contract):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def test_expected_hash_mismatch(self):
        self.rejected("ARTIFACT_IDENTITY_MISMATCH", field="artifact.expected_sha256",
                      artifact=artifact(sha256="0" * 64))

    def test_declaration_scope_hash_mismatch(self):
        self.rejected("ARTIFACT_IDENTITY_MISMATCH",
                      field="coordinate_declaration.scope.artifact_sha256",
                      coordinate_declaration=declaration(name="pair_oblique.pdb"))

    def test_declaration_scope_artifact_id_mismatch(self):
        self.rejected("ARTIFACT_IDENTITY_MISMATCH",
                      field="coordinate_declaration.scope.artifact_id",
                      coordinate_declaration=declaration(artifact_id="other-artifact"))

    def test_selected_model_mismatches(self):
        self.rejected("ARTIFACT_IDENTITY_MISMATCH",
                      field="coordinate_declaration.scope.selected_model_id",
                      coordinate_declaration=declaration(model="2"))
        self.rejected("ARTIFACT_IDENTITY_MISMATCH", endpoint="x",
                      field="endpoints.x.locator.model_id",
                      endpoints=endpoints(**{"x.locator": locator("N", model="2")}))

    def test_model_not_present_in_the_artifact(self):
        self.rejected("ARTIFACT_IDENTITY_MISMATCH",
                      artifact=artifact(model="7"),
                      coordinate_declaration=declaration(model="7"),
                      endpoints=endpoints(**{"x.locator": locator("N", model="7"),
                                             "y.locator": locator("CA", model="7")}))

    def test_a_second_model_is_never_chosen_implicitly(self):
        result = admit(artifact=artifact("pair_two_models.pdb"),
                       coordinate_declaration=declaration(name="pair_two_models.pdb"))
        self.assertEqual(result.status, "COMPUTED")
        self.assertEqual(result.distance_nm, 5.0)
        other = admit(artifact=artifact("pair_two_models.pdb", model="2"),
                      coordinate_declaration=declaration(name="pair_two_models.pdb", model="2"),
                      endpoints=endpoints(**{"x.locator": locator("N", model="2"),
                                             "y.locator": locator("CA", model="2")}))
        self.assertEqual(other.distance_nm, 10.0)

    def test_unparsable_artifact_under_the_declared_layout(self):
        self.rejected("ARTIFACT_IDENTITY_MISMATCH", field="artifact",
                      artifact=artifact("pair_malformed.pdb"),
                      coordinate_declaration=declaration(name="pair_malformed.pdb"))

    def test_artifact_modified_during_processing(self):
        source = self.root / "pair_unit.pdb"
        shutil.copy(FIXTURES / "pair_unit.pdb", source)
        chosen, declared = artifact(root=self.root), declaration(root=self.root)
        real = f01.read_structure

        def mutate(path, **kwargs):
            structure = real(path, **kwargs)
            Path(path).write_bytes(Path(path).read_bytes() + b"REMARK   APPENDED\n")
            return structure

        with patch.object(f01, "read_structure", mutate):
            result = admit(artifact=chosen, coordinate_declaration=declared)
        data = result.to_dict()
        self.assertEqual(data["status"], "REJECTED")
        self.assertEqual(data["diagnostic"]["code"], "ARTIFACT_IDENTITY_MISMATCH")
        self.assertEqual(data["observation"]["read_status"], "BYTES_CHANGED_DURING_ADMISSION")


class GuardCoverage(Contract):
    """Guards whose integrated path is shadowed, pinned directly so they stay load-bearing."""

    def test_a_parsed_model_that_contradicts_the_request_is_rejected(self):
        """read_structure already selects by model_id; the cross-check must still hold."""
        real = f01.read_structure

        class Relabelled:
            def __init__(self, structure):
                self.model_id, self.atoms = "9", structure.atoms

        with patch.object(f01, "read_structure", lambda path, **kw: Relabelled(real(path, **kw))):
            self.rejected("ARTIFACT_IDENTITY_MISMATCH", field="artifact.selected_model_id")

    def test_an_ambiguous_endpoint_records_no_coordinates(self):
        """No first matching record is ever taken: an ambiguous locator yields no triple."""
        data = admit(artifact=artifact("pair_ambiguous.pdb"),
                     coordinate_declaration=declaration(name="pair_ambiguous.pdb")).to_dict()
        resolution = data["observation"]["resolution"]
        self.assertEqual(resolution["y"]["match_count"], 2)
        self.assertIsNone(resolution["y"]["source_coordinates"])
        self.assertEqual(resolution["x"]["match_count"], 1)

    def test_a_boolean_coordinate_component_in_a_seed_is_refused(self):
        """A reloaded seed is JSON, so a component may arrive as true. The schema refuses it
        and _component refuses it independently; neither admits it as the number one."""
        rejected = admit(artifact=artifact("pair_nonfinite.pdb"),
                         coordinate_declaration=declaration(name="pair_nonfinite.pdb")).to_dict()
        self.assertEqual(rejected["observation"]["resolution"]["y"]["source_coordinates"][0], "nan")
        rejected["observation"]["resolution"]["y"]["source_coordinates"][0] = True
        without = {k: v for k, v in rejected.items() if k != "result_id"}
        rejected["result_id"] = coordinate_digest("f01_coordinate_distance_result", without)
        with self.assertRaises(F01CoordinateAdmissionError) as caught:
            F01CoordinateDistance.from_dict(rejected)
        self.assertEqual(caught.exception.code, "RESULT_INVALID")

    def test_component_admission_is_exact(self):
        for value in (True, False, "nan", "3.0", None, 2 ** 53 + 1, 10 ** 400, [3.0],
                      float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=repr(value)):
                self.assertIsNone(f01._component(value))
        for value, expected in ((0, 0.0), (3, 3.0), (-2, -2.0), (2 ** 53, float(2 ** 53)),
                                (2.5, 2.5), (-0.0, -0.0)):
            with self.subTest(value=repr(value)):
                admitted = f01._component(value)
                self.assertIs(type(admitted), float)
                self.assertEqual(admitted, expected)

    def test_an_inexact_integer_component_in_a_seed_is_not_admitted(self):
        rejected = admit(artifact=artifact("pair_nonfinite.pdb"),
                         coordinate_declaration=declaration(name="pair_nonfinite.pdb")).to_dict()
        rejected["observation"]["resolution"]["y"]["source_coordinates"][0] = 2 ** 53 + 1
        without = {k: v for k, v in rejected.items() if k != "result_id"}
        rejected["result_id"] = coordinate_digest("f01_coordinate_distance_result", without)
        self.assertEqual(F01CoordinateDistance.from_dict(rejected).status, "REJECTED")

    def test_an_exact_integer_component_in_a_seed_is_admitted(self):
        computed = admit().to_dict()
        self.assertEqual(computed["observation"]["resolution"]["y"]["source_coordinates"],
                         [3.0, 4.0, 0.0])
        self.assertEqual(F01CoordinateDistance.from_dict(computed).distance_nm, 5.0)


class TraceVerification(unittest.TestCase):
    """The admission trace is built and re-derived by one pure function, so its verification
    stage cannot fail through the integrated path. Each branch is pinned directly."""

    def records(self):
        return deepcopy(admit().to_dict()["payload"]["endpoints"])

    def digest(self):
        return admit().to_dict()["payload"]["coordinate_declaration_sha256"]

    def corrupted(self, mutate):
        records = self.records()
        mutate(records)
        with self.assertRaises(Exception) as caught:
            f01._stage_trace_invalid(records, self.digest())
        self.assertEqual(caught.exception.code, "NORMALIZATION_TRACE_INVALID")
        return caught.exception

    def test_an_intact_trace_passes(self):
        self.assertIsNone(f01._stage_trace_invalid(self.records(), self.digest()))

    def test_a_trace_digest_that_does_not_match_its_trace(self):
        self.corrupted(lambda r: r["x"].update(normalization_trace_sha256="0" * 64))

    def test_source_and_normalized_coordinates_that_differ(self):
        def mutate(records):
            trace = records["y"]["normalization_trace"]
            trace["normalized_coordinates"] = [3.0, 4.0, 1.0]
            records["y"]["coordinates_nm"] = [3.0, 4.0, 1.0]
            records["y"]["normalization_trace_sha256"] = coordinate_digest(
                "normalization_trace", trace)

        failure = self.corrupted(mutate)
        self.assertEqual(failure.endpoint, "y")
        self.assertIn("not identical", failure.detail)

    def test_endpoint_coordinates_that_do_not_match_the_trace(self):
        self.corrupted(lambda r: r["x"].update(coordinates_nm=[1.0, 0.0, 0.0]))

    def test_each_profile_field_of_the_trace_is_verified(self):
        fields = {"source_unit": "angstrom", "target_unit": "angstrom",
                  "operation": "conversion", "normalization_pass_count": 2,
                  "conversion_count": 1, "conversion_applied": True, "factor": 10,
                  "formula": "x_nm = 0.1 * x_source",
                  "normalization_profile_id": "coordinate-angstrom-to-nm",
                  "normalization_profile_version": "2",
                  "canonicalization_version": "coordinate-json-v2",
                  "coordinate_declaration_sha256": "0" * 64}
        for key, value in fields.items():
            with self.subTest(key=key):
                def mutate(r, key=key, value=value):
                    r["x"]["normalization_trace"][key] = value
                    r["x"]["normalization_trace_sha256"] = coordinate_digest(
                        "normalization_trace", r["x"]["normalization_trace"])
                self.corrupted(mutate)


class Selectors(Contract):
    def test_selector_resolves_to_no_atom(self):
        self.rejected("POINT_SELECTOR_NOT_FOUND", endpoint="x", field="endpoints.x.locator",
                      endpoints=endpoints(**{"x.locator": locator("CB")}))
        self.rejected("POINT_SELECTOR_NOT_FOUND", endpoint="y", field="endpoints.y.locator",
                      endpoints=endpoints(**{"y.locator": locator("CA", altloc="A")}))

    def test_a_partial_identity_never_matches(self):
        for change in ({"chain": "Z"}, {"residue_id": 99}, {"residue_name": "ALA"},
                       {"segment": 3}, {"group": "HETATM"}, {"insertion_code": "A"}):
            with self.subTest(**change):
                self.rejected("POINT_SELECTOR_NOT_FOUND",
                              endpoints=endpoints(**{"x.locator": locator("N", **change)}))

    def test_selector_resolves_to_several_atoms(self):
        self.rejected("POINT_SELECTOR_AMBIGUOUS", endpoint="y", field="endpoints.y.locator",
                      artifact=artifact("pair_ambiguous.pdb"),
                      coordinate_declaration=declaration(name="pair_ambiguous.pdb"))

    def test_malformed_selector_fails_the_outer_contract(self):
        self.error("INPUT_CONTRACT_INVALID",
                   endpoints=endpoints(**{"x.locator": {"atom_name": "N"}}))
        self.error("INPUT_CONTRACT_INVALID",
                   endpoints=endpoints(**{"x.locator": locator("N", residue_id="1")}))
        self.error("INPUT_CONTRACT_INVALID", endpoints={"x": endpoints()["x"]})


class Coordinates(Contract):
    def test_nonfinite_component(self):
        for name, expected in (("pair_nonfinite.pdb", "nan"), ("pair_infinite.pdb", "inf")):
            with self.subTest(name=name):
                self.rejected("COORDINATE_NONFINITE", endpoint="y",
                              field="endpoints.y.coordinates_nm[0]",
                              artifact=artifact(name),
                              coordinate_declaration=declaration(name=name))

    def test_finite_coordinates_with_an_unrepresentable_distance(self):
        self.rejected("DISTANCE_NONFINITE", field="payload.distance_nm",
                      artifact=artifact("pair_overflow.pdb"),
                      coordinate_declaration=declaration(name="pair_overflow.pdb"))


class Conversion(Contract):
    def test_a_declared_prior_pass_is_a_repeated_conversion(self):
        for key in ("prior_normalization_pass_count", "prior_conversion_count"):
            with self.subTest(key=key):
                self.rejected("COORDINATE_CONVERSION_REPEATED", field=f"source_admission.{key}",
                              source_admission={**SOURCE_ADMISSION, key: 1})

    def test_the_recorded_single_admission_pass_is_not_a_repeated_conversion(self):
        trace = admit().to_dict()["payload"]["endpoints"]["x"]["normalization_trace"]
        self.assertEqual((trace["normalization_pass_count"], trace["conversion_count"]), (1, 0))


class OuterContract(Contract):
    def test_activation_is_required_exactly(self):
        for key, value in (("opt_in", False), ("opt_in", "true"), ("lane", "baseline"),
                           ("input_contract_id", "F01-coordinate-admission-v2")):
            with self.subTest(key=key, value=value):
                self.error("INPUT_CONTRACT_INVALID", activation={**ACTIVATION, key: value})

    def test_layout_and_locator_profile_are_pinned(self):
        self.error("INPUT_CONTRACT_INVALID", artifact=artifact(layout="af3_native_v1"))
        self.error("INPUT_CONTRACT_INVALID",
                   locator_profile={**LOCATOR_PROFILE, "profile_version": "2"})

    def test_path_must_be_absolute_canonical_and_a_regular_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            alias = root / "alias.pdb"
            alias.symlink_to(FIXTURES / "pair_unit.pdb")
            for path in ("pair_unit.pdb", str(alias), str(root),
                         str(root / "missing.pdb"), str(root / "sub" / ".." / "alias.pdb")):
                with self.subTest(path=path):
                    self.error("INPUT_CONTRACT_INVALID",
                               artifact={**artifact(), "path": path})

    def test_configuration_provenance_pairing(self):
        snapshot = {"a": 1}
        for value in (
                {"producer_configuration_hash": None, "producer_configuration_missing_reason": None},
                {"producer_configuration_hash": None,
                 "producer_configuration_missing_reason": "unknown"},
                {"producer_configuration": snapshot, "producer_configuration_hash": "0" * 64},
                {"producer_configuration": snapshot},
                {"producer_configuration": snapshot,
                 "producer_configuration_hash": coordinate_digest("producer_configuration", snapshot),
                 "producer_configuration_missing_reason": None}):
            with self.subTest(keys=sorted(value)):
                self.error("INPUT_CONTRACT_INVALID", producer_configuration=value)

    def test_output_declaration_must_use_a_candidate_evidence_context(self):
        self.error("INPUT_CONTRACT_INVALID",
                   output_declaration={**OUTPUT_DECLARATION, "context": "geometry_report"})
        self.error("INPUT_CONTRACT_INVALID",
                   output_declaration={**OUTPUT_DECLARATION, "category": ""})

    def test_source_admission_counts_must_be_declared(self):
        self.error("INPUT_CONTRACT_INVALID", source_admission={"prior_conversion_count": 0})
        self.error("INPUT_CONTRACT_INVALID",
                   source_admission={**SOURCE_ADMISSION, "prior_conversion_count": -1})

    def test_a_lone_surrogate_in_a_top_level_identity_field_is_refused(self):
        """A Python string may hold a code point UTF-8 cannot encode; that is malformed input."""
        for label, over in (
                ("artifact.artifact_id", dict(artifact=artifact(artifact_id="syn-\ud800"))),
                ("declaration.frame_id", dict(coordinate_declaration=declaration(frame="\ud800"))),
                ("declaration.coordinate_declaration_id",
                 dict(coordinate_declaration=declaration(declaration_id="decl-\udfff"))),
                ("output_declaration.category",
                 dict(output_declaration={**OUTPUT_DECLARATION, "category": "geo\ud834"}))):
            with self.subTest(field=label):
                failure = self.error("INPUT_CONTRACT_INVALID", **over)
                self.assertIn("UTF-8", str(failure))
                self.assertIn("surrogate", str(failure))

    def test_a_lone_surrogate_in_an_endpoint_or_locator_string_is_refused(self):
        for label, over in (
                ("endpoints.x.point_id", dict(endpoints=endpoints(**{"x.point_id": "pt-\ud800"}))),
                ("endpoints.y.frame_id", dict(endpoints=endpoints(**{"y.frame_id": "\udbff"}))),
                ("endpoints.x.locator.atom_name",
                 dict(endpoints=endpoints(**{"x.locator": locator("\ud800")})))):
            with self.subTest(field=label):
                failure = self.error("INPUT_CONTRACT_INVALID", **over)
                self.assertIn("UTF-8", str(failure))

    def test_a_lone_surrogate_request_reads_no_artifact_and_runs_no_parser(self):
        chosen, declared = artifact(), declaration()  # built before recording
        opened, parsed, real = [], [], builtins.open

        def record(target, *args, **kwargs):
            if not isinstance(target, int):
                opened.append(os.fspath(target))
            return real(target, *args, **kwargs)

        with patch.object(builtins, "open", record), patch.object(io, "open", record), \
                patch.object(f01, "read_structure", lambda *a, **k: parsed.append(a)):
            with self.assertRaises(F01CoordinateAdmissionError) as caught:
                admit(artifact=chosen, coordinate_declaration=declared,
                      endpoints=endpoints(**{"x.point_id": "pt-\ud800"}))
        self.assertEqual(caught.exception.code, "INPUT_CONTRACT_INVALID")
        self.assertEqual(parsed, [])
        self.assertNotIn(chosen["path"], opened)
        schemas = Path(f01.__file__).resolve().parent / "schemas"
        self.assertEqual({Path(p).resolve() for p in opened
                          if Path(p).resolve().parent != schemas}, set())

    def test_valid_non_ascii_text_is_unaffected(self):
        frame = "cadre-étalon-体系-\U0001f9ed"
        result = admit(coordinate_declaration=declaration(frame=frame),
                       endpoints=endpoints(frame=frame, **{"x.point_id": "pt-é"}),
                       output_declaration={**OUTPUT_DECLARATION, "category": "géométrie"})
        self.assertEqual(result.status, "COMPUTED")
        self.assertEqual(result.distance_nm, 5.0)
        data = result.to_dict()
        self.assertEqual(data["payload"]["endpoints"]["x"]["frame_id"], frame)
        self.assertEqual(data["output_metric"]["category"], "géométrie")
        raw = result.to_json_bytes()
        self.assertEqual(raw.decode("utf-8").count(frame) > 0, True)
        self.assertEqual(F01CoordinateDistance.from_dict(data).to_json_bytes(), raw)


class Canonicalization(unittest.TestCase):
    def test_number_rendering_follows_coordinate_json_v1(self):
        cases = ((0.0, b"0"), (-0.0, b"0"), (5.0, b"5"), (2.5, b"2.5"), (-2.5, b"-2.5"),
                 (0.1, b"0.10000000000000001"), (1e20, b"1e20"), (1e-5, b"1.0000000000000001e-5"),
                 (1e300, b"1.0000000000000001e300"), (1e-300, b"1e-300"), (100000.0, b"100000"))
        for value, expected in cases:
            with self.subTest(value=repr(value)):
                self.assertEqual(coordinate_json(value), expected)

    def test_keys_are_sorted_and_whitespace_is_absent(self):
        self.assertEqual(coordinate_json({"b": 1, "a": [2, 1]}), b'{"a":[2,1],"b":1}')

    def test_control_characters_and_escapes(self):
        self.assertEqual(coordinate_json("\n\t\x00\"\\"), b'"\\u000a\\u0009\\u0000\\"\\\\"')

    def test_non_finite_and_unsupported_types_are_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf"), (1, 2), {1: "a"}, {2.5}):
            with self.subTest(value=repr(value)):
                with self.assertRaises(F01CoordinateAdmissionError):
                    coordinate_json(value)

    def test_text_utf_8_cannot_encode_is_a_contract_failure_not_a_codec_error(self):
        # chr() is used for the nested cases: a surrogate pair written as a source literal
        # is combined into one astral code point, which UTF-8 encodes perfectly well.
        for value in ("\ud800", "\udfff", {"k\ud800": 1}, {"k": ["a", chr(0xDBFF)]},
                      [1.5, chr(0xDC00)]):
            with self.subTest(value=repr(value)):
                with self.assertRaises(F01CoordinateAdmissionError) as caught:
                    coordinate_json(value)
                self.assertEqual(caught.exception.code, "INPUT_CONTRACT_INVALID")
                self.assertIn("UTF-8", str(caught.exception))

    def test_valid_non_ascii_text_canonicalizes_to_exact_utf_8_bytes(self):
        for value, expected in (("é", '"é"'), ("体系", '"体系"'),
                                ("\U0001f9ed", '"\U0001f9ed"'),
                                ({"é": 1, "é": 2}, '{"é":2,"é":1}')):
            with self.subTest(value=repr(value)):
                raw = coordinate_json(value)
                self.assertEqual(raw, expected.encode("utf-8"))
                self.assertEqual(raw.decode("utf-8"), expected)

    def test_digests_are_separated_by_object_kind(self):
        obj = {"a": 1}
        kinds = {coordinate_digest(kind, obj) for kind in
                 ("coordinate_declaration", "normalization_trace", "endpoint_mapping",
                  "result_payload", "producer_configuration", "f01_coordinate_distance_result")}
        self.assertEqual(len(kinds), 6)


class Serialization(Contract):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def test_identical_requests_are_byte_identical(self):
        self.assertEqual(admit().to_json_bytes(), admit().to_json_bytes())
        self.assertEqual(admit().result_id, admit().result_id)

    def test_export_reload_reserialize_is_stable(self):
        for over in ({}, {"coordinate_declaration": declaration(source_unit="angstrom")}):
            with self.subTest(status="COMPUTED" if not over else "REJECTED"):
                original = admit(**over)
                path = self.root / f"result_{len(over)}.json"
                path.write_bytes(original.to_json_bytes())
                reloaded = load_f01_coordinate_distance(path)
                self.assertEqual(reloaded.to_json_bytes(), original.to_json_bytes())
                self.assertEqual(reloaded.result_id, original.result_id)
                self.assertEqual(reloaded.status, original.status)
                again = self.root / f"again_{len(over)}.json"
                again.write_bytes(reloaded.to_json_bytes())
                self.assertEqual(again.read_bytes(), path.read_bytes())
                self.assertEqual(reloaded.execution_metadata, {})

    def tampered(self, mutate):
        data = admit().to_dict()
        mutate(data)
        with self.assertRaises(F01CoordinateAdmissionError) as caught:
            F01CoordinateDistance.from_dict(data)
        self.assertEqual(caught.exception.code, "RESULT_INVALID", str(caught.exception))

    def test_tampering_is_rejected(self):
        for mutate in (
                lambda d: d.update(result_id="0" * 64),
                lambda d: d.update(status="REJECTED"),
                lambda d: d["output_metric"].update(value=7.0),
                lambda d: d["payload"].update(distance_nm=7.0),
                lambda d: d["payload"]["endpoints"]["x"].update(coordinates_nm=[1.0, 0.0, 0.0]),
                lambda d: d["payload"]["endpoints"]["y"]["normalization_trace"].update(
                    normalized_coordinates=[3.0, 4.0, 1.0]),
                lambda d: d["payload"]["endpoints"]["y"].update(normalization_trace_sha256="0" * 64),
                lambda d: d["payload"].update(coordinate_declaration_sha256="0" * 64),
                lambda d: d["payload"].update(endpoint_mapping_sha256="0" * 64),
                lambda d: d.update(payload_sha256="0" * 64),
                lambda d: d["payload"].update(producer_configuration_missing_reason=None),
                lambda d: d["payload"].update(producer_configuration_hash="0" * 64),
                lambda d: d["observation"]["resolution"]["x"].update(source_coordinates=[1.0, 0.0, 0.0]),
                lambda d: d["request"]["coordinate_declaration"].update(frame_id="frame-02"),
                lambda d: d["checks"][0].update(result="NOT_REACHED"),
                lambda d: d.update(diagnostic={"code": "X", "endpoint": None, "field": None,
                                               "detail": "invented"})):
            with self.subTest():
                self.tampered(mutate)

    def test_a_consistently_relabelled_rejection_is_still_rejected(self):
        data = admit(coordinate_declaration=declaration(source_unit="angstrom")).to_dict()
        data["status"] = "COMPUTED"
        data["diagnostic"] = None
        data["payload"]["distance_nm"] = 5.0
        data["output_metric"]["value"] = 5.0
        for check in data["checks"]:
            check["result"] = "PASSED"
        without = {k: v for k, v in data.items() if k != "result_id"}
        data["result_id"] = coordinate_digest("f01_coordinate_distance_result", without)
        with self.assertRaises(F01CoordinateAdmissionError) as caught:
            F01CoordinateDistance.from_dict(data)
        self.assertEqual(caught.exception.code, "RESULT_INVALID")

    def test_reload_refuses_a_document_that_is_not_this_contract(self):
        path = self.root / "other.json"
        path.write_bytes(b'{"schema_version": "pointwise_measurement/1"}')
        with self.assertRaises(F01CoordinateAdmissionError) as caught:
            load_f01_coordinate_distance(path)
        self.assertEqual(caught.exception.code, "RESULT_INVALID")

    def test_reload_refuses_duplicate_keys_and_non_finite_tokens(self):
        for raw in (b'{"a": 1, "a": 2}', b'{"payload": {"distance_nm": NaN}}'):
            with self.subTest(raw=raw[:20]):
                path = self.root / f"bad_{len(raw)}.json"
                path.write_bytes(raw)
                with self.assertRaises(F01CoordinateAdmissionError):
                    load_f01_coordinate_distance(path)


class Reading(Contract):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def test_only_the_selected_artifact_is_opened(self):
        shutil.copy(FIXTURES / "pair_unit.pdb", self.root / "pair_unit.pdb")
        decoy = self.root / "decoy_unselected.pdb"
        shutil.copy(FIXTURES / "decoy_unselected.pdb", decoy)
        chosen, declared = artifact(root=self.root), declaration(root=self.root)
        opened, real = [], builtins.open

        def record(target, *args, **kwargs):
            if not isinstance(target, int):
                opened.append(os.fspath(target))
            return real(target, *args, **kwargs)

        with patch.object(builtins, "open", record), patch.object(io, "open", record):
            result = admit(artifact=chosen, coordinate_declaration=declared)
        self.assertEqual(result.status, "COMPUTED")
        schemas = Path(f01.__file__).resolve().parent / "schemas"
        outside = {Path(p).resolve() for p in opened if Path(p).resolve().parent != schemas}
        self.assertEqual(sorted(outside), [Path(chosen["path"]).resolve()])
        self.assertNotIn(str(decoy), opened)
        self.assertGreaterEqual(sum(p == chosen["path"] for p in opened), 2)


class EvidenceConversion(Contract):
    def test_a_computed_result_converts_to_one_metric(self):
        result = admit()
        metric = to_candidate_evidence_metric(result, source_path="/synthetic/selected/pair_unit.pdb")
        self.assertEqual(metric, {
            "name": "distance_nm", "raw_value": 5.0, "value": 5.0, "context": "complex",
            "category": "declared_geometry", "unit": "nm", "scale": None,
            "source": {"path": "/synthetic/selected/pair_unit.pdb",
                       "sha256": digest_of(FIXTURES / "pair_unit.pdb"), "row": None},
            "provenance": {"model_id": None, "checkpoint_id": None, "seed": None},
            "missing_reason": None})
        record = CandidateEvidence(candidate_id="syn-pair", sequence_hash=None,
                                   target_id="syn-target", conformer_id=None, metrics=[metric],
                                   missing_values={"sequence_hash": "synthetic fixture",
                                                   "conformer_id": "synthetic fixture"})
        self.assertEqual(record.to_dict()["metrics"][0], metric)

    def test_a_rejected_result_does_not_convert(self):
        result = admit(coordinate_declaration=declaration(source_unit="angstrom"))
        with self.assertRaises(F01CoordinateAdmissionError) as caught:
            to_candidate_evidence_metric(result, source_path="/synthetic/selected/pair_unit.pdb")
        self.assertEqual(caught.exception.code, "INPUT_CONTRACT_INVALID")

    def test_conversion_refuses_a_bare_document_or_an_empty_path(self):
        result = admit()
        with self.assertRaises(F01CoordinateAdmissionError):
            to_candidate_evidence_metric(result.to_dict(), source_path="/synthetic/p.pdb")
        with self.assertRaises(F01CoordinateAdmissionError):
            to_candidate_evidence_metric(result, source_path="")


if __name__ == "__main__":
    unittest.main()
