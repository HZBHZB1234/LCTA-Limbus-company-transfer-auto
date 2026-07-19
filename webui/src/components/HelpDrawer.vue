<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'

const route = useRoute()
const visible = ref(false)
const activeTab = ref<'page-help' | 'guide' | 'faq'>('page-help')
const loading = ref(false)

const pageHelpContent = ref('')
const guideContent = ref('')
const faqContent = ref('')

async function loadMarkdown(name: string): Promise<string> {
  const resp = await fetch(`guide/${name}.md`)
  if (!resp.ok) return '# 暂无内容'
  const md = await resp.text()
  return await marked.parse(md)
}

watch(activeTab, async (tab) => {
  const pageName = (route.name as string) || 'dashboard'
  loading.value = true
  if (tab === 'page-help') {
    pageHelpContent.value = await loadMarkdown(pageName)
  } else if (tab === 'guide') {
    guideContent.value = await loadMarkdown('dashboard')
  } else {
    faqContent.value = '# 常见问题\n\n暂无内容。'
  }
  loading.value = false
})

function open() {
  visible.value = true
  activeTab.value = 'page-help'
  loadMarkdown((route.name as string) || 'dashboard').then((html) => {
    pageHelpContent.value = html
  })
}

function close() {
  visible.value = false
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape' && visible.value) {
    close()
  }
}

defineExpose({ open, close })
document.addEventListener('keydown', onKeyDown)
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="help-drawer-overlay" @click="close"></div>
    <div v-if="visible" class="help-drawer">
      <div class="help-drawer-header">
        <div class="help-drawer-title">
          <i class="fas fa-question-circle"></i>
          <span>LCTA 帮助中心</span>
        </div>
        <button class="help-drawer-close" @click="close" title="关闭 (Esc)">
          <i class="fas fa-times"></i>
        </button>
      </div>
      <div class="help-drawer-tabs">
        <button
          v-for="tab in (['page-help', 'guide', 'faq'] as const)"
          :key="tab"
          :class="['help-drawer-tab', { active: activeTab === tab }]"
          @click="activeTab = tab"
        >
          <i :class="['fas', tab === 'page-help' ? 'fa-file-alt' : tab === 'guide' ? 'fa-book' : 'fa-comments']"></i>
          {{ tab === 'page-help' ? '页面帮助' : tab === 'guide' ? '使用指南' : '常见问题' }}
        </button>
      </div>
      <div class="help-drawer-body markdown-body">
        <div v-if="loading" class="help-drawer-loading">
          <i class="fas fa-spinner fa-spin"></i> 加载中...
        </div>
        <div v-else v-html="activeTab === 'page-help' ? pageHelpContent : activeTab === 'guide' ? guideContent : faqContent"></div>
      </div>
      <div class="help-drawer-footer">
        <i class="fas fa-lightbulb"></i>
        提示：在任意页面长按 W 键 2 秒即可打开帮助
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.help-drawer-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.3); z-index: 2500;
}
.help-drawer {
  position: fixed; top: 0; right: 0; bottom: 0;
  width: 420px; max-width: 90vw;
  background: var(--color-bg-card);
  box-shadow: var(--shadow-lg);
  z-index: 2501;
  display: flex; flex-direction: column;
  animation: slideInRight 0.3s var(--transition-easing);
}
.help-drawer-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--spacing-lg); border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-primary); flex-shrink: 0;
}
.help-drawer-title {
  font-size: 18px; font-weight: 600; color: var(--color-text-primary);
  display: flex; align-items: center; gap: 8px;
}
.help-drawer-title i { color: var(--color-primary); }
.help-drawer-close {
  width: 32px; height: 32px; border-radius: var(--radius-md);
  border: 1px solid var(--color-border); background: var(--color-bg-input);
  color: var(--color-text-secondary); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; transition: all var(--transition-speed) var(--transition-easing);
}
.help-drawer-close:hover { background: var(--color-danger); color: white; border-color: var(--color-danger); }
.help-drawer-tabs {
  display: flex; border-bottom: 1px solid var(--color-border);
  flex-shrink: 0; padding: 0 var(--spacing-lg); gap: 0;
}
.help-drawer-tab {
  padding: 10px 16px; border: none; background: transparent;
  color: var(--color-text-secondary); cursor: pointer; font-size: 13px;
  font-weight: 500; border-bottom: 2px solid transparent; margin-bottom: -1px;
  transition: all var(--transition-speed) var(--transition-easing);
}
.help-drawer-tab:hover { color: var(--color-text-primary); }
.help-drawer-tab.active { color: var(--color-primary); border-bottom-color: var(--color-primary); }
.help-drawer-body {
  flex: 1; overflow-y: auto; padding: var(--spacing-lg);
}
.help-drawer-body .markdown-body { background: transparent !important; font-size: 14px; }
.help-drawer-body .markdown-body h2 { font-size: 20px; margin-top: 0; }
.help-drawer-loading {
  display: flex; align-items: center; justify-content: center;
  padding: 40px; color: var(--color-text-secondary);
}
.help-drawer-error {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 40px; color: var(--color-danger);
  text-align: center; gap: 12px;
}
.help-drawer-footer {
  padding: var(--spacing-md) var(--spacing-lg); border-top: 1px solid var(--color-border);
  background: var(--color-bg-primary); font-size: 12px; color: var(--color-text-secondary);
  flex-shrink: 0; display: flex; align-items: center; gap: 6px;
}
.help-drawer-footer i { color: var(--color-warning); }
</style>
