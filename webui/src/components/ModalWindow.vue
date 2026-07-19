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

      <div v-if="modal.type === 'message' && modal.bodyHtml" class="modal-message-body" v-html="modal.bodyHtml"></div>

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
        <template v-if="modal.actionButtons && modal.actionButtons.length > 0">
          <button
            v-for="(btn, idx) in modal.actionButtons"
            :key="idx"
            class="modal-btn"
            :class="{ 'modal-btn-danger': btn.danger }"
            @click="btn.onClick()"
          >
            {{ btn.text }}
          </button>
        </template>
        <button v-else class="modal-btn" @click="emit('close', modal.id)">确定</button>
      </template>
    </div>
  </div>
</template>

<style scoped>
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
  flex: 1;
}
.modal-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--color-primary);
  color: white;
}
.modal-status.canceled { background: var(--color-danger); }
.modal-status.completed { background: var(--color-success); }

.modal-header-actions { display: flex; gap: var(--spacing-sm); }
.modal-btn-icon {
  width: 32px; height: 32px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  background: var(--color-bg-input);
  color: var(--color-text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: all var(--transition-speed) var(--transition-easing);
}
.modal-btn-icon:hover {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.modal-body {
  padding: var(--spacing-lg);
  overflow-y: auto;
  flex: 1;
}
.modal-log {
  margin-top: var(--spacing-md);
  max-height: 200px;
  overflow-y: auto;
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  padding: var(--spacing-md);
  font-size: 12px;
  font-family: 'Consolas', monospace;
}
.modal-log-entry { display: flex; gap: 8px; padding: 2px 0; }
.log-time { color: var(--color-text-secondary); flex-shrink: 0; }
.log-msg { word-break: break-all; }
.modal-confirm-message { padding: var(--spacing-md) 0; }
.modal-message-body {
  padding: var(--spacing-md) 0;
  max-height: 400px;
  overflow-y: auto;
}
.modal-message-body :deep(h1),
.modal-message-body :deep(h2),
.modal-message-body :deep(h3) {
  margin-top: 0;
  color: var(--color-text-primary);
}
.modal-message-body :deep(p) {
  margin: 8px 0;
  line-height: 1.6;
}
.modal-message-body :deep(a) {
  color: var(--color-primary);
}

.modal-footer {
  padding: var(--spacing-lg);
  border-top: 1px solid var(--color-border);
  background: var(--color-bg-primary);
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
}
.modal-btn {
  padding: 8px 20px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-input);
  color: var(--color-text-primary);
  cursor: pointer;
  font-size: 14px;
  transition: all var(--transition-speed) var(--transition-easing);
}
.modal-btn:hover { background: var(--color-primary); color: white; border-color: var(--color-primary); }
.modal-btn-danger { color: var(--color-danger); border-color: var(--color-danger); }
.modal-btn-danger:hover { background: var(--color-danger); color: white; }
.modal-btn-cancel { color: var(--color-text-secondary); }
</style>
