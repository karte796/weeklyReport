import { useEffect, useState } from 'react'
import { errorText } from '../api'
import type { BridgeApi, ProgressEvent } from '../api'
import type { ActivityDTO, PeriodSpec, RepoDTO, SessionDTO } from '../api/types'
import type { Selection } from '../App'
import { Banner, Spinner } from '../components/ui'

interface Props {
  api: BridgeApi
  activity: ActivityDTO | null
  selection: Selection
  onCollected: (activity: ActivityDTO, spec: PeriodSpec, selection: Selection) => void
  onSelectionChange: (selection: Selection) => void
  onNext: () => void
}

type PeriodMode = 'week' | 'month' | 'range'
type WeekChoice = 'this' | 'last' | 'prev'

export default function CollectPage({
  api, activity, selection, onCollected, onSelectionChange, onNext,
}: Props) {
  const [mode, setMode] = useState<PeriodMode>('week')
  const [week, setWeek] = useState<WeekChoice>('last')
  const [month, setMonth] = useState(new Date().getMonth() + 1)
  const [year, setYear] = useState(new Date().getFullYear())
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [topic, setTopic] = useState('')
  const [keywords, setKeywords] = useState('')
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<ProgressEvent | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    window.__wrProgress = event => setProgress(event)
    return () => { window.__wrProgress = undefined }
  }, [])

  const periodSpec: PeriodSpec =
    mode === 'week' ? { week }
    : mode === 'month' ? { month, year }
    : { since, until }

  async function runCollect() {
    setError('')
    if (mode === 'range' && (!since || !until)) {
      setError('自定义区间需要填写起止日期')
      return
    }
    setBusy(true)
    setProgress(null)
    try {
      const result = await api.collect(periodSpec, topic, keywords)
      onCollected(result, periodSpec, {
        repos: new Set(result.repos.map(repo => repo.path)),
        sessions: new Set(result.sessions.map(session => session.id)),
      })
    } catch (collectError) {
      setError(errorText(collectError))
    } finally {
      setBusy(false)
      setProgress(null)
    }
  }

  function toggle(kind: 'repos' | 'sessions', key: string) {
    const next = new Set(selection[kind])
    if (next.has(key)) next.delete(key)
    else next.add(key)
    onSelectionChange({ ...selection, [kind]: next })
  }

  function selectAll(selected: boolean) {
    if (!activity) return
    onSelectionChange(selected
      ? {
          repos: new Set(activity.repos.map(repo => repo.path)),
          sessions: new Set(activity.sessions.map(session => session.id)),
        }
      : { repos: new Set(), sessions: new Set() })
  }

  const selectedTotal = selection.repos.size + selection.sessions.size
  const progressSource = progress?.source === 'git' ? 'Git 仓库' : 'AI 会话'
  const progressLabel = busy
    ? progress?.current ? `${progressSource} · ${progress.current}` : `${progressSource} · 准备中…`
    : ''

  const grouped = new Map<string, SessionDTO[]>()
  activity?.sessions.forEach(session => {
    const list = grouped.get(session.project) ?? []
    list.push(session)
    grouped.set(session.project, list)
  })

  return (
    <div className="page">
      <h1>采集</h1>
      <p className="muted">读取选定时段内的 git 提交与 AI 助手会话（只读）。</p>

      <section className="card">
        <div className="segmented">
          {([['week', '按周'], ['month', '按月'], ['range', '自定义区间']] as const).map(([value, label]) => (
            <button key={value} className={mode === value ? 'on' : ''} onClick={() => setMode(value)}>
              {label}
            </button>
          ))}
        </div>
        <div className="row">
          {mode === 'week' && (
            <div className="segmented">
              {([['this', '本周'], ['last', '上周'], ['prev', '上上周']] as const).map(([value, label]) => (
                <button key={value} className={week === value ? 'on' : ''} onClick={() => setWeek(value)}>
                  {label}
                </button>
              ))}
            </div>
          )}
          {mode === 'month' && (
            <>
              <label className="inline">月份
                <input type="number" min={1} max={12} value={month}
                       onChange={event => setMonth(Math.min(12, Math.max(1, Number(event.target.value) || 1)))} />
              </label>
              <label className="inline">年份
                <input type="number" value={year}
                       onChange={event => setYear(Number(event.target.value) || year)} />
              </label>
            </>
          )}
          {mode === 'range' && (
            <>
              <label className="inline">起
                <input type="date" value={since} onChange={event => setSince(event.target.value)} />
              </label>
              <label className="inline">止（含当天）
                <input type="date" value={until} onChange={event => setUntil(event.target.value)} />
              </label>
            </>
          )}
        </div>
        <button className="link" onClick={() => setShowAdvanced(!showAdvanced)}>
          {showAdvanced ? '收起选项' : '专项报告（主题 / 关键词）'}
        </button>
        {showAdvanced && (
          <div className="row">
            <label className="inline grow">主题
              <input value={topic} onChange={event => setTopic(event.target.value)} placeholder="如:性能" />
            </label>
            <label className="inline grow">关键词
              <input value={keywords} onChange={event => setKeywords(event.target.value)} placeholder="逗号分隔,默认同主题" />
            </label>
          </div>
        )}
        <div className="actions">
          {busy ? (
            <>
              <Spinner label={progressLabel} />
              {progress?.total ? <progress value={(progress.scanned ?? 0) + 1} max={progress.total} /> : null}
              <button className="ghost" onClick={() => { api.cancel_collect().catch(() => undefined) }}>
                取消
              </button>
            </>
          ) : (
            <button className="primary" onClick={runCollect}>采集</button>
          )}
        </div>
        {error ? <Banner kind="error">{error}</Banner> : null}
      </section>

      {activity && (
        <>
          <div className="summary">
            <strong>{activity.period.label}</strong>
            <span>
              {activity.commit_count} 次提交 · {activity.repos.length}/{activity.repos_scanned} 个仓库 ·{' '}
              {activity.sessions.length} 个 AI 会话
            </span>
            {activity.cancelled && <span className="badge warn">已取消（部分结果）</span>}
            {activity.missing_sources.length > 0 && (
              <span className="badge">未找到: {activity.missing_sources.join(', ')}</span>
            )}
          </div>

          <section className="card">
            <div className="card-head">
              <h2>Git 仓库</h2>
              <div className="spacer" />
              <span className="muted small">{selection.repos.size}/{activity.repos.length} 已选</span>
            </div>
            {activity.repos.map(repo => (
              <RepoRow key={repo.path} repo={repo}
                       checked={selection.repos.has(repo.path)}
                       onToggle={() => toggle('repos', repo.path)} />
            ))}
            {activity.repos.length === 0 && (
              <div className="muted">该时段没有提交。可在「设置」里检查 git.roots。</div>
            )}
          </section>

          <section className="card">
            <div className="card-head">
              <h2>AI 会话</h2>
              <div className="spacer" />
              <span className="muted small">{selection.sessions.size}/{activity.sessions.length} 已选</span>
            </div>
            {[...grouped.entries()].map(([project, sessions]) => (
              <div key={project} className="group">
                <div className="group-title">{project}</div>
                {sessions.map(session => (
                  <SessionRow key={session.id} session={session}
                              checked={selection.sessions.has(session.id)}
                              onToggle={() => toggle('sessions', session.id)} />
                ))}
              </div>
            ))}
            {activity.sessions.length === 0 && <div className="muted">该时段没有 AI 会话。</div>}
          </section>

          <div className="actions">
            <button className="ghost" onClick={() => selectAll(true)}>全选</button>
            <button className="ghost" onClick={() => selectAll(false)}>全不选</button>
            <div className="spacer" />
            <span className="muted small">已选 {selectedTotal} 项进入生成</span>
            <button className="primary" disabled={selectedTotal === 0} onClick={onNext}>
              下一步：生成
            </button>
          </div>
        </>
      )}
    </div>
  )
}

