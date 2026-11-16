#!/usr/bin/env python3
"""Render classified report JSON into the fixed, script-free HTML template."""

import argparse
import html
import json
from pathlib import Path


GLOSSARY_PATH = Path(__file__).resolve().parent.parent / "assets" / "metric-glossary.json"
METRIC_GLOSSARY = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))

ADVERSE_METRICS = {
    "xray-new-findings", "xray-critical-findings", "xray-high-findings", "xray-non-indexed",
    "access-expiring-7d", "access-expiring-30d", "access-non-expiring",
    "ai-malicious-skills", "ai-suspicious-skills", "ai-vulnerable-skills",
    "ai-skills-without-project", "runtime-critical-high", "runtime-malicious-packages",
    "runtime-critical-applicable", "runtime-integrity-violations",
    "curation-cache-gap-policies", "jas-applicable", "jas-rescan-required", "jas-not-scanned",
}
ADVERSE_TERMS = {
    "malicious", "suspicious", "vulnerable", "critical", "high",
    "integrity violation", "not linked", "unmanaged", "expired",
    "permission denied", "collection failed", "not scanned", "no xray data", "never used",
}


def esc(value):
    return html.escape("" if value is None else str(value), quote=True)


def number(value):
    if value is None:
        return "Unavailable"
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{value:,}" if isinstance(value, int) else esc(value)


def usd(value):
    return f"${value:,.0f}" if value is not None else "Unavailable"


def currency_value(value, currency):
    if value is None:
        return "Unavailable"
    try:
        return f"{currency} {float(value):,.0f}"
    except (TypeError, ValueError):
        return f"{currency} {value}"


def is_adverse_text(value):
    text = str(value or "").strip().lower()
    if text in {"not malicious", "no known vulnerabilities", "not vulnerable", "0"}:
        return False
    return any(term in text for term in ADVERSE_TERMS)


def metric_risk(item):
    explicit = item.get("risk_state")
    if explicit in {"bad", "warning", "good", "neutral"}:
        return explicit
    value = item.get("value")
    if item.get("id") in ADVERSE_METRICS and isinstance(value, (int, float)) and value > 0:
        return "bad"
    return "neutral"


def card(item):
    glossary = METRIC_GLOSSARY.get(item.get("id"), {})
    meaning = item.get("meaning") or glossary.get("meaning") or f'This is the reported value for {item.get("label", "this metric").lower()}.'
    why = item.get("why_it_matters") or glossary.get("why") or "Use this value with its source, period, and evidence classification before drawing a conclusion."
    risk = metric_risk(item)
    return (f'<article class="card risk-{risk}"><span class="tag {esc(item["classification"])}">{esc(item["classification"])}</span>'
            f'<h3>{esc(item["label"])}</h3><div class="value">{number(item.get("value"))}'
            f'<span class="unit">{esc(item.get("unit"))}</span></div>'
            f'<div class="plain" style="border-top:1px solid #263a5b;margin-top:14px;padding-top:12px">'
            f'<strong style="display:block;font-size:11px">What this means</strong>'
            f'<p style="color:#b4c0d4;font-size:11px;line-height:1.45;margin:3px 0 10px">{esc(meaning)}</p>'
            f'<strong style="display:block;font-size:11px">Why it matters</strong>'
            f'<p style="color:#b4c0d4;font-size:11px;line-height:1.45;margin:3px 0 10px">{esc(why)}</p></div>'
            f'<details class="measurement" style="border-top:1px solid #263a5b;color:#b4c0d4;font-size:10px;padding-top:9px">'
            f'<summary style="cursor:pointer;color:#9fb3cf;font-weight:700">How this was measured</summary>'
            f'<div><b>Source:</b> {esc(item.get("source"))}</div><div><b>Method:</b> {esc(item.get("formula"))}</div>'
            f'</details></article>')


def section(title, description, content, status="", anchor=""):
    badge = f'<span class="status {esc(status)}">{esc(status)}</span>' if status else ""
    return f'<section class="section" id="{esc(anchor)}"><div class="section-head"><div><h2>{esc(title)}</h2><div class="section-desc">{esc(description)}</div></div>{badge}</div>{content}</section>'


def bar_panel(title, rows):
    maximum = max([float(row[1] or 0) for row in rows] + [1])
    bars = "".join(f'<div class="barrow {"risk-bad" if is_adverse_text(label) and float(value or 0) > 0 else ""}"><span>{esc(label)}</span><div class="track"><div class="fill" style="width:{max(1,float(value or 0)/maximum*100):.2f}%"></div></div><span class="number">{number(value)}</span></div>' for label, value in rows)
    return f'<div class="panel"><div class="panel-head"><h3>{esc(title)}</h3></div><div class="panel-body"><div class="bars">{bars}</div></div></div>'


def table_cell(value):
    css = ' class="risk-bad-text"' if is_adverse_text(value) else ""
    return f"<td{css}>{esc(value)}</td>"


def data_table(title, headers, rows):
    head = "".join(f"<th>{esc(x)}</th>" for x in headers)
    body = "".join("<tr>" + "".join(table_cell(cell) for cell in row) + "</tr>" for row in rows)
    return f'<div class="panel"><div class="panel-head"><h3>{esc(title)}</h3></div><div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></div>'


