---
name: setup
description: Configure GitLab MR Guardian by persisting the hostname and safety options into the plugin data directory, then verify glab authentication and run a read-only status check. Use when the user asks to initialize, enable, or change automatic MR monitoring, rebasing, auto-merge, project filters, or the GitLab host.
disable-model-invocation: true
argument-hint: [GitLab hostname]
---

# Set up GitLab MR Guardian

1. Show the currently effective configuration and monitor switch:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/gitlab-mr-guardian" \
     --plugin-data-dir "${CLAUDE_PLUGIN_DATA}" \
     configure
   ```

   The `CONFIG_SHOW` output includes `config` (effective values) and `monitor_enabled` (the real persistent background-polling switch).

2. Determine the GitLab hostname: use `$ARGUMENTS` when supplied; otherwise keep the already-configured hostname when it is non-empty; otherwise infer it from `git remote get-url origin`; otherwise ask the user.

3. Run `glab auth status --hostname <hostname>`. If it reports a token problem, do not stop there: confirm with a real read call such as `glab api user --hostname <hostname>`, because `glab auth status` can report an invalid token while API access still works. Never print or request an access token when `glab` API calls succeed. Warn the user that write operations (rebase, pipeline trigger, auto-merge) may still fail if the token lacks `api` scope.

4. Explain that automatic rebase changes the source branch and automatic merge can merge code immediately. Obtain confirmation before enabling either mutation unless the user already explicitly requested it in the current turn.

5. Persist the configuration into the plugin data directory. Pass only the options the user chose to set; omitted options keep their previous or default values:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/gitlab-mr-guardian" \
     --plugin-data-dir "${CLAUDE_PLUGIN_DATA}" \
     configure \
     --hostname "<hostname>" \
     --auto-rebase false \
     --auto-merge false
   ```

   This writes `settings.json` inside `${CLAUDE_PLUGIN_DATA}`. The background monitor and all other commands read configuration from this file; native plugin userConfig substitution is not used. Never create or edit configuration inside the user's repository.

   Optional managed-rule extensions (all off by default) can be set the same way: `--retry-failed-pipeline-once true` (retry a failed pipeline's jobs once per pipeline for approved MRs), `--rebase-when-ci-failed true` (allow safe rebase for `need_rebase` MRs even while CI is failed, missing, or skipped), and `--advisory-reviewers <bot,names>` (comma-separated usernames, e.g. AI review bots, whose unresolved discussions are advisory and never block automation). Explain the behavior change and confirm before enabling any of them unless the user already explicitly requested it.

6. Run a read-only status check and summarize which merge requests are monitored, paused for review, waiting for CI, or blocked:

   ```bash
   "${CLAUDE_PLUGIN_ROOT}/bin/gitlab-mr-guardian" \
     --plugin-data-dir "${CLAUDE_PLUGIN_DATA}" \
     status
   ```

7. Report the real monitoring state from the `monitor_enabled` field of the `CONFIG_SAVED` output — do not assume polling is off. If it is `true`, background polling is already active and will pick up the new configuration on its next cycle. If it is `false`, tell the user that `/gitlab-mr-guardian:start` enables background polling and `/gitlab-mr-guardian:stop` disables it; polling runs only while an interactive Claude Code session is open.

Do not weaken approval or unresolved-discussion checks. Do not enable `allow_rebase_that_resets_approvals` unless the user explicitly accepts that a rebase can invalidate approvals.
