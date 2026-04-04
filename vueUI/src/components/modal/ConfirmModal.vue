<template>
  <BaseModal
    :title="title"
    :content="content"
    :showCancel="true"
    :showConfirm="true"
    :showMinimize="false"
    cancelText="取消"
    confirmText="确定"
    @close="$emit('close')"
    @confirm="$emit('confirm')"
    @cancel="$emit('cancel')"
  />
</template>

<script setup>
import BaseModal from './BaseModal.vue'

defineProps({
  title: String,
  content: String
})

defineEmits(['close', 'confirm', 'cancel'])
</script>