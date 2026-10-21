"""Read local AI-assistant session records (read-only) and normalise them.

Supported sources and their on-disk formats:
  claude   ~/.claude/projects/<encoded-cwd>/<session>.jsonl   one JSON record per line, UTC timestamps
  codex    ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl     {timestamp, type, payload} per line
  kiro     <Kiro app data>/kiro.kiroagent/workspace-sessions/<b64>/<id>.json
           one JSON document without timestamps -> file mtime is used (marked approximate)
  kiro-cli ~/.kiro/sessions/cli/<id>.json (+ <id>.jsonl)     metadata + event stream with unix timestamps
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone, tzinfo
from pathlib import Path
from typing import Callable, Optional

from weekly_report.periods import Period

ALL_SOURCES = ["claude", "codex", "kiro", "kiro-cli"]
LABELS = {"claude": "Claude Code", "codex": "Codex", "kiro": "Kiro", "kiro-cli": "Kiro CLI"}


def _app_data_dir() -> Path:
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    return Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))


def default_roots() -> dict[str, Path]:
    home = Path.home()
    return {
        "claude": Path(os.environ.get("CLAUDE_CONFIG_DIR", home / ".claude")) / "projects",
        "codex": Path(os.environ.get("CODEX_HOME", home / ".codex")) / "sessions",
        "kiro": _app_data_dir() / "Kiro" / "User" / "globalStorage" / "kiro.kiroagent" / "workspace-sessions",
        "kiro-cli": home / ".kiro" / "sessions" / "cli",
    }


@dataclass
class Session:
    source: str
    session_id: str
    title: Optional[str]
    cwd: Optional[str]
    prompts: list[str] = field(default_factory=list)
    branches: list[str] = field(default_factory=list)
    message_count: int = 0
    first_date: Optional[date] = None
    last_date: Optional[date] = None
    date_approx: bool = False

    @property
    def project(self) -> str:
        if not self.cwd:
            return "(unknown project)"
        parts = Path(self.cwd).parts
        return "/".join(parts[-2:]) if len(parts) >= 2 else self.cwd

    @property
    def key(self) -> str:
        """Stable identity used by the GUI selection."""
        return f"{self.source}:{self.session_id}"

    def matches(self, keywords: list[str]) -> bool:
        if not keywords:
            return True
        haystack = " ".join([self.title or "", self.cwd or "", " ".join(self.branches),
                             " ".join(self.prompts)]).lower()
        return any(k.lower() in haystack for k in keywords)


# ---------------------------------------------------------------- helpers

def parse_iso(raw) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw:
        return None
    text = raw.strip().replace("Z", "+00:00")
    # Python < 3.11 only accepts 3 or 6 fractional digits: normalise to 6.
    text = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], text, count=1)
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def clean_prompt(text: str, max_len: int) -> str:
    """Collapse whitespace, drop command echoes / image-only messages, truncate."""
    text = " ".join((text or "").split())
    if text.startswith(("<command-", "<local-command", "[Request interrupted", "Caveat:")):
        return ""
    while text.startswith("[Image") and "]" in text:
        text = text[text.index("]") + 1:].strip()
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return text


def extract_text(content) -> str:
    """Pull plain text out of str / [{type|kind, text|data}] message content."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    texts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type") or block.get("kind")
        if kind in ("text", "input_text"):
            value = block.get("text", block.get("data", ""))
            if isinstance(value, str) and value:
                texts.append(value)
    if len(texts) > 1:  # drop pasted code-fence context blocks when real text exists
        non_fence = [t for t in texts if not t.lstrip().startswith("```")]
        texts = non_fence or texts
    return "\n".join(texts)


def derive_title(title: Optional[str], prompts: list[str]) -> Optional[str]:
    if title and title.strip() and title.strip().lower() != "new session":
        return " ".join(title.split())[:80]
    if prompts:
        return prompts[0][:40] + ("…" if len(prompts[0]) > 40 else "")
    return None


class _Window:
    """Track message count and first/last date inside the period."""

    def __init__(self, period: Period, tz: Optional[tzinfo]):
        self.period, self.tz = period, tz
        self.count = 0
        self.first: Optional[date] = None
        self.last: Optional[date] = None

    def accept(self, moment: Optional[datetime]) -> bool:
        if moment is None:
            return False
        local = moment.astimezone(self.tz).date()
        if not self.period.contains(local):
            return False
        self.count += 1
        self.first = local if self.first is None or local < self.first else self.first
        self.last = local if self.last is None or local > self.last else self.last
        return True


def _read_jsonl(path: Path):
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    yield record
    except OSError:
        return


def _mtime_date(path: Path, tz: Optional[tzinfo]) -> Optional[date]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz).date() if tz else \
            datetime.fromtimestamp(path.stat().st_mtime).date()
    except OSError:
        return None


# ---------------------------------------------------------------- claude

