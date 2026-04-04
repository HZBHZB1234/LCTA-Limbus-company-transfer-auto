<template>
  <div class="fancy-view">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-paint-brush"></i> 美化规则
      </h2>
      <p class="section-subtitle">管理文本美化规则集</p>
    </div>

    <div class="settings-grid two-columns">
      <SettingCard title="规则集列表">
        <ToggleList
          :items="rulesetNames"
          v-model:selectedKey="selectedRulesetName"
          :enabledMap="enabledMap"
          emptyText="暂无规则集"
          @toggle="onToggleRuleset"
          @select="onSelectRuleset"
        />
        <div class="button-group">
          <Button variant="secondary" @click="newRuleset">新建</Button>
          <Button variant="success" @click="saveAll">保存全部</Button>
          <Button variant="danger" @click="deleteSelected" :disabled="!selectedRulesetName">删除</Button>
          <Button variant="primary" @click="applyFancy">立即应用美化</Button>
        </div>
      </SettingCard>

      <SettingCard title="规则集编辑器">
        <div class="form-group">
          <label>名称</label>
          <input type="text" v-model="editingName" :disabled="isBuiltin" />
        </div>
        <div class="form-group">
          <label>描述</label>
          <input type="text" v-model="editingDesc" :disabled="isBuiltin" />
        </div>
        <div class="form-group">
          <label>规则 (JSON 格式)</label>
          <textarea v-model="editingRules" rows="12" :disabled="isBuiltin" class="monospace"></textarea>
          <div class="button-group">
            <Button variant="secondary" @click="formatJson" :disabled="isBuiltin">格式化JSON</Button>
          </div>
        </div>
        <div v-if="isBuiltin" class="builtin-notice">内置规则集（不可编辑）</div>
        <div class="action-area">
          <Button variant="primary" @click="saveCurrent" :disabled="isBuiltin">保存当前</Button>
        </div>
      </SettingCard>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useConfigStore } from '@/stores/config'
import { useModalStore } from '@/stores/modal'
import { api } from '@/utils/api'
import SettingCard from '@/components/common/SettingCard.vue'
import Button from '@/components/common/Button.vue'
import ToggleList from '@/components/list/ToggleList.vue'

const configStore = useConfigStore()
const modalStore = useModalStore()

// 数据
const rulesets = ref([])        // { name, desc, rules, builtin, conflict }
const enabledMap = ref({})
const selectedRulesetName = ref(null)

// 编辑状态
const editingName = ref('')
const editingDesc = ref('')
const editingRules = ref('')
const isBuiltin = ref(false)

// 计算属性
const rulesetNames = computed(() => rulesets.value.map(rs => rs.name))

// 加载规则集
async function loadRulesets() {
  try {
    const result = await api.call('get_fancy_rulesets')
    if (result.success) {
      const builtin = result.data.builtin || []
      const user = result.data.user || []
      rulesets.value = [
        ...builtin.map(rs => ({ ...rs, builtin: true })),
        ...user.map(rs => ({ ...rs, builtin: false }))
      ]
      enabledMap.value = result.data.enabled || {}
      if (rulesets.value.length > 0 && !selectedRulesetName.value) {
        selectedRulesetName.value = rulesets.value[0].name
        loadSelectedRuleset()
      }
    }
  } catch (error) {
    modalStore.openModal('message', { title: '错误', content: `加载规则集失败: ${error.message}` })
  }
}

function loadSelectedRuleset() {
  const rs = rulesets.value.find(r => r.name === selectedRulesetName.value)
  if (rs) {
    editingName.value = rs.name
    editingDesc.value = rs.desc || ''
    editingRules.value = JSON.stringify(rs.rules, null, 2)
    isBuiltin.value = rs.builtin || false
  }
}

function onSelectRuleset(name) {
  selectedRulesetName.value = name
  loadSelectedRuleset()
}

function onToggleRuleset(item, enabled) {
  // 检查冲突
  const rs = rulesets.value.find(r => r.name === item)
  if (rs && rs.conflict) {
    for (const conflict of rs.conflict) {
      if (enabledMap.value[conflict]) {
        modalStore.openModal('message', {
          title: '冲突',
          content: `无法在启用 ${conflict} 的情况下启用 ${item}。请先取消冲突规则的启用。`
        })
        return
      }
    }
  }
  enabledMap.value[item] = enabled
}

