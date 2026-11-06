import json

REQUIRED = ["schema_version", "submission_id", "category", "rule_pack", "image_assessment",
            "observations", "rule_results", "uncertainties", "recommended_next_image"]
STATUSES = {"PASS", "FAIL", "CANNOT_DETERMINE", "NOT_APPLICABLE"}


def _parse(sample, item):
    """Accept a decision record (rows mode) or raw agent JSON (agent-target mode)."""
    raw = item.get("response") if isinstance(item, dict) else None
    if not raw and isinstance(sample, dict):
        raw = sample.get("output_text")
    resp = json.loads(raw) if isinstance(raw, str) else (raw or {})
    out = resp.get("agent_output") if "agent_output" in resp else resp
    return resp, (out or {})


def grade(sample, item) -> float:
    """1.0 when the agent output parsed and passed the contract (the pipeline enforces the
    full JSON Schema; this re-checks the essentials so cloud runs can score it too)."""
    try:
        resp, out = _parse(sample, item)
    except (ValueError, TypeError):
        return 0.0
    if not isinstance(out, dict) or any(k not in out for k in REQUIRED):
        return 0.0
    if "score" in out or "decision" in out:
        return 0.0  # the agent must never return authoritative score/decision
    return 1.0 if all(r.get("status") in STATUSES for r in out["rule_results"]) else 0.0
