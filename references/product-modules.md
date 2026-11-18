# Product module contract

The report has independently selectable product modules. Collection builds the
complete evidence model first; module selection changes presentation only. Each module
must answer: what happened in the period, what is the current posture, what changed,
and what leadership should do next.

Do not render an empty product section. Record unavailable evidence in the evidence
ledger, but show a product module only when it has at least one decision-useful metric.

## Shared time model

Every activity metric should expose the selected period, prior-period comparison, and
year-to-date context when snapshots exist. Estate/configuration metrics are explicitly
point-in-time. Never compare a point-in-time inventory with a period event count.

## Curation

### Period activity and adoption

- Total, approved, and blocked decisions; block rate.
- Unique requester identities, users with approvals, and users encountering blocks.
- Distinct repositories used, decisions by ecosystem, weekly trend, prior-period
  movement, and year-to-date activity.
- Top requester identities, with requests, blocks, repositories, and distinct packages.
- Repeated attempts against the same blocked package and blocked requests per active
  identity. Do not treat identities as licensed developers.

### Prevention and governance

- Unique blocked package name/version combinations, top blocked packages, blocking
  reasons, risk categories, policies producing blocks, and cache enforcement.
- Registered, enabled, disabled, blocking, and dry-run policies; policy risk type and
  project/global scope when available.
- Pending, approved, rejected, expired, and aging waivers; oldest pending waiver and
  30/60/90-day aging. Identify broad or long-lived waivers when evidence supports it.
- Conclude with what was prevented, where friction occurred, coverage movement, and
  policies or waivers needing review.

## Xray

### Coverage and risk

- Indexed/non-indexed repositories and coverage percentage; covered builds and release
  bundles when available; scan freshness and stale assets.
- New and open violations; severity and security/license split; unique CVEs versus
  repeated occurrences; affected repositories, artifacts, builds, releases, and projects.
- Most widespread CVEs. Show fix availability only when a supported enrichment returns structured fix versions; do not parse advisory prose or substitute zero.

### Remediation and governance

- Resolved findings, new-versus-resolved movement, backlog growth, age buckets, mean and
  median age, critical time-to-remediation, and SLA compliance.
- Active watches, policies, coverage, ignore rules and expiration, and license posture.
- Threat context belongs inside Xray when a verified supported source exists. Include
  known-exploitation/research context and customer blast radius, but never render an
  empty standalone Threat Hub section.

## AppTrust

AppTrust is the application and release-governance view. It does not replace Xray risk
or infer that every finding in a repository affects every application using that
repository.

- Application and project inventory; criticality; maturity; assigned ownership; and
  critical applications without an owner.
- Version stage and release status; trusted releases; completed, failed and rejected
  promotions; and release-gate evidence.
- Verified and unverified evidence predicates associated with enriched high-value
  application versions.
- The standard collector fully paginates application inventory and enriches critical,
  high, production and end-of-life applications. If detail enrichment is unsupported
  or a bounded nested connection is truncated, preserve the complete inventory as a
  partial module and mark release versions, promotions and evidence unavailable. Never
  publish a partial detail count or convert it to zero.
- Application vulnerability or fixability requires a deterministic relationship from
  Xray evidence through the affected artifact or build to the AppTrust application.
  Inventory similarity or repository naming is never sufficient attribution.

## Artifactory

### Estate and artifact flow

- Local, remote, virtual, and federated repositories; ecosystems; new/inactive/orphaned
  repositories; ownership/project assignment; and virtual-repository adoption.
- Period uploads, downloads, unique artifacts, internal versus cached external use,
  build/release activity, top repositories, prior-period movement, and year-to-date.

### Efficiency, reliability, and governance

- Storage and artifact growth, largest repositories, old/unused artifacts, cleanup
  coverage, remote-cache behavior, and deterministically supported reclaimable storage.
- Download failures, remote failures, replication/federation health, availability,
  latency, and failed lifecycle activity where supported.
- Permissions, anonymous/public exposure, privileged identities, expiring tokens,
  naming drift, unowned repositories, and evidence/signing adoption.
- Never infer business criticality or ownership from repository names.

## AI security

AI security covers models, agent packages, agent plugins, skills, and editor extensions.
Repository totals are owned by Artifactory; this module references the AI subset and must
not add it again to platform totals.

- Inventory by AI asset/repository type; unique assets and versions; period additions;
  internal/external source; active/inactive repositories.
- Scanned/unscanned assets, dependency vulnerabilities, malicious findings, provenance,
  publisher verification, licenses, secrets, unsafe serialization or executable-code
  indicators, and assets without traceable origin when supported.
- AI Catalog allow/block policy coverage, malicious-skill checks, project governance,
  approved sources, version pinning, deprecation, exceptions, and exception aging.
- Period consumption, top assets and unique consumers where identity evidence exists.
  Repository inventory alone proves footprint, not consumption or realized value.

## JFrog Advanced Security (JAS)

JAS is separate from Xray composition analysis. It covers advanced scanners and
exploitability evidence at application/build context.

- Coverage by Contextual Analysis, Secrets, SAST, IaC, applicability/exposure analysis,
  repositories, builds, and applications; recent scans and stale/unscanned assets.
- New/open/resolved findings, severity, scanner category, exploitable/non-exploitable,
  secrets, SAST categories, IaC misconfigurations, fix availability, and affected assets.
- Reduction from raw vulnerability volume to actionable findings; critical exploitable
  backlog; reachable findings with a fix; findings connected to releases.
- Age, SLA, recurrence, remediation recommendations, and verified Agentic Remediation
  actions when supported. Configuration proves policy presence, not period findings.

## Runtime Security

- Critical/high findings in monitored production images; applicable findings; findings
  with a fix; and findings validated by runtime observation.
- Running image count, malicious packages, critical-and-applicable image risk, integrity
  violations, and the number of affected image tags.
- Running-image and applicable-risk trend when a bounded historical series is available.
- Runtime is production posture. Do not label a current dashboard value as September or
  October activity, and do not merge it with JAS applicability counts.

## Cross-module allocation

- Curation block to Xray risk: prevention before entry.
- Xray finding to JAS applicability: refinement into actionable application risk.
- Artifactory consumption to Curation identity: governed adoption.
- AI asset to Xray/JAS evidence: security posture of an AI asset.
- JAS remediation to Xray backlog: validated actionable-risk reduction.

One event may appear as linked evidence in multiple modules, but one economic benefit
key may be allocated only once. Maintain stable identifiers to join evidence instead of
adding occurrence counts across modules.

## Renderer module names

`scripts/render_report.py --modules` accepts `executive`, `curation`, `xray`,
`apptrust`, `artifactory`, `ai-security`, `jas`, `runtime`, `economic`, and `evidence`.
`all` is the default.
