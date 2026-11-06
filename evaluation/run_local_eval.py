"""Run the evaluation harness locally / in CI and enforce release gates.

  python evaluation/run_local_eval.py                              # offline replay, all partitions
  python evaluation/run_local_eval.py --provider foundry-model     # real model in your Foundry project
  python evaluation/run_local_eval.py --provider hosted-agent --repeats 3

Writes evaluation/results/<run_id>/report.json and foundry_rows.jsonl (upload with
run_foundry_eval.py --from-rows to see the same rows/scores in the Foundry portal).
Exit code 1 when any release gate fails.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from siv.analyzers import get_analyzer  # noqa: E402
from siv.evaluation import EVAL_DIR, check_gates, run  # noqa: E402
from siv.tracing import configure  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="replay", choices=["replay", "foundry-model", "hosted-agent"])
    ap.add_argument("--partitions", default="golden,challenge,abstention,adversarial")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--no-gates", action="store_true")
    args = ap.parse_args()

    analyzer = get_analyzer(args.provider)
    configure(getattr(analyzer, "project", None))
    report = run(analyzer, args.partitions.split(","), args.repeats)
    report["gates"] = check_gates(report["metrics"])

    out = EVAL_DIR / "results" / report["run_id"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(report, indent=2))
    with (out / "foundry_rows.jsonl").open("w") as f:
        for r in report["rows"]:
            f.write(json.dumps({k: r[k] for k in ("id", "partition", "query", "response", "ground_truth")}) + "\n")

    print(f"run {report['run_id']}  analyzer={report['analyzer']}  agent={report['agent_version']}")
    print(f"{'case':<32}{'expected':<18}{'got':<18}worst evaluator")
    for r in report["rows"]:
        worst = min(r["scores"].items(), key=lambda kv: kv[1])
        print(f"{r['id']:<32}{r['expected_decision']:<18}{str(r['decision']):<18}{worst[0]}={worst[1]:.2f}")
    print("\nmetrics:")
    for k, v in report["metrics"].items():
        print(f"  {k:<28}{v}")
    print("\ngates:")
    for g in report["gates"]:
        print(f"  {'PASS' if g['passed'] else 'FAIL'}  {g['gate']:<28}{g['value']}")
    print(f"\nreport: {out / 'report.json'}")
    failed = [g for g in report["gates"] if not g["passed"]]
    if failed and not args.no_gates:
        print(f"\n{len(failed)} release gate(s) failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
