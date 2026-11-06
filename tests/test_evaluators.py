"""Evaluators must catch bad outputs, not just score the happy path."""
import base64
import json
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from evaluation.run_foundry_eval import AGENT_LEVEL, blob_image_data_url, cmd_agent_target, criteria, register_evaluators
from siv.evaluation import aggregate, check_gates, load_dataset, load_evaluators, ground_truth, to_response
from tests.helpers import StaticAnalyzer, recording, run

EV = load_evaluators()

MODELS = ModuleType("azure.ai.projects.models")
MODELS.EvaluatorCategory = SimpleNamespace(QUALITY="quality")
MODELS.EvaluatorDefinitionType = SimpleNamespace(CODE="code")
MODELS.TestingCriterionAzureAIEvaluator = dict


def item(record, row_id):
    row = next(r for r in load_dataset(["golden", "challenge", "abstention", "adversarial"]) if r["id"] == row_id)
    return {"response": json.dumps(to_response(record)), "ground_truth": json.dumps(ground_truth(row))}


class BlobEvaluationImages(unittest.TestCase):
    def test_entra_download_authenticates_and_encodes_image(self):
        image = Path(__file__).resolve().parent.parent / "fixtures" / "images" / "syn-compliant.jpg"
        with patch("azure.identity.AzureCliCredential") as credential, \
                patch("azure.storage.blob.BlobClient.from_blob_url") as create_blob:
            blob = create_blob.return_value.__enter__.return_value
            blob.download_blob.return_value.readall.return_value = image.read_bytes()
            result = blob_image_data_url("https://example.blob.core.windows.net/eval-images", "syn-compliant.jpg")
            create_blob.assert_called_once_with(
                "https://example.blob.core.windows.net/eval-images/syn-compliant.jpg",
                credential=credential.return_value.__enter__.return_value)
            self.assertTrue(result.startswith("data:image/jpeg;base64,"))
            self.assertTrue(base64.b64decode(result.split(",", 1)[1]).startswith(b"\xff\xd8"))
            from siv.images import MAX_BYTES
            blob.download_blob.assert_called_once_with(offset=0, length=MAX_BYTES + 1)

    def test_entra_rejects_signed_or_non_https_base_without_download(self):
        with patch("azure.storage.blob.BlobClient.from_blob_url") as create_blob:
            for base in ("http://example.test/images", "https://example.test/images?sig=secret"):
                with self.subTest(base=base), self.assertRaises(ValueError):
                    blob_image_data_url(base, "syn-compliant.jpg")
            create_blob.assert_not_called()

    def test_entra_download_failure_propagates(self):
        with patch("azure.identity.AzureCliCredential"), \
                patch("azure.storage.blob.BlobClient.from_blob_url") as create_blob:
            blob = create_blob.return_value.__enter__.return_value
            blob.download_blob.side_effect = PermissionError("Blob read denied")
            with self.assertRaisesRegex(PermissionError, "Blob read denied"):
                blob_image_data_url("https://example.test/images", "syn-compliant.jpg")

    def test_entra_rejects_non_image_blob(self):
        from siv.images import ImageValidationError

        with patch("azure.identity.AzureCliCredential"), \
                patch("azure.storage.blob.BlobClient.from_blob_url") as create_blob:
            blob = create_blob.return_value.__enter__.return_value
            blob.download_blob.return_value.readall.return_value = b"not an image"
            with self.assertRaises(ImageValidationError):
                blob_image_data_url("https://example.test/images", "syn-compliant.jpg")

    def test_agent_target_submits_inline_image_only_in_entra_mode(self):
        row = load_dataset(["golden"])[0]
        base = "https://example.blob.core.windows.net/eval-images"
        for mode, sas in (("entra", ""), ("url", "?example-sas")):
            with self.subTest(mode=mode), \
                    patch.dict("os.environ", {"SIV_EVAL_IMAGE_BASE_URL": base, "SIV_EVAL_IMAGE_SAS": sas}), \
                    patch("siv.evaluation.load_dataset", return_value=[row]), \
                    patch("evaluation.run_foundry_eval.blob_image_data_url", return_value="data:image/jpeg;base64,example") as encode, \
                    patch("evaluation.run_foundry_eval.clients") as clients, \
                    patch("evaluation.run_foundry_eval.register_evaluators", return_value={}), \
                    patch("evaluation.run_foundry_eval.wait", return_value=SimpleNamespace(status="completed")), \
                    patch("evaluation.run_foundry_eval.summarize"):
                client = Mock()
                clients.return_value = (Mock(), client)
                args = SimpleNamespace(image_auth=mode, partitions="golden",
                                       agent_name="store-image-inspector", agent_version="8", name="test", output_dir=None)
                cmd_agent_target(args)
                source = client.evals.runs.create.call_args.kwargs["data_source"]
                actual = source["source"]["content"][0]["item"]["image_url"]
                if mode == "entra":
                    encode.assert_called_once_with(base, "syn-compliant.jpg")
                    self.assertEqual(actual, "data:image/jpeg;base64,example")
                else:
                    encode.assert_not_called()
                    self.assertEqual(actual, base + "/syn-compliant.jpg" + sas)
                self.assertEqual(source["input_messages"]["template"][0]["content"][1]["image_url"],
                                 "{{item.image_url}}")

    def test_entra_rejects_sas_before_creating_cloud_objects(self):
        with patch.dict("os.environ", {"SIV_EVAL_IMAGE_BASE_URL": "https://example.test/images",
                                      "SIV_EVAL_IMAGE_SAS": "?example-sas"}), \
                patch("evaluation.run_foundry_eval.clients") as clients:
            with self.assertRaisesRegex(SystemExit, "Remove SIV_EVAL_IMAGE_SAS"):
                cmd_agent_target(SimpleNamespace(image_auth="entra", partitions="golden"))
            clients.assert_not_called()


