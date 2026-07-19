<script setup lang="ts">
import { ref } from 'vue'
import { getApi } from '@/utils/api'
import { useModalStore } from '@/stores/modal'

const modalStore = useModalStore()

const cleanProgress = ref(true)
const cleanNotice = ref(true)
const cleanMods = ref(false)

async function doClean() {
  const mid = modalStore.create('progress', { title: '清理缓存' })
  await getApi().clean_cache(mid, [], cleanProgress.value, cleanNotice.value, cleanMods.value)
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
        <div class="form-group">
          <label class="checkbox-label"><input v-model="cleanProgress" type="checkbox" /> 清理进度缓存</label>
        </div>
        <div class="form-group">
          <label class="checkbox-label"><input v-model="cleanNotice" type="checkbox" /> 清理通知缓存</label>
        </div>
        <div class="form-group">
          <label class="checkbox-label"><input v-model="cleanMods" type="checkbox" /> 清理 Mod 缓存</label>
        </div>
        <div class="action-area">
          <button class="primary-btn" @click="doClean"><i class="fas fa-broom"></i> 开始清理</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.section-header { margin-bottom: 24px; }
.section-title { font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.section-title i { color: var(--accent-color); }
.section-subtitle { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }
.settings-grid { display: grid; grid-template-columns: 1fr; gap: 20px; max-width: 500px; }
.setting-card { background: var(--bg-secondary); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color); }
.setting-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
.form-group { margin-bottom: 14px; }
.action-area { margin-top: 16px; }
.primary-btn {
  padding: 10px 24px; border-radius: 8px; border: none; background: var(--accent-color); color: white; cursor: pointer; font-size: 14px;
}
.checkbox-label { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 14px; }
</style>
