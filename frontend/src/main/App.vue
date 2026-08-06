<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ProductAction, ProductTask } from '../shared/types'
import { useProductStore } from './store'

const store = useProductStore()
const activeArea = ref('home')
const taskCenterOpen = ref(false)
const selectedTask = ref<ProductTask | null>(null)
const search = ref('')
let refreshTimer = 0

const navigation = [
  { id: 'home', label: '首页', icon: '⌂' },
  { id: 'workbench', label: '工作台', icon: '◇' },
  { id: 'library', label: '内容库', icon: '▦' },
  { id: 'automation', label: '自动化', icon: '↻' },
  { id: 'settings', label: '设置', icon: '⚙' },
]

const healthLabel = computed(() => ({ healthy: '状态良好', attention: '建议处理', blocked: '需要设置' }[store.workspace?.health ?? 'blocked']))
const availableActions = computed(() => store.workspace?.recommended_actions ?? [])
const searchResults = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return []
  return availableActions.value.filter((action) => `${action.title}${action.summary}`.toLowerCase().includes(keyword))
})
const launcher = computed(() => store.workspace?.launcher_session)

watch(
  () => store.workspace?.theme,
  (theme) => { if (theme) document.documentElement.dataset.theme = theme },
  { immediate: true },
)

onMounted(async () => {
  await store.bootstrap()
  const targetMap: Record<string, string> = {
    home: 'home', automation: 'automation', launcher: 'automation', settings: 'settings', tasks: 'home',
  }
  activeArea.value = targetMap[store.startTarget] ?? 'home'
  refreshTimer = window.setInterval(() => store.refresh(), 1400)
})

onBeforeUnmount(() => window.clearInterval(refreshTimer))

function openLegacy() {
  window.location.href = '../index.html'
}

async function runAction(action: ProductAction) {
  search.value = ''
  if (action.id === 'install-recommended-localization') {
    activeArea.value = 'workbench'
    await store.prepareInstall()
  } else if (action.id === 'open-launcher') {
    await store.openLauncher()
  } else {
    activeArea.value = 'settings'
  }
}

function inspectTask(task: ProductTask) {
  selectedTask.value = task
  taskCenterOpen.value = true
}

function formatTime(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}
</script>

