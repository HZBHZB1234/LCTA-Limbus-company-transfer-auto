<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { getApi } from '@/utils/api'
import { useConfigStore } from '@/stores/config'
import { useModalStore } from '@/stores/modal'

interface Ruleset {
  name: string
  description: string
  config: unknown
  enabled: boolean
  builtin: boolean
}

const modalStore = useModalStore()
const configStore = useConfigStore()
const rulesets = ref<Ruleset[]>([])
const selectedName = ref<string | null>(null)
const editingJson = ref('')
const loading = ref(true)
const loadError = ref(false)

const selectedRuleset = computed(() => {
  if (!selectedName.value) return null
  return rulesets.value.find(r => r.name === selectedName.value) ?? null
})

const formattedJson = computed(() => {
  if (!selectedRuleset.value) return ''
  return JSON.stringify(selectedRuleset.value.config, null, 2)
})

watch(selectedName, () => {
  editingJson.value = formattedJson.value
})

onMounted(async () => {
  await loadRulesets()
})

async function loadRulesets() {
  loading.value = true
  loadError.value = false
  try {
    const rawResult = await getApi().get_fancy_rulesets()
    const wrapper = rawResult as unknown as Record<string, unknown>
    const result = (wrapper.success ? wrapper.data : rawResult) as Record<string, unknown>
    const rawEnabled = result.enabled
    // enabled may be an array of names (after save) or an object {name: boolean} (default)
    let enabledList: string[] = []
    if (Array.isArray(rawEnabled)) {
      enabledList = rawEnabled as string[]
    } else if (rawEnabled && typeof rawEnabled === 'object') {
      enabledList = Object.keys(rawEnabled as Record<string, unknown>).filter(k => (rawEnabled as Record<string, unknown>)[k])
    }
    const enabledSet = new Set<string>(enabledList)
    const all: Ruleset[] = []

    for (const r of (result.builtin as Array<{ name: string; config: Record<string, unknown> }>) || []) {
      all.push({
        name: r.name,
        description: '',
        config: r.config,
        enabled: enabledSet.has(r.name),
        builtin: true
      })
    }

    const userFancy = configStore.get<string>('user_fancy')
    let userRulesets: Array<{ name: string; description: string; config: unknown }> = []
    if (userFancy) {
      try { userRulesets = JSON.parse(userFancy) } catch { /* ignore */ }
    } else if ((result.user as Array<{ name: string; config: unknown }>)?.length) {
      userRulesets = (result.user as Array<{ name: string; config: unknown }>).map(r => ({ name: r.name, description: '', config: r.config }))
    }
    for (const u of userRulesets) {
      all.push({
        name: u.name,
        description: u.description || '',
        config: u.config,
        enabled: enabledSet.has(u.name),
        builtin: false
      })
    }

    rulesets.value = all
  } catch (e) {
    console.error('Fancy rulesets load failed:', e)
    getApi().log(`[Fancy] 规则集加载失败: ${e}`).catch(() => {})
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function selectRuleset(name: string) {
  selectedName.value = name
}

function formatJson() {
  try {
    const parsed = JSON.parse(editingJson.value)
    editingJson.value = JSON.stringify(parsed, null, 2)
    if (selectedRuleset.value) {
      selectedRuleset.value.config = parsed
    }
  } catch (e) {
    alert('JSON 格式错误: ' + (e as Error).message)
  }
}

function createRuleset() {
  const name = `新规则集_${Date.now()}`
  const ruleset: Ruleset = { name, description: '', config: {}, enabled: true, builtin: false }
  rulesets.value.push(ruleset)
  selectedName.value = name
}

function deleteSelected() {
  if (!selectedRuleset.value || selectedRuleset.value.builtin) return
  const name = selectedRuleset.value.name
  rulesets.value = rulesets.value.filter(r => r.name !== name)
  selectedName.value = rulesets.value.length > 0 ? rulesets.value[0].name : null
}

function syncCurrentConfig() {
  if (!selectedRuleset.value || selectedRuleset.value.builtin) return
  try {
    const parsed = JSON.parse(editingJson.value)
    selectedRuleset.value.config = parsed
  } catch { /* keep current config if invalid */ }
}

function saveCurrent() {
  syncCurrentConfig()
  saveAllRulesets()
}

function saveAllRulesets() {
  const userRulesets = rulesets.value.filter(r => !r.builtin).map(r => ({
    name: r.name,
    description: r.description,
    config: r.config
  }))
  configStore.set('user_fancy', JSON.stringify(userRulesets))
  const enabled = rulesets.value.filter(r => r.enabled).map(r => r.name)
  configStore.set('fancy_allow', enabled)
  configStore.save()
}

function toggleRuleset(name: string) {
  const r = rulesets.value.find(rs => rs.name === name)
  if (!r) return
  r.enabled = !r.enabled
  const enabled = rulesets.value.filter(rs => rs.enabled).map(rs => rs.name)
  configStore.set('fancy_allow', enabled)
  configStore.save()
}

async function applyFancy() {
  syncCurrentConfig()
  saveAllRulesets()
  const configs = rulesets.value.filter(r => r.enabled).map(r => ({ name: r.name, config: r.config }))
  const enableMap: Record<string, boolean> = {}
  for (const r of rulesets.value) { enableMap[r.name] = r.enabled }
  const mid = modalStore.create('progress', { title: '应用文本美化' })
  try {
    await getApi().fancy_main(configs as Array<{ name: string; config: Record<string, unknown> }>, enableMap)
    modalStore.setStatus(mid, 'completed')
    modalStore.updateProgress(mid, 100, '完成')
  } catch {
    modalStore.setStatus(mid, 'canceled')
  }
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-paint-brush"></i> 美化规则</h2>
      <p class="section-subtitle">管理文本美化规则集</p>
    </div>

    <div class="fancy-layout">
      <div class="fancy-left">
        <div class="setting-card">
          <h3 class="setting-title">规则集列表</h3>
          <div v-if="loading" class="list-empty">
            <i class="fas fa-spinner fa-spin"></i><p>加载中...</p>
          </div>
          <div v-else-if="loadError" class="list-empty list-error">
            <i class="fas fa-exclamation-triangle"></i>
            <p>加载规则集失败</p>
            <button class="action-btn" @click="loadRulesets"><i class="fas fa-redo"></i> 重试</button>
          </div>
          <div v-else-if="rulesets.length === 0" class="list-empty">
            <i class="fas fa-inbox"></i>
            <p>暂无规则集</p>
          </div>
          <div
            v-for="r in rulesets"
            :key="r.name"
            class="list-item"
            :class="{ selected: selectedName === r.name }"
            @click="selectRuleset(r.name)"
          >
            <span class="ruleset-name">{{ r.name }}</span>
            <span v-if="r.builtin" class="badge builtin-badge">内置</span>
            <label class="toggle" @click.stop>
              <input v-model="r.enabled" type="checkbox" @change="toggleRuleset(r.name)" />
              <span class="toggle-slider"></span>
            </label>
          </div>
          <div class="button-group">
            <button class="action-btn" @click="createRuleset"><i class="fas fa-plus"></i> 新建规则集</button>
            <button class="action-btn danger" @click="deleteSelected" :disabled="!selectedRuleset || selectedRuleset.builtin"><i class="fas fa-trash"></i> 删除选中规则集</button>
            <button class="primary-btn" @click="saveAllRulesets"><i class="fas fa-save"></i> 保存全部规则集</button>
          </div>
        </div>
      </div>

      <div class="fancy-right">
        <div class="setting-card" v-if="selectedRuleset">
          <div class="editor-header">
            <h3 class="setting-title">编辑规则集: {{ selectedRuleset.name }}</h3>
            <span v-if="selectedRuleset.builtin" class="builtin-hint"><i class="fas fa-lock"></i> 内置规则集，不可编辑</span>
          </div>

          <div class="form-group">
            <label>名称</label>
            <input v-model="selectedRuleset.name" type="text" :disabled="selectedRuleset.builtin" />
          </div>

          <div class="form-group">
            <label>描述</label>
            <input v-model="selectedRuleset.description" type="text" :disabled="selectedRuleset.builtin" placeholder="输入规则集描述" />
          </div>

          <div class="form-group">
            <label>规则 (JSON)</label>
            <textarea
              v-model="editingJson"
              class="rules-textarea"
              :disabled="selectedRuleset.builtin"
              placeholder="{&quot;key&quot;: &quot;value&quot;}"
              spellcheck="false"
            ></textarea>
          </div>

          <div class="button-group">
            <button class="action-btn" @click="formatJson" :disabled="selectedRuleset.builtin"><i class="fas fa-indent"></i> 格式化JSON</button>
            <button v-if="!selectedRuleset.builtin" class="primary-btn" @click="saveCurrent"><i class="fas fa-save"></i> 保存当前规则集</button>
          </div>
        </div>
        <div class="setting-card editor-empty" v-else>
          <div class="empty-state">
            <i class="fas fa-arrow-left"></i>
            <p>请从左侧列表选择一个规则集进行编辑</p>
          </div>
        </div>
      </div>
    </div>

    <div class="fancy-actions">
      <button class="primary-btn" @click="applyFancy"><i class="fas fa-magic"></i> 立即应用美化</button>
    </div>
  </div>
</template>

<style scoped>
.list-error {
  color: var(--color-danger);
}
.list-error .action-btn {
  margin-top: 8px;
}

.fancy-layout {
  display: flex;
  gap: var(--spacing-lg);
  align-items: flex-start;
}

.fancy-left {
  flex: 0 0 320px;
  min-width: 280px;
}

.fancy-left .setting-card {
  height: fit-content;
}

.fancy-left .list-item {
  cursor: pointer;
}

.fancy-right {
  flex: 1;
  min-width: 0;
}

.ruleset-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.builtin-badge {
  background: var(--color-primary);
  color: white;
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-md);
}

.editor-header .setting-title {
  margin-bottom: 0;
}

.builtin-hint {
  font-size: 13px;
  color: var(--color-text-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
}

.rules-textarea {
  width: 100%;
  min-height: 300px;
  padding: var(--spacing-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-input);
  color: var(--color-text-primary);
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
  tab-size: 2;
}

.rules-textarea:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.rules-textarea:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(52, 152, 219, 0.15);
}

.editor-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 300px;
}

.fancy-actions {
  margin-top: var(--spacing-lg);
  text-align: center;
}

.fancy-actions .primary-btn {
  font-size: 16px;
  padding: 14px 32px;
}

@media (max-width: 768px) {
  .fancy-layout {
    flex-direction: column;
  }

  .fancy-left {
    flex: none;
    width: 100%;
    min-width: 0;
  }
}
</style>
