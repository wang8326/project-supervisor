#!/usr/bin/env python3
"""Black-box behavior tests for project_supervisor.py v3."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("project_supervisor.py")
SUPERVISOR_ID = "supervisor-window-001"
EXECUTOR_ID = "executor-task-002"
MODEL = "gpt-5.6-sol"
REASONING = "high"


class ProjectSupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="project-supervisor-v3-")
        self.root = Path(self.temporary.name) / "含 中文 空格"
        self.root.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Skill Test")
        self.git("config", "user.email", "skill-test@example.invalid")
        (self.root / "seed.txt").write_text("seed\n", encoding="utf-8")
        (self.root / ".gitignore").write_text(".env*\n", encoding="utf-8")
        self.git("add", "seed.txt", ".gitignore")
        self.git("commit", "-m", "initial")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def git(self, *args: str, root: Path | None = None) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args], cwd=root or self.root, capture_output=True, text=True,
            encoding="utf-8", check=False,
        )
        if result.returncode != 0:
            self.fail(result.stderr)
        return result

    def environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment["PYTHONUTF8"] = "1"
        return environment

    def command(self, *args: str, expected: int = 0, root: Path | None = None) -> subprocess.CompletedProcess[str]:
        checkout = root or self.root
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args], cwd=checkout, capture_output=True, text=True,
            encoding="utf-8", env=self.environment(), check=False,
        )
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result

    def identity(self, command: str, *, task_id: str = EXECUTOR_ID,
                 role: str = "executor", root: Path | None = None) -> list[str]:
        return [
            command, "--project-root", str(root or self.root), "--role", role,
            "--supervisor-id", SUPERVISOR_ID, "--task-id", task_id,
            "--model", MODEL, "--reasoning", REASONING,
        ]

    def initialize_active(self, *, role: str = "executor") -> subprocess.CompletedProcess[str]:
        return self.command(
            *self.identity("init", role=role), "--project-name", "示例项目", "--risk", "R2",
            expected=0 if role == "executor" else 2,
        )

    def submit(self, *, task_id: str = EXECUTOR_ID, verification: str = "tests passed") -> None:
        self.command(
            *self.identity("submit", task_id=task_id), "--verification", verification,
            "--remaining-risk", "none known",
        )

    def finish(self, *, task_id: str = EXECUTOR_ID) -> None:
        self.command(*self.identity("finish", task_id=task_id), "--accepted-by", SUPERVISOR_ID)

    def complete_initialization(self) -> None:
        self.initialize_active()
        self.git("add", "AGENTS.md", "docs")
        self.git("commit", "-m", "initialize supervision v3")
        self.submit(verification="project-supervisor tests passed")
        self.finish()

    def claim(self, *allowed: str, task_id: str = EXECUTOR_ID,
              root: Path | None = None, expected: int = 0,
              role: str = "executor", protect: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
        arguments = [
            *self.identity("claim", task_id=task_id, role=role, root=root),
            "--task-name", "实现示例功能", "--risk", "R2",
        ]
        for path in allowed:
            arguments.extend(("--allow", path))
        for path in protect:
            arguments.extend(("--protect", path))
        return self.command(*arguments, expected=expected, root=root)

    def database_path(self, root: Path | None = None) -> Path:
        checkout = root or self.root
        common = self.git("rev-parse", "--git-common-dir", root=checkout).stdout.strip()
        common_path = Path(common)
        if not common_path.is_absolute():
            common_path = checkout / common_path
        return common_path.resolve() / "project-supervisor" / "state-v3.sqlite3"

    def remove_database(self) -> None:
        database = self.database_path()
        for suffix in ("", "-wal", "-shm"):
            Path(str(database) + suffix).unlink(missing_ok=True)
        if database.parent.exists():
            shutil.rmtree(database.parent)

    def test_bootstrap_is_executor_only_and_stays_locked_until_acceptance(self) -> None:
        denied = self.initialize_active(role="supervisor")
        self.assertIn("终身只读", denied.stderr)
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertFalse(self.database_path().exists())

        self.initialize_active()
        status = json.loads(self.command("status", "--project-root", str(self.root)).stdout)
        self.assertEqual("active", status["lock_backend"]["status"])
        self.assertEqual("project-supervisor-shared", status["lock_backend"]["kind"])
        self.assertEqual(EXECUTOR_ID, status["lock_backend"]["state"]["executor_id"])

        self.git("add", "AGENTS.md", "docs")
        self.git("commit", "-m", "initialize supervision v3")
        self.submit()
        awaiting = json.loads(self.command("status", "--project-root", str(self.root)).stdout)
        self.assertEqual("awaiting_acceptance", awaiting["lock_backend"]["status"])
        blocked = self.claim("src/other.txt", task_id="executor-other", expected=2)
        self.assertIn("已有任务占用", blocked.stderr)

        self.finish()
        idle = json.loads(self.command("status", "--project-root", str(self.root)).stdout)
        self.assertEqual("idle", idle["lock_backend"]["status"])
        self.assertEqual("completed", idle["lock_backend"]["state"]["last_receipt"]["outcome"])
        self.command("check", "--project-root", str(self.root), "--expect", "idle")
        audit = json.loads(self.command("audit", "--project-root", str(self.root)).stdout)
        self.assertEqual("completed", audit["events"][0]["event_type"])

    def test_interrupted_bootstrap_can_resume_before_any_file_survives(self) -> None:
        self.initialize_active()
        for relative in (
            "AGENTS.md", "docs/PRODUCT_BRIEF.md", "docs/PROJECT_STATUS.md",
            "docs/UPDATE_GOVERNANCE.md", "docs/SUPERVISION_HANDOFF.md",
            "docs/ACTIVE_TASK.md", "docs/BACKLOG.md",
        ):
            (self.root / relative).unlink()
        resumed = self.initialize_active()
        self.assertIn("保持共享锁为 active", resumed.stdout)
        self.assertTrue((self.root / "docs" / "ACTIVE_TASK.md").is_file())
        audit = json.loads(self.command("audit", "--project-root", str(self.root)).stdout)
        self.assertEqual("init_resumed", audit["events"][0]["event_type"])

    def test_shared_lock_is_atomic_across_worktrees(self) -> None:
        self.complete_initialization()
        linked = Path(self.temporary.name) / "linked worktree"
        self.git("worktree", "add", "-b", "linked-test", str(linked))

        self.claim("src/one.txt", task_id="executor-main")
        result = self.claim("src/two.txt", task_id="executor-linked", root=linked, expected=2)
        self.assertIn("已有任务占用", result.stderr)
        main_status = json.loads(self.command("status", "--project-root", str(self.root)).stdout)
        linked_status = json.loads(self.command("status", "--project-root", str(linked), root=linked).stdout)
        self.assertEqual(main_status["lock_backend"]["database"], linked_status["lock_backend"]["database"])
        self.assertEqual("executor-main", linked_status["lock_backend"]["state"]["task_id"])

    def test_simultaneous_claims_have_exactly_one_winner(self) -> None:
        self.complete_initialization()
        commands: list[list[str]] = []
        for task_id in ("executor-race-a", "executor-race-b"):
            commands.append([
                sys.executable, str(SCRIPT), *self.identity("claim", task_id=task_id),
                "--task-name", task_id, "--risk", "R1", "--allow", "src/race.txt",
            ])
        processes = [
            subprocess.Popen(command, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding="utf-8", env=self.environment())
            for command in commands
        ]
        results = [process.communicate(timeout=20) + (process.returncode,) for process in processes]
        self.assertEqual([0, 2], sorted(item[2] for item in results), results)
        self.assertFalse(any("Traceback" in (item[0] + item[1]) for item in results), results)

    def test_exact_scope_checks_uncommitted_and_committed_changes(self) -> None:
        self.complete_initialization()
        (self.root / "src").mkdir()
        broad = self.claim("src", expected=2)
        self.assertIn("精确文件", broad.stderr)
        for unsafe in ("docs/", "**", ".", "C:/work/file.txt", "../file.txt", "src/name:stream"):
            with self.subTest(unsafe=unsafe):
                result = self.claim(unsafe, expected=2)
                self.assertRegex(result.stderr, "精确文件|glob|根目录|安全的仓库相对路径")

        self.claim("src/allowed.txt")
        (self.root / "src" / "allowed.txt").write_text("allowed\n", encoding="utf-8")
        (self.root / "outside.txt").write_text("outside\n", encoding="utf-8")
        dirty = self.command("check", "--project-root", str(self.root), "--expect", "active", expected=2)
        self.assertIn("范围外修改", dirty.stderr)
        self.git("add", "src/allowed.txt", "outside.txt")
        self.git("commit", "-m", "attempt out-of-scope commit")
        committed = self.command("check", "--project-root", str(self.root), "--expect", "active", expected=2)
        self.assertIn("提交范围含未声明路径", committed.stderr)

    def test_protects_preexisting_dirty_ignored_secrets_and_git_controls(self) -> None:
        self.complete_initialization()
        owner = self.root / "owner-note.txt"
        owner.write_text("owner\n", encoding="utf-8")
        self.claim("src/allowed.txt")

        owner.write_text("changed\n", encoding="utf-8")
        result = self.command("check", "--project-root", str(self.root), "--expect", "active", expected=2)
        self.assertIn("受保护路径内容发生变化", result.stderr)
        owner.write_text("owner\n", encoding="utf-8")

        (self.root / ".env.staging").write_text("TOKEN=secret\n", encoding="utf-8")
        result = self.command("check", "--project-root", str(self.root), "--expect", "active", expected=2)
        self.assertIn("新增敏感环境文件", result.stderr)
        (self.root / ".env.staging").unlink()

        self.git("config", "alias.unsafe", "status")
        result = self.command("check", "--project-root", str(self.root), "--expect", "active", expected=2)
        self.assertIn("Git config", result.stderr)

    def test_staged_user_file_is_rejected_before_claim(self) -> None:
        self.complete_initialization()
        (self.root / "owner-note.txt").write_text("owner\n", encoding="utf-8")
        self.git("add", "owner-note.txt")
        result = self.claim("src/allowed.txt", expected=2)
        self.assertIn("已暂存文件", result.stderr)

    def test_submission_requires_clean_commit_and_original_executor(self) -> None:
        self.complete_initialization()
        self.claim("src/allowed.txt")
        (self.root / "src").mkdir()
        (self.root / "src" / "allowed.txt").write_text("feature\n", encoding="utf-8")
        uncommitted = self.command(
            *self.identity("submit"), "--verification", "tests passed", "--remaining-risk", "none",
            expected=2,
        )
        self.assertIn("尚未全部提交", uncommitted.stderr)
        self.git("add", "src/allowed.txt")
        self.git("commit", "-m", "implement feature")
        wrong = self.command(
            *self.identity("submit", task_id="executor-other"), "--verification", "tests passed",
            "--remaining-risk", "none", expected=2,
        )
        self.assertIn("不匹配", wrong.stderr)
        self.submit()
        duplicate = self.command(
            *self.identity("submit"), "--verification", "again", "--remaining-risk", "none", expected=2,
        )
        self.assertIn("只有 active executor", duplicate.stderr)
        (self.root / "src" / "allowed.txt").write_text("post acceptance drift\n", encoding="utf-8")
        finish = self.command(*self.identity("finish"), "--accepted-by", SUPERVISOR_ID, expected=2)
        self.assertIn("finish 前检查失败", finish.stderr)

    def test_database_tamper_is_detected(self) -> None:
        self.complete_initialization()
        database = self.database_path()
        connection = sqlite3.connect(database)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE events SET actor_id = 'forged' WHERE event_id = 1")
            connection.rollback()
            connection.execute(
                "UPDATE state SET state_json = ? WHERE singleton = 1",
                (json.dumps({"version": 3, "status": "idle", "last_receipt": {"forged": True}}),),
            )
            connection.commit()
        finally:
            connection.close()
        result = json.loads(self.command("status", "--project-root", str(self.root)).stdout)
        self.assertEqual("invalid", result["lock_backend"]["kind"])
        self.assertIn("最后审计事件不一致", result["lock_backend"]["error"])
        blocked = self.claim("src/blocked.txt", expected=2)
        self.assertIn("审计事件不一致", blocked.stderr)

    def test_missing_database_and_modified_pointer_are_explicitly_invalid(self) -> None:
        self.complete_initialization()
        pointer = self.root / "docs" / "ACTIVE_TASK.md"
        pointer.write_text(pointer.read_text(encoding="utf-8") + "\nmanual edit\n", encoding="utf-8")
        modified = json.loads(self.command("doctor", "--project-root", str(self.root)).stdout)
        self.assertFalse(modified["doctor"]["readonly_takeover_supported"])
        self.assertIn("静态指针", modified["lock_backend"]["error"])

        self.git("restore", "docs/ACTIVE_TASK.md")
        self.remove_database()
        missing = json.loads(self.command("doctor", "--project-root", str(self.root)).stdout)
        self.assertEqual("invalid", missing["lock_backend"]["kind"])
        self.assertIn("数据库缺失", missing["lock_backend"]["error"])

    def test_status_doctor_and_audit_are_read_only(self) -> None:
        self.complete_initialization()
        pointer = self.root / "docs" / "ACTIVE_TASK.md"
        database = self.database_path()
        state_dir = database.parent
        before = (
            pointer.read_bytes(), pointer.stat().st_mtime_ns, database.stat().st_mtime_ns,
            sorted(path.name for path in state_dir.iterdir()),
        )
        status = json.loads(self.command("status", "--project-root", str(self.root)).stdout)
        doctor = json.loads(self.command("doctor", "--project-root", str(self.root)).stdout)
        self.command("audit", "--project-root", str(self.root))
        self.assertTrue(status["readonly"])
        self.assertTrue(doctor["doctor"]["readonly_takeover_supported"])
        self.assertEqual(before, (
            pointer.read_bytes(), pointer.stat().st_mtime_ns, database.stat().st_mtime_ns,
            sorted(path.name for path in state_dir.iterdir()),
        ))

    def test_idle_legacy_v2_requires_explicit_executor_migration(self) -> None:
        self.complete_initialization()
        self.remove_database()
        pointer = self.root / "docs" / "ACTIVE_TASK.md"
        pointer.write_text(
            "# 当前任务占用\n\n<!-- PROJECT_SUPERVISOR_STATE\n"
            '{"version":2,"status":"idle","task_id":null,"allowed_paths":[]}\n'
            "PROJECT_SUPERVISOR_STATE -->\n",
            encoding="utf-8",
        )
        self.git("add", "docs/ACTIVE_TASK.md")
        self.git("commit", "-m", "legacy v2 pointer")
        status = json.loads(self.command("doctor", "--project-root", str(self.root)).stdout)
        self.assertEqual("legacy-project-supervisor", status["lock_backend"]["kind"])

        supervisor = self.command(*self.identity("migrate", role="supervisor"), "--risk", "R1", expected=2)
        self.assertIn("终身只读", supervisor.stderr)
        self.command(*self.identity("migrate"), "--risk", "R1")
        self.git("add", "docs/ACTIVE_TASK.md")
        self.git("commit", "-m", "migrate pointer to v3")
        self.submit()
        self.finish()
        migrated = json.loads(self.command("status", "--project-root", str(self.root)).stdout)
        self.assertEqual("git-common-dir-sqlite-v3", migrated["lock_backend"]["format"])

    def test_external_guard_needs_complete_signature_and_is_never_overwritten(self) -> None:
        self.complete_initialization()
        self.remove_database()
        pointer = self.root / "docs" / "ACTIVE_TASK.md"
        pointer.write_text("# 普通项目说明\n\n状态：空闲\n\n- 任务名称：无\n", encoding="utf-8")
        incomplete = json.loads(self.command("doctor", "--project-root", str(self.root)).stdout)
        self.assertEqual("invalid", incomplete["lock_backend"]["kind"])

        pointer.write_text(
            "# 仓库自有守卫\n\n状态：空闲\n\n"
            "- 任务名称：无\n- 风险等级：无\n- 执行窗口：无\n"
            "- 允许修改路径：无\n- 既有用户路径：无\n",
            encoding="utf-8",
        )
        original = pointer.read_bytes()
        external = json.loads(self.command("doctor", "--project-root", str(self.root)).stdout)
        self.assertEqual("external-repository-guard", external["lock_backend"]["kind"])
        claim = self.claim("src/file.txt", expected=2)
        self.assertIn("v3 静态指针", claim.stderr)
        self.assertEqual(original, pointer.read_bytes())

    def test_release_is_removed(self) -> None:
        result = self.command("release", expected=2)
        self.assertIn("已移除 release", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
