import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useConfigStore } from './config'

export type ThemeName = 'light' | 'dark' | 'purple'

const THEME_KEY = '--theme'
const THEME_CLASSES: ThemeName[] = ['light', 'dark', 'purple']

function applyBodyClass(theme: ThemeName): void {
  for (const cls of THEME_CLASSES) {
    document.body.classList.remove(`theme-${cls}`)
  }
  document.body.classList.add(`theme-${theme}`)
}

function getStoredTheme(): ThemeName {
  try {
    const stored = localStorage.getItem('lcta-theme')
    if (stored && THEME_CLASSES.includes(stored as ThemeName)) {
      return stored as ThemeName
    }
  } catch { /* localStorage unavailable */ }
  return 'light'
}

export const useThemeStore = defineStore('theme', () => {
  const current = ref<ThemeName>(getStoredTheme())

  function init(): void {
    applyBodyClass(current.value)
  }

  function switchTheme(theme: ThemeName): void {
    current.value = theme
    applyBodyClass(theme)
    try {
      localStorage.setItem('lcta-theme', theme)
    } catch { /* localStorage unavailable */ }
    try {
      const configStore = useConfigStore()
      if (configStore.initialized) {
        configStore.set(THEME_KEY, theme)
        configStore.save().catch(() => {})
      }
    } catch { /* config store not ready */ }
  }

  return { current, init, switchTheme }
})
