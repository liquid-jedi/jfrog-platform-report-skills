# Unsupported assumptions and product-data gaps

- JFrog does not determine end-to-end DORA outcomes by itself; mappings are contributing
  influence unless customer CI/CD and incident data provide direct measurement.
- Repository names do not establish business criticality, environment, or ownership.
- Labor savings, incident avoidance, developer time, infrastructure rates, license cost,
  and realization factors are customer assumptions, never observed JFrog facts.
- A blocked download is not automatically an avoided incident.
- Storage bytes do not establish cloud spend without customer unit rates and applicability.
- Vulnerability occurrence counts do not establish business risk without asset context.
- Xray impact-search coverage excludes assets outside SBOM-indexed/scanned scope;
  a report must disclose the exact CVE/XRAY ID or package used as the search input.
- Frogbot, Runtime, AI Catalog active-consumption, and agentic-remediation realized-value
  evidence still require dedicated live collectors. AppTrust inventory and bounded
  release-governance evidence are collected through OneModel, but application-specific
  vulnerability attribution still requires a deterministic Xray-to-build relationship.
  Supported AI Catalog registries can provide governed model, MCP, skill, and plugin inventories, but registry
  presence alone does not prove use or realized value.
- External benchmarks remain `benchmark` and never feed projections unless explicitly
  adopted by the customer as an assumption.
- Unique requester identities can include service tokens and do not establish licensed
  developer population, team ownership, or human adoption without identity enrichment.
- AI repository inventory proves governed footprint, not model provenance, scanning,
  active consumption, or AI Catalog policy enforcement. Shadow AI detection currently
  covers model packages; it must not be described as shadow-skill or shadow-MCP detection.
- A current Open Metrics counter is not period activity. Downloads, uploads, failures,
  bytes, and cache-fs efficiency require same-period counter deltas or bounded logs.
- The documented cache-fs hit rate measures the binary-provider cache. It is not proof
  of remote-repository dependency cache effectiveness or avoided internet transfer.
- JAS policies prove configuration only. They do not establish scan coverage, period
  findings, exploitability reduction, remediation, or Agentic Remediation outcomes.
- Xray violation occurrences must not be added to JAS actionable findings or Curation
  prevention counts as one combined risk-reduction total.
