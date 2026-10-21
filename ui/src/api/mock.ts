import type {
  ActivityDTO, ConfigState, EffectiveRecipients, GenerateResult,
  ProviderDTO, ProgressEvent, SendOptions,
} from './types'
import type { BridgeApi } from './index'

const wait = (milliseconds: number) => new Promise(resolve => setTimeout(resolve, milliseconds))

function emitProgress(event: ProgressEvent): void {
  window.__wrProgress?.(event)
}

const sampleConfig: ConfigState = {
  config_path: '~/.config/weekly-report/config.toml',
  exists: true,
  version: '0.2.0',
  config: {
    provider: 'deepseek',
    language: 'zh',
    author_name: '绍伟荣',
    output_dir: '~/weekly-reports',
    default_week: 'last',
    template: '',
    extra_instructions: '',
    max_context_chars: 60000,
    git: {
      enabled: true,
      roots: ['~/Desktop/shao/05-项目', '~/code'],
      authors: [],
      max_depth: 4,
      exclude: ['learn-', 'demo'],
    },
    agents: {
      enabled: true,
      sources: ['claude', 'codex', 'kiro', 'kiro-cli'],
      include_prompts: true,
      max_prompt_len: 160,
      max_prompts_per_session: 8,
      exclude: [],
      roots: {},
    },
    providers: {},
    email: {
      method: 'smtp',
      to: ['me@example.com'],
      cc: [],
      subject: '{title}',
      smtp: {
        host: 'smtp.qq.com',
        port: 465,
        security: 'ssl',
        username: 'me@example.com',
        password_env: 'SMTP_PASSWORD',
        from: 'me@example.com',
      },
    },
  },
}

const sampleProviders: ProviderDTO[] = [
  { name: 'anthropic', type: 'anthropic', model: 'claude-sonnet-4-5', key_env: 'ANTHROPIC_API_KEY', key_status: 'missing', is_default: false },
  { name: 'deepseek', type: 'openai', model: 'deepseek-chat', key_env: 'DEEPSEEK_API_KEY', key_status: 'ok', is_default: true },
  { name: 'gemini', type: 'gemini', model: 'gemini-2.5-flash', key_env: 'GEMINI_API_KEY', key_status: 'missing', is_default: false },
  { name: 'kimi', type: 'openai', model: 'moonshot-v1-32k', key_env: 'MOONSHOT_API_KEY', key_status: 'missing', is_default: false },
  { name: 'ollama', type: 'openai', model: 'qwen2.5', key_env: '', key_status: 'none', is_default: false },
  { name: 'openai', type: 'openai', model: 'gpt-4o-mini', key_env: 'OPENAI_API_KEY', key_status: 'missing', is_default: false },
  { name: 'qwen', type: 'openai', model: 'qwen-plus', key_env: 'DASHSCOPE_API_KEY', key_status: 'ok', is_default: false },
  { name: 'zhipu', type: 'openai', model: 'glm-4-flash', key_env: 'ZHIPUAI_API_KEY', key_status: 'missing', is_default: false },
]

