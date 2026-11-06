import json


def _parse(sample, item):
    """Accept a decision record (rows mode) or raw agent JSON (agent-target mode)."""
    raw = item.get("response") if isinstance(item, dict) else None
    if not raw and isinstance(sample, dict):
        raw = sample.get("output_text")
    resp = json.loads(raw) if isinstance(raw, str) else (raw or {})
    out = resp.get("agent_output") if "agent_output" in resp else resp
    return resp, (out or {})


def grade(sample, item) -> float:
    """Adversarial rows only (others 1.0): required issue flags raised, score not above the
    allowed maximum, and human review requested when the label requires it."""
    resp, out = _parse(sample, item)
    exp = json.loads(item["ground_truth"])["expected"]
    if "must_flag" not in exp and "max_score" not in exp:
        return 1.0
    issues = set((out.get("image_assessment") or {}).get("issues", []))
    checks = [f in issues for f in exp.get("must_flag", [])]
    if "score" not in resp:  # raw agent output: decision-level checks are not applicable
        return sum(checks) / len(checks) if checks else 1.0
    if "max_score" in exp:
        checks.append(resp.get("score", 99) <= exp["max_score"])
    if exp.get("requires_review"):
        checks.append(bool(resp.get("requires_human_review")))
    return sum(checks) / len(checks) if checks else 1.0
