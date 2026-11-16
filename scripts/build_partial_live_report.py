#!/usr/bin/env python3
"""Normalize successful payloads from one live run into a classified JFrog Platform report."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path


def load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def metric(mid, label, value, unit, classification, source, formula="API field"):
    return {"id": mid, "label": label, "value": value, "unit": unit, "classification": classification, "source": source, "formula": formula}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--server", required=True)
    parser.add_argument("--date-from", required=True, help="Inclusive ISO date, YYYY-MM-DD")
    parser.add_argument("--date-to", required=True, help="Inclusive ISO date, YYYY-MM-DD")
    parser.add_argument("--cadence", choices=("weekly", "monthly", "custom"), required=True)
    args = parser.parse_args()
    raw = args.raw_dir

    start = datetime.strptime(args.date_from, "%Y-%m-%d").date()
    end = datetime.strptime(args.date_to, "%Y-%m-%d").date()
    period_label = start.strftime("%B %Y") if args.cadence == "monthly" else f'{start.strftime("%B %d, %Y").replace(" 0", " ")} – {end.strftime("%B %d, %Y").replace(" 0", " ")}'

    repos = load(raw / "ciso-repos-all.json")
    watches = load(raw / "ciso-watches.json")
    xray_policies = load(raw / "ciso-policies.json").get("result", [])
    indexed_payload = load(raw / "ciso-indexed-repos.json")
    curation = load(raw / "ciso-curation.json").get("data", [])
    curation_policies = load(raw / "ciso-curation-policies.json").get("data", [])
    waivers = load(raw / "ciso-curation-waivers.json")
    diagnostics = load(raw / "ciso-curation-diagnostics.json")
    benchmark = load(args.benchmark)

    indexed = indexed_payload.get("indexed_repos", [])
    non_indexed = indexed_payload.get("non_indexed_repos", [])
    actions = Counter(str(row.get("action") or "unknown").lower() for row in curation)
    repo_types = Counter(str(row.get("type") or "unknown").lower() for row in repos)
    package_types = Counter(str(row.get("packageType") or "unknown") for row in repos)
    curation_types = Counter(str(row.get("package_type") or "unknown") for row in curation)
    active_watches = sum(bool((row.get("general_data") or {}).get("active")) for row in watches)
    xray_policy_types = Counter(str(row.get("type") or "unknown") for row in xray_policies)
    jas_policies = [row for row in xray_policies if any("exposures" in (rule.get("criteria") or {}) for rule in row.get("rules", []))]
    ai_types = {"AIEditorExtensions", "AgentPackages", "AgentPlugins", "HuggingFaceML", "MachineLearning", "NimModel", "Skills"}
    ai_repos = [row for row in repos if row.get("packageType") in ai_types]

    user_rows = [row for row in curation if row.get("username")]
    unique_users = len({row["username"] for row in user_rows})
    unique_users_approved = len({row["username"] for row in user_rows if str(row.get("action")).lower() == "approved"})
    unique_repos = len({row.get("curated_repository_name") for row in curation if row.get("curated_repository_name")})
    blocked_rows = [row for row in curation if str(row.get("action")).lower() == "blocked"]
    unique_blocked = len({(row.get("package_type"), row.get("package_name"), row.get("package_version")) for row in blocked_rows})
    block_reasons = Counter(str(row.get("reason") or "Unknown") for row in blocked_rows)
    top_blocked_counter = Counter((str(row.get("package_name") or "Unknown"), str(row.get("package_type") or "unknown")) for row in blocked_rows)
    top_blocked = [{"package": name, "ecosystem": ecosystem, "count": count} for (name, ecosystem), count in top_blocked_counter.most_common(15)]

    by_user = {}
    for row in user_rows:
        item = by_user.setdefault(row["username"], {"user": row["username"], "requests": 0, "blocked": 0, "approved": 0, "repos": set(), "packages": set()})
        item["requests"] += 1
        action = str(row.get("action") or "unknown").lower()
        if action in ("blocked", "approved"):
            item[action] += 1
        if row.get("curated_repository_name"):
            item["repos"].add(row["curated_repository_name"])
        item["packages"].add((row.get("package_type"), row.get("package_name"), row.get("package_version")))
    # Build serializable rows without leaking the working sets.
    top_users = [{"user": x["user"], "requests": x["requests"], "blocked": x["blocked"], "approved": x["approved"], "repos": len(by_user[x["user"]]["repos"]), "packages": len(by_user[x["user"]]["packages"])} for x in sorted(by_user.values(), key=lambda x: x["requests"], reverse=True)[:10]]

    policy_events = Counter()
    risk_events = Counter()
    blocking_policy_names_by_risk = {}
    for event in blocked_rows:
        for policy in event.get("policies") or []:
            policy_name = str(policy.get("policy_name") or "Unknown")
            risk_type = str(policy.get("condition_category") or "unknown").lower()
            policy_events[policy_name] += 1
            risk_events[risk_type] += 1
            blocking_policy_names_by_risk.setdefault(risk_type, set()).add(policy_name)
    enabled_policies = [row for row in curation_policies if row.get("enabled") is True]
    block_policies = [row for row in enabled_policies if row.get("policy_action") == "block"]
    dry_run_policies = [row for row in enabled_policies if row.get("policy_action") == "dry_run"]
    policy_risks = Counter(str((row.get("condition") or {}).get("risk_type") or "unknown") for row in enabled_policies)
    cache_enforcing = sum(bool(row.get("block_from_cache")) for row in block_policies)

    indexed_total = len(indexed) + len(non_indexed)
    indexed_pct = round(len(indexed) / indexed_total * 100, 1) if indexed_total else None
    watch_active_pct = round(active_watches / len(watches) * 100, 1) if watches else None
    block_rate = round(len(blocked_rows) / len(curation) * 100, 2) if curation else None

    # Forrester's reduced-vulnerability model: baseline × reduction × value per
    # vulnerability × risk adjustment. We substitute observed unique blocked
    # package versions for the baseline and expose the conversion assumption.
    value_per_unit = 435
    risk_adjustment = 0.90
    scenario_factors = {"conservative": 0.25, "expected": 0.50, "optimistic": 1.0}
    scenario_values = {key: round(unique_blocked * factor * value_per_unit * risk_adjustment, 2) for key, factor in scenario_factors.items()}

    report = {
        "schema_version": "0.3",
        "meta": {"title": "JFrog Platform Value & Risk Report", "server_id": args.server, "data_source": "live", "report_type": args.cadence.title(), "period_label": period_label, "date_from": start.strftime("%B %d, %Y").replace(" 0", " "), "date_to": end.strftime("%B %d, %Y").replace(" 0", " "), "generated": date.today().isoformat(), "fallback_used": False, "scope": f"All repositories visible to the configured {args.server} identity"},
        "executive_signals": [
            metric("curation-blocks", "Blocked package requests", len(blocked_rows), "requests", "observed", "Curation audit", "count(action = blocked)"),
            metric("unique-blocked", "Unique package versions stopped", unique_blocked, "packages", "derived", "Curation audit", "distinct(package type, name, version) where blocked"),
            metric("active-curation-users", "Active Curation users", unique_users, "identities", "derived", "Curation audit", "distinct requester identities in period"),
            metric("xray-index-coverage", "Xray repository coverage", indexed_pct, "%", "derived", "Xray binary manager", "indexed / (indexed + non-indexed) × 100")
        ],
        "platform": {"metrics": [metric("repositories", "Repositories", len(repos), "count", "observed", "Artifactory inventory"), metric("local-repositories", "Local", repo_types.get("local", 0), "count", "observed", "Artifactory inventory"), metric("remote-repositories", "Remote", repo_types.get("remote", 0), "count", "observed", "Artifactory inventory"), metric("virtual-repositories", "Virtual", repo_types.get("virtual", 0), "count", "observed", "Artifactory inventory"), metric("federated-repositories", "Federated", repo_types.get("federated", 0), "count", "observed", "Artifactory inventory")], "package_types": package_types.most_common(12)},
        "xray": {"status": "partial", "collection_note": "Configuration inventory succeeded. Period violation collection failed with EOF; findings are unavailable, not zero.", "metrics": [metric("xray-indexed", "Indexed repositories", len(indexed), "count", "observed", "Xray binary manager"), metric("xray-non-indexed", "Non-indexed repositories", len(non_indexed), "count", "observed", "Xray binary manager"), metric("xray-watches", "Watches", len(watches), "count", "observed", "Xray watches"), metric("xray-active-watches", "Active watches", active_watches, "count", "observed", "Xray watches"), metric("active-watch-ratio", "Active watch ratio", watch_active_pct, "%", "derived", "Xray watches", "active / total watches × 100"), metric("xray-policies", "Policies", len(xray_policies), "count", "observed", "Xray policies")], "policy_types": dict(xray_policy_types)},
        "curation": {
            "status": "available", "collection": diagnostics,
            "metrics": [metric("curation-decisions", "Policy decisions", len(curation), "requests", "observed", "Curation audit"), metric("curation-approved", "Approved after inspection", actions.get("approved", 0), "requests", "observed", "Curation audit"), metric("curation-blocked", "Blocked requests", len(blocked_rows), "requests", "observed", "Curation audit"), metric("curation-block-rate", "Block rate", block_rate, "%", "derived", "Curation audit", "blocked / all decisions × 100"), metric("curation-users", "Unique active users", unique_users, "identities", "derived", "Curation audit", "distinct requesters"), metric("curation-users-approved", "Users with approvals", unique_users_approved, "identities", "derived", "Curation audit", "distinct requesters with approved decision"), metric("curation-repos", "Repositories used", unique_repos, "repositories", "derived", "Curation audit", "distinct curated repository names"), metric("unique-blocked-packages", "Unique blocked versions", unique_blocked, "packages", "derived", "Curation audit", "distinct type + name + version")],
            "events_by_package_type": curation_types.most_common(), "top_block_reasons": block_reasons.most_common(10), "top_blocked": top_blocked, "top_users": top_users,
            "risk_events": risk_events.most_common(), "top_policies": policy_events.most_common(10),
            "blocking_policies_by_risk": sorted(((key, len(value)) for key, value in blocking_policy_names_by_risk.items()), key=lambda row: row[1], reverse=True),
            "policy_inventory": {"registered": len(curation_policies), "enabled": len(enabled_policies), "block_active": len(block_policies), "dry_run_active": len(dry_run_policies), "by_risk_type": policy_risks.most_common(), "cache_enforcing": cache_enforcing, "cache_not_enforcing": max(0, len(block_policies) - cache_enforcing)},
            "waivers": waivers
        },
        "jas": {"status": "available", "metrics": [metric("jas-policies", "Policies with JAS exposure criteria", len(jas_policies), "policies", "observed", "Xray policy inventory")], "note": "Configured exposure criteria—not a count of period JAS findings."},
        "ai_catalog": {"status": "available", "metrics": [metric("ai-repositories-total", "AI and agent repositories", len(ai_repos), "repositories", "observed", "Artifactory inventory")], "repositories_by_type": Counter(row.get("packageType") for row in ai_repos).most_common()},
        "economic_model": {
            "source": benchmark["title"], "classification": "projected", "currency": "USD", "confidence": "low", "period": f"{period_label}; not annualized",
            "baseline": unique_blocked, "baseline_unit": "unique blocked package versions", "formula": "baseline × assumed vulnerability-equivalent conversion × $435 × 90% Forrester risk adjustment", "value_per_unit": 435, "risk_adjustment": 0.90, "adoption_coverage": 1.0, "realization_factor": "scenario conversion factor", "scenarios": scenario_values,
            "assumptions": ["Each unique blocked package version maps to 0.25, 0.50, or 1.00 avoided vulnerability-equivalent depending on scenario.", "Forrester's $435 average remediation cost and 10% downward risk adjustment are used unchanged."],
            "applicability": "Illustrative prevention-value scenario only. A blocked package request is not automatically an avoided vulnerability or incident.",
            "data_gaps": ["No customer remediation cost", "No confirmed vulnerability-to-package mapping", "No incident conversion evidence", "No customer currency selection"],
            "unavailable_models": [
                {"name": "Faster vulnerability remediation", "reason": "Period Xray violations and customer remediation hours were unavailable."},
                {"name": "Developer onboarding", "reason": "Active Curation users are not newly onboarded developers."},
                {"name": "Tool consolidation", "reason": "Customer legacy-tool and JFrog cost baselines were not supplied."}
            ],
            "benchmark_summary": benchmark
        },
        "limitations": ["Period Xray violation collection was unavailable in the base collector; no zero was substituted.", "The economic scenario is benchmark-derived and projected, not observed customer value.", "Requester identities can include service tokens as well as people; active users are not license counts.", f"Repository inventory is point-in-time; Curation decisions cover only the {period_label} reporting window."]
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
