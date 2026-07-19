<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getApi } from '@/utils/api'
import { useModalStore } from '@/stores/modal'

const modalStore = useModalStore()

const enableLang = ref(true)
const installedPackages = ref<Array<{ name: string; selected: boolean }>>([])
const mods = ref<Array<{ name: string; enabled: boolean }>>([])

onMounted(async () => {
  await refreshAll()
})

async function refreshAll() {
  try {
    const result = await getApi().get_installed_packages()
    installedPackages.value = (result.packages || []).map((p: { name: string }) => ({
      name: p.name,
      selected: result.selected === p.name,
    }))
  } catch { /* ignore */ }

  try {
    const modResult = await getApi().find_installed_mod()
    const able = (modResult.able || []).map((m: { name: string }) => ({ name: m.name, enabled: true }))
    const disable = (modResult.disable || []).map((m: { name: string }) => ({ name: m.name, enabled: false }))
    mods.value = [...able, ...disable]
  } catch { /* ignore */ }
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
    </div>
  </div>
</template>

<style scoped>
.section-header { margin-bottom: 24px; }
.section-title { font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.section-title i { color: var(--accent-color); }
.section-subtitle { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }
.settings-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 20px; }
.setting-card { background: var(--bg-secondary); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color); }
.setting-title { font-size: 16px; font-weight: 600; margin: 16px 0 12px; }
.form-group { margin-bottom: 14px; }
.list-item {
  display: flex; align-items: center; gap: 8px; padding: 10px 12px;
  border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 6px;
}
.list-item.active { border-color: var(--accent-color); }
.list-empty { padding: 24px; text-align: center; color: var(--text-secondary); }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; }
.badge.enabled { background: #27ae60; color: white; }
.badge.disabled { background: var(--text-secondary); color: white; }
.list-actions { margin-left: auto; display: flex; gap: 4px; }
.action-btn-sm {
  padding: 4px 12px; border-radius: 6px; border: 1px solid var(--border-color);
  background: var(--bg-primary); color: var(--text-primary); cursor: pointer; font-size: 12px;
}
.action-btn-sm.danger { color: #e74c3c; border-color: #e74c3c; }
.action-btn {
  padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border-color);
  background: var(--bg-primary); color: var(--text-primary); cursor: pointer; font-size: 14px;
}
.checkbox-label { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 14px; }
</style>
