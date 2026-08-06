(function () {
    'use strict';

    // ──── 状态 ────
    var state = {
        apiReady: false,
        rulesets: [],            // fancy/ 规则集列表 [{name, rules, is_bus}]
        apiRaw: null,            // api_config 原始值（可能为密文）
        apiEncrypted: false,
        apiSettings: {},         // 解密后的 {服务名: 设置}
        busy: false,             // 任务执行中
        theme: 'light',
    };

    var DEFAULT_SELECTION = {
        name: 'LLM 文本美化',
        files: ['*.json'],
        rules: [
            {'files': ['Skills*.json', 'Characters*.json'], 'path': 'dataList[*].name'},
            {'files': ['Skills*.json'], 'path': 'dataList[*].desc'}
        ]
    };

    // ──── 工具 ────
    function $i(id) { return document.getElementById(id); }

    function getApi() {
        return (typeof window !== 'undefined' && window.pywebview && window.pywebview.api) ? window.pywebview.api : null;
    }

    function escapeHtml(str) {
        if (str === null || str === undefined) return '';
        var s = String(str);
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function parseJSON(value, fallback) {
        try {
            return JSON.parse(value);
        } catch (e) {
            return fallback;
        }
    }

    async function decryptText(password, encryptedBase64) {
        var combinedBuffer = Uint8Array.from(atob(encryptedBase64), function (c) { return c.charCodeAt(0); });
        var salt = combinedBuffer.slice(0, 16);
        var iv = combinedBuffer.slice(16, 28);
        var encryptedData = combinedBuffer.slice(28);
        var encoder = new TextEncoder();
        var keyMaterial = await crypto.subtle.importKey(
            'raw', encoder.encode(password), { name: 'PBKDF2' }, false, ['deriveKey']
        );
        var key = await crypto.subtle.deriveKey(
            { name: 'PBKDF2', salt: salt, iterations: 100000, hash: 'SHA-256' },
            keyMaterial, { name: 'AES-GCM', length: 256 }, false, ['decrypt']
        );
        var decryptedBuffer = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: iv }, key, encryptedData);
        return new TextDecoder().decode(decryptedBuffer);
    }

    async function resolveApiSettings() {
        if (state.apiRaw === null || state.apiRaw === '') {
            return {};
        }
        var text = state.apiRaw;
        if (state.apiEncrypted) {
            try {
                text = await decryptText('AutoTranslate', text);
            } catch (e) {
                text = null;
            }
        }
        if (text === null) {
            return {};
        }
        var parsed = parseJSON(text, null);
        return (parsed && typeof parsed === 'object') ? parsed : {};
    }

    // ──── 日志与进度 ────
    function addLog(message) {
        var logEl = $i('llmf-log');
        if (!logEl) return;
        var line = document.createElement('div');
        line.textContent = message;
        logEl.appendChild(line);
        logEl.scrollTop = logEl.scrollHeight;
    }

    function setProgress(pct, message) {
        var fill = $i('llmf-progress-fill');
        if (fill) fill.style.width = pct + '%';
        if (message) addLog(message);
    }

    function showProgressCard(show) {
        var card = $i('llmf-progress-card');
        if (card) card.classList.toggle('active', !!show);
    }

    function setBusy(busy) {
        state.busy = busy;
        $i('llmf-scan-btn').disabled = busy;
        $i('llmf-run-btn').disabled = busy;
        $i('llmf-cancel-btn').disabled = !busy;
    }

    function showResult(html) {
        var box = $i('llmf-result');
        $i('llmf-result-body').innerHTML = html;
        box.classList.add('active');
        box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // 后端线程事件分发入口
    window.__llmFancyDispatch = function (payload) {
        if (!payload) return;
        if (payload.type === 'log') {
            addLog(payload.message || '');
        } else if (payload.type === 'progress') {
            setProgress(payload.pct, payload.message || '');
        } else if (payload.type === 'scan_done') {
            onScanDone(payload.payload || {});
        } else if (payload.type === 'run_done') {
            onRunDone(payload.payload || {});
        }
    };

    // ──── 数据收集 ────
    function collectSelection() {
        var raw = $i('llmf-selection').value.trim();
        if (!raw) {
            return { name: 'LLM 文本美化', files: ['*.json'], rules: [] };
        }
        return parseJSON(raw, null);
    }

    function collectPayload() {
        var selection = collectSelection();
        var exclusions = [];
        var boxes = document.querySelectorAll('#llmf-exclusions input[type="checkbox"]:checked');
        for (var i = 0; i < boxes.length; i++) {
            exclusions.push(boxes[i].getAttribute('data-name'));
        }
        return {
            selection: selection,
            exclusions: exclusions,
            custom_prompt: $i('llmf-prompt').value,
            custom_prompt_enabled: $i('llmf-prompt-enabled').checked,
            max_length: parseInt($i('llmf-max-length').value, 10) || 20000,
            max_workers: parseInt($i('llmf-max-workers').value, 10) || 4,
            dedup_enabled: $i('llmf-dedup-enabled').checked,
        };
    }

    // ──── 初始化 ────
    async function init() {
        var api = getApi();
        if (!api) return;
        try {
            var stateData = await api.get_initial_state();
            if (stateData) {
                state.rulesets = stateData.rulesets || [];
                state.apiRaw = stateData.api ? stateData.api.raw : null;
                state.apiEncrypted = !!(stateData.api && stateData.api.encrypted);

                if (stateData.config) {
                    var cfg = stateData.config;
                    if (cfg.selection) {
                        $i('llmf-selection').value = JSON.stringify(cfg.selection, null, 2);
                    }
                    if (Array.isArray(cfg.exclusions)) {
                        for (var i = 0; i < cfg.exclusions.length; i++) {
                            var box = document.querySelector('#llmf-exclusions input[data-name="' + cssEscape(cfg.exclusions[i]) + '"]');
                            if (box) box.checked = true;
                        }
                    }
                    if (cfg.custom_prompt) $i('llmf-prompt').value = cfg.custom_prompt;
                    $i('llmf-prompt-enabled').checked = !!cfg.custom_prompt_enabled;
                    if (cfg.max_length) $i('llmf-max-length').value = cfg.max_length;
                    if (cfg.max_workers) $i('llmf-max-workers').value = cfg.max_workers;
                    if (typeof cfg.dedup_enabled !== 'undefined') {
                        $i('llmf-dedup-enabled').checked = !!cfg.dedup_enabled;
                    }
                }
                renderRulesets();
                updateApiStatus();
            }
            var theme = await api.get_config_value('theme', 'light');
            applyTheme(theme);
        } catch (e) {
            console.error('初始化失败:', e);
        }
    }

    function cssEscape(value) {
        return String(value).replace(/"/g, '\\"');
    }

    function renderRulesets() {
        var container = $i('llmf-exclusions');
        if (!container) return;
        var busRulesets = state.rulesets.filter(function (rs) { return rs.is_bus; });
        if (!busRulesets.length) {
            container.innerHTML = '<div class="llmf-empty">fancy/ 中暂无 bus 规则集可作为排除项</div>';
            return;
        }
        var html = '';
        for (var i = 0; i < busRulesets.length; i++) {
            var rs = busRulesets[i];
            html += '<label class="llmf-exclusion-item" title="' + escapeHtml(rs.name) + '">' +
                '<input type="checkbox" data-name="' + escapeHtml(rs.name) + '">' +
                '<span>' + escapeHtml(truncate(rs.name, 36)) + '</span>' +
                '<span class="llmf-count">' + rs.rules + ' 条规则</span>' +
                '</label>';
        }
        container.innerHTML = html;
    }

    function truncate(str, maxLen) {
        return str.length > maxLen ? str.substring(0, maxLen) + '...' : str;
    }

    function updateApiStatus() {
        var chip = $i('llmf-api-status');
        if (!chip) return;
        if (state.apiRaw === null || state.apiRaw === '') {
            chip.className = 'llmf-api-badge warn';
            chip.innerHTML = '<i class="fas fa-exclamation-triangle"></i> 未配置 LLM 服务，请先在「API 配置」页配置「LLM通用翻译服务」';
            return;
        }
        resolveApiSettings().then(function (settings) {
            var llm = settings['LLM通用翻译服务'] || {};
            var base = llm.base_url || '';
            var model = llm.model_name || '';
            if (base && model) {
                chip.className = 'llmf-api-badge';
                chip.innerHTML = '<i class="fas fa-check-circle"></i> LLM 通用翻译服务：' + escapeHtml(model) +
                    '（' + escapeHtml(base.replace(/^https?:\/\//, '')) + '）';
            } else {
                chip.className = 'llmf-api-badge warn';
                chip.innerHTML = '<i class="fas fa-exclamation-triangle"></i> LLM 服务配置不完整（缺少 base_url/model_name），请在「API 配置」页检查';
            }
        }).catch(function () {
            chip.className = 'llmf-api-badge warn';
            chip.innerHTML = '<i class="fas fa-exclamation-triangle"></i> 无法读取 API 配置';
        });
    }

    // ──── 主题 ────
    window.applyTheme = function (theme) {
        document.body.className = 'theme-' + (theme || 'light');
        document.body.setAttribute('data-injected-theme', theme || 'light');
    };

    // ──── 操作 ────
    function onValidateSelection() {
        var api = getApi();
        if (!api) return;
        var selection = collectSelection();
        if (selection === null) {
            addLog('JSON 格式错误：无法解析匹配规则');
            return;
        }
        api.validate_selection(selection).then(function (result) {
            if (result && result.success) {
                addLog('匹配规则校验通过');
            } else {
                addLog('匹配规则错误: ' + ((result && result.message) || '未知错误'));
            }
        });
    }

    function onLoadExample() {
        $i('llmf-selection').value = JSON.stringify(DEFAULT_SELECTION, null, 2);
    }

    function onScan() {
        var api = getApi();
        if (!api || state.busy) return;
        var payload = collectPayload();
        if (payload.selection === null) {
            addLog('JSON 格式错误：无法解析匹配规则');
            return;
        }
        $i('llmf-result').classList.remove('active');
        $i('llmf-log').innerHTML = '';
        setProgress(0, '');
        showProgressCard(true);
        setBusy(true);
        addLog('开始扫描预览...');
        api.scan_preview(payload).then(function (res) {
            if (res && res.success === false) {
                addLog('扫描失败: ' + ((res && res.message) || '未知错误'));
                setBusy(false);
            }
            // 成功时结果通过 scan_done 事件返回
        }).catch(function (err) {
            addLog('扫描出错: ' + err);
            setBusy(false);
        });
    }

    function onScanDone(result) {
        setBusy(false);
        if (!result) return;
        setProgress(100, '扫描完成');
        if (result.candidates > 0) {
            var errors = result.errors && result.errors.length ? '<br>警告：' + result.errors.length + ' 个文件读取失败（详见日志）' : '';
            var dedupText = result.deduped > 0
                ? '，去重合并：' + result.deduped + ' 条相同文本'
                : '';
            showResult(
                '<div class="llmf-result-row"><b>扫描完成</b></div>' +
                '<div class="llmf-result-row">语言包目录：<span class="llmf-result-path">' + escapeHtml(result.lang_dir || '') + '</span></div>' +
                '<div class="llmf-result-row">扫描文件：' + result.files_scanned + '，候选文本：' + result.candidates +
                '，被排除：' + result.excluded + dedupText + '</div>' +
                '<div class="llmf-result-row">确认无误后可点击「开始美化」' + errors + '</div>'
            );
        } else {
            showResult(
                '<div class="llmf-result-row"><b>没有匹配到任何候选文本</b></div>' +
                '<div class="llmf-result-row">请检查匹配规则（bus 语法）或排除规则集是否过宽</div>'
            );
        }
    }

    function onRun() {
        var api = getApi();
        if (!api || state.busy) return;
        var payload = collectPayload();
        if (payload.selection === null) {
            addLog('JSON 格式错误：无法解析匹配规则');
            return;
        }
        $i('llmf-result').classList.remove('active');
        $i('llmf-log').innerHTML = '';
        setProgress(0, '');
        showProgressCard(true);
        setBusy(true);
        resolveApiSettings().then(function (settings) {
            var llm = settings['LLM通用翻译服务'] || {};
            if (!llm.base_url || !llm.api_key) {
                addLog('错误：LLM 服务未配置（缺少 base_url / api_key），请先在「API 配置」页配置');
                setBusy(false);
                return;
            }
            addLog('开始 LLM 美化...');
            return api.run_beautify({
                config: payload,
                api_settings: llm,
            }).then(function (res) {
                if (res && res.success === false) {
                    addLog('启动失败: ' + ((res && res.message) || '未知错误'));
                    setBusy(false);
                }
            });
        }).catch(function (err) {
            addLog('出错: ' + err);
            setBusy(false);
        });
    }

    function onRunDone(result) {
        setBusy(false);
        if (!result) return;
        setProgress(100, '');
        if (result.cancelled) {
            addLog('任务已取消');
            showResult('<div class="llmf-result-row"><b>任务已取消，未生成规则集</b></div>');
            return;
        }
        if (result.success === false) {
            addLog('美化失败: ' + (result.message || '未知错误'));
            return;
        }
        var html =
            '<div class="llmf-result-row">候选：' + result.candidates + '，排除：' + result.excluded +
            (result.deduped > 0 ? '，去重合并：' + result.deduped : '') +
            '，批次：' + result.batches + '</div>' +
            '<div class="llmf-result-row">美化：<b>' + result.changed + '</b> 条，未变化：' + result.unchanged +
            '，失败：' + result.llm_failed + '</div>';
        if (result.ruleset_name) {
            html += '<div class="llmf-result-row">规则集：' + escapeHtml(result.ruleset_name) + '（已自动启用）</div>' +
                '<div class="llmf-result-row">保存位置：<span class="llmf-result-path">' + escapeHtml(result.ruleset_path || '') + '</span></div>' +
                '<div class="llmf-result-row">回到主窗口「文本美化」页点击「立即应用美化」即可生效</div>';
        } else {
            html += '<div class="llmf-result-row">没有产生任何文本变化，未生成规则集</div>';
        }
        showResult(html);
    }

    function onCancel() {
        var api = getApi();
        if (!api) return;
        api.cancel_beautify();
    }

    function onSaveConfig() {
        var api = getApi();
        if (!api) return;
        var payload = collectPayload();
        if (payload.selection === null) {
            addLog('JSON 格式错误：无法保存配置');
            return;
        }
        api.save_window_config(payload).then(function (res) {
            if (res && res.success) {
                addLog('配置已保存');
            } else {
                addLog('保存失败: ' + ((res && res.message) || '未知错误'));
            }
        }).catch(function (err) {
            addLog('保存出错: ' + err);
        });
    }

    // ──── 事件绑定 ────
    function bindEvents() {
        $i('llmf-selection-validate').addEventListener('click', onValidateSelection);
        $i('llmf-selection-example').addEventListener('click', onLoadExample);
        $i('llmf-scan-btn').addEventListener('click', onScan);
        $i('llmf-run-btn').addEventListener('click', onRun);
        $i('llmf-cancel-btn').addEventListener('click', onCancel);
        $i('llmf-save-config-btn').addEventListener('click', onSaveConfig);
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (!$i('llmf-selection')) return;
        $i('llmf-selection').value = JSON.stringify(DEFAULT_SELECTION, null, 2);
        bindEvents();
        // pywebview API 可能尚未注入（DOMContentLoaded 先于 pywebviewready）
        if (getApi()) {
            init();
            return;
        }
        var readyFlag = false;
        function handleReady() {
            if (readyFlag) return;
            readyFlag = true;
            init();
        }
        window.addEventListener('pywebviewready', handleReady);
        // 兜底：事件在注册前已触发
        if (window.pywebview && window.pywebview.api) {
            handleReady();
        }
        // 兜底：长时间无 API（如浏览器单独打开调试），显示错误而非无限加载
        setTimeout(function () {
            if (readyFlag || getApi()) return;
            var container = $i('llmf-exclusions');
            if (container) {
                container.innerHTML = '<div class="llmf-empty"><i class="fas fa-exclamation-triangle"></i> 无法连接到后端 API，请关闭窗口后重新打开</div>';
            }
        }, 10000);
    });
})();
