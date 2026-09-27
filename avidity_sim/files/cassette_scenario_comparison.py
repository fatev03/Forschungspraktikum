"""Read-only comparison of finished candidate-priority reports.

No evaluator, classifier, provider, hash or I/O path is invoked here. Run links
are caller declarations, not resolved locators or kernel identities. A missing
ledger context hash stays missing. Ranks are copied dense group ordinals, not
scores; evidence never participates in comparison. Structural incompatibility
returns NOT_COMPARABLE diagnostics rather than a repaired or partial comparison.

The two public records store immutable JSON snapshots and expose fresh display
documents. This also protects them from mutable containers inside upstream
frozen dataclasses. No upstream report is reconstructed or reevaluated.
"""

from __future__ import annotations

import json
from dataclasses import InitVar, dataclass, field
from typing import Optional, Sequence

from .cassette_candidate_batch import CandidateBatchReport
from .cassette_candidate_priority import (
    CandidatePriorityReport,
    IneligibilityReason,
    PRIORITY_DISPLAY_DISCLAIMER,
    PRIORITY_DOCUMENT_TYPE,
    PRIORITY_NON_CLAIM,
    TIER_ORDER,
)

__all__ = [
    "ScenarioDeclaration", "ScenarioComparisonReport", "compare_scenarios", "render_lines",
]


def _bytes(document) -> bytes:
    return json.dumps(document, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ScenarioDeclaration:
    """Explicit run association plus snapshots of two already-finished reports.

    Empty/None metadata and incompatible reports are retained as diagnostics by
    compare_scenarios. Labels and references are never filled or normalized.
    Other metadata types raise TypeError; only strings or explicit absence are
    meaningful declarations. A run reference alone is not proof of provenance.
    """

    scenario_id: Optional[str]
    label: Optional[str]
    evaluation_run_ref: Optional[str]
    batch_report: InitVar[CandidateBatchReport]
    priority_report: InitVar[CandidatePriorityReport]
    _batch: Optional[bytes] = field(init=False, repr=False)
    _priority: Optional[bytes] = field(init=False, repr=False)
    _shape_errors: tuple[str, ...] = field(init=False, repr=False)

    def __post_init__(self, batch_report, priority_report):
        for name in ("scenario_id", "label", "evaluation_run_ref"):
            value = getattr(self, name)
            if value is not None and type(value) is not str:
                raise TypeError(f"{name} must be a plain str or None")
        errors = []
        for name, value, expected in (
            ("_batch", batch_report, CandidateBatchReport),
            ("_priority", priority_report, CandidatePriorityReport),
        ):
            snapshot = None
            if type(value) is not expected:
                errors.append(f"{name[1:]} must be {expected.__name__}")
            else:
                try:
                    snapshot = _bytes(value.as_dict())
                except (AttributeError, KeyError, TypeError, ValueError) as exc:
                    errors.append(f"{name[1:]} has incompatible fields: {type(exc).__name__}")
            object.__setattr__(self, name, snapshot)
        object.__setattr__(self, "_shape_errors", tuple(errors))

    def as_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "label": self.label,
            "evaluation_run_ref": self.evaluation_run_ref,
            "batch_report": None if self._batch is None else json.loads(self._batch),
            "priority_report": None if self._priority is None else json.loads(self._priority),
        }


@dataclass(frozen=True, slots=True)
class ScenarioComparisonReport:
    """Immutable presentation snapshot produced by compare_scenarios."""

    _document: bytes = field(repr=False)

    def __post_init__(self):
        if type(self._document) is not bytes:
            raise TypeError("report storage must be immutable bytes")

    def as_dict(self) -> dict:
        return json.loads(self._document)

    @property
    def ordering_stability(self) -> str:
        return self.as_dict()["ordering_stability"]

    @property
    def eligibility_changed(self) -> Optional[bool]:
        return self.as_dict()["eligibility_changed"]

    @property
    def stable_top(self) -> Optional[bool]:
        return self.as_dict()["stable_top"]


def _present(value) -> bool:
    return type(value) is str and bool(value.strip())


