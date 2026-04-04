<template>
  <div class="proper-view">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-book"></i> 抓取专有词汇
      </h2>
      <p class="section-subtitle">从文本中提取专有名词和术语</p>
    </div>

    <div class="settings-grid">
      <SettingCard title="抓取配置">
        <div class="form-group">
          <label>输出格式</label>
          <div class="select-wrapper">
            <select v-model="outputFormat">
              <option value="json">JSON格式</option>
              <option value="single">单文件格式</option>
              <option value="double">双文件格式</option>
            </select>
            <i class="fas fa-chevron-down"></i>
          </div>
        </div>

        <Checkbox v-model="skipSpace">跳过含空格的词汇</Checkbox>

        <div class="form-group">
          <label>最大词汇数量</label>
          <input type="number" v-model="maxCount" placeholder="留空表示无限制">
          <small class="form-hint">留空表示无限制</small>
        </div>

        <div class="form-group">
          <label>最短专有名词数长度，减少错误匹配</label>
          <input type="number" v-model="minCount" placeholder="例如：2">
          <small class="form-hint">留空表示无限制</small>
        </div>

        <div v-if="outputFormat === 'single'" class="form-group">
          <label>分隔符(仅在单文本格式输出有效)</label>
          <input type="text" v-model="joinChar" placeholder="例如：,">
          <small class="form-hint">指定单词之间的分隔符，留空则使用逗号</small>
        </div>

        <div class="action-area">
          <Button @click="fetchProper" :loading="fetching">
            <i class="fas fa-search"></i> 抓取专有词汇
          </Button>
        </div>
      </SettingCard>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useConfigStore } from '@/stores/config'
import { useModalStore } from '@/stores/modal'
import { api } from '@/utils/api'
import SettingCard from '@/components/common/SettingCard.vue'
import Button from '@/components/common/Button.vue'
import Checkbox from '@/components/common/Checkbox.vue'

const configStore = useConfigStore()
const modalStore = useModalStore()

const outputFormat = ref('json')
const skipSpace = ref(false)
const maxCount = ref('')
const minCount = ref('')
const joinChar = ref('')
const fetching = ref(false)

function loadConfig() {
  outputFormat.value = configStore.getById('proper-output') || 'json'
  skipSpace.value = configStore.getById('proper-skip-space') || false
  maxCount.value = configStore.getById('proper-max-count') || ''
  minCount.value = configStore.getById('proper-min-count') || ''
  joinChar.value = configStore.getById('proper-join-char') || ''
}

let saveTimer = null
function saveConfig(id, value) {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    configStore.updateConfig(id, value)
    configStore.flushUpdates()
  }, 300)
}

watch(outputFormat, (v) => saveConfig('proper-output', v))
watch(skipSpace, (v) => saveConfig('proper-skip-space', v))
watch(maxCount, (v) => saveConfig('proper-max-count', v))
watch(minCount, (v) => saveConfig('proper-min-count', v))
watch(joinChar, (v) => saveConfig('proper-join-char', v))

async function fetchProper() {
  fetching.value = true
  await configStore.flushUpdates()

  const modalId = modalStore.openModal('progress', { title: '抓取专有词汇' })
  modalStore.addLog(modalId, `输出格式: ${outputFormat.value}`)
  modalStore.addLog(modalId, `跳过含空格词汇: ${skipSpace.value ? '是' : '否'}`)
  if (minCount.value) modalStore.addLog(modalId, `最短长度: ${minCount.value}`)
  if (maxCount.value) modalStore.addLog(modalId, `最大词汇数量: ${maxCount.value}`)
  if (outputFormat.value === 'single' && joinChar.value) {
    modalStore.addLog(modalId, `分隔符: ${joinChar.value}`)
  }

  try {
    const result = await api.call('fetch_proper_nouns', modalId)
    if (result.success) {
      modalStore.completeModal(modalId, true, '专有词汇抓取成功')
    } else {
      modalStore.completeModal(modalId, false, result.message || '抓取失败')
    }
  } catch (error) {
    modalStore.completeModal(modalId, false, error.message)
  } finally {
    fetching.value = false
  }
}

onMounted(() => {
  loadConfig()
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
  max-width: 600px;
}
.action-area {
  margin-top: var(--spacing-lg);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border);
}
</style>