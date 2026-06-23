// ============================
// 通用列表管理器
// ============================

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

async function changeFontForPackage() {
    const packageName = packageItemManager.getSelectedItem();
    if (!packageName) {
        showMessage('错误', '无法获取选中汉化包的名称');
        return;
    }

    showMessage('选择字体文件', '请选择字体文件', 
        async ()=>{
            const fontPath = await pywebview.api.browse_file('font-path');
            if (fontPath) {
                const modal = new ProgressModal('更换字体');
                modal.setStatus('开始');
                const result = await pywebview.api.change_font_for_package(packageName, fontPath, modal.id);
                if (result.success) {
                    modal.complete(true, '完成更换字体');
                    setTimeout(modal.close, 500);
                    refreshInstallPackageList();
                } else {
                    modal.addLog('更换失败');
                    modal.addLog(result.message);
                    modal.complete(false, result.message);
                }
            }
        }
    )
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
                            const exportPath = result;
                            
                            modal.close();
                            
                            const progressModal = new ProgressModal('导出字体');
                            progressModal.addLog(`开始导出字体 "${fontName}" 到 "${exportPath}"`);
                            
                            pywebview.api.export_selected_font(fontName, exportPath)
                                .then(function(result) {
                                    if (result.success) {
                                        progressModal.complete(true, '字体导出成功');
                                    setTimeout(progressModal.close, 250);
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
            };
            toggleCustomLangGui();
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

/**
 * 支持启用/禁用切换的列表管理器
 * 继承自 ItemListManager
 * @param {string} containerId - 容器元素ID
 * @param {Object} options - 配置选项
 * @param {function} options.onToggle - 切换启用状态时的回调 (item, enabled) => {}
 * @param {boolean|function} options.defaultEnabled - 默认启用状态（可设为函数，接收item返回布尔值）
 * @param {string} options.itemKey - 当item为对象时，用作唯一标识的属性名，默认为 'name'
 * @param {function} options.onSelect - 选中回调 (item) => {}
 * @param {string} options.emptyMessage - 列表为空时的提示文本
 * @param {string} options.itemIcon - 条目图标类名
 */
class ToggleItemListManager extends ItemListManager {
    constructor(containerId, options = {}) {
        super(containerId, options);
        // 启用状态映射 { itemKey: boolean }
        this.enabledMap = {};
        this.defaultEnabled = options.defaultEnabled || false;
        this.onToggle = options.onToggle || null;
        this.itemKey = options.itemKey || 'name'; // 从对象中提取键的属性
    }

    /**
     * 设置列表数据，同时初始化启用状态映射
     * @param {Array<string|Object>} items - 可包含字符串或对象，对象需包含 this.itemKey 指定字段
     */
    setItems(items) {
        // 初始化启用状态
        this.enabledMap = {};
        if (Array.isArray(items)) {
            items.forEach(item => {
                const key = this._getItemKey(item);
                // 若 defaultEnabled 为函数则调用，否则直接取值
                const defaultValue = typeof this.defaultEnabled === 'function'
                    ? this.defaultEnabled(item)
                    : this.defaultEnabled;
                this.enabledMap[key] = defaultValue;
            });
        }
        // 调用父类 setItems（会更新 this.items 并触发 updateList）
        super.setItems(items);
    }

    /**
     * 获取条目的唯一标识键
     */
    _getItemKey(item) {
        if (typeof item === 'string') {
            return item;
        } else if (item && typeof item === 'object') {
            return item[this.itemKey] ?? String(item);
        }
        return String(item);
    }

    /**
     * 获取条目的显示名称（用于列表文本）
     */
    _getDisplayName(item) {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
            return item.displayName || item[this.itemKey] || String(item);
        }
        return String(item);
    }

    /**
     * 重写列表项 DOM 创建方法，添加启用/禁用按钮
     */
    _createItemElement(item) {
        const key = this._getItemKey(item);
        const displayName = this._getDisplayName(item);
        const isEnabled = this.enabledMap[key] || false;

        const itemDiv = document.createElement('div');
        itemDiv.className = 'list-item';
        if (this.selectedItem === item) {
            itemDiv.classList.add('selected');
            itemDiv.setAttribute('data-selected', 'true');
        }

        itemDiv.innerHTML = `
            <div class="list-item-content">
                <i class="fas ${this.itemIcon}"></i>
                <span>${displayName}</span>
            </div>
            <div class="list-item-actions">
                <button class="list-action-btn toggle-btn" title="${isEnabled ? '禁用' : '启用'}" style="margin-right: 5px;">
                    <i class="fas ${isEnabled ? 'fa-toggle-on' : 'fa-toggle-off'}"></i>
                </button>
                <button class="list-action-btn select-btn" title="选择">
                    <i class="fas fa-check"></i>
                </button>
            </div>
        `;

        // 切换按钮事件
        const toggleBtn = itemDiv.querySelector('.toggle-btn');
        toggleBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const newState = !this.enabledMap[key];
            this.enabledMap[key] = newState;
            // 更新按钮图标和标题
            const icon = toggleBtn.querySelector('i');
            icon.className = `fas ${newState ? 'fa-toggle-on' : 'fa-toggle-off'}`;
            toggleBtn.title = newState ? '禁用' : '启用';
            // 触发外部回调
            if (this.onToggle && typeof this.onToggle === 'function') {
                this.onToggle(item, newState);
            }
        });

        // 选择按钮事件（保留原有选择功能）
        const selectBtn = itemDiv.querySelector('.select-btn');
        selectBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.setSelectedItem(item);
            if (this.onSelect && typeof this.onSelect === 'function') {
                this.onSelect(item);
            }
        });

        // 点击条目内容区域（非按钮部分）也触发选中
        itemDiv.addEventListener('click', (e) => {
            if (e.target.closest('.list-action-btn')) {
                return;
            }
            this.setSelectedItem(item);
            if (this.onSelect && typeof this.onSelect === 'function') {
                this.onSelect(item);
            }
        });

        return itemDiv;
    }

    /**
     * 获取当前启用状态映射
     */
    getEnabledMap() {
        return this.enabledMap;
    }

    /**
     * 手动设置某个条目的启用状态（会触发重新渲染）
     * @param {string} key - 条目标识键
     * @param {boolean} enabled
     */
    setEnabled(key, enabled) {
        if (this.enabledMap.hasOwnProperty(key)) {
            this.enabledMap[key] = enabled;
            this.updateList();
        }
    }
}

