<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getApi } from '@/utils/api'
import { useConfigStore } from '@/stores/config'
import { useModalStore } from '@/stores/modal'

const modalStore = useModalStore()
const configStore = useConfigStore()

const outputFormat = ref('json')
const minCount = ref<number | null>(2)
const skipSpace = ref(true)
const maxCount = ref<number | null>(null)
const joinChar = ref(',')

onMounted(() => {
  outputFormat.value = (configStore.get('ui_default.proper.output_type') as string) || 'json'
  minCount.value = (configStore.get('ui_default.proper.min_length') as number) || 2
  skipSpace.value = (configStore.get('ui_default.proper.disable_space') as boolean) ?? true
  maxCount.value = (configStore.get('ui_default.proper.max_length') as number) || null
  joinChar.value = (configStore.get('ui_default.proper.join_char') as string) || ','
})

async function fetchNouns() {
  configStore.set('ui_default.proper.output_type', outputFormat.value)
  configStore.set('ui_default.proper.min_length', minCount.value)
  configStore.set('ui_default.proper.disable_space', skipSpace.value)
  configStore.set('ui_default.proper.max_length', maxCount.value)
  configStore.set('ui_default.proper.join_char', joinChar.value)
  await configStore.save()

  const mid = modalStore.create('progress', { title: '抓取专有词汇' })
  await getApi().fetch_proper_nouns(mid)
}
</script>

<template>
  <div>
    <div class="section-header">
      <h2 class="section-title"><i class="fas fa-book"></i> 抓取专有词汇</h2>
      <p class="section-subtitle">从文本中提取专有名词和术语</p>
    </div>

    <div class="settings-grid">
      <div class="setting-card">
        <h3 class="setting-title">抓取配置</h3>
        <div class="form-group" v-tooltip="'proper-output'">
          <label for="proper-output">输出格式:</label>
          <select id="proper-output" v-model="outputFormat">
            <option value="json">JSON格式</option>
            <option value="single">单文件格式</option>
            <option value="double">双文件格式</option>
          </select>
        </div>
        <div class="form-group" v-tooltip="'proper-skip-space'">
          <label class="checkbox-label">
            <input id="proper-skip-space" v-model="skipSpace" type="checkbox" />
            跳过含空格的词汇
          </label>
        </div>
        <div class="form-group" v-tooltip="'proper-max-count'">
          <label for="proper-max-count">最大专有名词数量:</label>
          <input id="proper-max-count" v-model.number="maxCount" type="number" placeholder="不限制" />
        </div>
        <div class="form-group" v-tooltip="'proper-min-count'">
          <label for="proper-min-count">最短专有名词长度:</label>
          <input id="proper-min-count" v-model.number="minCount" type="number" placeholder="例如：2" />
        </div>
        <div class="form-group" v-tooltip="'proper-join-char'">
          <label for="proper-join-char">词汇分隔符（单文件格式）:</label>
          <input id="proper-join-char" v-model="joinChar" type="text" placeholder="默认逗号" />
        </div>
        <div class="action-area">
          <button class="primary-btn" @click="fetchNouns">
            <i class="fas fa-download"></i> 开始抓取
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Proper view uses shared global classes from main.css */
</style>
