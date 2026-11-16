#!/usr/bin/env python3
"""Resolve stable weekly and monthly report periods in a configured timezone."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def parse_now(value: str | None) -> datetime:
    if value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("--now must include a UTC offset or Z")
        return parsed
    return datetime.now(timezone.utc)


def utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_midnight(value: datetime) -> datetime:
    return value.replace(hour=0, minute=0, second=0, microsecond=0)


def format_date(value: datetime, pattern: str) -> str:
    return value.strftime(pattern.replace("%-d", "%d")).replace(" 0", " ")


def range_label(start: datetime, end: datetime) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{format_date(start, '%B %-d')}–{format_date(end, '%-d, %Y')}"
    if start.year == end.year:
        return f"{format_date(start, '%B %-d')}–{format_date(end, '%B %-d, %Y')}"
    return f"{format_date(start, '%B %-d, %Y')}–{format_date(end, '%B %-d, %Y')}"


def resolve(mode: str, timezone_name: str, now: datetime,
            date_from: str | None = None, date_to: str | None = None,
            month: str | None = None) -> dict:
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {timezone_name}") from exc
    local_now = now.astimezone(zone)

    if mode in {"completed-week", "current-week"}:
        current_monday = local_midnight(local_now) - timedelta(days=local_now.weekday())
        if mode == "completed-week":
            start_local = current_monday - timedelta(days=7)
            end_local = current_monday - timedelta(seconds=1)
            completeness = "complete"
        else:
            start_local = current_monday
            end_local = local_now.replace(microsecond=0)
            completeness = "week_to_date"
        period_key = end_local.date().isoformat()
        label = range_label(start_local, end_local)
    elif mode == "week-ending":
        if not date_to:
            raise ValueError("week-ending mode requires --date-to")
        end_date = datetime.strptime(date_to, "%Y-%m-%d")
        start_local = (end_date - timedelta(days=6)).replace(tzinfo=zone)
        end_local = (end_date + timedelta(days=1)).replace(tzinfo=zone) - timedelta(seconds=1)
        completeness = "complete" if end_local < local_now else "week_to_date"
        if completeness == "week_to_date":
            end_local = local_now.replace(microsecond=0)
        period_key = end_date.date().isoformat()
        label = range_label(start_local, end_local)
    elif mode == "explicit":
        if not date_from or not date_to:
            raise ValueError("explicit mode requires --date-from and --date-to")
        start_date = datetime.strptime(date_from, "%Y-%m-%d")
        end_date = datetime.strptime(date_to, "%Y-%m-%d")
        start_local = start_date.replace(tzinfo=zone)
        end_local = (end_date + timedelta(days=1)).replace(tzinfo=zone) - timedelta(seconds=1)
        if end_local < start_local:
            raise ValueError("--date-to precedes --date-from")
        completeness = "explicit"
        period_key = end_local.date().isoformat()
        label = range_label(start_local, end_local)
    elif mode == "calendar-month":
        target = month or local_now.strftime("%Y-%m")
        first = datetime.strptime(target, "%Y-%m").replace(tzinfo=zone)
        next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        start_local, end_local = first, next_month - timedelta(seconds=1)
        completeness = "complete" if end_local < local_now else "month_to_date"
        if completeness == "month_to_date":
            end_local = local_now.replace(microsecond=0)
        period_key = end_local.date().isoformat()
        label = first.strftime("%B %Y") if completeness == "complete" else f"{format_date(first, '%B %-d')}–{format_date(end_local, '%B %-d, %Y')}"
    else:
        raise ValueError(f"unsupported mode: {mode}")

    return {
        "schema_version": "1.0", "mode": mode, "timezone": timezone_name,
        "cadence": "monthly" if mode == "calendar-month" else "weekly",
        "completeness": completeness, "period_key": period_key, "label": label,
        "local": {"start": start_local.isoformat(), "end": end_local.isoformat()},
        "utc": {"start": utc(start_local), "end": utc(end_local)},
        "resolved_at": utc(now),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("completed-week", "current-week", "week-ending", "explicit", "calendar-month"), default="completed-week")
    parser.add_argument("--timezone", default=os.environ.get("JFROG_REPORT_TIMEZONE", "UTC"))
    parser.add_argument("--now", help="Testing/replay clock with offset or Z")
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--month", help="YYYY-MM for calendar-month mode")
    args = parser.parse_args()
    print(json.dumps(resolve(args.mode, args.timezone, parse_now(args.now), args.date_from, args.date_to, args.month), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
