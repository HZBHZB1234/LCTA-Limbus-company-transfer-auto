<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { listenEvent } from '@/utils/events'
import { getApi } from '@/utils/api'
import { useModalStore } from '@/stores/modal'

const modalStore = useModalStore()
const visible = ref(false)
let dragCounter = 0
let eventCleanup: (() => void) | null = null

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
}

async function handleFileDrop(files: string[]) {
  try {
    const result = await getApi().handle_dropped_files(files)
    if (!result || !result.success) {
      return
    }
    const confirmId = modalStore.create('confirm', {
      title: result.message,
      confirmText: '确认执行',
      onConfirm: async () => {
        modalStore.remove(confirmId)
        const progressId = modalStore.create('progress', { title: '处理文件' })
        modalStore.addLog(progressId, '正在处理文件...')
        try {
          await getApi().eval_dropped_files(result.file_info as unknown as string[], progressId)
          modalStore.setStatus(progressId, 'completed')
          modalStore.updateProgress(progressId, 100, '处理完成')
        } catch (err) {
          modalStore.setStatus(progressId, 'canceled')
          modalStore.addLog(progressId, `处理失败：${String(err)}`)
        }
      },
    })
  } catch (err) {
    console.error('处理拖入文件时出错:', err)
  }
}

onMounted(() => {
  document.addEventListener('dragenter', onDragEnter)
  document.addEventListener('dragover', onDragOver)
  document.addEventListener('dragleave', onDragLeave)
  document.addEventListener('drop', onDrop)

  eventCleanup = listenEvent('lcta:file-dropped', (detail) => {
    if (detail.files && detail.files.length > 0) {
      handleFileDrop(detail.files)
    }
  })
})

onUnmounted(() => {
  document.removeEventListener('dragenter', onDragEnter)
  document.removeEventListener('dragover', onDragOver)
  document.removeEventListener('dragleave', onDragLeave)
  document.removeEventListener('drop', onDrop)
  if (eventCleanup) eventCleanup()
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
  z-index: 10000;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  animation: maskFadeIn 0.2s ease-out;
}
.drag-box {
  text-align: center;
  color: white;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
  animation: contentScaleIn 0.25s cubic-bezier(0.2, 0.9, 0.4, 1.1);
}
.drag-box i { font-size: 64px; margin-bottom: 20px; opacity: 0.9; filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.3)); }
.drag-box p { font-size: 24px; font-weight: 500; opacity: 0.9; margin: 0 0 8px; }
</style>
