import { defineStore } from 'pinia'
import { api } from '@/utils/api'
import { useModalStore } from './modal'

export const useDragDropStore = defineStore('dragDrop', {
  state: () => ({
    isDragging: false,
    dragCounter: 0
  }),
  
  actions: {
    init() {
      window.addEventListener('dragenter', this.onDragEnter)
      window.addEventListener('dragover', this.onDragOver)
      window.addEventListener('dragleave', this.onDragLeave)
      window.addEventListener('drop', this.onDrop)
    },
    
    destroy() {
      window.removeEventListener('dragenter', this.onDragEnter)
      window.removeEventListener('dragover', this.onDragOver)
      window.removeEventListener('dragleave', this.onDragLeave)
      window.removeEventListener('drop', this.onDrop)
    },
    
    onDragEnter(e) {
      e.preventDefault()
      this.dragCounter++
      if (this.dragCounter === 1) {
        this.isDragging = true
      }
    },
    
    onDragOver(e) {
      e.preventDefault()
      e.dataTransfer.dropEffect = 'copy'
    },
    
    onDragLeave(e) {
      e.preventDefault()
      this.dragCounter--
      if (this.dragCounter === 0) {
        this.isDragging = false
      }
    },
    
    async onDrop(e) {
      e.preventDefault()
      this.dragCounter = 0
      this.isDragging = false
      
      const files = Array.from(e.dataTransfer.files)
      if (files.length === 0) return
      
      const modalStore = useModalStore()
      const confirmId = modalStore.openModal('confirm', {
        title: '处理文件',
        content: `检测到 ${files.length} 个文件被拖入，是否立即处理？`,
        onConfirm: async () => {
          const progressId = modalStore.openModal('progress', {
            title: '处理拖拽文件',
            statusText: '正在处理...'
          })
          try {
            const result = await api.call('handle_dropped_files', files)
            if (result.success) {
              modalStore.completeModal(progressId, true, '文件处理完成')
            } else {
              modalStore.completeModal(progressId, false, result.message)
            }
          } catch (err) {
            modalStore.completeModal(progressId, false, err.message)
          }
        }
      })
    }
  }
})