import { useEffect, useState } from 'react'
import { errorText } from '../api'
import type { BridgeApi } from '../api'
import { Banner, splitList } from '../components/ui'

interface SettingsDraft {
  provider: string
  language: string
  author_name: string
  output_dir: string
  default_week: string
  extra_instructions: string
  gitRoots: string
  gitAuthors: string
  gitDepth: number
  gitExclude: string
  agentsEnabled: boolean
  agentSources: string[]
  includePrompts: boolean
  agentsExclude: string
  emailMethod: string
  emailTo: string
  emailCc: string
  emailSubject: string
  smtpHost: string
  smtpPort: number
  smtpSecurity: string
  smtpUsername: string
  smtpPasswordEnv: string
  smtpFrom: string
}

const AGENT_SOURCES = [
  ['claude', 'Claude Code'],
  ['codex', 'Codex'],
  ['kiro', 'Kiro'],
  ['kiro-cli', 'Kiro CLI'],
] as const

const toLines = (list: string[] | undefined): string => (list ?? []).join('\n')

export default function SettingsPage({ api }: { api: BridgeApi }) {
  const [draft, setDraft] = useState<SettingsDraft | null>(null)
  const [configPath, setConfigPath] = useState<string | null>(null)
  const [exists, setExists] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [savedTo, setSavedTo] = useState('')

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const state = await api.get_config()
        if (cancelled) return
        const cfg = state.config
        setConfigPath(state.config_path)
        setExists(state.exists)
        setDraft({
          provider: cfg.provider,
          language: cfg.language,
          author_name: cfg.author_name,
          output_dir: cfg.output_dir,
          default_week: cfg.default_week,
          extra_instructions: cfg.extra_instructions ?? '',
          gitRoots: toLines(cfg.git?.roots),
          gitAuthors: (cfg.git?.authors ?? []).join(', '),
          gitDepth: cfg.git?.max_depth ?? 4,
          gitExclude: toLines(cfg.git?.exclude),
          agentsEnabled: cfg.agents?.enabled ?? true,
          agentSources: cfg.agents?.sources ?? [],
          includePrompts: cfg.agents?.include_prompts ?? true,
          agentsExclude: toLines(cfg.agents?.exclude),
          emailMethod: cfg.email?.method ?? 'smtp',
          emailTo: (cfg.email?.to ?? []).join(', '),
          emailCc: (cfg.email?.cc ?? []).join(', '),
          emailSubject: cfg.email?.subject ?? '',
          smtpHost: cfg.email?.smtp?.host ?? '',
          smtpPort: cfg.email?.smtp?.port ?? 465,
          smtpSecurity: cfg.email?.smtp?.security ?? 'ssl',
          smtpUsername: cfg.email?.smtp?.username ?? '',
          smtpPasswordEnv: cfg.email?.smtp?.password_env ?? 'SMTP_PASSWORD',
          smtpFrom: cfg.email?.smtp?.from ?? '',
        })
      } catch (loadError) {
        if (!cancelled) setError(errorText(loadError))
      }
    })()
    return () => { cancelled = true }
  }, [api])

  function patch(part: Partial<SettingsDraft>) {
    setDraft(current => (current ? { ...current, ...part } : current))
  }

  function toggleSource(source: string) {
    if (!draft) return
    const next = draft.agentSources.includes(source)
      ? draft.agentSources.filter(item => item !== source)
      : [...draft.agentSources, source]
    patch({ agentSources: next })
  }

  async function save() {
    if (!draft) return
    setSaving(true)
    setError('')
    setSavedTo('')
    try {
      const saved = await api.save_config({
        provider: draft.provider,
        language: draft.language,
        author_name: draft.author_name,
        output_dir: draft.output_dir,
        default_week: draft.default_week,
        extra_instructions: draft.extra_instructions,
        git: {
          roots: toLinesList(draft.gitRoots),
          authors: splitList(draft.gitAuthors),
          max_depth: Number(draft.gitDepth) || 4,
          exclude: toLinesList(draft.gitExclude),
        },
        agents: {
          enabled: draft.agentsEnabled,
          sources: draft.agentSources,
          include_prompts: draft.includePrompts,
          exclude: toLinesList(draft.agentsExclude),
        },
        email: {
          method: draft.emailMethod,
          to: splitList(draft.emailTo),
          cc: splitList(draft.emailCc),
          subject: draft.emailSubject,
          smtp: {
            host: draft.smtpHost,
            port: Number(draft.smtpPort) || 465,
            security: draft.smtpSecurity,
            username: draft.smtpUsername,
            password_env: draft.smtpPasswordEnv,
            from: draft.smtpFrom,
          },
        },
      })
      setSavedTo(saved.path)
      setExists(true)
    } catch (saveError) {
      setError(errorText(saveError))
    } finally {
      setSaving(false)
    }
  }

  if (!draft) {
    return (
      <div className="page">
        <h1>设置</h1>
        {error ? <Banner kind="error">{error}</Banner> : <p className="muted">读取配置中…</p>}
      </div>
    )
  }

  return (
    <div className="page">
      <h1>设置</h1>
      <p className="muted">
        {exists ? `配置文件: ${configPath}` : `未找到配置文件,保存后将创建 ${configPath}`}
      </p>

      <section className="card">
        <h2>基础</h2>
        <div className="grid-2">
          <label className="field">
            <span className="field-label">默认 AI 服务商</span>
            <input value={draft.provider} onChange={event => patch({ provider: event.target.value })} />
          </label>
          <div className="field">
            <span className="field-label">报告语言</span>
            <div className="segmented">
              <button className={draft.language === 'zh' ? 'on' : ''} onClick={() => patch({ language: 'zh' })}>中文</button>
              <button className={draft.language === 'en' ? 'on' : ''} onClick={() => patch({ language: 'en' })}>English</button>
            </div>
          </div>
          <label className="field">
            <span className="field-label">署名（可空）</span>
            <input value={draft.author_name} onChange={event => patch({ author_name: event.target.value })} />
          </label>
          <label className="field">
            <span className="field-label">报告保存目录</span>
            <input value={draft.output_dir} onChange={event => patch({ output_dir: event.target.value })} />
          </label>
          <div className="field">
            <span className="field-label">默认周（命令行不带参数时）</span>
            <select value={draft.default_week}
                    onChange={event => patch({ default_week: event.target.value })}>
              <option value="this">本周</option>
              <option value="last">上周</option>
              <option value="prev">上上周</option>
            </select>
          </div>
          <label className="field">
            <span className="field-label">额外指令（附加到系统提示）</span>
            <input value={draft.extra_instructions} onChange={event => patch({ extra_instructions: event.target.value })} />
          </label>
        </div>
      </section>

      <section className="card">
        <h2>Git 采集</h2>
        <label className="field">
          <span className="field-label">代码根目录（每行一个,支持 ~）</span>
          <textarea rows={3} value={draft.gitRoots}
                    onChange={event => patch({ gitRoots: event.target.value })} />
        </label>
        <div className="grid-2">
          <label className="field">
            <span className="field-label">提交作者邮箱（逗号分隔,留空用各仓库自身配置）</span>
            <input value={draft.gitAuthors} onChange={event => patch({ gitAuthors: event.target.value })} />
          </label>
          <label className="field">
            <span className="field-label">扫描深度</span>
            <input type="number" min={1} max={8} value={draft.gitDepth}
                   onChange={event => patch({ gitDepth: Number(event.target.value) || 4 })} />
          </label>
        </div>
        <label className="field">
          <span className="field-label">排除仓库（每行一个,路径子串匹配）</span>
          <textarea rows={2} value={draft.gitExclude}
                    onChange={event => patch({ gitExclude: event.target.value })} />
        </label>
      </section>

      <section className="card">
        <h2>AI 会话采集</h2>
        <label className="inline check">
          <input type="checkbox" checked={draft.agentsEnabled}
                 onChange={event => patch({ agentsEnabled: event.target.checked })} />
          启用会话采集
        </label>
        <div className="field">
          <span className="field-label">数据源</span>
          <div className="row">
            {AGENT_SOURCES.map(([source, label]) => (
              <label key={source} className="inline check">
                <input type="checkbox" checked={draft.agentSources.includes(source)}
                       onChange={() => toggleSource(source)} />
                {label}
              </label>
            ))}
          </div>
        </div>
        <label className="inline check">
          <input type="checkbox" checked={draft.includePrompts}
                 onChange={event => patch({ includePrompts: event.target.checked })} />
          发送会话输入内容给模型（关闭则只用标题）
        </label>
        <label className="field">
          <span className="field-label">排除项目（每行一个,匹配会话工作目录子串）</span>
          <textarea rows={2} value={draft.agentsExclude}
                    onChange={event => patch({ agentsExclude: event.target.value })} />
        </label>
      </section>

      <section className="card">
        <h2>邮件</h2>
        <div className="field">
          <span className="field-label">发送方式</span>
          <div className="segmented">
            <button className={draft.emailMethod === 'smtp' ? 'on' : ''}
                    onClick={() => patch({ emailMethod: 'smtp' })}>SMTP</button>
            <button className={draft.emailMethod === 'agently' ? 'on' : ''}
                    onClick={() => patch({ emailMethod: 'agently' })}>agently</button>
          </div>
        </div>
        <div className="grid-2">
          <label className="field">
            <span className="field-label">收件人（逗号分隔）</span>
            <input value={draft.emailTo} onChange={event => patch({ emailTo: event.target.value })} />
          </label>
          <label className="field">
            <span className="field-label">抄送</span>
            <input value={draft.emailCc} onChange={event => patch({ emailCc: event.target.value })} />
          </label>
          <label className="field">
            <span className="field-label">主题模板（{`{title} {name} {label} {start} {end}`}）</span>
            <input value={draft.emailSubject} onChange={event => patch({ emailSubject: event.target.value })} />
          </label>
        </div>
        <h3>SMTP 服务器</h3>
        <div className="grid-2">
          <label className="field">
            <span className="field-label">服务器</span>
            <input value={draft.smtpHost} onChange={event => patch({ smtpHost: event.target.value })} />
          </label>
          <div className="field">
            <span className="field-label">加密方式</span>
            <select value={draft.smtpSecurity}
                    onChange={event => patch({ smtpSecurity: event.target.value })}>
              <option value="ssl">SSL</option>
              <option value="starttls">STARTTLS</option>
              <option value="none">无</option>
            </select>
          </div>
          <label className="field">
            <span className="field-label">端口</span>
            <input type="number" value={draft.smtpPort}
                   onChange={event => patch({ smtpPort: Number(event.target.value) || 465 })} />
          </label>
          <label className="field">
            <span className="field-label">用户名</span>
            <input value={draft.smtpUsername} onChange={event => patch({ smtpUsername: event.target.value })} />
          </label>
          <label className="field">
            <span className="field-label">发件人（留空同用户名）</span>
            <input value={draft.smtpFrom} onChange={event => patch({ smtpFrom: event.target.value })} />
          </label>
          <label className="field">
            <span className="field-label">密码所在环境变量</span>
            <input value={draft.smtpPasswordEnv}
                   onChange={event => patch({ smtpPasswordEnv: event.target.value })} />
          </label>
        </div>
      </section>

      <div className="actions">
        <button className="primary" disabled={saving} onClick={save}>
          {saving ? '保存中…' : '保存配置'}
        </button>
        {savedTo ? <span className="muted small">已保存到 {savedTo}</span> : null}
      </div>
      {error ? <Banner kind="error">{error}</Banner> : null}
      <Banner kind="info">
        保存会重写 TOML 文件,文件里的注释会丢失;表单未覆盖的配置项保持不变。API key
        建议放环境变量,不写进配置。
      </Banner>
    </div>
  )
}

function toLinesList(text: string): string[] {
  return text.split('\n').map(line => line.trim()).filter(Boolean)
}
