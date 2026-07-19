<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { useLogStore } from '@/stores/log'

const logStore = useLogStore()
const logEntries = computed(() => logStore.messages)
const logContainer = ref<HTMLElement | null>(null)

watch(logEntries, async () => {
  await nextTick()
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
})
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-clipboard-list"></i> 日志</h2>
      <p class="section-subtitle">查看系统运行日志</p>
    </div>

    <div ref="logContainer" class="log-container">
      <div v-if="logEntries.length === 0" style="color: var(--text-secondary); padding: 20px">
        暂无日志记录
      </div>
      <div v-for="(entry, i) in logEntries" :key="i" class="log-entry" :class="entry.level">
        <span class="log-timestamp">[{{ entry.timestamp }}]</span>
        <span class="log-level">[{{ entry.level.toUpperCase() }}]</span>
        <span class="log-message">{{ entry.message }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.log-container {
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  overflow: hidden;
}
.log-entry {
  padding: 8px 12px;
  margin: 0;
  border-bottom: 1px solid var(--color-border-light);
  display: grid;
  grid-template-columns: auto auto 1fr;
  gap: var(--spacing-sm);
  align-items: center;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  animation: slideIn 0.3s ease;
}
.log-entry:hover { background: var(--color-bg-primary); }
.log-entry.info { border-left: 4px solid var(--color-info); }
.log-entry.warning { border-left: 4px solid var(--color-warning); }
.log-entry.warn { border-left: 4px solid var(--color-warning); }
.log-entry.error { border-left: 4px solid var(--color-danger); }
.log-entry.success { border-left: 4px solid var(--color-success); }
.log-timestamp {
  color: var(--color-text-secondary);
  font-size: 11px;
  min-width: 160px;
  flex-shrink: 0;
}
.log-level {
  font-weight: 600;
  font-size: 11px;
  min-width: 60px;
  flex-shrink: 0;
}
.log-message {
  color: var(--color-text-primary);
  word-break: break-all;
}
</style>
