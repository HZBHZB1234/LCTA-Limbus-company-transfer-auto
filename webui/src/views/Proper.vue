<script setup lang="ts">
import { ref } from 'vue'
import { getApi } from '@/utils/api'
import { useModalStore } from '@/stores/modal'

const modalStore = useModalStore()

const outputFormat = ref('json')
const minCount = ref<number | null>(2)

async function fetchNouns() {
  const mid = modalStore.create('progress', { title: '抓取专有词汇' })
  await getApi().fetch_proper_nouns(mid)
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-book"></i> 抓取专有词汇</h2>
      <p class="section-subtitle">从文本中提取专有名词和术语</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card">
        <h3 class="setting-title">抓取配置</h3>
        <div class="form-group">
          <label>输出格式:</label>
          <select v-model="outputFormat">
            <option value="json">JSON格式</option>
            <option value="single">单文件格式</option>
            <option value="double">双文件格式</option>
          </select>
        </div>
        <div class="form-group">
          <label>最短专有名词长度:</label>
          <input v-model.number="minCount" type="number" placeholder="例如：2" />
        </div>
        <div class="action-area">
          <button class="primary-btn" @click="fetchNouns">
            <i class="fas fa-download"></i> 开始抓取
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.section-header { margin-bottom: 24px; }
.section-title { font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.section-title i { color: var(--accent-color); }
.section-subtitle { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }
.settings-grid { display: grid; grid-template-columns: 1fr; gap: 20px; max-width: 500px; }
.setting-card { background: var(--bg-secondary); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color); }
.setting-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 14px; color: var(--text-secondary); margin-bottom: 6px; }
.form-group select, .form-group input {
  width: 100%; padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border-color);
  background: var(--bg-primary); color: var(--text-primary); font-size: 14px;
}
.action-area { margin-top: 16px; }
.primary-btn {
  padding: 10px 24px; border-radius: 8px; border: none; background: var(--accent-color); color: white; cursor: pointer; font-size: 14px;
}
</style>
