import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getApi } from '@/utils/api'

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
    await getApi().perform_update_in_modal(modalId)
    updating.value = false
  }

  return { latestVersion, currentVersion, releaseNotes, hasUpdate, updating, check, perform }
})
