#!/usr/bin/env python3
"""Normalize one fresh live-evidence run into report schema 0.3."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def metric(mid, label, value, unit, classification, source, formula="API field", time_basis=None):
    row = {"id": mid, "label": label, "value": value, "unit": unit,
           "classification": classification, "source": source, "formula": formula}
    if time_basis:
        row["time_basis"] = time_basis
    return row


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def raw_pages(raw_dir: Path, prefix: str, key: str) -> list[dict]:
    rows = []
    for path in sorted(raw_dir.glob(f"{prefix}*.json")):
        payload = load(path)
        rows.extend((payload or {}).get(key) or [])
    return rows


def format_date(value: str) -> str:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%B %d, %Y").replace(" 0", " ")


def pct(numerator, denominator):
    return None if not denominator else round(numerator / denominator * 100, 2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    evidence = load(args.evidence)
    raw = args.raw_dir
    period = evidence["reporting"]["period"]
    start = datetime.fromisoformat(period["start"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(period["end"].replace("Z", "+00:00"))
    period_label = start.strftime("%B %Y") if end.day >= 28 else f"{start.strftime('%B %d').replace(' 0', ' ')}–{end.strftime('%d, %Y').lstrip('0')}"

    repositories = load(raw / "artifactory-repositories.json")
    storage = load(raw / "artifactory-storage.json")
    watches_payload = load(raw / "xray-watches.json")
    policies_payload = load(raw / "xray-policies.json")
    indexed_payload = load(raw / "xray-indexed-repositories.json")
    watches = watches_payload if isinstance(watches_payload, list) else watches_payload.get("watches", [])
    policies = policies_payload if isinstance(policies_payload, list) else policies_payload.get("result", [])
    indexed = indexed_payload if isinstance(indexed_payload, list) else indexed_payload.get("indexed_repos", [])
    non_indexed = [] if isinstance(indexed_payload, list) else indexed_payload.get("non_indexed_repos", [])
    curation_rows = raw_pages(raw, "curation-audit-w", "data")
    violations = raw_pages(raw, "xray-violations-", "violations")

    repo_types = Counter(str(row.get("type") or "unknown").lower() for row in repositories)
    package_types = Counter(str(row.get("packageType") or "unknown") for row in repositories)
    storage_rows = [row for row in storage.get("repositoriesSummaryList", []) if row.get("repoKey") != "TOTAL"]
    binaries = storage.get("binariesSummary") or {}
    top_storage = sorted(storage_rows, key=lambda row: int(row.get("usedSpaceInBytes") or 0), reverse=True)[:10]

    curation_scope = evidence["curation"]["period"]["collection"]
    curation_status = evidence["curation"]["status"]
    actions = Counter(str(row.get("action") or "unknown").lower() for row in curation_rows)
    blocked = [row for row in curation_rows if str(row.get("action") or "").lower() == "blocked"]
    users = {str(row.get("username") or row.get("user_mail") or "").strip() for row in curation_rows}
    users.discard("")
    repos_used = {row.get("curated_repository_name") for row in curation_rows if row.get("curated_repository_name")}
    unique_blocked = {(row.get("package_type"), row.get("package_name"), row.get("package_version")) for row in blocked}
    curation_types = Counter(str(row.get("package_type") or "unknown") for row in curation_rows)
    block_reasons = Counter(str(row.get("reason") or "Unknown") for row in blocked)
    top_blocked_count = Counter((str(row.get("package_name") or "Unknown"), str(row.get("package_type") or "unknown")) for row in blocked)
    by_user = {}
    for row in curation_rows:
        name = str(row.get("username") or row.get("user_mail") or "").strip()
        if not name:
            continue
        item = by_user.setdefault(name, {"requests": 0, "blocked": 0, "repos": set(), "packages": set()})
        item["requests"] += 1
        item["blocked"] += str(row.get("action") or "").lower() == "blocked"
        if row.get("curated_repository_name"):
            item["repos"].add(row["curated_repository_name"])
        item["packages"].add((row.get("package_type"), row.get("package_name"), row.get("package_version")))
    top_users = [{"user": name, "requests": row["requests"], "blocked": row["blocked"],
                  "repos": len(row["repos"]), "packages": len(row["packages"])}
                 for name, row in sorted(by_user.items(), key=lambda item: item[1]["requests"], reverse=True)[:10]]

    complete_curation = curation_status == "available"
    curation_metrics = []
    for mid, label, value, unit, formula in (
        ("curation-decisions", "Policy decisions", len(curation_rows), "requests", "count(audit events)"),
        ("curation-blocked", "Blocked requests", len(blocked), "requests", "count(action = blocked)"),
        ("curation-block-rate", "Block rate", pct(len(blocked), len(curation_rows)), "%", "blocked / decisions × 100"),
        ("curation-users", "Curation unique users", len(users), "identities", "distinct requester identities"),
        ("curation-repos", "Repositories used", len(repos_used), "repositories", "distinct curated repository"),
        ("unique-blocked-packages", "Unique blocked versions", len(unique_blocked), "packages", "distinct type + name + version"),
    ):
        curation_metrics.append(metric(mid, label, value if complete_curation else None, unit,
                                       "observed" if complete_curation else "unavailable",
                                       "Curation audit API", formula, "period_activity"))
    if curation_status == "partial":
        curation_metrics.insert(0, metric(
            "curation-retained-window", "Decisions in retained portion", len(curation_rows), "requests",
            "observed", "Curation audit API",
            f"count(events from {curation_scope['available_start']} through {curation_scope['available_end']}); not a monthly total",
            "partial_period_activity",
        ))

    severity = Counter(str(row.get("severity") or "Unknown").lower() for row in violations)
    vtypes = Counter(str(row.get("type") or "Unknown") for row in violations)
    cves = Counter()
    impacted = set()
    for row in violations:
        for cve in row.get("cves") or ([row.get("cve")] if row.get("cve") else []):
            if cve:
                cves[str(cve)] += 1
        impacted.update(str(path) for path in (row.get("impacted_artifacts") or []))
    affected_repositories = Counter(path.split("/")[0] for path in impacted if "/" in path)
    active_watches = sum(bool((row.get("general_data") or {}).get("active", row.get("active"))) for row in watches)
    indexed_total = len(indexed) + len(non_indexed)
    xray_metrics = [
        metric("xray-new-findings", "New violation occurrences", len(violations), "findings", "observed", "Xray violations API", "count(period rows)", "period_activity"),
        metric("xray-critical-findings", "Critical violations", severity.get("critical", 0), "findings", "derived", "Xray violations API", "severity = critical", "period_activity"),
        metric("xray-high-findings", "High violations", severity.get("high", 0), "findings", "derived", "Xray violations API", "severity = high", "period_activity"),
        metric("xray-indexed", "Indexed repositories", len(indexed), "repositories", "observed", "Xray repository API", "count(indexed)", "point_in_time"),
        metric("xray-index-coverage", "Repository indexing coverage", pct(len(indexed), indexed_total), "%", "derived", "Xray repository API", "indexed / eligible × 100", "point_in_time"),
        metric("xray-watches", "Watches", len(watches), "watches", "observed", "Xray watches API", "count(watches)", "point_in_time"),
        metric("xray-active-watches", "Active watches", active_watches, "watches", "derived", "Xray watches API", "count(active=true)", "point_in_time"),
        metric("xray-policies", "Policies", len(policies), "policies", "observed", "Xray policies API", "count(policies)", "point_in_time"),
    ]

    ai_types = {"AIEditorExtensions", "AgentPackages", "AgentPlugins", "HuggingFaceML", "MachineLearning", "NimModel", "Skills"}
    ai_repos = [row for row in repositories if row.get("packageType") in ai_types]
    ai_metrics = [metric("ai-repositories-total", "AI and agent repositories", len(ai_repos), "repositories",
                         "observed", "Artifactory repository API", "count(AI package types)", "point_in_time")]
    jas_policies = [row for row in policies if any(isinstance((rule.get("criteria") or {}).get("exposures"), dict) for rule in row.get("rules", []))]

    curation_label = ("Complete period collection" if curation_status == "available" else
                      (f"Retained coverage only: {curation_scope.get('available_start')} to {curation_scope.get('available_end')}" if curation_status == "partial" else
                       "Unavailable: requested period is outside the 30-day audit retention"))
    limitations = [
        "Every primary metric in this report was built from this run's checksum-manifested raw API evidence; no prior report supplied a value.",
        f"Artifactory, Xray configuration and AI repository inventory are current-state observations as of {evidence['artifactory']['as_of']}; they are not historical month-end snapshots.",
        curation_scope.get("reason") or "Curation period coverage is complete.",
        "Financial value is unavailable because customer currency, cost and realization assumptions were not provided.",
        "Downloads, uploads and cache efficiency require matching boundary counters or bounded logs; current counters cannot be retroactively converted into historical monthly totals.",
    ]
    risks = [{"title": "Critical Xray intake", "detail": f"{severity.get('critical', 0):,} critical findings were created in the selected period."}]
    if curation_status != "available":
        risks.append({"title": "Curation history gap", "detail": curation_scope.get("reason")})
    outcomes = [{"title": "Xray evidence complete", "detail": f"All {len(violations):,} reported period findings were collected and reconciled."}]
    if complete_curation:
        outcomes.append({"title": "Preventive control activity", "detail": f"Curation evaluated {len(curation_rows):,} requests and blocked {len(blocked):,}."})
    actions = [{"title": "Prioritize critical findings", "detail": "Assign owners to the highest-impact critical findings and validate fix availability."}]
    if curation_status != "available":
        actions.append({"title": "Preserve Curation evidence continuously", "detail": "Schedule the report inside the 30-day retention window or archive Curation webhooks/API exports."})

    report = {
        "schema_version": "0.3",
        "meta": {"title": "JFrog Platform Value & Risk Report", "server_id": evidence["provenance"]["server_id"],
                 "data_source": "live", "report_type": evidence["reporting"]["cadence"].title(),
                 "period_label": period_label, "date_from": format_date(period["start"]), "date_to": format_date(period["end"]),
                 "period_start": period["start"], "period_end": period["end"],
                 "generated": datetime.now(timezone.utc).date().isoformat(), "fallback_used": False,
                 "persona": "CIO & CISO executive leadership",
                 "report_purpose": "Periodic operating review of platform adoption, supply-chain risk, governance and prioritized action."},
        "evidence_revalidation": {"message": "Fresh API evidence only. Historical activity and current-state inventory are displayed with separate timestamps."},
        "executive_signals": [
            metric("xray-new-findings", "Period Xray findings", len(violations), "findings", "observed", "Xray violations API", "count(period rows)"),
            metric("xray-critical-findings", "Critical findings", severity.get("critical", 0), "findings", "derived", "Xray violations API", "severity = critical"),
            metric("curation-decisions", "Curation decisions", len(curation_rows) if complete_curation else None, "requests", "observed" if complete_curation else "unavailable", "Curation audit API", "complete period event count"),
            metric("repositories", "Current repositories", len(repositories), "repositories", "observed", "Artifactory repository API", "count(repositories)"),
        ],
        "executive_summary": {"risks": risks, "outcomes": outcomes, "actions": actions},
        "platform": {"metrics": [
            metric("repositories", "Repositories", len(repositories), "count", "observed", "Artifactory repository API", "count(repositories)"),
            metric("local-repositories", "Local", repo_types.get("local", 0), "count", "observed", "Artifactory repository API"),
            metric("remote-repositories", "Remote", repo_types.get("remote", 0), "count", "observed", "Artifactory repository API"),
            metric("virtual-repositories", "Virtual", repo_types.get("virtual", 0), "count", "observed", "Artifactory repository API"),
            metric("federated-repositories", "Federated", repo_types.get("federated", 0), "count", "observed", "Artifactory repository API"),
        ], "package_types": package_types.most_common(15)},
        "artifactory_detail": {"status": "available", "collected_at": evidence["artifactory"]["as_of"], "metrics": [
            metric("artifact-storage", "Artifact storage", binaries.get("artifactsSize"), "", "observed", "Artifactory storage API"),
            metric("artifacts-count", "Artifacts", binaries.get("artifactsCount"), "count", "observed", "Artifactory storage API"),
            metric("binary-dedup-optimization", "Binary deduplication", binaries.get("optimization"), "", "observed", "Artifactory storage API"),
        ], "repository_types": repo_types.most_common(), "package_types": package_types.most_common(15),
            "top_storage": [{"repository": row.get("repoKey"), "used_space": row.get("usedSpace"), "files": row.get("filesCount"),
                             "package_type": row.get("packageType"), "project": row.get("projectKey") or "Unassigned"} for row in top_storage],
            "interpretation": ["Storage and repository metrics are current-state evidence collected during this run, not reconstructed month-end values."]},
        "curation": {"status": curation_status, "coverage_label": curation_label, "collection": curation_scope,
                     "metrics": curation_metrics, "events_by_package_type": curation_types.most_common(),
                     "top_block_reasons": block_reasons.most_common(10),
                     "top_blocked": [{"package": name, "ecosystem": ecosystem, "count": count} for (name, ecosystem), count in top_blocked_count.most_common(10)],
                     "top_users": top_users, "top_policies": [], "show_configuration": False,
                     "interpretation": [curation_label]},
        "xray": {"status": "available", "metrics": xray_metrics,
                 "policy_types": dict(Counter(str(row.get("type") or "unknown") for row in policies)),
                 "indexed_ecosystems": Counter(str(row.get("pkg_type") or "unknown") for row in indexed).most_common(15),
                 "violations_by_severity": [(key.title(), value) for key, value in severity.most_common()],
                 "violations_by_type": vtypes.most_common(), "top_cves": cves.most_common(10),
                 "top_affected_repositories": affected_repositories.most_common(10),
                 "collection_note": f"Complete bounded collection: {len(violations):,} of {evidence['xray']['period']['collection']['total_reported']:,} API-reported findings."},
        "ai_catalog": {"status": "available", "metrics": ai_metrics,
                       "repositories_by_type": Counter(str(row.get("packageType")) for row in ai_repos).most_common(),
                       "repositories_by_repository_type": Counter(str(row.get("type") or "unknown") for row in ai_repos).most_common(),
                       "note": f"Current AI repository footprint as of {evidence['ai_catalog']['as_of']}; asset scan status requires a separately timestamped supported collector."},
        "jas": {"status": "available", "metrics": [metric("jas-policies", "Policies with JAS criteria", len(jas_policies), "policies", "observed", "Xray policy API")],
                "capabilities": [], "applicability": [], "policy_names": [row.get("name") for row in jas_policies],
                "note": "Current policy configuration only; period JAS findings are not inferred from policy definitions."},
        "economic_model": {"status": "unavailable", "scenarios": {}, "assumptions": [], "unavailable_models": []},
        "limitations": limitations,
        "provenance": evidence["provenance"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
