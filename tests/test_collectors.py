from datetime import timezone

from conftest import make_records, make_repo

from weekly_report.collectors import Activity, filter_activity, gather, render_activity
from weekly_report.collectors.agents import clean_prompt, collect_agents, parse_iso
from weekly_report.collectors.git import collect_git
from weekly_report.config import DEFAULTS, deep_merge


def test_all_agent_sources(tmp_path, week):
    roots = make_records(tmp_path)
    sessions, missing, cancelled = collect_agents(list(roots), week, tz=timezone.utc, roots=roots)
    assert missing == [] and not cancelled
    by_source = {s.source: s for s in sessions}
    assert set(by_source) == {"claude", "codex", "kiro", "kiro-cli"}

    claude = by_source["claude"]
    assert claude.title == "Fix login bug"
    assert claude.prompts == ["why does login fail"]          # tool_result and old prompt dropped
    assert claude.branches == ["fix/login"] and claude.message_count == 3

    codex = by_source["codex"]
    assert codex.prompts == ["add pagination"]               # env context dropped, duplicate removed
    assert codex.branches == ["main"] and codex.project == "code/api"

    assert by_source["kiro"].date_approx and by_source["kiro"].prompts == ["split store"]
    assert by_source["kiro-cli"].title == "Write release notes"
    assert by_source["kiro-cli"].prompts == ["draft notes for v2"]


def test_agent_filters_and_missing(tmp_path, week):
    roots = make_records(tmp_path)
    sessions, _, _ = collect_agents(list(roots), week, tz=timezone.utc, roots=roots,
                                    keywords=["pagination"])
    assert [s.source for s in sessions] == ["codex"]
    sessions, _, _ = collect_agents(list(roots), week, tz=timezone.utc, roots=roots,
                                    exclude=["code/app"])
    assert "claude" not in {s.source for s in sessions}
    _, missing, _ = collect_agents(["claude"], week, roots={"claude": str(tmp_path / "nope")})
    assert missing == ["claude"]


def test_parse_iso_and_clean_prompt():
    assert parse_iso("2026-10-13T02:00:00.1234567Z").tzinfo is not None
    assert parse_iso("2026-10-13T02:00:00").tzinfo is timezone.utc
    assert parse_iso("garbage") is None
    assert clean_prompt("<command-name>/clear</command-name>", 50) == ""
    assert clean_prompt("[Image #1] look   here", 50) == "look here"
    assert clean_prompt("x" * 20, 10) == "x" * 10 + "…"


def test_git_collects_own_commits_only(tmp_path, week):
    make_repo(tmp_path / "code" / "app", commits=(
        ("2026-10-13T10:00:00", "feat: add search"),
        ("2026-10-01T10:00:00", "chore: old"),
    ))
    make_repo(tmp_path / "code" / "other", email="someone@example.com")
    make_repo(tmp_path / "code" / "app" / "node_modules" / "dep")  # pruned
    repos, scanned, cancelled = collect_git([tmp_path / "code"], week)
    assert scanned == 2 and not cancelled
    found = {r.name: [c.subject for c in r.commits] for r in repos}
    # each repo is filtered by its own user.email; the out-of-order old commit is excluded
    assert found == {"app": ["feat: add search"], "other": ["feat: add search"]}

    repos, _, _ = collect_git([tmp_path / "code"], week, authors=["someone@example.com"])
    assert [r.name for r in repos] == ["other"]
    repos, _, _ = collect_git([tmp_path / "code"], week, keywords=["nothing"])
    assert repos == []


def test_git_progress_and_cancel(tmp_path, week):
    make_repo(tmp_path / "code" / "app")
    make_repo(tmp_path / "code" / "api")
    events: list[dict] = []
    repos, scanned, cancelled = collect_git([tmp_path / "code"], week, progress=events.append)
    assert not cancelled and scanned == 2 and len(repos) == 2
    phases = {event["phase"] for event in events}
    assert {"discover", "collect"} <= phases
    collecting = [event for event in events if event["phase"] == "collect"]
    assert [event["total"] for event in collecting] == [2, 2]

    # discovery checks once per root, then once per repository: trips on the second repo
    polls = {"count": 0}

    def cancel_soon() -> bool:
        polls["count"] += 1
        return polls["count"] > 2

    repos, _, cancelled = collect_git([tmp_path / "code"], week, cancel=cancel_soon)
    assert cancelled and len(repos) == 1


def test_gather_cancel_stops_early(tmp_path, week):
    make_repo(tmp_path / "code" / "app")
    roots = make_records(tmp_path)
    cfg = deep_merge(DEFAULTS, {"git": {"roots": [str(tmp_path / "code")]},
                                "agents": {"roots": {k: str(v) for k, v in roots.items()}}})
    activity = gather(cfg, week, [], cancel=lambda: True)
    assert activity.cancelled and activity.repos == [] and activity.sessions == []

    seen: list[dict] = []
    gather(cfg, week, [], progress=seen.append)
    assert {event["source"] for event in seen} == {"git", "agents"}


def test_gather_and_render_respects_limits(tmp_path, week):
    make_repo(tmp_path / "code" / "app")
    roots = make_records(tmp_path)
    cfg = deep_merge(DEFAULTS, {"git": {"roots": [str(tmp_path / "code")]},
                                "agents": {"roots": {k: str(v) for k, v in roots.items()}}})
    activity = gather(cfg, week, [])
    text = render_activity(activity)
    assert "feat: add search" in text and "[Claude Code] Fix login bug" in text
    assert "why does login fail" in text

    activity.include_prompts = False
    assert "why does login fail" not in render_activity(activity)

    activity.include_prompts = True
    small = render_activity(activity, max_chars=300)
    assert len(small) <= 300 + 60


def test_render_empty(week):
    activity = Activity(week)
    assert activity.is_empty
    assert "no commits" in render_activity(activity)


def test_filter_activity_selects_subsets(tmp_path, week):
    make_repo(tmp_path / "code" / "app")
    roots = make_records(tmp_path)
    cfg = deep_merge(DEFAULTS, {"git": {"roots": [str(tmp_path / "code")]},
                                "agents": {"roots": {k: str(v) for k, v in roots.items()}}})
    activity = gather(cfg, week, [])
    repo_keys = [repo.key for repo in activity.repos]
    session_keys = [session.key for session in activity.sessions]

    filtered = filter_activity(activity, {session_keys[0]}, set(repo_keys[:1]))
    assert [session.key for session in filtered.sessions] == [session_keys[0]]
    assert [repo.key for repo in filtered.repos] == repo_keys[:1]
    assert not filtered.is_empty and not filtered.cancelled
    assert len(activity.sessions) == len(session_keys)  # the original is untouched

    nothing = filter_activity(activity, set(), set())
    assert nothing.is_empty
    assert "no commits" in render_activity(nothing) and "no AI assistant sessions" in render_activity(nothing)
