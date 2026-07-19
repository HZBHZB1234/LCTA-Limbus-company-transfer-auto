<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getApi } from '@/utils/api'
import { useConfigStore } from '@/stores/config'
import { useModalStore } from '@/stores/modal'
import { listenEvent } from '@/utils/events'

const modalStore = useModalStore()
const configStore = useConfigStore()

const translator = ref('')
const enableProper = ref(false)
const autoFetchProper = ref(false)
const properPath = ref('')
const enableRole = ref(false)
const enableSkill = ref(false)
const enableDevSettings = ref(false)
const krPath = ref('')
const jpPath = ref('')
const enPath = ref('')
const llcPath = ref('')
const hasPrefix = ref(true)
const dumpTranslation = ref(false)
const fallback = ref(true)
const promptFormat = ref('xml_json')
const fromLang = ref('EN')
const maxWorkers = ref(4)
const enableConcurrent = ref(true)
const translationMode = ref('multi_stage')
const enableSelfCheck = ref(false)
const enableThinking = ref(false)
const disambiguationMode = ref('hybrid')
const minConfidence = ref('medium')

const showAutoProperPath = computed(() => autoFetchProper.value === false)

listenEvent('lcta:file-picked', (detail) => {
  if (detail.inputId === 'proper-path') properPath.value = detail.path
  if (detail.inputId === 'kr-path') krPath.value = detail.path
  if (detail.inputId === 'jp-path') jpPath.value = detail.path
  if (detail.inputId === 'en-path') enPath.value = detail.path
  if (detail.inputId === 'llc-path') llcPath.value = detail.path
})

onMounted(async () => {
  translator.value = (configStore.get('ui_default.translator.translator') as string) || ''
  enableProper.value = (configStore.get('ui_default.translator.enable_proper') as boolean) ?? false
  autoFetchProper.value = (configStore.get('ui_default.translator.auto_fetch_proper') as boolean) ?? false
  properPath.value = (configStore.get('ui_default.translator.proper_path') as string) || ''
  enableRole.value = (configStore.get('ui_default.translator.enable_role') as boolean) ?? false
  enableSkill.value = (configStore.get('ui_default.translator.enable_skill') as boolean) ?? false
  enableDevSettings.value = (configStore.get('ui_default.translator.enable_dev_settings') as boolean) ?? false
  krPath.value = (configStore.get('ui_default.translator.kr_path') as string) || ''
  jpPath.value = (configStore.get('ui_default.translator.jp_path') as string) || ''
  enPath.value = (configStore.get('ui_default.translator.en_path') as string) || ''
  llcPath.value = (configStore.get('ui_default.translator.llc_path') as string) || ''
  hasPrefix.value = (configStore.get('ui_default.translator.has_prefix') as boolean) ?? true
  dumpTranslation.value = (configStore.get('ui_default.translator.dump') as boolean) ?? false
  fallback.value = (configStore.get('ui_default.translator.fallback') as boolean) ?? true
  promptFormat.value = (configStore.get('ui_default.translator.prompt_format') as string) || 'xml_json'
  fromLang.value = (configStore.get('ui_default.translator.from_lang') as string) || 'EN'
  maxWorkers.value = (configStore.get('ui_default.translator.max_workers') as number) || 4
  enableConcurrent.value = (configStore.get('ui_default.translator.enable_concurrent') as boolean) ?? true
  translationMode.value = (configStore.get('ui_default.translator.translation_mode') as string) || 'multi_stage'
  enableSelfCheck.value = (configStore.get('ui_default.translator.enable_self_check') as boolean) ?? false
  enableThinking.value = (configStore.get('ui_default.translator.enable_thinking') as boolean) ?? false
  disambiguationMode.value = (configStore.get('ui_default.translator.disambiguation_mode') as string) || 'hybrid'
  minConfidence.value = (configStore.get('ui_default.translator.min_confidence') as string) || 'medium'
})

