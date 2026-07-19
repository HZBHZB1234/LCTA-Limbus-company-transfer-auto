import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { initApi, getApi } from './utils/api'
import { useConfigStore } from './stores/config'
import { setupGlobalErrorHandling, flushPreApiErrors } from './utils/errorHandler'
import { installTooltipDirective } from './utils/tooltips'

import '@fortawesome/fontawesome-free/css/all.min.css'
import '@/assets/main.css'

async function bootstrap() {
  setupGlobalErrorHandling()

  const connectionMask = document.getElementById('connection-mask')
  try {
    await initApi()
    ;(window as unknown as Record<string, unknown>).apiReady = true
    await flushPreApiErrors()
  } finally {
    if (connectionMask) {
      connectionMask.style.opacity = '0'
      setTimeout(() => connectionMask.remove(), 300)
    }
  }

  const app = createApp(App)
  const pinia = createPinia()
  app.use(pinia)
  app.use(router)
  installTooltipDirective(app)

  // Register global goAndShow for backward compatibility with backend-generated HTML
  ;(window as unknown as Record<string, unknown>).goAndShow = (page: string) => {
    const routeMap: Record<string, string> = {
      elder: '/elder',
      settings: '/settings',
      dashboard: '/',
      translate: '/translate',
      download: '/download',
      install: '/install',
      manage: '/manage',
      launcher: '/launcher',
      config: '/config',
    }
    const path = routeMap[page] || `/${page}`
    router.push(path)
  }

  const configStore = useConfigStore()
  await configStore.init()

  // Backend initialization (ported from old init.js pywebviewready handler)
  const api = getApi()
  Promise.allSettled([
    api.init_github().catch(() => {}),
    api.init_cache().catch(() => {}),
    api.init_log().catch(() => {}),
  ])

  // Check for version update notification
  api.check_show().then((result) => {
    if (result && result.show) {
      // Navigate to welcome page with update notes
      router.push('/welcome')
    }
  }).catch(() => {})

  // Auto-detect game path if not set
  try {
    const gamePath = configStore.get<string>('game_path')
    if (!gamePath) {
      api.run_func('find_lcb').catch(() => {})
    }
  } catch { /* ignore */ }

  app.mount('#app')

  // Save settings when window is closing (pywebview window close event)
  window.addEventListener('beforeunload', () => {
    try {
      getApi().save_setting_from()
    } catch { /* ignore - may fail during shutdown */ }
  })
}

bootstrap()
