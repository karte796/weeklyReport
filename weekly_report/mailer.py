"""Send the finished report by e-mail via SMTP or agently-cli (QQ Mail agent mailbox)."""
from __future__ import annotations

import json
import os
import shutil
import smtplib
import ssl
import subprocess
import tempfile
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Callable, Optional


class MailError(Exception):
    pass


def send_smtp(smtp_cfg: dict, to: list[str], cc: list[str], subject: str,
              text: str, html_body: str) -> str:
    host = smtp_cfg.get("host")
    if not host:
        raise MailError("email.smtp.host is not configured")
    username = smtp_cfg.get("username", "")
    sender = smtp_cfg.get("from") or username
    if not sender:
        raise MailError("set email.smtp.from or email.smtp.username")
    password = smtp_cfg.get("password") or os.environ.get(smtp_cfg.get("password_env") or "", "")
    if username and not password:
        raise MailError(f"SMTP password not found: set environment variable "
                        f"{smtp_cfg.get('password_env') or 'SMTP_PASSWORD'}")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid()
    message.set_content(text)
    message.add_alternative(html_body, subtype="html")

    port = int(smtp_cfg.get("port") or 465)
    security = (smtp_cfg.get("security") or "ssl").lower()
    context = ssl.create_default_context()
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, context=context, timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
        with server:
            if security == "starttls":
                server.starttls(context=context)
            if username:
                server.login(username, password)
            server.send_message(message, to_addrs=to + cc)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"SMTP error: {exc}") from exc
    return f"sent to {', '.join(to + cc)} via {host}"


# ------------------------------------------------------------------ agently-cli

def _agently(args: list[str], cwd: Optional[str] = None) -> tuple[int, dict]:
    binary = shutil.which("agently-cli")
    if not binary:
        raise MailError("agently-cli not found. Install: npm install -g @tencent-qqmail/agently-cli "
                        "&& agently-cli auth login")
    try:
        result = subprocess.run([binary, *args], capture_output=True, text=True, cwd=cwd, timeout=120)
    except (subprocess.SubprocessError, OSError) as exc:
        raise MailError(f"agently-cli failed to run: {exc}") from exc
    raw = result.stdout.strip()
    start = raw.find("{")
    try:
        data = json.loads(raw[start:raw.rfind("}") + 1]) if start >= 0 else {}
    except json.JSONDecodeError:
        data = {}
    if result.returncode != 0 and not data:
        data = {"error": {"message": (result.stderr or raw).strip()[:500]}}
    return result.returncode, data


def _agently_error(code: int, data: dict) -> MailError:
    message = (data.get("error") or {}).get("message") or "unknown error"
    hint = " (run `agently-cli auth login`)" if code == 3 or "re-authenticate" in message else ""
    return MailError(f"agently-cli exit {code}: {message}{hint}")


def agently_self_address() -> str:
    code, data = _agently(["+me"])
    if code != 0 or not data.get("ok", True):
        raise _agently_error(code, data)
    aliases = (data.get("data") or {}).get("aliases") or []
    primary = next((a for a in aliases if a.get("is_primary")), aliases[0] if aliases else None)
    if not primary or not primary.get("email"):
        raise MailError("agently-cli +me returned no mailbox address")
    return primary["email"]


def send_agently(to: list[str], cc: list[str], subject: str, html_body: str,
                 confirm: Callable[[dict], bool]) -> str:
    """Two-phase send: the first call returns a summary + token; the human confirms; then send."""
    if not to:
        to = [agently_self_address()]
    with tempfile.TemporaryDirectory(prefix="weekly-report-") as tmp:
        Path(tmp, "body.html").write_text(html_body, encoding="utf-8")
        args = ["message", "+send", "--subject", subject, "--body-file", "./body.html"]
        for address in to:
            args += ["--to", address]
        for address in cc:
            args += ["--cc", address]

        code, data = _agently(args, cwd=tmp)
        payload = data.get("data") or {}
        if code != 0 or data.get("ok") is False:
            raise _agently_error(code, data)
        token = payload.get("confirmation_token")
        if not token:
            return f"sent to {', '.join(to + cc)} via agently-cli"
        if not confirm(payload.get("summary") or {"to": to, "subject": subject}):
            raise MailError("cancelled, nothing was sent")
        code, data = _agently(args + ["--confirmation-token", token], cwd=tmp)
        if code != 0 or data.get("ok") is False:
            raise _agently_error(code, data)
    return f"sent to {', '.join(to + cc)} via agently-cli"
