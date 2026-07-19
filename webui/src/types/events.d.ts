export interface LctaLogEvent {
  message: string
  level: 'info' | 'warn' | 'error'
}

export interface LctaModalLogEvent {
  modalId: string
  message: string
}

export interface LctaModalProgressEvent {
  modalId: string
  percent: number
  text: string
}

export interface LctaModalStatusEvent {
  modalId: string
  status: string
  text?: string
}

export interface LctaFilePickedEvent {
  inputId: string
  path: string
}

export interface LctaFileDroppedEvent {
  files: string[]
}

export interface LctaConfigReloadedEvent {
  // empty payload
}

export type LctaEventMap = {
  'lcta:log': LctaLogEvent
  'lcta:modal-log': LctaModalLogEvent
  'lcta:modal-progress': LctaModalProgressEvent
  'lcta:modal-status': LctaModalStatusEvent
  'lcta:file-picked': LctaFilePickedEvent
  'lcta:file-dropped': LctaFileDroppedEvent
  'lcta:config-reloaded': LctaConfigReloadedEvent
}

export type LctaEventName = keyof LctaEventMap
