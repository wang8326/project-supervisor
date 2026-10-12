# Project Supervisor

让 Codex 按项目文件和 Git 监管开发：监管窗口负责范围、派发和验收，另一个独立执行任务负责修改与提交。项目事实留在仓库里，换窗口时可以重新接管。

本仓库提供完整的 `project-supervisor` Skill、v3 协调脚本、原有测试与项目模板，以及中文使用说明。它适用于需要持续监管的 Git 项目；普通问答或仅读取 Skill 不会自动建立监管流程。

## 安装

在支持本地 skills 的 Codex 环境中，可以直接说：

```text
$skill-installer 从 https://github.com/wang8326/project-supervisor 安装目录 project-supervisor。
```

也可以下载或克隆本仓库，把其中整个 `project-supervisor/` 目录放到用户 skills 目录，例如 `~/.agents/skills/project-supervisor/`。必须保留 `scripts/`、`references/`、`assets/` 和 `agents/`，不能只复制 `SKILL.md`。

安装路径依据 2026-10-12 核对的 [OpenAI 官方 skills 文档](https://learn.chatgpt.com/docs/build-skills)：当前用户级位置是 `~/.agents/skills`，项目级位置是 `.agents/skills`。已有环境也可能使用已配置的 `~/.codex/skills`；以安装器返回位置和当前运行环境实际识别结果为准。安装后确认 `project-supervisor` 出现在可用 skills 中；若未出现，可重启 Codex 后再检查。

使用协调脚本需要可运行该脚本的 Python 3 和 Git。安装 Skill 不会自动初始化任何业务项目，也不会自动建立后台监控。

## 一句话开始

在目标项目的监管窗口中输入：

```text
使用 $project-supervisor 监管当前项目。先只读核对项目规则、Git 和协调状态，说明当前结论与唯一下一任务；需要修改时安排不同任务 ID 的独立 executor。
```

阅读结论后，用“开始执行”推进已明确的任务。监管窗口保持只读，执行与验收流程见 [使用指南](docs/USAGE.md)。

## 仓库目录

```text
README.md
docs/
  USAGE.md                 新项目、接管、执行、验收和迁移
  MAINTENANCE.md           检查、维护、发布与模型分工
project-supervisor/
  SKILL.md                 技能入口
  agents/openai.yaml       界面元数据
  scripts/                 协调脚本与行为测试
  references/              运行协议、诊断与模型路由
  assets/project-template/ 七份项目治理模板
```

窗口之间通过项目文件和 Git 共享事实，不会自动同步聊天。v3 锁仅在共享同一 Git common dir 的 worktree 之间互斥，独立 clone 和其他电脑不共享这把锁。详细限制见 [使用指南](docs/USAGE.md)；修改或发布本 Skill 前请阅读 [维护说明](docs/MAINTENANCE.md)。
