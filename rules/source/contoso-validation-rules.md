# Contoso — Image Validation Rules

Source: `ValidationRules.xlsx` (Sheet1, 9 categories), converted 2026-10-14.
This file is the editable source of truth for rule packs. After editing, regenerate:

```bash
python scripts/rules_from_md.py            # writes rules/<category>/*.yaml and policy/<category>/*.md
python scripts/rules_from_md.py --check    # CI: fails if generated files are out of date
```

## How to read this file

- Each `##` section with a **Rule pack** table becomes one versioned rule pack.
- **Requirements** and **Guidance** come from the spreadsheet word for word, split into one rule per requirement.
- The spreadsheet only provides the requirement text and `SCORE_THRESHOLD`. These columns are **proposed defaults** for you to confirm:
  **Type**, **Weight**, **Mandatory**, **Can't determine when**, **Review threshold**, and the storefront **Interpretation notes**.
  (The storefront weights and mandatory flags come from the build specification §6.)
- The spreadsheet's closing line, "Assign an integer score from 0 to 10.", is left out on purpose. In this project the model never scores; `siv/scoring.py` calculates the score from the rule results and weights.
- `SCORE_THRESHOLD` → **Pass threshold**.

Guidance bullet tags (optional):

| Tag | Effect |
|---|---|
| `- text` | Category-wide guidance (goes to the policy file the agent reads) |
| `- [SF-004] text` | Note for one rule (policy file) |
| `- [SF-004 ignore] text` | Also added to the rule's `ignore` list (shown to the agent with the rule) |
| `- [SF-001 accept] text` | Also added to the rule's `acceptedAlternatives` list |
| `- [BR-002,BR-003 ignore] text` | Same, for several rules |

Rule types must be one of: `visual_presence`, `visual_absence`, `prohibited_visual`, `text_legibility`, `count_or_quantity`, `spatial_relationship`, `condition_or_cleanliness`, `coverage_or_full_view`, `comparison_to_reference`, `seal_or_label_integrity`, `date_or_code_readability`. Use `;` to separate several "can't determine" conditions. Don't use `|` inside cells.

---

## Store Front (Contoso)

| Field | Value |
|---|---|
| Rule pack | contoso-storefront |
| Version | 1.0.0 |
| Category | storefront |
| Customer | contoso |
| Effective from | 2026-10-01 |
| Images | 1-5 |
| Pass threshold | 8 |
| Review threshold | 6 |

### Rules

| ID | Title | Requirement | Type | Weight | Mandatory | Can't determine when |
|---|---|---|---|---|---|---|
| SF-001 | Full storefront view | Full view of the storefront or approved plaza directory sign. | coverage_or_full_view | 2.5 | yes | Storefront boundaries are outside the frame; sign is materially occluded; image is too blurred to identify the location |
| SF-002 | Branding readable | Contoso branding is clearly readable. | text_legibility | 2.5 | yes | Sign is blurred, glared or too distant to read; sign is outside the frame |
| SF-003 | Window and door clings | Window and door clings are visible. | visual_presence | 2.0 | no | Windows or entrance doors are outside the frame; glass is obscured by heavy glare or reflections |
| SF-004 | Previous tenant remnants | No visible remnants of a previous tenant around the Contoso sign. | prohibited_visual | 3.0 | no | The area directly around the Contoso sign is not visible |

### Guidance

- [SF-001 accept] Plaza directory signs are acceptable.
- [SF-004 ignore] Temporary seasonal signage is acceptable.
- [SF-004 ignore] Only deduct for previous tenant remnants that are directly around the Contoso sign.

### Interpretation notes

- [SF-001] The full storefront means both side edges of the unit's facade and the entrance are inside the frame.
- [SF-002] The words "Contoso" (or the Contoso logo wordmark) must be legible without guessing letters.
- [SF-003] Clings on the entrance door(s) and on the storefront windows both count. If the door is outside the frame, the rule is CANNOT_DETERMINE, not FAIL.
- [SF-004] Remnants include old signage, ghost lettering, brackets with old logos or paint outlines adjacent to the Contoso sign. Remnants elsewhere on the facade or on neighbouring units are ignored.

<details><summary>Source prompt (spreadsheet)</summary>

The spreadsheet cell repeats this prompt twice; it is included once here.

```text
Evaluate this Contoso storefront photo.

Requirements:
1. Full view of the storefront or approved plaza directory sign.
2. Contoso branding is clearly readable.
3. Window and door clings are visible.
4. No visible remnants of a previous tenant around the Contoso sign.

Additional Guidance:
- Plaza directory signs are acceptable.
- Temporary seasonal signage is acceptable.
- Only deduct for previous tenant remnants that are directly around the Contoso sign.

Assign an integer score from 0 to 10.
```
</details>

