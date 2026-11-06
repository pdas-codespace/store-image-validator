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
    """Fraction of rules whose effective status matches the human rule adjudication.
    For raw agent output the confidence gate from the pinned rule pack is applied first."""
    resp, out = _parse(sample, item)
    gt = json.loads(item["ground_truth"])
    expected = gt["expected"]["rules"]
    if "effective_rule_results" in resp:
        got = {r["rule_id"]: r["status"] for r in resp["effective_rule_results"] or []}
    else:
        floor = gt["rule_pack"]["scoring"].get("min_rule_confidence", 0.0)
        got = {}
        for r in out.get("rule_results", []):
            s = r.get("status")
            if s in ("PASS", "FAIL") and r.get("confidence", 0) < floor:
                s = "CANNOT_DETERMINE"
            got[r.get("rule_id")] = s
    if not expected:
        return 1.0
    return sum(1 for k, v in expected.items() if got.get(k) == v) / len(expected)
