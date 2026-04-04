<template>
  <div class="file-input-group">
    <div class="input-wrapper">
      <input 
        type="text" 
        :value="modelValue" 
        @input="$emit('update:modelValue', $event.target.value)"
        :placeholder="placeholder"
        :disabled="disabled"
      >
      <button v-if="clearable && modelValue" type="button" class="input-clear" @click="clear">
        <i class="fas fa-times"></i>
      </button>
    </div>
    <Button variant="secondary" size="small" @click="browse">
      <i class="fas fa-folder-open"></i> 浏览
    </Button>
  </div>
</template>

<script setup>
import Button from './Button.vue'
import { api } from '@/utils/api'

const props = defineProps({
  modelValue: String,
  placeholder: String,
  disabled: Boolean,
  clearable: { type: Boolean, default: true },
  type: { type: String, default: 'file' } // 'file' or 'folder'
})

const emit = defineEmits(['update:modelValue'])

async function browse() {
  let path
  if (props.type === 'folder') {
    path = await api.browse_folder('')
  } else {
    path = await api.browse_file('')
  }
  if (path) {
    emit('update:modelValue', path)
  }
}

function clear() {
  emit('update:modelValue', '')
}
</script>

<style scoped>
.file-input-group {
  display: flex;
  gap: var(--spacing-sm);
}
.input-wrapper {
  position: relative;
  flex: 1;
}
.input-wrapper input {
  width: 100%;
  padding-right: 30px;
}
.input-clear {
  position: absolute;
  right: 5px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
}
.input-clear:hover {
  background: var(--color-bg-primary);
  color: var(--color-danger);
}
</style>