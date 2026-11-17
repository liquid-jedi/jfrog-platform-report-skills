#!/usr/bin/env python3
"""Collect a redacted Access-token and OIDC governance snapshot via jf api."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


def jf_api(server: str, path: str):
    proc = subprocess.run(
        ["jf", "api", "--server-id", server, path],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode:
        raise RuntimeError(f"jf api failed for {path}: {proc.stderr.strip()}")
    return json.loads(proc.stdout or "null")


def token_summary(payload, now: int):
    rows = payload.get("tokens", []) if isinstance(payload, dict) else []
    expiring = [r for r in rows if isinstance(r.get("expiry"), (int, float))]
    remaining = [max(0, int((r["expiry"] - now) / 86400)) for r in expiring if r["expiry"] > now]
    rotation_queue = []
    for row in expiring:
        days = int((row["expiry"] - now) / 86400)
        if 0 < row["expiry"] - now <= 30 * 86400:
            token_key = str(row.get("token_id") or row.get("description") or row.get("subject") or "unknown")
            rotation_queue.append({
                "reference": hashlib.sha256(token_key.encode("utf-8")).hexdigest()[:10],
                "owner": row.get("subject") or "Unassigned",
                "description": row.get("description") or "No description",
                "expires_at": datetime.fromtimestamp(row["expiry"], timezone.utc).date().isoformat(),
                "days_remaining": max(0, days),
                "last_used": row.get("last_used") or "Never used",
            })
    rotation_queue.sort(key=lambda item: (item["days_remaining"], item["owner"], item["reference"]))
    return {
        "listed_active": len(rows),
        "expiring": len(expiring),
        "non_expiring": sum(r.get("expiry") is None for r in rows),
        "issued_last_7_days": sum(isinstance(r.get("issued_at"), (int, float)) and r["issued_at"] >= now - 7 * 86400 for r in rows),
        "issued_last_30_days": sum(isinstance(r.get("issued_at"), (int, float)) and r["issued_at"] >= now - 30 * 86400 for r in rows),
        "expires_within_7_days": sum(now < r["expiry"] <= now + 7 * 86400 for r in expiring),
        "expires_within_30_days": sum(now < r["expiry"] <= now + 30 * 86400 for r in expiring),
        "expires_within_90_days": sum(now < r["expiry"] <= now + 90 * 86400 for r in expiring),
        "long_lived_over_90_days": sum(r["expiry"] > now + 90 * 86400 for r in expiring),
        "refreshable": sum(r.get("refreshable") is True for r in rows),
        "never_used": sum(not r.get("last_used") for r in rows),
        "median_days_remaining": sorted(remaining)[len(remaining) // 2] if remaining else None,
        "maximum_days_remaining": max(remaining) if remaining else None,
        "rotation_queue": rotation_queue,
        "expired": None,
        "expired_note": "The active-token endpoint does not return expired or revoked history. An expired-token list cannot be reconstructed from this response; future report snapshots can record tokens as they leave the active inventory.",
        "privacy_note": "Rotation references are deterministic hashes of token metadata. Token IDs, secrets and scopes are never written to the report.",
    }


def provider_family(row):
    text = " ".join(str(row.get(k) or "") for k in ("provider_type", "issuer_url", "name", "token_issuer")).lower()
    if "github" in text:
        return "GitHub"
    if "gitlab" in text:
        return "GitLab"
    if "azure" in text or "ado" in text:
        return "Azure DevOps"
    return str(row.get("provider_type") or "Other")


def mapping_rows(provider, mappings):
    out = []
    for item in mappings if isinstance(mappings, list) else []:
        claims = item.get("claims") or {}
        repositories = []
        for key in ("repository", "project_path", "repo", "project"):
            value = claims.get(key)
            if isinstance(value, str) and value:
                repositories.append({"claim": key, "pattern": value})
        out.append({
            "provider": provider.get("name"),
            "provider_family": provider_family(provider),
            "mapping": item.get("name"),
            "repository_claims": repositories,
            "claim_keys": sorted(claims),
            "token_ttl_seconds": (item.get("token_spec") or {}).get("expires_in"),
        })
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--server-id", required=True)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--as-of", help="ISO timestamp; defaults to current UTC time")
    args = p.parse_args()
    moment = datetime.fromisoformat(args.as_of.replace("Z", "+00:00")) if args.as_of else datetime.now(timezone.utc)
    tokens = jf_api(args.server_id, "/access/api/v1/tokens")
    providers = jf_api(args.server_id, "/access/api/v1/oidc") or []
    all_mappings = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs = {
            pool.submit(jf_api, args.server_id, f"/access/api/v1/oidc/{quote(str(row.get('name')), safe='')}/identity_mappings"): row
            for row in providers if row.get("name")
        }
        for future in as_completed(jobs):
            provider = jobs[future]
            all_mappings.extend(mapping_rows(provider, future.result()))
    families = Counter(provider_family(row) for row in providers)
    repo_patterns = [
        {"provider": m["provider"], "provider_family": m["provider_family"], "mapping": m["mapping"], **claim}
        for m in all_mappings for claim in m["repository_claims"]
    ]
    output = {
        "schema_version": "1.0",
        "server_id": args.server_id,
        "collected_at": moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "JFrog Access REST API",
        "tokens": token_summary(tokens, int(moment.timestamp())),
        "oidc": {
            "providers_total": len(providers),
            "providers_by_family": sorted(families.items()),
            "identity_mappings_total": len(all_mappings),
            "repository_claim_patterns_total": len(repo_patterns),
            "repository_claim_patterns": sorted(repo_patterns, key=lambda x: (x["provider_family"], x["provider"], x["mapping"])),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
