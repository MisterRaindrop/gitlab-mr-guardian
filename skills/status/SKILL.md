---
name: status
description: Inspect authored GitLab merge requests and report whether each is approved, waiting for review, passing CI, stale, blocked, or eligible for automated handling. Use for read-only MR guardian status checks.
disable-model-invocation: true
---

# Show MR guardian status

Run:

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/gitlab-mr-guardian" status
```

This command is read-only. Summarize the JSON output by MR and highlight CI failures, conflicts, lost approvals, and configuration errors. Do not rebase, retry CI, resolve discussions, or merge anything.
