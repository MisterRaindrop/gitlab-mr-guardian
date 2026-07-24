# GitLab MR Guardian for Claude Code

[简体中文](README.md) | [English](README.en.md)

A Claude Code plugin that continuously watches GitLab merge requests after code review is complete.

The plugin only performs automated actions on MRs that meet all of these conditions:

- The MR was created by the current `glab` user and is not a draft.
- All GitLab approval requirements are satisfied, with at least one actual approver by default.
- There are no unresolved review discussions or `requested_changes` states.
- The current MR pipeline has succeeded.

Once an MR enters the monitored set, the plugin can:

- Request a rebase when GitLab explicitly reports `need_rebase`, allowing GitLab to start a new CI pipeline.
- Create a new MR pipeline when the current pipeline is missing or skipped.
- Request auto-merge after the new pipeline succeeds. Projects using Merge Trains are queued by GitLab.
- Notify Claude when CI fails, without retrying the pipeline or changing code.
- Pause and report conflicts, lost approvals, or rebases that could reset approvals.

## Requirements

- Claude Code 2.1.105 or later.
- Python 3.9 or later.
- `glab` installed and authenticated with `glab auth login`.

The plugin never stores a GitLab token. Authentication is delegated entirely to `glab`.

## Install from a Marketplace (recommended)

Run the following commands in a terminal:

```bash
claude plugin marketplace add MisterRaindrop/gitlab-mr-guardian
claude plugin install gitlab-mr-guardian@gitlab-mr-guardian-marketplace \
  --scope user
```

After installation, run the setup command once inside Claude Code to persist the GitLab host and safety options into the plugin data directory:

```text
/gitlab-mr-guardian:setup gitlab.example.com
```

`setup` verifies `glab` authentication, persists the configuration into `${CLAUDE_PLUGIN_DATA}/settings.json`, and performs a read-only status check. `auto_rebase` and `auto_merge` default to off; enabling them allows the plugin to rewrite source branches and merge code, so confirm that both actions comply with your team's rules.

Background monitoring remains stopped after installation and starting Claude does not contact GitLab. Run `/gitlab-mr-guardian:start` explicitly in Claude Code to begin automatic polling, and `/gitlab-mr-guardian:stop` to stop it. Manual `/check` remains available regardless of the monitoring state. You can also use the `/plugin` interface for the entire marketplace, installation, and management flow.

## Recommended configuration

The following settings best match the plugin's primary goal: keep reviewed MRs mergeable and move them into the merge flow as soon as CI succeeds.

| Option | Recommended value | Purpose |
| --- | --- | --- |
| `hostname` | Your GitLab host | For example, `gitlab.example.com`. Required when the host cannot be inferred from the current repository remote. |
| `poll_interval_seconds` | `3600` | Check once per hour. The allowed range is 60 to 86400 seconds. |
| `auto_rebase` | `true` | Request a rebase when GitLab reports `need_rebase` and all approval safety checks pass. |
| `auto_merge` | `true` | Request auto-merge after approvals and CI satisfy all guarded conditions. |
| `trigger_pipeline_when_missing_or_skipped` | `true` | Start a pipeline when a managed MR has no pipeline or its pipeline was skipped. |
| `max_mr_age_days` | `90` | Only handle MRs updated within the last 90 days, avoiding long-lived branches. |
| `report_ci_failures` | `true` | Notify the current Claude session when CI fails without retrying failed CI automatically. |

You do not need to configure `include_projects`. By default, the plugin monitors MRs authored by the current `glab` user across all projects. The filter remains available in an explicit JSON configuration file for advanced testing scenarios.

### Optional managed-rule extensions (all off by default)