---

## Bathroom (Contoso)

| Field | Value |
|---|---|
| Rule pack | contoso-bathroom |
| Version | 1.0.0 |
| Category | bathroom |
| Customer | contoso |
| Effective from | 2026-10-01 |
| Images | 1-5 |
| Pass threshold | 8 |
| Review threshold | 6 |

### Rules

| ID | Title | Requirement | Type | Weight | Mandatory | Can't determine when |
|---|---|---|---|---|---|---|
| BR-001 | Bathroom visible | Bathroom is clearly visible. | coverage_or_full_view | 3 | yes | Image is too dark, blurred or close-up to show the room; image does not show a bathroom |
| BR-002 | Floor and walls clean | Floor and walls are clean. | condition_or_cleanliness | 4 | yes | Floor or walls are mostly outside the frame; lighting is too dark to judge cleanliness |
| BR-003 | Safe and usable | Bathroom appears safe and usable. | condition_or_cleanliness | 3 | no | Too little of the room is visible to judge safety or usability |

### Guidance

- [BR-001] Sink or toilet does not need to be visible.
- Focus on operational cleanliness.
- [BR-002,BR-003 ignore] Ignore normal wear, ceiling stains, peeling paint, or cosmetic issues.

<details><summary>Source prompt (spreadsheet)</summary>

```text
Evaluate this Contoso bathroom photo.

Requirements:
1. Bathroom is clearly visible.
2. Floor and walls are clean.
3. Bathroom appears safe and usable.

Additional Guidance:
- Sink or toilet does not need to be visible.
- Focus on operational cleanliness.
- Ignore normal wear, ceiling stains, peeling paint, or cosmetic issues.

Assign an integer score from 0 to 10.
```
</details>

---

## Pylon (Contoso)

| Field | Value |
|---|---|
| Rule pack | contoso-pylon |
| Version | 1.0.0 |
| Category | pylon |
| Customer | contoso |
| Effective from | 2026-10-01 |
| Images | 1-5 |
| Pass threshold | 8 |
| Review threshold | 6 |

### Rules

| ID | Title | Requirement | Type | Weight | Mandatory | Can't determine when |
|---|---|---|---|---|---|---|
| PY-001 | Valid identification sign | Valid Contoso store identification sign. | visual_presence | 3 | yes | Sign is outside the frame; image is too blurred or distant to tell what the sign is |
| PY-002 | Branding readable | Contoso branding is readable. | text_legibility | 3 | yes | Sign is blurred, glared or too distant to read |
| PY-003 | Branding fills sign area | Branding fills the intended sign area. | spatial_relationship | 2 | no | The edges of the sign panel are outside the frame or hidden |
| PY-004 | Identifies store location | Sign can easily identify the store location. | visual_presence | 2 | no | Too little of the surroundings is visible to relate the sign to the store |

### Guidance

- [PY-001 accept] Seasonal banner signs are acceptable.
- [PY-001 accept] Plaza directories are acceptable.
- Ignore sign position or construction material.
- Only deduct if branding is unreadable, substantially obstructed, or the image is not a valid store identification sign.

<details><summary>Source prompt (spreadsheet)</summary>

```text
Evaluate this Contoso store identification sign.

Requirements:
1. Valid Contoso store identification sign.
2. Contoso branding is readable.
3. Branding fills the intended sign area.
4. Sign can easily identify the store location.

Additional Guidance:
- Seasonal banner signs are acceptable.
- Plaza directories are acceptable.
- Ignore sign position or construction material.
- Only deduct if branding is unreadable, substantially obstructed, or the image is not a valid store identification sign.

Assign an integer score from 0 to 10.
```
</details>

---

## EOS Open Container

| Field | Value |
|---|---|
| Rule pack | contoso-eos-open-container |
| Version | 1.0.0 |
| Category | eos-open-container |
| Customer | contoso |
| Effective from | 2026-10-01 |
| Images | 1-5 |
| Pass threshold | 8 |
| Review threshold | 6 |

### Rules

| ID | Title | Requirement | Type | Weight | Mandatory | Can't determine when |
|---|---|---|---|---|---|---|
| EOC-001 | Contents match container type | Contents are appropriate for the container type. | visual_presence | 3 | yes | Container type is not stated in the request and cannot be seen; contents are hidden by darkness or the door frame |
| EOC-002 | No contamination | No contamination with fixtures, registers, or communication kits. | prohibited_visual | 4 | yes | Large parts of the load are not visible |
| EOC-003 | Orderly and secure load | Load is orderly and secure. | condition_or_cleanliness | 3 | no | The load is mostly outside the frame or too dark to judge |

