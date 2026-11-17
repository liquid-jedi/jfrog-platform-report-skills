---
name: jfrog-platform-report
description: >-
  Generate modular, evidence-backed JFrog Platform Value & Risk reports. Use when a
  user says "generate weekly JFrog Platform report", asks for a JFrog platform report,
  executive value report, platform leadership report, adoption, efficiency, reliability, delivery,
  or platform-opportunity reporting. Supports Artifactory-only, Artifactory and Xray,
  full-platform, and offline fixture modes. Do not use for a security-only CISO report.
metadata:
  role: workflow
  version: "1.6.3"
---

# JFrog Platform Report Skill

Generate a deterministic report from structured JFrog evidence. The agent chooses
scope and orchestrates collection; scripts normalize, classify, calculate, validate,
and render. Never calculate financial or platform KPIs in free-form reasoning.

## Non-negotiable contracts

- Use the installed JFrog integration skill before live JFrog operations. Do not
  depend on a host-specific skill path; discover it through the host's normal skill
  mechanism.
- Live collection is read-only. Publishing requires explicit user authorization.
- Render only by injecting validated JSON into `assets/dashboard.html`.
- Every metric has exactly one classification: `observed`, `derived`, `projected`,
  `benchmark`, or `unavailable`.
- Missing, unlicensed, forbidden, partial, and genuine-zero states are distinct.
- Never represent a projection or benchmark as an observed customer result.
- Never count the same benefit in more than one value category.
- Do not ask the platform administrator for currency, platform cost, baselines,
  adoption coverage, realization factors, or other finance-owned assumptions.
- The only economic content in the normal workflow is the optional bundled Forrester
  composite, classified as `benchmark`. State that it is external research, not this
  customer's savings and not derived from collected JFrog evidence.
- For weekly and monthly runs, lead with the selected period, prior-period movement,
  and trend. Show year-to-date and estate totals only as context.
- Put report type, inclusive start date, inclusive end date, server, scope, and
  live/fixture provenance in the masthead. Never make the reader infer the period.
- Build and validate the full capability evidence model before applying profile filters.
  Profiles hide modules; they do not change collection semantics or calculations.
- A live report run must collect its primary evidence from JFrog again. Never use an
  earlier report, rendered HTML, normalized `data.json`, or product snapshot to fill a
  metric in the new report. Prior validated reports may be read only after the current
  report is complete, and only to calculate an explicitly labelled trend.
- Persist every raw response in the run directory with endpoint, requested period,
  collection time, completeness and SHA-256 evidence. A collector must fail the run
  when pagination is incomplete; it must never publish the rows fetched so far.
- Never edit, patch, or hot-fix an installed copy of this Skill during report
  generation. Preserve a failed run and its diagnostics, then stop and instruct the
  user to upgrade or report the collector defect. Fixes belong in a tested, versioned
  source release.

## Modes and profiles

Modes are capability-detected: `artifactory-only`, `artifactory-xray`,
`full-platform`, and `offline-demo`.

Profiles select modules without changing calculations. Product modules are independently
selectable and never share ownership of the same metric:

- `executive`: outcomes, financial summary, top opportunities, confidence.
- `adoption`: repository/package usage and platform adoption.
- `efficiency`: storage, transfer, automation, and operational-efficiency evidence.
- `delivery`: build/release evidence and explicitly qualified DORA/SPACE mappings.
- `security-value`: prevention and remediation value without duplicating the CISO report.
- `full`: all available modules, including AppTrust and Runtime when feature-detected.
- `curation`, `xray`, `apptrust`, `artifactory`, `ai-security`, `access`, `jas`: focused product views.

The full report order is Executive, Trends, Curation, Artifactory, Xray, AppTrust, AI security,
Access/OIDC, JAS, Runtime, Recommendations, Evidence ledger, and the optional external
Forrester benchmark at the end. Read the complete
[product module contract](references/product-modules.md) before adding or changing a
product metric. AI inventory is an Artifactory subset; JAS exploitability is distinct
from Xray composition analysis; related evidence may be linked but not summed.

