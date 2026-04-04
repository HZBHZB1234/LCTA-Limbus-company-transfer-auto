<template>
  <BaseModal
    :title="title"
    :content="content"
    :statusText="statusText"
    :showCancel="false"
    :showConfirm="true"
    :showMinimize="false"
    confirmText="确定"
    @close="$emit('close')"
    @confirm="$emit('confirm')"
  />
</template>

<script setup>
import BaseModal from './BaseModal.vue'

defineProps({
  title: String,
  content: String,
  statusText: String
})

defineEmits(['close', 'confirm'])
</script>