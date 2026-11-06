import json


def grade(sample, item) -> float:
    """0.0 when a case humans judged PASS was rejected (FAIL). Abstention is not a false fail."""
    resp, gt = json.loads(item["response"]), json.loads(item["ground_truth"])
    return 0.0 if gt["expected"]["decision"] == "PASS" and resp.get("decision") == "FAIL" else 1.0
