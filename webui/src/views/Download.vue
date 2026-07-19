<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getApi } from '@/utils/api'
import { useConfigStore } from '@/stores/config'
import { useModalStore } from '@/stores/modal'
import { listenEvent } from '@/utils/events'

const configStore = useConfigStore()
const modalStore = useModalStore()

const ourplaySource = ref('pc')
const ourplayFontOption = ref('keep')
const ourplayCheckHash = ref(true)
const ourplayUseApi = ref(true)
const ourplayOfficial = ref(true)
const ourplayReferPackage = ref('')

const llcZipType = ref('zip')
const llcDownloadSource = ref('github')
const llcUseProxy = ref(true)
const llcUseCache = ref(true)
const llcDumpDefault = ref(false)

const machineDownloadSource = ref('github')
const machineUseProxy = ref(true)

const bubbleColor = ref(true)
const bubbleLlc = ref(true)
const bubbleInstall = ref(false)

const showAndroidOptions = computed(() => ourplaySource.value === 'android')

listenEvent('lcta:file-picked', (detail) => {
  if (detail.inputId === 'ourplay-refer-package') ourplayReferPackage.value = detail.path
})

onMounted(async () => {
  ourplaySource.value = (configStore.get('ui_default.ourplay.source') as string) || 'pc'
  ourplayFontOption.value = (configStore.get('ui_default.ourplay.font_option') as string) || 'keep'
  ourplayCheckHash.value = (configStore.get('ui_default.ourplay.check_hash') as boolean) ?? true
  ourplayUseApi.value = (configStore.get('ui_default.ourplay.use_api') as boolean) ?? true
  ourplayOfficial.value = (configStore.get('ui_default.ourplay.official') as boolean) ?? true
  ourplayReferPackage.value = (configStore.get('ui_default.ourplay.refer_package') as string) || ''

  llcZipType.value = (configStore.get('ui_default.zero.zip_type') as string) || 'zip'
  llcDownloadSource.value = (configStore.get('ui_default.zero.download_source') as string) || 'github'
  llcUseProxy.value = (configStore.get('ui_default.zero.use_proxy') as boolean) ?? true
  llcUseCache.value = (configStore.get('ui_default.zero.use_cache') as boolean) ?? true
  llcDumpDefault.value = (configStore.get('ui_default.zero.dump_default') as boolean) ?? false

  machineDownloadSource.value = (configStore.get('ui_default.machine.download_source') as string) || 'github'
  machineUseProxy.value = (configStore.get('ui_default.machine.use_proxy') as boolean) ?? true

  bubbleColor.value = (configStore.get('ui_default.bubble.color') as boolean) ?? true
  bubbleLlc.value = (configStore.get('ui_default.bubble.llc') as boolean) ?? true
  bubbleInstall.value = (configStore.get('ui_default.bubble.install') as boolean) ?? false
})

async function browseFolder(inputId: string) {
  try {
    await getApi().browse_folder(inputId)
  } catch (e) {
    console.error('Browse folder failed:', e)
    getApi().log(`[Download] 浏览文件夹失败: ${e}`).catch(() => {})
  }
}

async function browseFile(inputId: string) {
  try {
    await getApi().browse_file(inputId)
  } catch (e) {
    console.error('Browse file failed:', e)
    getApi().log(`[Download] 浏览文件失败: ${e}`).catch(() => {})
  }
}

function logDownloadError(source: string, e: unknown): void {
  const msg = `[Download] ${source} 下载启动失败: ${e}`
  console.error(msg)
  getApi().log(msg).catch(() => {})
}

