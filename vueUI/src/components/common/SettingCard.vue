<template>
  <div class="setting-card" :class="{ warning }">
    <div class="card-header" v-if="$slots.header || title">
      <h3 class="setting-title" v-if="title">{{ title }}</h3>
      <slot name="header"></slot>
    </div>
    <div class="card-body">
      <slot></slot>
    </div>
    <div class="card-footer" v-if="$slots.footer">
      <slot name="footer"></slot>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: String,
  warning: Boolean
})
</script>

<style scoped>
.setting-card {
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--color-border);
  transition: all var(--transition-speed) var(--transition-easing);
  position: relative;
  overflow: hidden;
}
.setting-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: linear-gradient(90deg, var(--color-primary), var(--color-secondary));
}
.setting-card.warning {
  border-color: var(--color-warning);
}
.setting-card.warning::before {
  background: var(--color-warning);
}
.setting-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--shadow-lg);
  border-color: var(--color-primary);
}
.setting-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: var(--spacing-md);
  color: var(--color-text-primary);
}
.card-body {
  /* 内容区域 */
}
</style>