async function saveSettings() {
  configStore.set('ui_default.translator.translator', translator.value)
  configStore.set('ui_default.translator.enable_proper', enableProper.value)
  configStore.set('ui_default.translator.auto_fetch_proper', autoFetchProper.value)
  configStore.set('ui_default.translator.proper_path', properPath.value)
  configStore.set('ui_default.translator.enable_role', enableRole.value)
  configStore.set('ui_default.translator.enable_skill', enableSkill.value)
  configStore.set('ui_default.translator.enable_dev_settings', enableDevSettings.value)
  configStore.set('ui_default.translator.kr_path', krPath.value)
  configStore.set('ui_default.translator.jp_path', jpPath.value)
  configStore.set('ui_default.translator.en_path', enPath.value)
  configStore.set('ui_default.translator.llc_path', llcPath.value)
  configStore.set('ui_default.translator.has_prefix', hasPrefix.value)
  configStore.set('ui_default.translator.dump', dumpTranslation.value)
  configStore.set('ui_default.translator.fallback', fallback.value)
  configStore.set('ui_default.translator.prompt_format', promptFormat.value)
  configStore.set('ui_default.translator.from_lang', fromLang.value)
  configStore.set('ui_default.translator.max_workers', maxWorkers.value)
  configStore.set('ui_default.translator.enable_concurrent', enableConcurrent.value)
  configStore.set('ui_default.translator.translation_mode', translationMode.value)
  configStore.set('ui_default.translator.enable_self_check', enableSelfCheck.value)
  configStore.set('ui_default.translator.enable_thinking', enableThinking.value)
  configStore.set('ui_default.translator.disambiguation_mode', disambiguationMode.value)
  configStore.set('ui_default.translator.min_confidence', minConfidence.value)
  await configStore.save()
}

async function startTranslate() {
  await saveSettings()
  const mid = modalStore.create('progress', { title: '正在翻译...' })
  const settings: Record<string, unknown> = {}
  const apiCfg = configStore.get('api_config') as Record<string, Record<string, unknown>> | undefined
  if (apiCfg && translator.value && apiCfg[translator.value]) {
    Object.assign(settings, apiCfg[translator.value])
  }
  await getApi().start_translation({
    translator: translator.value,
    api_settings: settings,
  }, mid)
}

async function browseFolder(inputId: string) {
  await getApi().browse_folder(inputId)
}

