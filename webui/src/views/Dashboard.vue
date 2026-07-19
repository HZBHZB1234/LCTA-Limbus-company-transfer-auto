<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getApi } from '@/utils/api'
import { useUpdateStore } from '@/stores/update'

const router = useRouter()
const updateStore = useUpdateStore()

const packageStatus = ref('检测中...')
const packageClass = ref('')
const launcherStatus = ref('检测中...')
const launcherClass = ref('')
const updateStatus = ref('检测中...')
const updateClass = ref('')
const apiStatus = ref('检测中...')
const apiClass = ref('')

onMounted(async () => {
  try {
    const [packageResult, configBatch] = await Promise.all([
      getApi().get_installed_packages().catch(() => null),
      getApi().get_config_batch(['auto_check_update', 'game_path', 'launcher_work_update']).catch(() => null),
    ])

    if (packageResult && (packageResult as unknown as Record<string, unknown>).success) {
      const pkg = packageResult as unknown as Record<string, unknown>
      if (pkg.enable) {
        const count = ((pkg.packages as unknown[])?.length) || 0
        packageStatus.value = count > 0 ? `已安装 ${count} 个汉化包` : '未安装汉化包'
        packageClass.value = count > 0 ? 'success' : 'warning'
      } else {
        packageStatus.value = '未启用'
        packageClass.value = 'warning'
      }
    } else {
      packageStatus.value = '无法检测'
    }

    const configValues = configBatch?.config_values || {}
    const launcherMode = configValues['launcher_work_update'] as string
    const gamePath = configValues['game_path'] as string
    if (launcherMode && launcherMode !== 'no') {
      launcherStatus.value = `已配置（${launcherMode}）`
      launcherClass.value = 'success'
    } else if (gamePath) {
      launcherStatus.value = '游戏已设置，未配置启动器'
    } else {
      launcherStatus.value = '未配置'
      launcherClass.value = 'warning'
    }

    const autoUpdate = configValues['auto_check_update']
    if (autoUpdate === true || autoUpdate === 'true') {
      updateStatus.value = '自动更新已开启'
      updateClass.value = 'success'
    } else if (autoUpdate !== undefined && autoUpdate !== null) {
      updateStatus.value = '自动更新未开启'
    } else {
      updateStatus.value = '状态未知'
    }

    try {
      const fullConfig = await getApi().get_attr('config') as Record<string, unknown>
      let apiCount = 0
      if (fullConfig && typeof fullConfig === 'object') {
        for (const key of Object.keys(fullConfig)) {
          if (key.startsWith('api_') && key.endsWith('_key') && fullConfig[key]) {
            apiCount++
          }
        }
      }
      if (apiCount > 0) {
        apiStatus.value = `已配置 ${apiCount} 个服务`
        apiClass.value = 'success'
      } else {
        apiStatus.value = '未配置 API'
        apiClass.value = 'warning'
      }
    } catch (e) {
      console.error('Dashboard API config check failed:', e)
      getApi().log(`[Dashboard] API配置检查失败: ${e}`).catch(() => {})
      apiStatus.value = '点击配置'
    }
  } catch (e) {
    console.error('Dashboard refresh failed:', e)
    getApi().log(`[Dashboard] 首页数据刷新失败: ${e}`).catch(() => {})
  }
})
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-tachometer-alt"></i> 首页
      </h2>
      <p class="section-subtitle">LCTA 工具箱状态总览</p>
    </div>

    <div class="dashboard-grid">
      <div class="dashboard-card status-card" :class="packageClass">
        <div class="dash-card-icon"><i class="fas fa-language"></i></div>
        <div class="dash-card-content">
          <div class="dash-card-label">汉化包状态</div>
          <div class="dash-card-value">{{ packageStatus }}</div>
        </div>
      </div>

      <div class="dashboard-card status-card" :class="launcherClass">
        <div class="dash-card-icon"><i class="fas fa-rocket"></i></div>
        <div class="dash-card-content">
          <div class="dash-card-label">启动器配置</div>
          <div class="dash-card-value">{{ launcherStatus }}</div>
        </div>
      </div>

      <div class="dashboard-card status-card" :class="updateClass">
        <div class="dash-card-icon"><i class="fas fa-sync-alt"></i></div>
        <div class="dash-card-content">
          <div class="dash-card-label">LCTA-AU 更新</div>
          <div class="dash-card-value">{{ updateStatus }}</div>
        </div>
      </div>

      <div class="dashboard-card status-card" :class="apiClass">
        <div class="dash-card-icon"><i class="fas fa-key"></i></div>
        <div class="dash-card-content">
          <div class="dash-card-label">API 配置</div>
          <div class="dash-card-value">{{ apiStatus }}</div>
        </div>
      </div>
    </div>

    <div class="settings-grid" style="margin-top: 24px">
      <div class="setting-card" style="padding: 20px">
        <h3 class="setting-title"><i class="fas fa-bolt"></i> 快速操作</h3>
        <div style="display: flex; flex-wrap: wrap; gap: 8px">
          <button class="action-btn" @click="updateStore.check()">
            <i class="fas fa-sync-alt"></i> 检查更新
          </button>
          <button class="primary-btn" @click="router.push('/elder')">
            <i class="fas fa-play-circle"></i> 设置向导
          </button>
          <button class="action-btn secondary" @click="router.push('/download')">
            <i class="fas fa-download"></i> 下载汉化包
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard-card.warning { border-left-color: var(--color-warning); }
.dashboard-card.success { border-left-color: var(--color-success); }
</style>
