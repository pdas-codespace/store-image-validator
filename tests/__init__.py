import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="siv-tests-")
os.environ.setdefault("SIV_TRACE_FILE", os.path.join(_TMP, "traces.jsonl"))
os.environ.setdefault("SIV_RESULTS_DIR", os.path.join(_TMP, "results"))
