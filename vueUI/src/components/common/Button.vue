<template>
  <button 
    :class="['btn', `btn-${variant}`, { 'btn-loading': loading, 'btn-disabled': disabled }]"
    :disabled="disabled || loading"
    @click="handleClick"
  >
    <i v-if="icon" :class="icon" class="btn-icon"></i>
    <span v-if="loading" class="btn-spinner"></span>
    <slot></slot>
  </button>
</template>

<script setup>
const props = defineProps({
  variant: {
    type: String,
    default: 'primary', // primary, secondary, success, danger, warning
    validator: v => ['primary', 'secondary', 'success', 'danger', 'warning'].includes(v)
  },
  icon: String,
  loading: Boolean,
  disabled: Boolean
})

const emit = defineEmits(['click'])

function handleClick(e) {
  if (props.disabled || props.loading) return
  emit('click', e)
}
</script>

<style scoped>
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 500;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-speed) var(--transition-easing);
  font-family: inherit;
}

.btn-primary {
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-dark));
  color: white;
}
.btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(var(--color-primary), 0.3);
}

.btn-secondary {
  background: var(--color-secondary);
  color: white;
}
.btn-secondary:hover:not(:disabled) {
  background: var(--color-secondary-dark);
}

.btn-success {
  background: var(--color-success);
  color: white;
}
.btn-danger {
  background: var(--color-danger);
  color: white;
}
.btn-warning {
  background: var(--color-warning);
  color: white;
}

.btn:active:not(:disabled) {
  transform: translateY(0);
}

.btn-loading, .btn-disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>