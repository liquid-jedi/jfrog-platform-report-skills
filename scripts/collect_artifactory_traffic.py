#!/usr/bin/env python3
"""Persist Artifactory application-metric counters and calculate safe deltas."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SAMPLE = re.compile(r'^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)\{(?P<labels>.*)\}\s+(?P<value>[-+0-9.eE]+)(?:\s+\d+)?$')
LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^"])*)"')


def parse_samples(text):
    rows = []
    for line in text.splitlines():
        match = SAMPLE.match(line.strip())
        if not match:
            continue
        labels = {key: bytes(value, "utf-8").decode("unicode_escape") for key, value in LABEL.findall(match.group("labels"))}
        rows.append((match.group("name"), labels, float(match.group("value"))))
    return rows


def aggregate(text):
    rows = parse_samples(text)
    counter = "http_time_resolve_self_seconds_count"
    download = upload = 0
    by_package = {"download": {}, "upload": {}}
    for name, labels, value in rows:
        if name != counter:
            continue
        group, method, status = labels.get("group"), labels.get("method"), labels.get("status", "")
        successful = status.startswith("2") or status.startswith("3")
        if group == "download" and method == "GET" and successful:
            download += int(value)
            package = labels.get("package") or "unknown"
            by_package["download"][package] = by_package["download"].get(package, 0) + int(value)
        elif group == "upload" and method in {"PUT", "POST", "PATCH"} and successful:
            upload += int(value)
            package = labels.get("package") or "unknown"
            by_package["upload"][package] = by_package["upload"].get(package, 0) + int(value)
    cache_download = sum(value for name, labels, value in rows if name == "jfsh_binaries_download_total" and labels.get("provider") == "cache-fs")
    cache_miss = sum(value for name, labels, value in rows if name == "jfsh_binaries_not_found_total" and labels.get("provider") == "cache-fs")
    return {
        "metric": counter,
        "download_requests_total": download,
        "upload_requests_total": upload,
        "by_package": by_package,
        "cache_fs_download_total": int(cache_download) if cache_download else None,
        "cache_fs_not_found_total": int(cache_miss) if cache_miss else None,
    }


def delta(current, prior):
    result = {}
    for key in ("download_requests_total", "upload_requests_total", "cache_fs_download_total", "cache_fs_not_found_total"):
        now, before = current.get(key), (prior or {}).get("counters", {}).get(key)
        result[key.replace("_total", "_delta")] = now - before if now is not None and before is not None and now >= before else None
    downloads, misses = result.get("cache_fs_download_delta"), result.get("cache_fs_not_found_delta")
    result["cache_fs_hit_rate"] = round(downloads / (downloads + misses) * 100, 2) if downloads is not None and misses is not None and downloads + misses else None
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--snapshot-root", required=True, type=Path)
    parser.add_argument("--collected-at")
    args = parser.parse_args()
    collected = datetime.fromisoformat(args.collected_at.replace("Z", "+00:00")) if args.collected_at else datetime.now(timezone.utc)
    result = subprocess.run(["jf", "rt", "curl", "-s", "--server-id", args.server_id,
                             "/api/v1/metrics/application"], check=True, capture_output=True, text=True)
    counters = aggregate(result.stdout)
    args.snapshot_root.mkdir(parents=True, exist_ok=True)
    output = args.snapshot_root / f"{collected.date().isoformat()}.json"
    prior_files = sorted(path for path in args.snapshot_root.glob("*.json") if path != output)
    prior = json.loads(prior_files[-1].read_text(encoding="utf-8")) if prior_files else None
    payload = {
        "schema_version": "1.0",
        "server_id": args.server_id,
        "collected_at": collected.isoformat().replace("+00:00", "Z"),
        "source": "GET /artifactory/api/v1/metrics/application",
        "classification": "observed",
        "counter_scope": "Successful Artifactory GET requests grouped as download and successful PUT/POST/PATCH requests grouped as upload",
        "counters": counters,
        "previous_snapshot": str(prior_files[-1]) if prior_files else None,
        "period_delta": delta(counters, prior),
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
