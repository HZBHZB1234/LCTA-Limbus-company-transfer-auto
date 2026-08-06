type ApiMethod = (...args: unknown[]) => Promise<unknown>

const waitForPywebview = async (): Promise<Record<string, ApiMethod> | null> => {
  if (window.pywebview?.api) return window.pywebview.api as Record<string, ApiMethod>

  await new Promise<void>((resolve) => {
    const timeout = window.setTimeout(resolve, 1200)
    window.addEventListener(
      'pywebviewready',
      () => {
        window.clearTimeout(timeout)
        resolve()
      },
      { once: true },
    )
  })
  return (window.pywebview?.api as Record<string, ApiMethod> | undefined) ?? null
}

export async function callBridge<T>(method: string, ...args: unknown[]): Promise<T> {
  const api = await waitForPywebview()
  const target = api?.[method]
  if (!target) {
    throw new Error(`Bridge method unavailable: ${method}`)
  }
  return (await target(...args)) as T
}

export function bridgeAvailable(): boolean {
  return Boolean(window.pywebview?.api)
}
