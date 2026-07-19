<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const visible = ref(false)
let dragCounter = 0

function onDragEnter(e: DragEvent) {
  e.preventDefault()
  dragCounter++
  if (dragCounter === 1) visible.value = true
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
}

function onDragLeave(e: DragEvent) {
  e.preventDefault()
  dragCounter--
  if (dragCounter === 0) visible.value = false
}

async function onDrop(e: DragEvent) {
  e.preventDefault()
  dragCounter = 0
  visible.value = false
  // pywebview handles the actual file paths
}

onMounted(() => {
  document.addEventListener('dragenter', onDragEnter)
  document.addEventListener('dragover', onDragOver)
  document.addEventListener('dragleave', onDragLeave)
  document.addEventListener('drop', onDrop)
})

onUnmounted(() => {
  document.removeEventListener('dragenter', onDragEnter)
  document.removeEventListener('dragover', onDragOver)
  document.removeEventListener('dragleave', onDragLeave)
  document.removeEventListener('drop', onDrop)
})
</script>

<template>
  <div v-if="visible" class="drag-overlay">
    <div class="drag-box">
      <i class="fas fa-cloud-upload-alt"></i>
      <p>释放文件以安装汉化包</p>
    </div>
  </div>
</template>

<style scoped>
.drag-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  z-index: 9999;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
}
.drag-box {
  text-align: center;
  color: white;
  border: 3px dashed rgba(255, 255, 255, 0.6);
  border-radius: 16px;
  padding: 48px 64px;
}
.drag-box i { font-size: 48px; margin-bottom: 16px; opacity: 0.8; }
.drag-box p { font-size: 18px; opacity: 0.8; }
</style>
