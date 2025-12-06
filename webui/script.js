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
        container.style.bottom = '20px';
        container.style.right = '20px';
        container.style.display = 'flex';
        container.style.flexDirection = 'row';
        container.style.gap = '10px';
        container.style.zIndex = '999';
        container.style.flexWrap = 'wrap';
        container.style.justifyContent = 'flex-end';
        container.style.alignItems = 'flex-end';
        container.style.maxWidth = 'calc(300px * 3 + 10px * 2)'; // 限制最大宽度为三个窗口加间隙
        document.body.appendChild(container);
    }
    return container;
}

// 切换侧边栏按钮激活状态
document.querySelectorAll('.sidebar button').forEach(button => {
    button.addEventListener('click', () => {
        // 移除所有按钮的active类
        document.querySelectorAll('.sidebar button').forEach(btn => {
            btn.classList.remove('active');
        });
        
        // 添加active类到当前按钮
        button.classList.add('active');
        
        // 隐藏所有内容区域
        document.querySelectorAll('.content-section').forEach(section => {
            section.classList.remove('active');
        });
        
        // 显示对应的内容区域
        const sectionId = button.id.replace('-btn', '-section');
        const section = document.getElementById(sectionId);
        if (section) {
            section.classList.add('active');
            
            // 如果是设置界面，加载设置
            if (sectionId === 'settings-section') {
                loadSettings();
            }
        }
    });
});

// 复选框逻辑
document.getElementById('custom-script').addEventListener('change', function() {
    const group = document.getElementById('script-path-group');
    group.style.display = this.checked ? 'block' : 'none';
});

document.getElementById('half-trans').addEventListener('change', function() {
    const group = document.getElementById('half-trans-path-group');
    group.style.display = this.checked ? 'block' : 'none';
});

document.getElementById('backup').addEventListener('change', function() {
    const group = document.getElementById('backup-path-group');
    group.style.display = this.checked ? 'block' : 'none';
});

// 浏览文件函数
function browseFile(inputId) {
    pywebview.api.browse_file(inputId);
}

function browseFolder(inputId) {
    pywebview.api.browse_folder(inputId);
}

// 模态窗口基类
class ModalWindow {
    constructor(title, options = {}) {
        this.id = 'modal-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
        this.title = title;
        this.isMinimized = false;
        this.isCompleted = false;
        this.options = {
            showProgress: false,
            showCancelButton: true,
            cancelButtonText: '取消',
            confirmButtonText: '确定',
            showMinimizeButton: true,  // 默认显示最小化按钮
            showLog: true,  // 默认显示日志区域
            ...options
        };
        this.createModal();
        modalWindows.push(this);
    }
    
    createModal() {
        const modalContainer = ensureModalContainer();
        
        this.element = document.createElement('div');
        this.element.className = 'modal-overlay';
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
        if (this.options.showCancelButton) {
            return `<button class="action-btn" id="cancel-btn-${this.id}">${this.options.cancelButtonText}</button>`;
        }
        return '';
    }
    
