/**
 * script.js —— LCTA v5.0.0 核心前端基础设施
 *
 * 提供:
 *   - ThemeManager: 三主题切换（亮色/暗色/紫色）
 *   - AnimationManager: 淡入/淡出/滑动动画
 *   - ConfigManager: 配置缓存 + 防抖批量更新 + schema 驱动的 ID 映射
 *   - PagesManager: 页面生命周期管理 + DOM 就绪检查 + 切换事件钩子
 *   - ModalWindow / ProgressModal: 模态窗口系统
 *   - DragDropManager: 拖拽文件处理
 *   - 工具函数: addLogMessage / showMessage / showConfirm / 加密等
 *
 * 页面逻辑已拆分至各插件的 page.js 文件中。
 */

// ═══════════════════════════════════════════════════════════════════════════════
// ThemeManager
// ═══════════════════════════════════════════════════════════════════════════════

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
            setTimeout(() => clickedBtn.classList.remove('changing'), 300);
        }
        if (this.debounceTimer) clearTimeout(this.debounceTimer);
        this.debounceTimer = setTimeout(() => this.setTheme(theme), this.debounceDelay);
    }

    setTheme(theme, skipDebounce = false) {
        if (this.isTransitioning) { this.pendingTheme = theme; return; }
        if (this.currentTheme === theme) return;
        this.isTransitioning = true;
        document.body.classList.add('theme-transition');
        document.body.classList.remove('theme-light', 'theme-dark', 'theme-purple');
        document.body.classList.add(`theme-${theme}`);
        this.currentTheme = theme;
        configManager.updateConfigValue('theme', theme);
        this.updateThemeButtons(theme);
        setTimeout(() => {
            document.body.classList.remove('theme-transition');
            this.isTransitioning = false;
            if (this.pendingTheme && this.pendingTheme !== this.currentTheme) {
                const pt = this.pendingTheme; this.pendingTheme = null; this.setTheme(pt);
            }
        }, 300);
    }

    updateThemeButtons(theme) {
        document.querySelectorAll('.theme-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.theme === theme);
        });
    }
}


// ═══════════════════════════════════════════════════════════════════════════════
// AnimationManager
// ═══════════════════════════════════════════════════════════════════════════════

class AnimationManager {
    static fadeIn(element, duration = 150) {
        element.style.opacity = 0;
        element.style.display = 'block';
        let start = null;
        const animate = (ts) => {
            if (!start) start = ts;
            element.style.opacity = Math.min((ts - start) / duration, 1);
            if (ts - start < duration) requestAnimationFrame(animate);
        };
        requestAnimationFrame(animate);
    }

    static fadeOut(element, duration = 150) {
        let start = null;
        const animate = (ts) => {
            if (!start) start = ts;
            element.style.opacity = 1 - Math.min((ts - start) / duration, 1);
            if (ts - start < duration) requestAnimationFrame(animate);
            else { element.style.display = 'none'; element.style.opacity = 1; }
        };
        requestAnimationFrame(animate);
    }

    static slideIn(element, from = 'left', duration = 150) {
        const dir = from === 'left' ? '-100%' : '100%';
        element.style.transform = `translateX(${dir})`;
        element.style.display = 'block';
        let start = null;
        const animate = (ts) => {
            if (!start) start = ts;
            element.style.transform = `translateX(${parseInt(dir) * (1 - Math.min((ts - start) / duration, 1))}%)`;
            if (ts - start < duration) requestAnimationFrame(animate);
        };
        requestAnimationFrame(animate);
    }
}


// ═══════════════════════════════════════════════════════════════════════════════
// PagesManager —— 页面生命周期管理
// ═══════════════════════════════════════════════════════════════════════════════

class PagesManager {
    constructor() {
        /** @type {Map<string, {html:string, js:{}, css:{}, config:{}}>} */
        this._pages = new Map();
        /** @type {string|null} */
        this._activeId = null;
        /** @type {Map<string, {onActivate:Function, onDeactivate:Function}>} */
        this._hooks = new Map();
        /** @type {boolean} */
        this._switching = false;
    }

    /**
     * 注册插件的页面切换事件钩子。
     * 由插件 page.js 在初始化时调用。
     *
     * @param {string} pluginId
     * @param {{onActivate?:Function, onDeactivate?:Function}} hooks
     */
    registerSwitchHook(pluginId, hooks) {
        if (!this._hooks.has(pluginId)) {
            this._hooks.set(pluginId, {});
        }
        const existing = this._hooks.get(pluginId);
        if (hooks.onActivate) existing.onActivate = hooks.onActivate;
        if (hooks.onDeactivate) existing.onDeactivate = hooks.onDeactivate;
    }

    /**
     * 切换到指定插件页面。
     * 处理：触发旧页面 deactivate → 加载新页面内容 → 注入 DOM → 触发新页面 activate
     *
     * @param {string} pluginId - 插件 ID 或 'welcome' / 'log' / 'test' 等内置页面
     * @returns {Promise<boolean>}
     */
    async switchPage(pluginId) {
        if (this._switching) {
            console.warn('[PagesManager] 正在切换页面中，忽略重复请求');
            return false;
        }

        if (this._activeId === pluginId && this._pages.has(pluginId)) {
            return true; // 已经是当前页面
        }

        this._switching = true;

        try {
            // 1. 触发旧页面 deactivate
            if (this._activeId) {
                await this._fireHook(this._activeId, 'onDeactivate');
            }

            // 2. 加载新页面内容
            if (!this._pages.has(pluginId)) {
                const loaded = await this._loadPageContent(pluginId);
                if (!loaded) {
                    console.error(`[PagesManager] 加载页面失败: ${pluginId}`);
                    this._switching = false;
                    return false;
                }
            }

            // 3. 等待 DOM 就绪后注入内容
            await this._waitForDOM();
            this._renderPage(pluginId);

            // 4. 触发新页面 activate
            this._activeId = pluginId;
            await this._waitForDOM();
            await this._fireHook(pluginId, 'onActivate');

            // 5. 填充配置到页面元素
            this._fillConfigForPage(pluginId);

            // 6. 更新导航高亮
            this._updateNavHighlight(pluginId);

            this._switching = false;
            return true;
        } catch (e) {
            console.error(`[PagesManager] 切换页面异常:`, e);
            this._switching = false;
            return false;
        }
    }

