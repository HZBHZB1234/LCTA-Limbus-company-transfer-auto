// ============================
// 模态窗口系统与 UI 工具函数
// ============================

async function loadMarkdownContent(url, className) {
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
}

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
        loadMarkdownContent(url, className);
    });

    // 等待所有文件加载完成
    await Promise.allSettled(promises);
    
    console.log('所有Markdown文件加载完成');
    
  } catch (error) {
    console.error('加载Markdown文件过程中发生错误:', error);
  }
}

// 老年人模式切换相关代码

class ElderManager {
    // 向导步骤定义（页面key → 显示名 + 图标）
    static PAGE_ORDER = [
        { key: 'main',             label: '开始',       icon: 'fa-home' },
        { key: 'gamepath',         label: '游戏路径',   icon: 'fa-folder-open' },
        { key: 'character',        label: '功能选择',   icon: 'fa-list-check' },
        { key: 'base',             label: '基础设置',   icon: 'fa-cog' },
        { key: 'network',          label: '网络更新',   icon: 'fa-globe' },
        { key: 'launcher',         label: '启动器',     icon: 'fa-rocket' },
        { key: 'launcher-source',  label: '启动器来源', icon: 'fa-download' },
        { key: 'translate',        label: '翻译设置',   icon: 'fa-language' },
        { key: 'download',         label: '下载设置',   icon: 'fa-cloud-download-alt' },
        { key: 'bubble',           label: '气泡文本',   icon: 'fa-comment-dots' },
        { key: 'mod',              label: '模组',       icon: 'fa-puzzle-piece' },
        { key: 'manage',           label: '数据管理',   icon: 'fa-archive' },
        { key: 'final',            label: '完成',       icon: 'fa-flag-checkered' },
    ];

    async init() {
        this.targetDiv = document.querySelector('.quetion-content')
        this.updateList = await pywebview.api.get_attr('updateList');
        this.refer = await pywebview.api.get_attr('bindRefer');
        this.relyList = await pywebview.api.get_attr('relyList')
        const version = '5.0.0'
        this.version = version.replaceAll('.', '')
        let elderList = configManager.getCachedValue('elder_list');
        if (!elderList) {
            elderList = JSON.stringify(this.updateList);
            this.historyList = JSON.parse(elderList);
            for (const value of Object.keys(this.historyList)) {
                this.historyList[value] = 'new';
            }
        } else {
            this.historyList = JSON.parse(elderList);
            for (const value of Object.keys(this.updateList)) {
                if (this.historyList[value] === undefined) {
                    this.historyList[value] = 'new';
                }
            }
        }

        // 事件委托：处理 data-warn-uncheck 复选框警告
        this._setupEventDelegation();
    }

    _setupEventDelegation() {
        const contentEl = document.querySelector('.quetion-content');
        if (!contentEl) return;
        contentEl.addEventListener('change', (e) => {
            const target = e.target;
            if (target.type === 'checkbox' && target.dataset.warnUncheck) {
                if (!target.checked && typeof showMessage === 'function') {
                    showMessage(target.dataset.warnUncheck, '(ó﹏ò｡)');
                }
            }
        });
    }

    async initPage() {
        this.latestPage = 'main';
        await this.loadPage('main');
    }

    evalNextPage() {
        let hasShowFlag = false;
        let result = '';
        for (const value of Object.keys(this.historyList)) {
            if (!hasShowFlag) {
                if (value == this.latestPage) {
                    hasShowFlag = true;
                }
                continue;
            }
            if (this.historyList[value] == 'new' || this.historyList[value] < this.updateList[value]) {
                if (this.relyList[value].every(
                    (rely) => {
                        if (typeof(rely) == 'string') {
                            return configManager.getCachedValue(rely)
                        } else if (rely[0] == 'not'){
                            return !configManager.getCachedValue(rely[1]);
                        } else {
                            const targetValue = configManager.getCachedValue(rely[0]);
                            return rely.slice(1).some(
                                (relyValue) => targetValue == relyValue);
                        }
                    }
                )) {
                    result = value;
                    break;
                };
            }
        }
        return result;
    }

    async savePageRefer() {
        const pageRefer = this.refer[this.latestPage];
        if (!pageRefer) return;
        for (const value of Object.keys(pageRefer)) {
            const target = document.getElementById(value);
            if (!target) continue;
            let newValue;
            if (target.type === 'checkbox') {
                newValue = target.checked;
            } else if (target.tagName === 'SELECT' || target.tagName === 'INPUT') {
                newValue = target.value;
            }
            if (newValue !== undefined) {
                await configManager.updateConfigValue(pageRefer[value][0], newValue);
            }
        }
        this.historyList[this.latestPage] = this.version;
        configManager.updateConfigValue('--elder', JSON.stringify(this.historyList));
        await configManager.flushPendingUpdates();
    }

