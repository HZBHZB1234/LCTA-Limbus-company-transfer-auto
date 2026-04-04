<template>
  <div class="settings-view">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-sliders-h"></i> 设置
      </h2>
      <p class="section-subtitle">程序配置与选项</p>
    </div>

    <div class="settings-grid">
      <SettingCard title="程序设置">
        <div class="form-group">
          <label>游戏路径</label>
          <FileInput v-model="gamePath" type="folder" placeholder="选择游戏安装路径" />
        </div>

        <Checkbox v-model="debugMode">启用调试模式</Checkbox>
        <Checkbox v-model="autoCheckUpdate">启动时自动检查更新</Checkbox>
        <Checkbox v-model="deleteUpdating">更新时删除废弃的包</Checkbox>
        <Checkbox v-model="updateUseProxy">更新通过镜像加速</Checkbox>
        <Checkbox v-model="updateOnlyStable">仅更新稳定版本</Checkbox>
        <Checkbox v-model="apiCrypto">加密api配置</Checkbox>
        <small class="form-hint">修改后请在api配置界面进行保存后关闭</small>

        <div class="form-group">
          <label>Github代理重试线程数</label>
          <input type="number" v-model="githubMaxWorkers" placeholder="例如：100">
        </div>

        <div class="form-group">
          <label>Github代理超时秒数</label>
          <input type="number" v-model="githubTimeout" placeholder="例如：100">
        </div>

        <Checkbox v-model="enableCache">启用资源缓存</Checkbox>
        <div v-if="enableCache" class="nested">
          <FileInput v-model="cachePath" type="folder" placeholder="tmp" />
        </div>

        <Checkbox v-model="enableStorage">启用数据持久化</Checkbox>
        <div v-if="enableStorage" class="nested">
          <FileInput v-model="storagePath" type="folder" placeholder="tmp" />
        </div>

        <div class="action-area">
          <Button @click="saveSettings" :loading="saving">保存设置</Button>
        </div>
      </SettingCard>

      <SettingCard title="配置操作">
        <div class="action-grid">
          <Button variant="secondary" @click="useDefaultConfig">使用默认配置</Button>
          <Button variant="danger" @click="resetConfig">重置配置</Button>
          <Button variant="secondary" @click="manualCheckUpdates">检查更新</Button>
          <Button variant="secondary" @click="doUpdate">强制进行更新</Button>
          <Button variant="secondary" @click="goTestSection">进入调试页面</Button>
          <Button variant="secondary" @click="goCleanSection">进入已废弃的缓存清理页面</Button>
        </div>
      </SettingCard>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useConfigStore } from '@/stores/config'
import { useModalStore } from '@/stores/modal'
import { api } from '@/utils/api'
import SettingCard from '@/components/common/SettingCard.vue'
import Button from '@/components/common/Button.vue'
import Checkbox from '@/components/common/Checkbox.vue'
import FileInput from '@/components/common/FileInput.vue'

const router = useRouter()
const configStore = useConfigStore()
const modalStore = useModalStore()

const gamePath = ref('')
const debugMode = ref(false)
const autoCheckUpdate = ref(true)
const deleteUpdating = ref(false)
const updateUseProxy = ref(true)
const updateOnlyStable = ref(true)
const apiCrypto = ref(true)
const githubMaxWorkers = ref('')
const githubTimeout = ref('')
const enableCache = ref(false)
const cachePath = ref('tmp')
const enableStorage = ref(false)
const storagePath = ref('tmp')
const saving = ref(false)

function loadConfig() {
  gamePath.value = configStore.getById('game-path') || ''
  debugMode.value = configStore.getById('debug-mode') || false
  autoCheckUpdate.value = configStore.getById('auto-check-update') !== false
  deleteUpdating.value = configStore.getById('delete-updating') || false
  updateUseProxy.value = configStore.getById('update-use-proxy') !== false
  updateOnlyStable.value = configStore.getById('update-only-stable') !== false
  apiCrypto.value = configStore.getById('api-crypto') !== false
  githubMaxWorkers.value = configStore.getById('github-max-workers') || ''
  githubTimeout.value = configStore.getById('github-timeout') || ''
  enableCache.value = configStore.getById('enable-cache') || false
  cachePath.value = configStore.getById('cache-path') || 'tmp'
  enableStorage.value = configStore.getById('enable-storage') || false
  storagePath.value = configStore.getById('storage-path') || 'tmp'
}

