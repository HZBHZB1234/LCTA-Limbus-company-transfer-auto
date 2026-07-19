<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getApi } from '@/utils/api'
import { useModalStore } from '@/stores/modal'

interface CfResult {
  ip: string
  avg_latency_ms: number
  download_mbps: number
  loss_rate: number
}

interface CloudfrontResult {
  domain: string
  ip: string
  median_latency_ms: number
}

const modalStore = useModalStore()

const cfIp = ref<string | null>(null)
const cloudfrontMappings = ref<Array<{ domain: string; ip: string }>>([])
const hostsContent = ref<string>('')

const cfResult = ref<CfResult | null>(null)
const cloudfrontResults = ref<CloudfrontResult[] | null>(null)

const hostsWritten = ref(false)

const statusError = ref(false)

const showWriteReminder = computed(() => {
  return (cfResult.value !== null || cloudfrontResults.value !== null) && !hostsWritten.value
})

onMounted(async () => {
  await refreshStatus()
})

async function refreshStatus() {
  try {
    statusError.value = false
    const result = await getApi().cdn_get_status()
    const wrapper = result as unknown as Record<string, unknown>
    if (!wrapper.success) { statusError.value = true; return }
    const status = wrapper.data as Record<string, unknown>
    cfIp.value = (status.cf_ip as string) ?? null
    cloudfrontMappings.value = (status.cloudfront_mappings as Array<{ domain: string; ip: string }>) ?? []
    hostsContent.value = (status.hosts_content as string) ?? ''

    if (cfResult.value && cfResult.value.ip === status.cf_ip) {
      if (cloudfrontResults.value) {
        const allMatch = cloudfrontResults.value.every((r) =>
          (status.cloudfront_mappings as Array<{ domain: string; ip: string }>)?.some((m) => m.domain === r.domain && m.ip === r.ip),
        )
        if (allMatch) hostsWritten.value = true
      } else {
        hostsWritten.value = true
      }
    } else if (cloudfrontResults.value && !cfResult.value) {
      const allMatch = cloudfrontResults.value.every((r) =>
        (status.cloudfront_mappings as Array<{ domain: string; ip: string }>)?.some((m) => m.domain === r.domain && m.ip === r.ip),
      )
      if (allMatch) hostsWritten.value = true
    }
  } catch (e) {
    console.error('CDN status refresh failed:', e)
    getApi().log(`[CDN] 状态刷新失败: ${e}`).catch(() => {})
    statusError.value = true
  }
}

async function runCloudflare() {
  const mid = modalStore.create('progress', { title: 'Cloudflare CDN 优选' })
  await getApi().cdn_optimize_cloudflare(mid)
  const result = await getApi().cdn_get_status()
  const wrapper = result as unknown as Record<string, unknown>
  const status = (wrapper.success ? wrapper.data : result) as Record<string, unknown>
  cfResult.value = {
    ip: (status.cf_ip as string) ?? '',
    avg_latency_ms: 0,
    download_mbps: 0,
    loss_rate: 0,
  }
  hostsWritten.value = false
  await refreshStatus()
}

async function runCloudFront() {
  const mid = modalStore.create('progress', { title: 'CloudFront CDN 优选' })
  await getApi().cdn_optimize_cloudfront(mid)
  const result = await getApi().cdn_get_status()
  const wrapper = result as unknown as Record<string, unknown>
  const status = (wrapper.success ? wrapper.data : result) as Record<string, unknown>
  cloudfrontResults.value = ((status.cloudfront_mappings as Array<{ domain: string; ip: string }>) ?? []).map((m) => ({
    domain: m.domain,
    ip: m.ip,
    median_latency_ms: 0,
  }))
  hostsWritten.value = false
  await refreshStatus()
}

async function runFull() {
  const mid = modalStore.create('progress', { title: '全量 CDN 优选' })
  await getApi().cdn_full_optimization(mid)
  const result = await getApi().cdn_get_status()
  const wrapper = result as unknown as Record<string, unknown>
  const status = (wrapper.success ? wrapper.data : result) as Record<string, unknown>
  cfResult.value = {
    ip: (status.cf_ip as string) ?? '',
    avg_latency_ms: 0,
    download_mbps: 0,
    loss_rate: 0,
  }
  cloudfrontResults.value = ((status.cloudfront_mappings as Array<{ domain: string; ip: string }>) ?? []).map((m) => ({
    domain: m.domain,
    ip: m.ip,
    median_latency_ms: 0,
  }))
  hostsWritten.value = false
  await refreshStatus()
}

async function writeHosts() {
  const confirmId = modalStore.create('confirm', {
    title: '确认写入 Hosts',
    confirmText: '确认写入',
    onConfirm: async () => {
      modalStore.remove(confirmId)
      const mid = modalStore.create('progress', { title: '写入 Hosts 文件' })
      await getApi().cdn_write_hosts(
        cfResult.value?.ip ?? cfIp.value ?? undefined,
        cloudfrontResults.value ?? cloudfrontMappings.value,
        mid,
      )
      hostsWritten.value = true
      await refreshStatus()
    },
  })
}

async function removeCloudflare() {
  const confirmId = modalStore.create('confirm', {
    title: '移除 Cloudflare 优选',
    confirmText: '确认移除',
    onConfirm: async () => {
      modalStore.remove(confirmId)
      await getApi().cdn_remove_cloudflare()
      cfResult.value = null
      await refreshStatus()
    },
  })
}