def _claude_is_human(record: dict) -> bool:
    if record.get("type") != "user" or record.get("isMeta") or record.get("isSidechain"):
        return False
    if "promptSource" in record:
        return record.get("promptSource") == "typed"
    origin = record.get("origin")
    if isinstance(origin, dict):
        return origin.get("kind") == "human"
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    return isinstance(content, list) and not any(
        isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def parse_claude(path: Path, period: Period, tz, max_len: int) -> Optional[Session]:
    window = _Window(period, tz)
    title = cwd = None
    branches: set[str] = set()
    prompts: list[str] = []
    for record in _read_jsonl(path):
        kind = record.get("type")
        if kind == "ai-title":
            title = record.get("aiTitle") or title
            continue
        if kind == "summary":
            title = title or record.get("summary")
            continue
        if not window.accept(parse_iso(record.get("timestamp"))):
            continue
        cwd = cwd or record.get("cwd")
        if record.get("gitBranch"):
            branches.add(record["gitBranch"])
        if _claude_is_human(record):
            text = clean_prompt(extract_text((record.get("message") or {}).get("content")), max_len)
            if text:
                prompts.append(text)
    if not window.count:
        return None
    return Session("claude", path.stem, derive_title(title, prompts), cwd, prompts,
                   sorted(branches), window.count, window.first, window.last)


# ---------------------------------------------------------------- codex

def parse_codex(path: Path, period: Period, tz, max_len: int) -> Optional[Session]:
    window = _Window(period, tz)
    cwd = None
    branches: set[str] = set()
    prompts: list[str] = []
    for record in _read_jsonl(path):
        payload = record.get("payload") or {}
        if record.get("type") == "session_meta":
            cwd = cwd or payload.get("cwd")
            branch = (payload.get("git") or {}).get("branch")
            if branch:
                branches.add(branch)
        if not window.accept(parse_iso(record.get("timestamp"))):
            continue
        if record.get("type") == "response_item" and payload.get("type") == "message" \
                and payload.get("role") == "user":
            text = extract_text(payload.get("content"))
            if text.lstrip().startswith(("<environment_context>", "<user_instructions>")):
                continue
            text = clean_prompt(text, max_len)
            if text:
                prompts.append(text)
    if not window.count:
        return None
    return Session("codex", path.stem.replace("rollout-", ""), derive_title(None, prompts), cwd,
                   prompts, sorted(branches), window.count, window.first, window.last)


# ---------------------------------------------------------------- kiro (IDE)

def parse_kiro(path: Path, period: Period, tz, max_len: int) -> Optional[Session]:
    day = _mtime_date(path, tz)
    if day is None or not period.contains(day):
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    history = data.get("history") or []
    prompts = []
    for turn in history:
        message = turn.get("message") if isinstance(turn, dict) else None
        if isinstance(message, dict) and message.get("role") == "user":
            text = clean_prompt(extract_text(message.get("content")), max_len)
            if text:
                prompts.append(text)
    if not history:
        return None
    return Session("kiro", path.stem, derive_title(data.get("title"), prompts),
                   data.get("workspacePath"), prompts, [], len(history), day, day, True)


# ---------------------------------------------------------------- kiro-cli

def parse_kiro_cli(path: Path, period: Period, tz, max_len: int) -> Optional[Session]:
    """path is the <id>.json metadata file; events live in the sibling .jsonl."""
    try:
        meta = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(meta, dict):
        return None
    events = path.with_suffix(".jsonl")
    window = _Window(period, tz)
    prompts: list[str] = []
    for record in _read_jsonl(events):
        data = record.get("data") or {}
        kind = record.get("kind")
        ts = ((data.get("meta") or {}).get("timestamp")) if isinstance(data, dict) else None
        if kind == "Prompt" and isinstance(ts, (int, float)):
            moment = datetime.fromtimestamp(ts).astimezone()
            if window.accept(moment):
                text = clean_prompt(extract_text(data.get("content")), max_len)
                if text:
                    prompts.append(text)
    if not window.count:
        # sessions without per-prompt timestamps: fall back to updated_at
        moment = parse_iso(meta.get("updated_at"))
        if not window.accept(moment):
            return None
    return Session("kiro-cli", str(meta.get("session_id") or path.stem),
                   derive_title(meta.get("title"), prompts), meta.get("cwd"), prompts, [],
                   window.count, window.first, window.last)


# ---------------------------------------------------------------- orchestration

_GLOBS: dict[str, tuple[str, Callable]] = {
    "claude": ("*/*.jsonl", parse_claude),
    "codex": ("*/*/*/rollout-*.jsonl", parse_codex),
    "kiro": ("*/*.json", parse_kiro),
    "kiro-cli": ("*.json", parse_kiro_cli),
}


def collect_agents(sources: list[str], period: Period, tz: Optional[tzinfo] = None,
                   max_prompt_len: int = 160, roots: Optional[dict] = None,
                   exclude: Optional[list[str]] = None,
                   keywords: Optional[list[str]] = None,
                   progress: Optional[Callable[[dict], None]] = None,
                   cancel: Optional[Callable[[], bool]] = None) -> tuple[list[Session], list[str], bool]:
    """Return (sessions, sources whose record directory does not exist, cancelled).

    `cancel` is polled per source and per record file; a cancelled run stops early
    and returns the sessions parsed so far.
    """
    defaults = default_roots()
    roots = roots or {}
    sessions: list[Session] = []
    missing: list[str] = []
    cancelled = False
    for source in sources:
        if cancel and cancel():
            cancelled = True
            break
        if source not in _GLOBS:
            continue
        root = Path(roots.get(source) or defaults[source]).expanduser()
        if not root.is_dir():
            missing.append(source)
            continue
        if progress:
            progress({"phase": "collect", "current": LABELS[source]})
        pattern, parser = _GLOBS[source]
        for path in sorted(root.glob(pattern)):
            if cancel and cancel():
                return sessions, missing, True
            if path.name == "sessions.json":
                continue
            session = parser(path, period, tz, max_prompt_len)
            if session is None or (not session.prompts and not session.title):
                continue
            session.prompts = list(dict.fromkeys(session.prompts))  # drop repeated prompts
            if any(p and p in (session.cwd or "") for p in exclude or []):
                continue
            if session.matches(keywords or []):
                sessions.append(session)
    return sessions, missing, cancelled