    async loadPageRefer() {
        const pageRefer = this.refer[this.latestPage];
        if (!pageRefer) return;
        for (const value of Object.keys(pageRefer)) {
            const target = document.getElementById(value);
            if (!target) continue;
            let newValue = configManager.getCachedValue(pageRefer[value][1]);
            if (target.type === 'checkbox') {
                target.checked = newValue;
            } else if (target.tagName === 'SELECT' || target.tagName === 'INPUT') {
                target.value = newValue;
            }
        }
    }

    async switchPage() {
        await this.savePageRefer();
        const nextPage = this.evalNextPage();
        if (nextPage) {
            this.latestPage = nextPage;
            await this.loadPage(nextPage);
            this.loadPageRefer();
        } else {
            this.latestPage = 'final';
            await this.loadPage('final');
        }
    }

    // 简化的 markdownPrefix：仅做文本直通，不再处理 script/version
    // 所有动态逻辑已移至 processVersionBadges() 和 renderPageDynamic()
    markdownPrefix(text, value='') {
        // 移除旧的 <version> 标签和 <script> 标签文本（兼容旧 markdown 文件）
        // 新文件使用 data-version 属性，此方法作为兼容层存在
        let processedText = text.replace(/<script>[\s\S]*?<\/script>/gi, '');
        processedText = processedText.replace(/<version>[\s\S]*?<\/version>/gi, '');
        return processedText;
    }

    // 处理 [data-version] 元素，注入 NEW 标记
    processVersionBadges(name) {
        const container = this.targetDiv;
        if (!container) return;
        const versionElements = container.querySelectorAll('[data-version]');
        versionElements.forEach(el => {
            const dataVer = el.getAttribute('data-version').trim();
            const num = parseFloat(dataVer);
            if (isNaN(num)) return;
            const historyVer = this.historyList[name];
            if (historyVer === 'new' || num > historyVer) {
                const badge = document.createElement('span');
                badge.className = 'elder-badge--new';
                badge.textContent = 'NEW';
                // 插入到元素内部的开头
                if (el.firstChild) {
                    el.insertBefore(badge, el.firstChild);
                } else {
                    el.appendChild(badge);
                }
            }
        });
    }

    // 页面特定动态渲染
    renderPageDynamic(name) {
        switch (name) {
            case 'main':
                this._renderMainPage();
                break;
            case 'final':
                this._renderFinalSummary();
                break;
            default:
                break;
        }
    }

    // main.md 三态面板逻辑
    _renderMainPage() {
        const panels = this.targetDiv.querySelectorAll('[data-state]');
        if (panels.length === 0) return;

        let activeState;
        if (typeof first_use !== 'undefined' && first_use) {
            activeState = 'first-use';
        } else if (this.evalNextPage()) {
            activeState = 'continue';
        } else {
            activeState = 'all-complete';
        }

        panels.forEach(panel => {
            if (panel.getAttribute('data-state') === activeState) {
                panel.style.display = 'block';
            } else {
                panel.style.display = 'none';
            }
        });
    }

    // final.md 摘要生成
    _renderFinalSummary() {
        const summaryDiv = document.getElementById('elder-summary');
        if (!summaryDiv) return;

        const items = [];

        // 游戏路径
        const gamePath = configManager.getCachedValue('game_path');
        if (gamePath) {
            items.push({ icon: 'fa-folder-open', title: '游戏路径', desc: gamePath });
        }

        // 功能选择
        if (configManager.getCachedValue('elder.character.base')) {
            items.push({ icon: 'fa-info-circle', title: '基础介绍', desc: '已阅读' });
        }
        if (configManager.getCachedValue('elder.character.launcher')) {
            const updateMap = {
                'no': '不自动更新',
                'llc': '零协 (LLC)',
                'ourplay': 'OurPlay',
                'LCTA-AU': 'LCTA-AU',
                'LO': 'LO',
                'LM-G': 'LM-G',
                'LM-A': 'LM-A',
            };
            const updateVal = configManager.getCachedValue('launcher.work.update') || 'LM-G';
            const updateLabel = updateMap[updateVal] || updateVal;
            const extras = [];
            if (configManager.getCachedValue('launcher.work.mod')) extras.push('MOD');
            if (configManager.getCachedValue('launcher.work.bubble')) extras.push('气泡文本');
            if (configManager.getCachedValue('launcher.work.fancy')) extras.push('文本美化');
            const extraStr = extras.length > 0 ? '（' + extras.join(' + ') + '）' : '';
            items.push({ icon: 'fa-rocket', title: '启动器模式', desc: '更新源：' + updateLabel + ' ' + extraStr });
        }
        if (configManager.getCachedValue('elder.character.translate')) {
            const translator = configManager.getCachedValue('ui_default.translator.translator') || '未设置';
            items.push({ icon: 'fa-language', title: '手动翻译', desc: '翻译服务：' + translator });
        }
        if (configManager.getCachedValue('elder.character.manage')) {
            items.push({ icon: 'fa-archive', title: '数据管理', desc: '已启用' });
        }

        // 基础设置
        if (configManager.getCachedValue('auto_check_update')) {
            items.push({ icon: 'fa-sync-alt', title: '自动检查更新', desc: '已启用' });
        }
        const theme = configManager.getCachedValue('theme') || 'light';
        const themeMap = { 'light': '亮色', 'dark': '暗色', 'purple': '紫色' };
        items.push({ icon: 'fa-palette', title: '主题', desc: themeMap[theme] || theme });

        if (items.length === 0) {
            items.push({ icon: 'fa-smile', title: '基础设置已完成', desc: '你可以随时在侧边栏探索更多功能' });
        }

        let html = '';
        items.forEach(item => {
            html += `<div class="elder-summary-item">
                <i class="fas ${item.icon}"></i>
                <div><strong>${item.title}</strong><span>${item.desc}</span></div>
            </div>`;
        });
        summaryDiv.innerHTML = html;
    }

