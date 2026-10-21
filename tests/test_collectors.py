from datetime import timezone

from conftest import make_records, make_repo

from weekly_report.collectors import Activity, gather, render_activity
from weekly_report.collectors.agents import clean_prompt, collect_agents, parse_iso
from weekly_report.collectors.git import collect_git
from weekly_report.config import DEFAULTS, deep_merge


def test_all_agent_sources(tmp_path, week):
    roots = make_records(tmp_path)
    sessions, missing = collect_agents(list(roots), week, tz=timezone.utc, roots=roots)
    assert missing == []
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
    sessions, _ = collect_agents(list(roots), week, tz=timezone.utc, roots=roots, keywords=["pagination"])
    assert [s.source for s in sessions] == ["codex"]
    sessions, _ = collect_agents(list(roots), week, tz=timezone.utc, roots=roots, exclude=["code/app"])
    assert "claude" not in {s.source for s in sessions}
    _, missing = collect_agents(["claude"], week, roots={"claude": str(tmp_path / "nope")})
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
    repos, scanned = collect_git([tmp_path / "code"], week)
    assert scanned == 2
    found = {r.name: [c.subject for c in r.commits] for r in repos}
    # each repo is filtered by its own user.email; the out-of-order old commit is excluded
    assert found == {"app": ["feat: add search"], "other": ["feat: add search"]}

    repos, _ = collect_git([tmp_path / "code"], week, authors=["someone@example.com"])
    assert [r.name for r in repos] == ["other"]
    repos, _ = collect_git([tmp_path / "code"], week, keywords=["nothing"])
    assert repos == []


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
