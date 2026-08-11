(function () {
    'use strict';

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

    const state = {
        langFiles: [],
        currentFile: null,
        currentFileRaw: null,
        currentFileParsed: null,
        currentFileCategory: null,
        currentFilePrefix: null,
        currentRuleset: null,
        rulesetList: [],
        mode: 'simple',
        activeTab: 'file-list',
        activeMainTab: 'file-edit',
        searchResults: null,
        searchTotal: 0,
        searchRequestId: 0,
        fileCache: new Map(),
        fileFilter: '',               // 侧边栏搜索关键字（渲染文件列表时保持过滤）
        advancedContentView: null,
        selectedFieldPath: null,
        selectedItemId: null,
        autocomplete: null,
        advancedEditor: null,
        smartChanges: [],
        smartGenOverlay: null,
        smartGenGroups: null,
        smartGenV2Bias: 'conservative',
        templates: [],
        lastPreviewRule: null,
        // File editing mode state
        fileEditor: null,
        fileOriginalContent: null,
        fileOriginalParsed: null,
        pendingChanges: [],
        // Dirty state
        isDirty: false,
        // 多文件标签页系统
        openFiles: new Map(),       // Map<string, FileTabState>
        activeFileTab: null,        // string | null: 当前活动文件路径
        fileTabOrder: [],           // string[]: 有序的打开文件路径
        _lastViewedFile: null,      // 用于标签页切换时判断文件是否变化
        _editingRuleIndex: null, // 正在编辑的规则索引（非 null 时 generateRule 执行更新而非新增）
        _rulesetDirty: false,    // 规则集是否有未保存的修改
        _v3SkipAutoMerge: false, // 拆分后跳过 V3 自动合并（直到下一次重新分析）
    };

    // 跨标签搜索状态桥接
    var _searchBridge = {
        query: '',
        replaceQuery: '',
        caseSensitive: false,
        wholeWord: false,
        regexp: false,
        isOpen: false,
        panelLeft: null,   // 拖拽后的 left 值（相对 #re-file-edit-panel）
        panelTop: null,    // 拖拽后的 top 值（相对 #re-file-edit-panel）
        panelRight: null,  // 拖拽后的 right 值
        // 面板关闭时清理（供 EditorSearchPanel 回调）
        onPanelClose: function () {
            if (_searchBridge._restoreTimeout) {
                clearTimeout(_searchBridge._restoreTimeout);
                _searchBridge._restoreTimeout = null;
            }
        }
    };

    var CATEGORY_FILE_PATTERNS = {
        'Skill': 'Skill.*\\.json$', 'Bufs': 'Bufs.*\\.json$',
        'BattleSpeechBubbleDlg': 'BattleSpeechBubbleDlg.*\\.json$',
        'Egos': '(Skills_Ego|Egos).*\\.json$',
        'Passives': 'Passives.*\\.json$', 'Personalities': 'Personalities.*\\.json$',
        'Enemies': 'Enemies.*\\.json$', 'EGOgift': 'EGOgift.*\\.json$',
        'Railway': 'Railway.*\\.json$', 'MirrorDungeon': 'MirrorDungeon.*\\.json$',
        'Dungeon': 'Dungeon.*\\.json$', 'Stage': 'Stage.*\\.json$',
        'Story': 'Story.*\\.json$', 'Event': 'Event.*\\.json$',
        'BattleUIText': 'BattleUIText.*\\.json$', 'BattleKeywords': 'BattleKeywords.*\\.json$',
        'AbEvents': 'AbEvents.*\\.json$', 'Announcer': 'Announcer.*\\.json$',
        'UnitKeyword': 'UnitKeyword.*\\.json$'
    };

    function $i(id) { return document.getElementById(id); }

    function getApi() {
        return (typeof window !== 'undefined' && window.pywebview && window.pywebview.api) ? window.pywebview.api : null;
    }

    function warnNoApi() {
        console.warn('[rule-editor] pywebview.api 不可用（开发模式或后端未就绪）');
        return false;
    }

    function classifyPath(relativePath) {
        // Skills_Ego_*（人格EGO技能）与 'Skill' 前缀冲突，强制归入 Egos 分类
        if (relativePath.indexOf('Skills_Ego') !== -1) {
            for (let i = 0; i < FILE_PREFIX_RULES.length; i++) {
                if (FILE_PREFIX_RULES[i][0] === 'Egos') {
                    return { prefix: 'Egos', category: FILE_PREFIX_RULES[i][1] };
                }
            }
        }
        for (let i = 0; i < FILE_PREFIX_RULES.length; i++) {
            const prefix = FILE_PREFIX_RULES[i][0];
            const category = FILE_PREFIX_RULES[i][1];
            if (relativePath.startsWith(prefix) || relativePath.indexOf(prefix) !== -1) {
                return { prefix: prefix, category: category };
            }
        }
        return { prefix: null, category: 'Other' };
    }

    function groupFilesByCategory(files) {
        const groups = {};
        for (let i = 0; i < files.length; i++) {
            const f = files[i];
            const info = classifyPath(f);
            if (!groups[info.category]) groups[info.category] = [];
            groups[info.category].push(f);
        }
        return groups;
    }

    function escapeHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function escapeAttr(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;')
            .replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    // ═══════════════════════════════════════════════════════
    //  Multi-File Tab System — Core
    // ═══════════════════════════════════════════════════════

    function getTabState(path) {
        return state.openFiles.get(path) || null;
    }

    function getActiveTabState() {
        if (!state.activeFileTab) return null;
        return state.openFiles.get(state.activeFileTab) || null;
    }

    function syncLegacyState() {
        var ts = getActiveTabState();
        if (ts) {
            state.currentFile = ts.path;
            state.currentFileRaw = ts.editor.state.doc.toString();
            state.currentFileParsed = ts.baselineParsed;
            state.currentFileCategory = ts.category;
            state.currentFilePrefix = ts.prefix;
            state.fileEditor = ts.editor;
            state.fileOriginalContent = ts.baselineContent;
            state.fileOriginalParsed = ts.baselineParsed;
            state.isDirty = (ts.editStatus === 'staged');
            state.pendingChanges = ts.pendingChanges;
        } else {
            state.currentFile = null;
            state.currentFileRaw = null;
            state.currentFileParsed = null;
            state.currentFileCategory = null;
            state.currentFilePrefix = null;
            state.fileEditor = null;
            state.fileOriginalContent = null;
            state.fileOriginalParsed = null;
            state.isDirty = false;
            state.pendingChanges = [];
        }
    }

    function createEditorForTab(container) {
        if (!window.CodeMirror || !window.CodeMirror.EditorView) {
            console.warn('[rule-editor] CodeMirror not loaded');
            return null;
        }
        var CM = window.CodeMirror;
        var statusListener = CM.EditorView.updateListener.of(function (update) {
            if (update.selectionSet) {
                var pos = update.state.selection.main.head;
                var line = update.state.doc.lineAt(pos);
                var statusEl = document.getElementById('re-status-cursor');
                if (statusEl) {
                    statusEl.textContent = '行 ' + line.number + ', 列 ' + (pos - line.from + 1);
                }
            }
            if (update.docChanged) {
                var ts = getActiveTabState();
                if (ts) updateFileEditStatus(ts);
            }
        });
        try {
            return new CM.EditorView({
                doc: '',
                extensions: [CM.basicSetup, CM.json(), statusListener],
                parent: container
            });
        } catch (e) {
            console.error('[rule-editor] createEditorForTab failed:', e);
            return null;
        }
    }

    function updateFileEditStatus(tabState) {
        if (!tabState || !tabState.editor) return;
        var editorContent = tabState.editor.state.doc.toString();
        var isDifferentFromDisk = (editorContent !== tabState.diskContent);
        var isDifferentFromBaseline = (tabState.diskContent !== tabState.baselineContent);

        if (isDifferentFromDisk) {
            tabState.editStatus = 'staged';
        } else if (isDifferentFromBaseline) {
            tabState.editStatus = 'applied';
        } else {
            tabState.editStatus = 'clean';
        }

        renderFileTabBar();
        renderFileList();
        updateFileEditTabLabel();
        updateStatusBar();
        // 刷新文件状态面板（如果当前处于活跃状态）
        if (state.activeTab === 'file-status') renderFileStatusPanel();
    }

    async function createFileTab(path) {
        if (state.openFiles.has(path)) {
            activateFileTab(path);
            return;
        }

        var api = getApi();
        if (!api) { warnNoApi(); return; }

        var res;
        if (state.fileCache.has(path)) {
            res = state.fileCache.get(path);
        } else {
            try {
                res = await api.get_file_content(path);
                if (res && res.error) {
                    showToast('无法打开文件: ' + res.error, 'error');
                    return;
                }
                state.fileCache.set(path, {
                    raw: res.raw,
                    parsed: res.parsed,
                    category: (res.file_classification) || classifyPath(path).category
                });
            } catch (e) {
                console.error('[rule-editor] openFile failed:', e);
                return;
            }
        }

        if (state.openFiles.has(path)) {
            activateFileTab(path);
            return;
        }

        var raw = res.raw || '';
        var parsed = res.parsed || null;
        var category = res.category || classifyPath(path).category;
        var prefix = classifyPath(path).prefix;

        var tabsContainer = document.getElementById('re-file-editor-tabs-container');
        if (!tabsContainer) return;

        var wrapper = document.createElement('div');
        wrapper.className = 're-file-editor-wrapper';
        wrapper.dataset.path = path;

        var editor = createEditorForTab(wrapper);
        if (!editor) return;

        var docLen = editor.state.doc.length;
        editor.dispatch({ changes: { from: 0, to: docLen, insert: raw } });

        var tabState = {
            path: path,
            editor: editor,
            container: wrapper,
            baselineContent: raw,
            diskContent: raw,
            baselineParsed: parsed ? JSON.parse(JSON.stringify(parsed)) : null,
            category: category,
            prefix: prefix,
            editStatus: 'clean',
            pendingChanges: [],
            lastSavedAt: null
        };

        state.openFiles.set(path, tabState);
        state.fileTabOrder.push(path);
        tabsContainer.appendChild(wrapper);

        activateFileTab(path);
    }

    function activateFileTab(path) {
        if (!path || !state.openFiles.has(path)) return;

        // 捕获当前活动编辑器的搜索状态
        var oldTs = getActiveTabState();
        if (oldTs && oldTs.editor) {
            _captureSearchState(oldTs.editor);
        }

        var allWrappers = document.querySelectorAll('.re-file-editor-wrapper');
        for (var i = 0; i < allWrappers.length; i++) {
            allWrappers[i].classList.remove('active');
        }

        var ts = state.openFiles.get(path);
        if (ts && ts.container) {
            ts.container.classList.add('active');
        }
        state.activeFileTab = path;
        state._lastViewedFile = path;

        syncLegacyState();

        renderFileTabBar();
        updateFileEditTabLabel();
        updateStatusBar();

        var empty = document.getElementById('re-fe-empty');
        if (empty) empty.style.display = 'none';

        // 恢复搜索状态到新编辑器
if (ts && ts.editor && _searchBridge.isOpen) {
            setTimeout(function () {
                _restoreSearchState(ts.editor, ts.container);
            }, 50);
        }
    }

    async function closeFileTab(path, force) {
        if (!path || !state.openFiles.has(path)) return;

        var ts = state.openFiles.get(path);

        if (!force && ts.editStatus === 'staged') {
            var confirmed = await showConfirmDialog({
                title: '未保存的更改',
                message: '文件 ' + path + ' 有未保存的更改，是否保存？',
                saveLabel: '保存',
                discardLabel: '不保存',
                cancelLabel: '取消'
            });
            if (confirmed === 'cancel') return;
            if (confirmed === 'save') {
                await saveEditedFileForTab(path);
            }
        }

        if (ts.editor) {
            ts.editor.destroy();
        }

        if (ts.container && ts.container.parentNode) {
            ts.container.parentNode.removeChild(ts.container);
        }

        var wasActive = (path === state.activeFileTab);
        state.openFiles.delete(path);
        var idx = state.fileTabOrder.indexOf(path);
        if (idx !== -1) state.fileTabOrder.splice(idx, 1);

        if (wasActive) {
            if (state.fileTabOrder.length > 0) {
                var nextPath = state.fileTabOrder[Math.min(idx, state.fileTabOrder.length - 1)];
                activateFileTab(nextPath);
            } else {
                state.activeFileTab = null;
                state._lastViewedFile = null;
                syncLegacyState();
                var empty = document.getElementById('re-fe-empty');
                if (empty) empty.style.display = '';
                updateFileEditTabLabel();
                updateStatusBar();
            }
        }

        renderFileTabBar();
        renderFileList();
    }

    function renderFileTabBar() {
        var bar = document.getElementById('re-file-tab-bar');
        if (!bar) return;

        var html = '';
        for (var i = 0; i < state.fileTabOrder.length; i++) {
            var path = state.fileTabOrder[i];
            var ts = state.openFiles.get(path);
            if (!ts) continue;

            var isActive = (path === state.activeFileTab);
            var displayName = path.length > 30 ? '...' + path.slice(-27) : path;
            var statusClass = ts.editStatus === 'staged' ? 'staged'
                : ts.editStatus === 'applied' ? 'applied' : '';

            html += '<div class="re-file-tab' + (isActive ? ' active' : '') +
                '" data-path="' + escapeAttr(path) + '" title="' + escapeAttr(path) + '">' +
                '<span class="re-tab-status ' + statusClass + '"></span>' +
                '<span class="re-tab-label">' + escapeHtml(displayName) + '</span>' +
                '<button class="re-tab-close" data-close="' + escapeAttr(path) + '">&times;</button>' +
                '</div>';
        }
        bar.innerHTML = html;

        var tabs = bar.querySelectorAll('.re-file-tab');
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].addEventListener('click', function (e) {
                if (e.target.closest('.re-tab-close')) return;
                activateFileTab(this.dataset.path);
            });
            tabs[i].addEventListener('mousedown', function (e) {
                if (e.button === 1) {
                    e.preventDefault();
                    closeFileTab(this.dataset.path);
                }
            });
        }

        var closeBtns = bar.querySelectorAll('.re-tab-close');
        for (var i = 0; i < closeBtns.length; i++) {
            closeBtns[i].addEventListener('click', function (e) {
                e.stopPropagation();
                closeFileTab(this.dataset.close);
            });
        }
    }

    function updateFileEditTabLabel() {
        var tab = document.querySelector('.re-main-tab[data-maintab="file-edit"]');
        if (!tab) return;
        // 始终保持 "文件编辑" 标签不变，仅切换 dirty 状态图标
        var ts = getActiveTabState();
        var icon = (ts && ts.editStatus === 'staged') ? 'fas fa-circle re-dirty-dot' : 'fas fa-pen';
        tab.innerHTML = '<i class="' + icon + '"></i> 文件编辑';
    }

    function updateStatusBar() {
        var statusEl = document.getElementById('re-status-edit-status');
        var timeEl = document.getElementById('re-status-save-time');
        var ts = getActiveTabState();

        if (statusEl) {
            if (!ts) {
                statusEl.textContent = '';
            } else if (ts.editStatus === 'clean') {
                statusEl.textContent = '未修改';
                statusEl.className = '';
            } else if (ts.editStatus === 'staged') {
                statusEl.textContent = '● 修改暂存';
                statusEl.className = 're-status-staged';
            } else if (ts.editStatus === 'applied') {
                statusEl.textContent = '✓ 修改应用';
                statusEl.className = 're-status-applied';
            }
        }

        if (timeEl) {
            if (ts && ts.lastSavedAt) {
                var d = new Date(ts.lastSavedAt);
                timeEl.textContent = '上次保存: ' +
                    String(d.getHours()).padStart(2, '0') + ':' +
                    String(d.getMinutes()).padStart(2, '0') + ':' +
                    String(d.getSeconds()).padStart(2, '0');
                timeEl.style.display = '';
            } else {
                timeEl.style.display = 'none';
            }
        }
    }

    /** init — bind events, prime UI, then load data once pywebview is ready. */
    function init() {
        bindEvents();
        populateSimpleFileSelect();
        switchTab('file-list');
        switchMainTab('file-edit');
        if (window.EditorSearchPanel) {
            EditorSearchPanel.attach($i('re-file-editor-container'), _searchBridge);
        } else {
            console.warn('[rule-editor] EditorSearchPanel 未加载，编辑器内搜索面板不可用');
        }
        initResizeHandles();
        // 检查 pywebview API 是否已可用（防竞态）
        if (getApi()) {
            onApiReady();
        } else {
            let readyFlag = false;
            function handleReady() {
                if (readyFlag) return;
                readyFlag = true;
                onApiReady();
            }
            window.addEventListener('pywebviewready', handleReady);
            // 兜底：若事件在注册前已触发
            if (window.pywebview && window.pywebview.api) {
                handleReady();
            }
        }
    }

    async function onApiReady() {
        setMode('simple', true);
        initAdvancedMode();
        initFileEditor();
        await Promise.all([loadEditorConstants(), loadLangFiles(), loadRulesets(), initSimpleFileSelect(), loadTemplates(), syncThemeFromMain()]);
        syncAdvancedFromRuleset();
    }

    async function loadEditorConstants() {
        var api = getApi();
        if (!api || !api.get_editor_constants) return;
        try {
            var data = await api.get_editor_constants();
            if (data && Array.isArray(data.file_prefix_rules) && data.file_prefix_rules.length) {
                FILE_PREFIX_RULES = data.file_prefix_rules;
                CATEGORY_ORDER = FILE_PREFIX_RULES.map(function (r) { return r[1]; }).concat(['Other']);
            }
            if (data && data.category_file_patterns) {
                CATEGORY_FILE_PATTERNS = data.category_file_patterns;
            }
        } catch (e) {
            console.warn('[rule-editor] loadEditorConstants failed, using built-in defaults', e);
        }
    }

    async function syncThemeFromMain() {
        const api = getApi();
        if (!api || !api.get_config_value) return;
        try {
            const theme = await api.get_config_value('theme', 'light');
            applyTheme(theme);
        } catch (e) {
            console.warn('[rule-editor] 主题同步失败:', e);
        }
    }

    function applyTheme(theme) {
        const valid = ['light', 'dark', 'purple'];
        const t = valid.includes(theme) ? theme : 'light';
        document.body.className = 'theme-' + t;
        updateEditorTheme(t);
    }

    window.applyTheme = applyTheme;

    function updateEditorTheme(theme) {
        // CodeMirror 编辑器通过 CSS 变量适配主题，无需额外操作
        // 如需刷新编辑器可 dispatch 空事务
        const editor = state.fileEditor;
        if (editor) {
            editor.dispatch({});
        }
    }

    async function loadLangFiles() {
        const api = getApi();
        if (!api) return warnNoApi();
        try {
            const files = await api.get_lang_files();
            state.langFiles = Array.isArray(files) ? files : [];
        } catch (e) {
            console.error('[rule-editor] loadLangFiles failed:', e);
            state.langFiles = [];
        }
        renderFileList();
    }

    async function loadRulesets() {
        const api = getApi();
        if (!api) return warnNoApi();
        try {
            const list = await api.get_ruleset_list();
            state.rulesetList = Array.isArray(list) ? list : [];
        } catch (e) {
            console.error('[rule-editor] loadRulesets failed:', e);
            state.rulesetList = [];
        }
        renderRulesetSelect();
    }

    async function loadRulesetByName(name) {
        const api = getApi();
        if (!api || !name) return;
        try {
            const rs = await api.get_ruleset(name);
            if (rs && rs.error) {
                console.warn('[rule-editor] load ruleset error:', rs.error);
                state.currentRuleset = null;
            } else {
                state.currentRuleset = rs;
            }
        } catch (e) {
            console.error('[rule-editor] loadRulesetByName failed:', e);
            state.currentRuleset = null;
        }
        resetEditingRule();
        renderRulesPreview();
        syncAdvancedFromRuleset();
    }

    async function openFile(relativePath) {
        if (!relativePath) return;
        await createFileTab(relativePath);
    }

    function applyFileContent(relativePath, raw, parsed, category) {
        state.currentFile = relativePath;
        state.currentFileRaw = raw;
        state.currentFileParsed = parsed;
        state.currentFileCategory = category;
        state.currentFilePrefix = classifyPath(relativePath).prefix;
        const cur = $i('re-current-file');
        if (cur) cur.textContent = relativePath || '未选择文件';
        const fileSel = $i('re-simple-file');
        if (fileSel && state.currentFilePrefix) fileSel.value = state.currentFilePrefix;
        refreshContentPanel();
        if (state.activeMainTab === 'file-edit') {
            loadFileIntoEditor(relativePath);
        }
    }

    function loadFileIntoEditor(relativePath) {
        if (!relativePath) return;
        const raw = state.currentFileRaw;
        if (raw == null && state.fileCache.has(relativePath)) {
            const cached = state.fileCache.get(relativePath);
            loadRawIntoEditor(cached.raw, cached.parsed);
            return;
        }
        if (raw != null) {
            loadRawIntoEditor(raw, state.currentFileParsed);
        }
    }

    function loadRawIntoEditor(raw, parsed) {
        initFileEditor();
        const editor = state.fileEditor;
        if (!editor) return;
        if (raw != null) {
            const len = editor.state.doc.length;
            editor.dispatch({ changes: { from: 0, to: len, insert: raw } });
        }
        state.fileOriginalContent = raw;
        state.fileOriginalParsed = parsed ? JSON.parse(JSON.stringify(parsed)) : null;
        state.isDirty = false;
        clearPendingChanges();
        updateFileEditTabLabel();
    }

    function renderFileList(filtered) {
        const container = $i('re-file-list-container');
        if (!container) return;
        if (!filtered && state.fileFilter && state.fileFilter.trim()) {
            filterFilesByKeyword(state.fileFilter);
            return;
        }
        const files = filtered || state.langFiles;
        if (!files.length) {
            container.innerHTML = '<div class="re-empty-state">未找到匹配的文件</div>';
            return;
        }
        const groups = groupFilesByCategory(files);
        let html = '';
        for (let ci = 0; ci < CATEGORY_ORDER.length; ci++) {
            const category = CATEGORY_ORDER[ci];
            const files = groups[category];
            if (!files || !files.length) continue;
            html += '<div class="re-file-group"><div class="re-file-group-title">' + escapeHtml(category) +
                ' <span class="re-file-group-count">(' + files.length + ')</span></div>';
            for (let fi = 0; fi < files.length; fi++) {
                const f = files[fi];
                var ts = state.openFiles.get(f);
                var statusDot = '';
                var dirtyClass = '';
                if (ts) {
                    if (ts.editStatus === 'staged') {
                        statusDot = '<span class="re-file-dirty-dot staged" title="修改暂存（未保存）">●</span>';
                        dirtyClass = ' is-dirty-staged';
                    } else if (ts.editStatus === 'applied') {
                        statusDot = '<span class="re-file-dirty-dot applied" title="修改应用（已保存）">●</span>';
                        dirtyClass = ' is-dirty-applied';
                    }
                }
                html += '<div class="re-file-item' + dirtyClass +
                    '" data-path="' + escapeAttr(f) +
                    '" title="双击打开: ' + escapeAttr(f) + '">' +
                    statusDot + escapeHtml(f) + '</div>';
            }
            html += '</div>';
        }
        container.innerHTML = html;
        const items = container.querySelectorAll('.re-file-item');
        for (let i = 0; i < items.length; i++) {
            items[i].addEventListener('dblclick', (function (el) {
                return function () { openFile(el.dataset.path); };
            })(items[i]));
        }
        updateFileListTabBadge();
    }

    function updateFileListTabBadge() {
        var tab = document.querySelector('.re-tab[data-tab="file-list"]');
        if (!tab) return;
        var dirtyCount = 0;
        state.openFiles.forEach(function (ts) {
            if (ts.editStatus === 'staged' || ts.editStatus === 'applied') {
                dirtyCount++;
            }
        });
        tab.innerHTML = '文件列表' + (dirtyCount > 0 ? ' (' + dirtyCount + ')' : '');
    }

    function populateSimpleFileSelect() {
        const sel = $i('re-simple-file');
        if (!sel) return;
        let opts = ['<option value="">-- 选择文件分类 --</option>'];
        for (let i = 0; i < FILE_PREFIX_RULES.length; i++) {
            opts.push('<option value="' + escapeAttr(FILE_PREFIX_RULES[i][0]) + '">' +
                escapeHtml(FILE_PREFIX_RULES[i][1]) + '</option>');
        }
        sel.innerHTML = opts.join('');
    }

    function refreshContentPanel() {
        // 文件编辑模式下不渲染底部预览面板（已隐藏）
        if (state.activeMainTab === 'file-edit') return;
        if (state.mode === 'simple') renderSimpleContent();
        else renderAdvancedContent();
    }

    /** renderSimpleContent — parse cached JSON into structured data cards for the bottom panel. */
    function renderSimpleContent() {
        const container = $i('re-content-simple');
        if (!container) return;
        if (!state.currentFile) {
            container.innerHTML = '<div class="re-empty-state">双击左侧文件以查看内容</div>';
            return;
        }
        const parsed = state.currentFileParsed;
        if (parsed == null) {
            container.innerHTML = '<div class="re-empty-state">⚠️ 文件格式异常（无法解析为 JSON）</div>';
            return;
        }
        let entries = [];
        if (Array.isArray(parsed.dataList)) {
            entries = parsed.dataList.map(function (item, idx) { return { item: item, idx: idx }; });
        } else if (Array.isArray(parsed)) {
            entries = parsed.map(function (item, idx) { return { item: item, idx: idx }; });
        } else if (parsed && typeof parsed === 'object') {
            entries = [{ item: parsed, idx: 0 }];
        }
        if (!entries.length) {
            container.innerHTML = '<div class="re-empty-state">无 dataList 条目</div>';
            return;
        }
        let html = '<div class="re-data-cards">';
        for (let i = 0; i < entries.length; i++) {
            html += renderDataCard(entries[i].item, entries[i].idx);
        }
        html += '</div>';
        container.innerHTML = html;
    }

    function renderDataCard(item, idx) {
        if (item == null || typeof item !== 'object') {
            return '<div class="re-data-card"><div class="re-data-card-header">[' + idx + '] ' +
                escapeHtml(String(item)) + '</div></div>';
        }
        const id = (item.id != null) ? String(item.id) : '';
        const name = (item.name != null) ? String(item.name) : '';
        let html = '<div class="re-data-card" data-card-idx="' + idx + '">';
        html += '<div class="re-data-card-header"><span class="re-card-id">🎯 id:' + escapeHtml(id) +
            '</span> <span class="re-card-name">' + escapeHtml(name) + '</span></div>';
        html += '<div class="re-data-card-body">';
        const keys = Object.keys(item);
        for (let k = 0; k < keys.length; k++) {
            if (keys[k] === 'id' || keys[k] === 'name') continue;
            html += renderFieldLine(keys[k], item[keys[k]], id);
        }
        html += '</div>';
        html += '<div class="re-data-card-footer"><button class="re-btn re-btn-sm re-add-item-btn" data-item-id="' +
            escapeAttr(id) + '">＋ 将此条目加入规则</button></div>';
        html += '</div>';
        return html;
    }

    function renderFieldLine(key, value, itemId) {
        const isComplex = (typeof value === 'object' && value !== null);
        let valueHtml;
        let nestedHtml = '';
        if (isComplex) {
            const isArr = Array.isArray(value);
            const count = isArr ? value.length : Object.keys(value).length;
            valueHtml = '<span class="re-field-value-muted">' + (isArr ? '[' + count + ']' : '{…}') + '</span>';
            nestedHtml = '<div class="re-nested-toggle">▸ 展开查看</div><pre class="re-nested-list" style="display:none;">' +
                escapeHtml(JSON.stringify(value, null, 2)) + '</pre>';
        } else {
            valueHtml = '<span class="re-field-value">' + escapeHtml(value == null ? '' : String(value)) + '</span>';
        }
        const sel = '<button class="re-btn re-btn-sm re-select-field-btn" data-field="' + escapeAttr(key) +
            '" data-item-id="' + escapeAttr(itemId) + '">选中此字段</button>';
        return '<div class="re-field-line" data-field="' + escapeAttr(key) + '" data-item-id="' + escapeAttr(itemId) +
            '"><div class="re-field-row"><span class="re-field-name">' + escapeHtml(key) + ':</span> ' +
            valueHtml + ' ' + sel + '</div>' + nestedHtml + '</div>';
    }

    /** renderAdvancedContent — show raw JSON in a read-only CodeMirror 6 viewer. */
    function renderAdvancedContent() {
        const container = $i('re-content-advanced');
        if (!container) return;
        if (!state.currentFile) {
            if (state.advancedContentView) {
                state.advancedContentView.destroy();
                state.advancedContentView = null;
            }
            container.innerHTML = '<div class="re-empty-state">双击左侧文件以查看内容</div>';
            return;
        }
        const view = ensureAdvancedContentViewer();
        if (view) {
            const doc = state.currentFileRaw || '';
            view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: doc } });
        } else {
            container.textContent = state.currentFileRaw || '';
        }
    }

    function ensureAdvancedContentViewer() {
        if (state.advancedContentView) return state.advancedContentView;
        const container = $i('re-content-advanced');
        if (!container) return null;
        if (!window.CodeMirror) {
            console.warn('[rule-editor] CodeMirror not loaded; falling back to plain text');
            return null;
        }
        const CM = window.CodeMirror;
        const EditorView = CM.EditorView;
        if (!EditorView) return null;
        state.advancedContentView = new EditorView({
            doc: '',
            extensions: [CM.basicSetup, CM.json(), EditorView.editable.of(false)],
            parent: container
        });
        return state.advancedContentView;
    }

    function renderRulesetSelect() {
        const sel = $i('re-ruleset-select');
        if (!sel) return;
        let opts = ['<option value="">-- 选择规则集 --</option>'];
        for (let i = 0; i < state.rulesetList.length; i++) {
            const rs = state.rulesetList[i];
            const nm = rs.name || '';
            const count = (rs.rule_count != null) ? rs.rule_count : 0;
            opts.push('<option value="' + escapeAttr(nm) + '">' + escapeHtml(nm) + ' (' + count + ')</option>');
        }
        sel.innerHTML = opts.join('');
    }

    function refreshRulesetUI() {
        renderRulesPreview();
        syncAdvancedFromRuleset();
    }

    function renderRulesPreview() {
        const container = $i('re-rules-preview-list');
        if (!container) return;
        if (!state.currentRuleset || !Array.isArray(state.currentRuleset.rules) || !state.currentRuleset.rules.length) {
            container.innerHTML = '<div class="re-empty-state">暂无规则</div>';
            return;
        }
        const rules = state.currentRuleset.rules;
        let html = '';
        for (let i = 0; i < rules.length; i++) {
            const rule = rules[i];
            const files = Array.isArray(rule.files) ? rule.files.join(', ') : 'no files';
            const scope = rule.scope || '(root)';
            const targetField = Array.isArray(rule.targets) ? rule.targets.join(', ') : '?';
            let actionStr = '';
            if (Array.isArray(rule.actions) && rule.actions.length) {
                actionStr = rule.actions.map(function (a) {
                    if (a && a.type === 'replace') return escapeHtml(String(a.from)) + '→' + escapeHtml(String(a.to));
                    return escapeHtml(a.type || JSON.stringify(a));
                }).join(', ');
            }
            html += '<div class="re-rule-summary">' +
                '<span class="re-rule-index">#' + (i + 1) + '</span>' +
                '<span class="re-rule-summary-text">' + escapeHtml(files) + ' [' + escapeHtml(scope) + '] → ' + escapeHtml(targetField) +
                (actionStr ? ' {' + actionStr + '}' : '') + '</span>' +
                '<div class="re-rule-actions">' +
                '<button class="re-edit-rule-btn" data-idx="' + i + '" title="编辑规则">✏</button>' +
                '<button class="re-btn re-btn-sm re-btn-danger re-remove-rule-btn" data-idx="' + i + '" title="移除规则">✕</button>' +
                '</div>' +
                '</div>';
        }
        container.innerHTML = html;
    }

    function filterFilesByKeyword(keyword) {
        if (!keyword.trim()) {
            renderFileList(state.langFiles);
            return;
        }
        var kw = keyword.toLowerCase();
        
        // 1. 匹配分类名：找出 keyword 命中的分类
        var matchedCategories = {};
        for (var i = 0; i < FILE_PREFIX_RULES.length; i++) {
            var catName = FILE_PREFIX_RULES[i][1];
            if (catName.toLowerCase().indexOf(kw) !== -1) {
                matchedCategories[catName] = true;
            }
        }
        var hasCategoryMatch = Object.keys(matchedCategories).length > 0;
        
        // 2. 按文件名筛选
        var filenameMatches = [];
        var categoryFileSets = {};  // category -> files[]
        for (var i = 0; i < state.langFiles.length; i++) {
            var f = state.langFiles[i];
            var info = classifyPath(f);
            // 收集分类命中的文件
            if (matchedCategories[info.category]) {
                if (!categoryFileSets[info.category]) categoryFileSets[info.category] = [];
                categoryFileSets[info.category].push(f);
            }
            // 文件名匹配
            if (f.toLowerCase().indexOf(kw) !== -1) {
                filenameMatches.push(f);
            }
        }
        
        // 3. 合并结果：分类命中置顶
        var resultFiles = [];
        var seen = {};
        
        // 先添加分类命中的文件（按 CATEGORY_ORDER 顺序）
        if (hasCategoryMatch) {
            for (var ci = 0; ci < CATEGORY_ORDER.length; ci++) {
                var cat = CATEGORY_ORDER[ci];
                var catFiles = categoryFileSets[cat];
                if (catFiles) {
                    for (var fi = 0; fi < catFiles.length; fi++) {
                        if (!seen[catFiles[fi]]) {
                            seen[catFiles[fi]] = true;
                            resultFiles.push(catFiles[fi]);
                        }
                    }
                }
            }
        }
        
        // 再添加仅文件名匹配的文件（去重）
        for (var i = 0; i < filenameMatches.length; i++) {
            if (!seen[filenameMatches[i]]) {
                seen[filenameMatches[i]] = true;
                resultFiles.push(filenameMatches[i]);
            }
        }
        
        // 4. 渲染
        if (hasCategoryMatch) {
            // 使用带高亮的渲染（分类名匹配的组高亮显示）
            renderFileListWithHighlight(resultFiles, matchedCategories);
        } else {
            renderFileList(resultFiles);
        }
        
        // 5. 更新搜索提示
        var hint = $i('re-search-hint');
        if (hint) {
            if (resultFiles.length) {
                hint.className = 're-search-hint re-search-hint-file';
                var msg = '🔍 ';
                if (hasCategoryMatch) {
                    msg += '分类匹配: ' + Object.keys(matchedCategories).join(', ') + ' — ';
                }
                msg += resultFiles.length + ' 个文件';
                hint.textContent = msg;
                hint.style.display = '';
            } else {
                hint.className = 're-search-hint';
                hint.textContent = '未找到文件名匹配；按 Enter 或点击「搜索」查找内容';
                hint.style.display = '';
            }
        }
        
        return resultFiles;
    }

    // 新增：带高亮分类的渲染函数
    function renderFileListWithHighlight(files, highlightedCategories) {
        var container = $i('re-file-list-container');
        if (!container) return;
        if (!files.length) {
            container.innerHTML = '<div class="re-empty-state">未找到匹配的文件</div>';
            return;
        }
        var groups = groupFilesByCategory(files);
        var html = '';
        for (var ci = 0; ci < CATEGORY_ORDER.length; ci++) {
            var category = CATEGORY_ORDER[ci];
            var groupFiles = groups[category];
            if (!groupFiles || !groupFiles.length) continue;
            var isHighlighted = !!highlightedCategories[category];
            html += '<div class="re-file-group' + (isHighlighted ? ' re-file-group-highlighted' : '') + '">';
            html += '<div class="re-file-group-title">' + escapeHtml(category) +
                ' <span class="re-file-group-count">(' + groupFiles.length + ')</span></div>';
            for (var fi = 0; fi < groupFiles.length; fi++) {
                var f = groupFiles[fi];
                var ts = state.openFiles.get(f);
                var statusDot = '';
                var dirtyClass = '';
                if (ts) {
                    if (ts.editStatus === 'staged') {
                        statusDot = '<span class="re-file-dirty-dot staged" title="修改暂存（未保存）">●</span>';
                        dirtyClass = ' is-dirty-staged';
                    } else if (ts.editStatus === 'applied') {
                        statusDot = '<span class="re-file-dirty-dot applied" title="修改应用（已保存）">●</span>';
                        dirtyClass = ' is-dirty-applied';
                    }
                }
                html += '<div class="re-file-item' + dirtyClass + (isHighlighted ? ' re-file-item-highlighted' : '') +
                    '" data-path="' + escapeAttr(f) + '" title="双击打开: ' + escapeAttr(f) + '">' +
                    statusDot + escapeHtml(f) + '</div>';
            }
            html += '</div>';
        }
        container.innerHTML = html;
        var items = container.querySelectorAll('.re-file-item');
        for (var i = 0; i < items.length; i++) {
            items[i].addEventListener('dblclick', (function (el) {
                return function () { openFile(el.dataset.path); };
            })(items[i]));
        }
    }

    async function performSearch() {
        let api = getApi();
        let input = $i('re-file-search');
        let keyword = input ? input.value : '';
        let cb = $i('re-case-sensitive');
        let caseSensitive = !!(cb && cb.checked);
        if (!keyword.trim()) { clearSearch(); return; }
        if (!api) return warnNoApi();
        const requestId = ++state.searchRequestId;
        const searchBtn = $i('re-search-btn');
        if (searchBtn) searchBtn.disabled = true;
        setSearchHint('content', '正在搜索文件内容...');
        try {
            let res = await api.search_files(keyword, caseSensitive);
            if (requestId !== state.searchRequestId) return;
            if (res && res.results_by_category) {
                state.searchResults = res.results_by_category;
                state.searchTotal = res.total_matches || 0;
            } else {
                state.searchResults = {};
                state.searchTotal = 0;
            }
        } catch (e) {
            if (requestId !== state.searchRequestId) return;
            console.error('[rule-editor] performSearch failed:', e);
            state.searchResults = {};
            state.searchTotal = 0;
        } finally {
            if (requestId === state.searchRequestId && searchBtn) searchBtn.disabled = false;
        }
        if (requestId !== state.searchRequestId) return;
        renderSearchCategories();
        if (state.searchTotal > 0) {
            let hint = $i('re-search-hint');
            if (hint) { hint.style.display = 'none'; }
            switchTab('search-results');
        } else {
            setSearchHint('', '未找到任何匹配');
        }
    }

    function setSearchHint(type, msg) {
        let hint = $i('re-search-hint');
        if (!hint) return;
        hint.textContent = msg;
        hint.style.display = '';
        if (type === 'file') hint.className = 're-search-hint re-search-hint-file';
        else if (type === 'content') hint.className = 're-search-hint re-search-hint-content';
        else hint.className = 're-search-hint';
    }

    function renderSearchCategories() {
        const container = $i('re-search-results-container');
        if (!container) return;
        if (!state.searchResults) {
            container.innerHTML = '<div class="re-empty-state">输入关键词后点击搜索</div>';
            return;
        }
        const entries = Object.keys(state.searchResults);
        let any = false;
        for (let i = 0; i < entries.length; i++) {
            if (state.searchResults[entries[i]] && state.searchResults[entries[i]].length) { any = true; break; }
        }
        if (!any) {
            container.innerHTML = '<div class="re-empty-state">未找到匹配（共 0 处）</div>';
            return;
        }
        let html = '<div class="re-search-summary">共 ' + state.searchTotal + ' 处匹配</div>';
        for (let ci = 0; ci < CATEGORY_ORDER.length; ci++) {
            const category = CATEGORY_ORDER[ci];
            const list = state.searchResults[category];
            if (!list || !list.length) continue;
            html += '<div class="re-file-group"><div class="re-file-group-title">' + escapeHtml(category) + '</div>';
            for (let li = 0; li < list.length; li++) {
                const entry = list[li];
                const path = Array.isArray(entry) ? entry[0] : (entry.file || entry.path || '');
                const count = Array.isArray(entry) ? entry[1] : (entry.matches || 0);
                html += '<div class="re-file-item re-search-item" data-path="' + escapeAttr(path) +
                    '" title="双击打开"><span>' + escapeHtml(path) + '</span> <span class="re-match-count">' +
                    count + ' 处</span></div>';
            }
            html += '</div>';
        }
        container.innerHTML = html;
        var currentKeyword = document.getElementById('re-file-search');
        var kw = currentKeyword ? currentKeyword.value : '';
        const items = container.querySelectorAll('.re-search-item');
        for (let i = 0; i < items.length; i++) {
            items[i].addEventListener('dblclick', (function (el, keyword) {
                return async function () {
                    await createFileTab(el.dataset.path);
                    if (keyword) {
                        prefillEditorSearch(keyword);
                    }
                };
            })(items[i], kw));
        }
    }

    // ═══════════════════════════════════════════════════════
    //  文件状态面板 — 类 VSCode Source Control，显示修改文件
    // ═══════════════════════════════════════════════════════
    function renderFileStatusPanel() {
        var container = $i('re-file-status-container');
        if (!container) return;

        var stagedCount = 0;
        var appliedCount = 0;
        var fileEntries = [];

        state.openFiles.forEach(function (ts, path) {
            if (ts.editStatus === 'staged') stagedCount++;
            else if (ts.editStatus === 'applied') appliedCount++;
            if (ts.editStatus === 'staged' || ts.editStatus === 'applied') {
                fileEntries.push({ path: path, status: ts.editStatus, ts: ts });
            }
        });

        if (!fileEntries.length) {
            container.innerHTML = '<div class="re-empty-state"><i class="fas fa-check-circle"></i> 无更改</div>';
            return;
        }

        var html = '<div class="re-file-status-summary">' +
            '<span class="re-file-status-summary-text">' + fileEntries.length + ' 个文件已修改' +
            '（' + stagedCount + ' 暂存, ' + appliedCount + ' 已应用）</span>';
        // Feature 6: 应用规则集到暂存文件按钮
        if (stagedCount > 0 && state.currentRuleset && state.currentRuleset.name) {
            html += '<button class="re-btn re-btn-sm re-file-status-apply-btn" id="re-apply-to-staged-btn" style="margin-left:12px;">' +
                '<i class="fas fa-play"></i> 应用规则集到暂存文件</button>';
        }
        html += '</div>' +
            '<div class="re-file-status-list" id="re-file-status-list">';

        for (var i = 0; i < fileEntries.length; i++) {
            var entry = fileEntries[i];
            var dotCls = entry.status === 'staged' ? 'staged' : 'applied';
            var statusLabel = entry.status === 'staged' ? '暂存' : '已应用';
            html += '<div class="re-file-status-item" data-path="' + escapeAttr(entry.path) + '">' +
                '<span class="re-file-status-dot ' + dotCls + '">●</span>' +
                '<span class="re-file-status-name">' + escapeHtml(entry.path) + '</span>' +
                '<span class="re-file-status-badge re-file-status-badge-' + dotCls + '">' + statusLabel + '</span>' +
                '<span class="re-file-status-actions">';
            if (entry.status === 'applied') {
                html += '<button class="re-file-status-action-btn re-fsa-revert-applied" data-path="' + escapeAttr(entry.path) + '" title="还原到暂存">↩</button>';
            } else if (entry.status === 'staged') {
                html += '<button class="re-file-status-action-btn re-fsa-discard" data-path="' + escapeAttr(entry.path) + '" title="放弃更改">↩</button>' +
                    '<button class="re-file-status-action-btn re-fsa-apply" data-path="' + escapeAttr(entry.path) + '" title="保存为应用">✓</button>';
            }
            html += '</span></div>';
        }

        html += '</div>';
        container.innerHTML = html;

        // 事件委托：处理操作按钮点击（防止冒泡到文件项）
        var list = container.querySelector('#re-file-status-list');
        if (list) {
            list.addEventListener('click', async function (e) {
                var btn = e.target.closest('button');
                if (!btn) {
                    // 点击文件项（非按钮区）→ 打开文件
                    var item = e.target.closest('.re-file-status-item');
                    if (item) {
                        var path = item.dataset.path;
                        if (path) await createFileTab(path);
                    }
                    return;
                }
                e.stopPropagation();
                var path = btn.dataset.path;
                if (!path) return;
                var ts = state.openFiles.get(path);
                if (!ts) return;
                if (btn.classList.contains('re-fsa-revert-applied')) {
                    await revertAppliedToStaged(ts);
                } else if (btn.classList.contains('re-fsa-discard')) {
                    revertStagedToOriginal(ts);
                } else if (btn.classList.contains('re-fsa-apply')) {
                    await saveStagedAsApplied(ts);
                }
            });
        }

        // Feature 6: 应用规则集到暂存文件按钮
        var applyBtn = container.querySelector('#re-apply-to-staged-btn');
        if (applyBtn) {
            applyBtn.addEventListener('click', async function (e) {
                e.stopPropagation();
                await applyRulesetToStagedFiles();
            });
        }
    }

    function prefillEditorSearch(query) {
        if (!query) return;
        var ts = getActiveTabState();
        if (!ts || !ts.editor) return;

        // 保存到跨标签搜索桥接
        _searchBridge.query = query;
        _searchBridge.replaceQuery = '';
        _searchBridge.caseSensitive = false;
        _searchBridge.wholeWord = false;
        _searchBridge.regexp = false;
        _searchBridge.isOpen = true;

        var CM = window.CodeMirror;
        if (!CM || !CM.openSearchPanel) return;

        try {
            CM.openSearchPanel(ts.editor);
        } catch(e) {}

        setTimeout(function () {
            if (!_searchBridge.isOpen) return;
            if (CM.SearchQuery && CM.setSearchQuery) {
                try {
                    ts.editor.dispatch({
                        effects: CM.setSearchQuery.of(new CM.SearchQuery({
                            search: query,
                            replace: '',
                            caseSensitive: false,
                            wholeWord: false,
                            regexp: false
                        }))
                    });
                } catch(e) {}
            }
        }, 100);
    }

    function clearSearch() {
        state.searchRequestId++;
        state.searchResults = null;
        state.searchTotal = 0;
        const searchBtn = $i('re-search-btn');
        if (searchBtn) searchBtn.disabled = false;
        const input = $i('re-file-search');
        if (input) input.value = '';
        state.fileFilter = '';
        renderSearchCategories();
        renderFileList();
        switchTab('file-list');
        let hint = $i('re-search-hint');
        if (hint) hint.style.display = 'none';
    }

    function switchTab(tab) {
        state.activeTab = tab;
        const tabs = document.querySelectorAll('.re-tab');
        for (let i = 0; i < tabs.length; i++) {
            tabs[i].classList.toggle('active', tabs[i].dataset.tab === tab);
        }
        const fileListC = $i('re-file-list-container');
        const searchC = $i('re-search-results-container');
        const statusC = $i('re-file-status-container');
        if (fileListC) fileListC.style.display = tab === 'file-list' ? '' : 'none';
        if (statusC) statusC.style.display = tab === 'file-status' ? '' : 'none';
        if (searchC) searchC.style.display = tab === 'search-results' ? '' : 'none';

        // 切换到文件状态标签时刷新视图
        if (tab === 'file-status') {
            renderFileStatusPanel();
        }
    }

    function setMode(mode, skipContentRefresh) {
        state.mode = mode;
        const btns = document.querySelectorAll('.re-mode-btn');
        for (let i = 0; i < btns.length; i++) {
            btns[i].classList.toggle('active', btns[i].dataset.mode === mode);
        }
        const simpleMain = $i('re-simple-mode');
        const advMain = $i('re-advanced-mode');
        if (simpleMain) simpleMain.style.display = mode === 'simple' ? '' : 'none';
        if (advMain) advMain.style.display = mode === 'advanced' ? '' : 'none';
        const simpleContent = $i('re-content-simple');
        const advContent = $i('re-content-advanced');
        if (simpleContent) simpleContent.style.display = mode === 'simple' ? '' : 'none';
        if (advContent) advContent.style.display = mode === 'advanced' ? '' : 'none';
        if (mode === 'advanced' && !state.advancedEditor) initAdvancedMode();
        if (!skipContentRefresh) refreshContentPanel();
    }

    function switchMainTab(tab) {
        var prevTab = state.activeMainTab;
        // Feature 3: 离开规则集编辑 tab 时自动保存
        if (prevTab === 'ruleset-edit' && tab !== 'ruleset-edit') {
            _autoPersistRuleset();
        }
        state.activeMainTab = tab;
        
        var tabs = document.querySelectorAll('.re-main-tab');
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].classList.toggle('active', tabs[i].dataset.maintab === tab);
        }
        
        var fePanel = $i('re-file-edit-panel');
        var rePanel = $i('re-ruleset-edit-panel');
        if (fePanel) fePanel.style.display = tab === 'file-edit' ? '' : 'none';
        if (rePanel) rePanel.style.display = tab === 'ruleset-edit' ? '' : 'none';
        
        // Hide bottom preview panel + resize handle in file-edit mode
        var bottomPanel = document.querySelector('.re-bottom-panel');
        var bottomHandle = document.getElementById('re-resize-bottom');
        if (tab === 'file-edit') {
            if (bottomPanel) bottomPanel.style.display = 'none';
            if (bottomHandle) bottomHandle.style.display = 'none';
        } else {
            if (bottomPanel) bottomPanel.style.display = '';
            if (bottomHandle) bottomHandle.style.display = '';
        }
        
        if (tab === 'file-edit') {
            var currentPath = state.activeFileTab || state.currentFile;
            if (currentPath && prevTab !== 'file-edit') {
                if (state._lastViewedFile !== currentPath) {
                    activateFileTab(currentPath);
                    state._lastViewedFile = currentPath;
                }
            } else if (currentPath && !state._lastViewedFile) {
                activateFileTab(currentPath);
                state._lastViewedFile = currentPath;
            }
        } else if (tab === 'ruleset-edit') {
            // 记录当前正在查看的文件
            state._lastViewedFile = state.activeFileTab || state.currentFile;
            refreshContentPanel();
        }
    }

    function bindEvents() {
        const searchBtn = $i('re-search-btn');
        if (searchBtn) searchBtn.addEventListener('click', performSearch);
        const searchClear = $i('re-search-clear-btn');
        if (searchClear) searchClear.addEventListener('click', clearSearch);
        const searchInput = $i('re-file-search');
        if (searchInput) {
            searchInput.addEventListener('input', function () {
                state.fileFilter = searchInput.value;
                filterFilesByKeyword(searchInput.value);
            });
            searchInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    performSearch();
                }
            });
        }
        const caseSensitive = $i('re-case-sensitive');
        if (caseSensitive) {
            caseSensitive.addEventListener('change', function () {
                if (state.activeTab === 'search-results' && searchInput && searchInput.value.trim()) {
                    performSearch();
                }
            });
        }

        const tabs = document.querySelectorAll('.re-tab');
        for (let i = 0; i < tabs.length; i++) {
            tabs[i].addEventListener('click', (function (el) {
                return function () { switchTab(el.dataset.tab); };
            })(tabs[i]));
        }

        // Main tabs
        const mainTabs = document.querySelectorAll('.re-main-tab');
        for (let i = 0; i < mainTabs.length; i++) {
            mainTabs[i].addEventListener('click', (function (el) {
                return function () { switchMainTab(el.dataset.maintab); };
            })(mainTabs[i]));
        }

        // Ruleset toolbar
        const rsSelect = $i('re-ruleset-select');
        if (rsSelect) rsSelect.addEventListener('change', onRulesetSelectChange);
        const newBtn = $i('re-new-ruleset-btn');
        if (newBtn) newBtn.addEventListener('click', onNewRuleset);
        const saveBtn = $i('re-save-ruleset-btn');
        if (saveBtn) saveBtn.addEventListener('click', onSaveRuleset);
        const delBtn = $i('re-delete-ruleset-btn');
        if (delBtn) delBtn.addEventListener('click', onDeleteRuleset);

        const modeBtns = document.querySelectorAll('.re-mode-btn');
        for (let i = 0; i < modeBtns.length; i++) {
            modeBtns[i].addEventListener('click', (function (el) {
                return function () { setMode(el.dataset.mode); };
            })(modeBtns[i]));
        }

        const addCond = $i('re-add-condition-btn');
        if (addCond) addCond.addEventListener('click', addConditionRow);
        const addOp = $i('re-add-op-btn');
        if (addOp) addOp.addEventListener('click', addOperationRow);
        const previewBtn = $i('re-preview-rule-btn');
        if (previewBtn) previewBtn.addEventListener('click', previewRule);
        const genBtn = $i('re-generate-rule-btn');
        if (genBtn) genBtn.addEventListener('click', generateRule);
        const applyBtn = $i('re-apply-btn');
        if (applyBtn) applyBtn.addEventListener('click', onApplyRuleset);

        const tplSel = $i('re-template-select');
        if (tplSel) tplSel.addEventListener('change', onTemplateSelectChange);
        const fmtBtn = $i('re-format-json-btn');
        if (fmtBtn) fmtBtn.addEventListener('click', formatAdvancedContent);
        const valBtn = $i('re-validate-btn');
        if (valBtn) valBtn.addEventListener('click', validateAdvancedContent);

        const opsCont = $i('re-simple-operations');
        if (opsCont) opsCont.addEventListener('click', function (e) {
            const btn = e.target.closest('.re-remove-op-btn');
            if (btn) { const row = btn.closest('.re-operation-item'); if (row) row.remove(); }
        });
        const condCont = $i('re-simple-conditions');
        if (condCont) condCont.addEventListener('click', function (e) {
            const btn = e.target.closest('.re-remove-cond-btn');
            if (btn) { const row = btn.closest('.re-condition-item'); if (row) row.remove(); }
        });
        const previewList = $i('re-rules-preview-list');
        if (previewList) previewList.addEventListener('click', function (e) {
            const btn = e.target.closest('.re-remove-rule-btn');
            if (btn) { const idx = parseInt(btn.dataset.idx, 10); if (!isNaN(idx)) removeRule(idx); return; }
            const editBtn = e.target.closest('.re-edit-rule-btn');
            if (editBtn) { const idx = parseInt(editBtn.dataset.idx, 10); if (!isNaN(idx)) editRule(idx); return; }
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && state.smartGenOverlay) { closeAnySmartGenDialog(); return; }

            var ctrl = e.ctrlKey || e.metaKey;
            if (ctrl && e.key === 's') {
                e.preventDefault();
                saveEditedFile();
                return;
            }
            if (ctrl && e.key === 'w') {
                e.preventDefault();
                var ts = getActiveTabState();
                if (ts && ts.path) closeFileTab(ts.path);
                return;
            }
            if (ctrl && e.shiftKey && e.key === 'F') {
                e.preventDefault();
                var searchInput = $i('re-file-search');
                if (searchInput) { searchInput.focus(); searchInput.select(); }
                return;
            }
            if (ctrl && e.key === 'f') {
                var ts = getActiveTabState();
                if (ts && ts.editor) {
                    e.preventDefault();
                    var CM = window.CodeMirror;
                    if (CM && CM.openSearchPanel) {
                        if (_searchBridge.isOpen && _searchBridge.query) {
                            // 恢复保存的搜索状态（内部打开面板 + 设置查询）
                            _restoreSearchState(ts.editor, ts.container);
                        } else {
                            // 打开空白搜索面板
                            CM.openSearchPanel(ts.editor);
                            _searchBridge.isOpen = true;
                        }
                    }
                }
                return;
            }
        });

        const simpleContent = $i('re-content-simple');
        if (simpleContent) simpleContent.addEventListener('click', onContentPanelClick);

        // File edit toolbar buttons
        const feSave = $i('re-fe-save-btn');
        if (feSave) feSave.addEventListener('click', saveEditedFile);
        const feRevert = $i('re-fe-revert-btn');
        if (feRevert) feRevert.addEventListener('click', revertEditedFile);
        const feRefresh = $i('re-fe-refresh-btn');
        if (feRefresh) feRefresh.addEventListener('click', refreshEditedFile);
        const feDiff = $i('re-fe-diff-btn');
        if (feDiff) feDiff.addEventListener('click', diffAndTrackChanges);
        const clearChangesBtn = $i('re-clear-changes-btn');
        if (clearChangesBtn) clearChangesBtn.addEventListener('click', clearPendingChanges);
        const genFromChanges = $i('re-gen-from-changes-btn');
        if (genFromChanges) genFromChanges.addEventListener('click', generateRulesFromChanges);

    }

    function onContentPanelClick(e) {
        const selectBtn = e.target.closest('.re-select-field-btn');
        if (selectBtn) {
            selectField(selectBtn.dataset.field, selectBtn.dataset.itemId);
            return;
        }
        const addBtn = e.target.closest('.re-add-item-btn');
        if (addBtn) {
            addItemToRule(addBtn.dataset.itemId);
            return;
        }
        const toggle = e.target.closest('.re-nested-toggle');
        if (toggle) {
            const nested = toggle.nextElementSibling;
            if (nested) nested.style.display = nested.style.display === 'none' ? '' : 'none';
        }
    }

    async function onRulesetSelectChange() {
        const sel = $i('re-ruleset-select');
        if (!sel) return;
        const name = sel.value;
        if (!name) {
            state.currentRuleset = null;
            resetEditingRule();
            renderRulesPreview();
            return;
        }
        await loadRulesetByName(name);
    }

    async function onNewRuleset() {
        const api = getApi();
        if (!api) return warnNoApi();
        const name = window.prompt('请输入新规则集名称：');
        if (!name || !name.trim()) return;
        const trimmed = name.trim();
        try {
            const res = await api.create_ruleset(trimmed);
            if (res && res.success === false) {
                console.warn('[rule-editor] create_ruleset failed:', res.error);
                return;
            }
        } catch (e) {
            console.error('[rule-editor] create_ruleset error:', e);
            return;
        }
        await loadRulesets();
        const sel = $i('re-ruleset-select');
        if (sel) sel.value = trimmed;
        await loadRulesetByName(trimmed);
    }

    async function onSaveRuleset() {
        if (!state.currentRuleset || !state.currentRuleset.name) {
            showToast('没有可保存的规则集（请先选择或新建）', 'error');
            return;
        }
        if (state.mode === 'advanced') {
            const parsed = getAdvancedContent();
            if (parsed == null) return;
            parsed.version = 2;
            parsed.name = parsed.name || state.currentRuleset.name;
            state.currentRuleset = parsed;
        }
        state.currentRuleset.version = 2;
        const api = getApi();
        if (!api || !api.save_ruleset) return warnNoApi();
        try {
            const res = await api.save_ruleset(state.currentRuleset.name, state.currentRuleset);
            if (res && res.success === false) {
                showToast('保存失败: ' + (res.error || ''), 'error');
            } else {
                state._rulesetDirty = false;
                showToast('规则集已保存', 'success');
                // 保存按钮脉冲动画
                var saveBtn = $i('re-save-ruleset-btn');
                if (saveBtn) {
                    saveBtn.classList.add('re-btn-saved');
                    setTimeout(function () { saveBtn.classList.remove('re-btn-saved'); }, 500);
                }
            }
        } catch (e) {
            showToast('保存异常: ' + (e && e.message ? e.message : e), 'error');
        }
    }

    async function onDeleteRuleset() {
        if (!state.currentRuleset || !state.currentRuleset.name) return;
        if (!window.confirm('确认删除规则集 "' + state.currentRuleset.name + '"？此操作不可撤销。')) return;
        const api = getApi();
        if (!api || !api.delete_ruleset) return warnNoApi();
        try {
            const res = await api.delete_ruleset(state.currentRuleset.name);
            if (res && res.success === false) {
                showToast('删除失败: ' + (res.error || ''), 'error');
                return;
            }
            showToast('规则集已删除', 'success');
            state.currentRuleset = null;
            resetEditingRule();
            await loadRulesets();
            refreshRulesetUI();
        } catch (e) {
            showToast('删除异常: ' + (e && e.message ? e.message : e), 'error');
        }
    }

    async function onApplyRuleset() {
        if (!state.currentRuleset || !state.currentRuleset.name) {
            showToast('请先选择一个规则集', 'error');
            return;
        }
        const api = getApi();
        if (!api || !api.apply_ruleset) return warnNoApi();
        try {
            const res = await api.apply_ruleset(state.currentRuleset.name);
            if (res && res.success) showToast('已应用: ' + (res.message || ''), 'success');
            else showToast('应用失败: ' + ((res && res.message) || ''), 'error');
        } catch (e) {
            showToast('应用异常: ' + (e && e.message ? e.message : e), 'error');
        }
    }

    /** Feature 6: 将当前规则集应用到所有暂存文件（仅内存修改，不写硬盘） */
    async function applyRulesetToStagedFiles() {
        if (!state.currentRuleset || !state.currentRuleset.name) {
            showToast('请先选择一个规则集', 'error');
            return;
        }
        var stagedFiles = [];
        state.openFiles.forEach(function (ts, path) {
            if (ts.editStatus === 'staged') stagedFiles.push({ path: path, ts: ts });
        });
        if (!stagedFiles.length) {
            showToast('没有暂存文件可应用', 'info');
            return;
        }
        var api = getApi();
        if (!api || !api.apply_ruleset_to_content) { warnNoApi(); return; }
        var appliedCount = 0;
        var skippedCount = 0;
        for (var i = 0; i < stagedFiles.length; i++) {
            var sf = stagedFiles[i];
            var content = sf.ts.editor.state.doc.toString();
            try {
                var res = await api.apply_ruleset_to_content(state.currentRuleset.name, sf.path, content);
                if (res && res.success && res.rules_applied > 0) {
                    var editor = sf.ts.editor;
                    var docLen = editor.state.doc.length;
                    editor.dispatch({ changes: { from: 0, to: docLen, insert: res.modified_content } });
                    appliedCount++;
                } else if (res && res.success && res.rules_applied === 0) {
                    skippedCount++;
                }
            } catch (e) {
                console.error('[rule-editor] apply to staged failed for', sf.path, e);
            }
        }
        // 刷新所有受影响文件的 UI
        for (var j = 0; j < stagedFiles.length; j++) {
            updateFileEditStatus(stagedFiles[j].ts);
        }
        renderFileTabBar();
        updateFileEditTabLabel();
        if (state.activeTab === 'file-status') renderFileStatusPanel();
        var msg = '已对 ' + appliedCount + ' 个文件应用规则集';
        if (skippedCount > 0) msg += '（' + skippedCount + ' 个无匹配规则）';
        showToast(msg, 'success');
    }

    /** selectField — store user's field selection into state and fill the simple-mode form targeting inputs. */
    function selectField(field, itemId) {
        state.selectedFieldPath = field;
        state.selectedItemId = itemId;
        const idEl = $i('re-simple-item-id');
        if (idEl) idEl.value = itemId != null ? String(itemId) : '';
        const fieldEl = $i('re-simple-field');
        if (fieldEl) fieldEl.value = field || '';
        const useId = $i('re-simple-use-id');
        if (useId && itemId != null && String(itemId) !== '') useId.checked = true;
        highlightSelectedField(field, itemId);
    }

    /** addItemToRule — fill file matching + id + default field so Task 6 form logic can read them. */
    function addItemToRule(itemId) {
        if (state.currentFilePrefix) {
            const fileSel = $i('re-simple-file');
            if (fileSel) fileSel.value = state.currentFilePrefix;
        }
        const field = state.selectedFieldPath || 'desc';
        selectField(field, itemId);
    }

    function highlightSelectedField(field, itemId) {
        const container = $i('re-content-simple');
        if (!container) return;
        const prev = container.querySelectorAll('.re-field-line.is-selected');
        for (let i = 0; i < prev.length; i++) prev[i].classList.remove('is-selected');
        const btns = container.querySelectorAll('.re-select-field-btn');
        const targetId = itemId != null ? String(itemId) : '';
        for (let i = 0; i < btns.length; i++) {
            if (btns[i].dataset.field === field && btns[i].dataset.itemId === targetId) {
                const line = btns[i].closest('.re-field-line');
                if (line) line.classList.add('is-selected');
            }
        }
    }

    function escapeRegex(s) {
        return String(s == null ? '' : s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    function filePatternFromSelection(selection) {
        if (!selection) return '*.json';
        if (CATEGORY_FILE_PATTERNS[selection]) return CATEGORY_FILE_PATTERNS[selection];
        return selection;
    }

    function categoryToPattern(catName) {
        for (let i = 0; i < FILE_PREFIX_RULES.length; i++) {
            if (FILE_PREFIX_RULES[i][1] === catName) {
                const prefix = FILE_PREFIX_RULES[i][0];
                return CATEGORY_FILE_PATTERNS[prefix] || (prefix + '*.json');
            }
        }
        if (CATEGORY_FILE_PATTERNS[catName]) return CATEGORY_FILE_PATTERNS[catName];
        return escapeRegex(catName) + '.*\\.json$';
    }

    /** initSimpleFileSelect — populate #re-simple-file, preferring autocomplete data; cache it. */
    async function initSimpleFileSelect() {
        const sel = $i('re-simple-file');
        if (!sel) return;
        const api = getApi();
        if (api && api.get_autocomplete_data) {
            try {
                const data = await api.get_autocomplete_data();
                if (data && data.file_patterns) state.autocomplete = data;
            } catch (e) {
                console.warn('[rule-editor] get_autocomplete_data failed', e);
            }
        }
        if (!state.autocomplete) state.autocomplete = localAutocompleteFallback();
        const prefixToCategory = {};
        for (let i = 0; i < FILE_PREFIX_RULES.length; i++) prefixToCategory[FILE_PREFIX_RULES[i][0]] = FILE_PREFIX_RULES[i][1];
        const fps = (state.autocomplete && state.autocomplete.file_patterns) ? state.autocomplete.file_patterns : [];
        if (!fps.length) { populateSimpleFileSelect(); return; }
        let opts = ['<option value="">-- 选择文件分类 --</option>'];
        const seen = {};
        for (let i = 0; i < fps.length; i++) {
            const key = fps[i].label || '';
            if (!key || seen[key]) continue;
            seen[key] = true;
            const display = prefixToCategory[key] || key;
            opts.push('<option value="' + escapeAttr(key) + '">' + escapeHtml(display) + '</option>');
        }
        sel.innerHTML = opts.join('');
    }

    function localAutocompleteFallback() {
        const fps = [];
        for (let i = 0; i < FILE_PREFIX_RULES.length; i++) {
            const prefix = FILE_PREFIX_RULES[i][0];
            const value = CATEGORY_FILE_PATTERNS[prefix] || (prefix + '*.json');
            fps.push({ label: prefix, value: value });
        }
        return {
            file_patterns: fps,
            common_replacements: [
                { from: '大于', to: '>' }, { from: '小于', to: '<' },
                { from: '不低于', to: '≥' }, { from: '不高于', to: '≤' },
                { from: '自身', to: '<u><color=#7C5738>自身</color></u>' },
                { from: '目标', to: '<u><color=#7C5738>目标</color></u>' },
                { from: '护盾', to: '<u><color=#81BBE8>护盾</color></u>' },
                { from: '体力', to: '<u><color=#61DA61>体力</color></u>' }
            ]
        };
    }

    function buildFormData() {
        const fileSel = $i('re-simple-file');
        const fileCustom = $i('re-simple-file-custom');
        let file_pattern = '';
        if (fileCustom && fileCustom.value.trim()) file_pattern = fileCustom.value.trim();
        else if (fileSel) file_pattern = fileSel.value || '';
        const useId = $i('re-simple-use-id');
        const useIdChecked = !!(useId && useId.checked);
        const idEl = $i('re-simple-item-id');
        let item_ids = [];
        if (useIdChecked && idEl && idEl.value.trim()) {
            item_ids = idEl.value.split(',').map(function (s) { return s.trim(); }).filter(function (s) { return s.length; }).map(function (s) {
                const n = Number(s);
                return isNaN(n) ? s : n;
            });
        }
        const fieldEl = $i('re-simple-field');
        const target_paths = fieldEl ? fieldEl.value.split(',').map(function (s) { return s.trim(); }).filter(Boolean) : ['desc'];
        const scopeEl = $i('re-simple-scope');
        const scope = scopeEl ? (scopeEl.value.trim() || 'dataList[*]') : 'dataList[*]';
        return {
            file_pattern: file_pattern,
            item_ids: item_ids,
            scope: scope,
            target_paths: target_paths.length ? target_paths : ['desc'],
            operations: readOperationRows(),
            extra_conditions: readConditionRows()
        };
    }

    function readOperationRows() {
        const cont = $i('re-simple-operations');
        if (!cont) return [];
        const rows = cont.querySelectorAll('.re-operation-item');
        const out = [];
        for (let i = 0; i < rows.length; i++) {
            const typeEl = rows[i].querySelector('.re-op-type');
            const modeEl = rows[i].querySelector('.re-op-mode');
            const fromEl = rows[i].querySelector('.re-op-from');
            const toEl = rows[i].querySelector('.re-op-to');
            const type = typeEl ? typeEl.value : 'replace';
            const mode = modeEl ? modeEl.value : 'literal';
            const from = fromEl ? fromEl.value : '';
            const to = toEl ? toEl.value : '';
            if (type === 'replace' && (from.length || to.length)) out.push({ type: type, mode: mode, from: from, to: to });
            else if (type === 'wrap') out.push({ type: type, prefix: from, suffix: to });
            else if (type === 'gradient' && from.length) out.push({ type: type, rate: Number(from) });
            else if (type === 'skill_color') out.push({ type: type, idPath: from || 'id' });
        }
        return out;
    }

    function readConditionRows() {
        const cont = $i('re-simple-conditions');
        if (!cont) return [];
        const rows = cont.querySelectorAll('.re-condition-item');
        const out = [];
        for (let i = 0; i < rows.length; i++) {
            const fieldEl = rows[i].querySelector('.re-cond-field');
            const operatorEl = rows[i].querySelector('.re-cond-operator');
            const patEl = rows[i].querySelector('.re-cond-pattern');
            const field = fieldEl ? fieldEl.value : '';
            const operator = operatorEl ? operatorEl.value : 'regex';
            const value = patEl ? patEl.value : '';
            if (field && value) out.push({ path: field, operator: operator, value: value });
        }
        return out;
    }

    function buildRuleLocally(form) {
        const filePattern = filePatternFromSelection(form.file_pattern || '');
        const item_ids = form.item_ids || [];
        const targetPaths = form.target_paths || ['desc'];
        const operations = form.operations || [];
        const extra_conditions = form.extra_conditions || [];
        const where = [];
        if (item_ids.length) {
            where.push({ path: 'id', operator: 'in', value: item_ids });
        }
        for (let i = 0; i < extra_conditions.length; i++) {
            const ec = extra_conditions[i];
            if (ec.path && ec.value) {
                let value = ec.value;
                if (ec.operator === 'in') value = String(value).split(',').map(function (part) { return part.trim(); }).filter(Boolean);
                where.push({ path: ec.path, operator: ec.operator || 'regex', value: value });
            }
        }
        return { files: [filePattern], scope: form.scope || 'dataList[*]', targets: targetPaths, where: where, actions: operations };
    }

    function validateRuleLocally(rule) {
        const errors = [];
        if (!rule || typeof rule !== 'object') return { valid: false, errors: ['规则必须是 JSON 对象'] };
        if (Array.isArray(rule.rules)) {
            if (rule.version !== 2) errors.push('规则集必须包含 version: 2');
            for (let ruleIndex = 0; ruleIndex < rule.rules.length; ruleIndex++) {
                const result = validateRuleLocally(rule.rules[ruleIndex]);
                for (let errorIndex = 0; errorIndex < result.errors.length; errorIndex++) {
                    errors.push('rules[' + ruleIndex + ']: ' + result.errors[errorIndex]);
                }
            }
            return { valid: errors.length === 0, errors: errors };
        }
        if (!Array.isArray(rule.files) || !rule.files.length) errors.push('缺少 files 字段（Glob 列表）');
        if (!Array.isArray(rule.targets) || !rule.targets.length) errors.push('缺少 targets 字段');
        const action = rule.actions || [];
        if (!action.length) errors.push('缺少 actions 字段（操作列表）');
        else {
            for (let i = 0; i < action.length; i++) {
                const a = action[i];
                if (!a || typeof a !== 'object' || !a.type) errors.push('actions[' + i + '] 缺少 type');
            }
        }
        return { valid: errors.length === 0, errors: errors };
    }

    async function previewRule() {
        const form = buildFormData();
        let rule = null;
        const api = getApi();
        if (api && api.build_rule_from_form) {
            try { rule = await api.build_rule_from_form(form); }
            catch (e) { console.warn('[rule-editor] build_rule_from_form failed, local fallback', e); rule = null; }
        }
        if (!rule) rule = buildRuleLocally(form);
        state.lastPreviewRule = rule;
        const pre = $i('re-simple-preview-content');
        const wrap = $i('re-simple-preview');
        if (pre) pre.textContent = JSON.stringify(rule, null, 2);
        if (wrap) wrap.style.display = '';
        return rule;
    }

    async function generateRule() {
        const rule = await previewRule();
        if (!rule) return;
        let valid = true, errors = [];
        const api = getApi();
        if (api && api.validate_rule) {
            try {
                const r = await api.validate_rule(JSON.stringify(rule));
                valid = !!(r && r.valid);
                errors = (r && r.errors) ? r.errors : [];
            } catch (e) { console.warn(e); }
        } else {
            const r = validateRuleLocally(rule);
            valid = r.valid; errors = r.errors;
        }
        if (!valid) {
            showToast('规则验证失败: ' + (errors.join('; ') || '未知错误'), 'error');
            return;
        }
        if (!state.currentRuleset) {
            showToast('请先选择或新建一个规则集', 'error');
            return;
        }
        if (!Array.isArray(state.currentRuleset.rules)) state.currentRuleset.rules = [];
        // 检查是否处于编辑模式
        var editIdx = state._editingRuleIndex;
        if (editIdx != null && editIdx >= 0 && editIdx < state.currentRuleset.rules.length) {
            state.currentRuleset.rules[editIdx] = rule;
            state._editingRuleIndex = null;
            state._rulesetDirty = true;
            var genBtn = $i('re-generate-rule-btn');
            if (genBtn) genBtn.textContent = '📋 生成规则JSON';
            refreshRulesetUI();
            await persistCurrentRuleset();
            showToast('已更新规则 #' + (editIdx + 1), 'success');
        } else {
            state.currentRuleset.rules.push(rule);
            state._rulesetDirty = true;
            refreshRulesetUI();
            await persistCurrentRuleset();
            showToast('已添加规则到当前规则集', 'success');
        }
    }

    function resetEditingRule() {
        state._editingRuleIndex = null;
        var genBtn = $i('re-generate-rule-btn');
        if (genBtn) genBtn.textContent = '📋 生成规则JSON';
    }

    async function persistCurrentRuleset() {
        if (!state.currentRuleset || !state.currentRuleset.name) return;
        state.currentRuleset.version = 2;
        const api = getApi();
        if (!api || !api.save_ruleset) return;
        try {
            var result = await api.save_ruleset(state.currentRuleset.name, state.currentRuleset);
            if (result && result.success === false) {
                throw new Error(result.error || '保存失败');
            }
            state._rulesetDirty = false;
        } catch (e) {
            console.error('[rule-editor] persist failed:', e);
            throw e; // 重新抛出，让调用方知晓失败
        }
    }

    async function _autoPersistRuleset() {
        if (!state._rulesetDirty) return;
        if (!state.currentRuleset || !state.currentRuleset.name) return;
        try {
            await persistCurrentRuleset();
            state._rulesetDirty = false;
        } catch (e) {
            console.error('[rule-editor] auto-persist failed:', e);
        }
    }

    function removeRule(index) {
        if (!state.currentRuleset || !Array.isArray(state.currentRuleset.rules)) return;
        if (index < 0 || index >= state.currentRuleset.rules.length) return;
        state.currentRuleset.rules.splice(index, 1);
        state._rulesetDirty = true;
        resetEditingRule();
        refreshRulesetUI();
        persistCurrentRuleset();
    }

    function editRule(index) {
        if (!state.currentRuleset || !Array.isArray(state.currentRuleset.rules)) return;
        if (index < 0 || index >= state.currentRuleset.rules.length) return;
        var rule = state.currentRuleset.rules[index];
        if (!rule) return;

        // 切换到简单模式并填充表单
        setMode('simple');

        // 填充文件 Glob
        var filePattern = (rule.files && rule.files[0]) || '';
        var fileSelect = $i('re-simple-file');
        var fileCustom = $i('re-simple-file-custom');
        var matched = false;
        if (fileSelect) {
            for (var ci = 0; ci < FILE_PREFIX_RULES.length; ci++) {
                var key = FILE_PREFIX_RULES[ci][0];
                if (CATEGORY_FILE_PATTERNS[key] === filePattern) {
                    fileSelect.value = key;
                    matched = true;
                    break;
                }
            }
            if (!matched) fileSelect.value = '';
        }
        if (fileCustom) {
            fileCustom.value = !matched ? filePattern : '';
        }

        // 填充作用域、目标与条件
        var conditions = rule.where || [];
        var condContainer = $i('re-simple-conditions');
        if (condContainer) condContainer.innerHTML = '';

        var useIdEl = $i('re-simple-use-id');
        var idEl = $i('re-simple-item-id');
        var fieldEl = $i('re-simple-field');
        var scopeEl = $i('re-simple-scope');
        if (scopeEl) scopeEl.value = rule.scope || 'dataList[*]';
        if (fieldEl) fieldEl.value = (rule.targets || ['desc']).join(', ');

        var useId = false;
        var idValues = [];
        for (var ci2 = 0; ci2 < conditions.length; ci2++) {
            var condition = conditions[ci2];
            if (condition.path === 'id' && condition.operator === 'in' && Array.isArray(condition.value)) {
                useId = true;
                idValues = condition.value;
                continue;
            }
            addConditionRow();
            var conditionRows = condContainer ? condContainer.querySelectorAll('.re-condition-item') : [];
            var conditionRow = conditionRows[conditionRows.length - 1];
            if (conditionRow) {
                var condField = conditionRow.querySelector('.re-cond-field');
                var condOperator = conditionRow.querySelector('.re-cond-operator');
                var condValue = conditionRow.querySelector('.re-cond-pattern');
                if (condField) condField.value = condition.path || '';
                if (condOperator) condOperator.value = condition.operator || 'regex';
                if (condValue) condValue.value = Array.isArray(condition.value) ? condition.value.join(', ') : String(condition.value == null ? '' : condition.value);
            }
        }
        if (useIdEl) useIdEl.checked = useId;
        if (idEl) idEl.value = useId ? idValues.join(', ') : '';

        // 填充操作列表
        var action = rule.actions || [];
        var opsContainer = $i('re-simple-operations');
        if (opsContainer) {
            opsContainer.innerHTML = '';
            for (var ai = 0; ai < action.length; ai++) {
                var a = action[ai];
                addOperationRow();
                var rows = opsContainer.querySelectorAll('.re-operation-item');
                var lastRow = rows[rows.length - 1];
                if (lastRow) {
                    var typeInp = lastRow.querySelector('.re-op-type');
                    var modeInp = lastRow.querySelector('.re-op-mode');
                    var fromInp = lastRow.querySelector('.re-op-from');
                    var toInp = lastRow.querySelector('.re-op-to');
                    if (typeInp) typeInp.value = a.type || 'replace';
                    if (modeInp) modeInp.value = a.mode || 'literal';
                    if (fromInp) {
                        if (a.type === 'wrap') fromInp.value = a.prefix || '';
                        else if (a.type === 'gradient') fromInp.value = String(a.rate == null ? 2 : a.rate);
                        else if (a.type === 'skill_color') fromInp.value = a.idPath || 'id';
                        else fromInp.value = a.from || '';
                    }
                    if (toInp) toInp.value = a.type === 'wrap' ? (a.suffix || '') : (a.to || '');
                }
            }
            if (action.length === 0) addOperationRow();
        }

        // 记录编辑索引 + 修改按钮文本
        state._editingRuleIndex = index;
        var genBtn = $i('re-generate-rule-btn');
        if (genBtn) genBtn.textContent = '📋 更新规则 (#' + (index + 1) + ')';

        // 切换到规则集编辑标签
        switchMainTab('ruleset-edit');
        showToast('已加载规则 #' + (index + 1) + ' 到编辑表单，修改后点击更新即可', 'info');
    }

    function addConditionRow() {
        const cont = $i('re-simple-conditions');
        if (!cont) return;
        const row = document.createElement('div');
        row.className = 're-condition-item';
        row.innerHTML = '<input type="text" class="re-cond-field" placeholder="相对路径，例如 levelList[*].desc">' +
            '<select class="re-cond-operator"><option value="equals">等于</option><option value="in">属于</option><option value="contains">包含</option><option value="regex">正则</option></select>' +
            '<input type="text" class="re-cond-pattern" placeholder="条件值">' +
            '<button class="re-btn re-btn-sm re-remove-cond-btn">✕</button>';
        cont.appendChild(row);
    }

    function addOperationRow() {
        const cont = $i('re-simple-operations');
        if (!cont) return;
        const row = document.createElement('div');
        row.className = 're-operation-item';
        row.innerHTML = '<select class="re-op-type"><option value="replace">替换</option><option value="wrap">包裹</option><option value="gradient">渐变</option><option value="skill_color">技能颜色</option></select>' +
            '<select class="re-op-mode"><option value="literal">普通文本</option><option value="regex">正则</option></select>' +
            '<input type="text" placeholder="查找 / 前缀 / 渐变率 / ID路径" class="re-op-from">' +
            '<span>→</span>' +
            '<input type="text" placeholder="替换为 / 后缀" class="re-op-to">' +
            '<button class="re-btn re-btn-sm re-remove-op-btn">✕</button>';
        cont.appendChild(row);
    }

    function initAdvancedMode() {
        if (state.advancedEditor) return state.advancedEditor;
        const container = $i('re-advanced-editor');
        if (!container) return null;
        if (!window.CodeMirror || !window.CodeMirror.EditorView) {
            console.warn('[rule-editor] CodeMirror not loaded; advanced editor disabled');
            return null;
        }
        const CM = window.CodeMirror;
        try {
            state.advancedEditor = new CM.EditorView({
                doc: '{}',
                extensions: [CM.basicSetup, CM.json()],
                parent: container
            });
        } catch (e) {
            console.error('[rule-editor] initAdvancedMode failed:', e);
            state.advancedEditor = null;
            return null;
        }
        if (state.currentRuleset) {
            try { setAdvancedEditorDoc(JSON.stringify(state.currentRuleset, null, 2)); } catch (err) { void err; }
        }
        return state.advancedEditor;
    }

    function setAdvancedEditorDoc(text) {
        const view = initAdvancedMode();
        if (!view) return;
        const len = view.state.doc.length;
        view.dispatch({ changes: { from: 0, to: len, insert: text || '' } });
    }

    function getAdvancedContent() {
        if (!state.advancedEditor) initAdvancedMode();
        const v = state.advancedEditor;
        if (!v) return null;
        const text = v.state.doc.toString();
        try { return JSON.parse(text); }
        catch (e) {
            const res = $i('re-validation-result');
            if (res) { res.className = 'invalid'; res.textContent = '❌ JSON 解析错误: ' + e.message; }
            return null;
        }
    }

    function validateAdvancedContent() {
        const parsed = getAdvancedContent();
        if (parsed == null) return;
        const api = getApi();
        const run = async function () {
            let result;
            if (api && api.validate_rule) {
                try { result = await api.validate_rule(JSON.stringify(parsed)); }
                catch (e) { console.warn(e); result = validateRuleLocally(parsed); }
            } else {
                result = validateRuleLocally(parsed);
            }
            const res = $i('re-validation-result');
            if (!res) return;
            if (result && result.valid) {
                res.className = 'valid'; res.textContent = '✓ 有效';
            } else {
                res.className = 'invalid';
                const errs = (result && result.errors) ? result.errors : ['未知错误'];
                res.innerHTML = '❌ 无效<ul style="margin:4px 0 0 16px;">' +
                    errs.map(function (e) { return '<li>' + escapeHtml(e) + '</li>'; }).join('') + '</ul>';
            }
        };
        run();
    }

    function formatAdvancedContent() {
        const parsed = getAdvancedContent();
        if (parsed == null) return;
        setAdvancedEditorDoc(JSON.stringify(parsed, null, 2));
        const res = $i('re-validation-result');
        if (res) { res.className = ''; res.textContent = '已格式化'; }
    }

    function syncAdvancedFromRuleset() {
        if (!state.advancedEditor) return;
        let doc = '{}';
        if (state.currentRuleset) {
            try { doc = JSON.stringify(state.currentRuleset, null, 2); } catch (e) { doc = '{}'; }
        }
        setAdvancedEditorDoc(doc);
    }

    async function loadTemplates() {
        const sel = $i('re-template-select');
        if (!sel) return;
        let templates = [];
        const api = getApi();
        if (api && api.get_templates) {
            try { const t = await api.get_templates(); if (Array.isArray(t)) templates = t; }
            catch (e) { console.warn(e); templates = localTemplates(); }
        } else {
            templates = localTemplates();
        }
        state.templates = templates;
        let opts = ['<option value="">📋 模板...</option>'];
        for (let i = 0; i < templates.length; i++) {
            opts.push('<option value="' + escapeAttr(String(i)) + '">' +
                escapeHtml(templates[i].name || ('模板 ' + (i + 1))) + '</option>');
        }
        sel.innerHTML = opts.join('');
    }

    function localTemplates() {
        return [
            { name: '空规则集', template: { version: 2, name: '', desc: '', rules: [] } },
            { name: '简单文本替换', template: { version: 2, name: '', desc: '', rules: [{
                files: ['Skill*.json'], scope: 'dataList[*]', targets: ['desc'], where: [],
                actions: [{ type: 'replace', mode: 'literal', from: '查找', to: '替换' }]
            }] } },
            { name: '按ID定位替换', template: { version: 2, name: '', desc: '', rules: [{
                files: ['Skill*.json'], scope: 'dataList[*]', targets: ['desc'],
                where: [{ path: 'id', operator: 'equals', value: 10001 }],
                actions: [{ type: 'replace', mode: 'literal', from: '查找', to: '替换' }]
            }] } },
            { name: '颜色渐变', template: { version: 2, name: '', desc: '', rules: [{
                files: ['BattleSpeechBubbleDlg*.json'], scope: 'dataList[*]', targets: ['dlg'], where: [],
                actions: [{ type: 'gradient', rate: 0.4 }]
            }] } }
        ];
    }

    function onTemplateSelectChange() {
        const sel = $i('re-template-select');
        if (!sel || !sel.value) return;
        const idx = parseInt(sel.value, 10);
        if (isNaN(idx) || !state.templates || !state.templates[idx]) return;
        const tpl = state.templates[idx].template;
        let doc;
        try { doc = JSON.stringify(tpl, null, 2); } catch (e) { doc = '{}'; }
        setAdvancedEditorDoc(doc);
        const res = $i('re-validation-result');
        if (res) { res.className = ''; res.textContent = '已加载模板: ' + state.templates[idx].name; }
    }

    async function openSmartGeneration() {
        const api = getApi();
        if (!state.smartChanges) state.smartChanges = [];
        let groups = null;
        if (api && api.analyze_changes) {
            try {
                const res = await api.analyze_changes(state.smartChanges);
                if (res && Array.isArray(res.groups)) groups = res.groups;
            } catch (e) { console.warn('[rule-editor] analyze_changes failed', e); groups = null; }
        }
        if (!groups) groups = analyzeChangesLocally(state.smartChanges);
        showSmartGenDialog(groups);
    }

    function showSmartGenDialog(groups) {
        closeSmartGenDialog();
        const overlay = document.createElement('div');
        overlay.className = 're-overlay';
        state.smartGenOverlay = overlay;
        state.smartGenGroups = groups || [];

        let bodyHtml;
        if (!groups || !groups.length) {
            bodyHtml = '<div class="re-empty-state">' +
                '<i class="fas fa-info-circle"></i>' +
                '未检测到修改。可在下方粘贴一个 JSON 数组（每项含 file, field_path, item_id, old_val, new_val）进行分析。<br>' +
                '<textarea id="re-smart-changes-input" style="width:100%;min-height:120px;font-family:Consolas,monospace;font-size:12px;margin-top:8px;padding:6px;border-radius:6px;border:1px solid var(--color-border);"></textarea>' +
                '<button class="re-btn re-btn-primary re-btn-sm" id="re-smart-parse-btn" style="margin-top:6px;">解析并分析</button>' +
                '</div>';
        } else {
            bodyHtml = '';
            for (let i = 0; i < groups.length; i++) bodyHtml += renderSmartGroupCard(groups[i], i);
            bodyHtml += '<div style="text-align:right;margin-top:8px;">' +
                '<button class="re-btn re-btn-accent re-btn-sm" id="re-gen-all-btn">✅ 一键应用所有推荐</button></div>';
        }

        overlay.innerHTML =
            '<div class="re-smart-gen-dialog">' +
            '<div class="re-smart-gen-header"><h3><i class="fas fa-brain"></i> 智能生成规则集</h3>' +
            '<button class="re-btn re-btn-sm" id="re-smart-close-btn">✕</button></div>' +
            '<div class="re-smart-gen-body">' + bodyHtml + '</div>' +
            '</div>';
        document.body.appendChild(overlay);

        const closeBtn = overlay.querySelector('#re-smart-close-btn');
        if (closeBtn) closeBtn.addEventListener('click', closeSmartGenDialog);
        overlay.addEventListener('click', function (e) { if (e.target === overlay) closeSmartGenDialog(); });
        const parseBtn = overlay.querySelector('#re-smart-parse-btn');
        if (parseBtn) parseBtn.addEventListener('click', reparseSmartChanges);
        const genAllBtn = overlay.querySelector('#re-gen-all-btn');
        if (genAllBtn) genAllBtn.addEventListener('click', generateAllSmart);
        const previewBtns = overlay.querySelectorAll('.re-smart-preview-btn');
        for (let i = 0; i < previewBtns.length; i++) {
            previewBtns[i].addEventListener('click', (function (idx) {
                return function () { previewSmartGroup(state.smartGenGroups[idx]); };
            })(parseInt(previewBtns[i].dataset.idx, 10)));
        }
        const applyBtns = overlay.querySelectorAll('.re-smart-apply-btn');
        for (let i = 0; i < applyBtns.length; i++) {
            applyBtns[i].addEventListener('click', (function (idx) {
                return function () { applySmartGroup(state.smartGenGroups[idx]); };
            })(parseInt(applyBtns[i].dataset.idx, 10)));
        }
        const editBtns = overlay.querySelectorAll('.re-smart-edit-btn');
        for (let i = 0; i < editBtns.length; i++) {
            editBtns[i].addEventListener('click', (function (idx) {
                return function () { editSmartGroupScope(idx); };
            })(parseInt(editBtns[i].dataset.idx, 10)));
        }
    }

    function editSmartGroupScope(idx) {
        var overlay = state.smartGenOverlay;
        var card = overlay ? overlay.querySelector('.re-smart-gen-group[data-group-idx="' + idx + '"]') : null;
        if (!card) return;
        card.scrollIntoView({ behavior: 'smooth', block: 'start' });
        card.style.transition = 'outline-color 0.3s ease';
        card.style.outline = '2px solid var(--color-primary, #4f8cff)';
        setTimeout(function () { card.style.outline = ''; }, 2000);
    }

    function renderSmartGroupCard(group, idx) {
        const score = group.score || {};
        const priority = score.priority || 0;
        let tier, tierLabel, badgeCls;
        if (priority >= 70) { tier = '🟢'; tierLabel = '推荐'; badgeCls = 're-score-green'; }
        else if (priority >= 40) { tier = '🟡'; tierLabel = '可选'; badgeCls = 're-score-yellow'; }
        else { tier = '🔴'; tierLabel = '需审查'; badgeCls = 're-score-red'; }

        let html = '<div class="re-smart-gen-group" data-group-idx="' + idx + '">';
        html += '<h4>组 #' + (idx + 1) + ' — ' + tier + ' ' + escapeHtml(tierLabel) +
            ' <span class="re-score-badge ' + badgeCls + '">' + priority + '分</span></h4>';
        if (group.change_type) html += '<div style="font-size:12px;color:var(--color-text-secondary);margin-bottom:4px;">类型: ' + escapeHtml(group.change_type) + '</div>';
        if (group.summary) html += '<div style="margin-bottom:6px;font-size:13px;">💡 ' + escapeHtml(group.summary) + '</div>';
        if (group.action_preview && group.action_preview.length) {
            html += '<div class="re-group-patterns">';
            for (let i = 0; i < group.action_preview.length; i++) {
                const ap = group.action_preview[i];
                html += '<span class="re-pattern-pair">' + escapeHtml(String(ap.from || '')) +
                    ' → ' + escapeHtml(String(ap.to || '')) + '</span>';
            }
            html += '</div>';
        }
        if (group.suggestions && group.suggestions.length) {
            html += '<ul style="margin:4px 0 8px 18px;font-size:12px;color:var(--color-text-secondary);">';
            for (let i = 0; i < group.suggestions.length; i++) html += '<li>' + escapeHtml(group.suggestions[i]) + '</li>';
            html += '</ul>';
        }
        html += renderL1(group.l1_options, idx);
        html += renderL2(group.l2_options, idx);
        html += renderL3(group.l3_options, idx);
        html += renderL4(group.l4_options, idx);
        html += '<div style="display:flex;gap:6px;justify-content:flex-end;margin-top:8px;">' +
            '<button class="re-btn re-btn-sm re-smart-edit-btn" data-idx="' + idx + '">✏ 编辑范围</button>' +
            '<button class="re-btn re-btn-sm re-smart-preview-btn" data-idx="' + idx + '">📋 预览JSON</button>' +
            '<button class="re-btn re-btn-sm re-btn-success re-smart-apply-btn" data-idx="' + idx + '">✅ 生成此规则</button>' +
            '</div>';
        html += '<pre class="re-smart-preview-out" style="display:none;margin-top:6px;font-size:12px;background:var(--color-bg-primary);padding:8px;border-radius:6px;overflow:auto;max-height:200px;white-space:pre-wrap;"></pre>';
        html += '</div>';
        return html;
    }

    function renderL1(l1, scopeId) {
        if (!l1) return '';
        let html = '<div class="re-tier-label">L1 文件范围</div>';
        const suggested = l1.suggested || 'category';
        const opts = [
            { val: 'all', text: '全部文件' },
            { val: 'category', text: '按分类筛选' },
            { val: 'exact', text: '精确文件' },
            { val: 'custom', text: '自定义正则' }
        ];
        for (let i = 0; i < opts.length; i++) {
            const checked = (opts[i].val === suggested) ? 'checked' : '';
            html += '<label class="re-tier-option"><input type="radio" class="re-tier-radio" name="l1-' + scopeId +
                '" value="' + opts[i].val + '" ' + checked + '><span class="re-tier-text">' + opts[i].text + '</span></label>';
        }
        if (l1.categories && l1.categories.length) {
            html += '<div class="re-tier-checks">';
            for (let i = 0; i < l1.categories.length; i++) {
                const c = l1.categories[i];
                const ck = c.selected ? 'checked' : '';
                html += '<label class="re-checkbox"><input type="checkbox" class="re-l1-cat" value="' +
                    escapeAttr(c.name) + '" ' + ck + '> ' + escapeHtml(c.name) + ' (' + c.count + ')</label>';
            }
            html += '</div>';
        }
        html += '<div class="re-tier-hint"><input type="text" class="re-l1-custom" placeholder="自定义正则" style="width:80%;"></div>';
        if (l1.exact_files && l1.exact_files.length) {
            html += '<div class="re-tier-hint">精确文件: ' + escapeHtml(l1.exact_files.join(', ')) + '</div>';
        }
        return html;
    }

    function renderL2(l2, scopeId) {
        if (!l2) return '';
        let html = '<div class="re-tier-label">L2 条目定位</div>';
        const suggested = l2.suggested || (l2.item_ids && l2.item_ids.length ? 'id' : 'full_text');
        const opts = [
            { val: 'full_text', text: '全文匹配（对所有 dataList 项生效）' },
            { val: 'id', text: '按 id 定位' }
        ];
        for (let i = 0; i < opts.length; i++) {
            const checked = (opts[i].val === suggested) ? 'checked' : '';
            html += '<label class="re-tier-option"><input type="radio" class="re-tier-radio" name="l2-' + scopeId +
                '" value="' + opts[i].val + '" ' + checked + '><span class="re-tier-text">' + opts[i].text + '</span></label>';
        }
        const idsStr = (l2.item_ids || []).join(',');
        html += '<div class="re-tier-hint"><input type="text" class="re-l2-ids" placeholder="ID 列表（逗号分隔）" value="' +
            escapeAttr(idsStr) + '" style="width:80%;"></div>';
        return html;
    }

    function renderL3(l3, scopeId) {
        if (!l3) return '';
        let html = '<div class="re-tier-label">L3 字段约束</div>';
        const suggested = l3.suggested || 'restricted';
        const opts = [
            { val: 'restricted', text: '限定字段' },
            { val: 'all_text', text: '所有文本字段' }
        ];
        for (let i = 0; i < opts.length; i++) {
            const checked = (opts[i].val === suggested) ? 'checked' : '';
            html += '<label class="re-tier-option"><input type="radio" class="re-tier-radio" name="l3-' + scopeId +
                '" value="' + opts[i].val + '" ' + checked + '><span class="re-tier-text">' + opts[i].text + '</span></label>';
        }
        if (l3.fields && l3.fields.length) {
            html += '<div class="re-tier-checks">';
            for (let i = 0; i < l3.fields.length; i++) {
                const ck = (l3.fields.length === 1) ? 'checked' : '';
                html += '<label class="re-checkbox"><input type="checkbox" class="re-l3-field" value="' +
                    escapeAttr(l3.fields[i]) + '" ' + ck + '> ' + escapeHtml(l3.fields[i]) + '</label>';
            }
            html += '</div>';
        }
        return html;
    }

    function renderL4(l4, scopeId) {
        if (!l4) return '';
        let html = '<div class="re-tier-label">L4 额外条件</div>';
        const suggested = l4.suggested || 'exact';
        const opts = [
            { val: 'exact', text: '完整匹配（避免误替换）' },
            { val: 'none', text: '无额外条件' },
            { val: 'custom', text: '自定义' }
        ];
        for (let i = 0; i < opts.length; i++) {
            const checked = (opts[i].val === suggested) ? 'checked' : '';
            html += '<label class="re-tier-option"><input type="radio" class="re-tier-radio" name="l4-' + scopeId +
                '" value="' + opts[i].val + '" ' + checked + '><span class="re-tier-text">' + opts[i].text + '</span></label>';
        }
        html += '<div class="re-tier-checks">' +
            '<input type="text" class="re-l4-field" placeholder="字段" style="width:32%;padding:4px 8px;"> ' +
            '<input type="text" class="re-l4-pattern" placeholder="匹配正则" style="width:48%;padding:4px 8px;">' +
            '</div>';
        return html;
    }

    function previewSmartGroup(group) {
        const idx = state.smartGenGroups ? state.smartGenGroups.indexOf(group) : -1;
        if (idx < 0 || !state.smartGenOverlay) return;
        const card = state.smartGenOverlay.querySelector('.re-smart-gen-group[data-group-idx="' + idx + '"]');
        if (!card) return;
        const sel = readSmartSelections(card, idx);
        const rules = buildSmartGroupRules(group, sel);
        const out = card.querySelector('.re-smart-preview-out');
        if (!out) return;
        out.textContent = JSON.stringify(rules, null, 2);
        out.style.display = '';
    }

    async function applySmartGroup(group) {
        if (!group) return;
        const idx = state.smartGenGroups ? state.smartGenGroups.indexOf(group) : -1;
        if (idx < 0) { showToast('找不到该组', 'error'); return; }
        if (!state.smartGenOverlay) return;
        const card = state.smartGenOverlay.querySelector('.re-smart-gen-group[data-group-idx="' + idx + '"]');
        if (!card) { showToast('找不到组的 DOM', 'error'); return; }
        const sel = readSmartSelections(card, idx);
        const rules = buildSmartGroupRules(group, sel);
        if (!rules || !rules.length) { showToast('未能从该组生成规则', 'error'); return; }
        if (!state.currentRuleset) { showToast('请先选择或新建一个规则集', 'error'); return; }
        if (!Array.isArray(state.currentRuleset.rules)) state.currentRuleset.rules = [];
        for (let i = 0; i < rules.length; i++) state.currentRuleset.rules.push(rules[i]);
        state._rulesetDirty = true;
        refreshRulesetUI();
        try {
            await persistCurrentRuleset();
            showToast('已添加 ' + rules.length + ' 条规则', 'success');
        } catch (e) {
            showToast('保存失败: ' + (e && e.message ? e.message : e), 'error');
        }
    }

    function readSmartSelections(card, idx) {
        const sel = {};
        function radio(name) {
            const nodes = card.querySelectorAll('input[name="' + name + '"]');
            for (let i = 0; i < nodes.length; i++) if (nodes[i].checked) return nodes[i].value;
            return '';
        }
        function val(selector) {
            const el = card.querySelector(selector);
            return (el && el.value) ? el.value : '';
        }
        sel.l1 = radio('l1-' + idx);
        sel.l2 = radio('l2-' + idx);
        sel.l3 = radio('l3-' + idx);
        sel.l4 = radio('l4-' + idx);
        sel.l1Categories = [];
        const catNodes = card.querySelectorAll('.re-l1-cat');
        for (let i = 0; i < catNodes.length; i++) if (catNodes[i].checked) sel.l1Categories.push(catNodes[i].value);
        sel.l1Custom = val('.re-l1-custom');
        sel.l2Ids = val('.re-l2-ids').split(',').map(function (s) { return s.trim(); }).filter(function (s) { return s.length; });
        sel.l3Fields = [];
        const fNodes = card.querySelectorAll('.re-l3-field');
        for (let i = 0; i < fNodes.length; i++) if (fNodes[i].checked) sel.l3Fields.push(fNodes[i].value);
        sel.l4Field = val('.re-l4-field');
        sel.l4Pattern = val('.re-l4-pattern');
        return sel;
    }

    function buildSmartGroupRules(group, sel) {
        const rules = [];
        const actionPreview = group.action_preview || [];
        if (!actionPreview.length) return rules;

        let files;
        if (sel.l1 === 'all') files = ['*.json'];
        else if (sel.l1 === 'custom') files = [sel.l1Custom || '*.json'];
        else if (sel.l1 === 'exact') {
            const exactFiles = (group.l1_options && group.l1_options.exact_files) || [];
            files = exactFiles.map(function (f) { return String(f).endsWith('.json') ? String(f) : String(f) + '.json'; });
            if (!files.length) files = ['*.json'];
        } else if (sel.l1 === 'category') {
            const cats = sel.l1Categories.length ? sel.l1Categories :
                ((group.l1_options && group.l1_options.categories) || []).map(function (c) { return c.name; });
            files = cats.map(categoryToPattern).filter(Boolean);
            if (!files.length) files = ['*.json'];
        } else { files = ['*.json']; }

        let fields = sel.l3Fields.slice();
        if (!fields.length) fields = ((group.l3_options && group.l3_options.fields) || []).slice();
        if (!fields.length) fields = ['desc'];

        const useId = sel.l2 === 'id' && sel.l2Ids && sel.l2Ids.length;
        const exact = sel.l4 === 'exact';
        const customCond = (sel.l4 === 'custom' && sel.l4Field && sel.l4Pattern);

        rules.push(buildSmartRule(files, fields, useId, sel.l2Ids || [], exact, customCond, sel, actionPreview));
        return rules;
    }

    function buildSmartRule(files, fields, useId, ids, exact, customCond, sel, actionPreview) {
        const where = [];
        if (useId) where.push({ path: 'id', operator: 'in', value: ids.map(function (id) {
            const numberValue = Number(id);
            return isNaN(numberValue) ? id : numberValue;
        }) });
        if (customCond) {
            where.push({ path: sel.l4Field, operator: 'regex', value: sel.l4Pattern });
        }
        const actions = [];
        for (let i = 0; i < actionPreview.length; i++) {
            const ap = actionPreview[i];
            actions.push({
                type: 'replace',
                mode: exact ? 'regex' : 'literal',
                from: exact ? ('^' + escapeRegex(ap.from) + '$') : ap.from,
                to: ap.to
            });
        }
        return { files: files, scope: 'dataList[*]', targets: fields, where: where, actions: actions };
    }

    async function generateAllSmart() {
        const groups = state.smartGenGroups || [];
        if (!groups.length) { showToast('没有可应用的组', 'error'); return; }
        let count = 0;
        for (let i = 0; i < groups.length; i++) {
            await applySmartGroup(groups[i]);
            count++;
        }
        showToast('已应用 ' + count + ' 个组的推荐规则', 'success');
    }

    async function reparseSmartChanges() {
        if (!state.smartGenOverlay) return;
        const ta = state.smartGenOverlay.querySelector('#re-smart-changes-input');
        if (!ta) return;
        let arr = [];
        try {
            arr = JSON.parse(ta.value || '[]');
            if (!Array.isArray(arr)) arr = [];
        } catch (e) {
            showToast('JSON 解析失败: ' + e.message, 'error');
            return;
        }
        state.smartChanges = arr;
        let groups = null;
        const api = getApi();
        if (api && api.analyze_changes) {
            try { const res = await api.analyze_changes(arr); if (res && Array.isArray(res.groups)) groups = res.groups; }
            catch (e) { groups = null; }
        }
        if (!groups) groups = analyzeChangesLocally(arr);
        closeSmartGenDialog();
        showSmartGenDialog(groups);
    }

    function closeSmartGenDialog() {
        if (state.smartGenOverlay && state.smartGenOverlay.parentNode) {
            state.smartGenOverlay.parentNode.removeChild(state.smartGenOverlay);
        }
        state.smartGenOverlay = null;
        state.smartGenGroups = null;
    }

    function closeAnySmartGenDialog() {
        // Unified close for V1/V2/V3 dialogs
        if (state.smartGenOverlay && state.smartGenOverlay.parentNode) {
            state.smartGenOverlay.parentNode.removeChild(state.smartGenOverlay);
        }
        state.smartGenOverlay = null;
        state.smartGenGroups = null;
        state.smartGenV2Bias = 'conservative';
    }

    // ═══════════════════════════════════════════════════════
    //  V2 偏向式智能生成（保守/进取）+ 交集逻辑
    // ═══════════════════════════════════════════════════════

    function collectChangesForSmartGen() {
        var changes = [];
        state.openFiles.forEach(function (ts) {
            if (ts.editStatus === 'staged' || ts.editStatus === 'applied') {
                var parsed;
                try { parsed = JSON.parse(ts.editor.state.doc.toString()); } catch (e) { return; }
                if (!parsed || !parsed.dataList) return;
                var baseline = ts.baselineParsed;
                if (!baseline) return;
                var diffs = diffJson(baseline, parsed, '');
                var extracted = extractChangesFromDiff(diffs, ts.path, baseline);
                for (var i = 0; i < extracted.length; i++) {
                    changes.push(extracted[i]);
                }
            }
        });
        return changes;
    }

    function getChangeCounts() {
        var staged = 0;
        var applied = 0;
        state.openFiles.forEach(function (ts) {
            if (ts.editStatus === 'staged') staged++;
            else if (ts.editStatus === 'applied') applied++;
        });
        return { staged: staged, applied: applied };
    }

    async function openSmartGenerationV2() {
        var changes = collectChangesForSmartGen();
        var counts = getChangeCounts();
        closeSmartGenDialogV2();

        var overlay = document.createElement('div');
        overlay.className = 're-overlay';
        state.smartGenOverlay = overlay;
        state.smartGenGroups = null;

        overlay.innerHTML =
            '<div class="re-smart-gen-dialog">' +
            '<div class="re-smart-gen-header"><h3><i class="fas fa-brain"></i> 智能生成规则集 (V2)</h3>' +
            '<button class="re-btn re-btn-sm" id="re-v2-close-btn">✕</button></div>' +
            '<div class="re-smart-gen-body">' +
            '<div class="re-bias-selector">' +
            '<label class="re-bias-option"><input type="radio" name="re-bias-mode" value="conservative" checked>' +
            '<span class="re-bias-label">保守模式</span><span class="re-bias-desc">— 仅对 3+ 文件中共有的变更生成规则</span></label>' +
            '<label class="re-bias-option"><input type="radio" name="re-bias-mode" value="aggressive">' +
            '<span class="re-bias-label">进取模式</span><span class="re-bias-desc">— 对所有变更生成，建议合并低出现项</span></label>' +
            '</div>' +
            '<div class="re-bias-summary">共收集到 ' + changes.length + ' 处变更（暂存: ' + counts.staged + ' 文件, 已应用: ' + counts.applied + ' 文件）</div>' +
            '<div id="re-bias-results" class="re-bias-results"></div>' +
            '<div class="re-bias-footer">' +
            '<button class="re-btn re-btn-primary" id="re-bias-analyze-btn">开始分析</button>' +
            '<button class="re-btn" id="re-v2-close-footer-btn">关闭</button>' +
            '</div>' +
            '</div>' +
            '</div>';

        document.body.appendChild(overlay);

        var closeBtn = overlay.querySelector('#re-v2-close-btn');
        if (closeBtn) closeBtn.addEventListener('click', closeSmartGenDialogV2);
        var closeFooterBtn = overlay.querySelector('#re-v2-close-footer-btn');
        if (closeFooterBtn) closeFooterBtn.addEventListener('click', closeSmartGenDialogV2);
        overlay.addEventListener('click', function (e) { if (e.target === overlay) closeSmartGenDialogV2(); });

        var analyzeBtn = overlay.querySelector('#re-bias-analyze-btn');
        if (analyzeBtn) analyzeBtn.addEventListener('click', loadBiasResults);
    }

    function closeSmartGenDialogV2() {
        if (state.smartGenOverlay && state.smartGenOverlay.parentNode) {
            state.smartGenOverlay.parentNode.removeChild(state.smartGenOverlay);
        }
        state.smartGenOverlay = null;
        state.smartGenGroups = null;
        state.smartGenV2Bias = 'conservative';
    }

    async function loadBiasResults() {
        var overlay = state.smartGenOverlay;
        if (!overlay) return;

        var radios = overlay.querySelectorAll('input[name="re-bias-mode"]');
        var mode = 'conservative';
        for (var i = 0; i < radios.length; i++) {
            if (radios[i].checked) { mode = radios[i].value; break; }
        }
        state.smartGenV2Bias = mode;

        var changes = collectChangesForSmartGen();
        if (!changes.length) {
            showToast('没有收集到变更', 'error');
            return;
        }

        var result = null;
        var api = getApi();
        if (api && api.analyze_changes_v2) {
            try {
                var res = await api.analyze_changes_v2(changes, mode);
                if (res && Array.isArray(res.groups)) result = res;
            } catch (e) {
                console.warn('[rule-editor] analyze_changes_v2 failed', e);
                result = null;
            }
        }
        if (!result) result = analyzeChangesLocallyV2(changes, mode);

        state.smartGenGroups = result.groups || [];
        renderBiasResultSummary(result);
    }

    function renderBiasResultSummary(result) {
        var container = document.getElementById('re-bias-results');
        if (!container) return;

        var groups = (result && result.groups) || [];
        var mergeSuggestions = (result && result.merge_suggestions) || [];

        if (!groups.length) {
            container.innerHTML = '<div class="re-empty-state"><i class="fas fa-info-circle"></i> 未生成任何规则组</div>';
            return;
        }

        var html = '';
        for (var i = 0; i < groups.length; i++) {
            var g = groups[i];
            var score = g.score || {};
            var priority = score.priority || 0;

            var files = g.l1_options && g.l1_options.exact_files ? g.l1_options.exact_files : [];
            var categories = g.l1_options && g.l1_options.categories ? g.l1_options.categories : [];
            var intersectionHtml = '';
            if (files.length > 0) {
                intersectionHtml += '<div class="re-group-intersection"><strong>交集文件:</strong> ' +
                    escapeHtml(files.slice(0, 5).join(', ')) +
                    (files.length > 5 ? ' (+' + (files.length - 5) + ')' : '') + '</div>';
            }
            if (categories.length > 0) {
                var catNames = [];
                for (var k = 0; k < categories.length; k++) catNames.push(categories[k].name);
                intersectionHtml += '<div class="re-group-intersection"><strong>交集分类:</strong> ' +
                    escapeHtml(catNames.join(', ')) + '</div>';
            }

            var mergeBadge = (g.merge_suggestion) ? '<span class="re-bias-merge-badge">建议合并</span>' : '';

            html += '<div class="re-bias-group-card" data-group-idx="' + i + '">' +
                '<div class="re-group-header">' +
                '<h4>组 #' + (i + 1) + ' — ' + priority + '分 ' + mergeBadge + '</h4>' +
                '<div class="re-group-meta">文件: ' + (g.file_count || files.length) +
                ' | 条目: ' + (g.item_count || 0) +
                ' | 出现: ' + (g.occurrence_count || 0) + '</div>' +
                '</div>';
            if (g.summary) html += '<div style="margin-bottom:6px;font-size:13px;">💡 ' + escapeHtml(g.summary) + '</div>';
            if (g.action_preview && g.action_preview.length) {
                html += '<div class="re-group-patterns">';
                for (var j = 0; j < g.action_preview.length; j++) {
                    var ap = g.action_preview[j];
                    html += '<span class="re-pattern-pair">' + escapeHtml(String(ap.from || '')) +
                        ' → ' + escapeHtml(String(ap.to || '')) + '</span>';
                }
                html += '</div>';
            }
            html += intersectionHtml;
            html += renderSimplifiedTierControls(g, i);
            html += '<div class="re-bias-actions">' +
                '<button class="re-btn re-btn-sm re-bias-preview-btn" data-idx="' + i + '">📋 预览JSON</button>' +
                '<button class="re-btn re-btn-sm re-btn-success re-bias-apply-btn" data-idx="' + i + '">✅ 生成此规则</button>' +
                '</div>' +
                '<pre class="re-bias-preview-out" style="display:none;margin-top:6px;font-size:12px;background:var(--color-bg-primary);padding:8px;border-radius:6px;overflow:auto;max-height:200px;white-space:pre-wrap;"></pre>' +
                '</div>';
        }

        if (mergeSuggestions.length) {
            html += '<div style="margin-top:10px;padding:8px 12px;background:rgba(243,156,18,0.06);border-radius:6px;">';
            html += '<strong style="font-size:12px;">合并建议 (' + mergeSuggestions.length + ')</strong>';
            for (var m = 0; m < mergeSuggestions.length; m++) {
                html += '<div style="font-size:11px;margin:4px 0;color:var(--color-text-secondary);">' +
                    escapeHtml(String(mergeSuggestions[m])) + '</div>';
            }
            html += '</div>';
        }

        container.innerHTML = html;

        var previewBtns = container.querySelectorAll('.re-bias-preview-btn');
        for (var pi = 0; pi < previewBtns.length; pi++) {
            previewBtns[pi].addEventListener('click', (function (idx) {
                return function () { previewBiasResult(groups[idx]); };
            })(parseInt(previewBtns[pi].dataset.idx, 10)));
        }
        var applyBtns = container.querySelectorAll('.re-bias-apply-btn');
        for (var ai = 0; ai < applyBtns.length; ai++) {
            applyBtns[ai].addEventListener('click', (function (idx) {
                return function () { applyBiasResult(groups[idx]); };
            })(parseInt(applyBtns[ai].dataset.idx, 10)));
        }
    }

    function previewBiasResult(group) {
        var idx = group && state.smartGenGroups ? state.smartGenGroups.indexOf(group) : -1;
        if (idx < 0 || !state.smartGenOverlay) return;
        var card = state.smartGenOverlay.querySelector('.re-bias-group-card[data-group-idx="' + idx + '"]');
        if (!card) return;
        var sel = readSmartSelections(card, idx);
        var rules = buildSmartGroupRules(group, sel);
        var out = card.querySelector('.re-bias-preview-out');
        if (!out) return;
        out.textContent = JSON.stringify(rules, null, 2);
        out.style.display = '';
    }

    async function applyBiasResult(group) {
        if (!group) return;
        var idx = state.smartGenGroups ? state.smartGenGroups.indexOf(group) : -1;
        if (idx < 0) { showToast('找不到该组', 'error'); return; }
        if (!state.smartGenOverlay) return;
        var card = state.smartGenOverlay.querySelector('.re-bias-group-card[data-group-idx="' + idx + '"]');
        if (!card) { showToast('找不到组的 DOM', 'error'); return; }
        var sel = readSmartSelections(card, idx);
        var rules = buildSmartGroupRules(group, sel);
        if (!rules || !rules.length) { showToast('未能从该组生成规则', 'error'); return; }
        if (!state.currentRuleset) { showToast('请先选择或新建一个规则集', 'error'); return; }
        if (!Array.isArray(state.currentRuleset.rules)) state.currentRuleset.rules = [];
        for (var i = 0; i < rules.length; i++) state.currentRuleset.rules.push(rules[i]);
        state._rulesetDirty = true;
        refreshRulesetUI();
        try {
            await persistCurrentRuleset();
            showToast('已添加 ' + rules.length + ' 条规则', 'success');
        } catch (e) {
            showToast('保存失败: ' + (e && e.message ? e.message : e), 'error');
        }
    }

    function analyzeChangesLocallyV2(changes, bias) {
        if (!changes || !changes.length) return { groups: [], merge_suggestions: [] };

        var buckets = {};
        var order = [];
        for (var i = 0; i < changes.length; i++) {
            var c = changes[i];
            var key = String(c.old_val) + '::' + String(c.new_val);
            if (!buckets[key]) { buckets[key] = []; order.push(key); }
            buckets[key].push(c);
        }

        var groups = [];
        var mergeSuggestions = [];

        for (var oi = 0; oi < order.length; oi++) {
            var items = buckets[order[oi]];
            var first = items[0];
            var files = uniqArr(items.map(function (c) { return c.file; }));
            var itemIds = uniqArr(items.map(function (c) { return c.item_id; }).filter(function (v) { return v != null && v !== ''; }));
            var fieldPaths = uniqArr(items.map(function (c) { return c.field_path; }));
            var cats = {};
            for (var j = 0; j < files.length; j++) {
                var cc = classifyPath(files[j]).category;
                cats[cc] = (cats[cc] || 0) + 1;
            }
            var catList = Object.keys(cats).map(function (k) { return { name: k, count: cats[k], selected: true }; });

            if (bias === 'conservative') {
                if (files.length < 3) continue;
            }

            var priority = Math.min(80, 30 + items.length * 5);
            var mergeSuggestion = false;
            if (bias === 'aggressive' && files.length < 3) {
                mergeSuggestion = true;
                mergeSuggestions.push('组 "' + first.old_val + ' → ' + first.new_val + '" 出现于 ' + files.length + ' 个文件，建议合并到其他组');
            }

            groups.push({
                change_type: 'PURE_REPLACE',
                summary: '检测到 ' + items.length + ' 处相同替换 (' + first.old_val + ' → ' + first.new_val + ')',
                suggestions: [],
                action_preview: [{ from: first.old_val, to: first.new_val }],
                file_count: files.length,
                item_count: itemIds.length,
                occurrence_count: items.length,
                l1_options: { suggested: catList.length <= 2 ? 'category' : 'multi_category', categories: catList, exact_files: files },
                l2_options: { suggested: itemIds.length ? 'id' : 'full_text', item_ids: itemIds },
                l3_options: { suggested: fieldPaths.length === 1 ? 'restricted' : 'all_text', fields: fieldPaths },
                l4_options: { suggested: 'exact' },
                score: { priority: priority },
                merge_suggestion: mergeSuggestion
            });
        }

        groups.sort(function (a, b) { return (b.score.priority || 0) - (a.score.priority || 0); });

        return { groups: groups, merge_suggestions: mergeSuggestions };
    }

    // ═══════════════════════════════════════════════════════
    //  V3 统一智能规则生成 — 无模式选择 + 自动合并 + 即时展示
    // ═══════════════════════════════════════════════════════

    async function analyzeChangesV3(changes) {
        var result = null;
        var api = getApi();
        if (api && api.analyze_changes_v3) {
            try {
                var res = await api.analyze_changes_v3(changes);
                if (res && Array.isArray(res.groups)) result = res;
            } catch (e) {
                console.warn('[rule-editor] analyze_changes_v3 failed, using local fallback', e);
            }
        }
        if (!result) {
            result = analyzeChangesLocallyV3(changes);
        }
        return result;
    }

    function analyzeChangesLocallyV3(changes) {
        if (!changes || !changes.length) return {
            groups: [], merge_suggestions: [],
            stats: { change_count: 0, group_count: 0, file_count: 0, category_count: 0 },
            merge_candidates: []
        };

        // 按 (old_val, new_val, field_path) 合并 key 分桶
        var buckets = {};
        var order = [];
        for (var i = 0; i < changes.length; i++) {
            var c = changes[i];
            var key = String(c.old_val) + '::' + String(c.new_val) + '::' + String(c.field_path);
            if (!buckets[key]) { buckets[key] = []; order.push(key); }
            buckets[key].push(c);
        }

        var allFiles = {};
        var allCats = {};
        var groups = [];

        for (var oi = 0; oi < order.length; oi++) {
            var items = buckets[order[oi]];
            var first = items[0];
            var files = uniqArr(items.map(function (c) { return c.file; }));
            var itemIds = uniqArr(items.map(function (c) { return c.item_id; }).filter(function (v) { return v != null && v !== ''; }));
            var fieldPaths = uniqArr(items.map(function (c) { return c.field_path; }));

            for (var fi = 0; fi < files.length; fi++) {
                allFiles[files[fi]] = true;
                var cc = classifyPath(files[fi]).category;
                allCats[cc] = true;
            }

            var cats = {};
            for (var fj = 0; fj < files.length; fj++) {
                var ccc = classifyPath(files[fj]).category;
                cats[ccc] = (cats[ccc] || 0) + 1;
            }
            var catList = Object.keys(cats).map(function (k) { return { name: k, count: cats[k], selected: true }; });

            var priority = Math.min(80, 30 + items.length * 5);

            // 构建 merged_from
            var mergedFrom = [];
            for (var mf = 0; mf < files.length; mf++) {
                var fname = files[mf];
                var fcount = 0;
                for (var mc = 0; mc < items.length; mc++) {
                    if (items[mc].file === fname) fcount++;
                }
                mergedFrom.push({ file: fname, count: fcount });
            }

            var totalItemCount = itemIds.length || items.length;
            groups.push({
                change_type: 'PURE_REPLACE',
                summary: '检测到 ' + items.length + ' 处相同替换 (' + first.old_val + ' → ' + first.new_val + ')',
                suggestions: [],
                action_preview: [{ from: first.old_val, to: first.new_val }],
                file_count: files.length,
                item_count: itemIds.length,
                occurrence_count: items.length,
                l1_options: {
                    suggested: 'exact',
                    categories: catList,
                    exact_files: files,
                    available: [
                        { level: 'exact', label: '仅涉及文件', count: files.length },
                        { level: 'category', label: '同分类文件', count: Object.keys(cats).length > 0 ? Object.values(cats).reduce(function(a,b){return a+b;},0) : files.length },
                        { level: 'all', label: '所有文件', count: Object.keys(cats).length > 0 ? Object.values(cats).reduce(function(a,b){return a+b;},0) : files.length }
                    ]
                },
                l2_options: {
                    suggested: itemIds.length ? 'id' : 'full_text',
                    item_ids: itemIds,
                    available: [
                        { level: 'id', label: '按ID定位', count: itemIds.length },
                        { level: 'full_text', label: '全文匹配', count: totalItemCount }
                    ]
                },
                l3_options: {
                    suggested: fieldPaths.length === 1 ? 'restricted' : 'all_text',
                    fields: fieldPaths,
                    available: [
                        { level: 'restricted', label: '限定字段', count: fieldPaths.length },
                        { level: 'all_text', label: '全部字段', count: fieldPaths.length }
                    ]
                },
                l4_options: {
                    suggested: 'exact',
                    available: [
                        { level: 'exact', label: '完整匹配' },
                        { level: 'none', label: '子串匹配' }
                    ]
                },
                score: { priority: priority },
                merged_from: mergedFrom,
                is_merged: files.length > 1,
                _raw_changes: items.map(function (c) { return { old_val: c.old_val, new_val: c.new_val }; }),
                merge_candidates: []
            });
        }

        // 语义化合并候选检测（规则推广验证）
        var candidates = detectMergeCandidatesLocally(groups);

        groups.sort(function (a, b) { return (b.score.priority || 0) - (a.score.priority || 0); });

        return {
            groups: groups,
            merge_suggestions: [],
            stats: {
                change_count: changes.length,
                group_count: groups.length,
                file_count: Object.keys(allFiles).length,
                category_count: Object.keys(allCats).length
            },
            merge_candidates: candidates
        };
    }

    async function openSmartGenerationV3() {
        // Feature 3: 打开智能生成前自动保存规则集
        await _autoPersistRuleset();
        var changes = collectChangesForSmartGen();
        var counts = getChangeCounts();
        closeSmartGenDialogV3();

        // 创建 overlay
        var overlay = document.createElement('div');
        overlay.className = 're-overlay';
        state.smartGenOverlay = overlay;
        state.smartGenGroups = null;
        state._v3SkipAutoMerge = false;

        // 渲染加载状态
        overlay.innerHTML =
            '<div class="re-smart-gen-dialog">' +
            '<div class="re-smart-gen-header"><h3><i class="fas fa-brain"></i> 智能生成规则集</h3>' +
            '<button class="re-btn re-btn-sm" id="re-v3-close-btn">✕</button></div>' +
            '<div class="re-smart-gen-body" id="re-v3-body">' +
            '<div class="re-empty-state" style="padding:40px;">' +
            '<i class="fas fa-spinner fa-pulse"></i>' +
            '正在分析 ' + changes.length + ' 处变更...</div>' +
            '</div>' +
            '</div>';

        document.body.appendChild(overlay);

        var closeBtn = overlay.querySelector('#re-v3-close-btn');
        if (closeBtn) closeBtn.addEventListener('click', closeSmartGenDialogV3);
        overlay.addEventListener('click', function (e) { if (e.target === overlay) closeSmartGenDialogV3(); });

        // 立即分析
        var result = await analyzeChangesV3(changes);
        state.smartGenGroups = result.groups || [];

        // 渲染结果
        renderV3Results(result, counts);
    }

    function closeSmartGenDialogV3() {
        if (state.smartGenOverlay && state.smartGenOverlay.parentNode) {
            state.smartGenOverlay.parentNode.removeChild(state.smartGenOverlay);
        }
        state.smartGenOverlay = null;
        state.smartGenGroups = null;
    }

    function renderV3Results(result, counts) {
        var overlay = state.smartGenOverlay;
        if (!overlay) return;

        var body = overlay.querySelector('#re-v3-body');
        if (!body) return;

        var groups = result.groups || [];
        var stats = result.stats || {};
        var mergeCandidates = result.merge_candidates || [];

        if (!groups.length) {
            body.innerHTML = '<div class="re-empty-state"><i class="fas fa-info-circle"></i>' +
                '未检测到可生成规则的变更。<br><small>请先在文件中修改并保存，然后点击"比较变更"后再试。</small></div>';
            return;
        }

        // 自动合并高置信度候选
        var autoMergeResult = state._v3SkipAutoMerge
            ? { groups: groups, remaining: mergeCandidates }
            : _autoMergeCandidates(groups, mergeCandidates);
        groups = autoMergeResult.groups;
        mergeCandidates = autoMergeResult.remaining;
        // 回写状态，保证 preview/apply/split 按渲染后的组索引查找
        state.smartGenGroups = groups;
        var autoMergedCount = 0;
        for (var ai = 0; ai < groups.length; ai++) {
            if (groups[ai]._auto_merged) autoMergedCount++;
        }

        // 保存 mergeCandidates 供拆分时使用
        state._lastMergeCandidates = mergeCandidates;

        // 顶部摘要栏
        var html = '<div class="re-v3-summary-bar">' +
            '<span>📊 ' + (stats.change_count || 0) + ' 处变更 → ' + groups.length + ' 个规则建议</span>' +
            '<span class="re-v3-stat">' + (stats.file_count || 0) + ' 个文件</span>' +
            '<span class="re-v3-stat">' + (stats.category_count || 0) + ' 个分类</span>';
        if (autoMergedCount) {
            html += '<span class="re-v3-stat re-v3-stat-auto-merge">🔄 已自动合并 ' + autoMergedCount + ' 组</span>';
        } else if (mergeCandidates.length) {
            html += '<span class="re-v3-stat re-v3-stat-merge">🔄 ' + mergeCandidates.length + ' 组可合并</span>';
        }
        // Feature 3: 全部合并到全局 + Feature 4: 全选/取消全选
        html += '<span class="re-v3-summary-actions">' +
            '<button class="re-btn re-btn-xs" id="re-v3-select-all-btn" title="全选所有规则">☑ 全选</button>' +
            '<button class="re-btn re-btn-xs" id="re-v3-deselect-all-btn" title="取消全选">☐ 取消</button>' +
            '<button class="re-btn re-btn-xs" id="re-v3-expand-all-btn" title="将所有规则的 L1 文件范围提升至「全部文件」">🌐 全部展开至全局</button>' +
            '</span>' +
            '</div>';

        // 检查 merge candidate 关系，用于在卡片间插入连接器
        var mergeMap = {};  // idx -> [mergeInfo, ...]
        if (mergeCandidates.length) {
            for (var mi = 0; mi < mergeCandidates.length; mi++) {
                var mc = mergeCandidates[mi];
                if (!mergeMap[mc.idx1]) mergeMap[mc.idx1] = [];
                mergeMap[mc.idx1].push(mc);
            }
        }

        // 渲染组卡片（按结果顺序渲染，在可合并组之间插入连接器）
        var rendered = {};
        for (var i = 0; i < groups.length; i++) {
            html += renderV3GroupCard(groups[i], i);

            // 如果有指向后续组的 merge，插入连接器提示
            if (mergeMap[i]) {
                for (var mj = 0; mj < mergeMap[i].length; mj++) {
                    var mc2 = mergeMap[i][mj];
                    if (mc2.idx2 > i && !rendered[mc2.idx1 + '_' + mc2.idx2]) {
                        rendered[mc2.idx1 + '_' + mc2.idx2] = true;
                        html += renderMergeConnector(mc2.idx1, mc2.idx2, mc2.score, mc2.reason);
                    }
                }
            }
        }

        // 底部操作栏
        html += '<div class="re-v3-footer">' +
            '<button class="re-btn re-btn-accent" id="re-v3-apply-all-btn">✅ 全部应用 (' + groups.length + '条)</button>' +
            '<button class="re-btn" id="re-v3-close-footer-btn">关闭</button>' +
            '</div>';

        body.innerHTML = html;

        // 绑定事件
        var closeFooterBtn = overlay.querySelector('#re-v3-close-footer-btn');
        if (closeFooterBtn) closeFooterBtn.addEventListener('click', closeSmartGenDialogV3);

        var applyAllBtn = overlay.querySelector('#re-v3-apply-all-btn');
        if (applyAllBtn) applyAllBtn.addEventListener('click', applyAllV3WithDedup);

        // 辅助：更新「全部应用」按钮的计数
        function _updateApplyAllCount() {
            var btn = overlay.querySelector('#re-v3-apply-all-btn');
            if (!btn) return;
            var toggles = body.querySelectorAll('.re-v3-group-toggle');
            var checked = 0;
            for (var t = 0; t < toggles.length; t++) {
                if (toggles[t].checked) checked++;
            }
            btn.textContent = '✅ 全部应用 (' + checked + '条)';
        }

        // Feature 4: 全选 / 取消全选
        var selectAllBtn = overlay.querySelector('#re-v3-select-all-btn');
        if (selectAllBtn) {
            selectAllBtn.addEventListener('click', function () {
                var toggles = body.querySelectorAll('.re-v3-group-toggle');
                for (var t = 0; t < toggles.length; t++) toggles[t].checked = true;
                _updateApplyAllCount();
            });
        }
        var deselectAllBtn = overlay.querySelector('#re-v3-deselect-all-btn');
        if (deselectAllBtn) {
            deselectAllBtn.addEventListener('click', function () {
                var toggles = body.querySelectorAll('.re-v3-group-toggle');
                for (var t = 0; t < toggles.length; t++) toggles[t].checked = false;
                _updateApplyAllCount();
            });
        }

        // Feature 3: 全部展开至全局
        var expandAllBtn = overlay.querySelector('#re-v3-expand-all-btn');
        if (expandAllBtn) {
            expandAllBtn.addEventListener('click', function () {
                for (var gi = 0; gi < groups.length; gi++) {
                    if (groups[gi].l1_options) groups[gi].l1_options.suggested = 'all';
                    var card = body.querySelector('.re-v3-group-card[data-group-idx="' + gi + '"]');
                    if (card) {
                        var radio = card.querySelector('input[name="l1-' + gi + '"][value="all"]');
                        if (radio) radio.checked = true;
                        // 更新推广按钮
                        updatePromoteButtons(card, gi);
                    }
                }
                showToast('已将所有组作用域设为全局', 'success');
            });
        }

        var previewBtns = body.querySelectorAll('.re-v3-preview-btn');
        for (var pi = 0; pi < previewBtns.length; pi++) {
            previewBtns[pi].addEventListener('click', (function (idx) {
                return function () { previewV3Group(groups[idx]); };
            })(parseInt(previewBtns[pi].dataset.idx, 10)));
        }

        var applyBtns = body.querySelectorAll('.re-v3-apply-btn');
        for (var ai = 0; ai < applyBtns.length; ai++) {
            applyBtns[ai].addEventListener('click', (function (idx) {
                return function () { applyV3Group(groups[idx]); };
            })(parseInt(applyBtns[ai].dataset.idx, 10)));
        }

        var expandToggles = body.querySelectorAll('.re-v3-group-header');
        for (var ei = 0; ei < expandToggles.length; ei++) {
            expandToggles[ei].addEventListener('click', function (evt) {
                // 不拦截复选框的点击
                if (evt.target.tagName === 'INPUT') return;
                var card = this.closest('.re-v3-group-card');
                if (!card) return;
                var controls = card.querySelector('.re-v3-tier-controls');
                var toggle = this.querySelector('.re-v3-expand-toggle');
                if (controls) controls.classList.toggle('collapsed');
                if (toggle) toggle.classList.toggle('expanded');
            });
        }

        // Feature 4: 组切换复选框 — 更新「全部应用」计数
        var toggleCbs = body.querySelectorAll('.re-v3-group-toggle');
        for (var tci = 0; tci < toggleCbs.length; tci++) {
            toggleCbs[tci].addEventListener('change', _updateApplyAllCount);
        }

        var mergeBtns = body.querySelectorAll('.re-v3-merge-btn');
        for (var mbi = 0; mbi < mergeBtns.length; mbi++) {
            mergeBtns[mbi].addEventListener('click', (function (g1Idx, g2Idx) {
                return function () { mergeAndApplyV3(g1Idx, g2Idx); };
            })(parseInt(mergeBtns[mbi].dataset.g1 || '0', 10),
               parseInt(mergeBtns[mbi].dataset.g2 || '0', 10)));
        }

        var splitBtns = body.querySelectorAll('.re-v3-split-btn');
        for (var si = 0; si < splitBtns.length; si++) {
            splitBtns[si].addEventListener('click', (function (idx) {
                return function (e) {
                    e.stopPropagation();
                    splitAutoMergedGroup(idx);
                };
            })(parseInt(splitBtns[si].dataset.idx, 10)));
        }

        var promoteBtns = body.querySelectorAll('.re-v3-promote-btn');
        for (var pmi = 0; pmi < promoteBtns.length; pmi++) {
            promoteBtns[pmi].addEventListener('click', (function (btn) {
                return function (e) {
                    e.stopPropagation();
                    var tier = btn.dataset.tier;
                    var level = btn.dataset.level;
                    var idx = parseInt(btn.dataset.idx, 10);
                    promoteConstraint(idx, tier, level);
                };
            })(promoteBtns[pmi]));
        }
    }

    function renderV3GroupCard(group, idx) {
        var score = group.score || {};
        var priority = score.priority || 0;
        var tier, tierLabel, badgeCls;
        if (priority >= 70) { tier = '🟢'; tierLabel = '推荐'; badgeCls = 're-score-green'; }
        else if (priority >= 40) { tier = '🟡'; tierLabel = '可选'; badgeCls = 're-score-yellow'; }
        else { tier = '🔴'; tierLabel = '需审查'; badgeCls = 're-score-red'; }

        // 高分组默认收起 L1-L4
        var collapsedClass = (priority >= 70) ? ' collapsed' : '';

        var html = '<div class="re-v3-group-card" data-group-idx="' + idx + '">';
        html += '<div class="re-v3-group-header">' +
            '<input type="checkbox" class="re-v3-group-toggle" data-idx="' + idx + '" checked title="包含此规则到「全部应用」">' +
            '<h4><span>' + tier + '</span> 规则 #' + (idx + 1) +
            ' · <span class="re-score-badge ' + badgeCls + '">' + priority + '分</span>';
        if (group.is_merged) {
            html += ' <span class="re-v3-merged-badge">已合并 ' + (group.file_count || 0) + ' 文件</span>';
        }
        if (group._auto_merged) {
            html += ' <span class="re-v3-auto-merged-badge">🔄 已自动合并 ' +
                (group._split_origin ? group._split_origin.length : 0) + ' 组</span>';
        }
        html += '</h4>' +
            '<span class="re-v3-expand-toggle' + (priority >= 70 ? '' : ' expanded') + '">▼</span>' +
            '</div>';

        // 摘要
        if (group.summary) {
            html += '<div class="re-v3-summary">💡 ' + escapeHtml(group.summary) + '</div>';
        }

        // Action preview chips
        if (group.action_preview && group.action_preview.length) {
            html += '<div class="re-v3-action-patterns">';
            for (var i = 0; i < group.action_preview.length; i++) {
                var ap = group.action_preview[i];
                html += '<span class="re-v3-pattern-chip">' +
                    escapeHtml(String(ap.from || '')) + ' → ' + escapeHtml(String(ap.to || '')) + '</span>';
            }
            html += '</div>';
        }

        // 作用域摘要
        var files = group.l1_options && group.l1_options.exact_files ? group.l1_options.exact_files : [];
        var categories = group.l1_options && group.l1_options.categories ? group.l1_options.categories : [];
        html += '<div class="re-v3-scope-summary">📁 ';
        if (categories.length) {
            var catNames = [];
            for (var ci = 0; ci < categories.length; ci++) catNames.push(categories[ci].name + '(' + categories[ci].count + ')');
            html += escapeHtml(catNames.join(', '));
        }
        if (files.length <= 5 && files.length > 0) {
            html += ' — ' + escapeHtml(files.join(', '));
        }
        html += '</div>';

        // 合并来源展示
        if (group.merged_from && group.merged_from.length > 1) {
            html += '<div class="re-v3-merged-from">';
            html += '<span class="re-v3-merged-label">🔗 合并来源: </span>';
            var mfParts = [];
            for (var mi = 0; mi < Math.min(group.merged_from.length, 5); mi++) {
                var mf = group.merged_from[mi];
                var shortName = mf.file.length > 35 ? '...' + mf.file.slice(-32) : mf.file;
                mfParts.push(escapeHtml(shortName) + '(' + mf.count + ')');
            }
            html += mfParts.join(', ');
            if (group.merged_from.length > 5) {
                html += ' +' + (group.merged_from.length - 5) + ' 更多';
            }
            html += '</div>';
        }

        // 简化的 L1-L4 控件
        html += renderSimplifiedTierControls(group, idx, collapsedClass);

        // 操作按钮
        html += '<div class="re-v3-actions-row">' +
            '<button class="re-btn re-btn-sm re-v3-preview-btn" data-idx="' + idx + '">📋 预览JSON</button>' +
            '<button class="re-btn re-btn-sm re-btn-success re-v3-apply-btn" data-idx="' + idx + '">✅ 生成此规则</button>';
        if (group._auto_merged) {
            html += '<button class="re-btn re-btn-xs re-v3-split-btn" data-idx="' + idx + '" title="拆分为原始组">↩ 拆分</button>';
        }
        html += '</div>';

        // 预览输出区域
        html += '<pre class="re-v3-preview-out" style="display:none;margin-top:6px;font-size:12px;background:var(--color-bg-primary);padding:8px;border-radius:6px;overflow:auto;max-height:200px;white-space:pre-wrap;"></pre>';

        html += '</div>';
        return html;
    }

    function renderSimplifiedTierControls(group, idx, collapsedClass) {
        var l1 = group.l1_options || {};
        var l2 = group.l2_options || {};
        var l3 = group.l3_options || {};
        var l4 = group.l4_options || {};

        var html = '<div class="re-v3-tier-controls' + (collapsedClass || '') + '">';

        // L1: 文件范围 — 紧凑 radio + 分类复选框
        var l1Default = l1.suggested || 'exact';
        // 确保 valid 值
        if (['all', 'category', 'exact', 'custom'].indexOf(l1Default) === -1) l1Default = 'exact';
        html += '<div class="re-v3-tier-row">' +
            '<span class="re-v3-tier-label">L1 文件范围</span>';
        var l1Opts = [
            { val: 'category', text: '按分类' },
            { val: 'all', text: '全部文件' },
            { val: 'exact', text: '精确文件' },
            { val: 'custom', text: '自定义' }
        ];
        for (var oi = 0; oi < l1Opts.length; oi++) {
            var checked = (l1Opts[oi].val === l1Default) ? 'checked' : '';
            html += '<label class="re-tier-option"><input type="radio" class="re-tier-radio" name="l1-' + idx +
                '" value="' + l1Opts[oi].val + '" ' + checked + '>' +
                '<span class="re-tier-text">' + l1Opts[oi].text + '</span></label>';
        }
        // L1 推广按钮
        var l1Avail = l1.available || [];
        if (l1Avail.length > 1) {
            for (var l1ai = 0; l1ai < l1Avail.length - 1; l1ai++) {
                if (l1Avail[l1ai].level === l1Default) {
                    var nextL1 = l1Avail[l1ai + 1];
                    html += '<button class="re-v3-promote-btn" data-tier="l1" data-level="' + nextL1.level +
                        '" data-idx="' + idx + '" title="放宽文件范围">▸ ' + escapeHtml(nextL1.label) +
                        ' (' + (nextL1.count || '?') + ')</button>';
                    break;
                }
            }
        }
        html += '</div>';
        if (l1.categories && l1.categories.length) {
            html += '<div class="re-v3-tier-row" style="margin-left:74px;">';
            for (var ci = 0; ci < l1.categories.length; ci++) {
                var c = l1.categories[ci];
                var ck = c.selected !== false ? 'checked' : '';
                html += '<label class="re-checkbox"><input type="checkbox" class="re-l1-cat" value="' +
                    escapeAttr(c.name) + '" ' + ck + '> ' + escapeHtml(c.name) + ' (' + c.count + ')</label>';
            }
            html += '</div>';
        }
        html += '<div class="re-v3-tier-row" style="margin-left:74px;">' +
            '<input type="text" class="re-l1-custom re-v3-custom-input" placeholder="自定义正则" style="width:60%;">' +
            '</div>';

        // L2: 条目定位
        var useId = l2.suggested === 'id' && l2.item_ids && l2.item_ids.length;
        var l2Default = useId ? 'id' : 'full_text';
        html += '<div class="re-v3-tier-row">' +
            '<span class="re-v3-tier-label">L2 条目定位</span>' +
            '<label class="re-tier-option"><input type="radio" class="re-tier-radio" name="l2-' + idx +
            '" value="full_text"' + (useId ? '' : ' checked') + '>全文</label>' +
            '<label class="re-tier-option"><input type="radio" class="re-tier-radio" name="l2-' + idx +
            '" value="id"' + (useId ? ' checked' : '') + '>按ID:</label>' +
            '<input type="text" class="re-l2-ids re-v3-l2-input" placeholder="id1,id2" value="' +
            escapeAttr((l2.item_ids || []).join(',')) + '">';
        // L2 推广按钮
        var l2Avail = l2.available || [];
        if (l2Avail.length > 1) {
            for (var l2ai = 0; l2ai < l2Avail.length - 1; l2ai++) {
                if (l2Avail[l2ai].level === l2Default) {
                    var nextL2 = l2Avail[l2ai + 1];
                    html += '<button class="re-v3-promote-btn" data-tier="l2" data-level="' + nextL2.level +
                        '" data-idx="' + idx + '" title="放宽条目定位">▸ ' + escapeHtml(nextL2.label) +
                        ' (' + (nextL2.count || '?') + ')</button>';
                    break;
                }
            }
        }
        html += '</div>';

        // L3: 字段约束
        var fields = l3.fields || [];
        html += '<div class="re-v3-tier-row">' +
            '<span class="re-v3-tier-label">L3 字段约束</span>' +
            '<label class="re-tier-option"><input type="radio" class="re-tier-radio" name="l3-' + idx +
            '" value="restricted"' + (fields.length <= 1 ? ' checked' : '') + '>限定</label>' +
            '<label class="re-tier-option"><input type="radio" class="re-tier-radio" name="l3-' + idx +
            '" value="all_text"' + (fields.length > 1 ? ' checked' : '') + '>所有文本</label>';
        if (fields.length) {
            html += '<div class="re-v3-tier-checks">';
            for (var fi = 0; fi < fields.length; fi++) {
                var fck = (fields.length === 1) ? 'checked' : '';
                html += '<label class="re-checkbox"><input type="checkbox" class="re-l3-field" value="' +
                    escapeAttr(fields[fi]) + '" ' + fck + '> ' + escapeHtml(fields[fi]) + '</label>';
            }
            html += '</div>';
        }
        html += '</div>';

        // L4: 额外条件
        var l4Suggested = l4.suggested || 'exact';
        html += '<div class="re-v3-tier-row">' +
            '<span class="re-v3-tier-label">L4 额外条件</span>' +
            '<label class="re-tier-option"><input type="radio" class="re-tier-radio" name="l4-' + idx +
            '" value="exact"' + (l4Suggested === 'exact' ? ' checked' : '') + '>完整匹配</label>' +
            '<label class="re-tier-option"><input type="radio" class="re-tier-radio" name="l4-' + idx +
            '" value="none"' + (l4Suggested === 'none' ? ' checked' : '') + '>无</label>' +
            '<label class="re-tier-option"><input type="radio" class="re-tier-radio" name="l4-' + idx +
            '" value="custom"' + (l4Suggested === 'custom' ? ' checked' : '') + '>自定义</label>' +
            '<input type="text" class="re-l4-field re-v3-l4-field" placeholder="字段" style="width:80px;">' +
            '<input type="text" class="re-l4-pattern re-v3-l4-pattern" placeholder="匹配正则" style="width:120px;">';
        // L4 推广按钮
        var l4Avail = l4.available || [];
        if (l4Avail.length > 1) {
            for (var l4ai = 0; l4ai < l4Avail.length - 1; l4ai++) {
                if (l4Avail[l4ai].level === l4Suggested) {
                    var nextL4 = l4Avail[l4ai + 1];
                    html += '<button class="re-v3-promote-btn" data-tier="l4" data-level="' + nextL4.level +
                        '" data-idx="' + idx + '" title="放宽匹配方式">▸ ' + escapeHtml(nextL4.label) + '</button>';
                    break;
                }
            }
        }
        html += '</div>';

        html += '</div>';
        return html;
    }

    function renderMergeConnector(g1Idx, g2Idx, score, reason) {
        return '<div class="re-v3-merge-connector">' +
            '<span class="re-v3-merge-icon">🔄</span>' +
            '<span class="re-v3-merge-text">规则 #' + (g1Idx + 1) + ' 和 #' + (g2Idx + 1) +
            ' — ' + escapeHtml(String(reason)) + '</span>' +
            '<button class="re-btn re-btn-sm re-v3-merge-btn" data-g1="' + g1Idx + '" data-g2="' + g2Idx + '">合并并应用</button>' +
            '</div>';
    }

    function previewV3Group(group) {
        var idx = state.smartGenGroups ? state.smartGenGroups.indexOf(group) : -1;
        if (idx < 0 || !state.smartGenOverlay) return;
        var card = state.smartGenOverlay.querySelector('.re-v3-group-card[data-group-idx="' + idx + '"]');
        if (!card) return;
        var sel = readSmartSelections(card, idx);
        var rules = buildSmartGroupRules(group, sel);
        var out = card.querySelector('.re-v3-preview-out');
        if (!out) return;
        out.textContent = JSON.stringify(rules, null, 2);
        out.style.display = '';
    }

    async function applyV3Group(group) {
        if (!group) return;
        var idx = state.smartGenGroups ? state.smartGenGroups.indexOf(group) : -1;
        if (idx < 0) { showToast('找不到该组', 'error'); return; }
        if (!state.smartGenOverlay) return;
        var card = state.smartGenOverlay.querySelector('.re-v3-group-card[data-group-idx="' + idx + '"]');
        if (!card) { showToast('找不到组的 DOM', 'error'); return; }
        var sel = readSmartSelections(card, idx);
        var rules = buildSmartGroupRules(group, sel);
        if (!rules || !rules.length) { showToast('未能从该组生成规则', 'error'); return; }
        // Feature 5/6: 若无规则集则弹窗创建
        if (!state.currentRuleset) {
            var created = await _promptCreateRuleset();
            if (!created) return;
        }
        if (!Array.isArray(state.currentRuleset.rules)) state.currentRuleset.rules = [];
        for (var i = 0; i < rules.length; i++) state.currentRuleset.rules.push(rules[i]);
        state._rulesetDirty = true;
        refreshRulesetUI();
        try {
            await persistCurrentRuleset();
            switchMainTab('ruleset-edit');
            showToast('已添加 ' + rules.length + ' 条规则', 'success');
        } catch (e) {
            showToast('保存失败: ' + (e && e.message ? e.message : e), 'error');
            return;
        }

        // 视觉反馈
        card.style.borderColor = 'var(--color-success, #2ecc71)';
        var applyBtn = card.querySelector('.re-v3-apply-btn');
        if (applyBtn) { applyBtn.textContent = '✓ 已应用'; applyBtn.disabled = true; }
    }

    function ruleCoversItems(actions, items) {
        // 判断规则 actions（按顺序的字面全局替换）能否在 items 上推广：
        // 每条 item 的 old_val 应用规则后必须恰好等于 new_val
        if (!actions || !actions.length || !items || !items.length) return false;
        for (var i = 0; i < items.length; i++) {
            var item = items[i];
            var oldVal = item.old_val;
            var newVal = item.new_val;
            if (typeof oldVal !== 'string' || typeof newVal !== 'string') return false;
            var result = oldVal;
            for (var j = 0; j < actions.length; j++) {
                var frm = actions[j].from;
                var to = actions[j].to;
                if (typeof frm !== 'string' || typeof to !== 'string' || !frm) return false;
                result = result.split(frm).join(to);
            }
            if (result !== newVal) return false;
        }
        return true;
    }

    function detectMergeCandidatesLocally(groups) {
        // 语义化合并候选检测：一组的规则能推广覆盖另一组的全部原始变更即可合并
        var candidates = [];
        for (var i = 0; i < groups.length; i++) {
            for (var j = i + 1; j < groups.length; j++) {
                var g1 = groups[i], g2 = groups[j];
                if (g1.change_type !== g2.change_type) continue;
                var ap1 = g1.action_preview || [];
                var ap2 = g2.action_preview || [];
                var it1 = g1._raw_changes || [];
                var it2 = g2._raw_changes || [];
                if (!ap1.length || !ap2.length || !it1.length || !it2.length) continue;
                var cov1 = ruleCoversItems(ap1, it2);
                var cov2 = ruleCoversItems(ap2, it1);
                if (!cov1 && !cov2) continue;

                var files1 = (g1.l1_options && g1.l1_options.exact_files) || [];
                var files2 = (g2.l1_options && g2.l1_options.exact_files) || [];
                var sharedFiles = 0;
                for (var sf = 0; sf < files1.length; sf++) {
                    if (files2.indexOf(files1[sf]) !== -1) sharedFiles++;
                }
                var cats1 = (g1.l1_options && g1.l1_options.categories || []).map(function (c) { return c.name; });
                var cats2 = (g2.l1_options && g2.l1_options.categories || []).map(function (c) { return c.name; });
                var sharedCats = 0;
                for (var ca = 0; ca < cats1.length; ca++) {
                    if (cats2.indexOf(cats1[ca]) !== -1) sharedCats++;
                }

                var score = 20 + (sharedFiles >= 2 ? 5 : 0) + (sharedCats >= 2 ? 3 : 0);
                var ruleSrc = cov1 ? g1 : g2;
                var apText = (ruleSrc.action_preview || []).map(function (a) {
                    return String(a.from || '') + ' → ' + String(a.to || '');
                }).join('、');
                var reason = '规则 "' + apText + '" 可推广覆盖另外 ' + (cov1 ? it2.length : it1.length) + ' 项变更';
                candidates.push({ idx1: i, idx2: j, score: score, reason: reason });
                groups[i].merge_candidates.push([j, score, reason]);
                groups[j].merge_candidates.push([i, score, reason]);
            }
        }
        candidates.sort(function (a, b) { return b.score - a.score; });
        return candidates;
    }

    function _collectOriginalGroups(g) {
        if (g && Array.isArray(g._original_groups) && g._original_groups.length) {
            return g._original_groups;
        }
        return [g];
    }

    function _mergeTwoGroups(g1, g2) {
        var items1 = g1._raw_changes || [];
        var items2 = g2._raw_changes || [];
        var ap1 = g1.action_preview || [];
        var ap2 = g2.action_preview || [];
        var cov1 = ruleCoversItems(ap1, items2);
        var cov2 = ruleCoversItems(ap2, items1);

        // 语义合并：保留能推广覆盖对方变更的规则（不拼接冗余 action）
        var mergedActions, ruleSrc, mergedSummary;
        if (cov1 && cov2) {
            ruleSrc = ap1.length <= ap2.length ? g1 : g2;
            mergedActions = (ruleSrc.action_preview || []).slice();
        } else if (cov1) {
            ruleSrc = g1;
            mergedActions = ap1.slice();
        } else if (cov2) {
            ruleSrc = g2;
            mergedActions = ap2.slice();
        } else {
            // 防御回退：拼接 + 去重（旧行为）
            ruleSrc = null;
            mergedActions = ap1.slice();
            for (var i = 0; i < ap2.length; i++) {
                var dup = false;
                for (var j = 0; j < mergedActions.length; j++) {
                    if (mergedActions[j].from === ap2[i].from &&
                        mergedActions[j].to === ap2[i].to) { dup = true; break; }
                }
                if (!dup) mergedActions.push(ap2[i]);
            }
        }

        // 合并文件范围
        var files1 = (g1.l1_options && g1.l1_options.exact_files) || [];
        var files2 = (g2.l1_options && g2.l1_options.exact_files) || [];
        var mergedFiles = uniqArr(files1.concat(files2));

        var cats1 = (g1.l1_options && g1.l1_options.categories) || [];
        var cats2 = (g2.l1_options && g2.l1_options.categories) || [];
        var catMap = {};
        for (var k = 0; k < cats1.length; k++) catMap[cats1[k].name] = cats1[k].count;
        for (var k = 0; k < cats2.length; k++) {
            if (catMap[cats2[k].name]) catMap[cats2[k].name] = Math.max(catMap[cats2[k].name], cats2[k].count);
            else catMap[cats2[k].name] = cats2[k].count;
        }
        var mergedCats = Object.keys(catMap).map(function (cn) { return { name: cn, count: catMap[cn], selected: true }; });

        var mergedFields = uniqArr(
            (g1.l3_options && g1.l3_options.fields || []).concat(
            g2.l3_options && g2.l3_options.fields || [])
        );

        var mergedFrom = (g1.merged_from || []).concat(g2.merged_from || []);
        var mergedIds = uniqArr((g1.l2_options && g1.l2_options.item_ids || []).concat(
                                g2.l2_options && g2.l2_options.item_ids || []));

        var totalOccur = (g1.occurrence_count || 0) + (g2.occurrence_count || 0);
        if (ruleSrc) {
            mergedSummary = (ruleSrc.summary || '检测到 ' + totalOccur + ' 处相同修改')
                .replace(/检测到 \d+ 处/, '检测到 ' + totalOccur + ' 处');
        } else {
            mergedSummary = '已合并 2 组规则: ' + (g1.summary || '') + ' + ' + (g2.summary || '');
        }

        // 合并原始变更（去重）
        var mergedRaw = [];
        var seenRaw = {};
        var rawAll = (g1._raw_changes || []).concat(g2._raw_changes || []);
        for (var ri = 0; ri < rawAll.length; ri++) {
            var rk = String(rawAll[ri].old_val) + '::' + String(rawAll[ri].new_val);
            if (!seenRaw[rk]) {
                seenRaw[rk] = true;
                mergedRaw.push({ old_val: rawAll[ri].old_val, new_val: rawAll[ri].new_val });
            }
        }

        var originGroups = _collectOriginalGroups(g1).concat(_collectOriginalGroups(g2));

        return {
            change_type: g1.change_type,
            summary: mergedSummary,
            suggestions: [],
            action_preview: mergedActions,
            file_count: mergedFiles.length,
            item_count: (g1.item_count || 0) + (g2.item_count || 0),
            occurrence_count: totalOccur,
            l1_options: { suggested: mergedCats.length <= 2 ? 'category' : 'multi_category', categories: mergedCats, exact_files: mergedFiles },
            l2_options: { suggested: mergedIds.length ? 'id' : 'full_text', item_ids: mergedIds },
            l3_options: { suggested: mergedFields.length === 1 ? 'restricted' : 'all_text', fields: mergedFields },
            l4_options: { suggested: 'exact' },
            score: { priority: Math.max(g1.score && g1.score.priority || 0, g2.score && g2.score.priority || 0) },
            merged_from: mergedFrom,
            is_merged: true,
            merge_candidates: [],
            _raw_changes: mergedRaw,
            _original_groups: originGroups.map(function (g) { return JSON.parse(JSON.stringify(g)); })
        };
    }

    function _autoMergeCandidates(groups, mergeCandidates) {
        if (!mergeCandidates || !mergeCandidates.length) return { groups: groups.slice(), remaining: [] };

        // 只自动合并高分候选（score >= 10）
        var highConf = [];
        for (var h = 0; h < mergeCandidates.length; h++) {
            if (mergeCandidates[h].score >= 10) highConf.push(mergeCandidates[h]);
        }
        if (!highConf.length) return { groups: groups.slice(), remaining: mergeCandidates.slice() };

        // 按分数降序排序
        highConf.sort(function (a, b) { return b.score - a.score; });

        var merged = {};   // idx -> mergedGroup
        var consumed = {}; // idx -> true

        for (var i = 0; i < highConf.length; i++) {
            var mc = highConf[i];
            var idx1 = mc.idx1, idx2 = mc.idx2;
            if (consumed[idx1] || consumed[idx2]) continue;

            var g1 = merged[idx1] || groups[idx1];
            var g2 = groups[idx2];

            var mergedGroup = _mergeTwoGroups(g1, g2);
            mergedGroup._auto_merged = true;
            mergedGroup._split_origin = mergedGroup._original_groups.map(function (g) { return g; });

            merged[idx1] = mergedGroup;
            consumed[idx2] = true;
        }

        // 构建新的 groups 列表
        var newGroups = [];
        var oldToNew = {};  // 旧 idx -> 新 idx
        for (var j = 0; j < groups.length; j++) {
            if (consumed[j]) continue;
            if (merged[j]) {
                oldToNew[j] = newGroups.length;
                newGroups.push(merged[j]);
            } else {
                oldToNew[j] = newGroups.length;
                newGroups.push(groups[j]);
            }
        }

        // 过滤剩余 candidates（去重 + 重映射 idx）
        var remaining = [];
        var seenPairs = {};
        for (var k = 0; k < mergeCandidates.length; k++) {
            var rmc = mergeCandidates[k];
            // 已被合并进其他组（新数组中不再独立存在）的旧索引无法安全映射，直接丢弃
            var ni1 = oldToNew.hasOwnProperty(rmc.idx1) ? oldToNew[rmc.idx1] : -1;
            var ni2 = oldToNew.hasOwnProperty(rmc.idx2) ? oldToNew[rmc.idx2] : -1;
            if (ni1 < 0 || ni2 < 0) continue;
            // 跳过已自动合并的（两者映射到相同 idx）
            if (ni1 === ni2) continue;
            var pairKey = Math.min(ni1, ni2) + '_' + Math.max(ni1, ni2);
            if (seenPairs[pairKey]) continue;
            seenPairs[pairKey] = true;
            if (rmc.score < 10) {
                remaining.push({ idx1: ni1, idx2: ni2, score: rmc.score, reason: rmc.reason });
            }
        }

        return { groups: newGroups, remaining: remaining };
    }

    async function mergeAndApplyV3(g1Idx, g2Idx) {
        var groups = state.smartGenGroups;
        if (!groups || g1Idx >= groups.length || g2Idx >= groups.length) {
            showToast('找不到要合并的组', 'error');
            return;
        }
        var g1 = groups[g1Idx], g2 = groups[g2Idx];
        var mergedGroup = _mergeTwoGroups(g1, g2);
        mergedGroup._auto_merged = true;
        mergedGroup._split_origin = mergedGroup._original_groups.map(function (g) { return g; });

        // 将合并组加入 state.smartGenGroups 并重新渲染，使 applyV3Group 能按索引定位到合并组卡片
        var newGroups = groups.slice();
        newGroups.push(mergedGroup);
        state.smartGenGroups = newGroups;

        // 移除已应用的合并候选，其余候选索引在 append 后保持不变
        var remaining = [];
        var candidates = state._lastMergeCandidates || [];
        for (var c = 0; c < candidates.length; c++) {
            var cd = candidates[c];
            if (cd.idx1 === g1Idx && cd.idx2 === g2Idx) continue;
            remaining.push(cd);
        }

        var overlay = state.smartGenOverlay;
        if (overlay) {
            renderV3Results({ groups: newGroups, merge_candidates: remaining, stats: { group_count: newGroups.length } }, {});
        }
        await applyV3Group(mergedGroup);
    }

    function splitAutoMergedGroup(groupIdx) {
        var groups = state.smartGenGroups;
        if (!groups || groupIdx >= groups.length) return;
        var group = groups[groupIdx];
        var originGroups = group._original_groups || [];
        if (originGroups.length < 2) {
            showToast('该组没有可拆分的来源', 'error');
            return;
        }

        // 用原始组替换当前合并组
        var newGroups = [];
        for (var i = 0; i < groups.length; i++) {
            if (i === groupIdx) {
                for (var j = 0; j < originGroups.length; j++) {
                    var og = JSON.parse(JSON.stringify(originGroups[j]));
                    delete og._auto_merged;
                    delete og._split_origin;
                    delete og._original_groups;
                    newGroups.push(og);
                }
            } else {
                newGroups.push(groups[i]);
            }
        }

        state.smartGenGroups = newGroups;

        // 重新渲染
        var overlay = state.smartGenOverlay;
        if (!overlay) return;
        var result = {
            groups: newGroups,
            merge_candidates: state._lastMergeCandidates || [],
            stats: { group_count: newGroups.length }
        };
        // 重新检测合并候选
        if (typeof detectMergeCandidatesLocally !== 'undefined') {
            // 使用本地语义检测重新计算 merge_candidates
            result.merge_candidates = detectMergeCandidatesLocally(newGroups);
        }
        state._v3SkipAutoMerge = true;
        renderV3Results(result, {});
        showToast('已拆分为 ' + originGroups.length + ' 个独立组', 'success');
    }

    function promoteConstraint(idx, tier, level) {
        if (!state.smartGenOverlay) return;
        var card = state.smartGenOverlay.querySelector('.re-v3-group-card[data-group-idx="' + idx + '"]');
        if (!card) return;

        // 找到对应 radio 并选中
        var radio = card.querySelector('input[name="' + tier + '-' + idx + '"][value="' + level + '"]');
        if (!radio) {
            // 检查是否是 L1 category 特殊情况
            if (tier === 'l1' && level === 'category') {
                // 选中按分类 radio + 勾选所有分类
                var catRadio = card.querySelector('input[name="l1-' + idx + '"][value="category"]');
                if (catRadio) { catRadio.checked = true; catRadio.dispatchEvent(new Event('change', { bubbles: true })); }
                var catChecks = card.querySelectorAll('.re-l1-cat');
                for (var cci = 0; cci < catChecks.length; cci++) { catChecks[cci].checked = true; }
            }
            return;
        }
        radio.checked = true;
        radio.dispatchEvent(new Event('change', { bubbles: true }));

        // 更新推广按钮（隐藏当前按钮，显示下一级）
        updatePromoteButtons(card, idx);
        checkPostPromotionMerge(idx);
    }

    function updatePromoteButtons(card, idx) {
        if (!card) return;

        // L1: promote button shows NEXT broader level; hide if already at or past its target
        var l1Radios = card.querySelectorAll('input[name="l1-' + idx + '"]');
        var currentL1 = '';
        for (var ri = 0; ri < l1Radios.length; ri++) {
            if (l1Radios[ri].checked) { currentL1 = l1Radios[ri].value; break; }
        }
        // L1 broadening order: exact → category → all
        var l1Order = ['exact', 'category', 'all'];
        var l1CurrentIdx = l1Order.indexOf(currentL1);
        var l1PromoteBtns = card.querySelectorAll('.re-v3-promote-btn[data-tier="l1"]');
        for (var pi = 0; pi < l1PromoteBtns.length; pi++) {
            var btnTargetIdx = l1Order.indexOf(l1PromoteBtns[pi].dataset.level);
            // Show only the button that targets the immediate next level
            l1PromoteBtns[pi].style.display = (btnTargetIdx === l1CurrentIdx + 1) ? '' : 'none';
        }

        // L2 broadening order: id → full_text
        var l2Radios = card.querySelectorAll('input[name="l2-' + idx + '"]');
        var currentL2 = '';
        for (var rj = 0; rj < l2Radios.length; rj++) {
            if (l2Radios[rj].checked) { currentL2 = l2Radios[rj].value; break; }
        }
        var l2Order = ['id', 'full_text'];
        var l2CurrentIdx = l2Order.indexOf(currentL2);
        var l2PromoteBtns = card.querySelectorAll('.re-v3-promote-btn[data-tier="l2"]');
        for (var pj = 0; pj < l2PromoteBtns.length; pj++) {
            var btnTargetIdx2 = l2Order.indexOf(l2PromoteBtns[pj].dataset.level);
            l2PromoteBtns[pj].style.display = (btnTargetIdx2 === l2CurrentIdx + 1) ? '' : 'none';
        }

        // L4 broadening order: exact → none
        var l4Radios = card.querySelectorAll('input[name="l4-' + idx + '"]');
        var currentL4 = '';
        for (var rk = 0; rk < l4Radios.length; rk++) {
            if (l4Radios[rk].checked) { currentL4 = l4Radios[rk].value; break; }
        }
        var l4Order = ['exact', 'none'];
        var l4CurrentIdx = l4Order.indexOf(currentL4);
        var l4PromoteBtns = card.querySelectorAll('.re-v3-promote-btn[data-tier="l4"]');
        for (var pk = 0; pk < l4PromoteBtns.length; pk++) {
            var btnTargetIdx4 = l4Order.indexOf(l4PromoteBtns[pk].dataset.level);
            l4PromoteBtns[pk].style.display = (btnTargetIdx4 === l4CurrentIdx + 1) ? '' : 'none';
        }
    }

    function checkPostPromotionMerge(groupIdx) {
        // 检查推广后是否可与其他组合并
        var groups = state.smartGenGroups;
        if (!groups || groupIdx >= groups.length) return;
        var card = state.smartGenOverlay ?
            state.smartGenOverlay.querySelector('.re-v3-group-card[data-group-idx="' + groupIdx + '"]') : null;
        if (!card) return;
        var sel = readSmartSelections(card, groupIdx);
        var thisRules = buildSmartGroupRules(groups[groupIdx], sel);
        if (!thisRules || !thisRules.length) return;
        var thisSig = _computeRuleSignature(thisRules[0]);
        if (!thisSig) return;

        for (var i = 0; i < groups.length; i++) {
            if (i === groupIdx) continue;
            var otherCard = state.smartGenOverlay ?
                state.smartGenOverlay.querySelector('.re-v3-group-card[data-group-idx="' + i + '"]') : null;
            if (!otherCard) continue;
            var otherSel = readSmartSelections(otherCard, i);
            var otherRules = buildSmartGroupRules(groups[i], otherSel);
            if (!otherRules || !otherRules.length) continue;
            var otherSig = _computeRuleSignature(otherRules[0]);
            if (thisSig === otherSig) {
                showToast('推广后规则与规则 #' + (i + 1) + ' 相同，建议合并', 'info');
                return;
            }
        }
    }

    async function applyAllV3WithDedup() {
        var groups = state.smartGenGroups || [];
        if (!groups.length) { showToast('没有可应用的组', 'error'); return; }
        // Feature 5/6: 若无规则集则弹窗创建
        if (!state.currentRuleset) {
            var created = await _promptCreateRuleset();
            if (!created) return;
        }

        var existingRules = state.currentRuleset.rules || [];
        var appliedSigs = {};
        var appliedCount = 0;
        var skippedCount = 0;

        // 为已有规则建立签名索引
        for (var ei = 0; ei < existingRules.length; ei++) {
            var sig = _computeRuleSignature(existingRules[ei]);
            if (sig) appliedSigs[sig] = true;
        }

        for (var i = 0; i < groups.length; i++) {
            var group = groups[i];
            var card = state.smartGenOverlay ?
                state.smartGenOverlay.querySelector('.re-v3-group-card[data-group-idx="' + i + '"]') : null;
            // Feature 4: 跳过未勾选的组
            if (card) {
                var toggle = card.querySelector('.re-v3-group-toggle');
                if (toggle && !toggle.checked) continue;
            }
            var sel = card ? readSmartSelections(card, i) : {
                l1: 'category',
                l1Categories: (group.l1_options && group.l1_options.categories || []).map(function (c) { return c.name; }),
                l1Custom: '',
                l2: (group.l2_options && group.l2_options.item_ids && group.l2_options.item_ids.length) ? 'id' : 'full_text',
                l2Ids: (group.l2_options && group.l2_options.item_ids) || [],
                l3: (group.l3_options && group.l3_options.fields && group.l3_options.fields.length <= 1) ? 'restricted' : 'all_text',
                l3Fields: (group.l3_options && group.l3_options.fields) || [],
                l4: 'exact',
                l4Field: '',
                l4Pattern: ''
            };

            var rules = buildSmartGroupRules(group, sel);
            if (!rules || !rules.length) continue;

            for (var j = 0; j < rules.length; j++) {
                var sig = _computeRuleSignature(rules[j]);
                if (sig && appliedSigs[sig]) {
                    skippedCount++;
                    continue;
                }
                if (sig) appliedSigs[sig] = true;
                existingRules.push(rules[j]);
                appliedCount++;
            }
        }

        if (!Array.isArray(state.currentRuleset.rules)) state.currentRuleset.rules = [];
        state.currentRuleset.rules = existingRules;
        state._rulesetDirty = true;

        refreshRulesetUI();
        try {
            await persistCurrentRuleset();
        } catch (e) {
            showToast('保存失败: ' + (e && e.message ? e.message : e), 'error');
            return;
        }
        closeSmartGenDialogV3();
        switchMainTab('ruleset-edit');
        showToast('已应用 ' + appliedCount + ' 条规则' +
            (skippedCount > 0 ? '（跳过 ' + skippedCount + ' 条重复）' : ''), 'success');
    }

    function _computeRuleSignature(rule) {
        if (!rule) return null;
        return JSON.stringify({
            files: rule.files || [],
            scope: rule.scope || '',
            targets: rule.targets || [],
            where: rule.where || [],
            actions: rule.actions || []
        });
    }

    function analyzeChangesLocally(changes) {
        if (!changes || !changes.length) return [];
        const buckets = {};
        const order = [];
        for (let i = 0; i < changes.length; i++) {
            const c = changes[i];
            const key = String(c.old_val) + '::' + String(c.new_val);
            if (!buckets[key]) { buckets[key] = []; order.push(key); }
            buckets[key].push(c);
        }
        const groups = [];
        for (let i = 0; i < order.length; i++) {
            const items = buckets[order[i]];
            const first = items[0];
            const files = uniqArr(items.map(function (c) { return c.file; }));
            const itemIds = uniqArr(items.map(function (c) { return c.item_id; }).filter(function (v) { return v != null && v !== ''; }));
            const fieldPaths = uniqArr(items.map(function (c) { return c.field_path; }));
            const cats = {};
            for (let j = 0; j < files.length; j++) {
                const cc = classifyPath(files[j]).category;
                cats[cc] = (cats[cc] || 0) + 1;
            }
            const catList = Object.keys(cats).map(function (k) { return { name: k, count: cats[k], selected: true }; });
            const priority = Math.min(80, 30 + items.length * 5);
            groups.push({
                change_type: 'PURE_REPLACE',
                summary: '检测到 ' + items.length + ' 处相同替换 (' + first.old_val + ' → ' + first.new_val + ')',
                suggestions: [],
                action_preview: [{ from: first.old_val, to: first.new_val }],
                file_count: files.length, item_count: itemIds.length, occurrence_count: items.length,
                l1_options: { suggested: catList.length <= 2 ? 'category' : 'multi_category', categories: catList, exact_files: files },
                l2_options: { suggested: itemIds.length ? 'id' : 'full_text', item_ids: itemIds },
                l3_options: { suggested: fieldPaths.length === 1 ? 'restricted' : 'all_text', fields: fieldPaths },
                l4_options: { suggested: 'exact' },
                score: { priority: priority }
            });
        }
        return groups;
    }

    function uniqArr(arr) {
        const seen = {}; const out = [];
        for (let i = 0; i < arr.length; i++) {
            const k = String(arr[i]);
            if (!seen[k]) { seen[k] = true; out.push(arr[i]); }
        }
        return out;
    }

    function showToast(message, kind) {
        const main = document.querySelector('.re-main');
        if (!main) { console.log('[rule-editor] ' + message); return; }
        let toast = main.querySelector('.re-toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.className = 're-toast';
            main.insertBefore(toast, main.firstChild);
        }
        toast.className = 're-toast re-toast-' + (kind || 'info');
        toast.textContent = message;
        toast.style.display = 'block';
        clearTimeout(showToast._t);
        showToast._t = setTimeout(function () { toast.style.display = 'none'; }, 3000);
    }

    // ═══════════════════════════════════════════════════════
    //  File Edit Mode — init, editor, diff, save
    // ═══════════════════════════════════════════════════════

    function initFileEditor() {
        var container = document.getElementById('re-file-editor-tabs-container');
        if (!container) return null;

        var ts = getActiveTabState();
        return ts ? ts.editor : null;
    }

    function getFileEditorDoc() {
        const editor = state.fileEditor;
        if (!editor) return '';
        return editor.state.doc.toString();
    }

    function setFileEditorDoc(text) {
        const editor = initFileEditor();
        if (!editor) return;
        const len = editor.state.doc.length;
        editor.dispatch({ changes: { from: 0, to: len, insert: text || '' } });
    }

    // ---- Dirty State & File Tab Label ----
    function updateDirtyState() {
        var ts = getActiveTabState();
        if (!ts) return;
        updateFileEditStatus(ts);

        var hasDirty = false;
        state.openFiles.forEach(function (t) {
            if (t.editStatus === 'staged') hasDirty = true;
        });
        document.title = (hasDirty ? '● ' : '') + 'LCTA - 美化规则编辑器';
    }

    /** Recursive JSON diff returning [(path_string, old_val, new_val)] */
    function diffJson(original, modified, prefix) {
        if (prefix == null) prefix = '';
        let changes = [];
        if (typeof original !== typeof modified) {
            changes.push([prefix, original, modified]);
        } else if (Array.isArray(original) && Array.isArray(modified)) {
            let maxLen = Math.max(original.length, modified.length);
            for (let i = 0; i < maxLen; i++) {
                let newPrefix = prefix + '[' + i + ']';
                if (i >= original.length) {
                    changes.push([newPrefix, null, modified[i]]);
                } else if (i >= modified.length) {
                    changes.push([newPrefix, original[i], null]);
                } else {
                    changes = changes.concat(diffJson(original[i], modified[i], newPrefix));
                }
            }
        } else if (typeof original === 'object' && original !== null && typeof modified === 'object' && modified !== null) {
            let allKeys = {};
            for (let k in original) { if (original.hasOwnProperty(k)) allKeys[k] = true; }
            for (let k in modified) { if (modified.hasOwnProperty(k)) allKeys[k] = true; }
            let sortedKeys = Object.keys(allKeys).sort();
            for (let ki = 0; ki < sortedKeys.length; ki++) {
                let key = sortedKeys[ki];
                let newPrefix = prefix ? prefix + '.' + key : key;
                if (!(key in original)) {
                    changes.push([newPrefix, null, modified[key]]);
                } else if (!(key in modified)) {
                    changes.push([newPrefix, original[key], null]);
                } else {
                    changes = changes.concat(diffJson(original[key], modified[key], newPrefix));
                }
            }
        } else if (original !== modified) {
            changes.push([prefix, original, modified]);
        }
        return changes;
    }

    /** Parse a diff path like "dataList[0].desc" → {field_path: "desc", itemIdx: 0} */
    function parseDiffPath(path) {
        let match = path.match(/^dataList\[(\d+)\]\.(.+)$/);
        if (match) {
            return { field_path: match[2], itemIdx: parseInt(match[1], 10) };
        }
        return { field_path: path.split('.').pop(), itemIdx: null };
    }

    /** Convert diff entries to {file, field_path, item_id, old_val, new_val} format */
    function extractChangesFromDiff(diffEntries, filePath, parsedData) {
        let changes = [];
        for (let i = 0; i < diffEntries.length; i++) {
            let entry = diffEntries[i];
            let path = entry[0];
            let oldVal = entry[1];
            let newVal = entry[2];
            // Only track string value changes
            if (typeof newVal !== 'string' || typeof oldVal !== 'string') continue;
            let parsed = parseDiffPath(path);
            // Only track dataList items (rules can only target these)
            if (parsed.itemIdx == null) continue;
            let itemId = null;
            if (parsedData && parsedData.dataList && parsedData.dataList[parsed.itemIdx]) {
                let item = parsedData.dataList[parsed.itemIdx];
                itemId = (item.id != null) ? String(item.id) : null;
            }
            changes.push({
                file: filePath,
                field_path: parsed.field_path,
                item_id: itemId,
                old_val: oldVal,
                new_val: newVal
            });
        }
        return changes;
    }

    function diffAndTrackChanges() {
        var ts = getActiveTabState();
        if (!ts) {
            showToast('请先打开一个文件', 'error');
            return;
        }
        var raw = ts.editor.state.doc.toString();
        if (!raw.trim()) {
            showToast('编辑器内容为空', 'error');
            return;
        }
        var parsed;
        try {
            parsed = JSON.parse(raw);
        } catch (e) {
            showToast('JSON 解析错误: ' + e.message, 'error');
            return;
        }
        var originalParsed = ts.baselineParsed;
        if (!originalParsed) {
            showToast('没有原始内容可比较（请先加载文件）', 'error');
            return;
        }
        var diffs = diffJson(originalParsed, parsed, '');
        if (!diffs.length) {
            showToast('未检测到变更', 'info');
            ts.pendingChanges = [];
            renderChangeList();
            return;
        }
        var changes = extractChangesFromDiff(diffs, ts.path, originalParsed);
        ts.pendingChanges = changes;
        state.pendingChanges = changes;
        renderChangeList();
        showToast('检测到 ' + changes.length + ' 处文本变更', 'success');
    }

    function renderChangeList() {
        let container = $i('re-change-list');
        let panel = $i('re-changes-panel');
        let countEl = $i('re-change-count');
        if (!container) return;
        let changes = state.pendingChanges || [];
        if (panel) panel.style.display = changes.length ? '' : 'none';
        if (countEl) countEl.textContent = String(changes.length);
        if (!changes.length) {
            container.innerHTML = '<div class="re-change-empty">暂无变更 — 编辑文件后点击「比较变更」</div>';
            return;
        }
        let html = '';
        for (let i = 0; i < changes.length; i++) {
            let c = changes[i];
            let displayFile = c.file || '';
            if (displayFile.length > 40) displayFile = '...' + displayFile.slice(-37);
            html += '<div class="re-change-item">' +
                '<span class="re-change-file" title="' + escapeAttr(c.file) + '">' + escapeHtml(displayFile) + '</span>' +
                '<span class="re-change-detail">' +
                '<span class="re-change-old">' + escapeHtml(String(c.old_val)) + '</span>' +
                '<span class="re-change-arrow"> → </span>' +
                '<span class="re-change-new">' + escapeHtml(String(c.new_val)) + '</span>' +
                '</span></div>';
        }
        container.innerHTML = html;
    }

    function clearPendingChanges() {
        state.pendingChanges = [];
        renderChangeList();
    }

    async function saveEditedFile() {
        var ts = getActiveTabState();
        if (!ts) {
            showToast('没有打开的文件', 'error');
            return;
        }
        var path = ts.path;
        var raw = ts.editor.state.doc.toString();
        if (!raw.trim()) {
            showToast('编辑器内容为空', 'error');
            return;
        }
        try {
            JSON.parse(raw);
        } catch (e) {
            showToast('JSON 格式无效，无法保存: ' + e.message, 'error');
            return;
        }
        var api = getApi();
        if (!api || !api.save_file_content) return warnNoApi();
        try {
            var res = await api.save_file_content(path, raw);
            if (res && res.success) {
                ts.diskContent = raw;
                ts.baselineContent = raw;
                try { ts.baselineParsed = JSON.parse(raw); } catch (e) { void e; }
                ts.lastSavedAt = Date.now();
                ts.pendingChanges = [];
                state.pendingChanges = [];
                updateFileEditStatus(ts);
                renderChangeList();

                if (state.fileCache.has(path)) {
                    var cached = state.fileCache.get(path);
                    cached.raw = raw;
                    try { cached.parsed = JSON.parse(raw); } catch (e) { void e; }
                }

                renderFileTabBar();
                renderFileList();
                updateFileEditTabLabel();
                document.title = 'LCTA - 美化规则编辑器';
                showToast('文件已保存到游戏: ' + path, 'success');
            } else {
                showToast('保存失败: ' + ((res && res.error) || ''), 'error');
            }
        } catch (e) {
            showToast('保存异常: ' + (e && e.message ? e.message : e), 'error');
        }
    }

    async function saveEditedFileForTab(path) {
        var prevActive = state.activeFileTab;
        activateFileTab(path);
        await saveEditedFile();
        if (prevActive && prevActive !== path) {
            activateFileTab(prevActive);
        }
    }

    function revertEditedFile() {
        var ts = getActiveTabState();
        if (!ts) {
            showToast('没有打开的文件', 'error');
            return;
        }
        var editor = ts.editor;
        var docLen = editor.state.doc.length;
        editor.dispatch({ changes: { from: 0, to: docLen, insert: ts.diskContent } });
        ts.pendingChanges = [];
        updateFileEditStatus(ts);
        renderFileTabBar();
        renderFileList();
        updateFileEditTabLabel();
        showToast('已撤销所有更改', 'info');
    }

    // Feature 1: 三向状态转换函数

    /** applied → staged: 将磁盘内容还原为基线，保留编辑器修改 */
    async function revertAppliedToStaged(ts) {
        if (!ts || ts.editStatus !== 'applied') return;
        var api = getApi();
        if (!api || !api.save_file_content) { warnNoApi(); return; }
        try {
            var res = await api.save_file_content(ts.path, ts.baselineContent);
            if (res && res.success) {
                ts.diskContent = ts.baselineContent;
                updateFileEditStatus(ts);
                renderFileTabBar();
                updateFileEditTabLabel();
                if (state.activeTab === 'file-status') renderFileStatusPanel();
                showToast('已还原到暂存状态: ' + ts.path, 'info');
            } else {
                showToast('还原失败: ' + ((res && res.error) || ''), 'error');
            }
        } catch (e) {
            showToast('还原异常: ' + (e && e.message ? e.message : e), 'error');
        }
    }

    /** staged → clean: 放弃编辑器更改，恢复到硬盘内容 */
    function revertStagedToOriginal(ts) {
        if (!ts || ts.editStatus !== 'staged') return;
        var editor = ts.editor;
        if (!editor) return;
        var docLen = editor.state.doc.length;
        editor.dispatch({ changes: { from: 0, to: docLen, insert: ts.diskContent } });
        ts.pendingChanges = [];
        updateFileEditStatus(ts);
        renderFileTabBar();
        updateFileEditTabLabel();
        if (state.activeTab === 'file-status') renderFileStatusPanel();
        showToast('已放弃更改: ' + ts.path, 'info');
    }

    /** staged → applied: 保存编辑器内容到硬盘但不更新基线 */
    async function saveStagedAsApplied(ts) {
        if (!ts || ts.editStatus !== 'staged') return;
        var path = ts.path;
        var raw = ts.editor.state.doc.toString();
        if (!raw.trim()) { showToast('编辑器内容为空', 'error'); return; }
        try { JSON.parse(raw); }
        catch (e) { showToast('JSON 格式无效: ' + e.message, 'error'); return; }
        var api = getApi();
        if (!api || !api.save_file_content) { warnNoApi(); return; }
        try {
            var res = await api.save_file_content(path, raw);
            if (res && res.success) {
                ts.diskContent = raw; // 更新 disk，不更新 baseline
                try { ts.baselineParsed = JSON.parse(raw); } catch (e) { void e; }
                ts.lastSavedAt = Date.now();
                ts.pendingChanges = [];
                if (state.fileCache.has(path)) {
                    var cached = state.fileCache.get(path);
                    cached.raw = raw;
                    try { cached.parsed = JSON.parse(raw); } catch (e) { void e; }
                }
                updateFileEditStatus(ts);
                renderFileTabBar();
                updateFileEditTabLabel();
                if (state.activeTab === 'file-status') renderFileStatusPanel();
                showToast('已保存为应用状态: ' + path, 'success');
            } else {
                showToast('保存失败: ' + ((res && res.error) || ''), 'error');
            }
        } catch (e) {
            showToast('保存异常: ' + (e && e.message ? e.message : e), 'error');
        }
    }

    async function refreshEditedFile() {
        var ts = getActiveTabState();
        if (!ts) { showToast('没有打开的文件', 'error'); return; }
        var path = ts.path;

        if (state.fileCache.has(path)) {
            state.fileCache.delete(path);
        }
        state.openFiles.delete(path);
        var idx = state.fileTabOrder.indexOf(path);
        if (idx !== -1) state.fileTabOrder.splice(idx, 1);
        if (ts.editor) ts.editor.destroy();
        if (ts.container && ts.container.parentNode) {
            ts.container.parentNode.removeChild(ts.container);
        }

        await createFileTab(path);
        showToast('已刷新', 'info');
    }

    async function generateRulesFromChanges() {
        var hasEdits = false;
        state.openFiles.forEach(function (ts) {
            if (ts.editStatus === 'staged' || ts.editStatus === 'applied') hasEdits = true;
        });
        if (!hasEdits) {
            showToast('没有已暂存或已应用的编辑 — 请先在文件中修改并保存', 'error');
            return;
        }
        // Feature 6: 未选中规则集时弹窗允许创建
        if (!state.currentRuleset || !state.currentRuleset.name) {
            var created = await _promptCreateRuleset();
            if (!created) return; // 用户取消
        }
        await openSmartGenerationV3();
    }

    // Feature 6: 弹窗创建规则集（可复用）
    async function _promptCreateRuleset() {
        var name = window.prompt('当前未选择规则集。请输入名称创建新规则集：');
        if (!name || !name.trim()) return null;
        var trimmed = name.trim();
        var api = getApi();
        if (!api) { warnNoApi(); return null; }
        try {
            var res = await api.create_ruleset(trimmed);
            if (res && res.success === false) {
                showToast('创建失败: ' + (res.error || ''), 'error');
                return null;
            }
        } catch (e) {
            showToast('创建异常: ' + (e && e.message ? e.message : e), 'error');
            return null;
        }
        await loadRulesets();
        var sel = $i('re-ruleset-select');
        if (sel) sel.value = trimmed;
        await loadRulesetByName(trimmed);
        showToast('已创建规则集: ' + trimmed, 'success');
        return state.currentRuleset;
    }

    // ═══════════════════════════════════════════════════════
    //  跨标签搜索状态桥接 — 标签切换时保存/恢复搜索面板
    // ═══════════════════════════════════════════════════════
    function _captureSearchState(editorView) {
        var CM = window.CodeMirror;
        if (!CM || !CM.getSearchQuery) return;
        try {
            var query = CM.getSearchQuery(editorView.state);
            if (query && query.search !== '') {
                _searchBridge.query = query.search || '';
                _searchBridge.replaceQuery = query.replace || '';
                _searchBridge.caseSensitive = !!query.caseSensitive;
                _searchBridge.wholeWord = !!query.wholeWord;
                _searchBridge.regexp = !!query.regexp;
                _searchBridge.isOpen = true;
            } else {
                _searchBridge.isOpen = false;
            }
            // 保存当前面板位置（用于跨标签恢复）
            var dom = editorView.dom;
            if (dom) {
                var panels = dom.querySelector('.cm-panels');
                if (panels && panels.style.left) {
                    _searchBridge.panelLeft = panels.style.left;
                    _searchBridge.panelTop = panels.style.top || '';
                    _searchBridge.panelRight = panels.style.right || 'auto';
                }
            }
            // 关闭旧编辑器的搜索面板，防止切换标签后 DOM 残留
            if (CM.closeSearchPanel) {
                try {
                    CM.closeSearchPanel(editorView);
                } catch(e) {}
            }
        } catch(e) { /* CM6 getSearchQuery may fail across versions */ }
    }

    function _restoreSearchState(editorView, container) {
        var CM = window.CodeMirror;
        if (!CM || !CM.openSearchPanel || !_searchBridge.isOpen) return;
        if (!_searchBridge.query) return;

        // 工具函数：恢复拖拽位置
        function _applyStoredPosition() {
            if (!_searchBridge.panelLeft) return; // 从未拖拽过，使用 CSS 默认值
            var c = container;
            if (!c) {
                var wrapper = editorView.dom ? editorView.dom.closest('.re-file-editor-wrapper') : null;
                c = wrapper || editorView.dom;
            }
            if (!c) return;
            var panels = c.querySelector('.cm-panels');
            if (!panels) return;
            if (window.EditorSearchPanel) {
                EditorSearchPanel.setSearchPanelPosition(
                    panels,
                    parseFloat(_searchBridge.panelLeft) || 8,
                    parseFloat(_searchBridge.panelTop) || 8
                );
            }
        }

        // 目标编辑器已有可见搜索面板：仅更新查询 + 位置
        if (container) {
            var existingPanel = container.querySelector('.cm-search');
            if (existingPanel) {
                if (CM.SearchQuery && CM.setSearchQuery) {
                    try {
                        editorView.dispatch({
                            effects: CM.setSearchQuery.of(new CM.SearchQuery({
                                search: _searchBridge.query,
                                replace: _searchBridge.replaceQuery || '',
                                caseSensitive: !!_searchBridge.caseSensitive,
                                wholeWord: !!_searchBridge.wholeWord,
                                regexp: !!_searchBridge.regexp
                            }))
                        });
                    } catch(e) {}
                }
                _applyStoredPosition();
                return;
            }
        }

        // 无现有面板：打开新面板
        try {
            CM.openSearchPanel(editorView);
        } catch(e) {}

        // 取消之前的待执行恢复
        if (_searchBridge._restoreTimeout) {
            clearTimeout(_searchBridge._restoreTimeout);
            _searchBridge._restoreTimeout = null;
        }

        _searchBridge._restoreTimeout = setTimeout(function () {
            _searchBridge._restoreTimeout = null;
            if (!_searchBridge.isOpen) return; // 用户可能已关闭面板
            if (CM.SearchQuery && CM.setSearchQuery) {
                try {
                    editorView.dispatch({
                        effects: CM.setSearchQuery.of(new CM.SearchQuery({
                            search: _searchBridge.query,
                            replace: _searchBridge.replaceQuery || '',
                            caseSensitive: !!_searchBridge.caseSensitive,
                            wholeWord: !!_searchBridge.wholeWord,
                            regexp: !!_searchBridge.regexp
                        }))
                    });
                } catch(e) {}
            }
            // 恢复拖拽位置
            _applyStoredPosition();
        }, 80);
    }

    // ═══════════════════════════════════════════════════════
    //  Panel Resize — 拖拽调整侧边栏和底部面板大小
    // ═══════════════════════════════════════════════════════

    var RESIZE_MIN_SIDEBAR = 180;
    var RESIZE_MAX_SIDEBAR = 500;
    var RESIZE_MIN_BOTTOM = 100;
    var RESIZE_MAX_BOTTOM = 500;

    function initResizeHandles() {
        var sidebarHandle = document.getElementById('re-resize-sidebar');
        var bottomHandle = document.getElementById('re-resize-bottom');
        
        if (sidebarHandle) {
            sidebarHandle.addEventListener('mousedown', function (e) {
                startResize(e, 'sidebar');
            });
        }
        if (bottomHandle) {
            bottomHandle.addEventListener('mousedown', function (e) {
                startResize(e, 'bottom');
            });
        }
        
        loadResizeSizes();
    }

    function startResize(e, type) {
        e.preventDefault();
        var sidebar = document.querySelector('.re-sidebar');
        var bottomPanel = document.querySelector('.re-bottom-panel');
        var handle = type === 'sidebar'
            ? document.getElementById('re-resize-sidebar')
            : document.getElementById('re-resize-bottom');
        
        var startX = e.clientX;
        var startY = e.clientY;
        var startWidth = sidebar ? sidebar.offsetWidth : 280;
        var startHeight = bottomPanel ? bottomPanel.offsetHeight : 0;
        
        if (handle) handle.classList.add('dragging');
        document.body.classList.add(type === 'sidebar' ? 're-resizing' : 're-resizing-bottom');
        
        function onMove(ev) {
            if (type === 'sidebar') {
                var newWidth = startWidth + (ev.clientX - startX);
                newWidth = Math.max(RESIZE_MIN_SIDEBAR, Math.min(RESIZE_MAX_SIDEBAR, newWidth));
                if (sidebar) sidebar.style.width = newWidth + 'px';
            } else {
                var newHeight = startHeight - (ev.clientY - startY);
                newHeight = Math.max(RESIZE_MIN_BOTTOM, Math.min(RESIZE_MAX_BOTTOM, newHeight));
                if (bottomPanel) bottomPanel.style.height = newHeight + 'px';
            }
        }
        
        function onUp() {
            if (handle) handle.classList.remove('dragging');
            document.body.classList.remove('re-resizing', 're-resizing-bottom');
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            saveResizeSizes();
        }
        
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
    }

    function loadResizeSizes() {
        try {
            var saved = localStorage.getItem('lcta_rule_editor_sizes');
            if (saved) {
                var sizes = JSON.parse(saved);
                var sidebar = document.querySelector('.re-sidebar');
                var bottomPanel = document.querySelector('.re-bottom-panel');
                if (sizes.sidebar && sidebar) {
                    sidebar.style.width = Math.max(RESIZE_MIN_SIDEBAR,
                        Math.min(RESIZE_MAX_SIDEBAR, sizes.sidebar)) + 'px';
                }
                if (sizes.bottom && bottomPanel) {
                    bottomPanel.style.height = Math.max(RESIZE_MIN_BOTTOM,
                        Math.min(RESIZE_MAX_BOTTOM, sizes.bottom)) + 'px';
                }
            }
        } catch (e) {
            // localStorage 不可用时静默忽略
        }
    }

    function saveResizeSizes() {
        try {
            var sidebar = document.querySelector('.re-sidebar');
            var bottomPanel = document.querySelector('.re-bottom-panel');
            var sizes = {
                sidebar: sidebar ? sidebar.offsetWidth : 280,
                bottom: bottomPanel ? bottomPanel.offsetHeight : undefined
            };
            localStorage.setItem('lcta_rule_editor_sizes', JSON.stringify(sizes));
        } catch (e) {
            // localStorage 不可用时静默忽略
        }
    }

    // ═══════════════════════════════════════════════════════
    //  Confirm Dialog
    // ═══════════════════════════════════════════════════════

    function showConfirmDialog(opts) {
        return new Promise(function (resolve) {
            var overlay = document.createElement('div');
            overlay.className = 're-overlay';

            var title = opts.title || '确认';
            var message = opts.message || '';
            var saveLabel = opts.saveLabel || '保存';
            var discardLabel = opts.discardLabel || '不保存';
            var cancelLabel = opts.cancelLabel || '取消';

            overlay.innerHTML =
                '<div class="re-confirm-dialog">' +
                '<div class="re-confirm-header">' +
                '<h4><i class="fas fa-exclamation-triangle"></i> ' + escapeHtml(title) + '</h4>' +
                '</div>' +
                '<div class="re-confirm-body">' +
                '<p>' + escapeHtml(message) + '</p>' +
                '</div>' +
                '<div class="re-confirm-actions">' +
                '<button class="re-btn re-btn-primary re-confirm-save-btn">' + escapeHtml(saveLabel) + '</button>' +
                '<button class="re-btn re-confirm-discard-btn">' + escapeHtml(discardLabel) + '</button>' +
                '<button class="re-btn re-confirm-cancel-btn">' + escapeHtml(cancelLabel) + '</button>' +
                '</div>' +
                '</div>';

            document.body.appendChild(overlay);

            function cleanup() {
                document.removeEventListener('keydown', onKey);
                if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
            }

            overlay.querySelector('.re-confirm-save-btn').addEventListener('click', function () {
                cleanup(); resolve('save');
            });
            overlay.querySelector('.re-confirm-discard-btn').addEventListener('click', function () {
                cleanup(); resolve('discard');
            });
            overlay.querySelector('.re-confirm-cancel-btn').addEventListener('click', function () {
                cleanup(); resolve('cancel');
            });
            overlay.addEventListener('click', function (e) {
                if (e.target === overlay) { cleanup(); resolve('cancel'); }
            });
            function onKey(e) {
                if (e.key === 'Escape') {
                    cleanup(); resolve('cancel');
                }
            }
            document.addEventListener('keydown', onKey);
        });
    }

    window.addEventListener('beforeunload', function () {
        if (state._rulesetDirty) {
            _autoPersistRuleset();
        }
    });

    // 页面隐藏（最小化/切走）时提前触发保存，给异步保存留出完成时间
    document.addEventListener('visibilitychange', function () {
        if (document.hidden && state._rulesetDirty) {
            _autoPersistRuleset();
        }
    });

    document.addEventListener('DOMContentLoaded', init);
})();
