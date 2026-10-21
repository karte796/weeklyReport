"""Gather all activity for a period and render it as Markdown for the model."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import tzinfo
from typing import Optional

from weekly_report.collectors.agents import LABELS, Session, collect_agents
from weekly_report.collectors.git import RepoCommits, collect_git
from weekly_report.config import expand
from weekly_report.periods import Period


@dataclass
class Activity:
    period: Period
    repos: list[RepoCommits] = field(default_factory=list)
    repos_scanned: int = 0
    sessions: list[Session] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)
    git_enabled: bool = True
    agents_enabled: bool = True
    include_prompts: bool = True
    max_prompts_per_session: int = 8

    @property
    def commit_count(self) -> int:
        return sum(len(r.commits) for r in self.repos)

    @property
    def is_empty(self) -> bool:
        return not self.repos and not self.sessions


def gather(cfg: dict, period: Period, keywords: list[str], tz: Optional[tzinfo] = None) -> Activity:
    git_cfg, agents_cfg = cfg["git"], cfg["agents"]
    activity = Activity(period, git_enabled=bool(git_cfg["enabled"]),
                        agents_enabled=bool(agents_cfg["enabled"]),
                        include_prompts=bool(agents_cfg["include_prompts"]),
                        max_prompts_per_session=int(agents_cfg["max_prompts_per_session"]))
    if activity.git_enabled:
        activity.repos, activity.repos_scanned = collect_git(
            [expand(r) for r in git_cfg["roots"]], period,
            authors=list(git_cfg["authors"]), max_depth=int(git_cfg["max_depth"]),
            exclude=list(git_cfg["exclude"]), keywords=keywords)
    if activity.agents_enabled:
        activity.sessions, activity.missing_sources = collect_agents(
            list(agents_cfg["sources"]), period, tz=tz,
            max_prompt_len=int(agents_cfg["max_prompt_len"]),
            roots=dict(agents_cfg.get("roots") or {}),
            exclude=list(agents_cfg["exclude"]), keywords=keywords)
    return activity


def render_git(activity: Activity) -> str:
    lines = [f"## Git commits ({activity.commit_count} commits in {len(activity.repos)} "
             f"of {activity.repos_scanned} scanned repositories)"]
    if not activity.repos:
        lines.append("\n(no commits in this period)")
    for repo in activity.repos:
        lines.append(f"\n### {repo.name} ({len(repo.commits)})")
        lines += [f"- {c.date} {c.subject} ({c.short_hash})" for c in repo.commits]
    return "\n".join(lines)


def _date_span(session: Session) -> str:
    if not session.first_date:
        return ""
    approx = "≈" if session.date_approx else ""
    first = session.first_date.strftime("%m-%d")
    if session.last_date and session.last_date != session.first_date:
        return f"{approx}{first}~{session.last_date.strftime('%m-%d')}"
    return approx + first


def render_sessions(activity: Activity, prompt_limit: Optional[int] = None) -> str:
    limit = activity.max_prompts_per_session if prompt_limit is None else prompt_limit
    sessions = activity.sessions
    lines = [f"## AI assistant sessions ({len(sessions)} sessions)"]
    if any(s.date_approx for s in sessions):
        lines.append("> Dates marked ≈ come from file modification time (approximate).")
    if activity.missing_sources:
        lines.append("> Not found on this machine: "
                     + ", ".join(LABELS[s] for s in activity.missing_sources))
    if not sessions:
        lines.append("\n(no AI assistant sessions in this period)")
    by_project: dict[str, list[Session]] = {}
    for session in sessions:
        by_project.setdefault(session.project, []).append(session)
    for project in sorted(by_project):
        lines.append(f"\n### {project}")
        for s in sorted(by_project[project], key=lambda x: x.first_date or activity.period.start):
            meta = ", ".join(filter(None, [_date_span(s),
                                           f"branch {', '.join(s.branches)}" if s.branches else "",
                                           f"{s.message_count} messages"]))
            lines.append(f"- [{LABELS[s.source]}] {s.title or '(untitled)'} ({meta})")
            if activity.include_prompts and limit > 0:
                shown = s.prompts[:limit]
                lines += [f"  - {p}" for p in shown]
                if len(s.prompts) > len(shown):
                    lines.append(f"  - … {len(s.prompts) - len(shown)} more prompts")
    return "\n".join(lines)


def render_activity(activity: Activity, max_chars: int = 60000) -> str:
    """Render activity, shrinking per-session prompt lists until it fits max_chars."""
    parts = []
    if activity.git_enabled:
        parts.append(render_git(activity))
    limit = activity.max_prompts_per_session
    while True:
        session_part = render_sessions(activity, limit) if activity.agents_enabled else ""
        text = "\n\n".join(filter(None, parts + [session_part]))
        if len(text) <= max_chars or limit <= 0:
            break
        limit = limit // 2 if limit > 1 else 0
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n\n(… truncated to fit the context limit)"
    return text
