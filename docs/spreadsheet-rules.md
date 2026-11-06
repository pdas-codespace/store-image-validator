# Using the business rules spreadsheet in the demo

## Recommendation

Use Excel as the **business authoring and approval artifact**, and the versioned YAML
rule pack as the **published runtime contract**. Keep interpretation guidance separate
from agent instructions and evaluation labels.

```text
Business workbook (approved source, not read at runtime)
  -> reviewed extraction and normalization
  -> versioned rules + policy guidance
  -> human-labeled evaluation cases
  -> agent evidence -> deterministic scoring -> release gates
```

The supplied screenshot shows `Category`, `PROMPT`, and `SCORE_THRESHOLD`, a storefront
row, and part of a bathroom row. It is not the workbook itself. The screenshot's
threshold value is clipped, and the bathroom requirements are incomplete; neither
should be imported by guessing.

There is currently **no Excel importer or runtime spreadsheet reader** in this
workspace. This guide describes how to use and house the source without changing
inspection behavior.

## Where each piece belongs

| Content | Recommended home | Why |
|---|---|---|
| Original workbook and approval history | Approved private document library; optionally a new `rules\source\` folder if repository access/licensing permits | Preserve the business source unchanged; do not package it into the agent |
| Source reference | A reviewed source record alongside the workbook or in the rule-change review | Capture workbook version/hash, sheet, cell/row, owner, approval date, and published rule-pack version |
| Atomic executable requirements | [Versioned storefront YAML](../rules/storefront/contoso-storefront-1.0.0.yaml) | Stable IDs, rule types, explicit scoring policy |
| Exceptions/interpretation | [Versioned policy Markdown](../policy/storefront/contoso-storefront-1.0.0.md) | Directory-sign alternative, seasonal signage, sign-area scope |
| General reasoning behavior | [Agent instructions](../.agent_configs/baseline/instructions.md) and [storefront skill](../.agent_configs/baseline/skills/storefront-inspection/SKILL.md) | How to inspect, cite evidence, abstain, and ignore in-image instructions |
| Example photos and human answers | [Evaluation datasets](../evaluation/datasets/) with approved image storage | Tests of rules, not the rules themselves |
| Quality acceptance targets | [Release gates](../evaluation/release_gates.yaml) | Measure false passes, abstention, consistency, and failures |

`rules\source\` is a proposed location, not a folder populated by this task. If you add
the workbook there, explicitly exclude `rules/source/` from both the remote-code upload
and Docker build inputs: current packaging includes the rules tree. Do not merely
assume a source workbook is excluded because `.env` is excluded.

For this demo, a private document library is the simplest safe home for the original.
Show a sanitized workbook view, then switch to the published YAML and policy files.
No runtime Foundry IQ, Search index, or new storage deployment is needed to do that.

## Mapping the visible storefront row to the current code

| Spreadsheet content | Published representation |
|---|---|
| Category: Store Front (Contoso) | `category: storefront`, `rulePackId: contoso-storefront` |
| Full storefront or approved plaza directory sign | SF-001, coverage rule and accepted alternatives |
| Contoso branding clearly readable | SF-002, text-legibility rule |
| Window and door clings visible | SF-003, visual-presence rule |
| No previous-tenant remnants around the Contoso sign | SF-004, prohibited-visual rule with scoped ignores |
| Directory signs acceptable | SF-001 alternative plus interpretation guidance |
| Temporary seasonal signage acceptable | SF-004 ignore plus interpretation guidance |
| Deduct only for remnants directly around the sign | SF-004 requirement and policy scope |
| Assign integer score from 0 to 10 | Application scoring range and half-up rounding, not a model-authored score |
| `SCORE_THRESHOLD` | Map to `scoring.passThreshold` **only after confirming what the source means and its actual value** |

The current pack already implements the visible storefront meaning. It has a pass
threshold of 8, review threshold of 6, confidence floor of 0.65, weights
2.5/2.5/2.0/3.0, and mandatory SF-001/SF-002. **Those weights, mandatory flags,
confidence/review policy, and abstention handling are not established by this
screenshot.** Present them as existing implementation choices requiring business
confirmation, not values extracted from Excel.

The visible storefront prompt appears duplicated inside the same cell. Normalize it
to one set of four rules while preserving the original unchanged. Duplicated prose
must not become eight rules or double the scoring weight.

## Keep three kinds of threshold separate

1. **Inspection pass threshold:** business cutoff for one storefront's weighted score.
2. **Confidence floor:** when a model judgment must become CANNOT_DETERMINE.
3. **Evaluation release gates:** acceptable measured performance across labeled cases.

A spreadsheet score threshold of 8, if confirmed, would not mean an 80% evaluation
accuracy gate. Similarly, a four-rule description alone does not specify how to
weight the rules or when a mandatory failure overrides the score.

## A simple, controlled publication process

1. Obtain the actual `.xls`/`.xlsx`, workbook version, owner, and approval status.
   Preserve the original. Do not reconstruct hidden rows from the screenshot.
2. Review all sheets and actual cell values, merged category cells, formulas, duplicate
   text, and threshold semantics. Never execute macros to extract rules.
3. Normalize categories and split each requirement into one stable rule ID.
4. Have the business owner confirm weights, mandatory flags, pass/review thresholds,
   accepted alternatives, missing-evidence behavior, and effective date.
5. Publish rules and policy under a **new explicit version** when behavior changes;
   do not overwrite an already approved version with different semantics.
6. Record workbook-to-rule lineage outside the runtime schema, or extend the schema
   deliberately. Arbitrary new YAML fields are rejected by the current strict schema.
7. Add adjudicated photos covering each requirement and exception. Update each
   dataset row's pinned rule-pack version consciously; retain old-version regression cases.
8. Validate rules, run tests, and run real-model/full-pipeline and hosted evaluations.
9. Review differences and approve deployment. Keep prior rules/configuration and
   platform versions for rollback.

An eventual import tool should produce a **draft plus validation errors**, not silently
publish or overwrite business rules. For two or a few categories, a reviewed manual
conversion is simpler than adding an importer before the demo.

## Where to put this in the demonstration

Add a 2-3 minute opening, before the first image:

1. **Show Excel:** "This is the policy the business gave us."
2. **Show SF-001 through SF-004:** "We turn prose into versioned, independently
   testable requirements. Duplicate prompt text is not duplicate business policy."
3. **Show the policy exceptions:** "Directory signs and seasonal banners are
   intentional exceptions, not model improvisation."
4. **Show scoring code:** "The model does not award itself a 10. Business code
   computes the result from evidence and approved policy."
5. **Show two scope cases:** a remnant away from the sign should not deduct; a remnant
   directly around it should. The [golden dataset](../evaluation/datasets/golden.jsonl)
   already contains this contrast.
6. **Start the Foundry loop:** trace the answer, inspect recurring problems, evaluate,
   and optimize behavior while preserving the approved rules.

**Narration:** "Excel defines what good means. Foundry helps us determine whether the
agent reliably applies it. The optimizer improves the inspector, not the policy."

The screenshot also mentions bathrooms. Show that as a **future extension**, not a
working category: [bathroom photos](../fixtures/images/Bathroom/) exist, but there is
no checked-in bathroom rule pack, policy, or labeled dataset. "Safe and usable" also
needs observable criteria; a photo cannot certify all hidden safety conditions.
Obtain the full approved row and define those criteria before claiming bathroom support.

## Should the workbook go into Foundry IQ?

Not as the authoritative scoring mechanism for this demo. Keep exact rule selection,
weights, versions, and thresholds deterministic. Later, Foundry IQ could retrieve
approved supporting documents/examples filtered by category, customer, effective date,
and rule-pack version. The current policy retrieval is local Markdown; do not
describe it as an already connected Foundry IQ knowledge base.
