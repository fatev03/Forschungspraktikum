"""Phase 1c remediation regression tests.

Every test here was written BEFORE the corresponding fix and fails on the
0.3.0-phase1c baseline. Each class names the finding it pins (B = blocker,
H = high) so the audit trail is explicit.

Assertion style follows the Phase 1c complete-diagnosis policy: diagnostic-code
MEMBERSHIP, never exclusivity.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import unittest
from dataclasses import dataclass, replace
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from gotne import cassette_topology  # noqa: E402
from gotne.cassette_schema import (  # noqa: E402
    MISSING,
    AnchorSpec,
    EngagementOrderPolicy,
    TetherSpec,
    TopologyMode,
)
from gotne.cassette_topology import (  # noqa: E402
    Code,
    Reason,
    validate_cassette_config,
    validate_cassette_order_constraints,
    validate_cassette_policy_fields,
    validate_cassette_topology,
)
from gotne.identity import (  # noqa: E402
    CanonicalizationError,
    cache_key,
    canonical_form,
    config_identity_hash,
)
from gotne.mode_applicability import mode_applicability  # noqa: E402
from gotne.status import (  # noqa: E402
    Status,
    apply_status_field_pattern,
    make_config_result,
)
from test_cassette_topology import (  # noqa: E402
    CassetteTestCase,
    base_policy,
    module,
    ref_cassette_3,
)

ALL_STAGES = (
    validate_cassette_policy_fields,
    validate_cassette_topology,
    validate_cassette_order_constraints,
    validate_cassette_config,
)


def _with_segments(cfg, segments):
    return replace(cfg, cassettes=(replace(cfg.cassettes[0], ordered_segments=segments),))


# --------------------------------------------------------------------------
# B1 -- duplicate module identifiers accepted (last declaration wins)
# --------------------------------------------------------------------------
class B1DuplicateModuleId(CassetteTestCase):
    def _variants(self):
        cfg = ref_cassette_3()
        broken_d3 = module("D3", 3, terminal=True, exclusion_centre=MISSING)
        good_d3 = cfg.modules[2]
        return (
            replace(cfg, modules=cfg.modules[:2] + (broken_d3, good_d3)),
            replace(cfg, modules=cfg.modules[:2] + (good_d3, broken_d3)),
        )

    def test_duplicate_module_id_rejected(self):
        for cfg in self._variants():
            result = validate_cassette_topology(cfg)
            self.assertTopologyRejection(result, Code.DUPLICATE_IDENTIFIER)
            d = next(x for x in result.diagnostics if x.code == Code.DUPLICATE_IDENTIFIER)
            self.assertEqual(d.quantities["id"], "D3")
            self.assertEqual(d.quantities["namespace"], "node")
            self.assertEqual(d.quantities["count"], 2)

    def test_verdict_does_not_depend_on_declaration_order(self):
        a, b = self._variants()
        ra, rb = validate_cassette_config(a), validate_cassette_config(b)
        self.assertIs(ra.status, rb.status)
        self.assertEqual(ra.status_reason, rb.status_reason)
        self.assertIs(ra.status, Status.INFEASIBLE)

    def test_offset_checks_skipped_not_guessed(self):
        """C10a/C10b must not read one arbitrary copy of a duplicated module."""
        result = validate_cassette_topology(self._variants()[0])
        skipped = {
            x.quantities.get("check")
            for x in result.diagnostics
            if x.code == Code.CHECK_SKIPPED
        }
        self.assertIn("C10b", skipped)
        self.assertNotIn(Code.TERMINAL_EXCLUSION_CENTRE_MISSING, result.codes())


# --------------------------------------------------------------------------
# B2 -- duplicate anchor ids, anchor/module id collision, duplicate tether ids
# --------------------------------------------------------------------------
class B2DuplicateOtherIdentifiers(CassetteTestCase):
    def test_duplicate_anchor_id_rejected(self):
        cfg = ref_cassette_3()
        cfg = replace(cfg, anchors=cfg.anchors + (AnchorSpec(id="a0", surface_id="S9"),))
        result = validate_cassette_config(cfg)
        self.assertTopologyRejection(result, Code.DUPLICATE_IDENTIFIER)

    def test_anchor_module_namespace_collision_rejected(self):
        cfg = ref_cassette_3()
        cfg = replace(cfg, anchors=cfg.anchors + (AnchorSpec(id="D2"),))
        result = validate_cassette_topology(cfg)
        self.assertTopologyRejection(result, Code.DUPLICATE_IDENTIFIER)
        d = next(x for x in result.diagnostics if x.code == Code.DUPLICATE_IDENTIFIER)
        self.assertEqual(d.quantities["id"], "D2")
        self.assertEqual(sorted(d.quantities["kinds"]), ["anchor", "module"])

    def test_duplicate_tether_id_rejected(self):
        cfg = ref_cassette_3()
        tethers = (
            cfg.tethers[0],
            TetherSpec(id="s1", from_node="D1", to_node="D2"),
            TetherSpec(id="s1", from_node="D2", to_node="D3"),
        )
        cfg = _with_segments(replace(cfg, tethers=tethers), ("s0", "s1", "s1"))
        result = validate_cassette_config(cfg)
        self.assertTopologyRejection(result, Code.DUPLICATE_IDENTIFIER)
        d = next(x for x in result.diagnostics if x.code == Code.DUPLICATE_IDENTIFIER)
        self.assertEqual(d.quantities["namespace"], "tether")


# --------------------------------------------------------------------------
# B3 -- invalid topology_mode falls back to NOT_APPLICABLE / VALID
# --------------------------------------------------------------------------
class B3TopologyModeFailClosed(CassetteTestCase):
    BAD_MODES = (MISSING, None, "LINEAR_ORDERED_CASSETTE", "GENERAL_DAG", "garbage", 1)

    def test_every_stage_rejects_invalid_mode(self):
        for mode in self.BAD_MODES:
            cfg = replace(ref_cassette_3(), policy=base_policy(topology_mode=mode))
            for stage in ALL_STAGES:
                with self.subTest(mode=repr(mode), stage=stage.__name__):
                    result = stage(cfg)
                    self.assertIs(result.status, Status.INFEASIBLE)
                    self.assertEqual(result.status_reason, Reason.POLICY_MISSING)
                    self.assertCode(result, Code.TOPOLOGY_MODE_MISSING)
                    self.assertVetoFieldPattern(result)

    def test_general_dag_enum_still_not_applicable(self):
        cfg = replace(
            ref_cassette_3(), policy=base_policy(topology_mode=TopologyMode.GENERAL_DAG)
        )
        for stage in ALL_STAGES:
            with self.subTest(stage=stage.__name__):
                result = stage(cfg)
                self.assertEqual(result.status_reason, Reason.NOT_APPLICABLE)
                self.assertIs(result.status, Status.NOT_EVALUATED)  # v0.3.1 §3.1.1


# --------------------------------------------------------------------------
# B4 -- repr-based / non-injective identity hashing
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class _LookalikeAnchor:
    id: str
    surface_id: object = None
    position: object = MISSING
    normal: object = MISSING


class _Opaque:
    pass


class B4IdentityHashing(CassetteTestCase):
    def test_enum_and_plain_string_mode_do_not_collide(self):
        enum_cfg = ref_cassette_3()
        str_cfg = replace(
            enum_cfg, policy=base_policy(topology_mode="LINEAR_ORDERED_CASSETTE")
        )
        self.assertNotEqual(config_identity_hash(enum_cfg), config_identity_hash(str_cfg))

    def test_missing_sentinel_does_not_collide_with_its_token_string(self):
        cfg = ref_cassette_3()
        a = replace(cfg, modules=(module("D1", 1, exclusion_centre=MISSING),) + cfg.modules[1:])
        b = replace(
            cfg, modules=(module("D1", 1, exclusion_centre="__MISSING__"),) + cfg.modules[1:]
        )
        self.assertNotEqual(config_identity_hash(a), config_identity_hash(b))

    def test_dataclass_type_is_part_of_identity(self):
        self.assertNotEqual(
            canonical_form(AnchorSpec(id="x")), canonical_form(_LookalikeAnchor(id="x"))
        )

    def test_int_and_str_dict_keys_do_not_collide(self):
        self.assertNotEqual(canonical_form({1: "a"}), canonical_form({"1": "a"}))

    def test_unsupported_types_raise_instead_of_repr(self):
        for value in (_Opaque(), {"a", "b"}, frozenset({"a"}), b"bytes", 1 + 2j):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(CanonicalizationError):
                    canonical_form(value)

    def test_unordered_declared_value_rejected_by_config_hash(self):
        cfg = ref_cassette_3()
        cfg = replace(
            cfg,
            cassettes=(replace(cfg.cassettes[0], explicit_partial_order={("D1", "D2")}),),
        )
        with self.assertRaises(CanonicalizationError):
            config_identity_hash(cfg)

    def test_hash_is_stable_across_interpreter_hash_seeds(self):  # T78, strengthened
        root = pathlib.Path(__file__).resolve().parents[1]
        code = (
            "import sys; sys.path[:0]=[{r!r},{t!r}];"
            "from test_cassette_topology import ref_cassette_3;"
            "from gotne.identity import config_identity_hash;"
            "print(config_identity_hash(ref_cassette_3()))"
        ).format(r=str(root), t=str(root / "tests"))
        outs = set()
        for seed in ("1", "2", "977"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            outs.add(
                subprocess.run(
                    [sys.executable, "-c", code], env=env, capture_output=True,
                    text=True, check=True,
                ).stdout.strip()
            )
        self.assertEqual(len(outs), 1, outs)

    def test_cache_key_rejects_non_enum_topology_mode(self):
        with self.assertRaises(TypeError):
            cache_key("D2", "S0", "P0", "G0", "T0", "1.0.0", "LINEAR_ORDERED_CASSETTE")

    def test_cache_key_rejects_non_string_component(self):
        with self.assertRaises(TypeError):
            cache_key("D2", None, "P0", "G0", "T0", "1.0.0", TopologyMode.GENERAL_DAG)


# --------------------------------------------------------------------------
# B5 -- a stage that skipped its own checks reports VALID
# --------------------------------------------------------------------------
class B5SkippedStageIsNotValid(CassetteTestCase):
    def assertNotEvaluated(self, result):
        self.assertIs(result.status, Status.NOT_EVALUATED)
        self.assertTrue(result.nulled_due_to_status)
        self.assertFalse(result.zeroed_due_to_status)
        self.assertCode(result, Code.CHECK_SKIPPED)

    def test_order_stage_with_two_cassettes(self):
        cfg = ref_cassette_3()
        cfg = replace(cfg, cassettes=cfg.cassettes * 2)
        self.assertNotEvaluated(validate_cassette_order_constraints(cfg))

    def test_order_stage_explicit_policy_without_order(self):
        cfg = ref_cassette_3(
            policy=base_policy(
                engagement_order_policy=EngagementOrderPolicy.EXPLICIT_PARTIAL_ORDER
            )
        )
        self.assertNotEvaluated(validate_cassette_order_constraints(cfg))

    def test_composed_path_unchanged_for_two_cassettes(self):
        cfg = ref_cassette_3()
        cfg = replace(cfg, cassettes=cfg.cassettes * 2)
        self.assertTopologyRejection(validate_cassette_config(cfg), Code.CASSETTE_COUNT_INVALID)

    def test_composition_never_upgrades_a_non_valid_stage_to_valid(self):
        """precedence() ranks VALID above NOT_EVALUATED (§3.3), so composition
        must not rely on it alone."""
        cfg = ref_cassette_3()
        not_evaluated = make_config_result(
            object_id=cfg.id,
            status=Status.NOT_EVALUATED,
            status_reason=Reason.PREREQUISITE_FAILED,
            diagnostics=(),
        )
        with mock.patch.object(
            cassette_topology,
            "validate_cassette_order_constraints",
            return_value=not_evaluated,
        ):
            result = cassette_topology.validate_cassette_config(cfg)
        self.assertIsNot(result.status, Status.VALID)


# --------------------------------------------------------------------------
# B6 -- tether not belonging to the cassette silently accepted
# --------------------------------------------------------------------------
class B6DanglingTether(CassetteTestCase):
    def test_disconnected_tether_between_undeclared_nodes_rejected(self):
        cfg = ref_cassette_3()
        cfg = replace(
            cfg,
            tethers=cfg.tethers + (TetherSpec(id="sx", from_node="ghost", to_node="ghost2"),),
        )
        result = validate_cassette_config(cfg)
        self.assertTopologyRejection(result, Code.SEGMENT_SEQUENCE_INVALID)
        flagged = {
            x.quantities.get("tether")
            for x in result.diagnostics
            if x.code == Code.SEGMENT_SEQUENCE_INVALID
        }
        self.assertIn("sx", flagged)


# --------------------------------------------------------------------------
# H1 -- bool / float index coerced through ==
# --------------------------------------------------------------------------
class H1IndexTypeCoercion(CassetteTestCase):
    def test_bool_module_index_rejected(self):
        cfg = ref_cassette_3()
        cfg = replace(cfg, modules=(module("D1", True),) + cfg.modules[1:])
        self.assertTopologyRejection(validate_cassette_topology(cfg), Code.INDEX_SEQUENCE_INVALID)

    def test_float_module_index_rejected(self):
        cfg = ref_cassette_3()
        cfg = replace(cfg, modules=(cfg.modules[0], module("D2", 2.0), cfg.modules[2]))
        self.assertTopologyRejection(validate_cassette_topology(cfg), Code.INDEX_SEQUENCE_INVALID)

    def test_bool_tether_index_rejected(self):
        cfg = ref_cassette_3()
        cfg = replace(cfg, tethers=(replace(cfg.tethers[0], cassette_index=False),) + cfg.tethers[1:])
        self.assertTopologyRejection(
            validate_cassette_topology(cfg), Code.SEGMENT_SEQUENCE_INVALID
        )


# --------------------------------------------------------------------------
# H2 -- §10.1 field pattern passes unknown fields / unknown statuses through
# --------------------------------------------------------------------------
class H2FieldPatternFailClosed(unittest.TestCase):
    def test_unknown_field_under_veto_raises(self):
        with self.assertRaises(ValueError):
            apply_status_field_pattern(Status.INFEASIBLE, {"p_typo": 0.7})

    def test_unknown_field_under_valid_raises(self):
        with self.assertRaises(ValueError):
            apply_status_field_pattern(Status.VALID, {"joint_scor": 0.7})

    def test_non_status_value_raises(self):
        for bad in ("FOO", "INFEASIBLE", None):
            with self.subTest(status=bad):
                with self.assertRaises(TypeError):
                    apply_status_field_pattern(bad, {"conditional_probability": 0.7})

    def test_known_density_field_still_nulled_under_veto(self):
        out, zeroed, _ = apply_status_field_pattern(
            Status.UNREACHABLE, {"conditional_density": 3.0}
        )
        self.assertIsNone(out["conditional_density"])
        self.assertTrue(zeroed)


# --------------------------------------------------------------------------
# H3 -- mode_applicability treats a plain string mode as APPLICABLE
# --------------------------------------------------------------------------
class H3ModeApplicabilityType(unittest.TestCase):
    def test_string_mode_rejected(self):
        with self.assertRaises(TypeError):
            mode_applicability("T12", "LINEAR_ORDERED_CASSETTE")


# --------------------------------------------------------------------------
# H4 -- explicit_partial_order presence rule (D8)
# --------------------------------------------------------------------------
class H4ExplicitOrderPresence(CassetteTestCase):
    def test_policy_stage_checks_every_cassette(self):
        cfg = ref_cassette_3(
            policy=base_policy(
                engagement_order_policy=EngagementOrderPolicy.EXPLICIT_PARTIAL_ORDER
            )
        )
        cfg = replace(cfg, cassettes=cfg.cassettes * 2)
        result = validate_cassette_policy_fields(cfg)
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertCode(result, Code.EXPLICIT_ORDER_MISSING)

    def test_declared_null_is_not_missing_under_any_order(self):
        """D8: explicit_partial_order must be MISSING unless the policy is
        EXPLICIT_PARTIAL_ORDER. Declared null is declared (D7)."""
        cfg = ref_cassette_3()
        cfg = replace(
            cfg, cassettes=(replace(cfg.cassettes[0], explicit_partial_order=None),)
        )
        result = validate_cassette_policy_fields(cfg)
        self.assertIs(result.status, Status.INFEASIBLE)
        self.assertCode(result, Code.EXPLICIT_ORDER_UNEXPECTED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
