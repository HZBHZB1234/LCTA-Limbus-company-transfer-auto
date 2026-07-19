<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getApi } from '@/utils/api'
import { useConfigStore } from '@/stores/config'
import { listenEvent } from '@/utils/events'

const configStore = useConfigStore()

const launcherZeroZipType = ref('zip')
const launcherZeroDownloadSource = ref('github')
const launcherZeroUseProxy = ref(true)
const launcherZeroUseCache = ref(true)

const launcherOurplaySource = ref('pc')
const launcherOurplayFontOption = ref('keep')
const launcherOurplayUseApi = ref(true)
const launcherOurplayOfficial = ref(true)
const launcherOurplayReferPackage = ref('')

const launcherMachineDownloadSource = ref('github')
const launcherMachineUseProxy = ref(true)

const launcherWorkUpdate = ref('no')
const launcherWorkMod = ref(true)
const launcherWorkFancy = ref(true)
const launcherWorkBubble = ref(true)
const launcherWorkCdnOptimize = ref(false)
const launcherWorkCdnAutoApply = ref(false)
const launcherWorkCdnCacheTtl = ref(24)
const launcherWorkGuiMode = ref(false)
const launcherWorkSpeed = ref(false)
const launcherSpeedFactor = ref(2.0)

const steamCommand = ref('')

const showAndroidOptions = computed(() => launcherOurplaySource.value === 'android')

listenEvent('lcta:file-picked', (detail) => {
  if (detail.inputId === 'launcher-ourplay-refer-package') launcherOurplayReferPackage.value = detail.path
  if (detail.inputId === 'steam-command') steamCommand.value = detail.path
})

onMounted(async () => {
  launcherZeroZipType.value = (configStore.get('launcher.zero.zip_type') as string) || 'zip'
  launcherZeroDownloadSource.value = (configStore.get('launcher.zero.download_source') as string) || 'github'
  launcherZeroUseProxy.value = (configStore.get('launcher.zero.use_proxy') as boolean) ?? true
  launcherZeroUseCache.value = (configStore.get('launcher.zero.use_cache') as boolean) ?? true

  launcherOurplaySource.value = (configStore.get('launcher.ourplay.source') as string) || 'pc'
  launcherOurplayFontOption.value = (configStore.get('launcher.ourplay.font_option') as string) || 'keep'
  launcherOurplayUseApi.value = (configStore.get('launcher.ourplay.use_api') as boolean) ?? true
  launcherOurplayOfficial.value = (configStore.get('launcher.ourplay.official') as boolean) ?? true
  launcherOurplayReferPackage.value = (configStore.get('launcher.ourplay.refer_package') as string) || ''

  launcherMachineDownloadSource.value = (configStore.get('launcher.machine.download_source') as string) || 'github'
  launcherMachineUseProxy.value = (configStore.get('launcher.machine.use_proxy') as boolean) ?? true

  launcherWorkUpdate.value = (configStore.get('launcher.work.update') as string) || 'no'
  launcherWorkMod.value = (configStore.get('launcher.work.mod') as boolean) ?? true
  launcherWorkFancy.value = (configStore.get('launcher.work.fancy') as boolean) ?? true
  launcherWorkBubble.value = (configStore.get('launcher.work.bubble') as boolean) ?? true
  launcherWorkCdnOptimize.value = (configStore.get('launcher.work.cdn_optimize') as boolean) ?? false
  launcherWorkCdnAutoApply.value = (configStore.get('launcher.work.cdn_auto_apply') as boolean) ?? false
  launcherWorkCdnCacheTtl.value = (configStore.get('launcher.work.cdn_cache_ttl') as number) || 24
  launcherWorkGuiMode.value = (configStore.get('launcher.work.gui_mode') as boolean) ?? false
  launcherWorkSpeed.value = (configStore.get('launcher.work.speed') as boolean) ?? false
  launcherSpeedFactor.value = (configStore.get('launcher.work.speed_factor') as number) || 2.0

  steamCommand.value = (configStore.get('launcher.steam_command') as string) || ''
})

async function saveLauncher() {
  configStore.set('launcher.zero.zip_type', launcherZeroZipType.value)
  configStore.set('launcher.zero.download_source', launcherZeroDownloadSource.value)
  configStore.set('launcher.zero.use_proxy', launcherZeroUseProxy.value)
  configStore.set('launcher.zero.use_cache', launcherZeroUseCache.value)

  configStore.set('launcher.ourplay.source', launcherOurplaySource.value)
  configStore.set('launcher.ourplay.font_option', launcherOurplayFontOption.value)
  configStore.set('launcher.ourplay.use_api', launcherOurplayUseApi.value)
  configStore.set('launcher.ourplay.official', launcherOurplayOfficial.value)
  configStore.set('launcher.ourplay.refer_package', launcherOurplayReferPackage.value)

  configStore.set('launcher.machine.download_source', launcherMachineDownloadSource.value)
  configStore.set('launcher.machine.use_proxy', launcherMachineUseProxy.value)

  configStore.set('launcher.work.update', launcherWorkUpdate.value)
  configStore.set('launcher.work.mod', launcherWorkMod.value)
  configStore.set('launcher.work.fancy', launcherWorkFancy.value)
  configStore.set('launcher.work.bubble', launcherWorkBubble.value)
  configStore.set('launcher.work.cdn_optimize', launcherWorkCdnOptimize.value)
  configStore.set('launcher.work.cdn_auto_apply', launcherWorkCdnAutoApply.value)
  configStore.set('launcher.work.cdn_cache_ttl', launcherWorkCdnCacheTtl.value)
  configStore.set('launcher.work.gui_mode', launcherWorkGuiMode.value)
  configStore.set('launcher.work.speed', launcherWorkSpeed.value)
  configStore.set('launcher.work.speed_factor', launcherSpeedFactor.value)

  configStore.set('launcher.steam_command', steamCommand.value)
  await configStore.save()
}

