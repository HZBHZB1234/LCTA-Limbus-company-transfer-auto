<template>
  <div class="theme-toggle">
    <button 
      v-for="theme in themes" 
      :key="theme.value"
      class="theme-btn" 
      :class="{ active: currentTheme === theme.value }"
      @click="setTheme(theme.value)"
      :title="theme.name"
    >
      <i :class="theme.icon"></i>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()
const currentTheme = computed(() => themeStore.currentTheme)

const themes = [
  { value: 'light', name: '亮色主题', icon: 'fas fa-sun' },
  { value: 'dark', name: '暗色主题', icon: 'fas fa-moon' },
  { value: 'purple', name: '蓝紫色主题', icon: 'fas fa-palette' }
]

function setTheme(theme) {
  themeStore.setTheme(theme)
}
</script>

<style scoped>
.theme-toggle {
  position: fixed;
  top: 20px;
  right: 20px;
  display: flex;
  gap: 8px;
  background: var(--color-bg-secondary);
  padding: 8px;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  z-index: 1000;
  backdrop-filter: blur(10px);
  border: 1px solid var(--color-border);
}
.theme-btn {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  transition: all var(--transition-speed) var(--transition-easing);
}
.theme-btn:hover {
  background: var(--color-bg-primary);
  color: var(--color-primary);
  transform: translateY(-2px);
}
.theme-btn.active {
  background: var(--color-primary);
  color: white;
  box-shadow: 0 4px 12px rgba(var(--color-primary), 0.3);
}
</style>