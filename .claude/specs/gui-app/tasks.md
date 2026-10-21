# weekly-report GUI (Mac) 任务拆分

> 原则:每项任务 2-5 分钟可完成,粒度够小以便独立验证。

## 任务清单

### Phase 0 核心改造

- [x] T1 - gather/collect_git/collect_agents 增加 progress、cancel 可选参数
  - 输入:`collectors/__init__.py`、`collectors/git.py`、`collectors/agents.py`
  - 输出:git 逐仓库、agents 逐源回调 `{phase, scanned, total, current}`;cancel 触发时优雅返回部分结果
  - 验证:新增 pytest 用例(monkeypatch run_git 模拟多仓库 + cancel 中途 True)
- [x] T2 - 新增 `filter_activity` 与会话/仓库稳定键
  - 输入:`collectors/__init__.py`
  - 输出:`filter_activity(activity, keep_session_ids, keep_repo_paths)` 返回过滤副本(不改动原对象)
  - 验证:pytest 覆盖全保留/部分保留/空选择

### Phase 1 GUI

- [x] T3 - 新增 `weekly_report/gui.py` 的 Bridge(无窗口依赖)
  - 输入:T1/T2 产物
  - 输出:get_config/save_config/list_providers/collect/cancel_collect/previous_report/generate/save_report/send_report/pick_file
  - 验证:`tests/test_gui.py` 直接实例化 Bridge 断言 DTO 结构、过滤生成、配置写回
- [x] T4 - 静态伺服 + run_gui() + cli `gui` 子命令
  - 输入:T3
  - 输出:stdlib http.server 随机端口伺服 `gui_static/`;`--dev` 指 Vite dev server;缺 pywebview 报安装指引
  - 验证:`weekly-report gui --help`;未装 gui extra 时运行给出明确报错
- [x] T5 - pyproject/gui extra/版本号/.gitignore
  - 输出:`gui = ["pywebview>=5","tomli-w>=1"]`;dev 加 tomli-w;0.2.0;package-data 加 gui_static
  - 验证:`pip install -e ".[gui,dev]"` 成功,`weekly-report --version` 输出 0.2.0
- [x] T6 - ui/ Vite+React+TS 脚手架(api 层 + mock 桥 + 布局)
  - 输出:package.json/vite.config(base:'./')/tsconfig/index.html/src 骨架,`window.pywebview` 缺失时自动用 MockApi
  - 验证:`npm run build` 通过;浏览器直接打开有 mock 数据
- [x] T7 - 采集页(周期选择/进度/两级勾选)
- [x] T8 - 生成页(provider 选择/上期报告/报告编辑与保存)
- [x] T9 - 发送页(收件人/主题/方法/确认发送)
- [x] T10 - 设置页(配置表单/保存提示)
  - T7-T10 验证:dev server 下浏览器逐页走查 + `npm run build`
- [x] T11 - 构建产物入库 + README GUI 章节(中英)
  - 验证:干净 venv `pip install .`(不带 gui)测试不受影响;`pip install ".[gui]"` 后 `weekly-report gui` 可启动

### Phase 2(本次不做,占位)

- 流式 LLM 输出(SSE,urllib)/ 历史报告库 / 菜单栏与定时 / .app 打包

## 依赖关系

T1→T2→T3→T4、T5 可并行;T6 独立可先行;T6→T7→T8→T9(页面间状态传递);T10 独立;T11 收尾。

## 风险点

- **pywebview + 线程取消**:cancel 只作用于采集循环,generate 阶段不可取消——UI 需明示。
- **create_file_dialog 死锁**:js_api 线程调原生对话框在 macOS 偶发问题,pick_file 全 try/except 包裹,失败返回错误串由前端退化为手输路径。
- **pipx 从 git 构建时静态资源缺失**:gui_static 必须入库且 package-data 覆盖嵌套 assets/;T11 干净安装验证兜底。
- **Python 3.9 兼容**:Bridge 类型注解避免 `X | Y` 语法(用 Optional/Union 或 `from __future__ import annotations`——项目已统一后者)。
