import json
import smtplib
import subprocess

import pytest
from conftest import make_records, make_repo

from weekly_report import cli, mailer
from weekly_report.mailer import MailError


def write_config(home, extra=""):
    roots = make_records(home / "records")
    make_repo(home / "code" / "app", commits=(("2026-10-13T10:00:00", "feat: add search"),))
    agent_roots = "\n".join(f'"{k}" = "{v}"' for k, v in roots.items())
    path = home / "config.toml"
    path.write_text(f"""
provider = "gw"
output_dir = "{home / 'reports'}"
[git]
roots = ["{home / 'code'}"]
[agents.roots]
{agent_roots}
[providers.gw]
type = "openai"
base_url = "https://gw.test/v1"
model = "m"
api_key = "k"
{extra}
""")
    return path


@pytest.fixture
def fake_llm(monkeypatch):
    prompts = []

    def fake_complete(provider, system, user):
        prompts.append(user)
        return "# 周报（10.12 ~ 10.18）\n\n## 本周完成\n- 完成搜索功能"
    monkeypatch.setattr(cli, "complete", fake_complete)
    return prompts


PERIOD = ["--since", "2026-10-12", "--until", "2026-10-18"]


def test_dry_run_prints_prompt_without_calling_api(home, capsys, fake_llm):
    cfg = write_config(home)
    assert cli.main(["--config", str(cfg), *PERIOD, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "feat: add search" in out and "Fix login bug" in out
    assert fake_llm == []


def test_generate_writes_file_and_uses_previous(home, capsys, fake_llm):
    cfg = write_config(home)
    reports = home / "reports"
    reports.mkdir()
    (reports / "2026-10-05_2026-10-11.md").write_text("# Last\n## 下周计划\n- 搜索功能")
    assert cli.main(["--config", str(cfg), *PERIOD]) == 0
    saved = reports / "2026-10-12_2026-10-18.md"
    assert saved.read_text().startswith("# 周报")
    assert "<previous_report>" in fake_llm[-1] and "搜索功能" in fake_llm[-1]


def test_generate_no_activity(home, capsys, fake_llm):
    cfg = write_config(home)
    assert cli.main(["--config", str(cfg), "--since", "2020-01-01", "--until", "2020-01-07"]) == 1
    assert "no activity" in capsys.readouterr().err


def test_errors_are_friendly(home, capsys):
    assert cli.main(["--config", str(home / "missing.toml")]) == 1
    assert "config file not found" in capsys.readouterr().err
    bad = home / "bad.toml"
    bad.write_text("provider = ")
    assert cli.main(["--config", str(bad)]) == 1
    assert "invalid TOML" in capsys.readouterr().err


def test_init_and_providers(home, capsys, monkeypatch):
    target = home / "cfg" / "config.toml"
    assert cli.main(["init", "--config", str(target)]) == 0
    assert target.exists() and (target.stat().st_mode & 0o777) == 0o600
    assert cli.main(["init", "--config", str(target)]) == 1
    monkeypatch.setenv("DEEPSEEK_API_KEY", "x")
    capsys.readouterr()
    assert cli.main(["providers", "--config", str(target)]) == 0
    out = capsys.readouterr().out
    assert "* deepseek" in out and "DEEPSEEK_API_KEY ✓" in out and "ollama" in out


def test_send_smtp(home, monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, context=None, timeout=None):
            sent["host"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, message, to_addrs):
            sent["to"] = to_addrs
            sent["subject"] = message["Subject"]
            sent["html"] = message.get_body(("html",)).get_content()

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setenv("SMTP_PASSWORD", "app-pass")
    cfg = write_config(home, """
[email]
to = ["boss@example.com"]
cc = ["me@example.com"]
[email.smtp]
host = "smtp.example.com"
username = "me@example.com"
""")
    report = home / "r.md"
    report.write_text("# 周报（10.12 ~ 10.18）\n- **done**")
    assert cli.main(["send", str(report), "--config", str(cfg), "--yes"]) == 0
    assert sent["host"] == ("smtp.example.com", 465)
    assert sent["login"] == ("me@example.com", "app-pass")
    assert sent["to"] == ["boss@example.com", "me@example.com"]
    assert sent["subject"] == "周报（10.12 ~ 10.18）"
    assert "<strong>done</strong>" in sent["html"]


def test_send_requires_confirmation_without_tty(home, capsys, monkeypatch):
    cfg = write_config(home, '[email]\nto = ["a@example.com"]\n[email.smtp]\nhost = "h"\nfrom = "x@example.com"')
    report = home / "r.md"
    report.write_text("# R")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert cli.main(["send", str(report), "--config", str(cfg)]) == 1
    assert "use --yes" in capsys.readouterr().err


class FakeAgently:
    """Simulates agently-cli: +me, then the two-phase +send."""

    def __init__(self):
        self.calls = []

    def __call__(self, argv, capture_output, text, cwd=None, timeout=None):
        args = argv[1:]
        self.calls.append((args, cwd))
        if args == ["+me"]:
            data = {"ok": True, "data": {"aliases": [{"email": "me@agent.qq.com", "is_primary": True}]}}
        elif "--confirmation-token" in args:
            data = {"ok": True, "data": {"queued": True}}
        else:
            assert (cwd and open(f"{cwd}/body.html", encoding="utf-8").read().startswith("<!DOCTYPE"))
            data = {"ok": True, "data": {"confirmation_required": True, "confirmation_token": "ctk_1",
                                         "summary": {"to": ["me@agent.qq.com"], "subject": "S"}}}
        return subprocess.CompletedProcess(argv, 0, json.dumps(data), "")


def test_agently_two_phase(monkeypatch):
    fake = FakeAgently()
    monkeypatch.setattr(mailer.shutil, "which", lambda name: "/bin/agently-cli")
    monkeypatch.setattr(mailer.subprocess, "run", fake)
    summaries = []
    result = mailer.send_agently([], [], "S", "<!DOCTYPE html>", lambda s: summaries.append(s) or True)
    assert "me@agent.qq.com" in result
    assert summaries == [{"to": ["me@agent.qq.com"], "subject": "S"}]
    assert fake.calls[-1][0][-2:] == ["--confirmation-token", "ctk_1"]


def test_agently_cancel_and_auth_error(monkeypatch):
    fake = FakeAgently()
    monkeypatch.setattr(mailer.shutil, "which", lambda name: "/bin/agently-cli")
    monkeypatch.setattr(mailer.subprocess, "run", fake)
    with pytest.raises(MailError, match="cancelled"):
        mailer.send_agently(["a@x.com"], [], "S", "<!DOCTYPE html>", lambda s: False)
    assert not any("--confirmation-token" in c[0] for c in fake.calls)

    def expired(argv, **kwargs):
        body = json.dumps({"ok": False, "error": {"message": "refresh token is invalid or expired, "
                                                             "please re-authenticate"}})
        return subprocess.CompletedProcess(argv, 3, body, "")
    monkeypatch.setattr(mailer.subprocess, "run", expired)
    with pytest.raises(MailError, match="agently-cli auth login"):
        mailer.agently_self_address()


def test_agently_missing(monkeypatch):
    monkeypatch.setattr(mailer.shutil, "which", lambda name: None)
    with pytest.raises(MailError, match="npm install"):
        mailer.agently_self_address()
