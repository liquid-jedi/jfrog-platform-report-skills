#!/usr/bin/env python3
"""Print the portable report-section selection contract for any agent host."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


CATALOG = Path(__file__).resolve().parent.parent / "assets" / "report-sections.json"


def selection(catalog: dict, requested: str | None) -> dict:
    known = [row["id"] for row in catalog["sections"]]
    choice = (requested or "full").strip().lower()
    if choice in {"all", "full"}:
        profile = "full"
        selected = catalog["profiles"]["full"]
    elif choice == "executive":
        profile = "executive"
        selected = catalog["profiles"]["executive"]
    else:
        profile = "custom"
        selected = [part.strip() for part in choice.split(",") if part.strip()]
    unknown = sorted(set(selected) - set(known))
    if unknown:
        raise ValueError(f"unknown report sections: {', '.join(unknown)}")
    return {
        "schema_version": "1.0",
        "selection_required": False,
        "default": "full",
        "profile": profile,
        "show_section_list": profile == "custom",
        "profiles": catalog["profiles"],
        "sections": catalog["sections"],
        "selected": selected,
        "renderer_modules": ",".join(selected),
        "prompt": "Report: Full (recommended). Reply Proceed to continue, Executive for a concise leadership view, or Custom to choose individual sections."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="List and validate modular JFrog report sections")
    parser.add_argument("--select", help="Full, Executive, or comma-separated custom section IDs")
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    try:
        result = selection(catalog, args.select)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
