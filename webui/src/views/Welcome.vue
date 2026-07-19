<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { marked } from 'marked'

const router = useRouter()
const welcomeHtml = ref('')

onMounted(async () => {
  try {
    const resp = await fetch('assets/firstUse.md')
    if (resp.ok) welcomeHtml.value = await marked.parse(await resp.text())
  } catch { /* ignore */ }
})
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-user-circle"></i> 欢迎</h2>
      <p class="section-subtitle">边狱公司汉化工具箱</p>
    </div>

    <div class="about-card">
      <div class="about-header">
        <div class="about-logo"><i class="fas fa-language"></i></div>
        <div class="about-title">
          <h3>LCTA - 边狱公司汉化工具箱</h3>
          <p class="version-badge">版本 5.0.0</p>
        </div>
      </div>
      <div class="markdown-body" v-html="welcomeHtml"></div>
      <div style="margin-top: 20px">
        <button class="primary-btn" @click="router.push('/')">
          <i class="fas fa-home"></i> 进入首页
        </button>
        <button class="action-btn" style="margin-left: 8px" @click="router.push('/elder')">
          <i class="fas fa-compass"></i> 设置向导
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.section-header { margin-bottom: 24px; }
.section-title { font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.section-title i { color: var(--accent-color); }
.section-subtitle { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }
.about-card { background: var(--bg-secondary); border-radius: 12px; padding: 24px; border: 1px solid var(--border-color); max-width: 700px; }
.about-header { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.about-logo { font-size: 32px; color: var(--accent-color); }
.about-title h3 { font-size: 18px; margin: 0; }
.version-badge { font-size: 13px; color: var(--text-secondary); margin: 4px 0 0; }
.markdown-body { font-size: 14px; line-height: 1.6; }
.primary-btn {
  padding: 10px 24px; border-radius: 8px; border: none;
  background: var(--accent-color); color: white; cursor: pointer; font-size: 14px;
}
.action-btn {
  padding: 10px 24px; border-radius: 8px; border: 1px solid var(--border-color);
  background: var(--bg-primary); color: var(--text-primary); cursor: pointer; font-size: 14px;
}
</style>
