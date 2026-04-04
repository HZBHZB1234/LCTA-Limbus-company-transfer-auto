<template>
  <div class="log-view">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-clipboard-list"></i> 日志
      </h2>
      <p class="section-subtitle">查看系统运行日志</p>
    </div>

    <div class="log-container">
      <div class="log-controls">
        <button class="log-control-btn" :class="{ active: logLevel === 'all' }" @click="logLevel = 'all'">全部</button>
        <button class="log-control-btn" :class="{ active: logLevel === 'info' }" @click="logLevel = 'info'">信息</button>
        <button class="log-control-btn" :class="{ active: logLevel === 'warning' }" @click="logLevel = 'warning'">警告</button>
        <button class="log-control-btn" :class="{ active: logLevel === 'error' }" @click="logLevel = 'error'">错误</button>
        <button class="log-control-btn" :class="{ active: logLevel === 'success' }" @click="logLevel = 'success'">成功</button>
        <div class="log-control-spacer"></div>
        <button class="log-control-btn" @click="clearLogs">清空</button>
        <button class="log-control-btn" @click="scrollToBottom">滚动到底部</button>
      </div>
      <div class="log-display" ref="logContainer">
        <div
          v-for="(log, idx) in filteredLogs"
          :key="idx"
          class="log-entry"
          :class="log.level"
        >
          <div class="log-timestamp">{{ log.formattedTime }}</div>
          <div class="log-level">[{{ log.level.toUpperCase() }}]</div>
          <div class="log-message">{{ log.message }}</div>
        </div>
        <div v-if="filteredLogs.length === 0" class="log-empty">暂无日志</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useLogStore } from '@/stores/log'

const logStore = useLogStore()
const logContainer = ref(null)
const logLevel = ref('all')

const filteredLogs = computed(() => {
  if (logLevel.value === 'all') return logStore.logs
  return logStore.logs.filter(log => log.level === logLevel.value)
})

function clearLogs() {
  logStore.clearLogs()
}

function scrollToBottom() {
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
}

// 监听新日志自动滚动
let autoScroll = true
function onScroll() {
  if (!logContainer.value) return
  const isAtBottom = logContainer.value.scrollHeight - logContainer.value.scrollTop <= logContainer.value.clientHeight + 50
  autoScroll = isAtBottom
}

watch(filteredLogs, () => {
  if (autoScroll) {
    nextTick(scrollToBottom)
  }
})

function onLogUpdated() {
  if (autoScroll) {
    nextTick(scrollToBottom)
  }
}

onMounted(() => {
  if (logContainer.value) {
    logContainer.value.addEventListener('scroll', onScroll)
  }
  window.addEventListener('log-updated', onLogUpdated)
  scrollToBottom()
})

onUnmounted(() => {
  if (logContainer.value) {
    logContainer.value.removeEventListener('scroll', onScroll)
  }
  window.removeEventListener('log-updated', onLogUpdated)
})
</script>

<style scoped>
.section-header {
  margin-bottom: var(--spacing-xl);
  padding-bottom: var(--spacing-md);
  border-bottom: 2px solid var(--color-border-light);
}
.section-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}
.section-subtitle {
  color: var(--color-text-secondary);
  font-size: 16px;
}
.log-container {
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  overflow: hidden;
}
.log-controls {
  display: flex;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
  flex-wrap: wrap;
}
.log-control-btn {
  padding: 6px 12px;
  border: 1px solid var(--color-border);
  background: var(--color-bg-input);
  color: var(--color-text-secondary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 12px;
}
.log-control-btn.active {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}
.log-control-btn:hover {
  background: var(--color-bg-primary);
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.log-control-spacer {
  flex: 1;
}
.log-display {
  height: 500px;
  padding: var(--spacing-md);
  overflow-y: auto;
  font-family: 'Consolas', monospace;
  font-size: 13px;
  background: var(--color-bg-input);
}
.log-entry {
  padding: 8px 12px;
  margin-bottom: 6px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-card);
  border-left: 4px solid var(--color-info);
  display: grid;
  grid-template-columns: auto auto 1fr;
  gap: var(--spacing-sm);
  align-items: center;
}
.log-entry.info { border-left-color: var(--color-info); }
.log-entry.warning { border-left-color: var(--color-warning); }
.log-entry.error { border-left-color: var(--color-danger); }
.log-entry.success { border-left-color: var(--color-success); }
.log-timestamp {
  color: var(--color-text-secondary);
  font-size: 11px;
  min-width: 160px;
}
.log-level {
  font-weight: 600;
  font-size: 11px;
  min-width: 60px;
}
.log-message {
  color: var(--color-text-primary);
  word-break: break-all;
}
.log-empty {
  text-align: center;
  padding: var(--spacing-xl);
  color: var(--color-text-secondary);
}
</style>