| Option | Default | Purpose |
| --- | --- | --- |
| `manage_all_approved` | `false` | Manage every approved MR with no blocking discussions directly, without requiring a previously successful pipeline. Managed MRs get missing/skipped pipelines refreshed and failed CI retried or reported per the rules below; explicit errors such as conflicts or lost approvals still pause and report. |
| `retry_failed_pipeline_once` | `false` | For approved MRs with no blocking discussions, retry the failed jobs of the current pipeline once per pipeline, targeting flaky environment failures. A failure after the retry is treated as a real regression: reported, never retried again. |
| `rebase_when_ci_failed` | `false` | Allow the safe rebase flow when GitLab reports `need_rebase` while the current pipeline is failed, missing, or skipped (the rebase triggers a fresh pipeline on the new base). Requires `auto_rebase`; all approval safety checks still apply. |
| `advisory_reviewers` | `[]` | Unresolved discussions started by these usernames (for example AI review bots) are advisory and never block automation; their count appears as `advisory_unresolved` in status output. Unresolved notes from any other account — including human replies inside an AI thread — still block. |

Enable them through setup or the `configure` subcommand, for example:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/gitlab-mr-guardian" \
  --plugin-data-dir "${CLAUDE_PLUGIN_DATA}" \
  configure \
  --manage-all-approved true \
  --retry-failed-pipeline-once true \
  --rebase-when-ci-failed true \
  --advisory-reviewers ai-review-bot
```

Note: when a GitLab project requires all threads to be resolved before merging, GitLab itself still refuses the merge even though the plugin treats AI threads as advisory; resolve the threads or adjust the project setting.

The safety checks still apply with the recommended settings. The plugin does not advance MRs with missing approvals, unresolved discussions, code conflicts, or rebases that would reset approvals. Failed or canceled CI is reported but never retried automatically.

### How configuration is created

- **`/gitlab-mr-guardian:setup`:** the single configuration entry point. It verifies `glab` authentication, writes the hostname and safety options into `${CLAUDE_PLUGIN_DATA}/settings.json` (mode 0600), and performs a read-only status check. It does not create or modify files in the application repository.
- **The background Monitor and all commands read the same `settings.json`.** Starting with Claude Code 2.1.207, Monitor commands no longer receive `${user_config.*}` substitutions or `CLAUDE_PLUGIN_OPTION_*` environment variables, so the plugin maintains its own configuration file. The Monitor re-reads it on every polling cycle, so configuration changes take effect without restarting the session.
- **Monitoring control:** the `start` / `stop` state is stored in `${CLAUDE_PLUGIN_DATA}/control.json`, defaults to stopped, and persists across Claude sessions.
- **Reconfiguration:** run `/gitlab-mr-guardian:setup` again, or invoke the `configure` subcommand directly; pass only the options you want to change and the rest stay as they are.
- **`--plugin-dir` development mode:** normally uses plugin defaults and infers the host from the Git remote. A user-level development configuration file is needed only when testing the standalone script outside Claude Code, as described below.

## Install from a local Marketplace

Before publishing, test the complete installation flow using the plugin directory containing this README:

```bash
claude plugin marketplace add /absolute/path/to/gitlab-mr-guardian
claude plugin install gitlab-mr-guardian@gitlab-mr-guardian-marketplace \
  --scope user
```

Configure it the same way with `/gitlab-mr-guardian:setup` after installation.

The path must be absolute or relative to the directory from which Claude Code was started.

## Development mode

`--plugin-dir` is intended only for development and quick testing, not routine installation. Run this command from the parent directory of the plugin:

```bash
claude --plugin-dir ./gitlab-mr-guardian
```

To test the command-line program independently from Claude Code's plugin configuration interface, create a user-level development configuration:

```bash
./gitlab-mr-guardian/bin/gitlab-mr-guardian init \
  --hostname gitlab.example.com \
  --auto-rebase \
  --auto-merge
