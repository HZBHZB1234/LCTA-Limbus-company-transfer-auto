<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getApi } from '@/utils/api'
import { useModalStore } from '@/stores/modal'
import { listenEvent } from '@/utils/events'
import { useConfigStore } from '@/stores/config'

const modalStore = useModalStore()
const configStore = useConfigStore()

const packageDirectory = ref('')
const packages = ref<Array<{ name: string; path: string; size?: number }>>([])
const selectedPackage = ref<string | null>(null)
const loadError = ref(false)

// Font management state
const fonts = ref<Array<{ name: string; path: string }>>([])
const selectedFont = ref<string | null>(null)
const fontsLoadError = ref(false)
const fontFilter = ref('')

const filteredFonts = computed(() => {
  if (!fontFilter.value) return fonts.value
  const q = fontFilter.value.toLowerCase()
  return fonts.value.filter(f => f.name.toLowerCase().includes(q))
})

listenEvent('lcta:file-picked', (detail) => {
  if (detail.inputId === 'install-package-directory') packageDirectory.value = detail.path
  if (detail.inputId === 'install-font-path') {
    if (selectedPackage.value) {
      getApi().change_font_for_package(selectedPackage.value, detail.path)
    }
  }
  if (detail.inputId === 'install-font-export-dest') {
    if (selectedFont.value) {
      getApi().export_selected_font(selectedFont.value, detail.path)
    }
  }
})

onMounted(async () => {
  packageDirectory.value = configStore.get<string>('ui_default.install.package_directory') || ''
  await refreshList()
})

async function refreshList() {
  try {
    loadError.value = false
    const result = await getApi().get_translation_packages() as unknown as Record<string, unknown>
    if (result && result.success) {
      packages.value = (result.packages as Array<{ name: string; path: string; size?: number }>) || []
    } else {
      packages.value = []
    }
  } catch (e) {
    console.error('Install packages list load failed:', e)
    getApi().log(`[Install] 汉化包列表加载失败: ${e}`).catch(() => {})
    loadError.value = true
  }
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

// Font management methods
async function loadFonts() {
  try {
    fontsLoadError.value = false
    const result = await getApi().get_system_fonts_list()
    fonts.value = (result.fonts || []) as Array<{ name: string; path: string }>
  } catch (e) {
    console.error('Font list load failed:', e)
    getApi().log(`[Install] 系统字体列表加载失败: ${e}`).catch(() => {})
    fontsLoadError.value = true
  }
}

async function changeFontForPackage() {
  if (!selectedPackage.value) return
  await getApi().browse_file('install-font-path')
}

async function browseExportDest() {
  if (!selectedFont.value) return
  await getApi().browse_folder('install-font-export-dest')
}

function loadFontsIfNeeded() {
  if (fonts.value.length === 0 && !fontsLoadError.value) {
    loadFonts()
  }
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
            <div v-if="loadError" class="list-empty list-error">
              <i class="fas fa-exclamation-triangle"></i>
              <p>加载汉化包列表失败</p>
              <button class="action-btn" @click="refreshList"><i class="fas fa-redo"></i> 重试</button>
            </div>
            <div v-else-if="packages.length === 0" class="list-empty">
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

    <div class="settings-grid" style="margin-top: 16px;">
      <div class="setting-card">
        <h3 class="setting-title"><i class="fas fa-font"></i> 字体管理</h3>

        <div class="form-group">
          <label>更换汉化包字体:</label>
          <div class="button-group">
            <button class="action-btn" :disabled="!selectedPackage" @click="changeFontForPackage">
              <i class="fas fa-exchange-alt"></i> 为选中包更换字体
            </button>
          </div>
          <small v-if="!selectedPackage" class="form-hint">请先在汉化包列表中选择一个汉化包</small>
        </div>

        <div class="form-group" style="margin-top: 16px;">
          <label>系统字体列表:</label>
          <div v-if="fonts.length > 0" style="margin-bottom: 8px;">
            <input
              v-model="fontFilter"
              type="text"
              placeholder="搜索字体..."
              style="max-width: 300px; font-size: 13px;"
            />
          </div>
          <div v-if="fontsLoadError" class="list-empty list-error">
            <i class="fas fa-exclamation-triangle"></i>
            <p>加载字体列表失败</p>
            <button class="action-btn" @click="loadFonts"><i class="fas fa-redo"></i> 重试</button>
          </div>
          <div v-else-if="fonts.length === 0 && !fontsLoadError" class="list-empty">
            <i class="fas fa-font"></i>
            <p>点击下方按钮加载系统字体</p>
          </div>
          <div v-else class="list-container" style="max-height: 200px;">
            <div
              v-for="font in filteredFonts"
              :key="font.path"
              class="list-item"
              :class="{ selected: selectedFont === font.name }"
              @click="selectedFont = font.name"
            >
              <span>{{ font.name }}</span>
            </div>
          </div>
        </div>

        <div class="button-group">
          <button class="action-btn" @click="loadFontsIfNeeded">
            <i class="fas fa-sync-alt"></i> {{ fonts.length > 0 ? '刷新字体列表' : '加载字体列表' }}
          </button>
          <button class="action-btn success" :disabled="!selectedFont" @click="browseExportDest">
            <i class="fas fa-file-export"></i> 导出选中字体
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.list-item-size { font-size: 12px; opacity: 0.7; }
.list-error { color: var(--color-danger); }
.list-error .action-btn { margin-top: 8px; }
</style>
