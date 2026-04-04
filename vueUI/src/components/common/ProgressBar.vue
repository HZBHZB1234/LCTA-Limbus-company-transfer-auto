<template>
  <div class="progress-container">
    <div class="progress-info">
      <span class="progress-text">{{ text }}</span>
      <span class="progress-percent">{{ percent }}%</span>
    </div>
    <div class="progress-bar">
      <div class="progress-bar-fill" :style="{ width: percent + '%' }"></div>
      <div class="progress-bar-pulse" v-if="percent < 100"></div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  percent: { type: Number, default: 0 },
  text: { type: String, default: '处理中...' }
})
</script>

<style scoped>
.progress-container {
  margin: var(--spacing-md) 0;
}
.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-sm);
}
.progress-text {
  font-weight: 500;
  color: var(--color-text-primary);
}
.progress-percent {
  font-weight: 600;
  color: var(--color-primary);
  font-size: 18px;
}
.progress-bar {
  width: 100%;
  height: 12px;
  background: var(--color-bg-input);
  border-radius: 6px;
  overflow: hidden;
  position: relative;
}
.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary), var(--color-secondary));
  width: 0%;
  transition: width 0.15s var(--transition-easing);
  position: relative;
  z-index: 1;
}
.progress-bar-pulse {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  width: 100%;
  background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.4) 50%, transparent 100%);
  animation: pulseBar 2s infinite;
  z-index: 0;
}
@keyframes pulseBar {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}
</style>