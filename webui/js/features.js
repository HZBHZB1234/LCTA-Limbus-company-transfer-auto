// ============================
// 业务功能模块
// ============================

// === 文本美化 ===
class FancyManager {
    constructor() {
        this.rulesets = [];           // 所有规则集（包含内置和用户自定义），每个对象含 { name, desc, rules, builtin }
        this.enabledMap = {};          // 启用状态映射，键为规则集名称（需唯一）
        this.selectedRuleset = null;   // 当前选中的规则集对象
        this.listManager = null;       // ToggleItemListManager 实例
        this.initialized = false;
    }

    async init() {
        if (this.initialized) return;
        // 初始化列表管理器
        this.listManager = new ToggleItemListManager('fancy-ruleset-list', {
            emptyMessage: '暂无规则集',
            itemIcon: 'fa-paint-brush',
            defaultEnabled: false,
            onSelect: (item) => this.onSelectRuleset(item),
            onToggle: (item, enabled) => this.onToggleRuleset(item, enabled)
        });

        await this.loadRulesets();
        this.initialized = true;
    }

    async loadRulesets() {
        // 从后端获取规则集数据（包括内置和用户自定义）
        try {
            const result = await pywebview.api.get_fancy_rulesets();
            if (result.success) {
                // result.data 应包含 { builtin: [], user: [], enabled: {} }
                const builtin = result.data.builtin || [];
                const user = result.data.user || [];
                this.enabledMap = result.data.enabled || {};

                // 标记内置规则集
                builtin.forEach(rs => { rs.builtin = true; });
                user.forEach(rs => { rs.builtin = false; });

                this.rulesets = [...builtin, ...user];

                // 更新列表显示
                const items = this.rulesets.map(rs => rs.name);
                this.listManager.setItems(items);
                // 根据 enabledMap 设置每个条目的启用状态
                items.forEach(name => {
                    if (this.enabledMap[name] !== undefined) {
                        this.listManager.enabledMap[name] = this.enabledMap[name];
                    }
                });
                this.listManager.updateList();

                // 如果有规则集，默认选中第一个
                if (this.rulesets.length > 0) {
                    this.listManager.setSelectedItem(this.rulesets[0].name);
                    this.onSelectRuleset(this.rulesets[0].name);
                }
            } else {
                showMessage('错误', '加载规则集失败: ' + result.message);
            }
        } catch (error) {
            console.error('加载规则集出错:', error);
            showMessage('错误', '加载规则集时发生异常');
        }
    }

    onSelectRuleset(itemName) {
        const ruleset = this.rulesets.find(rs => rs.name === itemName);
        if (!ruleset) return;
        this.selectedRuleset = ruleset;
        this.updateEditorUI();
    }

    onToggleRuleset(itemName, enabled) {
        let conflict = [];
        this.rulesets.forEach(element => {
            if (element.name == itemName) {
                conflict = element.conflict;
            }
        });
        try {
            let conflictMessage = '';
            conflict.forEach(element => {
                if (this.enabledMap[element]) {
                    conflictMessage += `${element}  `;
                }
            });
            if (conflictMessage) {
                showMessage('冲突', `无法在启用  ${conflictMessage}  的情况下启用 ${itemName} 。
                    请先取消冲突的规则的启用后再启用 ${itemName} `);
                this.listManager.enabledMap[itemName] = false;
                this.listManager.updateList();
                return
            };
        } catch (e) {
            console.log(`切换时警告: ${e} 一般而言不是问题`)
        }
        this.enabledMap[itemName] = enabled;
    }

    updateEditorUI() {
        if (!this.selectedRuleset) {
            const nameEl = document.getElementById('fancy-ruleset-name');
            if (!nameEl) return;
            nameEl.value = '';
            nameEl.disabled = true;
            const descEl = document.getElementById('fancy-ruleset-desc');
            if (descEl) { descEl.value = ''; descEl.disabled = true; }
            const rulesEl = document.getElementById('fancy-ruleset-rules');
            if (rulesEl) { rulesEl.value = ''; rulesEl.disabled = true; }
            const saveBtn = document.getElementById('fancy-save-current-btn');
            if (saveBtn) saveBtn.disabled = true;
            const ruleEditorBtn = document.getElementById('fancy-open-rule-editor-btn');
            if (ruleEditorBtn) ruleEditorBtn.disabled = false;
            return;
        }

        const nameInput = document.getElementById('fancy-ruleset-name');
        const descInput = document.getElementById('fancy-ruleset-desc');
        const rulesTextarea = document.getElementById('fancy-ruleset-rules');
        const builtinCheck = document.getElementById('builtinRule');
        const saveBtn = document.getElementById('fancy-save-current-btn');
        const ruleEditorBtn = document.getElementById('fancy-open-rule-editor-btn');

        if (!nameInput) return;

        nameInput.value = this.selectedRuleset.name;
        descInput.value = this.selectedRuleset.desc || '';
        rulesTextarea.value = JSON.stringify(this.selectedRuleset.rules, null, 2);
        builtinCheck.style = (this.selectedRuleset.builtin || false) ? 'display: block;' : 'display: none;' ;

        // 内置规则集不可编辑
        const isBuiltin = this.selectedRuleset.builtin;
        const isBus = this.selectedRuleset.format === 'lcta-bus';
        const isQuickEdits = this.selectedRuleset.name === '_quick_edits';
        nameInput.disabled = isBuiltin || isQuickEdits;
        descInput.disabled = isBuiltin || isQuickEdits;
        rulesTextarea.disabled = isBuiltin || isQuickEdits;
        saveBtn.disabled = isBuiltin || isQuickEdits;
        if (ruleEditorBtn) ruleEditorBtn.disabled = isBus;
    }

