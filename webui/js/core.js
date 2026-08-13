// ============================
// 核心模块：基础类与全局变量
// ============================

// === 全局变量声明 ===
let configManager;
let modalWindows = [];
let apiConfigManager;
let fancyManager;
let themeManager;
let quickStartManager;
let dragDropManager;
let first_use;

// === 主题管理器 ===
class ThemeManager {
    constructor() {
        this.currentTheme = 'light';
        this.isTransitioning = false;
        this.pendingTheme = null;
        this.debounceTimer = null;
        this.debounceDelay = 300;
        this.init();
    }
    
    init() {
        this.setTheme(this.currentTheme, true);
        
        document.querySelectorAll('.theme-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const theme = e.target.dataset.theme || e.target.closest('.theme-btn').dataset.theme;
                this.setThemeWithDebounce(theme);
            });
        });
    }
    
    setThemeWithDebounce(theme) {
        const clickedBtn = [...document.querySelectorAll('.theme-btn')].find(btn => btn.dataset.theme === theme);
        if (clickedBtn) {
            clickedBtn.classList.add('changing');
            setTimeout(() => {
                clickedBtn.classList.remove('changing');
            }, 300);
        }
        
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
        
        this.debounceTimer = setTimeout(() => {
            this.setTheme(theme);
        }, this.debounceDelay);
    }
    
    setTheme(theme, skipDebounce = false) {
        if (this.isTransitioning) {
            this.pendingTheme = theme;
            return;
        }
        
        if (this.currentTheme === theme) {
            return;
        }
        
        this.isTransitioning = true;
        document.body.classList.add('theme-transition');
        
        document.body.classList.remove('theme-light', 'theme-dark', 'theme-purple');
        document.body.classList.add(`theme-${theme}`);
        
        this.currentTheme = theme;
        configManager.updateConfigValue('--theme', theme);
        configManager.flushPendingUpdates();  // 立即持久化，供规则编辑器窗口读取

        this.updateThemeButtons(theme);

        // 推送主题变更到规则编辑器窗口（如果已打开）
        if (typeof window !== 'undefined' && window.pywebview && window.pywebview.api) {
            try {
                window.pywebview.api.sync_theme_to_rule_editor(theme);
            } catch (e) { /* 规则编辑器可能未打开 */ }
        }
        this.addThemeTransition();
    }
    
    updateThemeButtons(theme) {
        document.querySelectorAll('.theme-btn').forEach(btn => {
            if (btn.dataset.theme === theme) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });
    }
    
    addThemeTransition() {
        setTimeout(() => {
            document.body.classList.remove('theme-transition');
            this.isTransitioning = false;
            
            if (this.pendingTheme && this.pendingTheme !== this.currentTheme) {
                const pendingTheme = this.pendingTheme;
                this.pendingTheme = null;
                this.setTheme(pendingTheme);
            }
        }, 300);
    }
}

// === 动画管理器 ===
class AnimationManager {
    static fadeIn(element, duration = 150) {
        element.style.opacity = 0;
        element.style.display = 'block';
        
        let start = null;
        const animate = (timestamp) => {
            if (!start) start = timestamp;
            const progress = timestamp - start;
            const opacity = Math.min(progress / duration, 1);
            
            element.style.opacity = opacity;
            
            if (progress < duration) {
                requestAnimationFrame(animate);
            }
        };
        
        requestAnimationFrame(animate);
    }
    
    static fadeOut(element, duration = 150) {
        let start = null;
        const animate = (timestamp) => {
            if (!start) start = timestamp;
            const progress = timestamp - start;
            const opacity = 1 - Math.min(progress / duration, 1);
            
            element.style.opacity = opacity;
            
            if (progress < duration) {
                requestAnimationFrame(animate);
            } else {
                element.style.display = 'none';
                element.style.opacity = 1;
            }
        };
        
        requestAnimationFrame(animate);
    }
    
    static slideIn(element, from = 'left', duration = 150) {
        const direction = from === 'left' ? '-100%' : '100%';
        element.style.transform = `translateX(${direction})`;
        element.style.display = 'block';
        
        let start = null;
        const animate = (timestamp) => {
            if (!start) start = timestamp;
            const progress = timestamp - start;
            const percentage = Math.min(progress / duration, 1);
            
            element.style.transform = `translateX(${parseInt(direction) * (1 - percentage)}%)`;
            
            if (progress < duration) {
                requestAnimationFrame(animate);
            }
        };
        
        requestAnimationFrame(animate);
    }
}


