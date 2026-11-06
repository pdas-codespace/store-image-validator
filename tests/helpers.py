import copy
import json
import tempfile
from pathlib import Path

from siv import REPO_ROOT
from siv.analyzers import Analyzer, AnalyzerResult
from siv.analyzers.replay import ReplayAnalyzer
from siv.pipeline import inspect
from siv.store import ResultStore

IMG = REPO_ROOT / "fixtures" / "images"
REPLAY = REPO_ROOT / "evaluation" / "replay"


def recording(case_id: str) -> dict:
    return json.loads((REPLAY / f"{case_id}.json").read_text())


class StaticAnalyzer(Analyzer):
    """Returns a fixed sequence of raw outputs (to test retries, schema rejection, injection)."""
    name = "static"

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def analyze(self, req):
        out = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        if isinstance(out, dict):
            out = copy.deepcopy(out)
            out["submission_id"] = req.submission_id
            out = json.dumps(out)
        return AnalyzerResult(out, model="static", input_tokens=10, output_tokens=5)


def run(image: str, analyzer=None, store=None, **kw):
    store = store or ResultStore(Path(tempfile.mkdtemp()))
    kw.setdefault("rule_pack_id", "contoso-storefront")
    kw.setdefault("rule_pack_version", "1.0.0")
    kw.setdefault("submission_id", f"test-{Path(image).stem}")
    return inspect([str(IMG / image)], analyzer=analyzer or ReplayAnalyzer(), store=store, **kw)
