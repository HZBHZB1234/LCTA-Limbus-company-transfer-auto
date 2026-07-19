import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getApi } from '@/utils/api'
import type { StartupData } from '@/types/config'

function deepGet(obj: Record<string, unknown>, path: string): unknown {
  const keys = path.split('.')
  let current: unknown = obj
  for (const key of keys) {
    if (current == null || typeof current !== 'object') return undefined
    current = (current as Record<string, unknown>)[key]
  }
  return current
}

function deepSet(obj: Record<string, unknown>, path: string, value: unknown): void {
  const keys = path.split('.')
  let current = obj
  for (let i = 0; i < keys.length - 1; i++) {
    if (!(keys[i] in current) || typeof current[keys[i]] !== 'object' || current[keys[i]] === null) {
      current[keys[i]] = {}
    }
    current = current[keys[i]] as Record<string, unknown>
  }
  current[keys[keys.length - 1]] = value
}

function flattenUpdates(
  obj: Record<string, unknown>,
  prefix: string,
  result: Record<string, unknown>
): void {
  for (const [key, value] of Object.entries(obj)) {
    const fullPath = prefix ? `${prefix}.${key}` : key
    if (value != null && typeof value === 'object' && !Array.isArray(value)) {
      flattenUpdates(value as Record<string, unknown>, fullPath, result)
    } else {
      result[fullPath] = value
    }
  }
}

export const useConfigStore = defineStore('config', () => {
  const raw = ref<Record<string, unknown>>({})
  const dirty = ref(false)
  const initialized = ref(false)
  const firstUse = ref(false)
  const configOk = ref(true)
  const configError = ref<string[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function init(startupData?: StartupData): Promise<void> {
    loading.value = true
    error.value = null
    try {
      let data = startupData
      if (!data) {
        data = await getApi().get_startup_data()
      }
      raw.value = data.config as Record<string, unknown>
      firstUse.value = data.first_use
      configOk.value = data.config_ok
      configError.value = data.config_error
      initialized.value = true
    } catch (e) {
      const msg = `配置初始化失败: ${e}`
      console.error(msg)
      error.value = msg
      try { getApi().log(msg).catch(() => {}) } catch { /* ignore */ }
      throw e
    } finally {
      loading.value = false
    }
  }

  function get<T = unknown>(path: string): T {
    return deepGet(raw.value, path) as T
  }

  function set(path: string, value: unknown): void {
    deepSet(raw.value, path, value)
    dirty.value = true
  }

  async function save(): Promise<void> {
    error.value = null
    try {
      const updates: Record<string, unknown> = {}
      flattenUpdates(raw.value, '', updates)
      await getApi().update_config_batch(updates)
      await getApi().save_config_to_file()
      dirty.value = false
    } catch (e) {
      const msg = `配置保存失败: ${e}`
      console.error(msg)
      error.value = msg
      try { getApi().log(msg).catch(() => {}) } catch { /* ignore */ }
      throw e
    }
  }

  async function reload(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const data = await getApi().get_startup_data()
      raw.value = data.config as Record<string, unknown>
      dirty.value = false
    } catch (e) {
      const msg = `配置重载失败: ${e}`
      console.error(msg)
      error.value = msg
      try { getApi().log(msg).catch(() => {}) } catch { /* ignore */ }
      throw e
    } finally {
      loading.value = false
    }
  }

  return { raw, dirty, initialized, firstUse, configOk, configError, loading, error, init, get, set, save, reload }
})
