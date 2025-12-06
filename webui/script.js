// 全局变量
let modalWindows = [];
let update_info = null;

// 初始化函数
document.addEventListener('DOMContentLoaded', function() {
    // 初始化侧边栏菜单切换
    initSidebarMenu();
    
    // 加载设置
    loadSettings();
    
    // 初始化自定义脚本复选框
    initCustomScriptCheckbox();
    
    // 检查更新
    checkForUpdates();
});

// 初始化侧边栏菜单切换
function initSidebarMenu() {
    const menuItems = document.querySelectorAll('.menu-item');
    
    menuItems.forEach(item => {
        item.addEventListener('click', function() {
            // 移除所有活动状态
            document.querySelectorAll('.menu-item').forEach(menu => {
                menu.classList.remove('active');
            });
            document.querySelectorAll('.content-section').forEach(section => {
                section.classList.remove('active');
            });
            
            // 添加当前活动状态
            this.classList.add('active');
            const sectionId = this.getAttribute('data-section');
            document.getElementById(sectionId).classList.add('active');
        });
    });
}

// 初始化自定义脚本复选框
function initCustomScriptCheckbox() {
    const customScriptCheckbox = document.getElementById('custom-script');
    const scriptPathGroup = document.getElementById('script-path-group');
    
    // 检查初始状态
    scriptPathGroup.style.display = customScriptCheckbox.checked ? 'block' : 'none';
    
    // 添加事件监听
    customScriptCheckbox.addEventListener('change', function() {
        scriptPathGroup.style.display = this.checked ? 'block' : 'none';
    });
}

// 确保模态窗口容器存在
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
        document.body.appendChild(container);
    }
    return container;
}

