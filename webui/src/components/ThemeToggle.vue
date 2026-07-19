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
  padding: 4px;
}
.theme-btn {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  border: none;
  background: transparent;
  color: var(--color-text-light);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  transition: all var(--transition-speed) var(--transition-easing);
  position: relative;
  overflow: hidden;
  opacity: 0.7;
}
.theme-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: var(--color-primary);
  transform: translateY(-2px);
  opacity: 1;
}
.theme-btn.active {
  background: var(--color-primary);
  color: white;
  box-shadow: 0 4px 12px rgba(52, 152, 219, 0.3);
  opacity: 1;
}
.theme-btn:active:not(.active) {
  transform: scale(0.9);
}
.theme-btn.changing {
  animation: themeChanging 0.3s ease-in-out;
}
</style>
