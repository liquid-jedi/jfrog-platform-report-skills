#!/usr/bin/env python3
"""Refresh the current AI Catalog module in an existing classified report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def metric(mid, label, value, unit, source, formula):
    return {"id": mid, "label": label, "value": value, "unit": unit,
            "classification": "observed", "source": source, "formula": formula}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    inventory = evidence.get("inventory") or {}
    skills = inventory.get("skills") or {}
    mcps = inventory.get("mcp_servers") or {}
    source = evidence.get("source", "AI Catalog collector")
    definitions = []
    asset_specs = (
        ("mcp", "mcp_servers", "MCP servers", "servers", mcps),
        ("skills", "skills", "Skills", "skills", skills),
        ("plugins", "plugins", "Plugins", "plugins", inventory.get("plugins") or {}),
        ("models", "models", "Models", "models", inventory.get("models") or {}),
    )
    for slug, path, label, unit, asset in asset_specs:
        total = asset.get("visible") if asset.get("visible") is not None else asset.get("total")
        if total is None and asset.get("visible_assets") is not None:
            total = len(asset.get("visible_assets") or [])
        definitions.append((f"ai-{slug}-assets-observed", f"{label} with captured status", total, unit,
                            f"inventory.{path}.visible_assets"))
        for key, suffix in (("malicious", "malicious"), ("suspicious", "suspicious"), ("vulnerable", "vulnerable"),
                            ("not_malicious", "not malicious"), ("scanning", "scanning"),
                            ("not_scanned", "not scanned"), ("n_a", "N/A")):
            value = (asset.get("security_counts") or {}).get(key)
            definitions.append((f"ai-{slug}-{key}", f"{label}: {suffix}", value, unit,
                                f"inventory.{path}.security_counts.{key}"))
        for key, suffix in (("vulnerable", "vulnerable"), ("no_known_vulnerabilities", "without known vulnerabilities"), ("no_xray_data", "without Xray evidence")):
            value = (asset.get("vulnerability_counts") or {}).get(key)
            if value is not None:
                definitions.append((f"ai-{slug}-dependency-{key}", f"{label}: {suffix}", value, unit, f"inventory.{path}.vulnerability_counts.{key}"))
        for key, suffix in (("linked", "linked to a project"), ("unlinked", "not linked to a project"), ("unknown", "project link unknown")):
            value = (asset.get("project_counts") or {}).get(key)
            if value is not None:
                definitions.append((f"ai-{slug}-project-{key}", f"{label}: {suffix}", value, unit, f"inventory.{path}.project_counts.{key}"))
    module = report.setdefault("ai_catalog", {})
    retained = [row for row in module.get("metrics") or [] if not row.get("id", "").startswith("ai-") or row.get("id") in {"ai-repositories", "ai-storage", "ai-artifacts"}]
    retained.extend(metric(row[0], row[1], row[2], row[3], source, row[4])
                    for row in definitions if row[2] is not None)
    module["metrics"] = retained
    module["inventory"] = inventory
    module["catalog_inventory"] = inventory
    module["shadow_ai"] = evidence.get("shadow_ai") or {}
    module["gateway_activity"] = evidence.get("gateway_activity") or {}
    module["evidence_limitations"] = evidence.get("limitations") or []
    module["collected_at"] = evidence.get("security_collected_at") or evidence.get("collected_at")
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