// 添加日志消息
function addLogMessage(message) {
    const logContainer = document.getElementById('log-display');
    if (!logContainer) return;
    
    const now = new Date();
    const timestamp = `[${now.getFullYear()}-${(now.getMonth()+1).toString().padStart(2, '0')}-${now.getDate().toString().padStart(2, '0')} ${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}]`;
    
    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry';
    logEntry.innerHTML = `<span class="log-timestamp">${timestamp}</span> <span class="log-message">${message}</span>`;
    
    logContainer.appendChild(logEntry);
    logContainer.scrollTop = logContainer.scrollHeight;
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
        
        // 触发模态窗口显示动画
        setTimeout(() => {
            this.element.classList.add('active');
        }, 10);
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
            return `<button class="secondary-btn" id="cancel-btn-${this.id}">${this.options.cancelButtonText}</button>`;
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
    
    // 添加设置HTML内容的方法
    setHtmlContent(htmlContent) {
        const statusElement = document.getElementById(`modal-status-${this.id}`);
        if (statusElement) {
            statusElement.innerHTML = htmlContent;
        }
        // 同步更新到日志页面
        addLogMessage(`[${this.title}] 更新信息已设置`);
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
            cancelButton.className = 'primary-btn';
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
        
        // 添加关闭动画
        this.element.classList.remove('active');
        setTimeout(() => {
            // 删除元素
            if (this.element) {
                this.element.remove();
            }
        }, 300);
        
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
    constructor(title, message, onCloseCallback) {
        super(title, {
            showProgress: false,
            showCancelButton: true,
            cancelButtonText: '确定',
            showMinimizeButton: false,
            showLog: false
        });
        
        this.onCloseCallback = onCloseCallback;
        this.setStatus(message);
    }
    
    cancel() {
        this.close();
        if (this.onCloseCallback && typeof this.onCloseCallback === 'function') {
            this.onCloseCallback();
        }
    }
}

// 确认模态窗口类 - 继承自基类
class ConfirmModal extends ModalWindow {
    constructor(title, message, onConfirmCallback, onCancelCallback) {
        super(title, {
            showProgress: false,
            showCancelButton: true,
            showMinimizeButton: false,
            showLog: false
        });
        
        this.onConfirmCallback = onConfirmCallback;
        this.onCancelCallback = onCancelCallback;
        
        // 添加确认按钮
        const footer = document.getElementById(`modal-footer-${this.id}`);
        if (footer && onConfirmCallback) {
            const confirmBtn = document.createElement('button');
            confirmBtn.className = 'primary-btn';
            confirmBtn.id = `confirm-btn-${this.id}`;
            confirmBtn.textContent = this.options.confirmButtonText;
            confirmBtn.addEventListener('click', () => this.confirm());
            footer.insertBefore(confirmBtn, footer.firstChild);
        }
        
        this.setStatus(message);
    }
    
    confirm() {
        this.close();
        if (this.onConfirmCallback && typeof this.onConfirmCallback === 'function') {
            this.onConfirmCallback();
        }
    }
    
    cancel() {
        this.close();
        if (this.onCancelCallback && typeof this.onCancelCallback === 'function') {
            this.onCancelCallback();
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

function showConfirm(title, message, onConfirmCallback, onCancelCallback = () => {}) {
    return new ConfirmModal(title, message, onConfirmCallback, onCancelCallback);
}

function showProgress(title) {
    return new ProgressModal(title);
}

// 浏览文件函数
function browseFile(inputId) {
    pywebview.api.browse_file(inputId);
}

// 浏览文件夹函数
function browseFolder(inputId) {
    pywebview.api.browse_folder(inputId);
}

// 更新滑块值显示
function updateValue(id) {
    const input = document.getElementById(id);
    const valueDisplay = document.getElementById(`${id}-value`);
    if (input && valueDisplay) {
        valueDisplay.textContent = input.value;
    }
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
    const installPath = document.getElementById('install-path').value;
    if (!installPath) {
        showMessage('错误', '请选择汉化包路径');
        return;
    }
    
    const modal = new ProgressModal('安装汉化');
    modal.setStatus(`正在安装汉化包: ${installPath}`);
    modal.addLog('开始安装过程');
    
    // 模拟安装过程
    setTimeout(() => {
        modal.updateProgress(25, '正在验证文件完整性');
    }, 800);
    
    setTimeout(() => {
        modal.updateProgress(50, '正在解压文件');
    }, 1600);
    
    setTimeout(() => {
        modal.updateProgress(75, '正在复制文件到游戏目录');
    }, 2400);
    
    setTimeout(() => {
        modal.complete(true, '汉化安装完成');
    }, 3200);
}

function downloadOurPlay() {
    const modal = new ProgressModal('下载ourplay汉化');
    modal.addLog('连接到ourplay服务器...');
    
    // 模拟下载过程
    setTimeout(() => {
        modal.updateProgress(10, '正在获取下载列表');
    }, 1000);
    
    setTimeout(() => {
        modal.updateProgress(30, '开始下载汉化包');
    }, 2000);
    
    setTimeout(() => {
        modal.updateProgress(70, '下载中... 70%');
    }, 4000);
    
    setTimeout(() => {
        modal.complete(true, 'ourplay汉化包下载完成');
    }, 6000);
}

function cleanCache() {
    const cleanAll = document.getElementById('clean-all').checked;
    
    showConfirm(
        '确认清除缓存',
        cleanAll ? '确定要清除所有缓存和配置文件吗？此操作不可恢复。' : '确定要清除本地缓存吗？',
        () => {
            const modal = new ProgressModal('清除缓存');
            modal.addLog(cleanAll ? '开始清除所有缓存和配置文件' : '开始清除本地缓存');
            
            // 模拟清除过程
            setTimeout(() => {
                modal.updateProgress(50, '正在删除文件');
            }, 1000);
            
            setTimeout(() => {
                modal.complete(true, '缓存清除完成');
            }, 2000);
        }
    );
}

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
    const apiType = document.getElementById('api-type').value;
    const apiKey = document.getElementById('api-key').value;
    const apiSecret = document.getElementById('api-secret').value;
    
    if (!apiKey) {
        showMessage('错误', '请输入API密钥');
        return;
    }
    
    const modal = new ProgressModal('保存API配置');
    modal.addLog(`正在保存${apiType}的API配置...`);
    
    // 模拟保存过程
    setTimeout(() => {
        modal.complete(true, 'API配置保存成功');
    }, 1500);
}

function grabVocabulary() {
    const outputPath = document.getElementById('vocab-output').value;
    if (!outputPath) {
        showMessage('错误', '请选择保存路径');
        return;
    }
    
    const modal = new ProgressModal('抓取专有词汇');
    modal.addLog(`开始抓取专有词汇，保存到: ${outputPath}`);
    
    // 模拟抓取过程
    setTimeout(() => {
        modal.updateProgress(40, '正在分析游戏文件');
    }, 1500);
    
    setTimeout(() => {
        modal.updateProgress(80, '正在提取专有词汇');
    }, 3000);
    
    setTimeout(() => {
        modal.complete(true, `专有词汇已保存到 ${outputPath}`);
    }, 4500);
}

function searchText() {
    const searchText = document.getElementById('search-text').value;
    const searchPath = document.getElementById('search-path').value;
    
    if (!searchText) {
        showMessage('错误', '请输入要搜索的文本');
        return;
    }
    
    if (!searchPath) {
        showMessage('错误', '请选择搜索路径');
        return;
    }
    
    const modal = new ProgressModal('文本搜索');
    modal.addLog(`正在搜索: "${searchText}" 在 ${searchPath}`);
    
    // 模拟搜索过程
    setTimeout(() => {
        modal.updateProgress(50, '正在搜索文件...');
    }, 2000);
    
    setTimeout(() => {
        modal.complete(true, '搜索完成，结果已显示');
        
        // 更新搜索结果
        const resultsContainer = document.getElementById('search-results');
        resultsContainer.innerHTML = `
            <div class="log-entry">
                <span class="log-timestamp">[结果]</span>
                <span class="log-message">找到 3 个匹配项</span>
            </div>
            <div class="log-entry">
                <span class="log-timestamp">[文件]</span>
                <span class="log-message">${searchPath}/text1.txt - 第15行</span>
            </div>
            <div class="log-entry">
                <span class="log-timestamp">[文件]</span>
                <span class="log-message">${searchPath}/text2.txt - 第42行</span>
            </div>
        `;
    }, 4000);
}

function backupText() {
    const source = document.getElementById('backup-source').value;
    const dest = document.getElementById('backup-destination').value;
    
    if (!source) {
        showMessage('错误', '请选择源文件路径');
        return;
    }
    
    if (!dest) {
        showMessage('错误', '请选择备份保存路径');
        return;
    }
    
    const modal = new ProgressModal('备份原文');
    modal.addLog(`开始备份: ${source} 到 ${dest}`);
    
    // 模拟备份过程
    setTimeout(() => {
        modal.updateProgress(30, '正在读取源文件');
    }, 1000);
    
    setTimeout(() => {
        modal.updateProgress(60, '正在写入备份文件');
    }, 2500);
    
    setTimeout(() => {
        modal.complete(true, '备份完成');
    }, 4000);
}

function manageFonts() {
    showMessage('字体管理', '字体管理功能即将上线，敬请期待！');
}

function manageImages() {
    showMessage('图片资源', '图片资源管理功能即将上线，敬请期待！');
}

function manageAudio() {
    showMessage('音频资源', '音频资源管理功能即将上线，敬请期待！');
}

function adjustImage() {
    const imagePath = document.getElementById('image-path').value;
    const brightness = document.getElementById('brightness').value;
    const contrast = document.getElementById('contrast').value;
    
    if (!imagePath) {
        showMessage('错误', '请选择要调整的图片文件');
        return;
    }
    
    const modal = new ProgressModal('图片调整');
    modal.addLog(`正在调整图片: ${imagePath}`);
    modal.addLog(`亮度: ${brightness}, 对比度: ${contrast}`);
    
    // 模拟调整过程
    setTimeout(() => {
        modal.updateProgress(50, '正在处理图片');
    }, 1500);
    
    setTimeout(() => {
        modal.complete(true, '图片调整完成');
    }, 3000);
}

function calculateGacha() {
    const totalItems = parseInt(document.getElementById('total-items').value);
    const rareItems = parseInt(document.getElementById('rare-items').value);
    const drawCount = parseInt(document.getElementById('draw-count').value);
    
    if (isNaN(totalItems) || isNaN(rareItems) || isNaN(drawCount)) {
        showMessage('错误', '请输入有效的数值');
        return;
    }
    
    if (rareItems > totalItems) {
        showMessage('错误', '稀有物品数不能大于总物品数');
        return;
    }
    
    const modal = new ProgressModal('抽卡概率计算');
    modal.addLog(`开始计算: 总物品 ${totalItems}, 稀有物品 ${rareItems}, 抽取 ${drawCount} 次`);
    
    // 模拟计算过程
    setTimeout(() => {
        // 简单概率计算
        const probability = (1 - Math.pow((totalItems - rareItems) / totalItems, drawCount)) * 100;
        
        modal.updateProgress(100, '计算完成');
        modal.complete(true, `计算完成`);
        
        // 更新计算结果
        const resultsContainer = document.getElementById('calculation-results');
        resultsContainer.innerHTML = `
            <div class="log-entry">
                <span class="log-timestamp">[结果]</span>
                <span class="log-message">抽取 ${drawCount} 次的稀有物品获得概率: ${probability.toFixed(2)}%</span>
            </div>
            <div class="log-entry">
                <span class="log-timestamp">[详情]</span>
                <span class="log-message">总物品数: ${totalItems}</span>
            </div>
            <div class="log-entry">
                <span class="log-timestamp">[详情]</span>
                <span class="log-message">稀有物品数: ${rareItems}</span>
            </div>
        `;
    }, 2000);
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
    pywebview.api.check_game_path().then(function(path) {
        if (path && !document.getElementById('game-path').value) {
            document.getElementById('game-path').value = path;
        }
    }).catch(function() {
        // 找不到游戏路径时不做处理
    });
}

function saveSettings() {
    const gamePath = document.getElementById('game-path').value;
    const debugMode = document.getElementById('debug-mode').checked;
    
    const config = {
        game_path: gamePath,
        debug: debugMode
    };
    
    const modal = new ProgressModal('保存设置');
    modal.addLog('正在保存设置...');
    
    pywebview.api.save_config(config).then(function() {
        setTimeout(() => {
            modal.complete(true, '设置保存成功');
        }, 1000);
    }).catch(function(error) {
        modal.complete(false, '保存设置失败: ' + error);
    });
}

function useDefaultConfig() {
    showConfirm(
        '使用默认配置',
        '确定要使用默认配置吗？当前配置将被覆盖。',
        () => {
            const modal = new ProgressModal('加载默认配置');
            modal.addLog('正在加载默认配置...');
            
            pywebview.api.use_default_config().then(function() {
                setTimeout(() => {
                    modal.complete(true, '默认配置已加载');
                    loadSettings(); // 重新加载设置
                }, 1000);
            }).catch(function(error) {
                modal.complete(false, '加载默认配置失败: ' + error);
            });
        }
    );
}

function resetConfig() {
    showConfirm(
        '重置配置',
        '确定要重置当前配置吗？所有设置将被清空。',
        () => {
            document.getElementById('game-path').value = '';
            document.getElementById('debug-mode').checked = false;
            showMessage('提示', '配置已重置，请点击保存设置生效');
        }
    );
}

// 检查更新
function checkForUpdates() {
    pywebview.api.check_for_updates().then(function(info) {
        if (info && info.has_update) {
            update_info = info;
            showUpdateInfo(info);
        }
    }).catch(function() {
        // 检查更新失败时不做处理
    });
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
            htmlMessage += `<div style="margin: 10px 0; padding: 10px; background: rgba(0,0,0,0.05); border-radius: 4px; max-height: 300px; overflow-y: auto; border: 1px solid #eee;">${bodyHtml}</div>`;
        }
        
        // 添加发布时间
        if (update_info.published_at) {
            const publishDate = new Date(update_info.published_at);
            htmlMessage += `<p><strong>发布时间:</strong> ${publishDate.toLocaleDateString('zh-CN')}</p>`;
        }
        
        // 添加发布链接
        if (update_info.html_url) {
            htmlMessage += `<p><strong>发布页面:</strong> <a href="${update_info.html_url}" target="_blank" style="color: var(--primary-color); text-decoration: underline;">点击这里在浏览器中查看</a></p>`;
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
            htmlMessage += `<p style="margin-top: 15px; color: var(--accent-color);"><strong>注意:</strong> 您正在使用打包版本的应用，自动更新功能不可用。</p>`;
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
            modal.setHtmlContent(htmlMessage);
        }, 100);
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
    processedText = processedText.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" style="max-width: 100%; border-radius: 4px; margin: 10px 0;">');
    
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