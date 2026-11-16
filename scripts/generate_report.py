#!/usr/bin/env python3
"""Deterministically calculate and render a JFrog Platform value and risk report."""

from __future__ import annotations

import argparse
import base64
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

CLASSIFICATIONS = {"observed", "derived", "projected", "benchmark", "unavailable"}
SOURCE_STATUSES = {"available", "partial", "no_data", "permission_denied", "unlicensed", "unsupported", "not_configured", "collection_failed"}
PROFILES = {"executive", "adoption", "efficiency", "delivery", "security-value", "full", "curation", "xray", "artifactory", "ai-security", "jas"}
GLOSSARY_PATH = Path(__file__).resolve().parent.parent / "assets" / "metric-glossary.json"
METRIC_GLOSSARY = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))


def dec(value: object) -> Decimal:
    return Decimal(str(value))


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(evidence: dict, assumptions: dict) -> None:
    require(evidence.get("schema_version") == "0.1", "unsupported evidence schema_version")
    require(evidence.get("mode") in {"artifactory-only", "artifactory-xray", "full-platform", "offline-demo"}, "invalid mode")
    for key in ("period", "reporting", "sources", "artifactory"):
        require(key in evidence, f"evidence missing {key}")
    require(evidence["reporting"].get("cadence") in {"weekly", "monthly", "custom"}, "invalid reporting cadence")
    for source in evidence["sources"]:
        require(source.get("status") in SOURCE_STATUSES, f"invalid source status: {source.get('id')}")
        require(isinstance(source.get("complete"), bool), f"source complete must be boolean: {source.get('id')}")
    art = evidence["artifactory"]
    for key in ("repositories_total", "local_repositories", "remote_repositories", "virtual_repositories", "storage_bytes", "artifacts_total"):
        require(isinstance(art.get(key), int) and art[key] >= 0, f"invalid artifactory.{key}")
    require(assumptions.get("status") in {"not_configured", "customer_provided"}, "invalid assumptions status")
    if assumptions["status"] == "not_configured":
        require(assumptions.get("currency") is None and assumptions.get("annual_cost") is None and assumptions.get("discount_rate") is None, "unconfigured assumptions must not contain financial values")
        require(assumptions.get("projections") == [], "unconfigured assumptions must not contain projections")
        return
    require(isinstance(assumptions.get("currency"), str) and len(assumptions["currency"]) == 3 and assumptions["currency"].isupper(), "currency must be an ISO-style three-letter uppercase code")
    require(dec(assumptions.get("annual_cost", -1)) >= 0, "annual_cost must be non-negative")
    require(Decimal("0") <= dec(assumptions.get("discount_rate", -1)) <= Decimal("1"), "discount_rate must be between 0 and 1")
    seen: set[str] = set()
    for projection in assumptions.get("projections", []):
        key = projection.get("benefit_key")
        require(bool(key), f"projection {projection.get('id')} missing benefit_key")
        require(key not in seen, f"benefit double counting detected: {key}")
        seen.add(key)
        for factor in ("baseline_units", "value_per_unit", "adoption_coverage", "realization_factor", "conservative_factor", "expected_factor", "optimistic_factor"):
            require(dec(projection.get(factor, -1)) >= 0, f"projection {projection.get('id')} has invalid {factor}")
        require(dec(projection["adoption_coverage"]) <= 1 and dec(projection["realization_factor"]) <= 1, f"projection {projection.get('id')} has factor over 1")


def metric(mid: str, label: str, classification: str, value: object, unit: str, sources: list[str], formula: str, confidence: str = "high", data_gaps: list[str] | None = None) -> dict:
    require(classification in CLASSIFICATIONS, f"invalid classification for {mid}")
    explanation = METRIC_GLOSSARY.get(mid, {})
    return {"id": mid, "label": label, "classification": classification, "value": value, "unit": unit,
            "sources": sources, "formula": formula, "confidence": confidence, "data_gaps": data_gaps or [],
            "meaning": explanation.get("meaning", f"This is the reported value for {label.lower()}."),
            "why_it_matters": explanation.get("why", "Use this value with its source, period, and evidence classification before drawing a conclusion.")}


def projection_metric(row: dict, currency: str) -> dict:
    baseline = dec(row["baseline_units"])
    value_per_unit = dec(row["value_per_unit"])
    coverage = dec(row["adoption_coverage"])
    realization = dec(row["realization_factor"])
    base = baseline * value_per_unit * coverage * realization
    scenarios = {name: base * dec(row[f"{name}_factor"]) for name in ("conservative", "expected", "optimistic")}
    result = metric(row["id"], row.get("label", row["id"]), "projected", money(scenarios["expected"]), currency, [f"assumption:{row['benefit_key']}"], "baseline_units × value_per_unit × adoption_coverage × realization_factor × scenario_factor", row.get("confidence", "low"), ["Requires customer validation"])
    result["category"] = row["category"]
    result["benefit_key"] = row["benefit_key"]
    result["projection"] = {
        "baseline": str(baseline), "assumptions": row, "applicability": row.get("applicability", "Customer-defined"),
        "adoption_coverage": str(coverage), "realization_factor": str(realization), "value_per_unit": str(value_per_unit),
        "conservative": money(scenarios["conservative"]), "expected": money(scenarios["expected"]), "optimistic": money(scenarios["optimistic"]),
        "confidence_level": row.get("confidence", "low"), "data_gaps": ["Customer assumption; not observed platform value"]
    }
    return result


