import { useEffect, useState } from 'react'
import { errorText } from '../api'
import type { BridgeApi, PeriodSpec } from '../api'
import type { ActivityDTO, GenerateResult, ProviderDTO } from '../api/types'
import type { Selection } from '../App'
import { Banner, KeyDot, Spinner } from '../components/ui'

interface Props {
  api: BridgeApi
  activity: ActivityDTO | null
  periodSpec: PeriodSpec
  selection: Selection
  generation: GenerateResult | null
  reportText: string
  onGenerated: (result: GenerateResult, text: string) => void
  onReportChange: (text: string) => void
  onNext: () => void
}

type PreviousMode = 'auto' | 'none' | 'file'

export default function GeneratePage({
  api, activity, periodSpec, selection, generation, reportText,
  onGenerated, onReportChange, onNext,
}: Props) {
  const [providers, setProviders] = useState<ProviderDTO[]>([])
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [language, setLanguage] = useState('zh')
  const [previousMode, setPreviousMode] = useState<PreviousMode>('auto')
  const [previousPath, setPreviousPath] = useState<string | null>(null)
  const [previousFile, setPreviousFile] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [savedPath, setSavedPath] = useState('')

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const [providerState, configState, previous] = await Promise.all([
          api.list_providers(),
          api.get_config(),
          api.previous_report(periodSpec, ''),
        ])
        if (cancelled) return
        setProviders(providerState.providers)
        const configured = providerState.providers.find(item => item.name === configState.config.provider)
        const withKey = providerState.providers.find(item => item.key_status === 'ok' || item.key_status === 'none')
        setProvider(configured?.name ?? withKey?.name ?? providerState.providers[0]?.name ?? '')
        setLanguage(configState.config.language === 'en' ? 'en' : 'zh')
        setPreviousPath(previous.path)
      } catch (loadError) {
        if (!cancelled) setError(errorText(loadError))
      }
    })()
    return () => { cancelled = true }
  }, [api, periodSpec])

  const providerModel = providers.find(item => item.name === provider)?.model ?? ''

  async function runGenerate() {
    if (!activity) return
    setBusy(true)
    setError('')
    setSavedPath('')
    try {
      const result = await api.generate(
        { session_ids: [...selection.sessions], repo_paths: [...selection.repos] },
        {
          provider,
          model: model.trim() || undefined,
          language,
          // 'file' without a path falls back to auto-lookup instead of sending the literal word
          previous: previousMode === 'file'
            ? (previousFile.trim() || 'auto')
            : previousMode,
        },
      )
      onGenerated(result, result.report)
    } catch (generateError) {
      setError(errorText(generateError))
    } finally {
      setBusy(false)
    }
  }

  async function saveReport() {
    if (!generation) return
    try {
      const saved = await api.save_report(reportText, generation.filename)
      setSavedPath(saved.path)
    } catch (saveError) {
      setError(errorText(saveError))
    }
  }

  async function pickPreviousFile() {
    try {
      const picked = await api.pick_file('.md')
      if (picked.path) setPreviousFile(picked.path)
      else if (picked.error) setError(`选择文件失败: ${picked.error}（可直接输入路径）`)
    } catch (pickError) {
      setError(errorText(pickError))
    }
  }

  const keyStatus = providers.find(item => item.name === provider)?.key_status

  return (
    <div className="page">
      <h1>生成</h1>
      <p className="muted">
        将已选的 {selection.repos.size} 个仓库、{selection.sessions.size} 个会话交给大模型整理
        {activity ? `（${activity.period.label}）` : ''}。
      </p>

      <section className="card">
        <div className="grid-2">
          <label className="field">
            <span className="field-label">AI 服务商</span>
            <select value={provider} onChange={event => setProvider(event.target.value)}>
              {providers.map(item => (
                <option key={item.name} value={item.name}>
                  {item.name}（{item.model}）
                </option>
              ))}
            </select>
            {keyStatus ? <span className="field-hint"><KeyDot status={keyStatus} /></span> : null}
          </label>
          <label className="field">
            <span className="field-label">模型（留空用默认）</span>
            <input value={model} placeholder={providerModel}
                   onChange={event => setModel(event.target.value)} />
          </label>
          <div className="field">
            <span className="field-label">报告语言</span>
            <div className="segmented">
              <button className={language === 'zh' ? 'on' : ''} onClick={() => setLanguage('zh')}>中文</button>
              <button className={language === 'en' ? 'on' : ''} onClick={() => setLanguage('en')}>English</button>
            </div>
          </div>
          <div className="field">
            <span className="field-label">上期报告</span>
            <div className="radio-list">
              <label className="inline">
                <input type="radio" checked={previousMode === 'auto'} onChange={() => setPreviousMode('auto')} />
                自动查找 {previousPath ? `（${previousPath}）` : '（未找到）'}
              </label>
              <label className="inline">
                <input type="radio" checked={previousMode === 'none'} onChange={() => setPreviousMode('none')} />
                不使用
              </label>
              <label className="inline">
                <input type="radio" checked={previousMode === 'file'} onChange={() => setPreviousMode('file')} />
                指定文件
              </label>
              {previousMode === 'file' && (
                <div className="row">
                  <input className="grow" value={previousFile} placeholder="报告 .md 路径"
                         onChange={event => setPreviousFile(event.target.value)} />
                  <button className="ghost" onClick={pickPreviousFile}>选择…</button>
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="actions">
          {busy ? (
            <Spinner label={`正在用 ${provider} 生成,可能需要一两分钟…`} />
          ) : (
            <button className="primary" disabled={!activity || !provider} onClick={runGenerate}>
              {generation ? '重新生成' : '生成报告'}
            </button>
          )}
        </div>
        {error ? <Banner kind="error">{error}</Banner> : null}
      </section>

      {generation && (
        <section className="card">
          <div className="card-head">
            <h2>报告（可编辑）</h2>
            <div className="spacer" />
            <span className="muted small">{generation.provider} · {generation.model} · {generation.filename}</span>
          </div>
          <textarea className="report-editor" value={reportText} spellCheck={false}
                    onChange={event => onReportChange(event.target.value)} />
          <div className="actions">
            <button className="ghost" onClick={saveReport}>保存到报告目录</button>
            <div className="spacer" />
            {savedPath ? <span className="muted small">已保存: {savedPath}</span> : null}
            <button className="primary" disabled={!reportText.trim()} onClick={onNext}>
              下一步：发送
            </button>
          </div>
        </section>
      )}
    </div>
  )
}
