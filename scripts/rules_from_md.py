"""Generate rule packs and policy guidance from rules/source/*.md.

  python scripts/rules_from_md.py                 # (re)write rules/<category>/<pack>-<ver>.yaml + policy/<category>/<pack>-<ver>.md
  python scripts/rules_from_md.py --check         # exit 1 if generated files are missing or out of date
  python scripts/rules_from_md.py --source other.md

Format: see the "How to read this file" section of rules/source/contoso-validation-rules.md.
Every generated pack is validated against rules/schema/rule-pack.schema.json before it is written.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from siv.rulepack import _parse  # noqa: E402  (schema + consistency validation)

SOURCE_DIR = ROOT / "rules" / "source"
ABSTENTION_PREFIX = "Can't determine with confidence from images submitted and here's why:"
TAG = re.compile(r"^\[([A-Z]+-\d{3}(?:\s*,\s*[A-Z]+-\d{3})*)(?:\s+(ignore|accept|note))?\]\s*(.+)$")
RULE_COLUMNS = ["ID", "Title", "Requirement", "Type", "Weight", "Mandatory", "Can't determine when"]


class FormatError(Exception):
    pass


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _table(lines: list[str], start: int) -> tuple[list[list[str]], int]:
    rows, i = [], start
    while i < len(lines) and lines[i].lstrip().startswith("|"):
        cells = _cells(lines[i])
        if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
            rows.append(cells)
        i += 1
    return rows, i


def _bullets(block: list[str], heading: str) -> list[dict]:
    out = []
    for raw in block:
        if not raw.startswith("- "):
            continue
        text = raw[2:].strip()
        m = TAG.match(text)
        if m:
            ids = [x.strip() for x in m.group(1).split(",")]
            out.append({"rules": ids, "kind": m.group(2) or "note", "text": m.group(3).strip(), "section": heading})
        else:
            out.append({"rules": [], "kind": "note", "text": text, "section": heading})
    return out


def parse(md: str) -> list[dict]:
    """Return one dict per category section that has a 'Rule pack' field table."""
    lines = md.splitlines()
    sections, current = [], None
    in_code = in_details = False
    for line in lines:
        if line.startswith("```"):
            in_code = not in_code
        if line.strip().startswith("<details"):
            in_details = True
        if line.strip().startswith("</details>"):
            in_details = False
            continue
        if in_code or in_details:
            continue
        if line.startswith("## "):
            current = {"name": line[3:].strip(), "lines": []}
            sections.append(current)
        elif current is not None:
            current["lines"].append(line)

    packs = []
    for sec in sections:
        body = sec["lines"]
        sub, i = "_fields", 0
        blocks: dict[str, list[str]] = {}
        fields, rules = {}, []
        while i < len(body):
            line = body[i]
            if line.startswith("### "):
                sub = line[4:].strip().lower()
                i += 1
                continue
            if line.lstrip().startswith("|"):
                rows, i = _table(body, i)
                if sub == "_fields":
                    fields.update({r[0]: r[1] for r in rows[1:] if len(r) >= 2})
                elif sub == "rules":
                    header = rows[0]
                    if header != RULE_COLUMNS:
                        raise FormatError(f"{sec['name']}: rules table columns must be {RULE_COLUMNS}, got {header}")
                    rules = [dict(zip(header, r)) for r in rows[1:]]
                continue
            blocks.setdefault(sub, []).append(line.strip())
            i += 1
        if "Rule pack" not in fields:
            continue
        if not rules:
            raise FormatError(f"{sec['name']}: no rules table")
        guidance = _bullets(blocks.get("guidance", []), "guidance") + \
            _bullets(blocks.get("interpretation notes", []), "interpretation")
        packs.append({"title": sec["name"], "fields": fields, "rules": rules, "guidance": guidance})
    return packs


def _num(v: str, what: str):
    try:
        f = float(v)
    except ValueError as exc:
        raise FormatError(f"{what}: '{v}' is not a number") from exc
    return int(f) if f.is_integer() else f


def build_pack(p: dict) -> dict:
    f, name = p["fields"], p["title"]
    ids = {r["ID"] for r in p["rules"]}
    for g in p["guidance"]:
        unknown = [x for x in g["rules"] if x not in ids]
        if unknown:
            raise FormatError(f"{name}: guidance refers to unknown rule(s) {unknown}: {g['text']}")
    lo, _, hi = f.get("Images", "1-5").partition("-")
    rules = []
    for r in p["rules"]:
        mand = r["Mandatory"].strip().lower()
        if mand not in ("yes", "no"):
            raise FormatError(f"{name} {r['ID']}: Mandatory must be yes/no")
        rule = {"id": r["ID"], "title": r["Title"], "type": r["Type"], "weight": _num(r["Weight"], f"{name} {r['ID']} weight"),
                "mandatory": mand == "yes", "requirement": r["Requirement"]}
        accept = [g["text"] for g in p["guidance"] if r["ID"] in g["rules"] and g["kind"] == "accept"]
        ignore = [g["text"] for g in p["guidance"] if r["ID"] in g["rules"] and g["kind"] == "ignore"]
        cd = [c.strip() for c in r["Can't determine when"].split(";") if c.strip()]
        if accept:
            rule["acceptedAlternatives"] = accept
        if cd:
            rule["cannotDetermineWhen"] = cd
        if ignore:
            rule["ignore"] = ignore
        rules.append(rule)
    scoring = {"range": {"minimum": 0, "maximum": 10}, "method": "weighted_rule_score",
               "reviewThreshold": _num(f.get("Review threshold", "6"), f"{name} review threshold"),
               "passThreshold": _num(f["Pass threshold"], f"{name} pass threshold"),
               "cannotDetermineCredit": _num(f.get("CANNOT_DETERMINE credit", "0.5"), f"{name} CD credit"),
               "minimumRuleConfidence": _num(f.get("Min rule confidence", "0.65"), f"{name} min confidence")}
    doc = {"rulePackId": f["Rule pack"], "version": f["Version"], "category": f["Category"],
           "customerId": f.get("Customer", ""), "effectiveFrom": f.get("Effective from", ""),
           "captureRequirements": {"minimumImages": int(lo), "maximumImages": int(hi or lo)},
           "scoring": scoring, "rules": rules, "response": {"abstentionPrefix": ABSTENTION_PREFIX}}
    _parse(doc, f"{name} (from markdown)")  # raises RulePackError if invalid
    return doc


def build_policy(p: dict, doc: dict, source: str) -> str:
    fm = {"customer_id": doc["customerId"], "category": doc["category"], "rule_pack_id": doc["rulePackId"],
          "rule_pack_version": doc["version"], "jurisdiction": "US", "language": "en-US"}
    out = ["---", yaml.safe_dump(fm, sort_keys=False).strip(), "---",
           f"# {p['title']} interpretation guidance (v{doc['version']})", "",
           f"<!-- GENERATED from {source} by scripts/rules_from_md.py. Edit the source, not this file.",
           "     Local stand-in for Foundry IQ; filter by the metadata above when moving to a knowledge base. -->", ""]
    general = [g for g in p["guidance"] if not g["rules"]]
    if general:
        out += ["## General", *[f"- {g['text']}" for g in general], ""]
    for r in doc["rules"]:
        notes = [g for g in p["guidance"] if r["id"] in g["rules"]]
        out += [f"## {r['id']} {r['title']}", f"Requirement: {r['requirement']}"]
        for g in notes:
            suffix = " (interpretation note)" if g["section"] == "interpretation" else ""
            out.append(f"- {g['text']}{suffix}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_yaml(doc: dict, source: str) -> str:
    head = (f"# GENERATED from {source} by scripts/rules_from_md.py. Edit the source, not this file.\n"
            "# Weights, thresholds and mandatory flags are business-owned; the optimizer must not change them.\n")
    return head + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110)


def outputs(source: Path) -> dict[Path, str]:
    rel = source.relative_to(ROOT).as_posix()
    files = {}
    for p in parse(source.read_text()):
        doc = build_pack(p)
        stem = f"{doc['rulePackId']}-{doc['version']}"
        files[ROOT / "rules" / doc["category"] / f"{stem}.yaml"] = render_yaml(doc, rel)
        files[ROOT / "policy" / doc["category"] / f"{stem}.md"] = build_policy(p, doc, rel)
    return files


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, action="append")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    sources = [s.resolve() for s in args.source] if args.source else sorted(SOURCE_DIR.glob("*.md"))
    stale = []
    for src in sources:
        for path, text in outputs(src).items():
            rel = path.relative_to(ROOT)
            if args.check:
                if not path.exists() or path.read_text() != text:
                    stale.append(str(rel))
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            changed = not path.exists() or path.read_text() != text
            if changed and path.exists():
                path.unlink()  # replace rather than truncate (works on synced/network mounts)
            if changed:
                path.write_text(text)
            print(f"{'wrote ' if changed else 'same  '} {rel}")
    if args.check:
        if stale:
            print("Out of date (run scripts/rules_from_md.py):\n  " + "\n  ".join(stale))
            sys.exit(1)
        print("generated rule packs are up to date")


if __name__ == "__main__":
    main()
