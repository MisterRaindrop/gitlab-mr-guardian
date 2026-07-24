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
  status
```

Configuration is read from `settings.json` in the plugin data directory (written by `/gitlab-mr-guardian:setup`). If the output reports a missing hostname, direct the user to run `/gitlab-mr-guardian:setup <hostname>` first.

This command is read-only. Summarize the JSON output by MR and highlight CI failures, conflicts, lost approvals, and configuration errors. Do not rebase, retry CI, resolve discussions, or merge anything.
