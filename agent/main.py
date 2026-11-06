"""Foundry Hosted Agent: store-image-inspector (Responses protocol).

The container is the *visual reasoning worker* only: it returns the model-owned inspection
JSON (observations + per-rule results). Scoring/decisions stay in siv.scoring, run by the
caller (local pipeline today, orchestration worker later).

Optimizer-ready: instructions, skills, tool descriptions and model come from
.agent_configs/ via azure.ai.agentserver.optimization.load_config().
Tools are read-only, so optimizer/evaluation runs have no side effects.

VERIFY (version-dependent, see docs/architecture.md):
  - agent_framework / agent_framework_foundry_hosting import paths and constructor args
  - that input_image parts in the Responses request reach the model unchanged
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Annotated

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


from agent_framework import Agent, tool  # noqa: E402
from agent_framework.foundry import FoundryChatClient  # noqa: E402
from agent_framework_foundry_hosting import ResponsesHostServer  # noqa: E402
from azure.identity import DefaultAzureCredential  # noqa: E402
from pydantic import Field  # noqa: E402

from siv.agent_config import CONFIG_DIR, load_agent_config  # noqa: E402
from siv.analyzers import agent_response_format  # noqa: E402
from siv.policy import PolicyRetrievalError  # noqa: E402
from siv.policy import retrieve_policy_guidance as _retrieve  # noqa: E402
from siv.rulepack import RulePackError, load_rule_pack  # noqa: E402
from agent.blob_images import resolve_blob_images  # noqa: E402

logger = logging.getLogger("store-image-inspector")


@tool(approval_mode="never_require")
def get_rule_pack(
    rule_pack_id: Annotated[str, Field(description="Rule pack identifier from the request")],
    version: Annotated[str, Field(description="Exact semantic version from the request")],
) -> str:
    """Return the atomic rules for the exact pinned rule-pack version."""
    try:
        pack = load_rule_pack(rule_pack_id, version)
    except RulePackError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"rule_pack": {"id": pack.id, "version": pack.version}, "category": pack.category,
                       "rules": [r.agent_view() for r in pack.rules]})


@tool(approval_mode="never_require")
def retrieve_policy_guidance(
    category: Annotated[str, Field(description="Inspection category from the request")],
    rule_pack_id: Annotated[str, Field(description="Rule pack identifier")],
    version: Annotated[str, Field(description="Exact rule-pack version")],
) -> str:
    """Return interpretation guidance for the category and rule-pack version."""
    try:
        g = _retrieve(category, rule_pack_id, version)
    except PolicyRetrievalError as exc:
        return json.dumps({"error": str(exc)})
    return json.dumps({"source": g.source, "guidance": g.text})


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    _load_dotenv()
    config = load_agent_config(CONFIG_DIR)
    tools = [get_rule_pack, retrieve_policy_guidance]
    try:  # apply optimizer-tuned tool descriptions when the package is present
        from azure.ai.agentserver.optimization import load_config
        opt = load_config(config_dir=str(CONFIG_DIR))
        if opt is not None:
            opt.apply_tool_descriptions(tools)
    except ImportError:
        pass
    logger.info("Config source=%s | model=%s | prompt_len=%d", config.source, config.model, len(config.instructions))

    client = FoundryChatClient(project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], model=config.model,
                               credential=DefaultAzureCredential())
    options: dict = {"store": False, "response_format": agent_response_format()}
    if config.temperature is not None:
        options["temperature"] = config.temperature
    agent = Agent(client=client, name=os.environ.get("SIV_AGENT_NAME", "store-image-inspector"),
                  instructions=config.instructions, tools=tools, default_options=options,
                  middleware=[resolve_blob_images])
    ResponsesHostServer(agent).run()


if __name__ == "__main__":
    main()