```

The default path is `$XDG_CONFIG_HOME/gitlab-mr-guardian/config.json`, or `~/.config/gitlab-mr-guardian/config.json` when `XDG_CONFIG_HOME` is unset. Use `--path` or `MR_GUARDIAN_CONFIG` to select another path. This compatibility configuration never writes to the current application repository.

## Configuration and state

For a regular installation, configuration lives in `settings.json` inside the persistent `${CLAUDE_PLUGIN_DATA}` directory provided by Claude Code. It is written by `/gitlab-mr-guardian:setup` (the `configure` subcommand), and the background Monitor and every manual command read from it.

Configuration resolution order:

1. An explicit `--config` path or `MR_GUARDIAN_CONFIG` (advanced testing only).
2. `${CLAUDE_PLUGIN_DATA}/settings.json` (the normal source for installed plugins).
3. `CLAUDE_PLUGIN_OPTION_*` environment variables exported by older Claude Code versions (< 2.1.207), kept for backward compatibility.
4. The user-level development file `~/.config/gitlab-mr-guardian/config.json`.
5. Built-in safe defaults.

- `config.example.json` in the plugin source is only a reference for advanced options, not the runtime configuration.
- Polling state, event deduplication data, and the monitoring switch are also stored in `${CLAUDE_PLUGIN_DATA}`.
- The plugin does not write `.claude/`, `.gitignore`, or any other file in the current application repository.

## Usage

```text
/gitlab-mr-guardian:setup
/gitlab-mr-guardian:status
/gitlab-mr-guardian:check
/gitlab-mr-guardian:start
/gitlab-mr-guardian:stop
```

- `setup`: verify authentication, persist the hostname and safety options into `settings.json` in the plugin data directory, and run a read-only status check.
- `status`: inspect the current MR state without making changes.
- `check`: immediately run one configured and guarded advancement cycle.
- `start`: begin background polling; the control state persists across sessions.
- `stop`: stop new background polling while keeping all manual commands available.

Background monitoring is stopped by default. After `start`, an active Claude session begins polling within a few seconds, once per hour by default, and only notifies Claude when state changes. After `stop`, no new automatic cycle begins, although an individual GitLab request already in flight may finish. Use `poll_interval_seconds` to customize the interval from 60 to 86400 seconds.

## Safety boundaries

- `auto_rebase` and `auto_merge` must be explicitly enabled in the plugin configuration.
- By default, the plugin only handles MRs updated within the last 90 days to avoid touching long-lived branches. Set the limit to `0` to disable it.
- A rebase is requested only when GitLab reports `need_rebase`; the plugin does not repeatedly create commits merely to keep a branch fresh.
- By default a missing or skipped pipeline is refreshed only when the MR is already managed or has a previously successful pipeline; with `manage_all_approved` enabled, every approved MR with no blocking discussions is managed. Failed or canceled pipelines are reported by default; with `retry_failed_pipeline_once` explicitly enabled, each pipeline is retried at most once, and a post-retry failure is only reported.
- Unresolved discussions from human reviewers always block automation; only accounts explicitly listed in `advisory_reviewers` (such as AI review bots) are treated as advisory.
- Automatic rebase is blocked by default when a project uses `reset_approvals_on_push`, because the rebase could clear existing approvals.
- Auto-merge requests include the current MR SHA so the reviewed commit and merged commit cannot silently diverge.
- The plugin never retries failed CI automatically and never resolves review feedback or code conflicts automatically.

## Session scope

After `start`, the Claude Code plugin Monitor belongs only to the interactive session that acquires the runtime lock. Poll results and CI alerts are delivered to that session and are not propagated, synchronized, or broadcast to other Claude Code sessions.

If several Claude Code sessions with this plugin enabled are open at the same time, a process lock prevents duplicate actions against the same GitLab host. The session holding the lock performs monitoring and receives notifications; other sessions do not receive those notifications. If the monitoring session closes, another running session can take over on its next polling cycle.

The plugin stops polling after all Claude Code sessions are closed. For true 24/7 monitoring, run the same decision logic in a persistent service, a GitLab Scheduled Pipeline, or a system scheduler, then send alerts through email, Slack, or another channel.

## License

This project is licensed under the [Apache License 2.0](LICENSE).
