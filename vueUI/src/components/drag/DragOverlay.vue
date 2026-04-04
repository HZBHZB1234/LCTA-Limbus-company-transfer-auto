<template>
  <div v-if="isDragging" class="drop-zone-mask">
    <div class="drop-zone-mask-content">
      <i class="fas fa-cloud-upload-alt"></i>
      <p>拖拽文件到这里</p>
      <small>支持汉化包安装，模组安装或是版本更新</small>
    </div>
  </div>
</template>

<script setup>
import { useDragDropStore } from '@/stores/dragDrop'
import { storeToRefs } from 'pinia'

const dragDropStore = useDragDropStore()
const { isDragging } = storeToRefs(dragDropStore)
</script>

<style scoped>
.drop-zone-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  pointer-events: none;
  animation: maskFadeIn 0.2s ease-out;
}
.drop-zone-mask-content {
  text-align: center;
  color: white;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
  animation: contentScaleIn 0.25s cubic-bezier(0.2, 0.9, 0.4, 1.1);
}
.drop-zone-mask-content i {
  font-size: 64px;
  margin-bottom: 20px;
}
.drop-zone-mask-content p {
  font-size: 24px;
  font-weight: 500;
  margin: 0 0 8px;
}
@keyframes maskFadeIn {
  from { opacity: 0; backdrop-filter: blur(0); }
  to { opacity: 1; backdrop-filter: blur(8px); }
}
@keyframes contentScaleIn {
  from { opacity: 0; transform: scale(0.9); }
  to { opacity: 1; transform: scale(1); }
}
</style>