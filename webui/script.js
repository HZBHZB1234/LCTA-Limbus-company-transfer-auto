// 主题管理
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
        
        this.updateThemeButtons(theme);
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

// 动画管理器
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

// 配置管理器
class ConfigManager {
    constructor() {
        // 配置键名对照表：id -> 配置键路径
        this.configKeyMap = {
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
            "translator-service-select": "ui_default.translator.translator",
            "fallback": 'ui_default.translator.fallback',
            "is-text": 'ui_default.translator.is_text',
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
            
            // 安装设置
            'install-package-directory': 'ui_default.install.package_directory',
            'package-directory': 'ui_default.install.package_directory',
            
            // OurPlay设置
            'ourplay-font-option': 'ui_default.ourplay.font_option',
            'ourplay-check-hash': 'ui_default.ourplay.check_hash',
            'ourplay-use-api': 'ui_default.ourplay.use_api',
            
            // 零协设置
            'llc-zip-type': 'ui_default.zero.zip_type',
            'llc-download-source': 'ui_default.zero.download_source',
            'llc-use-proxy': 'ui_default.zero.use_proxy',
            'llc-use-cache': 'ui_default.zero.use_cache',
            'llc-dump-default': 'ui_default.zero.dump_default',

            // LCTA-auto-update配置
            'machine-download-source': 'ui_default.machine.download_source',
            'machine-use-proxy': 'ui_default.machine.use_proxy',

            // 气泡文本mod配置
            'bubble-color': 'ui_default.bubble.color',
            'bubble-enable-screen': 'ui_default.bubble.enable_screen',
            'bubble-screen': 'ui_default.bubble.screen',
            'bubble-install': 'ui_default.bubble.install',
            
            // 清理设置
            'clean-progress': 'ui_default.clean.clean_progress',
            'clean-notice': 'ui_default.clean.clean_notice',
            'clean-mods': 'ui_default.clean.clean_mods',

            // api配置设置
            'api-configs': 'api_config',
            'api-select': 'ui_default.api_config.key',

            // 抓取设置
            'proper-join-char': 'ui_default.proper.join_char',
            'proper-skip-space': 'ui_default.proper.disable_space',
            'proper-max-count': 'ui_default.proper.max_length',
            'proper-min-count': 'ui_default.proper.min_length',
            'proper-output': 'ui_default.proper.output_type',
            
            // Launcher设置
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
            'launcher-work-bubble': 'launcher.bubble'
        };
        
        this.configCache = {}; // 配置缓存
        this.pendingUpdates = {}; // 待更新的配置
        this.debounceTimer = null;
        this.debounceDelay = 500; // 防抖延迟
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
        const allIds = Object.keys(this.configKeyMap);
        const configValues = await this.getConfigValues(allIds);
        
        // 遍历所有配置项，更新UI
        for (const [id, keyPath] of Object.entries(this.configKeyMap)) {
            if (keyPath in configValues) {
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

// 初始化全局配置管理器
let configManager;

// 存储所有模态窗口的数组
let modalWindows = [];

// 确保modal-container存在
function ensureModalContainer() {
    let container = document.getElementById('modal-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'modal-container';
        document.body.appendChild(container);
    }
    return container;
}

// 确保最小化窗口容器存在
function ensureMinimizedContainer() {
    let container = document.getElementById('minimized-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'minimized-container';
        container.style.position = 'fixed';
        container.style.top = '80px';
        container.style.right = '20px';
        container.style.bottom = '20px';
        container.style.width = '300px';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.alignItems = 'flex-end';
        container.style.gap = '10px';
        container.style.zIndex = '999';
        container.style.maxHeight = 'calc(100vh - 100px)';
        container.style.overflowY = 'auto';
        container.style.overflowX = 'hidden';
        container.style.padding = '5px';
        document.body.appendChild(container);
    }
    return container;
}

// 切换侧边栏按钮激活状态
function initNavigation() {
    document.querySelectorAll('.nav-btn').forEach(button => {
        button.addEventListener('click', () => {
            if (button.classList.contains('active')) {
                return;
            }
            
            document.querySelectorAll('.nav-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            document.querySelectorAll('.nav-indicator').forEach(indicator => {
                indicator.remove();
            });
            
            button.classList.add('active');
            
            const indicator = document.createElement('div');
            indicator.className = 'nav-indicator';
            button.appendChild(indicator);
            
            document.querySelectorAll('.content-section').forEach(section => {
                if (section.classList.contains('active')) {
                    AnimationManager.fadeOut(section, 150);
                    setTimeout(() => {
                        section.classList.remove('active');
                    }, 150);
                }
            });
            
            const sectionId = button.id.replace('-btn', '-section');
            const section = document.getElementById(sectionId);
            if (section) {
                setTimeout(() => {
                    section.classList.add('active');
                    AnimationManager.fadeIn(section, 150);
                    
                    if (sectionId === 'log-section') {
                        scrollLogToBottom();
                    }
                    
                    if (sectionId === 'install-section') {
                        refreshInstallPackageList();
                    }

                    if (sectionId === 'manage-section') {
                        refreshInstalledPackageList();
                        refreshInstalledModList();
                    }

                    if (sectionId !== 'test-section') {
                        goTestSection(false);
                    }
                }, 150);
            }
        });
    });
}

// 滚动日志到底部
function scrollLogToBottom() {
    const logDisplay = document.getElementById('log-display');
    if (logDisplay) {
        setTimeout(() => {
            logDisplay.scrollTop = logDisplay.scrollHeight;
        }, 100);
    }
}

// 密码显示/隐藏切换
function initPasswordToggles() {
    document.querySelectorAll('.toggle-password').forEach(button => {
        button.addEventListener('click', function() {
            const input = this.parentElement.querySelector('input');
            const icon = this.querySelector('i');
            
            if (input.type === 'password') {
                input.type = 'text';
                icon.classList.remove('fa-eye');
                icon.classList.add('fa-eye-slash');
            } else {
                input.type = 'password';
                icon.classList.remove('fa-eye-slash');
                icon.classList.add('fa-eye');
            }
        });
    });
}
/**
 * 使用密码加密文本
 * @param {string} password - 密码字符串
 * @param {string} plaintext - 要加密的文本
 * @returns {Promise<string>} Base64编码的加密结果（包含IV和加密数据）
 */
async function encryptText(password, plaintext) {
    try {
        // 1. 准备密钥材料
        const encoder = new TextEncoder();
        const passwordBuffer = encoder.encode(password);
        
        // 2. 创建密钥
        const keyMaterial = await crypto.subtle.importKey(
            'raw',
            passwordBuffer,
            { name: 'PBKDF2' },
            false,
            ['deriveKey']
        );
        
        // 3. 派生加密密钥
        const salt = crypto.getRandomValues(new Uint8Array(16));
        const iv = crypto.getRandomValues(new Uint8Array(12)); // GCM推荐12字节IV
        
        const key = await crypto.subtle.deriveKey(
            {
                name: 'PBKDF2',
                salt: salt,
                iterations: 100000,
                hash: 'SHA-256'
            },
            keyMaterial,
            { name: 'AES-GCM', length: 256 },
            false,
            ['encrypt']
        );
        
        // 4. 加密数据
        const plaintextBuffer = encoder.encode(plaintext);
        const encryptedBuffer = await crypto.subtle.encrypt(
            {
                name: 'AES-GCM',
                iv: iv
            },
            key,
            plaintextBuffer
        );
        
        // 5. 组合结果：salt + iv + 加密数据
        const combinedBuffer = new Uint8Array(
            salt.length + iv.length + encryptedBuffer.byteLength
        );
        combinedBuffer.set(salt, 0);
        combinedBuffer.set(iv, salt.length);
        combinedBuffer.set(new Uint8Array(encryptedBuffer), salt.length + iv.length);
        
        // 6. 转换为Base64字符串
        return btoa(String.fromCharCode(...combinedBuffer));
        
    } catch (error) {
        console.error('加密失败:', error);
        throw new Error('加密失败: ' + error.message);
    }
}

/**
 * 使用密码解密文本
 * @param {string} password - 密码字符串
 * @param {string} encryptedBase64 - Base64编码的加密数据
 * @returns {Promise<string>} 解密后的文本
 */
async function decryptText(password, encryptedBase64) {
    try {
        // 1. 解码Base64数据
        const combinedBuffer = Uint8Array.from(atob(encryptedBase64), c => c.charCodeAt(0));
        
        // 2. 提取各部分数据
        const salt = combinedBuffer.slice(0, 16);
        const iv = combinedBuffer.slice(16, 28); // 12字节IV
        const encryptedData = combinedBuffer.slice(28);
        
        // 3. 准备密钥材料
        const encoder = new TextEncoder();
        const passwordBuffer = encoder.encode(password);
        
        const keyMaterial = await crypto.subtle.importKey(
            'raw',
            passwordBuffer,
            { name: 'PBKDF2' },
            false,
            ['deriveKey']
        );
        
        // 4. 派生解密密钥
        const key = await crypto.subtle.deriveKey(
            {
                name: 'PBKDF2',
                salt: salt,
                iterations: 100000,
                hash: 'SHA-256'
            },
            keyMaterial,
            { name: 'AES-GCM', length: 256 },
            false,
            ['decrypt']
        );
        
        // 5. 解密数据
        const decryptedBuffer = await crypto.subtle.decrypt(
            {
                name: 'AES-GCM',
                iv: iv
            },
            key,
            encryptedData
        );
        
        // 6. 转换为字符串
        const decoder = new TextDecoder();
        return decoder.decode(decryptedBuffer);
        
    } catch (error) {
        console.error('解密失败:', error);
        throw new Error('解密失败: ' + error.message);
    }
}

// API配置管理器
class APIConfigManager {
    constructor() {
        this.apiServices = null;
        this.selectedService = null;
        this.currentSettings = {};
        this.initialized = false;
    }
    
    // 初始化API服务
    async init() {
        if (this.initialized) return;
        
        try {
            // 从后端获取API服务数据
            const tkitMachine = await pywebview.api.get_attr('TKIT_MACHINE_OBJECT');
            const LLM_TRANSLATOR = await pywebview.api.get_attr('LLM_TRANSLATOR');
            if (tkitMachine && LLM_TRANSLATOR) {
                this.apiServices = tkitMachine;
                this.llmTranslator = LLM_TRANSLATOR;
                this.initialized = true;
                console.log('API服务数据加载成功');
            };
            await this.loadSettings();
            return true;
        } catch (error) {
            console.error('加载API服务数据失败:', error);
            return false;
        }
    }
    
    // 加载API服务到下拉框
    loadAPIServices() {
        if (!this.initialized || !this.apiServices) {
            console.error('API服务未初始化');
            return;
        }
        
        const apiSelectContainer = document.querySelector('.api-select');
        if (!apiSelectContainer) {
            console.error('找不到.api-select容器');
            return;
        }
        
        // 清空容器
        apiSelectContainer.innerHTML = '';
        
        // 创建下拉框
        const selectElement = document.createElement('select');
        selectElement.id = 'api-service-select';
        selectElement.className = 'api-service-select';
        
        // 添加所有API服务选项
        Object.keys(this.apiServices).forEach(serviceName => {
            const option = document.createElement('option');
            option.value = serviceName;
            option.textContent = serviceName;
            selectElement.appendChild(option);
        });
        
        // 添加到容器
        apiSelectContainer.appendChild(selectElement);
        
        // 添加选择事件监听
        selectElement.addEventListener('change', (e) => {
            this.onServiceSelected(e.target.value);
        });
    }
    
    // 当服务被选中时
    onServiceSelected(serviceKey) {
        if (!serviceKey || !this.apiServices[serviceKey]) {
            this.clearSettingsForm();
            this.clearStatusGrid();
            this.selectedService = null;
            return;
        }
        
        this.selectedService = serviceKey;
        configManager.updateConfigValue('api-select', serviceKey);
        const service = this.apiServices[serviceKey];
        
        // 更新服务状态
        this.updateServiceStatus(serviceKey, service);
        
        // 生成设置表单
        this.generateSettingsForm(serviceKey, service);

        if (serviceKey === 'LLM通用翻译服务') {
            this.addLLMServiceSelector();
        }
    }
    
    // 添加LLM服务选择器到表单
    addLLMServiceSelector() {
        if (!this.initialized || !this.llmTranslator) {
            console.error('LLM翻译器未初始化');
            return;
        }
        
        const apiSettingsContainer = document.querySelector('.api-settings-form');
        if (!apiSettingsContainer) {
            console.error('找不到.api-settings-form容器');
            return;
        }

        // 找到第一个设置字段容器，在其前面插入LLM选择器
        const firstField = apiSettingsContainer.querySelector('.api-setting-field');
        
        // 创建LLM选择器容器
        const selectorContainer = document.createElement('div');
        selectorContainer.className = 'api-setting-field';
        
        // 创建标签
        const label = document.createElement('label');
        label.htmlFor = 'api-llm-service-selector';
        label.textContent = '选择LLM服务';
        selectorContainer.appendChild(label);
        
        // 创建选择框
        const selectWrapper = document.createElement('div');
        selectWrapper.className = 'select-wrapper';
        
        const select = document.createElement('select');
        select.id = 'api-llm-service-selector';
        select.name = 'llm_service_selector';
        
        // 添加默认选项
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = '选择以使用预设LLM服务地址...';
        select.appendChild(defaultOption);
        
        // 添加所有LLM服务选项
        Object.keys(this.llmTranslator).forEach(serviceName => {
            const option = document.createElement('option');
            option.value = serviceName;
            option.textContent = serviceName;
            select.appendChild(option);
        });
        
        // 添加图标
        const chevronIcon = document.createElement('i');
        chevronIcon.className = 'fas fa-chevron-down';
        
        selectWrapper.appendChild(select);
        selectWrapper.appendChild(chevronIcon);
        selectorContainer.appendChild(selectWrapper);
        
        // 添加帮助文本
        const helpText = document.createElement('small');
        helpText.className = 'form-hint';
        helpText.textContent = '选择预设的LLM服务，将自动填充基础地址和模型名称参数';
        selectorContainer.appendChild(helpText);
        
        // 插入到表单顶部
        if (firstField) {
            apiSettingsContainer.insertBefore(selectorContainer, firstField);
        }
        
        // 添加选择事件监听
        select.addEventListener('change', (e) => {
            this.onLLMSelected(e.target.value);
        });
    }

    onLLMSelected(serviceKey) {
        if (!serviceKey || !this.llmTranslator[serviceKey]) {
            return;
        }
        
        const service = this.llmTranslator[serviceKey];
        
        // 填充对应的表单字段
        const baseURLElement = document.getElementById('api-base_url');
        const modelElement = document.getElementById('api-model_name');
        
        if (baseURLElement) {
            baseURLElement.value = service.base_url || '';
        }
        if (modelElement) {
            modelElement.value = service.model || '';
        }
    }

    // 加载API服务到翻译下拉框
    loadAPIServicesTranslator() {
        if (!this.initialized || !this.apiServices) {
            console.error('API服务未初始化');
            return;
        }
        
        const apiSelectContainer = document.querySelector('.translator-services');
        if (!apiSelectContainer) {
            console.error('找不到.translator-services容器');
            return;
        }
        
        // 清空容器
        apiSelectContainer.innerHTML = '';
        
        // 创建下拉框
        const selectElement = document.createElement('select');
        selectElement.id = 'translator-service-select';
        selectElement.className = 'translator-service-select';
        
        // 添加所有API服务选项
        Object.keys(this.apiServices).forEach(serviceName => {
            const option = document.createElement('option');
            option.value = serviceName;
            option.textContent = serviceName;
            selectElement.appendChild(option);
        });
        
        // 添加到容器
        apiSelectContainer.appendChild(selectElement);
    }
    
    // 生成API设置表单
    generateSettingsForm(serviceKey, service) {
        const apiSettingsContainer = document.querySelector('.api-settings');
        if (!apiSettingsContainer) {
            console.error('找不到.api-settings容器');
            return;
        }
        
        // 清空容器
        apiSettingsContainer.innerHTML = '';
        
        // 获取API设置描述
        const apiSetting = service['api-setting'];
        if (!apiSetting || !Array.isArray(apiSetting)) {
            const noSettings = document.createElement('div');
            noSettings.className = 'no-settings';
            noSettings.innerHTML = '<p>此服务无需API配置</p>';
            apiSettingsContainer.appendChild(noSettings);
            return;
        }
        
        // 创建表单容器
        const form = document.createElement('div');
        form.className = 'api-settings-form';
        
        // 添加表单标题
        const title = document.createElement('h4');
        title.textContent = 'API参数配置';
        form.appendChild(title);
        
        // 为每个设置项创建表单字段
        apiSetting.forEach(setting => {
            const fieldGroup = this.createSettingField(setting);
            form.appendChild(fieldGroup);
        });
        
        apiSettingsContainer.appendChild(form);
        
        // 加载已保存的设置
        this.loadSavedSettings(serviceKey);
    }
    
    // 创建单个设置字段 - 简化版
    createSettingField(setting) {
        const fieldGroup = document.createElement('div');
        fieldGroup.className = 'api-setting-field';
        
        // 创建标签（boolean类型不需要单独的标签）
        if (setting.type !== 'boolean') {
            const label = document.createElement('label');
            label.htmlFor = `api-${setting.id}`;
            label.textContent = setting.name;
            if (setting.required) {
                const requiredSpan = document.createElement('span');
                requiredSpan.className = 'required';
                requiredSpan.textContent = ' *';
                label.appendChild(requiredSpan);
            }
            fieldGroup.appendChild(label);
        }
        
        // 根据类型创建输入控件
        let inputElement;
        
        switch(setting.type) {
            case 'boolean':
                // 创建复选框结构
                inputElement = document.createElement('label');
                inputElement.className = 'checkbox-container';
                inputElement.htmlFor = `api-${setting.id}`;
                
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.id = `api-${setting.id}`;
                checkbox.name = setting.id;
                
                const checkmark = document.createElement('span');
                checkmark.className = 'checkmark';
                
                const labelText = document.createElement('span');
                labelText.textContent = setting.name || '';
                
                inputElement.appendChild(checkbox);
                inputElement.appendChild(checkmark);
                inputElement.appendChild(labelText);
                break;
                
            default:
                // 默认文本输入框
                inputElement = document.createElement('input');
                inputElement.type = 'text';
                inputElement.id = `api-${setting.id}`;
                inputElement.name = setting.id;
                inputElement.placeholder = setting.description || '';
                break;
        }
        
        fieldGroup.appendChild(inputElement);
        
        // 添加帮助文本（非boolean类型）
        if (setting.description && setting.type !== 'boolean') {
            const helpText = document.createElement('small');
            helpText.className = 'form-hint';
            helpText.textContent = setting.description;
            fieldGroup.appendChild(helpText);
        }
        
        return fieldGroup;
    }
    
    // 加载已保存的设置
    loadSavedSettings(serviceKey) {
        try {
            const savedSettings = this.currentSettings[serviceKey];
            
            if (savedSettings) {
                Object.keys(savedSettings).forEach(key => {
                    const input = document.getElementById(`api-${key}`);
                    if (input) {
                        if (input.type === 'checkbox') {
                            input.checked = savedSettings[key];
                        } else {
                            input.value = savedSettings[key];
                        }
                    }
                });
            }
        } catch (error) {
            console.error('加载保存的设置失败:', error);
        }
    }
    
    // 保存当前设置
    saveCurrentSettings() {
        if (!this.selectedService) {
            showMessage('错误', '请先选择翻译服务');
            return false;
        }
        
        const service = this.apiServices[this.selectedService];
        if (!service) {
            showMessage('错误', '未找到选中的服务');
            return false;
        }
        
        // 检查是否有 api-setting 配置
        const apiSetting = service['api-setting'];
        if (!apiSetting || !Array.isArray(apiSetting) || apiSetting.length === 0) {
            showMessage('提示', '此服务无需配置');
            
            // 如果服务没有配置，保存空对象
            this.currentSettings[this.selectedService] = {};
            
            // 发送到后端
            this.updateSettings();
            return true;
        }
        
        const settings = {};
        let isValid = true;
        const missingFields = [];
        
        // 收集所有设置值
        apiSetting.forEach(setting => {
            const input = document.getElementById(`api-${setting.id}`);
            if (input) {
                let value;
                
                if (input.type === 'checkbox') {
                    value = input.checked;
                } else if (input.tagName === 'SELECT') {
                    value = input.value;
                } else {
                    value = input.value.trim();
                }
                
                // 验证必填字段
                if (setting.required && (!value || value === '')) {
                    isValid = false;
                    missingFields.push(setting.name);
                    
                    // 添加错误样式
                    input.classList.add('error');
                } else {
                    input.classList.remove('error');
                }
                
                settings[setting.id] = value;
            }
        });
        
        if (!isValid) {
            showMessage('错误', `以下必填字段未填写：${missingFields.join(', ')}`);
            return false;
        }
        
        // 保存到后端
        try {
            this.currentSettings[this.selectedService] = settings;
            
            // 发送到后端
            this.updateSettings();
            
            return true;
        } catch (error) {
            console.error('保存设置失败:', error);
            showMessage('错误', '保存设置时发生错误');
            return false;
        }
    }

    collectCurrentSettings() {
        if (!this.selectedService) {
            showMessage('错误', '请先选择翻译服务');
            return false;
        }
        
        const service = this.apiServices[this.selectedService];
        if (!service) {
            showMessage('错误', '未找到选中的服务');
            return false;
        }
        
        // 检查是否有 api-setting 配置
        const apiSetting = service['api-setting'];
        if (!apiSetting || !Array.isArray(apiSetting) || apiSetting.length === 0) {
            // 返回空对象表示没有配置
            return {};
        }
        
        const settings = {};
        let isValid = true;
        const missingFields = [];
        
        // 收集所有设置值
        apiSetting.forEach(setting => {
            const input = document.getElementById(`api-${setting.id}`);
            if (input) {
                let value;
                
                if (input.type === 'checkbox') {
                    value = input.checked;
                } else if (input.tagName === 'SELECT') {
                    value = input.value;
                } else {
                    value = input.value.trim();
                }
                
                // 验证必填字段
                if (setting.required && (!value || value === '')) {
                    isValid = false;
                    missingFields.push(setting.name);
                    
                    // 添加错误样式
                    input.classList.add('error');
                } else {
                    input.classList.remove('error');
                }
                
                settings[setting.id] = value;
            }
        });
        
        if (!isValid) {
            showMessage('错误', `以下必填字段未填写：${missingFields.join(', ')}`);
            return false;
        }
        
        return settings;
    }    
    async loadSettings() { 
        try {
            const savedSettings = configManager.getCachedValue('api_config');
            let api_settings
            if (configManager.getCachedValue('api_crypto')) {
                api_settings = JSON.parse(await decryptText("AutoTranslate", savedSettings));
            }
            else {
                api_settings = JSON.parse(savedSettings);
            };
            this.currentSettings = api_settings;
        } catch (error) {
            console.error('加载设置失败:', error);
            addLogMessage('加载api设置时发生错误，清空api设置');
            this.updateSettings();
            return false;
        }
    }

    // 发送设置到后端
    async updateSettings() {
        try {
            let api_settings
            if (configManager.getCachedValue('api_crypto')) {
                api_settings = await encryptText("AutoTranslate", JSON.stringify(this.currentSettings));
            }
            else {
                api_settings = JSON.stringify(this.currentSettings);
            };
            configManager.updateConfigValue('api-configs', api_settings);
            configManager.flushPendingUpdates();
            return true;
        } catch (error) {
            console.error('发送到后端失败:', error);
            showMessage('错误', '保存到后端时发生错误');
            return false;
        }
    }
    
    // 更新服务状态网格
    updateServiceStatus(serviceKey, service) {
        const statusGrid = document.querySelector('.api-status-grid');
        if (!statusGrid) {
            console.error('找不到.api-status-grid容器');
            return;
        }
        
        // 清空容器
        statusGrid.innerHTML = '';
        
        // 获取metadata
        const metadata = service.metadata || {};
        
        // 创建状态卡片
        const statusCard = document.createElement('div');
        statusCard.className = 'api-status-card';
        
        // 服务名称
        const nameElement = document.createElement('h4');
        nameElement.textContent = serviceKey;
        statusCard.appendChild(nameElement);
        
        // 服务描述
        if (metadata.description) {
            const descElement = document.createElement('p');
            descElement.className = 'api-description';
            descElement.textContent = metadata.description;
            statusCard.appendChild(descElement);
        }

        // 使用说明
        if (metadata.usage_documentation) {
            const shortDescElement = document.createElement('p');
            shortDescElement.className = 'api-usage-documentation';
            shortDescElement.textContent = metadata.usage_documentation;
            statusCard.appendChild(shortDescElement);
        }

        // 短描述
        if (metadata.short_description) {
            const shortDescElement = document.createElement('p');
            shortDescElement.className = 'api-short-desc';
            shortDescElement.textContent = metadata.short_description;
            statusCard.appendChild(shortDescElement);
        }
        
        // 链接
        const linksContainer = document.createElement('div');
        linksContainer.className = 'api-links';
        
        if (metadata.console_url) {
            const consoleLink = document.createElement('a');
            consoleLink.href = metadata.console_url;
            consoleLink.target = '_blank';
            consoleLink.textContent = '控制台';
            consoleLink.className = 'api-link';
            linksContainer.appendChild(consoleLink);
        }
        
        if (metadata.documentation_url) {
            const docLink = document.createElement('a');
            docLink.href = metadata.documentation_url;
            docLink.target = '_blank';
            docLink.textContent = '文档';
            docLink.className = 'api-link';
            linksContainer.appendChild(docLink);
        }
        
        if (linksContainer.children.length > 0) {
            statusCard.appendChild(linksContainer);
        }
        
        // 语言代码
        if (service.langCode) {
            const langContainer = document.createElement('div');
            langContainer.className = 'api-lang-codes';
            
            const langTitle = document.createElement('h5');
            langTitle.textContent = '支持的语言代码:';
            langContainer.appendChild(langTitle);
            
            const langList = document.createElement('div');
            langList.className = 'lang-list';
            
            Object.entries(service.langCode).forEach(([key, value]) => {
                const langItem = document.createElement('span');
                langItem.className = 'lang-item';
                langItem.textContent = `${key} → ${value}`;
                langList.appendChild(langItem);
            });
            
            langContainer.appendChild(langList);
            statusCard.appendChild(langContainer);
        }
        
        // 添加到网格
        statusGrid.appendChild(statusCard);
    }
    
    // 清空设置表单
    clearSettingsForm() {
        const apiSettingsContainer = document.querySelector('.api-settings');
        if (apiSettingsContainer) {
            apiSettingsContainer.innerHTML = '';
        }
    }
    
    // 清空状态网格
    clearStatusGrid() {
        const statusGrid = document.querySelector('.api-status-grid');
        if (statusGrid) {
            statusGrid.innerHTML = '';
        }
    }
    
    // 获取所有服务的设置
    getAllSettings() {
        return this.currentSettings;
    }
    
    // 获取特定服务的设置
    getServiceSettings(serviceKey) {
        return this.currentSettings[serviceKey] || {};
    }

    async testAPIConfig() {
        const modal = new ProgressModal('测试API配置');
        modal.addLog('正在测试API配置...')
        const apiConfig = this.collectCurrentSettings();

        if (apiConfig === false) {
            modal.complete(false, '测试失败');
            return;
        }
        const result = await pywebview.api.test_api(
            this.selectedService, apiConfig
        )

        if (result.success) {
            modal.addLog('API配置测试成功！');
            modal.addLog('测试信息如下');
            const result_json = result.message;
            modal.addLog(`韩文：안녕 -> ${result_json.kr}`);
            modal.addLog(`英文：hello -> ${result_json.en}`);
            modal.addLog(`日文：こんにちは -> ${result_json.jp}`);
            modal.complete(true, '测试成功');
        } else {
            modal.addLog('API配置测试失败！');
            modal.addLog(result.message);
            modal.complete(false, '测试失败');
        }
    }
}

// 初始化API配置管理器
let apiConfigManager;

async function loadAndRenderMarkdown() {
  try {
    // 定义要加载的文件路径
    const files = [
      { url: '/assets/README.md', className: 'about-content' },
      { url: '/assets/update.md', className: 'update-content' },
      { url: '/assets/firstUse.md', className: 'use-help' }
    ];

    // 并发请求所有文件
    const promises = files.map(async ({ url, className }) => {
      try {
        // 请求Markdown文件
        const response = await fetch(url);
        
        if (!response.ok) {
          throw new Error(`加载 ${url} 失败: ${response.status} ${response.statusText}`);
        }
        
        // 获取文本内容
        const markdownText = await response.text();
        
        // 检查simpleMarkdownToHtml函数是否存在
        if (typeof simpleMarkdownToHtml !== 'function') {
          throw new Error('simpleMarkdownToHtml函数未定义');
        }
        
        // 转换Markdown为HTML
        const htmlContent = simpleMarkdownToHtml(markdownText);
        
        // 找到目标div元素
        const targetDiv = document.querySelector(`.${className}`);
        
        if (!targetDiv) {
          console.warn(`未找到class为${className}的元素`);
          return;
        }
        
        // 插入HTML内容
        targetDiv.innerHTML = htmlContent;
        
        console.log(`成功加载并渲染: ${url}`);
        
      } catch (error) {
        console.error(`处理 ${url} 时出错:`, error);
        // 可以选择在对应的div中显示错误信息
        const targetDiv = document.querySelector(`.${className}`);
        if (targetDiv) {
          targetDiv.innerHTML = `<p class="error">加载内容失败: ${error.message}</p>`;
        }
      }
    });

    // 等待所有文件加载完成
    await Promise.allSettled(promises);
    
    console.log('所有Markdown文件加载完成');
    
  } catch (error) {
    console.error('加载Markdown文件过程中发生错误:', error);
  }
}

// 浏览文件函数
function browseFile(inputId) {
    pywebview.api.browse_file(inputId);
}

function browseFolder(inputId) {
    pywebview.api.browse_folder(inputId);
}

function toggleCachePathInput() {
    const enableCacheCheckbox = document.getElementById('enable-cache');
    const cachePathGroup = document.getElementById('cache-path-group');
    
    if (enableCacheCheckbox.checked) {
        cachePathGroup.style.display = 'block';
    } else {
        cachePathGroup.style.display = 'none';
    }
}

function toggleStoragePathInput() {
    const enableStorageCheckbox = document.getElementById('enable-storage');
    const storagePathGroup = document.getElementById('storage-path-group');
    
    if (enableStorageCheckbox.checked) {
        storagePathGroup.style.display = 'block';
    } else {
        storagePathGroup.style.display = 'none';
    }
}

function toggleDevelopSettings() {
    const group = document.getElementById('dev-settings');
    const enable = document.getElementById('enable-dev-settings');
    if (enable.checked) {
        group.style.display = 'block';
    } 
    else {
        group.style.display = 'none';
    }
};

async function toggleCustomLang() {
    const checkbox = document.getElementById('enable-lang');
    await pywebview.api.toggle_installed_package(checkbox.checked);
    toggleCustomLangGui();
}

/**
 * 切换“客制化翻译”启用状态，控制遮罩层的显示与隐藏
 */
function toggleCustomLangGui() {
    const checkbox = document.getElementById('enable-lang');
    const group = document.getElementById('installed-package-group');
    if (!checkbox || !group) return;

    const overlayClass = 'installed-package-overlay';
    let overlay = group.querySelector('.' + overlayClass);

    if (!checkbox.checked) {
        // 未启用 → 显示遮罩层
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = overlayClass;
            overlay.innerHTML = `
                <i class="fas fa-lock"></i>
                <p>客制化翻译已禁用</p>
                <small>勾选上方选项以启用此区域</small>
            `;
            group.appendChild(overlay);
        }
    } else {
        // 已启用 → 移除遮罩层
        if (overlay) {
            overlay.remove();
        }
    }
}

function toggleProper() {
    const group = document.getElementById('proper-settings');
    const enable = document.getElementById('enable-proper');
    if (enable.checked) {
        group.style.display = 'block';
    } 
    else {
        group.style.display = 'none';
    }
};

function toggleAutoProper() {
    const group = document.getElementById('proper-path-text');
    const enable = document.getElementById('auto-fetch-proper');
    if (enable.checked) {
        group.style.display = 'none';
    } 
    else {
        group.style.display = 'block';
    }
};

function toggleEnableScreen() {
    const group = document.getElementById('bubble-screen-group');
    const enable = document.getElementById('bubble-enable-screen');
    if (enable.checked) {
        group.style.display = 'block';
    } 
    else {
        group.style.display = 'none';
    }
};

function toggleSteamCommand() {
    let command
    pywebview.api.run_func('get_steam_command').then(function(result) {
        command=result;
        const cmdElement = document.getElementById('steam-cmd');
        cmdElement.value = command;
    }).catch(function(error) {
        command=`获取失败 ${error}`;
        const cmdElement = document.getElementById('steam-cmd');
        cmdElement.value = command;
    });
}

function goTestSection(DIEPLAY){
    const testButton = document.getElementById('test-btn');
    if (DIEPLAY) {
        testButton.style.display = 'block';
        testButton.click();
    } 
    else {
        testButton.style.display = 'none';
    }
};

function copySteamPath() {
    const cmdElement = document.getElementById('steam-cmd');

    cmdElement.select();
    cmdElement.setSelectionRange(0, 99999); /* 为移动设备设置 */

    /* 复制内容到文本域 */
    navigator.clipboard.writeText(cmdElement.value);
}

// 浏览安装界面的汉化包目录
function browseInstallPackageDirectory() {
    pywebview.api.browse_folder('install-package-directory').then(function(result) {
        const packageDirInput = document.getElementById('install-package-directory');
        if (packageDirInput && result) {
            packageDirInput.value = result;
            configManager.updateConfigValue('install-package-directory', result)
                .then(() => {
                    refreshInstallPackageList();
                });
        }
    }).catch(function(error) {
        showMessage('错误', '浏览文件夹时发生错误: ' + error);
    });
}

// 清空汉化包目录输入框
function clearPackageDirectory() {
    const packageDirInput = document.getElementById('install-package-directory');
    if (packageDirInput) {
        packageDirInput.value = '';
        configManager.updateConfigValue('install-package-directory', '')
            .then(() => {
                refreshInstallPackageList();
            });
    }
}

// 浏览安装界面的汉化包目录
function browseInstallModDirectory() {
    pywebview.api.browse_folder('installed-mod-directory').then(function(result) {
        const modDirInput = document.getElementById('installed-mod-directory');
        if (modDirInput && result) {
            modDirInput.value = result;
            configManager.updateConfigValue('installed-mod-directory', result)
                .then(() => {
                    refreshInstallPackageList();
                });
        }
    }).catch(function(error) {
        showMessage('错误', '浏览文件夹时发生错误: ' + error);
    });
}

// 清空汉化包目录输入框
function clearModDirectory() {
    const modDirInput = document.getElementById('installed-mod-directory');
    if (modDirInput) {
        modDirInput.value = '';
        configManager.updateConfigValue('installed-mod-directory', '')
            .then(() => {
                refreshInstallPackageList();
            });
    }
}

// 模态窗口基类
class ModalWindow {
    constructor(title, options = {}) {
        this.id = 'modal-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
        this.title = title;
        this.isMinimized = false;
        this.isCompleted = false;
        this.isPaused = false;
        this.options = {
            showProgress: false,
            showCancelButton: true,
            showPauseButton: false,
            cancelButtonText: '取消',
            pauseButtonText: '暂停',
            resumeButtonText: '继续',
            confirmButtonText: '确定',
            showMinimizeButton: true,
            showLog: true,
            onCancel: null,
            onPause: null,
            onResume: null,
            ...options
        };
        this.createModal();
        modalWindows.push(this);
    }
    
    createModal() {
        const modalContainer = ensureModalContainer();
        
        this.element = document.createElement('div');
        this.element.className = 'modal-overlay';
        
        const currentTheme = document.body.classList.contains('theme-dark') ? 'theme-dark' :
                           document.body.classList.contains('theme-purple') ? 'theme-purple' : 'theme-light';
        
        this.element.classList.add(currentTheme);
        
        this.element.innerHTML = `
            <div class="modal-window">
                <div class="modal-header">
                    <div class="modal-title">${this.title}</div>
                    <div class="modal-controls">
                        ${this.options.showMinimizeButton ? `<button class="modal-button" id="minimize-btn-${this.id}" title="最小化">−</button>` : ''}
                        <button class="modal-button" id="close-btn-${this.id}" title="关闭">×</button>
                    </div>
                </div>
                <div class="modal-body">
                    <div class="modal-status" id="modal-status-${this.id}">准备就绪</div>
                    ${this.options.showLog ? `<div class="modal-log" id="modal-log-${this.id}"></div>` : ''}
                    <div class="modal-progress ${this.options.showProgress ? '' : 'hidden'}" id="modal-progress-${this.id}">
                        <div class="modal-progress-bar">
                            <div class="modal-progress-fill" id="modal-progress-fill-${this.id}"></div>
                        </div>
                    </div>
                </div>
                <div class="modal-footer" id="modal-footer-${this.id}">
                    ${this.getFooterButtons()}
                </div>
            </div>
        `;
        
        modalContainer.appendChild(this.element);
        
        this.bindEvents();
    }
    
    getFooterButtons() {
        let buttons = '';
        if (this.options.showPauseButton) {
            buttons += `<button class="action-btn" id="pause-btn-${this.id}">${this.options.pauseButtonText}</button>`;
        }
        if (this.options.showCancelButton) {
            buttons += `<button class="action-btn" id="cancel-btn-${this.id}">${this.options.cancelButtonText}</button>`;
        }
        return buttons;
    }
    
    bindEvents() {
        document.getElementById(`close-btn-${this.id}`).addEventListener('click', () => {
            this.close();
        });
        
        if (this.options.showMinimizeButton) {
            document.getElementById(`minimize-btn-${this.id}`).addEventListener('click', (e) => {
                e.stopPropagation();
                this.minimize();
            });
        }
        
        if (this.options.showPauseButton) {
            document.getElementById(`pause-btn-${this.id}`).addEventListener('click', () => {
                if (this.isPaused) {
                    this.resume();
                } else {
                    this.pause();
                }
            });
        }
        
        if (this.options.showCancelButton) {
            document.getElementById(`cancel-btn-${this.id}`).addEventListener('click', () => {
                if (this.isCompleted) {
                    this.close();
                } else {
                    this.cancel();
                }
            });
        }
    }
    
    setStatus(status) {
        const statusElement = document.getElementById(`modal-status-${this.id}`);
        if (statusElement) {
            if (typeof status === 'string' && status.includes('\n')) {
                statusElement.innerHTML = status.replace(/\n/g, '<br>');
            } else {
                statusElement.textContent = status;
            }
        }
        addLogMessage(`[${this.title}] ${status}`);
        this.updateMinimizedStatus(status);
    }
    
    addLog(message) {
        if (this.options.showLog) {
            const logElement = document.getElementById(`modal-log-${this.id}`);
            if (logElement) {
                const now = new Date();
                const timestamp = `[${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}]`;
                
                const logEntry = document.createElement('div');
                logEntry.textContent = `${timestamp} ${message}`;
                logElement.appendChild(logEntry);
                logElement.scrollTop = logElement.scrollHeight;
            }
        }
        addLogMessage(`[${this.title}] ${message}`);
    }
    
    showProgress(show = true) {
        const progressElement = document.getElementById(`modal-progress-${this.id}`);
        if (progressElement) {
            if (show) {
                progressElement.classList.remove('hidden');
            } else {
                progressElement.classList.add('hidden');
            }
        }
    }
    
    updateProgress(percent, text = '') {
        const progressFill = document.getElementById(`modal-progress-fill-${this.id}`);
        if (progressFill) {
            progressFill.style.width = percent + '%';
        }
        
        if (text) {
            addLogMessage(`[${this.title}] ${text}`);
        }
        
        const mainProgressFill = document.getElementById('progress-fill');
        const mainProgressPercent = document.getElementById('progress-percent');
        const mainProgressText = document.getElementById('progress-text');
        const progressContainer = document.getElementById('translation-progress');
        
        if (mainProgressFill && mainProgressPercent) {
            mainProgressFill.style.width = percent + '%';
            mainProgressPercent.textContent = percent + '%';
            progressContainer.style.display = 'block';
        }
        
        if (mainProgressText && text) {
            mainProgressText.textContent = text;
        }
        
        this.syncProgressToMinimized(percent);
    }
    
    setCompleted() {
        this.isCompleted = true;
        const cancelButton = document.getElementById(`cancel-btn-${this.id}`);
        const pauseButton = document.getElementById(`pause-btn-${this.id}`);
        
        if (cancelButton) {
            cancelButton.textContent = '完成';
        }
        
        if (pauseButton) {
            pauseButton.style.display = 'none';
        }
        
        this.updateMinimizedStatus('已完成');
    }
    
    pause() {
        if (this.isCompleted) return;
        
        this.isPaused = true;
        const pauseButton = document.getElementById(`pause-btn-${this.id}`);
        if (pauseButton) {
            pauseButton.textContent = this.options.resumeButtonText;
        }
        
        this.setStatus('已暂停');
        this.addLog('操作已暂停');
        
        if (this.options.onPause && typeof this.options.onPause === 'function') {
            this.options.onPause(this.id);
        }
    }
    
    resume() {
        if (this.isCompleted) return;
        
        this.isPaused = false;
        const pauseButton = document.getElementById(`pause-btn-${this.id}`);
        if (pauseButton) {
            pauseButton.textContent = this.options.pauseButtonText;
        }
        
        this.setStatus('正在恢复...');
        this.addLog('操作已恢复');
        
        if (this.options.onResume && typeof this.options.onResume === 'function') {
            this.options.onResume(this.id);
        }
    }
    
    cancel() {
        if (this.options.onCancel && typeof this.options.onCancel === 'function') {
            this.options.onCancel(this.id);
        }
        this.close();
    }
    
    minimize() {
        if (this.isMinimized) return;
        
        this.isMinimized = true;
        const minimizedContainer = ensureMinimizedContainer();
        
        const minimizedElement = document.createElement('div');
        minimizedElement.className = 'minimized-modal';
        minimizedElement.id = `minimized-${this.id}`;
        minimizedElement.innerHTML = `
            <div class="minimized-header">
                <div class="minimized-title">${this.title}</div>
                <div class="minimized-status" id="minimized-status-${this.id}">运行中</div>
            </div>
            <div class="minimized-progress">
                <div class="minimized-progress-bar">
                    <div class="minimized-progress-fill" id="minimized-progress-fill-${this.id}"></div>
                </div>
            </div>
        `;
        
        minimizedElement.addEventListener('click', (e) => {
            e.stopPropagation();
            this.restoreFromMinimized();
        });
        
        minimizedContainer.appendChild(minimizedElement);
        this.element.style.display = 'none';
    }
    
    restoreFromMinimized() {
        if (!this.isMinimized) return;
        
        this.isMinimized = false;
        const minimizedElement = document.getElementById(`minimized-${this.id}`);
        if (minimizedElement) {
            minimizedElement.remove();
        }
        
        this.element.style.display = 'flex';
    }
    
    close() {
        const index = modalWindows.indexOf(this);
        if (index > -1) {
            modalWindows.splice(index, 1);
        }
        
        if (this.element) {
            AnimationManager.fadeOut(this.element);
            setTimeout(() => {
                this.element.remove();
            }, 300);
        }
        
        const minimizedElement = document.getElementById(`minimized-${this.id}`);
        if (minimizedElement) {
            minimizedElement.remove();
        }
    }
    
    syncProgressToMinimized(percent) {
        if (!this.isMinimized) return;
        
        const progressFill = document.getElementById(`minimized-progress-fill-${this.id}`);
        if (progressFill) {
            progressFill.style.width = percent + '%';
        }
    }
    
    updateMinimizedStatus(status) {
        if (!this.isMinimized) return;
        
        const statusElement = document.getElementById(`minimized-status-${this.id}`);
        if (statusElement) {
            statusElement.textContent = status;
        }
    }
}

// 消息模态窗口类
class MessageModal extends ModalWindow {
    constructor(title, message, onCloseCallback = null) {
        super(title, {
            showProgress: false,
            showCancelButton: true,
            cancelButtonText: '确定',
            showMinimizeButton: false,
            showLog: false
        });
        
        this.onCloseCallback = onCloseCallback;
        this.setStatus(message);
        this.setupMessageButton();
    }
    
    setupMessageButton() {
        const cancelButton = document.getElementById(`cancel-btn-${this.id}`);
        if (cancelButton) {
            cancelButton.textContent = '确定';
            const newCancelButton = cancelButton.cloneNode(true);
            document.getElementById(`modal-footer-${this.id}`).replaceChild(newCancelButton, cancelButton);
            
            newCancelButton.addEventListener('click', () => {
                this.close();
                if (this.onCloseCallback && typeof this.onCloseCallback === 'function') {
                    this.onCloseCallback();
                }
            });
        }
    }
}

// 确认模态窗口类
class ConfirmModal extends ModalWindow {
    constructor(title, message, onConfirmCallback, onCancelCallback) {
        super(title, {
            showProgress: false,
            showCancelButton: true,
            cancelButtonText: '取消',
            showMinimizeButton: false,
            showLog: false
        });
        
        this.onConfirmCallback = onConfirmCallback;
        this.onCancelCallback = onCancelCallback;
        
        this.setStatus(message);
        this.setupConfirmButtons();
    }
    
    setupConfirmButtons() {
        const modalFooter = document.getElementById(`modal-footer-${this.id}`);
        if (modalFooter) {
            modalFooter.innerHTML = `
                <button class="primary-btn" id="confirm-btn-${this.id}">确定</button>
                <button class="action-btn" id="cancel-btn-${this.id}">取消</button>
            `;
            
            document.getElementById(`confirm-btn-${this.id}`).addEventListener('click', () => {
                this.close();
                if (this.onConfirmCallback && typeof this.onConfirmCallback === 'function') {
                    this.onConfirmCallback();
                }
            });
            
            document.getElementById(`cancel-btn-${this.id}`).addEventListener('click', () => {
                this.close();
                if (this.onCancelCallback && typeof this.onCancelCallback === 'function') {
                    this.onCancelCallback();
                }
            });
            
            document.getElementById(`close-btn-${this.id}`).addEventListener('click', () => {
                this.close();
                if (this.onCancelCallback && typeof this.onCancelCallback === 'function') {
                    this.onCancelCallback();
                }
            });
        }
    }
    
    setHtmlContent(htmlContent) {
        const statusElement = document.getElementById(`modal-status-${this.id}`);
        if (statusElement) {
            statusElement.innerHTML = htmlContent;
        }
        addLogMessage(`[${this.title}] 更新信息已设置`);
    }
}

// 进度模态窗口类
class ProgressModal extends ModalWindow {
    constructor(title) {
        super(title, {
            showProgress: true,
            showCancelButton: true,
            showPauseButton: true,
            cancelButtonText: '取消',
            pauseButtonText: '暂停',
            resumeButtonText: '继续'
        });
        
        this.setStatus('正在初始化...');
        this.showProgress(true);
        this.updateProgress(0, '初始化中...');
        
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.add_modal_id) {
            pywebview.api.add_modal_id(this.id)
                .catch(function(error) {
                    console.error('注册模态ID失败:', error);
                });
        }
    }
    
    complete(success = true, message = '操作完成') {
        if (success) {
            this.setStatus('操作完成');
            this.addLog(message);
            this.updateProgress(100, '完成');
        } else {
            this.setStatus('操作失败');
            this.addLog(message);
        }
        this.setCompleted();
    }
    
    cancel() {
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.handle_modal_cancel) {
            pywebview.api.handle_modal_cancel(this.id)
                .catch(function(error) {
                    console.error('处理取消操作失败:', error);
                });
        }
        
        super.cancel();
    }
    
