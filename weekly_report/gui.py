"""Optional pywebview GUI (WKWebView on macOS). Install: pip install "weekly-report[gui]".

The Bridge class is the JS-facing service object pywebview exposes as
window.pywebview.api; it deliberately imports pywebview/tomli-w lazily so the
core package (and these tests) work without the gui extra installed.
"""
from __future__ import annotations

import json
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional

from weekly_report import __version__
from weekly_report.collectors import Activity, filter_activity, gather, render_activity
from weekly_report.collectors.agents import LABELS
from weekly_report.config import (ConfigError, deep_merge, expand, load_config,
                                  read_user_toml, resolve_config_path)
from weekly_report.markdown import markdown_to_html
from weekly_report.periods import Period, resolve_period, split_keywords
from weekly_report.providers import PRESETS, complete, resolve_provider
from weekly_report.report import (build_messages, find_previous_report, first_heading,
                                  load_template, report_filename, report_title)


class Bridge:
    """Service object exposed to the UI. Methods run on pywebview worker threads.

    All public methods return JSON-serialisable dicts; raised errors surface as
    rejected promises on the JS side. Usable without pywebview (tests do this).
    """

    def __init__(self, config_path: Optional[str] = None,
                 notify: Optional[Callable[[dict], None]] = None) -> None:
        self._config_arg = config_path
        self._notify = notify            # progress-event sink; wired to evaluate_js by run_gui
        self._cancel = threading.Event()
        self._activity: Optional[Activity] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------ config

    def get_config(self) -> dict:
        cfg, cfg_path = load_config(self._config_arg)
        return {"config": cfg, "config_path": str(cfg_path) if cfg_path else None,
                "exists": cfg_path is not None, "version": __version__}

    def save_config(self, data: dict) -> dict:
        """Write form-managed keys back into the user TOML (other keys are kept)."""
        try:
            import tomli_w
        except ImportError as exc:  # pragma: no cover - only without the gui extra
            raise RuntimeError('tomli-w is not installed. Reinstall with the gui extra: '
                               'pipx install "weekly-report[gui] @ git+https://github.com/karte796/weeklyReport.git"') from exc
        cfg_path = resolve_config_path(self._config_arg)
        existing = read_user_toml(cfg_path) if cfg_path.is_file() else {}
        merged = deep_merge(existing, data or {})
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        with cfg_path.open("wb") as fh:
            tomli_w.dump(merged, fh)
        try:
            cfg_path.chmod(0o600)
        except OSError:
            pass
        return {"ok": True, "path": str(cfg_path)}

    def list_providers(self) -> dict:
        cfg, _ = load_config(self._config_arg)
        user_providers = cfg.get("providers") or {}
        default = cfg.get("provider", "openai")
        items = []
        for name in sorted(set(PRESETS) | set(user_providers)):
            merged = {**PRESETS.get(name, {}), **user_providers.get(name, {})}
            env = merged.get("api_key_env", "")
            if merged.get("api_key"):
                status = "config"
            elif not env:
                status = "none"
            elif os.environ.get(env):
                status = "ok"
            else:
                status = "missing"
            items.append({"name": name, "type": merged.get("type", "openai"),
                          "model": str(merged.get("model", "")), "key_env": env,
                          "key_status": status, "is_default": name == default})
        return {"providers": items}

    # ------------------------------------------------------------ collect

    def collect(self, period: dict, topic: str = "", keywords: str = "") -> dict:
        resolved = self._period(period)
        keys = split_keywords(keywords) or ([topic] if topic else [])
        cfg, _ = load_config(self._config_arg)
        self._cancel.clear()
        activity = gather(cfg, resolved, keys, progress=self._progress,
                          cancel=self._cancel.is_set)
        with self._lock:
            self._activity = activity
        return self._activity_dto(activity)

    def cancel_collect(self) -> dict:
        self._cancel.set()
        return {"ok": True}

    def previous_report(self, period: dict, topic: str = "") -> dict:
        resolved = self._period(period)
        cfg, _ = load_config(self._config_arg)
        output_dir = expand(cfg.get("output_dir", "~/weekly-reports"))
        path = find_previous_report(output_dir, resolved, topic)
        if not path:
            return {"path": None, "content": None}
        return {"path": str(path), "content": path.read_text(encoding="utf-8")[:2000]}

    # ------------------------------------------------------------ generate

    def generate(self, selection: dict, options: dict) -> dict:
        options = options or {}
        cfg, _ = load_config(self._config_arg)
        with self._lock:
            activity = self._activity
        if activity is None:
            raise RuntimeError("nothing collected yet: run collect first")
        filtered = filter_activity(activity, set((selection or {}).get("session_ids") or []),
                                   set((selection or {}).get("repo_paths") or []))
        if filtered.is_empty:
            raise ValueError("nothing selected: keep at least one repository or session")
        if options.get("language"):
            cfg["language"] = options["language"]
        topic = options.get("topic") or ""

        activity_md = render_activity(filtered, int(cfg.get("max_context_chars", 60000)))
        title = report_title(filtered.period, cfg.get("language", "zh"),
                             cfg.get("author_name", ""), topic)

        previous_text = None
        mode = options.get("previous", "auto")   # "auto" | "none" | a file path
        if mode == "auto":
            output_dir = expand(cfg.get("output_dir", "~/weekly-reports"))
            previous_path = find_previous_report(output_dir, filtered.period, topic)
            if previous_path:
                previous_text = previous_path.read_text(encoding="utf-8")
        elif mode and mode != "none":
            previous_text = expand(str(mode)).read_text(encoding="utf-8")

        template = load_template(cfg, filtered.period, options.get("template") or None)
        system, user = build_messages(cfg, filtered.period, activity_md, template, title,
                                      previous_text, topic, None)
        provider = resolve_provider(options.get("provider") or cfg.get("provider", "openai"),
                                    cfg, options.get("model") or None)
        report = complete(provider, system, user)
        if not report.lstrip().startswith("#"):
            report = f"# {title}\n\n{report}"
        return {"report": report.rstrip() + "\n", "title": title, "provider": provider.name,
                "model": provider.model, "filename": report_filename(filtered.period, topic)}

    def save_report(self, markdown: str, filename: str = "") -> dict:
        cfg, _ = load_config(self._config_arg)
        with self._lock:
            activity = self._activity
        name = Path(filename).name if filename else None   # basename only, never a path
        if not name:
            if activity is None:
                raise RuntimeError("no filename given and nothing collected yet")
            name = report_filename(activity.period, "")
        path = expand(cfg.get("output_dir", "~/weekly-reports")) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        return {"path": str(path)}

    # ------------------------------------------------------------ send

    def send_report(self, markdown: str, options: dict) -> dict:
        from weekly_report.mailer import send_agently, send_smtp
        cfg, _ = load_config(self._config_arg)
        options = options or {}
        email = cfg["email"]
        method = options.get("method") or email.get("method", "smtp")
        recipients = list(options.get("to") or email.get("to") or [])
        cc = list(options.get("cc") or email.get("cc") or [])
        subject = options.get("subject") or first_heading(markdown)
        html_body = markdown_to_html(markdown, subject)
        # The UI already asked for confirmation, so agently's own second prompt is accepted.
        if method == "agently":
            result = send_agently(recipients, cc, subject, html_body, confirm=lambda summary: True)
        elif method == "smtp":
            if not recipients:
                raise ValueError("no recipient: set email.to in the config or pass to")
            result = send_smtp(email.get("smtp") or {}, recipients, cc, subject,
                               markdown, html_body)
        else:
            raise ValueError(f"unknown method {method!r} (use smtp or agently)")
        return {"result": result}

    def effective_recipients(self, method: str = "") -> dict:
        """Recipients a send would use (agently with no `to` sends to your own mailbox)."""
        from weekly_report.mailer import MailError, agently_self_address
        cfg, _ = load_config(self._config_arg)
        email = cfg["email"]
        chosen = method or email.get("method", "smtp")
        recipients = list(email.get("to") or [])
        error = None
        if chosen == "agently" and not recipients:
            try:
                recipients = [agently_self_address()]
            except MailError as exc:
                error = str(exc)
        return {"to": recipients, "cc": list(email.get("cc") or []),
                "method": chosen, "error": error}

    # ------------------------------------------------------------ misc

    def pick_file(self, suffix: str = "") -> dict:
        """Native open-file dialog; {path: None} when it cannot run (type a path instead)."""
        try:
            import webview
            window = webview.windows[0] if webview.windows else None
            if window is None:
                return {"path": None, "error": "no window open"}
            file_types = (f"Files (*{suffix})",) if suffix else None
            chosen = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False,
                                               file_types=file_types)
            return {"path": chosen[0] if chosen else None, "error": None}
        except Exception as exc:  # dialog problems must never break the flow
            return {"path": None, "error": str(exc)}

    # ------------------------------------------------------------ internals

    @staticmethod
    def _period(spec: dict) -> Period:
        spec = spec or {}
        return resolve_period(spec.get("week"), spec.get("month"), spec.get("year"),
                              spec.get("since"), spec.get("until"))

    def _progress(self, event: dict) -> None:
        if self._notify:
            try:
                self._notify(event)
            except Exception:  # the window may not be ready yet, or may be closing
                pass

    @staticmethod
    def _activity_dto(activity: Activity) -> dict:
        return {
            "period": {"kind": activity.period.kind, "start": activity.period.start.isoformat(),
                       "end": activity.period.end.isoformat(), "label": activity.period.label},
            "cancelled": activity.cancelled,
            "commit_count": activity.commit_count,
            "repos_scanned": activity.repos_scanned,
            "include_prompts": activity.include_prompts,
            "missing_sources": activity.missing_sources,
            "repos": [{"name": repo.name, "path": repo.key, "commit_count": len(repo.commits),
                       "commits": [{"date": commit.date, "hash": commit.short_hash,
                                    "subject": commit.subject} for commit in repo.commits]}
                      for repo in activity.repos],
            "sessions": [{"id": session.key, "source": session.source,
                          "source_label": LABELS.get(session.source, session.source),
                          "title": session.title, "project": session.project,
                          "cwd": session.cwd, "branches": session.branches,
                          "message_count": session.message_count,
                          "first_date": session.first_date.isoformat() if session.first_date else None,
                          "last_date": session.last_date.isoformat() if session.last_date else None,
                          "date_approx": session.date_approx, "prompts": session.prompts}
                         for session in activity.sessions],
        }


