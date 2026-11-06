"""Evaluation harness shared by the local runner, CI, and the Foundry upload.

1. Run every dataset row through the real pipeline (any analyzer).
2. Build Foundry-compatible rows: {query, response, ground_truth, ...}.
3. Score rows with the self-contained code evaluators in evaluation/evaluators/.
4. Aggregate metrics, apply release gates, write a machine-readable report.
"""
from __future__ import annotations

import importlib.util
import json
import statistics
import tempfile
import time
import uuid
from pathlib import Path

import yaml

from . import REPO_ROOT
from .agent_config import load_agent_config
from .analyzers import Analyzer
from .pipeline import inspect
from .rulepack import load_rule_pack
from .store import ResultStore

EVAL_DIR = REPO_ROOT / "evaluation"
EVALUATOR_DIR = EVAL_DIR / "evaluators"


def load_dataset(partitions: list[str]) -> list[dict]:
    rows = []
    for p in partitions:
        path = EVAL_DIR / "datasets" / f"{p}.jsonl"
        rows += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return rows


def load_evaluators() -> dict:
    evs = {}
    for f in sorted(EVALUATOR_DIR.glob("[!_]*.py")):
        spec = importlib.util.spec_from_file_location(f"siv_eval_{f.stem}", f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        evs[f.stem] = mod.grade
    return evs


def ground_truth(row: dict) -> dict:
    pack = load_rule_pack(row["rule_pack"]["id"], row["rule_pack"]["version"])
    return {
        "expected": row["expected"],
        "rule_pack": {
            "id": pack.id, "version": pack.version,
            "rules": [{"id": r.id, "weight": r.weight, "mandatory": r.mandatory} for r in pack.rules],
            "scoring": {"min": pack.score_min, "max": pack.score_max,
                        "cannot_determine_credit": pack.cannot_determine_credit,
                        "min_rule_confidence": pack.min_rule_confidence},
        },
    }


def to_response(record: dict) -> dict:
    keep = ["event", "decision", "score", "raw_score", "requires_human_review", "review_reasons", "message",
            "next_action", "agent_output", "effective_rule_results", "failure", "trace_id", "agent_version"]
    out = {k: record.get(k) for k in keep}
    out["image_ids"] = [f"img-{n:03d}" for n in range(1, len(record.get("image_hashes", [])) + 1)]
    return out


def run(analyzer: Analyzer, partitions: list[str], repeats: int = 1) -> dict:
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    config = load_agent_config()
    rows = load_dataset(partitions)
    evaluators = load_evaluators()
    scored = []
    with tempfile.TemporaryDirectory() as tmp:
        for row in rows:
            records = []
            for rep in range(repeats):
                store = ResultStore(Path(tmp) / f"rep{rep}")  # fresh store: repeats are real re-runs
                records.append(inspect([str(REPO_ROOT / p) for p in row["images"]],
                                       rule_pack_id=row["rule_pack"]["id"],
                                       rule_pack_version=row["rule_pack"]["version"], analyzer=analyzer,
                                       submission_id=f"eval-{run_id}-{row['id']}", store_id="eval",
                                       correlation_id=f"eval-{run_id}-{row['id']}", store=store, config=config))
            record = records[0]
            item = {
                "id": row["id"], "partition": row["partition"],
                "query": f"Inspect {row['category']} images {row['images']} against {row['rule_pack']['id']}@{row['rule_pack']['version']}",
                "response": json.dumps(to_response(record)),
                "ground_truth": json.dumps(ground_truth(row)),
            }
            scores = {name: float(fn({}, item)) for name, fn in evaluators.items()} \
                if record["event"] != "InspectionFailed" else {name: 0.0 for name in evaluators}
            rep_scores = [r.get("score") for r in records if r.get("score") is not None]
            scored.append({**item, "scores": scores, "event": record["event"],
                           "decision": record.get("decision"), "expected_decision": row["expected"]["decision"],
                           "score_range": (max(rep_scores) - min(rep_scores)) if rep_scores else None,
                           "tokens": (record.get("usage") or {}),
                           "latency_ms": None})
    return {"run_id": run_id, "analyzer": analyzer.name, "agent_version": f"{config.source}@{config.version_hash}",
            "model": config.model, "partitions": partitions, "repeats": repeats, "rows": scored,
            "metrics": aggregate(scored)}


def aggregate(rows: list[dict]) -> dict:
    def mean(name, subset=None):
        vals = [r["scores"][name] for r in (subset or rows) if name in r["scores"]]
        return round(statistics.mean(vals), 4) if vals else None

    abstained = [r for r in rows if r["decision"] == "CANNOT_DETERMINE"]
    should = [r for r in rows if r["expected_decision"] == "CANNOT_DETERMINE"]
    tp = sum(1 for r in abstained if r["expected_decision"] == "CANNOT_DETERMINE")
    golden = [r for r in rows if r["partition"] == "golden"]
    adversarial = [r for r in rows if r["partition"] == "adversarial"]
    ranges = [r["score_range"] for r in rows if r["score_range"] is not None]
    tokens_in = [r["tokens"].get("input_tokens") or 0 for r in rows]
    tokens_out = [r["tokens"].get("output_tokens") or 0 for r in rows]
    return {
        "rows": len(rows),
        "decision_accuracy": mean("decision_accuracy"),
        "rule_status_agreement": mean("rule_status_accuracy"),
        "schema_valid_rate": mean("schema_validity"),
        "false_pass_rate": round(1 - mean("no_false_pass"), 4) if rows else None,
        "false_fail_rate": round(1 - mean("no_false_fail"), 4) if rows else None,
        "mandatory_false_pass_count": sum(1 for r in golden if r["scores"].get("no_false_pass") == 0.0),
        "abstention_precision": round(tp / len(abstained), 4) if abstained else 1.0,
        "abstention_recall": round(tp / len(should), 4) if should else 1.0,
        "evidence_consistency": mean("evidence_consistency"),
        "policy_adherence": mean("policy_adherence"),
        "score_consistency": mean("score_consistency"),
        "explanation_usefulness": mean("explanation_usefulness"),
        "injection_resistance": mean("injection_resistance", adversarial) if adversarial else 1.0,
        "repeat_score_variance": max(ranges) if ranges else 0,
        "failed_inspections": sum(1 for r in rows if r["event"] == "InspectionFailed"),
        "input_tokens_total": sum(tokens_in),
        "output_tokens_total": sum(tokens_out),
    }


def check_gates(metrics: dict, gates_path: Path = EVAL_DIR / "release_gates.yaml") -> list[dict]:
    gates = yaml.safe_load(gates_path.read_text())["gates"]
    results = []
    for name, g in gates.items():
        value = metrics.get(name)
        ok = value is not None and ("min" not in g or value >= g["min"]) and ("max" not in g or value <= g["max"])
        results.append({"gate": name, "value": value, "min": g.get("min"), "max": g.get("max"), "passed": ok})
    return results
