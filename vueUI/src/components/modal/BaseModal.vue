<template>
  <div class="modal-overlay" @click.self="handleOverlayClick">
    <div class="modal-window" :class="{ minimized: isMinimized }">
      <div class="modal-header">
        <div class="modal-title">{{ title }}</div>
        <div class="modal-controls">
          <button v-if="showMinimize" class="modal-button" @click="$emit('minimize')" title="最小化">−</button>
          <button class="modal-button" @click="$emit('close')" title="关闭">×</button>
        </div>
      </div>
      <div class="modal-body">
        <slot name="body">
          <div class="modal-status" v-if="statusText">{{ statusText }}</div>
          <div class="modal-log" v-if="showLog">
            <div v-for="(log, idx) in logs" :key="idx" class="log-line">{{ log.timestamp }} {{ log.message }}</div>
          </div>
          <div class="modal-progress" v-if="showProgress">
            <ProgressBar :percent="percent" :text="progressText" />
          </div>
          <div v-else-if="content" class="modal-content" v-html="content"></div>
        </slot>
      </div>
      <div class="modal-footer">
        <slot name="footer">
          <Button v-if="showCancel" variant="secondary" @click="handleCancel">{{ cancelText }}</Button>
          <Button v-if="showConfirm" variant="primary" @click="handleConfirm">{{ confirmText }}</Button>
        </slot>
      </div>
    </div>
  </div>
</template>

<script setup>
import Button from '@/components/common/Button.vue'
import ProgressBar from '@/components/common/ProgressBar.vue'

const props = defineProps({
  title: { type: String, default: '提示' },
  content: String,
  statusText: String,
  logs: { type: Array, default: () => [] },
  percent: { type: Number, default: 0 },
  showProgress: { type: Boolean, default: false },
  showLog: { type: Boolean, default: false },
  showMinimize: { type: Boolean, default: true },
  showCancel: { type: Boolean, default: true },
  showConfirm: { type: Boolean, default: true },
  cancelText: { type: String, default: '取消' },
  confirmText: { type: String, default: '确定' },
  closeOnOverlay: { type: Boolean, default: false },
  isMinimized: { type: Boolean, default: false },
  onConfirm: Function,
  onCancel: Function
})

const emit = defineEmits(['close', 'minimize', 'confirm', 'cancel'])

const progressText = computed(() => props.statusText || `${props.percent}%`)

function handleConfirm() {
  if (props.onConfirm) props.onConfirm()
  emit('confirm')
  emit('close')
}

function handleCancel() {
  if (props.onCancel) props.onCancel()
  emit('cancel')
  emit('close')
}

function handleOverlayClick() {
  if (props.closeOnOverlay) {
    emit('close')
  }
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--color-bg-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(5px);
  animation: fadeIn 0.3s ease;
}
.modal-window {
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  width: 600px;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: slideUp 0.4s var(--transition-easing);
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-lg);
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-primary);
}
.modal-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.modal-controls {
  display: flex;
  gap: var(--spacing-sm);
}
.modal-button {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  background: var(--color-bg-input);
  color: var(--color-text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}
.modal-button:hover {
  background: var(--color-primary);
  color: white;
}
.modal-body {
  padding: var(--spacing-lg);
  overflow-y: auto;
  flex: 1;
}
.modal-status {
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-md);
  background: var(--color-bg-primary);
  border-radius: var(--radius-md);
  border-left: 4px solid var(--color-primary);
}
.modal-log {
  height: 200px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-input);
  padding: var(--spacing-md);
  overflow-y: auto;
  font-family: monospace;
  font-size: 12px;
  margin-bottom: var(--spacing-lg);
}
.log-line {
  padding: 2px 0;
  border-bottom: 1px solid var(--color-border-light);
}
.modal-footer {
  padding: var(--spacing-lg);
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-primary);
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
}
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes slideUp {
  from {
    opacity: 0;
    transform: translateY(40px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}
</style>