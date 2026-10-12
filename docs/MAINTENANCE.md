# 维护与验收

本 Skill 的入口、脚本、测试、引用和模板共同组成完整资源。维护时保留原有能力与有效测试，只改当前需求涉及的内容。完整流程以 [SKILL.md](../project-supervisor/SKILL.md) 和 [运行协议](../project-supervisor/references/operating-protocol.md) 为准。

## 只读检查

下面命令从本仓库根目录运行，把 `<目标项目根目录>` 替换为实际 Git checkout 根目录。若从其他位置运行，使用 Skill 安装位置中的脚本路径。

```text
python -B project-supervisor/scripts/project_supervisor.py status --project-root "<目标项目根目录>"
python -B project-supervisor/scripts/project_supervisor.py doctor --project-root "<目标项目根目录>"
```

status/doctor 用于识别所有后端；只有确认是 `project-supervisor-shared` 时，再按实际预期状态使用共享态检查。例如项目应当空闲时：

```text
python -B project-supervisor/scripts/project_supervisor.py check --project-root "<目标项目根目录>" --expect idle
python -B project-supervisor/scripts/project_supervisor.py audit --project-root "<目标项目根目录>" --limit 20
```

活动任务使用 `--expect active --task-id <实际任务ID>`；待验收任务使用 `--expect awaiting_acceptance`，并核对所属任务。不要为了让检查通过而改写静态指针或状态数据库。外部 guard 沿用项目自己的命令。

## 修改与发布

已指定监管的任务始终只读，Skill 本身的维护也由不同 ID 的独立 executor 完成。调用 skill-creator 不会改变监管身份。安装目录没有 Git/治理时，先按协议建立或复用隔离维护副本，核对来源、备份和精确范围；不要直接在安装目录 git init。

修改前确认原始内容、既有用户改动和调用者；保留未要求改变的功能、错误处理与有效测试。在共享后端上按 `claim → 修改/验证/提交 → submit → 验收 → finish` 执行，始终保持锁到验收结束。回写安装目录前核对漂移；遇到他人改动停止回写并报告。

公开上传或生产发布需要明确的发布授权和独立 executor，普通开发授权不能代替。发布前核实目标账号、仓库、公开范围、稳定提交、必要备份与回退方式，只上传审查过的文件。不要把私有治理根、维护历史、SQLite 状态、内部身份、凭据或日志混入公开内容。发布前若远端 HEAD 或用户内容变化，先查明差异，不强推或覆盖。

源码完成、验证通过、远端上传和实际使用验收分别报告；只完成本地准备时不声称已经发布。`.gitignore` 不能替代文件白名单、内容审查及远端核验。

## 按影响验证

- 纯文档检查内容、引用、范围和 `git diff --check` / `git diff --cached --check`。
- 修改脚本行为时，复用相关行为回归，保留项目明确要求的门禁；失败、跳过、超时和未运行都如实说明。
- 重新分发未修改的 Skill 时，核对完整文件清单和原始字节，防止复制缺失或换行转换；按发布要求检查敏感内容及最终远端文件。
- 使用官方 skill-creator 的 `scripts/quick_validate.py <技能目录>` 验证技能结构；这不等于业务行为已通过。

本仓库现有行为测试可从根目录运行：

```text
python -B -m unittest discover -s project-supervisor/scripts -p test_project_supervisor.py -v
```

测试在临时仓库中覆盖角色隔离、bootstrap、共享 worktree 互斥与竞争、精确范围、受保护内容、提交/验收、完整性、只读检查、旧版迁移和外部 guard 等行为。需要 Git 和可运行脚本的 Python 环境；测试结果不能替代实际远端发布验收。

最终检查在内容稳定后执行，通过后仅在相关变更、失败或具体疑点出现时补验。监管读取实际输出和差异，无依据不重跑整套检查。

## 模型分工

以下是 Skill 内 2026-10-08 的本地默认策略；不是官方强制分工，也没有独立 A/B 性能证明。

| 工作 | 模型 | 推理 |
|---|---|---|
| 日常只读监管、排期、范围和普通验收 | `gpt-6.1-sol` | `high` |
| 范围明确的普通开发 | `gpt-6.1-sol` | `medium` |
| R3、复杂根因和高风险审查 | `gpt-6-astra` | `high` |
| 低影响机械调整 | `gpt-6-luna` | `low` / `medium` |

用户明确偏好和既有项目 pin 优先。派发时核对目标 host 可用性，执行时记录实际 model/reasoning；无法核实就说明未知，不悄悄换模型或自动使用 Max/Ultra。个人 Skill 更新不自动覆盖项目固定模型。详细依据和边界见 [模型路由](../project-supervisor/references/model-routing.md)。

## 支持边界

SQLite 协调只保护共享同一 Git common dir 的 worktree，不构成跨电脑分布式锁或抵御恶意参与者的安全边界。运行时不提供认证身份时，任务 ID、模型和验收字段仍有自报限制，需要核对实际任务与证据。

安装 Skill 不会自动同步聊天、恢复独立 clone 的锁或迁移业务数据。缺数据库的 v3 clone 应先只读诊断，再安排可审计重建；不能盲目 init/migrate 或复制活跃 SQLite/WAL。具体接管与迁移方法见 [使用指南](USAGE.md)。
