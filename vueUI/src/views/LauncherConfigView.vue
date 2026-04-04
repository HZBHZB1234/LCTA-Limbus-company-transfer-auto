<template>
  <div class="launcher-config-view">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-rocket"></i> Launcher配置
      </h2>
      <p class="section-subtitle">配置游戏启动器相关选项</p>
    </div>

    <div class="settings-grid">
      <SettingCard title="零协汉化配置">
        <div class="form-group">
          <label>压缩格式</label>
          <div class="select-wrapper">
            <select v-model="launcherZeroZipType">
              <option value="zip">ZIP格式</option>
              <option value="seven">7Z格式</option>
            </select>
            <i class="fas fa-chevron-down"></i>
          </div>
        </div>

        <div class="form-group">
          <label>文本下载来源</label>
          <div class="select-wrapper">
            <select v-model="launcherZeroDownloadSource">
              <option value="github">从github下载</option>
              <option value="mirror">从公益镜像下载 beta</option>
            </select>
            <i class="fas fa-chevron-down"></i>
          </div>
        </div>

        <Checkbox v-model="launcherZeroUseProxy">使用代理加速下载</Checkbox>
        <Checkbox v-model="launcherZeroUseCache">使用本地字体缓存</Checkbox>
        <small class="form-hint">使用本地已有的字体文件，加快下载速度</small>
      </SettingCard>

      <SettingCard title="OurPlay配置">
        <div class="form-group">
          <label>字体处理选项</label>
          <div class="select-wrapper">
            <select v-model="launcherOurplayFontOption">
              <option value="keep">保留原字体</option>
              <option value="simplify">精简字体</option>
              <option value="llc">使用本地字体缓存</option>
            </select>
            <i class="fas fa-chevron-down"></i>
          </div>
        </div>
        <Checkbox v-model="launcherOurplayUseApi">使用API获取版本信息</Checkbox>
      </SettingCard>

      <SettingCard title="LCTA-AU汉化配置">
        <div class="form-group">
          <label>文本下载来源</label>
          <div class="select-wrapper">
            <select v-model="launcherMachineDownloadSource">
              <option value="github">从github下载</option>
              <option value="mirror">从公益镜像下载 beta</option>
            </select>
            <i class="fas fa-chevron-down"></i>
          </div>
        </div>
        <Checkbox v-model="launcherMachineUseProxy">使用代理加速下载</Checkbox>
      </SettingCard>

      <SettingCard title="工作模式配置">
        <div class="form-group">
          <label>更新模式</label>
          <div class="select-wrapper">
            <select v-model="launcherWorkUpdate">
              <option value="no">不自动更新</option>
              <option value="llc">仅零协更新</option>
              <option value="ourplay">仅ourplay更新</option>
              <option value="LCTA-AU">仅LCTA-AU更新</option>
              <option value="LO">更新llc+ourplay</option>
              <option value="LM-G">更新llc+LCTA-AU (github)</option>
              <option value="LM-A">更新llc+LCTA-AU (API Beta)</option>
            </select>
            <i class="fas fa-chevron-down"></i>
          </div>
        </div>

        <Checkbox v-model="launcherWorkMod">启用MOD支持</Checkbox>
        <small class="form-hint">启用后将加载MOD并启动游戏</small>

        <Checkbox v-model="launcherWorkFancy">启用文本美化</Checkbox>
        <small class="form-hint">更新汉化包后将自动进行文本美化，相关设置请在文本美化页面配置</small>

        <Checkbox v-model="launcherWorkBubble">启用气泡文本</Checkbox>
        <small class="form-hint">启用后将自动更新气泡文本模组，相关设置请在安装汉化包页面配置</small>
      </SettingCard>

      <SettingCard title="Steam命令">
        <div class="form-group">
          <label>Steam命令</label>
          <div class="steam-command-group">
            <input type="text" :value="steamCommand" readonly class="steam-cmd-input">
            <Button variant="secondary" @click="copySteamCommand">复制</Button>
          </div>
        </div>
      </SettingCard>
    </div>

    <div class="action-area">
      <Button @click="saveSettings" :loading="saving">保存配置</Button>
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

