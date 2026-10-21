# weekly-report

[![CI](https://github.com/karte796/weeklyReport/actions/workflows/ci.yml/badge.svg)](https://github.com/karte796/weeklyReport/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**English** | [中文](#中文说明)

Write your weekly report in one command. `weekly-report` reads what you actually did — your **git commits** and your **AI coding-assistant sessions** (Claude Code, Codex, Kiro, Kiro CLI) — and asks the LLM of your choice to turn it into a clean Markdown report. It can then e-mail it for you.

```text
$ weekly-report
Period: 2026-10-12 ~ 2026-10-18
Collected 23 commits from 4 repos (37 scanned) and 18 AI sessions.
Previous report: ~/weekly-reports/2026-W41.md
Generating with deepseek (deepseek-chat) …
Saved to ~/weekly-reports/2026-W42.md
```

## Features

- **Two sources of truth**: git commits are the backbone; AI-assistant sessions fill in research, debugging and design work that never became a commit.
- **Any LLM**: OpenAI, DeepSeek, Qwen, Kimi, Zhipu GLM, SiliconFlow, OpenRouter, Anthropic Claude, Google Gemini, local Ollama — or any OpenAI-compatible endpoint.
- **Continuity**: finds your previous report automatically and checks last period's plan against this period's work.
- **Weekly, monthly, custom range, topic reports** (e.g. only "performance" work).
- **E-mail delivery** via SMTP or [agently-cli](https://agent.qq.com) (QQ Mail agent mailbox), always with a confirmation step.
- **Optional GUI**: `weekly-report gui` opens a native window (macOS) — pick a period, preview and deselect commits/sessions, generate, edit and send. React inside [pywebview](https://pywebview.flowrl.com); CLI and GUI share the same core.
- **Privacy controls**: `--dry-run` shows exactly what would be sent; send titles only; exclude repos/projects; or run fully local with Ollama.
- **Zero heavy dependencies**: pure Python standard library (plus `tomli` on Python < 3.11). No SDKs.

## Install

Requires Python 3.9+ and git.

```bash
pipx install git+https://github.com/karte796/weeklyReport.git
# with the GUI (adds pywebview):
pipx install "weekly-report[gui] @ git+https://github.com/karte796/weeklyReport.git"
# or
pip install git+https://github.com/karte796/weeklyReport.git
```

Updates are just git + pipx: push/pull the repo, then `pipx upgrade weekly-report`.

## Quick start

```bash
weekly-report init                 # creates ~/.config/weekly-report/config.toml
# edit git.roots (where your repos live) and provider in that file
export DEEPSEEK_API_KEY=sk-...     # key for the provider you chose
weekly-report --dry-run            # preview the collected data, no API call
weekly-report                      # generate last week's report
```

## Usage

```bash
weekly-report                          # last week (default)
weekly-report -w this                  # this week; also: prev (the week before last)
weekly-report -m 9                     # monthly report for September
weekly-report --since 2026-10-01 --until 2026-10-15
weekly-report --topic performance -k "perf,LCP,FCP"   # focused report
weekly-report -p anthropic --model claude-sonnet-4-5  # switch provider/model
weekly-report --lang en                # English report
weekly-report --stdout                 # print only, do not save
weekly-report --send                   # generate, optionally edit in $EDITOR, then e-mail
weekly-report send ~/weekly-reports/2026-W42.md --to boss@example.com
weekly-report providers                # list providers and whether keys are set
```

Reports are saved to `output_dir` (default `~/weekly-reports`) as `2026-W42.md`, `2026-09.md`, `2026-W42-performance.md`, … The newest earlier report of the same kind is passed to the model as the "previous report". Use `--previous FILE` to pick one or `--no-previous` to skip.

## GUI

```bash
pipx install "weekly-report[gui] @ git+https://github.com/karte796/weeklyReport.git"
weekly-report gui
```

A three-step window: **collect** (pick the period, watch the scan, tick off repos/sessions you do not want in the report) → **generate** (choose provider/model, compare with the previous report, edit the result) → **send** (recipients, subject, confirm). A settings form edits the TOML config without a text editor. Everything runs locally; the GUI talks only to the same collectors and providers as the CLI.

To develop the UI: `cd ui && npm install && npm run dev`, then `weekly-report gui --dev` (loads the Vite dev server; in a plain browser the UI runs on mock data). Build with `npm run build` — the output is committed under `weekly_report/gui_static/` so pip installs need no Node.

## Providers

| name | type | default model | API key env |
|---|---|---|---|
| `openai` | openai | gpt-4o-mini | `OPENAI_API_KEY` |
| `deepseek` | openai | deepseek-chat | `DEEPSEEK_API_KEY` |
| `qwen` | openai | qwen-plus | `DASHSCOPE_API_KEY` |
| `kimi` | openai | moonshot-v1-32k | `MOONSHOT_API_KEY` |
| `zhipu` | openai | glm-4-flash | `ZHIPUAI_API_KEY` |
| `siliconflow` | openai | deepseek-ai/DeepSeek-V3 | `SILICONFLOW_API_KEY` |
| `openrouter` | openai | openai/gpt-4o-mini | `OPENROUTER_API_KEY` |
| `ollama` | openai | qwen2.5 | — (local) |
| `anthropic` / `claude` | anthropic | claude-sonnet-4-5 | `ANTHROPIC_API_KEY` |
| `gemini` | gemini | gemini-2.5-flash | `GEMINI_API_KEY` |

Override any preset or add your own in the config:

```toml
[providers.deepseek]
model = "deepseek-reasoner"

[providers.company-gateway]       # any OpenAI-compatible API
type = "openai"
base_url = "https://llm.example.com/v1"
model = "gpt-4o"
api_key_env = "GATEWAY_KEY"
temperature = 0.3
```

Keep keys in environment variables (`api_key_env`). An inline `api_key` works but is not recommended.

## Data sources

| source | where it reads | dates |
|---|---|---|
| git | every repo under `git.roots` (worktrees merged, `node_modules`/`Pods`/… skipped) | commit date |
| `claude` | `~/.claude/projects` (respects `CLAUDE_CONFIG_DIR`) | exact |
| `codex` | `~/.codex/sessions` (respects `CODEX_HOME`) | exact |
| `kiro` | Kiro IDE `workspace-sessions` in the app-data folder | approximate (file mtime, marked ≈) |
| `kiro-cli` | `~/.kiro/sessions/cli` | exact |

Commits are filtered by author: by default each repository's own `git config user.email`, so per-repo or `includeIf` identities work. Set `git.authors` to override. Missing sources are skipped with a note. Paths can be overridden under `[agents.roots]`.

## E-mail

```toml
[email]
method = "smtp"                # or "agently"
to = ["me@example.com"]
cc = []
subject = "{title}"            # {title} {name} {label} {start} {end}

[email.smtp]
host = "smtp.qq.com"           # smtp.gmail.com, smtp.163.com, smtp.office365.com …
port = 465
security = "ssl"               # ssl | starttls | none
username = "me@example.com"
from = "me@example.com"
password_env = "SMTP_PASSWORD" # app password / authorization code
```

The report is sent as HTML with a plain-text fallback. You are always asked to confirm before sending (`--yes` skips it).

**agently-cli**: install with `npm install -g @tencent-qqmail/agently-cli && agently-cli auth login`, then set `method = "agently"`. With an empty `to`, the report goes to your own agent mailbox (`agently-cli +me`). agently-cli's two-phase confirmation is respected: you see its summary and confirm before anything is sent.

## Templates

Built-in templates (weekly/monthly × zh/en) live in [`weekly_report/templates`](weekly_report/templates). Copy one, edit the sections, and point `template = "~/my-template.md"` at it (or pass `--template`). `{title}` is replaced with the report title; HTML comments are instructions for the model. Add global guidance with `extra_instructions`.

## Privacy

- All collectors are **read-only**. Nothing is modified.
- Commit subjects, session titles, your prompts (truncated) and project folder names are sent **to the provider you choose**. Run `weekly-report --dry-run` to see the exact payload.
- `agents.include_prompts = false` sends session titles only; `git.exclude` / `agents.exclude` drop repos or projects; `agents.enabled = false` turns sessions off.
- Use `ollama` to keep everything on your machine.
- The model is instructed to omit secrets, but do not rely on it: review before sending.

## Development

```bash
git clone git@github.com:karte796/weeklyReport.git && cd weeklyReport
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Issues and pull requests are welcome — new session sources and providers especially.

## License

[MIT](LICENSE)

---

## 中文说明

一条命令写完周报。`weekly-report` 读取你**真实做过的事**——**git 提交**和 **AI 编程助手会话**（Claude Code、Codex、Kiro、Kiro CLI），交给你选的大模型整理成一份 Markdown 周报，还能直接发邮件。

### 功能

- **两路数据**：git 提交是产出主线；AI 会话补充没有提交的调研、排障、方案讨论。
- **多家 AI**：OpenAI、DeepSeek、通义千问、Kimi、智谱、硅基流动、OpenRouter、Claude、Gemini、本地 Ollama，以及任意 OpenAI 兼容接口。
- **连续性**：自动找到上一期报告，逐条对照上期计划和本期完成情况。
- **周报 / 月报 / 自定义区间 / 专项报告**（如只看“性能优化”相关工作）。
- **发邮件**：支持 SMTP 和 agently-cli（QQ 邮箱 agent 邮箱），发送前都要确认。
- **可选图形界面**：`weekly-report gui` 打开原生窗口（macOS）——选周期、预览并勾选不要的提交/会话、生成、编辑、发送。React + pywebview，与 CLI 共用同一核心。
- **隐私可控**：`--dry-run` 先看要发出去的内容；可以只发会话标题、排除指定仓库或项目，或用 Ollama 完全本地运行。
- **几乎零依赖**：只用 Python 标准库（Python 3.11 以下额外需要 `tomli`），不装任何 SDK。

### 安装与上手

需要 Python 3.9+ 和 git。

```bash
pipx install git+https://github.com/karte796/weeklyReport.git
# 带图形界面（额外安装 pywebview）：
pipx install "weekly-report[gui] @ git+https://github.com/karte796/weeklyReport.git"

weekly-report init                 # 生成 ~/.config/weekly-report/config.toml
# 修改配置里的 git.roots（代码目录）和 provider
export DEEPSEEK_API_KEY=sk-...
weekly-report --dry-run            # 只看采集结果，不调用接口
weekly-report                      # 生成上一周的周报
weekly-report gui                  # 打开图形界面（需 [gui] extra）
```

仓库更新后 `pipx upgrade weekly-report` 即完成升级，无需任何服务器。

### 图形界面

```bash
pipx install "weekly-report[gui] @ git+https://github.com/karte796/weeklyReport.git"
weekly-report gui
```

三步式窗口：**采集**（选周期，看扫描进度，勾掉不想写进周报的仓库/会话）→ **生成**（选服务商和模型，对照上期报告，直接编辑结果）→ **发送**（收件人、主题、确认）。设置页用表单编辑 TOML 配置，不用手改文件。全部本地运行，GUI 与 CLI 调用同一套采集器和接口。

前端开发：`cd ui && npm install && npm run dev`，另开 `weekly-report gui --dev`（加载 Vite 开发服务器）；直接用浏览器打开则自动使用 mock 数据。`npm run build` 的产物提交在 `weekly_report/gui_static/`，pip 安装无需 Node。

### 常用命令

```bash
weekly-report -w this              # 本周；prev 为上上周
weekly-report -m 9                 # 9 月月报
weekly-report --since 2026-10-01 --until 2026-10-15
weekly-report --topic 性能 -k "性能,LCP,白屏"     # 专项周报
weekly-report -p qwen              # 临时换一家 AI
weekly-report --send               # 生成后可用编辑器修改，确认后发邮件
weekly-report send ~/weekly-reports/2026-W42.md
weekly-report providers            # 查看各家 AI 及密钥是否已配置
```

报告保存在 `output_dir`（默认 `~/weekly-reports`），文件名如 `2026-W42.md`、`2026-09.md`。生成时会自动把同类型的上一期报告交给模型做比对。

### 邮件

- **SMTP**：在 `[email.smtp]` 填写服务器、账号，密码（QQ/163 邮箱用授权码）放在 `password_env` 指定的环境变量里。
- **agently-cli**：`npm install -g @tencent-qqmail/agently-cli && agently-cli auth login`，再把 `email.method` 设为 `"agently"`。`to` 留空时默认发到自己的 agent 邮箱；会先展示 agently-cli 的确认摘要，你确认后才真正发送。

### 隐私说明

所有采集都是**只读**的。提交信息、会话标题、截断后的输入内容和项目目录名会发送给**你选择的 AI 服务商**，用 `--dry-run` 可以看到完整内容。不想发送输入内容可设置 `agents.include_prompts = false`；用 `git.exclude` / `agents.exclude` 排除敏感项目；用 Ollama 则数据完全不离开本机。发送前请自己再检查一遍报告。