def asset_security_block(title, asset_type, inventory):
    """Render one AI asset class without merging unlike security states."""
    assets = inventory.get("visible_assets") or []
    counts = inventory.get("security_counts") or {}
    order = ("malicious", "suspicious", "vulnerable", "not_malicious", "scanning", "not_scanned", "n_a")
    labels = {
        "malicious": "Malicious", "suspicious": "Suspicious", "vulnerable": "Vulnerable",
        "not_malicious": "Not malicious", "scanning": "Scanning",
        "not_scanned": "Not scanned", "n_a": "N/A",
    }
    rows = [(labels[key], counts.get(key, 0)) for key in order if counts.get(key) is not None]
    summary = bar_panel(f"{title} security distribution", rows) if rows else ""
    if not assets:
        return summary
    vulnerability_counts = inventory.get("vulnerability_counts") or {}
    if vulnerability_counts:
        summary += bar_panel(f"{title} dependency vulnerability posture", [
            ("Vulnerable", vulnerability_counts.get("vulnerable", 0)),
            ("No known vulnerabilities", vulnerability_counts.get("no_known_vulnerabilities", 0)),
            ("No Xray data", vulnerability_counts.get("no_xray_data", 0)),
        ])
    project_counts = inventory.get("project_counts") or {}
    if project_counts:
        summary += bar_panel(f"{title} project attribution", [
            ("Linked", project_counts.get("linked", 0)), ("Not linked", project_counts.get("unlinked", 0)),
            ("Unknown", project_counts.get("unknown", 0)),
        ])
    details = []
    for item in assets:
        details.append((item.get("name"), item.get("version") or item.get("type"),
                        item.get("security_status") or "N/A", item.get("vulnerability_status") or "N/A",
                        item.get("vulnerability_count") if item.get("vulnerability_count") is not None else "N/A",
                        item.get("project_key") or item.get("project_status") or "Unknown",
                        item.get("governance") or item.get("management_status") or "N/A",
                        item.get("repository") or item.get("origin") or item.get("source") or "N/A"))
    table = data_table(f"{title} asset evidence", [asset_type, "Version / type", "Behavioral status", "Vulnerability posture", "Issues", "Project attribution", "Governance", "Repository / origin"], details)
    return summary + disclosure(f"View {title.lower()} asset details ({len(details)})", table, compact=True)


def disclosure(title, content, compact=False):
    css = "disclosure compact" if compact else "disclosure"
    return f'<details class="{css}"><summary>{esc(title)}</summary><div class="disclosure-body">{content}</div></details>'


def metric_value(metrics, metric_id):
    item = next((row for row in metrics or [] if row.get("id") == metric_id), None)
    return item.get("value") if item else None


def priority_panel(actions):
    rows = []
    for action in actions:
        rows.append(
            f'<div class="priority-item {"risk-bad" if action.get("priority") == "P1" else ""}">'
            f'<div class="priority">{esc(action.get("priority", "P2"))}</div>'
            f'<div><strong>{esc(action.get("title"))}</strong><p>{esc(action.get("detail"))}</p></div>'
            f'<div><strong>{esc(action.get("owner", "Leadership owner"))}</strong><p>{esc(action.get("reason", "Evidence-backed action"))}</p></div>'
            f'<div><strong>{esc(action.get("target", "30 days"))}</strong></div>'
            '</div>'
        )
    return '<div class="priority-list">' + ''.join(rows) + '</div>'


def insight_list(title, rows, numbered=False, adverse=False):
    items = "".join(f'<div class="insight"><span class="insight-index">{i if numbered else "•"}</span><div><strong>{esc(row.get("title"))}</strong><p>{esc(row.get("detail"))}</p></div></div>' for i, row in enumerate(rows, 1))
    css = "panel-body insight-list risk-bad" if adverse else "panel-body insight-list"
    return f'<div class="panel"><div class="panel-head"><h3>{esc(title)}</h3></div><div class="{css}">{items}</div></div>'


def leadership_lens(what, why, decisions):
    content = ('<div class="three component-lens">'
            + insight_list("What this component shows", [{"title": "Scope", "detail": what}])
            + insight_list("Why it matters", [{"title": "Leadership relevance", "detail": why}])
            + insight_list("Decisions it supports", [{"title": "Use this section to", "detail": decisions}])
            + '</div>')
    return disclosure("About this section", content, True)


def summary_panel(rows):
    body = ''.join(f'<li>{esc(row)}</li>' for row in rows)
    return f'<div class="panel"><div class="panel-head"><h3>Summary</h3></div><div class="panel-body"><ul class="summary-list">{body}</ul></div></div>'


def trend_panel(rows):
    cards = []
    for row in rows:
        pct = row.get("change_percent")
        direction = "flat" if pct in (None, 0) else ("up" if pct > 0 else "down")
        favorable_up = row.get("id") in {"curation-decisions", "curation-users", "curation-block-rate"}
        favorable_down = row.get("id") in {"xray-new-findings", "xray-critical-findings", "xray-unique-cves", "curation-blocked", "unique-blocked-packages"}
        sentiment = "neutral"
        if pct not in (None, 0):
            sentiment = "good" if (pct > 0 and favorable_up) or (pct < 0 and favorable_down) else "bad"
        arrow = "→" if direction == "flat" else ("↑" if direction == "up" else "↓")
        cards.append(
            f'<div class="trend-card {direction} {sentiment}"><div class="trend-title">{esc(row.get("label"))}</div>'
            f'<div class="trend-values"><strong>{number(row.get("previous"))}</strong><span>{arrow}</span><strong>{number(row.get("current"))}</strong></div>'
            f'<div class="trend-delta">{("New baseline" if pct is None else f"{pct:+.1f}%")}</div></div>'
        )
    return '<div class="trend-grid">' + ''.join(cards) + '</div>'