// === 配置缓存辅助函数 ===

function setConfigToCache(obj, prefix = '') {
    for (const [key, value] of Object.entries(obj)) {
        const path = prefix ? `${prefix}.${key}` : key;
        
        if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
            setConfigToCache(value, path);
        } else {
            configManager.setCachedValue(path, value);
        }
    }
}

// === 配置管理器 ===
class ConfigManager {
    constructor() {
        // 配置键名对照表：id -> 配置键路径
        this.configKeyMap = {
            // 基本设置
            'game-path': 'game_path',
            'debug-mode': 'debug',
            'auto-check-update': 'auto_check_update',
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
            "translator-service-select": "ui_default.translator.translator",
            "fallback": 'ui_default.translator.fallback',
            "prompt-format": 'ui_default.translator.prompt_format',
            'from-lang': 'ui_default.translator.from_lang',
            'enable-proper': 'ui_default.translator.enable_proper',
            'auto-fetch-proper': 'ui_default.translator.auto_fetch_proper',
            'proper-path': 'ui_default.translator.proper_path',
            'enable-role': 'ui_default.translator.enable_role',
            'enable-skill': 'ui_default.translator.enable_skill',
            'enable-dev-settings': 'ui_default.translator.enable_dev_settings',
            "en-path": "ui_default.translator.en_path",
            "kr-path": "ui_default.translator.kr_path",
            "jp-path": "ui_default.translator.jp_path",
            "llc-path": "ui_default.translator.llc_path",
            "has-prefix": "ui_default.translator.has_prefix",
            "dump-translation": "ui_default.translator.dump",
            "max-workers": "ui_default.translator.max_workers",
            "enable-concurrent": "ui_default.translator.enable_concurrent",
            "translation-mode": "ui_default.translator.translation_mode",
            "enable-self-check": "ui_default.translator.enable_self_check",
            "enable-thinking": "ui_default.translator.enable_thinking",
            "enable-rule-validation": "ui_default.translator.enable_rule_validation",
            "disambiguation-mode": "ui_default.translator.disambiguation_mode",
            "min-confidence": "ui_default.translator.min_confidence",
            
            // 安装设置
            'install-package-directory': 'ui_default.install.package_directory',
            'package-directory': 'ui_default.install.package_directory',
            
            // OurPlay设置
            'ourplay-font-option': 'ui_default.ourplay.font_option',
            'ourplay-check-hash': 'ui_default.ourplay.check_hash',
            'ourplay-use-api': 'ui_default.ourplay.use_api',
            'ourplay-source': 'ui_default.ourplay.source',
            'ourplay-official': 'ui_default.ourplay.official',
            'ourplay-refer-package': 'ui_default.ourplay.refer_package',
            
            // 零协设置
            'llc-zip-type': 'ui_default.zero.zip_type',
            'llc-download-source': 'ui_default.zero.download_source',
            'llc-use-proxy': 'ui_default.zero.use_proxy',
            'llc-use-cache': 'ui_default.zero.use_cache',
            'llc-dump-default': 'ui_default.zero.dump_default',

            // LCTA-auto-update配置
            'machine-download-source': 'ui_default.machine.download_source',
            'machine-use-proxy': 'ui_default.machine.use_proxy',

            // 调爪文本修改包配置
            'tiaozhua-install': 'ui_default.tiaozhua.install',
            // 调爪「替换」文本包：下载页 dl-* 与 Launcher 页 lc-* 共享同一配置键
            'dl-tiaozhua-replace-3': 'ui_default.tiaozhua.replace_3',
            'dl-tiaozhua-replace-4': 'ui_default.tiaozhua.replace_4',
            'dl-tiaozhua-replace-5': 'ui_default.tiaozhua.replace_5',
            'dl-tiaozhua-replace-7': 'ui_default.tiaozhua.replace_7',
            'dl-tiaozhua-replace-8': 'ui_default.tiaozhua.replace_8',
            'lc-tiaozhua-replace-3': 'ui_default.tiaozhua.replace_3',
            'lc-tiaozhua-replace-4': 'ui_default.tiaozhua.replace_4',
            'lc-tiaozhua-replace-5': 'ui_default.tiaozhua.replace_5',
            'lc-tiaozhua-replace-7': 'ui_default.tiaozhua.replace_7',
            'lc-tiaozhua-replace-8': 'ui_default.tiaozhua.replace_8',

            // 安装数据管理设置
            'installed-mod-directory': 'ui_default.manage.mod_path',
            
            // 清理设置
            'clean-progress': 'ui_default.clean.clean_progress',
            'clean-notice': 'ui_default.clean.clean_notice',
            'clean-mods': 'ui_default.clean.clean_mods',
            'custom-files': 'ui_default.clean.custom_files',

            // api配置设置
            'api-configs': 'api_config',
            'api-select': 'ui_default.api_config.key',

            'fancy-user': 'user_fancy',
            'fancy-allow': 'fancy_allow',

            // 抓取设置
            'proper-join-char': 'ui_default.proper.join_char',
            'proper-skip-space': 'ui_default.proper.disable_space',
            'proper-max-count': 'ui_default.proper.max_length',
            'proper-min-count': 'ui_default.proper.min_length',
            'proper-output': 'ui_default.proper.output_type',
            
            // Launcher设置
            'launcher-work-update': 'launcher.work.update',
            'launcher-work-mod': 'launcher.work.mod',
            'launcher-work-tiaozhua': 'launcher.work.tiaozhua',
            'launcher-work-fancy': 'launcher.work.fancy',
            'launcher-work-cdn-optimize': 'launcher.work.cdn_optimize',
            'launcher-work-cdn-auto-apply': 'launcher.work.cdn_auto_apply',
            'launcher-work-cdn-cache-ttl': 'launcher.work.cdn_cache_ttl',

            // 游戏加速
            'launcher-work-speed': 'launcher.work.speed',
            'launcher-speed-factor': 'launcher.work.speed_factor',

            // 输入反检测
            'launcher-work-input-bypass': 'launcher.work.input_bypass',
            'input-bypass-mode': 'launcher.work.input_bypass_mode',
            'input-bypass-mouse-real': 'launcher.work.input_bypass_mouse_real',
            'input-bypass-key-real': 'launcher.work.input_bypass_key_real',
            'input-bypass-mouse-synth': 'launcher.work.input_bypass_mouse_synth',
            'input-bypass-key-synth': 'launcher.work.input_bypass_key_synth',
            'input-bypass-volatility': 'launcher.work.input_bypass_volatility',

            // GUI进度窗口
            'launcher-work-gui-mode': 'launcher.work.gui_mode',
            'launcher-work-crash-popup': 'launcher.work.crash_popup',
            // 游戏官方资源预下载（仅开关，详细配置在游戏资源更新页面）
            'launcher-resource-update-enabled': 'launcher.resource_update.enabled',

            // 音频工具
            'bank-dll-dir': 'ui_default.bank.dll_dir',
            'bank-dll-url': 'ui_default.bank.dll_url',
            'bank-extract-dir': 'ui_default.bank.extract_dir'
        };
        
        this.configCache = {}; // 配置缓存
        this.pendingUpdates = {}; // 待更新的配置
        this.debounceTimer = null;
        this.debounceDelay = 500; // 防抖延迟
    }

