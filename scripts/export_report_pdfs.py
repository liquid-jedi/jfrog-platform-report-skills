#!/usr/bin/env python3
"""Export deterministic Executive and Full PDFs from a rendered report HTML file."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def browser_candidates() -> list[str]:
    if sys.platform == "darwin":
        return [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    return ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"]


def resolve_browser(explicit: str | None) -> str:
    candidates = [explicit] if explicit else browser_candidates()
    for candidate in candidates:
        if not candidate:
            continue
        path = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
        if path:
            return str(path)
    raise RuntimeError("Chrome, Chromium or Microsoft Edge is required for PDF export")


def export_command(browser: str, html: Path, output: Path, mode: str) -> list[str]:
    uri = html.resolve().as_uri() + f"?export={mode}"
    return [
        browser,
        "--headless",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-pdf-header-footer",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=1500",
        f"--print-to-pdf={output.resolve()}",
        uri,
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export shareable report PDFs")
    parser.add_argument("--html", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--mode", choices=("executive", "full", "both"), default="both")
    parser.add_argument("--browser", help="Explicit Chrome, Chromium or Edge executable")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.html.is_file():
        raise FileNotFoundError(args.html)
    browser = resolve_browser(args.browser)
    modes = ("executive", "full") if args.mode == "both" else (args.mode,)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for mode in modes:
        output = args.output_dir / f"{mode}-report.pdf"
        command = export_command(browser, args.html, output, mode)
        if args.dry_run:
            print(" ".join(command))
            continue
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode or not output.is_file() or output.stat().st_size == 0:
            diagnostic = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"{mode} PDF export failed: {diagnostic or 'no output produced'}")
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