### Guidance

- Partial loads are acceptable.
- Empty space is acceptable.
- Ignore weather, lighting, people, and surrounding conditions.

<details><summary>Source prompt (spreadsheet)</summary>

```text
Evaluate this End of Season open container or trailer.

Requirements:
1. Contents are appropriate for the container type.
2. No contamination with fixtures, registers, or communication kits.
3. Load is orderly and secure.

Additional Guidance:
- Partial loads are acceptable.
- Empty space is acceptable.
- Ignore weather, lighting, people, and surrounding conditions.

Assign an integer score from 0 to 10.
```
</details>

---

## EOS Contents Sheet

| Field | Value |
|---|---|
| Rule pack | contoso-eos-contents-sheet |
| Version | 1.0.0 |
| Category | eos-contents-sheet |
| Customer | contoso |
| Effective from | 2026-10-01 |
| Images | 1-5 |
| Pass threshold | 8 |
| Review threshold | 6 |

### Rules

| ID | Title | Requirement | Type | Weight | Mandatory | Can't determine when |
|---|---|---|---|---|---|---|
| ECS-001 | Correct summary sheet | Correct EOS summary sheet. | visual_presence | 3 | yes | Form title or layout is outside the frame or unreadable |
| ECS-002 | Sheet legible | Sheet is legible. | text_legibility | 3 | yes | Image is blurred, glared, too dark or too distant |
| ECS-003 | Store, container and seal info readable | Store, container, and seal information can be read. | date_or_code_readability | 4 | yes | The store, container or seal fields are cropped, folded or covered |

### Guidance

- [ECS-003] Blank carton counts are acceptable for fixture containers.
- Focus primarily on legibility and identification.

<details><summary>Source prompt (spreadsheet)</summary>

```text
Evaluate this End of Season container summary sheet.

Requirements:
1. Correct EOS summary sheet.
2. Sheet is legible.
3. Store, container, and seal information can be read.

Additional Guidance:
- Blank carton counts are acceptable for fixture containers.
- Focus primarily on legibility and identification.

Assign an integer score from 0 to 10.
```
</details>

---

## EOS Closed Container

| Field | Value |
|---|---|
| Rule pack | contoso-eos-closed-container |
| Version | 1.0.0 |
| Category | eos-closed-container |
| Customer | contoso |
| Effective from | 2026-10-01 |
| Images | 1-5 |
| Pass threshold | 8 |
| Review threshold | 6 |

### Rules

| ID | Title | Requirement | Type | Weight | Mandatory | Can't determine when |
|---|---|---|---|---|---|---|
| ECC-001 | Fully closed | Container is fully closed. | visual_presence | 4 | yes | The doors are outside the frame or blocked from view |
| ECC-002 | No structural damage | No visible structural damage. | condition_or_cleanliness | 3 | no | Large parts of the container body are outside the frame or too dark |
| ECC-003 | Suitable for transport | Container appears suitable for transport. | condition_or_cleanliness | 3 | no | Too little of the container is visible to judge |

### Guidance

- [ECC-001] Seal visibility is not required.
- Ignore surrounding conditions.

<details><summary>Source prompt (spreadsheet)</summary>

```text
Evaluate this End of Season closed container or trailer.

Requirements:
1. Container is fully closed.
2. No visible structural damage.
3. Container appears suitable for transport.

Additional Guidance:
- Seal visibility is not required.
- Ignore surrounding conditions.

Assign an integer score from 0 to 10.
```
</details>

---

## EOS Seal

| Field | Value |
|---|---|
| Rule pack | contoso-eos-seal |
| Version | 1.0.0 |
| Category | eos-seal |
| Customer | contoso |
| Effective from | 2026-10-01 |
| Images | 1-5 |
| Pass threshold | 8 |
| Review threshold | 6 |

### Rules

| ID | Title | Requirement | Type | Weight | Mandatory | Can't determine when |
|---|---|---|---|---|---|---|
| ESL-001 | Plastic seal present | Plastic security seal is present. | visual_presence | 3 | yes | The door latch area is outside the frame or blocked |
| ESL-002 | Seal intact | Seal is intact. | seal_or_label_integrity | 3 | yes | Part of the seal body or locking end is hidden |
| ESL-003 | Seal number readable | Seal number is readable. | date_or_code_readability | 3 | yes | Number is blurred, glared, turned away or too small to read |
| ESL-004 | Expected seal colour | Seal colour matches the expected seal colour. If no expected colour is given in the policy guidance, return NOT_APPLICABLE. | comparison_to_reference | 1 | no | Colour cannot be judged because of lighting or glare |

### Guidance

