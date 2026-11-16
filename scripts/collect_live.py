#!/usr/bin/env python3
"""Collect CIO report evidence without consuming prior reports or snapshots."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


class Collector:
    def __init__(self, server: str, raw_dir: Path):
        self.server = server
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.sources: list[dict] = []

    def api(self, source_id: str, path: str, *, method: str = "GET", body: dict | None = None,
            timeout: int = 180) -> object:
        command = ["jf", "api", "--server-id", self.server, path, "-X", method, "--timeout", str(timeout)]
        input_path: Path | None = None
        if body is not None:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
                json.dump(body, handle, separators=(",", ":"))
                input_path = Path(handle.name)
            command += ["-H", "Content-Type: application/json", "--input", str(input_path)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout + 15)
        finally:
            if input_path:
                input_path.unlink(missing_ok=True)
        if result.returncode:
            diagnostic = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"{self.server} failed for {path}: {diagnostic or 'unknown error'}")
        try:
            payload = json.loads(result.stdout or "null")
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{self.server} returned non-JSON for {path}: {exc}") from exc
        raw_path = self.raw_dir / f"{source_id}.json"
        blob = canonical_bytes(payload)
        raw_path.write_bytes(blob)
        self.sources.append({
            "id": source_id, "endpoint": path, "method": method,
            "raw_file": raw_path.name, "sha256": hashlib.sha256(blob).hexdigest(),
            "collected_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": "available", "complete": True,
        })
        return payload


def list_rows(payload: object, *keys: str) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def fetch_curation(collector: Collector, date_from: str, date_to: str,
                    collected_at: datetime, page_size: int = 2000) -> tuple[list[dict], dict]:
    def parse(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def fmt(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    start, end = parse(date_from), parse(date_to)
    if end < start:
        raise ValueError("Curation period end precedes start")
    retention_start = collected_at - timedelta(days=30)
    query_start = max(start, retention_start)
    if query_start > end:
        return [], {
            "rows_fetched": 0, "total_reported": None, "pages_fetched": 0,
            "windows": 0, "maximum_window_hours": 168, "complete": False,
            "coverage": "unavailable", "requested_start": fmt(start),
            "requested_end": fmt(end), "available_start": None, "available_end": None,
            "retention_days": 30,
            "reason": "JFrog Curation audit events are retained for 30 days; the requested period has expired.",
        }
    # The API rejects ranges over 168 hours. Use inclusive, non-overlapping
    # windows whose duration is one second below that ceiling.
    windows: list[tuple[str, str]] = []
    cursor = query_start
    while cursor <= end:
        window_end = min(cursor + timedelta(hours=168) - timedelta(seconds=1), end)
        windows.append((fmt(cursor), fmt(window_end)))
        cursor = window_end + timedelta(seconds=1)

    def fetch(window_number: int, window_start: str, window_end: str,
              offset: int) -> tuple[int, dict]:
        # Xray's Curation API expects RFC3339 separators verbatim. Encoding the
        # timestamp colons produces HTTP 400 on supported SaaS versions.
        query = urlencode({
            "order_by": "id", "direction": "desc", "num_of_rows": page_size,
            "created_at_start": window_start, "created_at_end": window_end,
            "include_total": "true", "dry_run": "false", "offset": offset,
        }, safe=":")
        payload = collector.api(
            f"curation-audit-w{window_number:02d}-{offset:08d}",
            f"/xray/api/v1/curation/audit/packages?{query}",
        )
        if not isinstance(payload, dict):
            raise RuntimeError(f"curation offset {offset} returned {type(payload).__name__}, expected object")
        if payload.get("errors") and not payload.get("data"):
            raise RuntimeError(f"curation offset {offset} rejected: {payload['errors']}")
        return offset, payload

    rows: list[dict] = []
    reported_total = 0
    pages_fetched = 0
    for window_number, (window_start, window_end) in enumerate(windows, start=1):
        first_offset, first = fetch(window_number, window_start, window_end, 0)
        pages = {first_offset: first}
        window_total = int((first.get("meta") or {}).get("total_count") or 0)
        offsets = list(range(page_size, window_total, page_size))
        with ThreadPoolExecutor(max_workers=min(6, max(1, len(offsets)))) as pool:
            futures = [pool.submit(fetch, window_number, window_start, window_end, offset)
                       for offset in offsets]
            for future in as_completed(futures):
                offset, page = future.result()
                pages[offset] = page
        window_rows = [row for offset in sorted(pages) for row in (pages[offset].get("data") or [])]
        if len(window_rows) != window_total:
            raise RuntimeError(
                f"curation window {window_start}..{window_end} incomplete: "
                f"fetched {len(window_rows)} of {window_total}"
            )
        rows.extend(window_rows)
        reported_total += window_total
        pages_fetched += len(pages)
    if len(rows) != reported_total:
        raise RuntimeError(f"curation pagination incomplete: fetched {len(rows)} of {reported_total}")
    coverage = "complete" if query_start == start else "partial"
    return rows, {"rows_fetched": len(rows), "total_reported": reported_total,
                  "pages_fetched": pages_fetched, "windows": len(windows),
                  "maximum_window_hours": 168, "complete": coverage == "complete",
                  "coverage": coverage, "requested_start": fmt(start),
                  "requested_end": fmt(end), "available_start": fmt(query_start),
                  "available_end": fmt(end), "retention_days": 30,
                  "reason": None if coverage == "complete" else
                  "Only the portion inside JFrog Curation's 30-day audit retention was available."}


def fetch_violations(collector: Collector, date_from: str, date_to: str,
                     page_size: int = 500) -> tuple[list[dict], dict]:
    def fetch(page_number: int) -> tuple[int, dict]:
        payload = collector.api(f"xray-violations-{page_number:06d}", "/xray/api/v1/violations", method="POST", body={
            "filters": {"created_from": date_from, "created_until": date_to},
            "pagination": {"limit": page_size, "offset": page_number,
                           "order_by": "severity", "direction": "desc"},
        })
        if not isinstance(payload, dict):
            raise RuntimeError(f"violations page {page_number} returned {type(payload).__name__}, expected object")
        return page_number, payload

    first_page, first = fetch(1)
    pages = {first_page: first}
    total = int(first.get("total_violations") or 0)
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    with ThreadPoolExecutor(max_workers=min(6, total_pages)) as pool:
        futures = [pool.submit(fetch, page) for page in range(2, total_pages + 1)]
        for future in as_completed(futures):
            page, payload = future.result()
            pages[page] = payload
    rows = [row for page in sorted(pages) for row in (pages[page].get("violations") or [])]
    if len(rows) != total:
        raise RuntimeError(f"Xray violation pagination incomplete: fetched {len(rows)} of {total}")
    return rows, {"rows_fetched": len(rows), "total_reported": total,
                  "pages_fetched": len(pages), "complete": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fresh, read-only JFrog CIO evidence collector")
    parser.add_argument("--server", required=True)
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--cadence", choices=["weekly", "monthly", "custom"], required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    args = parser.parse_args()

    collector = Collector(args.server, args.raw_dir)
    collected_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    repositories = list_rows(collector.api("artifactory-repositories", "/artifactory/api/repositories"))
    storage = collector.api("artifactory-storage", "/artifactory/api/storageinfo")
    watches = list_rows(collector.api("xray-watches", "/xray/api/v2/watches"), "watches")
    policies = list_rows(collector.api("xray-policies", "/xray/api/v2/policies"), "result", "policies")
    indexed = list_rows(collector.api("xray-indexed-repositories", "/xray/api/v1/binMgr/default/repos"), "indexed_repos", "repos")
    curation_rows, curation_meta = fetch_curation(
        collector, args.date_from, args.date_to,
        datetime.fromisoformat(collected_at.replace("Z", "+00:00")),
    )
    violations, violation_meta = fetch_violations(collector, args.date_from, args.date_to)

    action_counts = Counter(str(row.get("action") or "unknown").lower() for row in curation_rows)
    unique_users = {str(row.get("username") or row.get("user_mail") or "").strip() for row in curation_rows}
    unique_users.discard("")
    blocked = [row for row in curation_rows if str(row.get("action") or "").lower() == "blocked"]
    blocked_packages = {(row.get("package_type"), row.get("package_name"), row.get("package_version")) for row in blocked}
    severities = Counter(str(row.get("severity") or "unknown").lower() for row in violations)
    ai_types = {"AIEditorExtensions", "AgentPackages", "AgentPlugins", "HuggingFaceML", "MachineLearning", "Skills"}
    ai_repos = [row for row in repositories if row.get("packageType") in ai_types]

    inventory_as_of = {"classification": "observed", "temporal_scope": "point_in_time", "as_of": collected_at}
    period_scope = {"classification": "observed", "temporal_scope": "bounded_period",
                    "start": args.date_from, "end": args.date_to}
    result = {
        "schema_version": "0.3",
        "provenance": {
            "source": "live", "server_id": args.server, "collector": "jfrog-cio-value-report",
            "collection_started_at": collected_at, "prior_report_input_used": False,
            "raw_manifest": collector.sources,
        },
        "reporting": {"cadence": args.cadence, "period": {"start": args.date_from, "end": args.date_to}},
        "artifactory": {
            **inventory_as_of, "repositories_total": len(repositories),
            "repositories_by_type": dict(Counter(str(row.get("type") or "unknown").lower() for row in repositories)),
            "repositories_by_package_type": dict(Counter(str(row.get("packageType") or "unknown") for row in repositories)),
            "storage_summary": storage,
        },
        "xray": {
            "inventory": {**inventory_as_of, "watches_total": len(watches),
                          "policies_total": len(policies), "indexed_repositories": len(indexed)},
            "period": {**period_scope, "violations": len(violations),
                       "violations_by_severity": dict(severities), "collection": violation_meta},
        },
        "curation": {
            "status": "available" if curation_meta["coverage"] == "complete" else
                      ("partial" if curation_meta["coverage"] == "partial" else "unavailable"),
            "period": {
                **period_scope,
                "events": len(curation_rows) if curation_meta["coverage"] == "complete" else None,
                "actions": dict(action_counts) if curation_meta["coverage"] == "complete" else None,
                "unique_users": len(unique_users) if curation_meta["coverage"] == "complete" else None,
                "unique_blocked_packages": len(blocked_packages) if curation_meta["coverage"] == "complete" else None,
                "retained_window_events": len(curation_rows) if curation_meta["coverage"] == "partial" else None,
                "events_by_package_type": dict(Counter(str(row.get("package_type") or "unknown") for row in curation_rows)),
                "top_block_reasons": Counter(str(row.get("reason") or "Unknown") for row in blocked).most_common(10),
                "collection": curation_meta,
            },
        },
        "ai_catalog": {
            "status": "available" if ai_repos else "no_data", **inventory_as_of,
            "repositories_total": len(ai_repos),
            "repositories_by_type": dict(Counter(str(row.get("packageType") or "unknown") for row in ai_repos)),
            "note": "Repository footprint only; asset security posture uses its own as-of timestamp.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (args.raw_dir / "manifest.json").write_text(json.dumps({
        "schema_version": "1.0", "server_id": args.server,
        "period": result["reporting"]["period"], "prior_report_input_used": False,
        "sources": collector.sources,
    }, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
