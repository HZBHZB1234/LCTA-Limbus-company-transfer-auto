import { defineStore } from 'pinia'
import { callBridge } from '../shared/bridge'
import type { ActionPlan, ProductTask, WorkspaceSnapshot } from '../shared/types'

interface BootstrapPayload {
  workspace: WorkspaceSnapshot
  tasks: ProductTask[]
  start_context: { target: string; payload: string }
}

export const useProductStore = defineStore('product', {
  state: () => ({
    workspace: null as WorkspaceSnapshot | null,
    tasks: [] as ProductTask[],
    plan: null as ActionPlan | null,
    loading: true,
    busy: false,
    error: '',
    startTarget: 'home',
  }),
  getters: {
    recommendedAction(state) {
      return state.workspace?.recommended_actions.find((action) => action.recommended)
        ?? state.workspace?.recommended_actions.find((action) => action.availability === 'available')
        ?? null
    },
    runningTasks(state) {
      return state.tasks.filter((task) => ['queued', 'running', 'waiting', 'cancelling'].includes(task.state))
    },
  },
  actions: {
    async bootstrap() {
      this.loading = true
      this.error = ''
      try {
        const payload = await callBridge<BootstrapPayload>('get_product_bootstrap')
        this.workspace = payload.workspace
        this.tasks = payload.tasks
        this.startTarget = payload.start_context.target || 'home'
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error)
      } finally {
        this.loading = false
      }
    },
    async refresh() {
      try {
        const [workspace, tasks] = await Promise.all([
          callBridge<WorkspaceSnapshot>('get_workspace_snapshot'),
          callBridge<ProductTask[]>('list_tasks', { limit: 30 }),
        ])
        this.workspace = workspace
        this.tasks = tasks
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error)
      }
    },
    async prepareInstall() {
      this.busy = true
      this.error = ''
      try {
        this.plan = await callBridge<ActionPlan>('build_action_plan', 'install-recommended-localization', {})
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error)
      } finally {
        this.busy = false
      }
    },
    async executePlan() {
      if (!this.plan) return
      this.busy = true
      try {
        await callBridge<ProductTask>('execute_action_plan', this.plan.id)
        this.plan = null
        await this.refresh()
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error)
      } finally {
        this.busy = false
      }
    },
    async cancelTask(taskId: string) {
      await callBridge('cancel_task', taskId)
      await this.refresh()
    },
    async openLauncher() {
      await callBridge('open_launcher_window')
    },
    async setTheme(theme: 'light' | 'dark') {
      document.documentElement.dataset.theme = theme
      if (this.workspace) this.workspace.theme = theme
      await callBridge('set_product_theme', theme)
    },
  },
})
