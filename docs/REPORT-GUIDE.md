# JFrog Platform Report Guide

This guide explains how to read the weekly JFrog Platform Value & Risk Report.
It describes the fixed report interface, the meaning of each tile group and the
evidence rules that prevent an unavailable value from looking like a genuine zero.

## Start with the report header

The header identifies the report type, inclusive period and JFrog instance. The
navigation remains available while reading the HTML report. Export controls offer
Executive, Full and Custom views without changing the collected evidence.

The public sample uses the fictional instance `northstar-demo`. Its identities,
repositories, project keys, metrics, trends and recommendations are synthetic.

## How to read a metric tile

| Tile element | Meaning |
|---|---|
| Metric name | The decision signal being reported |
| Value and unit | The normalized value and its measurement unit |
| Classification | `observed`, `derived`, `projected`, `benchmark` or `unavailable` |
| Color | Red identifies an adverse state that requires attention. Green identifies a positive control outcome. Neutral movement remains neutral. |
| What this means | A plain-language definition of the value |
| Why it matters | The leadership decision or risk connected to the value |
| How this was measured | The source and deterministic formula, available by expansion |

An increase is not automatically good or bad. The Trends section assigns polarity to
each series. More Curation coverage can be favorable, while more critical findings is
adverse. Download volume is contextual and remains neutral unless the customer defines
an operating threshold.

## Evidence classifications

| Classification | Interpretation |
|---|---|
| `observed` | Directly collected from a supported source for the stated period or snapshot time |
| `derived` | Calculated in code from observed inputs using the displayed formula |
| `projected` | Reserved by the schema; the normal weekly workflow does not produce customer financial projections |
| `benchmark` | External research context that is not a customer result |
| `unavailable` | The source, permission, period boundary or required input was not available |

Missing, forbidden, unlicensed, partial and genuine-zero states remain distinct. A
current inventory is never backdated into an earlier reporting period.

## Report sections and tiles

### Executive overview

| Tile or panel | What it answers | Why it matters |
|---|---|---|
| Executive signals | Which few values describe the week? | Provides a compact operating view before product detail |
| Top risks | What requires immediate attention? | Directs leadership attention to adverse evidence |
| Demonstrated outcomes | Which controls produced a measurable result? | Separates demonstrated value from projected value |
| Recommended actions | What should happen next? | Assigns an owner and a 7-day or 30-day horizon |

### Trends

| Tile or panel | What it answers | Why it matters |
|---|---|---|
| Weekly series | How did a comparable metric move across the calendar month? | Reveals direction without mixing incompatible snapshots |
| Week-over-week change | What changed since the last validated week? | Highlights acceleration, improvement or deterioration |
| Weekly values | Which exact values produced the chart? | Keeps the visual auditable |

### Curation

| Tile or panel | What it answers | Why it matters |
|---|---|---|
| Requests evaluated | How much dependency demand passed through Curation? | Indicates preventive-control reach |
| Blocked requests | How many requests were stopped? | Shows risky demand prevented before consumption |
| Block rate | What share of evaluated requests was blocked? | Adds scale to the blocked count |
| Curation unique users | How many requester identities used governed repositories? | Indicates adoption without treating identities as licensed developers |
| Unique blocked versions | How broad was risky package demand? | Separates repeated attempts from distinct package risk |
| Ecosystems and block reasons | Where and why did blocks occur? | Supports policy tuning and developer guidance |
| Active requester identities | Which anonymized identities generated demand? | Helps investigate concentrated friction without exposing secrets |

### Artifactory

| Tile or panel | What it answers | Why it matters |
|---|---|---|
| Repository inventory | How is the repository estate distributed? | Supports ownership, standardization and lifecycle review |
| Artifact storage | How much binary storage is in use? | Supports capacity and retention planning |
| Period downloads and uploads | How much artifact traffic occurred in the week? | Quantifies platform activity using matching counter boundaries |
| Cache hit rate | How efficiently did the binary provider serve eligible requests? | Connects cache behavior to resilience and transfer efficiency |
| Largest repositories | Which repositories drive storage? | Directs cleanup and ownership decisions |

Traffic is a period value only when two matching cumulative counter snapshots or
complete bounded logs exist. A single cumulative value remains a baseline.

### Xray

| Tile or panel | What it answers | Why it matters |
|---|---|---|
| New findings | How much risk entered during the period? | Separates weekly intake from open backlog |
| Critical and high findings | How severe was the new intake? | Supports remediation priority |
| Unique CVEs | How diverse was the vulnerability set? | Prevents occurrence volume from being mistaken for distinct threats |
| Indexed repositories | How much of the repository estate is covered? | Qualifies confidence in the security conclusion |
| Top CVEs and repositories | Where is risk concentrated? | Connects findings to an actionable owner |

