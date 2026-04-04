<template>
  <div class="clean-view">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-broom"></i> 清除本地缓存
      </h2>
      <p class="section-subtitle">清理缓存文件，通过初始化解决一些问题</p>
    </div>

    <div class="settings-grid">
      <SettingCard title="清理选项">
        <Checkbox v-model="cleanProgress">清理进度文件</Checkbox>
        <small class="form-hint">清除游戏进度文件，包括存档数据</small>

        <Checkbox v-model="cleanNotice">清理通知文件</Checkbox>
        <small class="form-hint">清除游戏通知数据</small>

        <Checkbox v-model="cleanMods">清理默认mod资源</Checkbox>
        <small class="form-hint">清除默认mod目录对应资源</small>

        <div class="form-group">
          <label>自定义清理文件/文件夹</label>
          <div class="file-input-group">
            <input type="text" v-model="customFilePath" placeholder="输入或浏览选择要清理的文件或文件夹">
            <Button variant="secondary" size="small" @click="browseCustomFile">文件</Button>
            <Button variant="secondary" size="small" @click="browseCustomFolder">文件夹</Button>
          </div>
          <Button variant="secondary" size="small" @click="addCustomFile" class="mt-2">
            <i class="fas fa-plus"></i> 添加到清理列表
          </Button>
        </div>

        <div class="form-group">
          <div class="file-list-header">
            <label>清理列表</label>
            <Button variant="danger" size="small" @click="clearCustomFiles">清空列表</Button>
          </div>
          <div class="file-list-container">
            <div v-if="customFiles.length === 0" class="list-empty">暂无自定义清理项</div>
            <div v-for="(file, idx) in customFiles" :key="idx" class="file-item">
              <div class="file-info">
                <i class="fas fa-file"></i>
                <span class="file-path">{{ file }}</span>
              </div>
              <Button variant="danger" size="small" @click="removeCustomFile(idx)">
                <i class="fas fa-times"></i>
              </Button>
            </div>
          </div>
        </div>
      </SettingCard>

      <SettingCard title="警告" warning>
        <div class="warning-header">
          <i class="fas fa-exclamation-triangle"></i>
          <h3>警告</h3>
        </div>
        <p>此操作将清除本地的游戏进度和通知文件，以及您指定的自定义文件。这些操作不可逆，请谨慎操作。</p>
        <div class="action-area">
          <Button variant="danger" @click="cleanCache" :loading="cleaning">
            <i class="fas fa-trash-alt"></i> 清除缓存
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

const cleanProgress = ref(true)
const cleanNotice = ref(true)
const cleanMods = ref(true)
const customFilePath = ref('')
const customFiles = ref([])
const cleaning = ref(false)

// 加载配置
function loadConfig() {
  cleanProgress.value = configStore.getById('clean-progress') !== false
  cleanNotice.value = configStore.getById('clean-notice') !== false
  cleanMods.value = configStore.getById('clean-mods') !== false
  const saved = configStore.get('custom_files')
  if (Array.isArray(saved)) customFiles.value = saved
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

watch(cleanProgress, (v) => saveConfig('clean-progress', v))
watch(cleanNotice, (v) => saveConfig('clean-notice', v))
watch(cleanMods, (v) => saveConfig('clean-mods', v))

// 自定义文件操作
async function browseCustomFile() {
  const path = await api.browse_file('custom-file-path')
  if (path) customFilePath.value = path
}

async function browseCustomFolder() {
  const path = await api.browse_folder('custom-file-path')
  if (path) customFilePath.value = path
}

function addCustomFile() {
  if (!customFilePath.value.trim()) {
    modalStore.openModal('message', { title: '提示', content: '请先输入或选择文件路径' })
    return
  }
  if (!customFiles.value.includes(customFilePath.value)) {
    customFiles.value.push(customFilePath.value)
    customFilePath.value = ''
    saveCustomFiles()
  } else {
    modalStore.openModal('message', { title: '提示', content: '该路径已存在列表中' })
  }
}

function removeCustomFile(index) {
  customFiles.value.splice(index, 1)
  saveCustomFiles()
}

function clearCustomFiles() {
  customFiles.value = []
  saveCustomFiles()
}

function saveCustomFiles() {
  configStore.updateConfig('custom-files', customFiles.value)
  configStore.flushUpdates()
}

// 清除缓存
async function cleanCache() {
  modalStore.openModal('confirm', {
    title: '确认清除',
    content: '确定要清除所选缓存吗？此操作不可逆。',
    onConfirm: async () => {
      cleaning.value = true
      await configStore.flushUpdates()
      const modalId = modalStore.openModal('progress', { title: '清除缓存' })
      try {
        const result = await api.call('clean_cache', modalId, customFiles.value, cleanProgress.value, cleanNotice.value, cleanMods.value)
        if (result.success) {
          modalStore.completeModal(modalId, true, '缓存清除成功')
        } else {
          modalStore.completeModal(modalId, false, result.message || '清除失败')
        }
      } catch (error) {
        modalStore.completeModal(modalId, false, error.message)
      } finally {
        cleaning.value = false
      }
    }
  })
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
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: var(--spacing-lg);
}
.warning-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  color: var(--color-warning);
  margin-bottom: var(--spacing-md);
}
.form-hint {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.file-input-group {
  display: flex;
  gap: var(--spacing-sm);
}
.file-input-group input {
  flex: 1;
}
.file-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-sm);
}
.file-list-container {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-input);
  max-height: 200px;
  overflow-y: auto;
}
.file-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-border-light);
}
.file-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex: 1;
  overflow: hidden;
}
.file-path {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mt-2 {
  margin-top: 8px;
}
</style>