    // 保存当前编辑的规则集
    async saveCurrent() {
        if (!this.selectedRuleset || this.selectedRuleset.builtin) return;

        const newName = document.getElementById('fancy-ruleset-name').value.trim();
        const newDesc = document.getElementById('fancy-ruleset-desc').value.trim();
        const rulesText = document.getElementById('fancy-ruleset-rules').value.trim();

        if (!newName) {
            showMessage('提示', '规则集名称不能为空');
            return;
        }

        // 验证 JSON
        let newRules;
        try {
            newRules = JSON.parse(rulesText);
            if (!Array.isArray(newRules)) throw new Error('规则必须是一个数组');
        } catch (e) {
            showMessage('错误', '规则 JSON 格式错误: ' + e.message);
            return;
        }

        // 如果名称改变，需要更新 enabledMap 和列表
        const oldName = this.selectedRuleset.name;
        if (oldName !== newName) {
            // 检查新名称是否已存在
            if (this.rulesets.some(rs => rs.name === newName)) {
                showMessage('错误', '已存在同名的规则集');
                return;
            }
            // 更新 enabledMap
            this.enabledMap[newName] = this.enabledMap[oldName];
            delete this.enabledMap[oldName];
            // 更新列表项
            this.listManager.items = this.rulesets.map(rs => rs.name);
            this.listManager.updateList();
        }

        // 更新当前规则集对象
        this.selectedRuleset.name = newName;
        this.selectedRuleset.desc = newDesc;
        this.selectedRuleset.rules = newRules;

        // 重新选中该规则集（刷新高亮）
        this.listManager.setSelectedItem(newName);
        // 刷新列表显示（名称可能已变）
        this.listManager.items = this.rulesets.map(rs => rs.name);
        this.listManager.updateList();

        // 持久化到后端
        try {
            const payload = { ...this.selectedRuleset, name: newName, desc: newDesc, rules: newRules };
            delete payload.builtin;
            const result = await pywebview.api.save_ruleset(newName, payload);
            if (!result || !result.success) throw new Error((result && result.error) || '后端拒绝保存');
            showMessage('成功', '规则集已保存');
        } catch (e) {
            showMessage('错误', '保存失败: ' + (e.message || e));
        }
    }

    // 新建规则集
    newRuleset() {
        const newName = prompt('请输入新规则集名称（不可与现有重名）');
        if (!newName) return;

        if (this.rulesets.some(rs => rs.name === newName)) {
            showMessage('错误', '名称已存在');
            return;
        }

        const newRuleset = {
            name: newName,
            desc: '',
            rules: [],
            builtin: false
        };
        this.rulesets.push(newRuleset);
        this.enabledMap[newName] = false;  // 默认禁用

        // 更新列表
        this.listManager.setItems(this.rulesets.map(rs => rs.name));
        this.listManager.updateList();
        this.listManager.setSelectedItem(newName);
        this.onSelectRuleset(newName);
    }

    // 删除当前选中的规则集（仅限非内置）
    deleteSelected() {
        if (!this.selectedRuleset) {
            showMessage('提示', '请先选中一个规则集');
            return;
        }
        if (this.selectedRuleset.builtin) {
            showMessage('提示', '内置规则集不能删除');
            return;
        }

        showConfirm('确认删除', `确定要删除规则集 "${this.selectedRuleset.name}" 吗？`,
            () => {
                const index = this.rulesets.indexOf(this.selectedRuleset);
                if (index !== -1) {
                    this.rulesets.splice(index, 1);
                    delete this.enabledMap[this.selectedRuleset.name];
                    // 更新列表
                    this.listManager.setItems(this.rulesets.map(rs => rs.name));
                    this.listManager.updateList();
                    this.selectedRuleset = null;
                    this.updateEditorUI();
                }
            },
            () => {}
        );
    }

    // 保存所有规则集及启用状态到后端
    async saveAll() {
        // 分离内置和用户规则集（内置不应保存，但启用状态需要保存）
        const userRulesets = this.rulesets.filter(rs => !rs.builtin);
        // 移除 builtin 字段后再发送
        const userData = userRulesets.map(({ builtin, ...rest }) => rest);

        // 将用户规则集逐个写入 fancy/ 文件夹
        try {
            for (const rs of userData) {
                const result = await pywebview.api.save_ruleset(rs.name, rs);
                if (!result || !result.success) throw new Error((result && result.error) || `保存 ${rs.name} 失败`);
            }
            await configManager.updateConfigValue('fancy-allow', JSON.stringify(this.enabledMap));
            await configManager.flushPendingUpdates();
            showMessage('成功', '全部规则集已保存');
        } catch (e) {
            showMessage('错误', '保存全部失败: ' + (e.message || e));
        }
    }

