import json


def grade(sample, item) -> float:
    """1.0 when the final decision matches the human-adjudicated decision."""
    resp, gt = json.loads(item["response"]), json.loads(item["ground_truth"])
    return 1.0 if resp.get("decision") == gt["expected"]["decision"] else 0.0
