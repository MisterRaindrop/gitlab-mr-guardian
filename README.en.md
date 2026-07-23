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
  --scope user \
  --config hostname=gitlab.example.com \
  --config poll_interval_seconds=3600 \
  --config auto_rebase=true \
  --config auto_merge=true \
  --config trigger_pipeline_when_missing_or_skipped=true \
  --config max_mr_age_days=90 \
  --config report_ci_failures=true
```

These are the recommended settings for automatically advancing an MR after review is complete. They allow the plugin to rebase and request auto-merge, so confirm that both actions comply with your team's rules. To begin in monitoring-only mode, remove `auto_rebase=true` and `auto_merge=true`; both options are disabled by default.

Options omitted from `--config` use the safe defaults declared by the plugin. After installation, open the Installed page under `/plugin` to configure the plugin. Run `/reload-plugins` after installing or changing configuration in an existing session.

With `--scope user`, Claude Code automatically stores the options in user-level settings rather than the current application repository. You do not need to create a configuration file manually, and `/gitlab-mr-guardian:setup` does not create repository configuration files. You can also use the `/plugin` interface for the entire marketplace, installation, and management flow.

## Recommended configuration

The following settings best match the plugin's primary goal: keep reviewed MRs mergeable and move them into the merge flow as soon as CI succeeds.

| Option | Recommended value | Purpose |
| --- | --- | --- |
| `hostname` | Your GitLab host | For example, `gitlab.example.com`. Required when the host cannot be inferred from the current repository remote. |
| `poll_interval_seconds` | `3600` | Check once per hour. The allowed range is 60 to 86400 seconds. |
| `auto_rebase` | `true` | Request a rebase when GitLab reports `need_rebase` and all approval safety checks pass. |
| `auto_merge` | `true` | Request auto-merge after approvals and CI satisfy all guarded conditions. |
| `trigger_pipeline_when_missing_or_skipped` | `true` | Start a pipeline when a managed MR has no pipeline or its pipeline was skipped. |
| `include_projects` | Empty | Empty includes all projects authored by the current user. Use `group/project-a,group/project-b` to restrict the scope. |
| `max_mr_age_days` | `90` | Only handle MRs updated within the last 90 days, avoiding long-lived branches. |
| `report_ci_failures` | `true` | Notify the current Claude session when CI fails without retrying failed CI automatically. |

The safety checks still apply with the recommended settings. The plugin does not advance MRs with missing approvals, unresolved discussions, code conflicts, or rebases that would reset approvals. Failed or canceled CI is reported but never retried automatically.

### How configuration is created

- **Marketplace installation:** no JSON file is required. Claude Code automatically stores values supplied through installation-time `--config` arguments or the configuration dialog shown when the plugin is enabled.
- **`/gitlab-mr-guardian:setup`:** checks `glab` authentication, shows the effective settings, and performs a read-only status check. It does not create or modify files in the application repository.
- **Reconfiguration:** open `/plugin` → Installed → GitLab MR Guardian, change its options, and run `/reload-plugins`. Restart the session for Monitor configuration changes to take full effect.
- **`--plugin-dir` development mode:** normally uses plugin defaults and infers the host from the Git remote. A user-level development configuration file is needed only when testing the standalone script outside Claude Code, as described below.

## Install from a local Marketplace

Before publishing, test the complete installation flow using the plugin directory containing this README:

```bash
claude plugin marketplace add /absolute/path/to/gitlab-mr-guardian
claude plugin install gitlab-mr-guardian@gitlab-mr-guardian-marketplace \
  --scope user \
  --config hostname=gitlab.example.com \
  --config poll_interval_seconds=3600 \
  --config auto_rebase=true \
  --config auto_merge=true
```

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

For a regular installation, configuration comes from the `userConfig` declaration in `.claude-plugin/plugin.json`. Claude Code stores non-sensitive options in the plugin configuration area of the user-level `~/.claude/settings.json` and exports them to the plugin process as environment variables.

- `config.example.json` in the plugin source is only a reference for advanced options, not the runtime configuration.
- Polling state and event deduplication data are stored in the persistent `${CLAUDE_PLUGIN_DATA}` directory provided by Claude Code.
- The plugin does not write `.claude/`, `.gitignore`, or any other file in the current application repository.
- Explicit `--config` and `MR_GUARDIAN_CONFIG` values are only intended for advanced testing and compatibility scenarios.

## Usage

```text
/gitlab-mr-guardian:setup
/gitlab-mr-guardian:status
/gitlab-mr-guardian:check
```

- `setup`: verify authentication, explain the effective configuration, and run a read-only status check; it does not create a configuration file.
- `status`: inspect the current MR state without making changes.
- `check`: immediately run one configured and guarded advancement cycle.

The background Monitor starts automatically when the plugin is enabled. It polls once per hour by default and only notifies Claude when state changes. Set `poll_interval_seconds` while installing or reconfiguring the plugin to customize the interval from 60 to 86400 seconds.

## Safety boundaries

- `auto_rebase` and `auto_merge` must be explicitly enabled in the plugin configuration.
- By default, the plugin only handles MRs updated within the last 90 days to avoid touching long-lived branches. Set the limit to `0` to disable it.
- A rebase is requested only when GitLab reports `need_rebase`; the plugin does not repeatedly create commits merely to keep a branch fresh.
- A missing or skipped pipeline is refreshed only when the MR is already managed or has a previously successful pipeline. Failed or canceled pipelines are reported but never retried automatically.
- Automatic rebase is blocked by default when a project uses `reset_approvals_on_push`, because the rebase could clear existing approvals.
- Auto-merge requests include the current MR SHA so the reviewed commit and merged commit cannot silently diverge.
- The plugin never retries failed CI automatically and never resolves review feedback or code conflicts automatically.

## Session scope

The Claude Code plugin Monitor belongs only to the interactive session that started it. Poll results and CI alerts are delivered to that session and are not propagated, synchronized, or broadcast to other Claude Code sessions.

If several Claude Code sessions with this plugin enabled are open at the same time, a process lock prevents duplicate actions against the same GitLab host. The session holding the lock performs monitoring and receives notifications; other sessions do not receive those notifications. If the monitoring session closes, another running session can take over on its next polling cycle.

The plugin stops polling after all Claude Code sessions are closed. For true 24/7 monitoring, run the same decision logic in a persistent service, a GitLab Scheduled Pipeline, or a system scheduler, then send alerts through email, Slack, or another channel.

## License

This project is licensed under the [Apache License 2.0](LICENSE).
