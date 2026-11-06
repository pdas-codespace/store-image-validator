import json


def grade(sample, item) -> float:
    """1.0 when the reported score equals the weighted score recomputed from effective rule
    statuses using the pinned rule-pack weights (verifies the model did not own arithmetic)."""
    resp, gt = json.loads(item["response"]), json.loads(item["ground_truth"])
    if resp.get("decision") is None:
        return 0.0
    pack, sc = gt["rule_pack"], gt["rule_pack"]["scoring"]
    if not (resp.get("agent_output") or {}).get("image_assessment", {}).get("usable", True):
        return 1.0 if resp.get("score") == sc["min"] else 0.0
    credit = {"PASS": 1.0, "FAIL": 0.0, "CANNOT_DETERMINE": sc["cannot_determine_credit"]}
    status = {r["rule_id"]: r["status"] for r in resp.get("effective_rule_results", [])}
    num = den = 0.0
    for rule in pack["rules"]:
        s = status.get(rule["id"])
        if s == "NOT_APPLICABLE":
            continue
        if s not in credit:
            return 0.0
        num += rule["weight"] * credit[s]
        den += rule["weight"]
    raw = sc["min"] + (sc["max"] - sc["min"]) * (num / den if den else 0.0)
    return 1.0 if abs(raw - resp.get("raw_score", -99)) < 0.01 and int(raw + 0.5) == resp.get("score") else 0.0
