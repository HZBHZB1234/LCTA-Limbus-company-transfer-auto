<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getApi } from '@/utils/api'
import { useModalStore } from '@/stores/modal'

const modalStore = useModalStore()
const rulesets = ref<Array<{ name: string; config: Record<string, unknown>; enabled: boolean; builtin: boolean }>>([])

onMounted(async () => {
  await loadRulesets()
})

async function loadRulesets() {
  try {
    const result = await getApi().get_fancy_rulesets()
    const all: typeof rulesets.value = []
    for (const r of result.builtin || []) {
      all.push({ name: r.name, config: r.config, enabled: (result.enabled || []).includes(r.name), builtin: true })
    }
    for (const r of result.user || []) {
      all.push({ name: r.name, config: r.config, enabled: (result.enabled || []).includes(r.name), builtin: false })
    }
    rulesets.value = all
  } catch { /* ignore */ }
}

async function applyFancy() {
  const configs = rulesets.value.filter(r => r.enabled).map(r => ({ name: r.name, config: r.config }))
  const enableMap: Record<string, boolean> = {}
  for (const r of rulesets.value) { enableMap[r.name] = r.enabled }
  modalStore.create('progress', { title: '应用文本美化' })
  await getApi().fancy_main(configs, enableMap)
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-paint-brush"></i> 美化规则</h2>
      <p class="section-subtitle">管理文本美化规则集</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card">
        <h3 class="setting-title">规则集列表</h3>
        <div v-if="rulesets.length === 0" class="list-empty">
          <i class="fas fa-spinner fa-spin"></i><p>加载中...</p>
        </div>
        <div v-for="r in rulesets" :key="r.name" class="list-item">
          <span>{{ r.name }}</span>
          <span v-if="r.builtin" class="badge">内置</span>
          <label class="toggle">
            <input v-model="r.enabled" type="checkbox" />
            <span class="toggle-slider"></span>
          </label>
        </div>
        <div class="button-group">
          <button class="primary-btn" @click="applyFancy"><i class="fas fa-magic"></i> 立即应用美化</button>
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
.settings-grid { display: grid; grid-template-columns: 1fr; gap: 20px; }
.setting-card { background: var(--bg-secondary); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color); }
.setting-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
.list-item {
  display: flex; align-items: center; gap: 8px; padding: 10px 12px;
  border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 6px;
}
.list-empty { padding: 24px; text-align: center; color: var(--text-secondary); }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: var(--accent-color); color: white; }
.toggle { position: relative; margin-left: auto; }
.toggle input { display: none; }
.toggle-slider {
  width: 40px; height: 22px; border-radius: 11px; background: var(--border-color); display: block; cursor: pointer;
}
.toggle input:checked + .toggle-slider { background: var(--accent-color); }
.button-group { display: flex; gap: 8px; margin-top: 16px; }
.primary-btn {
  padding: 10px 24px; border-radius: 8px; border: none; background: var(--accent-color); color: white; cursor: pointer; font-size: 14px;
}
</style>
