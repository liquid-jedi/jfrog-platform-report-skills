#!/usr/bin/env python3
"""Create a fully synthetic schema 0.3 report for public examples.

The values and names in this file are fictional. The generator never reads a live
report, customer archive, JFrog instance, or environment variable.
"""

import argparse
import json
from pathlib import Path


def metric(metric_id, label, value, unit, classification="observed", source="Synthetic demonstration fixture", formula="Direct synthetic fixture value", risk_state="neutral", meaning=None, why=None):
    item = {
        "id": metric_id,
        "label": label,
        "value": value,
        "unit": unit,
        "classification": classification,
        "source": source,
        "formula": formula,
        "risk_state": risk_state,
    }
    if meaning:
        item["meaning"] = meaning
    if why:
        item["why_it_matters"] = why
    return item


def asset(name, version, security, vulnerability, issues, project, governance, repository):
    return {
        "name": name,
        "version": version,
        "security_status": security,
        "vulnerability_status": vulnerability,
        "vulnerability_count": issues,
        "project_key": project,
        "project_status": "Linked" if project not in {"Not linked", "Unknown"} else project,
        "governance": governance,
        "repository": repository,
    }


def inventory(assets, counts, vulnerable=0, clean=0, unknown=0, linked=0, unlinked=0, project_unknown=0):
    return {
        "visible_assets": assets,
        "security_counts": counts,
        "vulnerability_counts": {
            "vulnerable": vulnerable,
            "no_known_vulnerabilities": clean,
            "no_xray_data": unknown,
        },
        "project_counts": {"linked": linked, "unlinked": unlinked, "unknown": project_unknown},
    }


