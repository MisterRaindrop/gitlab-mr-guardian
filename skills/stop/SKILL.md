---
name: stop
description: Stop GitLab MR Guardian background polling. Use when the user explicitly asks to stop, pause, or disable automatic MR monitoring while keeping manual commands available.
disable-model-invocation: true
---

# Stop GitLab MR Guardian monitoring

Run:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/gitlab-mr-guardian" \
  --plugin-data-dir "${CLAUDE_PLUGIN_DATA}" \
  stop
```

Report that new polling is disabled. A GitLab request already in progress may finish, but no new automatic cycle will start. Manual `/gitlab-mr-guardian:status` and `/gitlab-mr-guardian:check` commands remain available.
