<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getApi } from '@/utils/api'

const router = useRouter()

const pages = ref<Array<{ name: string; title: string; done: boolean }>>([])

onMounted(async () => {
  try {
    const relyList = await getApi().get_attr('relyList') as Record<string, string[]> || {}
    pages.value = Object.entries(relyList).map(([name]) => ({
      name,
      title: name,
      done: false,
    }))
  } catch (e) {
    console.error('Elder relyList load failed:', e)
    getApi().log(`[Elder] 设置向导列表加载失败: ${e}`).catch(() => {})
  }
})
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-compass"></i> 设置向导</h2>
      <p class="section-subtitle">引导完成 LCTA 初始设置</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card">
        <p style="color: var(--text-secondary)">
          设置向导将引导你完成游戏路径设置、API 配置、汉化包下载等初始步骤。
        </p>
        <div style="margin-top: 20px">
          <button class="primary-btn" @click="router.push('/settings')">
            <i class="fas fa-wrench"></i> 前往设置
          </button>
          <button class="action-btn" style="margin-left: 8px" @click="router.push('/download')">
            <i class="fas fa-download"></i> 前往下载
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Elder view uses shared global classes from main.css */
</style>