# ------------------------------------------------------------------ window

class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:   # keep the console clean
        pass


def serve_static(directory: Path) -> tuple[str, ThreadingHTTPServer]:
    """Serve the built UI on a random local port (avoids WKWebView file:// limits)."""
    server = ThreadingHTTPServer(("127.0.0.1", 0),
                                 partial(_QuietHandler, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_port}", server


def run_gui(config_path: Optional[str] = None, dev: bool = False) -> int:
    """Open the GUI window; blocks until it is closed."""
    try:
        import webview
    except ImportError:
        raise ConfigError('the GUI needs the optional [gui] extra. Install it with:\n'
                          '  pipx install "weekly-report[gui] @ git+https://github.com/karte796/weeklyReport.git"\n'
                          '  (or: pip install "weekly-report[gui]")')
    bridge = Bridge(config_path)
    server: Optional[ThreadingHTTPServer] = None
    if dev:
        url = os.environ.get("WEEKLY_REPORT_GUI_DEV_URL", "http://localhost:5173")
    else:
        static_dir = Path(__file__).parent / "gui_static"
        if not (static_dir / "index.html").is_file():
            raise ConfigError(f"GUI assets missing under {static_dir}. Build them: "
                              "cd ui && npm run build")
        url, server = serve_static(static_dir)

    window = webview.create_window(f"weekly-report {__version__}", url, js_api=bridge,
                                   width=1140, height=780, min_size=(960, 640))

    def notify(event: dict) -> None:
        try:
            window.evaluate_js(f"window.__wrProgress && window.__wrProgress({json.dumps(event)})")
        except Exception:
            pass

    bridge._notify = notify   # wiring the window in; the bridge itself stays window-free
    webview.start()           # blocks on the main thread until the window is closed
    if server:
        server.shutdown()
    return 0
