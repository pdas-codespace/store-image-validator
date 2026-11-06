# Store Image Validator — phase 1: analyze + evaluate

Analyze a store image against a versioned rule pack (Contoso storefront v1.0.0), get per-rule
findings with evidence regions, a deterministic 0–10 score and PASS / FAIL / CANNOT_DETERMINE, and run
it through the Microsoft Foundry quality loop: **Tracing → Evaluation → Insights → Agent Optimizer**.

The event-driven application design from the spec (Blob → Event Grid → Service Bus → Durable
Functions, Cosmos DB) is deliberately **not** built yet. Foundry provisioning templates do exist in
`infra/`. `siv/pipeline.py` is the application seam: the same `inspect()` call later runs inside the
orchestration worker.

## Demo and codebase guides

- [Step-by-step Foundry demo](docs/demo-guide.md): presenter narrative, PowerShell commands,
  expected outputs, tracing, Agent Insights, evaluation, optimization, and fallbacks.
- [Easy-to-understand codebase tour](docs/codebase-guide.md): request flow and every source/config
  file worth knowing, including infrastructure, tests, fixtures, and generated state.
- [Hosted Agent setup](docs/hosted-agent-setup.md): runtime, identity, model settings,
  deployment readiness, and live integration checks.
- [Foundry evaluation schema fix and Blob image flow](docs/foundry-evaluation-schema-and-blob-flow.md):
  old/new schemas and code side by side, private image uploads and SAS access,
  evaluation request flow, run commands, and troubleshooting.
- [Using business rules from Excel](docs/spreadsheet-rules.md): where to house the workbook,
  map it to versioned rules/policy, and introduce it in the demo.

Offline verification on 2026-10-15: **47 tests, eight replay cases, all 12 gates passing**.
Live Foundry stages require authenticated rehearsal; replay is not evidence of model quality.

```
image(s) ─► intake (type/size/hash) ─► rule pack @ pinned version ─► policy guidance (Foundry IQ stand-in)
        ─► model / hosted agent: observations + one result per rule (strict JSON schema)
        ─► contract checks (+1 retry) ─► confidence gate ─► deterministic score & decision
        ─► local result store (idempotent) ─► OTel spans → App Insights → Foundry Tracing/Insights
```

## 1. Run it offline (no Azure, 1 minute)

```bash
pip install pyyaml pillow
python -m siv analyze fixtures/images/syn-cropped-left.jpg --provider replay
python -m unittest discover -s tests -t .            # 47 tests incl. the 10 mandatory cases
python evaluation/run_local_eval.py                  # harness + release gates on recorded outputs
```
`replay` uses recorded (synthetic) agent outputs, so it proves the plumbing, scoring and evaluators —
not model quality.

## 2. Analyze your own image with a Foundry model

```bash
pip install -r requirements.txt
cp .env.example .env        # set FOUNDRY_PROJECT_ENDPOINT and a vision-capable deployment
az login
python -m siv analyze path/to/storefront.jpg                # --provider foundry-model is the default
python -m siv analyze front.jpg door.jpg --json             # up to 5 images, full decision record
```
If the project has Application Insights connected, every run shows up in **Foundry → Tracing**
(`inspection` → `retrieve_policy_guidance` → `invoke_agent` → `rule_result` spans). A local copy of
the span attributes is always written to `.runs/traces.jsonl`; image bytes and URLs never are.

## 3. Evaluate

```bash
python evaluation/run_local_eval.py --provider foundry-model --repeats 2          # real model, gates enforced
python evaluation/run_foundry_eval.py rows --rows evaluation/results/<run_id>/foundry_rows.jsonl
```
The second command registers the 11 code evaluators in your project catalog and scores the same rows
in Foundry, so the run appears under **Evaluations** with a report URL. Datasets: `evaluation/datasets/`
(golden, challenge, abstention, adversarial). Gates: `evaluation/release_gates.yaml`.

## 4. Deploy and run as a hosted agent (needed for Insights + Optimizer)

```bash
pip install -r requirements.txt
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
azd ai agent run store-image-inspector --no-client --start-command ".\.venv\Scripts\python.exe agent\main.py"
azd up                          # Foundry project + model + hosted agent (azure.yaml)
python -m siv analyze store.jpg --provider hosted-agent
python evaluation/run_foundry_eval.py agent-target      # Foundry calls the agent per row
python -m siv analyze fixtures\images\Bathroom\iStock_000061778814_Large-scaled-1.jpg --rule-pack contoso-bathroom --provider hosted-agent  
```

## 5. Insights and Optimizer
- **Insights:** `python insights/run_insights.py scan` then `list`. Confirmed findings → annotate
  (`insights/annotate.py`, stable taxonomy) → regression dataset → evaluate. KQL in `insights/kql/`.
- **Optimizer:** baseline in `.agent_configs/baseline/` (instructions, storefront skill, read-only tool
  descriptions, model). `azd ai agent optimize --config .\optimizer\eval.yaml` (supply verified judge/optimizer models) →
  `azd ai agent optimize apply --candidate <id>` →
  `python optimizer/compare_candidate.py <id>`; it rejects candidates that touch business config and
  never deploys. See `optimizer/README.md`.

### Evaluate private Blob images with Entra ID (no SAS)

The evaluation runner can download images with your local `az login` identity,
then send inline JPEG data to the hosted agent. Your identity needs **Storage Blob
Data Reader** on the evaluation container and access to the Foundry project.
Install the updated requirements first (`.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt`).

