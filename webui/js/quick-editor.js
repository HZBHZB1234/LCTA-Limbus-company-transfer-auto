(function () {
    'use strict';

    // ──── 文件分类规则（与后端 rule_editor_constants.py 保持同步） ────
    var FILE_PREFIX_RULES = [
        ['BattleSpeechBubbleDlg', '战斗气泡'], ['BattleResultHint', '战斗结果提示'],
        ['BattleKeywords', '战斗关键词'], ['BattlePass', '通行证'],
        ['BattleUIText', '战斗UI'], ['BossRaidUI', '战斗映射UI'],
        ['BattleHint', '战斗提示'], ['BuffAbilities', '战斗Buff'],
        ['Bufs_Mirror', '镜牢Buff'], ['MirrorDungeon', '镜牢'],
        ['DailyLoginEvent', '签到'], ['CultivationEvent', '惜春养成'],
        ['CouponUIText', '兑换码UI'], ['ChoiceEvent', '事件选择'],
        ['DanteAbility', '但丁能力'], ['ActionEvents', '镜牢事件'],
        ['AbEventsResultLog', '事件效果'], ['AbnormalityGuides', '异想体线索/提示'],
        ['AttributeText', '七大罪'], ['AbEvents', '异想体事件'],
        ['AbDlg', '事件判定'], ['Announcer', '播报相关内容'],
        ['Assist', '援助相关'], ['ErrorCodeMsg', '错误代码'],
        ['UnitKeyword', '关键词'], ['Personalities', '人格'],
        ['Characters', '角色'], ['EGOgift', 'EGO饰品'],
        ['Dungeon', '地牢'], ['Enemies', '敌人'],
        ['PanicInfo', '效果'], ['Passives', '被动'],
        ['Railway', '轨道线'], ['Egos', '角色EGO'],
        ['Skill', '技能'], ['Stage', '舞台'],
        ['Story', '故事'], ['Event', '活动'], ['Bufs', '通用Buff'],
    ];
    var CATEGORY_ORDER = FILE_PREFIX_RULES.map(function (r) { return r[1]; }).concat(['Other']);

    // ──── 状态 ────
    var state = {
        langFiles: [],              // 文件路径数组
        currentFile: null,          // 当前打开的文件相对路径
        currentFileContent: null,   // 原始文件 JSON 字符串（用于 diff）
        fileEditor: null,          // CodeMirror 6 EditorView
        pendingEdits: [],           // {file, path, old, new}[]
        searchResults: null,        // {results_by_category: {}, total_matches: 0}
        searchActiveCategory: null,  // 搜索结果当前下钻分类
        activeTab: 'file-list',     // 'file-list' | 'search-results'
        isDirty: false,             // 编辑器是否有未记录的修改
        _apiReady: false,
    };

    // 编辑器内搜索面板状态桥接（供 EditorSearchPanel 共用模块使用）
    var qeSearchBridge = {
        isOpen: false,
        panelLeft: null,
        panelTop: null,
        panelRight: null,
        onPanelClose: function () {},
    };

    // ──── 工具函数 ────
    function $i(id) { return document.getElementById(id); }

    function getApi() {
        return (typeof window !== 'undefined' && window.pywebview && window.pywebview.api) ? window.pywebview.api : null;
    }

    function escapeHtml(str) {
        if (str === null || str === undefined) return '<i>null</i>';
        var s = String(str);
        return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function truncate(str, maxLen) {
        maxLen = maxLen || 60;
        if (!str) return '';
        var s = String(str);
        return s.length > maxLen ? s.substring(0, maxLen) + '...' : s;
    }

    // 后端返回 Windows 反斜杠分隔的相对路径，统一规范化为正斜杠
    function normalizePath(p) {
        return String(p || '').replace(/\\/g, '/');
    }

    function getCategory(relPath) {
        relPath = normalizePath(relPath);
        for (var i = 0; i < FILE_PREFIX_RULES.length; i++) {
            var prefix = FILE_PREFIX_RULES[i][0];
            // 与后端 browser.py get_category 语义一致：任意位置子串匹配
            if (relPath.indexOf(prefix) !== -1) {
                return FILE_PREFIX_RULES[i][1];
            }
        }
        return 'Other';
    }

    function confirmDialog(msg) {
        return window.confirm(msg);
    }

    // ──── 初始化 ────
    function init() {
        bindEvents();
        initResizeHandles();
        // CodeMirror 是 ESM 模块导入，可能尚未就绪
        waitForApi();
    }

    function waitForApi() {
        var api = getApi();
        if (api) {
            checkCodeMirrorReady();
            return;
        }
        // pywebview API 可能尚未注入
        var retries = 0;
        var maxRetries = 50;
        var interval = setInterval(function () {
            retries++;
            api = getApi();
            if (api) {
                clearInterval(interval);
                checkCodeMirrorReady();
            } else if (retries >= maxRetries) {
                clearInterval(interval);
                showError('无法连接到后端 API，请刷新窗口重试。');
            }
        }, 100);
    }

    function checkCodeMirrorReady() {
        if (window.CodeMirror && window.CodeMirror.EditorView) {
            state._apiReady = true;
            onApiReady();
            return;
        }
        var retries = 0;
        var interval = setInterval(function () {
            retries++;
            if (window.CodeMirror && window.CodeMirror.EditorView) {
                clearInterval(interval);
                state._apiReady = true;
                onApiReady();
            } else if (retries >= 50) {
                clearInterval(interval);
                showError('CodeMirror 模块加载失败，请检查网络连接。');
            }
        }, 100);
    }

    async function onApiReady() {
        try {
            await Promise.all([
                loadLangFiles(),
                loadQuickEdits(),
                syncThemeFromMain(),
            ]);
            initFileEditor();
            if (window.EditorSearchPanel) {
                EditorSearchPanel.attach($i('qe-editor-area'), qeSearchBridge);
            } else {
                console.warn('[quick-editor] EditorSearchPanel 未加载，编辑器内搜索面板不可用');
            }
            renderFileList();
        } catch (e) {
            console.error('初始化失败:', e);
        }
    }

    function showError(msg) {
        var el = $i('qe-file-list');
        el.innerHTML = '<div class="qe-empty-state" style="font-size:12px;padding:20px;color:var(--color-danger);">' +
            '<i class="fas fa-exclamation-triangle"></i>' + escapeHtml(msg) + '</div>';
    }

    // ──── CodeMirror 6 ────
    function initFileEditor() {
        var CM = window.CodeMirror;
        var parentEl = $i('qe-editor-area');
        if (state.fileEditor) {
            state.fileEditor.destroy();
            state.fileEditor = null;
        }
        state.fileEditor = new CM.EditorView({
            doc: '',
            extensions: [
                CM.basicSetup,
                CM.json(),
                CM.keymap.of([]),
                CM.EditorView.updateListener.of(function (update) {
                    if (update.docChanged && state.currentFile) {
                        state.isDirty = true;
                        updateStatusBar();
                    }
                    if (update.selectionSet) {
                        updateCursorPosition();
                    }
                }),
            ],
            parent: parentEl,
        });
        // 初始显示空状态，隐藏编辑器
        parentEl.querySelector('.qe-empty-state') && (parentEl.querySelector('.qe-empty-state').style.display = 'flex');
        updateStatusBar();
    }

    function setEditorContent(text) {
        if (!state.fileEditor) return;
        var CM = window.CodeMirror;
        var transaction = state.fileEditor.state.update({
            changes: { from: 0, to: state.fileEditor.state.doc.length, insert: text },
        });
        state.fileEditor.dispatch(transaction);
        state.isDirty = false;
        updateStatusBar();
        updateCursorPosition();
    }

    function getEditorContent() {
        if (!state.fileEditor) return '';
        return state.fileEditor.state.doc.toString();
    }

    // ──── 文件浏览 ────
    async function loadLangFiles() {
        var api = getApi();
        if (!api) return;
        try {
            var files = await api.get_lang_files();
            state.langFiles = files || [];
        } catch (e) {
            console.error('加载文件列表失败:', e);
            state.langFiles = [];
        }
    }

    function renderFileList() {
        var container = $i('qe-file-list');
        if (!state.langFiles.length) {
            container.innerHTML = '<div class="qe-empty-state" style="font-size:12px;padding:20px;">' +
                '<i class="fas fa-folder-open"></i>未找到 JSON 文件<br><small>请先在主应用中配置游戏路径</small></div>';
            return;
        }
        // 按分类分组
        var groups = {};
        var otherKey = 'Other';
        for (var i = 0; i < state.langFiles.length; i++) {
            var cat = getCategory(state.langFiles[i]);
            if (!groups[cat]) groups[cat] = [];
            groups[cat].push(state.langFiles[i]);
        }
        // 按 CATEGORY_ORDER 排序输出
        var html = '';
        for (var c = 0; c < CATEGORY_ORDER.length; c++) {
            var catName = CATEGORY_ORDER[c];
            var files = groups[catName];
            if (!files || !files.length) continue;
            html += '<div class="qe-category-group">';
            html += '<div class="qe-category-header" data-category="' + escapeHtml(catName) + '">';
            html += '<span class="qe-category-icon">▼</span>';
            html += escapeHtml(catName);
            html += '<span class="qe-category-count">' + files.length + '</span>';
            html += '</div>';
            html += '<div class="qe-category-files">';
            for (var f = 0; f < files.length; f++) {
                var fileName = normalizePath(files[f]).split('/').pop();
                var isActive = state.currentFile === files[f];
                html += '<div class="qe-file-item' + (isActive ? ' active' : '') + '" data-file="' + escapeHtml(files[f]) + '">';
                html += '<span class="qe-file-icon"><i class="fas fa-file-code"></i></span>';
                html += '<span class="qe-file-name">' + escapeHtml(fileName) + '</span>';
                html += '</div>';
            }
            html += '</div></div>';
        }
        // 其他未分组的
        delete groups['Other'];
        var remaining = Object.keys(groups);
        if (remaining.length || (groups['Other'] && groups['Other'].length)) {
            // 重新获取 Other
            var otherFiles = [];
            for (var j = 0; j < state.langFiles.length; j++) {
                var cat2 = getCategory(state.langFiles[j]);
                if (cat2 === 'Other') otherFiles.push(state.langFiles[j]);
            }
            if (otherFiles.length) {
                html += '<div class="qe-category-group">';
                html += '<div class="qe-category-header" data-category="Other">';
                html += '<span class="qe-category-icon">▼</span>其他';
                html += '<span class="qe-category-count">' + otherFiles.length + '</span>';
                html += '</div>';
                html += '<div class="qe-category-files">';
                for (var o = 0; o < otherFiles.length; o++) {
                    var fName = normalizePath(otherFiles[o]).split('/').pop();
                    var isAct = state.currentFile === otherFiles[o];
                    html += '<div class="qe-file-item' + (isAct ? ' active' : '') + '" data-file="' + escapeHtml(otherFiles[o]) + '">';
                    html += '<span class="qe-file-icon"><i class="fas fa-file-code"></i></span>';
                    html += '<span class="qe-file-name">' + escapeHtml(fName) + '</span>';
                    html += '</div>';
                }
                html += '</div></div>';
            }
        }
        container.innerHTML = html;
        // 绑定事件
        bindFileListEvents(container);
    }

    function bindFileListEvents(container) {
        // 分类折叠
        var headers = container.querySelectorAll('.qe-category-header');
        for (var i = 0; i < headers.length; i++) {
            headers[i].addEventListener('click', function () {
                var icon = this.querySelector('.qe-category-icon');
                var filesDiv = this.nextElementSibling;
                if (filesDiv) {
                    filesDiv.classList.toggle('collapsed');
                    icon.classList.toggle('collapsed');
                }
            });
        }
        // 文件项
        var items = container.querySelectorAll('.qe-file-item');
        for (var j = 0; j < items.length; j++) {
            items[j].addEventListener('click', function () {
                // 单选高亮
                var allItems = container.querySelectorAll('.qe-file-item');
                for (var k = 0; k < allItems.length; k++) {
                    allItems[k].classList.remove('active');
                }
                this.classList.add('active');
            });
            items[j].addEventListener('dblclick', function () {
                var relPath = this.getAttribute('data-file');
                openFile(relPath);
            });
        }
    }

    async function openFile(relPath) {
        var api = getApi();
        if (!api) return;
        try {
            var result = await api.get_file_content(relPath);
            if (result.error) {
                alert('加载文件失败: ' + result.error);
                return;
            }
            var formatted;
            if (result.parsed) {
                formatted = JSON.stringify(result.parsed, null, 2);
            } else {
                formatted = result.raw || '';
            }
            state.currentFile = relPath;
            state.currentFileContent = formatted;
            setEditorContent(formatted);
            // 隐藏空状态
            var emptyState = $i('qe-editor-area').querySelector('.qe-empty-state');
            if (emptyState) emptyState.style.display = 'none';
            // 更新当前文件标签
            $i('qe-current-file-label').textContent = relPath;
            $i('qe-status-file').textContent = 'JSON';
            // 刷新文件列表高亮
            renderFileList();
        } catch (e) {
            console.error('打开文件失败:', e);
            alert('打开文件失败: ' + e);
        }
    }

    async function refreshFileList() {
        await loadLangFiles();
        renderFileList();
    }

    // ──── 修改追踪 ────
    async function recordChanges() {
        if (!state.currentFile) {
            alert('请先打开一个文件');
            return;
        }
        var file = state.currentFile;   // 发起时的文件，await 期间可能被切换
        var currentContent = getEditorContent();
        if (!currentContent.trim()) return;

        // 验证 JSON
        var newParsed, origParsed;
        try {
            newParsed = JSON.parse(currentContent);
        } catch (e) {
            alert('JSON 格式无效，无法记录修改:\n' + e.message);
            return;
        }
        try {
            origParsed = JSON.parse(state.currentFileContent);
        } catch (e) {
            origParsed = {};
        }

        var api = getApi();
        if (!api) return;

        try {
            var changes = await api.diff_json(origParsed, newParsed);
            // await 期间用户可能已切换文件：丢弃本次记录，保留原文件状态
            if (state.currentFile !== file) return;
            if (!changes || !changes.length) {
                updateStatus('没有检测到修改');
                return;
            }
            // 追加到 pendingEdits
            for (var i = 0; i < changes.length; i++) {
                var ch = changes[i];
                state.pendingEdits.push({
                    file: file,
                    path: ch.path,
                    old: ch.old,
                    new: ch.new,
                });
            }
            // 持久化
            await saveQuickEdits();
            // 更新原始内容为当前内容，清除脏标记（确认未切换文件，避免误清新文件状态）
            if (state.currentFile === file) {
                state.currentFileContent = currentContent;
                state.isDirty = false;
            }
            renderEditList();
            updateStatus('已记录 ' + changes.length + ' 条修改');
        } catch (e) {
            console.error('记录修改失败:', e);
            alert('记录修改失败: ' + e);
        }
    }

    async function saveQuickEdits() {
        var api = getApi();
        if (!api) return;
        try {
            var result = await api.save_quick_edits(state.pendingEdits);
            if (!result || !result.success) {
                throw new Error((result && result.error) || '后端拒绝保存');
            }
            var warnings = result.report && result.report.warnings ? result.report.warnings : [];
            if (warnings.length) {
                alert('部分修改无法转换为文本替换规则:\n' + warnings.slice(0, 10).join('\n'));
            }
            return result;
        } catch (e) {
            console.error('保存快速编辑失败:', e);
            alert('保存快速编辑失败: ' + e);
            return null;
        }
    }

    async function loadQuickEdits() {
        var api = getApi();
        if (!api) return;
        try {
            var result = await api.load_quick_edits();
            state.pendingEdits = (result && result.edits) ? result.edits : [];
            renderEditList();
        } catch (e) {
            console.error('加载快速编辑失败:', e);
            state.pendingEdits = [];
        }
    }

    async function applyEditsToGame() {
        if (!state.pendingEdits.length) {
            alert('没有待应用的修改');
            return;
        }
        if (!confirmDialog('将应用 ' + state.pendingEdits.length + ' 条修改到游戏文件，是否继续？')) return;

        var api = getApi();
        if (!api) return;
        try {
            var result = await api.apply_quick_edits();
            if (result.success) {
                alert('修改应用完成!\n成功: ' + (result.applied || 0) + '\n失败: ' + (result.failed || 0));
            } else {
                var msg = '应用完成\n成功: ' + (result.applied || 0) + '\n失败: ' + (result.failed || 0);
                if (result.errors && result.errors.length) {
                    msg += '\n\n错误详情:\n' + result.errors.join('\n');
                }
                alert(msg);
            }
            updateStatus('应用完成: 成功 ' + (result.applied || 0) + ', 失败 ' + (result.failed || 0));
            await refreshFileList();
        } catch (e) {
            console.error('应用修改失败:', e);
            alert('应用修改失败: ' + e);
        }
    }

    async function clearAllEdits() {
        if (!state.pendingEdits.length) return;
        if (!confirmDialog('确定要清空所有修改记录吗？此操作不可撤销。')) return;
        state.pendingEdits = [];
        renderEditList();
        await saveQuickEdits();
        updateStatus('已清空所有修改记录');
    }

    function deleteEdit(index) {
        if (index < 0 || index >= state.pendingEdits.length) return;
        state.pendingEdits.splice(index, 1);
        renderEditList();
        saveQuickEdits();
        updateStatus('已删除修改记录 #' + (index + 1));
    }

    function renderEditList() {
        var container = $i('qe-change-list');
        var countEl = $i('qe-change-count');
        countEl.textContent = state.pendingEdits.length || '0';

        if (!state.pendingEdits.length) {
            container.innerHTML = '<div style="padding:16px;text-align:center;color:var(--color-text-secondary);font-size:12px;">暂无变更记录</div>';
            return;
        }
        var html = '';
        for (var i = 0; i < state.pendingEdits.length; i++) {
            var edit = state.pendingEdits[i];
            html += '<div class="qe-change-item">';
            html += '<span class="qe-change-index">' + (i + 1) + '</span>';
            html += '<div class="qe-change-info">';
            html += '<div class="qe-change-file">' + escapeHtml(edit.file) + '</div>';
            html += '<div class="qe-change-path">' + escapeHtml(edit.path) + '</div>';
            html += '<div class="qe-change-values">';
            html += '<span class="qe-change-old" title="' + escapeHtml(edit.old) + '">' + escapeHtml(truncate(edit.old, 30)) + '</span>';
            html += '<span class="qe-change-arrow">→</span>';
            html += '<span class="qe-change-new" title="' + escapeHtml(edit.new) + '">' + escapeHtml(truncate(edit.new, 30)) + '</span>';
            html += '</div></div>';
            html += '<button class="qe-change-delete" data-index="' + i + '" title="删除此修改">✕</button>';
            html += '</div>';
        }
        container.innerHTML = html;
        // 绑定删除按钮
        var deleteBtns = container.querySelectorAll('.qe-change-delete');
        for (var d = 0; d < deleteBtns.length; d++) {
            deleteBtns[d].addEventListener('click', function () {
                var idx = parseInt(this.getAttribute('data-index'), 10);
                deleteEdit(idx);
            });
        }
    }

    // ──── 撤销 / 格式化 / 刷新 ────
    async function revertFile() {
        if (!state.currentFile) return;
        setEditorContent(state.currentFileContent);
        updateStatus('已撤销更改');
    }

    function formatJson() {
        try {
            var content = getEditorContent();
            var parsed = JSON.parse(content);
            var formatted = JSON.stringify(parsed, null, 2);
            setEditorContent(formatted);
            updateStatus('JSON 格式化完成');
        } catch (e) {
            alert('JSON 格式无效:\n' + e.message);
        }
    }

    // ──── 搜索 ────
    async function performSearch() {
        var keyword = $i('qe-file-search').value.trim();
        if (!keyword) return;
        var caseSensitive = $i('qe-case-sensitive').checked;
        var api = getApi();
        if (!api) return;
        try {
            var result = await api.search_files(keyword, caseSensitive);
            state.searchResults = result;
            state.searchActiveCategory = null;
            renderSearchCategoryList();
            switchTab('search-results');
            $i('qe-search-hint').style.display = 'block';
            $i('qe-search-hint').textContent = '共 ' + (result.total_matches || 0) + ' 处匹配';
            updateStatus('搜索完成: ' + (result.total_matches || 0) + ' 处匹配');
        } catch (e) {
            console.error('搜索失败:', e);
            alert('搜索失败: ' + e);
        }
    }

    function renderSearchCategoryList() {
        var container = $i('qe-search-results');
        var results = state.searchResults;
        if (!results || !results.results_by_category) {
            container.innerHTML = '<div style="padding:12px;text-align:center;color:var(--color-text-secondary);font-size:12px;">未找到匹配结果</div>';
            return;
        }
        var categories = Object.keys(results.results_by_category).sort();
        if (!categories.length) {
            container.innerHTML = '<div style="padding:12px;text-align:center;color:var(--color-text-secondary);font-size:12px;">未找到匹配结果</div>';
            return;
        }
        var html = '';
        for (var c = 0; c < categories.length; c++) {
            var cat = categories[c];
            var files = results.results_by_category[cat];
            var total = 0;
            for (var f = 0; f < files.length; f++) {
                total += files[f][1];
            }
            html += '<div class="qe-search-result-category">';
            html += '<div class="qe-search-result-header" data-category="' + escapeHtml(cat) + '">';
            html += '<span class="qe-category-icon">▶</span> ';
            html += '[' + total + ' 处匹配] ' + escapeHtml(cat) + ' (' + files.length + ' 个文件)';
            html += '</div></div>';
        }
        container.innerHTML = html;
        // 绑定点击
        var headers = container.querySelectorAll('.qe-search-result-header');
        for (var h = 0; h < headers.length; h++) {
            headers[h].addEventListener('click', function () {
                var cat = this.getAttribute('data-category');
                renderSearchCategoryDetail(cat);
            });
        }
    }

    function renderSearchCategoryDetail(category) {
        var container = $i('qe-search-results');
        var results = state.searchResults;
        state.searchActiveCategory = category;
        var files = results.results_by_category[category] || [];
        var html = '<div style="padding:6px 12px;font-size:11px;color:var(--color-primary);cursor:pointer;" id="qe-search-back">';
        html += '← 返回分类列表</div>';
        for (var f = 0; f < files.length; f++) {
            var filePath = files[f][0];
            var matches = files[f][1];
            html += '<div class="qe-search-result-file" data-file="' + escapeHtml(filePath) + '" style="cursor:pointer;">';
            html += '[' + matches + ' 处] ' + escapeHtml(filePath);
            html += '</div>';
        }
        container.innerHTML = html;
        // 返回按钮
        $i('qe-search-back').addEventListener('click', function () {
            state.searchActiveCategory = null;
            renderSearchCategoryList();
        });
        // 双击打开文件
        var fileItems = container.querySelectorAll('.qe-search-result-file');
        for (var i = 0; i < fileItems.length; i++) {
            fileItems[i].addEventListener('dblclick', function () {
                var relPath = this.getAttribute('data-file');
                openFile(relPath);
                switchTab('file-list');
            });
        }
    }

    function clearSearch() {
        $i('qe-file-search').value = '';
        $i('qe-search-hint').style.display = 'none';
        state.searchResults = null;
        state.searchActiveCategory = null;
        $i('qe-search-results').innerHTML = '';
        switchTab('file-list');
        updateStatus('就绪');
    }

    // ──── 批量替换 ────
    function openBatchReplaceDialog() {
        var overlay = document.createElement('div');
        overlay.className = 'qe-dialog-overlay';
        overlay.innerHTML = '<div class="qe-dialog">' +
            '<h3><i class="fas fa-exchange-alt"></i> 批量替换</h3>' +
            '<label>查找内容:</label>' +
            '<input type="text" id="qe-replace-find" placeholder="输入要查找的文本...">' +
            '<label>替换为:</label>' +
            '<input type="text" id="qe-replace-to" placeholder="输入替换后的文本...">' +
            '<label style="display:flex;align-items:center;gap:6px;cursor:pointer;">' +
            '<input type="checkbox" id="qe-replace-case"> 区分大小写</label>' +
            '<label>预览:</label>' +
            '<textarea id="qe-replace-preview" readonly placeholder="点击「预览」查看替换结果..."></textarea>' +
            '<div class="qe-dialog-buttons">' +
            '<button id="qe-replace-preview-btn">预览</button>' +
            '<button id="qe-replace-confirm-btn" class="qe-btn-primary">确认替换</button>' +
            '<button id="qe-replace-cancel-btn">取消</button>' +
            '</div></div>';
        document.body.appendChild(overlay);

        var findInput = overlay.querySelector('#qe-replace-find');
        var toInput = overlay.querySelector('#qe-replace-to');
        var caseCheck = overlay.querySelector('#qe-replace-case');
        var previewArea = overlay.querySelector('#qe-replace-preview');

        function close() {
            overlay.remove();
        }

        overlay.querySelector('#qe-replace-cancel-btn').addEventListener('click', close);
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) close();
        });

        overlay.querySelector('#qe-replace-preview-btn').addEventListener('click', function () {
            var findStr = findInput.value;
            var replaceStr = toInput.value;
            if (!findStr) return;
            var content = getEditorContent();
            var newContent, count;
            if (caseCheck.checked) {
                newContent = content.split(findStr).join(replaceStr);
                count = (content.length - newContent.length) / (findStr.length - replaceStr.length);
                if (findStr.length === replaceStr.length) {
                    count = content.split(findStr).length - 1;
                }
            } else {
                var re = new RegExp(findStr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
                var matches = content.match(re);
                count = matches ? matches.length : 0;
                newContent = content.replace(re, replaceStr);
            }
            previewArea.value = newContent;
            updateStatus('找到 ' + count + ' 处匹配');
        });

        overlay.querySelector('#qe-replace-confirm-btn').addEventListener('click', function () {
            var findStr = findInput.value;
            var replaceStr = toInput.value;
            if (!findStr) return;
            var content = getEditorContent();
            var newContent;
            if (caseCheck.checked) {
                newContent = content.split(findStr).join(replaceStr);
            } else {
                var re = new RegExp(findStr.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
                newContent = content.replace(re, replaceStr);
            }
            setEditorContent(newContent);
            updateStatus('批量替换完成');
            close();
        });

        findInput.focus();
    }

    // ──── 标签切换 ────
    function switchTab(tabName) {
        state.activeTab = tabName;
        var tabs = document.querySelectorAll('.qe-tab');
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].classList.toggle('active', tabs[i].getAttribute('data-tab') === tabName);
        }
        $i('qe-file-list').style.display = tabName === 'file-list' ? '' : 'none';
        $i('qe-search-results').style.display = tabName === 'search-results' ? '' : 'none';
    }

    // ──── 状态栏 ────
    function updateStatus(msg) {
        var el = $i('qe-status-edit');
        if (msg) {
            el.textContent = msg;
            el.className = 'qe-status-saved';
        } else if (state.isDirty) {
            el.textContent = '已修改';
            el.className = 'qe-status-modified';
        } else if (state.currentFile) {
            el.textContent = '未修改';
            el.className = '';
        } else {
            el.textContent = '就绪';
            el.className = '';
        }
    }

    function updateStatusBar() {
        updateStatus();
        updateCursorPosition();
    }

    function updateCursorPosition() {
        if (!state.fileEditor) return;
        var pos = state.fileEditor.state.selection.main.head;
        var doc = state.fileEditor.state.doc;
        var line = doc.lineAt(pos);
        $i('qe-status-cursor').textContent = '行 ' + line.number + ', 列 ' + (pos - line.from + 1);
    }

    // ──── 主题 ────
    async function syncThemeFromMain() {
        var api = getApi();
        if (!api) return;
        try {
            var theme = await api.get_config_value('theme', 'light');
            applyTheme(theme);
        } catch (e) {
            applyTheme('light');
        }
    }

    window.applyTheme = function (theme) {
        document.body.className = 'theme-' + (theme || 'light');
        document.body.setAttribute('data-injected-theme', theme || 'light');
    };

    // ──── 拖拽调整大小 ────
    function initResizeHandles() {
        // 侧边栏宽度拖拽
        var sidebar = $i('qe-sidebar');
        var resizeSidebar = $i('qe-resize-sidebar');
        var sidebarDragging = false;
        var sidebarStartX = 0;
        var sidebarStartW = 0;

        resizeSidebar.addEventListener('mousedown', function (e) {
            sidebarDragging = true;
            sidebarStartX = e.clientX;
            sidebarStartW = sidebar.offsetWidth;
            resizeSidebar.classList.add('active');
            document.body.style.userSelect = 'none';
            document.body.style.cursor = 'col-resize';
        });

        document.addEventListener('mousemove', function (e) {
            if (!sidebarDragging) return;
            var delta = e.clientX - sidebarStartX;
            var newW = Math.max(200, Math.min(450, sidebarStartW + delta));
            sidebar.style.width = newW + 'px';
        });

        document.addEventListener('mouseup', function () {
            if (sidebarDragging) {
                sidebarDragging = false;
                resizeSidebar.classList.remove('active');
                document.body.style.userSelect = '';
                document.body.style.cursor = '';
            }
        });

        // 底部变更面板高度拖拽
        var changesPanel = $i('qe-changes-panel');
        var resizeBottom = $i('qe-resize-bottom');
        var bottomDragging = false;
        var bottomStartY = 0;
        var bottomStartH = 0;

        resizeBottom.addEventListener('mousedown', function (e) {
            bottomDragging = true;
            bottomStartY = e.clientY;
            bottomStartH = changesPanel.offsetHeight;
            resizeBottom.classList.add('active');
            document.body.style.userSelect = 'none';
            document.body.style.cursor = 'row-resize';
        });

        document.addEventListener('mousemove', function (e) {
            if (!bottomDragging) return;
            var delta = bottomStartY - e.clientY;
            var newH = Math.max(60, Math.min(400, bottomStartH + delta));
            changesPanel.style.maxHeight = newH + 'px';
            changesPanel.style.height = newH + 'px';
        });

        document.addEventListener('mouseup', function () {
            if (bottomDragging) {
                bottomDragging = false;
                resizeBottom.classList.remove('active');
                document.body.style.userSelect = '';
                document.body.style.cursor = '';
            }
        });
    }

    // ──── 事件绑定 ────
    function restoreSearchPanelPosition() {
        if (!qeSearchBridge.panelLeft || !state.fileEditor || !window.EditorSearchPanel) return;
        setTimeout(function () {
            if (!qeSearchBridge.isOpen || !state.fileEditor) return; // 用户可能已关闭面板
            var panels = state.fileEditor.dom.querySelector('.cm-panels');
            if (!panels) return;
            EditorSearchPanel.setSearchPanelPosition(
                panels,
                parseFloat(qeSearchBridge.panelLeft) || 8,
                parseFloat(qeSearchBridge.panelTop) || 8
            );
        }, 80);
    }

    function bindEvents() {
        $i('qe-search-btn').addEventListener('click', performSearch);
        $i('qe-search-clear-btn').addEventListener('click', clearSearch);
        $i('qe-file-search').addEventListener('keydown', function (e) {
            if (e.key === 'Enter') performSearch();
        });
        $i('qe-record-btn').addEventListener('click', recordChanges);
        $i('qe-apply-btn').addEventListener('click', applyEditsToGame);
        $i('qe-revert-btn').addEventListener('click', revertFile);
        $i('qe-refresh-btn').addEventListener('click', refreshFileList);
        $i('qe-format-btn').addEventListener('click', formatJson);
        $i('qe-replace-btn').addEventListener('click', openBatchReplaceDialog);
        $i('qe-changes-apply-btn').addEventListener('click', applyEditsToGame);
        $i('qe-changes-clear-btn').addEventListener('click', clearAllEdits);

        // 标签切换
        var tabs = document.querySelectorAll('.qe-tab');
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].addEventListener('click', function () {
                switchTab(this.getAttribute('data-tab'));
            });
        }

        // Ctrl+S 记录修改；Ctrl+F 打开编辑器内搜索面板（与规则编辑器共用一套）
        document.addEventListener('keydown', function (e) {
            var ctrl = e.ctrlKey || e.metaKey;
            if (ctrl && e.key === 's') {
                e.preventDefault();
                recordChanges();
                return;
            }
            if (ctrl && e.shiftKey && (e.key === 'F' || e.key === 'f')) {
                e.preventDefault();
                var sidebarSearch = $i('qe-file-search');
                if (sidebarSearch) { sidebarSearch.focus(); sidebarSearch.select(); }
                return;
            }
            if (ctrl && (e.key === 'f' || e.key === 'F')) {
                if (state.fileEditor) {
                    e.preventDefault();
                    var CM = window.CodeMirror;
                    if (CM && CM.openSearchPanel) {
                        CM.openSearchPanel(state.fileEditor);
                        qeSearchBridge.isOpen = true;
                        restoreSearchPanelPosition();
                    }
                }
            }
        });

        // 窗口关闭前确保数据已保存
        window.addEventListener('beforeunload', function () {
            if (state.pendingEdits.length) {
                saveQuickEdits();
            }
        });
    }

    // ──── 启动 ────
    document.addEventListener('DOMContentLoaded', init);
})();
