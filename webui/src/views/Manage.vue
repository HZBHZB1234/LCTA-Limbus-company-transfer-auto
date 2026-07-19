<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { getApi } from '@/utils/api'
import { useModalStore } from '@/stores/modal'
import { listenEvent } from '@/utils/events'
import { useConfigStore } from '@/stores/config'

const modalStore = useModalStore()
const configStore = useConfigStore()

const enableLang = ref(true)
const installedPackages = ref<Array<{ name: string; selected: boolean }>>([])
const mods = ref<Array<{ name: string; enabled: boolean }>>([])

interface SymlinkItem {
  status: string
  path: string
  target: string
}

const modDirectory = ref('')
const symlinkStatus = ref<{
  ProjectMoon: SymlinkItem | null
  Unity: SymlinkItem | null
}>({
  ProjectMoon: null,
  Unity: null,
})
const selectedSymlink = ref<'ProjectMoon' | 'Unity' | null>(null)

const symlinkItems = computed(() => [
  { key: 'ProjectMoon' as const, data: symlinkStatus.value.ProjectMoon },
  { key: 'Unity' as const, data: symlinkStatus.value.Unity },
])

function statusLabel(status?: string) {
  const map: Record<string, string> = {
    symlink: '符号链接',
    not_symlink: '非符号链接',
    directory: '普通目录',
  }
  return map[status || ''] || (status || '未知')
}

listenEvent('lcta:file-picked', (detail) => {
  if (detail.inputId === 'installed-mod-directory') {
    modDirectory.value = detail.path
    configStore.set('ui_default.manage.mod_path', detail.path)
    configStore.save()
  }
  if (detail.inputId === 'symlink-target-dir') {
    proceedSymlinkCreate(detail.path)
  }
})

onMounted(async () => {
  modDirectory.value = configStore.get<string>('ui_default.manage.mod_path') || ''
  await refreshAll()
})

async function refreshAll() {
  try {
    const result = await getApi().get_installed_packages()
    installedPackages.value = (result.packages || []).map((p: { name: string }) => ({
      name: p.name,
      selected: result.selected === p.name,
    }))
  } catch (e) {
    console.error('Manage packages load failed:', e)
    getApi().log(`[Manage] 已安装包列表加载失败: ${e}`).catch(() => {})
  }

  try {
    const modResult = await getApi().find_installed_mod()
    const able = (modResult.able || []).map((m: { name: string }) => ({ name: m.name, enabled: true }))
    const disable = (modResult.disable || []).map((m: { name: string }) => ({ name: m.name, enabled: false }))
    mods.value = [...able, ...disable]
  } catch (e) {
    console.error('Manage mods load failed:', e)
    getApi().log(`[Manage] Mod列表加载失败: ${e}`).catch(() => {})
  }

  try {
    await refreshSymlinkStatus()
  } catch (e) {
    console.error('Manage symlink status load failed:', e)
    getApi().log(`[Manage] 符号链接状态加载失败: ${e}`).catch(() => {})
  }
}

async function toggleLang() {
  await getApi().toggle_installed_package(enableLang.value)
}

async function usePackage(name: string) {
  const mid = modalStore.create('progress', { title: `切换汉化包: ${name}` })
  await getApi().use_translation(name, mid)
  await refreshAll()
}

async function deletePackage(name: string) {
  await getApi().delete_installed_package(name)
  await refreshAll()
}

async function toggleMod(name: string, enabled: boolean) {
  await getApi().toggle_mod(name, !enabled)
  await refreshAll()
}

async function deleteMod(name: string) {
  await getApi().delete_mod(name, true)
  await refreshAll()
}

async function openModPath() {
  await getApi().open_mod_path()
}

function browseModDir() {
  getApi().browse_folder('installed-mod-directory')
}

function clearModDir() {
  modDirectory.value = ''
  configStore.set('ui_default.manage.mod_path', '')
  configStore.save()
}