    async reloadConfig() {
        obj = await pywebview.api.get_attr('config');
        window.config = obj;
        setConfigToCache(obj);
    }
    
    // 动态登记配置键：id -> 配置键路径（如作弊工具箱插件按注册表登记的 Launcher 集成开关）。
    // 登记后该控件即纳入 applyConfigToUI/applyConfigToSection 回填、bindConfigAutoSave
    // 自动保存与 configCache 缓存管理，无需改动静态 configKeyMap。
    registerConfigKey(id, keyPath) {
        if (!id || !keyPath) return;
        this.configKeyMap[id] = keyPath;
    }

    // 批量获取配置值
    async getConfigValues(ids) {
        const keyPaths = ids.map(id => this.configKeyMap[id]).filter(path => path);
        
        if (keyPaths.length === 0) {
            return {};
        }
        
        try {
            const result = await pywebview.api.get_config_batch(keyPaths);
            if (result.success) {
                // 更新缓存
                Object.assign(this.configCache, result.config_values);
                return result.config_values;
            }
            return {};
        } catch (error) {
            console.error('批量获取配置失败:', error);
            return {};
        }
    }
    
    // 单次配置更新（自动批量化处理）
    async updateConfigValue(id, value) {
        const keyPath = this.configKeyMap[id];
        if (!keyPath) {
            console.warn(`未找到id对应的配置键: ${id}`);
            return false;
        }
        
        // 添加到待更新队列
        this.pendingUpdates[id] = value;
        
        // 防抖处理，避免频繁调用
        this.debounceUpdate();
        
        return true;
    }
    
