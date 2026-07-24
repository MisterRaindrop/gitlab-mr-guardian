# GitLab MR Guardian for Claude Code

[简体中文](README.md) | [English](README.en.md)

这是一个 Claude Code 插件，用来持续照看已经完成 Review 的 GitLab Merge Request。

它只会把同时满足以下条件的 MR 纳入自动操作：

- MR 由当前 `glab` 登录用户创建，并且不是 Draft。
- GitLab 的审批要求已经满足；默认还要求至少有一位实际审批人。
- 不存在未解决的 Review discussion，也没有 `requested_changes`。
- 当前 MR Pipeline 已成功。

进入监控范围后，插件可以：

- 在 GitLab 明确返回 `need_rebase` 时请求 rebase，让 GitLab 触发新 CI。
- 如果受监控 MR 的当前 Pipeline 缺失或被跳过，则创建新的 MR Pipeline。
- 新 CI 成功后请求 Auto-merge；启用 Merge Train 的项目会由 GitLab 排队。
- CI 失败时通知 Claude，不自动重试、不修改代码。
- 出现冲突、审批丢失或 rebase 可能清除审批时暂停并报告。

## 要求

- Claude Code 2.1.105 或更新版本。
- Python 3.9 或更新版本。
- 已安装 `glab`，并执行过 `glab auth login`。

插件不保存 GitLab Token，所有认证都交给 `glab`。

## 从 Marketplace 安装（推荐）

在终端执行：

```bash
claude plugin marketplace add MisterRaindrop/gitlab-mr-guardian
claude plugin install gitlab-mr-guardian@gitlab-mr-guardian-marketplace \
  --scope user
```

安装后在 Claude Code 中执行一次配置，把 GitLab 主机和安全选项写入插件数据目录：

```text
/gitlab-mr-guardian:setup gitlab.example.com
```

`setup` 会验证 `glab` 认证、把配置持久化到 `${CLAUDE_PLUGIN_DATA}/settings.json`，并执行一次只读状态检查。`auto_rebase` 和 `auto_merge` 默认关闭；启用它们意味着插件可以改写源分支并合并代码，请先确认这符合团队规则。

后台监控默认停止，不会因为启动 Claude 就访问 GitLab。需要自动轮询时，显式执行 `/gitlab-mr-guardian:start`；使用 `/gitlab-mr-guardian:stop` 可以随时停止。手动 `/check` 不受监控开关影响。也可以完全通过 `/plugin` 界面添加 Marketplace、安装和管理插件。

## 推荐配置

以下配置最适合本插件的目标：审批完成后持续保持 MR 可合并，并在 CI 成功后尽快进入合并流程。

| 配置项 | 推荐值 | 作用 |
| --- | --- | --- |
| `hostname` | 实际 GitLab 主机 | 例如 `gitlab.example.com`；无法从当前仓库 remote 推断时必须填写。 |
| `poll_interval_seconds` | `3600` | 每小时检查一次。允许范围为 60～86400 秒。 |
| `auto_rebase` | `true` | GitLab 返回 `need_rebase` 且审批安全检查通过时自动请求 rebase。 |
| `auto_merge` | `true` | 审批和 CI 均满足条件时请求 auto-merge。 |
| `trigger_pipeline_when_missing_or_skipped` | `true` | 已纳入监控的 MR 没有 Pipeline 或 Pipeline 被跳过时补跑。 |
| `max_mr_age_days` | `90` | 只处理最近 90 天更新过的 MR，避免误碰长期遗留分支。 |
| `report_ci_failures` | `true` | CI 失败时通知当前 Claude 会话，但不自动重试失败 CI。 |

不需要配置 `include_projects`。插件默认监控当前 `glab` 用户创建的所有项目中的 MR；高级调试场景仍可在显式 JSON 配置文件中使用该过滤器。

### 可选的托管规则扩展（默认全部关闭）

