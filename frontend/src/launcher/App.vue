<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { LauncherSession } from '../shared/types'
import { useLauncherStore } from './store'

const store = useLauncherStore()
const logsOpen = ref(false)
const closePanelOpen = ref(false)
let refreshTimer = 0

const stateMeta = computed(() => {
  const state = store.session?.state ?? 'ready'
  return {
    ready: ['启动计划已准备', '确认本次步骤后开始启动'],
    running: ['正在执行启动计划', '可以继续查看阶段详情或取消'],
    game_running: ['Limbus Company 正在运行', 'Launcher 会在游戏退出后完成清理'],
    cancelling: ['正在停止', '等待当前步骤安全结束'],
    succeeded: ['本次会话已结束', '所有必要的退出清理已完成'],
    cancelled: ['启动已取消', '可以修改计划后重新开始'],
    failed: ['启动遇到问题', '查看失败步骤或打开完整 LCTA 修复'],
  }[state] ?? ['Launcher', store.session?.message ?? '']
})
const activePhase = computed(() => store.session?.phases.find((phase) => phase.id === store.session?.current_phase))
const completedCount = computed(() => store.session?.phases.filter((phase) => phase.state === 'completed').length ?? 0)
const visiblePhases = computed(() => store.session?.phases.filter((phase) => phase.state !== 'skipped') ?? [])

function acceptSession(event: Event) {
  store.session = (event as CustomEvent<LauncherSession>).detail
}

onMounted(async () => {
  document.documentElement.dataset.theme = 'dark'
  window.addEventListener('lcta:launcher-session-changed', acceptSession)
  await store.refresh()
  refreshTimer = window.setInterval(() => store.refresh(), 700)
})

onBeforeUnmount(() => {
  window.clearInterval(refreshTimer)
  window.removeEventListener('lcta:launcher-session-changed', acceptSession)
})

function formatLogTime(value: string) {
  return new Date(value).toLocaleTimeString('zh-CN', { hour12: false })
}
</script>

