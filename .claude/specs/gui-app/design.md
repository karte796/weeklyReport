# weekly-report GUI (Mac) 技术设计

## 方案概述

在现有 Python 包内新增可选 GUI：`weekly-report gui` 子命令启动 pywebview 窗口（WKWebView），加载打包在包内的 React 构建产物；Python 侧新增 `Bridge` 类作为 JS↔Python 服务层，复用既有核心函数（gather / build_messages / complete / mailer），核心层补进度回调、取消与活动筛选三个小能力。

## 架构 / 数据流

```
React UI (ui/, Vite+TS, 构建产物 → weekly_report/gui_static/)
   │  window.pywebview.api.<method>(...)   ← 无桥时降级 MockApi(浏览器开发/预览)
   ▼
Bridge (weekly_report/gui.py)          ← js_api 对象, pywebview 派发到工作线程
   │  调用                              │ evaluate_js 推进度事件 window.__wrProgress(...)
   ▼
核心层: config / periods / collectors(gather, filter_activity)
        / report(build_messages) / providers(complete) / mailer
   ▲
cli.py 仅新增 gui 子命令(懒加载 pywebview)     CLI 原路径不动
```

生成主链路（两步 API）：`collect(period)` → 返回 ActivityDTO，Bridge 持有上次采集结果 → 前端勾选 → `generate(selection, options)` → `filter_activity` 过滤 → `render_activity` → `build_messages` → `complete` → 返回报告文本。同一次采集可多次以不同勾选生成。

## 接口设计

### 核心层新增（Phase 0）

```python
# collectors/__init__.py
def gather(cfg, period, keywords, tz=None,
           progress: Callable[[dict], None] | None = None,   # {phase, scanned, total, current}
           cancel: Callable[[], bool] | None = None) -> Activity  # 取消=优雅停止,返回已采集部分
def filter_activity(activity, keep_session_ids: set[str], keep_repo_paths: set[str]) -> Activity
```

- `collect_git` / `collect_agents` 透传 progress/cancel，返回值各增加一个 `cancelled` 布尔（git 逐仓库、agents 逐源/逐文件回调）。
- 取消**不抛异常**：循环顶检查 `cancel()`，break 返回部分结果；`Activity` 增加 `cancelled` 字段，`gather` 在 git 段取消后跳过 agents 段。
- 会话唯一 id = `Session.key`（`f"{source}:{session_id}"`），仓库键 = `RepoCommits.key`（`str(path)`）。

### Bridge（js_api，全部 snake_case，返回 JSON dict）

| 方法 | 入参 | 出参 |
|---|---|---|
| `get_config()` | — | `{config, config_path, exists}` |
| `save_config(data)` | 表单 dict | `{ok, path}`（tomli-w 写回；未知顶层键保留） |
| `list_providers()` | — | `[{name,type,model,key_status,is_default}]` |
| `collect(period, topic, keywords)` | period dict / 主题 | ActivityDTO（+`cancelled` 标记） |
| `cancel_collect()` | — | `{ok}`（threading.Event） |
| `previous_report(period, topic)` | — | `{path, content}` 或 `{path: None}` |
| `generate(selection, options)` | 勾选 id 列表 / provider·model·language·topic·previous_path | `{report}`；错误抛异常→JS promise reject |
| `save_report(markdown, filename?)` | 报告文本 | `{path}` |
| `send_report(markdown, options)` | to·cc·subject·method | `{result}`；agently 的 confirm 回调恒 True（GUI 弹窗替代，见风险） |
| `pick_file(suffix)` | 扩展名 | `{path}`（create_file_dialog，异常降级为错误串） |

`options.previous_path == null` 表示不用上期；缺省走 `find_previous_report` 自动查找。

### CLI

`weekly-report gui [--dev] [--config PATH]`；`--dev` 时窗口指向 `WEEKLY_REPORT_GUI_DEV_URL`（默认 `http://localhost:5173`），配合 `npm run dev` 热更新。

### 打包

