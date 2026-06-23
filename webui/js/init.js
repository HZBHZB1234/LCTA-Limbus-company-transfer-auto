// ============================
// 应用引导与初始化
// ============================

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    init();
    setupGlobalErrorHandling();
    loadAndRenderMarkdown();
});

// 与后端通信的初始化
window.addEventListener('pywebviewready', function() {
    window.apiReady = true;
    
    addLogMessage('PyWebview API 已准备就绪', 'success');
    
    if (window.preApiErrors && window.preApiErrors.length > 0) {
        addLogMessage(`正在发送 ${window.preApiErrors.length} 条之前捕获的错误信息...`, 'info');
        
        window.preApiErrors.forEach(function(error) {
            pywebview.api.log(`[前端错误][延迟发送] ${error.message}\n堆栈: ${error.stack}`)
                .catch(function(sendError) {
                    console.error('无法将延迟错误发送到后端:', sendError);
                });
        });
        
        window.preApiErrors = [];
    }
    
    if (window.preApiRejections && window.preApiRejections.length > 0) {
        addLogMessage(`正在发送 ${window.preApiRejections.length} 条之前捕获的Promise拒绝信息...`, 'info');
        
        window.preApiRejections.forEach(function(rejection) {
            pywebview.api.log(`[前端Promise错误][延迟发送] ${rejection.message}`)
                .catch(function(sendError) {
                    console.error('无法将延迟Promise错误发送到后端:', sendError);
                });
        });
        
        window.preApiRejections = [];
    }
    
    removeConnectionMask();
    
    pywebview.api.get_attr('message_config')
        .then(function(message_config) {
            if (message_config && Array.isArray(message_config) && message_config.length === 2) {
            showMessage(message_config[0], message_config[1]);
            }
        });

    pywebview.api.get_attr('first_use').then(
        async function(result) {
            first_use = result
            if (result) {
                await loadMarkdownContent('assets/firstUse.md', 'welcome-content');
                goAndShow('welcome');
            } else {
                // 非首次使用则刷新仪表盘
                refreshDashboard();
            }
        }
    );

    pywebview.api.run_func('change_icon').catch(
        function(error) {
            console.log(error)
        }
    );

    pywebview.api.init_cache().catch(
        function(error) {
            console.log(error)
        }
    );

    pywebview.api.set_attr('http_port', window.location.port);
    
    pywebview.api.get_attr('config_ok')
        .then(function(config_ok) {
            if (config_ok === false) {
                pywebview.api.get_attr('config_error')
                    .then(function(config_error) {
                        let errorMessage = "配置项格式错误，尝试修复?\n失败将会使用默认配置";
                        if (config_error && Array.isArray(config_error) && config_error.length > 0) {
                            errorMessage += "\n\n详细错误信息:\n" + config_error.join("\n");
                        }

                        addLogMessage(errorMessage);

                        {
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
                                .catch(function(error) {
                                    showMessage("错误", "修复配置时出错，使用默认配置: " + error);
                                    pywebview.api.use_default()
                                    .then(function() {
                                    })
                                    .catch(function(error) {
                                        showMessage("错误", "使用默认配置时出错: " + error);
                                    });
                                });
                        }
                    })
            }
            })
            .catch(function(error) {
                addLogMessage('检查配置时出错: ' + error, 'error');
            });
    
    pywebview.api.get_attr('config')
        .then(function(config) {
            console.log('配置已加载到前端:', config);
            window.config = config;
            
            // 初始化配置管理器的缓存
            if (configManager) {
                // 将后端配置数据填充到缓存
                setConfigToCache(config);
                
                // 应用配置到UI
                configManager.applyConfigToUI().then(function() {
                    toggleCachePathInput();
                    toggleStoragePathInput();
                    toggleDevelopSettings();
                    toggleCustomLangGui();
                    toggleAutoProper();
                    toggleSteamCommand();
                });

                pywebview.api.check_show().then(
                    (result) => {
                        if (result.show && !first_use) {
                            const bodyHtml = simpleMarkdownToHtml(result.message);
                            const targetDiv = document.querySelector(`.${className}`);

                            targetDiv.innerHTML = bodyHtml;
                            goAndShow('welcome');
                        }
                });

                fancyManager = new FancyManager();
                fancyManager.init();
                
                elderManager.init();

            }
            checkGamePath();
            
            const autoCheckUpdate = configManager.getCachedValue('auto_check_update');
            pywebview.api.init_github()
                .then(function() {
                if (autoCheckUpdate && !first_use) {
                    autoCheckUpdates();
                    }
                }
            );

            pywebview.api.init_log();

            const current_theme = configManager.getCachedValue('theme') || 'light';
            themeManager.setTheme(current_theme, true);

            apiConfigManager = new APIConfigManager();
            apiConfigManager.init().then(success => {
                if (success) {
                    apiConfigManager.loadAPIServices();
                    let current_select_api = configManager.getCachedValue('ui_default.api_config.key')
                    if (!current_select_api) {
                        current_select_api = Object.keys(apiConfigManager.apiServices)[0];
                    }
                    // 获取选择框元素
                    const selectBox = document.querySelector('.api-service-select');

                    if (selectBox) {
                        selectBox.value = current_select_api;
                        
                        const changeEvent = new Event('change', {
                            bubbles: true,
                            cancelable: true
                        });
                        
                        selectBox.dispatchEvent(changeEvent);
                    };

                    apiConfigManager.loadAPIServicesTranslator();

                    let current_select_translator = configManager.getCachedValue('ui_default.translator.translator')
                    if (!current_select_translator) {
                        current_select_translator = Object.keys(apiConfigManager.apiServices)[0];
                    }
                    // 获取选择框元素
                    const selectBoxtranslator = document.querySelector('.translator-service-select');

                    if (selectBoxtranslator) {
                        selectBoxtranslator.value = current_select_translator;
                        
                        const changeEvent = new Event('change', {
                            bubbles: true,
                            cancelable: true
                        });
                        
                        selectBoxtranslator.dispatchEvent(changeEvent);
                    };
                }
            });
        });
});
