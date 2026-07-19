<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getApi } from '@/utils/api'
import { useConfigStore } from '@/stores/config'
import { listenEvent } from '@/utils/events'

const configStore = useConfigStore()

const launcherMode = ref('no')
const launcherAutoCdn = ref(false)
const launcherCdnAutoApply = ref(false)
const launcherMods = ref(false)
const steamCommand = ref('')

listenEvent('lcta:file-picked', (detail) => {
  if (detail.inputId === 'steam-command') steamCommand.value = detail.path
})

onMounted(async () => {
  launcherMode.value = (configStore.get('launcher_work_update') as string) || 'no'
  launcherAutoCdn.value = configStore.get('launcher.work.cdn_optimize') as boolean || false
  launcherCdnAutoApply.value = configStore.get('launcher.work.cdn_auto_apply') as boolean || false
  launcherMods.value = configStore.get('launcher.work.mods') as boolean || false
  steamCommand.value = (configStore.get('launcher.steam_command') as string) || ''
})

async function saveLauncher() {
  configStore.set('launcher_work_update', launcherMode.value)
  configStore.set('launcher.work.cdn_optimize', launcherAutoCdn.value)
  configStore.set('launcher.work.cdn_auto_apply', launcherCdnAutoApply.value)
  configStore.set('launcher.work.mods', launcherMods.value)
  configStore.set('launcher.steam_command', steamCommand.value)
  await configStore.save()
}

async function browseSteam() {
  await getApi().browse_file('steam-command')
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-rocket"></i> Launcher配置</h2>
      <p class="section-subtitle">配置启动器行为</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card">
        <h3 class="setting-title">启动器配置</h3>
        <div class="form-group">
          <label>更新模式:</label>
          <select v-model="launcherMode">
            <option value="no">不自动更新</option>
            <option value="llc">零协会汉化</option>
            <option value="ourplay">OurPlay 汉化</option>
            <option value="machine">自动翻译</option>
          </select>
        </div>
        <div class="form-group">
          <label class="checkbox-label"><input v-model="launcherAutoCdn" type="checkbox" /> 自动 CDN 优选</label>
        </div>
        <div class="form-group">
          <label class="checkbox-label"><input v-model="launcherCdnAutoApply" type="checkbox" /> 自动应用 CDN</label>
        </div>
        <div class="form-group">
          <label class="checkbox-label"><input v-model="launcherMods" type="checkbox" /> 启用 Mod</label>
        </div>
        <div class="form-group">
          <label>Steam 命令:</label>
          <div class="file-input-group">
            <input v-model="steamCommand" type="text" placeholder="选择 steam.exe" />
            <button class="action-btn secondary" @click="browseSteam"><i class="fas fa-folder-open"></i> 浏览</button>
          </div>
        </div>
        <button class="primary-btn" @click="saveLauncher"><i class="fas fa-save"></i> 保存</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.section-header { margin-bottom: 24px; }
.section-title { font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.section-title i { color: var(--accent-color); }
.section-subtitle { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }
.settings-grid { display: grid; grid-template-columns: 1fr; gap: 20px; max-width: 500px; }
.setting-card { background: var(--bg-secondary); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color); }
.setting-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 14px; color: var(--text-secondary); margin-bottom: 6px; }
.form-group select, .form-group input[type="text"] {
  width: 100%; padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border-color);
  background: var(--bg-primary); color: var(--text-primary); font-size: 14px;
}
.file-input-group { display: flex; gap: 8px; }
.file-input-group input { flex: 1; }
.primary-btn {
  padding: 10px 24px; border-radius: 8px; border: none; background: var(--accent-color); color: white; cursor: pointer; font-size: 14px; margin-top: 12px;
}
.action-btn {
  padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border-color);
  background: var(--bg-primary); color: var(--text-primary); cursor: pointer; font-size: 14px;
}
.checkbox-label { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 14px; }
.secondary { font-size: 12px; }
</style>