def calculate(evidence: dict, assumptions: dict, profile: str) -> dict:
    validate(evidence, assumptions)
    art = evidence["artifactory"]
    currency = assumptions.get("currency")
    observed = [
        metric("repositories-total", "Repositories", "observed", art["repositories_total"], "count", ["artifactory-repositories"], "count(repositories)"),
        metric("artifacts-total", "Artifacts", "observed", art["artifacts_total"], "count", ["artifactory-storage"], "storage summary artifact count"),
        metric("storage-tib", "Storage", "derived", str((dec(art["storage_bytes"]) / dec(2**40)).quantize(Decimal("0.01"))), "TiB", ["artifactory-storage"], "storage_bytes / 2^40"),
    ]
    if art.get("downloads") is not None:
        observed.append(metric("downloads", "Downloads", "observed", art["downloads"], "count", ["artifactory-downloads"], "count(download events)"))
    if art.get("builds_published") is not None:
        observed.append(metric("builds-published", "Builds published", "observed", art["builds_published"], "count", ["artifactory-build-info"], "count(build-info records)"))
    reporting = evidence["reporting"]
    previous = reporting.get("previous_period") or {}
    period_activity = {
        "downloads": art.get("downloads"), "downloads_previous": previous.get("downloads"),
        "builds_published": art.get("builds_published"), "builds_previous": previous.get("builds_published"),
    }
    for current_key, previous_key, delta_key in (("downloads", "downloads_previous", "downloads_delta_pct"), ("builds_published", "builds_previous", "builds_delta_pct")):
        current, prior = period_activity[current_key], period_activity[previous_key]
        period_activity[delta_key] = None if current is None or prior in (None, 0) else str(((dec(current) - dec(prior)) / dec(prior) * 100).quantize(Decimal("0.1")))
    projections = [projection_metric(row, currency) for row in assumptions.get("projections", [])]
    scenario_totals = {name: sum((dec(p["projection"][name]) for p in projections), Decimal("0")) for name in ("conservative", "expected", "optimistic")}
    if assumptions["status"] == "not_configured":
        financial = {
            "available": False, "classification": "unavailable", "currency": None,
            "reason": "Customer financial assumptions were not provided.",
            "annual_benefit": None, "annual_cost": None, "net_annual_benefit": None,
            "three_year_benefit": None, "three_year_cost": None, "net_present_value": None,
            "roi_percent": None, "payback_years": None, "benefit_by_category": {}, "sensitivity": {}
        }
    else:
        annual_cost = dec(assumptions["annual_cost"])
        annual_benefit = scenario_totals["expected"]
        net = annual_benefit - annual_cost
        three_benefit = annual_benefit * 3
        three_cost = annual_cost * 3
        rate = dec(assumptions["discount_rate"])
        npv = sum(net / ((Decimal("1") + rate) ** year) for year in (1, 2, 3))
        roi = None if three_cost == 0 else ((three_benefit - three_cost) / three_cost * 100)
        payback = None if annual_benefit == 0 else annual_cost / annual_benefit
        by_category: dict[str, Decimal] = {}
        for item in projections:
            by_category[item["category"]] = by_category.get(item["category"], Decimal("0")) + dec(item["projection"]["expected"])
        financial = {
            "available": True, "currency": currency, "annual_benefit": money(annual_benefit), "annual_cost": money(annual_cost), "net_annual_benefit": money(net),
            "three_year_benefit": money(three_benefit), "three_year_cost": money(three_cost), "net_present_value": money(npv),
            "roi_percent": None if roi is None else money(roi), "payback_years": None if payback is None else money(payback),
            "benefit_by_category": {k: money(v) for k, v in sorted(by_category.items())},
            "sensitivity": {k: money(v) for k, v in scenario_totals.items()}, "classification": "projected"
        }
    profile_modules = {
        "executive": ["estate", "financial", "opportunities", "coverage"], "adoption": ["estate", "coverage"],
        "efficiency": ["estate", "financial", "opportunities"], "delivery": ["estate", "coverage"],
        "security-value": ["coverage"], "full": ["estate", "financial", "opportunities", "coverage"],
        "curation": ["curation"], "xray": ["xray"], "artifactory": ["artifactory"],
        "ai-security": ["ai-security"], "jas": ["jas"]
    }
    return {
        "schema_version": "0.1", "profile": profile, "mode": evidence["mode"], "period": reporting["period"],
        "reporting": reporting, "period_activity": period_activity, "year_to_date": evidence.get("year_to_date", {}),
        "modules": profile_modules[profile], "metrics": observed + projections, "financial": financial,
        "sources": evidence["sources"], "limitations": ["Financial value is unavailable until customer assumptions are explicitly provided.", "Optional products are reported as unavailable rather than zero."],
    }


def render(report: dict, template_path: Path) -> str:
    template = template_path.read_text(encoding="utf-8")
    require(template.count("__JFROG_PLATFORM_REPORT_DATA__") == 1, "template must contain one data placeholder")
    return (template
            .replace("__JFROG_PLATFORM_REPORT_DATA__", json.dumps(report, separators=(",", ":"), ensure_ascii=False))
            .replace("__JFROG_OPEN_SANS_FONT__", base64.b64encode((template_path.parent / "OpenSans-Variable.ttf").read_bytes()).decode("ascii")))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--assumptions", required=True, type=Path)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="executive")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    assumptions = json.loads(args.assumptions.read_text(encoding="utf-8"))
    report = calculate(evidence, assumptions, args.profile)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "data.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    template = Path(__file__).resolve().parent.parent / "assets" / "dashboard.html"
    (args.output / "report.html").write_text(render(report, template), encoding="utf-8")
    print(args.output / "report.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
