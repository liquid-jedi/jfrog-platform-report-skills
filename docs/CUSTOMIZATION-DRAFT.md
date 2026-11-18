# Customization architecture draft

This document describes the locally implemented profile foundation. It is not yet a
published customer contract.

## Compatibility rule

Running the weekly runner without `--profile` preserves the existing full report,
collector defaults, output paths and section set. Profiles are optional and declarative.
They cannot execute commands or replace calculation and rendering code.

## Profile responsibilities

A profile may:

- choose report sections;
- set optional collectors to `auto`, `required` or `disabled`;
- select Artifactory repositories or JFrog Projects;
- select source repositories through explicit customer-maintained mappings; and
- record a scope ledger in the normalized report.

A profile may not:

- change metric formulas or classifications;
- inject HTML or Python;
- infer relationships from similar repository names;
- disable the base Artifactory, Xray and Curation acquisition track in profile version 1; or
- attribute platform-wide posture to a selected repository without a supported mapping.

## Collector modes

- `auto`: attempt collection and preserve a supported failure as unavailable or partial.
- `required`: fail the run if the collector fails.
- `disabled`: do not invoke the optional collector and record it as `not_selected` in run diagnostics.

When an `auto` collector cannot produce truthfully scoped evidence, the resolver changes
that collector to `disabled` and records `scope_not_supported`. A `required` collector
with an incompatible scope fails profile validation before any API call.

The base platform track remains required in profile version 1 because the current
collector acquires Artifactory inventory, Xray and Curation concurrently. Separating
those three calls is a later internal refactor and is not required for profile support.

## Scope behavior

Scope is applied after immutable raw collection and before metric calculation. This
preserves the raw evidence manifest while ensuring repository and project metrics are
calculated from the selected records. Week-over-week trends compare only reports with
the same scope type and selected repository keys.

Supported scope types in profile version 1 are:

- `all`
- `artifactory_repository`
- `jfrog_project`
- `source_repository`

`source_repository` requires explicit mappings to JFrog repositories or projects.
GitHub repository names alone never establish a JFrog relationship.

## Feasibility matrix

| Capability | Scoped in profile version 1 | Method | Current gap |
|---|---|---|---|
| Artifactory repositories | Yes | Repository key or project assignment | Project assignment depends on the supported API field being present |
| Artifactory storage | Yes | Sum selected repository storage rows | Global deduplication cannot be attributed to a subset |
| Curation activity | Yes | `curated_repository_name` | Events without repository identity are excluded |
| Xray period findings | Yes | Repository prefix in impacted artifacts | Findings without an impacted repository cannot be attributed |
| Xray indexing | Yes | Indexed repository identity | None when the API supplies repository identity |
| Xray watches and policies | No | No safe repository join in the current collector | Omitted from scoped calculations |
| AppTrust | No | Requires a supported application/project/repository join | `auto` is disabled for scoped profiles |
| Access and OIDC | No | Platform-wide posture | `auto` is disabled for scoped profiles |
| AI skill security | No | Current collector reports platform inventory | `auto` is disabled for scoped profiles |
| Traffic counters | No | Application counters are platform-wide | `auto` is disabled for scoped profiles |
| External benchmark | Yes | External context only | Never represented as a scoped customer result |

## Unsupported assumptions and gaps

- A GitHub repository name is not assumed to be an Artifactory repository name.
- A JFrog Project is not assumed to own an AppTrust application unless the supported
  source carries that relationship.
- Global posture is not divided proportionally across selected repositories.
- Unmatched mappings remain visible in the scope ledger and are never converted to zero.
- Profile version 1 does not load customer Python, custom HTML or external extension code.

## Upgrade-safe extension direction

Future collectors should be registered through a versioned collector definition and
return a normalized evidence envelope. Profiles will reference only installed collector
IDs. The fixed renderer will continue to own HTML and PDF presentation. Third-party
profiles will never be treated as permission to execute third-party code.

See `examples/profiles/github-engineering.toml` for a synthetic example.