def _check(condition, detail):
    if not condition:
        raise ValueError(detail)


def _shape(batch, priority):
    """Structural checks only; deliberately no eligibility/tier derivation."""
    _check(type(batch) is dict and type(priority) is dict, "reports must be present")
    _check(batch["document_type"] == "cassette_candidate_batch/1", "batch document type")
    _check(priority["document_type"] == PRIORITY_DOCUMENT_TYPE, "priority document type")
    _check(priority["non_claim"] == PRIORITY_NON_CLAIM, "priority non-claim")
    for seq in (batch["entries"], batch["candidate_order"], priority["candidate_order"],
                priority["groups"], priority["excluded"]):
        _check(type(seq) is list, "report sequences must be arrays")
    for cid in batch["candidate_order"] + priority["candidate_order"]:
        _check(type(cid) is str and cid != "", "candidate identifiers must be nonempty strings")
    tiers = [tier.value for tier in TIER_ORDER]
    seen_tiers = []
    for index, group in enumerate(priority["groups"], 1):
        _check(type(group["rank"]) is int and group["rank"] == index, "dense group ranks")
        _check(group["geometry_tier"] in tiers, "unknown geometry tier")
        seen_tiers.append(group["geometry_tier"])
        _check(type(group["members"]) is list and bool(group["members"]), "empty/malformed group")
        for member in group["members"]:
            _check(member["geometry_tier"] == group["geometry_tier"], "member/group tier mismatch")
            _check(type(member["certificate_present"]) is bool, "certificate flag must be boolean")
            _check(type(member["tier_basis"]) is list, "tier basis must be an array")
    _check(seen_tiers == [tier for tier in tiers if tier in seen_tiers], "tier order/duplication")
    records = [m for g in priority["groups"] for m in g["members"]] + priority["excluded"]
    for record in batch["entries"] + records:
        for key in ("candidate_id", "slot_binding_hash"):
            _check(type(record[key]) is str and record[key] != "", f"invalid {key}")
    for entry in batch["entries"]:
        ledger, refusal = entry["ledger"], entry["refusal"]
        _check(entry["entry_kind"] in ("EVALUATED", "DECLARATION_REFUSED"), "unknown entry kind")
        if entry["entry_kind"] == "EVALUATED":
            _check(type(ledger) is dict and refusal is None, "evaluated entry shape")
            _check(type(ledger["rows"]) is list, "ledger rows must be an array")
            _check([r["slot"] for r in ledger["rows"]] == ["slot_1", "slot_2", "slot_3"],
                   "ledger must retain all three ordered slots")
            for key in ("context_hash", "config_identity_hash", "state_result_id"):
                _check(ledger[key] is None or (type(ledger[key]) is str and ledger[key] != ""),
                       f"invalid ledger {key}")
            _check(type(ledger["certificate_present"]) is bool, "ledger certificate flag")
        else:
            _check(ledger is None and type(refusal) is dict, "refused entry shape")
    for excluded in priority["excluded"]:
        _check(excluded["ineligibility_reason"] in [r.value for r in IneligibilityReason],
               "unknown exclusion reason")
        _check(type(excluded["vetoed_slots"]) is list, "vetoed slots must be an array")
    return records


