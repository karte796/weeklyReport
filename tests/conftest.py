from __future__ import annotations

import json
import os
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from weekly_report.periods import Period


@pytest.fixture
def week() -> Period:
    return Period("weekly", date(2026, 10, 12), date(2026, 10, 18))


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """Isolated HOME so default record directories point into tmp_path."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("WEEKLY_REPORT_CONFIG", raising=False)
    return tmp_path


def write_jsonl(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
                    encoding="utf-8")
    return path


def make_records(root: Path) -> dict[str, Path]:
    """Create one session per source, all inside the 2026-10-12..18 week."""
    roots = {k: root / k for k in ("claude", "codex", "kiro", "kiro-cli")}
    write_jsonl(roots["claude"] / "-Users-me-code-app" / "s1.jsonl", [
        {"type": "ai-title", "aiTitle": "Fix login bug"},
        {"type": "user", "timestamp": "2026-10-13T02:00:00.123Z", "cwd": "/Users/me/code/app",
         "gitBranch": "fix/login", "promptSource": "typed",
         "message": {"content": "why does login fail"}},
        {"type": "user", "timestamp": "2026-10-13T02:01:00Z", "cwd": "/Users/me/code/app",
         "message": {"content": [{"type": "tool_result", "content": "x"}]}},
        {"type": "assistant", "timestamp": "2026-10-13T02:02:00Z"},
        {"type": "user", "timestamp": "2026-09-01T02:00:00Z", "promptSource": "typed",
         "message": {"content": "outside the period"}},
    ])
    write_jsonl(roots["codex"] / "2026" / "10" / "14" / "rollout-abc.jsonl", [
        {"timestamp": "2026-10-14T01:00:00Z", "type": "session_meta",
         "payload": {"cwd": "/Users/me/code/api", "git": {"branch": "main"}}},
        {"timestamp": "2026-10-14T01:00:01Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "<environment_context>x"}]}},
        {"timestamp": "2026-10-14T01:00:02Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "add pagination"}]}},
        {"timestamp": "2026-10-14T01:00:03Z", "type": "response_item",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "add pagination"}]}},
    ])
    kiro_file = roots["kiro"] / "d29yaw==" / "k1.json"
    kiro_file.parent.mkdir(parents=True)
    kiro_file.write_text(json.dumps({
        "title": "Refactor store", "workspacePath": "/Users/me/code/web",
        "history": [{"message": {"role": "user", "content": [{"type": "text", "text": "split store"}]}},
                    {"message": {"role": "assistant", "content": "ok"}}]}))
    ts = datetime(2026, 10, 15, 12, tzinfo=timezone.utc).timestamp()
    os.utime(kiro_file, (ts, ts))
    (roots["kiro"] / "d29yaw==" / "sessions.json").write_text("[]")

    meta = roots["kiro-cli"] / "c1.json"
    meta.parent.mkdir(parents=True)
    meta.write_text(json.dumps({"session_id": "c1", "cwd": "/Users/me/code/cli",
                                "title": "Write release notes",
                                "updated_at": "2026-10-16T03:00:00Z"}))
    write_jsonl(meta.with_suffix(".jsonl"), [
        {"version": "v1", "kind": "Prompt",
         "data": {"message_id": "1", "meta": {"timestamp": int(datetime(2026, 10, 16, 4, tzinfo=timezone.utc).timestamp())},
                  "content": [{"kind": "text", "data": "draft notes for v2"}]}},
        {"version": "v1", "kind": "AssistantMessage", "data": {"content": []}},
    ])
    return roots


def git(repo: Path, *args: str, env: dict | None = None) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=env).stdout


def make_repo(path: Path, email: str = "me@example.com",
              commits: tuple = (("2026-10-13T10:00:00", "feat: add search"),)) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    git(path, "config", "user.email", email)
    git(path, "config", "user.name", "Me")
    for i, (when, subject) in enumerate(commits):
        (path / f"f{i}.txt").write_text(subject)
        git(path, "add", ".")
        env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
        git(path, "commit", "-q", "-m", subject, env=env)
    return path
