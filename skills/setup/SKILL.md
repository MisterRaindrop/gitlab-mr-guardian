---
name: setup
description: Verify and explain the user-level GitLab MR Guardian configuration. Use when the user asks to initialize, enable, or change automatic MR monitoring, rebasing, auto-merge, project filters, or the GitLab host.
disable-model-invocation: true
argument-hint: [GitLab hostname]
---

# Set up GitLab MR Guardian

1. Treat Claude Code's native plugin options as the normal configuration source. The configured values include:

   - `hostname`: `${user_config.hostname}`
   - `auto_rebase`: `${user_config.auto_rebase}`
   - `auto_merge`: `${user_config.auto_merge}`
   - `poll_interval_seconds`: `${user_config.poll_interval_seconds}`
   - `trigger_pipeline_when_missing_or_skipped`: `${user_config.trigger_pipeline_when_missing_or_skipped}`
   - `max_mr_age_days`: `${user_config.max_mr_age_days}`
   - `report_ci_failures`: `${user_config.report_ci_failures}`

2. Run `glab auth status`. Add `--hostname "$ARGUMENTS"` when a hostname was supplied; otherwise use the configured hostname when it is non-empty. Never print or request an access token when existing `glab` authentication works.
3. Explicitly tell the user that marketplace installation creates and stores native plugin configuration automatically. This setup skill does not create a JSON file and must not create or edit configuration inside the user's repository. If plugin options need changing, direct the user to `/plugin`, the installed plugin's configuration flow, or reinstall/re-enable it so Claude Code shows the native `userConfig` dialog.
4. Explain that automatic rebase changes the source branch and automatic merge can merge code immediately. Obtain confirmation before instructing the user to enable either mutation unless they already explicitly requested it in the current turn.
5. Run:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/gitlab-mr-guardian" \
     --plugin-data-dir "${CLAUDE_PLUGIN_DATA}" \
     --runtime-hostname "${user_config.hostname}" \
     --runtime-poll-interval-seconds "${user_config.poll_interval_seconds}" \
     --runtime-auto-rebase "${user_config.auto_rebase}" \
     --runtime-auto-merge "${user_config.auto_merge}" \
     --runtime-trigger-pipeline-when-missing-or-skipped "${user_config.trigger_pipeline_when_missing_or_skipped}" \
     --runtime-max-mr-age-days "${user_config.max_mr_age_days}" \
     --runtime-report-ci-failures "${user_config.report_ci_failures}" \
     status
   ```

   Summarize which merge requests are monitored, paused for review, waiting for CI, or blocked.
6. Tell the user that background polling is stopped by default, starts only after `/gitlab-mr-guardian:start`, and runs only while an interactive Claude Code session is open.

Do not weaken approval or unresolved-discussion checks. Do not enable `allow_rebase_that_resets_approvals` unless the user explicitly accepts that a rebase can invalidate approvals.
