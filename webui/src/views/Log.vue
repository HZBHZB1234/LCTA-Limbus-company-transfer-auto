<script setup lang="ts">
import { computed } from 'vue'
import { useLogStore } from '@/stores/log'

const logStore = useLogStore()
const logEntries = computed(() => logStore.messages)
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-clipboard-list"></i> 日志</h2>
      <p class="section-subtitle">查看系统运行日志</p>
    </div>

    <div class="log-container">
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
.section-header { margin-bottom: 24px; }
.section-title { font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.section-title i { color: var(--accent-color); }
.section-subtitle { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }
.log-container {
  background: var(--bg-secondary); border-radius: 12px; border: 1px solid var(--border-color);
  max-height: 70vh; overflow-y: auto; font-family: 'Consolas', 'Courier New', monospace; font-size: 13px;
}
.log-entry { display: flex; gap: 12px; padding: 6px 16px; border-bottom: 1px solid var(--border-color); }
.log-entry:hover { background: var(--bg-primary); }
.log-entry.error { color: #e74c3c; }
.log-entry.warn { color: #f39c12; }
.log-timestamp { color: var(--text-secondary); flex-shrink: 0; }
.log-level { flex-shrink: 0; width: 60px; }
.log-message { word-break: break-all; }
</style>