async function refreshSymlinkStatus() {
  try {
    const result = await getApi().get_symlink_status()
    const data = result as unknown as { status: { ProjectMoon: SymlinkItem; Unity: SymlinkItem } }
    if (data.status) {
      symlinkStatus.value.ProjectMoon = data.status.ProjectMoon || null
      symlinkStatus.value.Unity = data.status.Unity || null
    }
  } catch (e) {
    console.error('Manage symlink status refresh failed:', e)
    getApi().log(`[Manage] 符号链接状态刷新失败: ${e}`).catch(() => {})
  }
}

function selectSymlink(key: 'ProjectMoon' | 'Unity') {
  selectedSymlink.value = key
}

async function createOrModifySymlink() {
  if (!selectedSymlink.value) return
  await getApi().browse_folder('symlink-target-dir')
}

async function proceedSymlinkCreate(targetDir: string) {
  if (!selectedSymlink.value) return
  const itemData = symlinkStatus.value[selectedSymlink.value]
  if (!itemData) return

  const folderPath = itemData.path

  if (itemData.status === 'directory') {
    const confirmId = modalStore.create('confirm', {
      title: '目录已存在',
      confirmText: '删除并创建符号链接',
      onConfirm: async () => {
        modalStore.remove(confirmId)
        await getApi().run_func('remove_symlink', folderPath)
        await getApi().run_func('create_symlink', targetDir, folderPath)
        await refreshSymlinkStatus()
      },
    })
  } else {
    const confirmId = modalStore.create('confirm', {
      title: '创建符号链接',
      confirmText: '确认创建',
      onConfirm: async () => {
        modalStore.remove(confirmId)
        await getApi().run_func('create_symlink', targetDir, folderPath)
        await refreshSymlinkStatus()
      },
    })
  }
}

