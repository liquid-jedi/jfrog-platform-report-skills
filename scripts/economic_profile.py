#!/usr/bin/env python3
"""Resolve, validate and calculate deterministic economic-report context."""

from __future__ import annotations

import json
import os
import re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


def dec(value) -> Decimal:
    return Decimal(str(value))


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def default_profile_path(server: str, environment: dict[str, str] | None = None) -> Path:
    env = environment or dict(os.environ)
    if env.get("JFROG_REPORT_ECONOMIC_PROFILE"):
        return Path(env["JFROG_REPORT_ECONOMIC_PROFILE"]).expanduser()
    if env.get("JFROG_REPORT_CONFIG"):
        root = Path(env["JFROG_REPORT_CONFIG"]).expanduser().parent
    elif env.get("XDG_CONFIG_HOME"):
        root = Path(env["XDG_CONFIG_HOME"]).expanduser() / "jfrog-platform-value-report"
    elif os.name == "nt" and env.get("APPDATA"):
        root = Path(env["APPDATA"]) / "JFrog" / "PlatformValueReport"
    else:
        root = Path.home() / ".config" / "jfrog-platform-value-report"
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", server)
    return root / "instances" / slug / "economic-profile.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_profile(server: str, explicit: Path | None = None) -> tuple[dict | None, Path]:
    path = explicit or default_profile_path(server)
    if not path.is_file():
        return None, path
    profile = json.loads(path.read_text(encoding="utf-8"))
    require(profile.get("server_id") == server, "economic profile server_id does not match the report instance")
    require(profile.get("schema_version") == "1.0", "unsupported economic profile schema_version")
    require(profile.get("status") in {"draft", "customer_approved"}, "invalid economic profile status")
    require(profile.get("mode") in {"customer", "tei_assisted"}, "invalid economic profile mode")
    return profile, path


def validate_profile(profile: dict, server: str) -> None:
    require(profile.get("server_id") == server, "economic profile server_id does not match the report instance")
    require(profile.get("schema_version") == "1.0", "unsupported economic profile schema_version")
    require(profile.get("status") in {"draft", "customer_approved"}, "invalid economic profile status")
    require(profile.get("mode") in {"customer", "tei_assisted"}, "invalid economic profile mode")
    if profile["status"] == "customer_approved":
        validate_approved(profile)


def benchmark_context(benchmark: dict, profile: dict | None = None, profile_path: Path | None = None) -> dict:
    return {
        "status": "benchmark", "classification": "benchmark", "currency": "USD",
        "title": benchmark["title"],
        "source": {"id": benchmark["id"], "publisher": benchmark["publisher"],
                   "study_context": benchmark["study_context"]},
        "summary": benchmark["three_year_risk_adjusted"],
        "benefit_categories": benchmark["benefit_categories_pv_usd"],
        "composite": benchmark["composite"],
        "methodology_inputs": benchmark.get("projection_defaults", {}),
        "profile": {"status": (profile or {}).get("status", "not_configured"),
                    "path": str(profile_path) if profile_path else None,
                    "applied": False},
        "disclaimer": benchmark["applicability_note"],
        "assumptions": [], "scenarios": {}, "unavailable_models": [],
    }


def validate_approved(profile: dict) -> None:
    require(profile["status"] == "customer_approved", "only an approved profile can produce customer projections")
    currency = profile.get("currency")
    require(isinstance(currency, str) and re.fullmatch(r"[A-Z]{3}", currency), "currency must be a three-letter uppercase code")
    require(Decimal("0") <= dec(profile.get("discount_rate", -1)) <= Decimal("1"), "discount_rate must be between 0 and 1")
    costs = profile.get("costs") or {}
    for key in ("implementation_one_time", "annual_jfrog_license", "annual_professional_services", "annual_internal_platform_labor"):
        require(dec(costs.get(key, -1)) >= 0, f"invalid cost: {key}")
    models = profile.get("benefit_models")
    require(isinstance(models, list) and models, "approved profile requires at least one benefit model")
    seen: set[str] = set()
    for row in models:
        key = row.get("benefit_key")
        require(bool(key) and key not in seen, f"duplicate or missing benefit_key: {key}")
        seen.add(key)
        for field in ("baseline_units", "adoption_coverage", "realization_factor", "conservative_factor", "expected_factor", "optimistic_factor"):
            require(dec(row.get(field, -1)) >= 0, f"invalid {field} for {row.get('id')}")
        require(dec(row["adoption_coverage"]) <= 1 and dec(row["realization_factor"]) <= 1,
                f"coverage or realization exceeds 1 for {row.get('id')}")
        require(bool(row.get("benchmark_unit")) != (row.get("value_per_unit") is not None),
                f"{row.get('id')} must use exactly one of benchmark_unit or value_per_unit")
    if currency != "USD" and any(row.get("benchmark_unit") for row in models):
        require(dec(profile.get("usd_to_profile_currency_rate", 0)) > 0,
                "non-USD TEI-assisted profiles require an explicit FX conversion rate in usd_to_profile_currency_rate")
        require(bool(profile.get("fx_as_of")) and bool(profile.get("fx_source")),
                "non-USD TEI-assisted profiles require fx_as_of and fx_source")


