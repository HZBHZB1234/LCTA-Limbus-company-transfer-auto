<template>
  <div class="status-indicator">
    <div class="status-dot" :class="status"></div>
    <span>{{ text }}</span>
  </div>
</template>

<script setup>
defineProps({
  status: {
    type: String,
    default: 'connected',
    validator: v => ['connected', 'connecting', 'disconnected'].includes(v)
  },
  text: String
})
</script>

<style scoped>
.status-indicator {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: 12px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.status-dot.connected {
  background: var(--color-success);
  box-shadow: 0 0 10px rgba(var(--color-success), 0.5);
}
.status-dot.connecting {
  background: var(--color-warning);
  box-shadow: 0 0 10px rgba(var(--color-warning), 0.5);
}
.status-dot.disconnected {
  background: var(--color-danger);
}
</style>