// 保存当前编辑的规则集
async function saveCurrent() {
  if (isBuiltin.value) {
    modalStore.openModal('message', { title: '提示', content: '内置规则集不可编辑' })
    return
  }

  const newName = editingName.value.trim()
  if (!newName) {
    modalStore.openModal('message', { title: '提示', content: '规则集名称不能为空' })
    return
  }

  let newRules
  try {
    newRules = JSON.parse(editingRules.value)
    if (!Array.isArray(newRules)) throw new Error('规则必须是一个数组')
  } catch (e) {
    modalStore.openModal('message', { title: '错误', content: `JSON格式错误: ${e.message}` })
    return
  }

  const oldName = selectedRulesetName.value
  const rs = rulesets.value.find(r => r.name === oldName)
  if (rs) {
    // 如果名称改变，需要更新
    if (oldName !== newName) {
      if (rulesets.value.some(r => r.name === newName)) {
        modalStore.openModal('message', { title: '错误', content: '已存在同名的规则集' })
        return
      }
      // 更新 enabledMap
      enabledMap.value[newName] = enabledMap.value[oldName]
      delete enabledMap.value[oldName]
      rs.name = newName
    }
    rs.desc = editingDesc.value
    rs.rules = newRules
    selectedRulesetName.value = newName
  }
  modalStore.openModal('message', { title: '成功', content: '规则集已保存' })
}

// 新建规则集
function newRuleset() {
  const newName = prompt('请输入新规则集名称（不可与现有重名）')
  if (!newName) return
  if (rulesets.value.some(r => r.name === newName)) {
    modalStore.openModal('message', { title: '错误', content: '名称已存在' })
    return
  }
  const newRs = {
    name: newName,
    desc: '',
    rules: [],
    builtin: false
  }
  rulesets.value.push(newRs)
  enabledMap.value[newName] = false
  selectedRulesetName.value = newName
  loadSelectedRuleset()
}

// 删除选中的规则集
function deleteSelected() {
  if (!selectedRulesetName.value) return
  const rs = rulesets.value.find(r => r.name === selectedRulesetName.value)
  if (rs?.builtin) {
    modalStore.openModal('message', { title: '提示', content: '内置规则集不能删除' })
    return
  }
  modalStore.openModal('confirm', {
    title: '确认删除',
    content: `确定要删除规则集 "${selectedRulesetName.value}" 吗？`,
    onConfirm: () => {
      const index = rulesets.value.findIndex(r => r.name === selectedRulesetName.value)
      if (index !== -1) {
        rulesets.value.splice(index, 1)
        delete enabledMap.value[selectedRulesetName.value]
        if (rulesets.value.length > 0) {
          selectedRulesetName.value = rulesets.value[0].name
          loadSelectedRuleset()
        } else {
          selectedRulesetName.value = null
          editingName.value = ''
          editingDesc.value = ''
          editingRules.value = ''
        }
      }
    }
  })
}

// 保存所有规则集到后端
async function saveAll() {
  const userRulesets = rulesets.value.filter(rs => !rs.builtin).map(({ builtin, ...rest }) => rest)
  configStore.updateConfig('fancy-user', JSON.stringify(userRulesets))
  configStore.updateConfig('fancy-allow', JSON.stringify(enabledMap.value))
  await configStore.flushUpdates()
  modalStore.openModal('message', { title: '成功', content: '所有规则集已保存' })
}

// 格式化JSON
function formatJson() {
  try {
    const obj = JSON.parse(editingRules.value)
    editingRules.value = JSON.stringify(obj, null, 2)
  } catch (e) {
    modalStore.openModal('message', { title: '错误', content: 'JSON格式错误，无法格式化' })
  }
}

// 立即应用美化
async function applyFancy() {
  const modalId = modalStore.openModal('progress', { title: '应用美化文本' })
  try {
    await api.call('fancy_main', rulesets.value, enabledMap.value)
    modalStore.completeModal(modalId, true, '美化完成')
    setTimeout(() => modalStore.closeModal(modalId), 2000)
  } catch (error) {
    modalStore.completeModal(modalId, false, error.message)
  }
}

onMounted(() => {
  loadRulesets()
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
.settings-grid.two-columns {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: var(--spacing-lg);
}
.button-group {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
  margin-top: var(--spacing-md);
}
.monospace {
  font-family: 'Consolas', monospace;
  font-size: 13px;
  width: 100%;
}
.builtin-notice {
  margin-top: var(--spacing-md);
  padding: var(--spacing-sm);
  background: var(--color-bg-primary);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  text-align: center;
  font-size: 12px;
}
.action-area {
  margin-top: var(--spacing-lg);
  padding-top: var(--spacing-md);
  border-top: 1px solid var(--color-border);
}
</style>