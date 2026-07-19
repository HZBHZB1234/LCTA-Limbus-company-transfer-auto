<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getApi } from '@/utils/api'
import { useConfigStore } from '@/stores/config'

const configStore = useConfigStore()

const apiServices = ref<Record<string, { name: string; api_settings: Array<{ key: string; type: string; label: string }> }>>({})
const selectedService = ref('')
const apiSettings = ref<Record<string, string>>({})
const translatorServices = ref<Record<string, { name: string }>>({})
const selectedTranslator = ref('')

onMounted(async () => {
  try {
    const tkitMachine = await getApi().get_attr('TKIT_MACHINE_OBJECT') as Record<string, unknown>
    apiServices.value = tkitMachine as Record<string, { name: string; api_settings: Array<{ key: string; type: string; label: string }> }>
    const keys = Object.keys(apiServices.value)
    if (keys.length > 0) {
      selectedService.value = keys[0]
      onServiceChange()
    }
  } catch { /* ignore */ }

  try {
    const llmTranslator = await getApi().get_attr('LLM_TRANSLATOR') as Record<string, { name: string }>
    translatorServices.value = llmTranslator
    selectedTranslator.value = (configStore.get('ui_default.translator.translator') as string) || Object.keys(llmTranslator)[0] || ''
  } catch { /* ignore */ }
})

function onServiceChange() {
  const service = apiServices.value[selectedService.value]
  if (service?.api_settings) {
    const settings: Record<string, string> = {}
    for (const s of service.api_settings) {
      settings[s.key] = configStore.get(`api_${selectedService.value}_${s.key}`) as string || ''
    }
    apiSettings.value = settings
  }
}

async function saveConfig() {
  for (const [key, value] of Object.entries(apiSettings.value)) {
    configStore.set(`api_${selectedService.value}_${key}`, value)
  }
  if (selectedTranslator.value) {
    configStore.set('ui_default.translator.translator', selectedTranslator.value)
  }
  await configStore.save()
}

async function testApi() {
  if (!selectedService.value) return
  await getApi().test_api(selectedService.value, apiSettings.value)
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-cog"></i> 配置汉化API</h2>
      <p class="section-subtitle">管理翻译服务和API密钥</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card">
        <h3 class="setting-title">翻译器选择</h3>
        <div class="form-group">
          <label>翻译器:</label>
          <select v-model="selectedTranslator">
            <option v-for="(svc, key) in translatorServices" :key="key" :value="key">{{ svc.name }}</option>
          </select>
        </div>
      </div>

      <div class="setting-card" v-if="Object.keys(apiServices).length > 0">
        <h3 class="setting-title">API服务配置</h3>
        <div class="form-group">
          <label>服务:</label>
          <select v-model="selectedService" @change="onServiceChange">
            <option v-for="(svc, key) in apiServices" :key="key" :value="key">{{ svc.name }}</option>
          </select>
        </div>

        <template v-if="apiServices[selectedService]?.api_settings">
          <div v-for="setting in apiServices[selectedService].api_settings" :key="setting.key" class="form-group">
            <label>{{ setting.label }}:</label>
            <input
              v-if="setting.type === 'str'"
              v-model="apiSettings[setting.key]"
              type="text"
              :placeholder="setting.label"
            />
            <label v-else-if="setting.type === 'bool'" class="checkbox-label">
              <input v-model="apiSettings[setting.key]" type="checkbox" />
              {{ setting.label }}
            </label>
          </div>
        </template>

        <div class="button-group">
          <button class="primary-btn" @click="saveConfig"><i class="fas fa-save"></i> 保存</button>
          <button class="action-btn" @click="testApi"><i class="fas fa-flask"></i> 测试API</button>
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
.settings-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 20px; }
.setting-card { background: var(--bg-secondary); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color); }
.setting-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 14px; color: var(--text-secondary); margin-bottom: 6px; }
.form-group input[type="text"], .form-group select {
  width: 100%; padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border-color);
  background: var(--bg-primary); color: var(--text-primary); font-size: 14px;
}
.button-group { display: flex; gap: 8px; margin-top: 16px; }
.primary-btn {
  padding: 10px 24px; border-radius: 8px; border: none; background: var(--accent-color); color: white; cursor: pointer; font-size: 14px;
}
.action-btn {
  padding: 10px 24px; border-radius: 8px; border: 1px solid var(--border-color);
  background: var(--bg-primary); color: var(--text-primary); cursor: pointer; font-size: 14px;
}
.checkbox-label { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 14px; }
</style>