function RepoRow({ repo, checked, onToggle }: {
  repo: RepoDTO
  checked: boolean
  onToggle: () => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className={`row-item ${checked ? '' : 'off'}`}>
      <div className="row-main">
        <input type="checkbox" checked={checked} onChange={onToggle} />
        <button className="row-title" onClick={() => setOpen(!open)}>{repo.name}</button>
        <span className="badge">{repo.commit_count} 提交</span>
        <div className="spacer" />
        <button className="link" onClick={() => setOpen(!open)}>{open ? '收起' : '明细'}</button>
      </div>
      {open && (
        <ul className="commits">
          {repo.commits.map(commit => (
            <li key={commit.hash}>
              <span className="muted">{commit.date}</span> {commit.subject} <code>{commit.hash}</code>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function SessionRow({ session, checked, onToggle }: {
  session: SessionDTO
  checked: boolean
  onToggle: () => void
}) {
  const [open, setOpen] = useState(false)
  const dateSpan = session.first_date
    ? `${session.date_approx ? '≈' : ''}${session.first_date.slice(5)}${session.last_date && session.last_date !== session.first_date ? `~${session.last_date.slice(5)}` : ''}`
    : ''
  const metaParts = [
    dateSpan,
    session.branches.length > 0 ? `branch ${session.branches.join(', ')}` : '',
    `${session.message_count} 条消息`,
  ].filter(Boolean)
  return (
    <div className={`row-item ${checked ? '' : 'off'}`}>
      <div className="row-main">
        <input type="checkbox" checked={checked} onChange={onToggle} />
        <span className="chip">{session.source_label}</span>
        <button className="row-title" onClick={() => setOpen(!open)}>
          {session.title ?? '(未命名会话)'}
        </button>
        <div className="spacer" />
        <span className="muted small">{metaParts.join(' · ')}</span>
      </div>
      {open && session.prompts.length > 0 && (
        <ul className="prompts">
          {session.prompts.map((prompt, index) => (
            <li key={index}>{prompt}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
