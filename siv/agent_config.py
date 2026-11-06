"""Loads the optimizer-managed agent configuration.

Uses `azure.ai.agentserver.optimization.load_config` when installed, so candidate configs
injected by Foundry Agent Optimizer (OPTIMIZATION_CONFIG, resolver API, or
.agent_configs/<candidate>/) are honoured. Falls back to reading the baseline files
directly so local runs and CI work without the package.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import REPO_ROOT

CONFIG_DIR = REPO_ROOT / ".agent_configs"  # azd agent project root = repo root


@dataclass(frozen=True)
class AgentConfig:
    instructions: str
    model: str
    temperature: float | None
    tool_definitions: list
    source: str

    @property
    def version_hash(self) -> str:
        blob = json.dumps([self.instructions, self.model, self.temperature, self.tool_definitions], sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()[:12]


def _read_skills(skill_dir: Path) -> list[tuple[str, str, str]]:
    skills = []
    for md in sorted(skill_dir.glob("*/SKILL.md")) if skill_dir.exists() else []:
        raw = md.read_text()
        meta, body = {}, raw
        if raw.startswith("---"):
            _, fm, body = raw.split("---", 2)
            meta = yaml.safe_load(fm) or {}
        skills.append((meta.get("name", md.parent.name), meta.get("description", ""), body.strip()))
    return skills


def _fallback(config_dir: Path) -> AgentConfig:
    variant = os.environ.get("SIV_AGENT_CONFIG", "baseline")
    base = config_dir / variant
    meta = yaml.safe_load((base / "metadata.yaml").read_text())
    instructions = (base / meta["instruction_file"]).read_text().strip()
    skills = _read_skills(base / meta.get("skill_dir", "skills"))
    if skills:
        # Single-shot calls cannot activate skills progressively, so inline them.
        instructions += "\n\n# Skills\n" + "\n\n".join(f"## {n}\n{d}\n\n{b}" for n, d, b in skills)
    tools = json.loads((base / meta["tools_file"]).read_text()) if meta.get("tools_file") else []
    return AgentConfig(instructions, _model_override() or meta["model"],
                       meta.get("temperature"), tools, f"local:{variant}")


def _model_override() -> str | None:
    """Deployment-name override for the baseline only (optimizer candidates keep their model).
    FOUNDRY_* is reserved inside hosted containers, hence the MICROSOFT_ prefix."""
    return os.environ.get("MICROSOFT_FOUNDRY_MODEL_DEPLOYMENT_NAME") or os.environ.get("SIV_MODEL_DEPLOYMENT")


def _is_baseline_source(source: object) -> bool:
    source_text = str(source).replace("\\", "/").rstrip("/")
    return source_text == "baseline" or source_text.endswith("/baseline") or source_text.endswith(":baseline")


def load_agent_config(config_dir: Path = CONFIG_DIR) -> AgentConfig:
    try:
        from azure.ai.agentserver.optimization import load_config, load_skills_from_dir  # type: ignore
    except ImportError:
        return _fallback(config_dir)
    cfg = load_config(config_dir=str(config_dir))
    if cfg is None:
        return _fallback(config_dir)
    if not cfg.skills and cfg.skills_dir:
        cfg.skills.extend(load_skills_from_dir(Path(cfg.skills_dir)))
    model = (_model_override() if _is_baseline_source(cfg.source) else None) or cfg.model
    return AgentConfig(cfg.compose_instructions(), model,
                       cfg.temperature, list(cfg.tool_definitions or []), f"optimizer:{cfg.source}")
