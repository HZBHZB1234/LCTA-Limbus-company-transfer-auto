<script setup lang="ts">
import { ref } from 'vue'
import { getApi } from '@/utils/api'
import { useModalStore } from '@/stores/modal'

const modalStore = useModalStore()

const cleanProgress = ref(true)
const cleanNotice = ref(true)
const cleanMods = ref(false)

async function doClean() {
  const confirmId = modalStore.create('confirm', {
    title: '确定要清除缓存吗？',
    confirmText: '确定清除',
    onConfirm: async () => {
      modalStore.remove(confirmId)
      const mid = modalStore.create('progress', { title: '清理缓存' })
      await getApi().clean_cache(mid, [], cleanProgress.value, cleanNotice.value, cleanMods.value)
    },
  })
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-broom"></i> 清除本地缓存</h2>
      <p class="section-subtitle">清理游戏缓存文件</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card">
        <h3 class="setting-title">清理选项</h3>
        <div class="form-group" v-tooltip="'clean-progress'">
          <label class="checkbox-label">
            <input v-model="cleanProgress" type="checkbox" /> 清理进度缓存
          </label>
        </div>
        <div class="form-group" v-tooltip="'clean-notice'">
          <label class="checkbox-label">
            <input v-model="cleanNotice" type="checkbox" /> 清理通知缓存
          </label>
        </div>
        <div class="form-group" v-tooltip="'clean-mods'">
          <label class="checkbox-label">
            <input v-model="cleanMods" type="checkbox" /> 清理 Mod 缓存
          </label>
        </div>

        <div style="margin: 24px 0; padding: 16px; background: var(--color-bg-input); border-radius: var(--radius-md); border-left: 4px solid var(--color-danger);">
          <div style="color: var(--color-danger); font-weight: 600; margin-bottom: 4px;">
            <i class="fas fa-exclamation-triangle"></i> 注意
          </div>
          <p style="color: var(--color-text-secondary); font-size: 13px; margin: 0;">
            此操作不可逆！清除后将无法恢复被删除的文件。请确认已备份重要数据。
          </p>
        </div>

        <div class="action-area">
          <button class="primary-btn danger" @click="doClean"><i class="fas fa-broom"></i> 清除缓存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Clean view uses shared global classes from main.css */
</style>
