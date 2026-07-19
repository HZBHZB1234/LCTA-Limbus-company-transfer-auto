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
.progress-container { margin: var(--spacing-lg) 0; animation: fadeIn 0.5s ease; }
.progress-bar-bg {
  height: 12px;
  background: var(--color-bg-input);
  border-radius: 6px;
  overflow: hidden;
  position: relative;
}
.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary), var(--color-secondary));
  border-radius: 6px;
  transition: width 0.15s var(--transition-easing);
  position: relative;
  z-index: 1;
}
.progress-text {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: var(--spacing-sm);
  font-size: 13px;
}
.progress-text span:first-child {
  font-weight: 500;
  color: var(--color-text-primary);
}
.progress-text span:last-child {
  font-weight: 600;
  color: var(--color-primary);
  font-size: 18px;
}
</style>
