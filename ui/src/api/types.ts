export interface PeriodSpec {
  week?: 'this' | 'last' | 'prev'
  month?: number
  year?: number
  since?: string
  until?: string
}

export interface PeriodInfo {
  kind: 'weekly' | 'monthly' | 'custom'
  start: string
  end: string
  label: string
}

export interface CommitDTO {
  date: string
  hash: string
  subject: string
}

export interface RepoDTO {
  name: string
  path: string
  commit_count: number
  commits: CommitDTO[]
}

export interface SessionDTO {
  id: string
  source: string
  source_label: string
  title: string | null
  project: string
  cwd: string | null
  branches: string[]
  message_count: number
  first_date: string | null
  last_date: string | null
  date_approx: boolean
  prompts: string[]
}

export interface ActivityDTO {
  period: PeriodInfo
  cancelled: boolean
  commit_count: number
  repos_scanned: number
  include_prompts: boolean
  missing_sources: string[]
  repos: RepoDTO[]
  sessions: SessionDTO[]
}

export type KeyStatus = 'ok' | 'missing' | 'config' | 'none'

export interface ProviderDTO {
  name: string
  type: string
  model: string
  key_env: string
  key_status: KeyStatus
  is_default: boolean
}

export interface SmtpConfig {
  host: string
  port: number
  security: string
  username: string
  password_env: string
  from: string
}

export interface AppConfig {
  provider: string
  language: string
  author_name: string
  output_dir: string
  default_week: string
  template: string
  extra_instructions: string
  max_context_chars: number
  git: {
    enabled: boolean
    roots: string[]
    authors: string[]
    max_depth: number
    exclude: string[]
  }
  agents: {
    enabled: boolean
    sources: string[]
    include_prompts: boolean
    max_prompt_len: number
    max_prompts_per_session: number
    exclude: string[]
    roots: Record<string, string>
  }
  providers: Record<string, Record<string, unknown>>
  email: {
    method: string
    to: string[]
    cc: string[]
    subject: string
    smtp: SmtpConfig
  }
}

export interface ConfigState {
  config: AppConfig
  config_path: string | null
  exists: boolean
  version: string
}

export interface GenerateOptions {
  provider?: string
  model?: string
  language?: string
  topic?: string
  previous?: 'auto' | 'none' | string
  template?: string | null
}

export interface GenerateResult {
  report: string
  title: string
  provider: string
  model: string
  filename: string
}

export interface ProgressEvent {
  source: 'git' | 'agents'
  phase: string
  current?: string
  scanned?: number
  total?: number
}

export interface SendOptions {
  to?: string[]
  cc?: string[]
  subject?: string
  method?: string
}

export interface EffectiveRecipients {
  to: string[]
  cc: string[]
  method: string
  error: string | null
}
