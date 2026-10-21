# weekly-report GUI (Mac) Review 记录

## 实现摘要

2026-10-21 完成 Phase 0 + Phase 1（MVP）。相对设计的偏差：

- 取消语义按设计"关键实现点"实现（优雅停止 + `Activity.cancelled` 标记），design 接口节中残留的 `Cancelled` 异常描述已修正。
- `first_heading` 从 cli.py 抽到 `report.py` 共享（CLI 与 Bridge 复用）。
- `Bridge.generate` 的 `options.previous` 采用 `"auto" | "none" | <路径>` 三态字符串，比 design 初稿的字段方案更明确。
- 实测发现本机 macOS 系统代理（127.0.0.1:1082）会被 urllib 读取，已记入 design 风险节；WKWebView 回环访问不受影响。

## 自检清单

- [x] 验收标准逐条通过（见 requirements.md；pytest 47 通过 = 原 36 + 新增 11）
- [x] 构建 / 类型检查通过：`npm run build`（tsc --noEmit + vite build）
- [x] 测试覆盖：tests/test_collectors.py 增 3 例（progress/cancel/filter）、tests/test_gui.py 增 8 例（Bridge 全方法）
- [x] 手动验证：浏览器（mock 桥）走通 采集→勾选→生成→保存→发送→设置 全链路；`weekly-report gui` 缺 extra 时给出安装指引；serve_static 用无代理 opener 验证 200
- [x] 回滚方案可用：GUI 为纯增量，core 改动均为可选参数

## 已知遗留

- 生成阶段不可取消、无流式输出（Phase 2）。
- `pick_file` 原生文件对话框在 js_api 线程的稳定性未在真实窗口验证（已 try/except 兜底为手输路径）。
- SettingsPage 保存会重写 TOML、丢失注释（UI 已提示）。
- `weekly-report gui` 真实窗口（WKWebView + pywebview js_api 桥）尚未人工点过——浏览器只验证了 mock 桥。首次真机使用时注意 `pywebviewready` 时序与进度事件。
- CI 未覆盖前端构建（gui_static 已入库，可后补 npm build 校验 job）。

## 后续建议

- Phase 2：providers 三适配器加 SSE 流式 + 生成阶段取消；历史报告库页。
- `ui/` 可加 ESLint/Prettier；React 19 / Vite 5 需先升级 Node ≥ 18。
- 若同事反馈 Node 版本困扰，可在 CI 加 gui_static 构建校验防止产物过期。
