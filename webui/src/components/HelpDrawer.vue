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
  background: rgba(0, 0, 0, 0.3); z-index: 2000;
}
.help-drawer {
  position: fixed; top: 0; right: 0; bottom: 0;
  width: 420px;
  background: var(--bg-primary);
  box-shadow: -4px 0 20px rgba(0, 0, 0, 0.15);
  z-index: 2001;
  display: flex; flex-direction: column;
}
.help-drawer-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--border-color);
}
.help-drawer-title { display: flex; align-items: center; gap: 8px; font-weight: 600; }
.help-drawer-close { background: none; border: none; cursor: pointer; color: var(--text-secondary); font-size: 16px; }
.help-drawer-tabs { display: flex; border-bottom: 1px solid var(--border-color); padding: 0 16px; }
.help-drawer-tab {
  flex: 1; padding: 10px 0; border: none; border-bottom: 2px solid transparent;
  background: none; color: var(--text-secondary); cursor: pointer; font-size: 13px;
}
.help-drawer-tab.active { color: var(--accent-color); border-bottom-color: var(--accent-color); }
.help-drawer-body { flex: 1; overflow-y: auto; padding: 16px 20px; }
.help-drawer-loading { text-align: center; padding: 40px 0; color: var(--text-secondary); }
.help-drawer-footer {
  padding: 12px 20px; border-top: 1px solid var(--border-color);
  font-size: 12px; color: var(--text-secondary);
}
.markdown-body { font-size: 14px; line-height: 1.6; }
</style>
