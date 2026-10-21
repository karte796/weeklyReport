import { useEffect, useState } from 'react'
import { mockApi } from './mock'
import type {
  ActivityDTO, ConfigState, EffectiveRecipients, GenerateOptions, GenerateResult,
  PeriodSpec, ProgressEvent, ProviderDTO, SendOptions,
} from './types'

export type {
  ActivityDTO, AppConfig, CommitDTO, ConfigState, EffectiveRecipients,
  GenerateOptions, GenerateResult, KeyStatus, PeriodInfo, PeriodSpec,
  ProgressEvent, ProviderDTO, RepoDTO, SendOptions, SessionDTO, SmtpConfig,
} from './types'

export interface BridgeApi {
  get_config(): Promise<ConfigState>
  save_config(data: Record<string, unknown>): Promise<{ ok: boolean; path: string }>
  list_providers(): Promise<{ providers: ProviderDTO[] }>
  collect(period: PeriodSpec, topic: string, keywords: string): Promise<ActivityDTO>
  cancel_collect(): Promise<{ ok: boolean }>
  previous_report(period: PeriodSpec, topic: string): Promise<{ path: string | null; content: string | null }>
  generate(selection: { session_ids: string[]; repo_paths: string[] }, options: GenerateOptions): Promise<GenerateResult>
  save_report(markdown: string, filename?: string): Promise<{ path: string }>
  send_report(markdown: string, options: SendOptions): Promise<{ result: string }>
  effective_recipients(method?: string): Promise<EffectiveRecipients>
  pick_file(suffix?: string): Promise<{ path: string | null; error: string | null }>
}

declare global {
  interface Window {
    pywebview?: { api: BridgeApi }
    __wrProgress?: (event: ProgressEvent) => void
  }
}

/** True inside the pywebview window; false in a plain browser (mock api is used). */
export const isEmbedded = typeof window !== 'undefined' && 'pywebview' in window

/**
 * The bridge object pywebview injects. It appears after the "pywebviewready"
 * event, so callers must handle null; outside the window the mock is returned
 * immediately (handy for developing the UI in a browser).
 */
export function useBridgeApi(): BridgeApi | null {
  const [bridge, setBridge] = useState<BridgeApi | null>(() =>
    isEmbedded ? window.pywebview?.api ?? null : mockApi)
  useEffect(() => {
    if (!isEmbedded || bridge) return
    const ready = () => setBridge(window.pywebview?.api ?? null)
    window.addEventListener('pywebviewready', ready)
    return () => window.removeEventListener('pywebviewready', ready)
  }, [bridge])
  return bridge
}

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}
