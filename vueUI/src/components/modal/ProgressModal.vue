<template>
  <BaseModal
    :title="title"
    :statusText="statusText"
    :logs="logs"
    :percent="percent"
    :showProgress="true"
    :showLog="true"
    :showMinimize="showMinimize"
    :showCancel="!completed && cancellable"
    :showConfirm="completed"
    :cancelText="paused ? '继续' : '暂停'"
    confirmText="完成"
    @close="$emit('close')"
    @minimize="$emit('minimize')"
    @confirm="$emit('confirm')"
    @cancel="handleCancel"
  />
</template>

<script setup>
import { ref } from 'vue'
import BaseModal from './BaseModal.vue'

const props = defineProps({
  title: String,
  percent: { type: Number, default: 0 },
  statusText: String,
  logs: { type: Array, default: () => [] },
  completed: { type: Boolean, default: false },
  success: { type: Boolean, default: true },
  cancellable: { type: Boolean, default: true },
  pausable: { type: Boolean, default: true },
  showMinimize: { type: Boolean, default: true },
  onCancel: Function,
  onPause: Function,
  onResume: Function,
  onRunning: Function
})

const emit = defineEmits(['close', 'minimize', 'confirm'])

const paused = ref(false)

function handleCancel() {
  if (props.completed) {
    emit('close')
    return
  }
  if (props.pausable) {
    if (paused.value) {
      // 恢复
      paused.value = false
      if (props.onResume) props.onResume()
      if (props.onRunning) props.onRunning('running')
    } else {
      // 暂停
      paused.value = true
      if (props.onPause) props.onPause()
      if (props.onRunning) props.onRunning('pause')
    }
  } else {
    // 取消
    if (props.onCancel) props.onCancel()
    if (props.onRunning) props.onRunning('cancel')
    emit('close')
  }
}
</script>