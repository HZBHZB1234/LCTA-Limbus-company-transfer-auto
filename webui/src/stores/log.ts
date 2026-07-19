import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listenEvent } from '@/utils/events'

export type LogLevel = 'info' | 'warn' | 'error'

export interface LogEntry {
  timestamp: string
  message: string
  level: LogLevel
}

const MAX_LOGS = 500

function formatTime(): string {
  const now = new Date()
  const h = String(now.getHours()).padStart(2, '0')
  const m = String(now.getMinutes()).padStart(2, '0')
  const s = String(now.getSeconds()).padStart(2, '0')
  return `${h}:${m}:${s}`
}

export const useLogStore = defineStore('log', () => {
  const messages = ref<LogEntry[]>([])

  function add(message: string, level: LogLevel = 'info'): void {
    messages.value.push({
      timestamp: formatTime(),
      message,
      level,
    })
    if (messages.value.length > MAX_LOGS) {
      messages.value = messages.value.slice(-MAX_LOGS)
    }
  }

  function clear(): void {
    messages.value = []
  }

  function setupEventListeners(): void {
    listenEvent('lcta:log', (detail) => {
      add(detail.message, detail.level)
    })
  }

  return { messages, add, clear, setupEventListeners }
})
