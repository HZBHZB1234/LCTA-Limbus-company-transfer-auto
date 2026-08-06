import { defineStore } from 'pinia'
import { callBridge } from '../shared/bridge'
import type { LauncherSession } from '../shared/types'

export const useLauncherStore = defineStore('launcher', {
  state: () => ({
    session: null as LauncherSession | null,
    loading: true,
    busy: false,
    error: '',
  }),
  actions: {
    async refresh() {
      try {
        this.session = await callBridge<LauncherSession>('get_launcher_session')
        this.error = ''
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error)
      } finally {
        this.loading = false
      }
    },
    async start() {
      this.busy = true
      try {
        this.session = await callBridge<LauncherSession>('start_launcher_session', {})
      } finally {
        this.busy = false
      }
    },
    async cancel() {
      this.session = await callBridge<LauncherSession>('cancel_launcher_session', this.session?.id)
    },
    async close(mode: 'close' | 'cancel' | 'stop-game') {
      await callBridge('close_launcher_window', mode)
    },
    async openMain(target = 'home') {
      await callBridge('open_main_window', target, { session_id: this.session?.id })
    },
  },
})
