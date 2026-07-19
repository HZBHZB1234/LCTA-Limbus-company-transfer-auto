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
  } catch { /* ignore */ }
  try {
    const updateResp = await fetch('assets/update.md')
    if (updateResp.ok) updateHtml.value = await marked.parse(await updateResp.text())
  } catch { /* ignore */ }
  try {
    const helpResp = await fetch('assets/firstUse.md')
    if (helpResp.ok) helpHtml.value = await marked.parse(await helpResp.text())
  } catch { /* ignore */ }
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
.section-header { margin-bottom: 24px; }
.section-title { font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.section-title i { color: var(--accent-color); }
.section-subtitle { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }
.about-container { display: flex; flex-direction: column; gap: 20px; }
.about-card { background: var(--bg-secondary); border-radius: 12px; padding: 24px; border: 1px solid var(--border-color); }
.about-header { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.about-logo { font-size: 32px; color: var(--accent-color); }
.about-title h3 { font-size: 18px; margin: 0; }
.version-badge { font-size: 13px; color: var(--text-secondary); margin: 4px 0 0; }
.markdown-body { font-size: 14px; line-height: 1.6; }
</style>
