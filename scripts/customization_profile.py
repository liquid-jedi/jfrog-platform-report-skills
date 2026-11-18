#!/usr/bin/env python3
"""Load and validate an optional, declarative report customization profile."""

from __future__ import annotations

import argparse
import fnmatch
import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COLLECTORS = ROOT / "assets" / "collector-registry.json"
SECTIONS = ROOT / "assets" / "report-sections.json"
VALID_MODES = {"auto", "required", "disabled"}
VALID_SCOPE_TYPES = {"all", "artifactory_repository", "jfrog_project", "source_repository"}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _strings(value: object, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ValueError(f"{field} must be an array of non-empty strings")
    return list(dict.fromkeys(item.strip() for item in value))


def default_profile() -> dict:
    registry = _load_json(COLLECTORS)
    sections = _load_json(SECTIONS)
    modes = {row["id"]: row["default_mode"] for row in registry["collectors"]}
    return {
        "profile_version": 1,
        "name": "default",
        "collectors": modes,
        "collector_decisions": {collector_id: {"mode": mode, "reason": "default_behavior"}
                                for collector_id, mode in modes.items()},
        "warnings": [],
        "sections": list(sections["profiles"]["full"]),
        "scope": {
            "type": "all", "include": [], "exclude": [],
            "mapping_policy": "explicit_only", "source_mappings": [],
        },
    }


def load_profile(path: Path | None) -> dict:
    resolved = default_profile()
    if path is None:
        return resolved
    source = tomllib.loads(path.read_text(encoding="utf-8"))
    if source.get("profile_version") != 1:
        raise ValueError("profile_version must be 1")
    resolved["name"] = str(source.get("name") or path.stem).strip()
    if not resolved["name"]:
        raise ValueError("profile name must not be empty")

    registry = {row["id"]: row for row in _load_json(COLLECTORS)["collectors"]}
    supplied_collectors = source.get("collectors") or {}
    if not isinstance(supplied_collectors, dict):
        raise ValueError("collectors must be a TOML table")
    unknown_collectors = sorted(set(supplied_collectors) - set(registry))
    if unknown_collectors:
        raise ValueError(f"unknown collectors: {', '.join(unknown_collectors)}")
    for collector_id, mode in supplied_collectors.items():
        if not isinstance(mode, str) or mode not in VALID_MODES:
            raise ValueError(f"collector {collector_id} must be auto, required or disabled")
        if not registry[collector_id].get("configurable") and mode != registry[collector_id]["default_mode"]:
            raise ValueError(f"collector {collector_id} is not configurable in profile version 1")
        resolved["collectors"][collector_id] = mode

    section_table = source.get("sections") or {}
    if not isinstance(section_table, dict):
        raise ValueError("sections must be a TOML table")
    known_sections = {row["id"] for row in _load_json(SECTIONS)["sections"]}
    selected_sections = _strings(section_table.get("include"), "sections.include")
    if selected_sections:
        unknown_sections = sorted(set(selected_sections) - known_sections)
        if unknown_sections:
            raise ValueError(f"unknown report sections: {', '.join(unknown_sections)}")
        resolved["sections"] = selected_sections

    scope = source.get("scope") or {}
    if not isinstance(scope, dict):
        raise ValueError("scope must be a TOML table")
    scope_type = str(scope.get("type") or "all")
    if scope_type not in VALID_SCOPE_TYPES:
        raise ValueError(f"scope.type must be one of: {', '.join(sorted(VALID_SCOPE_TYPES))}")
    include = _strings(scope.get("include"), "scope.include")
    exclude = _strings(scope.get("exclude"), "scope.exclude")
    mappings = scope.get("source_mappings") or []
    if not isinstance(mappings, list):
        raise ValueError("scope.source_mappings must be an array of tables")
    normalized_mappings = []
    for index, row in enumerate(mappings):
        if not isinstance(row, dict) or not str(row.get("source") or "").strip():
            raise ValueError(f"scope.source_mappings[{index}] requires source")
        normalized_mappings.append({
            "source": str(row["source"]).strip(),
            "repositories": _strings(row.get("repositories"), f"scope.source_mappings[{index}].repositories"),
            "projects": _strings(row.get("projects"), f"scope.source_mappings[{index}].projects"),
        })
    if scope_type != "all" and not include:
        raise ValueError("scope.include is required when scope.type is not all")
    if scope_type == "source_repository" and not normalized_mappings:
        raise ValueError("source_repository scope requires explicit source_mappings")
    resolved["scope"] = {
        "type": scope_type, "include": include, "exclude": exclude,
        "mapping_policy": "explicit_only", "source_mappings": normalized_mappings,
    }
    decisions = {}
    for collector_id, definition in registry.items():
        mode = resolved["collectors"][collector_id]
        if scope_type in definition.get("scope_support", ["all"]):
            decisions[collector_id] = {"mode": mode, "reason": (
                "disabled_by_profile" if mode == "disabled" else "selected_by_profile"
            )}
            continue
        if mode == "required":
            raise ValueError(
                f"collector {collector_id} does not support {scope_type} scope and cannot be required"
            )
        if mode == "auto":
            resolved["collectors"][collector_id] = "disabled"
            decisions[collector_id] = {"mode": "disabled", "reason": "scope_not_supported"}
        else:
            decisions[collector_id] = {"mode": "disabled", "reason": "disabled_by_profile"}
    resolved["collector_decisions"] = decisions
    section_collectors = {
        "apptrust": "apptrust", "ai-security": "ai-security", "access": "access", "economic": "economic"
    }
    resolved["warnings"] = [
        f"section {section_id} is selected but collector {collector_id} is disabled"
        for section_id, collector_id in section_collectors.items()
        if section_id in resolved["sections"] and resolved["collectors"][collector_id] == "disabled"
    ]
    resolved["source_file"] = path.name
    return resolved


def matches(value: str, include: list[str], exclude: list[str]) -> bool:
    included = not include or any(fnmatch.fnmatchcase(value, pattern) for pattern in include)
    excluded = any(fnmatch.fnmatchcase(value, pattern) for pattern in exclude)
    return included and not excluded


def resolve_repository_scope(profile: dict, repositories: list[dict]) -> tuple[set[str], dict]:
    scope = profile["scope"]
    available = {str(row.get("key") or row.get("repoKey") or ""): row for row in repositories}
    available.pop("", None)
    scope_type = scope["type"]
    requested = list(scope["include"])
    selected: set[str]
    mapped_sources: list[str] = []
    mapped_repository_requests: set[str] = set()
    unmatched: list[str] = []
    if scope_type == "all":
        selected = set(available)
    elif scope_type == "artifactory_repository":
        selected = {key for key in available if matches(key, scope["include"], scope["exclude"])}
        unmatched = [pattern for pattern in scope["include"]
                     if not any(fnmatch.fnmatchcase(key, pattern) for key in available)]
    elif scope_type == "jfrog_project":
        selected = {key for key, row in available.items()
                    if matches(str(row.get("projectKey") or "Unassigned"), scope["include"], scope["exclude"])}
        projects = {str(row.get("projectKey") or "Unassigned") for row in available.values()}
        unmatched = [pattern for pattern in scope["include"]
                     if not any(fnmatch.fnmatchcase(project, pattern) for project in projects)]
    else:
        selected = set()
        for mapping in scope["source_mappings"]:
            source = mapping["source"]
            if not matches(source, scope["include"], scope["exclude"]):
                continue
            mapped_sources.append(source)
            mapped_repository_requests.update(mapping["repositories"])
            selected.update(mapping["repositories"])
            for key, row in available.items():
                if str(row.get("projectKey") or "") in mapping["projects"]:
                    selected.add(key)
        unmatched = [source for source in scope["include"]
                     if not any(fnmatch.fnmatchcase(mapping["source"], source)
                                for mapping in scope["source_mappings"])]
        selected.intersection_update(available)
    ledger = {
        "scope_type": scope_type,
        "mapping_policy": scope["mapping_policy"],
        "requested": requested,
        "available_repositories": len(available),
        "selected_repositories": len(selected),
        "excluded_repositories": len(available) - len(selected),
        "mapped_sources": mapped_sources,
        "unresolved_mapped_repositories": sorted(mapped_repository_requests - set(available)),
        "unmatched_requests": unmatched,
        "selected_repository_keys": [] if scope_type == "all" else sorted(selected),
    }
    return selected, ledger


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and resolve a JFrog Platform report profile")
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        value = load_profile(args.profile)
    except (OSError, tomllib.TOMLDecodeError, ValueError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(value, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(args.output)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
