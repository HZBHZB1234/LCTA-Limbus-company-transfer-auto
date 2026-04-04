class PywebviewAPI {
  constructor() {
    this.ready = false
    this.pendingCalls = []
    this._checkReady()
  }
  
  _checkReady() {
    if (window.pywebview && window.pywebview.api) {
      this.ready = true
      // 执行所有等待中的调用
      this.pendingCalls.forEach(cb => cb())
      this.pendingCalls = []
    } else {
      window.addEventListener('pywebviewready', () => {
        this.ready = true
        this.pendingCalls.forEach(cb => cb())
        this.pendingCalls = []
      }, { once: true })
    }
  }
  
  async call(method, ...args) {
    if (!this.ready) {
      await new Promise(resolve => {
        this.pendingCalls.push(resolve)
      })
    }
    try {
      return await window.pywebview.api[method](...args)
    } catch (error) {
      console.error(`API调用失败: ${method}`, error)
      throw error
    }
  }
  
  // 便捷方法
  async browse_file(inputId) {
    const path = await this.call('browse_file', inputId)
    const input = document.getElementById(inputId)
    if (input && path) input.value = path
    return path
  }
  
  async browse_folder(inputId) {
    const path = await this.call('browse_folder', inputId)
    const input = document.getElementById(inputId)
    if (input && path) input.value = path
    return path
  }
}

export const api = new PywebviewAPI()