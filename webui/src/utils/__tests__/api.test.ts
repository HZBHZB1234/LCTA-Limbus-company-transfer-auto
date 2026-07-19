import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockApi = {
  get_startup_data: vi.fn(),
  get_config_value: vi.fn(),
  update_config_batch: vi.fn(),
  save_config_to_file: vi.fn(),
  add_modal_id: vi.fn(),
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('pywebview', { api: mockApi })
})

describe('initApi', () => {
  it('returns api when pywebviewready already fired', async () => {
    const { initApi, getApi } = await import('../api')
    window.apiReady = false
    const api = await initApi()
    expect(api).toBeDefined()
    expect(getApi()).toBe(api)
  })

  it('throws if getApi called before initApi', async () => {
    vi.resetModules()
    const { getApi } = await import('../api')
    expect(() => getApi()).toThrow('not initialized')
  })
})
