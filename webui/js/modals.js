// ============================
// 模态窗口系统与 UI 工具函数
// ============================

const _loadedMarkdowns = {};

// === 轻量提示 Toast ===
// 用于无需用户确认的即时反馈（成功/失败/信息）。
// 需要确认或展示详细错误时仍使用 showMessage / showConfirm。
const toastContainerRef = { element: null };

function getToastContainer() {
    if (toastContainerRef.element && document.body.contains(toastContainerRef.element)) {
        return toastContainerRef.element;
    }
    const container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
    toastContainerRef.element = container;
    return container;
}

function showToast(message, type = 'info', duration = 2800) {
    if (!message) return;
    const container = getToastContainer();
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    const icons = { success: 'fa-circle-check', error: 'fa-circle-exclamation', info: 'fa-circle-info' };
    toast.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i><span></span>`;
    toast.querySelector('span').textContent = message;

    container.appendChild(toast);
    // 强制重排后触发进场动画
    requestAnimationFrame(() => toast.classList.add('visible'));

    const hide = () => {
        if (!toast.isConnected) return;
        toast.classList.remove('visible');
        toast.classList.add('hiding');
        setTimeout(() => toast.remove(), 300);
    };

    const timer = setTimeout(hide, duration);
    // 点击提前关闭
    toast.addEventListener('click', () => {
        clearTimeout(timer);
        hide();
    });
    return toast;
}

async function loadMarkdownContent(url, className) {
    try {
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error(`加载 ${url} 失败: ${response.status} ${response.statusText}`);
        }
        
        const markdownText = await response.text();
        
        if (typeof simpleMarkdownToHtml !== 'function') {
            throw new Error('simpleMarkdownToHtml函数未定义');
        }
        
        const htmlContent = simpleMarkdownToHtml(markdownText);
        
        const targetDiv = document.querySelector(`.${className}`);
        
        if (!targetDiv) {
            console.warn(`未找到class为${className}的元素`);
            return;
        }
        
        targetDiv.innerHTML = htmlContent;
        _loadedMarkdowns[url] = true;
        
        console.log(`成功加载并渲染: ${url}`);
        
    } catch (error) {
        console.error(`处理 ${url} 时出错:`, error);
        const targetDiv = document.querySelector(`.${className}`);
        if (targetDiv) {
            targetDiv.innerHTML = `<p class="error">加载内容失败: ${error.message}</p>`;
        }
    }
}

function isMarkdownLoaded(url) {
    return !!_loadedMarkdowns[url];
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
        return loadMarkdownContent(url, className);
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
    if (!enableCacheCheckbox || !cachePathGroup) return;
    
    if (enableCacheCheckbox.checked) {
        cachePathGroup.style.display = 'block';
    } else {
        cachePathGroup.style.display = 'none';
    }
}

function toggleStoragePathInput() {
    const enableStorageCheckbox = document.getElementById('enable-storage');
    const storagePathGroup = document.getElementById('storage-path-group');
    if (!enableStorageCheckbox || !storagePathGroup) return;
    
    if (enableStorageCheckbox.checked) {
        storagePathGroup.style.display = 'block';
    } else {
        storagePathGroup.style.display = 'none';
    }
}

function toggleDevelopSettings() {
    const group = document.getElementById('dev-settings');
    const enable = document.getElementById('enable-dev-settings');
    if (!group || !enable) return;
    if (enable.checked) {
        group.style.display = 'block';
    } 
    else {
        group.style.display = 'none';
    }
};

async function toggleCustomLang() {
    const checkbox = document.getElementById('enable-lang');
    if (!checkbox) return;
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
                <p>自定义汉化已禁用</p>
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
    if (!group || !enable) return;
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
    if (!group || !enable) return;
    if (enable.checked) {
        group.style.display = 'none';
    } 
    else {
        group.style.display = 'block';
    }
};

function toggleSteamCommand() {
    const cmdElement = document.getElementById('steam-cmd');
    if (!cmdElement) return;
    let command
    pywebview.api.run_func('get_steam_command').then(function(result) {
        command=result;
        cmdElement.value = command;
    }).catch(function(error) {
        command=`获取失败 ${error}`;
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
    navigator.clipboard.writeText(cmdElement.value).then(function() {
        if (typeof showToast === 'function') showToast('Steam 启动命令已复制到剪贴板', 'success');
    }).catch(function() {
        if (typeof showToast === 'function') showToast('复制失败，请手动复制', 'error');
    });
}

function steamLauncherStateText(status) {
    if (!status || !status.localconfig_path) return '未定位到 Steam 配置，请确认已安装 Steam 并登录过账号。';
    switch (status.state) {
        case 'lcta_current': return '已配置当前 LCTA 启动项';
        case 'lcta_stale': return '已配置 LCTA 启动项（非当前）';
        case 'lcta': return '已配置 LCTA 启动项';
        case 'other': return '已配置启动项（非 LCTA）';
        case 'unconfigured': return '当前未配置启动项';
        default: return '未定位到 Steam 配置';
    }
}

async function refreshSteamLauncherStatus() {
    const statusEl = document.getElementById('steam-launcher-status');
    if (!statusEl) return;
    try {
        const status = await pywebview.api.run_func('get_steam_launcher_status');
        statusEl.textContent = steamLauncherStateText(status);
    } catch (error) {
        statusEl.textContent = '获取Steam启动器状态失败';
    }
}

async function applySteamLaunchOptions() {
    let status;
    try {
        status = await pywebview.api.run_func('get_steam_launcher_status');
    } catch (error) {
        showMessage('错误', '获取Steam启动器状态失败: ' + error);
        return;
    }
    if (!status || !status.localconfig_path) {
        showMessage('提示', '无法定位 Steam localconfig.vdf，请确认已安装 Steam 并登录过账号。');
        return;
    }
    if (status.steam_running) {
        showConfirm('Steam 正在运行',
            'Steam 正在运行，其退出时可能覆盖 localconfig.vdf 的修改。建议先关闭 Steam 再写入。\n\n是否仍要继续？',
            function() { doApplySteamLaunchOptions(status); });
        return;
    }
    doApplySteamLaunchOptions(status);
}

function doApplySteamLaunchOptions(status) {
    pywebview.api.run_func('get_steam_command').then(function(command) {
        showConfirm('写入Steam启动选项',
            '当前状态：' + steamLauncherStateText(status) +
            '\n\n将写入 LCTA 启动命令。\n\n写入前会自动备份原文件（localconfig.vdf.lcta.bak），确认继续？',
            function() {
                pywebview.api.run_func('set_steam_launch_options', command).then(function(result) {
                    if (result && result.success) {
                        showMessage('成功', result.message);
                    } else {
                        showMessage('失败', '写入失败: ' + (result ? result.message : '未知错误'));
                    }
                    refreshSteamLauncherStatus();
                }).catch(function(error) {
                    showMessage('失败', '写入失败: ' + error);
                });
            });
    }).catch(function(error) {
        showMessage('失败', '获取Steam命令失败: ' + error);
    });
}

async function clearSteamLaunchOptions() {
    let status;
    try {
        status = await pywebview.api.run_func('get_steam_launcher_status');
    } catch (error) {
        showMessage('错误', '获取Steam启动器状态失败: ' + error);
        return;
    }
    if (!status || !status.localconfig_path) {
        showMessage('提示', '无法定位 Steam localconfig.vdf，请确认已安装 Steam 并登录过账号。');
        return;
    }
    if (!status.current_launch_options) {
        showMessage('提示', '当前未配置 Steam 启动选项，无需清除。');
        return;
    }
    if (status.steam_running) {
        showConfirm('Steam 正在运行',
            'Steam 正在运行，其退出时可能覆盖 localconfig.vdf 的修改。建议先关闭 Steam 再清除。\n\n是否仍要继续？',
            function() { doClearSteamLaunchOptions(status); });
        return;
    }
    doClearSteamLaunchOptions(status);
}

function doClearSteamLaunchOptions(status) {
    showConfirm('清除Steam启动选项',
        '当前状态：' + steamLauncherStateText(status) +
        '\n\n将清除 Steam 启动选项，恢复为默认直接启动游戏。\n\n清除前会自动备份原文件（localconfig.vdf.lcta.bak），确认继续？',
        function() {
            pywebview.api.run_func('clear_steam_launch_options').then(function(result) {
                if (result && result.success) {
                    showMessage('成功', result.message);
                } else {
                    showMessage('失败', '清除失败: ' + (result ? result.message : '未知错误'));
                }
                refreshSteamLauncherStatus();
            }).catch(function(error) {
                showMessage('失败', '清除失败: ' + error);
            });
        });
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
        percent = Math.max(0, Math.min(100, Number(percent) || 0));
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
        
        if (mainProgressFill && mainProgressPercent && progressContainer) {
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
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.del_modal_list) {
            pywebview.api.del_modal_list(this.id).catch(function(error) {
                console.error('删除模态窗口ID失败:', error);
            });
        }
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

// ============================
// 首次翻译提示：优先引导使用 LCTA-AU 现成汉化包
// ============================
// 自行翻译需要自备 API 密钥（可能产生费用）并等待整包跑完；作者已通过 LCTA-AU
// 每隔约一小时自动检测新版汉化包并完成翻译发布，直接下载安装即可、无需配置。
// 首次点击「开始翻译」时先给出这条提示，避免用户在不知情的情况下花了钱和时间。
// 看过一次后不再打断 —— 状态持久化在 ui_default.translator.au_hint_shown。

const TRANSLATE_AU_HINT_KEY = 'ui_default.translator.au_hint_shown';

// LCTA-AU 项目主页与作者赞助页（与 markdown 渲染器一致，外链交由系统浏览器打开）
const TRANSLATE_AU_REPO_URL = 'https://github.com/HZBHZB1234/LCTA_auto_update';
const TRANSLATE_AU_SPONSOR_URL = 'https://afdian.com/a/LCTAs';

const TRANSLATE_AU_HINT_HTML = `
    <div class="disclaimer-body" style="margin:0;">
        <p style="margin:0 0 0.75rem;">
            自己翻译需要你先在「配置汉化API」里填好自己的密钥（<strong>通常会产生费用</strong>），
            再等整包文本跑完。其实<strong>作者已经把汉化包翻译好并发布了</strong> ——
            LCTA-AU 会每隔约一小时自动检测新版汉化包并完成翻译发布，
            下载安装即可，<strong>无需任何配置、无需密钥</strong>。
        </p>

        <p class="risk-section-title">如何用 LCTA-AU（约 1 分钟）</p>
        <ol style="margin:0.25rem 0 0.75rem 1.2rem; padding:0;">
            <li>左侧进入「汉化包下载」，找到 <strong>LCTA-AU下载配置</strong> 卡片。</li>
            <li>「文本下载来源」选 <strong>从github下载</strong>（GitHub 访问不稳可改「从公益镜像下载」），
                并勾选「使用代理加速下载」。</li>
            <li>点击 <strong>下载LCTA-AU汉化包</strong>，等待下载完成。</li>
            <li>到「安装已有汉化」页面安装刚下载好的汉化包。</li>
            <li>（可选）「Launcher配置」把更新模式设为 <strong>零协 + LCTA-AU（GitHub 源）</strong>，
                以后通过 Launcher 启动游戏时自动更新汉化。</li>
        </ol>

        <p class="risk-section-title">项目与支持</p>
        <ul>
            <li>LCTA-AU 仓库：<a href="${TRANSLATE_AU_REPO_URL}" target="_blank" rel="noopener noreferrer">${TRANSLATE_AU_REPO_URL}</a></li>
            <li>赞助作者（爱发电）：<a href="${TRANSLATE_AU_SPONSOR_URL}" target="_blank" rel="noopener noreferrer">${TRANSLATE_AU_SPONSOR_URL}</a></li>
        </ul>

        <p style="margin:0.5rem 0 0; font-size:0.85rem; opacity:0.85;">
            如果你确实需要自己翻译（例如要自定义译文或做私人改动），可直接继续。
            此提示只出现一次，之后可在「开始翻译」旁的入口再次查看。
        </p>
    </div>`;

// 读取「已提示过」状态（API 优先，失败回退前端配置缓存）
async function isTranslateAuHintShown() {
    try {
        const value = await pywebview.api.get_config_value(TRANSLATE_AU_HINT_KEY, false);
        return !!value;
    } catch (e) {
        console.error('读取翻译引导提示状态失败:', e);
    }
    try {
        if (typeof configManager !== 'undefined') {
            return !!configManager.getCachedValue(TRANSLATE_AU_HINT_KEY);
        }
    } catch (e) { /* ignore */ }
    return false;
}

// 标记「已提示过」并同步前端缓存
async function markTranslateAuHintShown() {
    try {
        await pywebview.api.update_config_value(TRANSLATE_AU_HINT_KEY, true);
        if (typeof configManager !== 'undefined') {
            configManager.setCachedValue(TRANSLATE_AU_HINT_KEY, true);
        }
    } catch (e) {
        console.error('保存翻译引导提示状态失败:', e);
    }
}

// 展示引导弹窗。onContinue 仅在用户明确选择「我仍要自行翻译」时回调；
// onDismiss 在用户关闭/取消时回调（两者最多触发一次）。
// showContinue=false 时为「重看说明」入口，不提供继续翻译的按钮。
function showTranslateAuHint(onContinue, onDismiss, showContinue = true) {
    const modal = new ModalWindow('先看看现成的汉化包？', {
        showProgress: false,
        showCancelButton: false,
        showMinimizeButton: false,
        showLog: false,
    });

    // settled 兼作两件事：① 三个出口互斥（重复点击无效）② 结果只落一次。
    // finish(continued) 统一收口：必须先置 settled 再关窗，保证 dismissed/continued
    // 恰好触发一次；否则 Promise 永不落定，调用方 await 会一直挂住。
    let settled = false;
    const finish = (continued) => {
        if (settled) return;
        settled = true;
        modal.close();
        if (continued) {
            if (typeof onContinue === 'function') onContinue();
        } else if (typeof onDismiss === 'function') {
            onDismiss();
        }
    };
    // 标题栏 × 走 ModalWindow 原生关闭，兜住「关闭」语义
    const originalClose = modal.close.bind(modal);
    modal.close = function () {
        originalClose();
        if (!settled) {
            settled = true;
            if (typeof onDismiss === 'function') onDismiss();
        }
    };

    const statusEl = document.getElementById(`modal-status-${modal.id}`);
    if (statusEl) {
        statusEl.classList.add('risk-modal-scroll');
        statusEl.innerHTML = TRANSLATE_AU_HINT_HTML;
    }

    const footer = document.getElementById(`modal-footer-${modal.id}`);
    if (!footer) return modal;
    footer.innerHTML = `
        <button class="primary-btn" id="au-hint-download-${modal.id}">
            <i class="fas fa-download"></i> 前往下载 LCTA-AU 汉化包
        </button>
        ${showContinue ? `<button class="action-btn" id="au-hint-continue-${modal.id}">我仍要自行翻译</button>` : ''}
        <button class="action-btn" id="au-hint-close-${modal.id}">关闭</button>`;

    document.getElementById(`au-hint-download-${modal.id}`).addEventListener('click', async () => {
        if (settled) return;
        await markTranslateAuHintShown();
        finish(false);                       // 去下载 = 本次不启动翻译
        // 直达下载页的 LCTA-AU 卡片（锚点高亮）
        if (typeof goAndShow === 'function') goAndShow('download', 'dl-card-lcta-au');
    });

    const continueBtn = document.getElementById(`au-hint-continue-${modal.id}`);
    if (continueBtn) {
        continueBtn.addEventListener('click', async () => {
            if (settled) return;
            await markTranslateAuHintShown();
            finish(true);
        });
    }

    document.getElementById(`au-hint-close-${modal.id}`).addEventListener('click', () => {
        finish(false);
    });

    return modal;
}

// 开始翻译前的引导门控：已看过则直接放行；否则弹窗，用户明确继续才返回 true。
// 关闭弹窗 / 选择去下载都返回 false（本次不启动翻译）。
async function checkTranslateAuHint() {
    if (await isTranslateAuHintShown()) return true;
    return await new Promise(resolve => {
        showTranslateAuHint(() => resolve(true), () => resolve(false));
    });
}

// 「重看说明」入口：只展示内容，不改变已读状态，也不触发翻译
function showTranslateAuHintAgain() {
    showTranslateAuHint(null, null, false);
}

// 各功能函数
async function startTranslation() {
    // 首次点击先引导：作者已通过 LCTA-AU 发布现成汉化包，可能无需自行翻译
    const proceed = await checkTranslateAuHint();
    if (!proceed) return;

    const modal = new ProgressModal('开始翻译');
    modal.setStatus('正在初始化翻译过程...');
    modal.addLog('开始翻译任务');
    try {
        await configManager.updateConfigValues(configManager.collectConfigFromUI());
    } catch (error) {
        modal.complete(false, '配置保存失败: ' + error);
        return;
    }
    
    pywebview.api.start_translation(apiConfigManager.currentSettings,
        modal.id).then(function(result) {
        if (result && result.message === '已取消') {
            modal.cancel();
        } else if (result.success) {
            modal.complete(true, '翻译任务已完成');
        } else {
            modal.complete(false, '翻译失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '翻译过程中发生错误: ' + error);
    });
}