def weekly_trend_panel(model):
    cards = []
    for series in model.get("series") or []:
        points = [point for point in series.get("points") or [] if isinstance(point.get("value"), (int, float))]
        if not points:
            continue
        maximum = max([abs(point["value"]) for point in points] + [1])
        bars = []
        for point in points:
            height = max(3, abs(point["value"]) / maximum * 82)
            bars.append(f'<div class="week-bar"><div class="week-column" style="height:{height:.1f}px"></div><b>{number(point["value"])}</b><span>{esc(point.get("label") or point.get("period_key"))}</span></div>')
        wow = series.get("latest_change_percent")
        polarity = series.get("polarity", "contextual")
        sentiment = "neutral"
        if wow not in (None, 0):
            sentiment = "bad" if (polarity == "lower_is_better" and wow > 0) or (polarity == "higher_is_better" and wow < 0) else ("good" if polarity != "contextual" else "neutral")
        delta = "Baseline" if wow is None else f'{wow:+.1f}% WoW'
        cards.append(f'<article class="series-card trend-{sentiment}"><div class="series-head"><strong>{esc(series.get("label"))}</strong><span class="series-delta {sentiment}">{delta}</span></div><div class="week-bars">{"".join(bars)}</div></article>')
    return '<div class="weekly-series">' + ''.join(cards) + '</div>'


MODULES = {"executive", "trend", "curation", "xray", "artifactory", "ai-security", "access", "jas", "runtime", "economic", "recommendations", "evidence"}