let modItemManager = new ToggleItemListManager('install-mod-list', {
    emptyMessage: '未找到模组',
    itemIcon: 'fa-language',
    defaultEnabled: false, // 默认全部禁用
    onSelect: (item) => {
        console.log('选中翻译器:', item);
    },
    onToggle: (item, enabled) => {
        console.log(`模组 ${item} 状态变为: ${enabled ? '启用' : '禁用'}`);
        toggleMod(item, enabled)
    }
});

async function refreshInstalledModList() {
    modItemManager.waitList();
    const result = await pywebview.api.find_installed_mod();
    if (result.success) {
        const merge = result.able.concat(result.disable);
        modItemManager.setItems(merge);
        result.able.forEach(item =>{
            modItemManager.enabledMap[item]=true;
        })
        modItemManager.updateList();
    }
}

async function toggleMod(item, enable) {
    const result = await pywebview.api.toggle_mod(item, enable);
}

function openModPath() {
    pywebview.api.open_mod_path();
}

async function deleteSelectedMod() {
    const packageName = modItemManager.getSelectedItem();
    if (!packageName) {
        showMessage('提示', '请先选择一个模组');
        return;
    }

    showConfirm('确认删除', `确定要删除模组 "${packageName}" 吗？此操作不可撤销。`,
        async function() {
            const result = await pywebview.api.delete_mod(packageName, 
                modItemManager.getEnabledMap[selectedItem]);
                    if (result.success) {
                        // 从管理器中移除该项，自动更新列表并清空选中状态
                        packageItemManager.removeItem(packageName);
                    } else {
                        showMessage('删除失败', `删除模组失败: ${result.message}`);
                    }
        },
        function() {
        }
    );
}

/**
 * 支持自定义动作按钮的列表管理器
 * 继承自 ItemListManager，在每个列表项的选中按钮左侧添加一个可配置文本和回调的按钮
 * @param {string} containerId - 容器元素ID
 * @param {Object} options - 配置选项
 * @param {string|function} options.actionButtonText - 按钮显示文本，可以是字符串或接收 item 返回字符串的函数
 * @param {function} options.actionButtonCallback - 按钮点击回调，接收当前 item 作为参数
 * @param {function} options.onSelect - 选中回调 (item) => {}
 * @param {string} options.emptyMessage - 列表为空时显示的提示
 * @param {string} options.itemIcon - 项目图标类名
 */
