"""Insights in Foundry (preview) for the hosted agent: run a scan and pull findings.

  python insights/run_insights.py scan --lookback-hours 24     # on-demand analysis
  python insights/run_insights.py list                          # newest findings with details
  python insights/run_insights.py schedule --hours 6            # recurring (incurs model cost)

Needs: azure-ai-projects>=2.6.1, a GPT-5+ judge deployment (INSIGHTS_JUDGE_MODEL), the
agent's traces in the connected Application Insights, and the roles listed in
docs/foundry-setup.md. Findings are written to insights/out/ for review; nothing here
changes the agent. Route confirmed findings to: a new dataset row (evaluation/datasets),
an evaluator, or an optimizer run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"


def monitor_ops():
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    client = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=DefaultAzureCredential(),
                             allow_preview=True)
    return client.beta.agent_insight_monitors


def get_or_create_monitor(ops, agent_name: str, judge: str):
    from azure.ai.projects.models import AgentInsightMonitorCreate

    existing = list(ops.list(agent_name=agent_name))
    if len(existing) > 1:
        raise RuntimeError(f"Multiple Insights monitors returned for {agent_name}; refusing to choose.")
    if existing:
        return existing[0]
    return ops.create(AgentInsightMonitorCreate(agent_name=agent_name, model_deployment_name=judge, enabled=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scan", "list", "schedule", "unschedule"])
    ap.add_argument("--agent-name", default=os.environ.get("FOUNDRY_AGENT_NAME", "store-image-inspector"))
    ap.add_argument("--judge", default=os.environ.get("INSIGHTS_JUDGE_MODEL"))
    ap.add_argument("--lookback-hours", type=int, default=24)
    ap.add_argument("--hours", type=int, default=6)
    ap.add_argument("--output-dir", type=Path, default=OUT)
    args = ap.parse_args()
    if not args.judge:
        raise SystemExit("Set INSIGHTS_JUDGE_MODEL to a GPT-5 or newer deployment name.")
    ops = monitor_ops()
    monitor = get_or_create_monitor(ops, args.agent_name, args.judge)
    scope = hashlib.sha256(
        (os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/") + "/" + args.agent_name).encode()
    ).hexdigest()[:16]
    out = args.output_dir / scope
    out.mkdir(parents=True, exist_ok=True)
    (out / "monitor.json").write_text(json.dumps({
        "id": monitor.id, "project_endpoint": os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        "agent_name": args.agent_name,
    }, indent=2), encoding="utf-8")

    if args.cmd == "scan":
        from azure.ai.projects.models import AgentInsightRunCreate
        poller = ops.begin_create_run(monitor.id, AgentInsightRunCreate(lookback_hours=args.lookback_hours),
                                      operation_id=str(uuid.uuid4()))
        print("run id:", poller.details["run_id"])
        r = poller.result()
        print(f"traces analyzed={r.traces_analyzed} created={r.insights_created} updated={r.insights_updated}")
    elif args.cmd in ("schedule", "unschedule"):
        from azure.ai.projects.models import AgentInsightMonitorUpdate
        upd = AgentInsightMonitorUpdate(enabled=args.cmd == "schedule",
                                        **({"run_interval_hours": args.hours} if args.cmd == "schedule" else {}))
        m = ops.update(monitor.id, upd)
        print("schedule enabled:", m.enabled)
    if args.cmd in ("scan", "list"):
        insights = list(ops.list_insights(monitor.id, include_details=True))
        dump = []
        for i in insights:
            fix = None
            if getattr(i, "details", None) and getattr(i.details, "recommended_actions", None):
                fix = getattr(getattr(i.details.recommended_actions, "proposed_fix", None), "text", None)
            dump.append({"id": i.id, "title": i.title, "severity": str(i.severity), "status": str(i.status),
                         "trace_count": i.trace_count, "proposed_fix": fix})
            print(f"[{i.severity}] {i.title}  traces={i.trace_count}  status={i.status}")
        (out / "insights.json").write_text(json.dumps(dump, indent=2), encoding="utf-8")
        print(f"{len(dump)} insights -> {out / 'insights.json'} (an empty list does not prove the agent is healthy)")


if __name__ == "__main__":
    main()
