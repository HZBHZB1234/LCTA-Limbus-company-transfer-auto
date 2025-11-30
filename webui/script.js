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

// 从Python后端接收日志消息
window.addEventListener('pywebviewready', function() {
    addLogMessage('WebUI已准备就绪');
    console.log('PyWebview API is ready');

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
                            return pywebview.api.get_attr('fix_config')(config);
                        }).then(function(fixed_config) {
                            return pywebview.api.set_attr("config", fixed_config);
                        }).then(function() {
                            showMessage("提示", "配置已修复，请重新启动程序");
                        }).catch(function(error) {
                            showMessage("错误", "修复配置时出错: " + error);
                        });
                    },
                    () => {
                        // 点击取消按钮的处理
                        pywebview.api.init_config.use_default().then(function() {
                            showMessage("提示", "已使用默认配置，请重新启动程序");
                        }).catch(function(error) {
                            showMessage("错误", "使用默认配置时出错: " + error);
                        });
                    }
                );
            }).catch(function(error) {
                // 即使获取错误信息失败，也要显示基本的错误提示
                showConfirm(
                    "警告",
                    "配置项格式错误，是否尝试修复?\n否则将会使用默认配置",
                    () => {
                        // 点击确认按钮的处理
                        pywebview.api.get_attr("config").then(function(config) {
                            return pywebview.api.fix_config(config);
                        }).then(function(fixed_config) {
                            return pywebview.api.init_config.set_attr("config", fixed_config);
                        }).then(function() {
                            showMessage("提示", "配置已修复，请重新启动程序");
                        }).catch(function(error) {
                            showMessage("错误", "修复配置时出错: " + error);
                        });
                    },
                    () => {
                        // 点击取消按钮的处理
                        pywebview.api.init_config.use_default().then(function() {
                            showMessage("提示", "已使用默认配置，请重新启动程序");
                        }).catch(function(error) {
                            showMessage("错误", "使用默认配置时出错: " + error);
                        });
                    }
                );
            });
        }
    }).catch(function(error) {
        console.error('Error checking config:', error);
    });
});