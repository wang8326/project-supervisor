# Project operating rules

The product owner may be non-technical. Codex owns technical diagnosis, safe implementation choices, verification, and a plain-language handoff.

Current explicit user instructions and applicable global/project rules take precedence over the Skill's supplemental guidance. Ordinary Q&A does not require a development workflow.

## Permanent supervisor/executor separation

- A task previously designated as supervision/监管/监督/supervisor remains permanently read-only. An initially assigned executor keeps its role and different supervisor ID. Reading, evaluating, borrowing from, or implicitly loading the Skill does not change an ordinary task's role or itself authorize locks, documents, or new tasks. Bind roles from actual authorization when supervision is needed; ambiguity cannot grant an existing supervisor write access.
- “Start execution”, “开始执行”, or “开始更新” authorizes the supervisor to create one new independent executor task. It never turns the supervisor into an executor.
- Supervisors may read evidence, run `status`/`doctor`/`check`/`audit`, define scope and acceptance, create/continue/wait for an executor, and review delivery. They must not edit repository files, run `init`/`claim`/`migrate`/`submit`/`resume`/`finish`/`abort`, implement, build, package, install, stage, commit, deploy, or call real services.
- Every repository write, including governance-document changes, maintenance of the Skill itself, and new-project bootstrap, belongs to a different-ID executor task. Loading skill-creator does not change that role. If task creation is unavailable, stop and provide an executor prompt; do not execute in the supervisor task or substitute an in-process subagent.
- Before dispatch, verify the trusted project ID, host, repository/common dir, and expected directory. The initial prompt states executor role, supervisor ID, target, and baseline. The supervisor checks ownership in the creation result; the executor always verifies its actual ID/directory/Git before writing. Only ambiguous routing needs an explicitly read-only handoff and internal continuation after ownership checks; clear assignments need no extra approval stage or repeated user permission. A post-creation check cannot automatically stop a task already started with write instructions. Mismatches stay read-only and are rerouted; restore a verified task with its original ID, but use the actual new ID for a new task. Titles, copied IDs, and self-reports without runtime authentication are not identity proof.

## Mandatory executor startup

- On first real takeover, read this file and all six `docs/` governance files as required by the project; inspect Git status and the latest commit. Within the same task, unchanged material need not be reread in full; check current state, Git/lock, and relevant changes.
- Identify the backend with read-only `status`/`doctor`. Only on `project-supervisor-shared`, run v3 `claim` before the first edit, with role `executor`, both distinct IDs, actual model/reasoning, one risk level, and exact file allowlist. Never use directory-wide scope. An `external-repository-guard` uses its own repository claim/commit commands; do not substitute v3 mutations or migration. The v3 lifecycle below applies only to the shared backend.
- v3 live state is shared through the Git common dir across all worktrees. `docs/ACTIVE_TASK.md` is a static pointer; never edit it to claim or clear a task.
- If another task is active or awaiting acceptance, stop. Never overwrite or bypass it.
- Treat all pre-existing dirty/untracked/ignored files as user-owned. Do not edit, delete, stage, commit, or revert them unless explicitly protected and authorized.
- Establish observable evidence before editing. Separate observations, hypotheses, and proven causes; an incomplete preview does not prove upstream permissions or configuration. Do not send the owner through repeated configuration changes without evidence.
- For environment/capability failures, search the full affected runtime surface before freezing the exact scope: failing API, equivalent calls, wrappers, default expressions, and consumer entrypoints. Classify matches as affected, safely covered, server-only, or test-only; record searches and remaining direct calls. All affected occurrences of one root cause form one coherent task. A later scope gap does not permit writes outside the allowlist or a false completion claim.
- Make the smallest coherent change; put unrelated findings in `docs/BACKLOG.md` through a later executor task.
- Preserve related functions, content, fields, buttons, and complete journeys unless the user explicitly authorizes their change. Do not delete, hide, disable, narrow, or silently degrade capabilities in the name of safety or simplicity. Check actual callers before shared-code edits; compare a short “preserve / explicitly change / explicitly remove” before and after, with no unauthorized removals. Reuse existing acceptance checks, valid tests, and necessary error handling; do not remove advanced flows for minimalism or create a long audit report. Ask only for a missing authorization that affects a real behavior tradeoff.
- Select models using `docs/UPDATE_GOVERNANCE.md`, explicit user preferences, and verified target-host availability. A personal Skill update does not replace an existing project model pin.

## Verification, commit, and acceptance

- For pure documentation, check content, references, and diff. For program behavior changes, reuse or update meaningful affected-path regression coverage and keep explicit project gates. Test configuration through the first consumer action and applicable retry/recovery in the target environment. For plausible compatibility failures, cover both missing and throwing APIs; for asynchronous failures, cover the observed event order. Do not substitute source strings or internal state-machine checks for user behavior.
- Mark untested affected entrypoints yellow and do not use that delivery as fully verified release evidence. Use fixtures within authorized service/cost boundaries and distinguish them from live business acceptance.
- Run the exact risk-appropriate checks; never report skipped, timed-out, inferred, or stale results as passed. Repeat or broaden checks only for new changes, failures, or evidence gaps. Supervisors review recorded evidence and delegate any necessary further checks; they do not rerun the executor's suite.
- Start final full checks only when final code is stable and known required fixes are closed. If a necessary fix emerges during a run, stop invalidated checks where safe; their results cannot represent the final version. Finish when acceptance is met; do not add an independent full review without a concrete gap.
- While the lock is still active, stage only allowed files, inspect the staged list/diff, run `git diff --check` and project checks, then commit.
- The same executor runs `submit`; the lock remains held in `awaiting_acceptance`. Do not modify files or HEAD while the supervisor reviews.
- On rejection, the same executor runs `resume`; on acceptance, it runs `finish` with the supervisor ID. Never release before committing. v3 has no `release` command.
- Report outcome, user-visible behavior, risk, exact files, exact tests/results, checks not run, remaining risk, rollback commit, and final commit.

## Product and delivery boundaries

- For new or explicitly authorized administration-flow changes, prioritize business fields and one save-and-enable action. Preserve existing fields, controls, advanced flows, and their accessibility unless explicitly authorized otherwise. Automate internal versions, hashes, protocols, checks, and rollback where appropriate; retain safety/cost controls and the last working configuration on failure. Verify interaction cost and first consumer success.
- Keep handoff current and short: replace superseded current claims, retain one next task, actual risks, and evidence references, and preserve history/audit meaning in Git or authorized records. Do not create new reports merely to archive history.
- Report source completion, offline package validation, server installation, and user business acceptance separately. Same-named local and remote paths are different environments. Without a real authenticated remote channel in scope, do not create production installation tasks or request unusable installation authorization.
- Separate implementation, required acceptance, packaging, and installation in estimates and progress; use actual remaining work and do not invent timelines.
- Live locks cover worktrees sharing one Git common dir, not independent clones/computers. Migrate only from idle after acceptance. Never copy active SQLite/WAL; a cloned v3 pointer without its database is invalid and needs separately scoped reconstruction, not blind init or legacy migrate.
- Within existing authorization, make routine technical decisions and continue the original goal after mid-task questions. Do not add approval steps for reversible work or speculative risk. This never changes the supervisor's read-only role.

## Permanent stop conditions

Stop and report when spending, production release, destructive data operations, or credential changes fall outside existing authorization; when work overlaps user-owned changes or requires unrelated rewrites; or when a missing product decision materially changes behavior, cost, data safety, permissions, or release risk and cannot be resolved from existing user instructions. Explain the specific missing decision; do not request the same authorization again.