- [ESL-001] Padlocks are not acceptable.
- [ESL-004] Unexpected seal colors should only slightly reduce the score if the seal is otherwise valid.

<details><summary>Source prompt (spreadsheet)</summary>

```text
Evaluate this End of Season container seal.

Requirements:
1. Plastic security seal is present.
2. Seal is intact.
3. Seal number is readable.

Additional Guidance:
- Padlocks are not acceptable.
- Unexpected seal colors should only slightly reduce the score if the seal is otherwise valid.

Assign an integer score from 0 to 10.
```
</details>

---

## EOS Tracking Summary

| Field | Value |
|---|---|
| Rule pack | contoso-eos-tracking-summary |
| Version | 1.0.0 |
| Category | eos-tracking-summary |
| Customer | contoso |
| Effective from | 2026-10-01 |
| Images | 1-5 |
| Pass threshold | 8 |
| Review threshold | 6 |

### Rules

| ID | Title | Requirement | Type | Weight | Mandatory | Can't determine when |
|---|---|---|---|---|---|---|
| ETS-001 | Correct tracking form | Correct EOS tracking summary form. | visual_presence | 3 | yes | Form title or layout is outside the frame or unreadable |
| ETS-002 | Sheet legible | Sheet is legible. | text_legibility | 2.5 | yes | Image is blurred, glared, too dark or too distant |
| ETS-003 | Store identifiable | Store information is identifiable. | date_or_code_readability | 2.5 | yes | The store fields are cropped, folded or covered |
| ETS-004 | Summary readable | Summary information is readable. | text_legibility | 2 | no | The summary section is cropped, folded or covered |

### Guidance

- [ETS-001,ETS-002,ETS-003,ETS-004] Missing signatures alone should not significantly reduce the score.

<details><summary>Source prompt (spreadsheet)</summary>

```text
Evaluate this End of Season tracking summary sheet.

Requirements:
1. Correct EOS tracking summary form.
2. Sheet is legible.
3. Store information is identifiable.
4. Summary information is readable.

Additional Guidance:
- Missing signatures alone should not significantly reduce the score.

Assign an integer score from 0 to 10.
```
</details>

---

## EOS Overview

| Field | Value |
|---|---|
| Rule pack | contoso-eos-overview |
| Version | 1.0.0 |
| Category | eos-overview |
| Customer | contoso |
| Effective from | 2026-10-01 |
| Images | 1-5 |
| Pass threshold | 8 |
| Review threshold | 6 |

### Rules

| ID | Title | Requirement | Type | Weight | Mandatory | Can't determine when |
|---|---|---|---|---|---|---|
| EOV-001 | Contents organized | Container contents appear organized. | condition_or_cleanliness | 2.5 | no | The load is mostly outside the frame or too dark to judge |
| EOV-002 | Load secure | Load is secure. | condition_or_cleanliness | 2.5 | no | Restraints and load edges are not visible |
| EOV-003 | No contamination | No obvious contamination or prohibited items. | prohibited_visual | 3 | yes | Large parts of the load are not visible |
| EOV-004 | Container undamaged | Container appears undamaged. | condition_or_cleanliness | 2 | no | Too little of the container body is visible |

### Guidance

- Partial loads are acceptable.
- Empty space is acceptable.
- Ignore weather and surrounding conditions.

<details><summary>Source prompt (spreadsheet)</summary>

```text
Evaluate this End of Season overview photo.

Requirements:
1. Container contents appear organized.
2. Load is secure.
3. No obvious contamination or prohibited items.
4. Container appears undamaged.

Additional Guidance:
- Partial loads are acceptable.
- Empty space is acceptable.
- Ignore weather and surrounding conditions.

Assign an integer score from 0 to 10.
```
</details>

---

## Open questions for the business owner

1. **Weights and mandatory flags** for every category except storefront are proposals. Confirm them before you trust any score.
2. **Review threshold** isn't in the spreadsheet; 6 is the spec default for every category.
3. **EOS Open Container (EOC-001):** "appropriate for the container type" needs the container type (e.g. merchandise vs fixtures). It should come with the submission. Until it does, the agent will often return CANNOT_DETERMINE.
4. **EOS Seal (ESL-004):** what is the expected seal colour? Until it is added to the guidance, ESL-004 returns NOT_APPLICABLE and has no effect on the score.
5. **EOS Tracking Summary:** a missing signature currently has no effect on the score at all. If it should cost a little, add a low-weight, non-mandatory rule for it.
6. **Minor rules and abstention:** in the current decision policy, any CANNOT_DETERMINE (even on a non-mandatory rule) prevents a PASS. Decide whether low-weight rules such as ESL-004 should be exempt.
