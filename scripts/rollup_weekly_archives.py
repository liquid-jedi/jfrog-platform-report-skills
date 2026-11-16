#!/usr/bin/env python3
"""Build a truthful calendar-month evidence roll-up from validated weekly runs."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def canonical_id(row: dict) -> str:
    for key in ("id", "event_id", "violation_id"):
        if row.get(key) not in (None, ""):
            return f"{key}:{row[key]}"
    blob = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def event_time(row: dict) -> datetime | None:
    for key in ("created_at", "created", "created_time", "timestamp"):
        value = row.get(key)
        if value:
            try:
                parsed = parse_time(str(value))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
    return None


def month_bounds(month: str, timezone_name: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone_name)
    start = datetime.strptime(month, "%Y-%m").replace(tzinfo=zone)
    next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start.astimezone(timezone.utc), (next_month - timedelta(seconds=1)).astimezone(timezone.utc)


def verify_raw(run_dir: Path, manifest: dict) -> None:
    raw_dir = run_dir / "raw"
    for source in manifest.get("sources") or []:
        path = raw_dir / str(source["raw_file"])
        if not path.is_file():
            raise ValueError(f"missing raw evidence: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != source.get("sha256"):
            raise ValueError(f"checksum mismatch: {path}")


def raw_rows(run_dir: Path, prefix: str, key: str) -> list[dict]:
    rows: list[dict] = []
    for path in sorted((run_dir / "raw").glob(f"{prefix}*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        values = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(values, list):
            rows.extend(row for row in values if isinstance(row, dict))
    return rows


def coverage(intervals: list[tuple[datetime, datetime]], start: datetime,
             end: datetime) -> tuple[bool, list[dict]]:
    clipped = sorted((max(a, start), min(b, end)) for a, b in intervals if b >= start and a <= end)
    cursor = start
    gaps: list[dict] = []
    for left, right in clipped:
        if left > cursor:
            gaps.append({"start": cursor.isoformat(), "end": (left - timedelta(seconds=1)).isoformat()})
        cursor = max(cursor, right + timedelta(seconds=1))
    if cursor <= end:
        gaps.append({"start": cursor.isoformat(), "end": end.isoformat()})
    return not gaps, gaps


def rollup(month: str, timezone_name: str, archives: list[Path]) -> dict:
    start, end = month_bounds(month, timezone_name)
    intervals: list[tuple[datetime, datetime]] = []
    curation: dict[str, dict] = {}
    violations: dict[str, dict] = {}
    snapshots: list[tuple[datetime, dict, str]] = []
    used: list[str] = []

    for run_dir in archives:
        evidence_path, manifest_path = run_dir / "evidence.json", run_dir / "raw" / "manifest.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if evidence.get("provenance", {}).get("prior_report_input_used") is not False:
            raise ValueError(f"archive is not a fresh collection: {run_dir}")
        verify_raw(run_dir, manifest)
        period = evidence["reporting"]["period"]
        intervals.append((parse_time(period["start"]), parse_time(period["end"])))
        used.append(str(run_dir))

        for row in raw_rows(run_dir, "curation-audit-", "data"):
            stamp = event_time(row)
            if stamp and start <= stamp.astimezone(timezone.utc) <= end:
                curation[canonical_id(row)] = row
        for row in raw_rows(run_dir, "xray-violations-", "violations"):
            stamp = event_time(row)
            if stamp and start <= stamp.astimezone(timezone.utc) <= end:
                violations[canonical_id(row)] = row

        collected = parse_time(evidence["provenance"]["collection_started_at"])
        if collected <= end:
            snapshots.append((collected, evidence, str(run_dir)))

    complete, gaps = coverage(intervals, start, end)
    curation_rows = list(curation.values())
    violation_rows = list(violations.values())
    actions = Counter(str(row.get("action") or "unknown").lower() for row in curation_rows)
    blocked = [row for row in curation_rows if str(row.get("action") or "").lower() == "blocked"]
    users = {str(row.get("username") or row.get("user_mail") or "").strip() for row in curation_rows}
    users.discard("")
    blocked_packages = {
        (row.get("package_type"), row.get("package_name"), row.get("package_version"))
        for row in blocked
    }
    latest = max(snapshots, key=lambda item: item[0]) if snapshots else None
    posture = None if not latest else {
        "as_of": latest[0].isoformat(), "source_archive": latest[2],
        "artifactory": latest[1].get("artifactory"),
        "xray_inventory": (latest[1].get("xray") or {}).get("inventory"),
        "ai_catalog": latest[1].get("ai_catalog"),
    }
    return {
        "schema_version": "1.0", "cadence": "monthly", "month": month,
        "timezone": timezone_name,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "coverage": {"complete": complete, "gaps": gaps, "archives": used},
        "classification": "derived" if complete else "unavailable",
        "curation": {
            "events": len(curation_rows) if complete else None,
            "actions": dict(actions) if complete else None,
            "unique_users": len(users) if complete else None,
            "unique_blocked_packages": len(blocked_packages) if complete else None,
        },
        "xray": {
            "violations": len(violation_rows) if complete else None,
            "violations_by_severity": dict(Counter(str(row.get("severity") or "unknown").lower() for row in violation_rows)) if complete else None,
        },
        "period_end_posture": posture,
        "method": "Timestamp-filtered, checksum-verified weekly raw events; stable-ID deduplication; latest eligible posture snapshot.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Roll up validated weekly archives into a calendar month")
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--timezone", required=True)
    parser.add_argument("--archive", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = rollup(args.month, args.timezone, args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
