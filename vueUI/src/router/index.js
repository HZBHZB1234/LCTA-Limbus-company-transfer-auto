import { createRouter, createWebHistory } from 'vue-router'
import { useConfigStore } from '@/stores/config'

const routes = [
  { path: '/', redirect: '/translate' },
  { path: '/translate', name: 'Translate', component: () => import('@/views/TranslateView.vue') },
  { path: '/install', name: 'Install', component: () => import('@/views/InstallView.vue') },
  { path: '/download', name: 'Download', component: () => import('@/views/DownloadView.vue') },
  { path: '/clean', name: 'Clean', component: () => import('@/views/CleanView.vue') },
  { path: '/fancy', name: 'Fancy', component: () => import('@/views/FancyView.vue') },
  { path: '/manage', name: 'Manage', component: () => import('@/views/ManageView.vue') },
  { path: '/config-api', name: 'ConfigApi', component: () => import('@/views/ConfigApiView.vue') },
  { path: '/proper', name: 'Proper', component: () => import('@/views/ProperView.vue') },
  { path: '/log', name: 'Log', component: () => import('@/views/LogView.vue') },
  { path: '/about', name: 'About', component: () => import('@/views/AboutView.vue') },
  { path: '/settings', name: 'Settings', component: () => import('@/views/SettingsView.vue') },
  { path: '/launcher', name: 'LauncherConfig', component: () => import('@/views/LauncherConfigView.vue') },
  { path: '/test', name: 'Test', component: () => import('@/views/TestView.vue'), meta: { devOnly: true } },
  { path: '/welcome', name: 'Welcome', component: () => import('@/views/WelcomeView.vue') },
  { path: '/elder', name: 'Elder', component: () => import('@/views/ElderView.vue') }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫：测试页面仅在开发模式或调试模式下可用
router.beforeEach((to, from, next) => {
  if (to.meta.devOnly) {
    const configStore = useConfigStore()
    const isDebug = configStore.get('debug')
    if (!isDebug && import.meta.env.PROD) {
      next('/settings')
      return
    }
  }
  next()
})

export default router