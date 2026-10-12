#!/usr/bin/env python3
"""Initialize, inspect, and guard repository-backed Codex supervision state."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path, PurePosixPath


STATE_VERSION = 3
CONTROL_PATH = "docs/ACTIVE_TASK.md"
SHARED_DIR_NAME = "project-supervisor"
DATABASE_NAME = "state-v3.sqlite3"
POINTER_MARKER = "PROJECT_SUPERVISOR_SHARED_STATE"
LEGACY_STATE_START = "<!-- PROJECT_SUPERVISOR_STATE"
LEGACY_STATE_END = "PROJECT_SUPERVISOR_STATE -->"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
REQUIRED_PATHS = (
    "AGENTS.md",
    "docs/PRODUCT_BRIEF.md",
    "docs/PROJECT_STATUS.md",
    "docs/UPDATE_GOVERNANCE.md",
    "docs/SUPERVISION_HANDOFF.md",
    CONTROL_PATH,
    "docs/BACKLOG.md",
)
AUTOMATIC_PROTECTED_PATHS = (
    ".env",
    ".env.local",
    ".env.development.local",
    ".env.production.local",
    ".env.test.local",
    "config/secrets.json",
    "credentials.json",
    "secrets.json",
)


class SupervisorError(RuntimeError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def run_git(root: Path, *args: str, text: bool = True, check: bool = True) -> str | bytes | subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args], cwd=root, capture_output=True,
        text=text, encoding="utf-8" if text else None, check=False,
    )
    if check and result.returncode != 0:
        stderr = result.stderr if text else result.stderr.decode("utf-8", errors="replace")
        raise SupervisorError(stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout if check else result


def repository_root(value: str | Path) -> Path:
    requested = Path(value).expanduser().resolve()
    if not requested.is_dir():
        raise SupervisorError(f"项目目录不存在：{requested}")
    root = Path(str(run_git(requested, "rev-parse", "--show-toplevel")).strip()).resolve()
    if root != requested:
        raise SupervisorError(f"请传入当前 checkout/worktree 的 Git 根目录：{root}")
    return root


def git_common_dir(root: Path) -> Path:
    raw = str(run_git(root, "rev-parse", "--git-common-dir")).strip()
    path = Path(raw)
    return (path if path.is_absolute() else root / path).resolve()


def git_dir(root: Path) -> Path:
    raw = str(run_git(root, "rev-parse", "--git-dir")).strip()
    path = Path(raw)
    return (path if path.is_absolute() else root / path).resolve()


def shared_database_path(root: Path) -> Path:
    return git_common_dir(root) / SHARED_DIR_NAME / DATABASE_NAME


def current_branch(root: Path) -> str:
    branch = str(run_git(root, "branch", "--show-current")).strip()
    return branch or "detached-HEAD"


def current_commit(root: Path) -> str:
    result = run_git(root, "rev-parse", "HEAD", check=False)
    assert isinstance(result, subprocess.CompletedProcess)
    return result.stdout.strip() if result.returncode == 0 else "unborn"


def status_entries(root: Path) -> dict[str, str]:
    raw = bytes(run_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", text=False))
    chunks = raw.split(b"\0")
    entries: dict[str, str] = {}
    index = 0
    while index < len(chunks):
        record = chunks[index]
        index += 1
        if not record:
            continue
        decoded = record.decode("utf-8", errors="surrogateescape")
        if len(decoded) < 4:
            raise SupervisorError(f"无法解析 git status 记录：{decoded!r}")
        status = decoded[:2]
        path = decoded[3:].replace("\\", "/")
        entries[path] = status
        if "R" in status or "C" in status:
            if index >= len(chunks) or not chunks[index]:
                raise SupervisorError("无法解析 Git 重命名/复制记录")
            source = chunks[index].decode("utf-8", errors="surrogateescape").replace("\\", "/")
            index += 1
            entries[source] = status
    return entries


def fingerprint_path(path: Path) -> str:
    if not path.exists() and not path.is_symlink():
        return "missing"
    if path.is_symlink():
        target = os.readlink(path)
        return "symlink:" + hashlib.sha256(target.encode("utf-8", errors="surrogateescape")).hexdigest()
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return "file:" + digest.hexdigest()
    if path.is_dir():
        digest = hashlib.sha256()
        for child in sorted(path.rglob("*"), key=lambda item: item.as_posix()):
            digest.update(child.relative_to(path).as_posix().encode("utf-8", errors="surrogateescape"))
            digest.update(b"\0")
            if child.is_symlink() or child.is_file():
                digest.update(fingerprint_path(child).encode("ascii"))
            else:
                digest.update(b"directory")
            digest.update(b"\0")
        return "directory:" + digest.hexdigest()
    return "other"


def fingerprint(root: Path, relative: str) -> str:
    return fingerprint_path(root / Path(relative))


def normalize_repository_path(root: Path, value: str, *, allow_directory: bool,
                              allow_control: bool = False) -> str:
    raw = value.strip().replace("\\", "/")
    if raw.endswith("/") and not allow_directory:
        raise SupervisorError(f"允许路径必须是精确文件，不能是目录：{value}")
    raw = raw.removeprefix("./").rstrip("/")
    if not raw or raw == ".":
        raise SupervisorError("路径不能是仓库根目录")
    if any(character in raw for character in "*?["):
        raise SupervisorError(f"路径不能使用 glob：{value}")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or ".." in pure.parts or any(":" in part for part in pure.parts):
        raise SupervisorError(f"路径必须是安全的仓库相对路径：{value}")
    if any(part.casefold() == ".git" for part in pure.parts):
        raise SupervisorError(f"禁止把 Git 内部路径纳入任务范围：{value}")
    normalized = pure.as_posix()
    if normalized == CONTROL_PATH and not allow_control:
        raise SupervisorError(f"普通任务不得修改共享状态指针 {CONTROL_PATH}")
    candidate = root
    for part in pure.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise SupervisorError(f"路径包含符号链接，不能安全纳入范围：{value}")
    final = root / Path(normalized)
    if final.exists() and final.is_dir() and not allow_directory:
        raise SupervisorError(f"允许路径必须是精确文件，不能是目录：{value}")
    try:
        final.parent.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise SupervisorError(f"路径解析后越出仓库：{value}") from exc
    return normalized


def paths_overlap(first: str, second: str) -> bool:
    a = PurePosixPath(first).parts
    b = PurePosixPath(second).parts
    return a == b or (len(a) < len(b) and b[:len(a)] == a) or (len(b) < len(a) and a[:len(b)] == b)


def validate_token(label: str, value: str, pattern: str = r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}") -> str:
    normalized = value.strip()
    if not re.fullmatch(pattern, normalized):
        raise SupervisorError(f"{label} 格式无效")
    return normalized


def validate_text(label: str, value: str, maximum: int = 500) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > maximum or any(ord(character) < 32 for character in normalized):
        raise SupervisorError(f"{label} 不能为空、含控制字符或超过 {maximum} 字符")
    return normalized


def validate_executor_identity(args: argparse.Namespace) -> tuple[str, str, str, str]:
    if args.role != "executor":
        raise SupervisorError("操作已拒绝：监督/监管/supervisor 任务终身只读，role 必须是 executor")
    supervisor_id = validate_token("supervisor ID", args.supervisor_id)
    task_id = validate_token("executor/task ID", args.task_id)
    if supervisor_id == task_id:
        raise SupervisorError("操作已拒绝：supervisor ID 与 executor/task ID 必须不同")
    model = validate_token("model", args.model)
    reasoning = validate_token("reasoning", args.reasoning, r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
    return supervisor_id, task_id, model, reasoning


def pointer_content() -> str:
    return f"""# 当前任务状态指针

