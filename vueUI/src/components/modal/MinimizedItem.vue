<template>
  <div class="minimized-modal" @click="$emit('restore')">
    <div class="minimized-header">
      <div class="minimized-title">{{ title }}</div>
      <div class="minimized-status">{{ status }}</div>
    </div>
    <div class="minimized-progress">
      <div class="minimized-progress-bar">
        <div class="minimized-progress-fill" :style="{ width: percent + '%' }"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  id: [String, Number],
  title: String,
  percent: Number,
  status: String
})

defineEmits(['restore'])
</script>

<style scoped>
.minimized-modal {
  background: var(--color-bg-card);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  border: 1px solid var(--color-border);
  width: 100%;
  cursor: pointer;
  overflow: hidden;
  transition: all var(--transition-speed) var(--transition-easing);
}
.minimized-modal:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
  border-color: var(--color-primary);
}
.minimized-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-border);
}
.minimized-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}
.minimized-status {
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-left: var(--spacing-sm);
}
.minimized-progress {
  padding: var(--spacing-sm) var(--spacing-md);
}
.minimized-progress-bar {
  width: 100%;
  height: 6px;
  background: var(--color-bg-input);
  border-radius: 3px;
  overflow: hidden;
}
.minimized-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--color-primary), var(--color-secondary));
  width: 0%;
  transition: width 0.3s var(--transition-easing);
}
</style>