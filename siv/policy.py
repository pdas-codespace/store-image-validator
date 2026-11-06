"""Policy guidance retrieval.

Local provider reads versioned markdown under policy/ (stand-in for Foundry IQ).
The Foundry IQ provider is wired in the cloud phase; the contract is the same:
retrieval is constrained by rule-pack id + version and never substitutes another version.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import REPO_ROOT

POLICY_DIR = REPO_ROOT / "policy"


class PolicyRetrievalError(Exception):
    """Policy guidance is unavailable or does not match the pinned version."""


@dataclass(frozen=True)
class PolicyGuidance:
    rule_pack_id: str
    rule_pack_version: str
    source: str
    text: str


def retrieve_policy_guidance(category: str, rule_pack_id: str, version: str,
                             policy_dir: Path = POLICY_DIR) -> PolicyGuidance:
    if os.environ.get("SIV_SIMULATE_POLICY_OUTAGE") == "1":
        raise PolicyRetrievalError("Policy retrieval unavailable (simulated outage).")
    path = policy_dir / category / f"{rule_pack_id}-{version}.md"
    if not path.exists():
        raise PolicyRetrievalError(f"No policy guidance for {rule_pack_id}@{version} in category '{category}'.")
    raw = path.read_text()
    meta, body = {}, raw
    if raw.startswith("---"):
        _, fm, body = raw.split("---", 2)
        meta = yaml.safe_load(fm) or {}
    if str(meta.get("rule_pack_version")) != version or meta.get("rule_pack_id") != rule_pack_id:
        raise PolicyRetrievalError(
            f"Policy metadata {meta.get('rule_pack_id')}@{meta.get('rule_pack_version')} does not match {rule_pack_id}@{version}.")
    return PolicyGuidance(rule_pack_id, version, str(path.relative_to(REPO_ROOT)), body.strip())
