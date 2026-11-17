# Data-source and API feasibility matrix

| Module | Evidence | Preferred validation | Artifactory-only | State |
|---|---|---|---:|---|
| Repository estate | repositories, types, local/remote/virtual | JFrog MCP, then official Artifactory API | yes | feasible |
| Storage utilization | artifact/file counts and bytes | JFrog MCP or Storage Summary API | yes | feasible |
| Download activity | period requests, bytes, success/failure | SaaS `GET /artifactory/api/v1/metrics/application`, Open Metrics counter deltas, or period request/access/data-transfer logs; AQL statistics only for cumulative per-item context | yes | supported with observability/snapshots; the live SaaS response is cumulative and requires boundary snapshots |
| Upload activity | period requests, bytes, success/failure | Open Metrics counter deltas or period request/access/data-transfer logs | yes | supported with observability/snapshots; item `created` is only a new-content approximation |
| Binary cache efficiency | cache hits, misses, hit rate | Open Metrics `jfsh_binaries_download_total` and `jfsh_binaries_not_found_total` for the `cache-fs` provider | yes | supported on applicable self-managed storage topology; calculate from same-period counter deltas |
| Package breadth | package types and repository coverage | repository metadata | yes | feasible |
| Build adoption | build-info inventory and recency | MCP or Build Info API | yes | needs live validation |
| Release lifecycle | Release Bundles/promotions | MCP or Distribution APIs | optional | needs live validation |
| Xray coverage | indexed resources and violations | JFrog MCP or official Security APIs | no | feasible, optional |
| AppTrust | applications, projects, criticality, maturity and owners | OneModel GraphQL application inventory | no | supported when entitled; cursor-paginated and feature-detected |
| AppTrust release governance | application versions, stages, release status, promotions and evidence predicates | OneModel GraphQL application detail | no | bounded to high-value applications; nested truncation is unavailable, never partial |
| Curation value | audit outcomes, policies, waivers | JFrog MCP or official Curation APIs | no | feasible, optional |
| Advanced Security | contextual, secrets, IaC, SAST | JFrog MCP/Security APIs | no | optional/entitled |
| Runtime | critical/high, applicable, fix-available, runtime-validated, running images, malicious packages and integrity violations | supported timestamped Runtime collector envelope | no | UI metrics documented; validate a stable read source per platform version, never scrape/guess internal endpoints or backfill history from current posture |
| Frogbot | PR findings and remediation | MCP/official integration evidence | no | data-source gap |
| AI Catalog models | approved model registry and Shadow AI model inventory | AI Catalog model registry/Shadow AI; Artifactory model repositories for stored footprint | no | supported when entitled; Shadow AI currently detects model packages only |
| AI Catalog MCP | approved MCP servers, custom servers and tool policy | MCP Registry/Agent Guard; custom registration has a documented REST endpoint | no | supported when entitled; registry inventory is distinct from active tool-call usage |
| AI Catalog skills | project-scoped skills, versions, download count, behavioral scan status and dependency vulnerability posture | skill-property AQL plus `GET /artifactory/api/skills/{repo}/xrayStatus?path={path}` for behavior; `POST /xray/api/v2/summary/artifact` for dependency issues; `jf agent skills list` for governed discovery | no | behavioral approval does not imply vulnerability-free; preserve project attribution from the backing repository separately |
| AI Catalog plugins | project-scoped plugin bundles and security status | `jf agent plugins` / AI Catalog Plugins Registry / dated UI evidence | no | keep separate from skills; the Skills `xrayStatus` route does not accept plugin artifacts, so retain N/A unless a supported plugin source supplies status |
| AI/ML overview | detected/allowed models, allowed MCP servers, live models and gateway requests | supported timestamped AI Catalog/ML collector envelope | no | inventory is point-in-time; gateway requests require a bounded period; stable read source must be validated per platform version |
| Agentic remediation | actions and realized fixes | JFrog MCP/official API | no | unsupported until verified |
| Access token governance | active inventory, recent issuance, expiry windows, non-expiring and never-used tokens | `GET /access/api/v1/tokens`, redacted aggregation only | yes | feasible point-in-time; expired/revoked history requires snapshots |
| OIDC governance | providers, identity mappings, repository/project-path claim patterns and token TTL | `GET /access/api/v1/oidc` plus per-provider `identity_mappings` | yes | feasible; patterns are configured trust, not proof of recent use |
| Xray threat context | resources impacted by a CVE/XRAY ID or package | `GET /xray/api/v2/search/impactedResources` | no | verified; render inside Xray; requires Xray 3.131+, SBOM Service, Reports Manager |

