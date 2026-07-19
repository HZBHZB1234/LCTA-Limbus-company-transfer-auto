import type { PyWebViewApi } from '../types/api'

declare global {
  interface Window {
    pywebview?: {
      api: PyWebViewApi
    }
    apiReady: boolean
  }
}

let _api: PyWebViewApi | null = null

export function initApi(): Promise<PyWebViewApi> {
  return new Promise((resolve) => {
    if (window.pywebview?.api) {
      _api = window.pywebview.api
      window.apiReady = true
      resolve(_api)
    } else {
      window.addEventListener('pywebviewready', () => {
        _api = window.pywebview!.api
        window.apiReady = true
        resolve(_api)
      })
    }
  })
}

export function getApi(): PyWebViewApi {
  if (!_api) {
    throw new Error('API not initialized. Call initApi() first.')
  }
  return _api
}
