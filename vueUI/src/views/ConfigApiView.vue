<template>
  <div class="config-api-view">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-cog"></i> 配置汉化API
      </h2>
      <p class="section-subtitle">配置翻译服务API密钥</p>
    </div>

    <div class="settings-grid">
      <SettingCard title="API配置">
        <div class="form-group">
          <label>选择翻译服务</label>
          <div class="select-wrapper">
            <select v-model="selectedService" @change="onServiceChange">
              <option v-for="name in serviceNames" :key="name">{{ name }}</option>
            </select>
            <i class="fas fa-chevron-down"></i>
          </div>
        </div>

        <div v-if="currentService" class="api-settings-form">
          <h4>API参数配置</h4>
          <div v-for="field in currentService.apiSetting" :key="field.id" class="api-setting-field">
            <label v-if="field.type !== 'boolean'">
              {{ field.name }}
              <span v-if="field.required" class="required">*</span>
            </label>
            <Checkbox v-if="field.type === 'boolean'" v-model="formData[field.id]">
              {{ field.name }}
            </Checkbox>
            <input v-else-if="field.type === 'password'" type="password" v-model="formData[field.id]" :placeholder="field.description">
            <input v-else type="text" v-model="formData[field.id]" :placeholder="field.description">
            <small v-if="field.description && field.type !== 'boolean'" class="form-hint">{{ field.description }}</small>
          </div>

          <div v-if="selectedService === 'LLM通用翻译服务'" class="llm-selector">
            <div class="form-group">
              <label>选择LLM服务</label>
              <div class="select-wrapper">
                <select v-model="selectedLLM" @change="onLLMChange">
                  <option value="">选择以使用预设LLM服务地址...</option>
                  <option v-for="name in llmServiceNames" :key="name">{{ name }}</option>
                </select>
                <i class="fas fa-chevron-down"></i>
              </div>
              <small class="form-hint">选择预设的LLM服务，将自动填充基础地址和模型名称参数</small>
            </div>
          </div>
        </div>

        <div class="action-area">
          <Button @click="saveSettings" :loading="saving">保存配置</Button>
          <Button variant="secondary" @click="testApi" :loading="testing">测试API</Button>
        </div>
      </SettingCard>

      <SettingCard title="服务状态">
        <div v-if="currentService" class="api-status-card">
          <h4>{{ selectedService }}</h4>
          <p class="api-description">{{ currentService.metadata?.description }}</p>
          <p class="api-usage" v-if="currentService.metadata?.usage_documentation">{{ currentService.metadata.usage_documentation }}</p>
          <p class="api-short-desc" v-if="currentService.metadata?.short_description">{{ currentService.metadata.short_description }}</p>
          <div class="api-links">
            <a v-if="currentService.metadata?.console_url" :href="currentService.metadata.console_url" target="_blank" class="api-link">控制台</a>
            <a v-if="currentService.metadata?.documentation_url" :href="currentService.metadata.documentation_url" target="_blank" class="api-link">文档</a>
          </div>
          <div v-if="currentService.langCode" class="api-lang-codes">
            <h5>支持的语言代码:</h5>
            <div class="lang-list">
              <span v-for="(code, lang) in currentService.langCode" :key="lang" class="lang-item">{{ lang }} → {{ code }}</span>
            </div>
          </div>
        </div>
        <div v-else class="no-settings">请选择一个服务</div>
      </SettingCard>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useConfigStore } from '@/stores/config'
import { useModalStore } from '@/stores/modal'
import { api } from '@/utils/api'
import SettingCard from '@/components/common/SettingCard.vue'
import Button from '@/components/common/Button.vue'
import Checkbox from '@/components/common/Checkbox.vue'

const configStore = useConfigStore()
const modalStore = useModalStore()

const serviceNames = ref([])
const llmServiceNames = ref([])
const selectedService = ref('')
const selectedLLM = ref('')
const currentService = ref(null)
const formData = ref({})
const saving = ref(false)
const testing = ref(false)