    /** 从后端加载插件页面内容 */
    async _loadPageContent(pluginId) {
        // 内置页面无需从后端加载
        if (pluginId === 'welcome' || pluginId === 'log' || pluginId === 'test') {
            this._pages.set(pluginId, { html: null, js: {}, css: {}, config: {} });
            return true;
        }

        try {
            const result = await window.pywebview.api.plugin_activate(pluginId);
            if (!result.success) {
                console.error(`[PagesManager] 激活插件失败: ${result.message}`);
                return false;
            }

            this._pages.set(pluginId, {
                html: result.html || '',
                js: result.js || {},
                css: result.css || {},
                config: result.config || {},
            });

            // 将配置值同步到 ConfigManager 缓存
            if (result.config) {
                for (const [path, value] of Object.entries(result.config)) {
                    configManager.setCachedValue(path, value);
                }
            }

            return true;
        } catch (e) {
            console.error(`[PagesManager] 加载页面异常:`, e);
            return false;
        }
    }

    /** 将页面 HTML/CSS/JS 渲染到 DOM */
    _renderPage(pluginId) {
        const contentArea = document.getElementById('page-content');
        if (!contentArea) return;

        const page = this._pages.get(pluginId);
        if (!page) return;

        // 清除旧插件 CSS
        document.querySelectorAll('style[data-plugin]').forEach(s => s.remove());

        // 隐藏日志/测试等内置 section
        document.querySelectorAll('.content-section').forEach(s => s.style.display = 'none');

        // 内置页面：显示对应 section
        if (pluginId === 'log') {
            const logSection = document.getElementById('log-section');
            if (logSection) { logSection.style.display = 'block'; scrollLogToBottom(); }
            contentArea.innerHTML = '';
            return;
        }
        if (pluginId === 'test') {
            const testSection = document.getElementById('test-section');
            if (testSection) testSection.style.display = 'block';
            contentArea.innerHTML = '';
            return;
        }
        if (pluginId === 'welcome') {
            contentArea.innerHTML = `<div class="section-header">
                <h2 class="section-title"><i class="fas fa-language"></i> LCTA - 边狱公司汉化工具箱</h2>
                <p class="section-subtitle">欢迎使用</p>
            </div>`;
            return;
        }

        // 渲染插件 HTML
        if (page.html) {
            contentArea.innerHTML = page.html;
        }

        // 注入 CSS
        if (page.css) {
            Object.entries(page.css).forEach(([filename, css]) => {
                const style = document.createElement('style');
                style.textContent = css;
                style.dataset.plugin = pluginId;
                document.head.appendChild(style);
            });
        }

        // 执行 JS
        if (page.js) {
            Object.entries(page.js).forEach(([filename, code]) => {
                try {
                    const fn = new Function('pagesManager', 'configManager', 'pluginLoader', code);
                    fn(pagesManager, configManager, pluginLoader);
                } catch (e) {
                    console.error(`[PagesManager] 执行 ${filename} 失败:`, e);
                }
            });
        }
    }

    /** 将配置值填充到当前页面的 DOM 元素 */
    _fillConfigForPage(pluginId) {
        const contentArea = document.getElementById('page-content');
        if (!contentArea) return;

        const schema = configManager._schema || {};
        for (const [path, meta] of Object.entries(schema)) {
            if (meta.plugin_id !== pluginId) continue;
            const htmlId = meta.html_id;
            if (!htmlId) continue;
            const el = document.getElementById(htmlId);
            if (!el) continue;
            const value = configManager.getCachedValue(path);
            if (value === undefined) continue;
            configManager._applyValueToElement(el, value);
        }
    }

    /** 触发页面切换钩子 */
    async _fireHook(pluginId, event) {
        const hooks = this._hooks.get(pluginId);
        const fn = hooks && hooks[event];
        if (typeof fn === 'function') {
            try {
                await fn();
            } catch (e) {
                console.error(`[PagesManager] ${event} 钩子执行失败 (${pluginId}):`, e);
            }
        }
    }

    /** 等待 DOM 稳定 */
    _waitForDOM() {
        return new Promise(resolve => {
            if (document.readyState === 'complete' || document.readyState === 'interactive') {
                // 使用 requestAnimationFrame 确保渲染完成
                requestAnimationFrame(() => requestAnimationFrame(resolve));
            } else {
                document.addEventListener('DOMContentLoaded', () => {
                    requestAnimationFrame(() => requestAnimationFrame(resolve));
                }, { once: true });
            }
        });
    }

    /** 更新侧边栏导航高亮 */
    _updateNavHighlight(pluginId) {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        // 查找对应 nav 按钮：遍历所有按钮，匹配 data-plugin-id
        document.querySelectorAll('.nav-btn').forEach(btn => {
            if (btn.dataset.pluginId === pluginId) {
                btn.classList.add('active');
            }
        });
        // 兼容旧 ID 规则: xxx-btn -> xxx 匹配 pluginId
        if (!document.querySelector('.nav-btn.active')) {
            const fallback = document.getElementById(`${pluginId}-btn`);
            if (fallback) fallback.classList.add('active');
        }
    }

