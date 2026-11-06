"""Human annotation of inspection results -> regression dataset candidates.

  python insights/annotate.py add <result.json> --label FALSE_ABSTENTION \
      --rule SF-003=PASS --decision PASS --reviewer jdoe --comment "Door clings visible"
  python insights/annotate.py export        # adjudicated annotations -> production_regression.jsonl

Annotations are stored in insights/annotations.jsonl. Only entries marked
--adjudicated (second reviewer / SOP) are exported; overrides are never auto-promoted
into the golden set.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STORE = HERE / "annotations.jsonl"
LABELS = set(yaml.safe_load((HERE / "taxonomy.yaml").read_text())["labels"])


def add(args) -> None:
    rec = json.loads(Path(args.result).read_text())
    bad = [lbl for lbl in args.label if lbl not in LABELS]
    if bad:
        sys.exit(f"Unknown label(s) {bad}. Use insights/taxonomy.yaml.")
    corrections = dict(kv.split("=", 1) for kv in args.rule)
    agent = {r["rule_id"]: r["status"] for r in rec["effective_rule_results"]}
    ann = {
        "annotated_at": datetime.now(timezone.utc).isoformat(), "reviewer": args.reviewer,
        "trace_id": rec["trace_id"], "submission_id": rec["submission_id"], "image_hashes": rec["image_hashes"],
        "rule_pack": rec["rule_pack"], "agent_version": rec["agent_version"], "labels": args.label,
        "agent_decision": rec["decision"], "reviewer_decision": args.decision or rec["decision"],
        "rule_corrections": [{"rule_id": k, "agent_status": agent.get(k), "reviewer_status": v} for k, v in corrections.items()],
        "expected_rules": {**agent, **corrections}, "comments": args.comment, "adjudicated": args.adjudicated,
        "image_paths": args.image or [],
    }
    with STORE.open("a") as f:
        f.write(json.dumps(ann) + "\n")
    print(f"annotation stored for trace {ann['trace_id']}")


def export(_args) -> None:
    rows = [json.loads(line) for line in STORE.read_text().splitlines()] if STORE.exists() else []
    out = ROOT / "evaluation" / "datasets" / "production_regression.jsonl"
    n = 0
    with out.open("w") as f:
        for a in rows:
            if not a["adjudicated"] or not a["image_paths"]:
                continue
            f.write(json.dumps({"id": f"prod-{a['submission_id']}", "partition": "production_regression",
                                "synthetic": False, "images": a["image_paths"], "rule_pack": a["rule_pack"],
                                "category": "storefront",
                                "expected": {"decision": a["reviewer_decision"], "rules": a["expected_rules"]},
                                "notes": f"labels={a['labels']} trace={a['trace_id']} {a['comments'] or ''}"}) + "\n")
            n += 1
    print(f"exported {n} adjudicated rows -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("result")
    a.add_argument("--label", action="append", required=True)
    a.add_argument("--rule", action="append", default=[], help="RULE_ID=STATUS")
    a.add_argument("--decision")
    a.add_argument("--reviewer", required=True)
    a.add_argument("--comment")
    a.add_argument("--image", action="append", help="repo-relative image path (needed for export)")
    a.add_argument("--adjudicated", action="store_true")
    sub.add_parser("export")
    args = ap.parse_args()
    (add if args.cmd == "add" else export)(args)


if __name__ == "__main__":
    main()
