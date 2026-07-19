<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getApi } from '@/utils/api'
import { useModalStore } from '@/stores/modal'
import { listenEvent } from '@/utils/events'
import { useConfigStore } from '@/stores/config'

const modalStore = useModalStore()
const configStore = useConfigStore()

const packageDirectory = ref('')
const packages = ref<Array<{ name: string; path: string; size?: number }>>([])
const selectedPackage = ref<string | null>(null)

listenEvent('lcta:file-picked', (detail) => {
  if (detail.inputId === 'install-package-directory') packageDirectory.value = detail.path
})

onMounted(async () => {
  packageDirectory.value = configStore.get<string>('ui_default.install.package_directory') || ''
  await refreshList()
})

async function refreshList() {
  packages.value = await getApi().get_translation_packages()
}

async function installPackage() {
  if (!selectedPackage.value) return
  const mid = modalStore.create('progress', { title: `安装 ${selectedPackage.value}` })
  getApi().install_translation(selectedPackage.value, mid)
}

async function deletePackage() {
  if (!selectedPackage.value) return
  await getApi().delete_translation_package(selectedPackage.value)
  await refreshList()
}

async function browseDir() {
  await getApi().browse_folder('install-package-directory')
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-download"></i> 安装已有汉化</h2>
      <p class="section-subtitle">选择并安装本地汉化包</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card">
        <h3 class="setting-title">汉化包目录</h3>
        <div class="form-group">
          <label>汉化包目录:</label>
          <div class="file-input-group">
            <input v-model="packageDirectory" type="text" placeholder="留空则使用程序所在目录" />
            <button class="action-btn secondary" @click="browseDir">
              <i class="fas fa-folder-open"></i> 浏览
            </button>
          </div>
          <small class="form-hint">选择存放汉化包的目录，留空则使用程序所在目录</small>
        </div>

        <div class="form-group">
          <label>可用汉化包:</label>
          <div class="list-container">
            <div v-if="packages.length === 0" class="list-empty">
              <i class="fas fa-box-open"></i>
              <p>未找到可用的汉化包</p>
            </div>
            <div
              v-for="pkg in packages" :key="pkg.name"
              class="list-item" :class="{ selected: selectedPackage === pkg.name }"
              @click="selectedPackage = pkg.name"
            >
              <span>{{ pkg.name }}</span>
              <span v-if="pkg.size" class="list-item-size">{{ (pkg.size / 1024 / 1024).toFixed(1) }} MB</span>
            </div>
          </div>
        </div>

        <div class="button-group">
          <button class="action-btn" @click="refreshList"><i class="fas fa-sync-alt"></i> 刷新列表</button>
          <button class="action-btn success" :disabled="!selectedPackage" @click="installPackage">
            <i class="fas fa-check-circle"></i> 安装选中汉化包
          </button>
          <button class="action-btn danger" :disabled="!selectedPackage" @click="deletePackage">
            <i class="fas fa-trash"></i> 删除选中汉化包
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
.settings-grid { display: grid; grid-template-columns: 1fr; gap: 20px; }
.setting-card { background: var(--bg-secondary); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color); }
.setting-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 14px; color: var(--text-secondary); margin-bottom: 6px; }
.form-group input[type="text"] {
  width: 100%; padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border-color);
  background: var(--bg-primary); color: var(--text-primary); font-size: 14px;
}
.file-input-group { display: flex; gap: 8px; }
.file-input-group input { flex: 1; }
.form-hint { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.list-container { border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; }
.list-item {
  padding: 10px 16px; cursor: pointer; border-bottom: 1px solid var(--border-color);
  display: flex; justify-content: space-between; align-items: center;
}
.list-item:hover { background: var(--bg-primary); }
.list-item.selected { background: var(--accent-color); color: white; }
.list-item:last-child { border-bottom: none; }
.list-empty { padding: 24px; text-align: center; color: var(--text-secondary); }
.list-item-size { font-size: 12px; opacity: 0.7; }
.button-group { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 16px; }
.action-btn {
  padding: 8px 16px; border-radius: 8px; border: 1px solid var(--border-color);
  background: var(--bg-primary); color: var(--text-primary); cursor: pointer; font-size: 14px;
}
.action-btn:hover { background: var(--bg-secondary); }
.action-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.action-btn.success { border-color: #27ae60; color: #27ae60; }
.action-btn.danger { border-color: #e74c3c; color: #e74c3c; }
.secondary { font-size: 12px; }
</style>