def static_report(data, enabled=None):
    enabled = MODULES if enabled is None else set(enabled)
    meta, curation, xray, model = data["meta"], data["curation"], data["xray"], data["economic_model"]
    xray_has_findings = any(item.get("id") == "xray-new-findings" for item in xray.get("metrics", []))
    validation = data.get("evidence_revalidation") or {}
    evidence_message = validation.get("message") or (f"Actual {meta['period_label']} evidence captured for the reporting period. Later current-state inventory is excluded." if xray_has_findings else f"Actual {meta['period_label']} evidence is shown where available; missing period evidence is not represented as zero.")
    nav_items = [("executive","Executive overview"),("curation","Curation"),("artifactory","Artifactory"),("xray","Xray")]
    if (data.get("ai_catalog") or {}).get("metrics"):
        nav_items.append(("ai-security","AI security"))
    if (data.get("access_governance") or {}).get("metrics"):
        nav_items.append(("access","Access & OIDC"))
    nav_items.extend([("jas","JAS")])
    if data.get("weekly_trend") or (data.get("prior_period_comparison") or {}).get("metrics"):
        nav_items.append(("trend","Trends"))
    if model.get("status") in {"benchmark", "projected"}:
        nav_items.append(("economic", "Economic context"))
    nav_items.extend([("recommendations","Recommendations"),("evidence","Evidence notes")])
    access = data.get("access_governance") or {}
    glance_rows = [
        ("Repositories", metric_value(data.get("platform", {}).get("metrics"), "repositories")),
        ("Artifact storage", metric_value((data.get("artifactory_detail") or {}).get("metrics"), "artifact-storage")),
        ("Curation unique users", metric_value(curation.get("metrics"), "curation-users")),
        ("Critical findings", metric_value(xray.get("metrics"), "xray-critical-findings")),
        ("Active tokens", metric_value(access.get("metrics"), "access-active-tokens")),
        ("OIDC providers", metric_value(access.get("metrics"), "oidc-providers")),
    ]
    glance = '<div class="glance"><div class="nav-title">At a glance</div>' + ''.join(f'<div class="glance-row"><span>{esc(label)}</span><b>{number(value)}</b></div>' for label,value in glance_rows) + '</div>'
    nav_meta = (f'<div class="nav-meta"><span><b>Report type:</b> {esc(meta.get("report_type") or "Report")}</span>'
                f'<span><b>Period:</b> {esc(meta.get("period_range") or meta.get("period_label") or "Unavailable")}</span>'
                f'<span><b>Instance:</b> {esc(meta.get("server_id") or meta.get("server") or "Unavailable")}</span></div>')
    nav = '<nav class="section-nav">' + nav_meta + '<div class="nav-links">' + ''.join(f'<a href="#{a}"><span></span>{esc(label)}</a>' for a,label in nav_items) + '</div>' + glance + '</nav>'
    provenance = f'<strong>Actual-data status:</strong> {esc(evidence_message)}'
    out = [nav, disclosure("Data provenance and revalidation", provenance)]
    if "executive" in enabled:
        summary = data.get("executive_summary") or {}
        body = leadership_lens(meta.get("report_purpose", "Monthly platform value and risk review."), "Gives platform, security and technology leadership one shared view of adoption, preventive controls and actionable risk.", "Agree priorities, owners and investments for the next operating period.")
        body += '<div class="grid" style="margin-top:14px">' + "".join(map(card, data["executive_signals"])) + '</div>'
        trends = [] if (data.get("weekly_trend") or {}).get("series") else (data.get("prior_period_comparison") or {}).get("metrics", [])
        if trends:
            rows = [(x["label"], number(x["previous"]), number(x["current"]), (f'{x["change_percent"]:+.1f}%' if x.get("change_percent") is not None else "New baseline")) for x in trends]
            body += '<div id="trend" style="margin-top:14px">' + trend_panel(trends) + '<div style="margin-top:14px">' + data_table("October movement versus September", ["Metric", "September", "October", "Movement"], rows) + '</div></div>'
        if summary:
            body += '<div class="three" style="margin-top:14px">' + insight_list("Top risks", summary.get("risks", []), True, True) + insight_list("Demonstrated outcomes", summary.get("outcomes", []), True) + insight_list("Recommended actions", summary.get("actions", []), True) + '</div>'
        out.append(section("Executive overview", "One-page synthesis of period outcomes, risks and actions.", body, anchor="executive"))

    weekly_trend = data.get("weekly_trend") or {}
    if "trend" in enabled and weekly_trend:
        series = weekly_trend.get("series") or []
        if series:
            trend_body = weekly_trend_panel(weekly_trend)
            rows = []
            for item in series:
                rows.append((item.get("label"),) + tuple(number(point.get("value")) for point in item.get("points") or []))
            headers = ["Metric"] + [point.get("label") or point.get("period_key") for point in (weekly_trend.get("weeks") or [])]
            trend_body += '<div style="margin-top:14px">' + data_table("Weekly values", headers, rows) + '</div>'
        else:
            trend_body = '<div class="callout neutral">At least two validated weekly archives with the same metric are required. The section is retained so missing trend coverage is visible rather than silently omitted.</div>'
        note = weekly_trend.get("interpretation") or "Week-over-week movement uses validated weekly archives in the selected calendar month."
        trend_body += f'<p class="footnote">{esc(note)}</p>'
        out.append(section("Week-over-week trend", f'{esc(weekly_trend.get("month_label") or "Calendar-month weekly movement")} · adverse direction is red; contextual movement remains neutral.', trend_body, weekly_trend.get("status", "available"), "trend"))

    important_curation = {"curation-decisions", "curation-retained-window", "curation-blocked", "curation-block-rate", "curation-users", "curation-repos", "unique-blocked-packages"}
    curation_metrics = leadership_lens("Package requests evaluated, allowed or blocked before consumption, plus who and which repositories used the control.", "Curation reduces risky dependency intake before it becomes remediation work, while revealing developer friction and policy reach.", "Tune blocking policy, resolve repeat demand, expand governed repositories and review exceptions.")
    curation_metrics += '<div class="grid" style="margin-top:14px">' + "".join(card(x) for x in curation["metrics"] if x.get("id") in important_curation) + '</div>'
    curation_charts = '<div class="split" style="margin-top:14px">' + bar_panel("Decisions by ecosystem", curation["events_by_package_type"]) + bar_panel("Blocked-request reasons", curation["top_block_reasons"]) + '</div>'
    blocked_rows = [(x["package"], x["ecosystem"], x["count"]) for x in curation["top_blocked"][:10]]
    user_rows = [(x["user"], x["requests"], x["blocked"], x["repos"], x["packages"]) for x in curation["top_users"]]
    curation_tables = '<div class="split" style="margin-top:14px">' + data_table("Most frequently blocked packages", ["Package", "Ecosystem", "Blocks"], blocked_rows) + data_table("Most active requester identities", ["Identity", "Requests", "Blocked", "Repos", "Packages"], user_rows) + '</div>'
    interpretation = '<div style="margin-top:14px">' + summary_panel(curation.get("interpretation", [])) + '</div>' if curation.get("interpretation") else ''
    curation_body = curation_metrics + curation_charts + curation_tables
    if curation.get("show_configuration", True):
        inventory = curation["policy_inventory"]
        policy_cards = [
            {"id":"curation-active-blocking-policies","classification":"observed","label":"Active blocking policies","value":inventory["block_active"],"unit":"policies","source":"Curation policy API","formula":"enabled + action=block"},
            {"id":"curation-active-dry-run-policies","classification":"observed","label":"Active dry-run policies","value":inventory["dry_run_active"],"unit":"policies","source":"Curation policy API","formula":"enabled + action=dry_run"},
            {"id":"curation-cache-enforcing-policies","classification":"derived","label":"Blocking from cache","value":inventory["cache_enforcing"],"unit":"policies","source":"Curation policy API","formula":"block policies with block_from_cache=true"},
            {"id":"curation-cache-gap-policies","classification":"derived","label":"Not blocking cached packages","value":inventory.get("cache_not_enforcing"),"unit":"policies","source":"Curation policy API","formula":"blocking policies − cache enforcing"}
        ]
        policy_grid = '<h3 class="subhead">Policy violation insights</h3><div class="grid" style="margin-top:14px">' + "".join(map(card, policy_cards)) + '</div>'
        policy_lifecycle = data_table("Policy lifecycle inventory", ["State", "Policies", "Interpretation"], [
            ("Registered", inventory["registered"], "All configured policies, including inactive policy definitions"),
            ("Enabled", inventory["enabled"], "Policies currently enabled for block or dry-run evaluation"),
            ("Disabled", max(0, inventory["registered"]-inventory["enabled"]), "Configured policies that currently have no enforcement effect")])
        blocking_policy_types = curation.get("blocking_policies_by_risk") or []
        left_policy_chart = bar_panel("Blocking policies by type", blocking_policy_types) if blocking_policy_types else bar_panel("Enabled policies by risk type", inventory["by_risk_type"])
        policy_charts = '<div class="split" style="margin-top:14px">' + left_policy_chart + bar_panel("Blocking events per policy", curation["top_policies"]) + '</div>'
        waiver = curation["waivers"]
        waiver_cards = [
            {"classification":"observed","label":"Pending waivers","value":waiver["pending"],"unit":"requests","source":"Curation waiver API","formula":"status=pending"},
            {"classification":"observed","label":"Approved waivers","value":waiver["approved"],"unit":"requests","source":"Curation waiver API","formula":"status=approved"},
            {"classification":"observed","label":"Rejected waivers","value":waiver["rejected"],"unit":"requests","source":"Curation waiver API","formula":"status=rejected"},
            {"classification":"derived","label":"Oldest pending waiver","value":waiver["pending_aging"]["oldest_pending_days"],"unit":"days","source":"Curation waiver API","formula":"report date − created_at"}
        ]
        waiver_grid = '<div class="grid" style="margin-top:14px">' + "".join(map(card, waiver_cards)) + '</div>'
        waiver_age = bar_panel("Pending waiver aging", [(x["label"],x["count"]) for x in waiver["pending_aging"]["buckets"]])
        curation_body += policy_charts
        curation_body += policy_grid + '<div style="margin-top:14px">' + policy_lifecycle + '</div>' + waiver_grid + '<div style="margin-top:14px">' + waiver_age + '</div>'
    curation_body += interpretation
    if "curation" in enabled:
        coverage = curation.get("coverage_label") or ("Complete period collection" if curation.get("status") == "available" else "Historical coverage limitation")
        out.append(section("Curation", f'{coverage}: {number(curation["collection"].get("rows_fetched"))} retained decisions; requester identities may include service tokens.', curation_body, curation.get("status", "unavailable"), "curation"))

    platform = leadership_lens("The repository estate and, when captured at period end, storage and artifact-flow posture.", "Artifactory is the operating foundation for trusted software delivery; estate growth affects resilience, governance and cost.", "Review capacity, repository lifecycle, platform standardization and ownership.")
    platform += '<div class="grid five" style="margin-top:14px">' + "".join(map(card, data["platform"]["metrics"])) + '</div>'
    art = data.get("artifactory_detail") or {}
    if art:
        available_art_metrics = [item for item in art.get("metrics", []) if item.get("classification") != "unavailable"]
        platform += '<h3 class="subhead">Storage and efficiency</h3><div class="grid">' + "".join(map(card, available_art_metrics)) + '</div>'
        traffic = art.get("traffic_evidence") or {}
        if traffic:
            delta = traffic.get("period_delta") or {}
            counters = traffic.get("counters") or {}
            traffic_rows = [
                ("Baseline collected", traffic.get("collected_at")),
                ("Cumulative successful download requests", number(counters.get("download_requests_total"))),
                ("Cumulative successful upload requests", number(counters.get("upload_requests_total"))),
                ("Download delta for report period", number(delta.get("download_requests_delta"))),
                ("Upload delta for report period", number(delta.get("upload_requests_delta"))),
                ("Cache hit rate", number(delta.get("cache_fs_hit_rate"))),
            ]
            platform += '<h3 class="subhead">Artifact traffic counters</h3>' + data_table(
                "Traffic evidence", ["Measure", "Value"], traffic_rows)
            platform += '<p class="footnote">The cumulative baseline is current-state evidence. A monthly delta is shown only when both bounding snapshots exist; a missing boundary remains Unavailable rather than being reported as zero.</p>'
        platform += '<div class="split" style="margin-top:14px">' + bar_panel("Repository types", art.get("repository_types", [])) + bar_panel("Repository package types", art.get("package_types", [])) + '</div>'
        top_storage = [(x["repository"], x["used_space"], x["files"], x["package_type"], x["project"]) for x in art.get("top_storage", [])]
        platform += '<div style="margin-top:14px">' + data_table("Largest repositories by stored bytes", ["Repository", "Storage", "Files", "Package type", "Project"], top_storage) + '</div>'
        platform += '<div style="margin-top:14px">' + summary_panel(art.get("interpretation", [])) + '</div>'
    else:
        platform += '<div style="margin-top:14px">' + bar_panel("Repository package types", data["platform"]["package_types"]) + '</div>'
    if "artifactory" in enabled and data.get("platform", {}).get("metrics"):
        out.append(section("Artifactory", f'Repository, storage and available artifact-traffic evidence. Period deltas are calculated only from matching boundary snapshots.', platform, "snapshot", "artifactory"))

    xray_body = leadership_lens("New vulnerability and license-policy findings in the month, plus period-end indexing coverage when a snapshot exists.", "Xray shows both the rate of new risk entering the estate and whether scanning coverage is broad enough to trust the conclusion.", "Prioritize critical intake, close coverage gaps and direct remediation to the most affected repositories.")
    xray_body += '<div class="grid" style="margin-top:14px">' + "".join(map(card, xray["metrics"])) + '</div>'
    if xray.get("policy_types") or xray.get("indexed_ecosystems"):
        xray_body += '<div class="split" style="margin-top:14px">' + bar_panel("Xray policy types", list(xray["policy_types"].items())) + bar_panel("Indexed ecosystems", xray.get("indexed_ecosystems", [])) + '</div>'
    if xray.get("violations_by_severity"):
        xray_body += '<h3 class="subhead">Period risk posture</h3><div class="split">' + bar_panel("New violations by severity", xray["violations_by_severity"]) + bar_panel("New violations by type", xray.get("violations_by_type", [])) + '</div>'
        xray_body += '<div class="split" style="margin-top:14px">' + data_table("Most frequent CVEs", ["CVE", "Occurrences"], xray.get("top_cves", [])) + data_table("Most affected repositories", ["Repository", "Affected artifact paths"], xray.get("top_affected_repositories", [])) + '</div>'
    if xray.get("severity_thresholds"):
        governance = xray.get("governance", {})
        xray_body += '<h3 class="subhead">Governance</h3><div class="split">' + bar_panel("Configured minimum-severity thresholds", xray["severity_thresholds"]) + data_table("Policy controls", ["Control", "Rules"], [("Fix-version dependent", governance.get("fix_version_dependent_rules", 0)), ("Applicable CVEs only", governance.get("applicable_only_rules", 0)), ("Not assigned to active watch", len(governance.get("unassigned_policy_names", [])))]) + '</div>'
    xray_body += f'<div class="callout" style="margin-top:14px">{esc(xray["collection_note"])}</div>'
    if "xray" in enabled:
        out.append(section("Xray", f'Period activity is scoped to {esc(meta.get("period_label"))}; coverage appears only when a period-end snapshot exists.', xray_body, xray["status"], "xray"))

    ai = data["ai_catalog"]
    current_ai = data.get("current_ai_security") or {}
    ai_body = leadership_lens("Approved AI assets, Shadow AI models, MCP servers, skills and plugins, separated from their underlying repository footprint.", "This exposes ungoverned AI adoption and establishes whether agentic tools enter through approved, scanned paths.", "Bring unmanaged models under governance, close scan gaps and align allowed assets with project need.")
    ai_body += f'<h3 class="subhead">{esc(meta.get("period_label"))} repository footprint</h3><div class="grid">' + "".join(map(card, ai["metrics"])) + '</div>'
    if ai.get("repositories_by_type") or ai.get("repositories_by_repository_type"):
        ai_body += '<div class="split" style="margin-top:14px">' + bar_panel("AI and agent repository types", ai["repositories_by_type"]) + bar_panel("Repository configuration type", ai.get("repositories_by_repository_type", [])) + '</div>'
    if ai.get("top_storage"):
        ai_rows = [(x["repository"], x["used_space"], x["files"], x["package_type"], x["project"]) for x in ai["top_storage"]]
        ai_body += '<div style="margin-top:14px">' + data_table("Largest AI and agent repositories", ["Repository", "Storage", "Files", "Type", "Project"], ai_rows) + '</div>'
    inventory = current_ai.get("inventory") or {}
    shadow = current_ai.get("shadow_ai") or {}
    if (inventory.get("models") or {}).get("allowed_by_origin"):
        ai_body += '<div class="split" style="margin-top:14px">' + bar_panel("Allowed models by origin", list(inventory["models"]["allowed_by_origin"].items())) + bar_panel("Allowed MCP servers by type", list((inventory.get("mcp_servers") or {}).get("allowed_by_type", {}).items())) + '</div>'
    if shadow.get("visible_assets"):
        ai_body += '<div style="margin-top:14px">' + data_table("Shadow AI model governance", ["Model", "Management status"], [(x.get("name"), x.get("management_status")) for x in shadow["visible_assets"]]) + '</div>'
    if current_ai:
        ai_body += f'<div class="current-posture-banner"><strong>Current AI security posture</strong><span>As of {esc(current_ai.get("as_of") or "Unavailable")} · not attributed to {esc(meta.get("period_label"))}</span></div>'
        ai_body += '<div class="grid current-ai-metrics">' + "".join(map(card, current_ai.get("metrics") or [])) + '</div>'
    ai_body += '<h3 class="subhead">Current security and project attribution by AI asset type</h3>'
    asset_blocks = []
    for key, title, singular in (
        ("mcp_servers", "MCP servers", "MCP server"),
        ("skills", "Skills", "Skill"),
        ("plugins", "Plugins", "Plugin"),
        ("models", "Models", "Model"),
    ):
        asset = inventory.get(key) or {}
        if asset.get("security_counts") or asset.get("visible_assets"):
            asset_blocks.append(f'<section class="ai-asset-group"><h3>{esc(title)}</h3>{asset_security_block(title, singular, asset)}</section>')
    if asset_blocks:
        ai_body += '<div class="ai-asset-groups">' + ''.join(asset_blocks) + '</div>'
        ai_body += '<p class="footnote">Security status is kept separate for every asset class. N/A means the catalog did not expose a completed scan result; it is not treated as Not malicious.</p>'
    if current_ai.get("evidence_limitations"):
        ai_body += '<div class="callout neutral" style="margin-top:14px">' + '<br>'.join(esc(x) for x in current_ai["evidence_limitations"]) + '</div>'
    ai_body += f'<div class="callout" style="margin-top:14px">{esc(current_ai.get("note") or ai.get("note", "Repository inventory proves governed footprint, not active consumption, provenance or realized security value."))}</div>'
    if "ai-security" in enabled and ai.get("metrics"):
        out.append(section("AI security", "AI models, MCP servers, skills and agent repositories, with managed and unmanaged assets kept distinct.", ai_body, ai["status"], "ai-security"))

    if access.get("metrics") and "access" in enabled:
        access_body = leadership_lens("Access-token lifecycle and OIDC trust mappings used by automation and CI/CD.", "Long-lived, unused or non-expiring credentials increase blast radius; OIDC replaces stored secrets with scoped, short-lived trust.", "Rotate near-expiry tokens, remove unused credentials and verify repository claim patterns and token TTLs.")
        access_body += '<div class="grid" style="margin-top:14px">' + ''.join(map(card, access["metrics"])) + '</div>'
        posture = access.get("token_posture") or {}
        next_7 = posture.get("expires_within_7_days")
        next_30 = posture.get("expires_within_30_days")
        days_8_30 = max(0, (next_30 or 0) - (next_7 or 0))
        access_body += '<h3 class="subhead">Credential rotation operations</h3><div class="rotation-summary">' + ''.join([
            f'<div class="rotation-step {"risk-bad" if (next_7 or 0) > 0 else ""}"><strong>{number(next_7)}</strong><span>Rotate within 7 days</span></div>',
            f'<div class="rotation-step {"risk-bad" if days_8_30 > 0 else ""}"><strong>{number(days_8_30)}</strong><span>Schedule for days 8–30</span></div>',
            f'<div class="rotation-step {"risk-bad" if (posture.get("non_expiring") or 0) > 0 else ""}"><strong>{number(posture.get("non_expiring"))}</strong><span>Review non-expiring tokens</span></div>',
            f'<div class="rotation-step {"risk-bad" if (posture.get("never_used") or 0) > 0 else ""}"><strong>{number(posture.get("never_used"))}</strong><span>Validate or revoke never-used tokens</span></div>',
        ]) + '</div>'
        queue = access.get("rotation_queue") or []
        if queue:
            queue_table = data_table("30-day token rotation queue", ["Safe reference", "Owner", "Description", "Expires", "Days left", "Last used"], [(x.get("reference"),x.get("owner"),x.get("description"),x.get("expires_at"),x.get("days_remaining"),x.get("last_used")) for x in queue])
            access_body += disclosure("Open the 30-day token rotation queue", queue_table + f'<p class="footnote">{esc(access.get("privacy_note"))}</p>', True)
        access_body += disclosure("Expired and revoked token history", esc(access.get("note")), True)
        access_body += '<div style="margin-top:14px">' + bar_panel("OIDC providers by family", access.get("providers_by_family", [])) + '</div>'
        patterns = access.get("repository_claim_patterns") or []
        if patterns:
            oidc_table = data_table("Repositories and patterns trusted through OIDC", ["Provider family", "Provider", "Mapping", "Claim", "Repository pattern"], [(x.get("provider_family"),x.get("provider"),x.get("mapping"),x.get("claim"),x.get("pattern")) for x in patterns])
            access_body += disclosure("Open OIDC repository trust mappings", oidc_table, True)
        out.append(section("Access, tokens & OIDC", f'Point-in-time governance snapshot collected {esc(access.get("collected_at"))}.', access_body, access.get("status"), "access"))

    jas = data["jas"]
    jas_body = leadership_lens("Contextual analysis and advanced security signals that distinguish applicable risk from vulnerable components that are not actionable in context.", "JAS reduces remediation noise and concentrates engineering time on exploitable, reachable or otherwise actionable findings.", "Prioritize applicable findings, refresh incomplete analysis and connect fixes to release work.")
    jas_body += '<h3 class="subhead">Prioritized application risk</h3><div class="grid">' + "".join(map(card, jas["metrics"])) + '</div>'
    if jas.get("capabilities"):
        jas_body += '<div style="margin-top:14px">' + bar_panel("Enabled JAS policy capabilities", jas["capabilities"]) + '</div>'
    if jas.get("applicability"):
        jas_body += '<h3 class="subhead">Applicability and prioritization</h3><div style="margin-top:14px">' + bar_panel("Contextual analysis results", jas["applicability"]) + '</div>'
    if jas.get("policy_names"):
        jas_body += '<div style="margin-top:14px">' + data_table("Policies with JAS criteria", ["Policy"], [(x,) for x in jas["policy_names"]]) + '</div>'
    jas_body += f'<div class="callout" style="margin-top:14px">{esc(jas["note"])}</div>'
    if "jas" in enabled:
        out.append(section("JFrog Advanced Security (JAS)", "Exploitability, advanced scanning coverage and actionable application risk.", jas_body, jas["status"], "jas"))

    runtime = data.get("runtime")
    if runtime and runtime.get("metrics") and "runtime" in enabled:
        runtime_body = leadership_lens("Production image population, vulnerabilities applicable in running workloads, fix availability and integrity signals.", "Runtime context narrows the security queue to exposure that is present in production and can reveal drift after release.", "Escalate malicious or integrity findings and prioritize applicable vulnerabilities with fixes.")
        runtime_body += '<h3 class="subhead">Vulnerability prioritization</h3><div class="grid">' + "".join(map(card, runtime["metrics"][:4])) + '</div>'
        runtime_body += '<h3 class="subhead">Live assessment highlights</h3><div class="grid">' + "".join(map(card, runtime["metrics"][4:])) + '</div>'
        if runtime.get("running_image_trend"):
            runtime_body += '<div style="margin-top:14px">' + data_table("Running-image risk trend", ["Date", "Running image tags", "Critical/high/applicable"], [(x.get("date"), x.get("running_image_tags"), x.get("critical_high_applicable")) for x in runtime["running_image_trend"]]) + '</div>'
        runtime_body += f'<div class="callout" style="margin-top:14px">{esc(runtime.get("note"))}</div>'
        out.append(section("Runtime security prioritization", "Production-only context: running images, applicable vulnerabilities, fixes and integrity signals.", runtime_body, runtime.get("status", "available")))

    if "economic" in enabled and model.get("status") == "benchmark":
        summary_econ = model.get("summary") or {}
        benchmark_cards = [
            ("Benefits PV", summary_econ.get("benefits_pv_usd")), ("Costs PV", summary_econ.get("costs_pv_usd")),
            ("Net present value", summary_econ.get("npv_usd")), ("ROI", f'{summary_econ.get("roi_percent")}%'),
            ("Payback", summary_econ.get("payback")),
        ]
        cards_html = '<div class="scenario-grid">' + ''.join(
            f'<div class="scenario"><span class="tag benchmark">benchmark</span><h3>{esc(label)}</h3><div class="value">{esc(value if label in {"ROI", "Payback"} else currency_value(value, "USD"))}</div><div class="metric-note">Forrester composite organization · not a customer result</div></div>'
            for label, value in benchmark_cards) + '</div>'
        categories = data_table("Three-year benefit categories", ["Category", "Present value (USD)"],
                                [(key.replace("_", " ").title(), currency_value(value, "USD")) for key, value in (model.get("benefit_categories") or {}).items()])
        composite = data_table("Composite organization", ["Input", "Value"],
                               [(key.replace("_", " ").title(), value) for key, value in (model.get("composite") or {}).items()])
        methods = data_table("Reusable TEI methodology inputs", ["Model", "Value per unit", "Risk adjustment", "Source formula"],
                             [(key.replace("_", " ").title(), currency_value(row.get("value_per_unit_usd"), "USD"), row.get("risk_adjustment"), row.get("source_formula")) for key, row in (model.get("methodology_inputs") or {}).items()])
        draft_note = " A draft customer profile exists but is not applied." if (model.get("profile") or {}).get("status") == "draft" else ""
        economic_body = f'<div class="callout neutral"><strong>External benchmark only.</strong> {esc(model.get("disclaimer"))}{esc(draft_note)}</div>{cards_html}<div style="margin-top:14px">{categories}</div><div style="margin-top:14px">{composite}</div><div style="margin-top:14px">{methods}</div>'
        out.append(section("Economic context", "External benchmark context, kept separate from customer-observed and projected evidence.", economic_body, "benchmark", "economic"))
    elif "economic" in enabled and model.get("status") == "projected":
        currency = model.get("currency")
        scenarios = model.get("scenarios") or {}
        scenario_html = '<div class="scenario-grid">' + ''.join(f'<div class="scenario {name}"><span class="tag projected">{esc(name)}</span><h3>Annual benefit scenario</h3><div class="value">{esc(currency_value(value, currency))}</div><div class="metric-note">Customer-approved projection · confidence: {esc(model.get("confidence"))}</div></div>' for name, value in scenarios.items()) + '</div>'
        summary_rows = [(key.replace("_", " ").title(), (f'{value}%' if key == "roi_percent" and value is not None else currency_value(value, currency) if key not in {"payback_years", "discount_rate"} else value)) for key, value in (model.get("summary") or {}).items()]
        benefits = data_table("Projected benefit categories", ["Category", "Expected annual benefit"], [(key.replace("_", " ").title(), currency_value(value, currency)) for key, value in (model.get("benefit_categories") or {}).items()])
        details = data_table("Projection inputs", ["Model", "Baseline", "Value per unit", "Source", "Coverage", "Realization", "Expected"], [(row.get("label"), row.get("baseline_units"), currency_value(row.get("value_per_unit"), currency), row.get("value_source"), row.get("adoption_coverage"), row.get("realization_factor"), currency_value((row.get("scenarios") or {}).get("expected"), currency)) for row in model.get("projections", [])])
        economic_body = f'<div class="callout neutral"><strong>Projected, not observed.</strong> {esc(model.get("disclaimer"))}</div>{scenario_html}<div style="margin-top:14px">{data_table("Customer economic summary", ["Measure", "Value"], summary_rows)}</div><div style="margin-top:14px">{benefits}</div><div style="margin-top:14px">{details}</div><div class="formula">{esc(model.get("formula"))}</div>'
        out.append(section("Economic context", "Deterministic scenarios from an explicitly approved per-instance profile.", economic_body, "projected", "economic"))

    summary = data.get("executive_summary") or {}
    actions = []
    for index, item in enumerate(summary.get("actions", [])[:5]):
        actions.append({"priority": "P1" if index == 0 else "P2", "title": item.get("title"), "detail": item.get("detail"), "owner": "Platform & Security leadership", "reason": "Period evidence", "target": "7 days" if index == 0 else "30 days"})
    if access.get("metrics"):
        posture = access.get("token_posture") or {}
        if posture.get("expires_within_7_days"):
            actions.insert(0, {"priority":"P1","title":f'Rotate {posture.get("expires_within_7_days"):,} tokens expiring within 7 days',"detail":"Assign each credential to an owner, rotate it before expiry and verify the dependent workload after cutover.","owner":"IAM / Platform engineering","reason":"Access token snapshot","target":"7 days"})
        if posture.get("non_expiring"):
            actions.append({"priority":"P2","title":f'Review {posture.get("non_expiring"):,} non-expiring tokens',"detail":"Replace stored long-lived credentials with bounded TTLs or OIDC where the workload supports it.","owner":"IAM / Platform engineering","reason":"Credential blast-radius reduction","target":"30 days"})
    if actions and "recommendations" in enabled:
        out.append(section("Recommended actions", "Prioritized operating decisions with an accountable owner and time horizon.", priority_panel(actions[:7]), anchor="recommendations"))

    limitations = ''.join(f'<div>• {esc(x)}</div>' for x in data["limitations"])
    availability = data_table(
        "Reporting capability roadmap", ["Area", "Current status", "Why", "What enables it"],
        [(x.get("area"), x.get("status"), x.get("current_state"), x.get("next_step"))
         for x in data.get("availability_notes", [])],
    ) if data.get("availability_notes") else ""
    xray_ledger = ("Observed / derived", f'{meta.get("period_label")} watch violations; deduplicated issue/resource occurrences') if xray_has_findings else ("Unavailable", "No zero substituted")
    ledger_rows=[("Curation activity","Observed / derived",f'Bounded {meta.get("period_label")} audit activity'),("Xray period findings",xray_ledger[0],xray_ledger[1]),("JAS applicability","Derived","Applicability details in period findings; not added to Xray occurrence totals")]
    if data.get("platform",{}).get("metrics"): ledger_rows.insert(0,("Artifactory estate","Observed / derived","Preserved period-end repository snapshot"))
    ledger = data_table("Evidence classification", ["Area","Classification","Interpretation"], ledger_rows)
    if "evidence" in enabled:
        out.append(section("Methodology & evidence notes", "Compact provenance notes for readers who need to validate interpretation.", ledger + availability + f'<div class="callout neutral" style="margin-top:14px">{limitations}</div>', anchor="evidence"))
    return ''.join(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--modules", default="all", help="Comma-separated module IDs from assets/report-sections.json; default all")
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    if data.get("schema_version") != "0.3":
        raise ValueError("report JSON must use schema_version 0.3")
    template = args.template.read_text(encoding="utf-8")
    requested = MODULES if args.modules == "all" else {item.strip() for item in args.modules.split(",") if item.strip()}
    unknown = requested - MODULES
    if unknown:
        raise ValueError(f"unknown report modules: {', '.join(sorted(unknown))}")
    replacements = {
        "__JFROG_PLATFORM_REPORT_DATA__": esc(json.dumps(data, separators=(",", ":"), ensure_ascii=False)),
        "<!--JFROG_LOGO-->": (args.template.parent / "jfrog-logo-white.svg").read_text(encoding="utf-8"),
        "<!--REPORT_TYPE-->": esc(data["meta"]["report_type"]),
        "<!--REPORT_RANGE-->": esc(f'{data["meta"]["date_from"]} – {data["meta"]["date_to"]}'),
        "<!--REPORT_SERVER-->": esc(data["meta"]["server_id"]),
        "<!--REPORT_PERSONA-->": esc(data["meta"].get("persona", "Platform, security and technology leadership")),
        "<!--JFROG_PLATFORM_REPORT_STATIC-->": static_report(data, requested),
    }
    rendered = template
    for key,value in replacements.items():
        rendered = rendered.replace(key,value)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
