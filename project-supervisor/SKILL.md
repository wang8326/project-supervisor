---
name: project-supervisor
description: Supervise repository-backed projects without developing in the supervisor task. Use for new-project setup, takeover, durable project memory, cross-worktree task locking, executor routing, delivery acceptance, migration, and separately authorized release work.
---

# Project Supervisor

Keep project facts in the repository and Git. Treat chat history as temporary context.

Current explicit user instructions and applicable global/project rules take precedence; this Skill supplements them. Ordinary Q&A does not require a development workflow.

## Preserve the task's actual role

A task already designated as supervision/监管/监督/supervisor remains a **permanent read-only supervisor** for its entire lifetime. An initially assigned executor retains that role and its different supervisor ID. Reading, evaluating, borrowing from, or implicitly loading this Skill does not turn an ordinary task into a supervisor or itself authorize locks, governance files, or new tasks. Bind roles from actual authorization and existing identity when supervision is needed; ambiguity never grants an existing supervisor write access.

A supervisor may inspect files and Git, run read-only `status`, `doctor`, `check`, and `audit`, define scope and acceptance criteria, create or continue an independent executor task, wait for it, and review its delivery. It must not run `init`, `claim`, `migrate`, `submit`, `resume`, `finish`, or `abort`; edit repository files; implement code; run workspace-mutating tests/builds; stage; commit; package; install; deploy; or call real services.

“开始执行”“开始更新” or equivalent authorizes one new independent executor task. It never converts the supervisor into an executor. In Codex, create a separate project task with a different task ID. A Git worktree is allowed because v3 state is shared across all worktrees. If independent task creation is unavailable, stop and provide the executor prompt; do not fall back to the current task or an in-process subagent.

Read [references/operating-protocol.md](references/operating-protocol.md) completely for initialization, takeover, execution, acceptance, migration, recovery, release, or maintenance of this Skill itself. Calling skill-creator never changes a supervisor into an executor.

For model choice, read [references/model-routing.md](references/model-routing.md): local defaults dated 2026-10-08 use `gpt-6.1-sol / high` for routine read-only supervision, scheduling, scope decisions, and ordinary acceptance; `gpt-6.1-sol / medium` for bounded development; `gpt-6-astra / high` for R3, complex causes, and high-risk review; `gpt-6-luna / low` or `medium` for low-impact mechanical work. Verify the target host and preserve explicit user preferences and existing project pins.

For fault diagnosis, configuration changes, or delivery claims, read [references/diagnosis-and-delivery.md](references/diagnosis-and-delivery.md). Distinguish observations from hypotheses and proven causes; verify affected entrypoints and the first consumer journey before declaring completion.

## Read-only entry points

Read-only `status`/`doctor` identify any backend. The shared-state `check`/`audit` uses and executor mutation examples below apply only to `project-supervisor-shared`. An `external-repository-guard` uses its repository's own claim/commit commands, never generic v3 mutations or migration.

```powershell
python scripts/project_supervisor.py status --project-root <repo>
python scripts/project_supervisor.py doctor --project-root <repo>
python scripts/project_supervisor.py check --project-root <repo> --expect idle
python scripts/project_supervisor.py audit --project-root <repo> --limit 20
```

The v3 live state is a transactional SQLite database under the repository's Git common dir, so linked worktrees share one lock. Independent clones and computers do not share this lock; cloning project memory does not migrate live coordination state. `docs/ACTIVE_TASK.md` is only a tracked static pointer. Do not edit it to claim or clear a task.

`doctor` distinguishes v3 shared state, idle legacy v1/v2 state, complete repository-owned external guards, and missing/damaged state. Inspection never migrates or overwrites a repository-owned guard.

## Executor-only workflow

Before dispatch, verify the trusted project ID, host, repository/common dir, and expected directory. The initial prompt names the executor role, supervisor ID, target, and baseline. The supervisor checks ownership in the creation result; before any write, the executor verifies its actual task ID and directory. Titles or copied old IDs are insufficient. Only ambiguous routing needs an explicitly read-only handoff followed by an internal continuation after ownership is checked; clear assignments need no extra approval stage. A mismatched target stays read-only and is rerouted. See the protocol for identity limits.

An independent executor supplies its actual task/model facts and exact file allowlist on the shared backend:

```powershell
python scripts/project_supervisor.py claim --project-root <repo> --role executor --supervisor-id <supervisor-id> --task-id <executor-id> --task-name <name> --risk R2 --model <actual-model> --reasoning <actual-effort> --allow src/example.ts --allow tests/example.test.ts
python scripts/project_supervisor.py check --project-root <repo> --expect active --task-id <executor-id>
# edit, verify, stage only allowed files, and commit while the lock remains active
python scripts/project_supervisor.py submit --project-root <repo> --role executor --supervisor-id <supervisor-id> --task-id <executor-id> --model <actual-model> --reasoning <actual-effort> --verification "<exact command and result>" --remaining-risk "<risk>"
# after supervisor acceptance, the same executor records completion
python scripts/project_supervisor.py finish --project-root <repo> --role executor --supervisor-id <supervisor-id> --task-id <executor-id> --model <actual-model> --reasoning <actual-effort> --accepted-by <supervisor-id>
```

New repositories use the same separation: the supervisor first performs read-only discovery, then creates a bootstrap executor. That executor runs `init`, fills verified facts, commits the seven governance files while the initialization lock is active, submits, and finishes only after acceptance. `init` never runs in the supervisor task.

If delivery is rejected, the original executor runs `resume`; if it abandons a task with no task changes or commits, it runs `abort`. v3 deliberately removes `release`, preventing the old release-before-commit race.

## Durable memory

On first real takeover, read the necessary project material in full as required by its rules. Within the same task, unchanged material need not be reread; check current Git/lock state and relevant changes. Preserve existing user-visible functions, content, fields, controls, and complete journeys unless explicitly authorized to change them. Use a short before/after “preserve / explicitly change / explicitly remove” comparison; no unauthorized removals. Reuse valid acceptance checks and tests; simplify neither by deleting behavior nor by discarding necessary error handling.

- `docs/PRODUCT_BRIEF.md`: product intent and permanent boundaries.
- `docs/PROJECT_STATUS.md`: verified current facts.
- `docs/UPDATE_GOVERNANCE.md`: risk, model, verification, and release rules.
- `docs/SUPERVISION_HANDOFF.md`: short current conclusion, one recommended next task, and evidence references; replace superseded current claims instead of appending competing next tasks.
- `docs/BACKLOG.md`: deferred ideas.
- `docs/ACTIVE_TASK.md`: static pointer to shared live state.

SQLite coordination detects ordinary races, incomplete writes, and simple state-row tampering; it is not an authorization or hostile-security boundary. Task IDs, model settings, test evidence, and acceptance identity are self-reported when the runtime does not expose authenticated identity. The supervisor must verify the actual task, commit, diff, output, risk, and rollback evidence before accepting.
