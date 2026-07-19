import type { LctaEventMap, LctaEventName } from '../types/events'

export function listenEvent<E extends LctaEventName>(
  name: E,
  handler: (detail: LctaEventMap[E]) => void
): () => void {
  const listener = (e: Event) => {
    handler((e as CustomEvent<LctaEventMap[E]>).detail)
  }
  window.addEventListener(name, listener)
  return () => window.removeEventListener(name, listener)
}
