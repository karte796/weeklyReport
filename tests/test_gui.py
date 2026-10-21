"""Bridge (GUI service layer) tests — no pywebview window needed."""
from conftest import make_records, make_repo

import pytest

import weekly_report.gui as gui_module
from weekly_report.config import read_user_toml
from weekly_report.gui import Bridge

WEEK_SPEC = {"since": "2026-10-12", "until": "2026-10-18"}


@pytest.fixture
def bridge(tmp_path, monkeypatch, home) -> Bridge:
    make_repo(tmp_path / "code" / "app")
    roots = make_records(tmp_path)
    agents_roots = "\n".join(f'{k} = "{v}"' for k, v in roots.items())
    config_file = tmp_path / "wr-config.toml"
    config_file.write_text(
        f'provider = "ollama"\nlanguage = "zh"\n'
        f'output_dir = "{tmp_path / "reports"}"\n'
        f'[git]\nroots = ["{tmp_path / "code"}"]\n'
        f"[agents]\n[agents.roots]\n{agents_roots}\n",
        encoding="utf-8")
    monkeypatch.setenv("WEEKLY_REPORT_CONFIG", str(config_file))
    return Bridge(None)


def test_get_and_save_config_roundtrip(bridge, tmp_path):
    state = bridge.get_config()
    assert state["exists"] and state["config"]["provider"] == "ollama"
    assert state["config_path"].endswith("wr-config.toml")

    result = bridge.save_config({"language": "en", "author_name": "Me",
                                 "custom_section": {"keep": True}})
    assert result["ok"]
    raw = read_user_toml(tmp_path / "wr-config.toml")
    assert raw["language"] == "en" and raw["author_name"] == "Me"
    assert raw["provider"] == "ollama"            # untouched keys survive
    assert raw["custom_section"] == {"keep": True}  # unknown sections survive


def test_collect_dto_and_progress(bridge):
    events: list[dict] = []
    bridge._notify = events.append
    dto = bridge.collect(WEEK_SPEC)
    assert not dto["cancelled"] and dto["commit_count"] == 1
    assert dto["repos"][0]["name"] == "app"
    assert dto["repos"][0]["commits"][0]["subject"] == "feat: add search"
    assert {session["source"] for session in dto["sessions"]} == {"claude", "codex", "kiro", "kiro-cli"}
    assert dto["sessions"][0]["id"].count(":") == 1
    assert {event["source"] for event in events} == {"git", "agents"}


def test_generate_filters_selection(bridge, monkeypatch):
    bridge.collect(WEEK_SPEC)
    captured: list[tuple[str, str]] = []

    def fake_complete(provider, system, user):
        captured.append((system, user))
        return "# 周报\n\n## 本周工作\n- 修复登录"

    monkeypatch.setattr(gui_module, "complete", fake_complete)

    selection = {"session_ids": ["claude:s1"], "repo_paths": [bridge._activity.repos[0].key]}
    result = bridge.generate(selection, {"provider": "ollama", "previous": "none"})
    assert result["report"].startswith("# ")
    assert result["filename"].endswith(".md")
    system, user = captured[-1]
    assert "why does login fail" in user and "feat: add search" in user
    assert "add pagination" not in user and "split store" not in user   # deselected

    everything = {"session_ids": [session.key for session in bridge._activity.sessions],
                  "repo_paths": [repo.key for repo in bridge._activity.repos]}
    bridge.generate(everything, {"previous": "none"})
    assert "add pagination" in captured[-1][1]

    with pytest.raises(ValueError):
        bridge.generate({"session_ids": [], "repo_paths": []}, {"previous": "none"})


def test_generate_needs_collect_first(home):
    fresh = Bridge(None)
    with pytest.raises(RuntimeError):
        fresh.generate({"session_ids": ["x"], "repo_paths": []}, {})


def test_list_providers_status(bridge, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    providers = {item["name"]: item for item in bridge.list_providers()["providers"]}
    assert providers["ollama"]["is_default"] and providers["ollama"]["key_status"] == "none"
    assert providers["deepseek"]["key_status"] == "missing"


def test_save_and_find_previous_report(bridge, tmp_path):
    bridge.save_report("# 旧周报\n\n内容", "2026-09-01_2026-09-07.md")
    found = bridge.previous_report(WEEK_SPEC)
    assert found["path"] and found["path"].endswith("2026-09-01_2026-09-07.md")
    assert "旧周报" in found["content"]
    assert bridge.previous_report({"since": "2026-01-01", "until": "2026-01-07"})["path"] is None


def test_send_report_validates(bridge):
    with pytest.raises(ValueError):   # smtp without a recipient
        bridge.send_report("# 报告\n\nx", {"method": "smtp"})
    with pytest.raises(ValueError):   # unknown method
        bridge.send_report("# 报告\n\nx", {"method": "pigeon"})


def test_cancel_collect_stops(bridge):
    def cancel_on_first_progress(event: dict) -> None:   # like pressing the button mid-run
        bridge._cancel.set()
    bridge._notify = cancel_on_first_progress
    dto = bridge.collect(WEEK_SPEC)
    assert dto["cancelled"] and dto["repos"] == []
