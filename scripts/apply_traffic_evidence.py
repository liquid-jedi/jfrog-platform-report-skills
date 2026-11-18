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
    removed = {"period-downloads", "period-uploads", "binary-cache-hit-rate"}
    art["metrics"] = [metric for metric in art.get("metrics") or [] if metric.get("id") not in removed]
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
