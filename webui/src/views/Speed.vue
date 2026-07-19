<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { getApi } from '@/utils/api'
import { useModalStore } from '@/stores/modal'

const modalStore = useModalStore()

const disclaimerAccepted = ref(false)
const processRunning = ref(false)
const dllInjected = ref(false)
const currentSpeed = ref(1.0)
let pollTimer: ReturnType<typeof setInterval> | null = null

function startPolling() {
  pollTimer = setInterval(async () => {
    try {
      const status = await getApi().speed_get_status()
      processRunning.value = status.process_running
      dllInjected.value = status.dll_injected
      currentSpeed.value = status.current_speed
    } catch { /* ignore */ }
  }, 2000)
}

onMounted(() => { if (disclaimerAccepted.value) startPolling() })
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

function acceptDisclaimer() {
  disclaimerAccepted.value = true
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
    </div>
  </div>
</template>

<style scoped>
.disclaimer { max-width: 500px; margin: 40px auto; text-align: center; padding: 32px; background: var(--bg-secondary); border-radius: 12px; }
.disclaimer h2 { color: #f39c12; margin-bottom: 16px; }
.disclaimer p { color: var(--text-secondary); margin-bottom: 24px; line-height: 1.6; }
.section-header { margin-bottom: 24px; }
.section-title { font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.section-title i { color: var(--accent-color); }
.section-subtitle { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }
.settings-grid { display: grid; grid-template-columns: 1fr; gap: 20px; max-width: 500px; }
.setting-card { background: var(--bg-secondary); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color); }
.setting-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
.green { color: #27ae60; } .red { color: #e74c3c; }
.button-group { display: flex; gap: 8px; margin-top: 12px; }
.speed-buttons { display: flex; gap: 8px; flex-wrap: wrap; }
.action-btn {
  padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border-color);
  background: var(--bg-primary); color: var(--text-primary); cursor: pointer; font-size: 14px;
}
.action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.action-btn.danger { color: #e74c3c; }
.primary-btn { padding: 10px 24px; border-radius: 8px; border: none; background: var(--accent-color); color: white; cursor: pointer; font-size: 14px; }
</style>
