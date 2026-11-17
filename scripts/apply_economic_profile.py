#!/usr/bin/env python3
"""Attach optional external benchmark context to normalized report JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from economic_profile import build


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--server", required=True)
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--profile-snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    economic, _profile, _resolved_path = build(args.server, benchmark, None)
    report["economic_model"] = economic
    for note in report.get("availability_notes", []):
        if note.get("area") != "Economic context":
            continue
        note.update({"status": "Optional external benchmark",
                     "current_state": "Forrester TEI composite results are external research, not observed or derived customer savings.",
                     "next_step": "Include or exclude the benchmark section when choosing report sections."})
    report.setdefault("provenance", {})["economic_profile"] = {
        "resolved_path": None, "configured": False,
        "status": "benchmark_only",
        "classification": economic["classification"],
    }
    snapshot = {"schema_version": "1.0", "server_id": args.server,
                "status": "benchmark_only", "mode": "external_benchmark_context",
                "benchmark_id": benchmark["id"]}
    args.profile_snapshot.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
