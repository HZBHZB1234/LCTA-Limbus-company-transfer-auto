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
const servicesLoadError = ref(false)
const translatorLoadError = ref(false)

onMounted(async () => {
  try {
    const tkitMachine = await getApi().get_attr('TKIT_MACHINE_OBJECT') as Record<string, unknown>
    apiServices.value = tkitMachine as Record<string, { name: string; api_settings: Array<{ key: string; type: string; label: string }> }>
    const keys = Object.keys(apiServices.value)
    if (keys.length > 0) {
      selectedService.value = keys[0]
      onServiceChange()
    }
  } catch (e) {
    console.error('API services load failed:', e)
    getApi().log(`[ApiConfig] API服务列表加载失败: ${e}`).catch(() => {})
    servicesLoadError.value = true
  }

  try {
    const llmTranslator = await getApi().get_attr('LLM_TRANSLATOR') as Record<string, { name: string }>
    translatorServices.value = llmTranslator
    selectedTranslator.value = (configStore.get('ui_default.translator.translator') as string) || Object.keys(llmTranslator)[0] || ''
  } catch (e) {
    console.error('Translator services load failed:', e)
    getApi().log(`[ApiConfig] 翻译器列表加载失败: ${e}`).catch(() => {})
    translatorLoadError.value = true
  }
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
        <p v-if="translatorLoadError" style="color: var(--color-danger); font-size: 13px; display: flex; align-items: center; gap: 6px;">
          <i class="fas fa-exclamation-triangle"></i> 翻译器列表加载失败，请检查程序是否正常启动
        </p>
        <div class="form-group" v-if="Object.keys(translatorServices).length > 0">
          <label>翻译器:</label>
          <select v-model="selectedTranslator">
            <option v-for="(svc, key) in translatorServices" :key="key" :value="key">{{ svc.name }}</option>
          </select>
        </div>
      </div>

      <div class="setting-card" v-if="Object.keys(apiServices).length > 0">
        <h3 class="setting-title">API服务配置</h3>
        <p v-if="servicesLoadError" style="color: var(--color-warning); font-size: 13px; display: flex; align-items: center; gap: 6px;">
          <i class="fas fa-exclamation-triangle"></i> API服务列表加载失败，请检查程序配置
        </p>
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
/* ApiConfig view uses shared global classes from main.css */
</style>