def build():
    platform_metrics = [
        metric("repositories", "Repositories", 246, "repositories"),
        metric("local-repositories", "Local repositories", 92, "repositories"),
        metric("remote-repositories", "Remote repositories", 71, "repositories"),
        metric("virtual-repositories", "Virtual repositories", 83, "repositories"),
        metric("project-linked-repositories", "Repositories linked to projects", 219, "repositories", "derived", formula="Repositories with a project key"),
    ]
    art_metrics = [
        metric("artifact-storage", "Artifact storage", 18.7, "TiB", "derived", formula="total bytes / 2^40"),
        metric("artifacts-count", "Artifacts stored", 9240000, "artifacts"),
        metric("period-downloads", "Downloads during report period", 1842900, "requests", "derived", formula="period-end counter - period-start counter"),
        metric("period-uploads", "Uploads during report period", 128400, "requests", "derived", formula="period-end counter - period-start counter"),
        metric("binary-cache-hit-rate", "Binary provider cache hit rate", 87.4, "%", "derived", formula="cache hits / cache requests x 100"),
    ]
    curation_metrics = [
        metric("curation-decisions", "Requests evaluated", 68420, "requests"),
        metric("curation-retained-window", "Retained audit decisions", 68420, "decisions"),
        metric("curation-blocked", "Blocked requests", 187, "requests", risk_state="bad"),
        metric("curation-block-rate", "Block rate", 0.27, "%", "derived", formula="blocked / evaluated x 100"),
        metric("curation-users", "Curation unique users", 38, "identities"),
        metric("curation-repos", "Repositories using Curation", 54, "repositories"),
        metric("unique-blocked-packages", "Unique blocked package versions", 63, "versions", "derived", risk_state="bad"),
    ]
    xray_metrics = [
        metric("xray-new-findings", "New findings", 2840, "findings", risk_state="bad"),
        metric("xray-critical-findings", "Critical findings", 126, "findings", risk_state="bad"),
        metric("xray-high-findings", "High findings", 719, "findings", risk_state="bad"),
        metric("xray-unique-cves", "Unique CVEs", 463, "CVEs", "derived"),
        metric("xray-indexed-repositories", "Indexed repositories", 224, "repositories"),
        metric("xray-non-indexed", "Repositories not indexed", 22, "repositories", "derived", risk_state="warning"),
    ]
    ai_repo_metrics = [
        metric("ai-repositories", "AI and agent repositories", 21, "repositories"),
        metric("ai-repository-storage", "AI repository storage", 2.8, "TiB", "derived"),
        metric("ai-repository-artifacts", "AI repository artifacts", 18420, "artifacts"),
    ]
    access_metrics = [
        metric("access-active-tokens", "Active tokens", 164, "tokens"),
        metric("access-expiring-7d", "Tokens expiring within 7 days", 4, "tokens", risk_state="bad"),
        metric("access-expiring-30d", "Tokens expiring within 30 days", 17, "tokens", risk_state="warning"),
        metric("access-non-expiring", "Non-expiring tokens", 9, "tokens", risk_state="bad"),
        metric("oidc-providers", "OIDC providers", 7, "providers"),
    ]
    jas_metrics = [
        metric("jas-applicable", "Applicable vulnerabilities", 214, "findings", risk_state="bad"),
        metric("jas-fix-available", "Applicable with a fix", 183, "findings", "derived"),
        metric("jas-secrets", "Open secrets findings", 11, "findings", risk_state="bad"),
        metric("jas-iac", "Open IaC findings", 37, "findings", risk_state="warning"),
    ]
    runtime_metrics = [
        metric("runtime-critical-high", "Critical and high", 142, "findings", risk_state="bad"),
        metric("runtime-critical-applicable", "Applicable in runtime", 34, "findings", risk_state="bad"),
        metric("runtime-with-fix", "With a fix version", 29, "findings", "derived"),
        metric("runtime-validated", "Validated in runtime", 31, "findings"),
        metric("runtime-images", "Running images", 418, "images"),
        metric("runtime-malicious-packages", "Malicious packages", 1, "packages", risk_state="bad"),
        metric("runtime-integrity-violations", "Integrity violations", 2, "violations", risk_state="bad"),
    ]

    mcp_assets = [
        asset("issue-triage-mcp", "2.4.1", "Not malicious", "No known vulnerabilities", 0, "PLAT", "Allowed", "agent-tools-local"),
        asset("release-notes-mcp", "1.8.0", "Suspicious", "No known vulnerabilities", 0, "Not linked", "Allowed", "agent-tools-local"),
        asset("legacy-query-mcp", "0.9.3", "Malicious", "Vulnerable", 3, "LABS", "Blocked", "agent-tools-quarantine-local"),
        asset("remote-docs-mcp", "remote", "N/A", "No Xray data", None, "Unknown", "Allowed", "Public remote"),
    ]
    skill_assets = [
        asset("release-health-check", "1.4.0", "Not malicious", "No known vulnerabilities", 0, "REL", "Allowed", "agent-skills-local"),
        asset("dependency-upgrade-helper", "2.1.2", "Suspicious", "Vulnerable", 2, "PLAT", "Blocked", "agent-skills-local"),
        asset("service-log-summarizer", "1.0.6", "Vulnerable", "Vulnerable", 4, "Not linked", "Blocked", "agent-skills-local"),
        asset("incident-brief", "0.7.1", "Suspicious", "No known vulnerabilities", 0, "Not linked", "Allowed", "agent-skills-local"),
        asset("runbook-search", "1.2.0", "Not scanned", "No Xray data", None, "Unknown", "Review", "agent-skills-local"),
    ]
    plugin_assets = [
        asset("deployment-review-plugin", "3.0.0", "Not malicious", "No known vulnerabilities", 0, "REL", "Allowed", "agent-plugins-local"),
        asset("legacy-shell-plugin", "1.1.0", "Suspicious", "Vulnerable", 1, "Not linked", "Review", "agent-plugins-local"),
    ]
    model_assets = [
        asset("acme/embedding-small", "1", "Not malicious", "No known vulnerabilities", 0, "AI", "Managed", "ai-models-local"),
        asset("acme/code-assistant", "7b", "Not malicious", "No known vulnerabilities", 0, "AI", "Managed", "ai-models-local"),
        asset("external/research-model", "remote", "N/A", "No Xray data", None, "Not linked", "Unmanaged", "External"),
    ]

    weeks = [
        {"period_key": "2026-10-11", "label": "Oct 5-11"},
        {"period_key": "2026-10-18", "label": "Oct 12-18"},
        {"period_key": "2026-10-25", "label": "Oct 19-25"},
        {"period_key": "2026-11-01", "label": "Oct 26-31"},
    ]
    def series(series_id, label, values, polarity):
        return {
            "id": series_id,
            "label": label,
            "polarity": polarity,
            "latest_change_percent": round((values[-1] - values[-2]) / values[-2] * 100, 1),
            "points": [{**week, "value": value} for week, value in zip(weeks, values)],
        }

    return {
        "schema_version": "0.3",
        "meta": {
            "title": "JFrog Platform Value & Risk Report",
            "server_id": "northstar-demo",
            "data_source": "Synthetic demonstration fixture",
            "report_type": "Weekly",
            "period_label": "October 26-31, 2026",
            "period_range": "October 26-31, 2026",
            "date_from": "2026-10-26",
            "date_to": "2026-10-31",
            "period_start": "2026-10-26T00:00:00Z",
            "period_end": "2026-10-31T23:59:59Z",
            "generated": "2026-11-01T08:00:00Z",
            "fallback_used": False,
            "persona": "Platform, security and technology leadership",
            "report_purpose": "Weekly operating review of platform adoption, preventive controls, software supply chain risk and prioritized action.",
        },
        "evidence_revalidation": {"message": "Synthetic demonstration data. No customer system or live JFrog instance was queried."},
        "executive_signals": [
            metric("xray-critical-findings", "Critical findings", 126, "findings", risk_state="bad"),
            metric("curation-blocked", "Risky requests prevented", 187, "requests", risk_state="good"),
            metric("binary-cache-hit-rate", "Cache hit rate", 87.4, "%", "derived", risk_state="good"),
            metric("exec-ai-risk", "Risky AI assets", 7, "assets", "derived", risk_state="bad", meaning="AI asset records that are malicious, suspicious, vulnerable, unscanned or not linked to a project.", why="These records need review before the assets can be treated as governed and production-ready."),
        ],
        "executive_summary": {
            "risks": [
                {"title": "Critical vulnerability intake remains elevated", "detail": "126 critical findings entered the estate this week, with the highest concentration in two container repositories."},
                {"title": "AI asset governance has visible gaps", "detail": "Seven MCP, skill, plugin or model records are suspicious, vulnerable, malicious, unscanned or not linked to a project."},
            ],
            "outcomes": [
                {"title": "Curation stopped risky dependency demand", "detail": "187 requests were blocked before the packages entered development workflows."},
                {"title": "Artifact delivery remained cache efficient", "detail": "The binary provider cache served 87.4% of eligible requests during the period."},
            ],
            "actions": [
                {"title": "Assign owners to critical findings with fixes", "detail": "Start with the two repositories responsible for 61% of critical intake."},
                {"title": "Quarantine and review risky AI assets", "detail": "Remove the malicious MCP server, review suspicious skills and link approved assets to accountable projects."},
            ],
        },
        "platform": {"metrics": platform_metrics, "package_types": [["Docker", 68], ["Maven", 61], ["npm", 47], ["PyPI", 31], ["Other", 39]]},
        "artifactory_detail": {
            "status": "available",
            "collected_at": "2026-11-01T08:00:00Z",
            "metrics": art_metrics,
            "repository_types": [["Local", 92], ["Remote", 71], ["Virtual", 83]],
            "package_types": [["Docker", 68], ["Maven", 61], ["npm", 47], ["PyPI", 31], ["Other", 39]],
            "top_storage": [
                {"repository": "payments-containers-local", "used_space": "3.4 TiB", "files": 184320, "package_type": "Docker", "project": "PAY"},
                {"repository": "shared-maven-release-local", "used_space": "2.1 TiB", "files": 742810, "package_type": "Maven", "project": "PLAT"},
                {"repository": "analytics-python-local", "used_space": "1.2 TiB", "files": 263104, "package_type": "PyPI", "project": "DATA"},
            ],
            "traffic_evidence": {
                "collected_at": "2026-11-01T08:00:00Z",
                "counters": {"download_requests_total": 98432000, "upload_requests_total": 6214800},
                "period_delta": {"download_requests_delta": 1842900, "upload_requests_delta": 128400, "cache_fs_hit_rate": "87.4%"},
            },
            "interpretation": ["Artifact traffic increased 5.8% while cache efficiency remained above the 85% operating threshold.", "The three largest repositories account for 35.8% of stored bytes and should have explicit retention ownership."],
        },
        "curation": {
            "status": "available", "coverage_label": "Complete period collection",
            "collection": {"rows_fetched": 68420}, "metrics": curation_metrics,
            "events_by_package_type": [["npm", 28410], ["Maven", 17320], ["PyPI", 14510], ["Go", 8180]],
            "top_block_reasons": [["Malicious package", 72], ["Critical CVE", 51], ["License policy", 39], ["Immature version", 25]],
            "top_blocked": [
                {"package": "sample-left-pad", "ecosystem": "npm", "count": 34},
                {"package": "demo-logging-core", "ecosystem": "Maven", "count": 21},
                {"package": "example-parser", "ecosystem": "PyPI", "count": 17},
            ],
            "top_users": [
                {"user": "developer-07", "requests": 8420, "blocked": 21, "repos": 7, "packages": 1260},
                {"user": "build-service-03", "requests": 7180, "blocked": 9, "repos": 11, "packages": 980},
                {"user": "developer-14", "requests": 6240, "blocked": 17, "repos": 5, "packages": 846},
            ],
            "top_policies": [["Block malicious packages", 72], ["Block critical CVEs", 51], ["Restrict licenses", 39]],
            "show_configuration": False,
            "interpretation": ["Curation evaluated 68,420 requests from 38 identities and blocked 187 risky requests.", "Repeat demand is concentrated in three packages, which indicates where developer guidance can reduce friction."],
        },
        "xray": {
            "status": "available", "metrics": xray_metrics,
            "policy_types": {"Security": 31, "License": 8, "Operational": 5},
            "indexed_ecosystems": [["Docker", 64], ["Maven", 58], ["npm", 44], ["PyPI", 28], ["Other", 30]],
            "violations_by_severity": [["Critical", 126], ["High", 719], ["Medium", 1284], ["Low", 711]],
            "violations_by_type": [["Security", 2513], ["License", 327]],
            "top_cves": [["CVE-2026-41001", 84], ["CVE-2026-32914", 61], ["CVE-2026-20877", 49]],
            "top_affected_repositories": [["payments-containers-local", 392], ["shared-maven-release-local", 271], ["analytics-python-local", 184]],
            "collection_note": "Synthetic period findings are deduplicated by issue, infected component and impacted artifact.",
        },
        "ai_catalog": {
            "status": "available", "metrics": ai_repo_metrics,
            "repositories_by_type": [["Models", 8], ["MCP servers", 4], ["Skills", 6], ["Plugins", 3]],
            "repositories_by_repository_type": [["Local", 13], ["Remote", 3], ["Virtual", 5]],
            "top_storage": [],
            "note": "Synthetic registry inventory demonstrates asset security, scan state, governance and project attribution.",
        },
        "jas": {
            "status": "available", "metrics": jas_metrics,
            "capabilities": [["Contextual analysis", 18], ["Secrets", 7], ["IaC", 6], ["SAST", 5]],
            "applicability": [["Applicable", 214], ["Not applicable", 1630], ["Rescan required", 87], ["Not scanned", 42]],
            "policy_names": ["Production contextual risk", "Secrets in release artifacts", "Infrastructure policy"],
            "note": "JAS values are synthetic and are not added to Xray occurrence totals.",
        },
        "runtime": {
            "status": "available", "metrics": runtime_metrics,
            "running_image_trend": [
                {"date": "2026-10-27", "running_image_tags": 392, "critical_high_applicable": 38},
                {"date": "2026-10-29", "running_image_tags": 407, "critical_high_applicable": 36},
                {"date": "2026-10-31", "running_image_tags": 418, "critical_high_applicable": 34},
            ],
            "note": "Synthetic production context for sample-report demonstration only.",
        },
        "economic_model": {
            "status": "benchmark",
            "disclaimer": "External Forrester TEI composite benchmark. This is not a customer result or customer projection.",
            "summary": {"benefits_pv_usd": 9970000, "costs_pv_usd": 3200000, "npv_usd": 6770000, "roi_percent": 211, "payback": "Under 6 months"},
            "benefit_categories": {"developer_productivity": 4100000, "security_risk_reduction": 3020000, "platform_efficiency": 2850000},
            "composite": {"developers": "2,500", "applications": "450", "analysis_period": "Three years"},
            "methodology_inputs": {"developer_time": {"value_per_unit_usd": 78, "risk_adjustment": "15%", "source_formula": "Composite benchmark"}},
            "profile": {"status": "not_configured"},
            "scenarios": {}, "assumptions": [], "unavailable_models": [],
        },
        "current_ai_security": {
            "status": "available", "as_of": "2026-11-01T08:00:00Z",
            "metrics": [
                metric("ai-malicious-assets", "Malicious AI assets", 1, "assets", "derived", risk_state="bad"),
                metric("ai-suspicious-assets", "Suspicious AI assets", 4, "assets", "derived", risk_state="bad"),
                metric("ai-vulnerable-assets", "Vulnerable AI assets", 3, "assets", "derived", risk_state="bad"),
                metric("ai-unlinked-assets", "AI assets not linked to a project", 5, "assets", "derived", risk_state="warning"),
            ],
            "inventory": {
                "mcp_servers": inventory(mcp_assets, {"malicious": 1, "suspicious": 1, "vulnerable": 0, "not_malicious": 1, "scanning": 0, "not_scanned": 0, "n_a": 1}, 1, 2, 1, 2, 1, 1),
                "skills": inventory(skill_assets, {"malicious": 0, "suspicious": 2, "vulnerable": 1, "not_malicious": 1, "scanning": 0, "not_scanned": 1, "n_a": 0}, 2, 2, 1, 2, 2, 1),
                "plugins": inventory(plugin_assets, {"malicious": 0, "suspicious": 1, "vulnerable": 0, "not_malicious": 1, "scanning": 0, "not_scanned": 0, "n_a": 0}, 1, 1, 0, 1, 1, 0),
                "models": inventory(model_assets, {"malicious": 0, "suspicious": 0, "vulnerable": 0, "not_malicious": 2, "scanning": 0, "not_scanned": 0, "n_a": 1}, 0, 2, 1, 2, 1, 0),
            },
            "shadow_ai": {"visible_assets": [{"name": "external/research-model", "management_status": "Unmanaged"}]},
            "gateway_activity": {},
            "evidence_limitations": ["Registry presence proves governance inventory, not active use."],
            "collection_quality": "complete synthetic fixture", "source": "Synthetic demonstration fixture",
            "note": "Security and project attribution are shown separately for MCP servers, skills, plugins and models.",
        },
        "access_governance": {
            "status": "available", "collected_at": "2026-11-01T08:00:00Z", "metrics": access_metrics,
            "token_posture": {"expires_within_7_days": 4, "expires_within_30_days": 17, "non_expiring": 9, "never_used": 6},
            "rotation_queue": [
                {"reference": "token-ref-014", "owner": "platform-ci", "description": "Release automation", "expires_at": "2026-11-04", "days_remaining": 3, "last_used": "2026-10-31"},
                {"reference": "token-ref-027", "owner": "data-build", "description": "Analytics builds", "expires_at": "2026-11-06", "days_remaining": 5, "last_used": "2026-10-30"},
            ],
            "providers_by_family": [["GitHub", 4], ["GitLab", 2], ["Other", 1]],
            "repository_claim_patterns": [
                {"provider_family": "GitHub", "provider": "github-main", "mapping": "payments-ci", "claim": "repository", "pattern": "example-corp/payments-*"},
                {"provider_family": "GitLab", "provider": "gitlab-main", "mapping": "data-ci", "claim": "project_path", "pattern": "example-corp/data/*"},
            ],
            "note": "Expired and revoked token history requires prior snapshots and is unavailable in this synthetic baseline.",
            "privacy_note": "Safe references are synthetic. No token ID, secret or scope is included.",
        },
        "weekly_trend": {
            "status": "available", "month": "2026-10", "month_label": "October 2026", "timezone": "UTC", "weeks": weeks,
            "series": [
                series("curation-decisions", "Curation decisions", [58200, 61140, 64790, 68420], "higher_is_better"),
                series("curation-blocked", "Blocked requests", [251, 224, 205, 187], "lower_is_better"),
                series("xray-critical-findings", "Critical findings", [184, 167, 149, 126], "lower_is_better"),
                series("traffic-downloads", "Artifact downloads", [1612000, 1698000, 1741000, 1842900], "contextual"),
            ],
            "interpretation": "Synthetic weekly values demonstrate direction, polarity and comparable calendar-month trend analysis.",
        },
        "limitations": ["All names and values are synthetic.", "No customer environment, identity, repository or JFrog instance was queried."],
        "availability_notes": [],
        "provenance": {"source": "synthetic", "server_id": "northstar-demo", "collector": "generate_sample_data.py", "collection_started_at": "2026-11-01T08:00:00Z", "prior_report_input_used": False, "raw_manifest": "not-applicable"},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
