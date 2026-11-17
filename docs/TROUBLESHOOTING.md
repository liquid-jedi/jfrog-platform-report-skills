# Troubleshooting

## The skill is not discovered

Confirm the installed folder contains `SKILL.md` and its frontmatter name is
`jfrog-platform-report`. Restart or reload the agent after installation when required.

```bash
find .agents/skills/jfrog-platform-report-skills -maxdepth 2 -type f | sort
grep '^name: jfrog-platform-report$' \
  .agents/skills/jfrog-platform-report-skills/SKILL.md
npx skills list -g | grep jfrog-platform-report
```

## No JFrog instance is selected

Run `jf config show`. Set a default server, name the server in the prompt, or configure
`JFROG_PLATFORM_REPORT_SERVER_ID`. `JFROG_CIO_SERVER_ID` remains a deprecated
compatibility alias.

## The report asks where to save output

This is expected on first use. Accept `~/jfrog-platform-reports`, provide another path,
or set `JFROG_REPORT_ROOT`. Reports remain separated by instance.

## A module is unavailable

Unavailable is not zero. Check the evidence ledger: the capability may be unlicensed,
the API unavailable, the configured identity unauthorized, the response partial, the
period evidence expired, or financial assumptions missing.

Do not replace unavailable values with UI observations unless a supported, timestamped
collector records their source and collection time.

## Historical Curation is incomplete

Curation activity has retention and API-window constraints. Weekly collection preserves
evidence while available. The final coverage audit lists missed weeks and proposes
backfill only when the source can still provide it.

## A rerun failed

Failed runs never replace `latest.json` or the promoted `report.html`. Review
`collection-diagnostics.json`, correct the source or permission issue, and rerun.

## APM reports no trustworthy local deployment baseline

APM found deployed files that it cannot safely overwrite from its recorded baseline.
This commonly happens after an agent or user edits the installed Skill in place.

Do not use `--force` blindly. Review or preserve the changed files first. If the local
copy is disposable, or the local correction is already included in the target release,
repeat the versioned install with `--force` once:

```bash
apm install liquid-jedi/jfrog-platform-report-skills#v1.6.2 \
  --target claude \
  --force
```

Replace `claude` with the target in use. A successful transaction refreshes the lockfile
and restores a trustworthy deployment baseline for later upgrades.

## The report looks different between runs

Every run must use `assets/dashboard.html`. Check its template version marker. Data may
change; structure should change only when the versioned template changes.

## Native Windows issues

Use WSL2 with Python and JFrog CLI installed inside the distribution. This is the
supported Windows route and avoids separate PowerShell and POSIX runners.
