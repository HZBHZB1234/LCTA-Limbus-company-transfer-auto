<template>
  <div class="markdown-body" v-html="html"></div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { renderMarkdown, loadMarkdown } from '@/utils/markdown'

const props = defineProps({
  source: String,      // markdown 文本内容
  url: String,         // 或者从 url 加载
  autoRender: { type: Boolean, default: true }
})

const html = ref('')

async function render() {
  if (props.source) {
    html.value = renderMarkdown(props.source)
  } else if (props.url) {
    html.value = await loadMarkdown(props.url)
  }
}

if (props.autoRender) {
  render()
  watch(() => [props.source, props.url], render)
}
</script>

<style scoped>
.markdown-body {
  background: transparent !important;
}
</style>