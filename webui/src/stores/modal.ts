import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getApi } from '@/utils/api'
import { listenEvent } from '@/utils/events'

export type ModalType = 'progress' | 'confirm' | 'message'
export type ModalStatus = 'running' | 'paused' | 'canceled' | 'completed'

export interface LogEntry {
  timestamp: string
  message: string
}

export interface ActionButton {
  text: string
  danger?: boolean
  onClick: () => void
}

export interface ModalState {
  id: string
  type: ModalType
  title: string
  status: ModalStatus
  percent: number
  progressText: string
  logs: LogEntry[]
  minimized: boolean
  confirmText?: string
  cancelText?: string
  onConfirm?: () => void
  onCancel?: () => void
  bodyHtml?: string
  actionButtons?: ActionButton[]
}

export interface ModalOptions {
  title: string
  confirmText?: string
  cancelText?: string
  onConfirm?: () => void
  onCancel?: () => void
  bodyHtml?: string
  actionButtons?: ActionButton[]
}

function formatTime(): string {
  const now = new Date()
  const h = String(now.getHours()).padStart(2, '0')
  const m = String(now.getMinutes()).padStart(2, '0')
  const s = String(now.getSeconds()).padStart(2, '0')
  return `${h}:${m}:${s}`
}

let listenerCleanups: Array<() => void> = []

export const useModalStore = defineStore('modal', () => {
  const modals = ref<ModalState[]>([])

  const activeModals = computed(() => modals.value.filter((m) => !m.minimized))
  const minimizedModals = computed(() => modals.value.filter((m) => m.minimized))

  function create(type: ModalType, options: ModalOptions): string {
    const id = `modal-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const state: ModalState = {
      id,
      type,
      title: options.title,
      status: 'running',
      percent: 0,
      progressText: '',
      logs: [],
      minimized: false,
      confirmText: options.confirmText,
      cancelText: options.cancelText,
      onConfirm: options.onConfirm,
      onCancel: options.onCancel,
      bodyHtml: options.bodyHtml,
      actionButtons: options.actionButtons,
    }
    modals.value.push(state)
    getApi().add_modal_id(id)
    return id
  }

  function remove(id: string): void {
    const idx = modals.value.findIndex((m) => m.id === id)
    if (idx !== -1) {
      modals.value.splice(idx, 1)
    }
  }

  function find(id: string): ModalState | undefined {
    return modals.value.find((m) => m.id === id)
  }

  function updateProgress(id: string, percent: number, text: string): void {
    const modal = find(id)
    if (modal) {
      modal.percent = percent
      modal.progressText = text
    }
  }

  function addLog(id: string, message: string): void {
    const modal = find(id)
    if (modal) {
      modal.logs.push({ timestamp: formatTime(), message })
    }
  }

  function setStatus(id: string, status: ModalStatus): void {
    const modal = find(id)
    if (modal) {
      modal.status = status
    }
  }

  function minimize(id: string): void {
    const modal = find(id)
    if (modal) { modal.minimized = true }
  }

  function restore(id: string): void {
    const modal = find(id)
    if (modal) { modal.minimized = false }
  }

  function setupEventListeners(): void {
    listenerCleanups.push(
      listenEvent('lcta:modal-log', (detail) => {
        addLog(detail.modalId, detail.message)
      })
    )
    listenerCleanups.push(
      listenEvent('lcta:modal-progress', (detail) => {
        updateProgress(detail.modalId, detail.percent, detail.text)
      })
    )
    listenerCleanups.push(
      listenEvent('lcta:modal-status', (detail) => {
        setStatus(detail.modalId, detail.status as ModalStatus)
      })
    )
  }

  function cleanupEventListeners(): void {
    listenerCleanups.forEach((fn) => fn())
    listenerCleanups = []
  }

  return {
    modals, activeModals, minimizedModals,
    create, remove, updateProgress, addLog, setStatus, minimize, restore,
    setupEventListeners, cleanupEventListeners,
  }
})
