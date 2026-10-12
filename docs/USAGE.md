# 使用指南

先按 [README](../README.md) 安装完整 `project-supervisor/` 目录，再进入要监管的项目。Skill 的安装目录与业务项目的 Git 根目录是两处位置，不要在安装目录里初始化业务治理。

## 角色与授权

监管任务先读取事实、划定范围、安排执行并检查交付。已被指定为监管的窗口在整个生命周期内保持只读；“开始执行”“继续做”不会把它变为执行窗口。

写入由另一个真实 Codex task/thread 完成，executor 的任务 ID 必须与监管 ID 不同。每次写入前核对真实任务、目录、Git、实际模型与允许文件。普通问答或仅读取、评估 Skill，不会自动改变角色或创建锁与治理文件。

需要独立执行任务但当前工具无法创建时，监管提供可复制的执行指令，交给用户在另一个任务运行；不能由监管代做，也不能用当前会话的子代理替代。用户的明确要求和适用项目规则优先，已有授权内不重复增加流程性审批。

## 新项目

可以对监管窗口说：

```text
使用 $project-supervisor 监管这个新项目。先只读检查现有文件、Git、需求和验证方式，给出最小初始化范围；我说开始执行后，再安排独立 bootstrap executor。
```

监管确认边界后，bootstrap executor 使用现有初始化脚本建立 v3 active 锁，生成七份治理文件并填入已核实事实：

| 文件 | 保存什么 |
|---|---|
| `AGENTS.md` | 项目执行规则 |
| `docs/PRODUCT_BRIEF.md` | 产品目标与永久边界 |
| `docs/PROJECT_STATUS.md` | 当前事实与验证结论 |
| `docs/UPDATE_GOVERNANCE.md` | 风险、模型、验证与发布规则 |
| `docs/SUPERVISION_HANDOFF.md` | 当前结论与唯一下一任务 |
| `docs/ACTIVE_TASK.md` | 实时状态的静态指针 |
| `docs/BACKLOG.md` | 未进入当前范围的事项 |

executor 在锁仍 active 时验证并提交七文件，再 submit 等待监管验收。验收接受后，由同一 executor finish 转为空闲。模板或同名文件已经存在时不覆盖，先查明现状。

## 既有项目只读接管

```text
使用 $project-supervisor 只读接管当前项目。读取适用规则和必要治理文件，核对 Git 改动、提交与协调后端，报告当前状态、风险和唯一下一任务；保留已有用户改动。
```

首次接管读取完整必要项目资料；同一任务中资料未变时，只核对状态、Git 和相关变化。先用 status/doctor 识别后端：

- `project-supervisor-shared`：使用本 Skill 的 v3 流程。
- `external-repository-guard`：继续使用项目自己的占用与提交流程，不接管、不改写或迁移原守卫。
- `legacy-project-supervisor`：只有符合空闲、干净条件的旧 v1/v2 状态，才可由独立 executor 显式迁移。
- `missing` / `invalid`：报告缺失或不一致，不把失败检查当作初始化或修复授权。

## 开始执行与验收

范围明确后，说“开始执行”。监管派发一个独立 executor，列出具体结果、风险、模型、精确文件范围和必要验证。executor 在首次修改前 claim，只修改允许路径；一次只允许一个仓库修改任务。

常规流程为：`claim → 实现与验证 → 精确暂存并提交 → submit → 监管验收 → finish`。从提交到验收完成，锁持续保留；`awaiting_acceptance` 期间不能继续改文件或 HEAD，也不能由其他任务认领。

验收时核对实际提交、差异、验证输出、未运行项、剩余风险与回退方式。退回由原 executor resume 后修改；接受由原 executor finish。弃置任务的 abort 有基线与工作区前置条件，脚本不会替你覆盖或删除用户改动。v3 没有 release 命令，不采用先清锁再提交的顺序。

`docs/ACTIVE_TASK.md` 只是静态说明，编辑它不会合法认领或清除任务。实时状态要从脚本读取。

## 换窗口

项目事实通过治理文件、Git 提交和本机实时状态交接。新窗口不会自动获得旧聊天全文，也不能仅凭相同标题继承旧任务身份。

结束上一执行任务并完成验收后，可以在新监管窗口说：

```text
使用 $project-supervisor 接管此项目。先读取 AGENTS.md 和六份治理文档，再核对 Git 与实时状态；以文件和验证证据恢复当前结论，不依赖旧聊天。
```

若仍有 active 或 awaiting_acceptance，先查明原任务与未完成工作，不覆盖锁、不伪造空闲。交接文件只保留当前结论、唯一下一步和实际风险，历史由 Git 与已授权证据保存。

## 换电脑或独立 clone

Git 可以携带项目文件和提交，但不会携带 Git common dir 内的实时 SQLite 状态。共享同一 common dir 的 linked worktree 使用同一把锁；独立 clone、另一台电脑或安装目录不共享互斥。

迁移前，先确认源端任务已验收完成、状态 idle，并核对干净提交和受保护文件。不要复制 active SQLite/WAL，不要让两个独立副本同时写同一项目。

如果 clone 已含受 Git 跟踪的 v3 静态指针却没有数据库，当前脚本会报告 invalid。现有 migrate 仅支持符合条件的 v1/v2 到 v3，不是跨 clone 状态导入工具。保持只读，安排独立、可审计的状态重建或迁移任务；不能盲目 init/migrate、覆盖指针或宣称自动恢复。

脚本检查和模型分工见 [维护说明](MAINTENANCE.md)，完整约束见 [运行协议](../project-supervisor/references/operating-protocol.md)。