class Evaluators(unittest.TestCase):
    def test_cloud_mappings_match_registered_input_schema(self):
        project = Mock()
        project.evaluators.create_version.side_effect = lambda **kw: SimpleNamespace(name=kw["name"], version="1")
        with patch.dict(sys.modules, {"azure.ai.projects.models": MODELS}):
            registered = register_evaluators(project, AGENT_LEVEL)
            for target_mode in (False, True):
                with self.subTest(target_mode=target_mode):
                    configured = criteria(registered, target_mode)
                    for call, criterion in zip(project.evaluators.create_version.call_args_list, configured):
                        schema = call.kwargs["evaluator_version"]["definition"]["data_schema"]
                        mapping = criterion["data_mapping"]
                        self.assertEqual(set(schema["required"]), set(mapping))
                        self.assertEqual(set(schema["properties"]), set(mapping))
                        self.assertEqual(mapping["response"],
                                         "{{sample.output_text}}" if target_mode else "{{item.response}}")
                        self.assertEqual(mapping["ground_truth"], "{{item.ground_truth}}")
                        self.assertEqual(criterion["evaluator_version"], "1")

    def test_agent_level_evaluators_score_mapped_cloud_response(self):
        row = next(r for r in load_dataset(["challenge"]))
        mapped = {"response": json.dumps(recording("challenge-001-glare")),
                  "ground_truth": json.dumps(ground_truth(row))}
        for name in AGENT_LEVEL:
            with self.subTest(evaluator=name):
                self.assertEqual(EV[name]({}, mapped), 1.0)

    def test_good_output_scores_one(self):
        it = item(run("syn-compliant.jpg"), "golden-001-compliant")
        self.assertTrue(all(EV[n]({}, it) == 1.0 for n in EV), {n: EV[n]({}, it) for n in EV})

    def test_false_pass_detected(self):
        lying = recording("golden-001-compliant")  # claims everything passes on the noncompliant image
        rec = run("syn-noncompliant.jpg", analyzer=StaticAnalyzer(lying), submission_id="lie")
        it = item(rec, "golden-002-noncompliant")
        self.assertEqual(EV["no_false_pass"]({}, it), 0.0)
        self.assertEqual(EV["decision_accuracy"]({}, it), 0.0)
        self.assertEqual(EV["rule_status_accuracy"]({}, it), 0.5)

    def test_false_abstention_detected(self):
        lazy = recording("abstain-001-cropped")  # abstains on a clear compliant image
        rec = run("syn-compliant.jpg", analyzer=StaticAnalyzer(lazy), submission_id="lazy")
        it = item(rec, "golden-001-compliant")
        self.assertEqual(EV["abstention_correct"]({}, it), 0.0)
        self.assertEqual(EV["no_false_fail"]({}, it), 1.0)

    def test_dangling_evidence_detected(self):
        bad = recording("golden-001-compliant")
        bad["rule_results"][0]["evidence"][0]["observation_id"] = "obs-999"
        rec = run("syn-compliant.jpg", analyzer=StaticAnalyzer(bad), submission_id="dangling")
        self.assertEqual(EV["evidence_consistency"]({}, item(rec, "golden-001-compliant")), 0.75)

    def test_score_tamper_detected(self):
        rec = run("syn-compliant.jpg", submission_id="tamper")
        rec["score"] = 7
        self.assertEqual(EV["score_consistency"]({}, item(rec, "golden-001-compliant")), 0.0)

    def test_missing_injection_flag_detected(self):
        quiet = recording("adv-001-image-injection")
        quiet["image_assessment"]["issues"] = []
        rec = run("syn-injection.jpg", analyzer=StaticAnalyzer(quiet), submission_id="quiet")
        self.assertLess(EV["injection_resistance"]({}, item(rec, "adv-001-image-injection")), 1.0)

    def test_agent_level_evaluators_accept_raw_agent_output(self):
        row = next(r for r in load_dataset(["challenge"]))
        raw = {"ground_truth": json.dumps(ground_truth(row))}
        sample = {"output_text": json.dumps(recording("challenge-001-glare"))}
        # confidence gate applied inline -> SF-003 0.55 PASS counts as CANNOT_DETERMINE
        self.assertEqual(EV["rule_status_accuracy"](sample, raw), 1.0)
        self.assertEqual(EV["policy_adherence"](sample, raw), 1.0)
        self.assertEqual(EV["schema_validity"](sample, raw), 1.0)

    def test_gates_fail_on_regression(self):
        rows = [{"partition": "golden", "decision": "PASS", "expected_decision": "FAIL", "event": "InspectionCompleted",
                 "score_range": 0, "tokens": {}, "scores": {n: 1.0 for n in EV} | {"no_false_pass": 0.0}}]
        failed = {g["gate"] for g in check_gates(aggregate(rows)) if not g["passed"]}
        self.assertIn("false_pass_rate", failed)
        self.assertIn("mandatory_false_pass_count", failed)
