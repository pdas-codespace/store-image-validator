import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from agent_framework import AgentContext, Content, Message

from agent.blob_images import download_blob_image, resolve_blob_images
from evaluation.run_foundry_eval import agent_items, cmd_agent_target
from evaluation.review_foundry_results import review
from siv.evaluation import ground_truth, load_dataset
from tests.helpers import recording


class HostedBlobImages(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_blob_before_calling_model(self):
        request = {"images": [{"image_id": "img-001", "blob_name": "syn-compliant.jpg"}]}
        message = Message("user", [json.dumps(request)])
        context = AgentContext(agent=Mock(), messages=[message])
        next_call = AsyncMock()
        with patch("agent.blob_images.download_blob_image", AsyncMock(return_value="data:image/jpeg;base64,YQ==")) as read:
            await resolve_blob_images(context, next_call)
            await resolve_blob_images(context, next_call)
        read.assert_awaited_once_with("syn-compliant.jpg")
        self.assertEqual(len(message.contents), 1)
        self.assertEqual(len(context.messages[0].contents), 2)
        self.assertNotIn("blob_name", json.loads(context.messages[0].text)["images"][0])
        self.assertEqual(context.messages[0].contents[1].type, "data")
        self.assertEqual(next_call.await_count, 2)

    async def test_existing_inline_request_is_unchanged(self):
        message = Message("user", ["Inspect this image", Content.from_uri("data:image/jpeg;base64,YQ==")])
        with patch("agent.blob_images.download_blob_image", AsyncMock()) as read:
            await resolve_blob_images(SimpleNamespace(messages=[message]), AsyncMock())
        read.assert_not_awaited()
        self.assertEqual(len(message.contents), 2)

    async def test_denied_blob_read_prevents_inference(self):
        message = Message("user", [json.dumps({"images": [{"blob_name": "syn-compliant.jpg"}]})])
        next_call = AsyncMock()
        with patch("agent.blob_images.download_blob_image", AsyncMock(side_effect=PermissionError("Blob denied"))):
            with self.assertRaises(PermissionError):
                await resolve_blob_images(SimpleNamespace(messages=[message]), next_call)
        next_call.assert_not_awaited()

    async def test_managed_identity_read_is_bounded_and_not_cli_authenticated(self):
        with patch.dict(os.environ, {"MICROSOFT_EVAL_IMAGE_CONTAINER_URL": "https://example.test/eval-images"}, clear=True), \
                patch("azure.identity.aio.ManagedIdentityCredential") as identity, \
                patch("azure.storage.blob.aio.BlobClient.from_blob_url") as create_blob, \
                patch("agent.blob_images.image_bytes_to_data_url", return_value="encoded") as encode:
            blob = create_blob.return_value.__aenter__.return_value
            stream = SimpleNamespace(readall=AsyncMock(return_value=b"image bytes"))
            blob.download_blob = AsyncMock(return_value=stream)
            self.assertEqual(await download_blob_image("syn-compliant.jpg"), "encoded")
            create_blob.assert_called_once_with("https://example.test/eval-images/syn-compliant.jpg",
                                                credential=identity.return_value)
            from siv.images import MAX_BYTES
            blob.download_blob.assert_awaited_once_with(offset=0, length=MAX_BYTES + 1)
            encode.assert_called_once_with(b"image bytes")

    async def test_blob_paths_cannot_choose_arbitrary_host_or_escape_container(self):
        with patch.dict(os.environ, {"MICROSOFT_EVAL_IMAGE_CONTAINER_URL": "https://example.test/eval-images"}), \
                patch("azure.identity.aio.ManagedIdentityCredential") as identity:
            for name in ("../secret.jpg", "https://other.test/x.jpg", "folder\\image.jpg", "a%2fb.jpg"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    await download_blob_image(name)
            identity.assert_not_called()

    async def test_federated_host_uses_workload_identity(self):
        with patch.dict(os.environ, {"MICROSOFT_EVAL_IMAGE_CONTAINER_URL": "https://example.test/eval-images",
                                     "AZURE_FEDERATED_TOKEN_FILE": "injected-token-file"}, clear=True), \
                patch("azure.identity.aio.WorkloadIdentityCredential") as workload, \
                patch("azure.identity.aio.ManagedIdentityCredential") as managed, \
                patch("azure.storage.blob.aio.BlobClient.from_blob_url") as create_blob, \
                patch("agent.blob_images.image_bytes_to_data_url", return_value="encoded"):
            blob = create_blob.return_value.__aenter__.return_value
            blob.download_blob = AsyncMock(return_value=SimpleNamespace(readall=AsyncMock(return_value=b"image")))
            await download_blob_image("syn-compliant.jpg")
        workload.assert_called_once_with()
        managed.assert_not_called()
        self.assertIs(create_blob.call_args.kwargs["credential"], workload.return_value)


class HostedEvaluation(unittest.TestCase):
    def test_hosted_request_needs_no_local_storage_auth_or_image_url(self):
        with patch.dict(os.environ, {"SIV_EVAL_IMAGE_SAS": ""}, clear=True), \
                patch("evaluation.run_foundry_eval.blob_image_data_url") as read:
            rows = agent_items("golden", "hosted")
        self.assertEqual(len(rows), 4)
        self.assertNotIn("image_url", rows[0])
        self.assertEqual(json.loads(rows[0]["query"])["images"][0]["blob_name"], "syn-compliant.jpg")
        read.assert_not_called()

    def test_hosted_template_does_not_trigger_remote_url_download(self):
        with patch.dict(os.environ, {"SIV_EVAL_IMAGE_SAS": ""}, clear=True), \
                patch("evaluation.run_foundry_eval.clients") as clients, \
                patch("evaluation.run_foundry_eval.register_evaluators", return_value={}), \
                patch("evaluation.run_foundry_eval.wait", return_value=SimpleNamespace(status="completed")), \
                patch("evaluation.run_foundry_eval.summarize"):
            client = Mock()
            clients.return_value = (Mock(), client)
            cmd_agent_target(SimpleNamespace(partitions="golden", image_auth="hosted", name="MI test",
                                            agent_name="test-agent", agent_version="1", output_dir=None))
        source = client.evals.runs.create.call_args.kwargs["data_source"]
        self.assertEqual(source["input_messages"]["template"][0]["content"],
                         [{"type": "input_text", "text": "{{item.query}}"}])
        self.assertEqual(source["target"]["version"], "1")

    def test_independent_review_detects_cloud_local_disagreement(self):
        label = load_dataset(["golden"])[0]
        result = {
            "run_id": "run-test", "datasource_item": {
                "id": label["id"], "ground_truth": json.dumps(ground_truth(label)),
                "sample.output_text": json.dumps(recording(label["id"])),
            },
            "results": [{"name": name, "score": 0.0} for name in
                        ("schema_validity", "rule_status_accuracy", "evidence_consistency",
                         "policy_adherence", "injection_resistance")],
            "sample": {},
        }
        checked = review([result])
        self.assertEqual(checked["successful_responses"], 1)
        self.assertEqual(checked["cloud_local_mismatches"], 5)
        result["sample"]["error"] = {"message": "agent failed"}
        self.assertEqual(review([result])["runtime_failures"], 1)

    def test_failed_run_keeps_exported_context_before_exiting(self):
        client = Mock()
        client.evals.create.return_value = SimpleNamespace(id="eval-test")
        client.evals.runs.create.return_value = SimpleNamespace(id="run-test")
        output = Mock()
        output.model_dump.return_value = {"id": "output-test"}
        client.evals.runs.output_items.list.return_value = [output]
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {"SIV_EVAL_IMAGE_SAS": "", "FOUNDRY_PROJECT_ENDPOINT": "https://ncus.test"}), \
                patch("evaluation.run_foundry_eval.clients", return_value=(Mock(), client)), \
                patch("evaluation.run_foundry_eval.register_evaluators", return_value={}), \
                patch("evaluation.run_foundry_eval.wait",
                      return_value=SimpleNamespace(status="failed", report_url="https://report.test")), \
                patch("evaluation.run_foundry_eval.summarize"):
            with self.assertRaisesRegex(SystemExit, "failed"):
                cmd_agent_target(SimpleNamespace(partitions="golden", image_auth="hosted", name="MI test",
                                                agent_name="test-agent", agent_version="1", output_dir=directory))
            context = json.loads((Path(directory) / "run.json").read_text())
            self.assertEqual((context["run_id"], context["status"]), ("run-test", "failed"))
            self.assertEqual(json.loads((Path(directory) / "results.jsonl").read_text()), {"id": "output-test"})