async function browseFolder(inputId: string) {
  await getApi().browse_folder(inputId)
}

async function browseFile(inputId: string) {
  await getApi().browse_file(inputId)
}

async function copySteam() {
  try {
    await navigator.clipboard.writeText(steamCommand.value)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = steamCommand.value
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  }
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-rocket"></i> Launcher配置</h2>
      <p class="section-subtitle">配置游戏启动器相关选项</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card" v-tooltip>
        <h3 class="setting-title">零协汉化配置</h3>
        <div class="form-group" v-tooltip="'launcher-zero-zip-type'">
          <label for="launcher-zero-zip-type">压缩格式:</label>
          <select id="launcher-zero-zip-type" v-model="launcherZeroZipType">
            <option value="zip">ZIP格式</option>
            <option value="seven">7Z格式</option>
          </select>
        </div>
        <div class="form-group" v-tooltip="'launcher-zero-download-source'">
          <label for="launcher-zero-download-source">文本下载来源:</label>
          <select id="launcher-zero-download-source" v-model="launcherZeroDownloadSource">
            <option value="github">从github下载</option>
            <option value="mirror">从公益镜像下载 beta</option>
          </select>
        </div>
        <div class="form-group" v-tooltip="'launcher-zero-use-proxy'">
          <label class="checkbox-label">
            <input id="launcher-zero-use-proxy" v-model="launcherZeroUseProxy" type="checkbox" />
            使用代理加速下载
          </label>
        </div>
        <div class="form-group" v-tooltip="'launcher-zero-use-cache'">
          <label class="checkbox-label">
            <input id="launcher-zero-use-cache" v-model="launcherZeroUseCache" type="checkbox" />
            使用本地字体缓存
          </label>
        </div>
      </div>

      <div class="setting-card">
        <h3 class="setting-title">OurPlay配置</h3>
        <div class="form-group" v-tooltip="'launcher-ourplay-source'">
          <label for="launcher-ourplay-source">API源:</label>
          <select id="launcher-ourplay-source" v-model="launcherOurplaySource">
            <option value="pc">PC API</option>
            <option value="android">Android API (支持神人汉化)</option>
          </select>
        </div>
        <div class="form-group" v-tooltip="'launcher-ourplay-font-option'">
          <label for="launcher-ourplay-font-option">字体处理选项:</label>
          <select id="launcher-ourplay-font-option" v-model="launcherOurplayFontOption">
            <option value="keep">保留原字体</option>
            <option value="simplify">精简字体</option>
            <option value="llc">使用本地字体缓存</option>
          </select>
        </div>
        <div class="form-group" v-tooltip="'launcher-ourplay-use-api'">
          <label class="checkbox-label">
            <input id="launcher-ourplay-use-api" v-model="launcherOurplayUseApi" type="checkbox" />
            使用API获取版本信息
          </label>
        </div>

        <template v-if="showAndroidOptions">
          <div class="form-group" v-tooltip="'launcher-ourplay-official'">
            <label class="checkbox-label">
              <input id="launcher-ourplay-official" v-model="launcherOurplayOfficial" type="checkbox" />
              下载正经版本汉化（关闭则下载神人汉化）
            </label>
          </div>
          <div class="form-group" v-tooltip="'launcher-ourplay-refer-package'">
            <label for="launcher-ourplay-refer-package">基板包路径（可选）:</label>
            <div class="file-input-group">
              <input id="launcher-ourplay-refer-package" v-model="launcherOurplayReferPackage" type="text" placeholder="留空则自动检测（需已安装足够新版的零协会汉化包）" />
              <button class="action-btn secondary" @click="browseFolder('launcher-ourplay-refer-package')"><i class="fas fa-folder-open"></i> 浏览文件夹</button>
              <button class="action-btn secondary" @click="browseFile('launcher-ourplay-refer-package')"><i class="fas fa-file"></i> 浏览zip</button>
            </div>
          </div>
        </template>
      </div>

      <div class="setting-card">
        <h3 class="setting-title">LCTA-AU汉化配置</h3>
        <div class="form-group" v-tooltip="'launcher-machine-download-source'">
          <label for="launcher-machine-download-source">文本下载来源:</label>
          <select id="launcher-machine-download-source" v-model="launcherMachineDownloadSource">
            <option value="github">从github下载</option>
            <option value="mirror">从公益镜像下载 beta</option>
          </select>
        </div>
        <div class="form-group" v-tooltip="'launcher-machine-use-proxy'">
          <label class="checkbox-label">
            <input id="launcher-machine-use-proxy" v-model="launcherMachineUseProxy" type="checkbox" />
            使用代理加速下载
          </label>
        </div>
      </div>

      <div class="setting-card">
        <h3 class="setting-title">工作模式配置</h3>
        <div class="form-group" v-tooltip="'launcher-work-update'">
          <label for="launcher-work-update">更新模式:</label>
          <select id="launcher-work-update" v-model="launcherWorkUpdate">
            <option value="no">不自动更新</option>
            <option value="llc">仅零协更新</option>
            <option value="ourplay">仅ourplay更新</option>
            <option value="LCTA-AU">仅LCTA-AU更新</option>
            <option value="LO">更新llc+ourplay</option>
            <option value="LM-G">更新llc+LCTA-AU (github)</option>
            <option value="LM-A">更新llc+LCTA-AU (API Beta)</option>
          </select>
        </div>
        <div class="form-group" v-tooltip="'launcher-work-mod'">
          <label class="checkbox-label">
            <input id="launcher-work-mod" v-model="launcherWorkMod" type="checkbox" />
            启用MOD支持
          </label>
        </div>
        <div class="form-group" v-tooltip="'launcher-work-fancy'">
          <label class="checkbox-label">
            <input id="launcher-work-fancy" v-model="launcherWorkFancy" type="checkbox" />
            启用文本美化
          </label>
        </div>
        <div class="form-group" v-tooltip="'launcher-work-bubble'">
          <label class="checkbox-label">
            <input id="launcher-work-bubble" v-model="launcherWorkBubble" type="checkbox" />
            启用气泡文本
          </label>
        </div>
        <div class="form-group" v-tooltip="'launcher-work-cdn-optimize'">
          <label class="checkbox-label">
            <input id="launcher-work-cdn-optimize" v-model="launcherWorkCdnOptimize" type="checkbox" />
            启动时自动进行CDN优选
          </label>
        </div>
        <div class="form-group" v-tooltip="'launcher-work-cdn-auto-apply'">
          <label class="checkbox-label">
            <input id="launcher-work-cdn-auto-apply" v-model="launcherWorkCdnAutoApply" type="checkbox" />
            自动写入hosts
          </label>
        </div>
        <div class="form-group" v-tooltip="'launcher-work-cdn-cache-ttl'">
          <label for="launcher-work-cdn-cache-ttl">CDN缓存有效期:</label>
          <div class="input-with-suffix">
            <input id="launcher-work-cdn-cache-ttl" v-model.number="launcherWorkCdnCacheTtl" type="number" min="0" max="720" step="0.5" />
            <span class="input-suffix">小时</span>
          </div>
        </div>
        <div class="form-group" v-tooltip="'launcher-work-gui-mode'">
          <label class="checkbox-label">
            <input id="launcher-work-gui-mode" v-model="launcherWorkGuiMode" type="checkbox" />
            启用GUI进度窗口
          </label>
        </div>
        <div class="form-group" v-tooltip="'launcher-work-speed'">
          <label class="checkbox-label">
            <input id="launcher-work-speed" v-model="launcherWorkSpeed" type="checkbox" />
            在 Launcher 模式下启用游戏加速
          </label>
        </div>
        <div class="form-group" v-tooltip="'launcher-speed-factor'">
          <label for="launcher-speed-factor">热键切换速度因子:</label>
          <input id="launcher-speed-factor" v-model.number="launcherSpeedFactor" type="number" min="0.1" max="10" step="0.1" />
        </div>
      </div>
    </div>

    <div class="settings-grid" style="margin-top: 16px;">
      <div class="setting-card">
        <h3 class="setting-title">Steam 命令</h3>
        <div class="form-group" v-tooltip="'steam-command'">
          <label for="steam-command">steam命令:</label>
          <div class="file-input-group">
            <input id="steam-command" v-model="steamCommand" type="text" placeholder="选择 steam.exe" readonly />
            <button class="action-btn secondary" @click="browseFile('steam-command')"><i class="fas fa-folder-open"></i> 浏览</button>
            <button class="action-btn secondary" @click="copySteam"><i class="fas fa-copy"></i> 复制</button>
          </div>
        </div>
      </div>
    </div>

    <div class="action-area">
      <button class="primary-btn" @click="saveLauncher"><i class="fas fa-save"></i> 保存配置</button>
    </div>
  </div>
</template>

<style scoped>
.input-with-suffix {
  display: flex;
  align-items: center;
  gap: 6px;
}
.input-with-suffix input {
  flex: 1;
  min-width: 0;
}
.input-suffix {
  color: var(--color-text-secondary);
  font-size: 14px;
  white-space: nowrap;
}
</style>
