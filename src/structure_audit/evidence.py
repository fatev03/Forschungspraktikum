"""Supplied evidence records and independent thresholds; no composite score."""
from copy import deepcopy
from dataclasses import dataclass, field, asdict
import hashlib
import math

from .validation import validate_named


def sequence_hash(sequence):
    """Hash exact supplied sequence text; never normalize or generate residues."""
    if not isinstance(sequence, str) or not sequence:
        raise ValueError("Sequence must be nonempty supplied text")
    return hashlib.sha256(sequence.encode("utf-8")).hexdigest()


@dataclass
class CandidateEvidence:
    candidate_id: str
    sequence_hash: str | None
    target_id: str | None
    conformer_id: str | None
    metrics: list = field(default_factory=list)
    provenance: dict = field(default_factory=lambda: {"model_id": None, "checkpoint_id": None, "seed": None})
    warnings: list = field(default_factory=list)
    missing_values: dict = field(default_factory=dict)
    schema_version: str = "1.0"

    def to_dict(self):
        result = asdict(self)
        validate_named(result, "candidate_evidence")
        for key in ("sequence_hash", "target_id", "conformer_id"):
            if result[key] is None and not self.missing_values.get(key):
                raise ValueError(f"Missing {key} requires a missing_values explanation")
        seen = set()
        for metric in self.metrics:
            key = (metric["context"], metric["name"])
            if key in seen:
                raise ValueError(f"Ambiguous duplicate metric {key}")
            seen.add(key)
            if metric["value"] is None and not metric["missing_reason"]:
                raise ValueError("Null metric value requires a missing_reason")
        return result


def supplied_metric(name, raw, *, context, category, source, provenance,
                    unit=None, scale=None, missing_reason=None):
    value = raw if type(raw) in (int, float) and math.isfinite(raw) else None
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = float(raw)
            if math.isfinite(parsed):
                value = parsed
        except ValueError:
            pass
    # JSON cannot carry IEEE NaN/Infinity as a number. Preserve the token explicitly.
    if type(raw) is float and not math.isfinite(raw):
        raw = repr(raw)
    return {"name": name, "raw_value": deepcopy(raw), "value": value,
            "context": context, "category": category, "unit": unit, "scale": scale,
            "source": source, "provenance": dict(provenance),
            "missing_reason": (missing_reason or "not supplied or not a finite scalar") if value is None else None}


def filter_candidates(candidates, rules, *, missing="exclude"):
    """Return decisions with reasons, retaining independent metric dimensions.

    rules: [{context, name, min?: number, max?: number}]. No default scientific
    thresholds. missing='include' retains candidates with explicit warnings.
    """
    if missing not in ("exclude", "include", "error"):
        raise ValueError("missing must be exclude, include, or error")
    for rule in rules:
        if set(rule) - {"context", "name", "min", "max"} or not {"context", "name"} <= set(rule) or not ("min" in rule or "max" in rule):
            raise ValueError("Invalid filter rule")
        for bound in ("min", "max"):
            if bound in rule and (type(rule[bound]) not in (int, float) or not math.isfinite(rule[bound])):
                raise ValueError("Filter bounds must be finite numbers")
        if rule.get("min", -math.inf) > rule.get("max", math.inf):
            raise ValueError("Filter minimum exceeds maximum")
    decisions = []
    ids = set()
    for candidate in candidates:
        data = candidate.to_dict() if isinstance(candidate, CandidateEvidence) else CandidateEvidence(**candidate).to_dict()
        if data["candidate_id"] in ids:
            raise ValueError("Duplicate candidate_id")
        ids.add(data["candidate_id"])
        metrics = {(m["context"], m["name"]): m for m in data["metrics"]}
        accepted, reasons = True, []
        for rule in rules:
            key = (rule["context"], rule["name"])
            metric = metrics.get(key)
            value = metric["value"] if metric else None
            if value is None:
                if missing == "error":
                    raise ValueError(f"{data['candidate_id']}: missing metric {key}")
                accepted = accepted and missing == "include"
                reasons.append(f"missing {key}; policy={missing}")
            elif not rule.get("min", -math.inf) <= value <= rule.get("max", math.inf):
                accepted = False
                reasons.append(f"outside configured bounds: {key}={value}")
        decisions.append({"candidate_id": data["candidate_id"], "accepted": accepted,
                          "reasons": reasons, "rules": deepcopy(rules), "missing_policy": missing})
    return decisions
