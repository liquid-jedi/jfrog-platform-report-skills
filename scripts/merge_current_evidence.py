#!/usr/bin/env python3
"""Attach timestamped current-state evidence without changing period metrics."""

import argparse
import json
from pathlib import Path

from enrich_report_modules import build_access_governance, metric


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--ai-catalog-evidence", type=Path)
    parser.add_argument("--access-governance-evidence", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = load(args.report)

    if args.ai_catalog_evidence:
        evidence = load(args.ai_catalog_evidence)
        inventory = evidence.get("inventory") or {}
        models = inventory.get("models") or {}
        mcps = inventory.get("mcp_servers") or {}
        skills = inventory.get("skills") or {}
        plugins = inventory.get("plugins") or {}
        shadow = evidence.get("shadow_ai") or {}
        gateway = evidence.get("gateway_activity") or {}
        observed = []
        for mid, label, value, unit, formula in [
            ("ai-detected-models", "Detected models", models.get("detected"), "models", "inventory.models.detected"),
            ("ai-allowed-models", "Allowed models", models.get("allowed"), "models", "inventory.models.allowed"),
            ("ai-allowed-mcp-servers", "Allowed MCP servers", mcps.get("allowed"), "servers", "inventory.mcp_servers.allowed"),
            ("ai-registered-skills", "Registered agent skills", skills.get("total"), "skills", "inventory.skills.total"),
            ("ai-scanned-skills", "Security-scanned skills", skills.get("scanned"), "skills", "inventory.skills.scanned"),
            ("ai-not-malicious-skills", "Skills scanned as not malicious", (skills.get("security_counts") or {}).get("not_malicious"), "skills", "inventory.skills.security_counts.not_malicious"),
            ("ai-malicious-skills", "Skills classified malicious", (skills.get("security_counts") or {}).get("malicious"), "skills", "inventory.skills.security_counts.malicious"),
            ("ai-suspicious-skills", "Skills classified suspicious", (skills.get("security_counts") or {}).get("suspicious"), "skills", "inventory.skills.security_counts.suspicious"),
            ("ai-unscanned-skills", "Skills not scanned", (skills.get("security_counts") or {}).get("not_scanned"), "skills", "inventory.skills.security_counts.not_scanned"),
            ("ai-scanning-skills", "Skills still scanning", (skills.get("security_counts") or {}).get("scanning"), "skills", "inventory.skills.security_counts.scanning"),
            ("ai-vulnerable-skills", "Skills with vulnerable dependencies", (skills.get("vulnerability_counts") or {}).get("vulnerable"), "skills", "inventory.skills.vulnerability_counts.vulnerable"),
            ("ai-skills-without-project", "Skills not linked to a project", (skills.get("project_counts") or {}).get("unlinked"), "skills", "inventory.skills.project_counts.unlinked"),
            ("ai-registered-plugins", "Registered agent plugins", plugins.get("total"), "plugins", "inventory.plugins.total"),
            ("ai-malicious-mcp", "MCP servers classified malicious", (mcps.get("security_counts") or {}).get("malicious"), "servers", "inventory.mcp_servers.security_counts.malicious"),
            ("ai-suspicious-mcp", "MCP servers classified suspicious", (mcps.get("security_counts") or {}).get("suspicious"), "servers", "inventory.mcp_servers.security_counts.suspicious"),
            ("ai-malicious-plugins", "Plugins classified malicious", (plugins.get("security_counts") or {}).get("malicious"), "plugins", "inventory.plugins.security_counts.malicious"),
            ("ai-suspicious-plugins", "Plugins classified suspicious", (plugins.get("security_counts") or {}).get("suspicious"), "plugins", "inventory.plugins.security_counts.suspicious"),
            ("ai-malicious-models", "Models classified malicious", (models.get("security_counts") or {}).get("malicious"), "models", "inventory.models.security_counts.malicious"),
            ("ai-shadow-models", "Shadow AI models detected", shadow.get("detected"), "models", "shadow_ai.detected"),
            ("ai-shadow-managed", "Detected models under governance", shadow.get("managed"), "models", "shadow_ai.managed"),
            ("ai-shadow-unmanaged", "Detected models not yet governed", shadow.get("unmanaged"), "models", "shadow_ai.unmanaged"),
            ("ai-live-models", "Live models", gateway.get("live_models"), "models", "gateway_activity.live_models"),
            ("ai-gateway-requests", "AI gateway requests", gateway.get("requests"), "requests", "gateway_activity.requests"),
        ]:
            if value is not None:
                observed.append(metric(mid, label, value, unit, "observed", evidence.get("source", "AI Catalog collector"), formula))
        report["current_ai_security"] = {
            "status": evidence.get("status") or "available",
            "as_of": evidence.get("security_collected_at") or evidence.get("collected_at"),
            "metrics": observed, "inventory": inventory, "shadow_ai": shadow,
            "gateway_activity": gateway, "evidence_limitations": evidence.get("limitations") or [],
            "collection_quality": evidence.get("collection_quality") or {}, "source": evidence.get("source"),
            "note": "Current posture is timestamped and is not attributed to the historical report month or included in period trends.",
        }

    if args.access_governance_evidence:
        report["access_governance"] = build_access_governance(load(args.access_governance_evidence))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
