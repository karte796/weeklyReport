"""A small Markdown-to-HTML renderer for e-mail bodies (headings, lists, paragraphs,
blockquotes, code blocks, tables, bold/italic/code/links). No third-party dependency."""
from __future__ import annotations

import html
import re

STYLE = (
    "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',"
    "sans-serif;font-size:14px;line-height:1.7;color:#1f2328;max-width:760px;margin:0 auto;padding:16px}"
    "h1{font-size:20px;border-bottom:1px solid #d0d7de;padding-bottom:6px}"
    "h2{font-size:16px;margin-top:22px;color:#0b5394}h3{font-size:14px;margin-top:16px}"
    "ul,ol{padding-left:22px}li{margin:2px 0}code{background:#f3f4f6;padding:1px 4px;border-radius:3px}"
    "pre{background:#f6f8fa;padding:10px;border-radius:6px;overflow:auto}"
    "blockquote{border-left:3px solid #d0d7de;margin:8px 0;padding:0 12px;color:#57606a}"
    "table{border-collapse:collapse}td,th{border:1px solid #d0d7de;padding:4px 8px}"
)

_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")


def inline(text: str) -> str:
    codes: list[str] = []

    def stash(match: re.Match) -> str:
        codes.append(f"<code>{html.escape(match.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<em>\1</em>", text)
    text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+|mailto:[^)\s]+)\)",
                  lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def _render_list(items: list[tuple[int, bool, str]]) -> str:
    """items: (indent, ordered, text). Builds nested lists by indentation."""
    out: list[str] = []
    stack: list[tuple[int, str]] = []  # (indent, tag)
    for indent, ordered, text in items:
        tag = "ol" if ordered else "ul"
        while stack and indent < stack[-1][0]:
            out.append(f"</li></{stack.pop()[1]}>")
        if not stack or indent > stack[-1][0]:
            out.append(f"<{tag}>")
            stack.append((indent, tag))
        else:
            out.append("</li>")
        out.append(f"<li>{inline(text)}")
    while stack:
        out.append(f"</li></{stack.pop()[1]}>")
    return "".join(out)


def _is_table_sep(line: str) -> bool:
    return bool(re.match(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$", line))


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def markdown_to_html(md: str, title: str = "") -> str:
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("```"):
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(block))}</code></pre>")
            i += 1
            continue
        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,})$", stripped):
            out.append("<hr>")
            i += 1
            continue
        if stripped.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(f"<blockquote>{'<br>'.join(inline(q) for q in quote)}</blockquote>")
            continue
        if "|" in stripped and i + 1 < len(lines) and _is_table_sep(lines[i + 1]):
            header = _cells(stripped)
            i += 2
            rows = []
            while i < len(lines) and "|" in lines[i]:
                rows.append(_cells(lines[i]))
                i += 1
            head = "".join(f"<th>{inline(c)}</th>" for c in header)
            body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows)
            out.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
            continue
        if _LIST_RE.match(line):
            items = []
            while i < len(lines):
                match = _LIST_RE.match(lines[i])
                if match:
                    indent = len(match.group(1).replace("\t", "    "))
                    ordered = match.group(2)[0].isdigit()
                    if items and indent <= items[0][0] and ordered != items[0][1]:
                        break  # list type changed at top level: start a new list
                    items.append((indent, ordered, match.group(3)))
                elif lines[i].strip() and items and lines[i].startswith((" ", "\t")):
                    indent, ordered, text = items[-1]
                    items[-1] = (indent, ordered, f"{text} {lines[i].strip()}")
                else:
                    break
                i += 1
            out.append(_render_list(items))
            continue
        para = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,6}\s|```|>|[-*+]\s|\d+[.)]\s)",
                                                                    lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{'<br>'.join(inline(p) for p in para)}</p>")
    body = "\n".join(out)
    head_title = f"<title>{html.escape(title)}</title>" if title else ""
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8">{head_title}'
            f"<style>{STYLE}</style></head><body>\n{body}\n</body></html>")
