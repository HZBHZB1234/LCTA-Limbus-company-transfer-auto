<script setup lang="ts">
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()
const themes = [
  { name: 'light' as const, icon: 'fa-sun', title: '亮色主题' },
  { name: 'dark' as const, icon: 'fa-moon', title: '暗色主题' },
  { name: 'purple' as const, icon: 'fa-palette', title: '蓝紫色主题' },
]
</script>

<template>
  <div class="theme-toggle">
    <button
      v-for="t in themes"
      :key="t.name"
      :class="['theme-btn', { active: themeStore.current === t.name }]"
      :title="t.title"
      @click="themeStore.switchTheme(t.name)"
    >
      <i :class="['fas', t.icon]"></i>
    </button>
  </div>
</template>

<style scoped>
.theme-toggle {
  display: flex;
  gap: 4px;
  padding: 8px;
}
.theme-btn {
  width: 32px;
  height: 32px;
  border: 2px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}
.theme-btn.active {
  border-color: var(--accent-color);
  color: var(--accent-color);
}
</style>
