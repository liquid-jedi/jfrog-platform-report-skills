#!/usr/bin/env python3
"""Enrich a classified JFrog Platform report with deterministic live module evidence."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def metric(mid, label, value, unit, classification, source, formula="API field"):
    return {"id": mid, "label": label, "value": value, "unit": unit,
            "classification": classification, "source": source, "formula": formula}


def pct(numerator, denominator):
    return round(numerator / denominator * 100, 1) if denominator else None


def deduplicate_violations(rows):
    """Collapse the same issue/component/artifact occurrence returned by multiple watches."""
    by_key = {}
    for row in rows:
        key = (str(row.get("issue_id") or ""), tuple(sorted(row.get("infected_components") or [])),
               tuple(sorted(row.get("impacted_artifacts") or [])))
        by_key[key] = row
    return list(by_key.values())


def build_access_governance(access_evidence):
    tokens = access_evidence.get("tokens") or {}
    oidc = access_evidence.get("oidc") or {}
    return {
        "status": "available",
        "collected_at": access_evidence.get("collected_at"),
        "metrics": [
            metric("access-active-tokens", "Active access tokens", tokens.get("listed_active"), "tokens", "observed", "Access token inventory"),
            metric("access-new-tokens-7d", "Active tokens issued in 7 days before collection", tokens.get("issued_last_7_days"), "tokens", "derived", "Access token inventory", "active token issued_at within 7 days before collected_at"),
            metric("access-new-tokens-30d", "Active tokens issued in 30 days before collection", tokens.get("issued_last_30_days"), "tokens", "derived", "Access token inventory", "active token issued_at within 30 days before collected_at"),
            metric("access-expiring-7d", "Tokens expiring within 7 days", tokens.get("expires_within_7_days"), "tokens", "derived", "Access token inventory", "0 < expiry - collected_at <= 7 days"),
            metric("access-expiring-30d", "Tokens expiring within 30 days", tokens.get("expires_within_30_days"), "tokens", "derived", "Access token inventory", "0 < expiry - collected_at <= 30 days"),
            metric("access-long-lived", "Tokens valid beyond 90 days", tokens.get("long_lived_over_90_days"), "tokens", "derived", "Access token inventory", "expiry - collected_at > 90 days"),
            metric("access-non-expiring", "Tokens without expiry", tokens.get("non_expiring"), "tokens", "derived", "Access token inventory", "expiry is null"),
            metric("access-never-used", "Tokens never used", tokens.get("never_used"), "tokens", "derived", "Access token inventory", "last_used is empty"),
            metric("oidc-providers", "OIDC providers", oidc.get("providers_total"), "providers", "observed", "Access OIDC inventory"),
            metric("oidc-mappings", "OIDC identity mappings", oidc.get("identity_mappings_total"), "mappings", "observed", "Access OIDC inventory"),
            metric("oidc-repository-patterns", "Repository claim patterns", oidc.get("repository_claim_patterns_total"), "patterns", "derived", "OIDC identity mappings", "count repository/project-path claims"),
        ],
        "token_posture": tokens,
        "rotation_queue": tokens.get("rotation_queue") or [],
        "providers_by_family": oidc.get("providers_by_family") or [],
        "repository_claim_patterns": oidc.get("repository_claim_patterns") or [],
        "note": "Token metrics are current-state posture as of collection time, not historical activity for a backdated report period. " + str(tokens.get("expired_note") or ""),
        "privacy_note": tokens.get("privacy_note"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--repositories", required=True, type=Path)
    parser.add_argument("--storage", required=True, type=Path)
    parser.add_argument("--watches", required=True, type=Path)
    parser.add_argument("--policies", required=True, type=Path)
    parser.add_argument("--indexed", required=True, type=Path)
    parser.add_argument("--violations", type=Path)
    parser.add_argument("--ai-catalog-evidence", type=Path,
                        help="Optional normalized, timestamped AI Catalog/AI gateway evidence")
    parser.add_argument("--runtime-evidence", type=Path,
                        help="Optional normalized, timestamped Runtime Security evidence")
    parser.add_argument("--access-governance-evidence", type=Path,
                        help="Optional redacted Access token and OIDC governance snapshot")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report = load(args.report)
    repositories = load(args.repositories)
    storage = load(args.storage)
    posture_collected_at = datetime.fromtimestamp(args.storage.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
    watches_payload = load(args.watches)
    policies_payload = load(args.policies)
    indexed_payload = load(args.indexed)
    raw_violations = load(args.violations) if args.violations else []
    ai_evidence = load(args.ai_catalog_evidence) if args.ai_catalog_evidence else None
    runtime_evidence = load(args.runtime_evidence) if args.runtime_evidence else None
    access_evidence = load(args.access_governance_evidence) if args.access_governance_evidence else None
    if isinstance(raw_violations, dict):
        raw_violations = raw_violations.get("violations") or []

    watches = watches_payload if isinstance(watches_payload, list) else watches_payload.get("watches", [])
    policies = policies_payload if isinstance(policies_payload, list) else policies_payload.get("result", [])
    indexed = indexed_payload.get("indexed_repos", [])
    non_indexed = indexed_payload.get("non_indexed_repos", [])
    storage_rows = [row for row in storage.get("repositoriesSummaryList", []) if row.get("repoKey") != "TOTAL"]
    storage_by_key = {row.get("repoKey"): row for row in storage_rows}

    repo_types = Counter(str(row.get("type") or "unknown").lower() for row in repositories)
    package_types = Counter(str(row.get("packageType") or "unknown") for row in repositories)
    empty_repositories = sum(int(row.get("filesCount") or 0) == 0 and row.get("repoType") != "VIRTUAL" for row in storage_rows)
    project_keys = {str(row.get("projectKey")) for row in storage_rows if row.get("projectKey")}
    binaries = storage.get("binariesSummary") or {}
    top_storage = sorted(storage_rows, key=lambda row: int(row.get("usedSpaceInBytes") or 0), reverse=True)[:10]

    report["platform"] = {
        "collected_at": posture_collected_at,
        "metrics": [
            metric("repositories", "Repositories", len(repositories), "count", "observed", "Artifactory inventory"),
            metric("local-repositories", "Local", repo_types.get("local", 0), "count", "observed", "Artifactory inventory"),
            metric("remote-repositories", "Remote", repo_types.get("remote", 0), "count", "observed", "Artifactory inventory"),
            metric("virtual-repositories", "Virtual", repo_types.get("virtual", 0), "count", "observed", "Artifactory inventory"),
            metric("federated-repositories", "Federated", repo_types.get("federated", 0), "count", "observed", "Artifactory inventory"),
        ],
        "package_types": package_types.most_common(15)
    }

    report["artifactory_detail"] = {
        "status": "available",
        "collected_at": posture_collected_at,
        "metrics": [
            metric("artifact-storage", "Artifact storage", binaries.get("artifactsSize"), "", "observed", "Artifactory storage summary"),
            metric("artifacts-count", "Artifacts", binaries.get("artifactsCount"), "count", "observed", "Artifactory storage summary"),
            metric("binary-dedup-optimization", "Binary deduplication", binaries.get("optimization"), "", "observed", "Artifactory storage summary"),
            metric("empty-repositories", "Storage-bearing repositories with no files", empty_repositories, "repositories", "derived", "Artifactory storage summary", "count(filesCount = 0 and repoType != virtual)"),
            metric("projects-with-storage", "Projects represented", len(project_keys), "projects", "derived", "Artifactory storage summary", "distinct(projectKey)"),
        ],
        "repository_types": sorted(repo_types.items(), key=lambda x: x[1], reverse=True),
        "package_types": package_types.most_common(15),
        "top_storage": [{"repository": row.get("repoKey"), "used_space": row.get("usedSpace"),
                         "files": row.get("filesCount"), "package_type": row.get("packageType"),
                         "project": row.get("projectKey") or "Unassigned"} for row in top_storage],
        "interpretation": [
            f"{empty_repositories:,} non-virtual repositories currently report no stored files; validate whether they are intentional scaffolding, unused caches or retirement candidates.",
            f"The current storage estate spans {len(project_keys):,} JFrog Projects.",
            "Cumulative traffic counters are retained as timestamped snapshots for future boundary comparisons and are not attributed to a backdated period."
        ]
    }

    active_watches = [row for row in watches if bool((row.get("general_data") or {}).get("active", row.get("active")))]
    covered_resources = []
    policy_names_in_watches = set()
    for watch in active_watches:
        resources = ((watch.get("project_resources") or {}).get("resources") or
                     (watch.get("watch_resources") or {}).get("resources") or [])
        covered_resources.extend((str(row.get("type") or "unknown"), str(row.get("name") or "")) for row in resources)
        policy_names_in_watches.update(str(row.get("name")) for row in watch.get("assigned_policies", []) if row.get("name"))
    uncovered_policies = [row.get("name") for row in policies if row.get("name") not in policy_names_in_watches]
    policy_types = Counter(str(row.get("type") or "unknown") for row in policies)
    severity_thresholds = Counter()
    fix_dependent = applicable_only = 0
    for policy in policies:
        for rule in policy.get("rules", []):
            criteria = rule.get("criteria") or {}
            if criteria.get("min_severity"):
                severity_thresholds[str(criteria["min_severity"]).lower()] += 1
            fix_dependent += bool(criteria.get("fix_version_dependant"))
            applicable_only += bool(criteria.get("applicable_cves_only"))

    indexed_total = len(indexed) + len(non_indexed)
    violations = deduplicate_violations(raw_violations)
    violation_severity = Counter(str(row.get("severity") or "Unknown") for row in violations)
    violation_types = Counter(str(row.get("type") or "Unknown") for row in violations)
    affected_artifacts = {path for row in violations for path in (row.get("impacted_artifacts") or [])}
    affected_components = {component for row in violations for component in (row.get("infected_components") or [])}
    affected_repositories = Counter()
    for path in affected_artifacts:
        parts = str(path).split("/")
        if len(parts) > 1:
            affected_repositories[parts[1] if parts[0] == "default" else parts[0]] += 1
    cves = Counter()
    applicability = Counter()
    for row in violations:
        row_cves = {
            str(detail.get("cve_id")) for detail in row.get("applicability") or []
            if detail.get("cve_id")
        }
        for detail in row.get("applicability_details") or []:
            result = str(detail.get("result") or "unknown")
            applicability[result] += 1
            vulnerability_id = str(detail.get("vulnerability_id") or "")
            if vulnerability_id.startswith("CVE-"):
                row_cves.add(vulnerability_id)
        for cve in row_cves:
            cves[cve] += 1
    for item in report.get("executive_signals", []):
        if item.get("id") == "xray-index-coverage":
            item["value"] = pct(len(indexed), indexed_total)
    prior_xray_period = [item for item in report.get("xray", {}).get("metrics", [])
                         if item.get("time_basis") == "period_activity"]
    report["xray"].update({
        "metrics": [
            metric("xray-indexed", "Indexed repositories", len(indexed), "count", "observed", "Xray binary manager"),
            metric("xray-non-indexed", "Non-indexed repositories", len(non_indexed), "count", "observed", "Xray binary manager"),
            metric("xray-index-coverage", "Repository indexing coverage", pct(len(indexed), indexed_total), "%", "derived", "Xray binary manager", "indexed / eligible × 100"),
            metric("xray-watches", "Watches", len(watches), "count", "observed", "Xray watches"),
            metric("xray-active-watches", "Active watches", len(active_watches), "count", "observed", "Xray watches"),
            metric("xray-active-watches-without-policies", "Active watches without policies", sum(
                not (row.get("assigned_policies") or []) for row in active_watches
            ), "watches", "derived", "Xray watches", "count(active=true and assigned_policies is empty)"),
            metric("xray-inactive-watches-without-policies", "Inactive watches without policies", sum(
                not bool((row.get("general_data") or {}).get("active", row.get("active")))
                and not (row.get("assigned_policies") or []) for row in watches
            ), "watches", "derived", "Xray watches", "count(active=false and assigned_policies is empty)"),
            metric("xray-covered-resources", "Resources named by active watches", len(set(covered_resources)), "resources", "derived", "Xray watches", "distinct(type, name) in active watches"),
            metric("xray-policies", "Policies", len(policies), "count", "observed", "Xray policies"),
            metric("xray-unassigned-policies", "Policies not assigned to an active watch", len(uncovered_policies), "policies", "derived", "Xray watches + policies", "policy names − active-watch assignments"),
        ] + ([
            metric("xray-new-findings", "New violation occurrences", len(violations), "findings", "derived", "Xray period violations", "distinct(issue, components, impacted artifacts)"),
            metric("xray-critical-findings", "Critical violations", violation_severity.get("Critical", 0), "findings", "derived", "Xray period violations", "severity = Critical"),
            metric("xray-unique-cves", "Unique CVEs", len(cves), "CVEs", "derived", "Xray applicability details", "distinct(vulnerability_id)"),
            metric("xray-affected-artifacts", "Affected artifact paths", len(affected_artifacts), "artifacts", "derived", "Xray period violations", "distinct(impacted_artifacts)"),
            metric("xray-applicable", "Applicable findings", applicability.get("applicable", 0), "findings", "derived", "Xray applicability details", "count(result = applicable)"),
            metric("xray-rescan-required", "Findings requiring rescan", applicability.get("rescan_required", 0), "findings", "derived", "Xray applicability details", "count(result = rescan_required)"),
        ] if violations else prior_xray_period),
        "policy_types": dict(policy_types),
        "indexed_ecosystems": Counter(str(row.get("pkg_type") or "unknown") for row in indexed).most_common(15),
        "severity_thresholds": severity_thresholds.most_common(),
        "violations_by_severity": violation_severity.most_common(),
        "violations_by_type": violation_types.most_common(),
        "top_cves": cves.most_common(10),
        "top_affected_repositories": affected_repositories.most_common(10),
        "governance": {"fix_version_dependent_rules": fix_dependent, "applicable_only_rules": applicable_only,
                       "unassigned_policy_names": uncovered_policies[:15]},
        "collection_note": (f"{report['meta']['period_label']} violation collection is available across active watches and deduplicated by issue, component and impacted artifact. Open backlog, resolved findings, remediation age and SLA require lifecycle snapshots and are not inferred from new-period findings." if violations else "Indexing, watches and policy posture are live. Period violations, remediation age, fixes and SLA metrics are omitted because the period violation collection is unavailable; no zero is substituted.")
    })

    jas_policies = []
    capabilities = Counter()
    jas_watch_names = set()
    for policy in policies:
        has_jas = False
        for rule in policy.get("rules", []):
            exposures = (rule.get("criteria") or {}).get("exposures")
            if isinstance(exposures, dict):
                has_jas = True
                for key, enabled in exposures.items():
                    if isinstance(enabled, bool) and enabled:
                        capabilities[key] += 1
        if has_jas:
            jas_policies.append(policy)
            jas_watch_names.update(policy.get("watches") or [])
    jas_resources = set()
    for watch in watches:
        name = str((watch.get("general_data") or {}).get("name") or watch.get("name") or "")
        if name in jas_watch_names:
            resources = ((watch.get("project_resources") or {}).get("resources") or [])
            jas_resources.update((str(row.get("type") or "unknown"), str(row.get("name") or "")) for row in resources)
    prior_jas_period = [item for item in report.get("jas", {}).get("metrics", [])
                        if item.get("time_basis") == "period_activity"]
    report["jas"] = {
        "status": "partial" if applicability else "available",
        "metrics": [
            metric("jas-policies", "Policies with JAS criteria", len(jas_policies), "policies", "observed", "Xray policy inventory"),
            metric("jas-watch-assignments", "Watches assigned JAS policies", len(jas_watch_names), "watches", "derived", "Xray policies", "distinct policy.watches"),
            metric("jas-configured-resources", "Resources under JAS-configured watches", len(jas_resources), "resources", "derived", "Xray watches + policies", "distinct resources on watches assigned JAS policy"),
            metric("jas-capabilities", "Configured JAS capability types", len(capabilities), "capabilities", "derived", "Xray policy criteria", "distinct enabled exposure criteria"),
        ] + ([
            metric("jas-applicable", "Confirmed applicable findings", applicability.get("applicable", 0), "component-findings", "derived", "Xray applicability details", "result = applicable"),
            metric("jas-not-applicable", "Confirmed not applicable", applicability.get("not_applicable", 0), "component-findings", "derived", "Xray applicability details", "result = not_applicable"),
            metric("jas-rescan-required", "Rescan required", applicability.get("rescan_required", 0), "component-findings", "derived", "Xray applicability details", "result = rescan_required"),
            metric("jas-not-scanned", "Not scanned for applicability", applicability.get("not_scanned", 0), "component-findings", "derived", "Xray applicability details", "result = not_scanned"),
        ] if applicability else prior_jas_period),
        "capabilities": capabilities.most_common(),
        "applicability": applicability.most_common(),
        "policy_names": [row.get("name") for row in jas_policies],
        "note": ("Live JAS policy configuration and Xray applicability-detail results are included. Secrets, SAST, IaC, scan-age and remediation outcomes still require dedicated findings/lifecycle sources." if applicability else "Live configuration coverage only. Period JAS scans, findings, exploitability, secrets, SAST, IaC and remediation outcomes require a supported findings source and are not inferred from policies.")
    }

    ai_types = {"AIEditorExtensions", "AgentPackages", "AgentPlugins", "HuggingFaceML", "MachineLearning", "NimModel", "Skills"}
    ai_repositories = [row for row in repositories if row.get("packageType") in ai_types]
    ai_keys = {row.get("key") for row in ai_repositories}
    ai_storage = [row for key, row in storage_by_key.items() if key in ai_keys or key.removesuffix("-cache") in ai_keys]
    active_ai = sum(int(row.get("filesCount") or 0) > 0 for row in ai_storage)
    ai_items = sum(int(row.get("itemsCount") or 0) for row in ai_storage)
    ai_bytes = sum(int(row.get("usedSpaceInBytes") or 0) for row in ai_storage)
    ai_projects = {str(row.get("projectKey")) for row in ai_storage if row.get("projectKey")}
    ai_repo_types = Counter(str(row.get("type") or "unknown").lower() for row in ai_repositories)
    top_ai = sorted(ai_storage, key=lambda row: int(row.get("usedSpaceInBytes") or 0), reverse=True)[:10]
    report["ai_catalog"] = {
        "status": "partial",
        "metrics": [
            metric("ai-repositories-total", "AI and agent repositories", len(ai_repositories), "repositories", "observed", "Artifactory inventory"),
            metric("ai-repositories-active", "AI repositories with stored files", active_ai, "repositories", "derived", "Artifactory storage summary", "count(filesCount > 0)"),
            metric("ai-stored-items", "Stored AI repository items", ai_items, "items", "derived", "Artifactory storage summary", "sum(itemsCount)"),
            metric("ai-storage-gib", "AI repository storage", round(ai_bytes / 2**30, 2), "GiB", "derived", "Artifactory storage summary", "sum(usedSpaceInBytes) / 2^30"),
            metric("ai-projects", "Projects with AI repository storage", len(ai_projects), "projects", "derived", "Artifactory storage summary", "distinct(projectKey)"),
        ],
        "repositories_by_type": Counter(str(row.get("packageType")) for row in ai_repositories).most_common(),
        "repositories_by_repository_type": ai_repo_types.most_common(),
        "top_storage": [{"repository": row.get("repoKey"), "used_space": row.get("usedSpace"),
                         "files": row.get("filesCount"), "package_type": row.get("packageType"),
                         "project": row.get("projectKey") or "Unassigned"} for row in top_ai],
        "note": "Live AI/agent repository footprint and storage evidence. Consumption, provenance, malicious findings, publisher verification and AI Catalog policy enforcement require dedicated supported sources."
    }

    # AI Catalog inventory is not interchangeable with Artifactory repository
    # footprint. Merge it only from a normalized, timestamped collector envelope.
    if ai_evidence:
        inventory = ai_evidence.get("inventory") or {}
        models = inventory.get("models") or {}
        mcps = inventory.get("mcp_servers") or {}
        skills = inventory.get("skills") or {}
        plugins = inventory.get("plugins") or {}
        shadow = ai_evidence.get("shadow_ai") or {}
        gateway = ai_evidence.get("gateway_activity") or {}
        observed = []
        for mid, label, value, unit, formula in [
            ("ai-detected-models", "Detected models", models.get("detected"), "models", "inventory.models.detected"),
            ("ai-allowed-models", "Allowed models", models.get("allowed"), "models", "inventory.models.allowed"),
            ("ai-allowed-mcp-servers", "Allowed MCP servers", mcps.get("allowed"), "servers", "inventory.mcp_servers.allowed"),
            ("ai-registered-skills", "Registered agent skills", skills.get("total"), "skills", "inventory.skills.total"),
            ("ai-visible-skills", "Skills visible in supplied registry capture", skills.get("visible_in_capture"), "skills", "inventory.skills.visible_in_capture"),
            ("ai-scanned-skills", "Security-scanned skills", skills.get("scanned"), "skills", "inventory.skills.scanned"),
            ("ai-not-malicious-skills", "Skills scanned as not malicious", (skills.get("security_counts") or {}).get("not_malicious"), "skills", "inventory.skills.security_counts.not_malicious"),
            ("ai-malicious-skills", "Skills classified malicious", (skills.get("security_counts") or {}).get("malicious"), "skills", "inventory.skills.security_counts.malicious"),
            ("ai-unscanned-skills", "Skills not scanned", (skills.get("security_counts") or {}).get("not_scanned"), "skills", "inventory.skills.security_counts.not_scanned"),
            ("ai-scanning-skills", "Skills still scanning", (skills.get("security_counts") or {}).get("scanning"), "skills", "inventory.skills.security_counts.scanning"),
            ("ai-suspicious-skills", "Skills classified suspicious", (skills.get("security_counts") or {}).get("suspicious"), "skills", "inventory.skills.security_counts.suspicious"),
            ("ai-vulnerable-skills", "Skills with vulnerable dependencies", (skills.get("vulnerability_counts") or {}).get("vulnerable"), "skills", "inventory.skills.vulnerability_counts.vulnerable"),
            ("ai-skills-without-project", "Skills not linked to a project", (skills.get("project_counts") or {}).get("unlinked"), "skills", "inventory.skills.project_counts.unlinked"),
            ("ai-mcp-security-observed", "MCP servers with captured security status", mcps.get("security_observed"), "servers", "inventory.mcp_servers.security_observed"),
            ("ai-mcp-not-malicious-observed", "Captured MCP statuses: not malicious", (mcps.get("security_counts") or {}).get("not_malicious"), "servers", "inventory.mcp_servers.security_counts.not_malicious"),
            ("ai-registered-plugins", "Registered agent plugins", plugins.get("total"), "plugins", "inventory.plugins.total"),
            ("ai-shadow-models", "Shadow AI models detected", shadow.get("detected"), "models", "shadow_ai.detected"),
            ("ai-shadow-managed", "Detected models under governance", shadow.get("managed"), "models", "shadow_ai.managed"),
            ("ai-shadow-unmanaged", "Detected models not yet governed", shadow.get("unmanaged"), "models", "shadow_ai.unmanaged"),
            ("ai-live-models", "Live models", gateway.get("live_models"), "models", "gateway_activity.live_models"),
            ("ai-gateway-requests", "AI gateway requests", gateway.get("requests"), "requests", "gateway_activity.requests"),
        ]:
            if value is not None:
                observed.append(metric(mid, label, value, unit, "observed", ai_evidence.get("source", "AI Catalog collector"), formula))
        report["current_ai_security"] = {
            "status": ai_evidence.get("status") or "available",
            "as_of": ai_evidence.get("security_collected_at") or ai_evidence.get("collected_at"),
            "metrics": observed,
            "inventory": inventory,
            "shadow_ai": shadow,
            "gateway_activity": gateway,
            "evidence_limitations": ai_evidence.get("limitations") or [],
            "collection_quality": ai_evidence.get("collection_quality") or {},
            "source": ai_evidence.get("source"),
            "note": "Current posture is shown as of its collection timestamp. It is not attributed to the historical report month and is excluded from month-over-month trends."
        }

    if access_evidence:
        report["access_governance"] = build_access_governance(access_evidence)

    if runtime_evidence:
        prioritization = runtime_evidence.get("vulnerability_prioritization") or {}
        highlights = runtime_evidence.get("live_assessment") or {}
        runtime_metrics = []
        for mid, label, value, unit, formula in [
            ("runtime-critical-high", "Critical and high findings", prioritization.get("critical_high"), "findings", "vulnerability_prioritization.critical_high"),
            ("runtime-applicable", "Applicable in running images", prioritization.get("applicable"), "findings", "vulnerability_prioritization.applicable"),
            ("runtime-fix-available", "Applicable findings with a fix", prioritization.get("with_fix"), "findings", "vulnerability_prioritization.with_fix"),
            ("runtime-validated", "Validated at runtime", prioritization.get("validated"), "findings", "vulnerability_prioritization.validated"),
            ("runtime-images", "Running images assessed", highlights.get("images"), "images", "live_assessment.images"),
            ("runtime-malicious-packages", "Malicious packages in running images", highlights.get("malicious_packages"), "findings", "live_assessment.malicious_packages"),
            ("runtime-critical-applicable", "Critical and applicable risks", highlights.get("critical_applicable"), "findings", "live_assessment.critical_applicable"),
            ("runtime-integrity-violations", "Runtime integrity violations", highlights.get("integrity_violations"), "violations", "live_assessment.integrity_violations"),
        ]:
            if value is not None:
                runtime_metrics.append(metric(mid, label, value, unit, "observed", runtime_evidence.get("source", "Runtime Security collector"), formula))
        report["runtime"] = {
            "status": "available" if runtime_metrics else "unavailable",
            "collected_at": runtime_evidence.get("collected_at"),
            "metrics": runtime_metrics,
            "prioritization": prioritization,
            "live_assessment": highlights,
            "running_image_trend": runtime_evidence.get("running_image_trend") or [],
            "note": "Runtime narrows build-time findings to risks observed in production. It is point-in-time unless the evidence envelope declares a bounded activity period.",
        }

    curation_metrics = {item["id"]: item for item in report.get("curation", {}).get("metrics", [])}
    curation_values = {item["id"]: item.get("value") for item in report.get("curation", {}).get("metrics", [])}
    blocked_count = int(curation_values.get("curation-blocked") or 0)
    approved_count = int(curation_values.get("curation-approved") or 0)
    active_users = int(curation_values.get("curation-users") or 0)
    unique_blocked = int(curation_values.get("unique-blocked-packages") or 0)
    report["curation"]["metrics"] = [item for item in report["curation"]["metrics"]
                                         if item.get("id") != "curation-approval-block-ratio"]
    extra_curation = [
        metric("curation-repeat-block-attempts", "Repeat blocked attempts", max(0, blocked_count - unique_blocked), "requests", "derived", "Curation audit", "blocked requests − unique blocked package versions"),
        metric("curation-blocks-per-user", "Blocked requests per active identity", round(blocked_count / active_users, 2) if active_users else None, "requests/identity", "derived", "Curation audit", "blocked requests / active requester identities"),
    ]
    existing_curation_ids = {item.get("id") for item in report.get("curation", {}).get("metrics", [])}
    report["curation"]["metrics"].extend(item for item in extra_curation if item["id"] not in existing_curation_ids)
    report["curation"]["interpretation"] = [
        f"{unique_blocked:,} unique package versions were stopped across {blocked_count:,} blocked requests, including {max(0, blocked_count - unique_blocked):,} repeat attempts.",
        f"Curation evaluated {approved_count + blocked_count:,} requests from {active_users:,} requester identities during the period.",
        "Coverage movement and year-to-date adoption require prior snapshots; requester identities are not treated as licensed developers."
    ]
    executive = [item for item in report.get("executive_signals", []) if item.get("id") not in {"xray-critical-period", "jas-applicable-period", "artifact-storage"}]
    if violations:
        executive.append(metric("xray-critical-period", "Critical Xray intake", violation_severity.get("Critical", 0), "findings", "derived", "Xray period violations", "distinct critical issue/resource occurrences"))
    if applicability:
        executive.append(metric("jas-applicable-period", "Confirmed applicable findings", applicability.get("applicable", 0), "component-findings", "derived", "Xray applicability details", "result = applicable"))
    report["executive_signals"] = executive[:8]
    report["executive_summary"] = {
        "capabilities": [
            {"name": "Artifactory", "status": "available", "detail": "Estate and storage posture"},
            {"name": "Curation", "status": report.get("curation", {}).get("status", "unavailable"), "detail": "Period prevention and governance"},
            {"name": "Xray", "status": "partial", "detail": f"Coverage, governance and {report['meta']['period_label']} violations; lifecycle backlog unavailable" if violations else "Coverage and governance; period findings unavailable"},
            {"name": "AI security", "status": "partial", "detail": "Repository footprint; security findings unavailable"},
            {"name": "JAS", "status": "partial", "detail": "Configuration and applicability results; scanner-specific findings unavailable" if applicability else "Configuration coverage; findings unavailable"},
            *([{"name": "Runtime", "status": report.get("runtime", {}).get("status", "unavailable"), "detail": "Production image prioritization and live assessment"}] if report.get("runtime") else []),
        ],
        "risks": [
            ({"title": "Critical Xray intake", "detail": f"{violation_severity.get('Critical', 0):,} deduplicated critical issue/resource occurrences were created in the period; this is new intake, not open backlog.", "classification": "derived"} if violations else {"title": "Xray period risk trend unavailable", "detail": "Critical exposure, remediation backlog and age cannot be concluded without period violations.", "classification": "unavailable"}),
            {"title": "Empty repository footprint", "detail": f"{empty_repositories:,} repositories report no stored files and should be validated for ownership or retirement.", "classification": "derived"},
            {"title": "Aged Curation waivers", "detail": f"The oldest pending waiver is {report.get('curation', {}).get('waivers', {}).get('pending_aging', {}).get('oldest_pending_days', 'unavailable')} days old.", "classification": "derived"},
        ],
        "outcomes": [
            {"title": "Packages stopped before consumption", "detail": f"{curation_metrics.get('unique-blocked-packages', {}).get('value', 'Unavailable')} unique package versions were blocked in the period.", "classification": "derived"},
            {"title": "Repository indexing coverage", "detail": f"{pct(len(indexed), indexed_total)}% of eligible repositories returned by Xray are indexed.", "classification": "derived"},
            {"title": "AI supply-chain footprint identified", "detail": f"{len(ai_repositories):,} AI/model/agent repositories are now isolated as a governed subset of the Artifactory estate.", "classification": "observed"},
        ],
        "actions": [
            {"title": "Review waiver backlog", "detail": "Assign owners and expiry decisions to pending Curation waivers older than 90 days."},
            {"title": "Close Xray coverage gaps", "detail": f"Review {len(non_indexed):,} non-indexed repositories and policies not attached to active watches."},
            {"title": "Validate empty repositories", "detail": "Confirm whether empty repositories are intentional, newly provisioned or candidates for retirement."},
        ]
    }

    prior_limitations = [item for item in report.get("limitations", []) if not (violations and ("Period Xray violation collection failed" in item or "Xray and JAS period finding" in item))]
    report["limitations"] = list(dict.fromkeys(prior_limitations + [
        "Artifactory download/upload trends and reliability are unavailable without an event or observability source.",
        "Xray open backlog, resolved findings, remediation age and SLA require lifecycle snapshots; period-created violations alone cannot establish them.",
        "AI repository inventory and storage do not establish active consumption, provenance or security posture."
    ]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