async function removeCloudFront() {
  const confirmId = modalStore.create('confirm', {
    title: '移除 CloudFront 优选',
    confirmText: '确认移除',
    onConfirm: async () => {
      modalStore.remove(confirmId)
      await getApi().cdn_remove_cloudfront()
      cloudfrontResults.value = null
      await refreshStatus()
    },
  })
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
        <div class="status-item">
          <span class="status-label">Cloudflare IP:</span>
          <code>{{ cfIp || '未配置' }}</code>
        </div>
        <div class="status-item">
          <span class="status-label">CloudFront 映射:</span>
          <code>{{ cloudfrontMappings.length }} 条域名</code>
        </div>
        <p v-if="statusError" style="color: var(--color-danger); display: flex; align-items: center; gap: 8px;">
          <i class="fas fa-exclamation-triangle"></i>
          加载CDN状态失败
          <button class="action-btn" @click="refreshStatus" style="margin-left: 8px;"><i class="fas fa-redo"></i> 重试</button>
        </p>
        <p v-else-if="!cfIp && cloudfrontMappings.length === 0" style="color: var(--text-secondary)">
          尚未配置 CDN
        </p>
        <div class="button-group" style="margin-top: 12px">
          <button v-if="cfIp" class="action-btn danger" @click="removeCloudflare">
            <i class="fas fa-trash"></i> 移除Cloudflare优选
          </button>
          <button v-if="cloudfrontMappings.length > 0" class="action-btn danger" @click="removeCloudFront">
            <i class="fas fa-trash"></i> 移除CloudFront优选
          </button>
        </div>
      </div>

      <div class="setting-card">
        <h3 class="setting-title">CDN 优选</h3>
        <div class="button-group">
          <button class="action-btn" @click="runCloudflare"><i class="fas fa-bolt"></i> Cloudflare 优选</button>
          <button class="action-btn" @click="runCloudFront"><i class="fas fa-cloud"></i> CloudFront 优选</button>
          <button class="primary-btn" @click="runFull"><i class="fas fa-rocket"></i> 一键全优选</button>
        </div>
      </div>
    </div>

    <div v-if="cfResult || cloudfrontResults" class="settings-grid" style="margin-top: 16px">
      <div class="setting-card">
        <h3 class="setting-title">优选结果</h3>

        <div v-if="cfResult" class="result-section">
          <h4 class="result-subtitle">Cloudflare</h4>
          <table class="result-table">
            <thead>
              <tr>
                <th>IP</th>
                <th>延迟 (ms)</th>
                <th>下载速度 (MB/s)</th>
                <th>丢包率 (%)</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><code>{{ cfResult.ip }}</code></td>
                <td>{{ cfResult.avg_latency_ms.toFixed(1) }}</td>
                <td>{{ cfResult.download_mbps.toFixed(2) }}</td>
                <td>{{ cfResult.loss_rate.toFixed(1) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="cloudfrontResults && cloudfrontResults.length > 0" class="result-section">
          <h4 class="result-subtitle">CloudFront</h4>
          <table class="result-table">
            <thead>
              <tr>
                <th>域名</th>
                <th>IP</th>
                <th>延迟中位数 (ms)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in cloudfrontResults" :key="r.domain">
                <td>{{ r.domain }}</td>
                <td><code>{{ r.ip }}</code></td>
                <td>{{ r.median_latency_ms.toFixed(1) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="showWriteReminder" class="write-reminder">
          <i class="fas fa-exclamation-triangle"></i> 结果尚未写入hosts文件
        </div>

        <div class="button-group" style="margin-top: 12px">
          <button class="primary-btn" @click="writeHosts">
            <i class="fas fa-save"></i> 写入Hosts
          </button>
        </div>
      </div>
    </div>

    <div v-if="hostsContent" class="settings-grid" style="margin-top: 16px">
      <div class="setting-card">
        <h3 class="setting-title">Hosts 内容</h3>
        <pre class="hosts-content"><code>{{ hostsContent }}</code></pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.status-item {
  margin-bottom: 8px;
  display: flex;
  gap: 8px;
  align-items: center;
}

.status-label {
  font-size: 14px;
  color: var(--color-text-secondary);
}

code {
  background: var(--color-bg-primary);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--color-text-primary);
}

.result-section {
  margin-bottom: 16px;
}

.result-subtitle {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--color-text-primary);
}

.result-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.result-table th,
.result-table td {
  padding: 6px 10px;
  text-align: left;
  border-bottom: 1px solid var(--color-border);
}

.result-table th {
  color: var(--color-text-secondary);
  font-weight: 500;
  font-size: 12px;
}

.result-table td code {
  font-size: 12px;
}

.write-reminder {
  margin-top: 12px;
  padding: 8px 12px;
  background: rgba(255, 193, 7, 0.1);
  border: 1px solid rgba(255, 193, 7, 0.3);
  border-radius: 6px;
  color: #e6a817;
  font-size: 13px;
}

.write-reminder i {
  margin-right: 6px;
}

.hosts-content {
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  padding: 12px;
  margin: 0;
  overflow-x: auto;
  font-size: 12px;
  max-height: 300px;
  overflow-y: auto;
}

.hosts-content code {
  background: none;
  padding: 0;
  white-space: pre;
  font-size: 12px;
}

.danger {
  background: rgba(220, 53, 69, 0.1);
  border-color: rgba(220, 53, 69, 0.3);
  color: #dc3545;
}

.danger:hover {
  background: rgba(220, 53, 69, 0.2);
}
</style>
