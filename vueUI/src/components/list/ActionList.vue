<template>
  <BaseList v-bind="$attrs" @select="onSelect">
    <template #actions="{ item }">
      <button 
        v-if="actionButtonText" 
        class="list-action-btn action-btn" 
        @click.stop="handleAction(item)"
      >
        {{ getActionText(item) }}
      </button>
    </template>
  </BaseList>
</template>

<script setup>
import BaseList from './BaseList.vue'

const props = defineProps({
  actionButtonText: { type: [String, Function], required: true },
  onAction: { type: Function, default: null }
})

const emit = defineEmits(['action', 'select'])

function getActionText(item) {
  if (typeof props.actionButtonText === 'function') {
    return props.actionButtonText(item)
  }
  return props.actionButtonText
}

function handleAction(item) {
  if (props.onAction) props.onAction(item)
  emit('action', item)
}

function onSelect(item) {
  emit('select', item)
}
</script>