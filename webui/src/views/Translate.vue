<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getApi } from '@/utils/api'
import { useConfigStore } from '@/stores/config'
import { useModalStore } from '@/stores/modal'

const modalStore = useModalStore()
const configStore = useConfigStore()

const translator = ref('')
const apiSettings = ref<Record<string, unknown>>({})
const enableProper = ref(false)
const autoProper = ref(false)

onMounted(async () => {
  translator.value = (configStore.get('ui_default.translator.translator') as string) || ''
  enableProper.value = configStore.get('ui_default.translator.enable_proper') as boolean || false
  autoProper.value = configStore.get('ui_default.translator.auto_proper') as boolean || false
})

async function startTranslate() {
  const mid = modalStore.create('progress', { title: '正在翻译...' })
  await getApi().start_translation({
    translator: translator.value,
    api_settings: apiSettings.value,
  }, mid)
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-language"></i> 翻译工具</h2>
      <p class="section-subtitle">使用 LLM 自动翻译游戏文本</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card">
        <h3 class="setting-title">翻译配置</h3>
        <div class="form-group">
          <label class="checkbox-label"><input v-model="enableProper" type="checkbox" /> 启用专有名词匹配</label>
        </div>
        <div class="form-group">
          <label class="checkbox-label"><input v-model="autoProper" type="checkbox" /> 自动抓取专有名词</label>
        </div>
        <p style="color: var(--text-secondary); font-size: 13px; margin-bottom: 16px">
          翻译器请在「配置汉化API」页面选择和配置
        </p>
        <div class="action-area">
          <button class="primary-btn" @click="startTranslate">
            <i class="fas fa-play"></i> 开始翻译
          </button>
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