    // 重置向导进度
    async resetElder() {
        let elderList = JSON.stringify(this.updateList);
        this.historyList = JSON.parse(elderList);
        for (const value of Object.keys(this.historyList)) {
            this.historyList[value] = 'new';
        }
        configManager.updateConfigValue('--elder', JSON.stringify(this.historyList));
        await configManager.flushPendingUpdates();
        await pywebview.api.resetElder();
        await configManager.reloadConfig();
        this.initPage();
    }

    // 更新步骤进度指示器
    updateProgress(name) {
        const fillBar = document.getElementById('elder-progress-fill');
        if (!fillBar) return;

        const steps = ElderManager.PAGE_ORDER;
        const currentIdx = steps.findIndex(s => s.key === name);
        if (currentIdx < 0) return;

        const pct = steps.length > 1 ? (currentIdx / (steps.length - 1)) * 100 : 0;
        fillBar.style.width = pct + '%';
    }

    async loadPage(name) {
        const response = await fetch(`elder/${name}.md`);

        if (!response.ok) {
            throw new Error(`加载 elder/${name}.md 失败: ${response.status} ${response.statusText}`);
        }

        const markdownText = await response.text();

        // 清空 elder-container
        try {
            document.getElementById('elder-container').innerHTML = '';
        } catch (error) {
            console.log('未找到id为elder-container的元素');
        }

        const htmlContent = simpleMarkdownToHtml(this.markdownPrefix(markdownText, name));
        this.targetDiv.innerHTML = htmlContent;

        // 后处理管线
        this.processVersionBadges(name);
        this.renderPageDynamic(name);
        this.updateProgress(name);

        console.log(`成功加载并渲染: ${name}`);
    }
}

elderManager = new ElderManager();

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
    const result = await pywebview.api.toggle_installed_package(checkbox.checked);
    toggleCustomLangGui();
    if (result.success && result.changed && checkbox.checked) {
        refreshInstalledPackageList();
    }
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

function goCleanSection(DIEPLAY){
    const testButton = document.getElementById('clean-btn');
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
async function browseInstallPackageDirectory() {
    const result = await pywebview.api.browse_folder('install-package-directory');
    const packageDirInput = document.getElementById('install-package-directory');
    if (packageDirInput && result) {
        packageDirInput.value = result;
        await configManager.updateConfigValue('install-package-directory', result);
        await configManager.flushPendingUpdates();
        refreshInstallPackageList();
    }
}

// 清空汉化包目录输入框
async function clearPackageDirectory() {
    const packageDirInput = document.getElementById('install-package-directory');
    if (packageDirInput) {
        packageDirInput.value = '';
        await configManager.updateConfigValue('install-package-directory', '');
        await configManager.flushPendingUpdates();
        refreshInstallPackageList();
    }
}

// 浏览安装界面的汉化包目录
function browseInstallModDirectory() {
    pywebview.api.browse_folder('installed-mod-directory').then(async function(result) {
        const modDirInput = document.getElementById('installed-mod-directory');
        if (modDirInput && result) {
            modDirInput.value = result;
            await configManager.updateConfigValue('installed-mod-directory', result);
            await configManager.flushPendingUpdates();
            refreshInstalledModList();
        }
    }).catch(function(error) {
        showMessage('错误', '浏览文件夹时发生错误: ' + error);
    });
}

// 清空汉化包目录输入框
async function clearModDirectory() {
    const modDirInput = document.getElementById('installed-mod-directory');
    if (modDirInput) {
        modDirInput.value = '';
        await configManager.updateConfigValue('installed-mod-directory', '');
        await configManager.flushPendingUpdates();
        refreshInstalledModList();
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
        this.percent = 0
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
        this.updateProgress(0);
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
        this.percent = percent
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
        this.syncProgressToMinimized(this.percent);
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
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.set_modal_running) {
            pywebview.api.set_modal_running(this.id, 'cancel')
                .catch(function(error) {
                    console.error('处理取消操作失败:', error);
                });
        }
        
        super.cancel();
    }
    
    pause() {
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.set_modal_running) {
            pywebview.api.set_modal_running(this.id, 'pause')
                .catch(function(error) {
                    console.error('处理暂停操作失败:', error);
                });
        }
        
        super.pause();
    }
    
    resume() {
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.set_modal_running) {
            pywebview.api.set_modal_running(this.id, 'running')
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

