# 当前任务状态指针

<!-- PROJECT_SUPERVISOR_SHARED_STATE -->

实时状态不存放在本文件中。`project-supervisor` v3 将锁、待验收状态和审计事件保存在当前 Git 仓库所有 worktree 共享的 common dir 中。

- 本文件是静态、受 Git 跟踪的说明，不得通过编辑本文件认领或解除任务。
- 运行 `project_supervisor.py status --project-root <当前 checkout 根目录>` 查看共享状态和实际数据库路径。
- supervisor 任务永久只读；只有不同 ID 的 executor 可以运行 `init`、`claim`、`migrate`、`submit`、`resume`、`finish` 或 `abort`。
