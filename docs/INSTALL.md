# Installation

The installed skill name is `jfrog-platform-report`. APM is the recommended method
because it pins the package and records the selected agent targets.

## 1. Install prerequisites on macOS

```bash
brew install python git jfrog-cli apm
```

Verify the tools and configure at least one JFrog instance:

```bash
python3 --version
git --version
jf --version
apm --version
jf config add
jf config show
```

Python 3.11 or later is required. Install the official JFrog plugin for the agent that
will run the report. For Codex:

```bash
codex plugin marketplace add jfrog/codex-plugin
codex plugin add jfrog@codex-plugin
```

For Claude Code, start `claude`, open the plugin manager, and install
`jfrog@claude-plugins-official`. Follow the official host-specific JFrog plugin
instructions for other agents. The report requires the base JFrog Platform Skill.

## 2. Install prerequisites in Windows WSL2

Run these commands inside the WSL terminal:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv curl
curl -fL https://install-cli.jfrog.io | sh
curl -sSL https://aka.ms/apm-unix | sh
exec "$SHELL" -l
```

Verify and configure JFrog inside the same WSL environment:

```bash
python3 --version
git --version
jf --version
apm --version
jf config add
jf config show
```

Install and run the selected agent inside WSL so it can see the same JFrog CLI
configuration and report workspace.

## 3. Install with APM

These commands are the same on macOS and WSL:

```bash
mkdir -p ~/jfrog-platform-reporting
cd ~/jfrog-platform-reporting
apm init -y
apm install liquid-jedi/jfrog-platform-report-skills#v1.6.2 \
  --target claude,cursor,codex,gemini
apm deps list
apm audit
```

Use only targets available on the machine. If APM reports multiple harnesses, keep the
explicit target list. To make it persistent, add a top-level setting to `apm.yml`:

```yaml
targets:
  - claude
  - codex
  - cursor
  - gemini
```

The `liquid-jedi/...` value is the public GitHub package coordinate. It is not a JFrog
server ID or customer instance name.

## 4. Start an agent and invoke the skill

From the APM project directory, launch an installed CLI agent:

```bash
claude
```

or:

```bash
codex
```

For Cursor, open the folder in Cursor and start Agent chat. For Gemini CLI, run:

```bash
gemini
```

Then enter this prompt in the agent chat:

```text
Generate weekly JFrog Platform report
```

## 5. First-run walkthrough

The skill asks one decision at a time. Public examples use only generic instance names.

1. **Choose an instance.** The skill lists every server from `jf config show`, for
   example `1. production (default)` and `2. staging`. Reply with the intended
   production instance number.
2. **Choose a period.** Accept the last completed Monday-to-Sunday week, request another
   completed week, or explicitly choose a partial current week. The recommended answer
   is the last completed week.
3. **Choose report scope.** `Full` is recommended. `Executive` is shorter. `Custom`
   exposes individual sections and the optional Forrester benchmark.
4. **Confirm timezone.** Accept the detected IANA timezone when it matches the team.
5. **Choose output location.** Accept `~/jfrog-platform-reports` unless a shared path is
   required.
6. **Choose first-run trend history.** If no validated weekly archives exist for this
   instance in the current calendar month, the skill lists earlier completed weeks that
   can still be collected and asks whether to backfill them. Choose `Yes` when the first
   report should already include week-over-week trends. Collection runs one week at a
   time and excludes future, partial and retention-expired weeks.
7. **Review the summary.** Confirm the instance, period, scope, timezone, destination
   and any approved backfill with `Y` before read-only collection begins.

## Alternative global Skills installation

This is separate from APM and requires Node.js:

```bash
npx skills add git@github.com:liquid-jedi/jfrog-platform-report-skills.git \
  -g --skill jfrog-platform-report
```

After installation, start the agent separately and use the invocation prompt above.

## Upgrade an APM project

Run from the directory containing the existing `apm.yml`. The versioned install command
updates the existing dependency pin and deploys the selected release:

```bash
apm install liquid-jedi/jfrog-platform-report-skills#v1.6.2 \
  --target claude
apm deps list
apm audit
```

Replace `claude` with the installed target, or provide a comma-separated target list.
When a top-level `targets` list is already saved in `apm.yml`, omit `--target`.

If APM reports `no trustworthy local deployment baseline`, review the local differences
before allowing an overwrite. When the installed files are disposable or the local fix
is already present in the target release, rerun the versioned install command with
`--force`. Otherwise, preserve the changed files and reconcile them first.

Commit `apm.yml` and `apm.lock.yaml` together in a shared workspace.

## Platform compatibility

| Platform | Status | Notes |
|---|---|---|
| macOS | Supported | Primary development platform |
| Linux | Supported | Python 3.11 or later and JFrog CLI required |
| Windows with WSL2 | Supported | Install the CLI, APM and agent inside WSL |
| Native Windows | Best effort | WSL avoids agent and shell differences |
