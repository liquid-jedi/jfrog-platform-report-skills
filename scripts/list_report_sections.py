#!/usr/bin/env python3
"""Print the portable report-section selection contract for any agent host."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


CATALOG = Path(__file__).resolve().parent.parent / "assets" / "report-sections.json"


def selection(catalog: dict, requested: str | None) -> dict:
    known = [row["id"] for row in catalog["sections"]]
    selected = known if not requested or requested == "all" else [part.strip() for part in requested.split(",") if part.strip()]
    unknown = sorted(set(selected) - set(known))
    if unknown:
        raise ValueError(f"unknown report sections: {', '.join(unknown)}")
    return {
        "schema_version": "1.0",
        "selection_required": requested is None,
        "default": "all",
        "profiles": catalog["profiles"],
        "sections": catalog["sections"],
        "selected": selected,
        "renderer_modules": ",".join(selected),
        "prompt": "Select report sections by number or name, or choose All (default). Collection remains complete; this choice controls report presentation only."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="List and validate modular JFrog report sections")
    parser.add_argument("--select", help="Comma-separated section IDs, or all")
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
