import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'

// 导入全局样式
import './assets/styles/variables.css'
import './assets/styles/global.css'
import './assets/styles/markdown.css'

// 工具函数
import { api } from './utils/api'
import { addLogMessage } from './utils/logger'
import { useConfigStore } from './stores/config'
import { useThemeStore } from './stores/theme'
import { useLogStore } from './stores/log'

// 等待 pywebview 就绪
function waitForPywebview() {
  return new Promise((resolve) => {
    if (window.pywebview && window.pywebview.api) {
      resolve()
    } else {
      window.addEventListener('pywebviewready', () => resolve(), { once: true })
    }
  })
}

// 全局错误处理（在 Vue 挂载前捕获早期错误）
window.addEventListener('error', (event) => {
  console.error('全局错误:', event.error)
  // 如果已初始化日志 store，则记录
  if (window.__logStore) {
    window.__logStore.addLog(`[前端错误] ${event.message}`, 'error')
  }
})

window.addEventListener('unhandledrejection', (event) => {
  console.error('未处理的 Promise 拒绝:', event.reason)
  if (window.__logStore) {
    window.__logStore.addLog(`[Promise错误] ${event.reason}`, 'error')
  }
})

async function initApp() {
  try {
    // 等待后端 API 就绪
    await waitForPywebview()
    console.log('pywebview API 已就绪')
    
    // 创建 Vue 应用
    const app = createApp(App)
    const pinia = createPinia()
    app.use(pinia)
    app.use(router)
    
    // 初始化各个 store
    const configStore = useConfigStore()
    const themeStore = useThemeStore()
    const logStore = useLogStore()
    
    // 将 logStore 挂载到全局，供早期错误上报
    window.__logStore = logStore
    
    // 加载配置（从后端拉取）
    await configStore.loadConfig()
    
    // 初始化主题
    themeStore.initTheme()
    
    // 添加启动日志
    logStore.addLog('系统已启动，准备就绪')
    logStore.addLog(`当前主题: ${themeStore.currentTheme}`)
    logStore.addLog('WebUI 初始化完成')
    
    // 挂载应用
    app.mount('#app')
    
    // 移除加载遮罩
    const loadingEl = document.getElementById('app-loading')
    if (loadingEl) {
      loadingEl.style.opacity = '0'
      setTimeout(() => loadingEl.remove(), 300)
    }
    
    // 触发后续初始化（不阻塞 UI）
    setTimeout(() => {
      configStore.checkGamePath()
      if (configStore.get('auto_check_update')) {
        configStore.checkUpdate()
      }
      api.call('init_cache').catch(console.error)
      api.call('init_github').catch(console.error)
    }, 100)
    
  } catch (err) {
    console.error('应用初始化失败:', err)
    const loadingEl = document.getElementById('app-loading')
    if (loadingEl) {
      loadingEl.innerHTML = `
        <div style="text-align:center; color:#e74c3c;">
          <i class="fas fa-exclamation-triangle" style="font-size:48px; margin-bottom:16px;"></i>
          <p>加载失败: ${err.message}</p>
          <p>请重启应用或检查后端服务</p>
        </div>
      `
    }
  }
}

initApp()