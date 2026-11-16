# Installation

The installed skill name is `jfrog-platform-report`. The repository is
`liquid-jedi/jfrog-platform-report-skills`.

## Choose an installation mode

| Mode | Best for | Updates |
|---|---|---|
| APM project install | Teams and reproducible workspaces | Lockfile-controlled |
| Global `npx skills` install | Individual use from any folder | Re-run installer |
| Local clone | Development and contribution | `git pull` |
| JFrog AI Catalog | Governed enterprise distribution | Repository policy and signed versions |

## Prerequisites

```bash
python3 --version
jf --version
jf config show
```

Use Python 3.11 or newer. Configure at least one JFrog CLI server before a live run.
The report scripts require no third-party Python packages.

## APM

Install APM using an official method from <https://microsoft.github.io/apm/>. Then:

```bash
mkdir -p ~/jfrog-platform-reporting
cd ~/jfrog-platform-reporting
apm init -y
apm install liquid-jedi/jfrog-platform-report-skills#v1.0.2 \
  --target claude,cursor,codex,gemini
```

In a new directory, explicit `--target` avoids a “No harness detected” error. APM may
converge supported skills under `.agents/skills/` even when a target also has a native
configuration directory.

Verify:

```bash
test -f .agents/skills/jfrog-platform-report-skills/SKILL.md
grep '^name: jfrog-platform-report$' \
  .agents/skills/jfrog-platform-report-skills/SKILL.md
find .agents/skills/jfrog-platform-report-skills -maxdepth 2 -type f | sort
```

Commit `apm.yml` and the generated lockfile for a team workspace.

## Global Agent Skills install

```bash
npx skills add git@github.com:liquid-jedi/jfrog-platform-report-skills.git \
  -g --skill jfrog-platform-report
```

Verify:

```bash
npx skills list -g | grep jfrog-platform-report
```

Node.js is needed only for this installer. Report generation uses Python and JFrog CLI.

## Local development clone

```bash
git clone https://github.com/liquid-jedi/jfrog-platform-report-skills.git
cd jfrog-platform-report-skills
python3 -m unittest discover -s tests -v
python3 scripts/list_report_sections.py
```

## First run

```text
Generate weekly platform report
```

The agent resolves the JFrog instance, local timezone, last completed ISO week and
output root, then presents one compact confirmation. `Full` is recommended and a
single `Proceed` accepts the defaults. Choose `Executive` for the concise profile or
`Custom` to select individual sections. Hosts with native interactive controls display
selectable choices and checkboxes; other hosts use a numbered plain-text fallback.
The default output location offered on first use is `~/jfrog-platform-reports`.

## Platform compatibility

| Platform | Status | Notes |
|---|---|---|
| macOS | Supported | Primary development platform |
| Linux | Supported | Python 3.11+ and JFrog CLI required |
| Windows with WSL2 | Supported | Recommended Windows path; install tools inside WSL |
| Native Windows | Best effort | WSL avoids agent and shell differences |

## Updating

- APM: update the pinned release and review the lockfile change.
- Global Skills: rerun the `npx skills add` command.
- Local clone: `git pull`, then run the test suite.
- JFrog AI Catalog: publish and install a new signed semantic version.

Never replace a governed installation with an unverified public copy without the
customer's approval and policy review.