<!-- {POINTER_MARKER} -->

实时状态不存放在本文件中。`project-supervisor` v3 将锁、待验收状态和审计事件保存在当前 Git 仓库所有 worktree 共享的 common dir 中。

- 本文件是静态、受 Git 跟踪的说明，不得通过编辑本文件认领或解除任务。
- 运行 `project_supervisor.py status --project-root <当前 checkout 根目录>` 查看共享状态和实际数据库路径。
- supervisor 任务永久只读；只有不同 ID 的 executor 可以运行 `init`、`claim`、`migrate`、`submit`、`resume`、`finish` 或 `abort`。
"""


def validate_state(state: object) -> dict:
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        raise SupervisorError("共享状态版本无效")
    status = state.get("status")
    if status not in {"idle", "active", "awaiting_acceptance"}:
        raise SupervisorError("共享状态值无效")
    if status == "idle":
        return state
    required = (
        "role", "supervisor_id", "executor_id", "task_id", "task_name", "risk", "model",
        "reasoning", "started_at", "base_commit", "allowed_paths", "protected_paths",
        "git_controls", "worktree_root", "common_dir",
    )
    missing = [key for key in required if state.get(key) is None or state.get(key) == ""]
    if missing:
        raise SupervisorError("活动共享状态缺少字段：" + "、".join(missing))
    if state.get("role") != "executor" or state.get("executor_id") != state.get("task_id"):
        raise SupervisorError("活动共享状态的 executor 身份无效")
    if state.get("supervisor_id") == state.get("executor_id"):
        raise SupervisorError("共享状态的 supervisor ID 与 executor ID 不能相同")
    if state.get("risk") not in {"R1", "R2", "R3"}:
        raise SupervisorError("共享状态风险等级无效")
    if not isinstance(state.get("allowed_paths"), list) or not state["allowed_paths"]:
        raise SupervisorError("共享状态必须含非空精确允许路径")
    if not isinstance(state.get("protected_paths"), dict) or not isinstance(state.get("git_controls"), dict):
        raise SupervisorError("共享状态保护字段类型无效")
    for item in state["allowed_paths"]:
        if not isinstance(item, str) or item.endswith("/") or ".." in PurePosixPath(item).parts:
            raise SupervisorError("共享状态含无效允许路径")
    if status == "awaiting_acceptance" and not isinstance(state.get("submission"), dict):
        raise SupervisorError("待验收状态缺少 submission")
    return state


def database_connect_rw(root: Path) -> sqlite3.Connection:
    database = shared_database_path(root)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=FULL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS state (singleton INTEGER PRIMARY KEY CHECK (singleton = 1), state_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            state_json TEXT NOT NULL,
            details_json TEXT NOT NULL
        );
        CREATE TRIGGER IF NOT EXISTS events_no_update
        BEFORE UPDATE ON events BEGIN
            SELECT RAISE(ABORT, 'audit events are append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS events_no_delete
        BEFORE DELETE ON events BEGIN
            SELECT RAISE(ABORT, 'audit events are append-only');
        END;
        """
    )
    return connection


