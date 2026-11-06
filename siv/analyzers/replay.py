"""Replays recorded agent outputs keyed by image content hash.

Used for offline tests, CI smoke runs and deterministic regression of the scoring engine.
Recordings are synthetic and labeled as such in evaluation/replay/index.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from .. import REPO_ROOT
from . import AnalysisRequest, Analyzer, AnalyzerResult

REPLAY_DIR = REPO_ROOT / "evaluation" / "replay"


def replay_key(image_hashes: list[str]) -> str:
    return "+".join(h[:16] for h in image_hashes)


class ReplayAnalyzer(Analyzer):
    name = "replay"

    def __init__(self, replay_dir: Path = REPLAY_DIR):
        self.replay_dir = replay_dir
        self.index = json.loads((replay_dir / "index.json").read_text())["recordings"]

    def analyze(self, req: AnalysisRequest) -> AnalyzerResult:
        key = replay_key([i.sha256 for i in req.images])
        if key not in self.index:
            raise LookupError(f"No replay recording for images {key}. Use --provider foundry-model for new images.")
        doc = json.loads((self.replay_dir / self.index[key]).read_text())
        doc["submission_id"] = req.submission_id  # recordings are submission-agnostic
        return AnalyzerResult(json.dumps(doc), model="replay", input_tokens=0, output_tokens=0)
