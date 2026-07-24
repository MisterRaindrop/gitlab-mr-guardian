---
name: start
description: Start persistent GitLab MR Guardian background polling for the current Claude Code plugin installation. Use only when the user explicitly asks to start or resume monitoring.
disable-model-invocation: true
---

# Start GitLab MR Guardian monitoring

1. Show the effective configuration:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/gitlab-mr-guardian" \
     --plugin-data-dir "${CLAUDE_PLUGIN_DATA}" \
     configure
   ```

   State the `auto_rebase` and `auto_merge` values that background polling will use. If `hostname` is empty and cannot be inferred from the current repository remote, direct the user to run `/gitlab-mr-guardian:setup <hostname>` first instead of starting.

2. Run:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/gitlab-mr-guardian" \
     --plugin-data-dir "${CLAUDE_PLUGIN_DATA}" \
     start
   ```

3. Report that monitoring is enabled and will begin within a few seconds in an active Claude Code session.

The setting persists across Claude Code sessions until the user runs `/gitlab-mr-guardian:stop`.
