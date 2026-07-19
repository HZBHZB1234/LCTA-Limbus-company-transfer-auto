<script setup lang="ts">
import { computed } from 'vue'
import { useModalStore } from '@/stores/modal'
import type { ModalState } from '@/stores/modal'
import { getApi } from '@/utils/api'
import ProgressBar from './ProgressBar.vue'

const props = defineProps<{ modal: ModalState }>()
const emit = defineEmits<{
  minimize: [id: string]
  restore: [id: string]
  close: [id: string]
}>()

const modalStore = useModalStore()

const isCompleted = computed(() => props.modal.status === 'completed')
const isCanceled = computed(() => props.modal.status === 'canceled')
const isPaused = computed(() => props.modal.status === 'paused')

function handleCancel() {
  if (props.modal.type === 'confirm' && props.modal.onCancel) {
    props.modal.onCancel()
    return
  }
  getApi().set_modal_running(props.modal.id, 'cancel')
}

function handlePause() {
  getApi().set_modal_running(props.modal.id, isPaused.value ? 'running' : 'pause')
  modalStore.setStatus(props.modal.id, isPaused.value ? 'running' : 'paused')
}

function handleConfirm() {
  if (props.modal.onConfirm) {
    props.modal.onConfirm()
    emit('close', props.modal.id)
  }
}

function handleCancelConfirm() {
  if (props.modal.onCancel) {
    props.modal.onCancel()
  }
  emit('close', props.modal.id)
}
</script>

<template>
  <div class="modal-window" @click.stop>
    <div class="modal-header">
      <span class="modal-title">{{ modal.title }}</span>
      <span v-if="modal.type === 'progress'" class="modal-status" :class="modal.status">
        {{ isCompleted ? '完成' : isCanceled ? '已取消' : isPaused ? '已暂停' : '运行中' }}
      </span>
      <div class="modal-header-actions">
        <button
          v-if="modal.type === 'progress' && !isCompleted && !isCanceled"
          class="modal-btn-icon"
          @click="emit('minimize', modal.id)"
          title="最小化"
        >
          <i class="fas fa-minus"></i>
        </button>
        <button class="modal-btn-icon" @click="emit('close', modal.id)" title="关闭">
          <i class="fas fa-times"></i>
        </button>
      </div>
    </div>

    <div class="modal-body">
      <ProgressBar
        v-if="modal.type === 'progress'"
        :percent="modal.percent"
        :text="modal.progressText"
      />

      <div v-if="modal.type === 'confirm'" class="modal-confirm-message">
        {{ modal.title }}
      </div>

      <div
        v-if="modal.type === 'progress' && modal.logs.length > 0"
        class="modal-log"
      >
        <div v-for="(entry, i) in modal.logs" :key="i" class="modal-log-entry">
          <span class="log-time">[{{ entry.timestamp }}]</span>
          <span class="log-msg">{{ entry.message }}</span>
        </div>
      </div>
    </div>

    <div class="modal-footer">
      <template v-if="modal.type === 'progress'">
        <button
          v-if="!isCompleted && !isCanceled"
          class="modal-btn"
          @click="handlePause"
        >
          {{ isPaused ? '继续' : '暂停' }}
        </button>
        <button
          v-if="!isCompleted && !isCanceled"
          class="modal-btn modal-btn-danger"
          @click="handleCancel"
        >
          取消
        </button>
        <button
          v-if="isCompleted || isCanceled"
          class="modal-btn"
          @click="emit('close', modal.id)"
        >
          关闭
        </button>
      </template>

      <template v-if="modal.type === 'confirm'">
        <button class="modal-btn" @click="handleConfirm">
          {{ modal.confirmText || '确认' }}
        </button>
        <button class="modal-btn modal-btn-cancel" @click="handleCancelConfirm">
          {{ modal.cancelText || '取消' }}
        </button>
      </template>

      <template v-if="modal.type === 'message'">
        <button class="modal-btn" @click="emit('close', modal.id)">确定</button>
      </template>
    </div>
  </div>
</template>

<style scoped>
.modal-window {
  background: var(--bg-primary);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  width: 520px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}
.modal-header {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-color);
  gap: 12px;
}
.modal-title {
  font-weight: 600;
  font-size: 15px;
  flex: 1;
}
.modal-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--accent-color);
  color: white;
}
.modal-status.canceled { background: #e74c3c; }
.modal-status.completed { background: #27ae60; }
.modal-header-actions { display: flex; gap: 4px; }
.modal-btn-icon {
  width: 28px; height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.modal-btn-icon:hover { background: var(--bg-secondary); }
.modal-body { padding: 16px 20px; flex: 1; overflow-y: auto; }
.modal-log {
  margin-top: 12px;
  max-height: 200px;
  overflow-y: auto;
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
  font-family: 'Consolas', monospace;
}
.modal-log-entry { display: flex; gap: 8px; padding: 2px 0; }
.log-time { color: var(--text-secondary); flex-shrink: 0; }
.log-msg { word-break: break-all; }
.modal-confirm-message { padding: 16px 0; }
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--border-color);
}
.modal-btn {
  padding: 8px 20px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 14px;
}
.modal-btn:hover { background: var(--bg-secondary); }
.modal-btn-danger { color: #e74c3c; border-color: #e74c3c; }
.modal-btn-cancel { color: var(--text-secondary); }
</style>
