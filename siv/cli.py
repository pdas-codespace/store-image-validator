"""CLI: analyze images, validate rule packs.

  python -m siv analyze fixtures/images/syn-compliant.jpg --provider replay
  python -m siv analyze my-store.jpg --provider foundry-model
  python -m siv analyze my-store.jpg --provider hosted-agent --agent-name store-image-inspector
  python -m siv validate-rules
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid

from .analyzers import get_analyzer
from .pipeline import inspect
from .rulepack import validate_all
from .tracing import configure


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> None:
    _load_dotenv()
    ap = argparse.ArgumentParser(prog="siv")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="Analyze one submission (1-5 images)")
    a.add_argument("images", nargs="+")
    a.add_argument("--provider", default="foundry-model", choices=["foundry-model", "hosted-agent", "replay"])
    a.add_argument("--agent-name")
    a.add_argument("--rule-pack", default="contoso-storefront")
    a.add_argument("--version", default="1.0.0")
    a.add_argument("--submission-id", default=None)
    a.add_argument("--store-id", default="local")
    a.add_argument("--json", action="store_true", help="Print the full decision record")
    sub.add_parser("validate-rules", help="Validate all rule packs against the schema")
    args = ap.parse_args(argv)

    if args.cmd == "validate-rules":
        results = validate_all()
        for path, status in results.items():
            print(f"{status:>4}  {path}")
        sys.exit(0 if all(s == "ok" for s in results.values()) else 1)

    kwargs = {"agent_name": args.agent_name} if args.provider == "hosted-agent" and args.agent_name else {}
    analyzer = get_analyzer(args.provider, **kwargs)
    print(f"tracing -> {configure(getattr(analyzer, 'project', None))}", file=sys.stderr)
    record = inspect(args.images, rule_pack_id=args.rule_pack, rule_pack_version=args.version,
                     analyzer=analyzer, submission_id=args.submission_id or f"sub-{uuid.uuid4().hex[:10]}",
                     store_id=args.store_id)
    if args.json:
        print(json.dumps(record, indent=2))
        return
    if record["event"] == "InspectionFailed":
        print(f"InspectionFailed [{record['failure']['kind']}]: {record['failure']['reason']}")
        sys.exit(2)
    print(record["message"])
    print()
    for r in record["effective_rule_results"]:
        print(f"  {r['rule_id']}  {r['status']:<17} conf={r['confidence']:.2f}  {r['reason']}")
    if record["requires_human_review"]:
        print(f"\nHuman review: {', '.join(record['review_reasons'])}")
    print(f"\nevent={record['event']}  trace_id={record['trace_id']}  agent={record['agent_version']}")
