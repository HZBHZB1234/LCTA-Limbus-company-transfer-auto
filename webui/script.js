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

// 模态窗口类
class ModalWindow {
    constructor(title) {
        this.id = 'modal-' + Date.now() + '-' + Math.floor(Math.random() * 1000);
        this.title = title;
        this.isMinimized = false;
        this.isCompleted = false;
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
                        <button class="modal-button" id="minimize-btn-${this.id}" title="最小化">−</button>
                        <button class="modal-button" id="close-btn-${this.id}" title="关闭">×</button>
                    </div>
                </div>
                <div class="modal-body">
                    <div class="modal-status" id="modal-status-${this.id}">准备就绪</div>
                    <div class="modal-log" id="modal-log-${this.id}"></div>
                    <div class="modal-progress hidden" id="modal-progress-${this.id}">
                        <div class="modal-progress-bar">
                            <div class="modal-progress-fill" id="modal-progress-fill-${this.id}"></div>
                        </div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="action-btn" id="cancel-btn-${this.id}">取消</button>
                </div>
            </div>
        `;
        
        modalContainer.appendChild(this.element);
        
        // 绑定事件
        document.getElementById(`close-btn-${this.id}`).addEventListener('click', () => {
            this.close();
        });
        
        document.getElementById(`minimize-btn-${this.id}`).addEventListener('click', (e) => {
            e.stopPropagation();
            this.minimize();
        });
        
        document.getElementById(`cancel-btn-${this.id}`).addEventListener('click', () => {
            if (this.isCompleted) {
                this.close();
            } else {
                this.cancel();
            }
        });
    }
    
    setStatus(status) {
        const statusElement = document.getElementById(`modal-status-${this.id}`);
        if (statusElement) {
            statusElement.textContent = status;
        }
        // 同步更新到日志页面
        addLogMessage(`[${this.title}] ${status}`);
        
        // 同步更新到最小化窗口状态（如果已最小化）
        this.updateMinimizedStatus(status);
    }
    
    addLog(message) {
        const logElement = document.getElementById(`modal-log-${this.id}`);
        if (logElement) {
            const now = new Date();
            const timestamp = `[${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}]`;
            
            const logEntry = document.createElement('div');
            logEntry.textContent = `${timestamp} ${message}`;
            logElement.appendChild(logEntry);
            logElement.scrollTop = logElement.scrollHeight;
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

// 显示简单提示的模态窗口
function showMessage(title, message, onCloseCallback = () => {
    pywebview.api.log("用户关闭窗口")
}) {
    const modal = new ModalWindow(title);
    modal.setStatus(message);
    modal.showProgress(false);
    
    // 修改底部按钮为"确定"
    const cancelButton = document.getElementById(`cancel-btn-${modal.id}`);
    if (cancelButton) {
        cancelButton.textContent = '确定';
        cancelButton.addEventListener('click', () => {
            modal.close();
            if (onCloseCallback && typeof onCloseCallback === 'function') {
                onCloseCallback();
            }
        });
    }
    
    return modal;
}

// 显示带有确认/取消选项的模态窗口
function showConfirm(title, message, onConfirmCallback, onCancelCallback) {
    const modal = new ModalWindow(title);
    modal.setStatus(message);
    modal.showProgress(false);
    
    // 修改底部按钮
    const modalFooter = modal.element.querySelector('.modal-footer');
    if (modalFooter) {
        modalFooter.innerHTML = `
            <button class="action-btn" id="confirm-btn-${modal.id}">确定</button>
            <button class="secondary-btn" id="cancel-btn-${modal.id}">取消</button>
        `;
        
        // 绑定确认按钮事件
        document.getElementById(`confirm-btn-${modal.id}`).addEventListener('click', () => {
            modal.close();
            if (onConfirmCallback && typeof onConfirmCallback === 'function') {
                onConfirmCallback();
            }
        });
        
        // 绑定取消按钮事件
        document.getElementById(`cancel-btn-${modal.id}`).addEventListener('click', () => {
            modal.close();
            if (onCancelCallback && typeof onCancelCallback === 'function') {
                onCancelCallback();
            }
        });
    }
    
    return modal;
}

// 各功能函数
function startTranslation() {
    const modal = new ModalWindow('翻译工具');
    modal.setStatus('正在初始化翻译过程...');
    modal.showProgress(true);
    modal.updateProgress(10, '初始化中...');
    
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
        modal.setStatus('翻译完成');
        modal.addLog('翻译任务已完成');
        modal.updateProgress(100, '完成');
        modal.setCompleted();
    }, 4000);
}

function installTranslation() {
    const modal = new ModalWindow('安装汉化包');
    modal.setStatus('正在准备安装汉化包...');
    modal.showProgress(true);
    modal.updateProgress(0, '准备安装...');
    
    pywebview.api.install_translation().then(function(result) {
        if (result.success) {
            modal.setStatus('安装成功');
            modal.addLog('汉化包安装成功: ' + result.message);
            modal.updateProgress(100, '安装完成');
        } else {
            modal.setStatus('安装失败');
            modal.addLog('汉化包安装失败: ' + result.message);
        }
        modal.setCompleted();
    }).catch(function(error) {
        modal.setStatus('安装出错');
        modal.addLog('安装过程中出现错误: ' + error);
        modal.setCompleted();
    });
}

function downloadOurplay() {
    const modal = new ModalWindow('下载OurPlay汉化包');
    modal.setStatus('开始下载OurPlay汉化包...');
    modal.addLog('开始下载OurPlay汉化包...');
    modal.showProgress(true);
    modal.updateProgress(0, '开始下载...');
    
    pywebview.api.download_ourplay_translation().then(function(result) {
        if (result.success) {
            modal.setStatus('下载成功');
            modal.addLog('OurPlay汉化包下载成功: ' + result.message);
            modal.updateProgress(100, '下载完成');
        } else {
            modal.setStatus('下载失败');
            modal.addLog('OurPlay汉化包下载失败: ' + result.message);
        }
        modal.setCompleted();
    }).catch(function(error) {
        modal.setStatus('下载出错');
        modal.addLog('下载OurPlay汉化包时出现错误: ' + error);
        modal.setCompleted();
    });
}

function cleanCache() {
    const modal = new ModalWindow('清除缓存');
    modal.setStatus('正在清除本地缓存...');
    modal.showProgress(true);
    modal.updateProgress(0, '开始清除...');
    
    pywebview.api.clean_cache().then(function(result) {
        if (result.success) {
            modal.setStatus('清除成功');
            modal.addLog('缓存清除成功: ' + result.message);
            modal.updateProgress(100, '清除完成');
        } else {
            modal.setStatus('清除失败');
            modal.addLog('缓存清除失败: ' + result.message);
        }
        modal.setCompleted();
    }).catch(function(error) {
        modal.setStatus('清除出错');
        modal.addLog('清除缓存时出现错误: ' + error);
        modal.setCompleted();
    });
}

function downloadLLC() {
    const modal = new ModalWindow('下载零协汉化包');
    modal.setStatus('开始下载零协汉化包...');
    modal.addLog('开始下载零协汉化包...');
    modal.showProgress(true);
    modal.updateProgress(0, '开始下载...');
    
    pywebview.api.download_llc_translation().then(function(result) {
        if (result.success) {
            modal.setStatus('下载成功');
            modal.addLog('零协汉化包下载成功: ' + result.message);
            modal.updateProgress(100, '下载完成');
        } else {
            modal.setStatus('下载失败');
            modal.addLog('零协汉化包下载失败: ' + result.message);
        }
        modal.setCompleted();
    }).catch(function(error) {
        modal.setStatus('下载出错');
        modal.addLog('下载零协汉化包时出现错误: ' + error);
        modal.setCompleted();
    });
}

function saveAPIConfig() {
    const modal = new ModalWindow('保存API配置');
    modal.setStatus('正在保存API配置...');
    modal.showProgress(true);
    modal.updateProgress(0, '保存配置中...');
    
    pywebview.api.save_api_config().then(function(result) {
        if (result.success) {
            modal.setStatus('保存成功');
            modal.addLog('API配置保存成功: ' + result.message);
            modal.updateProgress(100, '保存完成');
        } else {
            modal.setStatus('保存失败');
            modal.addLog('API配置保存失败: ' + result.message);
        }
        modal.setCompleted();
    }).catch(function(error) {
        modal.setStatus('保存出错');
        modal.addLog('保存API配置时出现错误: ' + error);
        modal.setCompleted();
    });
}

function fetchProperNouns() {
    const modal = new ModalWindow('抓取专有词汇');
    modal.setStatus('正在抓取专有词汇...');
    modal.showProgress(true);
    modal.updateProgress(0, '开始抓取...');
    
    pywebview.api.fetch_proper_nouns().then(function(result) {
        if (result.success) {
            modal.setStatus('抓取成功');
            modal.addLog('专有词汇抓取成功: ' + result.message);
            modal.updateProgress(100, '抓取完成');
        } else {
            modal.setStatus('抓取失败');
            modal.addLog('专有词汇抓取失败: ' + result.message);
        }
        modal.setCompleted();
    }).catch(function(error) {
        modal.setStatus('抓取出错');
        modal.addLog('抓取专有词汇时出现错误: ' + error);
        modal.setCompleted();
    });
}

function searchText() {
    const modal = new ModalWindow('文本搜索');
    modal.setStatus('正在执行文本搜索...');
    modal.showProgress(true);
    modal.updateProgress(0, '开始搜索...');
    
    pywebview.api.search_text().then(function(result) {
        if (result.success) {
            modal.setStatus('搜索完成');
            modal.addLog('文本搜索完成: ' + result.message);
            modal.updateProgress(100, '搜索完成');
            if (result.results) {
                // 清空搜索结果区域
                const resultsDiv = document.getElementById('search-results');
                resultsDiv.innerHTML = '';
                
                if (result.results.length === 0) {
                    const noResultEntry = document.createElement('div');
                    noResultEntry.className = 'log-entry';
                    noResultEntry.innerHTML = `<span class="log-timestamp">[无结果]</span> <span class="log-message">未找到匹配的文本</span>`;
                    resultsDiv.appendChild(noResultEntry);
                } else {
                    // 显示搜索结果
                    result.results.forEach(function(r) {
                        const resultEntry = document.createElement('div');
                        resultEntry.className = 'log-entry';
                        resultEntry.innerHTML = `<span class="log-timestamp">[文件: ${r.file}:${r.line}]</span> <span class="log-message">${r.content}</span>`;
                        resultsDiv.appendChild(resultEntry);
                    });
                    
                    modal.addLog(`显示了 ${result.results.length} 个搜索结果`);
                }
            }
        } else {
            modal.setStatus('搜索失败');
            modal.addLog('文本搜索失败: ' + result.message);
        }
        modal.setCompleted();
    }).catch(function(error) {
        modal.setStatus('搜索出错');
        modal.addLog('搜索文本时出现错误: ' + error);
        modal.setCompleted();
    });
}

function backupText() {
    const modal = new ModalWindow('备份原文');
    modal.setStatus('正在执行备份操作...');
    modal.showProgress(true);
    modal.updateProgress(0, '开始备份...');
    
    pywebview.api.backup_text().then(function(result) {
        if (result.success) {
            modal.setStatus('备份完成');
            modal.addLog('备份完成: ' + result.message);
            modal.updateProgress(100, '备份完成');
        } else {
            modal.setStatus('备份失败');
            modal.addLog('备份失败: ' + result.message);
        }
        modal.setCompleted();
    }).catch(function(error) {
        modal.setStatus('备份出错');
        modal.addLog('备份文本时出现错误: ' + error);
        modal.setCompleted();
    });
}

function manageFonts() {
    const modal = new ModalWindow('字体管理');
    modal.setStatus('正在管理字体...');
    
    pywebview.api.manage_fonts().then(function(result) {
        if (result.success) {
            modal.setStatus('操作完成');
            modal.addLog('字体管理: ' + result.message);
        } else {
            modal.setStatus('操作失败');
            modal.addLog('字体管理失败: ' + result.message);
        }
        modal.setCompleted();
    }).catch(function(error) {
        modal.setStatus('操作出错');
        modal.addLog('字体管理时出现错误: ' + error);
        modal.setCompleted();
    });
}

function manageImages() {
    const modal = new ModalWindow('图片管理');
    modal.setStatus('正在管理图片...');
    
    pywebview.api.manage_images().then(function(result) {
        if (result.success) {
            modal.setStatus('操作完成');
            modal.addLog('图片管理: ' + result.message);
        } else {
            modal.setStatus('操作失败');
            modal.addLog('图片管理失败: ' + result.message);
        }
        modal.setCompleted();
    }).catch(function(error) {
        modal.setStatus('操作出错');
        modal.addLog('图片管理时出现错误: ' + error);
        modal.setCompleted();
    });
}

function manageAudio() {
    const modal = new ModalWindow('音频管理');
    modal.setStatus('正在管理音频...');
    
    pywebview.api.manage_audio().then(function(result) {
        if (result.success) {
            modal.setStatus('操作完成');
            modal.addLog('音频管理: ' + result.message);
        } else {
            modal.setStatus('操作失败');
            modal.addLog('音频管理失败: ' + result.message);
        }
        modal.setCompleted();
    }).catch(function(error) {
        modal.setStatus('操作出错');
        modal.addLog('音频管理时出现错误: ' + error);
        modal.setCompleted();
    });
}

function adjustImage() {
    const modal = new ModalWindow('调整图片');
    modal.setStatus('正在调整图片...');
    modal.showProgress(true);
    modal.updateProgress(0, '开始调整...');
    
    pywebview.api.adjust_image().then(function(result) {
        if (result.success) {
            modal.setStatus('调整完成');
            modal.addLog('图片调整: ' + result.message);
            modal.updateProgress(100, '调整完成');
        } else {
            modal.setStatus('调整失败');
            modal.addLog('图片调整失败: ' + result.message);
        }
        modal.setCompleted();
    }).catch(function(error) {
        modal.setStatus('调整出错');
        modal.addLog('调整图片时出现错误: ' + error);
        modal.setCompleted();
    });
}

function calculateGacha() {
    const modal = new ModalWindow('抽卡概率计算');
    modal.setStatus('正在计算抽卡概率...');
    modal.showProgress(true);
    modal.updateProgress(0, '开始计算...');
    
    pywebview.api.calculate_gacha().then(function(result) {
        if (result.success) {
            modal.setStatus('计算完成');
            modal.addLog('抽卡概率计算: ' + result.message);
            modal.updateProgress(100, '计算完成');
            
            // 更新计算结果区域
            const resultsDiv = document.getElementById('calculation-results');
            resultsDiv.innerHTML = '';
            const resultEntry = document.createElement('div');
            resultEntry.className = 'log-entry';
            resultEntry.innerHTML = `<span class="log-timestamp">[概率结果]</span> <span class="log-message">${result.message}</span>`;
            resultsDiv.appendChild(resultEntry);
        } else {
            modal.setStatus('计算失败');
            modal.addLog('概率计算失败: ' + result.message);
        }
        modal.setCompleted();
    }).catch(function(error) {
        modal.setStatus('计算出错');
        modal.addLog('计算抽卡概率时出现错误: ' + error);
        modal.setCompleted();
    });
}

function updateValue(sliderId) {
    const slider = document.getElementById(sliderId);
    const valueSpan = document.getElementById(sliderId + '-value');
    valueSpan.textContent = slider.value;
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
            showConfirm(
                "警告",
                "配置项格式错误，是否尝试修复?\n否则将会使用默认配置",
                () => {
                    pywebview.api.get_attr("config").then(function(config) {
                        pywebview.api.fix_config(config).then(function(fixed_config) {
                            pywebview.api.init_config.set_attr("config", fixed_config);
                        });
                    });
                },
                () => {
                    pywebview.api.init_config.use_default();
                }
            );
        }
    }).catch(function(error) {
        console.error('Error checking config:', error);
    });
});