    /** 获取当前激活的插件 ID */
    get activeId() {
        return this._activeId;
    }

    /** 判断指定页面是否已就绪（内容已加载） */
    isReady(pluginId) {
        return this._pages.has(pluginId);
    }
}


// ═══════════════════════════════════════════════════════════════════════════════
// ConfigManager —— schema 驱动的配置管理
// ═══════════════════════════════════════════════════════════════════════════════

class ConfigManager {
    constructor() {
        /** @type {Object<string, {type:string, default:*, label:string, options:Array, html_id:string, plugin_id:string}>} */
        this._schema = {};
        /** @type {Object} 配置值缓存（嵌套对象） */
        this.configCache = {};
        /** @type {Object} 待更新队列 */
        this.pendingUpdates = {};
        /** @type {number|null} */
        this.debounceTimer = null;
        this.debounceDelay = 500;
    }

    /**
     * 应用后端返回的全量同步数据（schema + 当前值）。
     * 由 pluginLoader.init() 在启动时调用。
     */
    applyFullSync(schema, values) {
        this._schema = schema || {};

        // 填充配置缓存
        if (values) {
            for (const [path, value] of Object.entries(values)) {
                this.setCachedValue(path, value);
            }
        }

        console.log(`[ConfigManager] 已同步 ${Object.keys(this._schema).length} 个配置项`);
    }

    /**
     * 根据 html_id 或 path 获取配置值。
     * 优先按 html_id 查找 schema，再尝试直接作为 path。
     */
    get(idOrPath) {
        // 先尝试按 html_id 查找
        for (const [path, meta] of Object.entries(this._schema)) {
            if (meta.html_id === idOrPath) {
                return this.getCachedValue(path);
            }
        }
        // 再尝试作为 path 直接读取
        return this.getCachedValue(idOrPath);
    }

    /** 获取嵌套缓存值 */
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

    /** 设置嵌套缓存值 */
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

    /** 通过 html_id 更新配置值（自动防抖批量发送到后端） */
    async updateConfigValue(id, value) {
        // 查找 html_id 对应的 config path
        let keyPath = null;
        for (const [path, meta] of Object.entries(this._schema)) {
            if (meta.html_id === id) {
                keyPath = path;
                break;
            }
        }
        if (!keyPath) {
            // 没有 schema 映射，直接当作 path 使用
            keyPath = id;
        }

        this.pendingUpdates[keyPath] = value;
        this.debounceUpdate();
        return true;
    }

    /** 防抖批量发送 */
    debounceUpdate() {
        if (this.debounceTimer) clearTimeout(this.debounceTimer);
        this.debounceTimer = setTimeout(() => this.flushPendingUpdates(), this.debounceDelay);
    }

    /** 立即发送所有待更新配置到后端 */
    async flushPendingUpdates() {
        if (Object.keys(this.pendingUpdates).length === 0) return;

        const updates = { ...this.pendingUpdates };
        this.pendingUpdates = {};

        // 更新本地缓存
        for (const [keyPath, value] of Object.entries(updates)) {
            this.setCachedValue(keyPath, value);
        }

        try {
            const result = await window.pywebview.api.config_set_batch(updates);
            if (result.success) {
                console.log(`[ConfigManager] 批量更新成功: ${result.updated} 项`);
            }
            return result;
        } catch (error) {
            console.error('[ConfigManager] 批量更新失败:', error);
            return { success: false, message: error.toString() };
        }
    }

    /** 将配置值填充到页面上所有匹配的元素 */
    applyConfigToPage() {
        for (const [path, meta] of Object.entries(this._schema)) {
            const htmlId = meta.html_id;
            if (!htmlId) continue;
            const el = document.getElementById(htmlId);
            if (!el) continue;
            const value = this.getCachedValue(path);
            if (value !== undefined) {
                this._applyValueToElement(el, value);
            }
        }
    }

    /** 将值写入 DOM 元素 */
    _applyValueToElement(el, value) {
        if (el.type === 'checkbox') {
            el.checked = Boolean(value);
        } else if (el.tagName === 'SELECT') {
            el.value = value != null ? String(value) : '';
        } else {
            el.value = value != null ? String(value) : '';
        }
    }

    /** 获取 schema 元数据 */
    getSchema(path) {
        return this._schema[path] || null;
    }

    /** 获取某个插件的所有配置项 */
    getPluginConfig(pluginId) {
        const result = {};
        for (const [path, meta] of Object.entries(this._schema)) {
            if (meta.plugin_id === pluginId) {
                result[path] = this.getCachedValue(path);
            }
        }
        return result;
    }
}


// ═══════════════════════════════════════════════════════════════════════════════
// 全局实例
// ═══════════════════════════════════════════════════════════════════════════════

let configManager;
let pagesManager;
let themeManager;
let dragDropManager;

/** @type {Array<ModalWindow>} */
let modalWindows = [];


// ═══════════════════════════════════════════════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════════════════════════════════════════════

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

function ensureModalContainer() {
    let container = document.getElementById('modal-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'modal-container';
        document.body.appendChild(container);
    }
    return container;
}

function ensureMinimizedContainer() {
    let container = document.getElementById('minimized-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'minimized-container';
        container.style.cssText = 'position:fixed;top:80px;right:20px;bottom:20px;width:300px;display:flex;flex-direction:column;align-items:flex-end;gap:10px;z-index:999;max-height:calc(100vh - 100px);overflow-y:auto;overflow-x:hidden;padding:5px;';
        document.body.appendChild(container);
    }
    return container;
}