| 配置项 | 默认 | 作用 |
| --- | --- | --- |
| `retry_failed_pipeline_once` | `false` | 已审批且无阻塞讨论的 MR，CI 失败时对同一条流水线自动重试一次（只重跑失败的 Job），用于偶发的环境类失败。重试后仍失败视为真实回归，只报告、不再重试。 |
| `rebase_when_ci_failed` | `false` | GitLab 返回 `need_rebase` 但当前 CI 失败、缺失或被跳过时，也允许执行安全 rebase（rebase 会在新基线上触发全新 CI）。需同时开启 `auto_rebase`，审批保护检查照常生效。 |
| `advisory_reviewers` | `[]` | 这些用户名（例如 AI Review 机器人）发起的未解决讨论视为参考意见，不阻塞自动操作；数量会以 `advisory_unresolved` 字段出现在状态输出中。任何其他账号的未解决讨论（包括在 AI 线程中的人工回复）仍然阻塞。 |

通过 setup 或 `configure` 子命令启用，例如：

```bash
"${CLAUDE_PLUGIN_ROOT}/bin/gitlab-mr-guardian" \
  --plugin-data-dir "${CLAUDE_PLUGIN_DATA}" \
  configure \
  --retry-failed-pipeline-once true \
  --rebase-when-ci-failed true \
  --advisory-reviewers ai-review-bot
```

注意：如果 GitLab 项目开启了“合并前必须解决所有讨论”，即使插件把 AI 讨论视为参考，GitLab 本身仍会拒绝合并；此时需要解决讨论或调整项目设置。

即使启用了推荐配置，以下保护仍然有效：未完成审批、存在未解决 discussion、存在代码冲突、rebase 会清除审批时，插件不会自动推进。失败或取消的 CI 也只报告，不会自动重试。

### 配置是如何创建的

- **`/gitlab-mr-guardian:setup`：**唯一的正式配置入口。它验证 `glab` 认证，把主机名和安全选项写入 `${CLAUDE_PLUGIN_DATA}/settings.json`（权限 0600），并执行只读状态检查；它不会创建或修改业务仓库中的文件。
- **后台 Monitor 与所有命令从同一个 `settings.json` 读取配置。**从 Claude Code 2.1.207 起，Monitor 命令不再接收 `${user_config.*}` 或 `CLAUDE_PLUGIN_OPTION_*`，因此插件自己维护这个配置文件。Monitor 每个轮询周期重新读取，配置修改后无需重启会话。
- **监控开关：**`start` / `stop` 状态保存在 `${CLAUDE_PLUGIN_DATA}/control.json`，默认停止并跨 Claude 会话保留。
- **重新配置：**再次运行 `/gitlab-mr-guardian:setup`，或直接执行 `configure` 子命令；只传需要修改的选项，其余保持不变。
- **`--plugin-dir` 开发模式：**通常直接使用插件默认选项和 Git remote 推断主机。只有脱离 Claude Code 单独测试脚本时，才需要后文所述的用户级开发配置文件。

## 从本地 Marketplace 安装

发布前可以使用包含本 README 的插件目录进行完整安装测试：

```bash
claude plugin marketplace add /absolute/path/to/gitlab-mr-guardian
claude plugin install gitlab-mr-guardian@gitlab-mr-guardian-marketplace \
  --scope user
```

安装后同样通过 `/gitlab-mr-guardian:setup` 写入配置。

这条路径必须是绝对路径，或是相对于启动 Claude Code 时所在目录的路径。

## 开发模式加载

`--plugin-dir` 只用于开发和快速调试，不是日常安装方式。在插件目录的上一级执行：

```bash
claude --plugin-dir ./gitlab-mr-guardian
```

如果需要脱离 Claude Code 的插件配置界面单独调试命令行程序，可以生成用户级开发配置：

```bash
./gitlab-mr-guardian/bin/gitlab-mr-guardian init \
  --hostname gitlab.example.com \
  --auto-rebase \
  --auto-merge
```

默认路径为 `$XDG_CONFIG_HOME/gitlab-mr-guardian/config.json`；未设置 `XDG_CONFIG_HOME` 时使用 `~/.config/gitlab-mr-guardian/config.json`。也可以通过 `--path` 或 `MR_GUARDIAN_CONFIG` 指定其他位置。这个兼容配置不会写入当前业务仓库。

## 配置与状态

