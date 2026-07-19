<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useModalStore } from '@/stores/modal'
import ThemeToggle from './ThemeToggle.vue'

const router = useRouter()
const modalStore = useModalStore()

const SIDEBAR_STORAGE_KEY = 'lcta-sidebar-collapsed'

function getStoredCollapsed(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true'
  } catch { return false }
}

const sidebarCollapsed = ref(getStoredCollapsed())

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  try {
    localStorage.setItem(SIDEBAR_STORAGE_KEY, String(sidebarCollapsed.value))
  } catch { /* ignore */ }
}

const navGroups = [
  {
    title: '常用工具',
    icon: 'fa-star',
    items: [
      { id: 'dashboard', icon: 'fa-tachometer-alt', label: '首页', route: '/' },
      { id: 'translate', icon: 'fa-language', label: '翻译工具', route: '/translate' },
      { id: 'download', icon: 'fa-cloud-download-alt', label: '汉化包下载', route: '/download' },
      { id: 'install', icon: 'fa-download', label: '安装已有汉化', route: '/install' },
      { id: 'fancy', icon: 'fa-paint-brush', label: '文本美化', route: '/fancy' },
      { id: 'cdn', icon: 'fa-bolt', label: 'CDN优选', route: '/cdn' },
      { id: 'speed', icon: 'fa-forward', label: '游戏加速', route: '/speed' },
    ],
  },
  {
    title: '管理配置',
    icon: 'fa-sliders-h',
    items: [
      { id: 'manage', icon: 'fa-archive', label: '已安装数据管理', route: '/manage' },
      { id: 'launcher-config', icon: 'fa-rocket', label: 'Launcher配置', route: '/launcher' },
      { id: 'config', icon: 'fa-cog', label: '配置汉化API', route: '/config' },
      { id: 'proper', icon: 'fa-book', label: '抓取专有词汇', route: '/proper' },
    ],
  },
  {
    title: '系统',
    icon: 'fa-server',
    items: [
      { id: 'log', icon: 'fa-clipboard-list', label: '日志', route: '/log' },
      { id: 'settings', icon: 'fa-wrench', label: '设置', route: '/settings' },
      { id: 'about', icon: 'fa-info-circle', label: '关于', route: '/about' },
    ],
  },
]

function navigate(routePath: string) {
  router.push(routePath)
}

function isActive(navId: string): boolean {
  const routeMap: Record<string, string> = {
    'dashboard': '/',
    'translate': '/translate',
    'download': '/download',
    'install': '/install',
    'fancy': '/fancy',
    'cdn': '/cdn',
    'speed': '/speed',
    'manage': '/manage',
    'launcher-config': '/launcher',
    'config': '/config',
    'proper': '/proper',
    'log': '/log',
    'settings': '/settings',
    'about': '/about',
    'welcome': '/welcome',
    'elder': '/elder',
    'clean': '/clean',
    'test': '/test',
  }
  return router.currentRoute.value.path === routeMap[navId]
}
</script>

<template>
  <div class="sidebar" :class="{ collapsed: sidebarCollapsed }">
    <div class="sidebar-header">
      <button class="sidebar-toggle" @click="toggleSidebar" title="折叠侧边栏">
        <i class="fas fa-bars"></i>
      </button>
      <div v-if="!sidebarCollapsed" class="logo">
        <i class="fas fa-language"></i>
        <h2>LCTA <span class="version">v5.0.0</span></h2>
      </div>
      <p v-if="!sidebarCollapsed" class="subtitle">边狱公司汉化工具箱</p>
    </div>

    <div v-if="!sidebarCollapsed" class="sidebar-menu">
      <div v-for="group in navGroups" :key="group.title" class="nav-group">
        <div class="nav-group-title">
          <i :class="['fas', group.icon]"></i> {{ group.title }}
        </div>
        <button
          v-for="item in group.items"
          :key="item.id"
          class="nav-btn"
          :class="{ active: isActive(item.id) }"
          @click="navigate(item.route)"
        >
          <i :class="['fas', item.icon]"></i>
          <span>{{ item.label }}</span>
          <div class="nav-indicator"></div>
        </button>
      </div>
    </div>

    <div v-if="!sidebarCollapsed" class="sidebar-theme">
      <ThemeToggle />
    </div>

    <div v-if="!sidebarCollapsed && modalStore.minimizedModals.length > 0" class="minimized-modals">
      <div class="minimized-title">最小化的任务</div>
      <button
        v-for="m in modalStore.minimizedModals"
        :key="m.id"
        class="minimized-btn"
        @click="modalStore.restore(m.id)"
      >
        <i class="fas fa-spinner fa-pulse"></i>
        <span>{{ m.title }}</span>
        <span class="minimized-pct">{{ Math.round(m.percent) }}%</span>
      </button>
    </div>

    <div v-if="!sidebarCollapsed" class="sidebar-footer">
      <div class="status-indicator">
        <div class="status-dot connected"></div>
        <span>已连接</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sidebar {
  width: 272px;
  height: 100vh;
  background: var(--color-bg-sidebar);
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
  z-index: 100;
  transition: width var(--transition-speed) var(--transition-easing);
  flex-shrink: 0;
}
.sidebar.collapsed { width: 60px; }