// 原始数据
let tkitMachine = {}
let llmTranslator = {}

async function loadApiServices() {
  try {
    tkitMachine = await api.call('get_attr', 'TKIT_MACHINE_OBJECT')
    llmTranslator = await api.call('get_attr', 'LLM_TRANSLATOR')
    serviceNames.value = Object.keys(tkitMachine)
    llmServiceNames.value = Object.keys(llmTranslator)

    const savedService = configStore.getById('api-select')
    if (savedService && serviceNames.value.includes(savedService)) {
      selectedService.value = savedService
    } else if (serviceNames.value.length) {
      selectedService.value = serviceNames.value[0]
    }
    await loadServiceSettings()
  } catch (error) {
    console.error('加载API服务失败:', error)
  }
}

async function loadServiceSettings() {
  if (!selectedService.value) return
  currentService.value = tkitMachine[selectedService.value]
  const savedConfigs = await configStore.getApiConfig()
  formData.value = savedConfigs[selectedService.value] || {}
}

function onServiceChange() {
  loadServiceSettings()
  configStore.updateConfig('api-select', selectedService.value)
  configStore.flushUpdates()
}

function onLLMChange() {
  const service = llmTranslator[selectedLLM.value]
  if (service) {
    formData.value.base_url = service.base_url || ''
    formData.value.model_name = service.model || ''
  }
}

async function saveSettings() {
  saving.value = true
  await configStore.saveApiConfig(selectedService.value, formData.value)
  modalStore.openModal('message', { title: '成功', content: 'API配置已保存' })
  saving.value = false
}

async function testApi() {
  testing.value = true
  const modalId = modalStore.openModal('progress', { title: '测试API配置' })
  try {
    const result = await api.call('test_api', selectedService.value, formData.value)
    if (result.success) {
      const res = result.message
      modalStore.addLog(modalId, 'API配置测试成功！')
      modalStore.addLog(modalId, `韩文：안녕 -> ${res.kr}`)
      modalStore.addLog(modalId, `英文：hello -> ${res.en}`)
      modalStore.addLog(modalId, `日文：こんにちは -> ${res.jp}`)
      modalStore.completeModal(modalId, true, '测试成功')
    } else {
      modalStore.completeModal(modalId, false, result.message)
    }
  } catch (error) {
    modalStore.completeModal(modalId, false, error.message)
  } finally {
    testing.value = false
  }
}

onMounted(() => {
  loadApiServices()
})
</script>

<style scoped>
.section-header {
  margin-bottom: var(--spacing-xl);
  padding-bottom: var(--spacing-md);
  border-bottom: 2px solid var(--color-border-light);
}
.section-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}
.section-subtitle {
  color: var(--color-text-secondary);
  font-size: 16px;
}
.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: var(--spacing-lg);
}
.api-settings-form {
  margin-top: var(--spacing-lg);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border);
}
.api-setting-field {
  margin-bottom: var(--spacing-md);
}
.required {
  color: var(--color-danger);
}
.form-hint {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.api-status-card {
  background: var(--color-bg-input);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
}
.api-status-card h4 {
  color: var(--color-primary);
  margin-bottom: var(--spacing-sm);
}
.api-description, .api-usage, .api-short-desc {
  font-size: 14px;
  margin-bottom: var(--spacing-sm);
}
.api-links {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}
.api-link {
  color: var(--color-primary);
  text-decoration: none;
  font-size: 13px;
}
.api-link:hover {
  text-decoration: underline;
}
.lang-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-xs);
}
.lang-item {
  background: var(--color-bg-card);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  border: 1px solid var(--color-border);
}
.no-settings {
  text-align: center;
  padding: var(--spacing-xl);
  color: var(--color-text-secondary);
}
.action-area {
  margin-top: var(--spacing-lg);
  display: flex;
  gap: var(--spacing-sm);
}
</style>