# Hosted Agent setup for this workspace

Use this before the [Foundry demo](demo-guide.md). It documents the current source
configuration, not a claim that Azure resources are already deployed.

## 1. Understand the two execution locations

```text
Presenter / evaluation caller
  siv pipeline -> images + rules + guidance -> hosted-agent Responses client
                                             |
Microsoft Foundry hosted runtime              v
  ResponsesHostServer -> Agent -> FoundryChatClient -> model deployment
                           |
                           +-> get_rule_pack (read-only local YAML)
                           +-> retrieve_policy_guidance (read-only local Markdown)
                                             |
Caller receives raw inspection JSON <---------+
  validate -> confidence gate -> deterministic decision -> local result store
```

The agent server does not call the caller's scoring/persistence pipeline.
Foundry **rows evaluation** scores the caller's final decision records;
**agent-target evaluation** calls the hosted worker and scores raw agent JSON.

## 2. Files controlling hosting

| File | Current setup |
|---|---|
| [azure.yaml](../azure.yaml) | `store-image-inspector`, `host: azure.ai.agent`, `kind: hosted`, project root `.`, Responses 2.0.0 |
| [azure.yaml](../azure.yaml) | `codeConfiguration`: Python 3.13, remote build, worker entrypoint; 1 CPU / 2 GiB |
| [agent/main.py](../agent/main.py) | Agent Framework, `FoundryChatClient`, `ResponsesHostServer`, two tools, optimizer configuration |
| [requirements.txt](../requirements.txt) | Root dependency list for the selected remote-code-build flow |
| [agent/requirements.txt](../agent/requirements.txt) | Dependencies used by the explicit Docker recipe |
| [Dockerfile](../Dockerfile) | Python 3.12 alternative container recipe, port 8088; not selected by current codeConfiguration |
| [.agentignore](../.agentignore) | Source upload exclusions; `.env` and `.venv` must not ship |
| [.agent_configs/baseline/](../.agent_configs/baseline/) | Model/instructions/skills/tool descriptions loaded at runtime |
| [infra/main.bicep](../infra/main.bicep) | Foundry infrastructure entrypoint; active azd provider is `microsoft.foundry` |

Do not run `azd ai agent init` over this workspace just to demonstrate it; that can
replace configuration. Do not silently switch to the Docker path.

## 3. Prepare identity, models, and tools

Required:

- Python compatible with the chosen runtime; local checks here used Python 3.12.
- Azure CLI authentication for `DefaultAzureCredential`; azd authentication for deployment.
- azd with the `azure.ai.agents` and `azure.ai.projects` extensions meeting the YAML's
  required versions.
- A selected subscription/project/region with hosted-agent support and model quota.
- A vision-capable **existing deployment name**, not merely a catalog model ID.
- A GPT-5+ judge deployment for Insights; a supported optimizer deployment for optimization.

```powershell
$python = (Resolve-Path .\.venv\Scripts\python.exe).Path
# If dependencies are absent:
& $python -m pip install -r .\requirements.txt

az login
$env:AZURE_DEV_USER_AGENT = 'microsoft_foundry_skill'  # this terminal only
azd auth login
azd version
azd ai agent run --help
azd ai agent optimize --help
```

Do not persist the local user-agent setting into `.env`, azd environment state, or source.
If a package feed is restricted, use your organization's approved feed; the app has no
requirement to use a particular internal feed.

### Permissions and observability

Use least-privilege roles appropriate to your project and current Foundry documentation:

| Principal / action | Required capability to verify |
|---|---|
| Developer/test caller | Invoke models and agents; project data-plane access |
| Deployment identity | Create/update the intended resources and role assignments when provisioning |
| Hosted runtime/project identity | Access selected model deployment; registry pull when applicable |
| Trace reader | Read linked Application Insights / Log Analytics telemetry |
| Insights caller and monitor identity | Read telemetry and invoke the GPT-5+ judge; project permissions for monitors |
| Dataset/image operator | Write images to approved private storage and grant bounded read access |

The short [Foundry checklist](foundry-setup.md) includes role suggestions. The inspected
templates grant a developer Cognitive Services User role conditionally; that is not
proof all model, monitor, telemetry, and storage permissions are satisfied.
Connect Application Insights in the project before the demo. The checked-in templates
do not create dedicated App Insights/Log Analytics resources or an eval-image container.

## 4. Set configuration explicitly

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT = 'https://<account>.services.ai.azure.com/api/projects/<project>'
$env:MICROSOFT_FOUNDRY_MODEL_DEPLOYMENT_NAME = '<existing-vision-deployment>'
$env:FOUNDRY_AGENT_NAME = 'store-image-inspector'
$env:INSIGHTS_JUDGE_MODEL = '<existing-gpt-5-or-newer-deployment>'
$env:OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT = 'false'
$env:SIV_AGENT_CONFIG = 'baseline'
```

The CLI and worker attempt dotenv loading; standalone evaluation/Insights/optimizer
scripts do not. Process environment makes all paths consistent. azd environment
configuration is separate from the PowerShell environment; reconcile selected project,
endpoint, model, and agent identity before deployment. Never publish raw `azd env get-values`
output, connection strings, or SAS.

Hosted platform `FOUNDRY_*` values are reserved; the YAML only explicitly passes the
`MICROSOFT_FOUNDRY_MODEL_DEPLOYMENT_NAME` override. Verify that the runtime supplies
`FOUNDRY_PROJECT_ENDPOINT` and usable managed identity. Do not ship the developer `.env`
inside the agent.

### Resolve these checked-in mismatches before provisioning

1. The project service binds `endpoint: ${FOUNDRY_PROJECT_ENDPOINT}`: decide whether you
   are reusing that project or intentionally provisioning a new one.
2. The checked-in model tuple is `gpt-5.5` / `2025-04-14`, also present in the parameter
   snapshot. Its validity/availability is not established by this repository. Verify the
   catalog model/version, deployment name, SKU, region, and capacity; do not blindly deploy it.
3. Baseline metadata defaults to `gpt-5.5`; the example environment uses `gpt-4.1`.
   Use a verified deployment override consistently.
4. Remote code build uses Python 3.13 while the Dockerfile uses 3.12. Test the selected
   path and current package versions; local tests do not certify the remote runtime.
5. The active infrastructure provider can synthesize templates. Review its actual
   deployment inputs; changing an old generated parameter file alone may not change deployment.

## 5. Smoke-test the worker locally

```powershell
azd ai agent run store-image-inspector --no-client `
    --start-command ".\.venv\Scripts\python.exe agent\main.py"
```

