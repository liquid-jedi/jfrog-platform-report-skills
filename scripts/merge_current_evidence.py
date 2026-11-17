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
    parser.add_argument("--apptrust-evidence", type=Path)
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
        executive = report.setdefault("executive_signals", [])
        existing = {item.get("id") for item in executive}
        curation_users = next((item for item in (report.get("curation") or {}).get("metrics", [])
                               if item.get("id") == "curation-users"), None)
        if curation_users and "curation-users" not in existing:
            executive.append(curation_users)
        access_metrics = {item.get("id"): item for item in report["access_governance"].get("metrics", [])}
        for metric_id in ("access-long-lived", "access-non-expiring"):
            if metric_id not in existing and access_metrics.get(metric_id):
                executive.append(access_metrics[metric_id])

    if args.apptrust_evidence:
        evidence = load(args.apptrust_evidence)
        inventory = evidence.get("inventory") or {}
        governance = evidence.get("release_governance") or {}
        attestations = evidence.get("evidence") or {}
        status = evidence.get("status") or "unavailable"
        metrics = []
        for mid, label, value, unit, classification, formula, risk_state in [
            ("apptrust-applications", "Applications", inventory.get("applications_total"), "applications", "observed", "count visible applications", "neutral"),
            ("apptrust-production", "Production applications", (inventory.get("maturity") or {}).get("production"), "applications", "derived", "count(maturity = production)", "neutral"),
            ("apptrust-critical", "Critical applications", (inventory.get("criticality") or {}).get("critical"), "applications", "derived", "count(criticality = critical)", "neutral"),
            ("apptrust-unowned", "Applications without an owner", inventory.get("unowned"), "applications", "derived", "count(owners is empty)", "bad"),
            ("apptrust-critical-unowned", "Critical applications without an owner", inventory.get("critical_unowned"), "applications", "derived", "count(criticality = critical and owners is empty)", "bad"),
            ("apptrust-versions", "Enriched application versions", governance.get("versions_total"), "versions", "observed", "count versions on high-value applications", "neutral"),
            ("apptrust-trusted-releases", "Trusted releases", governance.get("trusted_releases"), "versions", "derived", "count(releaseStatus = TRUSTED_RELEASE)", "good"),
            ("apptrust-failed-promotions", "Failed or rejected promotions", sum((governance.get("promotion_status") or {}).get(key, 0) for key in ("FAILED", "REJECTED")), "promotions", "derived", "count(status in FAILED, REJECTED)", "bad"),
            ("apptrust-verified-evidence", "Verified evidence records", attestations.get("verified"), "records", "derived", "count(verified = true)", "good"),
            ("apptrust-unverified-evidence", "Unverified evidence records", attestations.get("unverified"), "records", "derived", "count(verified = false)", "bad"),
            ("apptrust-gate-certifications", "Gate certification evidence", attestations.get("gate_certifications"), "records", "derived", "count(predicate slug contains gate)", "good"),
        ]:
            if value is not None:
                item = metric(mid, label, value, unit, classification, evidence.get("source", "JFrog OneModel AppTrust GraphQL"), formula)
                item["risk_state"] = risk_state
                metrics.append(item)
        report["apptrust"] = {
            "status": status, "collected_at": evidence.get("collected_at"), "metrics": metrics,
            "inventory": inventory, "release_governance": governance, "evidence": attestations,
            "applications": evidence.get("applications") or [], "limitations": evidence.get("limitations") or [],
            "reason": evidence.get("reason"), "collection": evidence.get("collection") or {},
        }
        if status == "available":
            executive = report.setdefault("executive_signals", [])
            existing = {item.get("id") for item in executive}
            by_id = {item.get("id"): item for item in metrics}
            for metric_id in ("apptrust-critical-unowned", "apptrust-failed-promotions", "apptrust-unverified-evidence"):
                if metric_id not in existing and by_id.get(metric_id):
                    executive.append(by_id[metric_id])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