async function removeSymlink() {
  if (!selectedSymlink.value) return
  const itemData = symlinkStatus.value[selectedSymlink.value]
  if (!itemData) return

  const confirmId = modalStore.create('confirm', {
    title: '删除符号链接',
    confirmText: '确认删除',
    onConfirm: async () => {
      modalStore.remove(confirmId)
      await getApi().run_func('remove_symlink', itemData.path)
      await refreshSymlinkStatus()
    },
  })
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-download"></i> 已安装数据管理</h2>
      <p class="section-subtitle">控制本地已安装的汉化包和皮肤mod</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card">
        <div class="form-group">
          <label class="checkbox-label">
            <input v-model="enableLang" type="checkbox" @change="toggleLang" /> 启用客制化翻译
          </label>
        </div>

        <h3 class="setting-title">已安装汉化包</h3>
        <div v-if="installedPackages.length === 0" class="list-empty">
          <i class="fas fa-box-open"></i><p>未找到已安装汉化包</p>
        </div>
        <div v-for="pkg in installedPackages" :key="pkg.name" class="list-item" :class="{ active: pkg.selected }">
          <span>{{ pkg.name }}</span>
          <span v-if="pkg.selected" class="badge">当前</span>
          <div class="list-actions">
            <button class="action-btn-sm" @click="usePackage(pkg.name)">使用</button>
            <button class="action-btn-sm danger" @click="deletePackage(pkg.name)">删除</button>
          </div>
        </div>
        <div style="margin-top: 12px">
          <button class="action-btn" @click="refreshAll"><i class="fas fa-sync-alt"></i> 刷新</button>
        </div>
      </div>

      <div class="setting-card">
        <h3 class="setting-title">已安装 Mod</h3>
        <div v-if="mods.length === 0" class="list-empty">
          <i class="fas fa-box-open"></i><p>未找到 Mod</p>
        </div>
        <div v-for="mod in mods" :key="mod.name" class="list-item">
          <span>{{ mod.name }}</span>
          <span :class="['badge', mod.enabled ? 'enabled' : 'disabled']">
            {{ mod.enabled ? '启用' : '禁用' }}
          </span>
          <div class="list-actions">
            <button class="action-btn-sm" @click="toggleMod(mod.name, mod.enabled)">
              {{ mod.enabled ? '禁用' : '启用' }}
            </button>
            <button class="action-btn-sm danger" @click="deleteMod(mod.name)">删除</button>
          </div>
        </div>
        <div style="margin-top: 12px">
          <button class="action-btn" @click="openModPath"><i class="fas fa-folder-open"></i> 打开 Mod 目录</button>
        </div>
      </div>

      <div class="setting-card">
        <h3 class="setting-title"><i class="fas fa-folder"></i> Mod 目录管理</h3>
        <div class="form-group">
          <label>Mod 目录:</label>
          <div class="file-input-group">
            <input
              id="installed-mod-directory"
              v-model="modDirectory"
              type="text"
              placeholder="选择 Mod 存放目录"
            />
            <button class="action-btn secondary" @click="browseModDir">
              <i class="fas fa-folder-open"></i> 浏览
            </button>
            <button class="action-btn secondary" @click="clearModDir">
              <i class="fas fa-times"></i> 清除
            </button>
          </div>
        </div>
      </div>

      <div class="setting-card">
        <h3 class="setting-title">
          <i class="fas fa-link"></i> C盘数据管理（符号链接）
          <button class="action-btn-sm" style="margin-left: 12px" @click="refreshSymlinkStatus">
            <i class="fas fa-sync-alt"></i> 刷新
          </button>
        </h3>

        <div v-if="!symlinkStatus.ProjectMoon && !symlinkStatus.Unity" class="list-empty">
          <i class="fas fa-link"></i>
          <p>点击刷新获取符号链接状态</p>
        </div>

        <div
          v-for="item in symlinkItems"
          :key="item.key"
          class="symlink-item"
          :class="{ selected: selectedSymlink === item.key }"
          @click="selectSymlink(item.key)"
        >
          <span class="symlink-name">{{ item.key }}</span>
          <span :class="['status-badge', item.data?.status]">
            {{ statusLabel(item.data?.status) }}
          </span>
          <span v-if="item.data?.path" class="symlink-path">{{ item.data.path }}</span>
        </div>

        <div class="symlink-actions">
          <button class="action-btn" :disabled="!selectedSymlink" @click="createOrModifySymlink">
            <i class="fas fa-plus"></i> 创建或修改符号链接
          </button>
          <button
            class="action-btn danger"
            :disabled="!selectedSymlink || !symlinkStatus[selectedSymlink]"
            @click="removeSymlink"
          >
            <i class="fas fa-trash"></i> 删除符号链接
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.badge.enabled { background: var(--color-success); color: white; }
.badge.disabled { background: var(--color-text-secondary); color: white; }
.list-actions { margin-left: auto; display: flex; gap: 4px; }
.action-btn-sm {
  padding: 4px 12px; border-radius: 6px; border: 1px solid var(--color-border);
  background: var(--color-bg-input); color: var(--color-text-primary); cursor: pointer; font-size: 12px;
  transition: all 0.2s ease;
}
.action-btn-sm:hover { background: var(--color-primary); color: white; border-color: var(--color-primary); }
.action-btn-sm.danger { color: var(--color-danger); border-color: var(--color-danger); }
.action-btn-sm.danger:hover { background: var(--color-danger); color: white; }

.symlink-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--color-bg-input);
}
.symlink-item:hover { border-color: var(--color-primary); }
.symlink-item.selected { border-color: var(--color-primary); background: rgba(var(--color-primary-rgb, 59, 130, 246), 0.08); }

.symlink-name { font-weight: 600; min-width: 120px; }

.status-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  background: var(--color-text-secondary); color: white;
}
.status-badge.symlink { background: var(--color-success); }
.status-badge.not_symlink { background: var(--color-text-secondary); }
.status-badge.directory { background: #f59e0b; }

.symlink-path {
  font-size: 12px;
  opacity: 0.7;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.symlink-actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
}
</style>