```powershell
az login
$env:FOUNDRY_PROJECT_ENDPOINT = "https://<foundry-account>.services.ai.azure.com/api/projects/<project-name>"
$env:SIV_EVAL_IMAGE_BASE_URL = "https://<storage-account>.blob.core.windows.net/<container-name>"
Remove-Item Env:\SIV_EVAL_IMAGE_SAS -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe .\evaluation\run_foundry_eval.py agent-target --image-auth entra --agent-name store-image-inspector --agent-version 8 --partitions golden --name "Storefront Entra baseline"
```

Replace the angle-bracket placeholders with your own resource names and `8` with
the deployed agent version you intend to evaluate. Omit
`--partitions golden` for all partitions. No agent redeployment is needed.
This uses `AzureCliCredential`, not the hosted agent's managed identity.
The images are validated and re-encoded using the existing image intake helpers;
their bytes are submitted in evaluation rows and may be retained in Foundry artifacts.
The existing URL/SAS behavior remains the default (`--image-auth url`).

### NCUS GPT / Fireworks Kimi demo with hosted Blob identity

The [task/action plan](docs/ncus-task-actions.md) and
[complete NCUS demo runbook](docs/ncus-demo.md) cover the isolated deployment,
environment files, exact runtime identity role grants, smoke checks, Insights,
evaluations, and optimizer commands. The existing East US deployment stays unchanged.

`--image-auth hosted` sends Blob basenames in the evaluation query. The updated
hosted worker downloads images from its configured private container using
managed/workload identity and attaches inline JPEGs before inference; no local
Blob login or SAS is needed. Deploy the new worker and grant its actual runtime
identity **Storage Blob Data Reader** first. Operator Foundry authentication is
still required. The demo exports and independently checks cloud grades, refusing
to present transport failures or cloud/local grading disagreements as valid quality.

### Find and reuse an existing Agent Insights monitor

Run these PowerShell commands from the repository root after installing the requirements.
Replace the angle-bracket placeholders with your own Foundry account and project names.

```powershell
az login
$env:FOUNDRY_PROJECT_ENDPOINT = "https://<foundry-account>.services.ai.azure.com/api/projects/<project-name>"
$agentName = "store-image-inspector"
$encodedAgentName = [uri]::EscapeDataString($agentName)
$uri = "$($env:FOUNDRY_PROJECT_ENDPOINT.TrimEnd('/'))/agent_insight_monitors?api-version=v1&agent_name=$encodedAgentName&limit=100"
$response = az rest --method get --url $uri --resource "https://ai.azure.com" `
    --headers "Foundry-Features=AgentInsights=V1Preview" --output json
if ($LASTEXITCODE -ne 0) { throw "Failed to list Agent Insights monitors." }
$monitors = $response | ConvertFrom-Json
$monitors.data | Format-Table id, agent_name, enabled, run_interval_hours, model_deployment_name

# The API allows one monitor per agent. Inspect its judge before running analysis.
if ($monitors.has_more -or @($monitors.data).Count -ne 1) {
    throw "Expected exactly one existing monitor. Check the project and agent name."
}
$monitor = $monitors.data[0]
$env:INSIGHTS_JUDGE_MODEL = $monitor.model_deployment_name
```

The [List Agent Insights monitors API](https://ai.azure.com/api-reference/agent-insight-monitors/list/)
returns a monitor **ID**, not a separate insight name. Discover the monitor and its judge
model in your own project rather than reusing an ID from another deployment.

With the endpoint and judge environment variables set above, run an on-demand scan against that monitor:

```powershell
.\.venv\Scripts\python.exe insights\run_insights.py scan --agent-name $agentName --lookback-hours 24
.\.venv\Scripts\python.exe insights\run_insights.py list --agent-name $agentName
```

The script now discovers monitors remotely for the current project and agent name;
it reuses one existing monitor, creates one only if none exists, and refuses to
choose if several are returned. Old `monitor-<agent>.json` files are not used to
select a monitor, so a cache cannot accidentally cross project boundaries.
Use `python` in place of `.\.venv\Scripts\python.exe` if dependencies are installed in another environment.
The scan incurs model usage but leaves the existing schedule unchanged. It prints the run ID and
trace/insight counts, then saves `monitor.json` and `insights.json` under
`insights\out\<scope>`, scoped by project endpoint and agent name. The `list` command
retrieves findings after resolving the monitor. Zero traces analyzed or no new findings
does not prove the agent is healthy.

## Layout
| Path | What |
|---|---|
| `rules/` | Rule-pack schema + `storefront/contoso-storefront-1.0.0.yaml` (weights, thresholds, mandatory flags) |
| `policy/` | Versioned interpretation guidance (local stand-in for Foundry IQ) |
| `siv/` | Pipeline, scoring engine, analyzers (`foundry-model`, `hosted-agent`, `replay`), tracing, evaluation core |
| `.agent_configs/baseline/` | Optimizer-owned agent config |
| `agent/` + `Dockerfile` + `azure.yaml` | Foundry hosted agent |
| `evaluation/` | Datasets, code evaluators, gates, local + Foundry runners |
| `insights/` | Insights scan/list, annotation loop, taxonomy, KQL |
| `optimizer/` | Optimizer eval config, guardrails, candidate comparison |
| `fixtures/` + `scripts/` | Synthetic images and the scripts that build fixtures/datasets |
