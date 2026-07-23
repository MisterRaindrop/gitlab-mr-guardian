---
name: check
description: Run one GitLab MR Guardian cycle using the configured safety policy. Use when the user asks to check approved MRs now, rebase eligible stale MRs, request auto-merge, or report current CI failures.
disable-model-invocation: true
---

# Run one guarded MR cycle

1. Briefly state the effective native plugin options: `auto_rebase=${user_config.auto_rebase}` and `auto_merge=${user_config.auto_merge}`. Do not look for or create repository-local configuration.
2. Run:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/gitlab-mr-guardian" check
   ```

3. Summarize actions and failures. Include clickable GitLab URLs from the output.

Never retry a failed pipeline automatically. Never modify an MR with unresolved review discussions or unmet approvals. If a rebase would reset approvals, report the block instead of overriding it.