let saveTimer = null
function saveConfig(id, value) {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    configStore.updateConfig(id, value)
    configStore.flushUpdates()
  }, 300)
}

watch(gamePath, (v) => saveConfig('game-path', v))
watch(debugMode, (v) => saveConfig('debug-mode', v))
watch(autoCheckUpdate, (v) => saveConfig('auto-check-update', v))
watch(deleteUpdating, (v) => saveConfig('delete-updating', v))
watch(updateUseProxy, (v) => saveConfig('update-use-proxy', v))
watch(updateOnlyStable, (v) => saveConfig('update-only-stable', v))
watch(apiCrypto, (v) => saveConfig('api-crypto', v))
watch(githubMaxWorkers, (v) => saveConfig('github-max-workers', v))
watch(githubTimeout, (v) => saveConfig('github-timeout', v))
watch(enableCache, (v) => saveConfig('enable-cache', v))
watch(cachePath, (v) => saveConfig('cache-path', v))
watch(enableStorage, (v) => saveConfig('enable-storage', v))
watch(storagePath, (v) => saveConfig('storage-path', v))

async function saveSettings() {
  saving.value = true
  await configStore.flushUpdates()
  await api.call('save_config_to_file')
  modalStore.openModal('message', { title: '成功', content: '设置已保存' })
  saving.value = false
}

async function useDefaultConfig() {
  const result = await api.call('use_default_config')
  if (result.success) {
    await configStore.loadConfig()
    loadConfig()
    modalStore.openModal('message', { title: '成功', content: '已使用默认配置' })
  } else {
    modalStore.openModal('message', { title: '错误', content: result.message })
  }
}

function resetConfig() {
  modalStore.openModal('confirm', {
    title: '确认重置',
    content: '确定要重置所有配置吗？这将删除当前配置并恢复为默认设置。',
    onConfirm: async () => {
      const result = await api.call('reset_config')
      if (result.success) {
        await configStore.loadConfig()
        loadConfig()
        modalStore.openModal('message', { title: '成功', content: '配置已重置' })
      } else {
        modalStore.openModal('message', { title: '错误', content: result.message })
      }
    }
  })
}

async function manualCheckUpdates() {
  const modalId = modalStore.openModal('progress', { title: '检查更新' })
  try {
    const result = await api.call('manual_check_update')
    if (result.has_update) {
      modalStore.completeModal(modalId, true, `发现新版本 ${result.latest_version}`)
      setTimeout(() => {
        modalStore.closeModal(modalId)
        showUpdateInfo(result)
      }, 2000)
    } else {
      modalStore.completeModal(modalId, true, '当前已是最新版本')
      setTimeout(() => modalStore.closeModal(modalId), 2000)
    }
  } catch (error) {
    modalStore.completeModal(modalId, false, error.message)
  }
}

function showUpdateInfo(updateInfo) {
  modalStore.openModal('confirm', {
    title: '发现新版本',
    content: `
      <p><strong>发现新版本:</strong> ${updateInfo.latest_version}</p>
      <p><strong>当前版本:</strong> v4.1.5</p>
      ${updateInfo.body ? `<div class="markdown-body">${updateInfo.body}</div>` : ''}
    `,
    onConfirm: () => doUpdate()
  })
}

async function doUpdate() {
  const modalId = modalStore.openModal('progress', { title: '更新程序' })
  try {
    const result = await api.call('perform_update_in_modal', modalId)
    if (result) {
      modalStore.completeModal(modalId, true, '更新完成，程序即将重启')
    } else {
      modalStore.completeModal(modalId, false, '更新失败')
    }
  } catch (error) {
    modalStore.completeModal(modalId, false, error.message)
  }
}

function goTestSection() {
  router.push('/test')
}

function goCleanSection() {
  router.push('/clean')
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
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: var(--spacing-lg);
}
.nested {
  margin-left: 28px;
  margin-top: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}
.action-grid {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}
.action-area {
  margin-top: var(--spacing-lg);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border);
}
.form-hint {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>