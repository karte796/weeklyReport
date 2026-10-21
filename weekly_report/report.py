"""Prompt construction, report titles, file naming and previous-report lookup."""
from __future__ import annotations

import re
from importlib import resources
from pathlib import Path
from typing import Optional

from weekly_report.config import expand
from weekly_report.periods import Period

MAX_PREVIOUS_CHARS = 8000

_TEXT = {
    "zh": {
        "weekly": "周报", "monthly": "月报", "custom": "工作报告", "topic": "{topic}专项",
        "language": "简体中文",
    },
    "en": {
        "weekly": "Weekly Report", "monthly": "Monthly Report", "custom": "Work Report",
        "topic": "{topic}", "language": "English",
    },
}


def report_kind(period: Period) -> str:
    return "monthly" if period.kind == "monthly" else "weekly"


def report_title(period: Period, language: str, name: str = "", topic: str = "") -> str:
    text = _TEXT.get(language, _TEXT["en"])
    span = f"{period.start:%m.%d} ~ {period.end:%m.%d}"
    if period.kind == "monthly":
        span = f"{period.start.year}-{period.start.month:02d}"
    kind = text[period.kind]
    if topic:
        kind = text["topic"].format(topic=topic) + ("周报" if language == "zh" else f" {kind}")
    who = f" - {name}" if name else ""
    return f"{kind}{who} ({span})" if language != "zh" else f"{kind}{who}（{span}）"


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value.strip()).strip("-")
    return value[:40]


def report_filename(period: Period, topic: str = "") -> str:
    suffix = f"-{slugify(topic)}" if topic else ""
    return f"{period.label}{suffix}.md"


def _label_pattern(period: Period, topic: str) -> re.Pattern:
    suffix = re.escape(f"-{slugify(topic)}") if topic else ""
    if period.kind == "monthly":
        return re.compile(rf"^(\d{{4}}-\d{{2}}){suffix}\.md$")
    if period.kind == "weekly":
        return re.compile(rf"^(\d{{4}}-W\d{{2}}){suffix}\.md$")
    return re.compile(rf"^(\d{{4}}-\d{{2}}-\d{{2}})_\d{{4}}-\d{{2}}-\d{{2}}{suffix}\.md$")


def find_previous_report(output_dir: Path, period: Period, topic: str = "") -> Optional[Path]:
    """Latest report of the same kind (and topic) whose label sorts before this period."""
    if not output_dir.is_dir():
        return None
    pattern = _label_pattern(period, topic)
    current = period.label if period.kind != "custom" else period.start.isoformat()
    candidates = []
    for path in output_dir.iterdir():
        match = pattern.match(path.name)
        if match and match.group(1) < current:
            candidates.append((match.group(1), path))
    return max(candidates)[1] if candidates else None


def load_template(cfg: dict, period: Period, override: Optional[str] = None) -> str:
    custom = override or cfg.get("template") or ""
    if custom:
        return expand(custom).read_text(encoding="utf-8")
    language = cfg.get("language", "zh")
    language = language if language in _TEXT else "en"
    name = f"{report_kind(period)}.{language}.md"
    return resources.files("weekly_report").joinpath("templates", name).read_text(encoding="utf-8")


def build_messages(cfg: dict, period: Period, activity_md: str, template: str, title: str,
                   previous: Optional[str] = None, topic: str = "",
                   keywords: Optional[list[str]] = None) -> tuple[str, str]:
    language = _TEXT.get(cfg.get("language", "zh"), _TEXT["en"])["language"]
    rules = [
        "You are an assistant that writes concise, factual work reports for a software engineer.",
        f"Write the report in {language}. Output Markdown only, no preamble and no code fences.",
        "Follow the template's section structure. Replace the HTML comments with content and "
        "remove the comments. Drop a section only if the template says it is conditional and "
        "its condition is not met.",
        "Git commits are the primary evidence of output. Use AI-assistant sessions to add "
        "context and work that was not committed (research, debugging, design, reviews).",
        "Merge related items by project or theme; never list the same work twice. Translate "
        "commit messages into readable outcomes instead of copying hashes or raw subjects.",
        "Do not invent work, numbers, people or dates that are not supported by the data. "
        "If the data is thin, keep the report short.",
        "Omit secrets, tokens, passwords, internal URLs and personal data if they appear in the data.",
        "Base 'next' plans on unfinished work visible in the data; keep them brief and realistic.",
    ]
    if topic:
        rules.append(f"This is a focused report on the topic \"{topic}\" "
                     f"(keywords: {', '.join(keywords or [topic])}). Only include related work.")
    if cfg.get("extra_instructions"):
        rules.append(str(cfg["extra_instructions"]))
    system = "\n".join(f"- {r}" for r in rules)

    template = template.replace("{title}", title)
    parts = [
        f"Report period: {period.start.isoformat()} to {period.end.isoformat()} ({period.kind}).",
        f"Report title: {title}",
        f"<template>\n{template.strip()}\n</template>",
    ]
    if previous:
        clipped = previous.strip()[:MAX_PREVIOUS_CHARS]
        parts.append("The previous report is below; compare its plan with this period's work.\n"
                     f"<previous_report>\n{clipped}\n</previous_report>")
    else:
        parts.append("No previous report is available; drop the plan-review section.")
    parts.append(f"<activity>\n{activity_md.strip()}\n</activity>")
    return system, "\n\n".join(parts)
