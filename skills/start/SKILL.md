---
name: start
description: Start persistent GitLab MR Guardian background polling for the current Claude Code plugin installation. Use only when the user explicitly asks to start or resume monitoring.
disable-model-invocation: true
---

# Start GitLab MR Guardian monitoring

1. State that background monitoring will use `auto_rebase=${user_config.auto_rebase}` and `auto_merge=${user_config.auto_merge}`.
2. Run:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/gitlab-mr-guardian" \
     --plugin-data-dir "${CLAUDE_PLUGIN_DATA}" \
     start
   ```

3. Report that monitoring is enabled and will begin within a few seconds in an active Claude Code session.

The setting persists across Claude Code sessions until the user runs `/gitlab-mr-guardian:stop`.
