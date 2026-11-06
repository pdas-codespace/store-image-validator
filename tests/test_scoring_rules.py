import json
import unittest

import yaml

from siv import REPO_ROOT
from siv.rulepack import RULES_DIR, RulePackError, _parse, load_rule_pack, validate_all
from siv.scoring import decide

PACK = load_rule_pack("contoso-storefront", "1.0.0")


def agent(statuses, conf=0.9, usable=True, issues=()):
    return {"image_assessment": {"usable": usable, "issues": list(issues)}, "recommended_next_image": None,
            "rule_results": [{"rule_id": k, "status": v, "confidence": conf, "reason": "r",
                              "evidence": [], "missing_evidence": ["m"] if v == "CANNOT_DETERMINE" else []}
                             for k, v in statuses.items()]}


ALL_PASS = {"SF-001": "PASS", "SF-002": "PASS", "SF-003": "PASS", "SF-004": "PASS"}


class Scoring(unittest.TestCase):
    def test_all_pass(self):
        d = decide(PACK, agent(ALL_PASS))
        self.assertEqual((d.decision, d.score, d.requires_human_review), ("PASS", 10, False))

    def test_mandatory_fail_overrides_score(self):
        d = decide(PACK, agent({**ALL_PASS, "SF-002": "FAIL"}))
        self.assertEqual((d.decision, d.score), ("FAIL", 8))  # 8/10 would pass without the override

    def test_mandatory_cd(self):
        d = decide(PACK, agent({**ALL_PASS, "SF-001": "CANNOT_DETERMINE"}))
        self.assertEqual(d.decision, "CANNOT_DETERMINE")
        self.assertTrue(d.requires_human_review)

    def test_non_mandatory_cd_blocks_pass_but_no_review(self):
        d = decide(PACK, agent({**ALL_PASS, "SF-003": "CANNOT_DETERMINE"}))
        self.assertEqual((d.decision, d.score, d.requires_human_review), ("CANNOT_DETERMINE", 9, False))

    def test_not_applicable_excluded_from_denominator(self):
        d = decide(PACK, agent({**ALL_PASS, "SF-004": "NOT_APPLICABLE"}))
        self.assertEqual((d.decision, d.score), ("PASS", 10))

    def test_fail_below_review_threshold(self):
        d = decide(PACK, agent({**ALL_PASS, "SF-003": "FAIL", "SF-004": "FAIL"}))
        self.assertEqual((d.decision, d.score, d.requires_human_review), ("FAIL", 5, False))

    def test_review_band(self):
        d = decide(PACK, agent({**ALL_PASS, "SF-004": "FAIL"}))
        self.assertEqual((d.decision, d.score), ("FAIL", 7))
        self.assertIn("score_in_review_band", d.review_reasons)

    def test_unusable_is_zero(self):
        d = decide(PACK, agent({k: "CANNOT_DETERMINE" for k in ALL_PASS}, usable=False))
        self.assertEqual((d.decision, d.score), ("CANNOT_DETERMINE", 0))

    def test_confidence_threshold_boundary(self):
        self.assertEqual(decide(PACK, agent(ALL_PASS, conf=0.65)).decision, "PASS")
        self.assertEqual(decide(PACK, agent(ALL_PASS, conf=0.64)).decision, "CANNOT_DETERMINE")

    def test_cd_never_converted_to_fail(self):
        d = decide(PACK, agent({k: "CANNOT_DETERMINE" for k in ALL_PASS}))
        self.assertTrue(all(r["status"] == "CANNOT_DETERMINE" for r in d.effective_rule_results))
        self.assertNotEqual(d.decision, "FAIL")


class RulePacks(unittest.TestCase):
    def test_all_rule_packs_valid(self):
        self.assertTrue(all(v == "ok" for v in validate_all().values()))

    def test_weights_hidden_from_agent(self):
        view = json.dumps([r.agent_view() for r in PACK.rules])
        self.assertNotIn("weight", view)
        self.assertNotIn("mandatory", view)

    def test_schema_rejects_unknown_rule_type(self):
        doc = yaml.safe_load((RULES_DIR / "storefront" / "contoso-storefront-1.0.0.yaml").read_text())
        doc["rules"][0]["type"] = "vibes"
        with self.assertRaises(RulePackError):
            _parse(doc, "x")

    def test_new_pack_needs_no_code(self):
        doc = yaml.safe_load((RULES_DIR / "storefront" / "contoso-storefront-1.0.0.yaml").read_text())
        doc.update(rulePackId="acme-restroom", category="bathroom")
        doc["rules"] = [{"id": "BR-001", "title": "Floor clean", "type": "condition_or_cleanliness",
                         "weight": 1, "mandatory": True, "requirement": "Floor has no visible debris."}]
        self.assertEqual(_parse(doc, "x").rule_ids, ["BR-001"])
