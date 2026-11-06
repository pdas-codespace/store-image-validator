# Architecture (phase 1)

For a file-by-file view, see the [codebase tour](codebase-guide.md). For a live walkthrough,
see the [demo runbook](demo-guide.md) and [Hosted Agent setup](hosted-agent-setup.md).

## Boundaries kept from the spec
| Concern | Where | Notes |
|---|---|---|
| Visual evidence + per-rule status | Model / hosted agent | Strict JSON schema (`siv/schemas/agent-result.schema.json`). No score/decision fields allowed; `additionalProperties:false` rejects them. |
| Rule definitions, weights, thresholds | `rules/*.yaml` | Weights and mandatory flags are withheld from the model (`Rule.agent_view`). |
| Policy interpretation | `policy/` (→ Foundry IQ later) | Retrieval keyed by rule-pack id + version; metadata mismatch = error, never substitution. |
| Contract enforcement | `siv/pipeline.check_agent_output` | Schema, rule-pack echo, exactly one result per rule, evidence for PASS/FAIL, missing evidence for CD. One retry with the errors fed back. |
| Score and decision | `siv/scoring.decide` | Deterministic; documented order of rules in the docstring. |
| Idempotency | `siv/store.ResultStore` | SHA-256 over tenant, submission, rule-pack version, ordered image hashes, agent version. Exclusive create. |
| Tracing | `siv/tracing.py` | OTel → App Insights when configured; local JSONL mirror always. |

## Decision policy (configurable in the rule pack)
1. Unusable image package → CANNOT_DETERMINE, score 0.
2. Rule confidence < `minimumRuleConfidence` (0.65) → that rule becomes CANNOT_DETERMINE.
3. Any mandatory FAIL → FAIL.
4. Any mandatory CANNOT_DETERMINE → CANNOT_DETERMINE + human review.
5. Any FAIL with score < `reviewThreshold` → FAIL.
6. Any other CANNOT_DETERMINE → CANNOT_DETERMINE (a PASS needs full evidence).
7. Score ≥ `passThreshold` → PASS; review band → FAIL + review; else FAIL.

Score = weighted share of applicable rules (PASS 1, FAIL 0, CANNOT_DETERMINE `cannotDetermineCredit` = 0.5,
NOT_APPLICABLE excluded) scaled to 0–10, rounded half-up.

**Calibration note:** with the spec's weights and `passThreshold: 8`, a store that fails only SF-003
(clings, weight 2.0) scores 8 and PASSes. That is what the spec config says; change `passThreshold` or
make SF-003 mandatory if that is not the business intent.

## Version-dependent decisions (checked against Microsoft Learn / azure-sdk-for-python, Oct 2026)
| Item | Decision | Status |
|---|---|---|
| Model call | `AIProjectClient(...).get_openai_client().responses.create(..., text.format=json_schema strict)` | Standard Responses API. |
| Hosted agent call | `AIProjectClient(..., allow_preview=True).get_openai_client(agent_name=...).responses.create(...)` in `siv/analyzers/foundry.py` | **VERIFY** endpoint routing for your SDK version. |
| Hosted agent runtime | `agent_framework` `Agent` + `FoundryChatClient` + `ResponsesHostServer`; strict response-format option passed to the framework | **VERIFY** imports, schema-option enforcement, and that `input_image` parts reach the model. |
| azd config | Unified `azure.yaml` (agent.yaml is deprecated) | **VERIFY** with `azd ai agent init` output. FOUNDRY_* env names are reserved in containers, so the model override is `MICROSOFT_FOUNDRY_MODEL_DEPLOYMENT_NAME`. |
| Optimizer | `.agent_configs/baseline/{metadata.yaml,instructions.md,tools.json,skills/}` + `azure-ai-agentserver-optimization.load_config()` | Verify current service/region availability and multimodal task mapping; no live optimization result established here. |
| Cloud evaluation | `project.evaluators.create_version` (code evaluator, `grade(sample, item)`) + `client.evals.create/runs.create` | Rows mode mirrors the SDK sample. Agent-target mode (`azure_ai_target_completions` with an `input_image` template) is **VERIFY**. |
| Tracing | Azure Monitor export of explicit business spans when connected; local JSONL mirror | Responses auto-instrumentation defaults off due to SDK compatibility issues; verify hosted server traces independently. |
| Insights | `AIProjectClient(..., allow_preview=True).beta.agent_insight_monitors` | Preview; judge must be GPT-5+. |

## Deferred to the cloud phase
Blob/Event Grid/Service Bus/Durable Functions application orchestration, Cosmos DB/SQL persistence,
Foundry IQ knowledge base, human-review queue service, shadow/canary routing. The contracts above
are what those components will call. Foundry provisioning Bicep already exists under
[infra/](../infra/); it is distinct from the deferred application infrastructure.
