<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useModalStore } from '@/stores/modal'
import ThemeToggle from './ThemeToggle.vue'

const router = useRouter()
const modalStore = useModalStore()

const sidebarCollapsed = ref(false)

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
      <button class="sidebar-toggle" @click="sidebarCollapsed = !sidebarCollapsed" title="折叠侧边栏">
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
  width: 220px;
  height: 100vh;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow-y: auto;
}
.sidebar.collapsed { width: 52px; }
.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid var(--border-color);
}
.sidebar-toggle {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 16px;
  padding: 4px;
}
.logo {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.logo i { font-size: 18px; color: var(--accent-color); }
.logo h2 { font-size: 18px; margin: 0; color: var(--text-primary); }
.version { font-size: 11px; color: var(--text-secondary); background: var(--bg-primary); padding: 2px 6px; border-radius: 4px; }
.subtitle { font-size: 12px; color: var(--text-secondary); margin: 4px 0 0; }
.sidebar-menu { flex: 1; overflow-y: auto; padding: 8px 0; }
.nav-group { padding: 0 8px 8px; }
.nav-group-title {
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: uppercase;
  padding: 8px 8px 4px;
  letter-spacing: 0.5px;
}
.nav-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  font-size: 14px;
  text-align: left;
  margin-bottom: 2px;
}
.nav-btn:hover { background: var(--bg-primary); }
.nav-btn.active {
  background: var(--accent-color);
  color: white;
}
.nav-btn i { width: 20px; text-align: center; }
.sidebar-theme { padding: 8px; border-top: 1px solid var(--border-color); }
.minimized-modals { padding: 8px; border-top: 1px solid var(--border-color); }
.minimized-title { font-size: 11px; color: var(--text-secondary); padding: 0 8px 4px; }
.minimized-btn {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: none;
  border-radius: 6px;
  background: var(--bg-primary);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 12px;
  margin-bottom: 4px;
  overflow: hidden;
}
.minimized-btn span:first-of-type { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.minimized-pct { font-weight: 600; color: var(--accent-color); flex-shrink: 0; }
.sidebar-footer {
  padding: 12px 16px;
  border-top: 1px solid var(--border-color);
}
.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}
.status-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #27ae60;
}
</style>