- `ui/` 为 Vite 根，`vite.config.ts` 设 `base: './'`；`npm run build` 产物输出到 `weekly_report/gui_static/` 并**提交进仓库**（pipx 从 git 构建无 npm 环境）。
- 静态资源由 Bridge 内置的 stdlib `http.server`（127.0.0.1 随机端口）伺服，规避 WKWebView 的 file:// 子资源限制。
- pyproject：`[project.optional-dependencies] gui = ["pywebview>=5", "tomli-w>=1"]`；`dev` 增加 `tomli-w`；package-data 增加 `gui_static/*`、`gui_static/assets/*`。
- pywebview / tomli-w 均在 `gui.py` 内**懒加载**：未装 gui extra 时 import 不炸，仅 `gui` 子命令给安装指引。

## 关键实现点

1. **线程模型**：pywebview 把每个 js_api 调用派发到独立线程，长任务（collect/generate）不阻塞其他调用；取消用 `threading.Event`，Bridge 实例持有 `_activity`（上次采集）与 `_activity_lock`。窗口对象在 collect 进行中通过 `evaluate_js` 推进度——窗口未就绪或测试环境下回调可注入、默认 no-op。
2. **配置写回**：`save_config` 读**原始用户 TOML**（非合并默认值）→ 用 `deep_merge` 覆盖表单管理的键 → tomli-w 序列化。表单不管理的键原样保留；文件注释会丢失（TOML 重写固有），UI 保存时提示一次。
3. **取消语义**：git 扫描在"发现仓库→逐仓库取 log"两段循环顶检查 cancel；LLM 调用中取消不支持（urllib 阻塞，接受现状，Phase 2 流式时一并解决）。

## 风险与权衡

- **Tauri 被否**：更新器需签名+服务器，分发优势用不上；双构建链成本高。
- **agently 双重确认合并为一次**：GUI 发送前已展示收件人/主题/正文预览，`confirm` 回调恒 True。若 agently 摘要解析出的实际收件人与预期不符（如 `to` 为空取自身地址），风险由发送预览页承担——`send_report` 前端先展示**实际生效**收件人（agently 且 to 空时调 `agently_self_address()` 展示）。
- **构建产物入库**：仓库会带上 ~几百 KB 静态文件，diff 噪音；换来 pipx 零 npm 安装。可接受，后续可加 CI 构建校验。
- **PyInstaller/.app** 不做：Gatekeeper 右键打开的体验仅留给未来远期选项。
- **流式输出缺失**：MVP 生成期间只有 loading 态；180s 超时内无反馈。Phase 2 补 SSE。
- **系统代理（实测发现）**：本机配置了 macOS 系统代理（127.0.0.1:1082），Python urllib 的 `getproxies()` 会读到它——CLI/GUI 调 LLM 接口会走代理（对本项目通常反而有利）。本地静态伺服验证时需注意 urllib 默认走代理会打到回环端口；WKWebView 对 loopback 目标默认不走系统代理，不受影响。

## 回滚 / 降级

- GUI 完全是增量：不装 gui extra 时包行为与现在完全一致；`gui` 子命令报错不影响其余命令。
- 核心层改动（progress/cancel/filter）均为**可选参数**，现有调用方零改动；出问题 revert 单个 commit 即可。
- 前端页面异常时可继续用 CLI 完成一切（同一核心）。

## 改动清单

- `weekly_report/collectors/__init__.py`：gather 加 progress/cancel；新增 `Cancelled`、`filter_activity`、会话/仓库键函数
- `weekly_report/collectors/git.py` / `agents.py`：透传 progress/cancel
- `weekly_report/gui.py`（新增）：Bridge + 本地静态伺服 + `run_gui()`
- `weekly_report/cli.py`：`gui` 子命令（懒加载）
- `weekly_report/__init__.py`：版本 0.2.0
- `pyproject.toml`：gui extra、package-data
- `ui/`（新增）：Vite + React + TS 工程，四个页面 + mock 桥
- `weekly_report/gui_static/`（新增，构建产物入库）
- `tests/test_collectors.py`、`tests/test_gui.py`（新增）：核心新能力 + Bridge 无窗口测试
- `README.md`：GUI 章节（中英）
- `.gitignore`：`ui/node_modules`
