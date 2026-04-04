<template>
  <div class="install-view">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-download"></i> 安装已有汉化
      </h2>
      <p class="section-subtitle">选择并安装本地汉化包</p>
    </div>

    <div class="settings-grid">
      <SettingCard title="汉化包目录">
        <div class="form-group">
          <label>汉化包目录</label>
          <FileInput v-model="packageDirectory" type="folder" placeholder="留空则使用程序所在目录" />
          <small class="form-hint">选择存放汉化包的目录，留空则使用程序所在目录</small>
        </div>

        <div class="form-group">
          <label>可用汉化包</label>
          <div class="list-container">
            <div class="list-header">
              <span>包名称</span>
              <span>操作</span>
            </div>
            <BaseList
              :items="packages"
              v-model:selectedKey="selectedPackage"
              emptyText="未找到可用的汉化包"
              @select="onSelectPackage"
            />
          </div>
        </div>

        <div class="button-group">
          <Button variant="secondary" @click="refreshPackages">
            <i class="fas fa-sync-alt"></i> 刷新列表
          </Button>
          <Button variant="success" @click="installPackage" :disabled="!selectedPackage">
            <i class="fas fa-check-circle"></i> 安装选中汉化包
          </Button>
          <Button variant="danger" @click="deletePackage" :disabled="!selectedPackage">
            <i class="fas fa-trash"></i> 删除选中汉化包
          </Button>
        </div>
      </SettingCard>

      <SettingCard title="字体管理">
        <div class="feature-grid">
          <div class="feature-card">
            <div class="feature-icon"><i class="fas fa-font"></i></div>
            <h4>更换字体</h4>
            <p>为选中的汉化包更换字体</p>
            <Button variant="secondary" @click="changeFont" :disabled="!selectedPackage">更换字体</Button>
          </div>
          <div class="feature-card">
            <div class="feature-icon"><i class="fas fa-file-export"></i></div>
            <h4>导出字体</h4>
            <p>从已安装字体中获取文件</p>
            <Button variant="secondary" @click="exportFont">导出字体</Button>
          </div>
        </div>
      </SettingCard>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useConfigStore } from '@/stores/config'
import { useModalStore } from '@/stores/modal'
import { api } from '@/utils/api'
import SettingCard from '@/components/common/SettingCard.vue'
import Button from '@/components/common/Button.vue'
import FileInput from '@/components/common/FileInput.vue'
import BaseList from '@/components/list/BaseList.vue'

const configStore = useConfigStore()
const modalStore = useModalStore()

const packageDirectory = ref('')
const packages = ref([])
const selectedPackage = ref(null)

// 加载配置
async function loadConfig() {
  packageDirectory.value = configStore.getById('install-package-directory') || ''
}

// 保存配置
watch(packageDirectory, (val) => {
  configStore.updateConfig('install-package-directory', val)
  configStore.flushUpdates()
  refreshPackages()
})

// 刷新汉化包列表
async function refreshPackages() {
  try {
    const result = await api.call('get_translation_packages')
    if (result.success && result.packages) {
      packages.value = result.packages
      if (packages.value.length > 0 && !selectedPackage.value) {
        selectedPackage.value = packages.value[0]
      }
    } else {
      packages.value = []
    }
  } catch (error) {
    modalStore.openModal('message', { title: '错误', content: `获取列表失败: ${error.message}` })
  }
}

function onSelectPackage(item) {
  selectedPackage.value = item
}

// 安装选中包
async function installPackage() {
  if (!selectedPackage.value) {
    modalStore.openModal('message', { title: '提示', content: '请先选择一个汉化包' })
    return
  }

  const modalId = modalStore.openModal('progress', {
    title: '安装汉化包',
    statusText: `开始安装: ${selectedPackage.value}`
  })

  try {
    const result = await api.call('install_translation', selectedPackage.value, modalId)
    if (result.success) {
      modalStore.completeModal(modalId, true, '汉化包安装成功')
      refreshPackages()
    } else {
      modalStore.completeModal(modalId, false, result.message || '安装失败')
    }
  } catch (error) {
    modalStore.completeModal(modalId, false, error.message)
  }
}

