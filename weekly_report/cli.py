"""Command-line interface."""
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from importlib import resources
from pathlib import Path
from typing import Optional

from weekly_report import __version__
from weekly_report.collectors import gather, render_activity
from weekly_report.config import ConfigError, expand, load_config, resolve_config_path
from weekly_report.mailer import MailError, send_agently, send_smtp
from weekly_report.markdown import markdown_to_html
from weekly_report.periods import Period, resolve_period, split_keywords
from weekly_report.providers import PRESETS, ProviderError, complete, resolve_provider
from weekly_report.report import (build_messages, find_previous_report, first_heading,
                                  load_template, report_filename, report_title)

COMMANDS = {"generate", "send", "init", "providers", "gui"}


def _err(message: str) -> None:
    print(f"weekly-report: {message}", file=sys.stderr)


def _info(message: str) -> None:
    print(message, file=sys.stderr)


# ------------------------------------------------------------------ argument parsing

def _period_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("period (default: last week)")
    group.add_argument("-w", "--week", choices=["this", "last", "prev"],
                       help="this / last / prev (the week before last)")
    group.add_argument("-m", "--month", type=int, help="monthly report for month 1-12")
    group.add_argument("--year", type=int, help="year for --month (default: most recent)")
    group.add_argument("--since", metavar="YYYY-MM-DD", help="custom range start")
    group.add_argument("--until", metavar="YYYY-MM-DD", help="custom range end (inclusive)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="weekly-report",
        description="Generate a weekly/monthly work report from your git commits and "
                    "AI-assistant sessions, using the LLM provider of your choice.")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="collect activity and write a report (default command)")
    _period_args(gen)
    gen.add_argument("-c", "--config", help="config file (default: ~/.config/weekly-report/config.toml)")
    gen.add_argument("-p", "--provider", help="provider name, e.g. deepseek, openai, anthropic, ollama")
    gen.add_argument("--model", help="override the provider's model")
    gen.add_argument("--lang", choices=["zh", "en"], help="report language")
    gen.add_argument("--topic", help="focused report on a topic, e.g. 'performance'")
    gen.add_argument("-k", "--keywords", help="filter keywords for --topic (default: the topic itself)")
    gen.add_argument("--template", help="custom Markdown template file")
    gen.add_argument("--previous", metavar="FILE", help="previous report to compare against")
    gen.add_argument("--no-previous", action="store_true", help="do not look up the previous report")
    gen.add_argument("-o", "--output", help="output file (default: <output_dir>/<period>.md)")
    gen.add_argument("--stdout", action="store_true", help="print the report instead of saving it")
    gen.add_argument("--dry-run", action="store_true",
                     help="print the prompt that would be sent, without calling any API")
    gen.add_argument("--send", action="store_true", help="e-mail the report after generating it")
    gen.add_argument("-y", "--yes", action="store_true", help="skip confirmation prompts")

    snd = sub.add_parser("send", help="e-mail an existing Markdown report")
    snd.add_argument("file", help="report file (.md)")
    snd.add_argument("-c", "--config")
    snd.add_argument("--to", action="append", help="recipient (repeatable, overrides config)")
    snd.add_argument("--subject", help="subject (default: first heading of the report)")
    snd.add_argument("--method", choices=["smtp", "agently"], help="override email.method")
    snd.add_argument("-y", "--yes", action="store_true")

    init = sub.add_parser("init", help="create a starter config file")
    init.add_argument("-c", "--config")
    init.add_argument("--force", action="store_true", help="overwrite an existing file")

    prov = sub.add_parser("providers", help="list providers and whether their API key is set")
    prov.add_argument("-c", "--config")

    gui = sub.add_parser("gui", help="open the graphical interface (needs the [gui] extra)")
    gui.add_argument("-c", "--config")
    gui.add_argument("--dev", action="store_true",
                     help="load the UI from the Vite dev server (development only)")
    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    if not argv or (argv[0] not in COMMANDS and argv[0] not in ("-h", "--help", "-V", "--version")):
        argv = ["generate", *argv]
    return build_parser().parse_args(argv)


# ------------------------------------------------------------------ helpers

def _ask(question: str, assume_yes: bool) -> str:
    if assume_yes:
        return "y"
    if not sys.stdin.isatty():
        raise MailError("confirmation required but stdin is not a terminal (use --yes)")
    try:
        return input(question).strip().lower()
    except EOFError:
        return ""


def _edit(path: Path) -> None:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    subprocess.call([*shlex.split(editor), str(path)])


def deliver(cfg: dict, markdown: str, subject: str, to: Optional[list[str]] = None,
            method: Optional[str] = None, assume_yes: bool = False) -> str:
    email = cfg["email"]
    method = method or email.get("method", "smtp")
    recipients = list(to or email.get("to") or [])
    cc = list(email.get("cc") or [])
    html_body = markdown_to_html(markdown, subject)

    if method == "agently":
        def confirm(summary: dict) -> bool:
            _info("\nagently-cli is ready to send:")
            for key in ("from", "to", "subject"):
                if summary.get(key):
                    value = summary[key]
                    _info(f"  {key:8}: {', '.join(value) if isinstance(value, list) else value}")
            return _ask("Send now? [y/N] ", assume_yes) in ("y", "yes")
        return send_agently(recipients, cc, subject, html_body, confirm)

    if method != "smtp":
        raise MailError(f"unknown email.method {method!r} (use smtp or agently)")
    if not recipients:
        raise MailError("no recipient: set email.to in the config or pass --to")
    _info(f"\nTo: {', '.join(recipients + cc)}\nSubject: {subject}")
    if _ask("Send now? [y/N] ", assume_yes) not in ("y", "yes"):
        raise MailError("cancelled, nothing was sent")
    return send_smtp(email.get("smtp") or {}, recipients, cc, subject, markdown, html_body)


