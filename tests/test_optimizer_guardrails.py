import json
import os
import shutil
import unittest

from siv.agent_config import CONFIG_DIR, _is_baseline_source, load_agent_config


class OptimizerGuardrails(unittest.TestCase):
    def setUp(self):
        import importlib.util
        from siv import REPO_ROOT
        spec = importlib.util.spec_from_file_location("cc", REPO_ROOT / "optimizer" / "compare_candidate.py")
        self.cc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cc)
        self.cand = CONFIG_DIR / "test-candidate"
        shutil.copytree(CONFIG_DIR / "baseline", self.cand)

    def tearDown(self):
        shutil.rmtree(self.cand, ignore_errors=True)

    def test_baseline_loads(self):
        cfg = load_agent_config()
        self.assertIn("CANNOT_DETERMINE", cfg.instructions)
        self.assertIn("storefront-inspection", cfg.instructions)
        self.assertEqual(len(cfg.tool_definitions), 2)

    def test_local_baseline_source_honors_model_override(self):
        self.assertTrue(_is_baseline_source(r"local:C:\repo\.agent_configs\baseline"))
        old = os.environ.get("MICROSOFT_FOUNDRY_MODEL_DEPLOYMENT_NAME")
        os.environ["MICROSOFT_FOUNDRY_MODEL_DEPLOYMENT_NAME"] = "test-deployment"
        try:
            self.assertEqual(load_agent_config().model, "test-deployment")
        finally:
            if old is None:
                os.environ.pop("MICROSOFT_FOUNDRY_MODEL_DEPLOYMENT_NAME", None)
            else:
                os.environ["MICROSOFT_FOUNDRY_MODEL_DEPLOYMENT_NAME"] = old

    def test_description_only_change_allowed(self):
        tools = json.loads((self.cand / "tools.json").read_text())
        tools[0]["function"]["description"] += " Improved."
        (self.cand / "tools.json").write_text(json.dumps(tools))
        self.assertEqual(self.cc.check_candidate_scope("test-candidate"), [])

    def test_tool_signature_change_rejected(self):
        tools = json.loads((self.cand / "tools.json").read_text())
        tools[0]["function"]["parameters"]["properties"]["weight_override"] = {"type": "number"}
        (self.cand / "tools.json").write_text(json.dumps(tools))
        self.assertTrue(self.cc.check_candidate_scope("test-candidate"))

    def test_business_config_in_candidate_rejected(self):
        (self.cand / "contoso-storefront-1.0.0.yaml").write_text("passThreshold: 1")
        self.assertTrue(self.cc.check_candidate_scope("test-candidate"))