    pause() {
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.handle_modal_pause) {
            pywebview.api.handle_modal_pause(this.id)
                .catch(function(error) {
                    console.error('处理暂停操作失败:', error);
                });
        }
        
        super.pause();
    }
    
    resume() {
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.handle_modal_resume) {
            pywebview.api.handle_modal_resume(this.id)
                .catch(function(error) {
                    console.error('处理恢复操作失败:', error);
                });
        }
        
        super.resume();
    }
}

// 工厂函数
function showMessage(title, message, onCloseCallback = () => {
    pywebview.api.log("用户关闭窗口")
}) {
    return new MessageModal(title, message, onCloseCallback);
}

function showConfirm(title, message, onConfirmCallback, onCancelCallback) {
    return new ConfirmModal(title, message, onConfirmCallback, onCancelCallback);
}

function showProgress(title) {
    return new ProgressModal(title);
}

// 各功能函数
async function startTranslation() {
    const modal = new ProgressModal('开始翻译');
    modal.setStatus('正在初始化翻译过程...');
    modal.addLog('开始翻译任务');
    await configManager.updateConfigValues(configManager.collectConfigFromUI());
    
    pywebview.api.start_translation(apiConfigManager.currentSettings,
        modal.id).then(function(result) {
        if (result.success) {
            modal.complete(true, '翻译任务已完成');
        } else {
            modal.complete(false, '翻译失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '翻译过程中发生错误: ' + error);
    });
}

// ================================
// 通用列表管理器（支持多实例、选中状态、自定义回调）
// ================================
class ItemListManager {
    /**
     * @param {string} containerId - 容器元素ID
     * @param {Object} options - 配置选项
     * @param {function} options.onSelect - 当项目被选中时的回调 (item) => {}
     * @param {string} options.emptyMessage - 列表为空时显示的消息
     * @param {string} options.itemIcon - 项目图标类名
     */
    constructor(containerId, options = {}) {
        this.containerElement = document.getElementById(containerId);
        if (!this.containerElement) {
            console.error(`容器元素未找到: #${containerId}`);
        }
        this.items = [];
        this.selectedItem = null;
        this.onSelect = options.onSelect || null;
        this.emptyMessage = options.emptyMessage || '未找到可用的项目';
        this.itemIcon = options.itemIcon || 'fa-box';
    }

    // 显示加载中
    waitList() {
        if (!this.containerElement) return;
        this.containerElement.innerHTML = `
            <div class="list-empty">
                <i class="fas fa-spinner fa-spin"></i>
                <p>正在加载中...</p>
            </div>
        `;
    }

    // 刷新整个列表（根据 items 数组）
    updateList() {
        if (!this.containerElement) return;
        this.containerElement.innerHTML = '';

        if (this.items.length > 0) {
            this.items.forEach(item => {
                const itemElement = this._createItemElement(item);
                this.containerElement.appendChild(itemElement);
            });
        } else {
            const emptyDiv = document.createElement('div');
            emptyDiv.className = 'list-empty';
            emptyDiv.innerHTML = `
                <i class="fas fa-box-open"></i>
                <p>${this.emptyMessage}</p>
            `;
            this.containerElement.appendChild(emptyDiv);
        }
    }

    // 创建单个列表项 DOM
    _createItemElement(item) {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'list-item';
        if (this.selectedItem === item) {
            itemDiv.classList.add('selected');
            itemDiv.setAttribute('data-selected', 'true');
        }

        itemDiv.innerHTML = `
            <div class="list-item-content">
                <i class="fas ${this.itemIcon}"></i>
                <span>${item}</span>
            </div>
            <div class="list-item-actions">
                <button class="list-action-btn" title="选择">
                    <i class="fas fa-check"></i>
                </button>
            </div>
        `;

        // 绑定选择按钮事件
        const selectBtn = itemDiv.querySelector('.list-action-btn');
        selectBtn.addEventListener('click', (e) => {
            e.preventDefault();
            this.setSelectedItem(item);
            if (this.onSelect && typeof this.onSelect === 'function') {
                this.onSelect(item);
            }
        });

        return itemDiv;
    }

    // ----- 数据操作方法 -----
    setItems(items) {
        this.items = items;
        // 如果之前选中的项目已不存在，清空选中
        if (this.selectedItem && !this.items.includes(this.selectedItem)) {
            this.selectedItem = null;
        }
        this.updateList();
    }

    addItem(item) {
        if (!this.items.includes(item)) {
            this.items.push(item);
            this.updateList();
        }
    }

    removeItem(item) {
        const index = this.items.indexOf(item);
        if (index !== -1) {
            this.items.splice(index, 1);
            if (this.selectedItem === item) {
                this.selectedItem = null;
            }
            this.updateList();
        }
    }

    // ----- 选中状态管理 -----
    setSelectedItem(item) {
        if (this.items.includes(item)) {
            this.selectedItem = item;
        } else {
            this.selectedItem = null;
        }
        this.updateList(); // 重新渲染以高亮选中项
    }

    getSelectedItem() {
        return this.selectedItem;
    }

    // ----- 错误显示 -----
    showErrorList(error) {
        if (!this.containerElement) return;
        console.error('获取列表失败:', error);
        this.containerElement.innerHTML = '';
        const errorDiv = document.createElement('div');
        errorDiv.className = 'list-empty';
        errorDiv.innerHTML = `
            <i class="fas fa-exclamation-triangle"></i>
            <p>获取列表失败: ${error.message || '未知错误'}</p>
        `;
        this.containerElement.appendChild(errorDiv);
    }
}


// 创建汉化包列表管理器实例
let packageItemManager = new ItemListManager('install-package-list', {
    emptyMessage: '未找到可用的汉化包',
    itemIcon: 'fa-box',
    onSelect: (item) => {
        addLogMessage(`已选中汉化包: ${item}`, 'info');
    }
});

/**
 * 刷新汉化包列表
 * 从后端获取数据后调用管理器的 setItems 和 updateList 进行渲染
 */
function refreshInstallPackageList() {
    const packageList = document.getElementById('install-package-list');
    if (!packageList) return;

    // 显示加载状态
    packageItemManager.waitList();

    pywebview.api.get_translation_packages()
        .then(function(result) {
            if (result.success && result.packages && result.packages.length > 0) {
                // 设置数据并更新列表
                packageItemManager.setItems(result.packages);
            } else {
                // 空列表也会自动显示 emptyMessage
                packageItemManager.setItems([]);
            }
        })
        .catch(function(error) {
            console.error('获取汉化包列表失败:', error);
            packageItemManager.showErrorList(error);
        });
}

/**
 * 安装选中的汉化包
 */
function installSelectedPackage() {
    const packageName = packageItemManager.getSelectedItem();
    if (!packageName) {
        showMessage('提示', '请先选择一个汉化包');
        return;
    }

    const modal = new ProgressModal('安装汉化包');
    modal.addLog(`开始安装汉化包: ${packageName}`);

    pywebview.api.install_translation(packageName, modal.id)
        .then(function(result) {
            if (result.success) {
                modal.complete(true, '汉化包安装成功');
            } else {
                modal.complete(false, '安装失败: ' + result.message);
            }
        })
        .catch(function(error) {
            modal.complete(false, '安装过程中发生错误: ' + error);
        });
}

/**
 * 删除选中的汉化包
 */
function deleteSelectedPackage() {
    const packageName = packageItemManager.getSelectedItem();
    if (!packageName) {
        showMessage('提示', '请先选择一个汉化包');
        return;
    }

    showConfirm('确认删除', `确定要删除汉化包 "${packageName}" 吗？此操作不可撤销。`,
        function() {
            pywebview.api.delete_translation_package(packageName)
                .then(function(result) {
                    if (result.success) {
                        // 从管理器中移除该项，自动更新列表并清空选中状态
                        packageItemManager.removeItem(packageName);
                        showMessage('删除成功', `汉化包 "${packageName}" 已被删除`);
                    } else {
                        showMessage('删除失败', `删除汉化包失败: ${result.message}`);
                    }
                })
                .catch(function(error) {
                    showMessage('删除失败', `删除过程中发生错误: ${error}`);
                });
        },
        function() {
            // 取消删除，无操作
        }
    );
}

function changeFontForPackage() {
    const packageName = packageItemManager.getSelectedItem();
    if (!packageName) {
        showMessage('错误', '无法获取选中汉化包的名称');
        return;
    }
    
    pywebview.api.get_system_fonts_list()
        .then(function(result) {
            const modal = new ModalWindow('更换字体', {
                showProgress: false,
                showCancelButton: true,
                cancelButtonText: '关闭',
                showMinimizeButton: true,
                showLog: false
            });
            
            let modalContent = `
                <div class="font-selector">
                    <div class="form-group">
                        <label for="font-search-${modal.id}">搜索字体:</label>
                        <input type="text" id="font-search-${modal.id}" placeholder="输入字体名称搜索..." style="width: 100%;">
                    </div>
                    <div class="form-group">
                        <label>系统字体:</label>
                        <div class="list-container" style="max-height: 200px; overflow-y: auto;">
                            <div id="font-list-${modal.id}" style="width: 100%; padding: 10px;">
            `;
            
            if (result.success && result.fonts && result.fonts.length > 0) {
                modalContent += '<div class="list-empty"><p>加载中...</p></div>';
            } else {
                modalContent += '<div class="list-empty"><p>未找到系统字体</p></div>';
            }
            
            modalContent += `
                            </div>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>预览:</label>
                        <div id="font-preview-${modal.id}" style="border: 1px solid var(--color-border); padding: 10px; min-height: 60px; background-color: var(--color-bg-input); border-radius: var(--radius-md);">
                            选择字体以预览
                        </div>
                    </div>
                </div>
            `;
            
            modal.element.querySelector('.modal-body').innerHTML = modalContent;
            
            if (result.success && result.fonts && result.fonts.length > 0) {
                const fontList = document.getElementById(`font-list-${modal.id}`);
                fontList.innerHTML = '';
                
                result.fonts.forEach(font => {
                    const fontItem = document.createElement('div');
                    fontItem.className = 'list-item';
                    fontItem.innerHTML = `
                        <div class="list-item-content">
                            <i class="fas fa-font"></i>
                            <span>${font}</span>
                        </div>
                    `;
                    fontItem.addEventListener('click', () => {
                        document.querySelectorAll(`#font-list-${modal.id} .list-item`).forEach(item => {
                            item.classList.remove('selected');
                        });
                        fontItem.classList.add('selected');
                        
                        const previewDiv = document.getElementById(`font-preview-${modal.id}`);
                        previewDiv.innerHTML = `
                            <div style="font-family: '${font}'; font-size: 16px; margin-bottom: 8px;">
                                字体预览: ${font}
                            </div>
                            <div style="font-family: '${font}';">
                                The quick brown fox jumps over the lazy dog.<br>
                                0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ<br>
                                abcdefghijklmnopqrstuvwxyz<br>
                                中文示例文本
                            </div>
                        `;
                    });
                    fontList.appendChild(fontItem);
                });
                
                const searchInput = document.getElementById(`font-search-${modal.id}`);
                searchInput.addEventListener('input', function() {
                    const searchTerm = searchInput.value.toLowerCase();
                    const items = fontList.querySelectorAll('.list-item');
                    
                    items.forEach(item => {
                        const fontName = item.querySelector('span')?.textContent?.toLowerCase() || '';
                        if (fontName.includes(searchTerm)) {
                            item.style.display = 'flex';
                        } else {
                            item.style.display = 'none';
                        }
                    });
                });
            }
            
            const confirmBtn = document.createElement('button');
            confirmBtn.className = 'primary-btn';
            confirmBtn.innerHTML = '<i class="fas fa-check"></i> 确定';
            confirmBtn.onclick = function() {
                const selectedFontItem = document.querySelector(`#font-list-${modal.id} .list-item.selected`);
                if (!selectedFontItem) {
                    showMessage('提示', '请先选择一个字体');
                    return;
                }
                
                const fontName = selectedFontItem.querySelector('span')?.textContent;
                if (!fontName) {
                    showMessage('错误', '无法获取选中字体的名称');
                    return;
                }
                
                modal.close();
                
                const progressModal = new ProgressModal('更换字体');
                progressModal.addLog(`开始为汉化包 "${packageName}" 更换字体为 "${fontName}"`);
                
                pywebview.api.export_selected_font(fontName, "")
                    .then(function(result) {
                        if (result.success) {
                            progressModal.complete(true, '字体更换成功');
                        } else {
                            progressModal.complete(false, '字体更换失败: ' + result.message);
                        }
                    })
                    .catch(function(error) {
                        progressModal.complete(false, '更换过程中发生错误: ' + error);
                    });
            };
            
            const footer = document.getElementById(`modal-footer-${modal.id}`);
            footer.innerHTML = '';
            footer.appendChild(confirmBtn);
            
            const cancelBtn = document.createElement('button');
            cancelBtn.className = 'action-btn';
            cancelBtn.textContent = '取消';
            cancelBtn.onclick = () => {
                modal.close();
                modal.setCompleted();
            };
            footer.appendChild(cancelBtn);
        })
        .catch(function(error) {
            showMessage('错误', '获取系统字体列表时发生错误: ' + error);
        });
}

function getFontFromInstalled() {
    pywebview.api.get_system_fonts_list()
        .then(function(result) {
            const modal = new ModalWindow('导出系统字体', {
                showProgress: false,
                showCancelButton: true,
                cancelButtonText: '关闭',
                showMinimizeButton: true,
                showLog: false
            });
            
            let modalContent = `
                <div class="font-selector">
                    <div class="form-group">
                        <label for="font-search-${modal.id}">搜索字体:</label>
                        <input type="text" id="font-search-${modal.id}" placeholder="输入字体名称搜索..." style="width: 100%;">
                    </div>
                    <div class="form-group">
                        <label>系统字体:</label>
                        <div class="list-container" style="max-height: 200px; overflow-y: auto;">
                            <div id="font-list-${modal.id}" style="width: 100%; padding: 10px;">
            `;
            
            if (result.success && result.fonts && result.fonts.length > 0) {
                modalContent += '<div class="list-empty"><p>加载中...</p></div>';
            } else {
                modalContent += '<div class="list-empty"><p>未找到系统字体</p></div>';
            }
            
            modalContent += `
                            </div>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>预览:</label>
                        <div id="font-preview-${modal.id}" style="border: 1px solid var(--color-border); padding: 10px; min-height: 60px; background-color: var(--color-bg-input); border-radius: var(--radius-md);">
                            选择字体以预览
                        </div>
                    </div>
                </div>
            `;
            
            modal.element.querySelector('.modal-body').innerHTML = modalContent;
            
            if (result.success && result.fonts && result.fonts.length > 0) {
                const fontList = document.getElementById(`font-list-${modal.id}`);
                fontList.innerHTML = '';
                
                result.fonts.forEach(font => {
                    const fontItem = document.createElement('div');
                    fontItem.className = 'list-item';
                    fontItem.innerHTML = `
                        <div class="list-item-content">
                            <i class="fas fa-font"></i>
                            <span>${font}</span>
                        </div>
                    `;
                    fontItem.addEventListener('click', () => {
                        document.querySelectorAll(`#font-list-${modal.id} .list-item`).forEach(item => {
                            item.classList.remove('selected');
                        });
                        fontItem.classList.add('selected');
                        
                        const previewDiv = document.getElementById(`font-preview-${modal.id}`);
                        previewDiv.innerHTML = `
                            <div style="font-family: '${font}'; font-size: 16px; margin-bottom: 8px;">
                                字体预览: ${font}
                            </div>
                            <div style="font-family: '${font}';">
                                The quick brown fox jumps over the lazy dog.<br>
                                0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ<br>
                                abcdefghijklmnopqrstuvwxyz<br>
                                中文示例文本
                            </div>
                        `;
                    });
                    fontList.appendChild(fontItem);
                });
                
                const searchInput = document.getElementById(`font-search-${modal.id}`);
                searchInput.addEventListener('input', function() {
                    const searchTerm = searchInput.value.toLowerCase();
                    const items = fontList.querySelectorAll('.list-item');
                    
                    items.forEach(item => {
                        const fontName = item.querySelector('span')?.textContent?.toLowerCase() || '';
                        if (fontName.includes(searchTerm)) {
                            item.style.display = 'flex';
                        } else {
                            item.style.display = 'none';
                        }
                    });
                });
            }
            
            const exportBtn = document.createElement('button');
            exportBtn.className = 'primary-btn';
            exportBtn.innerHTML = '<i class="fas fa-file-export"></i> 导出';
            exportBtn.onclick = function() {
                const selectedFontItem = document.querySelector(`#font-list-${modal.id} .list-item.selected`);
                if (!selectedFontItem) {
                    showMessage('提示', '请先选择一个字体');
                    return;
                }
                
                const fontName = selectedFontItem.querySelector('span')?.textContent;
                if (!fontName) {
                    showMessage('错误', '无法获取选中字体的名称');
                    return;
                }
                
                pywebview.api.browse_folder('font-export-path')
                    .then(function(result) {
                        if (result && result.length > 0) {
                            const exportPath = result[0];
                            
                            modal.close();
                            
                            const progressModal = new ProgressModal('导出字体');
                            progressModal.addLog(`开始导出字体 "${fontName}" 到 "${exportPath}"`);
                            
                            pywebview.api.export_selected_font(fontName, exportPath)
                                .then(function(result) {
                                    if (result.success) {
                                        progressModal.complete(true, '字体导出成功');
                                    } else {
                                        progressModal.complete(false, '字体导出失败: ' + result.message);
                                    }
                                })
                                .catch(function(error) {
                                    progressModal.complete(false, '导出过程中发生错误: ' + error);
                                });
                        }
                    })
                    .catch(function(error) {
                        showMessage('错误', '选择导出路径时发生错误: ' + error);
                    });
            };
            
            const footer = document.getElementById(`modal-footer-${modal.id}`);
            footer.innerHTML = '';
            footer.appendChild(exportBtn);
            
            const cancelBtn = document.createElement('button');
            cancelBtn.className = 'action-btn';
            cancelBtn.textContent = '取消';
            cancelBtn.onclick = () => {
                modal.close();
                modal.setCompleted();
            };
            footer.appendChild(cancelBtn);
        })
        .catch(function(error) {
            showMessage('错误', '获取系统字体列表时发生错误: ' + error);
        });
}

// 创建汉化包列表管理器实例
let installedPackageItemManager = new ItemListManager('installed-package-list', {
    emptyMessage: '未找到已安装汉化包',
    itemIcon: 'fa-box',
    onSelect: (item) => {
        addLogMessage(`已选中汉化包: ${item}`, 'info');
    }
});

/**
 * 刷新已安装汉化包列表
 * 从后端获取数据后调用管理器的 setItems 和 updateList 进行渲染
 */
function refreshInstalledPackageList() {
    const packageList = document.getElementById('installed-package-list');
    if (!packageList) return;

    // 显示加载状态
    installedPackageItemManager.waitList();

    pywebview.api.get_installed_packages()
        .then(function(result) {
            const box = document.getElementById('enable-lang');
            if (result.success && result.enable && result.packages && result.packages.length > 0) {
                // 设置数据并更新列表
                box.checked=true;
                installedPackageItemManager.setItems(result.packages);
                if (result.selected) {
                    installedPackageItemManager.setSelectedItem(result.selected);
                };
            } else {
                // 空列表也会自动显示 emptyMessage
                installedPackageItemManager.setItems([]);
                if (result.success) {
                    box.checked=false;
                }
            }
        })
        .catch(function(error) {
            console.error('获取汉化包列表失败:', error);
            installedPackageItemManager.showErrorList(error);
        });
}

/**
 * 使用选中的汉化包
 */
function useSelectedPackage() {
    const packageName = installedPackageItemManager.getSelectedItem();
    if (!packageName) {
        showMessage('提示', '请先选择一个汉化包');
        return;
    }

    const modal = new ProgressModal('使用选中汉化包');
    modal.addLog(`开始切换汉化包: ${packageName}`);

    pywebview.api.use_translation(packageName, modal.id)
        .then(function(result) {
            if (result.success) {
                modal.complete(true, '汉化包切换成功');

                setTimeout(
                    ()=>{modal.close()}, 300
                )
            } else {
                modal.complete(false, '切换失败: ' + result.message);
            }
        })
        .catch(function(error) {
            modal.complete(false, '切换过程中发生错误: ' + error);
        });
}

/**
 * 删除选中的汉化包
 */
function deleteInstalledPackage() {
    const packageName = installedPackageItemManager.getSelectedItem();
    if (!packageName) {
        showMessage('提示', '请先选择一个汉化包');
        return;
    }

    showConfirm('确认删除', `确定要删除汉化包 "${packageName}" 吗？此操作不可撤销。`,
        function() {
            pywebview.api.delete_installed_package(packageName)
                .then(function(result) {
                    if (result.success) {
                        // 从管理器中移除该项，自动更新列表并清空选中状态
                        packageItemManager.removeItem(packageName);
                        showMessage('删除成功', `汉化包 "${packageName}" 已被删除`);
                    } else {
                        showMessage('删除失败', `删除汉化包失败: ${result.message}`);
                    }
                })
                .catch(function(error) {
                    showMessage('删除失败', `删除过程中发生错误: ${error}`);
                });
        },
        function() {
            // 取消删除，无操作
        }
    );
}

function fetchProperNouns() {
    const outputFormat = document.getElementById('proper-output').value;
    const skipSpace = document.getElementById('proper-skip-space').checked;
    const maxCount = document.getElementById('proper-max-count').value;
    const minCount = document.getElementById('proper-min-count').value;
    const joinChar = document.getElementById('proper-join-char').value;
    
    const updates = {
        'proper-join-char': joinChar,
        'proper-max-lenth': maxCount,
        'proper-min-lenth': minCount,
        'proper-output-type': outputFormat,
        'proper-disable-space': skipSpace
    };

    const modal = new ProgressModal('抓取专有词汇');
    modal.addLog('开始抓取专有词汇...');
    modal.addLog(`输出格式: ${outputFormat}`);
    modal.addLog(`跳过含空格词汇: ${skipSpace ? '是' : '否'}`);
    modal.addLog(`最短长度: ${minCount}`);
    if (maxCount) {
        modal.addLog(`最大词汇数量: ${maxCount}`);
    }
    if (outputFormat === 'single') {
        modal.addLog(`文本分割符：${joinChar}`);
    }
    
    configManager.updateConfigValues(updates)
        .then(() => {
            pywebview.api.fetch_proper_nouns(modal.id)
                .then(function(result) {
                    if (result.success) {
                        modal.complete(true, '专有词汇抓取成功');
                    } else {
                        modal.complete(false, '抓取失败: ' + result.message);
                    }
                })
                .catch(function(error) {
                    modal.complete(false, '抓取过程中发生错误: ' + error);
                });
        })
}

function downloadOurplay() {
    const fontOption = document.getElementById('ourplay-font-option').value;
    const checkHash = document.getElementById('ourplay-check-hash').checked;
    const useApi = document.getElementById('ourplay-use-api').checked;
    
    const modal = new ProgressModal('下载OurPlay汉化包');
    modal.addLog('开始下载OurPlay汉化包...');
    modal.addLog(`字体选项: ${fontOption}`);
    modal.addLog(`哈希校验: ${checkHash ? '启用' : '禁用'}`);
    modal.addLog(`使用API: ${useApi ? '启用' : '禁用'}`);
    
    // 批量更新配置
    const updates = {
        'ourplay-font-option': fontOption,
        'ourplay-check-hash': checkHash,
        'ourplay-use-api': useApi
    };
    
    configManager.updateConfigValues(updates)
        .then(() => {
            pywebview.api.download_ourplay_translation(modal.id).then(function(result) {
                if (result.success) {
                    modal.complete(true, 'OurPlay汉化包下载成功');
                } else {
                    if (result.message === "已取消") {
                        modal.cancel();
                    } else {
                        modal.complete(false, '下载失败: ' + result.message);
                    }
                }
            }).catch(function(error) {
                modal.complete(false, '下载过程中发生错误: ' + error);
            });
        });
}

async function downloadBubble() {
    const modal = new ProgressModal('开始下载');
    modal.setStatus('正在初始化...');
    modal.addLog('开始下载任务');
    await configManager.updateConfigValues(configManager.collectConfigFromUI());
    
    pywebview.api.download_bubble(
        modal.id).then(function(result) {
        if (result.success) {
            modal.complete(true, '下载任务已完成');
        } else {
            modal.complete(false, '下载失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '下载过程中发生错误: ' + error);
    });
}

function cleanCache() {
    const modal = new ProgressModal('清除缓存');
    
    // 获取清理选项
    const cleanProgress = document.getElementById('clean-progress').checked;
    const cleanNotice = document.getElementById('clean-notice').checked;
    const cleanMods = document.getElementById('clean-mods').checked;
    
    // 获取自定义文件列表
    const customFilesList = [];
    const customFilesContainer = document.getElementById('custom-files-list');
    if (customFilesContainer) {
        // 从列表项中获取文件路径
        const fileItems = customFilesContainer.querySelectorAll('.file-item');
        fileItems.forEach(item => {
            const filePath = item.querySelector('.file-path').textContent;
            if (filePath) {
                customFilesList.push(filePath);
            }
        });
    }
    
    // 使用配置管理器批量更新配置
    const updates = {
        'clean-progress': cleanProgress,
        'clean-notice': cleanNotice,
        'clean-mods': cleanMods
    };
    
    // 保存清理配置并执行清理
    configManager.updateConfigValues(updates)
        .then(() => {
            // 配置保存成功后执行清理操作
            pywebview.api.clean_cache(modal.id, customFilesList, cleanProgress, cleanNotice, cleanMods).then(function(result) {
                if (result.success) {
                    modal.complete(true, '缓存清除成功');
                } else {
                    if (result.message === '已取消') {
                        modal.complete(null, '操作已取消');
                    } else {
                        modal.complete(false, '清除失败: ' + result.message);
                    }
                }
            }).catch(function(error) {
                modal.complete(false, '清除过程中发生错误: ' + error);
            });
        })
        .catch(function(error) {
            console.error('保存清理配置时发生错误:', error);
            modal.complete(false, '保存配置失败: ' + error);
        });
}

// 添加自定义清理文件/文件夹
function addCustomFile() {
    const filePathInput = document.getElementById('custom-file-path');
    if (filePathInput && filePathInput.value.trim()) {
        const filePath = filePathInput.value.trim();
        const customFilesContainer = document.getElementById('custom-files-list');
        
        // 检查文件路径是否已存在
        const existingItems = customFilesContainer.querySelectorAll('.file-path');
        let exists = false;
        existingItems.forEach(item => {
            if (item.textContent === filePath) {
                exists = true;
            }
        });
        
        if (exists) {
            showMessage('提示', '该文件路径已存在列表中');
            return;
        }
        
        // 创建列表项
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.innerHTML = `
            <div class="file-info">
                <i class="fas fa-file"></i>
                <span class="file-path">${filePath}</span>
            </div>
            <button class="action-btn small" onclick="removeCustomFile(this)">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        customFilesContainer.appendChild(fileItem);
        filePathInput.value = '';
        
        // 更新配置
        updateCustomFilesConfig();
    }
}

// 移除自定义清理文件
function removeCustomFile(element) {
    const fileItem = element.closest('.file-item');
    if (fileItem) {
        fileItem.remove();
        updateCustomFilesConfig();
    }
}

// 更新自定义文件配置
function updateCustomFilesConfig() {
    const customFilesList = [];
    const customFilesContainer = document.getElementById('custom-files-list');
    if (customFilesContainer) {
        const fileItems = customFilesContainer.querySelectorAll('.file-item');
        fileItems.forEach(item => {
            const filePath = item.querySelector('.file-path').textContent;
            if (filePath) {
                customFilesList.push(filePath);
            }
        });
    }
    
    // 更新配置
    configManager.updateConfigValue('custom-files', customFilesList);
}

// 添加浏览文件到自定义清理列表
function browseCustomFile() {
    pywebview.api.browse_file('custom-file-path');
}

// 添加浏览文件夹到自定义清理列表
function browseCustomFolder() {
    pywebview.api.browse_folder('custom-file-path');
}

// 清空自定义文件列表
function clearCustomFilesList() {
    const customFilesContainer = document.getElementById('custom-files-list');
    if (customFilesContainer) {
        customFilesContainer.innerHTML = '';
        updateCustomFilesConfig();
    }
}

function downloadLLC() {
    const zipType = document.getElementById('llc-zip-type').value;
    const useProxy = document.getElementById('llc-use-proxy').checked;
    const useCache = document.getElementById('llc-use-cache').checked;
    const dumpDefault = document.getElementById('llc-dump-default').checked;
    const download_source = document.getElementById('llc-download-source').value;
    
    // 批量更新配置
    const updates = {
        'llc-zip-type': zipType,
        'llc-use-proxy': useProxy,
        'llc-use-cache': useCache,
        'llc-dump-default': dumpDefault,
        'llc-download-source': download_source
    };
    
    configManager.updateConfigValues(updates)
        .then(() => {
            const modal = new ProgressModal('下载零协汉化包');
            modal.addLog('开始下载零协汉化包...');
            modal.addLog(`压缩格式: ${zipType}`);
            modal.addLog(`使用代理: ${useProxy ? '是' : '否'}`);
            modal.addLog(`使用缓存: ${useCache ? '是' : '否'}`);
            modal.addLog(`导出默认配置: ${dumpDefault ? '是' : '否'}`);
            modal.addLog(`下载源: ${download_source}`);
            
            pywebview.api.download_llc_translation(modal.id).then(function(result) {
                if (result.success) {
                    modal.complete(true, '零协汉化包下载成功');
                } else {
                    if (result.message === "已取消") {
                        modal.cancel();
                    } else {
                        modal.complete(false, '下载失败: ' + result.message);
                    }
                }
            }).catch(function(error) {
                modal.complete(false, '下载过程中发生错误: ' + error);
            });
        });
}

async function downloadMachine() {
    const modal = new ProgressModal('开始下载');
    modal.setStatus('正在初始化下载过程...');
    modal.addLog('开始下载任务');
    await configManager.updateConfigValues(configManager.collectConfigFromUI());
    
    pywebview.api.download_LCTA_auto(modal.id).then(function(result) {
        if (result.success) {
            modal.complete(true, '下载任务已完成');
        } else {
            modal.complete(false, '下载失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '下载过程中发生错误: ' + error);
    });
}

// ================================
// 配置管理函数
// ================================

// 保存设置
function saveSettings() {
    const modal = new ProgressModal('保存设置');
    modal.addLog('正在保存设置...');
    
    if (!configManager) {
        modal.complete(false, '配置管理器未初始化');
        return;
    }
    
    // 收集所有配置更新
    const updates = configManager.collectConfigFromUI();
    
    if (Object.keys(updates).length === 0) {
        modal.complete(true, '没有需要保存的更改');
        configManager.flushPendingUpdates();
        setTimeout(
            () => {
                modal.close();
            }, 500
        );
        return;
    }
    
    // 批量更新配置
    configManager.updateConfigValues(updates)
        .then(function(result) {
            if (result.success) {
                // 确保所有待更新都已刷新
                configManager.flushPendingUpdates()
                    .then(() => {
                        modal.complete(true, '设置保存成功');
                        pywebview.api.save_config_to_file();
                        setTimeout(
                            () => {
                            modal.close();
                        }, 500
                        )
                    });
            } else {
                modal.complete(false, '保存失败: ' + result.message);
            }
        })
        .catch(function(error) {
            modal.complete(false, '保存过程中发生错误: ' + error);
        });
}

function useDefaultConfig() {
    const modal = new ProgressModal('使用默认配置');
    modal.addLog('正在重置为默认配置...');
    
    pywebview.api.use_default_config()
        .then(function(result) {
            if (result.success) {
                modal.complete(true, '已使用默认配置');
                // 重新加载配置
                if (configManager) {
                    configManager.applyConfigToUI();
                }
                setTimeout(function() {
                    modal.close();
                }, 1000)
            } else {
                modal.complete(false, '配置重置失败: ' + result.message);
            }
        })
        .catch(function(error) {
            modal.complete(false, '重置过程中发生错误: ' + error);
        });
}

function resetConfig() {
    showConfirm(
        "确认重置",
        "确定要重置所有配置吗？这将删除当前配置并恢复为默认设置。",
        function() {
            const modal = new ProgressModal('重置配置');
            modal.addLog('正在重置配置...');
            
            pywebview.api.reset_config()
                .then(function(result) {
                    if (result.success) {
                        // 重新加载配置
                        if (configManager) {
                            configManager.applyConfigToUI();
                            modal.complete(true, '配置已重置');
                            setTimeout(function() {
                                modal.close();
                            }, 1000)
                        }
                    } else {
                        modal.complete(false, '配置重置失败: ' + result.message);
                    }
                })
                .catch(function(error) {
                    modal.complete(false, '重置过程中发生错误: ' + error);
                });
        },
        function() {
            // 取消操作
        }
    );
}

function manualCheckUpdates() {
    const modal = new ProgressModal('检查更新');
    modal.addLog('正在检查是否有可用更新...');
    
    pywebview.api.manual_check_update()
        .then(function(result) {
            if (result.has_update) {
                modal.complete(true, `发现新版本 ${result.latest_version}，请前往GitHub下载更新`);
                setTimeout(() => {
                    if (!modal.isMinimized) {
                        modal.close();
                        showUpdateInfo(result);
                    }
                }, 2000);
            } else {
                modal.complete(true, '当前已是最新版本');
                setTimeout(() => {
                    if (!modal.isMinimized) {
                        modal.close();
                    }
                }, 2000);
            }
        })
        .catch(function(error) {
            modal.complete(false, '检查更新时发生错误: ' + error);
            setTimeout(() => {
                if (!modal.isMinimized) {
                    modal.close();
                }
            }, 3000);
        });
}

// 自动检查更新函数（仅在有更新时显示窗口）
function autoCheckUpdates() {
    pywebview.api.manual_check_update()
        .then(function(result) {
            if (result.has_update) {
                showUpdateInfo(result);
            }
        })
        .catch(function(error) {
            addLogMessage('自动检查更新时发生错误: ' + error, 'error');
        });
}

// 更新进度条函数
function updateProgress(percent, text) {
    const progressFill = document.getElementById('progress-fill');
    const progressPercent = document.getElementById('progress-percent');
    const progressText = document.getElementById('progress-text');
    const progressContainer = document.getElementById('translation-progress');
    
    if (progressFill) {
        progressFill.style.width = percent + '%';
    }
    
    if (progressPercent) {
        progressPercent.textContent = percent + '%';
    }
    
    if (progressText && text) {
        progressText.textContent = text;
    }
    
    if (progressContainer) {
        progressContainer.style.display = 'block';
    }
}

// 添加日志消息
function addLogMessage(message, level = 'info') {
    const logDisplay = document.getElementById('log-display');
    if (logDisplay) {
        const now = new Date();
        const timestamp = `[${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}]`;
        
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${level}`;
        logEntry.innerHTML = `
            <div class="log-timestamp">${timestamp}</div>
            <div class="log-level">[${level.toUpperCase()}]</div>
            <div class="log-message">${message}</div>
        `;
        
        logDisplay.appendChild(logEntry);
        logDisplay.scrollTop = logDisplay.scrollHeight;
    };
    if (window.apiReady) {
        pywebview.api.log(message).catch(
            function(error) { console.log(error); })
    };
}

// 简单Markdown转HTML
function simpleMarkdownToHtml(text) {
    const html = marked.parse(text);
    return html;
}

// 添加一个变量来跟踪是否已经显示了更新窗口
let updateModalShown = false;

// 显示更新信息
function showUpdateInfo(update_info) {
    if (updateModalShown) {
        return;
    }
    
    updateModalShown = true;
    
    let htmlMessage = `<p><strong>发现新版本:</strong> ${update_info.latest_version}</p>`;
    htmlMessage += `<p><strong>当前版本:</strong> v4.0.8</p>`;
    
    if (update_info.title) {
        htmlMessage += `<p><strong>发布标题:</strong> ${update_info.title}</p>`;
    }
    
    if (update_info.body) {
        let body = update_info.body.trim();
        const bodyHtml = simpleMarkdownToHtml(body);
        htmlMessage += `<div><strong>更新详情:</strong></div>`;
        htmlMessage += `<div class="markdown-body" id="update-markdown">${bodyHtml}</div>`;
    }
    
    if (update_info.published_at) {
        const publishDate = new Date(update_info.published_at);
        htmlMessage += `<p><strong>发布时间:</strong> ${publishDate.toLocaleDateString('zh-CN')}</p>`;
    }
    
    if (update_info.html_url) {
        htmlMessage += `<p><strong>发布页面:</strong> <a href="${update_info.html_url}" target="_blank" style="color: var(--color-primary); text-decoration: underline;">点击这里在浏览器中查看</a></p>`;
    }
    
    const modal = showConfirm(
        '发现新版本',
        '',
        function() {
            this.close();
            const progressModal = new ProgressModal('更新程序');
            progressModal.addLog('开始下载并安装更新...');
            pywebview.api.perform_update_in_modal(progressModal.id)
                .then(function(result) {
                    if (!result) {
                        progressModal.addLog('更新失败');
                        progressModal.complete(false, '更新失败');
                        return;
                    }
                    progressModal.addLog('更新完成');
                    progressModal.addLog('正在重新启动程序...');
                    progressModal.complete(true, '更新完成');
                })
                .catch(function(error) {
                    progressModal.addLog('更新失败: ' + error);
                    progressModal.complete(false, '更新失败');
                });
        },
        function() {
            addLogMessage('用户取消了更新');
            updateModalShown = false;
        }
    );
    
    const originalClose = modal.close;
    modal.close = function() {
        updateModalShown = false;
        originalClose.call(this);
    };
    
    setTimeout(() => {
        const statusElement = document.getElementById(`modal-status-${modal.id}`);
        if (statusElement) {
            statusElement.innerHTML = htmlMessage;
        }
    }, 100);
}

// 初始化函数
function init() {
    // 初始化配置管理器
    configManager = new ConfigManager();
    
    // 初始化主题管理器
    themeManager = new ThemeManager();
    
    // 初始化导航
    initNavigation();
    
    // 初始化密码切换
    initPasswordToggles();
    
    // 添加初始日志
    addLogMessage('系统已启动，准备就绪');
    addLogMessage('当前主题: ' + themeManager.currentTheme);
    addLogMessage('WebUI 初始化完成');
    
    // 创建遮罩层
    createConnectionMask();
}

// 创建连接遮罩层
function createConnectionMask() {
    const mask = document.createElement('div');
    mask.id = 'connection-mask';
    mask.className = 'connection-mask';
    
    mask.innerHTML = `
        <div class="mask-content">
            <div class="spinner"></div>
            <div class="mask-text">正在连接到API...</div>
        </div>
    `;
    
    document.body.appendChild(mask);
    
    const statusIndicator = document.querySelector('.status-indicator');
    if (statusIndicator) {
        const statusDot = statusIndicator.querySelector('.status-dot');
        const statusText = statusIndicator.querySelector('span');
        
        if (statusDot) {
            statusDot.className = 'status-dot connecting';
        }
        
        if (statusText) {
            statusText.textContent = '连接中';
        }
    }
}

// 移除连接遮罩层
function removeConnectionMask() {
    const mask = document.getElementById('connection-mask');
    if (mask) {
        mask.style.opacity = '0';
        setTimeout(() => {
            if (mask.parentNode) {
                mask.parentNode.removeChild(mask);
            }
        }, 300);
    }
    
    const statusIndicator = document.querySelector('.status-indicator');
    if (statusIndicator) {
        const statusDot = statusIndicator.querySelector('.status-dot');
        const statusText = statusIndicator.querySelector('span');
        
        if (statusDot) {
            statusDot.className = 'status-dot connected';
        }
        
        if (statusText) {
            statusText.textContent = '已连接';
        }
    }
}

async function showFirstUseWindows() {

    const modal = showMessage('欢迎使用LCTA', '正在加载数据内容')

    const response = await fetch('assets/firstUse.md');

    let markdownText
    
    if (!response.ok) {
        markdownText = `加载 使用须知 失败: ${response.status} ${response.statusText}`;
    } else {
        markdownText = await response.text();
    };
    
    const bodyHtml = simpleMarkdownToHtml(markdownText);
    const showing = `<div class="markdown-body" id="update-markdown">${bodyHtml}</div>`

    setTimeout(() => {
        const statusElement = document.getElementById(`modal-status-${modal.id}`);
        if (statusElement) {
            statusElement.innerHTML = showing;
        }
    }, 100);
}

function setupGlobalErrorHandling() {
    window.preApiErrors = [];
    window.preApiRejections = [];
    window.apiReady = false;
    
    window.addEventListener('error', function(event) {
        const errorMessage = `[全局错误] ${event.message} at ${event.filename}:${event.lineno}:${event.colno}`;
        const stack = event.error && event.error.stack ? event.error.stack : '无堆栈信息';
        
        addLogMessage(errorMessage, 'error');
        addLogMessage(stack, 'error');
        console.log('已捕捉到异常',errorMessage);
        
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.log && window.apiReady) {
            pywebview.api.log(`[前端错误] ${errorMessage}\n堆栈: ${stack}`)
                .catch(function(error) {
                    console.error('无法将错误发送到后端:', error);
                });
        } else {
            window.preApiErrors.push({
                message: errorMessage,
                stack: stack,
                timestamp: new Date().toISOString()
            });
        }
    });
    
    window.addEventListener('unhandledrejection', function(event) {
        const errorMessage = `[未处理的Promise拒绝] ${event.reason}`;
        
        addLogMessage(errorMessage, 'error');
        console.log('已捕捉到异常',errorMessage);
        
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.log && window.apiReady) {
            pywebview.api.log(`[前端Promise错误] ${errorMessage}`)
                .catch(function(error) {
                    console.error('无法将Promise错误发送到后端:', error);
                });
        } else {
            window.preApiRejections.push({
                message: errorMessage,
                timestamp: new Date().toISOString()
            });
        }
    });
}

function checkGamePath() {
    const gamePath = configManager.getCachedValue('game_path');
    if (!gamePath) {
        pywebview.api.run_func('find_lcb')
            .then(function(foundPath) {
                if (foundPath) {
                    confirmGamePath(foundPath);
                } else {
                    requestGamePath();
                };
                configManager.applyConfigToUI();
            })
            .catch(function(error) {
                addLogMessage('检查游戏路径时发生错误: ' + error, 'error');
            });
    }
}

// 添加确认游戏路径的函数
function confirmGamePath(foundPath) {
    showConfirm(
        "确认游戏路径",
        `这是否是你的游戏路径：\n${foundPath}\n是否使用此路径？`,
        function() {
            configManager.updateConfigValue('game-path', foundPath)
                .then(function(success) {
                    if (success) {
                        configManager.flushPendingUpdates();
                        addLogMessage('游戏路径已确认并保存: ' + foundPath, 'success');
                    } else {
                        addLogMessage('保存游戏路径时出错', 'error');
                    }
                })
                .catch(function(error) {
                    addLogMessage('设置游戏路径时发生错误: ' + error, 'error');
                });
            pywebview.api.save_config_to_file();
        },
        function() {
            requestGamePath();
        }
    );
}

// 添加请求用户手动选择游戏路径的函数
function requestGamePath() {
    showMessage(
        "选择游戏路径", 
        "请手动选择游戏的安装目录（包含LimbusCompany.exe的文件夹）",
        function() {
            browseFolder('game-path');
        }
    );
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    init();
    setupGlobalErrorHandling();
    loadAndRenderMarkdown();
});

// 与后端通信的初始化
window.addEventListener('pywebviewready', function() {
    window.apiReady = true;
    
    addLogMessage('PyWebview API 已准备就绪', 'success');
    
    if (window.preApiErrors && window.preApiErrors.length > 0) {
        addLogMessage(`正在发送 ${window.preApiErrors.length} 条之前捕获的错误信息...`, 'info');
        
        window.preApiErrors.forEach(function(error) {
            pywebview.api.log(`[前端错误][延迟发送] ${error.message}\n堆栈: ${error.stack}`)
                .catch(function(sendError) {
                    console.error('无法将延迟错误发送到后端:', sendError);
                });
        });
        
        window.preApiErrors = [];
    }
    
    if (window.preApiRejections && window.preApiRejections.length > 0) {
        addLogMessage(`正在发送 ${window.preApiRejections.length} 条之前捕获的Promise拒绝信息...`, 'info');
        
        window.preApiRejections.forEach(function(rejection) {
            pywebview.api.log(`[前端Promise错误][延迟发送] ${rejection.message}`)
                .catch(function(sendError) {
                    console.error('无法将延迟Promise错误发送到后端:', sendError);
                });
        });
        
        window.preApiRejections = [];
    }
    
    removeConnectionMask();
    
    pywebview.api.get_attr('message_config')
        .then(function(message_config) {
            if (message_config && Array.isArray(message_config) && message_config.length === 2) {
            showMessage(message_config[0], message_config[1]);
            }
        });

    let first_use
    pywebview.api.get_attr('first_use').then(
        function(result) {
            first_use = result
            if (result) {
                showFirstUseWindows();
            }
        }
    );

    pywebview.api.run_func('change_icon').catch(
        function(error) {
            console.log(error)
        }
    );

    pywebview.api.init_cache().catch(
        function(error) {
            console.log(error)
        }
    );

    pywebview.api.set_attr('http_port', window.location.port);
    
    pywebview.api.get_attr('config_ok')
        .then(function(config_ok) {
            if (config_ok === false) {
                pywebview.api.get_attr('config_error')
                    .then(function(config_error) {
                        let errorMessage = "配置项格式错误，尝试修复?\n失败将会使用默认配置";
                        if (config_error && Array.isArray(config_error) && config_error.length > 0) {
                            errorMessage += "\n\n详细错误信息:\n" + config_error.join("\n");
                        }

                        addLogMessage(errorMessage);

                        {
                            pywebview.api.get_attr("config")
                                .then(function(config) {
                                    return pywebview.api.run_func('fix_config', config);
                                })
                                .then(function(fixed_config) {
                                    return pywebview.api.set_attr("config", fixed_config);
                                })
                                .then(function() {
                                    return pywebview.api.use_inner();
                                })
                                .catch(function(error) {
                                    showMessage("错误", "修复配置时出错，使用默认配置: " + error);
                                    pywebview.api.use_default()
                                    .then(function() {
                                    })
                                    .catch(function(error) {
                                        showMessage("错误", "使用默认配置时出错: " + error);
                                    });
                                });
                        }
                    })
            }
            })
            .catch(function(error) {
                addLogMessage('检查配置时出错: ' + error, 'error');
            });
    
    pywebview.api.get_attr('config')
        .then(function(config) {
            console.log('配置已加载到前端:', config);
            window.config = config;
            
            // 初始化配置管理器的缓存
            if (configManager) {
                // 递归函数，用于将配置对象扁平化并设置到缓存中
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
                
                // 将后端配置数据填充到缓存
                setConfigToCache(config);
                
                // 应用配置到UI
                configManager.applyConfigToUI().then(function() {
                    toggleCachePathInput();
                    toggleStoragePathInput();
                    toggleDevelopSettings();
                    toggleCustomLangGui();
                    toggleAutoProper();
                    toggleSteamCommand();
                    toggleEnableScreen()
                })
            }
            checkGamePath();
            
            const autoCheckUpdate = configManager.getCachedValue('auto_check_update');
            pywebview.api.init_github()
                .then(function() {
                if (autoCheckUpdate && !first_use) {
                    autoCheckUpdates();
                    }
                }
            );

            const current_theme = configManager.getCachedValue('theme') || 'light';
            themeManager.setTheme(current_theme, true);

            apiConfigManager = new APIConfigManager();
            apiConfigManager.init().then(success => {
                if (success) {
                    apiConfigManager.loadAPIServices();
                    let current_select_api = configManager.getCachedValue('ui_default.api_config.key')
                    if (!current_select_api) {
                        current_select_api = Object.keys(apiConfigManager.apiServices)[0];
                    }
                    // 获取选择框元素
                    const selectBox = document.querySelector('.api-service-select');

                    if (selectBox) {
                        selectBox.value = current_select_api;
                        
                        const changeEvent = new Event('change', {
                            bubbles: true,
                            cancelable: true
                        });
                        
                        selectBox.dispatchEvent(changeEvent);
                    };

                    apiConfigManager.loadAPIServicesTranslator();

                    let current_select_translator = configManager.getCachedValue('ui_default.translator.translator')
                    if (!current_select_translator) {
                        current_select_translator = Object.keys(apiConfigManager.apiServices)[0];
                    }
                    // 获取选择框元素
                    const selectBoxtranslator = document.querySelector('.translator-service-select');

                    if (selectBoxtranslator) {
                        selectBoxtranslator.value = current_select_translator;
                        
                        const changeEvent = new Event('change', {
                            bubbles: true,
                            cancelable: true
                        });
                        
                        selectBoxtranslator.dispatchEvent(changeEvent);
                    };
                }
            });
        });
});