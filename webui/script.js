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

// 各功能函数
function startTranslation() {
    // 显示进度条
    document.getElementById('translation-progress').style.display = 'block';
    // 更新进度到20%
    updateProgress(20, '开始翻译...');
    
    pywebview.api.start_translation();
}

function installTranslation() {
    pywebview.api.install_translation().then(function(result) {
        if (result.success) {
            addLogMessage('汉化包安装成功: ' + result.message);
        } else {
            addLogMessage('汉化包安装失败: ' + result.message);
        }
    }).catch(function(error) {
        addLogMessage('安装过程中出现错误: ' + error);
    });
}

function downloadOurplay() {
    addLogMessage('开始下载OurPlay汉化包...');
    pywebview.api.download_ourplay_translation().then(function(result) {
        if (result.success) {
            addLogMessage('OurPlay汉化包下载成功: ' + result.message);
        } else {
            addLogMessage('OurPlay汉化包下载失败: ' + result.message);
        }
    }).catch(function(error) {
        addLogMessage('下载OurPlay汉化包时出现错误: ' + error);
    });
}

function cleanCache() {
    if (confirm('确定要清除本地缓存吗？此操作不可撤销。')) {
        pywebview.api.clean_cache().then(function(result) {
            if (result.success) {
                addLogMessage('缓存清除成功: ' + result.message);
            } else {
                addLogMessage('缓存清除失败: ' + result.message);
            }
        }).catch(function(error) {
            addLogMessage('清除缓存时出现错误: ' + error);
        });
    }
}

function downloadLLC() {
    addLogMessage('开始下载零协汉化包...');
    pywebview.api.download_llc_translation().then(function(result) {
        if (result.success) {
            addLogMessage('零协汉化包下载成功: ' + result.message);
        } else {
            addLogMessage('零协汉化包下载失败: ' + result.message);
        }
    }).catch(function(error) {
        addLogMessage('下载零协汉化包时出现错误: ' + error);
    });
}

function saveAPIConfig() {
    pywebview.api.save_api_config().then(function(result) {
        if (result.success) {
            addLogMessage('API配置保存成功: ' + result.message);
        } else {
            addLogMessage('API配置保存失败: ' + result.message);
        }
    }).catch(function(error) {
        addLogMessage('保存API配置时出现错误: ' + error);
    });
}

function fetchProperNouns() {
    pywebview.api.fetch_proper_nouns().then(function(result) {
        if (result.success) {
            addLogMessage('专有词汇抓取成功: ' + result.message);
        } else {
            addLogMessage('专有词汇抓取失败: ' + result.message);
        }
    }).catch(function(error) {
        addLogMessage('抓取专有词汇时出现错误: ' + error);
    });
}

function searchText() {
    pywebview.api.search_text().then(function(result) {
        if (result.success) {
            addLogMessage('文本搜索完成: ' + result.message);
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
                    
                    addLogMessage(`显示了 ${result.results.length} 个搜索结果`);
                }
            }
        } else {
            addLogMessage('文本搜索失败: ' + result.message);
        }
    }).catch(function(error) {
        addLogMessage('搜索文本时出现错误: ' + error);
    });
}

function backupText() {
    pywebview.api.backup_text().then(function(result) {
        if (result.success) {
            addLogMessage('备份完成: ' + result.message);
        } else {
            addLogMessage('备份失败: ' + result.message);
        }
    }).catch(function(error) {
        addLogMessage('备份文本时出现错误: ' + error);
    });
}

function manageFonts() {
    pywebview.api.manage_fonts().then(function(result) {
        if (result.success) {
            addLogMessage('字体管理: ' + result.message);
        } else {
            addLogMessage('字体管理失败: ' + result.message);
        }
    }).catch(function(error) {
        addLogMessage('字体管理时出现错误: ' + error);
    });
}

function manageImages() {
    pywebview.api.manage_images().then(function(result) {
        if (result.success) {
            addLogMessage('图片管理: ' + result.message);
        } else {
            addLogMessage('图片管理失败: ' + result.message);
        }
    }).catch(function(error) {
        addLogMessage('图片管理时出现错误: ' + error);
    });
}

function manageAudio() {
    pywebview.api.manage_audio().then(function(result) {
        if (result.success) {
            addLogMessage('音频管理: ' + result.message);
        } else {
            addLogMessage('音频管理失败: ' + result.message);
        }
    }).catch(function(error) {
        addLogMessage('音频管理时出现错误: ' + error);
    });
}

function adjustImage() {
    pywebview.api.adjust_image().then(function(result) {
        if (result.success) {
            addLogMessage('图片调整: ' + result.message);
        } else {
            addLogMessage('图片调整失败: ' + result.message);
        }
    }).catch(function(error) {
        addLogMessage('调整图片时出现错误: ' + error);
    });
}

function calculateGacha() {
    pywebview.api.calculate_gacha().then(function(result) {
        if (result.success) {
            addLogMessage('抽卡概率计算: ' + result.message);
            
            // 更新计算结果区域
            const resultsDiv = document.getElementById('calculation-results');
            resultsDiv.innerHTML = '';
            const resultEntry = document.createElement('div');
            resultEntry.className = 'log-entry';
            resultEntry.innerHTML = `<span class="log-timestamp">[概率结果]</span> <span class="log-message">${result.message}</span>`;
            resultsDiv.appendChild(resultEntry);
        } else {
            addLogMessage('概率计算失败: ' + result.message);
        }
    }).catch(function(error) {
        addLogMessage('计算抽卡概率时出现错误: ' + error);
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
    const logArea = document.getElementById('log-area');
    const now = new Date();
    const timestamp = `[${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}]`;
    
    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry';
    logEntry.innerHTML = `<span class="log-timestamp">${timestamp}</span> <span class="log-message">${message}</span>`;
    
    logArea.appendChild(logEntry);
    logArea.scrollTop = logArea.scrollHeight;
}

// 从Python后端接收日志消息
window.addEventListener('pywebviewready', function() {
    addLogMessage('WebUI已准备就绪');
    console.log('PyWebview API is ready');
});