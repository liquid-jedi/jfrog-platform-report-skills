#!/usr/bin/env python3
"""Attach benchmark or approved customer economics to normalized report JSON."""

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
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--profile-snapshot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    economic, profile, resolved_path = build(args.server, benchmark, args.profile)
    report["economic_model"] = economic
    for note in report.get("availability_notes", []):
        if note.get("area") != "Economic context":
            continue
        if economic["status"] == "projected":
            note.update({"status": "Approved projection enabled",
                         "current_state": "Deterministic customer scenarios use the approved per-instance economic profile.",
                         "next_step": "Review assumptions and realized outcomes with Finance before using projections for investment decisions."})
        else:
            draft = (profile or {}).get("status") == "draft"
            note.update({"status": "Benchmark context available",
                         "current_state": "Forrester TEI composite results are shown only as an external benchmark; they are not customer results." + (" A draft customer profile exists but is not applied." if draft else ""),
                         "next_step": "Approve a per-instance customer profile to enable deterministic customer projections."})
    report.setdefault("provenance", {})["economic_profile"] = {
        "resolved_path": str(resolved_path), "configured": profile is not None,
        "status": (profile or {}).get("status", "not_configured"),
        "classification": economic["classification"],
    }
    snapshot = profile or {"schema_version": "1.0", "server_id": args.server,
                           "status": "not_configured", "mode": "benchmark_context",
                           "benchmark_id": benchmark["id"]}
    args.profile_snapshot.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