    // 格式化当前规则 JSON
    formatJson() {
        const textarea = document.getElementById('fancy-ruleset-rules');
        try {
            const obj = JSON.parse(textarea.value);
            textarea.value = JSON.stringify(obj, null, 2);
        } catch (e) {
            showMessage('错误', 'JSON 格式错误，无法格式化');
        }
    }
}

function doApplyFancy() {
    const modal = new ProgressModal('应用美化文本');
    modal.addLog(`开始执行美化`);
    modal.addLog(`应用规则集${fancyManager.enabledMap}`);
    pywebview.api.fancy_main(fancyManager.rulesets, fancyManager.enabledMap, modal.id).then(
        (result) => {
            if (result && result.message === '已取消') {
                modal.cancel();
                return;
            }
            if (result && result.success) {
                modal.complete(true, '完成美化');
                setTimeout(() => {
                    modal.close();
                }, 2000);
            } else {
                modal.complete(false, '美化执行失败');
            }
        }
    ).catch(
        (error) => {
            modal.addLog(`美化执行错误，错误提示${error}`);
            modal.complete(false, '美化执行失败');
        }
    );

};

async function applyFancy() {
    try {
        const result = await pywebview.api.check_fancy_marker();
        if (result && result.success && result.beautified) {
            showConfirm('提示',
                '该语言包已应用过文本美化，部分规则非幂等，重复应用可能产生非预期结果。是否继续？',
                () => doApplyFancy(),
                () => {}
            );
            return;
        }
    } catch (error) {
        console.error('检查美化标记失败:', error);
    }
    doApplyFancy();
};

// === 专有词汇 ===
function fetchProperNouns() {
    const outputFormat = document.getElementById('proper-output').value;
    const skipSpace = document.getElementById('proper-skip-space').checked;
    const maxCount = document.getElementById('proper-max-count').value;
    const minCount = document.getElementById('proper-min-count').value;
    const joinChar = document.getElementById('proper-join-char').value;
    
    const updates = {
        'proper-join-char': joinChar,
        'proper-max-count': maxCount,
        'proper-min-count': minCount,
        'proper-output': outputFormat,
        'proper-skip-space': skipSpace
    };

    const modal = new ProgressModal('抓取专有词汇');
    modal.addLog('开始抓取专有词汇...');
    modal.addLog(`输出格式: ${outputFormat}`);
    modal.addLog(`跳过含空格词汇: ${skipSpace ? '是' : '否'}`);
    modal.addLog(`最短长度: ${minCount}`);
    if (maxCount) {
        modal.addLog(`最大词汇数量: ${maxCount}`);
    }
    if (outputFormat === 'single') {
        modal.addLog(`文本分隔符：${joinChar}`);
    }
    
    configManager.updateConfigValues(updates)
        .then(() => {
            pywebview.api.fetch_proper_nouns(modal.id)
                .then(function(result) {
                    if (result && result.message === '已取消') {
                        modal.cancel();
                    } else if (result.success) {
                        modal.complete(true, '专有词汇抓取成功');
                    } else {
                        modal.complete(false, '抓取失败: ' + result.message);
                    }
                })
                .catch(function(error) {
                    modal.complete(false, '抓取过程中发生错误: ' + error);
                });
        })
        .catch(function(error) {
            modal.complete(false, '配置保存失败: ' + error);
        });
}


// === 下载功能 ===
function onOurplaySourceChange() {
    const sourceEl = document.getElementById('ourplay-source');
    const useApiGroup = document.getElementById('ourplay-use-api-group');
    const androidOptions = document.getElementById('ourplay-android-options');
    if (!sourceEl) return;
    const isAndroid = sourceEl.value === 'android';
    if (useApiGroup) useApiGroup.style.display = isAndroid ? 'none' : '';
    if (androidOptions) androidOptions.style.display = isAndroid ? '' : 'none';
}

function downloadOurplay() {
    const fontOption = document.getElementById('ourplay-font-option').value;
    const checkHash = document.getElementById('ourplay-check-hash').checked;
    const useApi = document.getElementById('ourplay-use-api').checked;
    const source = document.getElementById('ourplay-source').value;
    const official = document.getElementById('ourplay-official').checked;
    const referPackage = document.getElementById('ourplay-refer-package').value;

    const modal = new ProgressModal('下载OurPlay汉化包');
    modal.addLog('开始下载OurPlay汉化包...');
    modal.addLog(`字体选项: ${fontOption}`);
    modal.addLog(`哈希校验: ${checkHash ? '启用' : '禁用'}`);
    modal.addLog(`使用API: ${useApi ? '启用' : '禁用'}`);
    modal.addLog(`API源: ${source}`);
    if (source === 'android') {
        modal.addLog(`权威汉化: ${official ? '是' : '否（修改版）'}`);
        if (referPackage) modal.addLog(`基板包: ${referPackage}`);
    }

    // 批量更新配置
    const updates = {
        'ourplay-font-option': fontOption,
        'ourplay-check-hash': checkHash,
        'ourplay-use-api': useApi,
        'ourplay-source': source,
        'ourplay-official': official,
        'ourplay-refer-package': referPackage
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
        })
        .catch(function(error) {
            modal.complete(false, '配置保存失败: ' + error);
        });
}

