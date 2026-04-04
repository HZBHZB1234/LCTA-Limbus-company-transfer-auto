import { defineStore } from 'pinia'
import { api } from '@/utils/api'
import { encryptText, decryptText } from '@/utils/crypto'

// 配置键映射（保持与原 ConfigManager 兼容）
const configKeyMap = {
  // 基本设置
  'game-path': 'game_path',
  'debug-mode': 'debug',
  'auto-check-update': 'auto_check_update',
  'delete-updating': 'delete_updating',
  'update-use-proxy': 'update_use_proxy',
  'github-max-workers': 'github_max_workers',
  'github-timeout': 'github_timeout',
  'update-only-stable': 'update_only_stable',
  'enable-cache': 'enable_cache',
  'cache-path': 'cache_path',
  'api-crypto': 'api_crypto',
  'enable-storage': 'enable_storage',
  'storage-path': 'storage_path',
  '--theme': 'theme',
  
  // 翻译设置
  'translator-service-select': 'ui_default.translator.translator',
  'fallback': 'ui_default.translator.fallback',
  'is-text': 'ui_default.translator.is_text',
  'from-lang': 'ui_default.translator.from_lang',
  'enable-proper': 'ui_default.translator.enable_proper',
  'auto-fetch-proper': 'ui_default.translator.auto_fetch_proper',
  'proper-path': 'ui_default.translator.proper_path',
  'enable-role': 'ui_default.translator.enable_role',
  'enable-skill': 'ui_default.translator.enable_skill',
  'enable-dev-settings': 'ui_default.translator.enable_dev_settings',
  'en-path': 'ui_default.translator.en_path',
  'kr-path': 'ui_default.translator.kr_path',
  'jp-path': 'ui_default.translator.jp_path',
  'llc-path': 'ui_default.translator.llc_path',
  'has-prefix': 'ui_default.translator.has_prefix',
  'dump-translation': 'ui_default.translator.dump',
  
  // 安装设置
  'install-package-directory': 'ui_default.install.package_directory',
  
  // OurPlay
  'ourplay-font-option': 'ui_default.ourplay.font_option',
  'ourplay-check-hash': 'ui_default.ourplay.check_hash',
  'ourplay-use-api': 'ui_default.ourplay.use_api',
  
  // 零协
  'llc-zip-type': 'ui_default.zero.zip_type',
  'llc-download-source': 'ui_default.zero.download_source',
  'llc-use-proxy': 'ui_default.zero.use_proxy',
  'llc-use-cache': 'ui_default.zero.use_cache',
  'llc-dump-default': 'ui_default.zero.dump_default',
  
  // LCTA-AU
  'machine-download-source': 'ui_default.machine.download_source',
  'machine-use-proxy': 'ui_default.machine.use_proxy',
  
  // 气泡文本
  'bubble-color': 'ui_default.bubble.color',
  'bubble-llc': 'ui_default.bubble.llc',
  'bubble-install': 'ui_default.bubble.install',
  
  // 管理
  'installed-mod-directory': 'ui_default.manage.mod_path',
  
  // 清理
  'clean-progress': 'ui_default.clean.clean_progress',
  'clean-notice': 'ui_default.clean.clean_notice',
  'clean-mods': 'ui_default.clean.clean_mods',
  
  // API
  'api-configs': 'api_config',
  'api-select': 'ui_default.api_config.key',
  
  // 美化
  'fancy-user': 'user_fancy',
  'fancy-allow': 'fancy_allow',
  
  // 抓取
  'proper-join-char': 'ui_default.proper.join_char',
  'proper-skip-space': 'ui_default.proper.disable_space',
  'proper-max-count': 'ui_default.proper.max_length',
  'proper-min-count': 'ui_default.proper.min_length',
  'proper-output': 'ui_default.proper.output_type',
  
  // Launcher
  'launcher-zero-zip-type': 'launcher.zero.zip_type',
  'launcher-zero-download-source': 'launcher.zero.download_source',
  'launcher-zero-use-proxy': 'launcher.zero.use_proxy',
  'launcher-zero-use-cache': 'launcher.zero.use_cache',
  'machine-zero-download-source': 'launcher.machine.download_source',
  'machine-zero-use-proxy': 'launcher.machine.use_proxy',
  'launcher-ourplay-font-option': 'launcher.ourplay.font_option',
  'launcher-ourplay-use-api': 'launcher.ourplay.use_api',
  'launcher-work-update': 'launcher.work.update',
  'launcher-work-mod': 'launcher.work.mod',
  'launcher-work-bubble': 'launcher.work.bubble',
  'launcher-work-fancy': 'launcher.work.fancy'
}

