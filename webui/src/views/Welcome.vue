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
  } catch (e) {
    console.error('Welcome markdown load failed:', e)
  }
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
/* Welcome view uses shared global classes from main.css */
</style>