function scrollLogToBottom() {
    const logDisplay = document.getElementById('log-display');
    if (logDisplay) {
        setTimeout(() => { logDisplay.scrollTop = logDisplay.scrollHeight; }, 100);
    }
}

function initPasswordToggles() {
    document.querySelectorAll('.toggle-password').forEach(button => {
        button.addEventListener('click', function () {
            const input = this.parentElement.querySelector('input');
            const icon = this.querySelector('i');
            if (input.type === 'password') {
                input.type = 'text'; icon.classList.remove('fa-eye'); icon.classList.add('fa-eye-slash');
            } else {
                input.type = 'password'; icon.classList.remove('fa-eye-slash'); icon.classList.add('fa-eye');
            }
        });
    });
}

function browseFile(inputId) { window.pywebview.api.browse_file(inputId); }
function browseFolder(inputId) { window.pywebview.api.browse_folder(inputId); }

function goAndShow(name) {
    pagesManager.switchPage(name);
}


// ═══════════════════════════════════════════════════════════════════════════════
// 加密工具
// ═══════════════════════════════════════════════════════════════════════════════

async function encryptText(password, plaintext) {
    try {
        const encoder = new TextEncoder();
        const passwordBuffer = encoder.encode(password);
        const keyMaterial = await crypto.subtle.importKey('raw', passwordBuffer, { name: 'PBKDF2' }, false, ['deriveKey']);
        const salt = crypto.getRandomValues(new Uint8Array(16));
        const iv = crypto.getRandomValues(new Uint8Array(12));
        const key = await crypto.subtle.deriveKey(
            { name: 'PBKDF2', salt, iterations: 100000, hash: 'SHA-256' },
            keyMaterial, { name: 'AES-GCM', length: 256 }, false, ['encrypt']
        );
        const encryptedBuffer = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, encoder.encode(plaintext));
        const combined = new Uint8Array(salt.length + iv.length + encryptedBuffer.byteLength);
        combined.set(salt, 0); combined.set(iv, salt.length);
        combined.set(new Uint8Array(encryptedBuffer), salt.length + iv.length);
        return btoa(String.fromCharCode(...combined));
    } catch (error) {
        console.error('加密失败:', error);
        throw new Error('加密失败: ' + error.message);
    }
}

async function decryptText(password, encryptedBase64) {
    try {
        const combined = Uint8Array.from(atob(encryptedBase64), c => c.charCodeAt(0));
        const salt = combined.slice(0, 16);
        const iv = combined.slice(16, 28);
        const encryptedData = combined.slice(28);
        const encoder = new TextEncoder();
        const keyMaterial = await crypto.subtle.importKey('raw', encoder.encode(password), { name: 'PBKDF2' }, false, ['deriveKey']);
        const key = await crypto.subtle.deriveKey(
            { name: 'PBKDF2', salt, iterations: 100000, hash: 'SHA-256' },
            keyMaterial, { name: 'AES-GCM', length: 256 }, false, ['decrypt']
        );
        const decrypted = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, encryptedData);
        return new TextDecoder().decode(decrypted);
    } catch (error) {
        console.error('解密失败:', error);
        throw new Error('解密失败: ' + error.message);
    }
}


// ═══════════════════════════════════════════════════════════════════════════════
// Markdown 加载
// ═══════════════════════════════════════════════════════════════════════════════

async function loadMarkdownContent(url, className) {
    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`加载 ${url} 失败: ${response.status}`);
        const markdownText = await response.text();
        const htmlContent = simpleMarkdownToHtml(markdownText);
        const targetDiv = document.querySelector(`.${className}`);
        if (targetDiv) targetDiv.innerHTML = htmlContent;
    } catch (error) {
        console.error(`处理 ${url} 时出错:`, error);
        const targetDiv = document.querySelector(`.${className}`);
        if (targetDiv) targetDiv.innerHTML = `<p class="error">加载内容失败: ${error.message}</p>`;
    }
}

async function loadAndRenderMarkdown() {
    try {
        const files = [
            { url: 'webui/assets/README.md', className: 'about-content' },
            { url: 'webui/assets/update.md', className: 'update-content' },
            { url: 'webui/assets/firstUse.md', className: 'use-help' }
        ];
        await Promise.allSettled(files.map(({ url, className }) => loadMarkdownContent(url, className)));
    } catch (error) {
        console.error('加载Markdown文件过程中发生错误:', error);
    }
}


// ═══════════════════════════════════════════════════════════════════════════════
// ModalWindow / ProgressModal
// ═══════════════════════════════════════════════════════════════════════════════

class ModalWindow {
    constructor(title, options = {}) {
        this.id = 'modal-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
        this.title = title;
        this.isMinimized = false;
        this.isCompleted = false;
        this.isPaused = false;
        this.percent = 0;
        this.options = {
            showProgress: false, showCancelButton: true, showPauseButton: false,
            cancelButtonText: '取消', pauseButtonText: '暂停', resumeButtonText: '继续',
            confirmButtonText: '确定', showMinimizeButton: true, showLog: true,
            onCancel: null, onPause: null, onResume: null,
            ...options
        };
        this.createModal();
        modalWindows.push(this);
    }

