# Foundry setup checklist

For step-by-step runtime/deployment checks, see [Hosted Agent setup](hosted-agent-setup.md).
For the presenter sequence, see the [demo runbook](demo-guide.md). Standalone evaluation,
Insights, and optimizer scripts require exported environment variables; they do not load `.env`.

1. **Project + model**: a Foundry project with a vision-capable chat deployment (e.g. gpt-4.1 / gpt-5.x). Put
   its name in `MICROSOFT_FOUNDRY_MODEL_DEPLOYMENT_NAME` or `.agent_configs/baseline/metadata.yaml`.
2. **Your access**: Foundry User on the project (Foundry Project Manager for hosted-agent Insights).
3. **Tracing**: Foundry portal → your project → Tracing → connect Application Insights. Assign yourself
   Log Analytics Reader on it (plus Privileged Monitoring Data Reader if tables are protected).
4. **Insights**: a GPT-5 or newer judge deployment (`INSIGHTS_JUDGE_MODEL`); Monitoring Reader on App
   Insights for you **and** the project's managed identity; the managed identity also needs access to the
   judge deployment.
5. **Evaluation**: dataset uploads need write access to the project's storage.
6. **Content recording**: leave `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` off for real store
   images. Spans carry hashes and decisions, not pixels.
7. **Images for agent-target eval / optimizer**: private blob container + short-lived read-only SAS in
   `SIV_EVAL_IMAGE_SAS` for URL mode. `--image-auth entra` instead downloads
   private blobs using your `az login` identity (Storage Blob Data Reader) and submits inline
   image bytes; clear `SIV_EVAL_IMAGE_SAS` for that mode. See the
   [Entra evaluation walkthrough](foundry-evaluation-schema-and-blob-flow.md#entra-authenticated-image-download-no-sas).
   Do not use public URLs for real store photos.
8. **Hosted Blob identity**: `--image-auth hosted` sends basenames, and the updated
   worker resolves them with managed/workload identity before inference. Deploy
   `MICROSOFT_EVAL_IMAGE_CONTAINER_URL` and grant the actual deployed
   `instance_identity.principal_id` container-scoped Storage Blob Data Reader.
   The workstation does not need Blob data access in this mode. Optimizer candidate
   identity/input handling must be verified separately. See the
   [NCUS demo](ncus-demo.md) for environment isolation, role commands, and grading gates.
