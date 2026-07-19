<script setup lang="ts">
import { useModalStore } from '@/stores/modal'
import ModalWindow from './ModalWindow.vue'

const modalStore = useModalStore()

function onMinimize(id: string) {
  modalStore.minimize(id)
}

function onRestore(id: string) {
  modalStore.restore(id)
}

function onClose(id: string) {
  modalStore.remove(id)
}
</script>

<template>
  <Teleport to="body">
    <div
      v-for="modal in modalStore.activeModals"
      :key="modal.id"
      class="modal-overlay"
      :style="{ zIndex: 1000 + modalStore.modals.indexOf(modal) }"
    >
      <ModalWindow
        :modal="modal"
        @minimize="onMinimize"
        @restore="onRestore"
        @close="onClose"
      />
    </div>
  </Teleport>
</template>

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
</style>
