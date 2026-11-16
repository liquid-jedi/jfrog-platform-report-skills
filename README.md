# JFrog CIO Value Report

This skill is part of the **JFrog Agentic Dashboard Skills** product family. It
generates modular CIO value reports from classified JFrog evidence and explicit
customer assumptions. See `SKILL.md` for agent instructions and
`references/architecture.md` for the implementation plan.

The default live cadence is the last completed ISO week in the configured report
timezone. This makes the result stable when users run it on different weekdays.
Use `current-week` only for an explicitly requested week-to-date report. Monthly
executive reports are calendar-month roll-ups of validated weekly event archives.

## Install and portability

The canonical distribution is this Agent Skills folder. It contains one `SKILL.md`,
standard-library Python scripts and one fixed HTML template, so reporting behavior is
not duplicated per agent or operating system.

- Cross-agent convenience installer: `npx skills add <git-repository> --skill jfrog-cio-value-report`
- OpenAPM: install the repository subdirectory containing this folder, for example
  `apm install <git-repository>/jfrog-cio-value-report`; `apm.yml` declares the hybrid
  skill package and deliberately leaves target choice to the consumer.
- JFrog customers: publish the same folder as a signed skill to a governed JFrog AI
  Catalog repository and install it with `jf skills install`.

`npx` is a convenient adapter, not the skill format and not a universal requirement.
The portable contract is the Agent Skills folder itself. macOS and Linux/WSL are the
supported execution baseline; native Windows is best-effort. WSL uses the same tested
Python and JFrog CLI path, avoiding a separate Windows implementation.

Before collection, agents run `scripts/list_report_sections.py` and present the same
plain-text choices in Claude, Claude Code, Cursor, ChatGPT/Codex, Gemini, or another
Agent Skills host. `All` is the default. A focused selection changes only rendering;
the full available evidence model is still collected and validated.

Resolve a run before collecting:

```bash
python3 scripts/plan_report_run.py --server solenglatest \
  --output-root /path/to/reports --timezone Asia/Kolkata
```

At month end, pass each validated weekly run directory to the deterministic roll-up:

```bash
python3 scripts/rollup_weekly_archives.py --month 2026-10 \
  --timezone Asia/Kolkata --archive /path/to/week-1/run \
  --archive /path/to/week-2/run --output /path/to/monthly-evidence.json
```

Every report invocation should finish by auditing the previous calendar month for
missed weeks:

```bash
python3 scripts/audit_weekly_coverage.py --report-root /path/to/reports \
  --server solenglatest --timezone Asia/Kolkata
```

The audit is read-only. It proposes recoverable backfills but never runs them without
the user's approval, so the same workflow works without a scheduler in Codex, Claude,
Gemini, and other Agent Skills-compatible hosts.

After a weekly report validates, add calendar-month week-over-week movement before
rendering:

```bash
python3 scripts/apply_weekly_trends.py --report /path/to/current/data.json \
  --weekly-root /path/to/reports/solenglatest/weekly --month 2026-11 \
  --timezone Asia/Kolkata --output /path/to/current/data-with-trends.json
```

The template renders a dedicated trend section. Verified adverse states and adverse
metric directions use red text; contextual changes remain neutral.

The default fixtures intentionally contain no currency or financial assumptions.
The report therefore renders financial value as unavailable rather than inventing a
customer projection. Weekly/monthly views lead with period activity, comparison to
the prior period, a short trend, and year-to-date context.

The report has independently selectable modules for Executive overview, Trends,
Curation, Artifactory, Xray, AI security, Access/OIDC, JAS, Runtime, Economic context,
Recommendations, and Evidence. The complete metric and evidence contract is in
`references/product-modules.md`. Full collection is normalized before presentation,
so focused reports do not change formulas or totals.

Generate the offline demonstration:

```bash
python3 scripts/generate_report.py --evidence fixtures/artifactory-only.json \
  --assumptions fixtures/assumptions.json --profile executive \
  --output build/artifactory-only
```

Render all available live-report modules or a focused subset:

```bash
python3 scripts/render_report.py --data build/live/data.json \
  --template assets/dashboard.html --output build/live/report.html --modules all

python3 scripts/render_report.py --data build/live/data.json \
  --template assets/dashboard.html --output build/live/curation.html \
  --modules curation,evidence
```

Accepted module names are emitted by `scripts/list_report_sections.py`; do not maintain
a second hard-coded list in host-specific instructions.

For a live full-platform run, preserve collector responses and normalize them with
`scripts/enrich_report_modules.py` before rendering. The enrichment adds Artifactory
storage posture, Xray period findings, JAS applicability evidence, and AI/agent
repository footprint. It deliberately does not infer open backlog, remediation age,
downloads, provenance, or scanner findings from configuration data.

Run tests:

```bash
python3 -m unittest discover -s tests -v
```
The canonical live weekly entrypoint is `scripts/run_live_weekly.py`. It performs a
fresh base collection, current Skills security collection, optional MCP/model/plugin
evidence merge, Access posture collection, weekly trend calculation, rendering,
validation, and atomic promotion to `latest.json`.

Before the first live run, `scripts/resolve_report_root.py` asks for an output root
when neither `JFROG_REPORT_ROOT` nor a saved configuration exists. The offered default
is `~/jfrog-platform-reports`; reports are separated by instance at
`<report-root>/<instance>/weekly/<week-ending>/report.html`.

