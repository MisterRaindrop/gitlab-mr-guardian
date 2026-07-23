---
name: check
description: Run one GitLab MR Guardian cycle using the configured safety policy. Use when the user asks to check approved MRs now, rebase eligible stale MRs, request auto-merge, or report current CI failures.
disable-model-invocation: true
---

# Run one guarded MR cycle

1. Briefly state the effective native plugin options: `auto_rebase=${user_config.auto_rebase}` and `auto_merge=${user_config.auto_merge}`. Do not look for or create repository-local configuration.
2. Run:

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
     check
   ```

3. Summarize actions and failures. Include clickable GitLab URLs from the output.

Never retry a failed pipeline automatically. Never modify an MR with unresolved review discussions or unmet approvals. If a rebase would reset approvals, report the block instead of overriding it.
