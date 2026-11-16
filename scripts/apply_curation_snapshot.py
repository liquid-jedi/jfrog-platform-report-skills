#!/usr/bin/env python3
"""Replace a retained-period Curation result with a dated, preserved CISO snapshot."""

import argparse
import json
from collections import Counter
from pathlib import Path


def metric(mid, label, value, unit, classification, source, formula="API field"):
    return {"id": mid, "label": label, "value": value, "unit": unit,
            "classification": classification, "source": source, "formula": formula}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    source = snapshot["curation"]
    events = source.get("audit_events") or []
    unique_blocked = len({(row.get("type"), row.get("package"), row.get("version")) for row in events})
    repos = {repo for row in source.get("top_users") or [] for repo in row.get("repos") or []}
    package_types = Counter(str(row.get("type") or "unknown") for row in events)
    reason_rows = [(key.title(), value) for key, value in (source.get("by_reason") or {}).items() if value]
    top_users = [{"user": row.get("user"), "requests": row.get("events", 0),
                  "blocked": row.get("blocked", 0), "approved": row.get("approved", 0),
                  "repos": len(row.get("repos") or []), "packages": row.get("distinct_packages", 0)}
                 for row in (source.get("top_users") or [])[:10]]
    policy = source.get("policy_inventory") or {}
    cache = policy.get("cached_package_enforcement") or {}
    waivers = source.get("waiver_requests") or {"pending": 0, "approved": 0, "rejected": 0,
                                                  "pending_aging": {"oldest_pending_days": None, "buckets": []}}

    report["curation"] = {
        "status": "available",
        "collection": {"mode": "preserved_period_snapshot", "complete": True,
                       "rows_fetched": source.get("total"), "total_count_reported": source.get("total"),
                       "snapshot_path": str(args.snapshot), "current_historical_query_rows": 0},
        "metrics": [
            metric("curation-decisions", "Policy decisions", source.get("total"), "requests", "observed", "Preserved September CISO snapshot"),
            metric("curation-approved", "Approved after inspection", source.get("approved"), "requests", "observed", "Preserved September CISO snapshot"),
            metric("curation-blocked", "Blocked requests", source.get("blocked"), "requests", "observed", "Preserved September CISO snapshot"),
            metric("curation-block-rate", "Block rate", source.get("block_rate"), "%", "derived", "Preserved September CISO snapshot", "blocked / all decisions × 100"),
            metric("curation-users", "Unique active users", source.get("unique_users"), "identities", "derived", "Preserved September CISO snapshot", "distinct requesters"),
            metric("curation-users-approved", "Users with approvals", source.get("unique_users_approved"), "identities", "derived", "Preserved September CISO snapshot", "distinct requesters with approved decision"),
            metric("curation-repos", "Repositories represented in retained user detail", len(repos), "repositories", "derived", "Preserved September CISO snapshot", "distinct repositories in retained top-user detail"),
            metric("unique-blocked-packages", "Unique blocked versions", unique_blocked, "packages", "derived", "Preserved September CISO snapshot", "distinct type + name + version in retained blocked events"),
            metric("curation-repeat-block-attempts", "Repeat blocked attempts", max(0, (source.get("blocked") or 0) - unique_blocked), "requests", "derived", "Preserved September CISO snapshot", "blocked requests − unique blocked package versions"),
            metric("curation-blocks-per-user", "Blocked requests per active identity", round((source.get("blocked") or 0) / source.get("unique_users"), 2) if source.get("unique_users") else None, "requests/identity", "derived", "Preserved September CISO snapshot", "blocked requests / active requester identities"),
        ],
        "events_by_package_type": package_types.most_common(),
        "top_block_reasons": reason_rows,
        "top_blocked": [{"package": row.get("package"), "ecosystem": row.get("ecosystem"), "count": row.get("count", 0)} for row in (source.get("top_blocked") or [])[:15]],
        "top_users": top_users,
        "risk_events": reason_rows,
        "blocking_policies_by_risk": [(row.get("type"), row.get("count")) for row in (source.get("blocking_policies_by_risk") or [])],
        "top_policies": [(row.get("name"), row.get("blocked_events", 0)) for row in (source.get("top_policies") or [])[:10]],
        "policy_inventory": {"registered": policy.get("total_registered", 0),
                             "enabled": policy.get("block_active", 0) + policy.get("dry_run_active", 0),
                             "block_active": policy.get("block_active", 0), "dry_run_active": policy.get("dry_run_active", 0),
                             "by_risk_type": [(row.get("type"), row.get("count")) for row in policy.get("by_risk_type") or []],
                             "cache_enforcing": cache.get("policies_enforcing_cache", 0),
                             "cache_not_enforcing": max(0, (cache.get("blocking_policies_total") or 0) - (cache.get("policies_enforcing_cache") or 0))},
        "waivers": waivers,
        "interpretation": ["September Curation activity comes from the preserved September report snapshot because the current historical audit query returned no retained rows.",
                           "The snapshot is period evidence, not a current re-query; this distinction is recorded in the evidence ledger."],
    }

    signal_values = {"curation-blocks": source.get("blocked"), "unique-blocked": unique_blocked,
                     "active-curation-users": source.get("unique_users")}
    for item in report.get("executive_signals", []):
        if item.get("id") in signal_values:
            item["value"] = signal_values[item["id"]]
            item["source"] = "Preserved September CISO snapshot"

    model = report.get("economic_model") or {}
    factor = {"conservative": 0.25, "expected": 0.50, "optimistic": 1.0}
    model["baseline"] = unique_blocked
    model["scenarios"] = {name: round(unique_blocked * value * 435 * 0.90, 2) for name, value in factor.items()}

    report.setdefault("limitations", []).append(
        "September Curation uses a preserved period snapshot because the current historical audit query returned no retained rows; it is not a fresh-query zero.")
    summary = report.get("executive_summary") or {}
    for item in summary.get("outcomes", []):
        if item.get("title") == "Packages stopped before consumption":
            item["detail"] = f"{unique_blocked:,} unique package versions were blocked in the preserved September snapshot."

    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
