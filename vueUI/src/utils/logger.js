import { useLogStore } from '@/stores/log'

// 全局日志函数（可在任何地方调用）
export function addLogMessage(message, level = 'info') {
  // 尝试获取 log store（可能尚未初始化）
  if (window.__logStore) {
    window.__logStore.addLog(message, level)
  } else {
    console.log(`[${level.toUpperCase()}] ${message}`)
  }
}

// 初始化全局日志接口
export function initGlobalLogger() {
  window.addLogMessage = addLogMessage
}