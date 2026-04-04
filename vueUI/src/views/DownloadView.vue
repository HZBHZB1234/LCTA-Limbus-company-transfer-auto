<template>
  <div class="download-view">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fab fa-google-play"></i> 从各个平台下载汉化
      </h2>
      <p class="section-subtitle">下载各个来源的汉化包</p>
    </div>

    <div class="settings-grid">
      <SettingCard title="OurPlay下载配置">
        <div class="form-group">
          <label>字体处理选项</label>
          <div class="select-wrapper">
            <select v-model="ourplayFontOption">
              <option value="keep">保留原字体</option>
              <option value="simplify">精简字体</option>
              <option value="llc">使用本地字体缓存</option>
            </select>
            <i class="fas fa-chevron-down"></i>
          </div>
        </div>

        <Checkbox v-model="ourplayCheckHash">启用哈希校验</Checkbox>
        <Checkbox v-model="ourplayUseApi">使用API获取链接</Checkbox>

        <div class="action-area">
          <Button @click="downloadOurplay" :loading="downloadingOurplay">
            <i class="fas fa-download"></i> 下载OurPlay汉化包
          </Button>
        </div>
      </SettingCard>

      <SettingCard title="零协会下载配置">
        <div class="form-group">
          <label>压缩格式</label>
          <div class="select-wrapper">
            <select v-model="llcZipType">
              <option value="zip">ZIP格式</option>
              <option value="seven">7Z格式</option>
            </select>
            <i class="fas fa-chevron-down"></i>
          </div>
        </div>

        <div class="form-group">
          <label>文本下载来源</label>
          <div class="select-wrapper">
            <select v-model="llcDownloadSource">
              <option value="github">从github下载</option>
              <option value="mirror">从公益镜像下载 beta</option>
            </select>
            <i class="fas fa-chevron-down"></i>
          </div>
        </div>

        <Checkbox v-model="llcUseProxy">使用代理加速下载</Checkbox>
        <Checkbox v-model="llcUseCache">使用本地字体缓存</Checkbox>
        <Checkbox v-model="llcDumpDefault">保存原始文件而不打包</Checkbox>

        <div class="action-area">
          <Button @click="downloadLLC" :loading="downloadingLLC">
            <i class="fas fa-download"></i> 下载零协汉化包
          </Button>
        </div>
      </SettingCard>

      <SettingCard title="LCTA-AU下载配置">
        <div class="form-group">
          <label>文本下载来源</label>
          <div class="select-wrapper">
            <select v-model="machineDownloadSource">
              <option value="github">从github下载</option>
              <option value="mirror">从公益镜像下载 beta</option>
            </select>
            <i class="fas fa-chevron-down"></i>
          </div>
        </div>

        <Checkbox v-model="machineUseProxy">使用代理加速下载</Checkbox>

        <div class="action-area">
          <Button @click="downloadMachine" :loading="downloadingMachine">
            <i class="fas fa-download"></i> 下载LCTA-AU汉化包
          </Button>
        </div>
      </SettingCard>

      <SettingCard title="气泡文本下载配置">
        <Checkbox v-model="bubbleColor">下载有颜色的气泡文本</Checkbox>
        <Checkbox v-model="bubbleLlc">下载随机加载文本</Checkbox>
        <Checkbox v-model="bubbleInstall">立即安装</Checkbox>

        <div class="action-area">
          <Button @click="downloadBubble" :loading="downloadingBubble">
            <i class="fas fa-download"></i> 下载(安装)气泡文本
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

// OurPlay 配置
const ourplayFontOption = ref('keep')
const ourplayCheckHash = ref(true)
const ourplayUseApi = ref(false)

// 零协配置
const llcZipType = ref('zip')
const llcDownloadSource = ref('github')
const llcUseProxy = ref(true)
const llcUseCache = ref(false)
const llcDumpDefault = ref(false)

// LCTA-AU 配置
const machineDownloadSource = ref('github')
const machineUseProxy = ref(true)

// 气泡文本配置
const bubbleColor = ref(false)
const bubbleLlc = ref(false)
const bubbleInstall = ref(true)

// 加载状态
const downloadingOurplay = ref(false)
const downloadingLLC = ref(false)
const downloadingMachine = ref(false)
const downloadingBubble = ref(false)

