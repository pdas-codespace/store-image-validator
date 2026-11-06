import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from insights.run_insights import get_or_create_monitor
from scripts import ncus_demo
from scripts.ncus_demo import AGENTS, PROJECT, PROJECT_ID, agent_version, execute, stage_source


class NcusDemo(unittest.TestCase):
    def test_child_context_is_ncus_and_has_no_sas(self):
        with patch.dict(os.environ, {"FOUNDRY_PROJECT_ENDPOINT": "https://eastus.example/project",
                                     "SIV_EVAL_IMAGE_SAS": "?secret"}), \
                patch("scripts.ncus_demo.shutil.which", return_value="python.exe"), \
                patch("scripts.ncus_demo.subprocess.run", return_value=SimpleNamespace(stdout="done")) as run:
            self.assertEqual(execute("python", "example.py", capture=True), "done")
        self.assertEqual(run.call_args.kwargs["env"]["FOUNDRY_PROJECT_ENDPOINT"], PROJECT)
        self.assertNotIn("SIV_EVAL_IMAGE_SAS", run.call_args.kwargs["env"])
        self.assertTrue(run.call_args.kwargs["check"])

    def test_agent_version_cannot_come_from_eastus_environment(self):
        key = "AGENT_" + AGENTS["kimi"].upper().replace("-", "_") + "_VERSION"
        values = {"FOUNDRY_PROJECT_ENDPOINT": PROJECT, "AZURE_AI_PROJECT_ID": PROJECT_ID, key: "9"}
        with patch("scripts.ncus_demo.azd", return_value=json.dumps(values)):
            self.assertEqual(agent_version("ncus-demo", "kimi"), "9")
        values["AZURE_AI_PROJECT_ID"] = "/another-project"
        with patch("scripts.ncus_demo.azd", return_value=json.dumps(values)):
            with self.assertRaisesRegex(ValueError, "NCUS project"):
                agent_version("ncus-demo", "kimi")

    def test_stages_runtime_without_secrets_and_refreshes_deleted_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deployment = root / "deployments" / "ncus"
            for name in ("agent/main.py", "siv/images.py", "rules/storefront.yaml", "policy/guidance.md",
                         ".agent_configs/baseline/metadata.yaml", "requirements.txt", "pyproject.toml", ".agentignore",
                         ".env", ".azure/demo/.env", "tests/results.jsonl", "agent/__pycache__/cached.pyc"):
                path = root.joinpath(*name.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name)
            with patch("scripts.ncus_demo.ROOT", root), patch("scripts.ncus_demo.DEPLOY", deployment):
                source = stage_source()
                self.assertEqual((source / "agent" / "main.py").read_text(), "agent/main.py")
                self.assertTrue((source / ".agent_configs" / "baseline" / "metadata.yaml").is_file())
                for excluded in (".env", ".azure", "tests", "deployments"):
                    self.assertFalse((source / excluded).exists())
                self.assertFalse((source / "agent" / "__pycache__").exists())
                candidate = source / ".agent_configs" / "selected-candidate" / "instructions.md"
                candidate.parent.mkdir()
                candidate.write_text("review before promoting")
                (root / "siv" / "images.py").unlink()
                (root / "agent" / "main.py").write_text("updated")
                stage_source()
                self.assertFalse((source / "siv" / "images.py").exists())
                self.assertEqual((source / "agent" / "main.py").read_text(), "updated")
                self.assertEqual(candidate.read_text(), "review before promoting")
                self.assertTrue((root / ".env").exists())

    def test_staging_refuses_to_overwrite_an_unowned_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            deployment = Path(directory)
            (deployment / "source").mkdir()
            with patch("scripts.ncus_demo.DEPLOY", deployment):
                with self.assertRaisesRegex(ValueError, "unowned source directory"):
                    stage_source()

    def test_optimizer_preserves_explicit_candidate_limit(self):
        import yaml

        template = (ncus_demo.DEPLOY / "eval-kimi.yaml").read_text()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            deployment = root / "deployments" / "ncus"
            deployment.mkdir(parents=True)
            (deployment / "eval-kimi.yaml").write_text(template)
            output = root / "evaluation" / "results" / "ncus"
            output.mkdir(parents=True)
            with patch.dict(os.environ), \
                    patch.object(sys, "argv", ["ncus_demo.py", "optimize", "--agent", "kimi",
                                              "--confirm-optimizer-ready", "--max-candidates", "2"]), \
                    patch.object(ncus_demo, "ROOT", root), patch.object(ncus_demo, "DEPLOY", deployment), \
                    patch.object(ncus_demo, "agent_version", return_value="7"), \
                    patch.object(ncus_demo, "execute"), patch.object(ncus_demo, "azd") as optimize:
                ncus_demo.main()
            arguments = optimize.call_args.args
            self.assertEqual(arguments[arguments.index("--max-candidates") + 1], "2")
            self.assertEqual(arguments[arguments.index("--optimize-model") + 1], "gpt-5.5")
            config = yaml.safe_load((output / "optimizer-kimi-v7.yaml").read_text())
            self.assertEqual(config["options"]["max_candidates"], 2)
            self.assertEqual(config["agent"]["version"], "7")

    def test_insights_discovers_existing_monitor_without_local_cache(self):
        ops = Mock()
        monitor = SimpleNamespace(id="ncus-monitor")
        ops.list.return_value = [monitor]
        self.assertIs(get_or_create_monitor(ops, AGENTS["kimi"], "gpt-6-sol"), monitor)
        ops.list.assert_called_once_with(agent_name=AGENTS["kimi"])
        ops.create.assert_not_called()

    def test_insights_creates_only_when_no_remote_monitor_exists(self):
        ops = Mock()
        ops.list.return_value = []
        get_or_create_monitor(ops, AGENTS["gpt"], "gpt-6-sol")
        ops.create.assert_called_once()
        ops.list.return_value = [Mock(), Mock()]
        with self.assertRaisesRegex(RuntimeError, "Multiple Insights monitors"):
            get_or_create_monitor(ops, AGENTS["gpt"], "gpt-6-sol")