class ActionButtonItemListManager extends ItemListManager {
    constructor(containerId, options = {}) {
        super(containerId, options);
        this.actionButtonText = options.actionButtonText || null;
        this.actionButtonCallback = options.actionButtonCallback || null;
    }

    /**
     * 获取条目的显示名称（支持字符串或对象）
     * @param {string|Object} item
     * @returns {string}
     */
    _getDisplayName(item) {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object') {
            // 优先使用 displayName 或 name 属性，否则转为字符串
            return item.displayName || item.name || String(item);
        }
        return String(item);
    }

    /**
     * 重写列表项 DOM 创建方法，添加自定义动作按钮
     */
    _createItemElement(item) {
        const displayName = this._getDisplayName(item);
        const itemDiv = document.createElement('div');
        itemDiv.className = 'list-item';
        if (this.selectedItem === item) {
            itemDiv.classList.add('selected');
            itemDiv.setAttribute('data-selected', 'true');
        }

        // 构建操作区域 HTML
        let actionsHtml = '<div class="list-item-actions">';

        // 如果配置了动作按钮，添加动作按钮
        if (this.actionButtonText && this.actionButtonCallback) {
            const buttonText = typeof this.actionButtonText === 'function'
                ? this.actionButtonText(item)
                : this.actionButtonText;
            actionsHtml += `
                <button class="list-action-btn action-btn" title="${buttonText}" style="margin-right: 5px;">
                    <span>${buttonText}</span>
                </button>
            `;
        }

        // 添加原有的选择按钮
        actionsHtml += `
            <button class="list-action-btn select-btn" title="选择">
                <i class="fas fa-check"></i>
            </button>
        </div>`;

        itemDiv.innerHTML = `
            <div class="list-item-content">
                <i class="fas ${this.itemIcon}"></i>
                <span>${displayName}</span>
            </div>
            ${actionsHtml}
        `;

        // 绑定动作按钮事件（如果存在）
        if (this.actionButtonText && this.actionButtonCallback) {
            const actionBtn = itemDiv.querySelector('.action-btn');
            actionBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.actionButtonCallback(item);
            });
        }

        // 绑定选择按钮事件
        const selectBtn = itemDiv.querySelector('.select-btn');
        selectBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.setSelectedItem(item);
            if (this.onSelect && typeof this.onSelect === 'function') {
                this.onSelect(item);
            }
        });

        // 点击条目内容区域（非按钮部分）也触发选中
        itemDiv.addEventListener('click', (e) => {
            if (e.target.closest('.list-action-btn')) {
                return;
            }
            this.setSelectedItem(item);
            if (this.onSelect && typeof this.onSelect === 'function') {
                this.onSelect(item);
            }
        });

        return itemDiv;
    }
}

let symlinkStatus ;

async function loadSymlinkStatus() {
    try {
        const result = await pywebview.api.get_symlink_status();
        symlinkStatus = result.success ? result.status : {} 
    } catch (error) {
        console.log(error);
        addLogMessage(error);
    }
}

let symlinkManager;

async function refreshSymlink() {
    await loadSymlinkStatus();

    symlinkManager = new ActionButtonItemListManager('symlink-list', {
        actionButtonText: (item) => {
            let symlink = symlinkStatus[item];
            switch (symlink.status) {
                case 'not_exist':
                    return '不存在'
                case 'not_symlink':
                    return '文件夹'
                case 'symlink':
                    return '软链接'
                default:
                    return '处理错误'
            }
        },
        actionButtonCallback: (item) => {
            console.log('交互:', item);
            let symlink = symlinkStatus[item];
            switch (symlink.status) {
                case 'not_exist':
                    break;
                case 'not_symlink':
                    openPath(symlink.path);
                    break;
                case 'symlink':
                    openPath(symlink.target);
                    break;
                default:
                    showMessage('无法处理')
            }
        },
        onSelect: (item) => {
            console.log('选中:', item);
        },
        emptyMessage: '暂无数据',
        itemIcon: 'fa-file'
    });

    symlinkManager.setItems(['ProjectMoon', 'Unity']);
}

