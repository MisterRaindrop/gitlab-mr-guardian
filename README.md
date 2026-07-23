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
  --scope user \
  --config hostname=gitlab.example.com \
  --config poll_interval_seconds=3600 \
  --config auto_rebase=true \
  --config auto_merge=true \
  --config trigger_pipeline_when_missing_or_skipped=true \
  --config max_mr_age_days=90 \
  --config report_ci_failures=true
```

上面的参数允许插件执行 rebase 和请求 auto-merge，请先确认这符合团队规则。安装完成后后台监控仍保持停止，不会因为启动 Claude 就访问 GitLab。需要自动轮询时，在 Claude Code 中显式执行 `/gitlab-mr-guardian:start`；使用 `/gitlab-mr-guardian:stop` 可以随时停止。手动 `/check` 不受监控开关影响。

未通过 `--config` 提供的选项使用插件声明的安全默认值。安装后可以通过 `/plugin` 的 Installed 页面进入配置流程；在已经打开的会话中安装或修改配置后，运行 `/reload-plugins` 即可重新加载。

使用 `--scope user` 时，Claude Code 会自动把选项保存在用户级设置中，而不是当前业务仓库。无需手动创建配置文件，`/gitlab-mr-guardian:setup` 也不会创建业务仓库配置文件。也可以完全通过 `/plugin` 界面添加 Marketplace、安装和管理插件。

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

即使启用了推荐配置，以下保护仍然有效：未完成审批、存在未解决 discussion、存在代码冲突、rebase 会清除审批时，插件不会自动推进。失败或取消的 CI 也只报告，不会自动重试。

### 配置是如何创建的

- **Marketplace 正式安装：**无需创建 JSON。安装命令中的 `--config`，或 `/plugin` 启用时的配置界面，会由 Claude Code 自动保存到用户级插件设置。
- **`/gitlab-mr-guardian:setup`：**检查 `glab` 认证、展示当前配置并执行只读状态检查；它不会创建或修改业务仓库中的文件。
- **监控开关：**`start` / `stop` 状态保存在 `${CLAUDE_PLUGIN_DATA}`，默认停止并跨 Claude 会话保留，不需要修改插件安装配置。
- **重新配置：**打开 `/plugin` → Installed → GitLab MR Guardian 的配置流程，修改后执行 `/reload-plugins`。Monitor 配置变化需要重新启动会话才能完全生效。
- **`--plugin-dir` 开发模式：**通常直接使用插件默认选项和 Git remote 推断主机。只有脱离 Claude Code 单独测试脚本时，才需要后文所述的用户级开发配置文件。

## 从本地 Marketplace 安装

发布前可以使用包含本 README 的插件目录进行完整安装测试：

```bash
claude plugin marketplace add /absolute/path/to/gitlab-mr-guardian
claude plugin install gitlab-mr-guardian@gitlab-mr-guardian-marketplace \
  --scope user \
  --config hostname=gitlab.example.com \
  --config poll_interval_seconds=3600 \
  --config auto_rebase=true \
  --config auto_merge=true
```

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

正式安装时，配置来自 `.claude-plugin/plugin.json` 中声明的 `userConfig`。Claude Code 将非敏感选项保存在用户级 `~/.claude/settings.json` 的插件配置区域，并通过环境变量传给插件进程。

- 插件源码中的 `config.example.json` 只是高级选项参考，不是运行时配置。
- 轮询状态和去重信息保存在 Claude 提供的 `${CLAUDE_PLUGIN_DATA}` 持久目录。
- 插件不会写入当前仓库的 `.claude/`、`.gitignore` 或其他业务文件。
- 显式传入的 `--config` / `MR_GUARDIAN_CONFIG` 仅用于高级调试和兼容场景。

## 使用

```text
/gitlab-mr-guardian:setup
/gitlab-mr-guardian:status
/gitlab-mr-guardian:check
/gitlab-mr-guardian:start
/gitlab-mr-guardian:stop
```

- `setup`：检查认证、说明当前配置并执行只读状态检查，不创建配置文件。
- `status`：只读查看 MR 当前状态。
- `check`：立即执行一次已配置的受保护推进流程。
- `start`：开始后台轮询；开关状态跨会话保存。
- `stop`：停止新的后台轮询，但保留所有手动命令。

后台监控默认停止。执行 `start` 后，当前活跃 Claude 会话会在几秒内开始轮询，默认每 1 小时检查一次，并且只在状态发生变化时通知 Claude。执行 `stop` 后不会开始新的自动周期；已经发出的单次 GitLab 请求可能会先完成。可以通过 `poll_interval_seconds` 自定义 60～86400 秒的间隔。

## 安全边界

- `auto_rebase` 和 `auto_merge` 必须在插件配置中显式启用。
- 默认只处理最近 90 天内有更新的 MR，避免误碰长期遗留的开放分支；设为 `0` 才会取消时间限制。
- Rebase 仅在 GitLab 返回 `need_rebase` 时执行，不会为了“保持新鲜”而反复创建提交。
- 只有已受监控或历史上存在成功 Pipeline 的 MR，才会在当前 Pipeline 为 `missing/skipped` 时补跑；`failed/canceled` 仍只报告。
- 如果项目启用了 `reset_approvals_on_push`，默认禁止自动 rebase，因为它可能清除已有审批。
- Auto-merge 请求携带当前 MR SHA，避免审查过的提交与被合并提交不一致。
- 插件不会自动重试失败 CI，也不会自动解决 Review 意见或代码冲突。

## 运行范围

执行 `start` 后，Claude Code 的插件 Monitor 只属于取得运行锁的当前交互式会话：轮询结果和 CI 告警只会进入这个会话，不会扩散、同步或广播到其他 Claude Code 会话。

如果同时打开多个启用了本插件的 Claude Code 会话，插件会通过进程锁避免对同一 GitLab 主机重复执行操作。获得锁的会话负责监控并接收通知；其他会话不会收到这些通知。负责监控的会话关闭后，仍处于运行状态的其他会话可以在下一次轮询时接管。

关闭所有 Claude Code 会话后，插件不会继续轮询。需要真正 7×24 小时监控时，应把同一套判断逻辑放进常驻服务、GitLab Scheduled Pipeline 或系统调度器，再把告警发送到邮件、Slack 等渠道。

## 许可证

本项目采用 [Apache License 2.0](LICENSE)。
