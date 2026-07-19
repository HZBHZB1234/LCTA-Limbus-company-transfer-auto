<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppSidebar from '@/components/AppSidebar.vue'
import ModalContainer from '@/components/ModalContainer.vue'
import HelpDrawer from '@/components/HelpDrawer.vue'
import DragOverlay from '@/components/DragOverlay.vue'
import { useConfigStore } from '@/stores/config'
import { useModalStore } from '@/stores/modal'
import { useLogStore } from '@/stores/log'
import { useThemeStore } from '@/stores/theme'

const router = useRouter()
const configStore = useConfigStore()
const modalStore = useModalStore()
const logStore = useLogStore()
const themeStore = useThemeStore()

onMounted(() => {
  themeStore.init()
  modalStore.setupEventListeners()
  logStore.setupEventListeners()

  if (configStore.firstUse) {
    router.push('/welcome')
  }
})
</script>

<template>
  <div class="app-root">
    <AppSidebar />
    <div class="main-content">
      <router-view />
    </div>
    <ModalContainer />
    <HelpDrawer />
    <DragOverlay />
  </div>
</template>

<style>
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f6f8;
  --text-primary: #1a1a2e;
  --text-secondary: #6b7280;
  --border-color: #e5e7eb;
  --accent-color: #4a90d9;
  --accent-hover: #3a7bc8;
}

.theme-dark {
  --bg-primary: #1a1a2e;
  --bg-secondary: #16213e;
  --text-primary: #e0e0e0;
  --text-secondary: #9ca3af;
  --border-color: #2a2a4e;
  --accent-color: #6ea8fe;
  --accent-hover: #5a94e8;
}

.theme-purple {
  --bg-primary: #2d1b69;
  --bg-secondary: #1a0f3c;
  --text-primary: #e8dff5;
  --text-secondary: #b8a9d4;
  --border-color: #3d2b79;
  --accent-color: #b794f4;
  --accent-hover: #9b6ff0;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  overflow: hidden;
}

.app-root {
  display: flex;
  height: 100vh;
  width: 100vw;
}

.main-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

::-webkit-scrollbar {
  width: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: var(--border-color);
  border-radius: 3px;
}

.markdown-body {
  color: var(--text-primary);
}
.markdown-body h2 { color: var(--text-primary); }
.markdown-body h3 { color: var(--text-primary); }
.markdown-body p { color: var(--text-secondary); }
.markdown-body code { color: var(--accent-color); }
.markdown-body a { color: var(--accent-color); }
</style>
