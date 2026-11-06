"""Analyzer back-ends. All return the raw model JSON text; validation happens in the pipeline."""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .. import REPO_ROOT
from ..agent_config import AgentConfig
from ..images import SubmittedImage
from ..policy import PolicyGuidance
from ..rulepack import RulePack

AGENT_SCHEMA = json.loads((REPO_ROOT / "siv" / "schemas" / "agent-result.schema.json").read_text())


def agent_response_format() -> dict:
    return {"type": "json_schema", "name": "inspection_result", "schema": AGENT_SCHEMA, "strict": True}


@dataclass
class AnalysisRequest:
    submission_id: str
    category: str
    pack: RulePack
    images: list[SubmittedImage]
    guidance: PolicyGuidance | None
    config: AgentConfig
    retry_feedback: str | None = None

    def request_text(self) -> str:
        """Text part of the user message. Business weights/thresholds are deliberately excluded."""
        payload = {
            "task": "Inspect the attached images against every rule below and return the inspection JSON.",
            "submission_id": self.submission_id,
            "category": self.category,
            "rule_pack": {"id": self.pack.id, "version": self.pack.version},
            "rules": [r.agent_view() for r in self.pack.rules],
            "policy_guidance": self.guidance.text if self.guidance else
                "UNAVAILABLE: policy retrieval failed. Use the rule text only and note this in uncertainties.",
            "images": [{"image_id": i.image_id, "order": n + 1, "precheck": i.quality_hints()}
                       for n, i in enumerate(self.images)],
            "note": "Image ids are assigned in the order the images are attached.",
        }
        text = json.dumps(payload, indent=2)
        if self.retry_feedback:
            text += f"\n\nYour previous answer was rejected: {self.retry_feedback}\nReturn corrected JSON only."
        return text


@dataclass
class AnalyzerResult:
    raw_text: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    response_id: str | None = None
    extra: dict = field(default_factory=dict)


class Analyzer:
    name = "base"

    def analyze(self, req: AnalysisRequest) -> AnalyzerResult:  # pragma: no cover - interface
        raise NotImplementedError


class AnalyzerError(Exception):
    """Raised when a remote analyzer returns a terminal service error."""


def get_analyzer(provider: str, **kwargs) -> Analyzer:
    if provider == "replay":
        from .replay import ReplayAnalyzer
        return ReplayAnalyzer(**kwargs)
    if provider == "foundry-model":
        from .foundry import FoundryModelAnalyzer
        return FoundryModelAnalyzer(**kwargs)
    if provider == "hosted-agent":
        from .foundry import HostedAgentAnalyzer
        return HostedAgentAnalyzer(**kwargs)
    raise ValueError(f"Unknown provider {provider!r} (replay | foundry-model | hosted-agent)")
