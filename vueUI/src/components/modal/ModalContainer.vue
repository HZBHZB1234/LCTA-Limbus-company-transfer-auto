<template>
  <Teleport to="body">
    <div id="modal-container">
      <component
        v-for="modal in modals"
        :key="modal.id"
        :is="modalComponent(modal.type)"
        :id="modal.id"
        :title="modal.props.title"
        :content="modal.props.content"
        :percent="modal.percent"
        :logs="modal.logs"
        :statusText="modal.props.statusText"
        :completed="modal.props.completed"
        :success="modal.props.success"
        :cancellable="modal.props.cancellable !== false"
        :pausable="modal.props.pausable"
        :showMinimize="modal.props.showMinimize !== false"
        :onConfirm="modal.props.onConfirm"
        :onCancel="modal.props.onCancel"
        :onPause="modal.props.onPause"
        :onResume="modal.props.onResume"
        :onRunning="modal.props.onRunning"
        @close="() => modalStore.closeModal(modal.id)"
        @minimize="() => modalStore.minimizeModal(modal.id)"
      />
    </div>
    <div id="minimized-container">
      <MinimizedItem
        v-for="min in minimizedModals"
        :key="min.id"
        :id="min.id"
        :title="min.title"
        :percent="min.percent"
        :status="min.status"
        @restore="() => modalStore.restoreModal(min.id)"
      />
    </div>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue'
import { useModalStore } from '@/stores/modal'
import MessageModal from './MessageModal.vue'
import ConfirmModal from './ConfirmModal.vue'
import ProgressModal from './ProgressModal.vue'
import MinimizedItem from './MinimizedItem.vue'

const modalStore = useModalStore()
const modals = computed(() => modalStore.modals.filter(m => !m.isMinimized))
const minimizedModals = computed(() => modalStore.minimizedModals)

function modalComponent(type) {
  const map = {
    message: MessageModal,
    confirm: ConfirmModal,
    progress: ProgressModal
  }
  return map[type] || MessageModal
}
</script>

<style>
#modal-container {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  pointer-events: none;
  z-index: 2000;
}
#modal-container > * {
  pointer-events: auto;
}
#minimized-container {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 300px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  z-index: 2001;
}
</style>