<script setup lang="ts">
import { getApi } from '@/utils/api'
import { useRouter } from 'vue-router'

const router = useRouter()

async function doStartTest() {
  await getApi().startTest()
}

async function doEvalSkip() {
  await getApi().eval_skip()
}

async function doSignEvalJs() {
  await getApi().sign_eval_js()
}

function doForceReload() {
  location.reload()
}

function goWelcome() {
  router.push('/welcome')
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-flask"></i> 测试界面</h2>
      <p class="section-subtitle">开发和调试工具</p>
    </div>
    <div class="settings-grid">
      <div class="setting-card">
        <h3 class="setting-title">调试功能</h3>
        <div style="display: flex; flex-direction: column; gap: 12px;">
          <button class="primary-btn" @click="doStartTest"><i class="fas fa-terminal"></i> 开始启动</button>
          <button class="primary-btn" @click="doEvalSkip"><i class="fas fa-code"></i> 注入js</button>
          <button class="primary-btn" @click="doSignEvalJs"><i class="fas fa-globe"></i> 为窗口订阅js</button>
          <button class="action-btn" @click="doForceReload"><i class="fas fa-sync-alt"></i> 强制刷新缓存并重载</button>
          <button class="action-btn" @click="goWelcome"><i class="fas fa-home"></i> 显示欢迎页面</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Test view uses shared global classes from main.css */
</style>