    bindEvents() {
        document.getElementById(`close-btn-${this.id}`).addEventListener('click', () => {
            this.close();
        });
        
        // 只有当显示最小化按钮时才绑定最小化事件
        if (this.options.showMinimizeButton) {
            document.getElementById(`minimize-btn-${this.id}`).addEventListener('click', (e) => {
                e.stopPropagation();
                this.minimize();
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
            // 处理换行符，将 \n 转换为 <br> 标签
            if (typeof status === 'string' && status.includes('\n')) {
                statusElement.innerHTML = status.replace(/\n/g, '<br>');
            } else {
                statusElement.textContent = status;
            }
        }
        // 同步更新到日志页面
        addLogMessage(`[${this.title}] ${status}`);
        
        // 同步更新到最小化窗口状态（如果已最小化）
        this.updateMinimizedStatus(status);
    }
    
    addLog(message) {
        // 只有当显示日志区域时才添加日志
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
        // 同步更新到日志页面
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
        // 同步更新到日志页面
        if (text) {
            addLogMessage(`[${this.title}] ${text}`);
        }
        
        // 同步更新到最小化窗口进度条（如果已最小化）
        this.syncProgressToMinimized(percent);
    }
    
    setCompleted() {
        this.isCompleted = true;
        const cancelButton = document.getElementById(`cancel-btn-${this.id}`);
        if (cancelButton) {
            cancelButton.textContent = '完成';
        }
        
        // 更新最小化窗口状态为已完成
        this.updateMinimizedStatus('已完成');
    }
    
    cancel() {
        // 取消操作的逻辑可以在具体的实现中定义
        this.close();
    }
    
    minimize() {
        if (this.isMinimized) return;
        
        this.isMinimized = true;
        
        // 确保最小化容器存在
        const minimizedContainer = ensureMinimizedContainer();
        
        // 创建最小化窗口
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
        
        // 添加点击恢复事件
        minimizedElement.addEventListener('click', (e) => {
            e.stopPropagation();
            this.restoreFromMinimized();
        });
        
        // 将最小化窗口添加到容器中
        minimizedContainer.appendChild(minimizedElement);
        
        // 隐藏原始模态窗口
        this.element.style.display = 'none';
    }
    
    restoreFromMinimized() {
        if (!this.isMinimized) return;
        
        this.isMinimized = false;
        
        // 删除最小化窗口
        const minimizedElement = document.getElementById(`minimized-${this.id}`);
        if (minimizedElement) {
            minimizedElement.remove();
        }
        
        // 显示原始模态窗口
        this.element.style.display = 'flex';
    }
    
    close() {
        // 从modalWindows数组中移除
        const index = modalWindows.indexOf(this);
        if (index > -1) {
            modalWindows.splice(index, 1);
        }
        
        // 删除元素
        if (this.element) {
            this.element.remove();
        }
        
        // 删除最小化的元素（如果存在）
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

// 消息模态窗口类 - 继承自基类
class MessageModal extends ModalWindow {
    constructor(title, message, onCloseCallback = null) {
        super(title, {
            showProgress: false,
            showCancelButton: true,
            cancelButtonText: '确定',
            showMinimizeButton: false,  // 不显示最小化按钮
            showLog: false  // 不显示日志区域
        });
        
        this.onCloseCallback = onCloseCallback;
        
        this.setStatus(message);
        this.setupMessageButton();
    }
    
    setupMessageButton() {
        const cancelButton = document.getElementById(`cancel-btn-${this.id}`);
        if (cancelButton) {
            cancelButton.textContent = '确定';
            // 移除所有现有的事件监听器
            const newCancelButton = cancelButton.cloneNode(true);
            document.getElementById(`modal-footer-${this.id}`).replaceChild(newCancelButton, cancelButton);
            
            // 添加新的点击事件
            newCancelButton.addEventListener('click', () => {
                this.close();
                if (this.onCloseCallback && typeof this.onCloseCallback === 'function') {
                    this.onCloseCallback();
                }
            });
        }
    }
}

// 确认模态窗口类 - 继承自基类
class ConfirmModal extends ModalWindow {
    constructor(title, message, onConfirmCallback, onCancelCallback) {
        super(title, {
            showProgress: false,
            showCancelButton: true,
            cancelButtonText: '取消',
            showMinimizeButton: false,  // 不显示最小化按钮
            showLog: false  // 不显示日志区域
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
                <button class="action-btn" id="confirm-btn-${this.id}">确定</button>
                <button class="secondary-btn" id="cancel-btn-${this.id}">取消</button>
            `;
            
            // 绑定确认按钮事件
            document.getElementById(`confirm-btn-${this.id}`).addEventListener('click', () => {
                this.close();
                if (this.onConfirmCallback && typeof this.onConfirmCallback === 'function') {
                    this.onConfirmCallback();
                }
            });
            
            // 绑定取消按钮事件
            document.getElementById(`cancel-btn-${this.id}`).addEventListener('click', () => {
                this.close();
                if (this.onCancelCallback && typeof this.onCancelCallback === 'function') {
                    this.onCancelCallback();
                }
            });
            
            // 绑定关闭按钮事件（执行取消函数）
            document.getElementById(`close-btn-${this.id}`).addEventListener('click', () => {
                this.close();
                if (this.onCancelCallback && typeof this.onCancelCallback === 'function') {
                    this.onCancelCallback();
                }
            });
        }
    }
    
    // 添加设置HTML内容的方法
    setHtmlContent(htmlContent) {
        const statusElement = document.getElementById(`modal-status-${this.id}`);
        if (statusElement) {
            statusElement.innerHTML = htmlContent;
        }
        // 同步更新到日志页面
        addLogMessage(`[${this.title}] 更新信息已设置`);
    }
}

// 进度模态窗口类 - 继承自基类
class ProgressModal extends ModalWindow {
    constructor(title) {
        super(title, {
            showProgress: true,
            showCancelButton: true,
            cancelButtonText: '取消'
        });
        
        this.setStatus('正在初始化...');
        this.showProgress(true);
        this.updateProgress(0, '初始化中...');
    }
    
    // 可以添加进度窗口特有的方法
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
}

// 使用工厂函数创建不同类型的模态窗口
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

// 各功能函数 - 使用新的模态窗口类
function startTranslation() {
    const modal = new ProgressModal('翻译工具');
    modal.setStatus('正在初始化翻译过程...');
    modal.addLog('开始翻译任务');
    
    // 模拟翻译过程
    setTimeout(() => {
        modal.setStatus('正在解析游戏文件...');
        modal.addLog('开始解析游戏文件');
        modal.updateProgress(30, '解析游戏文件中...');
    }, 1000);
    
    setTimeout(() => {
        modal.setStatus('正在调用翻译API...');
        modal.addLog('调用百度翻译API');
        modal.updateProgress(60, '翻译进行中...');
    }, 2000);
    
    setTimeout(() => {
        modal.setStatus('正在生成翻译文件...');
        modal.addLog('生成翻译文件');
        modal.updateProgress(90, '生成文件中...');
    }, 3000);
    
    setTimeout(() => {
        modal.complete(true, '翻译任务已完成');
    }, 4000);
}

function installTranslation() {
    const modal = new ProgressModal('安装汉化包');
    
    pywebview.api.install_translation().then(function(result) {
        if (result.success) {
            modal.complete(true, '汉化包安装成功: ' + result.message);
        } else {
            modal.complete(false, '汉化包安装失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '安装过程中出现错误: ' + error);
    });
}

function downloadOurplay() {
    const modal = new ProgressModal('下载OurPlay汉化包');
    modal.addLog('开始下载OurPlay汉化包...');
    
    pywebview.api.download_ourplay_translation().then(function(result) {
        if (result.success) {
            modal.complete(true, 'OurPlay汉化包下载成功: ' + result.message);
        } else {
            modal.complete(false, 'OurPlay汉化包下载失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '下载OurPlay汉化包时出现错误: ' + error);
    });
}

function cleanCache() {
    const modal = new ProgressModal('清除缓存');
    
    pywebview.api.clean_cache().then(function(result) {
        if (result.success) {
            modal.complete(true, '缓存清除成功: ' + result.message);
        } else {
            modal.complete(false, '缓存清除失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '清除缓存时出现错误: ' + error);
    });
}

// 其他功能函数也类似地修改为使用新的模态窗口类...
// 由于篇幅限制，这里只展示几个示例，其他函数可以按照相同模式修改

function downloadLLC() {
    const modal = new ProgressModal('下载零协汉化包');
    modal.addLog('开始下载零协汉化包...');
    
    pywebview.api.download_llc_translation().then(function(result) {
        if (result.success) {
            modal.complete(true, '零协汉化包下载成功: ' + result.message);
        } else {
            modal.complete(false, '零协汉化包下载失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '下载零协汉化包时出现错误: ' + error);
    });
}

function saveAPIConfig() {
    const modal = new ProgressModal('保存API配置');
    
    pywebview.api.save_api_config().then(function(result) {
        if (result.success) {
            modal.complete(true, 'API配置保存成功: ' + result.message);
        } else {
            modal.complete(false, 'API配置保存失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '保存API配置时出现错误: ' + error);
    });
}

// 设置界面相关函数
function loadSettings() {
    // 从后端获取当前配置并填充到表单
    pywebview.api.get_attr('config').then(function(config) {
        if (config && typeof config === 'object') {
            // 填充游戏路径
            if (config.game_path !== undefined) {
                document.getElementById('game-path').value = config.game_path;
            }
            
            // 设置调试模式复选框
            if (config.debug !== undefined) {
                document.getElementById('debug-mode').checked = config.debug;
            }
        }
    }).catch(function(error) {
        console.error('加载设置时出错:', error);
    });
    
    // 检查游戏路径是否存在，如果不存在则尝试自动查找
    checkAndSetGamePath();
}

function checkAndSetGamePath() {
    // 检查当前设置的游戏路径
    pywebview.api.get_attr('config').then(function(config) {
        if (config && typeof config === 'object' && config.game_path) {
            // 验证当前游戏路径是否存在
            pywebview.api.run_func("check_game_path", config.game_path).then(function(isValid) {
                if (!isValid) {
                    // 当前路径无效，尝试自动查找
                    attemptAutoFindGamePath();
                }
            }).catch(function() {
                // 出错时也尝试自动查找
                attemptAutoFindGamePath();
            });
        } else {
            // 没有设置游戏路径，尝试自动查找
            attemptAutoFindGamePath();
        }
    });
}

function attemptAutoFindGamePath() {
    // 使用find_lcb查找游戏路径
    pywebview.api.run_func('find_lcb').then(function(foundPath) {
        if (foundPath) {
            // 找到了游戏路径，询问用户确认
            showConfirm(
                "确认游戏路径",
                `系统检测到游戏可能安装在以下位置:\n${foundPath}\n这是否正确?`,
                function() {
                    // 用户确认路径正确，更新配置
                    updateGamePathSetting(foundPath);
                },
                function() {
                    // 用户表示路径不正确，让用户手动选择
                    showGamePathSelection();
                }
            );
        } else {
            // 未找到游戏路径，让用户手动选择
            showGamePathSelection();
        }
    }).catch(function() {
        // 查找失败，让用户手动选择
        showGamePathSelection();
    });
}

function showGamePathSelection() {
    showMessage(
        "选择游戏路径",
        "请手动选择游戏路径:\n1. 点击确定后会弹出文件夹选择窗口\n2. 请选择包含 LimbusCompany.exe 文件的文件夹",
        function() {
            browseFolder('game-path');
        }
    );
}

function updateGamePathSetting(gamePath) {
    // 更新游戏路径配置
    const modal = new ProgressModal('更新配置');
    modal.addLog('正在更新游戏路径配置...');
    
    pywebview.api.save_settings(gamePath, document.getElementById('debug-mode').checked).then(function(result) {
        if (result.success) {
            // 更新界面上的显示
            document.getElementById('game-path').value = gamePath;
            modal.complete(true, '游戏路径配置更新成功');
        } else {
            modal.complete(false, '更新失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '更新过程中出现错误: ' + error);
    });
}

function saveSettings() {
    const modal = new ProgressModal('保存设置');
    
    // 获取表单数据
    const gamePath = document.getElementById('game-path').value;
    const debugMode = document.getElementById('debug-mode').checked;
    
    modal.addLog('正在保存设置...');
    
    // 调用后端API保存设置
    pywebview.api.save_settings(gamePath, debugMode).then(function(result) {
        if (result.success) {
            modal.complete(true, '设置保存成功: ' + result.message);
        } else {
            modal.complete(false, '设置保存失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '保存设置时出现错误: ' + error);
    });
}

function useDefaultConfig() {
    const modal = new ProgressModal('使用默认配置');
    
    modal.addLog('正在加载默认配置...');
    
    pywebview.api.use_default_config().then(function(result) {
        if (result.success) {
            modal.complete(true, result.message);
            // 重新加载设置到表单
            setTimeout(loadSettings, 1000);
        } else {
            modal.complete(false, '操作失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '操作时出现错误: ' + error);
    });
}

function resetConfig() {
    showConfirm(
        "确认重置",
        "确定要重置所有配置吗？这将删除当前配置并恢复为默认设置。",
        function() {
            const modal = new ProgressModal('重置配置');
            
            modal.addLog('正在重置配置...');
            
            pywebview.api.reset_config().then(function(result) {
                if (result.success) {
                    modal.complete(true, result.message);
                    // 重新加载设置到表单
                    setTimeout(loadSettings, 1000);
                } else {
                    modal.complete(false, '操作失败: ' + result.message);
                }
            }).catch(function(error) {
                modal.complete(false, '操作时出现错误: ' + error);
            });
        },
        function() {
            // 用户取消操作，不做任何事
        }
    );
}

// 更新进度条函数
function updateProgress(percent, text) {
    document.getElementById('progress-fill').style.width = percent + '%';
    document.getElementById('progress-text').textContent = text || percent + '%';
}

// 添加日志消息
function addLogMessage(message) {
    // 添加到日志页面
    const logDisplay = document.getElementById('log-display');
    if (logDisplay) {
        const now = new Date();
        const timestamp = `[${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}]`;
        
        const logEntry = document.createElement('div');
        logEntry.className = 'log-entry';
        logEntry.innerHTML = `<span class="log-timestamp">${timestamp}</span> <span class="log-message">${message}</span>`;
        
        logDisplay.appendChild(logEntry);
        logDisplay.scrollTop = logDisplay.scrollHeight;
    }
    
    // 同时添加到底部日志区域（为了向后兼容）
    const logArea = document.getElementById('log-area');
    if (logArea) {
        const now = new Date();
        const timestamp = `[${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}]`;
        
        const logEntry = document.createElement('div');
        logEntry.className = 'log-entry';
        logEntry.innerHTML = `<span class="log-timestamp">${timestamp}</span> <span class="log-message">${message}</span>`;
        
        logArea.appendChild(logEntry);
        logArea.scrollTop = logArea.scrollHeight;
    }
}

// 简单的代码转HTML函数
function simpleMarkdownToHtml(text) {
    if (!text) return '';
    
    // 保护已经存在的HTML标签
    const htmlTagRegex = /(<[^>]+>)/g;
    const htmlTags = [];
    let processedText = text.replace(htmlTagRegex, function(match) {
        htmlTags.push(match);
        return `\x01${htmlTags.length - 1}\x01`;
    });
    
    // 转换代码块 ```code```
    processedText = processedText.replace(/```(\w*)\n([\s\S]*?)```/g, function(match, lang, code) {
        const escapedCode = code.replace(/&/g, '&amp;')
                               .replace(/</g, '&lt;')
                               .replace(/>/g, '&gt;')
                               .trim();
        return `<pre><code class="language-${lang || 'text'}">${escapedCode}</code></pre>`;
    });
    
    // 转换行内代码 `code`
    processedText = processedText.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // 转换加粗 **text** 和 __text__
    processedText = processedText.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    processedText = processedText.replace(/__(.*?)__/g, '<strong>$1</strong>');
    
    // 转换斜体 *text* 和 _text_
    processedText = processedText.replace(/(?:^|\s)\*([^\*]+)\*(?:\s|$)/g, ' <em>$1</em> ');
    processedText = processedText.replace(/(?:^|\s)_([^_]+)_(?:\s|$)/g, ' <em>$1</em> ');
    
    // 转换链接 [text](url)
    processedText = processedText.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');
    
    // 转换图片 ![alt](url)
    processedText = processedText.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" style="max-width: 100%;">');
    
    // 转换标题 # Header
    processedText = processedText.replace(/^###### (.*$)/gm, '<h6>$1</h6>');
    processedText = processedText.replace(/^##### (.*$)/gm, '<h5>$1</h5>');
    processedText = processedText.replace(/^#### (.*$)/gm, '<h4>$1</h4>');
    processedText = processedText.replace(/^### (.*$)/gm, '<h3>$1</h3>');
    processedText = processedText.replace(/^## (.*$)/gm, '<h2>$1</h2>');
    processedText = processedText.replace(/^# (.*$)/gm, '<h1>$1</h1>');
    
    // 转换无序列表 - item 或 * item
    processedText = processedText.replace(/^[*-] (.*$)/gm, '<li>$1</li>');
    // 将连续的<li>元素包裹在<ul>中
    processedText = processedText.replace(/(<li>.*<\/li>)+/gs, function(match) {
        return '<ul>' + match.replace(/<\/li><li>/g, '</li>\n<li>') + '</ul>';
    });
    
    // 恢复HTML标签
    processedText = processedText.replace(/\x01(\d+)\x01/g, function(match, index) {
        return htmlTags[index];
    });
    
    // 处理段落：将多个换行符分隔的段落用<p>标签包裹
    const paragraphs = processedText.split(/\n\s*\n/);
    const processedParagraphs = paragraphs.map(paragraph => {
        // 清理段落前后的空白字符
        paragraph = paragraph.trim();
        
        // 如果段落不是HTML块级元素，则用<p>包裹
        if (paragraph && !paragraph.match(/^<(h[1-6]|ul|ol|li|pre|div|blockquote)/)) {
            // 处理段落内的单个换行符
            paragraph = paragraph.replace(/\n/g, '<br>');
            return '<p>' + paragraph + '</p>';
        }
        return paragraph;
    });
    
    return processedParagraphs.filter(p => p !== '').join('\n');
}

// 显示更新信息的专门函数
function showUpdateInfo(update_info) {
    // 检查是否在PyInstaller打包环境中
    // 从Python环境获取是否为打包环境
    let isFrozen = false;
    pywebview.api.get_attr('is_frozen').then(function(frozenValue) {
        isFrozen = frozenValue;
        continueShowUpdateInfo();
    }).catch(function() {
        isFrozen = true;  // 默认假设为打包环境
        continueShowUpdateInfo();
    });
    
    function continueShowUpdateInfo() {
        // 构建HTML格式的更新信息
        let htmlMessage = `<p><strong>发现新版本:</strong> ${update_info.latest_version}</p>`;
        htmlMessage += `<p><strong>当前版本:</strong> ${update_info.current_version || 'unknown'}</p>`;
        
        // 添加发布标题
        if (update_info.title) {
            htmlMessage += `<p><strong>发布标题:</strong> ${update_info.title}</p>`;
        }
        
        // 添加发布详情
        if (update_info.body) {
            let body = update_info.body.trim();
            // 使用代码转HTML处理
            const bodyHtml = simpleMarkdownToHtml(body);
            htmlMessage += `<div><strong>更新详情:</strong></div>`;
            htmlMessage += `<div style="margin: 10px 0; padding: 10px; background: rgba(0,0,0,0.1); border-radius: 4px; max-height: 300px; overflow-y: auto;">${bodyHtml}</div>`;
        }
        
        // 添加发布时间
        if (update_info.published_at) {
            const publishDate = new Date(update_info.published_at);
            htmlMessage += `<p><strong>发布时间:</strong> ${publishDate.toLocaleDateString('zh-CN')}</p>`;
        }
        
        // 添加发布链接
        if (update_info.html_url) {
            htmlMessage += `<p><strong>发布页面:</strong> <a href="${update_info.html_url}" target="_blank" style="color: #4CAF50; text-decoration: underline;">点击这里在浏览器中查看</a></p>`;
        }
        
        // 计算文件大小
        if (update_info.size > 0) {
            let sizeStr = '';
            if (update_info.size > 1024 * 1024) {
                sizeStr = (update_info.size / (1024 * 1024)).toFixed(2) + ' MB';
            } else if (update_info.size > 1024) {
                sizeStr = (update_info.size / 1024).toFixed(2) + ' KB';
            } else {
                sizeStr = update_info.size + ' bytes';
            }
            htmlMessage += `<p><strong>更新包大小:</strong> ${sizeStr}</p>`;
        }
        
        // 根据是否为打包环境显示不同的信息和按钮
        if (isFrozen) {
            htmlMessage += `<p style="margin-top: 15px; color: #FFA500;"><strong>注意:</strong> 您正在使用打包版本的应用，自动更新功能不可用。</p>`;
            htmlMessage += `<p>请前往发布页面手动下载最新版本并替换当前应用。</p>`;
        } else {
            htmlMessage += `<p style="margin-top: 15px;"><strong>是否现在更新？</strong></p>`;
        }
        
        // 使用HTML内容显示方式
        const modal = showConfirm(
            '发现新版本',
            '', // 初始时不设置文本内容
            isFrozen ? null : function() {
                // 用户确认更新（仅在非打包环境中）
                const progressModal = new ProgressModal('更新程序');
                progressModal.addLog('开始下载并安装更新...');
                
                // 执行更新
                pywebview.api.perform_update_in_modal(progressModal.id).then(function(result) {
                    if (result) {
                        progressModal.complete(true, '更新完成，应用将自动重启');
                    } else {
                        progressModal.complete(false, '更新失败，请查看日志');
                    }
                }).catch(function(error) {
                    progressModal.complete(false, '更新过程中出现错误: ' + error);
                });
            },
            function() {
                // 用户取消更新
                addLogMessage('用户取消了更新');
            }
        );
        
        // 如果是打包环境，则移除确认按钮，只保留取消按钮
        if (isFrozen) {
            // 等待DOM更新后修改按钮
            setTimeout(() => {
                const confirmBtn = document.getElementById(`confirm-btn-${modal.id}`);
                const cancelBtn = document.getElementById(`cancel-btn-${modal.id}`);
                const modalFooter = document.getElementById(`modal-footer-${modal.id}`);
                
                if (confirmBtn) {
                    confirmBtn.remove();
                }
                
                if (cancelBtn) {
                    cancelBtn.textContent = '知道了';
                }
            }, 100);
        }
        
        // 使用setTimeout确保DOM完全加载后再设置内容
        setTimeout(() => {
            const statusElement = document.getElementById(`modal-status-${modal.id}`);
            if (statusElement) {
                statusElement.innerHTML = htmlMessage;
            }
        }, 100);
    }
}

// 从Python后端接收日志消息
window.addEventListener('pywebviewready', function() {
    addLogMessage('WebUI已准备就绪');
    console.log('PyWebview API is ready');

    // 加载设置界面的数据
    loadSettings();

    pywebview.api.get_attr("message_list").then(function(message_list) {
        if (message_list && Array.isArray(message_list)) {
            for (let i = message_list.length - 1; i >= 0; i--) {
                const msg = message_list[i];
                if (Array.isArray(msg) && msg.length >= 2) {
                    showMessage(msg[0], msg[1]);
                    message_list.splice(i, 1);
                }
            }
        }
    });

    pywebview.api.get_attr('config_ok').then(function(config_ok) {
        console.log(config_ok);
        if (config_ok === false) { 
            // 获取详细的配置错误信息
            pywebview.api.get_attr('config_error').then(function(config_error) {
                let errorMessage = "配置项格式错误，是否尝试修复?\n否则将会使用默认配置";
                if (config_error && Array.isArray(config_error) && config_error.length > 0) {
                    errorMessage += "\n\n详细错误信息:\n" + config_error.join("\n");
                }
                
                showConfirm(
                    "警告",
                    errorMessage,
                    () => {
                        // 点击确认按钮的处理
                        pywebview.api.get_attr("config").then(function(config) {
                            return pywebview.api.run_func('fix_config', config);
                        }).then(function(fixed_config) {
                            return pywebview.api.set_attr("config", fixed_config);
                        }).then(function() {
                            // 保存修复后的配置到文件
                            return pywebview.api.use_inner();
                        }).then(function() {
                            showMessage("提示", "配置已修复并保存，请重新启动程序");
                        }).catch(function(error) {
                            showMessage("错误", "修复配置时出错: " + error);
                        });
                    },
                    () => {
                        // 点击取消按钮的处理
                        pywebview.api.use_default().then(function() {
                            showMessage("提示", "已使用默认配置，请重新启动程序");
                        }).catch(function(error) {
                            showMessage("错误", "使用默认配置时出错: " + error);
                        });
                    }
                );
            }).catch(function(error) {
                showMessage(
                    "错误",
                    "未知错误，可能导致未知后果。错误信息:\n" + error
                );
            });
        }
    }).catch(function(error) {
        pywebview.api.log('Error checking config:'+ error);
    });
    
    // 检查更新
    pywebview.api.auto_check_update().then(function(update_info) {
        if (update_info && update_info.has_update) {
            showUpdateInfo(update_info);
        }
    }).catch(function(error) {
        console.error('检查更新失败:', error);
        addLogMessage('检查更新失败: ' + error);
    });

    pywebview.api.get_attr('config').then(function(config) {
        pywebview.api.log('Config loaded  and close success');
    }).catch(function(error) {
        pywebview.api.log('Error getting config:'+ error);
    });
});