def _validate_scenario(document, add):
    batch, priority = document["batch_report"], document["priority_report"]
    try:
        records = _shape(batch, priority)
        order = priority["candidate_order"]
        ids = [r["candidate_id"] for r in records]
        if len(set(order)) != len(order) or len(set(ids)) != len(ids) or set(ids) != set(order):
            add("INCOMPLETE_CANDIDATE_COVERAGE", "Each candidate must occur exactly once, ranked or excluded.")
            return
        entries = batch["entries"]
        if batch["candidate_order"] != order or [e["candidate_id"] for e in entries] != order:
            add("BATCH_REPORT_MISMATCH", "Batch and priority candidate sequences differ.")
            return
        for seq in ([m["candidate_id"] for m in g["members"]] for g in priority["groups"]):
            _check(seq == [cid for cid in order if cid in seq], "tie members are not in caller order")
        excluded_order = [e["candidate_id"] for e in priority["excluded"]]
        _check(excluded_order == [cid for cid in order if cid in excluded_order],
               "exclusions are not in caller order")
        lookup = {r["candidate_id"]: r for r in records}
        contexts = []
        for entry in entries:
            cid = entry["candidate_id"]
            record, ledger, refusal = lookup[cid], entry["ledger"], entry["refusal"]
            matches = record["slot_binding_hash"] == entry["slot_binding_hash"]
            if ledger is not None:
                matches &= ledger["slot_binding_hash"] == entry["slot_binding_hash"]
                ctx = ledger["context_hash"]
                if ctx is not None and ctx not in contexts:
                    contexts.append(ctx)
            if "geometry_tier" in record:
                matches &= ledger is not None
                if ledger is not None:
                    matches &= all(record[k] == ledger[k] for k in ("state_result_id", "certificate_present"))
                    keys = ("slot", "label", "node_presence", "failure_class")
                    matches &= record["tier_basis"] == [{k: row[k] for k in keys} for row in ledger["rows"]]
            else:
                row = None if ledger is None else ledger["rows"][0]
                matches &= all(record[k] == (None if row is None else row[k])
                               for k in ("state_status", "state_status_reason"))
                matches &= all(record["refusal_" + k] == (None if refusal is None else refusal[k])
                               for k in ("stage", "error_class", "detail"))
                if refusal is not None:
                    matches &= refusal["candidate_id"] == cid
                _check(all(s in ("slot_1", "slot_2", "slot_3") for s in record["vetoed_slots"]),
                       "unknown vetoed slot")
            if not matches:
                add("BATCH_REPORT_MISMATCH", "Copied batch/priority fields disagree.", cid)
        if len(contexts) > 1:
            add("CONTEXT_ASSOCIATION_AMBIGUOUS", "Non-null ledger context hashes disagree within this scenario.")
    except (AttributeError, KeyError, TypeError, ValueError):
        add("INCOMPATIBLE_REPORT_SHAPE", "Reports do not satisfy the finished-report shape/order contract.")


def _observations(scenario):
    report = scenario["priority_report"]
    observations = {}
    for group in report["groups"]:
        members = [m["candidate_id"] for m in group["members"]]
        for member in group["members"]:
            observations[member["candidate_id"]] = {
                "scenario_id": scenario["scenario_id"], "eligible": True,
                "rank": group["rank"], "geometry_tier": group["geometry_tier"],
                "tie_members": list(members), "exclusion": None,
            }
    for entry in report["excluded"]:
        observations[entry["candidate_id"]] = {
            "scenario_id": scenario["scenario_id"], "eligible": False,
            "rank": None, "geometry_tier": None, "tie_members": [], "exclusion": entry,
        }
    return observations


