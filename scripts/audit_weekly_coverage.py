#!/usr/bin/env python3
"""Audit archived weekly coverage for a calendar month without collecting data."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from resolve_reporting_period import parse_now, utc


def month_bounds(month: str, timezone_name: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone_name)
    start = datetime.strptime(month, "%Y-%m").replace(tzinfo=zone)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, next_month - timedelta(seconds=1)


def previous_month(now: datetime, timezone_name: str) -> str:
    local = now.astimezone(ZoneInfo(timezone_name))
    first = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (first - timedelta(days=1)).strftime("%Y-%m")


def current_month(now: datetime, timezone_name: str) -> str:
    return now.astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m")


def last_completed_week_end(now: datetime, timezone_name: str) -> datetime:
    local = now.astimezone(ZoneInfo(timezone_name))
    monday = local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=local.weekday())
    return monday - timedelta(seconds=1)


def expected_weeks(start: datetime, end: datetime) -> list[dict]:
    cursor = start.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=start.weekday())
    weeks = []
    while cursor <= end:
        week_end = cursor + timedelta(days=7) - timedelta(seconds=1)
        weeks.append({
            "week_start": cursor,
            "week_end": week_end,
            "period_key": week_end.date().isoformat(),
            "month_overlap_start": max(cursor, start),
            "month_overlap_end": min(week_end, end),
        })
        cursor += timedelta(days=7)
    return weeks


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


def validated_periods(weekly_root: Path) -> list[dict]:
    periods: list[dict] = []
    for pointer in sorted(weekly_root.glob("*/latest.json")):
        run = pointer_run(pointer)
        if not run:
            continue
        evidence_path = run / "evidence.json"
        manifest_path = run / "raw" / "manifest.json"
        if not evidence_path.is_file() or not manifest_path.is_file():
            continue
        try:
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            period = evidence["reporting"]["period"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue
        if evidence.get("provenance", {}).get("prior_report_input_used") is not False:
            continue
        if manifest.get("prior_report_input_used") is not False:
            continue
        periods.append({
            "start": datetime.fromisoformat(period["start"].replace("Z", "+00:00")),
            "end": datetime.fromisoformat(period["end"].replace("Z", "+00:00")),
            "run_directory": str(run),
        })
    return periods


def audit(report_root: Path, server: str, month: str, timezone_name: str,
          now: datetime, retention_days: int = 30, *, completed_only: bool = False,
          exclude_period_key: str | None = None) -> dict:
    start, end = month_bounds(month, timezone_name)
    if completed_only:
        end = min(end, last_completed_week_end(now, timezone_name))
    periods = validated_periods(report_root / server / "weekly")
    cutoff = now.astimezone(timezone.utc) - timedelta(days=retention_days)
    missing = []
    covered = []
    for week in expected_weeks(start, end):
        if week["period_key"] == exclude_period_key:
            continue
        week_start = week["week_start"].astimezone(timezone.utc)
        week_end = week["week_end"].astimezone(timezone.utc)
        matches = [p for p in periods if p["start"] <= week_start and p["end"] >= week_end]
        if matches:
            covered.append({"period_key": week["period_key"], "run_directory": matches[-1]["run_directory"]})
            continue
        if week_start >= cutoff:
            curation = "fully_backfillable"
        elif week_end >= cutoff:
            curation = "partially_backfillable"
        else:
            curation = "expired"
        missing.append({
            "period_key": week["period_key"],
            "week_start": week["week_start"].date().isoformat(),
            "week_end": week["week_end"].date().isoformat(),
            "month_overlap_start": week["month_overlap_start"].date().isoformat(),
            "month_overlap_end": week["month_overlap_end"].date().isoformat(),
            "curation_backfill": curation,
        })
    backfillable = [item for item in missing if item["curation_backfill"] == "fully_backfillable"]
    return {
        "schema_version": "1.0", "server_id": server, "month": month,
        "timezone": timezone_name, "checked_at": utc(now),
        "first_run": not periods,
        "validated_week_count": len(periods),
        "trend_ready": len(covered) >= 2,
        "trend_ready_after_current_run": len(covered) >= 1,
        "complete": not missing, "covered_weeks": covered, "missing_weeks": missing,
        "suggest_backfill": bool(backfillable),
        "suggestion": None if not missing else (
            f"{len(missing)} weekly archive(s) are missing; {len(backfillable)} can still be fully "
            f"backfilled for Curation. Ask the user before collecting them."
        ),
        "retention_note": (
            "Backfill eligibility shown here is for the configured Curation audit retention. "
            "Other product APIs may have different historical availability."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit weekly report coverage for a calendar month")
    parser.add_argument("--report-root", required=True, type=Path)
    parser.add_argument("--server", required=True)
    parser.add_argument("--month", help="YYYY-MM; defaults to the previous calendar month")
    parser.add_argument("--timezone", default=os.environ.get("JFROG_REPORT_TIMEZONE", "UTC"))
    parser.add_argument("--now", help="Testing/replay clock with offset or Z")
    parser.add_argument("--curation-retention-days", type=int, default=30)
    parser.add_argument("--completed-only", action="store_true",
                        help="Audit only completed ISO weeks; use for first-run trend preflight")
    parser.add_argument("--exclude-period-key",
                        help="Ignore the week that the pending report run will create")
    args = parser.parse_args()
    now = parse_now(args.now)
    month = args.month or (current_month(now, args.timezone) if args.completed_only
                           else previous_month(now, args.timezone))
    print(json.dumps(audit(args.report_root, args.server, month, args.timezone, now,
                           args.curation_retention_days, completed_only=args.completed_only,
                           exclude_period_key=args.exclude_period_key), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