Use `scripts/generate_report.py --help` for the legacy offline vertical slice.
Use `scripts/collect_live.py` for the base live collector. It intentionally has no
resume/import option and requires a new raw-evidence directory for each run.
Its inventory, Curation and Xray period tracks run concurrently with bounded workers;
do not split them into separate agent tool calls or increase their worker counts without
rate-limit testing. The weekly runner also executes the independent traffic, AI skill
security, access-governance and AppTrust collectors concurrently, then merges their
results in a fixed order. Parallel completion order must never change raw filenames, manifests,
diagnostics or normalized output.
`scripts/collect_access_governance.py` for a redacted token/OIDC posture snapshot, and
`scripts/collect_artifactory_traffic.py` on every live run to preserve cumulative
application counters and calculate deltas from the preceding successful snapshot, and
`scripts/build_ai_security_evidence.py` to normalize MCP, skill, plugin and model
security states without collapsing `N/A`, `Not scanned`, `Suspicious` or `Malicious`.
For skills, use `scripts/collect_skill_security.py` to keep behavioral scan state,
dependency vulnerability posture and repository-project attribution separate; an
approved skill can still contain vulnerable dependencies. Use
`scripts/render_report.py` to inject schema 0.3 report JSON into the current fixed template.
Use `scripts/enrich_report_modules.py` to deterministically add Artifactory storage,
Xray watch/policy/period-violation, JAS applicability, and AI-repository evidence from
preserved live payloads. It may also merge timestamped AI Catalog and Access governance
envelopes without treating them as historical activity. Cross-watch violations are deduplicated by issue, infected
components, and impacted artifacts; period-created findings are never labeled open backlog.
Use `scripts/render_report.py --modules all` for the complete report or pass a
comma-separated subset such as `--modules curation,xray,evidence`.
Use `scripts/export_report_pdfs.py` after rendering to produce the dedicated light-paper
Executive and Full PDF presentations. PDF export changes presentation only and consumes
the same validated report HTML and embedded JSON.
Read [architecture](references/architecture.md) before extending collectors,
[data sources](references/data-source-matrix.md) before live collection, and
[metric contract](references/metric-contract.md) before adding calculations.

For Artifactory traffic, prefer same-period Open Metrics counter deltas or bounded
request/access/data-transfer logs. Never present cumulative AQL download statistics as
weekly or monthly activity. Label the documented binary-provider cache-fs hit rate
separately from remote-repository cache reuse.

For AI Catalog reporting, keep four inventories distinct: governed models (including
Shadow AI model packages), MCP servers, agent skills, and plugins. Shadow AI currently
applies to model packages; do not infer shadow skills or shadow MCP usage. Registry
presence proves governance inventory, not active consumption. Render each asset class
as its own group. Render scan-state counts
only when the supported registry, artifact-property, Xray, or dated UI evidence was
collected. Identify project attribution as Linked, Unlinked or Unknown; do not convert
missing evidence into Unlinked. A current UI revalidation may be included in an older report only when its
collection date is visible; never represent it as month-end inventory.

For Access governance, report the active-token inventory, issuance recency, configured
expiry windows, non-expiring and never-used counts, OIDC providers, identity mappings,
and repository claim patterns. The token list is not an expired-token history: classify
expired/revoked trend as unavailable until prior snapshots exist. Never emit token IDs,
scopes, or secrets. When the user explicitly requests an operational rotation queue,
put it in a collapsed appendix and expose only a deterministic safe reference, owner,
description, expiry, days remaining and last-use state.

Every metric card must include a plain-language meaning and why it matters. Keep source
and formula available as measurement detail rather than using them as the explanation.

Runtime Security is a separate optional module. Collect critical/high, applicable,
fix-available, runtime-validated, running-image, malicious-package and integrity signals
only from a supported timestamped source. Never backfill a historical report with a
current Runtime dashboard value.

## Workflow

For a normal live weekly run, use `scripts/run_live_weekly.py`; do not manually
assemble the collector chain. The runner always attempts the current Skills security
collector and always passes its timestamped AI evidence to the merge stage. Supply
same-run supported MCP/model/plugin registry evidence with `--ai-catalog-seed` when
available. A missing or failed optional asset collector remains explicitly unavailable
or partial and must never be replaced by AI repository counts.

1. On first use, resolve the instance before any other choice. Run
   `scripts/list_jfrog_instances.py`, which lists every server returned by
   `jf config show`. Present all server IDs and URLs as a single-select list, mark the
   CLI default as `(default)`, and ask the user to choose. Do not silently accept the
   default when several instances exist. Then resolve the period, report profile,
   timezone and output root step by step before presenting the final confirmation.
   The normal profile is `Full (recommended)`; alternatives
   are `Executive` and `Custom`. Do not print the individual section list unless the user
   chooses Custom. Do not ask separate questions for profile and output location.
   Use this host-neutral shape so it works in Claude, Claude Code, Cursor, ChatGPT,
   Codex, Gemini and other Agent Skills hosts:

   ```text
   Ready to generate the weekly JFrog Platform report:
   • Instance: <server> (JFrog CLI default)
   • Period: <inclusive local dates>
   • Report: Full (recommended)
   • Timezone: <timezone>
   • Save to: <promoted report path>

   Proceed? Reply Y, or say what to change (server, report, timezone or location).
   ```

   When the host exposes a native choice UI, use a single-select control for `Full
   (recommended)`, `Executive`, and `Custom`; do not make the user type the profile.
   If the user chooses Custom, run `scripts/list_report_sections.py` and use the host's
   native multi-select/checkbox control for the individual sections. Preselect every
   section, make section labels human-readable, and require at least one selection.
   Use a numbered plain-text list only when the host has no native interactive-choice
   capability. Never claim checkboxes are available unless the current host actually
   provides them. If the initial prompt already names a profile or sections, validate
   it with `--select` and do not ask again.
   Section selection controls rendering only: collect and validate the full available
   evidence model, and pass the selected IDs to `run_live_weekly.py --modules`.

