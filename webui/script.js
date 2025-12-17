// 主题管理
class ThemeManager {
    constructor() {
        this.currentTheme = localStorage.getItem('lcta-theme') || 'light';
        this.isTransitioning = false; // 添加过渡状态标志
        this.pendingTheme = null; // 存储待处理的主题
        this.debounceTimer = null; // 防抖计时器
        this.debounceDelay = 300; // 防抖延迟时间
        this.init();
    }
    
    init() {
        // 设置初始主题
        this.setTheme(this.currentTheme, true); // 初始化时不使用防抖
        
        // 绑定主题按钮事件
        document.querySelectorAll('.theme-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const theme = e.target.dataset.theme || e.target.closest('.theme-btn').dataset.theme;
                this.setThemeWithDebounce(theme);
            });
        });
    }
    
    // 带防抖功能的主题设置方法
    setThemeWithDebounce(theme) {
        // 添加视觉反馈
        const clickedBtn = [...document.querySelectorAll('.theme-btn')].find(btn => btn.dataset.theme === theme);
        if (clickedBtn) {
            clickedBtn.classList.add('changing');
            setTimeout(() => {
                clickedBtn.classList.remove('changing');
            }, 300);
        }
        
        // 清除之前的定时器
        if (this.debounceTimer) {
            clearTimeout(this.debounceTimer);
        }
        
        // 设置新的定时器
        this.debounceTimer = setTimeout(() => {
            this.setTheme(theme);
        }, this.debounceDelay);
    }
    
    setTheme(theme, skipDebounce = false) {
        // 如果正在过渡中，存储待处理的主题
        if (this.isTransitioning) {
            this.pendingTheme = theme;
            return;
        }
        
        // 如果点击的是当前主题，直接返回
        if (this.currentTheme === theme) {
            return;
        }
        
        // 设置过渡状态
        this.isTransitioning = true;
        document.body.classList.add('theme-transition');
        
        // 移除所有主题类
        document.body.classList.remove('theme-light', 'theme-dark', 'theme-purple');
        
        // 添加新主题类
        document.body.classList.add(`theme-${theme}`);
        
        // 更新当前主题
        this.currentTheme = theme;
        
        // 保存到本地存储
        localStorage.setItem('lcta-theme', theme);
        
        // 更新按钮状态
        this.updateThemeButtons(theme);
        
        // 添加主题切换动画
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
        // 使用setTimeout确保样式变化能够正确触发过渡动画
        setTimeout(() => {
            // 移除过渡效果
            document.body.classList.remove('theme-transition');
            this.isTransitioning = false;
            
            // 如果有待处理的主题，处理它
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
    static fadeIn(element, duration = 150) { // 默认加快动画速度
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
    
    static fadeOut(element, duration = 150) { // 默认加快动画速度
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
    
    static slideIn(element, from = 'left', duration = 150) { // 默认加快动画速度
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

// 初始化主题管理器
let themeManager;

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
        container.style.top = '80px'; // 增加与顶部的距离，避免与主题切换按钮重叠
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
            // 如果点击的是已经激活的按钮，则不执行任何操作
            if (button.classList.contains('active')) {
                return;
            }
            
            // 移除所有按钮的active类
            document.querySelectorAll('.nav-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            
            // 移除所有指示器
            document.querySelectorAll('.nav-indicator').forEach(indicator => {
                indicator.remove();
            });
            
            // 添加active类到当前按钮
            button.classList.add('active');
            
            // 添加指示器
            const indicator = document.createElement('div');
            indicator.className = 'nav-indicator';
            button.appendChild(indicator);
            
            // 隐藏所有内容区域
            document.querySelectorAll('.content-section').forEach(section => {
                if (section.classList.contains('active')) {
                    AnimationManager.fadeOut(section, 150); // 加快动画速度
                    setTimeout(() => {
                        section.classList.remove('active');
                    }, 150); // 加快动画速度
                }
            });
            
            // 显示对应的内容区域
            const sectionId = button.id.replace('-btn', '-section');
            const section = document.getElementById(sectionId);
            if (section) {
                setTimeout(() => {
                    section.classList.add('active');
                    AnimationManager.fadeIn(section, 150); // 加快动画速度
                    
                    // 如果是设置界面，加载设置
                    if (sectionId === 'settings-section') {
                        loadSettings();
                    }
                    
                    // 如果是日志界面，滚动到底部
                    if (sectionId === 'log-section') {
                        scrollLogToBottom();
                    }
                    
                    // 如果是安装汉化包界面，刷新包列表
                    if (sectionId === 'install-section') {
                        // 先保存目录设置再刷新列表
                        const packageDirInput = document.getElementById('install-package-directory');
                        if (packageDirInput) {
                            const packageDirValue = packageDirInput.value;
                            pywebview.api.update_config_value('ui_default.install.package_directory', packageDirValue)
                                .then(function(success) {
                                    if (success) {
                                        refreshInstallPackageList();
                                    } else {
                                        showMessage('错误', '保存汉化包目录设置失败');
                                    }
                                })
                                .catch(function(error) {
                                    showMessage('错误', '保存汉化包目录设置时发生错误: ' + error);
                                });
                        } else {
                            refreshInstallPackageList();
                        }
                    }
                }, 150); // 加快动画速度
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

// 添加一个新的函数用于浏览汉化包目录
function browsePackageDirectory() {
    pywebview.api.browse_folder('package-directory').then(function(result) {
        // 更新配置
        const packageDirInput = document.getElementById('package-directory');
        if (packageDirInput && packageDirInput.value) {
            pywebview.api.update_config_value('ui_default.install.package_directory', packageDirInput.value)
                .then(function(success) {
                    if (success) {
                        // 刷新汉化包列表
                        refreshPackageList();
                    } else {
                        showMessage('错误', '更新配置失败');
                    }
                })
                .catch(function(error) {
                    showMessage('错误', '更新配置时发生错误: ' + error);
                });
        }
    }).catch(function(error) {
        showMessage('错误', '浏览文件夹时发生错误: ' + error);
    });
}

// 添加一个新的函数用于浏览安装界面的汉化包目录
function browseInstallPackageDirectory() {
    pywebview.api.browse_folder('install-package-directory').then(function(result) {
        // 更新配置
        const packageDirInput = document.getElementById('install-package-directory');
        if (packageDirInput && packageDirInput.value) {
            pywebview.api.update_config_value('ui_default.install.package_directory', packageDirInput.value)
                .then(function(success) {
                    if (success) {
                        // 刷新汉化包列表
                        refreshInstallPackageList();
                    } else {
                        showMessage('错误', '更新配置失败');
                    }
                })
                .catch(function(error) {
                    showMessage('错误', '更新配置时发生错误: ' + error);
                });
        }
    }).catch(function(error) {
        showMessage('错误', '浏览文件夹时发生错误: ' + error);
    });
}

// 添加清空汉化包目录输入框的函数
function clearPackageDirectory() {
    const packageDirInput = document.getElementById('install-package-directory');
    if (packageDirInput) {
        packageDirInput.value = '';
        // 更新配置
        pywebview.api.update_config_value('ui_default.install.package_directory', '')
            .then(function(success) {
                if (success) {
                    // 刷新汉化包列表
                    refreshInstallPackageList();
                } else {
                    showMessage('错误', '更新配置失败');
                }
            })
            .catch(function(error) {
                showMessage('错误', '更新配置时发生错误: ' + error);
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
        
        // 获取当前主题以便应用正确的样式
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
        
        // 绑定事件
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
        
        // 更新主界面的进度条
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
        
        // 注册模态ID到后端
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
        // 调用后端API处理取消操作
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.handle_modal_cancel) {
            pywebview.api.handle_modal_cancel(this.id)
                .catch(function(error) {
                    console.error('处理取消操作失败:', error);
                });
        }
        
        // 调用父类的取消方法
        super.cancel();
    }
    
    pause() {
        // 调用后端API处理暂停操作
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.handle_modal_pause) {
            pywebview.api.handle_modal_pause(this.id)
                .catch(function(error) {
                    console.error('处理暂停操作失败:', error);
                });
        }
        
        // 调用父类的暂停方法
        super.pause();
    }
    
    resume() {
        // 调用后端API处理恢复操作
        if (typeof pywebview !== 'undefined' && pywebview.api && pywebview.api.handle_modal_resume) {
            pywebview.api.handle_modal_resume(this.id)
                .catch(function(error) {
                    console.error('处理恢复操作失败:', error);
                });
        }
        
        // 调用父类的恢复方法
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
    
    // 显示主界面进度条
    const progressContainer = document.getElementById('translation-progress');
    progressContainer.style.display = 'block';
    
    // 调用后端API进行实际翻译
    pywebview.api.start_translation(modal.id).then(function(result) {
        if (result.success) {
            modal.complete(true, '翻译任务已完成');
        } else {
            modal.complete(false, '翻译失败: ' + result.message);
        }
        
        // 隐藏主界面进度条
        setTimeout(() => {
            progressContainer.style.display = 'none';
        }, 2000);
    }).catch(function(error) {
        modal.complete(false, '翻译过程中发生错误: ' + error);
        
        // 隐藏主界面进度条
        setTimeout(() => {
            progressContainer.style.display = 'none';
        }, 2000);
    });
}

function refreshPackageList() {
    const packageList = document.getElementById('install-package-list');
    if (!packageList) return;
    
    packageList.innerHTML = '<div class="loading">正在加载...</div>';
    
    // 调用后端API获取汉化包列表
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
    // 显示加载状态
    const packageList = document.getElementById('install-package-list');
    if (!packageList) return;
    
    // 获取汉化包目录输入框的值并自动保存
    const packageDirInput = document.getElementById('install-package-directory');
    if (packageDirInput) {
        const packageDirValue = packageDirInput.value;
        pywebview.api.update_config_value('ui_default.install.package_directory', packageDirValue)
            .then(function(success) {
                if (!success) {
                    showMessage('错误', '保存汉化包目录设置失败');
                }
            })
            .catch(function(error) {
                showMessage('错误', '保存汉化包目录设置时发生错误: ' + error);
            });
    }
    
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
                    
                    // 使用addEventListener替代onclick属性，避免潜在的表单提交问题
                    const selectButton = packageItem.querySelector('.list-action-btn');
                    selectButton.addEventListener('click', function(e) {
                        e.preventDefault(); // 阻止任何可能的默认行为
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
    // 移除所有项目的选中状态
    document.querySelectorAll('.list-item').forEach(item => {
        item.classList.remove('selected');
        item.removeAttribute('data-selected');
    });
    
    // 查找并高亮选中的包
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
    
    // 调用后端API进行实际安装
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
    
    // 调用后端API获取系统字体列表
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
                        // 高亮选中项
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
                
                // 搜索功能
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
            
            // 添加确定按钮
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
                
                // 调用后端API进行实际字体更换
                pywebview.api.export_selected_font(fontName, "") // 目标路径将在后端处理
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
                modal.setCompleted(); // 确保调用setCompleted方法
            };
            footer.appendChild(cancelBtn);
        })
        .catch(function(error) {
            showMessage('错误', '获取系统字体列表时发生错误: ' + error);
        });
}

function getFontFromInstalled() {
    // 调用后端API获取系统字体列表
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
                        // 高亮选中项
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
                
                // 搜索功能
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
            
            // 添加导出按钮
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
                
                // 选择导出路径
                pywebview.api.browse_folder('font-export-path')
                    .then(function(result) {
                        if (result && result.length > 0) {
                            const exportPath = result[0];
                            
                            modal.close();
                            
                            const progressModal = new ProgressModal('导出字体');
                            progressModal.addLog(`开始导出字体 "${fontName}" 到 "${exportPath}"`);
                            
                            // 调用后端API进行实际字体导出
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
                modal.setCompleted(); // 确保调用setCompleted方法
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
            // 调用后端API进行实际删除
            pywebview.api.delete_translation_package(packageName).then(function(result) {
                if (result.success) {
                    selectedItem.style.opacity = '0.5';
                    selectedItem.style.textDecoration = 'line-through';
                    
                    setTimeout(() => {
                        selectedItem.remove();
                        
                        // 检查是否还有包
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
    
    const modal = new ProgressModal('抓取专有词汇');
    modal.addLog('开始抓取专有词汇...');
    modal.addLog(`输出格式: ${outputFormat}`);
    modal.addLog(`跳过含空格词汇: ${skipSpace ? '是' : '否'}`);
    if (maxCount) {
        modal.addLog(`最大词汇数量: ${maxCount}`);
    }
    
    // 调用后端API进行实际抓取
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
}

function searchText() {
    const keyword = document.getElementById('search-keyword').value;
    const searchPath = document.getElementById('search-path').value;
    const caseSensitive = document.getElementById('search-case-sensitive').checked;
    
    if (!keyword) {
        showMessage('提示', '请输入搜索关键词');
        return;
    }
    
    const modal = new ProgressModal('文本搜索');
    modal.addLog('开始文本搜索...');
    modal.addLog(`关键词: ${keyword}`);
    if (searchPath) {
        modal.addLog(`搜索路径: ${searchPath}`);
    }
    modal.addLog(`区分大小写: ${caseSensitive ? '是' : '否'}`);
    
    // 调用后端API进行实际搜索
    pywebview.api.search_text(modal.id)
        .then(function(result) {
            if (result.success) {
                modal.complete(true, '文本搜索完成');
                // 显示搜索结果
                showSearchResults(result.results);
            } else {
                modal.complete(false, '搜索失败: ' + result.message);
            }
        })
        .catch(function(error) {
            modal.complete(false, '搜索过程中发生错误: ' + error);
        });
}

function showSearchResults(results) {
    const resultsContainer = document.getElementById('search-results');
    if (!resultsContainer) return;
    
    if (!results || results.length === 0) {
        resultsContainer.innerHTML = `
            <div class="results-placeholder">
                <i class="fas fa-search"></i>
                <p>未找到匹配的结果</p>
            </div>
        `;
        return;
    }
    
    let html = '<div class="search-results-list">';
    results.forEach(result => {
        html += `
            <div class="search-result-item">
                <div class="result-header">
                    <span class="result-file">${result.file}</span>
                    <span class="result-line">第 ${result.line} 行</span>
                </div>
                <div class="result-content">${result.content}</div>
            </div>
        `;
    });
    html += '</div>';
    
    resultsContainer.innerHTML = html;
}

function backupText() {
    const sourcePath = document.getElementById('backup-source').value;
    const destPath = document.getElementById('backup-destination').value;
    
    if (!sourcePath) {
        showMessage('提示', '请选择源文件路径');
        return;
    }
    
    if (!destPath) {
        showMessage('提示', '请选择备份保存路径');
        return;
    }
    
    const modal = new ProgressModal('备份原文');
    modal.addLog('开始备份原文...');
    modal.addLog(`源路径: ${sourcePath}`);
    modal.addLog(`目标路径: ${destPath}`);
    
    // 调用后端API进行实际备份
    pywebview.api.backup_text(modal.id)
        .then(function(result) {
            if (result.success) {
                modal.complete(true, '原文备份成功');
            } else {
                modal.complete(false, '备份失败: ' + result.message);
            }
        })
        .catch(function(error) {
            modal.complete(false, '备份过程中发生错误: ' + error);
        });
}

function manageFonts() {
    const modal = new ProgressModal('管理字体');
    modal.addLog('开始管理字体...');
    
    // 调用后端API进行实际管理
    pywebview.api.manage_fonts(modal.id)
        .then(function(result) {
            if (result.success) {
                modal.complete(true, '字体管理完成');
            } else {
                modal.complete(false, '字体管理失败: ' + result.message);
            }
        })
        .catch(function(error) {
            modal.complete(false, '管理过程中发生错误: ' + error);
        });
}

function manageImages() {
    const modal = new ProgressModal('管理图片');
    modal.addLog('开始管理图片...');
    
    // 调用后端API进行实际管理
    pywebview.api.manage_images(modal.id)
        .then(function(result) {
            if (result.success) {
                modal.complete(true, '图片管理完成');
            } else {
                modal.complete(false, '图片管理失败: ' + result.message);
            }
        })
        .catch(function(error) {
            modal.complete(false, '管理过程中发生错误: ' + error);
        });
}

function manageAudio() {
    const modal = new ProgressModal('管理音频');
    modal.addLog('开始管理音频...');
    
    // 调用后端API进行实际管理
    pywebview.api.manage_audio(modal.id)
        .then(function(result) {
            if (result.success) {
                modal.complete(true, '音频管理完成');
            } else {
                modal.complete(false, '音频管理失败: ' + result.message);
            }
        })
        .catch(function(error) {
            modal.complete(false, '管理过程中发生错误: ' + error);
        });
}

function adjustImage() {
    const imagePath = document.getElementById('image-path').value;
    const brightness = document.getElementById('brightness').value;
    const contrast = document.getElementById('contrast').value;
    
    if (!imagePath) {
        showMessage('提示', '请选择要调整的图片文件');
        return;
    }
    
    const modal = new ProgressModal('调整图片');
    modal.addLog('开始调整图片...');
    modal.addLog(`图片路径: ${imagePath}`);
    modal.addLog(`亮度: ${brightness}`);
    modal.addLog(`对比度: ${contrast}`);
    
    // 调用后端API进行实际调整
    pywebview.api.adjust_image(modal.id)
        .then(function(result) {
            if (result.success) {
                modal.complete(true, '图片调整完成');
            } else {
                modal.complete(false, '图片调整失败: ' + result.message);
            }
        })
        .catch(function(error) {
            modal.complete(false, '调整过程中发生错误: ' + error);
        });
}

function calculateGacha() {
    const totalItems = document.getElementById('total-items').value;
    const rareItems = document.getElementById('rare-items').value;
    const drawCount = document.getElementById('draw-count').value;
    
    if (!totalItems || !rareItems || !drawCount) {
        showMessage('提示', '请填写所有参数');
        return;
    }
    
    const modal = new ProgressModal('计算抽卡概率');
    modal.addLog('开始计算抽卡概率...');
    modal.addLog(`总物品数: ${totalItems}`);
    modal.addLog(`稀有物品数: ${rareItems}`);
    modal.addLog(`抽取次数: ${drawCount}`);
    
    // 调用后端API进行实际计算
    pywebview.api.calculate_gacha(modal.id)
        .then(function(result) {
            if (result.success) {
                modal.complete(true, '抽卡概率计算完成');
                // 显示计算结果
                showCalculationResults(result.data);
            } else {
                modal.complete(false, '计算失败: ' + result.message);
            }
        })
        .catch(function(error) {
            modal.complete(false, '计算过程中发生错误: ' + error);
        });
}

function showCalculationResults(data) {
    const resultsContainer = document.getElementById('calculation-results');
    if (!resultsContainer) return;
    
    if (!data) {
        resultsContainer.innerHTML = `
            <div class="results-placeholder">
                <i class="fas fa-chart-pie"></i>
                <p>暂无计算结果</p>
            </div>
        `;
        return;
    }
    
    let html = `
        <div class="calculation-results-content">
            <div class="result-item">
                <h4>基础概率</h4>
                <p>单次抽取稀有物品概率: ${(data.singleProbability * 100).toFixed(2)}%</p>
            </div>
            <div class="result-item">
                <h4>多次抽取概率</h4>
                <p>至少获得一件稀有物品: ${(data.atLeastOneProbability * 100).toFixed(2)}%</p>
            </div>
            <div class="result-item">
                <h4>期望值</h4>
                <p>期望抽取次数: ${data.expectedDraws.toFixed(2)}</p>
            </div>
        </div>
    `;
    
    resultsContainer.innerHTML = html;
}

function downloadOurplay() {
    const fontOption = document.getElementById('ourplay-font-option').value;
    const checkHash = document.getElementById('ourplay-check-hash').checked;
    
    const modal = new ProgressModal('下载OurPlay汉化包');
    modal.addLog('开始下载OurPlay汉化包...');
    modal.addLog(`字体选项: ${fontOption}`);
    modal.addLog(`哈希校验: ${checkHash ? '启用' : '禁用'}`);
    
    // 调用后端API进行实际下载
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
}

function cleanCache() {
    const modal = new ProgressModal('清除缓存');
    
    // 调用后端API进行实际清理
    pywebview.api.clean_cache(modal.id).then(function(result) {
        if (result.success) {
            modal.complete(true, '缓存清除成功');
        } else {
            modal.complete(false, '清除失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '清除过程中发生错误: ' + error);
    });
}

function downloadLLC() {
    const checkHash = document.getElementById('llc-check-hash').checked;
    const dumpDefault = document.getElementById('llc-dump-default').checked;
    
    const modal = new ProgressModal('下载零协汉化包');
    modal.addLog('开始下载零协汉化包...');
    modal.addLog(`哈希校验: ${checkHash ? '启用' : '禁用'}`);
    modal.addLog(`保存原始文件: ${dumpDefault ? '是' : '否'}`);
    
    // 调用后端API进行实际下载
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
    
    // 调用后端API进行实际保存
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

// 设置界面相关函数
function loadSettings() {
    // 调用后端API获取游戏路径
    pywebview.api.get_game_path()
        .then(function(gamePath) {
            if (gamePath) {
                document.getElementById('game-path').value = gamePath;
            }
        })
        .catch(function(error) {
            console.error('获取游戏路径失败:', error);
        });
    
    // 从本地存储加载其他设置
    const debugMode = localStorage.getItem('lcta-debug-mode') === 'true';
    const autoCheckUpdate = localStorage.getItem('lcta-auto-check-update') !== 'false';
    
    document.getElementById('debug-mode').checked = debugMode;
    document.getElementById('auto-check-update').checked = autoCheckUpdate;
}

function saveSettings() {
    const gamePath = document.getElementById('game-path').value;
    const debugMode = document.getElementById('debug-mode').checked;
    const autoCheckUpdate = document.getElementById('auto-check-update').checked;
    
    const modal = new ProgressModal('保存设置');
    modal.addLog('正在保存设置...');
    
    // 调用后端API保存设置
    pywebview.api.save_settings(gamePath, debugMode, autoCheckUpdate)
        .then(function(result) {
            if (result.success) {
                // 保存到本地存储
                localStorage.setItem('lcta-debug-mode', debugMode);
                localStorage.setItem('lcta-auto-check-update', autoCheckUpdate);
                
                modal.complete(true, '设置保存成功');
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
    
    // 调用后端API使用默认配置
    pywebview.api.use_default_config()
        .then(function(result) {
            if (result.success) {
                modal.complete(true, '已使用默认配置');
                setTimeout(loadSettings, 500);
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
            
            // 调用后端API重置配置
            pywebview.api.reset_config()
                .then(function(result) {
                    if (result.success) {
                        // 清除本地存储
                        localStorage.removeItem('lcta-debug-mode');
                        localStorage.removeItem('lcta-auto-check-update');
                        
                        modal.complete(true, '配置已重置');
                        setTimeout(loadSettings, 500);
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
    
    // 调用后端API进行实际检查更新
    pywebview.api.manual_check_update()
        .then(function(result) {
            if (result.has_update) {
                modal.complete(true, `发现新版本 ${result.latest_version}，请前往GitHub下载更新`);
                // 显示更新详情
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
    // 调用后端API进行实际检查更新
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
    // 防止重复创建更新窗口
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
            // 用户确认更新
            const progressModal = new ProgressModal('更新程序');
            progressModal.addLog('开始下载并安装更新...');
        },
        function() {
            // 用户取消更新
            addLogMessage('用户取消了更新');
            updateModalShown = false;
        }
    );
    
    // 当窗口关闭时，重置标志
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
    // 创建遮罩层元素
    const mask = document.createElement('div');
    mask.id = 'connection-mask';
    mask.className = 'connection-mask';
    
    // 创建遮罩内容
    mask.innerHTML = `
        <div class="mask-content">
            <div class="spinner"></div>
            <div class="mask-text">正在连接到API...</div>
        </div>
    `;
    
    // 将遮罩层添加到body
    document.body.appendChild(mask);
    
    // 更新状态指示器为"连接中"
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
    
    // 更新状态指示器为"已连接"
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

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', init);

// 与后端通信的初始化
window.addEventListener('pywebviewready', function() {
    addLogMessage('PyWebview API 已准备就绪', 'success');
    
    // 移除遮罩层并更新状态
    removeConnectionMask();
    
    // 加载设置
    loadSettings();
    
    // 检查配置
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
    
    // 检查更新 - 只在这里检查一次，避免重复创建窗口
    const autoCheckUpdate = localStorage.getItem('lcta-auto-check-update') !== 'false';
    if (autoCheckUpdate) {
        autoCheckUpdates();
    }
});
