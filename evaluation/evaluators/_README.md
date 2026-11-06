Each `*.py` here (except files starting with `_`) is a self-contained, stdlib-only
code evaluator exposing `grade(sample, item) -> float` in [0, 1]. The same file text is
uploaded verbatim to Foundry as a code-based evaluator (`run_foundry_eval.py`) and is
imported by the local runner (`run_local_eval.py`), so local and cloud scores match.

`item` fields: `response` (JSON string: decision record) and `ground_truth`
(JSON string: human label + business config of the pinned rule pack).