2. Resolve mode, profile, cadence, period, timezone, and output path. The default
   live request is the **last completed ISO week (Monday 00:00 through Sunday
   23:59:59) in the report timezone**, regardless of which day it is run. Use
   `scripts/plan_report_run.py`; do not calculate dates in free-form reasoning.
   Do not request customer financial assumptions. Offer `External Forrester benchmark`
   as an ordinary optional section. Selecting it adds external research context at the
   end; deselecting it removes all economic content.

   Resolve output with `scripts/resolve_report_root.py` after resolving the instance.
   Precedence is an explicit user path, `JFROG_REPORT_ROOT`, a saved per-instance or
   global setting in `~/.config/jfrog-platform-value-report/config.json`, then user
   input. On first use, include `~/jfrog-platform-reports` in the single confirmation
   as the recommended default. A plain `Y`, `Proceed`, or equivalent accepts all shown
   defaults. Do not begin live collection until the user confirms or changes them.
   Before presenting that confirmation, run `scripts/audit_weekly_coverage.py` for
   the current calendar month with `--completed-only` and exclude the week the pending
   run will create with `--exclude-period-key`. If `first_run` is true and earlier
   completed weeks remain fully backfillable, explain that the first report has no
   trend baseline and ask one explicit question: `This is the first archived report for
   this instance. Backfill the available completed weeks so Trends is populated?
   Recommended: Yes.` List the eligible week-ending dates. Never include future,
   partial, expired, or only partially retained weeks. A Yes authorizes only the listed
   read-only weekly collections, which must run one week at a time and validate before
   promotion. A No continues with the requested week and establishes the first baseline.
3. Before collection, check whether the same instance and period already has a
   validated `latest.json`. If so, offer `Open existing`, `Rebuild presentation from
   saved evidence`, or `Refresh evidence`. Open and rebuild avoid live pagination;
   refresh performs a complete new collection. Never reuse saved evidence while
   claiming it is fresh collection.
4. Collect evidence into source envelopes; on live runs always preserve an Artifactory
   traffic-counter snapshot before rendering. Do not silently coerce failures to zero.
   Do not read a previous report during this step.
   Invoke the canonical runner with the planner's exact bounds. Do not make preparatory
   or guessed product-version API probes: the runner feature-detects supported evidence,
   and a 404 must be preserved as an unavailable capability rather than retried through
   another guessed path. Do not manually retry the whole run after a transport reset;
   the collector performs one bounded retry for connection-reset errors and records a
   persistent failure.
   Pass the planner's `period.completeness` to the runner as
   `--period-completeness`. Never default a `current-week` run to complete.
   Surface the canonical runner's stage progress. It explains that a normal run takes
   approximately one to three minutes and is a good time to get a coffee. Do not expose
   raw page-by-page chatter unless the run fails.
5. Validate source evidence and assumptions against the schemas.
6. Calculate metrics and scenarios with `scripts/generate_report.py`.
7. Validate the result, inject it into the fixed, versioned `assets/dashboard.html`
   template, and verify artifacts. Agents must never synthesize or restyle report HTML.
   Only after this succeeds may a prior validated report be used to calculate trend
   deltas; that comparison must not change the current report's observed values.
   For weekly reports, run `scripts/apply_weekly_trends.py` after the current report
   validates and before rendering. It reads only validated weekly `latest.json`
   archives intersecting the current calendar month and creates the dedicated
   week-over-week trend section.
8. Explain observed results, projections, limitations, and data gaps separately.
9. As the final read-only step, run `scripts/audit_weekly_coverage.py` for the
   previous calendar month. If coverage is complete, say nothing about backfill. If
   weeks are missing, show their complete Monday-Sunday local dates and Curation
   backfill eligibility. Offer collection only for fully backfillable weeks. A partially
   retained week may be described as incomplete but must not be promoted as a weekly
   archive or included in a complete monthly roll-up. Never clip a weekly backfill to
   calendar-month boundaries, backfill automatically, or claim expired evidence can be
   recovered.

### Weekly invocation contract

Map user language to deterministic modes:

