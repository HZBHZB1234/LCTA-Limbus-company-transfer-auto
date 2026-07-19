export interface StartupData {
  message_config: string | null
  first_use: boolean
  config_ok: boolean
  config_error: string[]
  config: Record<string, unknown>
}

export interface ApiResult<T = unknown> {
  success: boolean
  message: string
  data?: T
}

export interface TranslationConfig {
  translator: string
  api_settings: Record<string, unknown>
}

export interface PackageInfo {
  name: string
  path: string
  size?: number
  selected?: boolean
  enable?: boolean
}

export interface InstalledPackages {
  packages: PackageInfo[]
  selected: string | null
  enable: boolean
}

export interface ModInfo {
  name: string
  path: string
}

export interface InstalledMods {
  able: ModInfo[]
  disable: ModInfo[]
}

export interface CdnStatus {
  cf_ip: string | null
  cloudfront_mappings: Array<{ domain: string; ip: string }>
  hosts_content: string
}

export interface SpeedStatus {
  process_running: boolean
  dll_injected: boolean
  current_speed: number
}

export interface UpdateInfo {
  has_update: boolean
  latest_version: string | null
  current_version: string
  release_notes: string | null
}

export interface FancyRulesets {
  builtin: Array<{ name: string; config: Record<string, unknown> }>
  user: Array<{ name: string; config: Record<string, unknown> }>
  enabled: string[]
}

export interface FontInfo {
  name: string
  path: string
}

export interface SymlinkStatus {
  unity: string
  project_moon: string
}

export interface FileDropInfo {
  files: Array<{
    path: string
    type: string
    name: string
  }>
  message: string
}
