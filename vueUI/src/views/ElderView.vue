<template>
  <div class="elder-view">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-compass"></i> 老年人模式
      </h2>
      <p class="section-subtitle">简单方便，不需要动脑的指引程序</p>
    </div>

    <div class="question-container">
      <div class="about-card">
        <div class="markdown-body" v-html="content"></div>
        <div ref="dynamicContainer" class="dynamic-container"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useConfigStore } from '@/stores/config'
import { api } from '@/utils/api'
import { renderMarkdown } from '@/utils/markdown'

const configStore = useConfigStore()
const content = ref('')
const dynamicContainer = ref(null)

// 老年人模式数据
let updateList = {}
let refer = {}
let relyList = {}
let historyList = {}
let latestPage = 'main'
const version = '4.1.5'
const versionNum = version.replace(/\./g, '')

async function initElder() {
  updateList = await api.call('get_attr', 'updateList')
  refer = await api.call('get_attr', 'bindRefer')
  relyList = await api.call('get_attr', 'relyList')
  
  let saved = configStore.get('elder_list')
  if (!saved) {
    historyList = {}
    for (const key of Object.keys(updateList)) {
      historyList[key] = 'new'
    }
  } else {
    historyList = JSON.parse(saved)
    for (const key of Object.keys(updateList)) {
      if (historyList[key] === undefined) {
        historyList[key] = 'new'
      }
    }
  }
  await loadPage('main')
}

function evalNextPage() {
  let hasShowFlag = false
  for (const value of Object.keys(historyList)) {
    if (!hasShowFlag) {
      if (value === latestPage) hasShowFlag = true
      continue
    }
    if (historyList[value] === 'new' || historyList[value] < updateList[value]) {
      const rely = relyList[value] || []
      const satisfied = rely.every(cond => {
        if (typeof cond === 'string') {
          return configStore.get(cond)
        } else if (cond[0] === 'not') {
          return !configStore.get(cond[1])
        } else {
          const targetValue = configStore.get(cond[0])
          return cond.slice(1).some(v => targetValue == v)
        }
      })
      if (satisfied) return value
    }
  }
  return ''
}

async function savePageRefer() {
  const pageRefer = refer[latestPage]
  if (!pageRefer) return
  for (const [key, [configId]] of Object.entries(pageRefer)) {
    const element = document.getElementById(key)
    if (element) {
      let value
      if (element.type === 'checkbox') {
        value = element.checked
      } else {
        value = element.value
      }
      await configStore.updateConfig(configId, value)
    }
  }
  historyList[latestPage] = versionNum
  configStore.updateConfig('--elder', JSON.stringify(historyList))
  await configStore.flushUpdates()
}

async function loadPageRefer() {
  const pageRefer = refer[latestPage]
  if (!pageRefer) return
  for (const [key, [, configId]] of Object.entries(pageRefer)) {
    const element = document.getElementById(key)
    if (element) {
      const value = configStore.get(configId)
      if (element.type === 'checkbox') {
        element.checked = value
      } else {
        element.value = value
      }
    }
  }
}

async function switchPage() {
  await savePageRefer()
  const nextPage = evalNextPage()
  if (nextPage) {
    latestPage = nextPage
    await loadPage(nextPage)
    await loadPageRefer()
  } else {
    await loadPage('final')
  }
}

function markdownPrefix(text, pageName) {
  const scripts = []
  let processed = text.replace(/<script>([\s\S]*?)<\/script>/gi, (match, scriptContent) => {
    scripts.push(scriptContent)
    return ''
  })
  
  processed = processed.replace(/<version>([\s\S]*?)<\/version>/gi, (match, versionStr) => {
    const num = parseFloat(versionStr.trim())
    if (!isNaN(num) && historyList[pageName] !== 'new' && num > historyList[pageName]) {
      return '<span style="border:1px solid #ddd;color:#666;padding:2px 4px;border-radius:4px;font-size:12px;">NEW</span>'
    }
    return ''
  })
  
  // 延迟执行脚本
  if (scripts.length && dynamicContainer.value) {
    nextTick(() => {
      scripts.forEach(script => {
        const scriptEl = document.createElement('script')
        scriptEl.textContent = `setTimeout(() => { ${script} }, 100)`
        dynamicContainer.value.appendChild(scriptEl)
      })
    })
  }
  
  return renderMarkdown(processed)
}

async function loadPage(pageName) {
  try {
    const response = await fetch(`/assets/elder/${pageName}.md`)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const markdown = await response.text()
    const html = markdownPrefix(markdown, pageName)
    content.value = html
    // 清空动态容器
    if (dynamicContainer.value) {
      dynamicContainer.value.innerHTML = ''
    }
    // 重新绑定切换按钮
    nextTick(() => {
      const nextBtn = document.getElementById('elder-next')
      if (nextBtn) {
        nextBtn.onclick = switchPage
      }
    })
  } catch (error) {
    content.value = `<p class="error">加载页面失败: ${error.message}</p>`
  }
}

onMounted(() => {
  initElder()
})
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
.question-container {
  max-width: 800px;
  margin: 0 auto;
}
.about-card {
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-xl);
  box-shadow: var(--shadow-md);
  border: 1px solid var(--color-border);
}
.dynamic-container {
  margin-top: var(--spacing-lg);
}
</style>