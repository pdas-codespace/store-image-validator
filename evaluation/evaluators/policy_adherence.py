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
    """1.0 when the agent evaluated exactly the pinned rule-pack id/version and exactly its rules."""
    _, out = _parse(sample, item)
    pack = json.loads(item["ground_truth"])["rule_pack"]
    if out.get("rule_pack") != {"id": pack["id"], "version": pack["version"]}:
        return 0.0
    got = sorted(r.get("rule_id") for r in out.get("rule_results", []))
    return 1.0 if got == sorted(r["id"] for r in pack["rules"]) else 0.0
