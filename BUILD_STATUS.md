# Build Status

Scope of this phase (agreed): analyze images and evaluate findings with the Foundry quality loop
(tracing, evaluation, insights, optimizer). Production cloud design is deferred.

## Completed
- Rule-pack schema + Contoso storefront rule pack 1.0.0; explicit version resolution, no fallback; rule-type registry (11 types).
- Agent output JSON Schema (strict-mode compatible) and contract checks with one corrective retry.
- Deterministic scoring/decision engine, confidence gate, abstention prefix + re-capture guidance, human-review reasons.
- Analyzers: `foundry-model` (Responses API on a project deployment), `hosted-agent` (deployed agent by name), `replay` (offline).
- Local pipeline with image intake/hashing, policy retrieval (Foundry IQ stand-in), idempotent result store, decision records.
- Tracing: OTel spans with the spec's dimensions → App Insights (Foundry Tracing / Insights) + local JSONL mirror; no image data in spans.
- Evaluation: 4 dataset partitions (8 synthetic cases), 11 stdlib code evaluators, aggregate metrics, release gates, local runner, Foundry cloud runner (rows + agent-target).
- Insights: scan/list/schedule script (beta.agent_insight_monitors), annotation taxonomy + export to production-regression dataset, 5 KQL queries.
- Optimizer: `.agent_configs/baseline` (instructions, storefront skill, tool descriptions, model), guardrails, candidate scope check + baseline-vs-candidate comparison.
- Hosted agent (`agent/main.py`, Dockerfile, azure.yaml), CI workflow (offline always, live eval when Azure vars set).

## Tests Passing
- 47 unit/acceptance tests (`python -m unittest discover -s tests -t .`), including the 10 mandatory spec cases
  (verified 2026-10-15 with Python 3.12.10).
- `python evaluation/run_local_eval.py` (replay): all 12 gates pass.

## Azure / Foundry Resources Required
- Foundry project + vision-capable chat deployment; Application Insights connected to the project.
- GPT-5+ deployment as Insights judge. Private blob container for eval images (agent-target / optimizer).

## Manual Configuration Still Required
- `.env` from `.env.example`; `az login`; roles per docs/foundry-setup.md.
- `azd up` for the hosted agent; verify items marked VERIFY in docs/architecture.md.

## Known Limitations
- Live Foundry behavior was not verified during the 2026-10-15 documentation pass: Azure MCP discovery
  failed authentication. Offline tests include fake-client request shapes, not live service certification.
- All evaluation images are synthetic drawings; replay metrics are 100% by construction. Real quality numbers need real,
  human-adjudicated photos (start with the reference Contoso storefront photo, spec §13).
- Hosted agent supplies a strict response-format option, but enforcement/image handoff depends on the
  framework/runtime version and needs live verification; the caller pipeline validates and retries.
- Policy guidance is a local file, not Foundry IQ. No event-driven application orchestration or persistence
  service yet. Foundry Bicep templates are present under [infra/](infra/), including optional networking/ACR.

## Demo documentation
- [Presenter runbook](docs/demo-guide.md), [codebase tour](docs/codebase-guide.md),
  [Hosted Agent setup](docs/hosted-agent-setup.md), and [business spreadsheet mapping](docs/spreadsheet-rules.md).
- Confirm deployment/model settings and the version-sensitive integration surfaces before a live demo;
  the runbook distinguishes local replay, direct-model, and hosted-agent evidence.

## Evaluation Results
- Replay (synthetic, plumbing check): decision accuracy 1.0, rule agreement 1.0, false pass 0, abstention P/R 1.0/1.0.
- Live model: not yet run.

## Next Implementation Step
- Run `python -m siv analyze <real photo>` and `run_local_eval.py --provider foundry-model --repeats 2`; add 20+ real labeled
  photos across partitions; then deploy the hosted agent and run Insights + Optimizer.