def projected_context(profile: dict, benchmark: dict, profile_path: Path) -> dict:
    validate_approved(profile)
    currency = profile["currency"]
    fx = dec(profile.get("usd_to_profile_currency_rate", 1))
    projections = []
    totals = {name: Decimal("0") for name in ("conservative", "expected", "optimistic")}
    by_category: dict[str, Decimal] = {}
    for row in profile["benefit_models"]:
        if row.get("enabled", True) is False:
            continue
        benchmark_unit = row.get("benchmark_unit")
        if benchmark_unit:
            source = benchmark.get("projection_defaults", {}).get(benchmark_unit)
            require(source is not None, f"unknown TEI benchmark unit: {benchmark_unit}")
            unit_value = dec(source["value_per_unit_usd"]) * fx
            risk_adjustment = dec(row.get("risk_adjustment", source["risk_adjustment"]))
            value_source = f"benchmark:{benchmark['id']}:{benchmark_unit}"
        else:
            unit_value = dec(row["value_per_unit"])
            risk_adjustment = dec(row.get("risk_adjustment", 0))
            value_source = "customer_provided"
        require(Decimal("0") <= risk_adjustment <= Decimal("1"), f"invalid risk_adjustment for {row.get('id')}")
        base = (dec(row["baseline_units"]) * unit_value * dec(row["adoption_coverage"]) *
                dec(row["realization_factor"]) * (Decimal("1") - risk_adjustment))
        scenarios = {name: base * dec(row[f"{name}_factor"])
                     for name in ("conservative", "expected", "optimistic")}
        for name, value in scenarios.items():
            totals[name] += value
        category = row.get("category", "other")
        by_category[category] = by_category.get(category, Decimal("0")) + scenarios["expected"]
        projections.append({
            "id": row["id"], "label": row.get("label", row["id"]), "category": category,
            "benefit_key": row["benefit_key"], "classification": "projected",
            "baseline_units": row["baseline_units"], "baseline_source": row.get("baseline_source", "customer_provided"),
            "value_per_unit": money(unit_value), "value_source": value_source,
            "adoption_coverage": row["adoption_coverage"], "realization_factor": row["realization_factor"],
            "risk_adjustment": str(risk_adjustment), "scenarios": {k: money(v) for k, v in scenarios.items()},
            "confidence": row.get("confidence", "low"),
        })
    costs = profile["costs"]
    one_time = dec(costs["implementation_one_time"])
    annual_cost = sum((dec(costs[key]) for key in (
        "annual_jfrog_license", "annual_professional_services", "annual_internal_platform_labor"
    )), Decimal("0"))
    annual_benefit = totals["expected"]
    net_annual = annual_benefit - annual_cost
    three_benefit = annual_benefit * 3
    three_cost = one_time + annual_cost * 3
    rate = dec(profile["discount_rate"])
    npv = -one_time + sum(net_annual / ((Decimal("1") + rate) ** year) for year in (1, 2, 3))
    roi = None if three_cost == 0 else (three_benefit - three_cost) / three_cost * 100
    payback = None if annual_benefit == 0 else (one_time + annual_cost) / annual_benefit
    confidence_rank = {"low": 0, "medium": 1, "high": 2}
    confidence = min(
        (row.get("confidence", "low") for row in profile["benefit_models"] if row.get("enabled", True)),
        key=lambda item: confidence_rank.get(item, -1),
        default="low",
    )
    return {
        "status": "projected", "classification": "projected", "currency": currency,
        "title": "Customer economic scenario", "source": {"profile": profile.get("profile_id"),
        "benchmark": benchmark["id"] if any(row.get("benchmark_unit") for row in profile["benefit_models"]) else None},
        "profile": {"status": profile["status"], "mode": profile["mode"], "path": str(profile_path),
                    "effective_from": profile.get("effective_from"), "approved_by": profile.get("approved_by"),
                    "approved_at": profile.get("approved_at"), "applied": True},
        "summary": {"annual_benefit": money(annual_benefit), "annual_cost": money(annual_cost),
                    "net_annual_benefit": money(net_annual), "three_year_benefit": money(three_benefit),
                    "three_year_cost": money(three_cost), "npv": money(npv),
                    "roi_percent": None if roi is None else money(roi),
                    "payback_years": None if payback is None else money(payback),
                    "discount_rate": str(rate)},
        "scenarios": {k: money(v) for k, v in totals.items()},
        "benefit_categories": {k: money(v) for k, v in sorted(by_category.items())},
        "projections": projections,
        "assumptions": ["Customer-approved profile; benchmark-derived inputs are individually identified."],
        "formula": "baseline × value per unit × adoption coverage × realization factor × (1 - risk adjustment) × scenario factor",
        "confidence": confidence,
        "unavailable_models": [],
        "disclaimer": "Projected scenario, not an observed customer result. Actual realization requires financial validation.",
        "fx": None if currency == "USD" else {"usd_to_profile_currency_rate": profile["usd_to_profile_currency_rate"],
                                                "as_of": profile["fx_as_of"], "source": profile["fx_source"]},
    }


def build(server: str, benchmark: dict, explicit_profile: Path | None = None) -> tuple[dict, dict | None, Path]:
    profile, path = load_profile(server, explicit_profile)
    if profile is None or profile["status"] == "draft":
        return benchmark_context(benchmark, profile, path), profile, path
    return projected_context(profile, benchmark, path), profile, path
