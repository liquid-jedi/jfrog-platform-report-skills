#!/usr/bin/env python3
"""Record explicitly supplied MCP Registry security evidence in an AI envelope."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--type", required=True)
    parser.add_argument("--governance", required=True)
    parser.add_argument("--security-status", required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    mcp = evidence.setdefault("inventory", {}).setdefault("mcp_servers", {})
    assets = [row for row in mcp.get("visible_assets") or [] if row.get("name") != args.name]
    assets.append({"name": args.name, "type": args.type, "governance": args.governance,
                   "security_status": args.security_status, "source": args.source})
    mcp["visible_assets"] = sorted(assets, key=lambda row: row["name"].lower())
    mcp["security_observed"] = len(assets)
    mcp["security_counts"] = {
        "not_malicious": sum(row["security_status"].lower() == "not malicious" for row in assets),
        "malicious": sum(row["security_status"].lower() == "malicious" for row in assets),
        "not_scanned": sum(row["security_status"].lower() == "not scanned" for row in assets),
    }
    args.evidence.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(args.evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
