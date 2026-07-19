import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('@/views/Dashboard.vue') },
  { path: '/translate', name: 'translate', component: () => import('@/views/Translate.vue') },
  { path: '/download', name: 'download', component: () => import('@/views/Download.vue') },
  { path: '/install', name: 'install', component: () => import('@/views/Install.vue') },
  { path: '/fancy', name: 'fancy', component: () => import('@/views/Fancy.vue') },
  { path: '/cdn', name: 'cdn', component: () => import('@/views/Cdn.vue') },
  { path: '/speed', name: 'speed', component: () => import('@/views/Speed.vue') },
  { path: '/manage', name: 'manage', component: () => import('@/views/Manage.vue') },
  { path: '/launcher', name: 'launcher-config', component: () => import('@/views/LauncherConfig.vue') },
  { path: '/config', name: 'api-config', component: () => import('@/views/ApiConfig.vue') },
  { path: '/proper', name: 'proper', component: () => import('@/views/Proper.vue') },
  { path: '/log', name: 'log', component: () => import('@/views/Log.vue') },
  { path: '/settings', name: 'settings', component: () => import('@/views/Settings.vue') },
  { path: '/about', name: 'about', component: () => import('@/views/About.vue') },
  { path: '/welcome', name: 'welcome', component: () => import('@/views/Welcome.vue') },
  { path: '/elder', name: 'elder', component: () => import('@/views/Elder.vue') },
  { path: '/test', name: 'test', component: () => import('@/views/Test.vue') },
  { path: '/clean', name: 'clean', component: () => import('@/views/Clean.vue') },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
