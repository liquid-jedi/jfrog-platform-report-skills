# Architecture and implementation plan

## Product family

`JFrog Agentic Dashboard Skills` is the umbrella. Persona skills remain separate:

- `jfrog-ciso-report`: security and risk decisions.
- `jfrog-platform-report`: platform value, risk, governance and transformation decisions.
- Focused profiles/modules reuse shared evidence concepts without becoming one mega-skill.

The existing CISO skill is a structural reference for fixed-template rendering,
snapshots, and deterministic pagination. It is not the product specification for
this broader JFrog Platform report.

## Layers

1. Agent orchestration: intent, scope, authorization, and tool selection.
2. Collectors: read-only evidence with explicit status and provenance.
3. Normalization: stable versioned evidence independent of API response shape.
4. Calculation: deterministic metrics, scenarios, allocation, and double-count checks.
5. Presentation: validated JSON injected into a fixed HTML template.

Product modules are `curation`, `xray`, `artifactory`, `ai-security`, and `jas`.
Their metric ownership, cross-module links, and presentation rules are defined in
[product-modules.md](product-modules.md). Module filtering happens after normalization
and calculation so focused reports cannot change totals or classifications.

## Delivery sequence

1. Define evidence, assumptions, metric, and report schemas.
2. Implement Artifactory-only offline vertical slice.
3. Add source envelopes and collection diagnostics.
4. Establish the full-platform evidence contract (Artifactory, Xray including threat
   context, Curation, JAS, AI Catalog, Runtime, Frogbot, AppTrust, Agentic Remediation), then add
   collectors independently and mark unimplemented modules explicitly.
5. Add snapshot comparison and same-day rerun behavior.
6. Validate live APIs with JFrog MCP first; use official API specs/CLI only when MCP lacks the operation.
7. Generate Artifactory-only and full-platform fixture reports.
8. Apply persona/profile filters only after the full report and evidence ledger pass.

## Collector interface

Each collector returns `status`, `reason`, `complete`, `collected_at`, `source`,
`records`, and diagnostics. Valid states are `available`, `partial`, `no_data`,
`permission_denied`, `unlicensed`, `unsupported`, `not_configured`, and
`collection_failed`. Only `available`/`no_data` may support a genuine zero.

## Metric lineage

Every metric records source metric IDs, formula, classification, confidence, and data
gaps. Projected metrics additionally expose baseline, assumptions, applicability,
adoption coverage, realization factor, value per unit, three scenarios, and confidence.
# Live-run provenance boundary

Each live run is a clean evidence acquisition. The collector accepts a server, bounded
period and new raw-output directory; it does not accept prior report data. Raw API pages
are immutable run evidence and are recorded in a checksum manifest. Normalization and
rendering consume only that run's evidence.

Previous validated reports sit outside the collection boundary. They can be read only
after the current report validates, solely to create labelled trend deltas. A prior value
must never substitute for a missing current or historical API response.

## Collection cadence and reporting cadence

The operational collection unit is one local ISO week, Monday through Sunday. A run
without explicit dates always targets the last completed week, so a Tuesday run and a
Friday run resolve to identical boundaries. `current-week` is allowed only when the
reader explicitly asks for week-to-date and is always marked partial.

Each period has immutable timestamped run directories and one validated `latest.json`
pointer. Validation precedes promotion. This makes retries idempotent at the reporting
period level while retaining an audit trail of every attempt.

The monthly executive report is a view, not a second historical collection attempt.
It reads validated weekly archives, filters event-level records to the calendar month,
deduplicates stable event identities, and verifies continuous temporal coverage. For
point-in-time posture it selects the latest validated snapshot whose timestamp is no
later than month end. Additive event counts may be aggregated after filtering; distinct
counts are recomputed from events; rates are recomputed from their numerator and
denominator. Inventory, storage, percentages, unique counts and rates are never summed.

This split solves the Curation retention constraint: weekly collection preserves the
events before they expire, while the monthly report remains a truthful calendar-month
executive summary. It does not make past uncollected events recoverable.

## Missed-week recovery

Every invocation ends with a read-only coverage audit of the previous calendar month.
The audit evaluates validated `latest.json` pointers rather than treating any run
directory as successful. For each missing Monday–Sunday archive, it reports the week,
the portion overlapping the month, and whether the complete interval remains within
the configured Curation retention window. The agent offers eligible backfills but
does not start them without user approval. Expired Curation evidence remains
unavailable even when longer-lived Artifactory or Xray evidence can still be queried.