// 零协配置
const launcherZeroZipType = ref('zip')
const launcherZeroDownloadSource = ref('github')
const launcherZeroUseProxy = ref(true)
const launcherZeroUseCache = ref(true)

// OurPlay配置
const launcherOurplayFontOption = ref('keep')
const launcherOurplayUseApi = ref(true)

// LCTA-AU配置
const launcherMachineDownloadSource = ref('github')
const launcherMachineUseProxy = ref(true)

// 工作模式
const launcherWorkUpdate = ref('no')
const launcherWorkMod = ref(true)
const launcherWorkFancy = ref(true)
const launcherWorkBubble = ref(true)

const steamCommand = ref('')
const saving = ref(false)

function loadConfig() {
  launcherZeroZipType.value = configStore.getById('launcher-zero-zip-type') || 'zip'
  launcherZeroDownloadSource.value = configStore.getById('launcher-zero-download-source') || 'github'
  launcherZeroUseProxy.value = configStore.getById('launcher-zero-use-proxy') !== false
  launcherZeroUseCache.value = configStore.getById('launcher-zero-use-cache') !== false

  launcherOurplayFontOption.value = configStore.getById('launcher-ourplay-font-option') || 'keep'
  launcherOurplayUseApi.value = configStore.getById('launcher-ourplay-use-api') !== false

  launcherMachineDownloadSource.value = configStore.getById('machine-zero-download-source') || 'github'
  launcherMachineUseProxy.value = configStore.getById('machine-zero-use-proxy') !== false

  launcherWorkUpdate.value = configStore.getById('launcher-work-update') || 'no'
  launcherWorkMod.value = configStore.getById('launcher-work-mod') !== false
  launcherWorkFancy.value = configStore.getById('launcher-work-fancy') !== false
  launcherWorkBubble.value = configStore.getById('launcher-work-bubble') !== false
}

let saveTimer = null
function saveConfig(id, value) {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    configStore.updateConfig(id, value)
    configStore.flushUpdates()
  }, 300)
}

watch(launcherZeroZipType, (v) => saveConfig('launcher-zero-zip-type', v))
watch(launcherZeroDownloadSource, (v) => saveConfig('launcher-zero-download-source', v))
watch(launcherZeroUseProxy, (v) => saveConfig('launcher-zero-use-proxy', v))
watch(launcherZeroUseCache, (v) => saveConfig('launcher-zero-use-cache', v))
watch(launcherOurplayFontOption, (v) => saveConfig('launcher-ourplay-font-option', v))
watch(launcherOurplayUseApi, (v) => saveConfig('launcher-ourplay-use-api', v))
watch(launcherMachineDownloadSource, (v) => saveConfig('machine-zero-download-source', v))
watch(launcherMachineUseProxy, (v) => saveConfig('machine-zero-use-proxy', v))
watch(launcherWorkUpdate, (v) => saveConfig('launcher-work-update', v))
watch(launcherWorkMod, (v) => saveConfig('launcher-work-mod', v))
watch(launcherWorkFancy, (v) => saveConfig('launcher-work-fancy', v))
watch(launcherWorkBubble, (v) => saveConfig('launcher-work-bubble', v))

async function loadSteamCommand() {
  try {
    const cmd = await api.call('run_func', 'get_steam_command')
    steamCommand.value = cmd || '获取失败'
  } catch (error) {
    steamCommand.value = `获取失败: ${error.message}`
  }
}

function copySteamCommand() {
  navigator.clipboard.writeText(steamCommand.value)
  modalStore.openModal('message', { title: '提示', content: 'Steam命令已复制到剪贴板' })
}

async function saveSettings() {
  saving.value = true
  await configStore.flushUpdates()
  modalStore.openModal('message', { title: '成功', content: 'Launcher配置已保存' })
  saving.value = false
}

onMounted(() => {
  loadConfig()
  loadSteamCommand()
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
.steam-command-group {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
}
.steam-cmd-input {
  flex: 1;
  font-family: monospace;
  background: var(--color-bg-input);
  color: var(--color-text-primary);
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