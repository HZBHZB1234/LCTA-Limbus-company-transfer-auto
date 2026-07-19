<script setup lang="ts">
defineProps<{ percent: number; text: string }>()
</script>

<template>
  <div class="progress-container">
    <div class="progress-bar-bg">
      <div class="progress-bar-fill" :style="{ width: `${Math.min(100, Math.max(0, percent))}%` }"></div>
    </div>
    <div class="progress-text">
      <span>{{ text || '准备中...' }}</span>
      <span>{{ Math.round(percent) }}%</span>
    </div>
  </div>
</template>

<style scoped>
.progress-container { margin-bottom: 4px; }
.progress-bar-bg {
  height: 8px;
  background: var(--bg-secondary);
  border-radius: 4px;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  background: var(--accent-color);
  border-radius: 4px;
  transition: width 0.3s ease;
}
.progress-text {
  display: flex;
  justify-content: space-between;
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
