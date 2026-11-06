# Agent Optimizer loop

What the optimizer may change (`.agent_configs/`): instructions, skills, tool **descriptions**, model,
temperature. What it may not change: everything in `rules/` and `policy/`, release gates and datasets
(`guardrails.yaml`). Tools are read-only (`get_rule_pack`, `retrieve_policy_guidance`), so optimizer
runs have no side effects.

1. Deploy the hosted agent (`azd up`) and upload fixture images to a private container.
2. `python optimizer/build_optimizer_dataset.py` → `evaluation/datasets/optimizer_tasks.jsonl`.
3. Register evaluators: `python evaluation\run_foundry_eval.py register`.
   Agent-target evaluation also registers/pins the five raw-agent graders it uses.
4. `azd ai agent optimize --config .\optimizer\eval.yaml --eval-model <judge-deployment> --optimize-model <supported-deployment>`
   from the workspace root (confirm flags with `azd ai agent optimize --help`). The config is not at
   the root and must be selected explicitly. Verify actual image handoff before trusting results.
5. `azd ai agent optimize apply --candidate <id>` → writes `.agent_configs/<id>/`.
6. `python optimizer/compare_candidate.py <id>` → scope check + same frozen dataset for baseline vs
   candidate + gates + token delta. Exit 0 = eligible for **manual** review.
7. Promote by copying the candidate into `baseline/` in a reviewed PR → `azd deploy` → watch Insights.
   Roll back by reverting that PR and redeploying (the previous agent version stays in Foundry).

See the [demo runbook](../docs/demo-guide.md) for prerequisites, expected outputs, SAS handling,
and limitations: comparison uses direct model calls, does not exercise hosted tools, and requires
manual review of protected paths and actual model/config selection.

## NCUS / hosted identity variant

Use the [NCUS demo runbook](../docs/ncus-demo.md), not root `azd up`.
`python optimizer\build_optimizer_dataset.py --image-auth hosted` emits Blob
basenames using the same query/ground-truth builder as hosted evaluation.
No local Blob credential or SAS is used; candidates must actually execute the
hosted middleware with an authorized runtime identity and the correct input adapter.

The operator wrapper `python scripts\ncus_demo.py optimize --agent kimi
--confirm-optimizer-ready` prepares fixed train/validation inputs and a
version-pinned NCUS config, retaining `FW-Kimi-K3` as the target model.
Only acknowledge that flag after verifying cloud/local grader agreement and
candidate image access. The earlier Entra export still has a known grading
discrepancy; optimizing against those incorrect scores is not a valid quality demo.
No candidates are applied/promoted by the wrapper.
