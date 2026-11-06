"""Regrade exported responses independently; never mistake runtime failures for quality."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.run_foundry_eval import AGENT_LEVEL  # noqa: E402
from siv.evaluation import ground_truth, load_dataset, load_evaluators  # noqa: E402


def review(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("The export contains no evaluation output items.")
    labels = {row["id"]: row for row in load_dataset(["golden", "challenge", "abstention", "adversarial"])}
    evaluators = load_evaluators()
    cases = []
    for row in rows:
        data = row["datasource_item"]
        case_id = data["id"]
        if case_id not in labels or json.loads(data["ground_truth"]) != ground_truth(labels[case_id]):
            raise ValueError(f"{case_id}: ground truth does not match the current frozen local dataset.")
        response = data.get("sample.output_text")
        runtime_error = (row.get("sample") or {}).get("error")
        cloud = {}
        for name in AGENT_LEVEL:
            scores = [result["score"] for result in row["results"]
                      if result["name"] == name and isinstance(result.get("score"), (float, int))]
            if len(scores) != 1:
                raise ValueError(f"{case_id}: expected one numeric cloud score for {name}, got {len(scores)}.")
            cloud[name] = scores[0]
        local = None
        if not runtime_error and response:
            local = {name: evaluators[name]({}, {"response": response, "ground_truth": data["ground_truth"]})
                     for name in AGENT_LEVEL}
        cases.append({
            "id": case_id, "agent_name": data.get("agent_name"), "agent_version": data.get("agent_version"),
            "runtime_failed": bool(runtime_error) or not bool(response),
            "cloud_scores": cloud, "independent_local_scores": local,
            "mismatches": [name for name in AGENT_LEVEL if local is not None and abs(local[name] - cloud[name]) > 1e-8],
        })
    successful = [case for case in cases if not case["runtime_failed"]]
    return {
        "run_ids": sorted({row["run_id"] for row in rows}), "rows": len(cases),
        "successful_responses": len(successful), "runtime_failures": len(cases) - len(successful),
        "cloud_local_mismatches": sum(len(case["mismatches"]) for case in cases),
        "successful_response_local_means": {
            name: statistics.mean(case["independent_local_scores"][name] for case in successful)
            if successful else None for name in AGENT_LEVEL
        },
        "cases": cases,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path)
    ap.add_argument("--summary", type=Path)
    args = ap.parse_args()
    rows = [json.loads(line) for line in args.results.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    summary = review(rows)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "cases"}, indent=2))
    for case in summary["cases"]:
        print(f"{case['id']}: local={case['independent_local_scores']} mismatches={case['mismatches']}")
    if summary["runtime_failures"] or summary["cloud_local_mismatches"]:
        sys.exit("Measurement blocked: inspect runtime failures / cloud-local grading differences before comparing models.")


if __name__ == "__main__":
    main()