def _subject(cfg: dict, title: str, period: Period) -> str:
    pattern = cfg["email"].get("subject") or ""
    if not pattern:
        return title
    return pattern.format(title=title, name=cfg.get("author_name", ""), label=period.label,
                          start=period.start.isoformat(), end=period.end.isoformat())


# ------------------------------------------------------------------ commands

def cmd_generate(args: argparse.Namespace) -> int:
    cfg, cfg_path = load_config(args.config)
    if args.lang:
        cfg["language"] = args.lang
    period = resolve_period(args.week, args.month, args.year, args.since, args.until,
                            default_week=cfg.get("default_week", "last"))
    topic = (args.topic or "").strip()
    keywords = split_keywords(args.keywords) or ([topic] if topic else [])

    if cfg_path is None:
        _info("No config file found, using defaults (run `weekly-report init` to create one).")
    _info(f"Period: {period.start} ~ {period.end}" + (f", topic: {topic}" if topic else ""))
    activity = gather(cfg, period, keywords)
    _info(f"Collected {activity.commit_count} commits from {len(activity.repos)} repos "
          f"({activity.repos_scanned} scanned) and {len(activity.sessions)} AI sessions.")
    if activity.is_empty:
        _err("no activity found for this period. Check git.roots / agents.sources in the config.")
        return 1

    activity_md = render_activity(activity, int(cfg.get("max_context_chars", 60000)))
    title = report_title(period, cfg.get("language", "zh"), cfg.get("author_name", ""), topic)
    output_dir = expand(cfg.get("output_dir", "~/weekly-reports"))

    previous_text = None
    if args.previous:
        previous_text = expand(args.previous).read_text(encoding="utf-8")
    elif not args.no_previous:
        previous_path = find_previous_report(output_dir, period, topic)
        if previous_path:
            _info(f"Previous report: {previous_path}")
            previous_text = previous_path.read_text(encoding="utf-8")

    template = load_template(cfg, period, args.template)
    system, user = build_messages(cfg, period, activity_md, template, title, previous_text,
                                  topic, keywords)

    if args.dry_run:
        print("===== SYSTEM =====\n" + system + "\n\n===== USER =====\n" + user)
        _info(f"\n(dry run: {len(system) + len(user)} characters, nothing was sent)")
        return 0

    provider = resolve_provider(args.provider or cfg.get("provider", "openai"), cfg, args.model)
    _info(f"Generating with {provider.name} ({provider.model}) …")
    report = complete(provider, system, user)
    if not report.lstrip().startswith("#"):
        report = f"# {title}\n\n{report}"
    report = report.rstrip() + "\n"

    if args.stdout:
        print(report)
        out_path = None
    else:
        out_path = expand(args.output) if args.output else output_dir / report_filename(period, topic)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(report)
        _info(f"Saved to {out_path}")

    if not args.send:
        return 0
    if out_path and not args.yes and sys.stdin.isatty():
        answer = _ask("Edit the report before sending? [e = open $EDITOR / Enter = no] ", False)
        if answer == "e":
            _edit(out_path)
            report = out_path.read_text(encoding="utf-8")
    _info(deliver(cfg, report, _subject(cfg, first_heading(report), period), assume_yes=args.yes))
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    cfg, _ = load_config(args.config)
    markdown = expand(args.file).read_text(encoding="utf-8")
    subject = args.subject or first_heading(markdown)
    _info(deliver(cfg, markdown, subject, to=args.to, method=args.method, assume_yes=args.yes))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    path = resolve_config_path(args.config)
    if path.exists() and not args.force:
        _err(f"{path} already exists (use --force to overwrite)")
        return 1
    example = resources.files("weekly_report").joinpath("config.example.toml").read_text(encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(example, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    print(f"Created {path}\nEdit git.roots and provider, then export your API key, e.g.\n"
          f"  export DEEPSEEK_API_KEY=sk-...\n  weekly-report --dry-run")
    return 0


def cmd_providers(args: argparse.Namespace) -> int:
    cfg, _ = load_config(args.config)
    names = sorted(set(PRESETS) | set(cfg.get("providers") or {}))
    default = cfg.get("provider", "openai")
    print(f"{'':2}{'name':12} {'type':10} {'model':28} key")
    for name in names:
        merged = {**PRESETS.get(name, {}), **(cfg.get("providers") or {}).get(name, {})}
        env = merged.get("api_key_env", "")
        if merged.get("api_key"):
            status = "set in config"
        elif not env:
            status = "not needed"
        else:
            status = f"{env} {'✓' if os.environ.get(env) else '✗ missing'}"
        mark = "* " if name == default else "  "
        print(f"{mark}{name:12} {merged.get('type', 'openai'):10} {str(merged.get('model', '')):28} {status}")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    from weekly_report.gui import run_gui   # lazy: the gui extra is optional
    return run_gui(args.config, dev=args.dev)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(list(sys.argv[1:] if argv is None else argv))
    handlers = {"generate": cmd_generate, "send": cmd_send, "init": cmd_init,
                "providers": cmd_providers, "gui": cmd_gui}
    try:
        return handlers[args.command](args)
    except (ConfigError, ProviderError, MailError, ValueError, OSError) as exc:
        _err(str(exc))
        return 1
    except KeyboardInterrupt:
        _err("interrupted")
        return 130
