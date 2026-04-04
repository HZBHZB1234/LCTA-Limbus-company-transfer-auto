<template>
  <label class="checkbox-container">
    <input type="checkbox" :checked="modelValue" @change="onChange" :disabled="disabled">
    <span class="checkmark"></span>
    <span class="checkbox-label"><slot></slot></span>
  </label>
</template>

<script setup>
const props = defineProps({
  modelValue: Boolean,
  disabled: Boolean
})
const emit = defineEmits(['update:modelValue'])

function onChange(e) {
  emit('update:modelValue', e.target.checked)
}
</script>

<style scoped>
.checkbox-container {
  display: inline-flex;
  align-items: center;
  cursor: pointer;
  position: relative;
  padding-left: 28px;
  user-select: none;
  font-size: 14px;
  color: var(--color-text-primary);
}
.checkbox-container input {
  position: absolute;
  opacity: 0;
  cursor: pointer;
  height: 0;
  width: 0;
}
.checkmark {
  position: absolute;
  left: 0;
  top: 0;
  height: 20px;
  width: 20px;
  background-color: var(--color-bg-input);
  border: 2px solid var(--color-border);
  border-radius: var(--radius-sm);
  transition: all var(--transition-speed) var(--transition-easing);
}
.checkbox-container:hover input ~ .checkmark {
  border-color: var(--color-primary);
}
.checkbox-container input:checked ~ .checkmark {
  background-color: var(--color-primary);
  border-color: var(--color-primary);
}
.checkmark:after {
  content: "";
  position: absolute;
  display: none;
  left: 6px;
  top: 2px;
  width: 5px;
  height: 10px;
  border: solid white;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}
.checkbox-container input:checked ~ .checkmark:after {
  display: block;
}
.checkbox-label {
  margin-left: 4px;
}
</style>