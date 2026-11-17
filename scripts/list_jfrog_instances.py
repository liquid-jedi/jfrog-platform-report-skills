#!/usr/bin/env python3
"""List configured JFrog CLI instances for a host-neutral first-run chooser."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


FIELD = re.compile(r"^\s*([^:]+):\s*(.*?)\s*$")


def parse_config_show(text: str) -> list[dict]:
    servers: list[dict] = []
    current: dict[str, str] = {}
    for line in text.splitlines() + [""]:
        match = FIELD.match(line)
        if match:
            key = match.group(1).strip().lower().replace(" ", "_")
            value = match.group(2).strip()
            if key == "server_id" and current.get("server_id"):
                servers.append(current)
                current = {}
            current[key] = value
        elif not line.strip() and current.get("server_id"):
            servers.append(current)
            current = {}
    normalized = []
    for item in servers:
        url = item.get("jfrog_platform_url") or item.get("artifactory_url") or item.get("url")
        normalized.append({
            "id": item["server_id"],
            "url": url,
            "default": str(item.get("default", "")).lower() in {"true", "yes"},
        })
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser(description="List configured JFrog CLI server instances")
    parser.add_argument("--input", type=Path, help="Parse saved `jf config show` output instead of invoking jf")
    args = parser.parse_args()
    if args.input:
        output = args.input.read_text(encoding="utf-8")
    else:
        result = subprocess.run(["jf", "config", "show"], text=True, capture_output=True)
        if result.returncode:
            raise SystemExit((result.stderr or result.stdout or "jf config show failed").strip())
        output = result.stdout
    servers = parse_config_show(output)
    if not servers:
        raise SystemExit("No configured JFrog CLI instances were found. Configure one before generating a live report.")
    print(json.dumps({"schema_version": "1.0", "servers": servers}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
