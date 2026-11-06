"""Versioned rule-pack loading with explicit version resolution (no fallback)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import REPO_ROOT
from .jsonschema_lite import validate

RULES_DIR = REPO_ROOT / "rules"
SCHEMA_PATH = RULES_DIR / "schema" / "rule-pack.schema.json"

# Extensible rule-type registry. Each entry tells the agent how to reason about the
# type; adding a rule pack made of these types needs no category-specific code.
RULE_TYPES: dict[str, str] = {
    "visual_presence": "PASS only if the required item is visibly present. If the area where it should be is not visible, CANNOT_DETERMINE (not FAIL).",
    "visual_absence": "PASS only if the relevant area is visible and the item is absent. Not visible -> CANNOT_DETERMINE.",
    "prohibited_visual": "FAIL only if the prohibited item is visible inside the scoped area. Honour 'ignore' scopes. Scoped area not visible -> CANNOT_DETERMINE.",
    "text_legibility": "PASS only if the text can be read without guessing letters. Blur, glare or distance that prevents reading -> CANNOT_DETERMINE.",
    "count_or_quantity": "Count only clearly distinguishable items. Partial view of the counting area -> CANNOT_DETERMINE.",
    "spatial_relationship": "Judge relative placement only when both referenced objects are visible.",
    "condition_or_cleanliness": "Judge condition from visible surfaces only; do not extrapolate to unseen areas.",
    "coverage_or_full_view": "PASS only if the full required extent (or an accepted alternative) is in frame.",
    "comparison_to_reference": "Compare against the supplied reference example; no reference -> CANNOT_DETERMINE.",
    "seal_or_label_integrity": "Seal/label must be visible and intact; occluded seal -> CANNOT_DETERMINE.",
    "date_or_code_readability": "Every required character must be legible; otherwise CANNOT_DETERMINE.",
}


class RulePackError(Exception):
    """Raised when a rule pack cannot be resolved or is invalid. Never falls back."""


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    type: str
    weight: float
    mandatory: bool
    requirement: str
    accepted_alternatives: tuple[str, ...] = ()
    cannot_determine_when: tuple[str, ...] = ()
    ignore: tuple[str, ...] = ()

    def agent_view(self) -> dict[str, Any]:
        """What the model sees. Weights and mandatory flags are business-owned and withheld."""
        view = {
            "rule_id": self.id, "title": self.title, "type": self.type,
            "type_guidance": RULE_TYPES[self.type], "requirement": self.requirement.strip(),
        }
        if self.accepted_alternatives:
            view["accepted_alternatives"] = list(self.accepted_alternatives)
        if self.cannot_determine_when:
            view["cannot_determine_when"] = list(self.cannot_determine_when)
        if self.ignore:
            view["ignore"] = list(self.ignore)
        return view


@dataclass(frozen=True)
class RulePack:
    id: str
    version: str
    category: str
    customer_id: str
    effective_from: str
    min_images: int
    max_images: int
    review_threshold: float
    pass_threshold: float
    score_min: float
    score_max: float
    cannot_determine_credit: float
    min_rule_confidence: float
    abstention_prefix: str
    rules: tuple[Rule, ...] = field(default_factory=tuple)
    source_path: str = ""

    def rule(self, rule_id: str) -> Rule:
        for r in self.rules:
            if r.id == rule_id:
                return r
        raise KeyError(rule_id)

    @property
    def rule_ids(self) -> list[str]:
        return [r.id for r in self.rules]


def _parse(doc: dict, source: str) -> RulePack:
    errors = validate(doc, json.loads(SCHEMA_PATH.read_text()))
    if errors:
        raise RulePackError(f"{source} failed schema validation: " + "; ".join(errors))
    ids = [r["id"] for r in doc["rules"]]
    if len(ids) != len(set(ids)):
        raise RulePackError(f"{source}: duplicate rule ids")
    s = doc["scoring"]
    if not s["reviewThreshold"] <= s["passThreshold"]:
        raise RulePackError(f"{source}: reviewThreshold must be <= passThreshold")
    rules = tuple(
        Rule(
            id=r["id"], title=r["title"], type=r["type"], weight=float(r["weight"]),
            mandatory=bool(r["mandatory"]), requirement=r["requirement"],
            accepted_alternatives=tuple(r.get("acceptedAlternatives", [])),
            cannot_determine_when=tuple(r.get("cannotDetermineWhen", [])),
            ignore=tuple(r.get("ignore", [])),
        )
        for r in doc["rules"]
    )
    return RulePack(
        id=doc["rulePackId"], version=str(doc["version"]), category=doc["category"],
        customer_id=doc.get("customerId", ""), effective_from=str(doc["effectiveFrom"]),
        min_images=doc["captureRequirements"]["minimumImages"],
        max_images=doc["captureRequirements"]["maximumImages"],
        review_threshold=float(s["reviewThreshold"]), pass_threshold=float(s["passThreshold"]),
        score_min=float(s["range"]["minimum"]), score_max=float(s["range"]["maximum"]),
        cannot_determine_credit=float(s.get("cannotDetermineCredit", 0.5)),
        min_rule_confidence=float(s.get("minimumRuleConfidence", 0.65)),
        abstention_prefix=doc["response"]["abstentionPrefix"], rules=rules, source_path=source,
    )


def load_rule_pack(rule_pack_id: str, version: str, rules_dir: Path = RULES_DIR) -> RulePack:
    """Load exactly `<id>-<version>.yaml`. Unknown versions raise; there is no 'latest' fallback."""
    if not version or version.lower() in {"latest", "*"}:
        raise RulePackError("An explicit rule-pack version is required (no 'latest').")
    matches = list(rules_dir.glob(f"*/{rule_pack_id}-{version}.yaml"))
    if len(matches) != 1:
        raise RulePackError(f"Rule pack {rule_pack_id}@{version} not found (found {len(matches)} files).")
    doc = yaml.safe_load(matches[0].read_text())
    pack = _parse(doc, str(matches[0].relative_to(rules_dir.parent)))
    if pack.id != rule_pack_id or pack.version != version:
        raise RulePackError(f"File {matches[0].name} declares {pack.id}@{pack.version}, expected {rule_pack_id}@{version}.")
    return pack


def validate_all(rules_dir: Path = RULES_DIR) -> dict[str, str]:
    """Validate every rule pack file. Returns {path: 'ok' | error}."""
    results = {}
    for path in sorted(rules_dir.glob("*/*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text())
            _parse(doc, path.name)
            expected = f"{doc['rulePackId']}-{doc['version']}.yaml"
            results[str(path)] = "ok" if path.name == expected else f"file name should be {expected}"
        except Exception as exc:  # noqa: BLE001
            results[str(path)] = str(exc)
    return results
