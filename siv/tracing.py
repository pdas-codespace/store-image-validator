"""OpenTelemetry tracing with Foundry/Application Insights export and a local JSONL mirror.

- If APPLICATIONINSIGHTS_CONNECTION_STRING is set (or obtainable from the Foundry project),
  spans go to Application Insights, which is what Foundry Tracing and Insights read.
- Every span's business attributes are also appended to .runs/traces.jsonl so runs are
  inspectable offline and in tests.
- Raw image bytes and image URLs are never written to attributes.
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import os
import time
import uuid
from pathlib import Path

from . import REPO_ROOT

_TRACE_FILE = Path(os.environ.get("SIV_TRACE_FILE", REPO_ROOT / ".runs" / "traces.jsonl"))
_otel_tracer = None
_configured = False
FORBIDDEN_KEYS = ("image.url", "image.data", "image.base64")
_current_trace: contextvars.ContextVar[str | None] = contextvars.ContextVar("siv_trace", default=None)


def configure(project_client=None) -> str:
    """Configure exporters once. Returns a description of where spans go."""
    global _otel_tracer, _configured
    if _configured:
        return "already configured"
    _configured = True
    try:
        from opentelemetry import trace  # type: ignore
    except ImportError:
        return f"local only ({_TRACE_FILE})"
    conn = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn and project_client is not None:
        try:
            conn = project_client.telemetry.get_application_insights_connection_string()
        except Exception:  # noqa: BLE001 - project may have no App Insights connected
            conn = None
    target = f"local only ({_TRACE_FILE})"
    if conn:
        from azure.monitor.opentelemetry import configure_azure_monitor  # type: ignore
        configure_azure_monitor(connection_string=conn)
        target = "Application Insights + local mirror"
        os.environ.setdefault("AZURE_EXPERIMENTAL_ENABLE_GENAI_TRACING", "true")
        # The azure-ai-projects Responses API preview instrumentor can crash on
        # NonRecordingSpan in some SDK/OpenTelemetry combinations. Keep exporting
        # our explicit spans, but opt out of that fragile auto-instrumentation
        # unless a caller deliberately enables it.
        os.environ.setdefault("AZURE_TRACING_GEN_AI_INSTRUMENT_RESPONSES_API", "false")
        try:
            from azure.ai.projects.telemetry import AIProjectInstrumentor  # type: ignore
            AIProjectInstrumentor().instrument()
        except Exception:  # noqa: BLE001
            pass
    _otel_tracer = trace.get_tracer("store-image-validator")
    return target


class _Span:
    def __init__(self, name: str, attrs: dict, otel_span=None):
        self.name, self.attrs, self._otel = name, dict(attrs), otel_span
        self.trace_id = None
        if otel_span is not None:
            ctx = otel_span.get_span_context()
            self.trace_id = format(ctx.trace_id, "032x")

    def set(self, key: str, value) -> None:
        if any(key.startswith(k) for k in FORBIDDEN_KEYS):
            raise ValueError(f"Refusing to trace sensitive attribute {key}")
        if isinstance(value, (list, tuple)):
            value = [str(v) for v in value]
        self.attrs[key] = value
        if self._otel is not None and value is not None:
            self._otel.set_attribute(key, value)

    def event(self, name: str, **attrs) -> None:
        if self._otel is not None:
            self._otel.add_event(name, {k: str(v) for k, v in attrs.items()})
        self.attrs.setdefault("_events", []).append({"name": name, **attrs})


@contextlib.contextmanager
def span(name: str, correlation_id: str | None = None, **attrs):
    attrs = {k.replace("__", "."): v for k, v in attrs.items()}
    if correlation_id:
        attrs["correlation.id"] = correlation_id
    start = time.perf_counter()
    cm = _otel_tracer.start_as_current_span(name) if _otel_tracer else contextlib.nullcontext()
    with cm as otel_span:
        s = _Span(name, {}, otel_span)
        for k, v in attrs.items():
            s.set(k, v)
        s.trace_id = s.trace_id or _current_trace.get() or uuid.uuid4().hex
        token = _current_trace.set(s.trace_id)
        status = "ok"
        try:
            yield s
        except Exception as exc:
            status = f"error: {type(exc).__name__}"
            raise
        finally:
            _current_trace.reset(token)
            s.attrs["duration_ms"] = round((time.perf_counter() - start) * 1000, 1)
            _TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with _TRACE_FILE.open("a") as f:
                f.write(json.dumps({"span": name, "trace_id": s.trace_id, "status": status,
                                    "ts": time.time(), "attributes": s.attrs}, default=str) + "\n")
