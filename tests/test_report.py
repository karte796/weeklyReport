from datetime import date

from weekly_report.config import DEFAULTS, deep_merge
from weekly_report.markdown import markdown_to_html
from weekly_report.periods import Period, resolve_month
from weekly_report.report import (build_messages, find_previous_report, load_template,
                                  report_filename, report_title)


def test_titles(week):
    assert report_title(week, "zh") == "周报（10.12 ~ 10.18）"
    assert report_title(week, "en", "Alice") == "Weekly Report - Alice (10.12 ~ 10.18)"
    assert report_title(week, "zh", topic="性能") == "性能专项周报（10.12 ~ 10.18）"
    assert report_title(resolve_month(9, 2026), "zh", "张三") == "月报 - 张三（2026-09）"


def test_filenames(week):
    assert report_filename(week) == "2026-W42.md"
    assert report_filename(week, "性能 优化") == "2026-W42-性能-优化.md"


def test_find_previous_report(tmp_path, week):
    for name in ["2026-W40.md", "2026-W41.md", "2026-W42.md", "2026-W43.md", "2026-09.md",
                 "2026-W41-perf.md", "notes.md"]:
        (tmp_path / name).write_text("x")
    assert find_previous_report(tmp_path, week).name == "2026-W41.md"
    assert find_previous_report(tmp_path, week, "perf").name == "2026-W41-perf.md"
    assert find_previous_report(tmp_path, resolve_month(10, 2026)).name == "2026-09.md"
    assert find_previous_report(tmp_path / "missing", week) is None


def test_templates_and_messages(tmp_path, week):
    cfg = deep_merge(DEFAULTS, {"language": "en", "extra_instructions": "Be brief."})
    template = load_template(cfg, week)
    assert "## Done this week" in template
    assert "## 本月工作总结" in load_template(DEFAULTS, resolve_month(9, 2026))
    custom = tmp_path / "t.md"
    custom.write_text("# {title}\n## Custom")
    assert load_template(cfg, week, str(custom)).endswith("## Custom")

    system, user = build_messages(cfg, week, "## Git\n- x", template, "T", previous="# Last\n- plan A",
                                  topic="perf", keywords=["perf", "lcp"])
    assert "English" in system and "Be brief." in system and "perf, lcp" in system
    assert "<previous_report>\n# Last" in user and "<activity>\n## Git" in user
    assert "# T" in user and "{title}" not in user
    _, user = build_messages(cfg, week, "data", template, "T")
    assert "No previous report" in user


def test_markdown_to_html():
    page = markdown_to_html(
        "# Title\n<!-- hidden -->\n## Done\n- **bold** `a<b>`\n  - nested [link](https://x.test)\n"
        "1. one\n\n> quote\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nplain *it* <script>", "T")
    assert "<h1>Title</h1>" in page and "hidden" not in page
    assert "<strong>bold</strong> <code>a&lt;b&gt;</code>" in page
    assert '<ul><li>nested <a href="https://x.test">link</a>' in page
    assert "<ol><li>one</li></ol>" in page
    assert "<blockquote>quote</blockquote>" in page
    assert "<td>1</td><td>2</td>" in page
    assert "<em>it</em> &lt;script&gt;" in page


def test_custom_period_title():
    period = Period("custom", date(2026, 10, 1), date(2026, 10, 5))
    assert report_title(period, "en") == "Work Report (10.01 ~ 10.05)"