### AppTrust

| Tile or panel | What it answers | Why it matters |
|---|---|---|
| Application inventory | How many applications and projects are represented? | Establishes the governed application estate |
| Criticality and maturity | Which applications are critical, high, production or end of life? | Prioritizes governance by business and lifecycle context |
| Ownership gaps | Which applications, especially critical ones, have no owner? | Makes accountability gaps visible before release decisions |
| Release stages and promotions | Which versions are trusted, promoted, failed or rejected? | Connects delivery flow to release-governance outcomes |
| Evidence predicates | Which release records are verified or unverified? | Qualifies trust in release-gate decisions |

The collector fully paginates application inventory and enriches high-value applications.
If detail enrichment is unsupported or truncated, complete application inventory remains
visible while versions, promotions and evidence are marked unavailable. A partial detail
count is never published. Application-specific vulnerability impact is not inferred without a
deterministic Xray-to-artifact/build-to-application relationship.

### AI security

AI assets are grouped into MCP servers, skills, plugins and models. Their behavioral
security status, dependency vulnerability posture, governance state and project
attribution remain separate.

| Tile or panel | What it answers | Why it matters |
|---|---|---|
| Security distribution | How many assets are malicious, suspicious, vulnerable, not malicious, scanning, not scanned or N/A? | Preserves the exact security state exposed by the source |
| Dependency vulnerability posture | Does the asset contain vulnerable dependencies? | Prevents an approved asset from being mistaken for a dependency-clean asset |
| Project attribution | Is the asset linked to an accountable project? | Identifies governed inventory without a clear owner |
| Asset evidence | Which fictional asset produced each count in the sample? | Makes summary totals auditable |
| Shadow AI | Which model packages are managed or unmanaged? | Exposes unauthorized model adoption without inventing shadow skill usage |

`N/A` does not mean safe. It means the collected source did not expose a completed
security result.

### Access, tokens and OIDC

| Tile or panel | What it answers | Why it matters |
|---|---|---|
| Active tokens | How many active credentials exist? | Establishes the credential estate |
| Expiring within 7 or 30 days | Which credentials need rotation planning? | Reduces avoidable service disruption |
| Non-expiring tokens | Which credentials have an unbounded lifetime? | Highlights blast-radius risk |
| Rotation queue | Which safe references need action? | Supports operations without exposing token IDs, scopes or secrets |
| OIDC providers and claim patterns | Which GitHub, GitLab or other workload identities can access repositories? | Makes stored-secret replacement and trust boundaries visible |

### JFrog Advanced Security

| Tile or panel | What it answers | Why it matters |
|---|---|---|
| Applicable vulnerabilities | Which findings are actionable in context? | Reduces remediation noise |
| Applicable with a fix | Which actionable findings have a remediation path? | Prioritizes engineering work |
| Secrets, IaC and SAST findings | Which advanced scanners found open issues? | Extends risk visibility beyond dependency CVEs |

JAS context can refine prioritization, but it is not added to Xray occurrence totals.

### Runtime security

| Tile or panel | What it answers | Why it matters |
|---|---|---|
| Running images | What is present in production? | Narrows posture to deployed workloads |
| Applicable findings | Which findings affect running workloads? | Connects remediation to actual exposure |
| Malicious packages and integrity violations | Is there an urgent runtime signal? | Supports immediate escalation |
| Running-image trend | Is production exposure improving? | Tracks change without treating current state as historical evidence |

### External Forrester benchmark

The optional final section shows the Forrester TEI composite strictly as external
research. It is not customer ROI, is not derived from collected JFrog evidence and is
not a claim about realized savings. Users can include or exclude it when selecting
report sections. The weekly workflow does not request finance-owned assumptions.

### Recommendations

Recommendations are deterministic responses to report evidence. Every action includes
a priority, accountable role, evidence reason and target horizon. They are not generated
from an unbounded free-form narrative.

### Methodology and evidence notes

The final section documents source status, evidence classification, unavailable
capabilities and known data gaps. It belongs in the full report and can be excluded from
an Executive PDF when the reader only needs the decision summary.

## Sample-output security

The public HTML and PDFs are created only from `scripts/generate_sample_data.py`.
The generator contains fictional values and cannot read a live archive or customer
environment. Repository names, project keys, user identities and token references are
made-up examples intended to demonstrate the report interface.
