import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

beforeEach(async () => {
  setActivePinia(createPinia())
  vi.stubGlobal('pywebview', {
    api: {
      add_modal_id: vi.fn().mockResolvedValue(undefined),
      set_modal_running: vi.fn().mockResolvedValue(undefined),
    },
  })
  const { initApi } = await import('../../utils/api')
  await initApi()
})

describe('modalStore', () => {
  it('creates a modal and returns id', async () => {
    const { useModalStore } = await import('../../stores/modal')
    const store = useModalStore()
    const id = store.create('progress', { title: '测试任务' })
    expect(id).toBeTruthy()
    expect(id).toContain('modal-')
    expect(store.modals.length).toBe(1)
    expect(store.modals[0].title).toBe('测试任务')
  })

  it('updates progress', async () => {
    const { useModalStore } = await import('../../stores/modal')
    const store = useModalStore()
    const id = store.create('progress', { title: '下载' })
    store.updateProgress(id, 50, '处理中')
    expect(store.modals[0].percent).toBe(50)
    expect(store.modals[0].progressText).toBe('处理中')
  })

  it('adds log to modal', async () => {
    const { useModalStore } = await import('../../stores/modal')
    const store = useModalStore()
    const id = store.create('progress', { title: '任务' })
    store.addLog(id, '第一步完成')
    store.addLog(id, '第二步完成')
    expect(store.modals[0].logs.length).toBe(2)
    expect(store.modals[0].logs[0].message).toBe('第一步完成')
  })

  it('removes modal', async () => {
    const { useModalStore } = await import('../../stores/modal')
    const store = useModalStore()
    const id = store.create('message', { title: '提示' })
    store.remove(id)
    expect(store.modals.length).toBe(0)
  })

  it('minimizes and restores', async () => {
    const { useModalStore } = await import('../../stores/modal')
    const store = useModalStore()
    const id = store.create('progress', { title: '下载' })
    store.minimize(id)
    expect(store.modals[0].minimized).toBe(true)
    expect(store.minimizedModals.length).toBe(1)
    store.restore(id)
    expect(store.modals[0].minimized).toBe(false)
  })

  it('handles confirm modal callbacks', async () => {
    const { useModalStore } = await import('../../stores/modal')
    const store = useModalStore()
    const onConfirm = vi.fn()
    const onCancel = vi.fn()
    store.create('confirm', { title: '确认删除?', onConfirm, onCancel })
    expect(store.modals.length).toBe(1)
    expect(store.modals[0].type).toBe('confirm')
    expect(store.modals[0].onConfirm).toBe(onConfirm)
  })
})
