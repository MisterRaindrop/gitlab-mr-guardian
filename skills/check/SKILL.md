---
name: check
description: Run one GitLab MR Guardian cycle using the configured safety policy. Use when the user asks to check approved MRs now, rebase eligible stale MRs, request auto-merge, or report current CI failures.
disable-model-invocation: true
---

# Run one guarded MR cycle

1. Show the effective configuration first so the user knows whether mutations are enabled:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/gitlab-mr-guardian" \
     --plugin-data-dir "${CLAUDE_PLUGIN_DATA}" \
     configure
   ```

   Briefly state `auto_rebase` and `auto_merge` from the `CONFIG_SHOW` output. Configuration comes from `settings.json` in the plugin data directory; do not look for or create repository-local configuration.

2. Run:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/gitlab-mr-guardian" \
     --plugin-data-dir "${CLAUDE_PLUGIN_DATA}" \
     check
   ```

3. Summarize actions and failures. Include clickable GitLab URLs from the output. If the output reports a missing hostname, direct the user to run `/gitlab-mr-guardian:setup <hostname>` first.

Never retry a failed pipeline automatically. Never modify an MR with unresolved review discussions or unmet approvals. If a rebase would reset approvals, report the block instead of overriding it.