def compare_scenarios(scenarios: Sequence[ScenarioDeclaration]) -> ScenarioComparisonReport:
    """Compare declared orderings, never evaluate them. No implicit baseline.

    Movement names refer to adjacent scenarios in the supplied sequence, not
    improvement or causality. Structural diagnostics suppress comparison. An
    all-excluded scenario only makes ordering/top undefined: eligibility changes
    are still visible. Unknown context hashes are retained, not inferred.
    """
    if type(scenarios) not in (list, tuple):
        raise TypeError("scenarios must be an explicitly ordered list or tuple")
    declarations = tuple(scenarios)
    documents, diagnostics, seen = [], [], set()

    def add(code, detail, cid=None, position=None, sid=None):
        diagnostics.append({"code": code, "scenario_position": position,
                            "scenario_id": sid, "candidate_id": cid, "detail": detail})

    if len(declarations) < 2:
        add("INSUFFICIENT_SCENARIO_COUNT", "At least two scenarios are required.")
    for position, scenario in enumerate(declarations, 1):
        if type(scenario) is not ScenarioDeclaration:
            documents.append(None)
            add("INCOMPATIBLE_REPORT_SHAPE", "Expected ScenarioDeclaration.", position=position)
            continue
        document = scenario.as_dict()
        documents.append(document)

        def local(code, detail, cid=None):
            add(code, detail, cid, position, scenario.scenario_id)

        for key, code in (("scenario_id", "SCENARIO_ID_MISSING"),
                          ("label", "SCENARIO_LABEL_MISSING"),
                          ("evaluation_run_ref", "EVALUATION_RUN_REF_MISSING")):
            if not _present(document[key]):
                local(code, f"An explicit nonempty {key} is required.")
        if _present(scenario.scenario_id):
            if scenario.scenario_id in seen:
                local("SCENARIO_ID_DUPLICATE", "Scenario identity is repeated; nothing is deduplicated.")
            seen.add(scenario.scenario_id)
        if scenario._shape_errors:
            local("INCOMPATIBLE_REPORT_SHAPE", "; ".join(scenario._shape_errors))
        else:
            _validate_scenario(document, local)

    order = []
    if not diagnostics:
        order = documents[0]["priority_report"]["candidate_order"]
        bindings = []
        for document in documents:
            report = document["priority_report"]
            bindings.append({r["candidate_id"]: r["slot_binding_hash"]
                             for r in [m for g in report["groups"] for m in g["members"]] + report["excluded"]})
        if not order:
            add("EMPTY_CANDIDATE_UNIVERSE", "No candidates were supplied.")
        for position, document in enumerate(documents[1:], 2):
            other = document["priority_report"]["candidate_order"]
            sid = document["scenario_id"]
            if set(other) != set(order):
                missing = [cid for cid in order if cid not in other]
                extra = [cid for cid in other if cid not in order]
                add("CANDIDATE_UNIVERSE_MISMATCH", f"Missing: {missing!r}; extra: {extra!r}.",
                    position=position, sid=sid)
            elif other != order:
                add("CANDIDATE_ORDER_MISMATCH", "Caller candidate sequences differ; no reordering is allowed.",
                    position=position, sid=sid)
            else:
                for cid in order:
                    if bindings[position - 1][cid] != bindings[0][cid]:
                        add("SLOT_BINDING_MISMATCH", "Candidate binding identity differs across scenarios.",
                            cid, position, sid)

    movements, top_groups = [], []
    stability, eligibility_changed, stable_top = "NOT_COMPARABLE", None, None
    if not diagnostics:
        observed = [_observations(d) for d in documents]
        eligibility_changed = False
        partitions = []
        for position, document in enumerate(documents, 1):
            groups = document["priority_report"]["groups"]
            partitions.append([[m["candidate_id"] for m in g["members"]] for g in groups])
            top_groups.append({"scenario_id": document["scenario_id"],
                               "candidate_ids": [] if not groups else partitions[-1][0]})
            if not groups:
                add("ALL_EXCLUDED_SCENARIO", "Every candidate is explicitly excluded; ordering/top are unavailable.",
                    position=position, sid=document["scenario_id"])
        for cid in order:
            values = [o[cid] for o in observed]
            changes = []
            for left, right in zip(values, values[1:]):
                kinds = []
                if left["eligible"] != right["eligible"]:
                    eligibility_changed = True
                    kinds.append("BECAME_RANKED" if right["eligible"] else "BECAME_EXCLUDED")
                elif not right["eligible"]:
                    kinds.append("REMAINED_EXCLUDED")
                    if left["exclusion"] != right["exclusion"]:
                        kinds.append("EXCLUSION_DETAILS_CHANGED")
                else:
                    for key, kind in (("rank", "RANK_CHANGED"), ("geometry_tier", "TIER_CHANGED"),
                                      ("tie_members", "TIE_GROUP_CHANGED")):
                        if left[key] != right[key]:
                            kinds.append(kind)
                changes.append({"from_scenario_id": left["scenario_id"],
                                "to_scenario_id": right["scenario_id"], "kinds": kinds or ["UNCHANGED"]})
            movements.append({"candidate_id": cid, "slot_binding_hash": bindings[0][cid],
                              "observations": values, "changes": changes})
        if not diagnostics:
            stability = "STABLE" if all(p == partitions[0] for p in partitions[1:]) else "UNSTABLE"
            stable_top = all(t["candidate_ids"] == top_groups[0]["candidate_ids"] for t in top_groups[1:])
    else:
        order = []  # No common order is asserted when inputs are incompatible.

    if eligibility_changed or stability == "UNSTABLE":
        conclusion = "Ordering and/or eligibility differs across the declared scenarios."
    elif stability == "STABLE":
        conclusion = "Ordering is stable across the declared scenarios."
    else:
        conclusion = ""
    if stability == "NOT_COMPARABLE":
        conclusion += (" " if conclusion else "") + "Ordering is not comparable: " + ", ".join(
            d["code"] for d in diagnostics) + "."
    conclusion += " Declared-scenario comparison only; no biological or physical truth claim."
    return ScenarioComparisonReport(_bytes({
        "scenario_order": [None if d is None else d["scenario_id"] for d in documents],
        "candidate_order": order, "scenarios": documents, "movements": movements,
        "top_groups": top_groups, "ordering_stability": stability,
        "eligibility_changed": eligibility_changed, "stable_top": stable_top,
        "diagnostics": diagnostics, "conclusion": conclusion,
    }))


