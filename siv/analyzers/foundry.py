"""Microsoft Foundry back-ends (azure-ai-projects >= 2.x, OpenAI Responses API).

FoundryModelAnalyzer  - calls a model deployment in the Foundry project directly with the
                        optimizer-managed instructions and a strict JSON schema. Fastest way
                        to analyze an image today; traces land in Foundry when App Insights
                        is connected.
HostedAgentAnalyzer   - calls the deployed hosted agent's OpenAI protocol endpoint by name,
                        so evaluation, tracing, Insights and Optimizer all see the same
                        agent identity.

VERIFY: hosted-agent endpoint routing is version dependent; see docs/architecture.md
"Version-dependent decisions".
"""
from __future__ import annotations

import os

from ..images import to_data_url
from . import AnalysisRequest, Analyzer, AnalyzerError, AnalyzerResult, agent_response_format


def _project_client(*, allow_preview: bool = False):
    from azure.ai.projects import AIProjectClient  # type: ignore
    from azure.identity import DefaultAzureCredential  # type: ignore

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT is not set (see .env.example).")
    return AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential(), allow_preview=allow_preview)


def _user_content(req: AnalysisRequest) -> list[dict]:
    content: list[dict] = [{"type": "input_text", "text": req.request_text()}]
    for img in req.images:
        content.append({"type": "input_text", "text": f"Image {img.image_id}:"})
        content.append({"type": "input_image", "image_url": to_data_url(img), "detail": "high"})
    return content


def _usage(resp) -> tuple[int | None, int | None]:
    u = getattr(resp, "usage", None)
    return (getattr(u, "input_tokens", None), getattr(u, "output_tokens", None))


def _raise_for_response_error(resp, context: str) -> None:
    error = getattr(resp, "error", None)
    if getattr(resp, "status", None) != "failed" and not error:
        return
    code = getattr(error, "code", None) if error else None
    message = getattr(error, "message", None) if error else None
    details = ": ".join(x for x in (code, message) if x)
    raise AnalyzerError(f"{context} failed{f': {details}' if details else ''}")


class FoundryModelAnalyzer(Analyzer):
    name = "foundry-model"

    def __init__(self, project_client=None):
        self.project = project_client or _project_client()
        self.client = self.project.get_openai_client()

    def analyze(self, req: AnalysisRequest) -> AnalyzerResult:
        kwargs = dict(
            model=req.config.model,
            instructions=req.config.instructions,
            input=[{"role": "user", "content": _user_content(req)}],
            text={"format": agent_response_format()},
            store=False,
        )
        if req.config.temperature is not None and not req.config.model.startswith(("o", "gpt-5")):
            kwargs["temperature"] = req.config.temperature
        resp = self.client.responses.create(**kwargs)
        _raise_for_response_error(resp, "Foundry model response")
        i, o = _usage(resp)
        return AnalyzerResult(resp.output_text, model=req.config.model, input_tokens=i,
                              output_tokens=o, response_id=getattr(resp, "id", None))


class HostedAgentAnalyzer(Analyzer):
    name = "hosted-agent"

    def __init__(self, agent_name: str | None = None, project_client=None):
        self.agent_name = agent_name or os.environ.get("FOUNDRY_AGENT_NAME", "store-image-inspector")
        self.project = project_client or _project_client(allow_preview=True)
        self.client = self.project.get_openai_client(agent_name=self.agent_name)

    def analyze(self, req: AnalysisRequest) -> AnalyzerResult:
        resp = self.client.responses.create(
            input=[{"role": "user", "content": _user_content(req)}],
            text={"format": agent_response_format()},
        )
        _raise_for_response_error(resp, "Hosted agent response")
        i, o = _usage(resp)
        return AnalyzerResult(resp.output_text, model=f"hosted-agent:{self.agent_name}",
                              input_tokens=i, output_tokens=o, response_id=getattr(resp, "id", None))