export const useConfigStore = defineStore('config', {
  state: () => ({
    configCache: {},      // 扁平化配置缓存 { keyPath: value }
    pendingUpdates: {},   // 待批量更新的配置
    updateTimer: null,
    debounceDelay: 500
  }),
  
  getters: {
    // 获取配置值（支持点号路径）
    get: (state) => (keyPath) => {
      const keys = keyPath.split('.')
      let value = state.configCache
      for (const key of keys) {
        if (value && typeof value === 'object' && key in value) {
          value = value[key]
        } else {
          return undefined
        }
      }
      return value
    },
    
    // 获取 UI 元素的配置（通过 id）
    getById: (state) => (id) => {
      const keyPath = configKeyMap[id]
      if (!keyPath) return undefined
      return state.get(keyPath)
    }
  },
  
  actions: {
    // 从后端加载完整配置
    async loadConfig() {
      try {
        const config = await api.call('get_attr', 'config')
        this.configCache = this._flattenConfig(config)
        // 同步到 UI（通过事件通知组件）
        this._emitConfigLoaded()
        return true
      } catch (error) {
        console.error('加载配置失败:', error)
        return false
      }
    },
    
    // 扁平化配置对象
    _flattenConfig(obj, prefix = '') {
      const result = {}
      for (const [key, value] of Object.entries(obj)) {
        const path = prefix ? `${prefix}.${key}` : key
        if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
          Object.assign(result, this._flattenConfig(value, path))
        } else {
          result[path] = value
        }
      }
      return result
    },
    
    // 触发配置加载完成事件（供组件监听）
    _emitConfigLoaded() {
      window.dispatchEvent(new CustomEvent('config-loaded', { detail: this.configCache }))
    },
    
    // 更新单个配置（自动批量）
    async updateConfig(id, value) {
      const keyPath = configKeyMap[id]
      if (!keyPath) {
        console.warn(`未找到配置项: ${id}`)
        return false
      }
      this.pendingUpdates[id] = value
      this._debounceUpdate()
      return true
    },
    
    // 批量更新
    async updateConfigs(updates) {
      const configUpdates = {}
      for (const [id, value] of Object.entries(updates)) {
        const keyPath = configKeyMap[id]
        if (keyPath) {
          configUpdates[keyPath] = value
          // 更新缓存
          this._setCacheValue(keyPath, value)
        }
      }
      if (Object.keys(configUpdates).length === 0) return
      
      try {
        const result = await api.call('update_config_batch', configUpdates)
        if (result.success) {
          // 清空待更新队列中已处理的项
          for (const id of Object.keys(updates)) {
            delete this.pendingUpdates[id]
          }
        }
        return result
      } catch (error) {
        console.error('批量更新配置失败:', error)
        return { success: false, message: error.message }
      }
    },
    
    _setCacheValue(keyPath, value) {
      const keys = keyPath.split('.')
      let obj = this.configCache
      for (let i = 0; i < keys.length - 1; i++) {
        const key = keys[i]
        if (!(key in obj) || typeof obj[key] !== 'object') {
          obj[key] = {}
        }
        obj = obj[key]
      }
      obj[keys[keys.length - 1]] = value
    },
    
    _debounceUpdate() {
      if (this.updateTimer) clearTimeout(this.updateTimer)
      this.updateTimer = setTimeout(() => {
        this.flushUpdates()
      }, this.debounceDelay)
    },
    
    async flushUpdates() {
      if (Object.keys(this.pendingUpdates).length === 0) return
      const updates = { ...this.pendingUpdates }
      await this.updateConfigs(updates)
    },
    
    // 保存 API 配置（加密处理）
    async saveApiConfig(serviceKey, settings) {
      let currentSettings = this.get('api_config') || {}
      currentSettings[serviceKey] = settings
      const useCrypto = this.get('api_crypto')
      let value
      if (useCrypto) {
        value = await encryptText('AutoTranslate', JSON.stringify(currentSettings))
      } else {
        value = JSON.stringify(currentSettings)
      }
      await this.updateConfig('api-configs', value)
      await this.flushUpdates()
    },
    
    // 获取 API 配置（解密）
    async getApiConfig() {
      const encrypted = this.get('api_config')
      if (!encrypted) return {}
      const useCrypto = this.get('api_crypto')
      if (useCrypto) {
        try {
          const decrypted = await decryptText('AutoTranslate', encrypted)
          return JSON.parse(decrypted)
        } catch (e) {
          console.error('解密 API 配置失败', e)
          return {}
        }
      }
      return JSON.parse(encrypted)
    },
    
    // 检查游戏路径
    async checkGamePath() {
      const gamePath = this.get('game_path')
      if (!gamePath) {
        const foundPath = await api.call('run_func', 'find_lcb')
        if (foundPath) {
          this.confirmGamePath(foundPath)
        } else {
          this.requestGamePath()
        }
      }
    },
    
    async confirmGamePath(path) {
      // 使用模态窗确认
      window.dispatchEvent(new CustomEvent('request-confirm', {
        detail: {
          title: '确认游戏路径',
          message: `这是否是你的游戏路径：\n${path}\n是否使用此路径？`,
          onConfirm: async () => {
            await this.updateConfig('game-path', path)
            await this.flushUpdates()
            await api.call('init_cache')
          }
        }
      }))
    },
    
    requestGamePath() {
      window.dispatchEvent(new CustomEvent('request-message', {
        detail: {
          title: '选择游戏路径',
          message: '请手动选择游戏的安装目录（包含LimbusCompany.exe的文件夹）',
          onClose: () => {
            api.call('browse_folder', 'game-path').then(path => {
              if (path) this.updateConfig('game-path', path)
            })
          }
        }
      }))
    },
    
    async checkUpdate() {
      const result = await api.call('manual_check_update')
      if (result.has_update) {
        window.dispatchEvent(new CustomEvent('show-update', { detail: result }))
      }
    }
  }
})