async function saveDownloadConfig() {
  configStore.set('ui_default.ourplay.source', ourplaySource.value)
  configStore.set('ui_default.ourplay.font_option', ourplayFontOption.value)
  configStore.set('ui_default.ourplay.check_hash', ourplayCheckHash.value)
  configStore.set('ui_default.ourplay.use_api', ourplayUseApi.value)
  configStore.set('ui_default.ourplay.official', ourplayOfficial.value)
  configStore.set('ui_default.ourplay.refer_package', ourplayReferPackage.value)
  configStore.set('ui_default.zero.zip_type', llcZipType.value)
  configStore.set('ui_default.zero.download_source', llcDownloadSource.value)
  configStore.set('ui_default.zero.use_proxy', llcUseProxy.value)
  configStore.set('ui_default.zero.use_cache', llcUseCache.value)
  configStore.set('ui_default.zero.dump_default', llcDumpDefault.value)
  configStore.set('ui_default.machine.download_source', machineDownloadSource.value)
  configStore.set('ui_default.machine.use_proxy', machineUseProxy.value)
  configStore.set('ui_default.bubble.color', bubbleColor.value)
  configStore.set('ui_default.bubble.llc', bubbleLlc.value)
  configStore.set('ui_default.bubble.install', bubbleInstall.value)
  await configStore.save()
}

async function downloadOurplay() {
  try {
    await saveDownloadConfig()
    const mid = modalStore.create('progress', { title: '下载 OurPlay 汉化包' })
    getApi().download_ourplay_translation(mid)
  } catch (e) { logDownloadError('OurPlay', e) }
}

async function downloadLLC() {
  try {
    await saveDownloadConfig()
    const mid = modalStore.create('progress', { title: '下载零协会汉化包' })
    getApi().download_llc_translation(mid)
  } catch (e) { logDownloadError('零协会', e) }
}

async function downloadMachine() {
  try {
    await saveDownloadConfig()
    const mid = modalStore.create('progress', { title: '下载 LCTA 自动汉化' })
    getApi().download_LCTA_auto(mid)
  } catch (e) { logDownloadError('LCTA-AU', e) }
}