    createModal() {
        const container = ensureModalContainer();
        this.element = document.createElement('div');
        this.element.className = 'modal-overlay';
        const theme = document.body.classList.contains('theme-dark') ? 'theme-dark' :
            document.body.classList.contains('theme-purple') ? 'theme-purple' : 'theme-light';
        this.element.classList.add(theme);
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
                        <div class="modal-progress-bar"><div class="modal-progress-fill" id="modal-progress-fill-${this.id}"></div></div>
                    </div>
                </div>
                <div class="modal-footer" id="modal-footer-${this.id}">
                    ${this.options.showPauseButton ? `<button class="action-btn" id="pause-btn-${this.id}">${this.options.pauseButtonText}</button>` : ''}
                    ${this.options.showCancelButton ? `<button class="action-btn" id="cancel-btn-${this.id}">${this.options.cancelButtonText}</button>` : ''}
                </div>
            </div>`;
        container.appendChild(this.element);
        this.bindEvents();
        this.updateProgress(0);
    }

    bindEvents() {
        document.getElementById(`close-btn-${this.id}`).addEventListener('click', () => this.close());
        if (this.options.showMinimizeButton) {
            document.getElementById(`minimize-btn-${this.id}`).addEventListener('click', (e) => { e.stopPropagation(); this.minimize(); });
        }
        if (this.options.showPauseButton) {
            document.getElementById(`pause-btn-${this.id}`).addEventListener('click', () => {
                this.isPaused ? this.resume() : this.pause();
            });
        }
        if (this.options.showCancelButton) {
            document.getElementById(`cancel-btn-${this.id}`).addEventListener('click', () => {
                this.isCompleted ? this.close() : this.cancel();
            });
        }
    }

    setStatus(status) {
        const el = document.getElementById(`modal-status-${this.id}`);
        if (el) {
            el[typeof status === 'string' && status.includes('\n') ? 'innerHTML' : 'textContent'] =
                typeof status === 'string' && status.includes('\n') ? status.replace(/\n/g, '<br>') : status;
        }
        addLogMessage(`[${this.title}] ${status}`);
        this.updateMinimizedStatus(status);
    }

    addLog(message) {
        if (this.options.showLog) {
            const logEl = document.getElementById(`modal-log-${this.id}`);
            if (logEl) {
                const now = new Date();
                const ts = `[${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}]`;
                const entry = document.createElement('div');
                entry.textContent = `${ts} ${message}`;
                logEl.appendChild(entry);
                logEl.scrollTop = logEl.scrollHeight;
            }
        }
        addLogMessage(`[${this.title}] ${message}`);
    }

    showProgress(show = true) {
        const el = document.getElementById(`modal-progress-${this.id}`);
        if (el) el.classList.toggle('hidden', !show);
    }

    updateProgress(percent, status = null) {
        this.percent = percent;
        const fill = document.getElementById(`modal-progress-fill-${this.id}`);
        if (fill) fill.style.width = `${Math.min(100, Math.max(0, percent))}%`;
        if (status) this.setStatus(status);
    }

    updateMinimizedStatus(status) {
        if (this.isMinimized && this.minimizedElement) {
            const statusEl = this.minimizedElement.querySelector('.minimized-status');
            if (statusEl) statusEl.textContent = status;
        }
    }

    minimize() {
        if (this.isMinimized) return;
        this.isMinimized = true;
        const container = ensureMinimizedContainer();
        this.minimizedElement = document.createElement('div');
        this.minimizedElement.className = 'minimized-modal';
        this.minimizedElement.innerHTML = `
            <div class="minimized-header">
                <span class="minimized-title">${this.title}</span>
                <div class="minimized-controls">
                    <button class="minimized-restore-btn" title="还原">□</button>
                    <button class="minimized-close-btn" title="关闭">×</button>
                </div>
            </div>
            <div class="minimized-status">已最小化</div>`;
        this.minimizedElement.querySelector('.minimized-restore-btn').addEventListener('click', () => this.restore());
        this.minimizedElement.querySelector('.minimized-close-btn').addEventListener('click', () => {
            this.minimizedElement.remove(); this.close();
        });
        container.appendChild(this.minimizedElement);
        if (this.element) this.element.style.display = 'none';
    }

    restore() {
        if (!this.isMinimized) return;
        this.isMinimized = false;
        if (this.minimizedElement) { this.minimizedElement.remove(); this.minimizedElement = null; }
        if (this.element) this.element.style.display = '';
    }

    close() {
        if (this.isMinimized && this.minimizedElement) this.minimizedElement.remove();
        if (this.element) this.element.remove();
        modalWindows = modalWindows.filter(m => m !== this);
        if (this.options.onCancel && !this.isCompleted) this.options.onCancel();
        if (!this.isCompleted) {
            try { window.pywebview.api.del_modal_list(this.id); } catch (e) { }
        }
    }

    cancel() {
        this.updateProgress(0, '已取消');
        if (this.options.onCancel) this.options.onCancel();
        try { window.pywebview.api.set_modal_running(this.id, 'cancel'); } catch (e) { }
    }

    pause() {
        this.isPaused = true;
        const btn = document.getElementById(`pause-btn-${this.id}`);
        if (btn) btn.textContent = this.options.resumeButtonText;
        this.setStatus('已暂停');
        if (this.options.onPause) this.options.onPause();
        try { window.pywebview.api.set_modal_running(this.id, 'pause'); } catch (e) { }
    }

    resume() {
        this.isPaused = false;
        const btn = document.getElementById(`pause-btn-${this.id}`);
        if (btn) btn.textContent = this.options.pauseButtonText;
        this.setStatus('已继续');
        if (this.options.onResume) this.options.onResume();
        try { window.pywebview.api.set_modal_running(this.id, 'running'); } catch (e) { }
    }

    complete(success = true, message = '完成') {
        this.isCompleted = true;
        this.updateProgress(success ? 100 : 0, message);
        const footer = document.getElementById(`modal-footer-${this.id}`);
        if (footer) {
            footer.innerHTML = `<button class="action-btn success" id="confirm-btn-${this.id}">${this.options.confirmButtonText}</button>`;
            document.getElementById(`confirm-btn-${this.id}`).addEventListener('click', () => this.close());
        }
        const cancelBtn = document.getElementById(`cancel-btn-${this.id}`);
        if (cancelBtn) cancelBtn.textContent = '关闭';
        try { window.pywebview.api.del_modal_list(this.id); } catch (e) { }
    }
}


class ProgressModal extends ModalWindow {
    constructor(title, options = {}) {
        super(title, { showProgress: true, showPauseButton: true, ...options });
        try { window.pywebview.api.add_modal_id(this.id); } catch (e) { }
    }
}


// ═══════════════════════════════════════════════════════════════════════════════
// 消息弹窗
// ═══════════════════════════════════════════════════════════════════════════════

function showMessage(title, message, callback = null) {
    const modal = new ModalWindow(title, { showCancelButton: false, showLog: false, showMinimizeButton: false });
    modal.setStatus(message);
    const footer = document.getElementById(`modal-footer-${modal.id}`);
    if (footer) {
        footer.innerHTML = `<button class="action-btn success" id="msg-confirm-btn-${modal.id}">确定</button>`;
        document.getElementById(`msg-confirm-btn-${modal.id}`).addEventListener('click', () => {
            modal.close();
            if (callback) callback();
        });
    }
    return modal;
}

function showConfirm(title, message, onConfirm, onCancel = null) {
    const modal = new ModalWindow(title, { showLog: false, showMinimizeButton: false, cancelButtonText: '取消' });
    modal.setStatus(message);
    const footer = document.getElementById(`modal-footer-${modal.id}`);
    if (footer) {
        const confirmBtn = document.createElement('button');
        confirmBtn.className = 'action-btn success';
        confirmBtn.textContent = '确定';
        confirmBtn.addEventListener('click', () => { modal.close(); if (onConfirm) onConfirm(); });
        footer.insertBefore(confirmBtn, footer.firstChild);
    }
    const cancelBtn = document.getElementById(`cancel-btn-${modal.id}`);
    if (cancelBtn) {
        cancelBtn.addEventListener('click', () => { modal.close(); if (onCancel) onCancel(); });
    }
    return modal;
}


// ═══════════════════════════════════════════════════════════════════════════════
// 日志面板
// ═══════════════════════════════════════════════════════════════════════════════

function addLogMessage(message, level = 'info') {
    const logDisplay = document.getElementById('log-display');
    if (!logDisplay) return;
    const now = new Date();
    const timestamp = `[${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}]`;
    const entry = document.createElement('div');
    entry.className = `log-entry ${level}`;
    entry.innerHTML = `<div class="log-timestamp">${timestamp}</div><div class="log-level">[${level.toUpperCase()}]</div><div class="log-message">${message}</div>`;
    logDisplay.appendChild(entry);
    logDisplay.scrollTop = logDisplay.scrollHeight;
    while (logDisplay.children.length > 500) logDisplay.removeChild(logDisplay.firstChild);
}


// ═══════════════════════════════════════════════════════════════════════════════
// Simple Markdown to HTML
// ═══════════════════════════════════════════════════════════════════════════════

function simpleMarkdownToHtml(markdown) {
    if (typeof marked !== 'undefined') {
        marked.setOptions({ breaks: true, gfm: true });
        return marked.parse(markdown);
    }
    return markdown
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>');
}


// ═══════════════════════════════════════════════════════════════════════════════
// DragDropManager
// ═══════════════════════════════════════════════════════════════════════════════

class DragDropManager {
    constructor() {
        this.maskElement = null;
        this.onFileDropCallback = null;
        this.leaveChecked = 0;
        this.init();
    }

    init() {
        document.body.addEventListener('dragenter', (e) => { e.preventDefault(); e.stopPropagation(); this.showMask(); });
        document.body.addEventListener('dragover', (e) => { e.preventDefault(); e.stopPropagation(); this.showMask(); });
        document.body.addEventListener('dragleave', (e) => { e.preventDefault(); e.stopPropagation(); this.hideMask(); });
        document.body.addEventListener('drop', (e) => { this.maskLoad(); });
    }

    maskLoad() {
        if (!this.maskElement) return;
        const maskChar = document.getElementById('file-mask-char');
        if (maskChar) maskChar.className = 'spinner';
    }

    showMask() {
        this.leaveChecked = 0;
        if (this.maskElement) return;
        this.maskElement = document.createElement('div');
        this.maskElement.className = 'drop-zone-mask';
        this.maskElement.innerHTML = `
            <div class="drop-zone-mask-content">
                <i id="file-mask-char" class="fas fa-cloud-upload-alt"></i>
                <p>拖拽文件到这里</p>
                <small>支持汉化包安装，模组安装或是版本更新</small>
            </div>`;
        document.body.appendChild(this.maskElement);
    }

    hideMask() {
        this.leaveChecked = 1;
        setTimeout(() => {
            if (!this.leaveChecked) return;
            this.leaveChecked += 1;
            setTimeout(() => {
                if (this.leaveChecked >= 2 && this.maskElement) {
                    this.maskElement.remove(); this.maskElement = null; this.leaveChecked = 0;
                }
            }, 30);
        }, 30);
    }

    setOnFileDropCallback(callback) { this.onFileDropCallback = callback; }
}

function setupDragDropCallback() {
    if (!dragDropManager) return;
    dragDropManager.setOnFileDropCallback(async () => {
        const modal = showConfirm('处理文件', '正在处理拖入的文件...');
        const result = await window.pywebview.api.handle_dropped_files();
        document.getElementById(`modal-status-${modal.id}`).innerHTML = result.message;
        if (result.success) {
            modal.eval_dropped_files = function () {
                modal.close();
                const pm = new ProgressModal('处理文件');
                pm.addLog('正在处理文件...');
                window.pywebview.api.eval_dropped_files(result.file_info, pm.id);
            };
        }
    });
}


// ═══════════════════════════════════════════════════════════════════════════════
// 游戏路径
// ═══════════════════════════════════════════════════════════════════════════════

function checkGamePath() {
    const gamePath = configManager.getCachedValue('game_path');
    if (!gamePath) {
        window.pywebview.api.run_func('find_lcb')
            .then(foundPath => {
                if (foundPath) confirmGamePath(foundPath);
                else requestGamePath();
            })
            .catch(error => addLogMessage('检查游戏路径时发生错误: ' + error, 'error'));
    }
}

function confirmGamePath(foundPath) {
    showConfirm("确认游戏路径", `这是否是你的游戏路径：\n${foundPath}\n是否使用此路径？`,
        () => {
            configManager.updateConfigValue('game-path', foundPath)
                .then(() => configManager.flushPendingUpdates())
                .then(() => {
                    addLogMessage('游戏路径已确认并保存: ' + foundPath, 'success');
                    window.pywebview.api.init_cache();
                })
                .catch(error => addLogMessage('设置游戏路径时发生错误: ' + error, 'error'));
            window.pywebview.api.save_config_to_file();
        },
        () => requestGamePath()
    );
}

function requestGamePath() {
    showMessage("选择游戏路径", "请手动选择游戏的安装目录（包含LimbusCompany.exe的文件夹）",
        () => browseFolder('game-path')
    );
}


// ═══════════════════════════════════════════════════════════════════════════════
// 帮助引导
// ═══════════════════════════════════════════════════════════════════════════════

async function showGuide(page) {
    await showMarkdownModal(`webui/guide/${page}.md`, '俺寻思', '正在加载数据内容');
}

async function showMarkdownModal(link, title = '指导', pre = '正在加载数据内容') {
    const modal = showMessage(title, pre);
    const response = await fetch(link);
    let markdownText;
    if (!response.ok) {
        markdownText = `加载内容失败: ${response.status} ${response.statusText}`;
    } else {
        markdownText = await response.text();
    }
    const bodyHtml = simpleMarkdownToHtml(markdownText);
    setTimeout(() => {
        const statusEl = document.getElementById(`modal-status-${modal.id}`);
        if (statusEl) statusEl.innerHTML = `<div class="markdown-body" id="update-markdown">${bodyHtml}</div>`;
    }, 100);
}


// ═══════════════════════════════════════════════════════════════════════════════
// 长按 W 键引导
// ═══════════════════════════════════════════════════════════════════════════════

(function () {
    let wPressed = false, wTimer = null;
    const LONG_PRESS_TIME = 1000;

    function onLongPressW() {
        const activeId = pagesManager ? pagesManager.activeId : null;
        if (activeId) showGuide(activeId);
    }

    function resetWState() { if (wTimer) { clearTimeout(wTimer); wTimer = null; } wPressed = false; }

    window.addEventListener('keydown', (e) => {
        if (e.code === 'KeyW' && !wPressed) {
            wPressed = true;
            wTimer = setTimeout(() => { onLongPressW(); wTimer = null; }, LONG_PRESS_TIME);
        }
    });
    window.addEventListener('keyup', (e) => { if (e.code === 'KeyW') resetWState(); });
    window.addEventListener('blur', resetWState);
})();


// ═══════════════════════════════════════════════════════════════════════════════
// 全局错误处理
// ═══════════════════════════════════════════════════════════════════════════════

function setupGlobalErrorHandling() {
    window.preApiErrors = [];
    window.preApiRejections = [];
    window.apiReady = false;

    window.addEventListener('error', function (event) {
        const msg = `[全局错误] ${event.message} at ${event.filename}:${event.lineno}:${event.colno}`;
        const stack = event.error && event.error.stack ? event.error.stack : '无堆栈信息';
        addLogMessage(msg, 'error'); addLogMessage(stack, 'error');
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.log && window.apiReady) {
            pywebview.api.log(`[前端错误] ${msg}\n堆栈: ${stack}`).catch(() => { });
        } else {
            window.preApiErrors.push({ message: msg, stack, timestamp: new Date().toISOString() });
        }
    });

    window.addEventListener('unhandledrejection', function (event) {
        const msg = `[未处理的Promise拒绝] ${event.reason}`;
        addLogMessage(msg, 'error');
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.log && window.apiReady) {
            pywebview.api.log(`[前端Promise错误] ${msg}`).catch(() => { });
        } else {
            window.preApiRejections.push({ message: msg, timestamp: new Date().toISOString() });
        }
    });
}


// ═══════════════════════════════════════════════════════════════════════════════
// 连接遮罩
// ═══════════════════════════════════════════════════════════════════════════════

function createConnectionMask() {
    const mask = document.createElement('div');
    mask.id = 'connection-mask';
    mask.className = 'connection-mask';
    mask.innerHTML = `<div class="mask-content"><div class="spinner"></div><div class="mask-text">正在连接到API...</div></div>`;
    document.body.appendChild(mask);
    const indicator = document.querySelector('.status-indicator');
    if (indicator) {
        const dot = indicator.querySelector('.status-dot');
        const text = indicator.querySelector('span');
        if (dot) dot.className = 'status-dot connecting';
        if (text) text.textContent = '连接中';
    }
}

function removeConnectionMask() {
    const mask = document.getElementById('connection-mask');
    if (mask) { mask.style.opacity = '0'; setTimeout(() => { if (mask.parentNode) mask.parentNode.removeChild(mask); }, 300); }
    const indicator = document.querySelector('.status-indicator');
    if (indicator) {
        const dot = indicator.querySelector('.status-dot');
        const text = indicator.querySelector('span');
        if (dot) dot.className = 'status-dot connected';
        if (text) text.textContent = '已连接';
    }
}


// ═══════════════════════════════════════════════════════════════════════════════
// 初始化入口
// ═══════════════════════════════════════════════════════════════════════════════

function init() {
    configManager = new ConfigManager();
    pagesManager = new PagesManager();
    themeManager = new ThemeManager();
    dragDropManager = new DragDropManager();
    setupDragDropCallback();
    initPasswordToggles();
    addLogMessage('系统已启动，准备就绪');
    addLogMessage('当前主题: ' + themeManager.currentTheme);
    addLogMessage('WebUI 初始化完成');
    createConnectionMask();
}

// DOM 就绪后初始化核心
document.addEventListener('DOMContentLoaded', () => {
    init();
    setupGlobalErrorHandling();
    loadAndRenderMarkdown();
});


// ═══════════════════════════════════════════════════════════════════════════════
// PyWebView 就绪后加载配置和插件
// ═══════════════════════════════════════════════════════════════════════════════

let first_use;

window.addEventListener('pywebviewready', function () {
    window.apiReady = true;
    addLogMessage('PyWebview API 已准备就绪', 'success');

    // 发送缓冲的错误
    if (window.preApiErrors && window.preApiErrors.length > 0) {
        addLogMessage(`正在发送 ${window.preApiErrors.length} 条之前捕获的错误信息...`, 'info');
        window.preApiErrors.forEach(err => {
            window.pywebview.api.log(`[前端错误][延迟发送] ${err.message}\n堆栈: ${err.stack}`).catch(() => { });
        });
        window.preApiErrors = [];
    }
    if (window.preApiRejections && window.preApiRejections.length > 0) {
        addLogMessage(`正在发送 ${window.preApiRejections.length} 条之前捕获的Promise拒绝信息...`, 'info');
        window.preApiRejections.forEach(rej => {
            window.pywebview.api.log(`[前端Promise错误][延迟发送] ${rej.message}`).catch(() => { });
        });
        window.preApiRejections = [];
    }

    removeConnectionMask();

    // 显示启动消息
    window.pywebview.api.get_attr('message_config')
        .then(msgConfig => {
            if (msgConfig && Array.isArray(msgConfig) && msgConfig.length === 2) {
                showMessage(msgConfig[0], msgConfig[1]);
            }
        });

    // 首次使用检查
    window.pywebview.api.get_attr('first_use').then(async (result) => {
        first_use = result;
        if (result) {
            await loadMarkdownContent('webui/assets/firstUse.md', 'welcome-content');
            goAndShow('welcome');
        }
    });

    // 初始化后端服务
    window.pywebview.api.run_func('change_icon').catch(e => console.log(e));
    window.pywebview.api.init_cache().catch(e => console.log(e));
    window.pywebview.api.set_attr('http_port', window.location.port);

    // 配置修复
    window.pywebview.api.get_attr('config_ok').then(configOk => {
        if (configOk === false) {
            window.pywebview.api.get_attr('config_error').then(configError => {
                let errMsg = "配置项格式错误，尝试修复?\n失败将会使用默认配置";
                if (configError && Array.isArray(configError) && configError.length > 0) {
                    errMsg += "\n\n详细错误信息:\n" + configError.join("\n");
                }
                addLogMessage(errMsg);
                window.pywebview.api.get_attr("config")
                    .then(config => window.pywebview.api.run_func('fix_config', config))
                    .then(fixed => window.pywebview.api.set_attr("config", fixed))
                    .then(() => window.pywebview.api.use_inner())
                    .catch(() => {
                        showMessage("错误", "修复配置时出错，使用默认配置");
                        window.pywebview.api.use_default().catch(() => { });
                    });
            });
        }
    }).catch(error => addLogMessage('检查配置时出错: ' + error, 'error'));

    // 加载配置和初始化插件系统
    window.pywebview.api.get_attr('config').then(config => {
        console.log('配置已加载到前端:', config);
        window.config = config;

        if (configManager) {
            setConfigToCache(config);
        }

        // 初始化插件加载器（获取 schema + 导航 + 构建侧边栏）
        pluginLoader.init().then(() => {
            // 应用配置到页面
            if (configManager) {
                configManager.applyConfigToPage();
            }

            // 游戏路径检查
            checkGamePath();

            // 自动更新检查
            const autoCheckUpdate = configManager.getCachedValue('auto_check_update');
            window.pywebview.api.init_github().then(() => {
                if (autoCheckUpdate && !first_use) {
                    if (typeof autoCheckUpdates === 'function') autoCheckUpdates();
                }
            });

            window.pywebview.api.init_log();

            // 主题
            const currentTheme = configManager.getCachedValue('theme') || 'light';
            themeManager.setTheme(currentTheme, true);

            // 插件 on_startup 钩子（由各插件 page.js 在注册时执行）
            window.pywebview.api.check_show().then(result => {
                if (result.show && !first_use) {
                    goAndShow('welcome');
                }
            });
        });
    });
});
