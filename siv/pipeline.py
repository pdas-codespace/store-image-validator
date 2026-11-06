"""Single-submission inspection: intake -> agent -> validate -> deterministic decision -> persist.

This is the local equivalent of the orchestration worker. In the cloud phase the same
function runs behind Service Bus / Durable Functions; the contract does not change.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone

from .agent_config import AgentConfig, load_agent_config
from .analyzers import AGENT_SCHEMA, AnalysisRequest, Analyzer, AnalyzerError
from .images import ImageValidationError, load_image
from .jsonschema_lite import validate
from .policy import PolicyRetrievalError, retrieve_policy_guidance
from .rulepack import RulePack, RulePackError, load_rule_pack
from .scoring import decide
from .store import ResultStore
from .tracing import span

MAX_ATTEMPTS = 2  # 1 retry for malformed output


class AgentOutputError(Exception):
    pass


def idempotency_key(tenant_id: str, submission_id: str, pack_version: str, image_hashes: list[str],
                    agent_version: str) -> str:
    blob = "|".join([tenant_id, submission_id, pack_version, *image_hashes, agent_version])
    return hashlib.sha256(blob.encode()).hexdigest()


def check_agent_output(result: dict, pack: RulePack, submission_id: str) -> list[str]:
    errors = validate(result, AGENT_SCHEMA)
    if errors:
        return errors
    if result["rule_pack"] != {"id": pack.id, "version": pack.version}:
        errors.append(f"rule_pack echo {result['rule_pack']} != {pack.id}@{pack.version}")
    if result["submission_id"] != submission_id:
        errors.append("submission_id echo mismatch")
    got = [r["rule_id"] for r in result["rule_results"]]
    if sorted(got) != sorted(pack.rule_ids) or len(got) != len(set(got)):
        errors.append(f"rule_results must contain each of {pack.rule_ids} exactly once, got {got}")
    for r in result["rule_results"]:
        if r["status"] in ("PASS", "FAIL") and not r["evidence"]:
            errors.append(f"{r['rule_id']}: {r['status']} without evidence")
        if r["status"] == "CANNOT_DETERMINE" and not r["missing_evidence"]:
            errors.append(f"{r['rule_id']}: CANNOT_DETERMINE without missing_evidence")
    return errors


def _event_type(decision) -> str:
    if decision.requires_human_review:
        return "InspectionNeedsReview"
    if decision.decision == "CANNOT_DETERMINE":
        return "InspectionResubmissionRequired"
    return "InspectionCompleted"


def inspect(image_paths: list[str], *, rule_pack_id: str, rule_pack_version: str, analyzer: Analyzer,
            submission_id: str, tenant_id: str = "contoso", store_id: str = "local",
            correlation_id: str | None = None, store: ResultStore | None = None,
            config: AgentConfig | None = None) -> dict:
    store = store or ResultStore()
    config = config or load_agent_config()
    agent_version = f"{config.source}@{config.version_hash}"
    correlation_id = correlation_id or f"corr-{submission_id}"
    t0 = time.perf_counter()

    with span("inspection", correlation_id, tenant__id=tenant_id, submission__id=submission_id,
              store__id=store_id, rule_pack__id=rule_pack_id, rule_pack__version=rule_pack_version,
              agent__version=agent_version, model__deployment=config.model,
              **{"gen_ai.agent.name": "store-image-inspector", "gen_ai.agent.version": agent_version}) as root:
        base = {"submission_id": submission_id, "tenant_id": tenant_id, "store_id": store_id,
                "correlation_id": correlation_id, "trace_id": root.trace_id,
                "rule_pack": {"id": rule_pack_id, "version": rule_pack_version},
                "agent_version": agent_version, "model_deployment": config.model,
                "analyzer": analyzer.name}

        def failed(reason: str, kind: str) -> dict:
            root.set("decision", "FAILED")
            root.set("failure.kind", kind)
            return {**base, "event": "InspectionFailed", "failure": {"kind": kind, "reason": reason},
                    "evaluated_at": datetime.now(timezone.utc).isoformat()}

        # 1. Pin rule pack - no fallback to another version.
        try:
            pack = load_rule_pack(rule_pack_id, rule_pack_version)
        except RulePackError as exc:
            return failed(str(exc), "WRONG_POLICY_VERSION")
        root.set("category", pack.category)

        # 2. Image intake.
        try:
            if not pack.min_images <= len(image_paths) <= pack.max_images:
                raise ImageValidationError(f"{len(image_paths)} images; rule pack needs {pack.min_images}-{pack.max_images}")
            images = [load_image(p, f"img-{n:03d}") for n, p in enumerate(image_paths, 1)]
        except (ImageValidationError, OSError) as exc:
            return failed(str(exc), "INVALID_IMAGE")
        hashes = [i.sha256 for i in images]
        root.set("image.count", len(images))
        root.set("image.hashes", hashes)

        # 3. Idempotency.
        key = idempotency_key(tenant_id, submission_id, pack.version, hashes, agent_version)
        existing = store.get(key)
        if existing:
            root.set("idempotent.duplicate", True)
            return {**existing, "duplicate_delivery": True}

        # 4. Policy guidance (Foundry IQ stand-in), version-constrained.
        policy_ok, guidance = True, None
        try:
            with span("retrieve_policy_guidance", correlation_id, rule_pack__version=pack.version):
                guidance = retrieve_policy_guidance(pack.category, pack.id, pack.version)
        except PolicyRetrievalError as exc:
            policy_ok = False
            root.event("policy_retrieval_failed", reason=str(exc))

        # 5. Agent call + output validation with bounded retry.
        req = AnalysisRequest(submission_id, pack.category, pack, images, guidance, config)
        agent_result, ar, attempts = None, None, 0
        while attempts < MAX_ATTEMPTS:
            attempts += 1
            with span("invoke_agent", correlation_id, attempt=attempts, analyzer=analyzer.name,
                      **{"gen_ai.operation.name": "invoke_agent", "gen_ai.request.model": config.model}) as s:
                t_img = time.perf_counter()
                try:
                    ar = analyzer.analyze(req)
                except LookupError as exc:
                    return failed(str(exc), "NO_RECORDING")
                except AnalyzerError as exc:
                    return failed(str(exc), "AGENT_ERROR")
                s.set("latency.image_analysis_ms", round((time.perf_counter() - t_img) * 1000, 1))
                s.set("input_tokens", ar.input_tokens)
                s.set("output_tokens", ar.output_tokens)
                try:
                    candidate = json.loads(ar.raw_text)
                    errs = check_agent_output(candidate, pack, submission_id)
                except json.JSONDecodeError as exc:
                    errs = [f"not JSON: {exc}"]
                s.set("schema.valid", not errs)
                if not errs:
                    agent_result = candidate
                    break
                s.event("agent_output_rejected", errors="; ".join(errs[:5]))
                req.retry_feedback = "; ".join(errs[:10])
        if agent_result is None:
            return failed(f"Agent output invalid after {attempts} attempts: {req.retry_feedback}", "SCHEMA_INVALID")

        # 6. Deterministic decision.
        d = decide(pack, agent_result, policy_ok=policy_ok)
        for r in d.effective_rule_results:
            with span("rule_result", correlation_id, rule__id=r["rule_id"], rule__status=r["status"],
                      rule__confidence=r["confidence"]):
                pass
        root.set("decision", d.decision)
        root.set("score", d.score)
        root.set("human_review.required", d.requires_human_review)
        root.set("abstention.reason", d.abstention_reason)
        root.set("image.issues", agent_result["image_assessment"]["issues"])
        root.set("latency.total_ms", round((time.perf_counter() - t0) * 1000, 1))

        record = {
            **base,
            "category": pack.category,
            "idempotency_key": key,
            "image_hashes": hashes,
            "event": _event_type(d),
            "decision": d.decision,
            "score": d.score,
            "raw_score": d.raw_score,
            "requires_human_review": d.requires_human_review,
            "review_reasons": d.review_reasons,
            "message": d.message,
            "next_action": d.next_action,
            "gate_adjustments": d.gate_adjustments,
            "policy_guidance_source": guidance.source if guidance else None,
            "agent_output": agent_result,
            "effective_rule_results": d.effective_rule_results,
            "usage": {"input_tokens": ar.input_tokens, "output_tokens": ar.output_tokens,
                      "response_id": ar.response_id, "attempts": attempts},
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
        if not store.put_if_absent(key, record):
            return {**store.get(key), "duplicate_delivery": True}
        return record
