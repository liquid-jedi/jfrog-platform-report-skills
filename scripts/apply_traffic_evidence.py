#!/usr/bin/env python3
"""Attach a classified traffic-counter snapshot to report JSON."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--traffic", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    traffic = json.loads(args.traffic.read_text(encoding="utf-8"))
    art = report.setdefault("artifactory_detail", {"status": "partial", "metrics": []})
    art["traffic_evidence"] = traffic
    delta = traffic.get("period_delta") or {}
    values = {
        "period-downloads": delta.get("download_requests_delta"),
        "period-uploads": delta.get("upload_requests_delta"),
        "binary-cache-hit-rate": delta.get("cache_fs_hit_rate"),
    }
    for metric in art.get("metrics") or []:
        if metric.get("id") not in values:
            continue
        metric["value"] = values[metric["id"]]
        metric["classification"] = "derived" if metric["value"] is not None else "unavailable"
        metric["source"] = traffic.get("source")
        metric["formula"] = "later cumulative counter − earlier cumulative counter"
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
