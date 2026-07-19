<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getApi } from '@/utils/api'
import { useConfigStore } from '@/stores/config'
import { useUpdateStore } from '@/stores/update'
import { useModalStore } from '@/stores/modal'
import { listenEvent } from '@/utils/events'

const router = useRouter()
const configStore = useConfigStore()
const updateStore = useUpdateStore()
const modalStore = useModalStore()

const gamePath = ref('')
const debugMode = ref(false)
const autoCheckUpdate = ref(true)
const deleteUpdating = ref(false)
const updateUseProxy = ref(true)
const updateOnlyStable = ref(true)
const apiCrypto = ref(true)
const githubMaxWorkers = ref(100)
const githubTimeout = ref(100)
const enableCache = ref(false)
const cachePath = ref('tmp')
const enableStorage = ref(false)
const storagePath = ref('tmp')

const showCachePath = ref(false)
const showStoragePath = ref(false)

listenEvent('lcta:file-picked', (detail) => {
  if (detail.inputId === 'cache-path') cachePath.value = detail.path
  if (detail.inputId === 'storage-path') storagePath.value = detail.path
  if (detail.inputId === 'game-path') gamePath.value = detail.path
  if (detail.inputId === 'update-file') {
    const mid = modalStore.create('progress', { title: '从本地更新包更新' })
    getApi().perform_update_from_file(detail.path, mid)
  }
})

onMounted(() => {
  gamePath.value = configStore.get<string>('game_path') || ''
  debugMode.value = configStore.get<boolean>('debug') || false
  autoCheckUpdate.value = configStore.get<boolean>('auto_check_update') !== false
  deleteUpdating.value = configStore.get<boolean>('delete-updating') || false
  updateUseProxy.value = configStore.get<boolean>('update-use-proxy') !== false
  updateOnlyStable.value = configStore.get<boolean>('update-only-stable') !== false
  apiCrypto.value = configStore.get<boolean>('api_crypto') !== false
  githubMaxWorkers.value = configStore.get<number>('github_max_workers') || 100
  githubTimeout.value = configStore.get<number>('github_timeout') || 100
  enableCache.value = configStore.get<boolean>('enable_cache') || false
  cachePath.value = configStore.get<string>('cache_path') || 'tmp'
  enableStorage.value = configStore.get<boolean>('enable_storage') || false
  storagePath.value = configStore.get<string>('storage_path') || 'tmp'
  showCachePath.value = enableCache.value
  showStoragePath.value = enableStorage.value
})

watch(enableCache, (v) => { showCachePath.value = v })
watch(enableStorage, (v) => { showStoragePath.value = v })

async function saveSettings() {
  configStore.set('game_path', gamePath.value)
  configStore.set('debug', debugMode.value)
  configStore.set('auto_check_update', autoCheckUpdate.value)
  configStore.set('delete-updating', deleteUpdating.value)
  configStore.set('update-use-proxy', updateUseProxy.value)
  configStore.set('update-only-stable', updateOnlyStable.value)
  configStore.set('api_crypto', apiCrypto.value)
  configStore.set('github_max_workers', githubMaxWorkers.value)
  configStore.set('github_timeout', githubTimeout.value)
  configStore.set('enable_cache', enableCache.value)
  configStore.set('cache_path', cachePath.value)
  configStore.set('enable_storage', enableStorage.value)
  configStore.set('storage_path', storagePath.value)
  await configStore.save()
}

async function useDefaultConfig() {
  await getApi().use_default_config()
  await configStore.reload()
}

async function resetConfig() {
  await getApi().reset_config()
  await configStore.reload()
}

async function browseFolder(inputId: string) {
  await getApi().browse_folder(inputId)
}

async function manualUpdateFromLocal() {
  await getApi().browse_file('update-file')
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-sliders-h"></i> 设置</h2>
      <p class="section-subtitle">程序配置与选项</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card">
        <h3 class="setting-title">程序设置</h3>

        <div class="form-group">
          <label>游戏路径:</label>
          <div class="file-input-group">
            <input v-model="gamePath" type="text" placeholder="选择游戏安装路径" />
            <button class="action-btn secondary" @click="browseFolder('game-path')">
              <i class="fas fa-folder-open"></i> 浏览
            </button>
          </div>
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input v-model="debugMode" type="checkbox" /> 启用调试模式
          </label>
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input v-model="autoCheckUpdate" type="checkbox" /> 启动时自动检查更新
          </label>
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input v-model="deleteUpdating" type="checkbox" /> 更新时删除废弃的包
          </label>
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input v-model="updateUseProxy" type="checkbox" /> 更新通过镜像加速
          </label>
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input v-model="updateOnlyStable" type="checkbox" /> 仅更新稳定版本
          </label>
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input v-model="apiCrypto" type="checkbox" /> 加密api配置
          </label>
        </div>

        <div class="form-group">
          <label>Github代理重试线程数:</label>
          <input v-model.number="githubMaxWorkers" type="number" />
        </div>

        <div class="form-group">
          <label>Github代理超时秒数:</label>
          <input v-model.number="githubTimeout" type="number" />
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input v-model="enableCache" type="checkbox" /> 启用资源缓存
          </label>
          <div v-if="showCachePath" style="margin-top: 10px">
            <label>缓存路径:</label>
            <div class="file-input-group">
              <input v-model="cachePath" type="text" />
              <button class="action-btn secondary" @click="browseFolder('cache-path')">
                <i class="fas fa-folder-open"></i> 浏览
              </button>
            </div>
          </div>
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input v-model="enableStorage" type="checkbox" /> 启用数据持久化
          </label>
          <div v-if="showStoragePath" style="margin-top: 10px">
            <label>存储路径:</label>
            <div class="file-input-group">
              <input v-model="storagePath" type="text" />
              <button class="action-btn secondary" @click="browseFolder('storage-path')">
                <i class="fas fa-folder-open"></i> 浏览
              </button>
            </div>
          </div>
        </div>

        <div class="action-area">
          <button class="primary-btn" @click="saveSettings">
            <i class="fas fa-save"></i> 保存设置
          </button>
        </div>
      </div>

      <div class="setting-card">
        <h3 class="setting-title">配置操作</h3>
        <button class="action-btn" @click="useDefaultConfig">
          <i class="fas fa-file-alt"></i> 使用默认配置
        </button>
        <button class="action-btn danger" @click="resetConfig">
          <i class="fas fa-redo"></i> 重置配置
        </button>
        <button class="action-btn" @click="updateStore.check()">
          <i class="fas fa-sync-alt"></i> 检查更新
        </button>
        <button class="action-btn" @click="manualUpdateFromLocal">
          <i class="fas fa-file-upload"></i> 从本地更新包手动更新
        </button>
        <button class="action-btn" @click="updateStore.perform('')">
          <i class="fas fa-sync-alt"></i> 强制进行更新
        </button>
        <button class="action-btn" @click="router.push('/test')">
          <i class="fas fa-flask"></i> 进入调试页面
        </button>
        <button class="action-btn" @click="router.push('/clean')">
          <i class="fas fa-broom"></i> 进入缓存清理
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Settings view uses shared global classes from main.css */
</style>