- "Generate weekly JFrog Platform report", "Generate weekly platform report",
  "Generate my weekly report", or no dates:
  `completed-week` with the full available capability profile.
- "This week" or "week to date": `current-week`, visibly labelled partial.
- "Week ending YYYY-MM-DD": `week-ending`, the seven inclusive local dates ending
  on that date.
- Explicit start and end dates: `explicit`.
- "Monthly executive report" or a named month: `calendar-month` roll-up from
  validated weekly archives; never query an expired historical Curation month and
  never reconstruct it from an earlier rendered report.

### Instance resolution

The user does not need to include a server ID in the prompt. Resolve it during
preflight with the installed JFrog integration skill and `jf config show`:

1. Use a server explicitly named by the user after confirming it exists in
   `jf config show`.
2. Otherwise use `JFROG_PLATFORM_REPORT_SERVER_ID` when configured and valid. Continue
   to accept `JFROG_CIO_SERVER_ID` as a deprecated compatibility alias.
3. On first use, list every configured instance and ask the user to choose, even when
   the CLI marks one as default. Mark the default as recommended, not selected.
4. On later runs, show the saved or last-confirmed instance in the compact confirmation
   and provide a `Change instance` choice that reopens the complete list.
5. Never guess or silently switch instances after an API error.

Therefore the preferred natural-language invocation is simply:

`Generate weekly JFrog Platform report`

Timezone precedence is explicit user timezone, then `JFROG_REPORT_TIMEZONE`, then a
saved setting, then the machine's recognized IANA timezone, and finally `UTC`. Use
`scripts/resolve_reporting_period.py` for detection; do not guess from an offset.
Always print the selected timezone and inclusive local dates before collection. Keep
UTC bounds in the run plan/evidence rather than cluttering the confirmation unless the
user requests technical detail.

Store weekly runs at `<root>/<server>/weekly/<week-ending>/runs/<UTC-run-id>/`.
Preserve every run and update the period's `latest.json` only after collection,
pagination, checksums, schema validation, normalization, and rendering succeed. A
failed same-day rerun must not replace the previous successful run.

The promoted report path is always:
`<report-root>/<instance>/weekly/<week-ending>/report.html`. Each JFrog instance has
its own directory beneath the selected report root.

The monthly executive report is a calendar-month view over timestamped weekly raw
events. Clip cross-month weeks to the month, deduplicate by stable event identity,
and require continuous coverage. Use the last validated point-in-time inventory at
or before month end for posture. Never sum repository/storage snapshots, unique-user
counts, percentages, or weekly cache-hit ratios. If any day is missing, label the
monthly roll-up partial and list the uncovered interval.

Risk color is semantic, not merely directional. Malicious, suspicious, vulnerable,
critical, integrity, credential-expiry, collection-failure and verified governance-gap
states render in red when their value is non-zero. Warning/partial evidence remains
amber. A trend turns red only when its metric polarity defines that direction as
adverse; contextual measures such as download volume or Curation blocks remain neutral.
Use `scripts/rollup_weekly_archives.py` to produce the roll-up evidence. Render the
executive view only after this output validates; an incomplete roll-up must show the
coverage gap and must not present missing activity as zero.

### Portable host behavior

This is a portable Agent Skill: the same `SKILL.md`, standard-library Python scripts,
schemas, fixtures, and HTML template are the source of behavior in Codex, Claude,
Gemini, and other Agent Skills-compatible hosts. Host-specific UI metadata is optional
and must not contain reporting logic. Scheduling is never required for correctness;
the mandatory final coverage audit detects missed weeks whenever the skill next runs.
The supported execution baseline is Python 3.11+ and JFrog CLI on macOS or Linux/WSL.
Native Windows is best-effort; use WSL for the same supported code path and to avoid
maintaining a second shell/runtime implementation.

The folder is the canonical Agent Skills bundle. It is also an OpenAPM hybrid package
through `apm.yml`; do not duplicate reporting logic in package-manager manifests.
Repository consumers may use an Agent Skills installer such as `npx skills add`, while
JFrog customers should prefer signed publication and governed installation through the
JFrog AI Catalog. Installation choice never changes the skill, scripts or template.

Offline demonstration:

```bash
python3 scripts/generate_report.py \
  --evidence fixtures/artifactory-only.json \
  --assumptions fixtures/assumptions.json \
  --profile executive \
  --output /tmp/jfrog-platform-report-demo
```

## Extension rule

Add a capability in four isolated layers: source envelope, normalized evidence,
deterministic metric calculation, and template module. Optional collectors must not
break Artifactory-only generation. Supported threat/research context is rendered inside
Xray, never as an empty standalone section. Any impact search must record its query,
pagination, prerequisite and permission outcome; unsupported or uncollected capability
cards stay out of the executive report and remain in the evidence ledger.
