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
    """Fraction of rule results whose evidence supports the status:
    PASS/FAIL cite >=1 evidence item whose observation exists (or is null) on a known image
    with a valid normalized region; CANNOT_DETERMINE lists missing evidence; reason non-empty."""
    try:
        resp, out = _parse(sample, item)
    except (ValueError, TypeError):
        return 0.0
    obs = {o["observation_id"]: o for o in out.get("observations", [])}
    images = {o["image_id"] for o in out.get("observations", [])} | set(resp.get("image_ids", []))
    results = out.get("rule_results", [])
    if not results:
        return 0.0

    def region_ok(r):
        if r is None:
            return True
        return all(0 <= r[k] <= 1 for k in ("x", "y", "width", "height")) and r["x"] + r["width"] <= 1.0001 \
            and r["y"] + r["height"] <= 1.0001

    good = 0
    for r in results:
        ok = bool(r.get("reason", "").strip())
        if r["status"] in ("PASS", "FAIL"):
            ev = r.get("evidence", [])
            ok = ok and bool(ev) and all(
                (e.get("observation_id") is None or e["observation_id"] in obs)
                and (not images or e["image_id"] in images) and region_ok(e.get("region")) for e in ev)
        elif r["status"] == "CANNOT_DETERMINE":
            ok = ok and bool(r.get("missing_evidence"))
        good += 1 if ok else 0
    return good / len(results)