async function downloadBubble() {
  try {
    await saveDownloadConfig()
    const mid = modalStore.create('progress', { title: '下载 Bubble 语言包' })
    getApi().download_bubble(mid)
  } catch (e) { logDownloadError('Bubble', e) }
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fab fa-google-play"></i> 从各个平台下载汉化</h2>
      <p class="section-subtitle">下载各个来源的汉化包</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card" v-tooltip>
        <h3 class="setting-title">OurPlay 下载配置</h3>
        <div class="form-group" v-tooltip="'ourplay-source'">
          <label for="ourplay-source">API源:</label>
          <select id="ourplay-source" v-model="ourplaySource">
            <option value="pc">PC API</option>
            <option value="android">Android API</option>
          </select>
        </div>
        <div class="form-group" v-tooltip="'ourplay-font-option'">
          <label for="ourplay-font-option">字体处理选项:</label>
          <select id="ourplay-font-option" v-model="ourplayFontOption">
            <option value="keep">保留原字体</option>
            <option value="simplify">精简字体</option>
            <option value="llc">使用本地字体缓存</option>
          </select>
        </div>
        <div class="form-group" v-tooltip="'ourplay-check-hash'">
          <label class="checkbox-label">
            <input id="ourplay-check-hash" v-model="ourplayCheckHash" type="checkbox" />
            启用哈希校验
          </label>
        </div>
        <div class="form-group" v-tooltip="'ourplay-use-api'">
          <label class="checkbox-label">
            <input id="ourplay-use-api" v-model="ourplayUseApi" type="checkbox" />
            使用API获取版本信息
          </label>
        </div>

        <template v-if="showAndroidOptions">
          <div class="form-group" v-tooltip="'ourplay-official'">
            <label class="checkbox-label">
              <input id="ourplay-official" v-model="ourplayOfficial" type="checkbox" />
              下载正式版本汉化
            </label>
          </div>
          <div class="form-group" v-tooltip="'ourplay-refer-package'">
            <label for="ourplay-refer-package">基板包路径（可选）:</label>
            <div class="file-input-group">
              <input id="ourplay-refer-package" v-model="ourplayReferPackage" type="text" placeholder="留空则自动检测" />
              <button class="action-btn secondary" @click="browseFolder('ourplay-refer-package')"><i class="fas fa-folder-open"></i> 浏览文件夹</button>
              <button class="action-btn secondary" @click="browseFile('ourplay-refer-package')"><i class="fas fa-file"></i> 浏览文件</button>
            </div>
          </div>
        </template>

        <div class="action-area">
          <button class="primary-btn" @click="downloadOurplay"><i class="fas fa-download"></i> 下载 OurPlay 汉化包</button>
        </div>
      </div>

      <div class="setting-card" v-tooltip>
        <h3 class="setting-title">零协会下载配置</h3>
        <div class="form-group" v-tooltip="'llc-zip-type'">
          <label for="llc-zip-type">压缩格式:</label>
          <select id="llc-zip-type" v-model="llcZipType">
            <option value="zip">ZIP格式</option>
            <option value="seven">7Z格式</option>
          </select>
        </div>
        <div class="form-group" v-tooltip="'llc-download-source'">
          <label for="llc-download-source">文本下载来源:</label>
          <select id="llc-download-source" v-model="llcDownloadSource">
            <option value="github">从github下载</option>
            <option value="mirror">从公益镜像下载</option>
          </select>
        </div>
        <div class="form-group" v-tooltip="'llc-use-proxy'">
          <label class="checkbox-label">
            <input id="llc-use-proxy" v-model="llcUseProxy" type="checkbox" />
            使用代理加速下载
          </label>
        </div>
        <div class="form-group" v-tooltip="'llc-use-cache'">
          <label class="checkbox-label">
            <input id="llc-use-cache" v-model="llcUseCache" type="checkbox" />
            使用本地字体缓存
          </label>
        </div>
        <div class="form-group" v-tooltip="'llc-dump-default'">
          <label class="checkbox-label">
            <input id="llc-dump-default" v-model="llcDumpDefault" type="checkbox" />
            导出默认字体
          </label>
        </div>
        <div class="action-area">
          <button class="primary-btn" @click="downloadLLC"><i class="fas fa-download"></i> 下载零协会汉化包</button>
        </div>
      </div>

      <div class="setting-card" v-tooltip>
        <h3 class="setting-title">LCTA-AU 下载配置</h3>
        <div class="form-group" v-tooltip="'machine-download-source'">
          <label for="machine-download-source">文本下载来源:</label>
          <select id="machine-download-source" v-model="machineDownloadSource">
            <option value="github">从github下载</option>
            <option value="mirror">从公益镜像下载</option>
          </select>
        </div>
        <div class="form-group" v-tooltip="'machine-use-proxy'">
          <label class="checkbox-label">
            <input id="machine-use-proxy" v-model="machineUseProxy" type="checkbox" />
            使用代理加速下载
          </label>
        </div>
        <div class="action-area">
          <button class="primary-btn" @click="downloadMachine"><i class="fas fa-download"></i> 下载 LCTA 自动汉化</button>
        </div>
      </div>

      <div class="setting-card" v-tooltip>
        <h3 class="setting-title">Bubble 语言包</h3>
        <div class="form-group" v-tooltip="'bubble-color'">
          <label class="checkbox-label">
            <input id="bubble-color" v-model="bubbleColor" type="checkbox" />
            启用颜色气泡
          </label>
        </div>
        <div class="form-group" v-tooltip="'bubble-llc'">
          <label class="checkbox-label">
            <input id="bubble-llc" v-model="bubbleLlc" type="checkbox" />
            包含零协气泡
          </label>
        </div>
        <div class="form-group" v-tooltip="'bubble-install'">
          <label class="checkbox-label">
            <input id="bubble-install" v-model="bubbleInstall" type="checkbox" />
            下载后立即安装
          </label>
        </div>
        <div class="action-area">
          <button class="primary-btn" @click="downloadBubble"><i class="fas fa-download"></i> 下载 Bubble 语言包</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Download view uses shared global classes from main.css */
</style>
