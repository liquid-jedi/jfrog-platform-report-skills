#!/usr/bin/env python3
"""Validate and save one per-instance economic profile with private permissions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from economic_profile import default_profile_path, validate_profile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    profile = json.loads(args.input.read_text(encoding="utf-8"))
    validate_profile(profile, args.server)
    output = args.output or default_profile_path(args.server)
    if output.exists() and not args.replace:
        raise SystemExit(f"refusing to replace existing profile without --replace: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        output.chmod(0o600)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