// 删除选中包
async function deletePackage() {
  if (!selectedPackage.value) {
    modalStore.openModal('message', { title: '提示', content: '请先选择一个汉化包' })
    return
  }

  modalStore.openModal('confirm', {
    title: '确认删除',
    content: `确定要删除汉化包 "${selectedPackage.value}" 吗？此操作不可撤销。`,
    onConfirm: async () => {
      const result = await api.call('delete_translation_package', selectedPackage.value)
      if (result.success) {
        modalStore.openModal('message', { title: '删除成功', content: `汉化包 "${selectedPackage.value}" 已被删除` })
        refreshPackages()
      } else {
        modalStore.openModal('message', { title: '删除失败', content: result.message })
      }
    }
  })
}

// 更换字体
async function changeFont() {
  if (!selectedPackage.value) {
    modalStore.openModal('message', { title: '提示', content: '请先选择一个汉化包' })
    return
  }

  const fontPath = await api.browse_file('font-path')
  if (!fontPath) return

  const modalId = modalStore.openModal('progress', { title: '更换字体' })
  try {
    const result = await api.call('change_font_for_package', selectedPackage.value, fontPath, modalId)
    if (result.success) {
      modalStore.completeModal(modalId, true, '字体更换成功')
      refreshPackages()
    } else {
      modalStore.completeModal(modalId, false, result.message)
    }
  } catch (error) {
    modalStore.completeModal(modalId, false, error.message)
  }
}

// 导出字体
async function exportFont() {
  const result = await api.call('get_system_fonts_list')
  if (!result.success || !result.fonts?.length) {
    modalStore.openModal('message', { title: '提示', content: '未找到系统字体' })
    return
  }

  // 创建字体选择模态窗
  const fonts = result.fonts
  let selectedFont = null

  // 动态创建选择窗口（简化版，实际可使用更优雅的组件）
  modalStore.openModal('confirm', {
    title: '导出系统字体',
    content: `
      <div class="font-selector">
        <div class="form-group">
          <label>选择字体</label>
          <select id="font-select" style="width:100%;">
            ${fonts.map(f => `<option value="${f}">${f}</option>`).join('')}
          </select>
        </div>
      </div>
    `,
    onConfirm: async () => {
      const selectEl = document.getElementById('font-select')
      selectedFont = selectEl?.value
      if (!selectedFont) return

      const exportPath = await api.browse_folder('font-export-path')
      if (!exportPath) return

      const modalId = modalStore.openModal('progress', { title: '导出字体' })
      try {
        const result = await api.call('export_selected_font', selectedFont, exportPath)
        if (result.success) {
          modalStore.completeModal(modalId, true, '字体导出成功')
        } else {
          modalStore.completeModal(modalId, false, result.message)
        }
      } catch (error) {
        modalStore.completeModal(modalId, false, error.message)
      }
    }
  })
}

onMounted(() => {
  loadConfig()
  refreshPackages()
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
.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: var(--spacing-lg);
}
.list-container {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-input);
  overflow: hidden;
}
.list-header {
  display: flex;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
  font-weight: 500;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--spacing-lg);
  margin-top: var(--spacing-md);
}
.feature-card {
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-border);
  text-align: center;
}
.feature-icon {
  width: 60px;
  height: 60px;
  background: linear-gradient(135deg, var(--color-primary), var(--color-secondary));
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto var(--spacing-md);
  color: white;
  font-size: 24px;
}
.feature-card h4 {
  margin-bottom: var(--spacing-sm);
}
.feature-card p {
  color: var(--color-text-secondary);
  font-size: 14px;
  margin-bottom: var(--spacing-md);
}
.button-group {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
  margin-top: var(--spacing-md);
}
</style>