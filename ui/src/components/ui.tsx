import type { ReactNode } from 'react'

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="spinner-wrap">
      <span className="spinner" aria-hidden />
      {label ? <span className="spinner-label">{label}</span> : null}
    </span>
  )
}

export function Banner({ kind, children }: { kind: 'error' | 'ok' | 'info'; children: ReactNode }) {
  return <div className={`banner banner-${kind}`}>{children}</div>
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  )
}

export function KeyDot({ status }: { status: string }) {
  const label: Record<string, string> = {
    ok: '密钥已配置', missing: '密钥未配置', config: '写在配置里', none: '无需密钥',
  }
  return (
    <span className={`key-dot key-${status}`} title={label[status] ?? status}>
      <span className="key-dot-core" aria-hidden />
      {label[status] ?? status}
    </span>
  )
}

export function firstHeading(markdown: string): string {
  for (const line of markdown.split('\n')) {
    if (line.startsWith('# ')) return line.slice(2).trim()
  }
  return 'Work report'
}

export function splitList(text: string): string[] {
  return text.split(/[,，;；\s]+/).map(part => part.trim()).filter(Boolean)
}