.sidebar-header {
  padding: var(--spacing-xl) var(--spacing-lg);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  position: relative;
}

.sidebar-toggle {
  position: absolute;
  top: 16px;
  right: 12px;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  border: none;
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.6);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: all var(--transition-speed) var(--transition-easing);
}
.sidebar-toggle:hover {
  background: rgba(255, 255, 255, 0.2);
  color: white;
}

.logo {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: white;
  margin-bottom: var(--spacing-sm);
}
.logo i { font-size: 24px; color: var(--color-primary); }
.logo h2 { font-size: 20px; font-weight: 600; }
.version {
  font-size: 12px;
  opacity: 0.7;
  margin-left: 4px;
}
.subtitle {
  color: rgba(255, 255, 255, 0.7);
  font-size: 14px;
  margin: 0;
}

.sidebar-menu {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-sm) 0;
}

.nav-group {
  margin-bottom: var(--spacing-xs);
}
.nav-group + .nav-group {
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  padding-top: var(--spacing-xs);
}

.nav-group-title {
  padding: var(--spacing-sm) var(--spacing-lg);
  color: rgba(255, 255, 255, 0.4);
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.nav-group-title i {
  font-size: 10px;
  width: 14px;
  text-align: center;
}

.nav-btn {
  width: 100%;
  padding: var(--spacing-md) var(--spacing-lg);
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.8);
  text-align: left;
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  cursor: pointer;
  position: relative;
  transition: all var(--transition-speed) var(--transition-easing);
  font-size: 14px;
}
.nav-btn:hover {
  background: var(--color-bg-sidebar-hover);
  color: white;
  padding-left: calc(var(--spacing-lg) + 8px);
}
.nav-btn.active {
  background: var(--color-bg-sidebar-active);
  color: white;
}
.nav-btn.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: white;
}
.nav-btn i { width: 20px; text-align: center; font-size: 16px; }

.nav-indicator {
  visibility: hidden;
  margin-left: 4px;
  width: 8px;
  height: 8px;
  background: var(--color-success);
  border-radius: 50%;
  animation: pulse 2s infinite;
  flex-shrink: 0;
}
.nav-btn.active .nav-indicator { visibility: visible; }

.sidebar-theme {
  padding: var(--spacing-sm);
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.minimized-modals {
  padding: var(--spacing-sm);
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}
.minimized-title {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.4);
  padding: 0 var(--spacing-sm) var(--spacing-xs);
}
.minimized-btn {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: 6px 8px;
  border: none;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.8);
  cursor: pointer;
  font-size: 12px;
  margin-bottom: 4px;
  overflow: hidden;
}
.minimized-btn:hover { background: var(--color-bg-sidebar-hover); }
.minimized-btn span:first-of-type { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.minimized-pct { font-weight: 600; color: var(--color-primary); flex-shrink: 0; }

.sidebar-footer {
  padding: var(--spacing-md);
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
}
.status-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--color-success);
}
.status-dot.connected {
  background: var(--color-success);
  box-shadow: 0 0 10px rgba(46, 204, 113, 0.5);
}
.status-dot.connecting {
  background: var(--color-warning);
  box-shadow: 0 0 10px rgba(243, 156, 18, 0.5);
}

/* 折叠状态 */
.sidebar.collapsed .sidebar-header {
  padding: var(--spacing-md) var(--spacing-sm);
  text-align: center;
}
.sidebar.collapsed .logo {
  justify-content: center;
  margin-bottom: 0;
}
.sidebar.collapsed .logo h2,
.sidebar.collapsed .subtitle,
.sidebar.collapsed .version,
.sidebar.collapsed .nav-group-title,
.sidebar.collapsed .nav-btn span,
.sidebar.collapsed .nav-indicator,
.sidebar.collapsed .sidebar-search,
.sidebar.collapsed .sidebar-footer .status-indicator span {
  display: none;
}
.sidebar.collapsed .sidebar-toggle {
  position: static;
  margin: 0 auto 4px auto;
  display: flex;
}
.sidebar.collapsed .nav-btn {
  justify-content: center;
  padding: var(--spacing-md) var(--spacing-sm);
}
.sidebar.collapsed .nav-btn i {
  margin: 0;
  font-size: 16px;
  width: 34px;
  height: 34px;
  line-height: 34px;
  text-align: center;
  border-radius: 50%;
  transition: all var(--transition-speed) var(--transition-easing);
  flex-shrink: 0;
}
.sidebar.collapsed .nav-btn:hover i {
  background: var(--color-primary);
  color: white;
}
.sidebar.collapsed .sidebar-footer {
  text-align: center;
  padding: var(--spacing-sm);
}
.sidebar.collapsed .status-dot { margin: 0 auto; }
</style>
