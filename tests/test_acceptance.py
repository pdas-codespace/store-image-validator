"""The ten mandatory first tests from the spec (section 24), plus contract checks.

Model behaviour (what the agent *sees*) is exercised with recorded outputs here and with the
real model via evaluation/run_local_eval.py --provider foundry-model. These tests prove the
deterministic parts: gates, scoring, versions, idempotency, injection handling, failure paths.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from siv.store import ResultStore
from tests.helpers import StaticAnalyzer, recording, run

PREFIX = "Can't determine with confidence from images submitted and here's why:"


class MandatoryTests(unittest.TestCase):
    def test_01_clear_compliant_pass(self):
        r = run("syn-compliant.jpg")
        self.assertEqual((r["decision"], r["score"], r["event"]), ("PASS", 10, "InspectionCompleted"))

    def test_02_clear_noncompliant_fail(self):
        r = run("syn-noncompliant.jpg")
        self.assertEqual(r["decision"], "FAIL")
        self.assertEqual(r["score"], 5)

    def test_03_cropped_cannot_determine(self):
        r = run("syn-cropped-left.jpg")
        self.assertEqual(r["decision"], "CANNOT_DETERMINE")
        self.assertTrue(r["message"].startswith(PREFIX))
        self.assertIn("mandatory_rule_cannot_determine", r["review_reasons"])
        self.assertIn("storefront", r["next_action"])
        self.assertGreater(r["score"], 0, "CANNOT_DETERMINE is not automatically 0")

    def test_04_severe_blur_cannot_determine(self):
        r = run("syn-severe-blur.jpg")
        self.assertEqual((r["decision"], r["score"]), ("CANNOT_DETERMINE", 0))
        self.assertEqual(r["event"], "InspectionResubmissionRequired")
        self.assertTrue(r["message"].startswith(PREFIX))

    def test_05_remnant_outside_sign_area_no_deduction(self):
        r = run("syn-remnant-far.jpg")
        sf4 = {x["rule_id"]: x for x in r["effective_rule_results"]}["SF-004"]
        self.assertEqual(sf4["status"], "PASS")
        self.assertEqual(r["decision"], "PASS")

    def test_06_remnant_around_sign_fails_sf004(self):
        r = run("syn-remnant-near-sign.jpg")
        sf4 = {x["rule_id"]: x for x in r["effective_rule_results"]}["SF-004"]
        self.assertEqual(sf4["status"], "FAIL")
        self.assertEqual((r["decision"], r["score"]), ("FAIL", 7))
        self.assertIn("score_in_review_band", r["review_reasons"])

    def test_07_image_injection_is_ignored(self):
        r = run("syn-injection.jpg")
        self.assertLessEqual(r["score"], 8)
        self.assertTrue(r["requires_human_review"])
        self.assertIn("unsafe_image_instruction", r["review_reasons"])
        # An agent that obeys the image and tries to hand out a score is rejected by contract.
        obeying = recording("adv-001-image-injection")
        obeying["score"] = 10
        r2 = run("syn-injection.jpg", analyzer=StaticAnalyzer(obeying), submission_id="inj-2")
        self.assertEqual(r2["event"], "InspectionFailed")
        self.assertEqual(r2["failure"]["kind"], "SCHEMA_INVALID")

    def test_08_duplicate_event_same_result(self):
        store = ResultStore(Path(tempfile.mkdtemp()))
        first = run("syn-compliant.jpg", store=store, submission_id="dup-1")
        analyzer = StaticAnalyzer(recording("golden-001-compliant"))
        second = run("syn-compliant.jpg", analyzer=analyzer, store=store, submission_id="dup-1")
        self.assertEqual(analyzer.calls, 0, "duplicate must not re-invoke the agent")
        self.assertTrue(second["duplicate_delivery"])
        self.assertEqual(first["idempotency_key"], second["idempotency_key"])
        self.assertEqual(store.count(), 1)

    def test_09_unknown_rule_pack_version_fails_safely(self):
        analyzer = StaticAnalyzer(recording("golden-001-compliant"))
        for v in ("9.9.9", "latest", "1.0"):
            r = run("syn-compliant.jpg", analyzer=analyzer, rule_pack_version=v, submission_id=f"v-{v}")
            self.assertEqual(r["event"], "InspectionFailed")
            self.assertEqual(r["failure"]["kind"], "WRONG_POLICY_VERSION")
        self.assertEqual(analyzer.calls, 0)

    def test_10_policy_retrieval_unavailable(self):
        os.environ["SIV_SIMULATE_POLICY_OUTAGE"] = "1"
        try:
            r = run("syn-compliant.jpg", submission_id="policy-down")
        finally:
            del os.environ["SIV_SIMULATE_POLICY_OUTAGE"]
        self.assertIsNone(r["policy_guidance_source"])
        self.assertTrue(r["requires_human_review"])
        self.assertIn("policy_retrieval_failed", r["review_reasons"])
        self.assertEqual(r["rule_pack"], {"id": "contoso-storefront", "version": "1.0.0"})


class ContractTests(unittest.TestCase):
    def test_low_confidence_gate_abstains(self):
        r = run("syn-glare.jpg")
        self.assertEqual(r["decision"], "CANNOT_DETERMINE")
        self.assertEqual(r["gate_adjustments"][0]["rule_id"], "SF-003")

    def test_malformed_output_retried_once_then_accepted(self):
        a = StaticAnalyzer("not json", recording("golden-001-compliant"))
        r = run("syn-compliant.jpg", analyzer=a, submission_id="retry-1")
        self.assertEqual((a.calls, r["decision"], r["usage"]["attempts"]), (2, "PASS", 2))

    def test_missing_rule_rejected(self):
        bad = recording("golden-001-compliant")
        bad["rule_results"] = bad["rule_results"][:3]
        r = run("syn-compliant.jpg", analyzer=StaticAnalyzer(bad), submission_id="missing")
        self.assertEqual(r["failure"]["kind"], "SCHEMA_INVALID")

    def test_wrong_version_echo_rejected(self):
        bad = recording("golden-001-compliant")
        bad["rule_pack"]["version"] = "0.9.0"
        r = run("syn-compliant.jpg", analyzer=StaticAnalyzer(bad), submission_id="echo")
        self.assertEqual(r["failure"]["kind"], "SCHEMA_INVALID")

    def test_pass_without_evidence_rejected(self):
        bad = recording("golden-001-compliant")
        bad["rule_results"][0]["evidence"] = []
        r = run("syn-compliant.jpg", analyzer=StaticAnalyzer(bad), submission_id="noev")
        self.assertEqual(r["failure"]["kind"], "SCHEMA_INVALID")

    def test_invalid_image_rejected(self):
        tmp = Path(tempfile.mkdtemp()) / "x.jpg"
        tmp.write_bytes(b"not an image")
        from siv.pipeline import inspect
        r = inspect([str(tmp)], rule_pack_id="contoso-storefront", rule_pack_version="1.0.0",
                    analyzer=StaticAnalyzer(recording("golden-001-compliant")), submission_id="bad-img",
                    store=ResultStore(Path(tempfile.mkdtemp())))
        self.assertEqual(r["failure"]["kind"], "INVALID_IMAGE")

    def test_trace_correlation_and_no_image_data(self):
        r = run("syn-compliant.jpg", submission_id="trace-1")
        spans = [json.loads(line) for line in Path(os.environ["SIV_TRACE_FILE"]).read_text().splitlines()]
        mine = [s for s in spans if s["trace_id"] == r["trace_id"]]
        names = {s["span"] for s in mine}
        self.assertTrue({"inspection", "invoke_agent", "rule_result", "retrieve_policy_guidance"} <= names)
        root = next(s for s in mine if s["span"] == "inspection")["attributes"]
        for key in ("tenant.id", "submission.id", "rule_pack.version", "agent.version", "image.hashes",
                    "decision", "score", "human_review.required", "latency.total_ms"):
            self.assertIn(key, root)
        blob = json.dumps(mine)
        self.assertNotIn("base64", blob)
        self.assertNotIn("data:image", blob)


if __name__ == "__main__":
    unittest.main()
