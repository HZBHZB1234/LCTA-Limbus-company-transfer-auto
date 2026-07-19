<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getApi } from '@/utils/api'
import { useModalStore } from '@/stores/modal'
import { useConfigStore } from '@/stores/config'

const modalStore = useModalStore()
const configStore = useConfigStore()

const ourplaySource = ref('pc')
const ourplayFontOption = ref('keep')
const ourplayCheckHash = ref(true)

const llcZipType = ref('zip')
const llcDownloadSource = ref('github')

onMounted(async () => {
  if (configStore.initialized) {
    ourplaySource.value = (configStore.get('ui_default.download.ourplay_source') as string) || 'pc'
    ourplayFontOption.value = (configStore.get('ui_default.download.ourplay_font') as string) || 'keep'
  }
})

async function downloadOurplay() {
  const mid = modalStore.create('progress', { title: '下载 OurPlay 汉化包' })
  getApi().download_ourplay_translation(mid)
}

async function downloadLLC() {
  const mid = modalStore.create('progress', { title: '下载零协会汉化包' })
  getApi().download_llc_translation(mid)
}

async function downloadMachine() {
  const mid = modalStore.create('progress', { title: '下载 LCTA 自动汉化' })
  getApi().download_LCTA_auto(mid)
}

async function downloadBubble() {
  const mid = modalStore.create('progress', { title: '下载 Bubble 语言包' })
  getApi().download_bubble(mid)
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fab fa-google-play"></i> 从各个平台下载汉化</h2>
      <p class="section-subtitle">下载各个来源的汉化包</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card">
        <h3 class="setting-title">OurPlay 下载配置</h3>
        <div class="form-group">
          <label>API源:</label>
          <select v-model="ourplaySource">
            <option value="pc">PC API</option>
            <option value="android">Android API</option>
          </select>
        </div>
        <div class="form-group">
          <label>字体处理选项:</label>
          <select v-model="ourplayFontOption">
            <option value="keep">保留原字体</option>
            <option value="simplify">精简字体</option>
            <option value="llc">使用本地字体缓存</option>
          </select>
        </div>
        <div class="form-group">
          <label class="checkbox-label"><input v-model="ourplayCheckHash" type="checkbox" /> 启用哈希校验</label>
        </div>
        <div class="action-area">
          <button class="primary-btn" @click="downloadOurplay"><i class="fas fa-download"></i> 下载 OurPlay 汉化包</button>
        </div>
      </div>

      <div class="setting-card">
        <h3 class="setting-title">零协会下载配置</h3>
        <div class="form-group">
          <label>压缩格式:</label>
          <select v-model="llcZipType">
            <option value="zip">ZIP格式</option>
            <option value="seven">7Z格式</option>
          </select>
        </div>
        <div class="form-group">
          <label>文本下载来源:</label>
          <select v-model="llcDownloadSource">
            <option value="github">从 github 下载</option>
            <option value="mirror">从公益镜像下载</option>
          </select>
        </div>
        <div class="action-area">
          <button class="primary-btn" @click="downloadLLC"><i class="fas fa-download"></i> 下载零协会汉化包</button>
        </div>
      </div>

      <div class="setting-card">
        <h3 class="setting-title">自动翻译补全</h3>
        <p style="color: var(--text-secondary); font-size: 14px; margin-bottom: 12px">从 LCTA 自动翻译仓库下载最新机器学习翻译包</p>
        <button class="primary-btn" @click="downloadMachine"><i class="fas fa-download"></i> 下载 LCTA 自动汉化</button>
      </div>

      <div class="setting-card">
        <h3 class="setting-title">Bubble 语言包</h3>
        <p style="color: var(--text-secondary); font-size: 14px; margin-bottom: 12px">一键下载游戏 Bubble 语言包</p>
        <button class="primary-btn" @click="downloadBubble"><i class="fas fa-download"></i> 下载 Bubble 语言包</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.section-header { margin-bottom: 24px; }
.section-title { font-size: 22px; font-weight: 600; display: flex; align-items: center; gap: 10px; }
.section-title i { color: var(--accent-color); }
.section-subtitle { color: var(--text-secondary); font-size: 14px; margin-top: 4px; }
.settings-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 20px; }
.setting-card { background: var(--bg-secondary); border-radius: 12px; padding: 20px; border: 1px solid var(--border-color); }
.setting-title { font-size: 16px; font-weight: 600; margin-bottom: 16px; }
.form-group { margin-bottom: 14px; }
.form-group label { display: block; font-size: 14px; color: var(--text-secondary); margin-bottom: 6px; }
.form-group select {
  width: 100%; padding: 8px 12px; border-radius: 8px; border: 1px solid var(--border-color);
  background: var(--bg-primary); color: var(--text-primary); font-size: 14px;
}
.action-area { margin-top: 16px; }
.primary-btn {
  padding: 10px 24px; border-radius: 8px; border: none;
  background: var(--accent-color); color: white; cursor: pointer; font-size: 14px;
}
.checkbox-label { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 14px; }
</style>
