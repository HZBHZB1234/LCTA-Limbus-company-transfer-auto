function applyFancy() {
    const modal = new ProgressModal('应用美化文本');
    modal.addLog(`开始执行美化`);
    modal.addLog(`应用规则集${fancyManager.enabledMap}`);

    callApi('fancy_main', fancyManager.rulesets, fancyManager.enabledMap)
        .then(() => {
            modal.complete(true, '完成美化');
            setTimeout(() => {
                modal.close();
            }, 2000);
        })
        .catch((error) => {
            modal.addLog(`美化执行错误，错误提示${error}`);
            modal.complete(false, '美化执行失败');
        });
}

function fetchProperNouns() {
    const outputFormat = document.getElementById('proper-output').value;
    const skipSpace = document.getElementById('proper-skip-space').checked;
    const maxCount = document.getElementById('proper-max-count').value;
    const minCount = document.getElementById('proper-min-count').value;
    const joinChar = document.getElementById('proper-join-char').value;

    const updates = {
        'proper-join-char': joinChar,
        'proper-max-lenth': maxCount,
        'proper-min-lenth': minCount,
        'proper-output-type': outputFormat,
        'proper-disable-space': skipSpace
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
        modal.addLog(`文本分割符：${joinChar}`);
    }

    configManager.updateConfigValues(updates)
        .then(() => callApi('fetch_proper_nouns', modal.id))
        .then(function(result) {
            completeModalByResult(modal, result, '专有词汇抓取成功', '抓取失败');
        })
        .catch(function(error) {
            modal.complete(false, '抓取过程中发生错误: ' + error);
        });
}

function downloadOurplay() {
    const fontOption = document.getElementById('ourplay-font-option').value;
    const checkHash = document.getElementById('ourplay-check-hash').checked;
    const useApi = document.getElementById('ourplay-use-api').checked;

    const modal = new ProgressModal('下载OurPlay汉化包');
    modal.addLog('开始下载OurPlay汉化包...');
    modal.addLog(`字体选项: ${fontOption}`);
    modal.addLog(`哈希校验: ${checkHash ? '启用' : '禁用'}`);
    modal.addLog(`使用API: ${useApi ? '启用' : '禁用'}`);

    const updates = {
        'ourplay-font-option': fontOption,
        'ourplay-check-hash': checkHash,
        'ourplay-use-api': useApi
    };

    configManager.updateConfigValues(updates)
        .then(() => callApi('download_ourplay_translation', modal.id))
        .then(function(result) {
            if (!result.success && result.message === '已取消') {
                modal.cancel();
                return;
            }
            completeModalByResult(modal, result, 'OurPlay汉化包下载成功', '下载失败');
        })
        .catch(function(error) {
            modal.complete(false, '下载过程中发生错误: ' + error);
        });
}

async function downloadBubble() {
    const modal = new ProgressModal('开始下载');
    modal.setStatus('正在初始化...');
    modal.addLog('开始下载任务');
    await configManager.updateConfigValues(configManager.collectConfigFromUI());

    callApi('download_bubble', modal.id)
        .then(function(result) {
            completeModalByResult(modal, result, '下载任务已完成', '下载失败');
        })
        .catch(function(error) {
            modal.complete(false, '下载过程中发生错误: ' + error);
        });
}

function cleanCache() {
    const modal = new ProgressModal('清除缓存');

    const cleanProgress = document.getElementById('clean-progress').checked;
    const cleanNotice = document.getElementById('clean-notice').checked;
    const cleanMods = document.getElementById('clean-mods').checked;

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

    const updates = {
        'clean-progress': cleanProgress,
        'clean-notice': cleanNotice,
        'clean-mods': cleanMods
    };

    configManager.updateConfigValues(updates)
        .then(() => callApi('clean_cache', modal.id, customFilesList, cleanProgress, cleanNotice, cleanMods))
        .then(function(result) {
            if (!result.success && result.message === '已取消') {
                modal.complete(null, '操作已取消');
                return;
            }
            completeModalByResult(modal, result, '缓存清除成功', '清除失败');
        })
        .catch(function(error) {
            console.error('保存清理配置时发生错误:', error);
            modal.complete(false, '保存配置失败: ' + error);
        });
}

function addCustomFile() {
    const filePathInput = document.getElementById('custom-file-path');
    if (filePathInput && filePathInput.value.trim()) {
        const filePath = filePathInput.value.trim();
        const customFilesContainer = document.getElementById('custom-files-list');

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
        updateCustomFilesConfig();
    }
}

function removeCustomFile(element) {
    const fileItem = element.closest('.file-item');
    if (fileItem) {
        fileItem.remove();
        updateCustomFilesConfig();
    }
}

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

    configManager.updateConfigValue('custom-files', customFilesList);
}

function browseCustomFile() {
    callApi('browse_file', 'custom-file-path');
}

function browseCustomFolder() {
    callApi('browse_folder', 'custom-file-path');
}

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
    const downloadSource = document.getElementById('llc-download-source').value;

    const updates = {
        'llc-zip-type': zipType,
        'llc-use-proxy': useProxy,
        'llc-use-cache': useCache,
        'llc-dump-default': dumpDefault,
        'llc-download-source': downloadSource
    };

    configManager.updateConfigValues(updates)
        .then(() => {
            const modal = new ProgressModal('下载零协汉化包');
            modal.addLog('开始下载零协汉化包...');
            modal.addLog(`压缩格式: ${zipType}`);
            modal.addLog(`使用代理: ${useProxy ? '是' : '否'}`);
            modal.addLog(`使用缓存: ${useCache ? '是' : '否'}`);
            modal.addLog(`导出默认配置: ${dumpDefault ? '是' : '否'}`);
            modal.addLog(`下载源: ${downloadSource}`);
            return callApi('download_llc_translation', modal.id)
                .then(function(result) {
                    if (!result.success && result.message === '已取消') {
                        modal.cancel();
                        return;
                    }
                    completeModalByResult(modal, result, '零协汉化包下载成功', '下载失败');
                })
                .catch(function(error) {
                    modal.complete(false, '下载过程中发生错误: ' + error);
                });
        });
}

async function downloadMachine() {
    const modal = new ProgressModal('开始下载');
    modal.setStatus('正在初始化下载过程...');
    modal.addLog('开始下载任务');
    await configManager.updateConfigValues(configManager.collectConfigFromUI());

    callApi('download_LCTA_auto', modal.id)
        .then(function(result) {
            completeModalByResult(modal, result, '下载任务已完成', '下载失败');
        })
        .catch(function(error) {
            modal.complete(false, '下载过程中发生错误: ' + error);
        });
}

window.applyFancy = applyFancy;
window.fetchProperNouns = fetchProperNouns;
window.downloadOurplay = downloadOurplay;
window.downloadBubble = downloadBubble;
window.cleanCache = cleanCache;
window.addCustomFile = addCustomFile;
window.removeCustomFile = removeCustomFile;
window.updateCustomFilesConfig = updateCustomFilesConfig;
window.browseCustomFile = browseCustomFile;
window.browseCustomFolder = browseCustomFolder;
window.clearCustomFilesList = clearCustomFilesList;
window.downloadLLC = downloadLLC;
window.downloadMachine = downloadMachine;
