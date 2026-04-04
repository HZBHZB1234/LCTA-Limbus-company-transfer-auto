<template>
  <div class="sidebar">
    <div class="sidebar-header">
      <div class="logo">
        <i class="fas fa-language"></i>
        <h2>LCTA <span class="version">v4.1.5</span></h2>
      </div>
      <p class="subtitle">边狱公司汉化工具箱</p>
    </div>

    <div class="sidebar-menu">
      <router-link 
        v-for="item in navItems" 
        :key="item.path"
        :to="item.path"
        class="nav-btn"
        :class="{ active: $route.path === item.path }"
        v-show="item.visible !== false"
      >
        <i :class="item.icon"></i>
        <span>{{ item.name }}</span>
        <div class="nav-indicator" v-if="item.indicator"></div>
      </router-link>
    </div>

    <div class="sidebar-footer">
      <div class="status-indicator">
        <div class="status-dot connected"></div>
        <span>已连接</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useConfigStore } from '@/stores/config'

const configStore = useConfigStore()
const isDebug = computed(() => configStore.get('debug'))

const navItems = [
  { path: '/translate', name: '翻译工具', icon: 'fas fa-language', visible: true },
  { path: '/install', name: '安装已有汉化', icon: 'fas fa-download', visible: true },
  { path: '/download', name: '汉化包下载', icon: 'fas fa-users', visible: true },
  { path: '/fancy', name: '文本美化', icon: 'fas fa-paint-brush', visible: true },
  { path: '/manage', name: '已安装数据管理', icon: 'fas fa-archive', visible: true },
  { path: '/launcher', name: 'Launcher配置', icon: 'fas fa-rocket', visible: true },
  { path: '/config-api', name: '配置汉化api', icon: 'fas fa-cog', visible: true },
  { path: '/proper', name: '抓取专有词汇', icon: 'fas fa-book', visible: true },
  { path: '/log', name: '日志', icon: 'fas fa-clipboard-list', visible: true },
  { path: '/about', name: '关于', icon: 'fas fa-info-circle', visible: true },
  { path: '/settings', name: '设置', icon: 'fas fa-sliders-h', visible: true },
  { path: '/test', name: '测试界面', icon: 'fas fa-flask', visible: isDebug.value },
  { path: '/welcome', name: '欢迎', icon: 'fas fa-user-circle', visible: false }, // 隐藏，通过其他方式触发
  { path: '/elder', name: '老年人模式', icon: 'fas fa-compass', visible: false }, // 隐藏
  { path: '/clean', name: '清除本地缓存', icon: 'fas fa-broom', visible: false } // 隐藏
]
</script>

<style scoped>
.sidebar {
  width: 260px;
  background: var(--color-bg-sidebar);
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-lg);
  z-index: 100;
}
.sidebar-header {
  padding: var(--spacing-xl) var(--spacing-lg);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}
.logo {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: white;
  margin-bottom: var(--spacing-sm);
}
.logo i {
  font-size: 24px;
  color: var(--color-primary);
}
.logo h2 {
  font-size: 20px;
  font-weight: 600;
}
.version {
  font-size: 12px;
  opacity: 0.7;
  margin-left: 4px;
}
.subtitle {
  color: rgba(255, 255, 255, 0.7);
  font-size: 14px;
}
.sidebar-menu {
  flex: 1;
  padding: var(--spacing-md) 0;
  overflow-y: auto;
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
  text-decoration: none;
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
.nav-btn i {
  width: 20px;
  text-align: center;
  font-size: 16px;
}
.nav-indicator {
  margin-left: auto;
  width: 8px;
  height: 8px;
  background: var(--color-success);
  border-radius: 50%;
}
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
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-success);
}
</style>