import { defineStore } from 'pinia'

export const useModalStore = defineStore('modal', {
  state: () => ({
    modals: [],        // { id, type, props, isMinimized, logs, percent }
    nextId: 1,
    minimizedModals: [] // 最小化窗口列表
  }),
  
  actions: {
    openModal(type, props = {}) {
      const id = this.nextId++
      const modal = {
        id,
        type,
        props: {
          title: props.title || '提示',
          ...props
        },
        isMinimized: false,
        logs: props.logs || [],
        percent: props.percent || 0
      }
      this.modals.push(modal)
      
      // 注册到后端（用于进度更新）
      if (type === 'progress' && window.pywebview?.api) {
        window.pywebview.api.add_modal_id(id).catch(console.error)
      }
      
      return id
    },
    
    closeModal(id) {
      const index = this.modals.findIndex(m => m.id === id)
      if (index !== -1) {
        this.modals.splice(index, 1)
      }
      // 同时从最小化列表中移除
      const minIndex = this.minimizedModals.findIndex(m => m.id === id)
      if (minIndex !== -1) {
        this.minimizedModals.splice(minIndex, 1)
      }
    },
    
    minimizeModal(id) {
      const modal = this.modals.find(m => m.id === id)
      if (modal && !modal.isMinimized) {
        modal.isMinimized = true
        this.minimizedModals.push({
          id: modal.id,
          title: modal.props.title,
          percent: modal.percent,
          status: modal.props.statusText || '运行中'
        })
      }
    },
    
    restoreModal(id) {
      const modal = this.modals.find(m => m.id === id)
      if (modal && modal.isMinimized) {
        modal.isMinimized = false
        const minIndex = this.minimizedModals.findIndex(m => m.id === id)
        if (minIndex !== -1) {
          this.minimizedModals.splice(minIndex, 1)
        }
      }
    },
    
    updateProgress(id, percent, statusText = null) {
      const modal = this.modals.find(m => m.id === id)
      if (modal && modal.type === 'progress') {
        modal.percent = percent
        if (statusText !== null) {
          modal.props.statusText = statusText
        }
        // 更新最小化窗口中的进度
        const minModal = this.minimizedModals.find(m => m.id === id)
        if (minModal) {
          minModal.percent = percent
          if (statusText) minModal.status = statusText
        }
      }
    },
    
    addLog(id, message) {
      const modal = this.modals.find(m => m.id === id)
      if (modal && modal.type === 'progress') {
        const timestamp = new Date().toLocaleTimeString()
        modal.logs.push({ timestamp, message })
        // 限制日志数量
        if (modal.logs.length > 200) {
          modal.logs = modal.logs.slice(-150)
        }
      }
    },
    
    completeModal(id, success, message) {
      const modal = this.modals.find(m => m.id === id)
      if (modal && modal.type === 'progress') {
        modal.props.completed = true
        modal.props.success = success
        modal.props.statusText = message
        // 3秒后自动关闭
        setTimeout(() => {
          this.closeModal(id)
        }, 3000)
      }
    },
    
    setModalRunning(id, action) {
      // 供后端调用的接口
      const modal = this.modals.find(m => m.id === id)
      if (modal && modal.props.onRunning) {
        modal.props.onRunning(action)
      }
    }
  }
})

// 挂载全局函数供后端调用
if (typeof window !== 'undefined') {
  window.__updateModalProgress = (id, percent, text) => {
    const store = useModalStore()
    store.updateProgress(id, percent, text)
  }
  window.__addModalLog = (id, message) => {
    const store = useModalStore()
    store.addLog(id, message)
  }
  window.__completeModal = (id, success, message) => {
    const store = useModalStore()
    store.completeModal(id, success, message)
  }
  window.__setModalRunning = (id, action) => {
    const store = useModalStore()
    store.setModalRunning(id, action)
  }
}