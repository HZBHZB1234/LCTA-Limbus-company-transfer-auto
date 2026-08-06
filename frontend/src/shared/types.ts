export type Health = 'healthy' | 'attention' | 'blocked'
export type TaskState = 'queued' | 'running' | 'waiting' | 'cancelling' | 'succeeded' | 'failed' | 'cancelled'

export interface ProductAction {
  id: string
  title: string
  summary: string
  intent: string
  availability: string
  blockers: string[]
  recommended: boolean
}

export interface LauncherPhase {
  id: string
  title: string
  state: 'pending' | 'running' | 'completed' | 'failed' | 'skipped'
  progress: number | null
  message: string
}

export interface LauncherSession {
  schema_version: number
  revision: number
  id: string
  state: string
  current_phase: string | null
  message: string
  progress: number | null
  phases: LauncherPhase[]
  launch_plan: { title: string; steps: string[] }
  game_process: { pid: number | null; running: boolean; exit_code: number | null } | null
  enabled_features: string[]
  started_at: string | null
  finished_at: string | null
  can_cancel: boolean
  can_close_without_stopping_game: boolean
  issues: Array<{ id: string; severity: string; title: string; summary: string }>
  logs: Array<{ time: string; message: string }>
  result: Record<string, unknown> | null
}

export interface WorkspaceSnapshot {
  schema_version: number
  revision: string
  generated_at: string
  health: Health
  headline: string
  game: { path: string; executable: string; ready: boolean }
  localization: {
    installed: boolean
    count: number
    packages: Array<{ id: string; name: string; path: string }>
  }
  issues: Array<{ id: string; severity: string; title: string; summary: string; action_id?: string }>
  recommended_actions: ProductAction[]
  launcher_session: LauncherSession | null
  theme: 'light' | 'dark'
  legacy_ui_available: boolean
}

export interface ProductTask {
  schema_version: number
  id: string
  kind: string
  title: string
  state: TaskState
  stage: string
  progress: number
  message: string
  can_cancel: boolean
  can_retry: boolean
  result: Record<string, unknown> | null
  errors: string[]
  logs: Array<{ time: string; message: string }>
  created_at: string
  updated_at: string
}

export interface ActionPlan {
  schema_version: number
  id: string
  action_id: string
  title: string
  inputs: Record<string, unknown>
  steps: Array<{ id: string; title: string }>
  changes: string[]
  warnings: string[]
  requirements: string[]
  can_execute: boolean
}
