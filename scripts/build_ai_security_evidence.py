#!/usr/bin/env python3
"""Normalize AI asset security evidence without inventing unsupported statuses."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def props(item):
    return {row.get("key"): row.get("value") for row in item.get("properties") or []}


def version_key(value):
    return tuple((0, int(x)) if x.isdigit() else (1, x.lower())
                 for x in re.split(r"[.+_-]", str(value or "0")))


def label(raw):
    value = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    return {
        "approved": "Not malicious", "not_malicious": "Not malicious",
        "malicious": "Malicious", "suspicious": "Suspicious", "vulnerable": "Vulnerable",
        "scanning": "Scanning", "in_progress": "Scanning",
        "unscanned": "Not scanned", "not_scanned": "Not scanned",
        "n/a": "N/A", "n_a": "N/A", "": "N/A",
    }.get(value, str(raw or "N/A"))


def counts(assets):
    result = Counter()
    for row in assets:
        key = label(row.get("security_status")).lower().replace(" ", "_").replace("/", "_")
        result[key] += 1
    return {key: result.get(key, 0) for key in
            ("malicious", "suspicious", "not_malicious", "scanning", "not_scanned", "n_a")}


def latest_assets(payload, name_key, version_key_name, status_key=None):
    latest = {}
    for item in payload.get("results") or []:
        p = props(item)
        name = p.get(name_key)
        if not name:
            continue
        version = p.get(version_key_name) or "Unavailable"
        identity = (name, item.get("repo"))
        candidate = {
            "name": name, "version": version, "repository": item.get("repo"),
            "security_status": label(p.get(status_key)) if status_key else "N/A",
            "evidence_source": "Artifactory artifact properties",
        }
        current = latest.get(identity)
        if current is None or version_key(version) > version_key(current["version"]):
            latest[identity] = candidate
    return sorted(latest.values(), key=lambda row: (row["name"].lower(), row.get("repository") or ""))


def overlay(assets, rows):
    by_name = {row.get("name"): row for row in rows}
    found = set()
    for asset in assets:
        if asset["name"] in by_name:
            supplied = by_name[asset["name"]]
            asset.update({key: value for key, value in supplied.items() if value is not None})
            found.add(asset["name"])
    assets.extend(row for row in rows if row.get("name") not in found)
    return sorted(assets, key=lambda row: row.get("name", "").lower())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--skill-aql", required=True, type=Path)
    parser.add_argument("--plugin-aql", required=True, type=Path)
    parser.add_argument("--ui-evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    evidence = load(args.base)
    ui = load(args.ui_evidence)
    inventory = evidence.setdefault("inventory", {})
    skill_assets = latest_assets(load(args.skill_aql), "skill.name", "skill.version", "skills.xray.status")
    plugin_assets = latest_assets(load(args.plugin_aql), "agentplugins.name", "agentplugins.version")
    skill_assets = overlay(skill_assets, ui.get("skills") or [])
    plugin_assets = overlay(plugin_assets, ui.get("plugins") or [])
    mcp_assets = ui.get("mcp_servers") or []
    model_assets = ui.get("models") or []

    for key, assets in (("skills", skill_assets), ("plugins", plugin_assets),
                        ("mcp_servers", mcp_assets), ("models", model_assets)):
        target = inventory.setdefault(key, {})
        target["visible_assets"] = assets
        target["visible"] = len(assets)
        target["security_counts"] = counts(assets)
        target["security_observed"] = len(assets)

    evidence["collected_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    evidence["source"] = "JFrog Artifactory AI asset properties plus dated JFrog AI Catalog UI evidence"
    evidence["limitations"] = [
        "MCP and model totals below are the rows visible in the supplied current-state UI captures, not a historical month-end inventory.",
        "Plugin artifacts do not expose the Skills xrayStatus route; N/A is retained unless the UI supplied an explicit status.",
        "Current AI Catalog status is shown as a dated revalidation and is not backdated to the report period.",
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
