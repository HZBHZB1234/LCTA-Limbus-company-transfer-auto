<template>
  <div class="manage-view">
    <div class="section-header">
      <h2 class="section-title">
        <i class="fas fa-archive"></i> 已安装数据管理
      </h2>
      <p class="section-subtitle">控制本地已安装修改包，包括汉化包和皮肤mod</p>
    </div>

    <div class="settings-grid">
      <SettingCard>
        <Checkbox v-model="enableLang">启用客制化翻译</Checkbox>

        <div v-if="enableLang" class="installed-section">
          <div class="form-group">
            <label>已安装汉化包</label>
            <BaseList
              :items="installedPackages"
              v-model:selectedKey="selectedPackage"
              emptyText="未找到已安装汉化包"
              @select="onSelectPackage"
            />
          </div>
          <div class="button-group">
            <Button variant="secondary" @click="refreshInstalledPackages">刷新列表</Button>
            <Button variant="success" @click="useSelectedPackage" :disabled="!selectedPackage">使用选中汉化包</Button>
            <Button variant="danger" @click="deleteInstalledPackage" :disabled="!selectedPackage">删除选中汉化包</Button>
          </div>
        </div>
        <div v-else class="disabled-overlay">
          <i class="fas fa-lock"></i>
          <p>客制化翻译已禁用</p>
          <small>勾选上方选项以启用此区域</small>
        </div>
      </SettingCard>

      <SettingCard title="模组目录">
        <div class="form-group">
          <label>模组安装目录</label>
          <FileInput v-model="modDirectory" type="folder" placeholder="留空则使用默认路径" />
          <small class="form-hint">选择存放模组的目录，留空则使用默认目录</small>
        </div>

        <div class="form-group">
          <label>可用模组</label>
          <ToggleList
            :items="mods"
            v-model:selectedKey="selectedMod"
            :enabledMap="modEnabledMap"
            emptyText="未找到可用的模组"
            @toggle="onToggleMod"
            @select="onSelectMod"
          />
        </div>

        <div class="button-group">
          <Button variant="secondary" @click="refreshMods">刷新列表</Button>
          <Button variant="success" @click="openModFolder">打开mod文件夹</Button>
          <Button variant="danger" @click="deleteSelectedMod" :disabled="!selectedMod">删除选中模组</Button>
        </div>
      </SettingCard>

      <SettingCard title="C盘数据管理">
        <p class="form-hint">管理 Unity 和 ProjectMoon 数据目录的符号链接，便于迁移数据。</p>

        <div class="form-group">
          <label>数据文件夹</label>
          <ActionList
            :items="symlinkItems"
            v-model:selectedKey="selectedSymlink"
            :actionButtonText="getSymlinkActionText"
            :onAction="onSymlinkAction"
            emptyText="加载中..."
            @select="onSelectSymlink"
          />
        </div>

        <div class="button-group">
          <Button variant="secondary" @click="refreshSymlink">刷新列表</Button>
          <Button variant="success" @click="createSymlink" :disabled="!selectedSymlink">创建或修改软链接</Button>
          <Button variant="danger" @click="removeSymlink" :disabled="!selectedSymlink">删除软链接</Button>
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
import Checkbox from '@/components/common/Checkbox.vue'
import FileInput from '@/components/common/FileInput.vue'
import BaseList from '@/components/list/BaseList.vue'
import ToggleList from '@/components/list/ToggleList.vue'
import ActionList from '@/components/list/ActionList.vue'

const configStore = useConfigStore()
const modalStore = useModalStore()

// 客制化翻译
const enableLang = ref(true)

// 已安装汉化包
const installedPackages = ref([])
const selectedPackage = ref(null)

// 模组
const modDirectory = ref('')
const mods = ref([])
const modEnabledMap = ref({})
const selectedMod = ref(null)

// 软链接
const symlinkItems = ref(['ProjectMoon', 'Unity'])
const symlinkStatus = ref({})
const selectedSymlink = ref(null)

// 加载配置
function loadConfig() {
  enableLang.value = configStore.getById('enable-lang') !== false
  modDirectory.value = configStore.getById('installed-mod-directory') || ''
}

watch(enableLang, (val) => {
  configStore.updateConfig('enable-lang', val)
  configStore.flushUpdates()
  if (val) refreshInstalledPackages()
})

watch(modDirectory, (val) => {
  configStore.updateConfig('installed-mod-directory', val)
  configStore.flushUpdates()
  refreshMods()
})

// 已安装汉化包
async function refreshInstalledPackages() {
  try {
    const result = await api.call('get_installed_packages')
    if (result.success && result.enable) {
      installedPackages.value = result.packages || []
      selectedPackage.value = result.selected || null
    } else {
      installedPackages.value = []
    }
  } catch (error) {
    console.error('刷新已安装汉化包失败:', error)
  }
}

function onSelectPackage(item) {
  selectedPackage.value = item
}

async function useSelectedPackage() {
  if (!selectedPackage.value) return
  const modalId = modalStore.openModal('progress', { title: '切换汉化包' })
  try {
    const result = await api.call('use_translation', selectedPackage.value, modalId)
    if (result.success) {
      modalStore.completeModal(modalId, true, '汉化包切换成功')
      setTimeout(() => modalStore.closeModal(modalId), 500)
      refreshInstalledPackages()
    } else {
      modalStore.completeModal(modalId, false, result.message)
    }
  } catch (error) {
    modalStore.completeModal(modalId, false, error.message)
  }
}

