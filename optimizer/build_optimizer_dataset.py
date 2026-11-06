"""Build optimizer inputs from the same frozen rows as hosted-agent evaluation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.run_foundry_eval import agent_items  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image-auth", choices=["url", "entra", "hosted"], default="url")
    ap.add_argument("--partitions", default="golden,challenge,abstention,adversarial")
    ap.add_argument("--output", type=Path, default=ROOT / "evaluation" / "datasets" / "optimizer_tasks.jsonl")
    args = ap.parse_args()
    items = agent_items(args.partitions, args.image_auth, prefix="opt")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        for item in items:
            file.write(json.dumps(item) + "\n")
    print(f"wrote {len(items)} rows to {args.output}")
    if args.image_auth == "hosted":
        print("Optimizer input adapter must pass query as the user text; candidate runtime requires Blob identity.")


if __name__ == "__main__":
    main()
