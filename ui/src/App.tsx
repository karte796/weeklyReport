import { useState } from 'react'
import { isEmbedded, useBridgeApi } from './api'
import type { ActivityDTO, GenerateResult, PeriodSpec } from './api'
import CollectPage from './pages/CollectPage'
import GeneratePage from './pages/GeneratePage'
import SendPage from './pages/SendPage'
import SettingsPage from './pages/SettingsPage'

export type PageName = 'collect' | 'generate' | 'send' | 'settings'

export interface Selection {
  repos: Set<string>
  sessions: Set<string>
}

export default function App() {
  const bridge = useBridgeApi()
  const [page, setPage] = useState<PageName>('collect')
  const [activity, setActivity] = useState<ActivityDTO | null>(null)
  const [periodSpec, setPeriodSpec] = useState<PeriodSpec>({ week: 'last' })
  const [selection, setSelection] = useState<Selection>({ repos: new Set(), sessions: new Set() })
  const [generation, setGeneration] = useState<GenerateResult | null>(null)
  const [reportText, setReportText] = useState('')

  if (!bridge) {
    return <div className="boot">正在连接本地服务…</div>
  }

  const steps: { name: PageName; label: string; enabled: boolean }[] = [
    { name: 'collect', label: '1 · 采集', enabled: true },
    { name: 'generate', label: '2 · 生成', enabled: !!activity },
    { name: 'send', label: '3 · 发送', enabled: !!reportText },
  ]

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-name">weekly-report</div>
          <div className="brand-sub">git + AI 会话 → 周报</div>
        </div>
        <nav className="steps">
          {steps.map(step => (
            <button
              key={step.name}
              className={`step ${page === step.name ? 'active' : ''}`}
              disabled={!step.enabled}
              onClick={() => setPage(step.name)}
            >
              {step.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <button
            className={`step ${page === 'settings' ? 'active' : ''}`}
            onClick={() => setPage('settings')}
          >
            设置
          </button>
          {!isEmbedded && <div className="mock-note">浏览器预览 · mock 数据</div>}
        </div>
      </aside>
      <main className="content">
        {page === 'collect' && (
          <CollectPage
            api={bridge}
            activity={activity}
            selection={selection}
            onCollected={(result, spec, nextSelection) => {
              setActivity(result)
              setPeriodSpec(spec)
              setSelection(nextSelection)
              setGeneration(null)   // a fresh collection invalidates the old report
              setReportText('')
            }}
            onSelectionChange={setSelection}
            onNext={() => setPage('generate')}
          />
        )}
        {page === 'generate' && (
          <GeneratePage
            api={bridge}
            activity={activity}
            periodSpec={periodSpec}
            selection={selection}
            generation={generation}
            reportText={reportText}
            onGenerated={(result, text) => {
              setGeneration(result)
              setReportText(text)
            }}
            onReportChange={setReportText}
            onNext={() => setPage('send')}
          />
        )}
        {page === 'send' && <SendPage api={bridge} reportText={reportText} />}
        {page === 'settings' && <SettingsPage api={bridge} />}
      </main>
    </div>
  )
}