def read_database(root: Path) -> tuple[dict, list[dict]] | None:
    database = shared_database_path(root)
    if not database.is_file():
        return None
    uri = database.resolve().as_uri() + "?mode=ro"
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=15)
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT state_json FROM state WHERE singleton = 1").fetchone()
        if row is None:
            raise SupervisorError("共享状态数据库缺少 state 记录")
        state_json = row["state_json"]
        event = connection.execute(
            "SELECT event_id, created_at, event_type, actor_id, state_json, details_json "
            "FROM events ORDER BY event_id DESC LIMIT 1"
        ).fetchone()
        if event is None or event["state_json"] != state_json:
            raise SupervisorError("共享状态与最后审计事件不一致，可能被篡改或未完整写入")
        state = validate_state(json.loads(state_json))
        latest = [{
            "event_id": event["event_id"], "created_at": event["created_at"],
            "event_type": event["event_type"], "actor_id": event["actor_id"],
            "details": json.loads(event["details_json"]),
        }]
        return state, latest
    except (sqlite3.Error, json.JSONDecodeError) as exc:
        raise SupervisorError(f"共享状态数据库无效：{exc}") from exc
    finally:
        if connection is not None:
            connection.close()


def load_state_in_transaction(connection: sqlite3.Connection) -> dict | None:
    row = connection.execute("SELECT state_json FROM state WHERE singleton = 1").fetchone()
    if row is None:
        return None
    state_json = row["state_json"]
    event = connection.execute("SELECT state_json FROM events ORDER BY event_id DESC LIMIT 1").fetchone()
    if event is None or event["state_json"] != state_json:
        raise SupervisorError("共享状态与审计事件不一致，拒绝继续写入")
    return validate_state(json.loads(state_json))


def write_state_event(connection: sqlite3.Connection, state: dict, event_type: str,
                      actor_id: str, details: dict) -> None:
    state_json = canonical_json(validate_state(state))
    connection.execute(
        "INSERT INTO state(singleton, state_json) VALUES(1, ?) "
        "ON CONFLICT(singleton) DO UPDATE SET state_json = excluded.state_json", (state_json,),
    )
    connection.execute(
        "INSERT INTO events(created_at, event_type, actor_id, state_json, details_json) VALUES(?, ?, ?, ?, ?)",
        (now_iso(), event_type, actor_id, state_json, canonical_json(details)),
    )


def idle_state(last_receipt: dict | None = None) -> dict:
    return {"version": STATE_VERSION, "status": "idle", "last_receipt": last_receipt}


def parse_legacy_state(content: str) -> dict | None:
    pattern = re.escape(LEGACY_STATE_START) + r"\s*(\{.*?\})\s*" + re.escape(LEGACY_STATE_END)
    match = re.search(pattern, content, flags=re.DOTALL)
    if not match:
        return None
    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise SupervisorError(f"旧版 ACTIVE_TASK.md 状态 JSON 无效：{exc}") from exc
    if not isinstance(state, dict) or state.get("version") not in {1, 2} or state.get("status") not in {"idle", "active"}:
        raise SupervisorError("旧版 ACTIVE_TASK.md 状态无效")
    return state


def parse_external_state(content: str) -> dict | None:
    status_match = re.search(r"^\s*状态\s*[：:]\s*(空闲|执行中)\s*$", content, flags=re.MULTILINE)
    if not status_match:
        return None
    fields: dict[str, str] = {}
    for match in re.finditer(r"^\s*-\s*([^：:\r\n]+)\s*[：:]\s*(.*?)\s*$", content, flags=re.MULTILINE):
        fields.setdefault(match.group(1).strip(), match.group(2).strip())
    required = {"任务名称", "风险等级", "执行窗口", "允许修改路径", "既有用户路径"}
    if not required.issubset(fields):
        return None
    return {"status": "idle" if status_match.group(1) == "空闲" else "active",
            "display_status": status_match.group(1), "fields": fields}


def repository_pointer_backend(root: Path) -> dict:
    pointer = root / CONTROL_PATH
    if not pointer.is_file():
        return {"kind": "missing", "status": "unknown", "state": None, "error": f"缺少指针文件：{pointer}"}
    try:
        content = pointer.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return {"kind": "invalid", "status": "unknown", "state": None, "error": str(exc)}
    if POINTER_MARKER in content:
        if content == pointer_content():
            return {"kind": "v3-pointer", "status": "unknown", "state": None, "error": None}
        return {"kind": "invalid", "status": "unknown", "state": None,
                "error": "v3 ACTIVE_TASK.md 静态指针内容已被修改"}
    try:
        legacy = parse_legacy_state(content)
    except SupervisorError as exc:
        return {"kind": "invalid", "status": "unknown", "state": None, "error": str(exc)}
    if legacy:
        return {"kind": "legacy-project-supervisor", "status": legacy["status"], "state": legacy,
                "error": "需要由独立 executor 显式运行 migrate"}
    external = parse_external_state(content)
    if external:
        return {"kind": "external-repository-guard", "status": external["status"], "state": external, "error": None}
    return {"kind": "invalid", "status": "unknown", "state": None,
            "error": "ACTIVE_TASK.md 不是 v3 指针、有效旧版状态或完整外部守卫"}


def verify_required(root: Path) -> None:
    missing = [relative for relative in REQUIRED_PATHS if not (root / relative).is_file()]
    if missing:
        raise SupervisorError("缺少监管文件：" + "、".join(missing))


def governance_inventory(root: Path) -> dict:
    present = [relative for relative in REQUIRED_PATHS if (root / relative).is_file()]
    return {"present": present, "missing": [relative for relative in REQUIRED_PATHS if relative not in present]}


def git_control_snapshot(root: Path) -> dict[str, str]:
    common = git_common_dir(root)
    checkout_git_dir = git_dir(root)
    snapshot = {
        "common_config": fingerprint_path(common / "config"),
        "common_hooks": fingerprint_path(common / "hooks"),
        "worktree_config": fingerprint_path(checkout_git_dir / "config.worktree"),
    }
    dot_git = root / ".git"
    if dot_git.is_file() or dot_git.is_symlink():
        snapshot["worktree_git_pointer"] = fingerprint_path(dot_git)
    return snapshot


