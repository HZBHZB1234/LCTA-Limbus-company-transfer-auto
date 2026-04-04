import { defineStore } from 'pinia'

export const useLogStore = defineStore('log', {
  state: () => ({
    logs: []  // { timestamp, level, message }
  }),
  
  actions: {
    addLog(message, level = 'info') {
      const timestamp = new Date()
      const logEntry = {
        timestamp,
        formattedTime: this._formatTime(timestamp),
        level,
        message
      }
      this.logs.push(logEntry)
      
      // 限制日志数量
      if (this.logs.length > 1000) {
        this.logs = this.logs.slice(-800)
      }
      
      // 同步到后端
      if (window.pywebview?.api) {
        window.pywebview.api.log(`[${level.toUpperCase()}] ${message}`).catch(console.error)
      }
      
      // 触发滚动事件
      this._emitNewLog()
    },
    
    clearLogs() {
      this.logs = []
    },
    
    _formatTime(date) {
      return `[${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}:${String(date.getSeconds()).padStart(2, '0')}]`
    },
    
    _emitNewLog() {
      window.dispatchEvent(new CustomEvent('log-updated'))
    }
  }
})