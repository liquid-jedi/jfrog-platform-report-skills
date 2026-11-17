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
import time as monotonic_time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


HERE = Path(__file__).resolve().parent


def normalize_period_bound(value: str, timezone_name: str, *, end: bool) -> str:
    """Return an RFC3339 UTC bound, accepting a local date as a convenience."""
    zone = ZoneInfo(timezone_name)
    if len(value) == 10:
        day = datetime.strptime(value, "%Y-%m-%d").date()
        local = datetime.combine(day, time(23, 59, 59) if end else time.min, zone)
    else:
        local = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if local.tzinfo is None:
            local = local.replace(tzinfo=zone)
    return local.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_period(date_from: str, date_to: str, timezone_name: str) -> tuple[str, str]:
    start = normalize_period_bound(date_from, timezone_name, end=False)
    end = normalize_period_bound(date_to, timezone_name, end=True)
    if datetime.fromisoformat(end.replace("Z", "+00:00")) < datetime.fromisoformat(start.replace("Z", "+00:00")):
        raise ValueError("report period end precedes start")
    return start, end


def command_plan(args, run_dir: Path, weekly_root: Path) -> list[list[str]]:
    py = sys.executable
    raw = run_dir / "raw"
    seed = run_dir / "ai-security-seed.json"
    ai = run_dir / "ai-security.json"
    traffic = run_dir / "artifactory-traffic.json"
    traffic_report = run_dir / "data.traffic.json"
    economic_report = run_dir / "data.economic.json"
    snapshot_root = args.report_root / args.server / "snapshots" / "artifactory-traffic"
    commands = [
        [py, str(HERE / "collect_live.py"), "--server", args.server, "--date-from", args.date_from,
         "--date-to", args.date_to, "--timezone", args.timezone, "--cadence", "weekly", "--output", str(run_dir / "evidence.json"),
         "--raw-dir", str(raw)],
        [py, str(HERE / "build_report_from_live_evidence.py"), "--evidence", str(run_dir / "evidence.json"),
         "--raw-dir", str(raw), "--output", str(run_dir / "data.base.json")],
        [py, str(HERE / "collect_artifactory_traffic.py"), "--server-id", args.server,
         "--snapshot-root", str(snapshot_root), "--output", str(traffic)],
        [py, str(HERE / "apply_traffic_evidence.py"), "--report", str(run_dir / "data.base.json"),
         "--traffic", str(traffic), "--output", str(traffic_report)],
        [py, str(HERE / "apply_economic_profile.py"), "--report", str(traffic_report),
         "--server", args.server, "--benchmark", str(HERE.parent / "benchmarks" / "forrester-tei-2026.json"),
         "--profile-snapshot", str(run_dir / "economic-profile.snapshot.json"),
         "--output", str(economic_report)],
        [py, str(HERE / "collect_skill_security.py"), "--server-id", args.server, "--evidence", str(seed),
         "--output", str(ai), "--all-skills"],
        [py, str(HERE / "collect_access_governance.py"), "--server-id", args.server,
         "--output", str(run_dir / "access-governance.json")],
        [py, str(HERE / "collect_apptrust.py"), "--server-id", args.server,
         "--raw-dir", str(raw / "apptrust"), "--output", str(run_dir / "apptrust.json")],
        [py, str(HERE / "merge_current_evidence.py"), "--report", str(economic_report),
         "--ai-catalog-evidence", str(ai), "--access-governance-evidence", str(run_dir / "access-governance.json"),
         "--apptrust-evidence", str(run_dir / "apptrust.json"),
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


def execute(command: list[str], required: bool) -> tuple[bool, dict]:
    started = monotonic_time.monotonic()
    result = subprocess.run(command, text=True, capture_output=True)
    diagnostic = {"command": Path(command[1]).name, "required": required, "returncode": result.returncode,
                  "duration_seconds": round(monotonic_time.monotonic() - started, 3),
                  "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    if result.returncode and required:
        raise RuntimeError(
            f"{Path(command[1]).name} failed: {(result.stderr or result.stdout).strip()}\n"
            "The installed skill must not be edited in place. Preserve this run's diagnostics, "
            "then upgrade the package or report the collector defect."
        )
    return result.returncode == 0, diagnostic


def run(command: list[str], required: bool, diagnostics: list[dict]) -> bool:
    ok, diagnostic = execute(command, required)
    diagnostics.append(diagnostic)
    return ok


def run_parallel(tasks: list[tuple[list[str], bool]], diagnostics: list[dict]) -> list[bool]:
    """Run independent collectors concurrently and preserve diagnostic order."""
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        futures = [pool.submit(execute, command, required) for command, required in tasks]
        results = [future.result() for future in futures]
    diagnostics.extend(diagnostic for _, diagnostic in results)
    return [ok for ok, _ in results]


def mark_period_completeness(path: Path, completeness: str) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    value.setdefault("meta", {})["period_completeness"] = completeness
    value["meta"]["is_partial_period"] = completeness != "complete"
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def progress(message: str) -> None:
    print(message, flush=True)


def main() -> int:
    p = argparse.ArgumentParser(description="Generate and promote one live weekly JFrog Platform report")
    p.add_argument("--server", required=True); p.add_argument("--date-from", required=True); p.add_argument("--date-to", required=True)
    p.add_argument("--period-key", required=True); p.add_argument("--month", required=True)
    p.add_argument("--timezone", default="UTC"); p.add_argument("--report-root", required=True, type=Path)
    p.add_argument("--modules", default="all", help="Comma-separated report section IDs; collection remains complete")
    p.add_argument("--ai-catalog-seed", type=Path, help="Optional same-run supported MCP/model/plugin registry evidence")
    p.add_argument("--period-completeness", choices=("complete", "week_to_date", "explicit"), default="complete")
    p.add_argument("--run-id"); p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    args.date_from, args.date_to = normalize_period(args.date_from, args.date_to, args.timezone)
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
    diagnostics_path = run_dir / "collection-diagnostics.json"
    try:
        progress("Brewing your JFrog Platform report. This usually takes 1 to 3 minutes, so this is a good time to grab a coffee.")
        progress("[1/5] Collecting Artifactory, Curation and Xray evidence")
        run(commands[0], True, diagnostics); run(commands[1], True, diagnostics)
        progress("[2/5] Collecting traffic, AI security, access and AppTrust posture in parallel")
        traffic_ok, skill_ok, access_ok, apptrust_ok = run_parallel(
            [(commands[2], False), (commands[5], False), (commands[6], False), (commands[7], False)], diagnostics
        )
        if traffic_ok:
            run(commands[3], True, diagnostics)
        else:
            shutil.copyfile(run_dir / "data.base.json", run_dir / "data.traffic.json")
        progress("[3/5] Applying the optional external benchmark context")
        run(commands[4], True, diagnostics)
        ai_path = run_dir / "ai-security.json"
        if not ai_path.exists(): shutil.copyfile(run_dir / "ai-security-seed.json", ai_path)
        if not skill_ok:
            value = json.loads(ai_path.read_text(encoding="utf-8")); value["status"] = "partial"
            value.setdefault("limitations", []).append("Skills security collection failed; see collection diagnostics.")
            ai_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        merge = commands[8]
        if not access_ok:
            merge = [part for part in merge if part not in ("--access-governance-evidence", str(run_dir / "access-governance.json"))]
        if not apptrust_ok:
            merge = [part for part in merge if part not in ("--apptrust-evidence", str(run_dir / "apptrust.json"))]
        run(merge, True, diagnostics)
        mark_period_completeness(run_dir / "data.current.json", args.period_completeness)
        progress("[4/5] Validating comparable week-over-week trends")
        run(commands[9], True, diagnostics)
        progress("[5/5] Rendering and validating the fixed report template")
        run(commands[10], True, diagnostics)
    finally:
        diagnostics_path.write_text(json.dumps(diagnostics, indent=2) + "\n", encoding="utf-8")
    report = json.loads((run_dir / "data.json").read_text(encoding="utf-8"))
    if report.get("schema_version") != "0.3" or not (run_dir / "report.html").stat().st_size:
        raise RuntimeError("report validation failed")
    period_dir.mkdir(parents=True, exist_ok=True)
    pointer = {"schema_version": "1.0", "period_key": args.period_key, "run_directory": str(run_dir),
               "promoted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "validation_status": "passed"}
    (period_dir / "latest.json").write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(run_dir / "data.json", period_dir / "data.json"); shutil.copyfile(run_dir / "report.html", period_dir / "report.html")
    progress("Report validated and promoted successfully.")
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