    // 防抖更新
    debounceUpdate() {
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
        
        this.debounceTimer = setTimeout(() => {
            this.flushPendingUpdates();
        }, this.debounceDelay);
    }
    
    // 立即执行待更新
    async flushPendingUpdates() {
        if (Object.keys(this.pendingUpdates).length === 0) {
            return;
        }
        
        const updates = { ...this.pendingUpdates };
        this.pendingUpdates = {};
        
        await this.updateConfigValues(updates);
    }
    
    // 批量更新配置值
    async updateConfigValues(updates) {
        const configUpdates = {};
        
        // 转换id到配置键路径
        for (const [id, value] of Object.entries(updates)) {
            const keyPath = this.configKeyMap[id];
            if (keyPath) {
                configUpdates[keyPath] = value;
                // 更新缓存
                this.setCachedValue(keyPath, value);
            }
        }
        
        if (Object.keys(configUpdates).length === 0) {
            return { success: false, message: '没有有效的配置项' };
        }
        
        try {
            const result = await pywebview.api.update_config_batch(configUpdates);
            if (result.success) {
                console.log(`批量更新配置成功: ${result.updated}/${result.total} 项`);
            }
            return result;
        } catch (error) {
            console.error('批量更新配置失败:', error);
            return { success: false, message: error.toString() };
        }
    }
    
    // 获取缓存值
    getCachedValue(keyPath) {
        const keys = keyPath.split('.');
        let value = this.configCache;
        
        for (const key of keys) {
            if (value && typeof value === 'object' && key in value) {
                value = value[key];
            } else {
                return undefined;
            }
        }
        
        return value;
    }
    
    // 设置缓存值
    setCachedValue(keyPath, value) {
        const keys = keyPath.split('.');
        let obj = this.configCache;
        
        for (let i = 0; i < keys.length - 1; i++) {
            const key = keys[i];
            if (!(key in obj) || typeof obj[key] !== 'object') {
                obj[key] = {};
            }
            obj = obj[key];
        }
        
        obj[keys[keys.length - 1]] = value;
    }
    
    // 应用配置到UI（批量）
    async applyConfigToUI() {
        // 过滤掉 id 以 "--" 开头的配置项
        const allIds = Object.keys(this.configKeyMap).filter(id => !id.startsWith('--'));
        const configValues = await this.getConfigValues(allIds);
        
        // 遍历所有配置项，更新UI
        for (const [id, keyPath] of Object.entries(this.configKeyMap)) {
            if (id.startsWith('--')) continue; // 跳过以 "--" 开头的 id，不应用到 UI
            if (keyPath in configValues) {
                this.applyValueToUI(id, configValues[keyPath]);
            }
        }
    }
    
    // 应用配置到UI（限定容器：仅回填容器内已渲染的表单，
    // 跳过待保存的键，避免覆盖其他 section 未保存的编辑）
    async applyConfigToSection(sectionEl) {
        if (!sectionEl) return;
        const allIds = Object.keys(this.configKeyMap).filter(id => !id.startsWith('--'));
        const scopedIds = allIds.filter(id => {
            if (id in this.pendingUpdates) return false;
            const element = document.getElementById(id);
            return element && sectionEl.contains(element);
        });
        const configValues = await this.getConfigValues(scopedIds);
        
        for (const [id, keyPath] of Object.entries(this.configKeyMap)) {
            if (id.startsWith('--')) continue;
            if (id in this.pendingUpdates) continue;
            if (scopedIds.indexOf(id) >= 0 && keyPath in configValues) {
                this.applyValueToUI(id, configValues[keyPath]);
            }
        }
    }
    
    // 将值应用到UI元素
    applyValueToUI(id, value) {
        const element = document.getElementById(id);
        if (!element) return;
        
        if (element.type === 'checkbox') {
            element.checked = Boolean(value);
        } else if (element.tagName === 'SELECT') {
            element.value = value || '';
        } else {
            element.value = value || '';
        }
    }
    
    // 从UI收集配置值（批量）
    collectConfigFromUI() {
        const updates = {};
        
        for (const [id, keyPath] of Object.entries(this.configKeyMap)) {
            // 跳过以 "--" 开头的 id，这些没有对应的 UI 元素
            if (id.startsWith('--')) continue;
            
            const element = document.getElementById(id);
            if (element) {
                let value;
                
                if (element.type === 'checkbox') {
                    value = element.checked;
                } else if (element.tagName === 'SELECT' || element.tagName === 'INPUT') {
                    value = element.value;
                }
                
                // 如果值与缓存不同，则添加到更新
                const cachedValue = this.getCachedValue(keyPath);
                if (JSON.stringify(value) !== JSON.stringify(cachedValue)) {
                    updates[id] = value;
                }
            }
        }
        
        return updates;
    }
}