// 加载配置
function loadConfig() {
  ourplayFontOption.value = configStore.getById('ourplay-font-option') || 'keep'
  ourplayCheckHash.value = configStore.getById('ourplay-check-hash') !== false
  ourplayUseApi.value = configStore.getById('ourplay-use-api') || false

  llcZipType.value = configStore.getById('llc-zip-type') || 'zip'
  llcDownloadSource.value = configStore.getById('llc-download-source') || 'github'
  llcUseProxy.value = configStore.getById('llc-use-proxy') !== false
  llcUseCache.value = configStore.getById('llc-use-cache') || false
  llcDumpDefault.value = configStore.getById('llc-dump-default') || false

  machineDownloadSource.value = configStore.getById('machine-download-source') || 'github'
  machineUseProxy.value = configStore.getById('machine-use-proxy') !== false

  bubbleColor.value = configStore.getById('bubble-color') || false
  bubbleLlc.value = configStore.getById('bubble-llc') || false
  bubbleInstall.value = configStore.getById('bubble-install') !== false
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

watch(ourplayFontOption, (v) => saveConfig('ourplay-font-option', v))
watch(ourplayCheckHash, (v) => saveConfig('ourplay-check-hash', v))
watch(ourplayUseApi, (v) => saveConfig('ourplay-use-api', v))
watch(llcZipType, (v) => saveConfig('llc-zip-type', v))
watch(llcDownloadSource, (v) => saveConfig('llc-download-source', v))
watch(llcUseProxy, (v) => saveConfig('llc-use-proxy', v))
watch(llcUseCache, (v) => saveConfig('llc-use-cache', v))
watch(llcDumpDefault, (v) => saveConfig('llc-dump-default', v))
watch(machineDownloadSource, (v) => saveConfig('machine-download-source', v))
watch(machineUseProxy, (v) => saveConfig('machine-use-proxy', v))
watch(bubbleColor, (v) => saveConfig('bubble-color', v))
watch(bubbleLlc, (v) => saveConfig('bubble-llc', v))
watch(bubbleInstall, (v) => saveConfig('bubble-install', v))

// 下载函数
async function downloadOurplay() {
  downloadingOurplay.value = true
  await configStore.flushUpdates()
  const modalId = modalStore.openModal('progress', { title: '下载OurPlay汉化包' })
  try {
    const result = await api.call('download_ourplay_translation', modalId)
    if (result.success) {
      modalStore.completeModal(modalId, true, 'OurPlay汉化包下载成功')
    } else {
      modalStore.completeModal(modalId, false, result.message || '下载失败')
    }
  } catch (error) {
    modalStore.completeModal(modalId, false, error.message)
  } finally {
    downloadingOurplay.value = false
  }
}

async function downloadLLC() {
  downloadingLLC.value = true
  await configStore.flushUpdates()
  const modalId = modalStore.openModal('progress', { title: '下载零协汉化包' })
  try {
    const result = await api.call('download_llc_translation', modalId)
    if (result.success) {
      modalStore.completeModal(modalId, true, '零协汉化包下载成功')
    } else {
      modalStore.completeModal(modalId, false, result.message || '下载失败')
    }
  } catch (error) {
    modalStore.completeModal(modalId, false, error.message)
  } finally {
    downloadingLLC.value = false
  }
}

async function downloadMachine() {
  downloadingMachine.value = true
  await configStore.flushUpdates()
  const modalId = modalStore.openModal('progress', { title: '下载LCTA-AU汉化包' })
  try {
    const result = await api.call('download_LCTA_auto', modalId)
    if (result.success) {
      modalStore.completeModal(modalId, true, 'LCTA-AU汉化包下载成功')
    } else {
      modalStore.completeModal(modalId, false, result.message || '下载失败')
    }
  } catch (error) {
    modalStore.completeModal(modalId, false, error.message)
  } finally {
    downloadingMachine.value = false
  }
}

async function downloadBubble() {
  downloadingBubble.value = true
  await configStore.flushUpdates()
  const modalId = modalStore.openModal('progress', { title: '下载气泡文本' })
  try {
    const result = await api.call('download_bubble', modalId)
    if (result.success) {
      modalStore.completeModal(modalId, true, '气泡文本下载成功')
    } else {
      modalStore.completeModal(modalId, false, result.message || '下载失败')
    }
  } catch (error) {
    modalStore.completeModal(modalId, false, error.message)
  } finally {
    downloadingBubble.value = false
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
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: var(--spacing-lg);
}
.action-area {
  margin-top: var(--spacing-lg);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border);
}
.select-wrapper {
  position: relative;
}
.select-wrapper select {
  appearance: none;
  padding-right: 40px;
}
.select-wrapper i {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none;
  color: var(--color-text-secondary);
}
</style>