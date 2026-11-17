#!/usr/bin/env python3
"""Collect bounded AppTrust application and release-governance evidence.

The collector uses the supported OneModel GraphQL endpoint. Application inventory is
fully cursor-paginated. Detail enrichment is limited to applications that are high or
critical, production, or end-of-life so the standard weekly report does not turn into
an exhaustive platform crawl.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


INVENTORY_PAGE = 250
DETAIL_BATCH = 8


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def gql_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


class OneModel:
    def __init__(self, server: str, raw_dir: Path):
        self.server = server
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.sequence = 0
        self.sources: list[dict] = []

    def query(self, source_id: str, document: str) -> dict:
        self.sequence += 1
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"query": document}, handle, separators=(",", ":"))
            payload_path = Path(handle.name)
        command = [
            "jf", "api", "/onemodel/api/v1/graphql", "-X", "POST",
            "-H", "Content-Type: application/json", "--input", str(payload_path),
            "--server-id", self.server, "--timeout", "180",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=195)
        finally:
            payload_path.unlink(missing_ok=True)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip() or "OneModel request failed")
        try:
            payload = json.loads(result.stdout or "null")
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"OneModel returned non-JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("OneModel returned a non-object response")
        if payload.get("errors"):
            messages = "; ".join(str(item.get("message") or item) for item in payload["errors"])
            raise RuntimeError(f"OneModel GraphQL error: {messages}")
        raw_path = self.raw_dir / f"{self.sequence:03d}-{source_id}.json"
        blob = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
        raw_path.write_bytes(blob)
        self.sources.append({
            "id": source_id, "endpoint": "/onemodel/api/v1/graphql", "method": "POST",
            "raw_file": raw_path.name, "sha256": hashlib.sha256(blob).hexdigest(),
            "collected_at": utc_now(), "status": "available", "complete": True,
        })
        return payload


def inventory_query(after: str | None = None) -> str:
    after_arg = f", after: {gql_string(after)}" if after else ""
    return """query {
      applications {
        searchApplications(first: %d, where: {}%s) {
          totalCount
          edges { node { key projectKey displayName criticality maturityLevel owners { name type } } }
          pageInfo { hasNextPage endCursor }
        }
      }
    }""" % (INVENTORY_PAGE, after_arg)


def detail_selection(key: str, alias: str) -> str:
    return f"""{alias}: getApplication(key: {gql_string(key)}) {{
      key projectKey displayName criticality maturityLevel owners {{ name type }}
      versionsConnection(first: 100) {{
        totalCount
        edges {{ node {{
          version createdAt status releaseStatus currentStageName
          sla {{ type value message }}
          promotionsConnection(first: 100) {{
            totalCount
            edges {{ node {{ sourceStageName targetStageName status createdAt createdBy messages {{ text }} }} }}
            pageInfo {{ hasNextPage endCursor }}
          }}
          releasables {{ releasablesCount artifactsCount totalSize }}
          sources {{ sourceType }}
          evidenceSubject {{
            evidenceConnection(first: 100) {{
              totalCount
              edges {{ node {{ predicateSlug predicateCategory verified systemEvidence createdAt stageName }} }}
              pageInfo {{ hasNextPage endCursor }}
            }}
          }}
        }} }}
        pageInfo {{ hasNextPage endCursor }}
      }}
    }}"""


def collect_inventory(client: OneModel) -> tuple[list[dict], int]:
    rows: list[dict] = []
    after = None
    total = None
    page = 0
    while True:
        page += 1
        payload = client.query(f"apptrust-applications-{page:04d}", inventory_query(after))
        connection = payload["data"]["applications"]["searchApplications"]
        if total is None:
            total = int(connection.get("totalCount") or 0)
        elif total != int(connection.get("totalCount") or 0):
            raise RuntimeError("AppTrust application total changed during pagination")
        rows.extend(edge["node"] for edge in connection.get("edges") or [] if edge.get("node"))
        info = connection.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            break
        next_cursor = info.get("endCursor")
        if not next_cursor or next_cursor == after:
            raise RuntimeError("AppTrust application pagination did not advance")
        after = next_cursor
    if len(rows) != total:
        raise RuntimeError(f"AppTrust pagination incomplete: fetched {len(rows)} of {total}")
    if len({row.get('key') for row in rows}) != len(rows):
        raise RuntimeError("AppTrust pagination returned duplicate application keys")
    return rows, page


def needs_detail(application: dict) -> bool:
    return (
        str(application.get("criticality") or "").lower() in {"critical", "high"}
        or str(application.get("maturityLevel") or "").lower() in {"production", "end_of_life"}
    )


def collect_details(client: OneModel, applications: list[dict]) -> tuple[list[dict], int]:
    selected = [row for row in applications if needs_detail(row)]
    detailed: list[dict] = []
    for start in range(0, len(selected), DETAIL_BATCH):
        batch = selected[start:start + DETAIL_BATCH]
        selections = [detail_selection(row["key"], f"app{index}") for index, row in enumerate(batch)]
        payload = client.query(f"apptrust-details-{start // DETAIL_BATCH + 1:04d}",
                               "query { applications { " + "\n".join(selections) + " } }")
        result = payload["data"]["applications"]
        for index, expected in enumerate(batch):
            item = result.get(f"app{index}")
            if not item or item.get("key") != expected.get("key"):
                raise RuntimeError(f"AppTrust detail result missing for {expected.get('key')}")
            versions = item.get("versionsConnection") or {}
            edges = versions.get("edges") or []
            if (versions.get("pageInfo") or {}).get("hasNextPage"):
                raise RuntimeError(
                    f"AppTrust application {item['key']} has more than 100 versions; "
                    "bounded standard collection refuses a partial detail result"
                )
            if len(edges) != int(versions.get("totalCount") or 0):
                raise RuntimeError(f"AppTrust version pagination incomplete for {item['key']}")
            for edge in edges:
                version = edge.get("node") or {}
                promotions = version.get("promotionsConnection") or {}
                if (promotions.get("pageInfo") or {}).get("hasNextPage"):
                    raise RuntimeError(
                        f"AppTrust promotion pagination incomplete for {item['key']} {version.get('version')}"
                    )
                if len(promotions.get("edges") or []) != int(promotions.get("totalCount") or 0):
                    raise RuntimeError(
                        f"AppTrust promotion total mismatch for {item['key']} {version.get('version')}"
                    )
                evidence = ((version.get("evidenceSubject") or {}).get("evidenceConnection") or {})
                if (evidence.get("pageInfo") or {}).get("hasNextPage"):
                    raise RuntimeError(
                        f"AppTrust evidence pagination incomplete for {item['key']} {version.get('version')}"
                    )
                if evidence and len(evidence.get("edges") or []) != int(evidence.get("totalCount") or 0):
                    raise RuntimeError(
                        f"AppTrust evidence total mismatch for {item['key']} {version.get('version')}"
                    )
            detailed.append(item)
    return detailed, len(selected)


def summarize(applications: list[dict], detailed: list[dict], pages: int) -> dict:
    versions = [edge.get("node") or {} for app in detailed
                for edge in ((app.get("versionsConnection") or {}).get("edges") or [])]
    promotions = [edge.get("node") or {} for version in versions
                  for edge in ((version.get("promotionsConnection") or {}).get("edges") or [])]
    evidence = [edge.get("node") or {} for version in versions
                for edge in ((((version.get("evidenceSubject") or {}).get("evidenceConnection") or {}).get("edges")) or [])]
    high_value_keys = {row.get("key") for row in detailed}
    return {
        "schema_version": "1.0", "status": "available", "collected_at": utc_now(),
        "source": "JFrog OneModel AppTrust GraphQL",
        "collection": {
            "applications_total_reported": len(applications), "applications_fetched": len(applications),
            "application_pages": pages, "details_selected": len(detailed),
            "detail_policy": "criticality in critical/high OR maturity in production/end_of_life",
            "complete": True,
        },
        "inventory": {
            "applications_total": len(applications),
            "projects_total": len({row.get("projectKey") for row in applications if row.get("projectKey")}),
            "criticality": dict(Counter(str(row.get("criticality") or "unspecified").lower() for row in applications)),
            "maturity": dict(Counter(str(row.get("maturityLevel") or "unspecified").lower() for row in applications)),
            "unowned": sum(not (row.get("owners") or []) for row in applications),
            "critical_unowned": sum(str(row.get("criticality") or "").lower() == "critical" and not (row.get("owners") or []) for row in applications),
        },
        "release_governance": {
            "applications_enriched": len(high_value_keys), "versions_total": len(versions),
            "versions_by_stage": dict(Counter(str(row.get("currentStageName") or "Unpromoted") for row in versions)),
            "release_status": dict(Counter(str(row.get("releaseStatus") or "Unknown") for row in versions)),
            "promotion_status": dict(Counter(str(row.get("status") or "Unknown") for row in promotions)),
            "promotions_total": len(promotions),
            "trusted_releases": sum(str(row.get("releaseStatus")) == "TRUSTED_RELEASE" for row in versions),
        },
        "evidence": {
            "records_total": len(evidence), "verified": sum(row.get("verified") is True for row in evidence),
            "unverified": sum(row.get("verified") is False for row in evidence),
            "by_predicate": dict(Counter(str(row.get("predicateSlug") or "Unknown") for row in evidence)),
            "gate_certifications": sum("gate" in str(row.get("predicateSlug") or "").lower() for row in evidence),
        },
        "applications": detailed,
        "limitations": [
            "Standard collection enriches only high-value applications; inventory totals cover every visible application.",
            "Application risk requires a deterministic Xray-to-package/build-to-AppTrust join; application inventory alone is not treated as affected risk.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect bounded AppTrust application governance evidence")
    parser.add_argument("--server-id", required=True)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    client = OneModel(args.server_id, args.raw_dir)
    try:
        applications, pages = collect_inventory(client)
        details, _ = collect_details(client, applications)
        result = summarize(applications, details, pages)
        result["raw_manifest"] = client.sources
    except RuntimeError as exc:
        text = str(exc)
        lowered = text.lower()
        status = "permission_denied" if "403" in lowered or "forbidden" in lowered else (
            "unsupported" if "cannot query field" in lowered or "not found" in lowered else "collection_failed"
        )
        result = {
            "schema_version": "1.0", "status": status, "collected_at": utc_now(),
            "source": "JFrog OneModel AppTrust GraphQL", "reason": text,
            "collection": {"complete": False}, "inventory": {}, "release_governance": {},
            "evidence": {}, "applications": [], "limitations": ["Unavailable values are not converted to zero."],
            "raw_manifest": client.sources,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
