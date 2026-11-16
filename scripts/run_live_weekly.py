#!/usr/bin/env python3
"""Canonical read-only weekly live-report orchestrator.

The runner keeps period activity and current posture separate. Optional product
collectors may fail without suppressing the base report, but their failure is
persisted and rendered as unavailable/partial rather than zero.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


HERE = Path(__file__).resolve().parent


def command_plan(args, run_dir: Path, weekly_root: Path) -> list[list[str]]:
    py = sys.executable
    raw = run_dir / "raw"
    seed = run_dir / "ai-security-seed.json"
    ai = run_dir / "ai-security.json"
    commands = [
        [py, str(HERE / "collect_live.py"), "--server", args.server, "--date-from", args.date_from,
         "--date-to", args.date_to, "--cadence", "weekly", "--output", str(run_dir / "evidence.json"),
         "--raw-dir", str(raw)],
        [py, str(HERE / "build_report_from_live_evidence.py"), "--evidence", str(run_dir / "evidence.json"),
         "--raw-dir", str(raw), "--output", str(run_dir / "data.base.json")],
        [py, str(HERE / "collect_skill_security.py"), "--server-id", args.server, "--evidence", str(seed),
         "--output", str(ai), "--all-skills"],
        [py, str(HERE / "collect_access_governance.py"), "--server-id", args.server,
         "--output", str(run_dir / "access-governance.json")],
        [py, str(HERE / "merge_current_evidence.py"), "--report", str(run_dir / "data.base.json"),
         "--ai-catalog-evidence", str(ai), "--access-governance-evidence", str(run_dir / "access-governance.json"),
         "--output", str(run_dir / "data.current.json")],
        [py, str(HERE / "apply_weekly_trends.py"), "--report", str(run_dir / "data.current.json"),
         "--weekly-root", str(weekly_root), "--month", args.month, "--timezone", args.timezone,
         "--output", str(run_dir / "data.json")],
        [py, str(HERE / "render_report.py"), "--data", str(run_dir / "data.json"),
         "--template", str(HERE.parent / "assets" / "dashboard.html"), "--output", str(run_dir / "report.html"),
         "--modules", args.modules],
    ]
    return commands


def ai_seed(path: Path, supplied: Path | None) -> None:
    if supplied:
        shutil.copyfile(supplied, path)
        return
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    unavailable = lambda reason: {"status": "unavailable", "reason": reason, "visible_assets": []}
    payload = {
        "schema_version": "1.0", "collected_at": now, "status": "partial",
        "source": "Automated weekly AI security collection",
        "inventory": {
            "models": unavailable("No supported model-registry collector supplied"),
            "mcp_servers": unavailable("No supported MCP Registry collector supplied"),
            "skills": unavailable("Skills collector has not completed"),
            "plugins": unavailable("No supported plugin-registry security collector supplied"),
        },
        "limitations": ["Unavailable asset classes are not treated as zero."],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run(command: list[str], required: bool, diagnostics: list[dict]) -> bool:
    result = subprocess.run(command, text=True, capture_output=True)
    diagnostics.append({"command": Path(command[1]).name, "required": required, "returncode": result.returncode,
                        "stdout": result.stdout.strip(), "stderr": result.stderr.strip()})
    if result.returncode and required:
        raise RuntimeError(f"{Path(command[1]).name} failed: {(result.stderr or result.stdout).strip()}")
    return result.returncode == 0


def main() -> int:
    p = argparse.ArgumentParser(description="Generate and promote one live weekly CIO report")
    p.add_argument("--server", required=True); p.add_argument("--date-from", required=True); p.add_argument("--date-to", required=True)
    p.add_argument("--period-key", required=True); p.add_argument("--month", required=True)
    p.add_argument("--timezone", default="UTC"); p.add_argument("--report-root", required=True, type=Path)
    p.add_argument("--modules", default="all", help="Comma-separated report section IDs; collection remains complete")
    p.add_argument("--ai-catalog-seed", type=Path, help="Optional same-run supported MCP/model/plugin registry evidence")
    p.add_argument("--run-id"); p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    weekly_root = args.report_root / args.server / "weekly"
    period_dir = weekly_root / args.period_key
    run_dir = period_dir / "runs" / run_id
    commands = command_plan(args, run_dir, weekly_root)
    if args.dry_run:
        print(json.dumps({"run_directory": str(run_dir), "commands": commands}, indent=2)); return 0

    (run_dir / "raw").mkdir(parents=True, exist_ok=False)
    ai_seed(run_dir / "ai-security-seed.json", args.ai_catalog_seed)
    diagnostics: list[dict] = []
    run(commands[0], True, diagnostics); run(commands[1], True, diagnostics)
    skill_ok = run(commands[2], False, diagnostics)
    ai_path = run_dir / "ai-security.json"
    if not ai_path.exists(): shutil.copyfile(run_dir / "ai-security-seed.json", ai_path)
    if not skill_ok:
        value = json.loads(ai_path.read_text(encoding="utf-8")); value["status"] = "partial"
        value.setdefault("limitations", []).append("Skills security collection failed; see collection diagnostics.")
        ai_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    access_ok = run(commands[3], False, diagnostics)
    merge = commands[4]
    if not access_ok:
        merge = [part for part in merge if part not in ("--access-governance-evidence", str(run_dir / "access-governance.json"))]
    run(merge, True, diagnostics); run(commands[5], True, diagnostics); run(commands[6], True, diagnostics)
    (run_dir / "collection-diagnostics.json").write_text(json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8")
    report = json.loads((run_dir / "data.json").read_text(encoding="utf-8"))
    if report.get("schema_version") != "0.3" or not (run_dir / "report.html").stat().st_size:
        raise RuntimeError("report validation failed")
    period_dir.mkdir(parents=True, exist_ok=True)
    pointer = {"schema_version": "1.0", "period_key": args.period_key, "run_directory": str(run_dir),
               "promoted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "validation_status": "passed"}
    (period_dir / "latest.json").write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(run_dir / "data.json", period_dir / "data.json"); shutil.copyfile(run_dir / "report.html", period_dir / "report.html")
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