// 配置懒同步：任意配置表单控件 change 时，经 ConfigManager 防抖队列
// （debounceDelay=500ms）批量推送到后端并落盘，无需手动保存。
// 仅处理 configKeyMap 中登记且存在 DOM id 的控件；专属流程控件
// （--theme / api-* / fancy-allow / custom-files / class 式下拉等）
// 无匹配 id，天然跳过，不会与其专属保存逻辑冲突。
function bindConfigAutoSave() {
    document.addEventListener('change', function (e) {
        if (!configManager) return;
        const target = e.target;
        if (!target || !target.id) return;
        if (target.id.startsWith('--')) return;
        if (target.tagName !== 'INPUT' && target.tagName !== 'SELECT' && target.tagName !== 'TEXTAREA') return;
        if (!(target.id in configManager.configKeyMap)) return;

        let value;
        if (target.type === 'checkbox') {
            value = target.checked;
        } else if (target.type === 'radio') {
            if (!target.checked) return;
            value = target.value;
        } else {
            value = target.value;
        }
        configManager.updateConfigValue(target.id, value);
    });
}

// 调爪「替换」文本包跨页同步 + 互斥：
// 下载页（dl-*）与 Launcher 页（lc-*）各有一份复选框，映射到同一配置键。
// 任一页勾选时：1) 同步另一页对应复选框的视觉状态；2) 三种气泡
// （彩色 3 / 无色 4 / 旧翻译版 8）互斥，勾选其一自动取消其余两个并保存。
// 程序赋值不触发 change，不会造成事件循环。
function bindTiaozhuaReplaceSync() {
    const bubbleKeys = {
        'ui_default.tiaozhua.replace_3': true,
        'ui_default.tiaozhua.replace_4': true,
        'ui_default.tiaozhua.replace_8': true,
    };
    document.addEventListener('change', function (e) {
        if (!configManager) return;
        const target = e.target;
        if (!target || !target.id || target.type !== 'checkbox') return;
        const keyPath = configManager.configKeyMap[target.id];
        if (!keyPath || keyPath.indexOf('ui_default.tiaozhua.replace_') !== 0) return;

        // 1. 同步所有映射到同一配置键的复选框（两页）
        Object.keys(configManager.configKeyMap).forEach(function (id) {
            if (configManager.configKeyMap[id] === keyPath) {
                const el = document.getElementById(id);
                if (el && el.type === 'checkbox' && el.checked !== target.checked) {
                    el.checked = target.checked;
                }
            }
        });

        // 2. 气泡互斥：勾选某气泡时取消其余两个气泡（两页所有对应复选框）
        if (target.checked && bubbleKeys[keyPath]) {
            Object.keys(bubbleKeys).forEach(function (kp) {
                if (kp === keyPath) return;
                Object.keys(configManager.configKeyMap).forEach(function (id) {
                    if (configManager.configKeyMap[id] !== kp) return;
                    const el = document.getElementById(id);
                    if (el && el.checked) {
                        el.checked = false;
                        configManager.updateConfigValue(id, false);
                    }
                });
            });
        }
    });
}

// 按当前配置刷新调爪「替换」文本包复选框（两页），用于进入页面时兜底同步，
// 防止跨会话/外部修改后任一侧状态滞后。
async function syncTiaozhuaReplaceFromConfig() {
    if (!configManager) return;
    const suffixes = ['3', '4', '5', '7', '8'];
    const ids = [];
    suffixes.forEach(function (n) {
        ids.push('dl-tiaozhua-replace-' + n, 'lc-tiaozhua-replace-' + n);
    });
    const values = await configManager.getConfigValues(ids);
    if (!values) return;
    Object.keys(values).forEach(function (keyPath) {
        Object.keys(configManager.configKeyMap).forEach(function (id) {
            if (configManager.configKeyMap[id] === keyPath) {
                const el = document.getElementById(id);
                if (el && el.type === 'checkbox' && el.checked !== Boolean(values[keyPath])) {
                    el.checked = Boolean(values[keyPath]);
                }
            }
        });
    });
}