async function deleteInstalledPackage() {
  if (!selectedPackage.value) return
  modalStore.openModal('confirm', {
    title: '确认删除',
    content: `确定要删除汉化包 "${selectedPackage.value}" 吗？此操作不可撤销。`,
    onConfirm: async () => {
      const result = await api.call('delete_installed_package', selectedPackage.value)
      if (result.success) {
        modalStore.openModal('message', { title: '删除成功', content: `汉化包 "${selectedPackage.value}" 已被删除` })
        refreshInstalledPackages()
      } else {
        modalStore.openModal('message', { title: '删除失败', content: result.message })
      }
    }
  })
}

// 模组
async function refreshMods() {
  try {
    const result = await api.call('find_installed_mod')
    if (result.success) {
      const allMods = [...(result.able || []), ...(result.disable || [])]
      mods.value = allMods
      modEnabledMap.value = {}
      result.able.forEach(m => { modEnabledMap.value[m] = true })
      result.disable.forEach(m => { modEnabledMap.value[m] = false })
    }
  } catch (error) {
    console.error('刷新模组列表失败:', error)
  }
}

function onSelectMod(item) {
  selectedMod.value = item
}

async function onToggleMod(item, enabled) {
  await api.call('toggle_mod', item, enabled)
  refreshMods()
}

async function openModFolder() {
  await api.call('open_mod_path')
}

async function deleteSelectedMod() {
  if (!selectedMod.value) return
  modalStore.openModal('confirm', {
    title: '确认删除',
    content: `确定要删除模组 "${selectedMod.value}" 吗？`,
    onConfirm: async () => {
      const result = await api.call('delete_mod', selectedMod.value, modEnabledMap.value[selectedMod.value])
      if (result.success) {
        refreshMods()
      } else {
        modalStore.openModal('message', { title: '删除失败', content: result.message })
      }
    }
  })
}

// 软链接
async function loadSymlinkStatus() {
  try {
    const result = await api.call('get_symlink_status')
    if (result.success) symlinkStatus.value = result.status || {}
  } catch (error) {
    console.error('加载软链接状态失败:', error)
  }
}

function getSymlinkActionText(item) {
  const status = symlinkStatus.value[item]
  if (!status) return '未知'
  switch (status.status) {
    case 'not_exist': return '不存在'
    case 'not_symlink': return '文件夹'
    case 'symlink': return '软链接'
    default: return '错误'
  }
}

function onSymlinkAction(item) {
  const status = symlinkStatus.value[item]
  if (!status) return
  if (status.status === 'not_symlink') {
    api.call('run_func', 'open_explorer', status.path)
  } else if (status.status === 'symlink') {
    api.call('run_func', 'open_explorer', status.target)
  }
}

function onSelectSymlink(item) {
  selectedSymlink.value = item
}

async function refreshSymlink() {
  await loadSymlinkStatus()
}

async function createSymlink() {
  if (!selectedSymlink.value) return
  const folder = symlinkStatus.value[selectedSymlink.value]
  if (!folder) return

  const action = () => {
    modalStore.openModal('confirm', {
      title: '选择目标文件夹',
      content: '请选择您想要存放数据的文件夹',
      onConfirm: async () => {
        const targetDir = await api.browse_folder('symlink-target-dir')
        if (!targetDir) return

        const hasContent = await api.call('run_func', 'evaluate_path', targetDir)
        const doCreate = async () => {
          if (folder.status === 'symlink') {
            await api.call('run_func', 'remove_symlink', folder.path)
          }
          if (folder.status === 'not_symlink' && folder.path) {
            await api.call('move_folders', folder.path, targetDir)
          }
          await api.call('run_func', 'create_symlink', targetDir, folder.path)
          refreshSymlink()
        }

        if (hasContent) {
          modalStore.openModal('confirm', {
            title: '警告',
            content: '目标文件夹中含有文件。可能出现非预期行为。如果你确定知道自己在做什么，请点击确定',
            onConfirm: doCreate
          })
        } else {
          doCreate()
        }
      }
    })
  }

  if (folder.status === 'symlink') {
    modalStore.openModal('confirm', {
      title: '更换软链接',
      content: `您已经创建了一个可用的软链接，它的目录是 ${folder.target}，是否更换目录？`,
      onConfirm: action
    })
  } else if (folder.status === 'not_symlink') {
    modalStore.openModal('confirm', {
      title: '创建软链接',
      content: '是否要创建软链接？',
      onConfirm: action
    })
  } else if (folder.status === 'not_exist') {
    modalStore.openModal('confirm', {
      title: '创建软链接',
      content: '现在对应位置没有目录，如果您先前手动迁移了数据，请选择迁移后的文件夹',
      onConfirm: action
    })
  }
}

async function removeSymlink() {
  if (!selectedSymlink.value) return
  const folder = symlinkStatus.value[selectedSymlink.value]
  if (!folder || folder.status !== 'symlink') {
    modalStore.openModal('message', { title: '警告', content: '当前数据项不是软链接' })
    return
  }
  modalStore.openModal('confirm', {
    title: '删除软链接',
    content: `是否要删除软链接？这将使文件夹重新回到c盘`,
    onConfirm: async () => {
      await api.call('run_func', 'remove_symlink', folder.path)
      await api.call('move_folders', folder.target, folder.path)
      refreshSymlink()
    }
  })
}

onMounted(() => {
  loadConfig()
  refreshInstalledPackages()
  refreshMods()
  refreshSymlink()
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
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: var(--spacing-lg);
}
.installed-section {
  position: relative;
}
.disabled-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(128, 128, 128, 0.6);
  backdrop-filter: blur(3px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-lg);
  text-align: center;
  color: white;
  z-index: 10;
}
.disabled-overlay i {
  font-size: 48px;
  margin-bottom: 12px;
}
.button-group {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
  margin-top: var(--spacing-md);
}
.form-hint {
  font-size: 12px;
  color: var(--color-text-secondary);
}
</style>