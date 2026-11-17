#!/usr/bin/env python3
"""Inject calendar-month week-over-week trends from validated weekly archives."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


POLARITY = {
    "curation-decisions": "contextual", "curation-blocked": "contextual",
    "curation-block-rate": "contextual", "curation-users": "higher_is_better",
    "unique-blocked-packages": "contextual",
    "xray-new-findings": "lower_is_better", "xray-critical-findings": "lower_is_better",
    "xray-high-findings": "lower_is_better",
    "period-downloads": "contextual", "period-uploads": "contextual",
    "binary-cache-hit-rate": "higher_is_better",
}

MODULE_KEYS = ("curation", "xray", "artifactory_detail", "ai_catalog", "access_governance", "jas", "runtime", "platform")


def parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def period(report: dict) -> tuple[datetime, datetime] | None:
    meta = report.get("meta") or {}
    if meta.get("period_start") and meta.get("period_end"):
        return parse(meta["period_start"]), parse(meta["period_end"])
    return None


def is_complete_week(report: dict) -> bool:
    """Only complete periods may participate in week-over-week comparison."""
    return (report.get("meta") or {}).get("period_completeness", "complete") == "complete"


def metric_map(report: dict) -> dict[str, dict]:
    values: dict[str, dict] = {}
    for key in MODULE_KEYS:
        for item in (report.get(key) or {}).get("metrics") or []:
            if item.get("id") and isinstance(item.get("value"), (int, float)):
                values[item["id"]] = item
    return values


def pointer_run(pointer: Path) -> Path | None:
    try:
        value = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    candidate = value.get("run_directory") or (value.get("archive") or {}).get("run_directory")
    if not candidate:
        return None
    path = Path(candidate)
    return path if path.is_absolute() else pointer.parent / path


def archived_reports(weekly_root: Path) -> list[tuple[Path, dict]]:
    reports = []
    for pointer in sorted(weekly_root.glob("*/latest.json")):
        run = pointer_run(pointer)
        if not run or not (run / "data.json").is_file() or not (run / "raw" / "manifest.json").is_file():
            continue
        try:
            manifest = json.loads((run / "raw" / "manifest.json").read_text(encoding="utf-8"))
            report = json.loads((run / "data.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("prior_report_input_used") is not False or period(report) is None:
            continue
        reports.append((run, report))
    return reports


def calendar_bounds(month: str, timezone_name: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone_name)
    first = datetime.strptime(month, "%Y-%m").replace(tzinfo=zone)
    following = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first.astimezone(timezone.utc), (following - timedelta(seconds=1)).astimezone(timezone.utc)


def inject(report: dict, archives: list[tuple[Path, dict]], month: str, timezone_name: str) -> dict:
    start, end = calendar_bounds(month, timezone_name)
    current_bounds = period(report)
    as_of = current_bounds[1] if current_bounds else end
    candidates: dict[str, tuple[Path, dict, datetime, datetime]] = {}
    for run, item in archives:
        if not is_complete_week(item):
            continue
        bounds = period(item)
        if not bounds:
            continue
        left, right = bounds
        if right < start or left > end or right > as_of:
            continue
        key = right.astimezone(ZoneInfo(timezone_name)).date().isoformat()
        candidates[key] = (run, item, left, right)
    current_is_complete = is_complete_week(report)
    if current_bounds and current_is_complete and not (current_bounds[1] < start or current_bounds[0] > end):
        key = current_bounds[1].astimezone(ZoneInfo(timezone_name)).date().isoformat()
        candidates[key] = (Path("current-run"), report, *current_bounds)

    ordered = sorted(candidates.items())
    weeks = [{"period_key": key, "label": f'W/E {right.astimezone(ZoneInfo(timezone_name)).strftime("%b %d").replace(" 0", " ")}',
              "period_start": left.isoformat(), "period_end": right.isoformat(), "source_run": str(run)}
             for key, (run, _report, left, right) in ordered]
    all_metrics = [metric_map(item[1][1]) for item in ordered]
    ids = sorted(set().union(*(set(values) for values in all_metrics)) if all_metrics else set())
    series = []
    for metric_id in ids:
        if metric_id not in POLARITY:
            continue
        points = []
        exemplar = None
        for week, values in zip(weeks, all_metrics):
            item = values.get(metric_id)
            exemplar = exemplar or item
            points.append({"period_key": week["period_key"], "label": week["label"],
                           "value": item.get("value") if item else None})
        numeric = [point["value"] for point in points if isinstance(point.get("value"), (int, float))]
        if len(numeric) < 2:
            continue
        previous, latest = numeric[-2], numeric[-1]
        change = None if previous == 0 else round((latest - previous) / previous * 100, 1)
        series.append({"id": metric_id, "label": exemplar.get("label"), "unit": exemplar.get("unit"),
                       "polarity": POLARITY[metric_id], "points": points,
                       "latest_change_percent": change})
    excluded_note = ""
    if current_bounds and not current_is_complete:
        local_start = current_bounds[0].astimezone(ZoneInfo(timezone_name)).strftime("%b %d").replace(" 0", " ")
        local_end = current_bounds[1].astimezone(ZoneInfo(timezone_name)).strftime("%b %d").replace(" 0", " ")
        excluded_note = f" The current partial period ({local_start} to {local_end}) is excluded from WoW calculations."
    report["weekly_trend"] = {
        "status": "available" if len(weeks) >= 2 else "partial",
        "month": month, "month_label": datetime.strptime(month, "%Y-%m").strftime("%B %Y"),
        "timezone": timezone_name, "weeks": weeks, "series": series,
        "current_period_comparable": current_is_complete,
        "interpretation": "Red indicates an adverse current state or adverse week-over-week direction. Contextual metrics are neutral because movement alone is not good or bad." + excluded_note,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Add week-over-week calendar-month trends")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--weekly-root", required=True, type=Path)
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--timezone", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    result = inject(report, archived_reports(args.weekly_root), args.month, args.timezone)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
