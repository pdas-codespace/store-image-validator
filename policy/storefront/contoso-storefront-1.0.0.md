---
customer_id: contoso
category: storefront
rule_pack_id: contoso-storefront
rule_pack_version: 1.0.0
jurisdiction: US
language: en-US
---
# Store Front (Contoso) interpretation guidance (v1.0.0)

<!-- GENERATED from rules/source/contoso-validation-rules.md by scripts/rules_from_md.py. Edit the source, not this file.
     Local stand-in for Foundry IQ; filter by the metadata above when moving to a knowledge base. -->

## SF-001 Full storefront view
Requirement: Full view of the storefront or approved plaza directory sign.
- Plaza directory signs are acceptable.
- The full storefront means both side edges of the unit's facade and the entrance are inside the frame. (interpretation note)

## SF-002 Branding readable
Requirement: Contoso branding is clearly readable.
- The words "Contoso" (or the Contoso logo wordmark) must be legible without guessing letters. (interpretation note)

## SF-003 Window and door clings
Requirement: Window and door clings are visible.
- Clings on the entrance door(s) and on the storefront windows both count. If the door is outside the frame, the rule is CANNOT_DETERMINE, not FAIL. (interpretation note)

## SF-004 Previous tenant remnants
Requirement: No visible remnants of a previous tenant around the Contoso sign.
- Temporary seasonal signage is acceptable.
- Only deduct for previous tenant remnants that are directly around the Contoso sign.
- Remnants include old signage, ghost lettering, brackets with old logos or paint outlines adjacent to the Contoso sign. Remnants elsewhere on the facade or on neighbouring units are ignored. (interpretation note)
