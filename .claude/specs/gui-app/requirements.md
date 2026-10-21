# weekly-report GUI (Mac) 需求

## 背景

`weekly-report` 目前是纯 CLI：配置要手编 TOML、`--dry-run` 只能看不能改、生成时只能干等、发送靠终端问答。个人使用和公司内分享都希望有个图形界面。同时确定不做正式分发：无 Apple 开发者账号、不签名公证、无更新服务器，git 仓库即更新渠道（`pipx upgrade`）。

## 目标

1. `weekly-report gui` 打开本地 GUI 窗口（pywebview/WKWebView），覆盖完整主链路：选周期 → 采集预览并勾选 → 生成/编辑报告 → 发送邮件，外加配置表单页。
2. CLI 与 GUI 共享同一 Python 核心，CLI 行为零变化；核心库新增进度/取消回调与活动筛选能力。
3. 分发零基础设施：`pipx install "weekly-report[gui] @ git+<仓库>"` 一条命令安装，`pipx upgrade` 即更新。

## 非目标

- 不做 .app 打包、签名、公证、自动更新（远期可选）。
- 不做流式 LLM 输出（Phase 2，接口先留位）。
- 不做自定义 provider 表单编辑（TOML 手编仍可用）。
- 不做菜单栏常驻 / 定时任务（Phase 2 以后）。
- 不做 Windows/Linux 适配验证（pywebview 理论跨平台，本期只验证 macOS）。

## 用户场景 / 使用路径

1. **每周生成**：打开 `weekly-report gui` → 选"上周" → 采集 → 在预览里勾掉与工作无关的会话/仓库 → 选 provider 生成 → 在编辑框微调 → 确认收件人 → 发送。
2. **首次配置**：设置页填 git.roots（目录选择）、provider、语言、邮箱信息 → 保存；`providers` 状态（key 是否配置）可视化展示。
3. **同事安装**：`brew install pipx` → `pipx install "weekly-report[gui] @ git+..."` → `weekly-report gui`。

## 约束

- GUI 依赖必须可选：核心包保持"零重依赖"，`pip install weekly-report` 不拉 pywebview。
- 前端 React + TypeScript + Vite，构建产物提交进仓库（pipx 从 git 构建时没有 npm）。
- Python 3.9+ 兼容不变（与 CLI 一致）。
- 浏览器直接打开 UI 时走 mock 桥（无 `window.pywebview` 时自动降级），便于前端开发与本机预览。

## 验收标准

- [ ] `weekly-report gui` 打开窗口，四个页面（采集/生成/发送/设置）可用
- [ ] 采集结果按仓库/会话两级勾选，取消勾选的项不进入生成 prompt
- [ ] 生成复用 `build_messages` + `complete`，报告可编辑、可保存到 output_dir
- [ ] SMTP 与 agently 发送可用，发送前 GUI 内确认
- [ ] 设置表单可写回 config TOML（未知顶层键保留；注释丢失有提示）
- [ ] 无 pywebview 时 `weekly-report gui` 给出安装指引报错，其余子命令不受影响
- [ ] `pytest` 全绿（含新增核心与桥接层测试）；`npm run build` 通过
- [ ] CLI 原有行为不变（现有 36 个测试不改动语义）

## 开放问题

- （已决策）pywebview vs Tauri → pywebview；React 确认。
- （已决策）更新方式 → git 仓库 + pipx upgrade，无服务器。
- agently 两阶段确认在 GUI 中合并为一次确认（GUI 弹窗替代），见 design 风险节。
