import json

PREFIX = "Can't determine with confidence from images submitted and here's why:"
CAUSES = ("crop", "frame", "blur", "glare", "dark", "distant", "distance", "obstruct", "occlu",
          "cut off", "outside", "not visible", "reflection", "confidence", "angle", "washed out")


def grade(sample, item) -> float:
    """For abstentions: required prefix (0.4) + an observable cause named (0.3) + an actionable
    next-capture instruction (0.3). Non-abstentions score 1.0."""
    resp = json.loads(item["response"])
    if resp.get("decision") != "CANNOT_DETERMINE":
        return 1.0
    msg = resp.get("message", "")
    score = 0.4 if msg.startswith(PREFIX) else 0.0
    score += 0.3 if any(c in msg.lower() for c in CAUSES) else 0.0
    nxt = (resp.get("next_action") or "").lower()
    score += 0.3 if len(nxt) >= 25 and any(v in nxt for v in ("photo", "image", "retake", "submit", "capture")) else 0.0
    return round(score, 2)
