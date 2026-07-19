import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getApi } from '@/utils/api'
import { marked } from 'marked'
import { useModalStore } from '@/stores/modal'

export const useUpdateStore = defineStore('update', () => {
  const latestVersion = ref<string | null>(null)
  const currentVersion = ref<string>('')
  const releaseNotes = ref<string | null>(null)
  const hasUpdate = ref(false)
  const updating = ref(false)

  async function check(): Promise<void> {
    const result = await getApi().manual_check_update()
    latestVersion.value = result.latest_version
    currentVersion.value = result.current_version
    releaseNotes.value = result.release_notes
    hasUpdate.value = result.has_update
  }

  async function perform(modalId: string): Promise<void> {
    updating.value = true
    try {
      await getApi().perform_update_in_modal(modalId)
    } catch (e) {
      console.error('Update perform failed:', e)
      getApi().log(`[Update] 更新执行失败: ${e}`).catch(() => {})
    } finally {
      updating.value = false
    }
  }

  function showUpdateModal(): void {
    if (!hasUpdate.value) return

    const modalStore = useModalStore()
    const notes = releaseNotes.value || '(暂无更新说明)'
    const notesHtml = marked.parse(notes) as string

    const bodyHtml = `
<div class="update-info">
  <div class="update-version">
    <span>${currentVersion.value}</span>
    <i class="fas fa-arrow-right" style="margin: 0 8px;"></i>
    <span style="color: var(--color-primary); font-weight: bold;">${latestVersion.value}</span>
  </div>
  <div class="update-notes">
    <h3>更新内容</h3>
    ${notesHtml}
  </div>
</div>`

    const messageModalId = modalStore.create('message', {
      title: '发现新版本',
      bodyHtml,
      actionButtons: [
        {
          text: '立即更新',
          danger: false,
          onClick: () => {
            modalStore.remove(messageModalId)
            const progressId = modalStore.create('progress', { title: '正在更新 LCTA' })
            perform(progressId)
          },
        },
        {
          text: '稍后提醒',
          danger: false,
          onClick: () => {
            modalStore.remove(messageModalId)
          },
        },
      ],
    })
  }

  return { latestVersion, currentVersion, releaseNotes, hasUpdate, updating, check, perform, showUpdateModal }
})
