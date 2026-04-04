import { defineStore } from 'pinia'

const THEME_KEY = 'lcta_theme'

export const useThemeStore = defineStore('theme', {
  state: () => ({
    currentTheme: 'light',  // light, dark, purple
    isTransitioning: false
  }),
  
  actions: {
    initTheme() {
      const saved = localStorage.getItem(THEME_KEY)
      if (saved && ['light', 'dark', 'purple'].includes(saved)) {
        this.setTheme(saved, true)
      } else {
        // 检测系统偏好
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
        this.setTheme(prefersDark ? 'dark' : 'light', true)
      }
    },
    
    setTheme(theme, skipTransition = false) {
      if (this.currentTheme === theme) return
      
      if (!skipTransition) {
        this.isTransitioning = true
        document.body.classList.add('theme-transition')
      }
      
      // 更新 DOM 类
      document.body.classList.remove('theme-light', 'theme-dark', 'theme-purple')
      document.body.classList.add(`theme-${theme}`)
      
      this.currentTheme = theme
      localStorage.setItem(THEME_KEY, theme)
      
      if (!skipTransition) {
        setTimeout(() => {
          document.body.classList.remove('theme-transition')
          this.isTransitioning = false
        }, 300)
      }
    },
    
    toggleTheme() {
      const order = ['light', 'dark', 'purple']
      const currentIndex = order.indexOf(this.currentTheme)
      const next = order[(currentIndex + 1) % order.length]
      this.setTheme(next)
    }
  }
})