function sampleActivity(): ActivityDTO {
  return {
    period: { kind: 'weekly', start: '2026-10-12', end: '2026-10-18', label: '2026-W42' },
    cancelled: false,
    commit_count: 11,
    repos_scanned: 18,
    include_prompts: true,
    missing_sources: ['kiro'],
    repos: [
      {
        name: 'rentcar-mp', path: '/Users/me/code/rentcar-mp', commit_count: 6,
        commits: [
          { date: '2026-10-12', hash: 'a1b2c3d', subject: 'feat: 选址页支持门店营业时间展示' },
          { date: '2026-10-13', hash: 'e4f5a6b', subject: 'fix: 修复周末取车时间选择溢出' },
          { date: '2026-10-14', hash: 'c7d8e9f', subject: 'perf: 首页 LCP 优化,图片懒加载' },
          { date: '2026-10-15', hash: '0a1b2c3', subject: 'feat: 订单页新增发票入口' },
          { date: '2026-10-16', hash: 'd4e5f6a', subject: 'chore: 升级基础库到 3.7.x' },
          { date: '2026-10-16', hash: 'b7c8d9e', subject: 'fix: 修复 iOS 键盘遮挡输入框' },
        ],
      },
      {
        name: 'weeklyReport', path: '/Users/me/Desktop/shao/05-项目/weeklyReport', commit_count: 3,
        commits: [
          { date: '2026-10-20', hash: '659e6f6', subject: 'ci: test on Python 3.10/3.12/3.13' },
          { date: '2026-10-19', hash: '32552f7', subject: 'feat: weekly-report CLI - git + AI sessions to report with any LLM' },
        ],
      },
      {
        name: 'h5-components', path: '/Users/me/code/h5-components', commit_count: 2,
        commits: [
          { date: '2026-10-14', hash: 'f1e2d3c', subject: 'feat: Calendar 组件支持区间选择' },
          { date: '2026-10-15', hash: 'a9b8c7d', subject: 'docs: 补充 Calendar API 文档' },
        ],
      },
    ],
    sessions: [
      {
        id: 'claude:s1', source: 'claude', source_label: 'Claude Code', title: '排查周末取车时间溢出',
        project: 'code/rentcar-mp', cwd: '/Users/me/code/rentcar-mp', branches: ['fix/weekend-time'],
        message_count: 42, first_date: '2026-10-13', last_date: '2026-10-13', date_approx: false,
        prompts: ['周末取车时间选择会溢出到第二天,帮我定位', '改成 clamp 到营业时间末尾试试'],
      },
      {
        id: 'claude:s2', source: 'claude', source_label: 'Claude Code', title: '首页 LCP 优化方案调研',
        project: 'code/rentcar-mp', cwd: '/Users/me/code/rentcar-mp', branches: ['main'],
        message_count: 28, first_date: '2026-10-14', last_date: '2026-10-14', date_approx: false,
        prompts: ['分析首页 LCP 偏慢的原因', '图片懒加载 + 骨架屏的方案评估'],
      },
      {
        id: 'claude:s3', source: 'claude', source_label: 'Claude Code', title: '周报工具 GUI 方案讨论',
        project: '05-项目/weeklyReport', cwd: '/Users/me/Desktop/shao/05-项目/weeklyReport', branches: ['main'],
        message_count: 61, first_date: '2026-10-20', last_date: '2026-10-21', date_approx: false,
        prompts: ['想给 weekly-report 加个 GUI,分析下技术选型', 'pywebview + React 的架构怎么设计'],
      },
      {
        id: 'codex:r1', source: 'codex', source_label: 'Codex', title: null,
        project: 'code/h5-components', cwd: '/Users/me/code/h5-components', branches: ['feat/calendar-range'],
        message_count: 19, first_date: '2026-10-14', last_date: '2026-10-15', date_approx: false,
        prompts: ['Calendar 组件加区间选择,注意禁用日期逻辑', '跑一下现有测试'],
      },
      {
        id: 'kiro-cli:c1', source: 'kiro-cli', source_label: 'Kiro CLI', title: '发票入口接口联调',
        project: 'code/rentcar-mp', cwd: '/Users/me/code/rentcar-mp', branches: [],
        message_count: 12, first_date: '2026-10-15', last_date: '2026-10-15', date_approx: false,
        prompts: ['对照 yapi 检查发票接口字段'],
      },
    ],
  }
}

const sampleReport = `# 周报（10.12 ~ 10.18）

## 本周完成

### 租车小程序（rentcar-mp）
- 选址页支持门店营业时间展示,修复周末取车时间溢出问题
- 首页性能优化:图片懒加载落地,LCP 明显改善
- 订单页新增发票入口,完成接口联调

### 组件库（h5-components）
- Calendar 组件支持日期区间选择,补充 API 文档

### 个人项目
- weekly-report CLI 开源:git 提交 + AI 会话双数据源,支持 10 家 LLM 生成周报

## 数据与思考
- AI 会话共 5 次,其中 GUI 技术选型调研尚未落成代码,下周继续

## 下周计划
- 完成 weekly-report GUI(pywebview + React)MVP
- 租车小程序回归测试与发版
`

export const mockApi: BridgeApi = {
  async get_config(): Promise<ConfigState> {
    await wait(120)
    return sampleConfig
  },
  async save_config(): Promise<{ ok: boolean; path: string }> {
    await wait(300)
    return { ok: true, path: '~/.config/weekly-report/config.toml' }
  },
  async list_providers(): Promise<{ providers: ProviderDTO[] }> {
    await wait(120)
    return { providers: sampleProviders }
  },
  async collect(): Promise<ActivityDTO> {
    for (const repo of ['rentcar-mp', 'weeklyReport', 'h5-components', '…more']) {
      await wait(150)
      emitProgress({ source: 'git', phase: 'collect', current: repo, scanned: 1, total: 3 })
    }
    emitProgress({ source: 'agents', phase: 'collect', current: 'Claude Code' })
    await wait(200)
    return sampleActivity()
  },
  async cancel_collect(): Promise<{ ok: boolean }> {
    return { ok: true }
  },
  async previous_report(): Promise<{ path: string | null; content: string | null }> {
    return { path: '~/weekly-reports/2026-W41.md', content: '# 周报（10.05 ~ 10.11）\n\n…' }
  },
  async generate(_selection: { session_ids: string[]; repo_paths: string[] }, options: { provider?: string }): Promise<GenerateResult> {
    await wait(900)
    return {
      report: sampleReport,
      title: '周报（10.12 ~ 10.18）',
      provider: options.provider ?? 'deepseek',
      model: 'deepseek-chat',
      filename: '2026-W42.md',
    }
  },
  async save_report(): Promise<{ path: string }> {
    await wait(200)
    return { path: '~/weekly-reports/2026-W42.md' }
  },
  async send_report(_markdown: string, _options: SendOptions): Promise<{ result: string }> {
    await wait(700)
    return { result: 'sent to me@example.com via smtp.qq.com' }
  },
  async effective_recipients(method?: string): Promise<EffectiveRecipients> {
    await wait(100)
    return { to: sampleConfig.config.email.to, cc: [], method: method ?? 'smtp', error: null }
  },
  async pick_file(): Promise<{ path: string | null; error: string | null }> {
    return { path: '~/weekly-reports/2026-W41.md', error: null }
  },
}