async function downloadTiaozhua() {
    const modal = new ProgressModal('开始下载');
    modal.setStatus('正在初始化...');
    modal.addLog('开始下载任务');
    try {
        await configManager.updateConfigValues(configManager.collectConfigFromUI());
    } catch (error) {
        modal.complete(false, '配置保存失败: ' + error);
        return;
    }
    
    pywebview.api.download_lanzou_tiaozhua(
        modal.id).then(function(result) {
        if (result && result.message === '已取消') {
            modal.cancel();
        } else if (result.success) {
            modal.complete(true, '下载任务已完成');
        } else {
            modal.complete(false, '下载失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '下载过程中发生错误: ' + error);
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
                        modal.cancel();
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

    const modal = new ProgressModal('下载零协汉化包');
    modal.addLog('开始下载零协汉化包...');
    modal.addLog(`压缩格式: ${zipType}`);
    modal.addLog(`使用代理: ${useProxy ? '是' : '否'}`);
    modal.addLog(`使用缓存: ${useCache ? '是' : '否'}`);
    modal.addLog(`导出默认配置: ${dumpDefault ? '是' : '否'}`);
    modal.addLog(`下载源: ${download_source}`);

    configManager.updateConfigValues(updates)
        .then(() => {
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
        })
        .catch(function(error) {
            modal.complete(false, '配置保存失败: ' + error);
        });
}

async function downloadMachine() {
    const modal = new ProgressModal('开始下载');
    modal.setStatus('正在初始化下载过程...');
    modal.addLog('开始下载任务');
    try {
        await configManager.updateConfigValues(configManager.collectConfigFromUI());
    } catch (error) {
        modal.complete(false, '配置保存失败: ' + error);
        return;
    }
    
    pywebview.api.download_LCTA_auto(modal.id).then(function(result) {
        if (result && result.message === '已取消') {
            modal.cancel();
        } else if (result.success) {
            modal.complete(true, '下载任务已完成');
        } else {
            modal.complete(false, '下载失败: ' + result.message);
        }
    }).catch(function(error) {
        modal.complete(false, '下载过程中发生错误: ' + error);
    });
}

// ================================
// 配置管理函数
// ================================


// === 配置与设置 ===

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
        configManager.flushPendingUpdates();
        setTimeout(
            () => {
                modal.close();
            }, 500
        );
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
                        setTimeout(
                            () => {
                            modal.close();
                        }, 500
                        )
                    })
                    .catch(function(error) {
                        modal.complete(false, '保存配置刷新失败: ' + error);
                    });
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
    
    pywebview.api.use_default_config()
        .then(function(result) {
            if (result.success) {
                modal.complete(true, '已使用默认配置');
                // 重新加载配置
                if (configManager) {
                    configManager.applyConfigToUI();
                }
                setTimeout(function() {
                    modal.close();
                }, 1000)
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
                        }
                        modal.complete(true, '配置已重置');
                        setTimeout(function() {
                            modal.close();
                        }, 1000)
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


// === 从本地更新包手动更新 ===
function manualUpdateFromLocalZip() {
    pywebview.api.browse_file('').then(function(filePath) {
        if (!filePath) return;
        
        const fileName = filePath.split(/[/\\]/).pop();
        const modal = showConfirm(
            '手动更新',
            '确认要从本地更新包 <strong>' + fileName + '</strong> 执行更新吗？<br><small>更新完成后请手动重启程序。</small>',
            function() {
                modal.close();
                const progressModal = new ProgressModal('从本地文件更新');
                progressModal.addLog('正在验证更新包: ' + fileName);
                
                pywebview.api.perform_update_from_file(filePath, progressModal.id)
                    .then(function(result) {
                        if (result && result.message === '已取消') {
                            progressModal.cancel();
                            return;
                        }
                        if (result && result.success) {
                            progressModal.addLog('更新完成，请手动重启程序。');
                            progressModal.complete(true, '更新完成');
                        } else {
                            var msg = result && result.message ? result.message : '更新失败';
                            progressModal.addLog(msg);
                            progressModal.complete(false, msg);
                        }
                    })
                    .catch(function(error) {
                        progressModal.addLog('更新失败: ' + error);
                        progressModal.complete(false, '更新失败');
                    });
            },
            function() {
                addLogMessage('用户取消了手动更新');
            }
        );
    }).catch(function(error) {
        addLogMessage('选择文件失败: ' + error, 'error');
    });
}


// === 更新检测 ===
function manualCheckUpdates() {
    const modal = new ProgressModal('检查更新');
    modal.addLog('正在检查是否有可用更新...');
    
    pywebview.api.manual_check_update()
        .then(function(result) {
            if (result.has_update) {
                modal.complete(true, `发现新版本 ${result.latest_version}，请前往GitHub下载更新`);
                setTimeout(() => {
                    modal.close();
                    showUpdateInfo(result);
                }, 2000);
            } else {
                modal.complete(true, '当前已是最新版本');
                setTimeout(() => {
                    modal.close();
                }, 2000);
            }
        })
        .catch(function(error) {
            modal.complete(false, '检查更新时发生错误: ' + error);
            setTimeout(() => {
                modal.close();
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

// 添加一个变量来跟踪是否已经显示了更新窗口
let updateModalShown = false;

function escapeHtml(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function sanitizeHtml(html) {
    const template = document.createElement('div');
    template.innerHTML = html;
    template.querySelectorAll('script, iframe, object, embed, link, style, meta, form').forEach(el => el.remove());
    template.querySelectorAll('*').forEach(el => {
        Array.from(el.attributes).forEach(attr => {
            if (attr.name.toLowerCase().startsWith('on')) {
                el.removeAttribute(attr.name);
            }
        });
    });
    return template.innerHTML;
}

function doUpdate() {
            this.close();
            const progressModal = new ProgressModal('更新程序');
            progressModal.addLog('开始下载并安装更新...');
            pywebview.api.perform_update_in_modal(progressModal.id)
                .then(function(result) {
                    if (result && result.message === '已取消') {
                        progressModal.cancel();
                        return;
                    }
                    if (!result || !result.success) {
                        progressModal.addLog('更新失败');
                        progressModal.complete(false, '更新失败');
                        return;
                    }
                    progressModal.addLog('更新完成，请手动重启程序。');
                    progressModal.complete(true, '更新完成');
                })
                .catch(function(error) {
                    progressModal.addLog('更新失败: ' + error);
                    progressModal.complete(false, '更新失败');
                });
        }


// 显示更新信息
async function showUpdateInfo(update_info) {
    if (updateModalShown) {
        return;
    }
    
    updateModalShown = true;
    
    let htmlMessage = `<p><strong>发现新版本:</strong> ${update_info.latest_version}</p>`;
    htmlMessage += `<p><strong>当前版本:</strong> v5.0.1</p>`;
    
    if (update_info.title) {
        htmlMessage += `<p><strong>发布标题:</strong> ${escapeHtml(update_info.title)}</p>`;
    }
    
    if (update_info.body) {
        let body = update_info.body.trim();
        const bodyHtml = sanitizeHtml(simpleMarkdownToHtml(body));
        htmlMessage += `<div><strong>更新详情:</strong></div>`;
        htmlMessage += `<div class="markdown-body" id="update-markdown">${bodyHtml}</div>`;
    }
    
    if (update_info.published_at) {
        const publishDate = new Date(update_info.published_at);
        htmlMessage += `<p><strong>发布时间:</strong> ${publishDate.toLocaleDateString('zh-CN')}</p>`;
    }
    
    if (update_info.html_url) {
        htmlMessage += `<p><strong>发布页面:</strong> <a href="${escapeHtml(update_info.html_url)}" target="_blank" style="color: var(--color-primary); text-decoration: underline;">点击这里在浏览器中查看</a></p>`;
    }
    
    const modal = showConfirm(
        '发现新版本',
        '',
        doUpdate,
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
    
    setTimeout(async function() {
        const statusElement = document.getElementById(`modal-status-${modal.id}`);
        if (statusElement) {
            statusElement.innerHTML = htmlMessage;
        };
        let r = await pywebview.api.get_attr('is_frozen');
        if (!r) {
            r = r && (await pywebview.api.get_attr('debug') === 'true')
        };
        if (r) {
            const confirmButton = document.getElementById(`confirm-btn-${modal.id}`)
            confirmButton.removeEventListener('click', doUpdate)
            confirmButton.addEventListener('click', ()=>{
                showMessage('当前版本不兼容自动下载');
                modal.close()
            })
        }
    }, 100);
}


// === 硬件/系统初始化 ===

// 初始化函数
async function init() {
    // 预加载所有界面片段
    await preloadAllSections();

    // 初始化配置管理器
    configManager = new ConfigManager();
    
    // 初始化主题管理器
    themeManager = new ThemeManager();
    
    // 初始化拖拽文件管理器
    dragDropManager = new DragDropManager();
    setupDragDropCallback();

    // 初始化列表管理器（依赖 DOM 结构）
    initListManagers();
    
    // 初始化导航
    initNavigation();
    
    // 初始化密码切换
    initPasswordToggles();
    
    // 添加初始日志
    addLogMessage('系统已启动，准备就绪');
    addLogMessage('当前主题: ' + themeManager.currentTheme);
    addLogMessage('WebUI 初始化完成');
    
    // 初始化配置项悬停提示
    initTooltips();

    // 创建遮罩层
    createConnectionMask();
}


// === 游戏路径检测 ===
function checkGamePath() {
    const gamePath = configManager.getCachedValue('game_path');
    if (!gamePath) {
        pywebview.api.run_func('find_lcb')
            .then(function(foundPath) {
                if (foundPath) {
                    confirmGamePath(foundPath);
                } else {
                    requestGamePath();
                };
                configManager.applyConfigToUI();
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
                        configManager.applyConfigToUI();
                        addLogMessage('游戏路径已确认并保存: ' + foundPath, 'success');
                        pywebview.api.init_cache();
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

// ============================================
// 帮助抽屉管理器
// ============================================

// === 帮助抽屉 ===
const helpDrawer = {
    overlay: null,
    drawer: null,
    body: null,
    currentPage: null,
    currentTab: 'page-help',

    init() {
        this.overlay = document.getElementById('help-drawer-overlay');
        this.drawer = document.getElementById('help-drawer');
        this.body = document.getElementById('help-drawer-body');

        // Escape 关闭抽屉
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.drawer && this.drawer.classList.contains('open')) {
                this.close();
            }
        });
    },

    async open(page) {
        if (!this.drawer) this.init();
        this.currentPage = page;
        this.switchTab('page-help');

        this.overlay.classList.add('open');
        this.drawer.classList.add('open');

        // 加载页面对应的帮助文档
        await this.loadContent(`guide/${page}.md`);
    },

    async openIndex() {
        if (!this.drawer) this.init();
        this.currentPage = 'index';

        this.overlay.classList.add('open');
        this.drawer.classList.add('open');

        this.body.innerHTML = `
            <div class="markdown-body">
                <h2><i class="fas fa-compass"></i> 欢迎使用 LCTA 帮助中心</h2>
                <p>LCTA 工具箱是一款为《边狱公司》打造的全面辅助工具。选择下方入口获取帮助：</p>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:16px;">
                    <div class="setting-card" style="padding:16px;cursor:pointer;margin:0;"
                         onclick="helpDrawer.switchTab('page-help')">
                        <h4 style="margin-top:0;"><i class="fas fa-file-alt"></i> 页面帮助</h4>
                        <p style="font-size:13px;color:var(--color-text-secondary);">当前页面的详细操作说明</p>
                    </div>
                    <div class="setting-card" style="padding:16px;cursor:pointer;margin:0;"
                         onclick="helpDrawer.switchTab('guide')">
                        <h4 style="margin-top:0;"><i class="fas fa-book"></i> 使用指南</h4>
                        <p style="font-size:13px;color:var(--color-text-secondary);">完整功能手册与最佳实践</p>
                    </div>
                    <div class="setting-card" style="padding:16px;cursor:pointer;margin:0;"
                         onclick="helpDrawer.switchTab('faq')">
                        <h4 style="margin-top:0;"><i class="fas fa-comments"></i> 常见问题</h4>
                        <p style="font-size:13px;color:var(--color-text-secondary);">常见问题与排查方法</p>
                    </div>
                </div>
            </div>
        `;
    },

    close() {
        if (this.overlay) this.overlay.classList.remove('open');
        if (this.drawer) this.drawer.classList.remove('open');
    },

    switchTab(tab) {
        this.currentTab = tab;
        // 更新 tab 样式
        if (this.drawer) {
            this.drawer.querySelectorAll('.help-drawer-tab').forEach(t => {
                t.classList.toggle('active', t.dataset.tab === tab);
            });
        }

        switch(tab) {
            case 'page-help':
                if (this.currentPage && this.currentPage !== 'index') {
                    this.loadContent(`guide/${this.currentPage}.md`);
                }
                break;
            case 'guide':
                this.loadContent('guide/welcome.md');
                break;
            case 'faq':
                this.showFAQ();
                break;
        }
    },

    async loadContent(url) {
        if (!this.body) return;
        this.body.innerHTML = '<div class="help-drawer-loading"><i class="fas fa-spinner fa-spin"></i>&nbsp; 加载中...</div>';

        try {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`${response.status} ${response.statusText}`);
            }
            const markdownText = await response.text();
            const htmlContent = simpleMarkdownToHtml(markdownText);
            this.body.innerHTML = `${htmlContent}`;
        } catch (e) {
            this.body.innerHTML = `
                <div class="help-drawer-error">
                    <i class="fas fa-exclamation-circle" style="font-size:36px;"></i>
                    <div><strong>帮助内容加载失败</strong></div>
                    <small>${e.message}</small>
                    <small>文件: ${url}</small>
                </div>
            `;
        }
    },

    showFAQ() {
        if (!this.body) return;
        this.body.innerHTML = `
            <div class="markdown-body">
                <h2>常见问题解答</h2>

                <h3>Q: 如果遇到 Bug 或有改进建议，应该如何反馈？</h3>
                <p><strong>A:</strong> 推荐通过以下渠道反馈：</p>
                <ol>
                    <li><a href="https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto/issues" target="_blank">GitHub Issues</a>（国内访问可借助 Steam Community302 加速）</li>
                    <li><strong>QQ 群：1081988645</strong></li>
                </ol>
                <p><strong>反馈时请务必提供：</strong>Bug 出现的具体步骤、使用的 LCTA 版本号、相关的日志文件</p>

                <h3>Q: 如何获取日志文件？</h3>
                <p><strong>A:</strong> 打开软件安装目录 → 进入 <code>logs</code> 文件夹 → 若 Bug 发生在当天上传 <code>app.log</code>，否则根据日期选择对应日志文件</p>

                <h3>Q: 翻译失败，报错字样中带有 SSL Error？</h3>
                <p><strong>A:</strong> 请关闭加速器或代理后重试。</p>

                <h3>Q: Deepseek 报错 402？</h3>
                <p><strong>A:</strong> 请充值。更多报错码请看 <a href="https://api-docs.deepseek.com/zh-cn/quick_start/error_codes" target="_blank">Deepseek API 文档</a></p>

                <h3>Q: 汉化包更新失败怎么办？</h3>
                <p><strong>A:</strong></p>
                <ul>
                    <li>检查网络连接是否正常</li>
                    <li>尝试切换下载源（GitHub → 公益镜像）</li>
                    <li>开启/关闭代理加速选项</li>
                    <li>手动下载汉化包放入程序目录，使用"安装已有汉化"功能</li>
                </ul>

                <h3>Q: 调爪文本修改包不会自动导入？</h3>
                <p><strong>A:</strong> 如需在更新汉化包后自动下载导入调爪文本修改包，请在 Launcher 配置中启用"启用调爪文本"选项。</p>
            </div>
        `;
    }
};

// 页面加载时初始化帮助抽屉和帮助入口按钮
document.addEventListener('DOMContentLoaded', () => {
    helpDrawer.init();
    injectHelpButtons();
    restoreSidebarState();
});

// ============================================
// 仪表盘刷新
// ============================================

// === 仪表盘 ===
async function refreshDashboard() {
    if (!window.apiReady) return;

    const packageEl = document.getElementById('dash-package-value');
    const packageCard = document.getElementById('dash-translation-status');
    const launcherEl = document.getElementById('dash-launcher-value');
    const launcherCard = document.getElementById('dash-launcher-status');
    const apiEl = document.getElementById('dash-api-value');
    const apiCard = document.getElementById('dash-api-status');
    const updateEl = document.getElementById('dash-update-value');
    const updateCard = document.getElementById('dash-update-status');

    try {
        // 并行获取：汉化包列表 + 批量配置值
        const [packageResult, configBatch] = await Promise.all([
            pywebview.api.get_installed_packages().catch(() => null),
            pywebview.api.get_config_batch([
                'auto_check_update',
                'game_path',
                'launcher.work.update'
            ]).catch(() => null)
        ]);

        // === 汉化包状态 ===
        if (packageEl && packageCard) {
            if (packageResult && packageResult.success && packageResult.enable) {
                const count = (packageResult.packages && packageResult.packages.length) || 0;
                packageEl.textContent = count > 0 ? `已安装 ${count} 个汉化包` : '未安装汉化包';
                packageCard.className = 'dashboard-card status-card ' + (count > 0 ? 'success' : 'warning');
            } else if (packageResult && packageResult.success && !packageResult.enable) {
                packageEl.textContent = '未启用';
                packageCard.className = 'dashboard-card status-card warning';
            } else {
                packageEl.textContent = '无法检测';
                packageCard.className = 'dashboard-card status-card';
            }
        }

        // === 启动器配置状态 ===
        if (launcherEl && launcherCard) {
            const configValues = configBatch && configBatch.success ? configBatch.config_values : {};
            const launcherMode = configValues['launcher.work.update'];
            const gamePath = configValues['game_path'];
            if (launcherMode && launcherMode !== 'no') {
                launcherEl.textContent = '已配置（' + launcherMode + '）';
                launcherCard.className = 'dashboard-card status-card success';
            } else if (gamePath) {
                launcherEl.textContent = '游戏已设置，未配置启动器';
                launcherCard.className = 'dashboard-card status-card';
            } else {
                launcherEl.textContent = '未配置';
                launcherCard.className = 'dashboard-card status-card warning';
            }
        }

        // === 更新状态 ===
        if (updateEl && updateCard) {
            const configValues = configBatch && configBatch.success ? configBatch.config_values : {};
            const autoUpdate = configValues['auto_check_update'];
            if (autoUpdate === true || autoUpdate === 'true') {
                updateEl.textContent = '自动更新已开启';
                updateCard.className = 'dashboard-card status-card success';
            } else if (autoUpdate !== undefined && autoUpdate !== null) {
                updateEl.textContent = '自动更新未开启';
                updateCard.className = 'dashboard-card status-card';
            } else {
                updateEl.textContent = '状态未知';
                updateCard.className = 'dashboard-card status-card';
            }
        }

        // === API 配置状态 ===
        if (apiEl && apiCard) {
            // 通过 get_attr('config') 获取全量配置来检测 API key
            try {
                const fullConfig = await pywebview.api.get_attr('config');
                let apiCount = 0;
                if (fullConfig && typeof fullConfig === 'object') {
                    // 遍历 api_settings 相关键统计已配置的服务
                    for (const key of Object.keys(fullConfig)) {
                        if (key.startsWith('api_') && key.endsWith('_key') && fullConfig[key]) {
                            apiCount++;
                        }
                    }
                }
                if (apiCount > 0) {
                    apiEl.textContent = `已配置 ${apiCount} 个服务`;
                    apiCard.className = 'dashboard-card status-card success';
                } else {
                    apiEl.textContent = '未配置 API';
                    apiCard.className = 'dashboard-card status-card warning';
                }
            } catch (e) {
                apiEl.textContent = '点击配置';
                apiCard.className = 'dashboard-card status-card';
            }
        }
    } catch (e) {
        console.log('仪表盘刷新失败:', e);
    }

}


// === 拖拽文件管理 ===

// 拖拽文件管理器（毛玻璃遮罩版）
class DragDropManager {
    constructor() {
        this.maskElement = null;
        this.onFileDropCallback = null;
        this.hideTimer = null;
        this.dragCounter = 0;
        this.init();
    }

    init() {
        document.addEventListener('dragenter', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.dragCounter++;
            this.showMask();
        });

        document.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.showMask();
        });

        document.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.dragCounter--;
            if (this.dragCounter <= 0) {
                this.dragCounter = 0;
                this.hideMask();
            }
        });

        document.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.dragCounter = 0;
        });
    }

    showMask() {
        if (this.hideTimer) {
            clearTimeout(this.hideTimer);
            this.hideTimer = null;
        }
        if (this.maskElement) return;
        
        this.maskElement = document.createElement('div');
        this.maskElement.className = 'drop-zone-mask';
        this.maskElement.innerHTML = `
            <div class="drop-zone-mask-content">
                <i id="file-mask-char" class="fas fa-cloud-upload-alt"></i>
                <p>拖拽文件到这里</p>
                <small>支持汉化包安装，模组安装或是版本更新</small>
            </div>
        `;
        document.body.appendChild(this.maskElement);
    }
    
    hideMask() {
        if (this.hideTimer) {
            clearTimeout(this.hideTimer);
        }
        this.hideTimer = setTimeout(() => {
            this.hideTimer = null;
            if (this.maskElement) {
                this.maskElement.remove();
                this.maskElement = null;
            }
        }, 100);
    }
    
    hideMaskImmediate() {
        if (this.hideTimer) {
            clearTimeout(this.hideTimer);
            this.hideTimer = null;
        }
        if (this.maskElement) {
            this.maskElement.remove();
            this.maskElement = null;
        }
    }
    
    setOnFileDropCallback(callback) {
        this.onFileDropCallback = callback;
    }
}

// 打开规则编辑器独立窗口
function openRuleEditor() {
    pywebview.api.open_rule_editor();
}

// 打开简易翻译编辑器独立窗口
function openQuickEditor() {
    pywebview.api.open_quick_editor();
}

// 打开 LLM 文本美化独立窗口
function openLLMFancy() {
    pywebview.api.open_llm_fancy();
}

async function importBusRules() {
    try {
        const result = await pywebview.api.import_bus_rules();
        if (!result || result.cancelled) return;
        const escapeText = value => String(value ?? '').replace(/[&<>"']/g, char => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[char]);
        const lines = [];
        (result.imported || []).forEach(item => {
            const stats = item.stats || {};
            lines.push(`${escapeText(item.ruleset_name)}: ${stats.converted_rules || 0} 条规则，${stats.converted_actions || 0} 个操作`);
        });
        (result.errors || []).forEach(item => lines.push(`${escapeText(item.file)}: ${escapeText(item.error)}`));
        showMessage(result.success ? '导入完成' : '导入部分完成', lines.join('<br>') || '没有导入规则');
        await fancyManager.loadRulesets();
    } catch (error) {
        showMessage('错误', '导入文本替换规则失败: ' + error);
    }
}

// 设置拖拽文件回调函数（可根据需要自定义）
function setupDragDropCallback() {
    if (!dragDropManager) return;
    
    dragDropManager.setOnFileDropCallback(async (files) => {
        const modal = showConfirm('处理文件', '正在处理拖入的文件...');
        try {
            const result = await pywebview.api.handle_dropped_files(files);
            if (!result) {
                document.getElementById(`modal-status-${modal.id}`).innerHTML = '处理失败：未收到响应';
                return;
            }
            document.getElementById(`modal-status-${modal.id}`).innerHTML = result.message;
            if (result.success) {
                modal.eval_dropped_files = function() {
                    modal.close();
                    const progressModal = new ProgressModal('处理文件');
                    progressModal.addLog('正在处理文件...');
                    pywebview.api.eval_dropped_files(result.file_info, progressModal.id).then(async (processed) => {
                        if (processed && processed.message === '已取消') {
                            progressModal.cancel();
                            return;
                        }
                        if (processed && processed.imported) {
                            try {
                                await fancyManager.loadRulesets();
                            } catch (error) {
                                console.error('加载规则集失败:', error);
                            }
                        }
                        if (processed && processed.success) {
                            progressModal.complete(true, processed.message || '处理完成');
                        } else {
                            progressModal.complete(false, processed && processed.message ? processed.message : '处理失败');
                        }
                    }).catch(function(error) {
                        progressModal.complete(false, '处理过程中发生错误: ' + error);
                    });
                }
                modal.onConfirmCallback = modal.eval_dropped_files;
            }
        } catch (error) {
            document.getElementById(`modal-status-${modal.id}`).innerHTML = '处理拖入文件时出错：' + error;
        }
    });
}

