<template>
  <BaseList v-bind="$attrs" @select="onSelect">
    <template #actions="{ item }">
      <button class="list-action-btn toggle-btn" @click.stop="toggle(item)">
        <i :class="isEnabled(item) ? 'fas fa-toggle-on' : 'fas fa-toggle-off'"></i>
      </button>
    </template>
  </BaseList>
</template>

<script setup>
import BaseList from './BaseList.vue'

const props = defineProps({
  enabledMap: { type: Object, required: true }
})

const emit = defineEmits(['toggle', 'select'])

function getItemKey(item) {
  return typeof item === 'string' ? item : item.name
}

function isEnabled(item) {
  const key = getItemKey(item)
  return props.enabledMap[key] || false
}

function toggle(item) {
  const key = getItemKey(item)
  const newState = !props.enabledMap[key]
  emit('toggle', item, newState)
}

function onSelect(item) {
  emit('select', item)
}
</script>