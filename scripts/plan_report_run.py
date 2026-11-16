#!/usr/bin/env python3
"""Create deterministic period and archive paths for a report invocation."""

from __future__ import annotations

import argparse
import json
import os
from datetime import timezone
from pathlib import Path

from resolve_reporting_period import parse_now, resolve


def plan(server: str, output_root: Path, mode: str, timezone_name: str, now,
         date_from: str | None = None, date_to: str | None = None,
         month: str | None = None) -> dict:
    period = resolve(mode, timezone_name, now, date_from, date_to, month)
    cadence = period["cadence"]
    period_dir = output_root / server / cadence / period["period_key"]
    run_id = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = period_dir / "runs" / run_id
    return {
        "schema_version": "1.0",
        "server_id": server,
        "period": period,
        "archive": {
            "period_directory": str(period_dir),
            "run_directory": str(run_dir),
            "raw_directory": str(run_dir / "raw"),
            "evidence_file": str(run_dir / "evidence.json"),
            "normalized_report_file": str(run_dir / "data.json"),
            "rendered_report_file": str(run_dir / "report.html"),
            "latest_pointer": str(period_dir / "latest.json"),
        },
        "promotion_rule": (
            "Validate the run before updating latest.json. Preserve every run; "
            "never merge an incomplete rerun into a successful archive."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan a stable JFrog report run")
    parser.add_argument("--server", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--mode", choices=("completed-week", "current-week", "week-ending", "explicit", "calendar-month"), default="completed-week")
    parser.add_argument("--timezone", default=os.environ.get("JFROG_REPORT_TIMEZONE", "UTC"))
    parser.add_argument("--now")
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--month")
    args = parser.parse_args()
    value = plan(args.server, args.output_root, args.mode, args.timezone, parse_now(args.now),
                 args.date_from, args.date_to, args.month)
    print(json.dumps(value, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
