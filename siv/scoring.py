"""Deterministic decision engine. The model never owns score or business thresholds."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .rulepack import RulePack

PASS, FAIL, CD, NA = "PASS", "FAIL", "CANNOT_DETERMINE", "NOT_APPLICABLE"


@dataclass
class Decision:
    decision: str
    score: int
    raw_score: float
    requires_human_review: bool
    review_reasons: list[str]
    effective_rule_results: list[dict]
    gate_adjustments: list[dict]
    message: str
    next_action: str | None
    abstention_reason: str | None = None
    extra: dict = field(default_factory=dict)


def _round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def apply_confidence_gate(pack: RulePack, rule_results: list[dict]) -> tuple[list[dict], list[dict]]:
    """Low-confidence PASS/FAIL becomes CANNOT_DETERMINE. Returns (effective results, adjustments)."""
    effective, adjustments = [], []
    for r in rule_results:
        r = dict(r)
        if r["status"] in (PASS, FAIL) and r["confidence"] < pack.min_rule_confidence:
            adjustments.append({"rule_id": r["rule_id"], "from": r["status"], "to": CD,
                                "reason": f"confidence {r['confidence']:.2f} < {pack.min_rule_confidence}"})
            r["original_status"] = r["status"]
            r["status"] = CD
            r["missing_evidence"] = list(r.get("missing_evidence", [])) + [
                f"Model confidence {r['confidence']:.2f} below threshold {pack.min_rule_confidence}"]
        effective.append(r)
    return effective, adjustments


def weighted_score(pack: RulePack, rule_results: list[dict]) -> float:
    credit = {PASS: 1.0, FAIL: 0.0, CD: pack.cannot_determine_credit}
    by_id = {r["rule_id"]: r for r in rule_results}
    num = den = 0.0
    for rule in pack.rules:
        status = by_id[rule.id]["status"]
        if status == NA:
            continue
        num += rule.weight * credit[status]
        den += rule.weight
    if den == 0:
        return pack.score_min
    return pack.score_min + (pack.score_max - pack.score_min) * num / den


def decide(pack: RulePack, agent_result: dict, *, policy_ok: bool = True) -> Decision:
    """Spec section 7 policy, made explicit.

    1. Unusable image package            -> CANNOT_DETERMINE, score 0.
    2. Confidence gate per rule.
    3. Any mandatory FAIL                 -> FAIL.
    4. Any mandatory CANNOT_DETERMINE     -> CANNOT_DETERMINE (+ review).
    5. Score < reviewThreshold with a FAIL -> FAIL.
    6. Any other CANNOT_DETERMINE         -> CANNOT_DETERMINE (PASS needs full evidence).
    7. Score >= passThreshold             -> PASS; review band -> FAIL + review; else FAIL.
    """
    ia = agent_result["image_assessment"]
    review: list[str] = []
    if not policy_ok:
        review.append("policy_retrieval_failed")
    if "CONTRADICTORY_IMAGES" in ia.get("issues", []):
        review.append("contradictory_images")
    if "UNSUPPORTED_CATEGORY" in ia.get("issues", []):
        review.append("category_appears_incorrect")
    if "UNSAFE_IMAGE_INSTRUCTION" in ia.get("issues", []):
        review.append("unsafe_image_instruction")

    effective, adjustments = apply_confidence_gate(pack, agent_result["rule_results"])
    if adjustments:
        review.append("low_confidence_rule")

    if not ia["usable"]:
        reasons = _cd_reasons(effective, agent_result) or ["The submitted images are not usable for inspection."]
        return _abstain(pack, 0, 0.0, effective, adjustments, review, reasons, agent_result)

    raw = weighted_score(pack, effective)
    score = _round_half_up(raw)
    by_id = {r["rule_id"]: r for r in effective}
    mandatory = [r for r in pack.rules if r.mandatory]
    statuses = [r["status"] for r in effective]

    if any(by_id[r.id]["status"] == FAIL for r in mandatory):
        return _final(FAIL, score, raw, effective, adjustments, review, agent_result, pack)
    if any(by_id[r.id]["status"] == CD for r in mandatory):
        review.append("mandatory_rule_cannot_determine")
        return _abstain(pack, score, raw, effective, adjustments, review, _cd_reasons(effective, agent_result), agent_result)
    if FAIL in statuses and raw < pack.review_threshold:
        return _final(FAIL, score, raw, effective, adjustments, review, agent_result, pack)
    if CD in statuses:
        return _abstain(pack, score, raw, effective, adjustments, review, _cd_reasons(effective, agent_result), agent_result)
    if raw >= pack.pass_threshold:
        return _final(PASS, score, raw, effective, adjustments, review, agent_result, pack)
    if raw >= pack.review_threshold:
        review.append("score_in_review_band")
    return _final(FAIL, score, raw, effective, adjustments, review, agent_result, pack)


def _cd_reasons(effective: list[dict], agent_result: dict) -> list[str]:
    reasons = []
    for r in effective:
        if r["status"] == CD:
            missing = "; ".join(r.get("missing_evidence") or [])
            line = f"{r['rule_id']}: {r.get('reason', '').strip()}"
            if missing:
                line += f" Could not verify: {missing}."
            reasons.append(line)
    return reasons


def _abstain(pack, score, raw, effective, adjustments, review, reasons, agent_result) -> Decision:
    next_action = agent_result.get("recommended_next_image") or \
        "Submit one centered, well-lit image showing the complete storefront, including the sign, all entrance doors and windows."
    body = "\n".join(f"- {x}" for x in reasons)
    message = f"{pack.abstention_prefix}\n{body}\n\nScore: {score}/10\nDecision: {CD}\nNext action: {next_action}"
    return Decision(CD, score, round(raw, 3), bool(review), sorted(set(review)),
                    effective, adjustments, message, next_action, abstention_reason="; ".join(reasons))


def _final(decision, score, raw, effective, adjustments, review, agent_result, pack) -> Decision:
    fails = [f"{r['rule_id']}: {r['reason']}" for r in effective if r["status"] == FAIL]
    lines = [f"Decision: {decision}", f"Score: {score}/10"]
    if fails:
        lines.append("Failed rules:\n" + "\n".join(f"- {x}" for x in fails))
    return Decision(decision, score, round(raw, 3), bool(review), sorted(set(review)), effective,
                    adjustments, "\n".join(lines), None)
