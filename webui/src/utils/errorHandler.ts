import { getApi } from './api'

const preApiErrors: Array<{ message: string; stack: string; timestamp: string }> = []
const preApiRejections: Array<{ message: string; timestamp: string }> = []

function isApiReady(): boolean {
  return !!(window as unknown as Record<string, unknown> & { apiReady?: boolean }).apiReady
}

async function flushPreApiErrors(): Promise<void> {
  if (!isApiReady()) return

  if (preApiErrors.length > 0 || preApiRejections.length > 0) {
    const api = getApi()
    for (const err of preApiErrors.splice(0)) {
      try {
        await api.log(`[前端错误] ${err.message}\n堆栈: ${err.stack}`)
      } catch { /* ignore */ }
    }
    for (const rej of preApiRejections.splice(0)) {
      try {
        await api.log(`[前端Promise错误] ${rej.message}`)
      } catch { /* ignore */ }
    }
  }
}

export function setupGlobalErrorHandling(): void {
  ;(window as unknown as Record<string, unknown>).apiReady = false

  window.addEventListener('error', (event: ErrorEvent) => {
    const errorMessage = `[全局错误] ${event.message} at ${event.filename}:${event.lineno}:${event.colno}`
    const stack = event.error?.stack ?? '无堆栈信息'

    console.error('已捕捉到异常', errorMessage)

    if (isApiReady()) {
      try {
        getApi().log(`[前端错误] ${errorMessage}\n堆栈: ${stack}`).catch(() => {})
      } catch { /* api not ready */ }
    } else {
      preApiErrors.push({
        message: errorMessage,
        stack,
        timestamp: new Date().toISOString(),
      })
    }
  })

  window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
    const errorMessage = `[未处理的Promise拒绝] ${String(event.reason)}`

    console.error('已捕捉到异常', errorMessage)

    if (isApiReady()) {
      try {
        getApi().log(`[前端Promise错误] ${errorMessage}`).catch(() => {})
      } catch { /* api not ready */ }
    } else {
      preApiRejections.push({
        message: errorMessage,
        timestamp: new Date().toISOString(),
      })
    }
  })
}

export { flushPreApiErrors, preApiErrors, preApiRejections }
