"""Compare an optimizer candidate with the baseline on the same frozen dataset.

  azd ai agent optimize apply --candidate <id>      # writes .agent_configs/<id>/
  python optimizer/compare_candidate.py <id> --provider foundry-model

Checks the candidate only changed optimizer-owned files, runs the local evaluation for
baseline and candidate, and prints a quality / token comparison plus a promotion verdict.
It never deploys. Promotion = manual review -> shadow -> canary -> production.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from siv.agent_config import CONFIG_DIR  # noqa: E402

GUARD = yaml.safe_load((ROOT / "optimizer" / "guardrails.yaml").read_text())
GATED = ["rule_status_agreement", "abstention_precision", "abstention_recall", "evidence_consistency",
         "policy_adherence", "schema_valid_rate", "injection_resistance"]


def check_candidate_scope(candidate: str) -> list[str]:
    base, cand = CONFIG_DIR / "baseline", CONFIG_DIR / candidate
    if not cand.is_dir():
        return [f"{cand} not found"]
    problems = []
    for f in cand.rglob("*"):
        rel = f.relative_to(cand).as_posix()
        if f.is_file() and not any(fnmatch.fnmatch(rel, pat) for pat in GUARD["allowed_candidate_files"]):
            problems.append(f"unexpected file {rel}")
    meta = yaml.safe_load((cand / "metadata.yaml").read_text()) if (cand / "metadata.yaml").exists() else {}
    for k in meta:
        if k not in GUARD["allowed_metadata_keys"]:
            problems.append(f"metadata key {k} not allowed")
    if (cand / "tools.json").exists():
        sig = lambda t: (t["function"]["name"], sorted(t["function"]["parameters"].get("properties", {})))  # noqa: E731
        b = sorted(sig(t) for t in json.loads((base / "tools.json").read_text()))
        c = sorted(sig(t) for t in json.loads((cand / "tools.json").read_text()))
        if b != c:
            problems.append("tools.json changed tool names/parameters (only descriptions may change)")
    return problems


def evaluate(variant: str, provider: str, partitions: list[str]) -> dict:
    from siv.analyzers import get_analyzer
    from siv.evaluation import check_gates, run

    os.environ["SIV_AGENT_CONFIG"] = variant
    report = run(get_analyzer(provider), partitions)
    report["gates"] = check_gates(report["metrics"])
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("--provider", default="foundry-model", choices=["foundry-model", "replay"])
    ap.add_argument("--partitions", default="golden,challenge,abstention,adversarial")
    args = ap.parse_args()

    problems = check_candidate_scope(args.candidate)
    if problems:
        print("Candidate rejected (scope):\n  " + "\n  ".join(problems))
        sys.exit(1)
    parts = args.partitions.split(",")
    base, cand = evaluate("baseline", args.provider, parts), evaluate(args.candidate, args.provider, parts)
    print(f"{'metric':<28}{'baseline':>10}{'candidate':>11}")
    worse = []
    for m in GATED + ["decision_accuracy", "false_pass_rate", "input_tokens_total", "output_tokens_total"]:
        b, c = base["metrics"].get(m), cand["metrics"].get(m)
        print(f"{m:<28}{str(b):>10}{str(c):>11}")
        if m in GATED and b is not None and c is not None and c < b - GUARD["promotion"]["min_quality_delta"]:
            worse.append(m)
    tok_b = (base["metrics"]["input_tokens_total"] + base["metrics"]["output_tokens_total"]) or 1
    tok_c = cand["metrics"]["input_tokens_total"] + cand["metrics"]["output_tokens_total"]
    tok_pct = 100 * (tok_c - tok_b) / tok_b
    failed_gates = [g["gate"] for g in cand["gates"] if not g["passed"]]
    ok = not worse and not failed_gates and tok_pct <= GUARD["promotion"]["max_token_increase_pct"]
    print(f"\ntoken change: {tok_pct:+.1f}%  regressions: {worse or 'none'}  failed gates: {failed_gates or 'none'}")
    print("verdict:", "ELIGIBLE for manual review -> shadow -> canary" if ok else "NOT eligible for promotion")
    print("Manual approval required. This script never deploys.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
