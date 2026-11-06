import json


def grade(sample, item) -> float:
    """1.0 when the system abstained (CANNOT_DETERMINE) exactly when humans say it should.
    Precision/recall are aggregated by the runner from this per-row signal."""
    resp, gt = json.loads(item["response"]), json.loads(item["ground_truth"])
    should = gt["expected"]["decision"] == "CANNOT_DETERMINE"
    did = resp.get("decision") == "CANNOT_DETERMINE"
    return 1.0 if should == did else 0.0