## Product-module collection backlog

| Module | Decision evidence | Collection state |
|---|---|---|
| Curation | decisions, unique identities, repositories, packages, reasons, policy matches | validated live |
| Curation | policy inventory, block/dry-run state, risk type, cache enforcement | validated live |
| Curation | waiver state and aging | validated live |
| Curation | prior-period/YTD trend and team identity enrichment | snapshot/customer-data dependency |
| Xray | indexed/non-indexed repositories, watches, policies | validated live |
| Xray | period violations, severity, affected assets, top CVEs, fix-version presence | validated live; bounded per-active-watch pagination and cross-watch deduplication |
| Xray | resolution, backlog age, SLA, fix availability, ignore rules | dedicated normalized collector required |
| AppTrust | application inventory, project mapping, criticality, maturity and owners | validated live through OneModel GraphQL |
| AppTrust | high-value application versions, stages, promotions and evidence predicates | supported live bounded enrichment; application inventory remains complete |
| AppTrust | application-specific Xray risk, affected builds and fix availability | deterministic Xray-to-artifact/build-to-application join required |
| Artifactory | repository estate and package types | validated live |
| Artifactory | storage summary | feasible; live collector path exists |
| Artifactory | uploads/downloads, failures and byte trends | supported through Open Metrics deltas or period logs; requires metrics/log access and a prior snapshot for counters |
| Artifactory | cache-fs hit rate | supported through Open Metrics on applicable self-managed topology; not equivalent to remote-repository cache reuse |
| Artifactory | ownership, permissions, anonymous exposure, token expiry | separate access/governance collectors required |
| AI security | AI/agent repository subset by package type | validated live |
| AI security | approved models and Shadow AI model packages | AI Catalog entitlement required; Shadow AI is model-only and must not be presented as skills/MCP discovery |
| AI security | skills and scan status | supported through Skills Registry and JFrog CLI; distinguish Not malicious, Not scanned, Scanning, Suspicious and Malicious |
| AI security | approved MCP inventory and custom MCP registration | supported through MCP Registry/Agent Guard; documented custom-registration REST API exists |
| AI security | active consumption, users and MCP tool calls | separate telemetry gap; registry presence is not usage evidence |
| JAS | policies containing exposure criteria | validated live configuration evidence |
| JAS | applicability-detail results from period Xray violations | validated live; preserve every result category |
| JAS | secrets, SAST, IaC, scan age and remediation | entitlement/API feasibility validation required |
| JAS | Agentic Remediation recommendations and accepted fixes | unsupported until verified |

The Xray impact endpoint accepts either `vulnerability`, or package `name` +
`type` with optional `version`. Paginate using `last_key`; the maximum page size is
10,000. A 403 can mean either missing Reports Manager permission or disabled SBOM
Service and must not be reported as a clean/empty result.

No private UI endpoint is an acceptable production collector. Feature detection must
separate unlicensed, forbidden, unsupported, unused, and empty datasets.

## Traffic measurement rules

- Open Metrics values are cumulative counters. A weekly or monthly report uses
  `current counter - prior successful snapshot counter`, recording counter resets and
  missing snapshots as unavailable.
- The supported cache-fs calculation is
  `download_delta / (download_delta + not_found_delta) * 100`. It measures binary
  provider cache efficiency and must be labelled as such; it is not automatically the
  remote-repository dependency cache-hit rate.
- AQL `stat.downloads`, `stat.downloaded`, `stat.remote_downloads`, and related fields
  are useful for artifact-level popularity and recency. They are cumulative and do not
  by themselves prove report-period transfer activity.
- Access/request logs can count successful upload and download events. Cloud detailed
  data-transfer logs are a separate opt-in source and may add storage cost.
