<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { getApi } from '@/utils/api'
import { useModalStore } from '@/stores/modal'
import { useConfigStore } from '@/stores/config'

const modalStore = useModalStore()
const configStore = useConfigStore()

const disclaimerAccepted = ref(false)
const processRunning = ref(false)
const dllInjected = ref(false)
const currentSpeed = ref(1.0)
let pollTimer: ReturnType<typeof setInterval> | null = null

const launcherWorkSpeed = ref(false)
const launcherSpeedFactor = ref(2.0)

function startPolling() {
  pollTimer = setInterval(async () => {
    try {
      const result = await getApi().speed_get_status()
      if (!result?.success) return
      const s = result.data
      processRunning.value = s.running ?? false
      dllInjected.value = s.injected ?? false
      currentSpeed.value = s.speed ?? 1.0
    } catch (e) {
      console.error('Speed status polling failed:', e)
      getApi().log(`[Speed] 状态轮询失败: ${e}`).catch(() => {})
    }
  }, 2000)
}

onMounted(async () => {
  launcherWorkSpeed.value = (configStore.get('launcher.work.speed') as boolean) ?? false
  launcherSpeedFactor.value = (configStore.get('launcher.work.speed_factor') as number) || 2.0

  // Check if disclaimer was previously accepted
  try {
    const accepted = await getApi().get_config_value('speed.disclaimer_accepted', false) as boolean
    if (accepted) {
      disclaimerAccepted.value = true
    }
  } catch { /* ignore */ }
  if (disclaimerAccepted.value) startPolling()
})

onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

async function acceptDisclaimer() {
  disclaimerAccepted.value = true
  try {
    await getApi().update_config_value('speed.disclaimer_accepted', true)
  } catch { /* ignore */ }
  startPolling()
}

async function doInject() {
  modalStore.create('progress', { title: '注入加速 DLL' })
  await getApi().speed_inject()
}

async function doEject() {
  await getApi().speed_eject()
}

async function setSpeed(factor: number) {
  await getApi().speed_set(factor)
}

async function saveLauncherWorkSpeed() {
  configStore.set('launcher.work.speed', launcherWorkSpeed.value)
  await configStore.save()
}

async function saveLauncherSpeedFactor() {
  configStore.set('launcher.work.speed_factor', launcherSpeedFactor.value)
  await configStore.save()
}
</script>

<template>
  <div>
    <div v-if="!disclaimerAccepted" class="disclaimer">
      <h2><i class="fas fa-exclamation-triangle"></i> 免责声明</h2>
      <p>游戏加速功能通过 DLL 注入修改游戏运行速度，可能导致账号安全风险。使用即表示您已知晓并承担所有风险。</p>
      <button class="primary-btn" @click="acceptDisclaimer">我已了解，继续</button>
    </div>

    <div v-else>
      <div class="section-header">
        <h2 class="section-title"><i class="fas fa-forward"></i> 游戏加速</h2>
        <p class="section-subtitle">调整游戏运行速度</p>
      </div>

      <div class="settings-grid">
        <div class="setting-card">
          <h3 class="setting-title">状态</h3>
          <p>游戏进程: <span :class="processRunning ? 'green' : 'red'">{{ processRunning ? '运行中' : '未运行' }}</span></p>
          <p>DLL: <span :class="dllInjected ? 'green' : 'red'">{{ dllInjected ? '已注入' : '未注入' }}</span></p>
          <p>当前速度: {{ currentSpeed }}x</p>
          <div class="button-group">
            <button class="action-btn" @click="doInject" :disabled="!processRunning || dllInjected">注入 DLL</button>
            <button class="action-btn danger" @click="doEject" :disabled="!dllInjected">卸载 DLL</button>
          </div>
        </div>

        <div class="setting-card" v-if="dllInjected">
          <h3 class="setting-title">速度调节</h3>
          <div class="speed-buttons">
            <button v-for="s in [0.5, 1, 1.5, 2, 3, 5]" :key="s" class="action-btn" @click="setSpeed(s)">
              {{ s }}x
            </button>
          </div>
          <div style="margin-top: 12px">
            <input v-model.number="currentSpeed" type="range" min="0.1" max="10" step="0.1" @change="setSpeed(currentSpeed)" style="width: 100%" />
          </div>
        </div>
      </div>

      <div class="settings-grid" style="margin-top: 16px;">
        <div class="setting-card">
          <h3 class="setting-title">Launcher 模式下的游戏加速设置</h3>
          <div class="form-group">
            <label class="checkbox-label">
              <input id="launcher-work-speed" v-model="launcherWorkSpeed" type="checkbox" @change="saveLauncherWorkSpeed" />
              在 Launcher 模式下启用游戏加速
            </label>
          </div>
          <div class="form-group">
            <label for="launcher-speed-factor">热键切换的速度因子:</label>
            <input id="launcher-speed-factor" v-model.number="launcherSpeedFactor" type="number" min="0.1" max="10" step="0.1" @change="saveLauncherSpeedFactor" />
          </div>
          <p class="speed-info">快捷键：Ctrl+S 切换游戏加速开关，Ctrl+Shift+S 打开速度选择器</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.disclaimer {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  min-height: 60vh;
  text-align: center;
}
.disclaimer h2 { color: #dc2626; margin-bottom: 16px; font-size: 1.3rem; }
.disclaimer p {
  max-width: 500px;
  color: var(--color-text-secondary);
  margin-bottom: 24px;
  line-height: 1.6;
  font-size: 0.9rem;
}

.speed-buttons { display: flex; gap: 8px; flex-wrap: wrap; }
.speed-buttons .action-btn { min-width: 42px; text-align: center; }

.speed-info {
  color: var(--color-text-secondary);
  font-size: 0.85rem;
  margin-top: 8px;
}

.green { color: #16a34a; font-weight: 600; }
.red { color: #9ca3af; font-weight: 600; }
</style>