def render_lines(report: ScenarioComparisonReport) -> list[str]:
    """One comparison table, movement summary and contract-safe conclusion."""
    if type(report) is not ScenarioComparisonReport:
        raise TypeError("report must be ScenarioComparisonReport")
    data = report.as_dict()

    def cell(value):
        # Escape display delimiters only; as_dict preserves every literal.
        return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\r", "\\r").replace("\n", "\\n")

    lines = PRIORITY_NON_CLAIM.split("\n") + ["", PRIORITY_DISPLAY_DISCLAIMER, "", "Declared scenarios (caller-supplied run links):"]
    for position, scenario in enumerate(data["scenarios"], 1):
        if scenario is None:
            lines.append(f"{position}. unavailable declaration")
        else:
            lines.append(f"{position}. {cell(scenario['scenario_id'])} — {cell(scenario['label'])}; run {cell(scenario['evaluation_run_ref'])}")
    lines += ["Context hashes, where present, remain in the copied batch ledgers; missing hashes are unavailable.", ""]
    if data["movements"]:
        lines += [" | ".join(["Candidate"] + [cell(s) for s in data["scenario_order"]]),
                  " | ".join(["---"] * (len(data["scenario_order"]) + 1))]
        for movement in data["movements"]:
            cells = [cell(movement["candidate_id"])]
            for observation in movement["observations"]:
                cells.append(f"rank {observation['rank']} · {observation['geometry_tier']}" if observation["eligible"]
                             else "EXCLUDED · " + cell(observation["exclusion"]["ineligibility_reason"]))
            lines.append(" | ".join(cells))
        lines += ["", "Movement/eligibility (adjacent declared scenarios; not improvement):"]
        for movement in data["movements"]:
            changes = [f"{cell(c['from_scenario_id'])} → {cell(c['to_scenario_id'])}: {', '.join(c['kinds'])}"
                       for c in movement["changes"]]
            lines.append(f"{cell(movement['candidate_id'])}: " + "; ".join(changes))
    else:
        lines.append("Comparison table and movement summary unavailable; source snapshots remain in the report.")
    lines.append("Stable top group: " + ("unavailable" if data["stable_top"] is None else str(data["stable_top"]).lower()))
    for top in data["top_groups"]:
        lines.append(f"{cell(top['scenario_id'])} top tie group: " + (", ".join(cell(cid) for cid in top["candidate_ids"]) or "none (all excluded)"))
    for diagnostic in data["diagnostics"]:
        lines.append(f"{diagnostic['code']} [scenario {diagnostic['scenario_position']}, candidate {cell(diagnostic['candidate_id'])}]: {cell(diagnostic['detail'])}")
    return lines + ["", data["conclusion"]]