<template>
  <div class="product-shell">
    <aside class="rail">
      <div class="brand">
        <div class="brand-mark"><span>L</span></div>
        <div><strong>LCTA</strong><small>OPERATIONS DESK</small></div>
      </div>

      <nav class="rail-nav" aria-label="主导航">
        <button
          v-for="item in navigation"
          :key="item.id"
          class="rail-item"
          :class="{ active: activeArea === item.id }"
          @click="activeArea = item.id"
        >
          <span class="rail-icon">{{ item.icon }}</span><span>{{ item.label }}</span>
        </button>
      </nav>

      <div class="rail-footer">
        <button class="legacy-link" @click="openLegacy">打开旧版完整界面</button>
        <div class="connection"><span class="status-dot healthy"></span>本地桥接已连接</div>
      </div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <span class="eyebrow">LIMBUS COMPANY TOOLKIT</span>
          <h1>{{ navigation.find((item) => item.id === activeArea)?.label }}</h1>
        </div>
        <div class="topbar-actions">
          <div class="command-box">
            <span>⌕</span>
            <input v-model="search" placeholder="搜索操作，例如“安装汉化”" />
            <div v-if="searchResults.length" class="command-results">
              <button v-for="action in searchResults" :key="action.id" @click="runAction(action)">
                <strong>{{ action.title }}</strong><small>{{ action.summary }}</small>
              </button>
            </div>
          </div>
          <button class="task-button" @click="taskCenterOpen = true">
            任务 <span v-if="store.runningTasks.length">{{ store.runningTasks.length }}</span>
          </button>
        </div>
      </header>

      <div v-if="store.loading" class="loading-state"><div class="spinner"></div><span>正在读取工作区状态</span></div>
      <div v-else-if="store.error && !store.workspace" class="fatal-state">
        <span class="eyebrow">BRIDGE ERROR</span><h2>无法加载产品状态</h2><p>{{ store.error }}</p>
        <button class="button" @click="store.bootstrap">重试</button>
      </div>

      <template v-else-if="store.workspace">
        <section v-if="activeArea === 'home'" class="page home-page">
          <article class="hero-panel">
            <div class="hero-copy">
              <div class="health-line"><span class="status-dot" :class="store.workspace.health"></span>{{ healthLabel }}</div>
              <h2>{{ store.workspace.headline }}</h2>
              <p v-if="store.recommendedAction">{{ store.recommendedAction.summary }}</p>
              <div class="hero-actions">
                <button v-if="store.recommendedAction" class="button primary" :disabled="store.recommendedAction.availability === 'blocked'" @click="runAction(store.recommendedAction)">
                  {{ store.recommendedAction.title }} <span>→</span>
                </button>
                <button class="button" :disabled="!store.workspace.game.ready" @click="store.openLauncher">打开 Launcher</button>
              </div>
            </div>
            <div class="hero-sigil" aria-hidden="true"><span>LCTA</span><small>05</small></div>
          </article>

          <div class="home-grid">
            <article class="state-board">
              <header><div><span class="eyebrow">WORKSPACE</span><h3>环境概览</h3></div><span class="revision">REV {{ store.workspace.revision }}</span></header>
              <div class="state-row">
                <div><span class="state-index">01</span><strong>游戏目录</strong></div>
                <span :class="store.workspace.game.ready ? 'ok' : 'warning'">{{ store.workspace.game.ready ? '已就绪' : '未配置' }}</span>
              </div>
              <div class="state-row">
                <div><span class="state-index">02</span><strong>汉化内容</strong></div>
                <span :class="store.workspace.localization.installed ? 'ok' : 'warning'">{{ store.workspace.localization.installed ? `${store.workspace.localization.count} 个包` : '尚未安装' }}</span>
              </div>
              <div class="state-row">
                <div><span class="state-index">03</span><strong>Launcher</strong></div>
                <span class="ok">现代 GUI</span>
              </div>
              <p class="path-line">{{ store.workspace.game.path || '等待选择 Limbus Company 安装目录' }}</p>
            </article>

            <article class="launcher-card">
              <header><div><span class="eyebrow">LAUNCH SESSION</span><h3>Launcher 会话</h3></div><span class="status-dot" :class="launcher?.state ?? 'cancelled'"></span></header>
              <template v-if="launcher">
                <strong class="launcher-message">{{ launcher.message }}</strong>
                <p>{{ launcher.game_process?.running ? `游戏正在运行 · PID ${launcher.game_process.pid}` : `最近更新 ${formatTime(launcher.finished_at || launcher.started_at)}` }}</p>
                <div class="mini-phases">
                  <span v-for="phase in launcher.phases.filter((item) => item.state !== 'skipped').slice(0, 6)" :key="phase.id" :class="phase.state"></span>
                </div>
              </template>
              <template v-else><strong class="launcher-message">暂无启动记录</strong><p>打开 Launcher 后，本页会同步显示启动进度与游戏状态。</p></template>
              <button class="button" :disabled="!store.workspace.game.ready" @click="store.openLauncher">{{ launcher?.state === 'game_running' ? '查看启动窗口' : '新建启动会话' }}</button>
            </article>

            <article class="issues-panel">
              <header><span class="eyebrow">RECOMMENDED</span><h3>现在最值得做的事</h3></header>
              <button v-for="action in availableActions" :key="action.id" class="action-line" :disabled="action.availability === 'blocked'" @click="runAction(action)">
                <span><strong>{{ action.title }}</strong><small>{{ action.summary }}</small></span><b>{{ action.recommended ? '推荐' : '›' }}</b>
              </button>
            </article>

            <article class="recent-panel">
              <header><span class="eyebrow">RECENT TASKS</span><h3>最近任务</h3></header>
              <button v-for="task in store.tasks.slice(0, 4)" :key="task.id" class="task-line" @click="inspectTask(task)">
                <span class="status-dot" :class="task.state"></span><span><strong>{{ task.title }}</strong><small>{{ task.message }}</small></span><time>{{ task.progress }}%</time>
              </button>
              <p v-if="!store.tasks.length" class="empty-copy">任务会在后台持续运行，切换页面不会丢失状态。</p>
            </article>
          </div>
        </section>

        <section v-else-if="activeArea === 'workbench'" class="page focus-page">
          <div class="page-intro"><span class="eyebrow">GOAL-BASED WORKFLOW</span><h2>选择目标，而不是先理解设置</h2><p>常用工作被整理为带预检、变更预览和结果反馈的操作计划。</p></div>
          <article class="workflow-card featured">
            <div class="workflow-number">01</div><div class="workflow-copy"><span class="eyebrow">LOCALIZATION</span><h3>让游戏可以直接使用中文</h3><p>自动完成来源选择、下载、字体准备、安装与结果确认。高级来源与字体选项仍可在旧版界面调整。</p>
              <ul><li>安装前检查游戏目录</li><li>执行前展示写入位置</li><li>失败后保留任务日志与恢复建议</li></ul></div>
            <button class="button primary" :disabled="!store.workspace.game.ready || store.busy" @click="store.prepareInstall">生成安装计划</button>
          </article>
          <div class="workflow-secondary">
            <article><span>02</span><h3>更新已有汉化</h3><p>即将迁移到统一动作计划。</p><button class="button" @click="openLegacy">使用旧版功能</button></article>
            <article><span>03</span><h3>翻译与文本美化</h3><p>专业工作流保留完整能力。</p><button class="button" @click="openLegacy">打开专业工具</button></article>
          </div>
        </section>

        <section v-else-if="activeArea === 'library'" class="page focus-page">
          <div class="page-intro"><span class="eyebrow">CONTENT LIBRARY</span><h2>已安装内容集中管理</h2><p>汉化包、模组和规则资产将逐步迁移到统一内容库。</p></div>
          <div class="library-list">
            <article v-for="item in store.workspace.localization.packages" :key="item.id"><div class="library-icon">文</div><div><h3>{{ item.name }}</h3><p>{{ item.path }}</p></div><span class="library-state">已启用</span></article>
            <div v-if="!store.workspace.localization.packages.length" class="empty-library"><strong>暂无已安装汉化</strong><p>完成推荐安装后，内容会自动出现在这里。</p><button class="button primary" :disabled="!store.workspace.game.ready" @click="store.prepareInstall(); activeArea = 'workbench'">安装推荐汉化</button></div>
          </div>
        </section>

        <section v-else-if="activeArea === 'automation'" class="page focus-page">
          <div class="page-intro"><span class="eyebrow">AUTOMATION</span><h2>一次看懂 Launcher 会做什么</h2><p>配置与实际 Launcher 会话共享同一份计划数据，集成开关仍只在 Launcher 配置区域维护。</p></div>
          <article class="automation-board">
            <div class="automation-preview"><span class="preview-title">本次启动计划预览</span><ol>
              <li v-for="(step, index) in launcher?.launch_plan.steps ?? ['检查更新', '启动游戏', '等待游戏结束']" :key="step"><span>{{ String(index + 1).padStart(2, '0') }}</span><strong>{{ step }}</strong></li>
            </ol></div>
            <div class="automation-actions"><h3>现代 Launcher GUI</h3><p>默认显示启动前计划、阶段时间线、游戏运行状态和问题处理入口。</p><button class="button primary" :disabled="!store.workspace.game.ready" @click="store.openLauncher">打开 Launcher</button><button class="button" @click="openLegacy">编辑完整自动化配置</button></div>
          </article>
        </section>

        <section v-else class="page focus-page">
          <div class="page-intro"><span class="eyebrow">PREFERENCES</span><h2>设置只保留长期偏好</h2><p>当前里程碑先提供主题与旧版设置入口，后续按账户、存储、网络和高级参数重组。</p></div>
          <article class="settings-board">
            <div><span class="eyebrow">APPEARANCE</span><h3>界面主题</h3><p>暗色主题采用低饱和黑绿底色、黄铜强调色与克制的深红状态色。</p></div>
            <div class="theme-switch"><button :class="{ active: store.workspace.theme === 'dark' }" @click="store.setTheme('dark')">暗色</button><button :class="{ active: store.workspace.theme === 'light' }" @click="store.setTheme('light')">亮色</button></div>
          </article>
          <article class="settings-board"><div><span class="eyebrow">COMPATIBILITY</span><h3>完整旧版设置</h3><p>在迁移完成前，所有专业参数和工具仍可从旧界面访问。</p></div><button class="button" @click="openLegacy">打开旧版设置</button></article>
        </section>
      </template>
    </main>

    <div v-if="store.plan" class="overlay" @click.self="store.plan = null">
      <section class="plan-sheet">
        <header><div><span class="eyebrow">ACTION PLAN</span><h2>{{ store.plan.title }}</h2></div><button class="button ghost" @click="store.plan = null">关闭</button></header>
        <div class="plan-summary"><div><span>将执行</span><strong>{{ store.plan.steps.length }} 个步骤</strong></div><div><span>预计变更</span><strong>{{ store.plan.changes.length }} 项</strong></div><div><span>执行状态</span><strong>{{ store.plan.can_execute ? '可以开始' : '存在阻塞' }}</strong></div></div>
        <ol class="plan-steps"><li v-for="(step, index) in store.plan.steps" :key="step.id"><span>{{ String(index + 1).padStart(2, '0') }}</span><strong>{{ step.title }}</strong></li></ol>
        <div class="change-box"><h3>执行后会发生什么</h3><p v-for="change in store.plan.changes" :key="change">· {{ change }}</p><p v-for="warning in store.plan.warnings" :key="warning" class="warning">· {{ warning }}</p></div>
        <footer><button class="button" @click="store.plan = null">返回修改</button><button class="button primary" :disabled="!store.plan.can_execute || store.busy" @click="store.executePlan">确认并开始</button></footer>
      </section>
    </div>

    <div v-if="taskCenterOpen" class="drawer-layer" @click.self="taskCenterOpen = false">
      <aside class="task-drawer"><header><div><span class="eyebrow">TASK CENTER</span><h2>全局任务</h2></div><button class="button ghost" @click="taskCenterOpen = false">关闭</button></header>
        <div class="drawer-content"><button v-for="task in store.tasks" :key="task.id" class="drawer-task" :class="{ selected: selectedTask?.id === task.id }" @click="selectedTask = task"><span class="status-dot" :class="task.state"></span><span><strong>{{ task.title }}</strong><small>{{ task.message }}</small></span><b>{{ task.progress }}%</b></button><p v-if="!store.tasks.length" class="empty-copy">暂无任务</p></div>
        <section v-if="selectedTask" class="task-detail"><div class="progress-track"><div class="progress-value" :style="{ width: `${selectedTask.progress}%` }"></div></div><h3>{{ selectedTask.message }}</h3><p>阶段：{{ selectedTask.stage }} · {{ formatTime(selectedTask.updated_at) }}</p><div class="task-log"><p v-for="log in selectedTask.logs.slice(-12)" :key="`${log.time}-${log.message}`">{{ log.message }}</p></div><button v-if="selectedTask.can_cancel" class="button danger" @click="store.cancelTask(selectedTask.id)">取消任务</button></section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.product-shell { min-height: 100vh; display: grid; grid-template-columns: 220px minmax(0, 1fr); }
