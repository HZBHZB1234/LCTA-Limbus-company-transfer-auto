<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { marked } from 'marked'

const readmeHtml = ref('')
const updateHtml = ref('')
const helpHtml = ref('')

onMounted(async () => {
  try {
    const readmeResp = await fetch('assets/README.md')
    if (readmeResp.ok) readmeHtml.value = await marked.parse(await readmeResp.text())
  } catch (e) { console.error('About README load failed:', e) }
  try {
    const updateResp = await fetch('assets/update.md')
    if (updateResp.ok) updateHtml.value = await marked.parse(await updateResp.text())
  } catch (e) { console.error('About update.md load failed:', e) }
  try {
    const helpResp = await fetch('assets/firstUse.md')
    if (helpResp.ok) helpHtml.value = await marked.parse(await helpResp.text())
  } catch (e) { console.error('About firstUse.md load failed:', e) }
})
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-info-circle"></i> 关于 LCTA</h2>
      <p class="section-subtitle">边狱公司汉化工具箱</p>
    </div>

    <div class="about-container">
      <div class="about-card">
        <div class="about-header">
          <div class="about-logo"><i class="fas fa-language"></i></div>
          <div class="about-title">
            <h3>LCTA - 边狱公司汉化工具箱</h3>
            <p class="version-badge">版本 5.0.0</p>
          </div>
        </div>
        <div class="markdown-body" v-html="readmeHtml"></div>
      </div>

      <div class="about-card">
        <div class="about-header">
          <div class="about-logo"><i class="fas fa-language"></i></div>
          <div class="about-title">
            <h3>更新内容</h3>
          </div>
        </div>
        <div class="markdown-body" v-html="updateHtml"></div>
      </div>

      <div class="about-card">
        <div class="about-header">
          <div class="about-logo"><i class="fas fa-language"></i></div>
          <div class="about-title">
            <h3>引导</h3>
          </div>
        </div>
        <div class="markdown-body" v-html="helpHtml"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.about-container { display: flex; flex-direction: column; gap: var(--spacing-lg); }
</style>
