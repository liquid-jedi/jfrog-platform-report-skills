#!/usr/bin/env python3
"""Replace the point-in-time Access module in an existing normalized report."""
import argparse
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("enrich_report_modules", HERE / "enrich_report_modules.py")
ENRICH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENRICH)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--access-governance-evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    evidence = json.loads(args.access_governance_evidence.read_text(encoding="utf-8"))
    report["access_governance"] = ENRICH.build_access_governance(evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