def protected_snapshot(root: Path, allowed: list[str], explicit: list[str]) -> dict[str, dict[str, str | None]]:
    entries = status_entries(root)
    staged = [path for path, status in entries.items() if status[0] not in {" ", "?"}]
    if staged:
        raise SupervisorError("认领前存在已暂存文件：" + "、".join(staged))
    protected_names = set(entries)
    protected_names.update(AUTOMATIC_PROTECTED_PATHS)
    protected_names.update(
        path.relative_to(root).as_posix()
        for path in root.glob(".env*")
        if path.is_file() or path.is_symlink()
    )
    for value in explicit:
        protected_names.add(normalize_repository_path(root, value, allow_directory=True))
    for path in protected_names:
        for allowed_path in allowed:
            if paths_overlap(path, allowed_path):
                raise SupervisorError(f"允许路径与既有/受保护路径重叠：{path} / {allowed_path}")
    return {path: {"fingerprint": fingerprint(root, path), "status": entries.get(path)} for path in sorted(protected_names)}


def new_active_state(root: Path, args: argparse.Namespace, allowed: list[str], protected: dict,
                     git_controls: dict, task_name: str | None = None) -> dict:
    supervisor_id, task_id, model, reasoning = validate_executor_identity(args)
    return {
        "version": STATE_VERSION, "status": "active", "role": "executor",
        "supervisor_id": supervisor_id, "executor_id": task_id, "task_id": task_id,
        "task_name": validate_text("task name", task_name or args.task_name), "risk": args.risk,
        "model": model, "reasoning": reasoning, "started_at": now_iso(),
        "base_commit": current_commit(root), "allowed_paths": allowed,
        "protected_paths": protected, "git_controls": git_controls,
        "worktree_root": str(root), "common_dir": str(git_common_dir(root)),
    }


def validate_identity_against_state(args: argparse.Namespace, state: dict) -> None:
    supervisor_id, task_id, _model, _reasoning = validate_executor_identity(args)
    if state.get("supervisor_id") != supervisor_id:
        raise SupervisorError(f"supervisor ID 不匹配：当前为 {state.get('supervisor_id')}")
    if state.get("executor_id") != task_id or state.get("task_id") != task_id:
        raise SupervisorError(f"executor/task ID 不匹配：当前为 {state.get('task_id')}")


def changed_paths_between(root: Path, base: str, head: str) -> set[str]:
    if base == head or head == "unborn":
        return set()
    diff_base = EMPTY_TREE if base == "unborn" else base
    if base != "unborn":
        result = run_git(root, "merge-base", "--is-ancestor", base, head, check=False)
        assert isinstance(result, subprocess.CompletedProcess)
        if result.returncode != 0:
            raise SupervisorError(f"当前 HEAD {head} 不是起始提交 {base} 的后代")
    raw = bytes(run_git(root, "diff", "--name-status", "-z", "--find-renames", diff_base, head, "--", text=False))
    tokens = raw.split(b"\0")
    paths: set[str] = set()
    index = 0
    while index < len(tokens):
        if not tokens[index]:
            index += 1
            continue
        status = tokens[index].decode("ascii", errors="replace")
        index += 1
        for _ in range(2 if status.startswith(("R", "C")) else 1):
            if index >= len(tokens) or not tokens[index]:
                raise SupervisorError("无法解析提交差异路径")
            paths.add(tokens[index].decode("utf-8", errors="surrogateescape").replace("\\", "/"))
            index += 1
    return paths


def validate_active_checkout(state: dict, *, require_clean_task: bool = False,
                             expected_commit: str | None = None) -> dict:
    root = repository_root(state["worktree_root"])
    if str(git_common_dir(root)) != state["common_dir"]:
        raise SupervisorError("记录的 executor worktree 已不属于同一 Git common dir")
    errors: list[str] = []
    entries = status_entries(root)
    protected: dict[str, dict] = state["protected_paths"]
    allowed: list[str] = state["allowed_paths"]
    for path in root.glob(".env*"):
        relative = path.relative_to(root).as_posix()
        if relative not in protected:
            errors.append(f"认领后新增敏感环境文件：{relative}")
    for path, baseline in protected.items():
        actual_fingerprint = fingerprint(root, path)
        actual_status = entries.get(path)
        if actual_fingerprint != baseline.get("fingerprint"):
            errors.append(f"受保护路径内容发生变化：{path}")
        if actual_status != baseline.get("status"):
            errors.append(f"受保护路径 Git 状态发生变化：{path} ({baseline.get('status')} -> {actual_status})")
    task_dirty: list[str] = []
    for path in entries:
        if path in protected:
            continue
        if path not in allowed:
            errors.append(f"出现范围外修改：{path}")
        elif require_clean_task:
            task_dirty.append(path)
    if task_dirty:
        errors.append("任务修改尚未全部提交：" + "、".join(sorted(task_dirty)))
    if git_control_snapshot(root) != state["git_controls"]:
        errors.append("Git config、hooks 或 worktree 指针发生变化")
    head = current_commit(root)
    if expected_commit is not None and head != expected_commit:
        errors.append(f"验收后的 HEAD 发生变化：期望 {expected_commit}，实际 {head}")
    try:
        commit_paths = changed_paths_between(root, state["base_commit"], head)
    except SupervisorError as exc:
        errors.append(str(exc))
        commit_paths = set()
    outside_commits = sorted(path for path in commit_paths if path not in allowed)
    if outside_commits:
        errors.append("提交范围含未声明路径：" + "、".join(outside_commits))
    return {"errors": errors, "worktree_root": str(root), "head": head,
            "commit_paths": sorted(commit_paths), "task_dirty": sorted(task_dirty)}