正式安装时，配置保存在 Claude Code 提供的 `${CLAUDE_PLUGIN_DATA}` 持久目录下的 `settings.json`，由 `/gitlab-mr-guardian:setup`（即 `configure` 子命令）写入，后台 Monitor 和所有手动命令都从这个文件读取。

配置读取优先级：

1. 显式传入的 `--config` / `MR_GUARDIAN_CONFIG`（仅用于高级调试）。
2. `${CLAUDE_PLUGIN_DATA}/settings.json`（正式安装的配置来源）。
3. 旧版 Claude Code（< 2.1.207）导出的 `CLAUDE_PLUGIN_OPTION_*` 环境变量（向后兼容）。
4. 用户级开发配置文件 `~/.config/gitlab-mr-guardian/config.json`。
5. 内置安全默认值。

- 插件源码中的 `config.example.json` 只是高级选项参考，不是运行时配置。
- 轮询状态、去重信息和监控开关也保存在 `${CLAUDE_PLUGIN_DATA}`。
- 插件不会写入当前仓库的 `.claude/`、`.gitignore` 或其他业务文件。

## 使用

```text
/gitlab-mr-guardian:setup
/gitlab-mr-guardian:status
/gitlab-mr-guardian:check
/gitlab-mr-guardian:start
/gitlab-mr-guardian:stop
```

- `setup`：验证认证，把主机名与安全选项写入插件数据目录的 `settings.json`，并执行只读状态检查。
- `status`：只读查看 MR 当前状态。
- `check`：立即执行一次已配置的受保护推进流程。
- `start`：开始后台轮询；开关状态跨会话保存。
- `stop`：停止新的后台轮询，但保留所有手动命令。

后台监控默认停止。执行 `start` 后，当前活跃 Claude 会话会在几秒内开始轮询，默认每 1 小时检查一次，并且只在状态发生变化时通知 Claude。执行 `stop` 后不会开始新的自动周期；已经发出的单次 GitLab 请求可能会先完成。可以通过 `poll_interval_seconds` 自定义 60～86400 秒的间隔。

## 安全边界

- `auto_rebase` 和 `auto_merge` 必须在插件配置中显式启用。
- 默认只处理最近 90 天内有更新的 MR，避免误碰长期遗留的开放分支；设为 `0` 才会取消时间限制。
- Rebase 仅在 GitLab 返回 `need_rebase` 时执行，不会为了“保持新鲜”而反复创建提交。
- 只有已受监控或历史上存在成功 Pipeline 的 MR，才会在当前 Pipeline 为 `missing/skipped` 时补跑。`failed/canceled` 默认只报告；显式开启 `retry_failed_pipeline_once` 后，同一条流水线最多自动重试一次，重试后仍失败只报告。
- 人类评审的未解决讨论始终阻塞自动操作；只有显式列入 `advisory_reviewers` 的账号（如 AI Review 机器人）的讨论被视为参考。
- 如果项目启用了 `reset_approvals_on_push`，默认禁止自动 rebase，因为它可能清除已有审批。
- Auto-merge 请求携带当前 MR SHA，避免审查过的提交与被合并提交不一致。
- 插件不会自动重试失败 CI，也不会自动解决 Review 意见或代码冲突。

## 运行范围

执行 `start` 后，Claude Code 的插件 Monitor 只属于取得运行锁的当前交互式会话：轮询结果和 CI 告警只会进入这个会话，不会扩散、同步或广播到其他 Claude Code 会话。

如果同时打开多个启用了本插件的 Claude Code 会话，插件会通过进程锁避免对同一 GitLab 主机重复执行操作。获得锁的会话负责监控并接收通知；其他会话不会收到这些通知。负责监控的会话关闭后，仍处于运行状态的其他会话可以在下一次轮询时接管。

关闭所有 Claude Code 会话后，插件不会继续轮询。需要真正 7×24 小时监控时，应把同一套判断逻辑放进常驻服务、GitLab Scheduled Pipeline 或系统调度器，再把告警发送到邮件、Slack 等渠道。

## 许可证

本项目采用 [Apache License 2.0](LICENSE)。