<template>
  <div class="launcher-shell">
    <header class="launcher-header">
      <div class="launcher-brand"><div class="brand-seal">L</div><div><strong>LCTA LAUNCHER</strong><small>SESSION CONTROL</small></div></div>
      <div class="header-actions"><button class="icon-button" title="打开完整 LCTA" @click="store.openMain('home')">↗</button><button class="icon-button" title="关闭" @click="closePanelOpen = true">×</button></div>
    </header>

    <main v-if="store.session" class="launcher-content">
      <section class="session-hero" :class="store.session.state">
        <div class="session-copy"><span class="eyebrow">SESSION {{ store.session.id.slice(0, 8).toUpperCase() }}</span><h1>{{ stateMeta[0] }}</h1><p>{{ activePhase?.message || store.session.message || stateMeta[1] }}</p>
          <div class="session-actions">
            <button v-if="['ready', 'cancelled', 'failed', 'succeeded'].includes(store.session.state)" class="button primary" :disabled="store.busy" @click="store.start"><span v-if="store.busy" class="spinner"></span>{{ store.session.state === 'ready' ? '开始启动' : '重新运行' }}</button>
            <button v-if="store.session.can_cancel" class="button danger" @click="store.cancel">取消启动</button>
            <button v-if="store.session.state === 'failed'" class="button" @click="store.openMain('tasks')">打开 LCTA 修复</button>
            <button v-if="store.session.state === 'game_running'" class="button" @click="store.openMain('automation')">编辑下次启动计划</button>
          </div>
        </div>
        <div class="session-emblem"><div class="emblem-core"><span>{{ store.session.state === 'game_running' ? 'RUN' : String(completedCount).padStart(2, '0') }}</span><small>{{ store.session.state === 'game_running' ? `PID ${store.session.game_process?.pid}` : `/${visiblePhases.length}` }}</small></div></div>
      </section>

      <section class="session-grid">
        <article class="timeline-panel">
          <header><div><span class="eyebrow">LAUNCH PLAN</span><h2>启动阶段</h2></div><span class="phase-count">{{ completedCount }} / {{ visiblePhases.length }}</span></header>
          <ol class="timeline">
            <li v-for="(phase, index) in visiblePhases" :key="phase.id" :class="phase.state">
              <div class="phase-marker"><span v-if="phase.state === 'completed'">✓</span><span v-else-if="phase.state === 'failed'">!</span><span v-else>{{ String(index + 1).padStart(2, '0') }}</span></div>
              <div class="phase-copy"><strong>{{ phase.title }}</strong><small>{{ phase.message || ({ pending: '等待执行', running: '正在执行', completed: '已完成', failed: '需要处理', skipped: '已跳过' }[phase.state] ?? '') }}</small>
                <div v-if="phase.state === 'running'" class="progress-track"><div class="progress-value" :class="{ indeterminate: phase.progress == null }" :style="phase.progress == null ? {} : { width: `${phase.progress}%` }"></div></div>
              </div>
              <span class="phase-state">{{ phase.state === 'completed' ? '完成' : phase.state === 'running' ? '进行中' : phase.state === 'failed' ? '失败' : '等待' }}</span>
            </li>
          </ol>
        </article>

        <aside class="side-stack">
          <article class="context-panel">
            <span class="eyebrow">CURRENT CONTEXT</span><h2>{{ activePhase?.title || '启动前检查' }}</h2>
            <dl><div><dt>会话状态</dt><dd>{{ store.session.state }}</dd></div><div><dt>游戏进程</dt><dd>{{ store.session.game_process?.running ? `PID ${store.session.game_process.pid}` : '尚未运行' }}</dd></div><div><dt>启用能力</dt><dd>{{ store.session.enabled_features.length }} 项</dd></div></dl>
          </article>
          <article class="feature-panel"><span class="eyebrow">ENABLED</span><h2>本次启用</h2><div class="feature-tags"><span v-for="feature in store.session.enabled_features" :key="feature">{{ feature }}</span><span v-if="!store.session.enabled_features.length" class="muted">仅执行基础启动</span></div></article>
          <button class="log-entry" @click="logsOpen = true"><span><strong>运行日志</strong><small>{{ store.session.logs.length }} 条记录</small></span><b>查看 →</b></button>
        </aside>
      </section>
    </main>

    <div v-else class="launcher-loading"><div class="spinner"></div><p>{{ store.error || '正在准备 Launcher 会话' }}</p></div>

    <div v-if="logsOpen" class="drawer-layer" @click.self="logsOpen = false">
      <aside class="log-drawer"><header><div><span class="eyebrow">SESSION LOG</span><h2>运行日志</h2></div><button class="button ghost" @click="logsOpen = false">关闭</button></header><div class="log-stream"><p v-for="log in store.session?.logs ?? []" :key="`${log.time}-${log.message}`"><time>{{ formatLogTime(log.time) }}</time><span>{{ log.message }}</span></p><div v-if="!store.session?.logs.length" class="empty-log">启动后，关键运行信息会显示在这里。</div></div></aside>
    </div>

    <div v-if="closePanelOpen" class="modal-layer" @click.self="closePanelOpen = false">
      <section class="close-panel"><span class="eyebrow">CLOSE LAUNCHER</span><h2>{{ store.session?.state === 'game_running' ? '游戏仍在运行' : '关闭启动窗口？' }}</h2><p v-if="store.session?.state === 'game_running'">可以仅关闭 Launcher 并让游戏继续运行，也可以结束游戏后退出。</p><p v-else-if="store.session?.can_cancel">关闭窗口会停止尚未完成的启动步骤。</p><p v-else>当前会话状态已保存，可以安全关闭窗口。</p>
        <div class="close-actions"><button v-if="store.session?.state === 'game_running'" class="button danger" @click="store.close('stop-game')">结束游戏并退出</button><button class="button primary" @click="store.close(store.session?.can_cancel ? 'cancel' : 'close')">{{ store.session?.state === 'game_running' ? '仅关闭 Launcher' : '确认关闭' }}</button><button class="button" @click="closePanelOpen = false">返回</button></div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.launcher-shell { min-height: 100vh; padding: 0 34px 34px; }.launcher-header { height: 78px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--line); }.launcher-brand { display: flex; align-items: center; gap: 12px; }.launcher-brand strong { letter-spacing: .12em; }.launcher-brand small { display: block; margin-top: 3px; color: var(--muted); font-size: 9px; letter-spacing: .18em; }.brand-seal { width: 36px; height: 42px; display: grid; place-items: center; background: var(--crimson); clip-path: polygon(50% 0, 100% 20%, 88% 82%, 50% 100%, 12% 82%, 0 20%); font-weight: 900; }.header-actions { display: flex; gap: 8px; }.icon-button { width: 36px; height: 36px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); cursor: pointer; font-size: 18px; }.launcher-content { max-width: 1180px; margin: 0 auto; }.session-hero { min-height: 230px; display: flex; align-items: center; justify-content: space-between; gap: 30px; padding: 34px 44px; margin-top: 24px; border: 1px solid var(--line-strong); border-radius: var(--radius-lg); background: linear-gradient(120deg, color-mix(in srgb, var(--surface-raised) 92%, var(--crimson)), var(--surface)); box-shadow: var(--shadow); overflow: hidden; }.session-hero.game_running { background: linear-gradient(120deg, color-mix(in srgb, var(--surface-raised) 88%, var(--green)), var(--surface)); }.session-hero.failed { background: linear-gradient(120deg, color-mix(in srgb, var(--surface-raised) 80%, var(--crimson)), var(--surface)); }.session-copy { max-width: 650px; }.session-copy h1 { margin: 12px 0 9px; font-size: clamp(32px, 5vw, 52px); line-height: 1.05; letter-spacing: -.04em; }.session-copy p { color: var(--text-soft); }.session-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 24px; }.session-emblem { width: 152px; height: 152px; display: grid; place-items: center; border: 1px solid var(--line-strong); transform: rotate(45deg); background: rgba(0,0,0,.08); }.emblem-core { transform: rotate(-45deg); display: grid; place-items: center; }.emblem-core span { font: 800 34px/1 Consolas, monospace; color: var(--gold-bright); }.emblem-core small { margin-top: 8px; color: var(--muted); font-family: Consolas, monospace; }.session-grid { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(270px, .65fr); gap: 16px; margin-top: 16px; }.timeline-panel, .context-panel, .feature-panel, .log-entry { border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface-glass); }.timeline-panel { padding: 26px; }.timeline-panel > header { display: flex; justify-content: space-between; align-items: center; }.timeline-panel h2, .side-stack h2 { margin: 5px 0 0; }.phase-count { color: var(--gold); font-family: Consolas, monospace; }.timeline { list-style: none; padding: 0; margin: 22px 0 0; }.timeline li { position: relative; display: grid; grid-template-columns: auto 1fr auto; align-items: start; gap: 15px; min-height: 70px; }.timeline li:not(:last-child)::after { content: ""; position: absolute; left: 17px; top: 36px; bottom: 0; width: 1px; background: var(--line-strong); }.phase-marker { position: relative; z-index: 1; width: 35px; height: 35px; display: grid; place-items: center; border: 1px solid var(--line-strong); border-radius: 50%; background: var(--surface-raised); color: var(--muted); font: 11px Consolas, monospace; }.timeline li.running .phase-marker { border-color: var(--gold); color: var(--gold); box-shadow: 0 0 0 5px color-mix(in srgb, var(--gold) 12%, transparent); }.timeline li.completed .phase-marker { border-color: var(--green); background: var(--green); color: #0b120d; }.timeline li.failed .phase-marker { border-color: var(--danger); background: var(--danger); color: white; }.phase-copy { display: grid; gap: 5px; padding-top: 3px; }.phase-copy small { color: var(--muted); }.phase-copy .progress-track { margin-top: 6px; }.phase-state { padding-top: 5px; color: var(--muted); font-size: 12px; }.timeline li.running .phase-state { color: var(--gold); }.timeline li.completed .phase-state { color: var(--green); }.timeline li.failed .phase-state { color: var(--danger); }.progress-value.indeterminate { width: 36%; animation: slide 1.3s ease-in-out infinite; }@keyframes slide { 0% { transform: translateX(-120%); } 100% { transform: translateX(320%); } }.side-stack { display: grid; align-content: start; gap: 16px; }.context-panel, .feature-panel { padding: 23px; }.context-panel dl { margin: 18px 0 0; }.context-panel dl div { display: flex; justify-content: space-between; padding: 11px 0; border-top: 1px solid var(--line); }.context-panel dt { color: var(--muted); }.context-panel dd { margin: 0; }.feature-tags { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 16px; }.feature-tags span { padding: 7px 9px; border: 1px solid var(--line); border-radius: 6px; background: var(--surface-strong); font-size: 12px; }.log-entry { width: 100%; display: flex; align-items: center; justify-content: space-between; padding: 18px 22px; color: var(--text); cursor: pointer; text-align: left; }.log-entry span { display: grid; gap: 4px; }.log-entry small { color: var(--muted); }.log-entry b { color: var(--gold); }.launcher-loading { min-height: 70vh; display: grid; place-content: center; justify-items: center; gap: 12px; }.drawer-layer, .modal-layer { position: fixed; inset: 0; z-index: 30; display: grid; background: rgba(4,6,5,.72); backdrop-filter: blur(9px); }.drawer-layer { place-items: stretch end; }.log-drawer { width: min(590px, 100vw); height: 100%; background: var(--surface-raised); border-left: 1px solid var(--line-strong); box-shadow: var(--shadow); }.log-drawer header { display: flex; justify-content: space-between; padding: 25px; border-bottom: 1px solid var(--line); }.log-drawer h2 { margin: 4px 0 0; }.log-stream { height: calc(100% - 94px); overflow: auto; padding: 18px 24px; background: #090b0a; font: 12px/1.55 Consolas, monospace; }.log-stream p { display: grid; grid-template-columns: 72px 1fr; gap: 12px; margin: 0 0 8px; color: #b4b1a7; }.log-stream time { color: #686c67; }.empty-log { color: #686c67; text-align: center; margin-top: 25vh; }.modal-layer { place-items: center; padding: 24px; }.close-panel { width: min(510px, 100%); padding: 30px; border: 1px solid var(--line-strong); border-radius: var(--radius-lg); background: var(--surface-raised); box-shadow: var(--shadow); }.close-panel h2 { margin: 10px 0; font-size: 30px; }.close-panel p { color: var(--text-soft); line-height: 1.7; }.close-actions { display: grid; gap: 9px; margin-top: 24px; }
@media (max-width: 820px) { .launcher-shell { padding-inline: 18px; }.session-hero { padding: 28px; }.session-emblem { display: none; }.session-grid { grid-template-columns: 1fr; } }
@media (max-width: 560px) { .launcher-header { height: 66px; }.session-hero { margin-top: 16px; padding: 24px 20px; }.session-copy h1 { font-size: 34px; }.session-actions .button { width: 100%; }.timeline-panel { padding: 20px 15px; }.phase-state { display: none; }.timeline li { grid-template-columns: auto 1fr; } }
</style>
