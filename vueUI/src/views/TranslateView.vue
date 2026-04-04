<template>
  <div class="translate-view">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-language"></i> 翻译工具
      </h2>
      <p class="section-subtitle">使用多种翻译服务自动翻译游戏文本</p>
    </div>

    <div class="settings-grid">
      <SettingCard title="翻译选项">
        <Checkbox v-model="enableProper">启用专有名词 (LLM翻译专用)</Checkbox>
        
        <div v-if="enableProper" class="nested-options">
          <Checkbox v-model="autoFetchProper">在进行翻译时自动抓取专有词汇 (无法使用自定义设置)</Checkbox>
          <div v-if="!autoFetchProper" class="form-group">
            <label>专有名词json路径</label>
            <FileInput v-model="properPath" type="file" />
          </div>
        </div>

        <Checkbox v-model="enableRole">启用人物角色标识 (LLM翻译专用)</Checkbox>
        <Checkbox v-model="enableSkill">启用状态效果标识 (LLM翻译专用)</Checkbox>
        <Checkbox v-model="enableDevSettings">启用高级选项</Checkbox>

        <div v-if="enableDevSettings" class="nested-options">
          <FileInput v-model="krPath" label="韩文文本路径" type="folder" />
          <FileInput v-model="jpPath" label="日文文本路径" type="folder" />
          <FileInput v-model="enPath" label="英文文本路径" type="folder" />
          <FileInput v-model="llcPath" label="中文文本路径" type="folder" />
          <Checkbox v-model="hasPrefix">文件名存在前缀</Checkbox>
        </div>

        <Checkbox v-model="dumpTranslation">转储过程内容以供分析</Checkbox>
      </SettingCard>

      <SettingCard title="翻译服务配置">
        <div class="form-group">
          <label>翻译服务</label>
          <div class="select-wrapper">
            <select v-model="translatorService">
              <option v-for="name in translatorServices" :key="name">{{ name }}</option>
            </select>
            <i class="fas fa-chevron-down"></i>
          </div>
        </div>

        <Checkbox v-model="fallback">失败时进行相反重试 (LLM翻译专用)</Checkbox>
        <Checkbox v-model="isText">使用文本格式进行请求 (LLM翻译专用)</Checkbox>

        <div class="form-group">
          <label>使用源语言 (除LLM翻译外使用)</label>
          <div class="select-wrapper">
            <select v-model="fromLang">
              <option value="EN">英文</option>
              <option value="JP">日文</option>
              <option value="KR">韩文</option>
            </select>
            <i class="fas fa-chevron-down"></i>
          </div>
        </div>
      </SettingCard>
    </div>

    <div class="action-area">
      <Button @click="startTranslation" :loading="translating">
        <i class="fas fa-play"></i> 开始翻译
      </Button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useConfigStore } from '@/stores/config'
import { useModalStore } from '@/stores/modal'
import { api } from '@/utils/api'
import SettingCard from '@/components/common/SettingCard.vue'
import Checkbox from '@/components/common/Checkbox.vue'
import FileInput from '@/components/common/FileInput.vue'
import Button from '@/components/common/Button.vue'

const configStore = useConfigStore()
const modalStore = useModalStore()

// 配置绑定
const enableProper = ref(false)
const autoFetchProper = ref(false)
const properPath = ref('')
const enableRole = ref(false)
const enableSkill = ref(false)
const enableDevSettings = ref(false)
const krPath = ref('')
const jpPath = ref('')
const enPath = ref('')
const llcPath = ref('')
const hasPrefix = ref(true)
const dumpTranslation = ref(false)
const translatorService = ref('')
const fallback = ref(true)
const isText = ref(false)
const fromLang = ref('EN')

const translatorServices = ref([])
const translating = ref(false)

// 加载配置
async function loadConfig() {
  enableProper.value = configStore.getById('enable-proper') || false
  autoFetchProper.value = configStore.getById('auto-fetch-proper') || false
  properPath.value = configStore.getById('proper-path') || ''
  enableRole.value = configStore.getById('enable-role') || false
  enableSkill.value = configStore.getById('enable-skill') || false
  enableDevSettings.value = configStore.getById('enable-dev-settings') || false
  krPath.value = configStore.getById('kr-path') || ''
  jpPath.value = configStore.getById('jp-path') || ''
  enPath.value = configStore.getById('en-path') || ''
  llcPath.value = configStore.getById('llc-path') || ''
  hasPrefix.value = configStore.getById('has-prefix') !== false
  dumpTranslation.value = configStore.getById('dump-translation') || false
  translatorService.value = configStore.getById('translator-service-select') || ''
  fallback.value = configStore.getById('fallback') !== false
  isText.value = configStore.getById('is-text') || false
  fromLang.value = configStore.getById('from-lang') || 'EN'
}

// 保存配置（防抖）
let saveTimer = null
function saveConfig(id, value) {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    configStore.updateConfig(id, value)
    configStore.flushUpdates()
  }, 300)
}

// 监听配置变化
watch(enableProper, (val) => saveConfig('enable-proper', val))
watch(autoFetchProper, (val) => saveConfig('auto-fetch-proper', val))
watch(properPath, (val) => saveConfig('proper-path', val))
watch(enableRole, (val) => saveConfig('enable-role', val))
watch(enableSkill, (val) => saveConfig('enable-skill', val))
watch(enableDevSettings, (val) => saveConfig('enable-dev-settings', val))
watch(krPath, (val) => saveConfig('kr-path', val))
watch(jpPath, (val) => saveConfig('jp-path', val))
watch(enPath, (val) => saveConfig('en-path', val))
watch(llcPath, (val) => saveConfig('llc-path', val))
watch(hasPrefix, (val) => saveConfig('has-prefix', val))
watch(dumpTranslation, (val) => saveConfig('dump-translation', val))
watch(translatorService, (val) => saveConfig('translator-service-select', val))
watch(fallback, (val) => saveConfig('fallback', val))
watch(isText, (val) => saveConfig('is-text', val))
watch(fromLang, (val) => saveConfig('from-lang', val))

// 加载翻译服务列表
async function loadTranslatorServices() {
  try {
    const tkitMachine = await api.call('get_attr', 'TKIT_MACHINE_OBJECT')
    translatorServices.value = Object.keys(tkitMachine)
    if (!translatorService.value && translatorServices.value.length) {
      translatorService.value = translatorServices.value[0]
    }
  } catch (error) {
    console.error('加载翻译服务失败:', error)
  }
}

// 开始翻译
async function startTranslation() {
  translating.value = true
  // 先保存当前配置
  await configStore.flushUpdates()
  
  const apiConfig = await configStore.getApiConfig()
  const modalId = modalStore.openModal('progress', {
    title: '开始翻译',
    statusText: '正在初始化翻译过程...'
  })
  
  try {
    const result = await api.call('start_translation', apiConfig, modalId)
    if (result.success) {
      modalStore.completeModal(modalId, true, '翻译任务已完成')
    } else {
      modalStore.completeModal(modalId, false, '翻译失败: ' + result.message)
    }
  } catch (error) {
    modalStore.completeModal(modalId, false, '翻译过程中发生错误: ' + error.message)
  } finally {
    translating.value = false
  }
}

onMounted(() => {
  loadConfig()
  loadTranslatorServices()
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
  margin-bottom: var(--spacing-sm);
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
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-xl);
}
.nested-options {
  margin-left: 28px;
  margin-top: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
  padding-left: var(--spacing-md);
  border-left: 2px solid var(--color-border-light);
}
.action-area {
  margin-top: var(--spacing-lg);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border);
}
</style>