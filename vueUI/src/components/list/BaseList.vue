<template>
  <div class="base-list">
    <div v-if="loading" class="list-loading">
      <i class="fas fa-spinner fa-spin"></i> 加载中...
    </div>
    <div v-else-if="items.length === 0" class="list-empty">
      <i :class="emptyIcon"></i>
      <p>{{ emptyText }}</p>
    </div>
    <div v-else class="list-items">
      <div
        v-for="item in items"
        :key="getItemKey(item)"
        class="list-item"
        :class="{ selected: isSelected(item) }"
        @click="handleSelect(item)"
      >
        <div class="list-item-content">
          <slot name="prefix" :item="item"></slot>
          <span>{{ getDisplayName(item) }}</span>
        </div>
        <div class="list-item-actions">
          <slot name="actions" :item="item"></slot>
          <button v-if="selectable" class="list-action-btn select-btn" @click.stop="handleSelect(item)">
            <i class="fas fa-check"></i>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  items: { type: Array, required: true },
  itemKey: { type: String, default: 'name' },
  displayName: { type: Function, default: (item) => typeof item === 'string' ? item : item.name },
  selectedKey: { type: [String, Number], default: null },
  selectable: { type: Boolean, default: true },
  loading: { type: Boolean, default: false },
  emptyText: { type: String, default: '暂无数据' },
  emptyIcon: { type: String, default: 'fas fa-box-open' }
})

const emit = defineEmits(['update:selectedKey', 'select'])

function getItemKey(item) {
  return typeof item === 'object' ? item[props.itemKey] : item
}

function getDisplayName(item) {
  return props.displayName(item)
}

function isSelected(item) {
  return getItemKey(item) === props.selectedKey
}

function handleSelect(item) {
  if (!props.selectable) return
  const key = getItemKey(item)
  emit('update:selectedKey', key)
  emit('select', item)
}
</script>

<style scoped>
.base-list {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background-color: var(--color-bg-input);
  overflow: hidden;
}
.list-loading, .list-empty {
  padding: var(--spacing-xl);
  text-align: center;
  color: var(--color-text-secondary);
}
.list-items {
  max-height: 300px;
  overflow-y: auto;
}
.list-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-border-light);
  transition: background-color 0.2s ease;
}
.list-item:hover {
  background-color: var(--color-bg-primary);
}
.list-item.selected {
  background-color: rgba(var(--color-primary), 0.1);
  border-left: 3px solid var(--color-primary);
}
.list-item.selected .list-item-content span {
  color: var(--color-primary);
  font-weight: bold;
}
.list-item-content {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}
.list-item-actions {
  display: flex;
  gap: var(--spacing-sm);
}
.list-action-btn {
  background: var(--color-bg-input);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 4px 8px;
  cursor: pointer;
}
.list-action-btn:hover {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}
</style>