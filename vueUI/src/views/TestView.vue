<template>
  <div class="test-view">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-flask"></i> 调试界面
      </h2>
      <p class="section-subtitle">测试使用（仅在调试模式下可见）</p>
    </div>

    <div class="action-grid">
      <Button @click="startTest">开始启动</Button>
      <Button @click="evalSkip">注入js</Button>
      <Button @click="signEvalJs">为窗口订阅js</Button>
      <Button @click="reloadPage">强制刷新缓存并重载</Button>
      <Button @click="goToWelcome">显示欢迎页面</Button>
      <Button @click="createTestModal">创建一个模态窗口</Button>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useModalStore } from '@/stores/modal'
import { api } from '@/utils/api'
import Button from '@/components/common/Button.vue'

const router = useRouter()
const modalStore = useModalStore()

async function startTest() {
  await api.call('startTest')
}

async function evalSkip() {
  await api.call('eval_skip')
}

async function signEvalJs() {
  await api.call('sign_eval_js')
}

function reloadPage() {
  location.reload(true)
}

function goToWelcome() {
  router.push('/welcome')
}

function createTestModal() {
  const modalId = modalStore.openModal('progress', { title: '测试窗口' })
  modalStore.setModalRunning(modalId, (action) => {
    console.log('Modal action:', action)
  })
  modalStore.updateProgress(modalId, 50, '测试阶段')
  modalStore.addLog(modalId, '开始测试')
  setTimeout(() => {
    modalStore.completeModal(modalId, true, '测试完成')
  }, 3000)
}
</script>

<style scoped>
.section-header {
  margin-bottom: var(--spacing-xl);
  padding-bottom: var(--spacing-md);
  border-bottom: 2px solid var(--color-border-light);
}
.section-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}
.section-subtitle {
  color: var(--color-text-secondary);
  font-size: 16px;
}
.action-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-md);
}
</style>