def exclusive_create_text(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def atomic_replace_text(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        exclusive_create_text(temporary, content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def command_init(args: argparse.Namespace) -> None:
    root = repository_root(args.project_root)
    validate_executor_identity(args)
    template_root = Path(__file__).resolve().parent.parent / "assets" / "project-template"
    missing_templates = [relative for relative in REQUIRED_PATHS if not (template_root / relative).is_file()]
    if missing_templates:
        raise SupervisorError("Skill 模板不完整：" + "、".join(missing_templates))
    existing = [relative for relative in REQUIRED_PATHS if (root / relative).exists() or (root / relative).is_symlink()]
    if existing:
        raise SupervisorError("为避免覆盖，初始化已停止；这些路径已存在：" + "、".join(existing))
    allowed = [normalize_repository_path(root, item, allow_directory=False, allow_control=True) for item in REQUIRED_PATHS]
    protected = protected_snapshot(root, allowed, args.protect)
    active = new_active_state(root, args, allowed, protected, git_control_snapshot(root),
                              task_name=f"初始化 {args.project_name} 监管体系")
    connection = database_connect_rw(root)
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing_state = load_state_in_transaction(connection)
        if existing_state is not None:
            retryable = (
                existing_state["status"] == "idle"
                and isinstance(existing_state.get("last_receipt"), dict)
                and existing_state["last_receipt"].get("outcome") == "init-aborted"
            )
            resumable = (
                existing_state["status"] == "active"
                and existing_state.get("allowed_paths") == allowed
                and existing_state.get("task_name") == active["task_name"]
            )
            if resumable:
                validate_identity_against_state(args, existing_state)
                if existing_state["base_commit"] != current_commit(root):
                    raise SupervisorError("初始化续跑要求 HEAD 仍为原起始提交")
                resume_report = validate_active_checkout(existing_state, require_clean_task=True)
                if resume_report["errors"]:
                    raise SupervisorError("初始化续跑前检查失败：" + "；".join(resume_report["errors"]))
                active = existing_state
                write_state_event(connection, active, "init_resumed", active["task_id"],
                                  {"project_name": args.project_name, "allowed_paths": allowed})
            elif not retryable:
                raise SupervisorError("共享状态已初始化；init 不得覆盖现有 v3 状态")
        if existing_state is None or retryable:
            write_state_event(connection, active, "initialized", active["task_id"],
                              {"project_name": args.project_name, "allowed_paths": allowed})
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    replacements = {"{{PROJECT_NAME}}": args.project_name, "{{DATE}}": dt.date.today().isoformat(),
                    "{{DEFAULT_BRANCH}}": current_branch(root)}
    created: list[Path] = []
    try:
        for relative in REQUIRED_PATHS:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.parent.is_symlink():
                raise SupervisorError(f"初始化目标父目录是符号链接：{destination.parent}")
            content = pointer_content() if relative == CONTROL_PATH else (template_root / relative).read_text(encoding="utf-8")
            for old, new in replacements.items():
                content = content.replace(old, new)
            exclusive_create_text(destination, content)
            created.append(destination)
    except Exception as exc:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        connection = database_connect_rw(root)
        try:
            connection.execute("BEGIN IMMEDIATE")
            aborted = idle_state({"outcome": "init-aborted", "reason": str(exc), "at": now_iso()})
            write_state_event(connection, aborted, "init_aborted", active["task_id"], {"reason": str(exc)})
            connection.commit()
        finally:
            connection.close()
        raise
    print(f"已由独立 executor {active['task_id']} 创建 {len(created)} 份监管文件并保持共享锁为 active。")
    print("下一步：补全项目事实，提交全部初始化文件，然后 submit；监督验收后由本 executor finish。")


def command_claim(args: argparse.Namespace) -> None:
    root = repository_root(args.project_root)
    verify_required(root)
    if repository_pointer_backend(root)["kind"] != "v3-pointer":
        raise SupervisorError("claim 需要 v3 静态指针；旧版请先由独立 executor 运行 migrate")
    allowed = list(dict.fromkeys(normalize_repository_path(root, item, allow_directory=False) for item in args.allow))
    if not allowed:
        raise SupervisorError("至少声明一个精确文件路径")
    connection = database_connect_rw(root)
    try:
        connection.execute("BEGIN IMMEDIATE")
        state = load_state_in_transaction(connection)
        if state is None:
            raise SupervisorError("缺少 v3 共享状态；不要手工创建，请使用 init 或 migrate")
        if state["status"] != "idle":
            raise SupervisorError(f"已有任务占用：{state.get('task_id')} / {state.get('task_name')}")
        protected = protected_snapshot(root, allowed, args.protect)
        active = new_active_state(root, args, allowed, protected, git_control_snapshot(root))
        write_state_event(connection, active, "claimed", active["task_id"],
                          {"allowed_paths": allowed, "protected_paths": sorted(protected)})
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print(f"已由 executor {active['task_id']} 认领任务（{active['risk']}），共享锁覆盖所有 worktree。")


def command_migrate(args: argparse.Namespace) -> None:
    root = repository_root(args.project_root)
    verify_required(root)
    validate_executor_identity(args)
    pointer = repository_pointer_backend(root)
    if pointer["kind"] == "external-repository-guard":
        raise SupervisorError("这是仓库自有外部守卫，project-supervisor 不会接管或迁移")
    if pointer["kind"] != "legacy-project-supervisor" or pointer["status"] != "idle":
        raise SupervisorError("migrate 仅支持干净、空闲的 v1/v2 project-supervisor 状态")
    if CONTROL_PATH in status_entries(root):
        raise SupervisorError("迁移前 ACTIVE_TASK.md 必须无未提交变化")
    allowed = [CONTROL_PATH]
    allowed.extend(normalize_repository_path(root, item, allow_directory=False) for item in args.allow)
    allowed = list(dict.fromkeys(allowed))
    protected = protected_snapshot(root, allowed, args.protect)
    active = new_active_state(root, args, allowed, protected, git_control_snapshot(root),
                              task_name=args.task_name or "迁移 project-supervisor 到 v3")
    connection = database_connect_rw(root)
    try:
        connection.execute("BEGIN IMMEDIATE")
        if load_state_in_transaction(connection) is not None:
            raise SupervisorError("v3 共享状态已存在，拒绝重复迁移")
        write_state_event(connection, active, "migrated", active["task_id"],
                          {"from_version": pointer["state"].get("version"), "allowed_paths": allowed})
        atomic_replace_text(root / CONTROL_PATH, pointer_content())
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print("旧版空闲状态已迁移到 v3；迁移 executor 仍持有 active 锁，请提交指针变更后走 submit/finish。")


def command_check(args: argparse.Namespace) -> None:
    root = repository_root(args.project_root)
    if repository_pointer_backend(root)["kind"] != "v3-pointer":
        raise SupervisorError("仓库内 ACTIVE_TASK.md 不是有效 v3 静态指针")
    loaded = read_database(root)
    if loaded is None:
        raise SupervisorError("缺少 v3 共享状态数据库")
    state, _events = loaded
    if state["status"] != args.expect:
        raise SupervisorError(f"期望状态 {args.expect}，实际状态 {state['status']}")
    if args.task_id and state.get("task_id") != args.task_id:
        raise SupervisorError(f"任务 ID 不匹配：期望 {args.task_id}，实际 {state.get('task_id')}")
    if state["status"] in {"active", "awaiting_acceptance"}:
        expected = state.get("submission", {}).get("final_commit") if state["status"] == "awaiting_acceptance" else None
        report = validate_active_checkout(state, expected_commit=expected)
        if report["errors"]:
            raise SupervisorError("；".join(report["errors"]))
        print(json.dumps({"status": state["status"], "task_id": state["task_id"], "validation": report},
                         ensure_ascii=False, indent=2))
    else:
        print("监管检查通过：共享状态 idle。")


def command_submit(args: argparse.Namespace) -> None:
    root = repository_root(args.project_root)
    if not args.verification:
        raise SupervisorError("submit 至少需要一条 --verification")
    connection = database_connect_rw(root)
    try:
        connection.execute("BEGIN IMMEDIATE")
        state = load_state_in_transaction(connection)
        if state is None or state["status"] != "active":
            raise SupervisorError("只有 active executor 可以提交验收；退回后请先 resume")
        validate_identity_against_state(args, state)
        report = validate_active_checkout(state, require_clean_task=True)
        if report["errors"]:
            raise SupervisorError("提交验收前检查失败：" + "；".join(report["errors"]))
        submission = {
            "submitted_at": now_iso(), "final_commit": report["head"], "commit_paths": report["commit_paths"],
            "verification": [validate_text("verification", item, 1000) for item in args.verification],
            "not_run": [validate_text("not-run", item, 1000) for item in args.not_run],
            "remaining_risk": validate_text("remaining risk", args.remaining_risk, 1000),
        }
        state["status"] = "awaiting_acceptance"
        state["submission"] = submission
        write_state_event(connection, state, "submitted", state["task_id"], submission)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print("交付已进入 awaiting_acceptance；共享锁仍保持占用。请等待 supervisor 只读验收，不要自行 finish。")


def command_resume(args: argparse.Namespace) -> None:
    root = repository_root(args.project_root)
    reason = validate_text("resume reason", args.reason, 1000)
    connection = database_connect_rw(root)
    try:
        connection.execute("BEGIN IMMEDIATE")
        state = load_state_in_transaction(connection)
        if state is None or state["status"] != "awaiting_acceptance":
            raise SupervisorError("只有 awaiting_acceptance 任务可以恢复修改")
        validate_identity_against_state(args, state)
        prior = state.pop("submission")
        state["status"] = "active"
        write_state_event(connection, state, "resumed", state["task_id"],
                          {"reason": reason, "prior_submission": prior})
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print("任务已恢复 active；共享锁仍由原 executor 持有。")


def command_finish(args: argparse.Namespace) -> None:
    root = repository_root(args.project_root)
    accepted_by = validate_token("accepted-by", args.accepted_by)
    connection = database_connect_rw(root)
    try:
        connection.execute("BEGIN IMMEDIATE")
        state = load_state_in_transaction(connection)
        if state is None or state["status"] != "awaiting_acceptance":
            raise SupervisorError("只有 awaiting_acceptance 任务可以 finish")
        validate_identity_against_state(args, state)
        if accepted_by != state["supervisor_id"]:
            raise SupervisorError("accepted-by 必须与记录的 supervisor ID 一致")
        report = validate_active_checkout(state, require_clean_task=True,
                                          expected_commit=state["submission"]["final_commit"])
        if report["errors"]:
            raise SupervisorError("finish 前检查失败：" + "；".join(report["errors"]))
        receipt = {
            "receipt_id": uuid.uuid4().hex, "outcome": "completed", "completed_at": now_iso(),
            "accepted_by": accepted_by, "task_id": state["task_id"], "task_name": state["task_name"],
            "risk": state["risk"], "model": state["model"], "reasoning": state["reasoning"],
            "base_commit": state["base_commit"], "final_commit": report["head"],
            "allowed_paths": state["allowed_paths"], "protected_paths": state["protected_paths"],
            "submission": state["submission"], "worktree_root": state["worktree_root"],
        }
        idle = idle_state({"receipt_id": receipt["receipt_id"], "outcome": "completed",
                           "task_id": receipt["task_id"], "final_commit": receipt["final_commit"],
                           "completed_at": receipt["completed_at"]})
        write_state_event(connection, idle, "completed", state["task_id"], receipt)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def command_abort(args: argparse.Namespace) -> None:
    root = repository_root(args.project_root)
    reason = validate_text("abort reason", args.reason, 1000)
    connection = database_connect_rw(root)
    try:
        connection.execute("BEGIN IMMEDIATE")
        state = load_state_in_transaction(connection)
        if state is None or state["status"] not in {"active", "awaiting_acceptance"}:
            raise SupervisorError("当前没有可中止的 executor 任务")
        validate_identity_against_state(args, state)
        report = validate_active_checkout(state, require_clean_task=True)
        if report["head"] != state["base_commit"]:
            report["errors"].append("abort 要求 HEAD 恢复到起始提交；脚本不会自动回退提交")
        if report["errors"]:
            raise SupervisorError("abort 前检查失败：" + "；".join(report["errors"]))
        receipt = {"receipt_id": uuid.uuid4().hex, "outcome": "aborted", "completed_at": now_iso(),
                   "task_id": state["task_id"], "task_name": state["task_name"], "reason": reason,
                   "base_commit": state["base_commit"], "worktree_root": state["worktree_root"]}
        idle = idle_state({"receipt_id": receipt["receipt_id"], "outcome": "aborted",
                           "task_id": receipt["task_id"], "completed_at": receipt["completed_at"]})
        write_state_event(connection, idle, "aborted", state["task_id"], receipt)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


def command_release(_args: argparse.Namespace) -> None:
    raise SupervisorError("v3 已移除 release：提交后用 submit，验收后由原 executor 用 finish；无变更中止用 abort")


def discover_guard_commands(root: Path) -> list[str]:
    package_file = root / "package.json"
    if not package_file.is_file():
        return []
    try:
        package = json.loads(package_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    scripts = package.get("scripts")
    if not isinstance(scripts, dict):
        return []
    manager = str(package.get("packageManager") or "").split("@", 1)[0]
    if manager not in {"npm", "pnpm", "yarn", "bun"}:
        manager = "pnpm" if (root / "pnpm-lock.yaml").is_file() else "yarn" if (root / "yarn.lock").is_file() else "npm"
    commands: list[str] = []
    for name, command in sorted(scripts.items()):
        lowered = str(command).lower()
        if name.startswith("task:check") or "task-guard" in lowered or "active_task" in lowered:
            commands.append(f"{'npm run' if manager == 'npm' else manager} {name}")
    return commands


def readonly_summary(root: Path) -> dict:
    pointer = repository_pointer_backend(root)
    database = shared_database_path(root)
    try:
        loaded = read_database(root)
        database_error = None
    except SupervisorError as exc:
        loaded = None
        database_error = str(exc)
    if loaded:
        state, latest_events = loaded
        pointer_error = None if pointer["kind"] == "v3-pointer" else (
            "共享数据库可读，但仓库内 ACTIVE_TASK.md 不是有效 v3 静态指针"
        )
        backend = {"kind": "project-supervisor-shared", "managed": True,
                   "format": "git-common-dir-sqlite-v3", "status": state["status"], "state": state,
                   "database": str(database), "latest_event": latest_events[0], "error": pointer_error}
    elif database_error:
        backend = {"kind": "invalid", "managed": False, "format": "git-common-dir-sqlite-v3",
                   "status": "unknown", "state": None, "database": str(database), "error": database_error}
    elif pointer["kind"] == "v3-pointer":
        backend = {"kind": "invalid", "managed": False, "format": "git-common-dir-sqlite-v3",
                   "status": "unknown", "state": None, "database": str(database),
                   "error": "仓库含 v3 静态指针，但共享状态数据库缺失"}
    else:
        backend = {"kind": pointer["kind"], "managed": False, "format": None,
                   "status": pointer["status"], "state": pointer["state"], "database": str(database),
                   "error": pointer["error"]}
    return {
        "project_root": str(root), "git_common_dir": str(git_common_dir(root)),
        "branch": current_branch(root), "commit": current_commit(root), "readonly": True,
        "lock_backend": backend, "repository_pointer": pointer,
        "local_guard_commands": discover_guard_commands(root), "governance_files": governance_inventory(root),
        "git_changes": [{"path": path, "status": status} for path, status in sorted(status_entries(root).items())],
    }


def command_status(args: argparse.Namespace) -> None:
    print(json.dumps(readonly_summary(repository_root(args.project_root)), ensure_ascii=False, indent=2))


def command_doctor(args: argparse.Namespace) -> None:
    root = repository_root(args.project_root)
    summary = readonly_summary(root)
    backend = summary["lock_backend"]
    if backend["kind"] == "project-supervisor-shared":
        if backend.get("error"):
            policy, takeover = "v3 状态可读但仓库指针损坏；只读监督，交给独立 executor 修复", False
        else:
            policy, takeover = "v3 共享状态可用；所有 worktree 使用同一 SQLite 事务锁与审计事件", True
    elif backend["kind"] == "legacy-project-supervisor":
        policy, takeover = "只读识别旧版；必须由独立 executor 显式 migrate", True
    elif backend["kind"] == "external-repository-guard":
        policy, takeover = "只读接管；遵循仓库 AGENTS.md 和本地守卫，v3 不会改写", True
    else:
        policy, takeover = "只读诊断；缺失或损坏，禁止隐式修复", False
    summary["doctor"] = {"readonly_takeover_supported": takeover, "mutation_policy": policy,
                         "diagnostic": backend.get("error")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def command_audit(args: argparse.Namespace) -> None:
    root = repository_root(args.project_root)
    database = shared_database_path(root)
    if not database.is_file():
        raise SupervisorError("缺少 v3 共享状态数据库")
    uri = database.resolve().as_uri() + "?mode=ro"
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=15)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT event_id, created_at, event_type, actor_id, details_json FROM events "
            "ORDER BY event_id DESC LIMIT ?", (args.limit,)
        ).fetchall()
        events = [{"event_id": row["event_id"], "created_at": row["created_at"],
                   "event_type": row["event_type"], "actor_id": row["actor_id"],
                   "details": json.loads(row["details_json"])} for row in rows]
    except (sqlite3.Error, json.JSONDecodeError) as exc:
        raise SupervisorError(f"无法读取审计事件：{exc}") from exc
    finally:
        if connection is not None:
            connection.close()
    print(json.dumps({"database": str(database), "events": events}, ensure_ascii=False, indent=2))


def add_identity_arguments(parser: argparse.ArgumentParser, *, task_name: bool = False,
                           risk: bool = False) -> None:
    parser.add_argument("--role", required=True, choices=("executor", "supervisor"))
    parser.add_argument("--supervisor-id", required=True)
    parser.add_argument("--task-id", required=True, help="当前 executor/task ID")
    parser.add_argument("--model", required=True, help="当前任务实际模型")
    parser.add_argument("--reasoning", required=True, help="当前任务实际推理级别")
    if task_name:
        parser.add_argument("--task-name", required=True)
    if risk:
        parser.add_argument("--risk", choices=("R1", "R2", "R3"), required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init", help="由独立 bootstrap executor 初始化 v3")
    init_parser.add_argument("--project-root", required=True)
    init_parser.add_argument("--project-name", required=True)
    add_identity_arguments(init_parser, risk=True)
    init_parser.add_argument("--protect", action="append", default=[], metavar="PATH")
    init_parser.set_defaults(handler=command_init)
    status_parser = subparsers.add_parser("status", help="只读输出共享监管、指针与 Git 状态")
    status_parser.add_argument("--project-root", required=True)
    status_parser.set_defaults(handler=command_status)
    doctor_parser = subparsers.add_parser("doctor", help="只读诊断 v3、旧版或外部守卫")
    doctor_parser.add_argument("--project-root", required=True)
    doctor_parser.set_defaults(handler=command_doctor)
    audit_parser = subparsers.add_parser("audit", help="只读输出 v3 审计事件")
    audit_parser.add_argument("--project-root", required=True)
    audit_parser.add_argument("--limit", type=int, choices=range(1, 101), default=20)
    audit_parser.set_defaults(handler=command_audit)
    claim_parser = subparsers.add_parser("claim", help="由独立 executor 原子认领所有 worktree 共享锁")
    claim_parser.add_argument("--project-root", required=True)
    add_identity_arguments(claim_parser, task_name=True, risk=True)
    claim_parser.add_argument("--allow", action="append", default=[], metavar="FILE")
    claim_parser.add_argument("--protect", action="append", default=[], metavar="PATH")
    claim_parser.set_defaults(handler=command_claim)
    migrate_parser = subparsers.add_parser("migrate", help="显式迁移空闲 v1/v2 状态")
    migrate_parser.add_argument("--project-root", required=True)
    add_identity_arguments(migrate_parser, risk=True)
    migrate_parser.add_argument("--task-name")
    migrate_parser.add_argument("--allow", action="append", default=[], metavar="FILE")
    migrate_parser.add_argument("--protect", action="append", default=[], metavar="PATH")
    migrate_parser.set_defaults(handler=command_migrate)
    check_parser = subparsers.add_parser("check", help="只读验证共享状态、HEAD、范围和保护路径")
    check_parser.add_argument("--project-root", required=True)
    check_parser.add_argument("--expect", choices=("idle", "active", "awaiting_acceptance"), required=True)
    check_parser.add_argument("--task-id")
    check_parser.set_defaults(handler=command_check)
    submit_parser = subparsers.add_parser("submit", help="原 executor 提交已完成 commit 等待验收")
    submit_parser.add_argument("--project-root", required=True)
    add_identity_arguments(submit_parser)
    submit_parser.add_argument("--verification", action="append", default=[])
    submit_parser.add_argument("--not-run", action="append", default=[])
    submit_parser.add_argument("--remaining-risk", required=True)
    submit_parser.set_defaults(handler=command_submit)
    resume_parser = subparsers.add_parser("resume", help="原 executor 恢复被退回的任务")
    resume_parser.add_argument("--project-root", required=True)
    add_identity_arguments(resume_parser)
    resume_parser.add_argument("--reason", required=True)
    resume_parser.set_defaults(handler=command_resume)
    finish_parser = subparsers.add_parser("finish", help="验收后由原 executor 完成并保存回执")
    finish_parser.add_argument("--project-root", required=True)
    add_identity_arguments(finish_parser)
    finish_parser.add_argument("--accepted-by", required=True)
    finish_parser.set_defaults(handler=command_finish)
    abort_parser = subparsers.add_parser("abort", help="原 executor 在无任务修改/提交时安全中止")
    abort_parser.add_argument("--project-root", required=True)
    add_identity_arguments(abort_parser)
    abort_parser.add_argument("--reason", required=True)
    abort_parser.set_defaults(handler=command_abort)
    release_parser = subparsers.add_parser("release", help="v2 兼容提示")
    release_parser.set_defaults(handler=command_release)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.handler(args)
        return 0
    except (SupervisorError, sqlite3.Error) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
