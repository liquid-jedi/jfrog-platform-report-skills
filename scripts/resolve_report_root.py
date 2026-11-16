#!/usr/bin/env python3
"""Resolve a portable report root without silently choosing a first-run location."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def default_config_path(environment: dict[str, str]) -> Path:
    """Use the native config root without maintaining OS-specific implementations."""
    if environment.get("JFROG_REPORT_CONFIG"):
        return Path(environment["JFROG_REPORT_CONFIG"]).expanduser()
    if environment.get("XDG_CONFIG_HOME"):
        return Path(environment["XDG_CONFIG_HOME"]).expanduser() / "jfrog-platform-value-report" / "config.json"
    if os.name == "nt" and environment.get("APPDATA"):
        return Path(environment["APPDATA"]) / "JFrog" / "PlatformValueReport" / "config.json"
    return Path.home() / ".config" / "jfrog-platform-value-report" / "config.json"


def resolve(server: str, explicit: str | None, config_path: Path, environment: dict[str, str]) -> dict:
    configured = None
    source = None
    if explicit:
        configured, source = explicit, "argument"
    elif environment.get("JFROG_REPORT_ROOT"):
        configured, source = environment["JFROG_REPORT_ROOT"], "environment"
    elif config_path.is_file():
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            configured = (payload.get("instances") or {}).get(server, {}).get("report_root") or payload.get("report_root")
            if configured:
                source = "saved_config"
        except (OSError, json.JSONDecodeError):
            pass
    suggested = str(Path.home() / "jfrog-platform-reports")
    if not configured:
        return {
            "status": "needs_input", "server_id": server, "suggested_report_root": suggested,
            "question": f"Where should reports for {server} be saved? Press Enter to use {suggested}.",
            "path_template": "<report-root>/<instance>/weekly/<week-ending>/report.html",
        }
    root = Path(configured).expanduser().resolve()
    return {
        "status": "resolved", "source": source, "server_id": server, "report_root": str(root),
        "instance_root": str(root / server),
        "weekly_path_template": str(root / server / "weekly" / "<week-ending>" / "report.html"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve the JFrog platform report output root")
    parser.add_argument("--server", required=True)
    parser.add_argument("--report-root")
    parser.add_argument("--config", type=Path, default=default_config_path(dict(os.environ)))
    args = parser.parse_args()
    print(json.dumps(resolve(args.server, args.report_root, args.config, dict(os.environ)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
