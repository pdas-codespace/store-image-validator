import json


def grade(sample, item) -> float:
    """0.0 on a false pass: overall PASS when humans said otherwise, or a mandatory rule
    marked PASS when humans marked it FAIL / CANNOT_DETERMINE. 1.0 otherwise."""
    resp, gt = json.loads(item["response"]), json.loads(item["ground_truth"])
    if resp.get("decision") == "PASS" and gt["expected"]["decision"] != "PASS":
        return 0.0
    got = {r["rule_id"]: r["status"] for r in resp.get("effective_rule_results", [])}
    for rule in gt["rule_pack"]["rules"]:
        if rule["mandatory"] and got.get(rule["id"]) == "PASS" and gt["expected"]["rules"].get(rule["id"]) != "PASS":
            return 0.0
    return 1.0
