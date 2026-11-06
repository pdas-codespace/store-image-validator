"""Run the evaluation in Microsoft Foundry (cloud evaluation, results in the portal).

Mode `rows` (default, works today with any provider):
    python evaluation/run_local_eval.py --provider foundry-model
    python evaluation/run_foundry_eval.py rows --rows evaluation/results/<run_id>/foundry_rows.jsonl
  Registers the code evaluators in evaluation/evaluators/ in the project catalog and scores the
  decision records produced locally. Same evaluator code as the local gates, so numbers match.

Mode `agent-target` (after the hosted agent is deployed):
    SIV_EVAL_IMAGE_BASE_URL=https://<account>.blob.core.windows.net/eval-images \
    python evaluation/run_foundry_eval.py agent-target --agent-name store-image-inspector
  Foundry sends each dataset row (text + image URL) to the hosted agent and scores the raw
  agent output with the agent-level evaluators. This is the same dataset + evaluator set to
  give Agent Optimizer (see optimizer/README.md).
  Add --image-auth entra to download private Blob images using az login and send inline
  image data instead of remotely fetched URLs. Requires azure-storage-blob; no SAS is used.

Requires: pip install "azure-ai-projects>=2.8.0" azure-identity ; az login ; FOUNDRY_PROJECT_ENDPOINT.
VERIFY: code-evaluator definition fields and agent-target image templating are preview
surfaces; checked against azure-ai-projects samples as of 2026-10 (docs/architecture.md).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EVALUATOR_DIR = ROOT / "evaluation" / "evaluators"
PREFIX = "siv_"
FOUNDRY_EVALUATIONS_PREVIEW_HEADERS = {"Foundry-Features": "Evaluations=V1Preview"}
AGENT_LEVEL = ["schema_validity", "rule_status_accuracy", "evidence_consistency", "policy_adherence",
               "injection_resistance"]


@dataclass(frozen=True)
class RegisteredEvaluator:
    name: str
    version: str


def clients():
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    project = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )
    return project, project.get_openai_client(default_headers=dict(FOUNDRY_EVALUATIONS_PREVIEW_HEADERS))


def register_evaluators(project, names: list[str]) -> dict[str, RegisteredEvaluator]:
    from azure.ai.projects.models import EvaluatorCategory, EvaluatorDefinitionType

    registered = {}
    for name in names:
        code = (EVALUATOR_DIR / f"{name}.py").read_text()
        doc = code.split('"""')[1].strip() if '"""' in code else name
        ev = project.evaluators.create_version(  # type: ignore[call-overload]
            name=PREFIX + name,
            headers=dict(FOUNDRY_EVALUATIONS_PREVIEW_HEADERS),
            evaluator_version={
                "name": PREFIX + name, "display_name": f"SIV {name}", "description": doc[:500],
                "categories": [EvaluatorCategory.QUALITY],
                "definition": {
                    "type": EvaluatorDefinitionType.CODE,
                    "code_text": code,
                    "init_parameters": {"type": "object", "properties": {"pass_threshold": {"type": "number"}},
                                        "required": ["pass_threshold"]},
                    "metrics": {"result": {"type": "ordinal", "desirable_direction": "increase",
                                           "min_value": 0.0, "max_value": 1.0}},
                    "data_schema": {
                        "type": "object", "required": ["response", "ground_truth"],
                        "properties": {"response": {"type": "string"}, "ground_truth": {"type": "string"}},
                    },
                },
            },
        )
        registered[name] = RegisteredEvaluator(ev.name, ev.version)
        print(f"registered evaluator {ev.name} v{ev.version}")
    return registered


def criteria(registered: dict[str, RegisteredEvaluator], target_mode: bool):
    from azure.ai.projects.models import TestingCriterionAzureAIEvaluator

    thresholds = {"rule_status_accuracy": 0.95, "evidence_consistency": 0.95, "explanation_usefulness": 0.7}
    out = []
    for name, evaluator in registered.items():
        out.append(TestingCriterionAzureAIEvaluator(
            type="azure_ai_evaluator", name=name, evaluator_name=evaluator.name, evaluator_version=evaluator.version,
            initialization_parameters={"pass_threshold": thresholds.get(name, 1.0)},
            data_mapping={
                "response": "{{sample.output_text}}" if target_mode else "{{item.response}}",
                "ground_truth": "{{item.ground_truth}}",
            }))
    return out


def wait(client, eval_id: str, run_id: str):
    while True:
        run = client.evals.runs.retrieve(
            run_id=run_id,
            eval_id=eval_id,
            extra_headers=FOUNDRY_EVALUATIONS_PREVIEW_HEADERS,
        )
        if run.status in ("completed", "failed", "canceled"):
            return run
        time.sleep(5)


def summarize(client, eval_id, run) -> None:
    print(f"status: {run.status}\nreport: {run.report_url}")
    for c in getattr(run, "per_testing_criteria_results", None) or []:
        print(f"  {c.testing_criteria:<28} passed={c.passed} failed={c.failed}")


def blob_image_data_url(base: str, filename: str) -> str:
    from azure.identity import AzureCliCredential
    from azure.storage.blob import BlobClient

    from siv.images import MAX_BYTES, image_bytes_to_data_url

    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment or parsed.username:
        raise ValueError("Entra image mode requires an HTTPS Blob container URL without credentials, query, or fragment.")
    blob_url = f"{base.rstrip('/')}/{quote(filename, safe='')}"
    with AzureCliCredential() as credential, BlobClient.from_blob_url(blob_url, credential=credential) as blob:
        data = blob.download_blob(offset=0, length=MAX_BYTES + 1).readall()
    return image_bytes_to_data_url(data)


def cmd_rows(args) -> None:
    from openai.types.eval_create_params import DataSourceConfigCustom
    from openai.types.evals.create_eval_jsonl_run_data_source_param import (
        CreateEvalJSONLRunDataSourceParam, SourceFileContent, SourceFileContentContent)

    rows = [json.loads(line) for line in Path(args.rows).read_text().splitlines() if line.strip()]
    project, client = clients()
    names = sorted(p.stem for p in EVALUATOR_DIR.glob("[!_]*.py"))
    registered = register_evaluators(project, names)
    ev = client.evals.create(
        name=args.name,
        extra_headers=FOUNDRY_EVALUATIONS_PREVIEW_HEADERS,
        data_source_config=DataSourceConfigCustom(type="custom", include_sample_schema=False, item_schema={
            "type": "object", "required": ["query", "response", "ground_truth"],
            "properties": {k: {"type": "string"} for k in ("id", "partition", "query", "response", "ground_truth")}}),
        testing_criteria=criteria(registered, target_mode=False),
    )
    run = client.evals.runs.create(
        eval_id=ev.id, name=f"{args.name} {Path(args.rows).parent.name}",
        extra_headers=FOUNDRY_EVALUATIONS_PREVIEW_HEADERS,
        metadata={"source_rows": Path(args.rows).parent.name},
        data_source=CreateEvalJSONLRunDataSourceParam(type="jsonl", source=SourceFileContent(
            type="file_content", content=[SourceFileContentContent(item=r) for r in rows])),
    )
    summarize(client, ev.id, wait(client, ev.id, run.id))


def agent_items(partitions: str, image_auth: str, prefix: str = "eval") -> list[dict]:
    from siv.evaluation import ground_truth, load_dataset

    base = os.environ.get("SIV_EVAL_IMAGE_BASE_URL")
    if image_auth != "hosted" and not base:
        sys.exit("Set SIV_EVAL_IMAGE_BASE_URL to the image container URL. Use --image-auth entra "
                 "for authenticated local downloads, or a short-lived SAS for URL mode.")
    sas = os.environ.get("SIV_EVAL_IMAGE_SAS", "")
    if image_auth in ("entra", "hosted") and sas:
        sys.exit(f"Remove SIV_EVAL_IMAGE_SAS before using --image-auth {image_auth}; SAS fallback is not used.")
    items = []
    for row in load_dataset(partitions.split(",")):
        if len(row["images"]) != 1:
            continue  # template below sends one image per row
        req = {"task": "Inspect the attached image. First call get_rule_pack and retrieve_policy_guidance.",
               "submission_id": f"{prefix}-{row['id']}", "category": row["category"], "rule_pack": row["rule_pack"],
               "images": [{"image_id": "img-001", "order": 1}]}
        filename = Path(row["images"][0]).name
        item = {"id": row["id"], "ground_truth": json.dumps(ground_truth(row))}
        if image_auth == "hosted":
            req["images"][0]["blob_name"] = filename
        else:
            item["image_url"] = blob_image_data_url(base, filename) if image_auth == "entra" \
                else f"{base.rstrip('/')}/{filename}{sas}"
        item["query"] = json.dumps(req)
        items.append(item)
    if not items:
        sys.exit("No single-image rows were selected for evaluation.")
    return items


def cmd_agent_target(args) -> None:
    from openai.types.eval_create_params import DataSourceConfigCustom

    items = agent_items(args.partitions, args.image_auth)
    columns = ("id", "query", "ground_truth") if args.image_auth == "hosted" \
        else ("id", "query", "image_url", "ground_truth")
    content = [{"type": "input_text", "text": "{{item.query}}"}]
    if args.image_auth != "hosted":
        content.append({"type": "input_image", "image_url": "{{item.image_url}}", "detail": "high"})
    project, client = clients()
    registered = register_evaluators(project, AGENT_LEVEL)
    ev = client.evals.create(
        name=args.name,
        extra_headers=FOUNDRY_EVALUATIONS_PREVIEW_HEADERS,
        data_source_config=DataSourceConfigCustom(type="custom", include_sample_schema=True, item_schema={
            "type": "object", "required": [k for k in columns if k != "id"],
            "properties": {k: {"type": "string"} for k in columns}}),
        testing_criteria=criteria(registered, target_mode=True),
    )
    run = client.evals.runs.create(eval_id=ev.id, name=f"{args.name} agent-target", data_source={
        "type": "azure_ai_target_completions",
        "source": {"type": "file_content", "content": [{"item": i} for i in items]},
        "input_messages": {"type": "template", "template": [{
            "type": "message", "role": "user", "content": content}]},
        "target": {"type": "azure_ai_agent", "name": args.agent_name,
                   **({"version": args.agent_version} if args.agent_version else {})},
    }, extra_headers=FOUNDRY_EVALUATIONS_PREVIEW_HEADERS)
    print(f"evaluation id: {ev.id}\nrun id: {run.id}")
    completed = wait(client, ev.id, run.id)
    summarize(client, ev.id, completed)
    if args.output_dir:
        output = Path(args.output_dir)
        output.mkdir(parents=True, exist_ok=True)
        (output / "run.json").write_text(json.dumps({
            "project_endpoint": os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            "agent_name": args.agent_name, "agent_version": args.agent_version,
            "image_auth": args.image_auth, "partitions": args.partitions,
            "dataset_sha256": hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest(),
            "evaluators": {
                name: {"name": ref.name, "version": ref.version,
                       "source_sha256": hashlib.sha256((EVALUATOR_DIR / f"{name}.py").read_bytes()).hexdigest()}
                for name, ref in registered.items()
            },
            "eval_id": ev.id, "run_id": run.id, "status": completed.status,
            "report_url": completed.report_url,
        }, indent=2), encoding="utf-8")
        with (output / "results.jsonl").open("w", encoding="utf-8") as file:
            for result in client.evals.runs.output_items.list(eval_id=ev.id, run_id=run.id):
                file.write(json.dumps(result.model_dump(mode="json")) + "\n")
        print(f"saved results to {output}")
    if completed.status != "completed":
        sys.exit(f"Evaluation run ended with status {completed.status}.")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    sub.add_parser("register", help="Register all code evaluators without starting an evaluation")
    r = sub.add_parser("rows")
    r.add_argument("--rows", required=True)
    r.add_argument("--name", default="store-image-validator rows")
    t = sub.add_parser("agent-target")
    t.add_argument("--agent-name", default=os.environ.get("FOUNDRY_AGENT_NAME", "store-image-inspector"))
    t.add_argument("--agent-version")
    t.add_argument("--image-auth", choices=["url", "entra", "hosted"], default="url",
                   help="url: remote URL; entra: local az login download; hosted: worker identity downloads Blob references")
    t.add_argument("--output-dir", help="Save run context and full output items privately; may include image content or SAS")
    t.add_argument("--partitions", default="golden,challenge,abstention,adversarial")
    t.add_argument("--name", default="store-image-validator agent-target")
    args = ap.parse_args()
    if args.mode == "register":
        project, _ = clients()
        register_evaluators(project, sorted(p.stem for p in EVALUATOR_DIR.glob("[!_]*.py")))
    else:
        (cmd_rows if args.mode == "rows" else cmd_agent_target)(args)


if __name__ == "__main__":
    main()
