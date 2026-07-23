---
name: status
description: Inspect authored GitLab merge requests and report whether each is approved, waiting for review, passing CI, stale, blocked, or eligible for automated handling. Use for read-only MR guardian status checks.
disable-model-invocation: true
---

# Show MR guardian status

Run:

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

This command is read-only. Summarize the JSON output by MR and highlight CI failures, conflicts, lost approvals, and configuration errors. Do not rebase, retry CI, resolve discussions, or merge anything.
