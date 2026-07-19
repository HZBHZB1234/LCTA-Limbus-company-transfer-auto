<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getApi } from '@/utils/api'

const router = useRouter()

const pages = ref<Array<{ name: string; title: string; done: boolean }>>([])

onMounted(async () => {
  const relyList = await getApi().get_attr('relyList') as Record<string, string[]> || {}
  pages.value = Object.entries(relyList).map(([name]) => ({
    name,
    title: name,
    done: false,
  }))
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
.section-header { margin-bottom: 24px; }
.section-title { font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.section-title i { color: var(--accent-color); }
.section-subtitle { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }
.settings-grid { display: grid; grid-template-columns: 1fr; gap: 20px; max-width: 500px; }
.setting-card { background: var(--bg-secondary); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color); }
.primary-btn {
  padding: 10px 24px; border-radius: 8px; border: none; background: var(--accent-color); color: white; cursor: pointer; font-size: 14px;
}
.action-btn {
  padding: 10px 24px; border-radius: 8px; border: 1px solid var(--border-color);
  background: var(--bg-primary); color: var(--text-primary); cursor: pointer; font-size: 14px;
}
</style>
