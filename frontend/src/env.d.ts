/// <reference types="vite/client" />

declare global {
  interface Window {
    pywebview?: {
      api?: Record<string, (...args: unknown[]) => Promise<unknown>>
    }
  }
}

export {}
