import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const mockStartupData = {
  message_config: null,
  first_use: false,
  config_ok: true,
  config_error: [],
  config: {
    game_path: 'C:/Games/Limbus',
    debug: false,
    auto_check_update: true,
    ui_default: {
      translator: { translator: 'deepl', enable_proper: true },
      install: { package_directory: 'packages' },
    },
  },
}

beforeEach(async () => {
  setActivePinia(createPinia())
  vi.stubGlobal('pywebview', {
    api: {
      get_startup_data: vi.fn().mockImplementation(() => Promise.resolve(JSON.parse(JSON.stringify(mockStartupData)))),
      update_config_batch: vi.fn().mockResolvedValue({ updated: 1, total: 1 }),
      save_config_to_file: vi.fn().mockResolvedValue(true),
    },
  })
  const { initApi } = await import('../../utils/api')
  await initApi()
})

describe('configStore', () => {
  it('inits with startup data', async () => {
    const { useConfigStore } = await import('../../stores/config')
    const store = useConfigStore()
    await store.init(JSON.parse(JSON.stringify(mockStartupData)))
    expect(store.initialized).toBe(true)
    expect(store.firstUse).toBe(false)
  })

  it('gets nested config values', async () => {
    const { useConfigStore } = await import('../../stores/config')
    const store = useConfigStore()
    await store.init(JSON.parse(JSON.stringify(mockStartupData)))
    expect(store.get('game_path')).toBe('C:/Games/Limbus')
    expect(store.get('debug')).toBe(false)
    expect(store.get('ui_default.translator.enable_proper')).toBe(true)
    expect(store.get('ui_default.install.package_directory')).toBe('packages')
  })

  it('returns undefined for missing paths', async () => {
    const { useConfigStore } = await import('../../stores/config')
    const store = useConfigStore()
    await store.init(JSON.parse(JSON.stringify(mockStartupData)))
    expect(store.get('nonexistent.path')).toBeUndefined()
  })

  it('sets nested config values', async () => {
    const { useConfigStore } = await import('../../stores/config')
    const store = useConfigStore()
    await store.init(JSON.parse(JSON.stringify(mockStartupData)))
    store.set('game_path', 'D:/NewGame')
    expect(store.get('game_path')).toBe('D:/NewGame')
    expect(store.dirty).toBe(true)
  })

  it('saves to api', async () => {
    const { useConfigStore } = await import('../../stores/config')
    const store = useConfigStore()
    await store.init(JSON.parse(JSON.stringify(mockStartupData)))
    store.set('debug', true)
    await store.save()
    expect(store.dirty).toBe(false)
  })

  it('reloads from api', async () => {
    const { useConfigStore } = await import('../../stores/config')
    const store = useConfigStore()
    await store.init(JSON.parse(JSON.stringify(mockStartupData)))
    store.set('debug', true)
    await store.reload()
    expect(store.get('debug')).toBe(false)
    expect(store.dirty).toBe(false)
  })
})