This is a foreground development server, not automatically a Docker container.
In a second terminal, verify the actual advertised listener:

```powershell
Test-NetConnection localhost -Port 8088
```

A listening port proves only startup. Use Foundry Toolkit's Agent Inspector against
that local server to send a real multimodal Responses request containing:

- Request metadata with a unique submission ID, category `storefront`, and exact
  `contoso-storefront` version `1.0.0`.
- An actual image attachment/`input_image`, not a filename mentioned in text.
- The task to inspect the image and retrieve the rules/policy.

Confirm tool calls, image handoff, JSON output, and model identity. The local CLI's
`--provider hosted-agent` targets the **deployed** named endpoint, not this localhost
server. Stop the local development process with Ctrl+C after smoke-testing.

The worker supplies a strict response-format option and the prompt asks for JSON, but
the hosting adapter's enforcement must be verified against the installed framework.
The caller always validates and can retry once; agent-target evaluation does not add
the caller's contract checks or scoring.

## 6. Deploy only after the preceding checks

These are intentional cloud-changing operations that can incur cost. Select/review
the intended azd environment first. See
[official hosted-agent documentation](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)
for current provisioning/deployment behavior.

```powershell
$env:AZURE_DEV_USER_AGENT = 'microsoft_foundry_skill'
azd env list
# Initial provisioning + deployment, after reviewing project/model settings:
azd up
# Later code/config changes in the same reviewed environment:
azd deploy
```

Do not run both deployment commands merely to rehearse. Record the returned exact
agent name/version, project endpoint, environment, and deployment status.
Wait for the container to be running, then send a fresh request:

```powershell
$submission = 'hosted-smoke-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
& $python -m siv analyze .\fixtures\images\syn-compliant.jpg `
    --provider hosted-agent --agent-name $env:FOUNDRY_AGENT_NAME `
    --submission-id $submission --json
```

Verify `event` is not `InspectionFailed`, inspect schema/rules/evidence, then locate
actual hosted telemetry. With `--json`, the CLI prints a failure record without its
normal failure exit-code branch; inspect the returned `event`, not only exit code.
The hosted analyzer routes by agent name, not a pinned version, so record the version
actually served. Use agent-target evaluation's `--agent-version` when pinning a run.

## 7. Prepare the evaluation/Insights/Optimizer surfaces

1. Use the [demo's full-pipeline evaluation](demo-guide.md) to create decision records
   and enforce all local release gates.
2. Upload decision rows to Foundry to score them with all 11 custom evaluators.
3. For agent-target/optimizer, upload approved images to private storage, preserve
   basenames, and set `SIV_EVAL_IMAGE_BASE_URL` and short-lived `SIV_EVAL_IMAGE_SAS`.
4. Run a version-pinned agent-target evaluation; verify five custom evaluators and
   actual multimodal input.
5. Generate hosted traffic and run Insights. A local monitor ID cache is not portable
   across projects: verify its project association before reuse.
6. Build optimizer tasks; use the explicit optimizer config path and verify image handoff.
7. Save evaluation URLs, versions, candidate IDs, and promotion evidence privately.

SAS-bearing task JSONL and cloud output may be sensitive even if images are synthetic.
The generated datasets are not all ignored by Git; never stage them indiscriminately.
Expire access and disable demo-only Insights schedules afterward.

## 8. Deployment is ready when all answers are "yes"

- [ ] Correct project/environment, valid model tuple, and sufficient quota.
- [ ] Chosen remote-build runtime and imports start successfully.
- [ ] Required runtime files included; secrets/virtualenv excluded.
- [ ] Managed identity can invoke the chosen vision deployment.
- [ ] Real image reaches the model and evidence/rule JSON returns.
- [ ] Caller validates, scores, persists, and distinguishes failures from noncompliance.
- [ ] Hosted trace identity/tools and caller business traces are visible and distinguishable.
- [ ] Insights sees actual hosted traffic with a working GPT-5+ judge.
- [ ] Foundry evaluator registration and version-pinned agent evaluation complete.
- [ ] Optimizer input contains images, candidates are reviewable, and gates are enforced.
- [ ] Previous baseline/platform version and rollback procedure are recorded.

If any answer is "no", use the corresponding labeled fallback in the
[demo guide](demo-guide.md). Authentication/network restrictions are setup blockers;
do not disable security controls to make the demonstration run.
