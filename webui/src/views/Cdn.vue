<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getApi } from '@/utils/api'
import { useModalStore } from '@/stores/modal'

const modalStore = useModalStore()

const cfIp = ref<string | null>(null)
const cloudfrontMappings = ref<Array<{ domain: string; ip: string }>>([])

onMounted(async () => {
  await refreshStatus()
})

async function refreshStatus() {
  try {
    const status = await getApi().cdn_get_status()
    cfIp.value = status.cf_ip
    cloudfrontMappings.value = status.cloudfront_mappings
  } catch { /* ignore */ }
}

async function runCloudflare() {
  const mid = modalStore.create('progress', { title: 'Cloudflare CDN 优选' })
  await getApi().cdn_optimize_cloudflare(mid)
  await refreshStatus()
}

async function runCloudFront() {
  const mid = modalStore.create('progress', { title: 'CloudFront CDN 优选' })
  await getApi().cdn_optimize_cloudfront(mid)
  await refreshStatus()
}

async function runFull() {
  const mid = modalStore.create('progress', { title: '全量 CDN 优选' })
  await getApi().cdn_full_optimization(mid)
  await refreshStatus()
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-bolt"></i> CDN优选</h2>
      <p class="section-subtitle">优化游戏使用的 CDN 节点，降低延迟</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card">
        <h3 class="setting-title">当前状态</h3>
        <div v-if="cfIp" class="status-item">
          <span class="status-label">Cloudflare IP:</span>
          <code>{{ cfIp }}</code>
        </div>
        <div v-if="cloudfrontMappings.length > 0" class="status-item">
          <span class="status-label">CloudFront:</span>
          <code>{{ cloudfrontMappings.length }} 条映射</code>
        </div>
        <p v-if="!cfIp && cloudfrontMappings.length === 0" style="color: var(--text-secondary)">尚未配置 CDN</p>
      </div>

      <div class="setting-card">
        <h3 class="setting-title">CDN 优选</h3>
        <div class="button-group">
          <button class="action-btn" @click="runCloudflare"><i class="fas fa-bolt"></i> Cloudflare 优选</button>
          <button class="action-btn" @click="runCloudFront"><i class="fas fa-cloud"></i> CloudFront 优选</button>
          <button class="primary-btn" @click="runFull"><i class="fas fa-rocket"></i> 全量优化</button>
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
.settings-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 20px; }
.setting-card { background: var(--bg-secondary); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color); }
.setting-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
.status-item { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
.status-label { font-size: 14px; color: var(--text-secondary); }
code { background: var(--bg-primary); padding: 2px 8px; border-radius: 4px; font-size: 13px; }
.button-group { display: flex; gap: 8px; flex-wrap: wrap; }
.action-btn {
  padding: 10px 20px; border-radius: 8px; border: 1px solid var(--border-color);
  background: var(--bg-primary); color: var(--text-primary); cursor: pointer; font-size: 14px;
}
.action-btn:hover { background: var(--bg-secondary); }
.primary-btn {
  padding: 10px 24px; border-radius: 8px; border: none; background: var(--accent-color); color: white; cursor: pointer; font-size: 14px;
}
</style>