function openPath(path) {
    console.log(`打开 ${path}`);
    pywebview.api.run_func('open_explorer', path);
}


async function createSymlink() {
    const folderName = symlinkManager.getSelectedItem();
    const folder = symlinkStatus[folderName];
    try {
        if (folder.status === 'symlink') {
            showConfirm('是否要更换软链接目标？',
                `您已经创建了一个可用的软链接，它的目录是 ${folder.target}，是否更换目录？
                如果您确认继续，请选择您想要更换的目标路径`,
                async function() {
                    const targetDir = await pywebview.api.browse_folder('symlink-target-dir');
                    if (!targetDir || targetDir.length === 0) return;
                    const hasContent = await pywebview.api.run_func('evaluate_path', targetDir);
                    async function doCreate() {
                        await pywebview.api.run_func('remove_symlink', folder.path);
                        await pywebview.api.run_func('create_symlink', targetDir, folder.path);
                        await pywebview.api.move_folders(folder.target, targetDir);
                        refreshSymlink();
                    };
                    if (hasContent) {
                        showConfirm('警告', `目标文件夹中含有文件。可能出现非预期行为。
                            这有可能导致以下错误: 
                            游戏无法正常启动，点击删除软链接时同时移动目标文件夹下的所有文件。
                            正常的做法是创建一个空文件夹用来盛放文件。
                            如果你确定知道自己在做什么，请点击确定`,
                        doCreate, () => {})
                    } else {
                        doCreate();
                    };
                },
                () => {}
            )
        } else if (folder.status === 'not_symlink') {
            showConfirm('是否要创建软链接？',
                `如果您确认继续，请选择您想要把数据放在的文件夹`,
                async function() {
                    const targetDir = await pywebview.api.browse_folder('symlink-target-dir');
                    if (!targetDir || targetDir.length === 0) return;
                    const hasContent = await pywebview.api.run_func('evaluate_path', targetDir);
                    async function doCreate() {
                        await pywebview.api.move_folders(folder.path, targetDir);
                        await pywebview.api.run_func('remove_symlink', folder.path);
                        await pywebview.api.run_func('create_symlink', targetDir, folder.path);
                        refreshSymlink();
                    };
                    if (hasContent) {
                        showConfirm('警告', `目标文件夹中含有文件。可能出现非预期行为。
                            这有可能导致以下错误: 
                            游戏无法正常启动，点击删除软链接时同时移动目标文件夹下的所有文件。
                            正常的做法是创建一个空文件夹用来盛放文件。
                            如果你确定知道自己在做什么，请点击确定`,
                        doCreate, () => {})
                    } else {
                        doCreate();
                    };
                },
                () => {}
            )
        } else if (folder.status === 'not_exist') {
            showConfirm('创建软链接',
                '现在对应位置没有目录，如果您先前手动迁移了数据，那么点击是以创建软链接',
                () => {
                    showMessage('提示', '请选择您先前迁移的文件夹',
                        async ()=> {
                            const targetDir = await pywebview.api.browse_folder('symlink-target-dir');
                            if (!targetDir || targetDir.length === 0) return;
                            await pywebview.api.run_func('create_symlink', targetDir, folder.path);
                            refreshSymlink();
                        }
                    )
                },
            ()=>{});
        } else {
            showMessage('警告', '请先确保文件正确已安装');
        };
    } catch (error) {
        showMessage('错误', `创建软链接时发生错误
            ${error}`);
    };
}

async function removeSymlink() {
    const folderName = symlinkManager.getSelectedItem();
    const folder = symlinkStatus[folderName];
    try {
        if (folder.status === 'symlink') {
            showConfirm('是否要删除软链接？',
                `您已经创建了一个可用的软链接，它的目录是 ${folder.target}，是否删除？
                如果您确认继续，这将使文件夹重新回到c盘`,
                async function() {
                    await pywebview.api.run_func('remove_symlink', folder.path);
                    await pywebview.api.run_func('evaluate_path', folder.path);
                    await pywebview.api.move_folders(folder.target, folder.path);
                    refreshSymlink();
                },
                () => {}
            )
        } else {
            showMessage('警告', '当前数据项不是软链接');
        };
    } catch (error) {
        showMessage('错误', `删除软链接时发生错误
            ${error}`)
    };
}