.rail { position: fixed; inset: 0 auto 0 0; width: 220px; display: flex; flex-direction: column; padding: 24px 16px; background: color-mix(in srgb, var(--bg-soft) 94%, transparent); border-right: 1px solid var(--line); backdrop-filter: blur(18px); z-index: 10; }
.brand { display: flex; align-items: center; gap: 12px; padding: 0 8px 30px; }.brand-mark { width: 42px; height: 48px; display: grid; place-items: center; background: var(--crimson); clip-path: polygon(50% 0, 100% 20%, 88% 82%, 50% 100%, 12% 82%, 0 20%); font-weight: 900; color: #f3dfc2; }.brand strong { font-size: 21px; letter-spacing: .08em; }.brand small { display: block; color: var(--muted); font-size: 9px; letter-spacing: .16em; margin-top: 3px; }
.rail-nav { display: grid; gap: 7px; }.rail-item { width: 100%; border: 1px solid transparent; background: transparent; border-radius: 9px; padding: 11px 12px; display: flex; gap: 12px; align-items: center; color: var(--text-soft); cursor: pointer; text-align: left; }.rail-item:hover { background: var(--surface); color: var(--text); }.rail-item.active { background: linear-gradient(90deg, color-mix(in srgb, var(--crimson) 42%, var(--surface)), var(--surface)); color: var(--text); border-color: color-mix(in srgb, var(--crimson) 50%, var(--line)); }.rail-icon { width: 22px; color: var(--gold-bright); font-size: 18px; }.rail-footer { margin-top: auto; display: grid; gap: 14px; }.legacy-link { border: 0; background: transparent; padding: 0; color: var(--muted); text-align: left; cursor: pointer; }.connection { display: flex; align-items: center; gap: 9px; color: var(--muted); font-size: 12px; }
.workspace { grid-column: 2; min-width: 0; padding: 26px clamp(24px, 4vw, 64px) 70px; }.topbar { min-height: 72px; display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; }.topbar h1 { margin: 4px 0 0; font-size: 24px; }.topbar-actions { display: flex; gap: 10px; align-items: center; }.command-box { position: relative; width: min(34vw, 390px); min-width: 250px; height: 42px; display: flex; gap: 8px; align-items: center; padding: 0 13px; border: 1px solid var(--line); background: var(--surface-glass); border-radius: 9px; }.command-box input { width: 100%; border: 0; outline: 0; color: var(--text); background: transparent; }.command-results { position: absolute; top: 48px; left: 0; right: 0; padding: 8px; background: var(--surface-raised); border: 1px solid var(--line-strong); border-radius: 10px; box-shadow: var(--shadow); z-index: 20; }.command-results button { width: 100%; display: grid; gap: 3px; padding: 10px; color: var(--text); background: transparent; border: 0; border-radius: 7px; text-align: left; cursor: pointer; }.command-results button:hover { background: var(--surface-strong); }.command-results small { color: var(--muted); }.task-button { height: 42px; border: 1px solid var(--line); background: var(--surface-glass); border-radius: 9px; padding: 0 14px; cursor: pointer; }.task-button span { margin-left: 6px; min-width: 20px; display: inline-grid; place-items: center; border-radius: 99px; background: var(--crimson); color: white; }
.loading-state, .fatal-state { min-height: 60vh; display: grid; place-content: center; justify-items: center; gap: 14px; text-align: center; }.page { animation: reveal .32s ease-out; }@keyframes reveal { from { opacity: 0; transform: translateY(7px); } }
.hero-panel { min-height: 280px; position: relative; overflow: hidden; display: flex; align-items: center; justify-content: space-between; gap: 30px; padding: clamp(30px, 5vw, 64px); background: linear-gradient(120deg, color-mix(in srgb, var(--surface) 93%, var(--crimson)), var(--surface-raised)); border: 1px solid var(--line-strong); border-radius: var(--radius-lg); box-shadow: var(--shadow); }.hero-panel::after { content: ""; position: absolute; width: 420px; height: 420px; right: -140px; top: -180px; border: 1px solid rgba(198,164,93,.18); border-radius: 50%; box-shadow: 0 0 0 60px rgba(198,164,93,.025), 0 0 0 120px rgba(198,164,93,.02); }.health-line { display: flex; align-items: center; gap: 10px; color: var(--text-soft); }.hero-copy { max-width: 680px; position: relative; z-index: 1; }.hero-copy h2 { margin: 18px 0 12px; font-size: clamp(32px, 4vw, 56px); line-height: 1.08; letter-spacing: -.045em; }.hero-copy p { color: var(--text-soft); font-size: 16px; }.hero-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 28px; }.hero-sigil { position: relative; z-index: 1; width: 155px; aspect-ratio: 1; border: 1px solid var(--line-strong); display: grid; place-items: center; transform: rotate(45deg); background: rgba(0,0,0,.08); }.hero-sigil span, .hero-sigil small { position: absolute; transform: rotate(-45deg); }.hero-sigil span { font-weight: 900; letter-spacing: .12em; }.hero-sigil small { margin-top: 48px; color: var(--gold); }
.home-grid { display: grid; grid-template-columns: 1.35fr .85fr; gap: 18px; margin-top: 18px; }.home-grid article { border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface-glass); padding: 24px; }.home-grid article > header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }.home-grid h3 { margin: 4px 0 0; }.revision { color: var(--muted); font-size: 10px; letter-spacing: .08em; }.state-row { display: flex; align-items: center; justify-content: space-between; padding: 14px 0; border-top: 1px solid var(--line); }.state-row div { display: flex; align-items: center; gap: 13px; }.state-index { color: var(--gold); font-family: Consolas, monospace; }.ok { color: var(--green); }.warning { color: var(--danger); }.path-line { margin: 12px 0 0; padding: 10px 12px; border-radius: 7px; background: var(--bg-soft); color: var(--muted); font-family: Consolas, monospace; font-size: 11px; word-break: break-all; }.launcher-message { display: block; font-size: 19px; margin-bottom: 7px; }.launcher-card p { color: var(--muted); min-height: 42px; }.mini-phases { display: flex; gap: 5px; margin: 18px 0; }.mini-phases span { height: 5px; flex: 1; border-radius: 99px; background: var(--surface-strong); }.mini-phases span.completed { background: var(--green); }.mini-phases span.running { background: var(--gold); }.mini-phases span.failed { background: var(--danger); }.action-line, .task-line { width: 100%; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 13px 0; border: 0; border-top: 1px solid var(--line); background: transparent; color: var(--text); text-align: left; cursor: pointer; }.action-line > span, .task-line > span:nth-child(2) { display: grid; gap: 3px; }.action-line small, .task-line small { color: var(--muted); }.action-line b { color: var(--gold); }.task-line time { color: var(--muted); }.empty-copy { color: var(--muted); line-height: 1.6; }
.focus-page { max-width: 1160px; }.page-intro { padding: 45px 0 34px; max-width: 760px; }.page-intro h2 { margin: 10px 0; font-size: clamp(30px, 4vw, 48px); letter-spacing: -.035em; }.page-intro p { color: var(--text-soft); font-size: 16px; line-height: 1.7; }.workflow-card { display: grid; grid-template-columns: auto 1fr auto; gap: 28px; align-items: center; padding: 32px; border: 1px solid var(--line-strong); border-radius: var(--radius-lg); background: linear-gradient(120deg, var(--surface-raised), color-mix(in srgb, var(--surface) 84%, var(--crimson))); }.workflow-number { font: 800 44px/1 Consolas, monospace; color: var(--gold); opacity: .8; }.workflow-copy h3 { margin: 7px 0; font-size: 25px; }.workflow-copy p, .workflow-copy li { color: var(--text-soft); }.workflow-copy ul { display: flex; flex-wrap: wrap; gap: 8px 24px; padding-left: 18px; }.workflow-secondary { display: grid; grid-template-columns: repeat(2,1fr); gap: 16px; margin-top: 16px; }.workflow-secondary article, .settings-board { padding: 25px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface-glass); }.workflow-secondary span { color: var(--gold); }.workflow-secondary p, .settings-board p { color: var(--muted); }.library-list { display: grid; gap: 10px; }.library-list article { display: grid; grid-template-columns: auto 1fr auto; gap: 16px; align-items: center; padding: 18px; border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface-glass); }.library-icon { width: 44px; height: 44px; display: grid; place-items: center; border: 1px solid var(--gold); color: var(--gold); transform: rotate(45deg); }.library-icon::first-letter { transform: rotate(-45deg); }.library-list h3 { margin: 0 0 5px; }.library-list p { margin: 0; color: var(--muted); font-size: 12px; word-break: break-all; }.library-state { color: var(--green); }.empty-library { padding: 60px; text-align: center; border: 1px dashed var(--line-strong); border-radius: var(--radius-lg); }.automation-board { display: grid; grid-template-columns: 1.2fr .8fr; border: 1px solid var(--line-strong); border-radius: var(--radius-lg); overflow: hidden; }.automation-preview, .automation-actions { padding: 32px; background: var(--surface-glass); }.automation-actions { background: linear-gradient(145deg, var(--surface-raised), color-mix(in srgb, var(--surface) 86%, var(--crimson))); }.automation-actions p { color: var(--text-soft); line-height: 1.7; }.automation-actions .button { width: 100%; margin-top: 10px; }.preview-title { color: var(--muted); }.automation-preview ol { list-style: none; padding: 0; margin: 20px 0 0; }.automation-preview li { display: flex; gap: 16px; padding: 15px 0; border-top: 1px solid var(--line); }.automation-preview li span { color: var(--gold); font-family: Consolas, monospace; }.settings-board { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 14px; }.theme-switch { display: flex; padding: 4px; border-radius: 9px; background: var(--bg-soft); }.theme-switch button { border: 0; border-radius: 7px; padding: 10px 17px; color: var(--muted); background: transparent; cursor: pointer; }.theme-switch button.active { color: var(--gold-ink); background: var(--gold); font-weight: 700; }
.overlay, .drawer-layer { position: fixed; inset: 0; z-index: 50; display: grid; place-items: center; padding: 28px; background: rgba(4,6,5,.7); backdrop-filter: blur(10px); }.plan-sheet { width: min(760px, 100%); max-height: 90vh; overflow: auto; padding: 30px; border: 1px solid var(--line-strong); border-radius: var(--radius-lg); background: var(--surface-raised); box-shadow: var(--shadow); }.plan-sheet > header, .plan-sheet > footer { display: flex; justify-content: space-between; align-items: center; gap: 16px; }.plan-sheet h2 { margin: 5px 0 0; }.plan-summary { display: grid; grid-template-columns: repeat(3,1fr); gap: 10px; margin: 24px 0; }.plan-summary div { display: grid; gap: 5px; padding: 14px; background: var(--bg-soft); border-radius: 9px; }.plan-summary span { color: var(--muted); font-size: 12px; }.plan-steps { list-style: none; padding: 0; }.plan-steps li { display: flex; gap: 18px; padding: 15px 0; border-top: 1px solid var(--line); }.plan-steps span { color: var(--gold); font-family: Consolas, monospace; }.change-box { margin: 20px 0; padding: 18px; border-left: 3px solid var(--gold); background: var(--bg-soft); }.change-box h3 { margin-top: 0; }.change-box p { color: var(--text-soft); }.change-box .warning { color: var(--danger); }
.drawer-layer { place-items: stretch end; padding: 0; }.task-drawer { width: min(560px, 100vw); height: 100%; display: grid; grid-template-rows: auto minmax(180px, 1fr) auto; background: var(--surface-raised); border-left: 1px solid var(--line-strong); box-shadow: var(--shadow); }.task-drawer > header { display: flex; justify-content: space-between; padding: 24px; border-bottom: 1px solid var(--line); }.task-drawer h2 { margin: 4px 0 0; }.drawer-content { overflow: auto; padding: 10px 16px; }.drawer-task { width: 100%; display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 12px; padding: 13px 10px; border: 1px solid transparent; border-radius: 9px; background: transparent; color: var(--text); text-align: left; cursor: pointer; }.drawer-task.selected { border-color: var(--line-strong); background: var(--surface-strong); }.drawer-task span:nth-child(2) { display: grid; gap: 3px; }.drawer-task small { color: var(--muted); }.task-detail { padding: 20px 24px 26px; border-top: 1px solid var(--line); background: var(--bg-soft); }.task-detail p { color: var(--muted); }.task-log { max-height: 140px; overflow: auto; padding: 10px; margin: 15px 0; background: #090b0a; color: #aaa89f; border-radius: 8px; font: 11px/1.5 Consolas, monospace; }.task-log p { margin: 0 0 4px; color: inherit; }
@media (max-width: 980px) { .product-shell { grid-template-columns: 78px 1fr; }.rail { width: 78px; padding-inline: 10px; }.brand > div:last-child, .rail-item span:last-child, .legacy-link, .connection { display: none; }.brand { padding-inline: 6px; }.rail-item { justify-content: center; }.workspace { grid-column: 2; }.home-grid, .automation-board { grid-template-columns: 1fr; }.workflow-card { grid-template-columns: auto 1fr; }.workflow-card > .button { grid-column: 1 / -1; }.hero-sigil { display: none; } }
@media (max-width: 720px) { .product-shell { display: block; }.rail { position: fixed; inset: auto 0 0; width: auto; height: 66px; flex-direction: row; padding: 8px; border: 0; border-top: 1px solid var(--line); }.brand, .rail-footer { display: none; }.rail-nav { width: 100%; display: grid; grid-template-columns: repeat(5,1fr); }.rail-item { padding: 8px; display: grid; gap: 2px; font-size: 10px; }.rail-item span:last-child { display: block; }.rail-icon { width: auto; }.workspace { padding: 18px 16px 90px; }.topbar { display: grid; }.topbar-actions { width: 100%; }.command-box { width: 100%; min-width: 0; }.hero-panel { padding: 28px 22px; }.hero-copy h2 { font-size: 35px; }.home-grid, .workflow-secondary { grid-template-columns: 1fr; }.workflow-card { grid-template-columns: 1fr; }.workflow-number { font-size: 28px; }.settings-board { display: grid; }.plan-summary { grid-template-columns: 1fr; } }
</style>
