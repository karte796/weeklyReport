import { useEffect, useState } from 'react'
import { errorText } from '../api'
import type { BridgeApi } from '../api'
import type { EffectiveRecipients } from '../api/types'
import { Banner, firstHeading, splitList, Spinner } from '../components/ui'

export default function SendPage({ api, reportText }: { api: BridgeApi; reportText: string }) {
  const [method, setMethod] = useState('smtp')
  const [toText, setToText] = useState('')
  const [ccText, setCcText] = useState('')
  const [subject, setSubject] = useState('')
  const [effective, setEffective] = useState<EffectiveRecipients | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState('')

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const configState = await api.get_config()
        const chosen = configState.config.email.method === 'agently' ? 'agently' : 'smtp'
        const recipients = await api.effective_recipients(chosen)
        if (cancelled) return
        setMethod(chosen)
        setEffective(recipients)
        setToText(recipients.to.join(', '))
        setCcText(recipients.cc.join(', '))
        setSubject(firstHeading(reportText))
      } catch (loadError) {
        if (!cancelled) setError(errorText(loadError))
      }
    })()
    return () => { cancelled = true }
  }, [api, reportText])

  async function updateEffective(chosen: string) {
    setMethod(chosen)
    try {
      const recipients = await api.effective_recipients(chosen)
      setEffective(recipients)
    } catch {
      setEffective(null)  // keep the form usable; the config default is still shown
    }
  }

  async function send() {
    const to = splitList(toText)
    const cc = splitList(ccText)
    if (method === 'smtp' && to.length === 0) {
      setError('SMTP 发送需要至少一个收件人')
      return
    }
    const confirmed = window.confirm(
      `确认发送？\n\n方式: ${method}\n收件人: ${to.join(', ') || '(自己的 agent 邮箱)'}\n` +
      `抄送: ${cc.join(', ') || '无'}\n主题: ${subject}`,
    )
    if (!confirmed) return
    setBusy(true)
    setError('')
    setResult('')
    try {
      const sent = await api.send_report(reportText, { to, cc, subject, method })
      setResult(sent.result)
    } catch (sendError) {
      setError(errorText(sendError))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page">
      <h1>发送</h1>
      <p className="muted">发送前请确认报告内容与收件人；发送不可撤回。</p>

      <section className="card">
        <div className="field">
          <span className="field-label">发送方式</span>
          <div className="segmented">
            <button className={method === 'smtp' ? 'on' : ''} onClick={() => void updateEffective('smtp')}>
              SMTP
            </button>
            <button className={method === 'agently' ? 'on' : ''} onClick={() => void updateEffective('agently')}>
              agently（QQ 邮箱 agent）
            </button>
          </div>
        </div>
        <div className="grid-2">
          <label className="field">
            <span className="field-label">收件人（逗号分隔）</span>
            <input value={toText} onChange={event => setToText(event.target.value)}
                   placeholder={method === 'agently' ? '留空发送到自己的 agent 邮箱' : 'name@example.com'} />
          </label>
          <label className="field">
            <span className="field-label">抄送</span>
            <input value={ccText} onChange={event => setCcText(event.target.value)} />
          </label>
        </div>
        <label className="field">
          <span className="field-label">主题</span>
          <input value={subject} onChange={event => setSubject(event.target.value)} />
        </label>
        {method === 'agently' && effective?.error && (
          <Banner kind="error">无法获取 agent 邮箱地址: {effective.error}（需先 agently-cli auth login）</Banner>
        )}
        <div className="actions">
          {busy ? <Spinner label="发送中…" /> : (
            <button className="primary" disabled={!reportText.trim()} onClick={send}>
              确认并发送
            </button>
          )}
        </div>
        {error ? <Banner kind="error">{error}</Banner> : null}
        {result ? <Banner kind="ok">{result}</Banner> : null}
      </section>

      <section className="card">
        <div className="card-head">
          <h2>报告预览</h2>
          <div className="spacer" />
          <span className="muted small">{reportText.split('\n').length} 行</span>
        </div>
        <pre className="report-preview">{reportText.slice(0, 1200)}{reportText.length > 1200 ? '\n…' : ''}</pre>
      </section>
    </div>
  )
}