async function browseFile(inputId: string) {
  await getApi().browse_file(inputId)
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-language"></i> 翻译工具</h2>
      <p class="section-subtitle">使用多种翻译服务自动翻译游戏文本</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card">
        <h3 class="setting-title">翻译选项</h3>

        <div class="form-group" v-tooltip="'enable-proper'">
          <label class="checkbox-label">
            <input id="enable-proper" v-model="enableProper" type="checkbox" />
            启用专有名词 (LLM翻译专用)
          </label>
        </div>

        <div v-if="enableProper" class="form-group" v-tooltip="'auto-fetch-proper'">
          <label class="checkbox-label">
            <input id="auto-fetch-proper" v-model="autoFetchProper" type="checkbox" />
            在进行翻译时自动抓取专有词汇 (无法使用自定义设置)
          </label>
        </div>

        <div v-if="enableProper && showAutoProperPath" class="form-group" v-tooltip="'proper-path'">
          <label for="proper-path">专有名词json路径</label>
          <div class="file-input-group">
            <input id="proper-path" v-model="properPath" type="text" placeholder="选择专有名词json文件" />
            <button class="action-btn secondary" @click="browseFile('proper-path')"><i class="fas fa-folder-open"></i> 浏览</button>
          </div>
        </div>

        <div class="form-group" v-tooltip="'enable-role'">
          <label class="checkbox-label">
            <input id="enable-role" v-model="enableRole" type="checkbox" />
            启用人物角色标识 (LLM翻译专用)
          </label>
        </div>

        <div class="form-group" v-tooltip="'enable-skill'">
          <label class="checkbox-label">
            <input id="enable-skill" v-model="enableSkill" type="checkbox" />
            启用状态效果标识 (LLM翻译专用)
          </label>
        </div>

        <div class="form-group" v-tooltip="'enable-dev-settings'">
          <label class="checkbox-label">
            <input id="enable-dev-settings" v-model="enableDevSettings" type="checkbox" />
            启用高级选项
          </label>
        </div>

        <div v-if="enableDevSettings">
          <div class="form-group" v-tooltip="'kr-path-text'">
            <label for="kr-path">韩文文本路径</label>
            <div class="file-input-group">
              <input id="kr-path" v-model="krPath" type="text" placeholder="选择韩文文本文件夹" />
              <button class="action-btn secondary" @click="browseFolder('kr-path')"><i class="fas fa-folder-open"></i> 浏览</button>
            </div>
          </div>
          <div class="form-group" v-tooltip="'jp-path-text'">
            <label for="jp-path">日文文本路径</label>
            <div class="file-input-group">
              <input id="jp-path" v-model="jpPath" type="text" placeholder="选择日文文本文件夹" />
              <button class="action-btn secondary" @click="browseFolder('jp-path')"><i class="fas fa-folder-open"></i> 浏览</button>
            </div>
          </div>
          <div class="form-group" v-tooltip="'en-path-text'">
            <label for="en-path">英文文本路径</label>
            <div class="file-input-group">
              <input id="en-path" v-model="enPath" type="text" placeholder="选择英文文本文件夹" />
              <button class="action-btn secondary" @click="browseFolder('en-path')"><i class="fas fa-folder-open"></i> 浏览</button>
            </div>
          </div>
          <div class="form-group" v-tooltip="'llc-path-text'">
            <label for="llc-path">中文文本路径</label>
            <div class="file-input-group">
              <input id="llc-path" v-model="llcPath" type="text" placeholder="选择中文文本文件夹" />
              <button class="action-btn secondary" @click="browseFolder('llc-path')"><i class="fas fa-folder-open"></i> 浏览</button>
            </div>
          </div>
          <div class="form-group" v-tooltip="'has-prefix'">
            <label class="checkbox-label">
              <input id="has-prefix" v-model="hasPrefix" type="checkbox" />
              文件名存在前缀
            </label>
          </div>
        </div>

        <div class="form-group" v-tooltip="'dump-translation'">
          <label class="checkbox-label">
            <input id="dump-translation" v-model="dumpTranslation" type="checkbox" />
            转储过程内容以供分析
          </label>
        </div>
      </div>

      <div class="setting-card">
        <h3 class="setting-title">翻译服务配置</h3>

        <div class="form-group">
          <label for="translator-select">翻译服务:</label>
          <input id="translator-select" v-model="translator" type="text" placeholder="请在「配置汉化API」页面选择和配置" style="color: var(--text-secondary); font-size: 13px;" readonly />
        </div>

        <div class="form-group" v-tooltip="'fallback'">
          <label class="checkbox-label">
            <input id="fallback" v-model="fallback" type="checkbox" />
            失败时进行相反重试 (LLM翻译专用)
          </label>
        </div>

        <div class="form-group" v-tooltip="'prompt-format'">
          <label for="prompt-format">请求 / 响应格式:</label>
          <select id="prompt-format" v-model="promptFormat">
            <option value="xml_json">XML 请求 → JSON 响应（推荐）</option>
            <option value="json_json">JSON 请求 → JSON 响应</option>
            <option value="xml_xml">XML 请求 → XML 响应</option>
          </select>
        </div>

        <div class="form-group" v-tooltip="'from-lang'">
          <label for="from-lang">使用源语言 (除LLM翻译外使用):</label>
          <select id="from-lang" v-model="fromLang">
            <option value="EN">英文</option>
            <option value="JP">日文</option>
            <option value="KR">韩文</option>
          </select>
        </div>
      </div>

      <div class="setting-card">
        <h3 class="setting-title">高级管线配置</h3>

        <div class="form-group" v-tooltip="'max-workers'">
          <label for="max-workers">并发线程数:</label>
          <input id="max-workers" v-model.number="maxWorkers" type="number" placeholder="4" min="1" max="16" />
        </div>

        <div class="form-group" v-tooltip="'enable-concurrent'">
          <label class="checkbox-label">
            <input id="enable-concurrent" v-model="enableConcurrent" type="checkbox" />
            启用并发处理
          </label>
        </div>

        <div class="form-group" v-tooltip="'translation-mode'">
          <label for="translation-mode">翻译模式:</label>
          <select id="translation-mode" v-model="translationMode">
            <option value="multi_stage">多阶段翻译</option>
            <option value="single_stage">单阶段翻译</option>
          </select>
        </div>

        <div class="form-group" v-tooltip="'enable-self-check'">
          <label class="checkbox-label">
            <input id="enable-self-check" v-model="enableSelfCheck" type="checkbox" />
            启用翻译自检
          </label>
        </div>

        <div class="form-group" v-tooltip="'enable-thinking'">
          <label class="checkbox-label">
            <input id="enable-thinking" v-model="enableThinking" type="checkbox" />
            启用LLM思考模式
          </label>
        </div>

        <div class="form-group" v-tooltip="'disambiguation-mode'">
          <label for="disambiguation-mode">消歧模式:</label>
          <select id="disambiguation-mode" v-model="disambiguationMode">
            <option value="hybrid">混合模式（推荐）</option>
            <option value="similarity">相似度匹配</option>
            <option value="llm">LLM消歧</option>
          </select>
        </div>

        <div class="form-group" v-tooltip="'min-confidence'">
          <label for="min-confidence">最低匹配置信度:</label>
          <select id="min-confidence" v-model="minConfidence">
            <option value="medium">中（推荐）</option>
            <option value="high">高</option>
            <option value="low">低</option>
          </select>
        </div>
      </div>
    </div>

    <div class="action-area">
      <button class="primary-btn" @click="startTranslate">
        <i class="fas fa-play"></i> 开始翻译
      </button>
    </div>
  </div>
</template>

<style scoped>
/* Translate view uses shared global classes from main.css */
</style>
