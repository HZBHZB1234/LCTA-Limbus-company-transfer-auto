// ============================
// 应用引导与初始化
// ============================

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    init();
    setupGlobalErrorHandling();
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
    
    pywebview.api.get_startup_data()
        .then(function(data) {
            if (data.message_config && Array.isArray(data.message_config) && data.message_config.length === 2) {
                showMessage(data.message_config[0], data.message_config[1]);
            }

            first_use = data.first_use;
            if (data.first_use) {
                window._pendingWelcomeContent = { type: 'markdown', url: 'assets/firstUse.md' };
                goAndShow('welcome');
            } else {
                refreshDashboard();
            }

            if (data.config_ok === false) {
                let errorMessage = "配置项格式错误，尝试修复?\n失败将会使用默认配置";
                if (data.config_error && Array.isArray(data.config_error) && data.config_error.length > 0) {
                    errorMessage += "\n\n详细错误信息:\n" + data.config_error.join("\n");
                }
                addLogMessage(errorMessage);

                {
                    pywebview.api.run_func('fix_config', data.config)
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
            }

            console.log('配置已加载到前端:', data.config);
            window.config = data.config;
            
            if (configManager) {
                setConfigToCache(data.config);
                
                configManager.applyConfigToUI().then(function() {
                    toggleCachePathInput();
                    toggleStoragePathInput();
                    toggleDevelopSettings();
                    toggleCustomLangGui();
                    toggleAutoProper();
                    toggleSteamCommand();
                    if (typeof onOurplaySourceChange === 'function') onOurplaySourceChange();
                    if (typeof onLauncherOurplaySourceChange === 'function') onLauncherOurplaySourceChange();
                });

                pywebview.api.check_show().then(
                    (result) => {
                        if (result.show && !first_use) {
                            window._pendingWelcomeContent = { type: 'html', html: simpleMarkdownToHtml(result.message) };
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
});
