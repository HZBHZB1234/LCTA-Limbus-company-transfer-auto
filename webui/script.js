// 主题管理
class ThemeManager {
    constructor() {
        this.currentTheme = localStorage.getItem('lcta-theme') || 'light';
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
        localStorage.setItem('lcta-theme', theme);
        
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
            'update-only-stable': 'update_only_stable',
            
            // 安装设置
            'install-package-directory': 'ui_default.install.package_directory',
            'package-directory': 'ui_default.install.package_directory',
            
            // OurPlay设置
            'ourplay-font-option': 'ui_default.ourplay.font_option',
            'ourplay-check-hash': 'ui_default.ourplay.check_hash',
            
            // 零协设置
            'llc-zip-type': 'ui_default.zero.zip_type',
            'llc-download-source': 'ui_default.zero.download_source',
            'llc-use-proxy': 'ui_default.zero.use_proxy',
            'llc-use-cache': 'ui_default.zero.use_cache',
            'llc-dump-default': 'ui_default.zero.dump_default',
            
            // 清理设置
            'clean-progress': 'ui_default.clean.clean_progress',
            'clean-notice': 'ui_default.clean.clean_notice',
            'clean-mods': 'ui_default.clean.clean_mods',

            // 抓取设置
            'proper-join-char': 'ui_default.proper.join_char',
            'proper-disable-space': 'ui_default.proper.disable_space',
            'proper-max_length': 'ui_default.proper.max_length',
            'proper-output-type': 'ui_default.proper.output_type',
            
            // Launcher设置
            'launcher-zero-zip-type': 'launcher.zero.zip_type',
            'launcher-zero-download-source': 'launcher.zero.download_source',
            'launcher-zero-use-proxy': 'launcher.zero.use_proxy',
            'launcher-zero-use-cache': 'launcher.zero.use_cache',
            'launcher-ourplay-font-option': 'launcher.ourplay.font_option',
            'launcher-ourplay-use-api': 'launcher.ourplay.use_api',
            'launcher-work-update': 'launcher.work.update',
            'launcher-work-mod': 'launcher.work.mod'
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
                    
                    if (sectionId === 'settings-section') {
                        loadSettings();
                    }
                    
                    if (sectionId === 'log-section') {
                        scrollLogToBottom();
                    }
                    
                    if (sectionId === 'install-section') {
                        refreshInstallPackageList();
                    }
                    
                    if (sectionId === 'launcher-config-section') {
                        applyLauncherConfigToUI();
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

// 复选框逻辑
function initCheckboxes() {
    document.getElementById('custom-script')?.addEventListener('change', function() {
        const group = document.getElementById('script-path-group');
        if (group) {
            if (this.checked) {
                AnimationManager.fadeIn(group);
            } else {
                AnimationManager.fadeOut(group);
            }
        }
    });

    document.getElementById('half-trans')?.addEventListener('change', function() {
        const group = document.getElementById('half-trans-path-group');
        if (group) {
            if (this.checked) {
                AnimationManager.fadeIn(group);
            } else {
                AnimationManager.fadeOut(group);
            }
        }
    });

    document.getElementById('backup')?.addEventListener('change', function() {
        const group = document.getElementById('backup-path-group');
        if (group) {
            if (this.checked) {
                AnimationManager.fadeIn(group);
            } else {
                AnimationManager.fadeOut(group);
            }
        }
    });
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

// 浏览文件函数
function browseFile(inputId) {
    pywebview.api.browse_file(inputId);
}

function browseFolder(inputId) {
    pywebview.api.browse_folder(inputId);
}

// 浏览汉化包目录
function browsePackageDirectory() {
    pywebview.api.browse_folder('package-directory').then(function(result) {
        const packageDirInput = document.getElementById('package-directory');
        if (packageDirInput && result) {
            packageDirInput.value = result;
            configManager.updateConfigValue('package-directory', result);
        }
    }).catch(function(error) {
        showMessage('错误', '浏览文件夹时发生错误: ' + error);
    });
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
function startTranslation() {
    const modal = new ProgressModal('开始翻译');
    modal.setStatus('正在初始化翻译过程...');
    modal.addLog('开始翻译任务');
    
    const progressContainer = document.getElementById('translation-progress');
    progressContainer.style.display = 'block';
    
    pywebview.api.start_translation(modal.id).then(function(result) {
        if (result.success) {
            modal.complete(true, '翻译任务已完成');
        } else {
            modal.complete(false, '翻译失败: ' + result.message);
        }
        
        setTimeout(() => {
            progressContainer.style.display = 'none';
        }, 2000);
    }).catch(function(error) {
        modal.complete(false, '翻译过程中发生错误: ' + error);
        
        setTimeout(() => {
            progressContainer.style.display = 'none';
        }, 2000);
    });
}

function refreshPackageList() {
    const packageList = document.getElementById('install-package-list');
    if (!packageList) return;
    
    packageList.innerHTML = '<div class="loading">正在加载...</div>';
    
    pywebview.api.get_translation_packages()
        .then(function(result) {
            packageList.innerHTML = '';
            
            if (result.success && result.packages && result.packages.length > 0) {
                result.packages.forEach(pkg => {
                    const packageItem = document.createElement('div');
                    packageItem.className = 'list-item';
                    packageItem.innerHTML = `
                        <div class="list-item-content">
                            <i class="fas fa-box"></i>
                            <span>${pkg}</span>
                        </div>
                    `;
                    packageItem.addEventListener('click', () => selectListItem(packageItem));
                    packageList.appendChild(packageItem);
                });
            } else {
                const emptyItem = document.createElement('div');
                emptyItem.className = 'list-empty';
                emptyItem.innerHTML = `
                    <i class="fas fa-box-open"></i>
                    <p>未找到可用的汉化包</p>
                `;
                packageList.appendChild(emptyItem);
            }
        })
        .catch(function(error) {
            packageList.innerHTML = '';
            const errorItem = document.createElement('div');
            errorItem.className = 'list-error';
            errorItem.innerHTML = `
                <i class="fas fa-exclamation-triangle"></i>
                <p>加载汉化包列表失败: ${error}</p>
            `;
            packageList.appendChild(errorItem);
        });
}

// 初始化安装包列表
function initPackageList() {
    refreshPackageList();
}

function refreshInstallPackageList() {
    const packageList = document.getElementById('install-package-list');
    if (!packageList) return;
    
    packageList.innerHTML = `
        <div class="list-empty">
            <i class="fas fa-spinner fa-spin"></i>
            <p>正在加载汉化包列表...</p>
        </div>
    `;
    
    pywebview.api.get_translation_packages()
        .then(function(result) {
            packageList.innerHTML = '';
            
            if (result.success && result.packages && result.packages.length > 0) {
                result.packages.forEach(function(pkg) {
                    const packageItem = document.createElement('div');
                    packageItem.className = 'list-item';
                    packageItem.innerHTML = `
                        <div class="list-item-content">
                            <i class="fas fa-box"></i>
                            <span>${pkg}</span>
                        </div>
                        <div class="list-item-actions">
                            <button class="list-action-btn" title="选择">
                                <i class="fas fa-check"></i>
                            </button>
                        </div>
                    `;
                    
                    const selectButton = packageItem.querySelector('.list-action-btn');
                    selectButton.addEventListener('click', function(e) {
                        e.preventDefault();
                        selectPackage(pkg);
                    });
                    
                    packageList.appendChild(packageItem);
                });
            } else {
                const emptyItem = document.createElement('div');
                emptyItem.className = 'list-empty';
                emptyItem.innerHTML = `
                    <i class="fas fa-box-open"></i>
                    <p>未找到可用的汉化包</p>
                `;
                packageList.appendChild(emptyItem);
            }
        })
        .catch(function(error) {
            console.error('获取汉化包列表失败:', error);
            packageList.innerHTML = '';
            const errorItem = document.createElement('div');
            errorItem.className = 'list-empty';
            errorItem.innerHTML = `
                <i class="fas fa-exclamation-triangle"></i>
                <p>获取列表失败: ${error.message || '未知错误'}</p>
            `;
            packageList.appendChild(errorItem);
        });
}

function selectPackage(packageName) {
    document.querySelectorAll('.list-item').forEach(item => {
        item.classList.remove('selected');
        item.removeAttribute('data-selected');
    });
    
    const items = document.querySelectorAll('.list-item');
    for (let item of items) {
        const span = item.querySelector('span');
        if (span && span.textContent === packageName) {
            item.classList.add('selected');
            item.setAttribute('data-selected', 'true');
            break;
        }
    }
}

function installSelectedPackage() {
    const selectedItem = document.querySelector('.list-item[data-selected="true"]');
    if (!selectedItem) {
        showMessage('提示', '请先选择一个汉化包');
        return;
    }
    
    const packageName = selectedItem.querySelector('span')?.textContent;
    if (!packageName) {
        showMessage('错误', '无法获取选中汉化包的名称');
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

function changeFontForPackage() {
    const selectedItem = document.querySelector('.list-item[data-selected="true"]');
    if (!selectedItem) {
        showMessage('提示', '请先选择一个汉化包');
        return;
    }
    
    const packageName = selectedItem.querySelector('span')?.textContent;
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

function deleteSelectedPackage() {
    const selectedItem = document.querySelector('.list-item[data-selected="true"]');
    if (!selectedItem) {
        showMessage('提示', '请先选择一个汉化包');
        return;
    }
    
    const packageName = selectedItem.querySelector('span')?.textContent;
    if (!packageName) {
        showMessage('错误', '无法获取选中汉化包的名称');
        return;
    }
    
    showConfirm('确认删除', `确定要删除汉化包 "${packageName}" 吗？此操作不可撤销。`, 
        function() {
            pywebview.api.delete_translation_package(packageName).then(function(result) {
                if (result.success) {
                    selectedItem.style.opacity = '0.5';
                    selectedItem.style.textDecoration = 'line-through';
                    
                    setTimeout(() => {
                        selectedItem.remove();
                        
                        const packageList = document.getElementById('install-package-list');
                        if (!packageList.children.length || (packageList.children.length === 1 && packageList.children[0].classList.contains('list-empty'))) {
                            const emptyItem = document.createElement('div');
                            emptyItem.className = 'list-empty';
                            emptyItem.innerHTML = `
                                <i class="fas fa-box-open"></i>
                                <p>未找到可用的汉化包</p>
                            `;
                            packageList.appendChild(emptyItem);
                        }
                        
                        showMessage('删除成功', `汉化包 "${packageName}" 已被删除`);
                    }, 300);
                } else {
                    showMessage('删除失败', `删除汉化包失败: ${result.message}`);
                }
            }).catch(function(error) {
                showMessage('删除失败', `删除过程中发生错误: ${error}`);
            });
        },
        function() {
            // 取消操作
        }
    );
}

function fetchProperNouns() {
    const outputFormat = document.getElementById('proper-output').value;
    const skipSpace = document.getElementById('proper-skip-space').checked;
    const maxCount = document.getElementById('proper-max-count').value;
    const joinChar = document.getElementById('proper-join-char').value;
    
    const updates = {
        'proper-join-char': joinChar,
        'proper-max-lenth': maxCount,
        'proper-output-type': outputFormat,
        'proper-disable-space': skipSpace
    };

    const modal = new ProgressModal('抓取专有词汇');
    modal.addLog('开始抓取专有词汇...');
    modal.addLog(`输出格式: ${outputFormat}`);
    modal.addLog(`跳过含空格词汇: ${skipSpace ? '是' : '否'}`);
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
    
    const modal = new ProgressModal('下载OurPlay汉化包');
    modal.addLog('开始下载OurPlay汉化包...');
    modal.addLog(`字体选项: ${fontOption}`);
    modal.addLog(`哈希校验: ${checkHash ? '启用' : '禁用'}`);
    
    // 批量更新配置
    const updates = {
        'ourplay-font-option': fontOption,
        'ourplay-check-hash': checkHash
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

function saveAPIConfig() {
    const apiService = document.getElementById('api-service').value;
    const apiKey = document.getElementById('api-key').value;
    const apiSecret = document.getElementById('api-secret').value;
    
    if (!apiKey) {
        showMessage('错误', '请输入API密钥');
        return;
    }
    
    const modal = new ProgressModal('保存API配置');
    modal.addLog(`保存配置: ${apiService}`);
    
    pywebview.api.save_api_config(modal.id).then(function(result) {
        if (result.success) {
            modal.complete(true, 'API配置保存成功');
        } else {
            modal.complete(false, '保存失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '保存过程中发生错误: ' + error);
    });
}

// 滑块值更新
function updateValue(sliderId) {
    const slider = document.getElementById(sliderId);
    const valueSpan = document.getElementById(`${sliderId}-value`);
    if (slider && valueSpan) {
        valueSpan.textContent = slider.value;
    }
}

// ================================
// 配置管理函数
// ================================

// 应用设置到UI
async function loadSettings() {
    if (configManager) {
        await configManager.applyConfigToUI();
    }
}

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
                    });
            } else {
                modal.complete(false, '保存失败: ' + result.message);
            }
        })
        .catch(function(error) {
            modal.complete(false, '保存过程中发生错误: ' + error);
        });
}

// 应用launcher配置到UI
function applyLauncherConfigToUI() {
    if (configManager) {
        // launcher配置已经包含在configManager的映射表中
        // 它们会在applyConfigToUI时自动应用
    }
}

// 保存launcher配置
function saveLauncherConfig() {
    if (typeof pywebview === 'undefined' || !pywebview.api) {
        showMessage('错误', 'API尚未准备就绪');
        return;
    }
    
    const modal = new ProgressModal('保存Launcher配置');
    modal.addLog('正在保存Launcher配置...');
    
    if (!configManager) {
        modal.complete(false, '配置管理器未初始化');
        return;
    }
    
    // 收集launcher相关配置更新
    const launcherIds = [
        'launcher-zero-zip-type',
        'launcher-zero-download-source',
        'launcher-zero-use-proxy',
        'launcher-zero-use-cache',
        'launcher-ourplay-font-option',
        'launcher-ourplay-use-api',
        'launcher-work-update',
        'launcher-work-mod'
    ];
    
    const updates = {};
    launcherIds.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            let value;
            if (element.type === 'checkbox') {
                value = element.checked;
            } else {
                value = element.value;
            }
            updates[id] = value;
        }
    });
    
    // 批量更新配置
    configManager.updateConfigValues(updates)
        .then(function(result) {
            if (result.success) {
                configManager.flushPendingUpdates()
                    .then(() => {
                        modal.complete(true, 'Launcher配置保存成功');
                        pywebview.api.save_config_to_file();
                    });
            } else {
                modal.complete(false, '部分配置保存失败');
            }
        })
        .catch(function(error) {
            modal.complete(false, '保存配置时发生错误: ' + error);
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
    }
}

// 简单Markdown转HTML
function simpleMarkdownToHtml(text) {
    if (!text) return '';
    
    const htmlTagRegex = /(<[^>]+>)/g;
    const htmlTags = [];
    let processedText = text.replace(htmlTagRegex, function(match) {
        htmlTags.push(match);
        return `\x01${htmlTags.length - 1}\x01`;
    });
    
    processedText = processedText.replace(/```(\w*)\n([\s\S]*?)```/g, function(match, lang, code) {
        const escapedCode = code.replace(/&/g, '&amp;')
                               .replace(/</g, '&lt;')
                               .replace(/>/g, '&gt;')
                               .trim();
        return `<pre><code class="language-${lang || 'text'}">${escapedCode}</code></pre>`;
    });
    
    processedText = processedText.replace(/`([^`]+)`/g, '<code>$1</code>');
    processedText = processedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    processedText = processedText.replace(/__(.*?)__/g, '<strong>$1</strong>');
    processedText = processedText.replace(/(?:^|\s)\*([^\*]+)\*(?:\s|$)/g, ' <em>$1</em> ');
    processedText = processedText.replace(/(?:^|\s)_([^_]+)_(?:\s|$)/g, ' <em>$1</em> ');
    processedText = processedText.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
    processedText = processedText.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" style="max-width: 100%;">');
    
    processedText = processedText.replace(/^###### (.*$)/gm, '<h6>$1</h6>');
    processedText = processedText.replace(/^##### (.*$)/gm, '<h5>$1</h5>');
    processedText = processedText.replace(/^#### (.*$)/gm, '<h4>$1</h4>');
    processedText = processedText.replace(/^### (.*$)/gm, '<h3>$1</h3>');
    processedText = processedText.replace(/^## (.*$)/gm, '<h2>$1</h2>');
    processedText = processedText.replace(/^# (.*$)/gm, '<h1>$1</h1>');
    
    processedText = processedText.replace(/^[*-] (.*$)/gm, '<li>$1</li>');
    processedText = processedText.replace(/(<li>.*<\/li>)+/gs, function(match) {
        return '<ul>' + match.replace(/<\/li><li>/g, '</li>\n<li>') + '</ul>';
    });
    
    processedText = processedText.replace(/\x01(\d+)\x01/g, function(match, index) {
        return htmlTags[index];
    });
    
    const paragraphs = processedText.split(/\n\s*\n/);
    const processedParagraphs = paragraphs.map(paragraph => {
        paragraph = paragraph.trim();
        if (paragraph && !paragraph.match(/^<(h[1-6]|ul|ol|li|pre|div|blockquote)/)) {
            paragraph = paragraph.replace(/\n/g, '<br>');
            return '<p>' + paragraph + '</p>';
        }
        return paragraph;
    });
    
    return processedParagraphs.filter(p => p !== '').join('\n');
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
    htmlMessage += `<p><strong>当前版本:</strong> ${update_info.current_version || 'unknown'}</p>`;
    
    if (update_info.title) {
        htmlMessage += `<p><strong>发布标题:</strong> ${update_info.title}</p>`;
    }
    
    if (update_info.body) {
        let body = update_info.body.trim();
        const bodyHtml = simpleMarkdownToHtml(body);
        htmlMessage += `<div><strong>更新详情:</strong></div>`;
        htmlMessage += `<div style="margin: 10px 0; padding: 10px; background: var(--color-bg-input); border-radius: var(--radius-md); max-height: 300px; overflow-y: auto;">${bodyHtml}</div>`;
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
            const progressModal = new ProgressModal('更新程序');
            progressModal.addLog('开始下载并安装更新...');
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
    
    // 初始化复选框
    initCheckboxes();
    
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
                }
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
    
    pywebview.api.get_attr('config_ok')
        .then(function(config_ok) {
            if (config_ok === false) {
                pywebview.api.get_attr('config_error')
                    .then(function(config_error) {
                        let errorMessage = "配置项格式错误，是否尝试修复?\n否则将会使用默认配置";
                        if (config_error && Array.isArray(config_error) && config_error.length > 0) {
                            errorMessage += "\n\n详细错误信息:\n" + config_error.join("\n");
                        }
                        
                        showConfirm(
                            "警告",
                            errorMessage,
                            () => {
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
                                    .then(function() {
                                        showMessage("提示", "配置已修复并保存，请重新启动程序");
                                    })
                                    .catch(function(error) {
                                        showMessage("错误", "修复配置时出错: " + error);
                                    });
                            },
                            () => {
                                pywebview.api.use_default()
                                    .then(function() {
                                        showMessage("提示", "已使用默认配置，请重新启动程序");
                                    })
                                    .catch(function(error) {
                                        showMessage("错误", "使用默认配置时出错: " + error);
                                    });
                            }
                        );
                    })
                    .catch(function(error) {
                        showMessage(
                            "错误",
                            "未知错误，可能导致未知后果。错误信息:\n" + error
                        );
                    });
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
                configManager.applyConfigToUI();
            }
            
            checkGamePath();
            
            const autoCheckUpdate = configManager.getCachedValue('auto_check_update');
            if (autoCheckUpdate) {
               autoCheckUpdates();
            }
        });
});