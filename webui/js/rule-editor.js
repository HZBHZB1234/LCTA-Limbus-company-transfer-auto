(function () {
    'use strict';

    const FILE_PREFIX_RULES = [
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
    const CATEGORY_ORDER = FILE_PREFIX_RULES.map(function (r) { return r[1]; }).concat(['Other']);

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
        fileCache: new Map(),
        advancedContentView: null,
        selectedFieldPath: null,
        selectedItemId: null,
        autocomplete: null,
        advancedEditor: null,
        smartChanges: [],
        smartGenOverlay: null,
        smartGenGroups: null,
        templates: [],
        lastPreviewRule: null,
        // File editing mode state
        fileEditor: null,
        fileOriginalContent: null,
        fileOriginalParsed: null,
        pendingChanges: [],
        // Dirty state
        isDirty: false
    };

    const CATEGORY_FILE_PATTERNS = {
        'Skill': 'Skill.*\\.json$', 'Bufs': 'Bufs.*\\.json$',
        'BattleSpeechBubbleDlg': 'BattleSpeechBubbleDlg.*\\.json$',
        'Egos': '(Skills_Ego_Personality|Egos).*\\.json$',
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

    /** init — bind events, prime UI, then load data once pywebview is ready. */
    function init() {
        bindEvents();
        populateSimpleFileSelect();
        switchTab('file-list');
        switchMainTab('file-edit');
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
        await Promise.all([loadLangFiles(), loadRulesets(), initSimpleFileSelect(), loadTemplates()]);
        syncAdvancedFromRuleset();
        syncThemeFromMain();
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
        renderRulesPreview();
        syncAdvancedFromRuleset();
    }

    async function openFile(relativePath) {
        if (!relativePath) return;
        // 未保存更改时提示
        if (state.isDirty && state.currentFile !== relativePath) {
            if (!window.confirm('当前文件有未保存的更改，是否放弃更改并打开新文件？')) return;
        }
        const api = getApi();
        if (!api) return warnNoApi();
        if (state.fileCache.has(relativePath)) {
            const cached = state.fileCache.get(relativePath);
            applyFileContent(relativePath, cached.raw, cached.parsed, cached.category);
            return;
        }
        try {
            const res = await api.get_file_content(relativePath);
            if (res && res.error) {
                console.warn('[rule-editor] openFile error:', res.error);
                $i('re-current-file').textContent = relativePath;
                $i('re-content-simple').innerHTML = '<div class="re-empty-state">⚠️ ' + escapeHtml(res.error) + '</div>';
                return;
            }
            const raw = res ? res.raw : null;
            const parsed = res ? res.parsed : null;
            const category = (res && res.file_classification) || classifyPath(relativePath).category;
            state.fileCache.set(relativePath, { raw: raw, parsed: parsed, category: category });
            applyFileContent(relativePath, raw, parsed, category);
        } catch (e) {
            console.error('[rule-editor] openFile failed:', e);
        }
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
                html += '<div class="re-file-item" data-path="' + escapeAttr(f) +
                    '" title="双击打开: ' + escapeAttr(f) + '">' + escapeHtml(f) + '</div>';
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
            const aimFile = rule.aimFile || 'no aimFile';
            let conds = rule.conditions;
            if (!conds && (rule.trigger || rule.aim)) conds = [rule];
            let targetField = '?';
            if (conds && conds[0]) {
                targetField = conds[0].aim || (conds[0].trigger ? conds[0].trigger.aim : '') || '?';
            }
            let actionStr = '';
            if (Array.isArray(rule.action) && rule.action.length) {
                actionStr = rule.action.map(function (a) {
                    if (a && 'from' in a && 'to' in a) return escapeHtml(String(a.from)) + '→' + escapeHtml(String(a.to));
                    return escapeHtml(JSON.stringify(a));
                }).join(', ');
            }
            html += '<div class="re-rule-summary">' +
                '<span class="re-rule-index">#' + (i + 1) + '</span>' +
                '<span class="re-rule-summary-text">' + escapeHtml(aimFile) + ' → ' + escapeHtml(targetField) +
                (actionStr ? ' {' + actionStr + '}' : '') + '</span>' +
                '<button class="re-btn re-btn-sm re-btn-danger re-remove-rule-btn" data-idx="' + i + '" title="移除规则">✕</button>' +
                '</div>';
        }
        container.innerHTML = html;
    }

    function filterFilesByKeyword(keyword) {
        if (!keyword.trim()) {
            renderFileList(state.langFiles);
            return;
        }
        let kw = keyword.toLowerCase();
        let filtered = [];
        for (let i = 0; i < state.langFiles.length; i++) {
            if (state.langFiles[i].toLowerCase().indexOf(kw) !== -1) {
                filtered.push(state.langFiles[i]);
            }
        }
        renderFileList(filtered);
        let hint = $i('re-search-hint');
        if (hint) {
            if (filtered.length) {
                hint.className = 're-search-hint re-search-hint-file';
                hint.textContent = '🔍 文件名匹配: ' + filtered.length + ' 个文件';
                hint.style.display = '';
            } else {
                hint.className = 're-search-hint';
                hint.textContent = '未找到文件名匹配，点击「搜索」查找文件内容';
                hint.style.display = '';
            }
        }
        return filtered;
    }

    async function performSearch() {
        let api = getApi();
        let input = $i('re-file-search');
        let keyword = input ? input.value : '';
        let cb = $i('re-case-sensitive');
        let caseSensitive = !!(cb && cb.checked);
        if (!keyword.trim()) { clearSearch(); return; }
        // First try filename filter
        let filtered = filterFilesByKeyword(keyword);
        if (filtered.length) {
            switchTab('file-list');
            return;
        }
        // No filename matches, do full-text content search
        if (!api) return warnNoApi();
        setSearchHint('content', '正在搜索文件内容...');
        try {
            let res = await api.search_files(keyword, caseSensitive);
            if (res && res.results_by_category) {
                state.searchResults = res.results_by_category;
                state.searchTotal = res.total_matches || 0;
            } else {
                state.searchResults = {};
                state.searchTotal = 0;
            }
        } catch (e) {
            console.error('[rule-editor] performSearch failed:', e);
            state.searchResults = {};
            state.searchTotal = 0;
        }
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
        const items = container.querySelectorAll('.re-search-item');
        for (let i = 0; i < items.length; i++) {
            items[i].addEventListener('dblclick', (function (el) {
                return function () { openFile(el.dataset.path); };
            })(items[i]));
        }
    }

    function clearSearch() {
        state.searchResults = null;
        state.searchTotal = 0;
        const input = $i('re-file-search');
        if (input) input.value = '';
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
        if (fileListC) fileListC.style.display = tab === 'file-list' ? '' : 'none';
        if (searchC) searchC.style.display = tab === 'search-results' ? '' : 'none';
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
        state.activeMainTab = tab;
        const tabs = document.querySelectorAll('.re-main-tab');
        for (let i = 0; i < tabs.length; i++) {
            tabs[i].classList.toggle('active', tabs[i].dataset.maintab === tab);
        }
        const fePanel = $i('re-file-edit-panel');
        const rePanel = $i('re-ruleset-edit-panel');
        if (fePanel) fePanel.style.display = tab === 'file-edit' ? '' : 'none';
        if (rePanel) rePanel.style.display = tab === 'ruleset-edit' ? '' : 'none';
        // Hide bottom preview panel in file-edit mode
        const bottomPanel = document.querySelector('.re-bottom-panel');
        if (bottomPanel) {
            bottomPanel.style.display = tab === 'file-edit' ? 'none' : '';
        }
        if (tab === 'file-edit' && state.currentFile) {
            loadFileIntoEditor(state.currentFile);
        } else if (tab === 'ruleset-edit') {
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
                filterFilesByKeyword(searchInput.value);
            });
            searchInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter') {
                    e.preventDefault();
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
        const smartBtn = $i('re-smart-gen-btn');
        if (smartBtn) smartBtn.addEventListener('click', openSmartGeneration);

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
            if (btn) { const idx = parseInt(btn.dataset.idx, 10); if (!isNaN(idx)) removeRule(idx); }
        });

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && state.smartGenOverlay) closeSmartGenDialog();
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
        const api = getApi();
        if (!api || !api.save_ruleset) return warnNoApi();
        try {
            const res = await api.save_ruleset(state.currentRuleset.name, state.currentRuleset);
            if (res && res.success === false) showToast('保存失败: ' + (res.error || ''), 'error');
            else showToast('规则集已保存', 'success');
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
            await loadRulesets();
            renderRulesPreview();
            syncAdvancedFromRuleset();
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
        if (!selection) return '.*\\.json$';
        if (CATEGORY_FILE_PATTERNS[selection]) return CATEGORY_FILE_PATTERNS[selection];
        if (/[.*+?^${}()|[\]\\]/.test(selection)) return selection;
        return escapeRegex(selection) + '.*\\.json$';
    }

    function categoryToPattern(catName) {
        for (let i = 0; i < FILE_PREFIX_RULES.length; i++) {
            if (FILE_PREFIX_RULES[i][1] === catName) {
                const prefix = FILE_PREFIX_RULES[i][0];
                return CATEGORY_FILE_PATTERNS[prefix] || (escapeRegex(prefix) + '.*\\.json$');
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
            const value = CATEGORY_FILE_PATTERNS[prefix] || (prefix + '.*\\.json$');
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
        const field_path = fieldEl ? (fieldEl.value.trim() || 'desc') : 'desc';
        return {
            file_pattern: file_pattern,
            item_ids: item_ids,
            field_path: field_path,
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
            const fromEl = rows[i].querySelector('.re-op-from');
            const toEl = rows[i].querySelector('.re-op-to');
            const from = fromEl ? fromEl.value : '';
            const to = toEl ? toEl.value : '';
            if (from.length || to.length) out.push({ from: from, to: to });
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
            const patEl = rows[i].querySelector('.re-cond-pattern');
            const field = fieldEl ? fieldEl.value : '';
            const pattern = patEl ? patEl.value : '';
            if (field && pattern) out.push({ field: field, pattern: pattern });
        }
        return out;
    }

    function buildRuleLocally(form) {
        const aim_file = filePatternFromSelection(form.file_pattern || '');
        const item_ids = form.item_ids || [];
        const field_path = form.field_path || 'desc';
        const operations = form.operations || [];
        const extra_conditions = form.extra_conditions || [];
        const conditions = [];
        if (item_ids.length) {
            const idPattern = '^(' + item_ids.map(function (i) { return escapeRegex(String(i)); }).join('|') + ')$';
            conditions.push({
                trigger: { aim: 'dataList\\.\\d+\\.id', re: idPattern },
                aim: '[back].' + field_path
            });
        } else {
            conditions.push({ aim: 'dataList\\.\\d+\\.' + escapeRegex(field_path) });
        }
        for (let i = 0; i < extra_conditions.length; i++) {
            const ec = extra_conditions[i];
            if (ec.field && ec.pattern) {
                conditions.push({
                    trigger: { aim: 'dataList\\.\\d+\\.' + escapeRegex(ec.field), re: ec.pattern },
                    aim: '[back].' + field_path
                });
            }
        }
        const action = operations.map(function (op) { return { from: op.from, to: op.to }; });
        return { aimFile: aim_file, conditions: conditions, action: action };
    }

    function validateRuleLocally(rule) {
        const errors = [];
        if (!rule || typeof rule !== 'object') return { valid: false, errors: ['规则必须是 JSON 对象'] };
        if (!rule.aimFile) errors.push('缺少 aimFile 字段（文件匹配模式）');
        const conds = rule.conditions || [];
        if (!conds.length && !rule.aim && !rule.trigger) errors.push('缺少 conditions 或 aim 字段（定位条件）');
        const action = rule.action || [];
        if (!action.length) errors.push('缺少 action 字段（操作列表）');
        else {
            for (let i = 0; i < action.length; i++) {
                const a = action[i];
                if (!a || typeof a !== 'object') errors.push('action[' + i + '] 不是有效的操作对象');
                else if ('from' in a && !('to' in a)) errors.push('action[' + i + '] 有 from 但缺少 to');
                else if ('to' in a && !('from' in a)) errors.push('action[' + i + '] 有 to 但缺少 from');
            }
        }
        try { new RegExp(rule.aimFile || ''); } catch (e) { errors.push('aimFile 正则语法错误: ' + e.message); }
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
        state.currentRuleset.rules.push(rule);
        renderRulesPreview();
        syncAdvancedFromRuleset();
        await persistCurrentRuleset();
        showToast('已添加规则到当前规则集', 'success');
    }

    async function persistCurrentRuleset() {
        if (!state.currentRuleset || !state.currentRuleset.name) return;
        const api = getApi();
        if (!api || !api.save_ruleset) return;
        try { await api.save_ruleset(state.currentRuleset.name, state.currentRuleset); }
        catch (e) { console.error('[rule-editor] persist failed:', e); }
    }

    function removeRule(index) {
        if (!state.currentRuleset || !Array.isArray(state.currentRuleset.rules)) return;
        if (index < 0 || index >= state.currentRuleset.rules.length) return;
        state.currentRuleset.rules.splice(index, 1);
        renderRulesPreview();
        syncAdvancedFromRuleset();
        persistCurrentRuleset();
    }

    function addConditionRow() {
        const cont = $i('re-simple-conditions');
        if (!cont) return;
        const fields = ['id', 'name', 'desc', 'dlg', 'text', 'title', 'comment', 'keyword'];
        let opts = '';
        for (let i = 0; i < fields.length; i++) {
            opts += '<option value="' + escapeAttr(fields[i]) + '">' + escapeHtml(fields[i]) + '</option>';
        }
        const row = document.createElement('div');
        row.className = 're-condition-item';
        row.innerHTML = '<select class="re-cond-field">' + opts + '</select>' +
            '<input type="text" class="re-cond-pattern" placeholder="匹配正则">' +
            '<button class="re-btn re-btn-sm re-remove-cond-btn">✕</button>';
        cont.appendChild(row);
    }

    function addOperationRow() {
        const cont = $i('re-simple-operations');
        if (!cont) return;
        const row = document.createElement('div');
        row.className = 're-operation-item';
        row.innerHTML = '<input type="text" placeholder="查找" class="re-op-from">' +
            '<span>→</span>' +
            '<input type="text" placeholder="替换为" class="re-op-to">' +
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
            { name: '空规则集', template: { name: '', desc: '', rules: [] } },
            { name: '简单文本替换', template: { name: '', desc: '', rules: [{
                aimFile: 'Skill.*\\.json$',
                conditions: [{ aim: 'dataList\\.\\d+\\.desc' }],
                action: [{ from: '查找', to: '替换' }]
            }] } },
            { name: '按ID定位替换', template: { name: '', desc: '', rules: [{
                aimFile: 'Skill.*\\.json$',
                conditions: [{ trigger: { aim: 'dataList\\.\\d+\\.id', re: '^10001$' }, aim: '[back].desc' }],
                action: [{ from: '查找', to: '替换' }]
            }] } },
            { name: '颜色渐变', template: { name: '', desc: '', rules: [{
                aimFile: 'BattleSpeechBubbleDlg.*\\.json$',
                conditions: [{ aim: 'dataList\\.\\d+\\.dlg' }],
                action: [{ rate: 0.4 }]
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
            '<button class="re-btn re-btn-sm re-smart-edit-btn">✏ 编辑范围</button>' +
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
        renderRulesPreview();
        syncAdvancedFromRuleset();
        await persistCurrentRuleset();
        showToast('已添加 ' + rules.length + ' 条规则', 'success');
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

        let aimFile;
        if (sel.l1 === 'all') aimFile = '.*\\.json$';
        else if (sel.l1 === 'custom') aimFile = sel.l1Custom || '.*\\.json$';
        else if (sel.l1 === 'exact') {
            const files = (group.l1_options && group.l1_options.exact_files) || [];
            const pats = files.map(function (f) { return escapeRegex(f) + '\\.json$'; });
            aimFile = pats.length ? pats.join('|') : '.*\\.json$';
        } else if (sel.l1 === 'category') {
            const cats = sel.l1Categories.length ? sel.l1Categories :
                ((group.l1_options && group.l1_options.categories) || []).map(function (c) { return c.name; });
            const pats = cats.map(categoryToPattern);
            aimFile = pats.length ? pats.join('|') : '.*\\.json$';
        } else { aimFile = '.*\\.json$'; }

        let fields = sel.l3Fields.slice();
        if (!fields.length) fields = ((group.l3_options && group.l3_options.fields) || []).slice();
        if (!fields.length) fields = ['desc'];

        const useId = sel.l2 === 'id' && sel.l2Ids && sel.l2Ids.length;
        const idPattern = useId ? '^(' + sel.l2Ids.map(function (i) { return escapeRegex(String(i)); }).join('|') + ')$' : '';
        const exact = sel.l4 === 'exact';
        const customCond = (sel.l4 === 'custom' && sel.l4Field && sel.l4Pattern);

        rules.push(buildSmartRule(aimFile, fields, useId, idPattern, exact, customCond, sel, actionPreview));
        return rules;
    }

    function buildSmartRule(aimFile, fields, useId, idPattern, exact, customCond, sel, actionPreview) {
        const conditions = [];
        for (let i = 0; i < fields.length; i++) {
            const f = fields[i] || 'desc';
            if (useId) {
                conditions.push({
                    trigger: { aim: 'dataList\\.\\d+\\.id', re: idPattern },
                    aim: '[back].' + f
                });
            } else {
                conditions.push({ aim: 'dataList\\.\\d+\\.' + escapeRegex(f) });
            }
        }
        if (customCond) {
            conditions.push({
                trigger: { aim: 'dataList\\.\\d+\\.' + escapeRegex(sel.l4Field), re: sel.l4Pattern },
                aim: '[back].' + (fields[0] || 'desc')
            });
        }
        const action = [];
        for (let i = 0; i < actionPreview.length; i++) {
            const ap = actionPreview[i];
            const from = exact ? ('^' + ap.from + '$') : ap.from;
            action.push({ from: from, to: ap.to });
        }
        return { aimFile: aimFile, conditions: conditions, action: action };
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
        if (state.fileEditor) return state.fileEditor;
        const container = $i('re-file-editor-container');
        if (!container) return null;
        if (!window.CodeMirror || !window.CodeMirror.EditorView) {
            console.warn('[rule-editor] CodeMirror not loaded; file editor disabled');
            return null;
        }
        // Remove empty state placeholder
        const empty = container.querySelector('.re-empty-state');
        if (empty) empty.style.display = 'none';
        const CM = window.CodeMirror;

        // Status bar cursor position listener
        const statusListener = CM.EditorView.updateListener.of(function (update) {
            if (update.selectionSet) {
                const pos = update.state.selection.main.head;
                const line = update.state.doc.lineAt(pos);
                const statusEl = document.getElementById('re-status-cursor');
                if (statusEl) {
                    statusEl.textContent = '行 ' + line.number + ', 列 ' + (pos - line.from + 1);
                }
            }
            if (update.docChanged) {
                updateDirtyState();
            }
        });

        const extensions = [
            CM.basicSetup, CM.json(),
            statusListener
        ];

        try {
            state.fileEditor = new CM.EditorView({
                doc: '',
                extensions: extensions,
                parent: container
            });
        } catch (e) {
            console.error('[rule-editor] initFileEditor failed:', e);
            state.fileEditor = null;
            return null;
        }
        return state.fileEditor;
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
        const editor = state.fileEditor;
        if (!editor) return;
        const current = editor.state.doc.toString();
        const isDirty = (state.fileOriginalContent !== null && current !== state.fileOriginalContent);
        state.isDirty = isDirty;
        // 更新文件编辑标签页图标
        const tab = document.querySelector('.re-main-tab[data-maintab="file-edit"]');
        if (tab) {
            const icon = tab.querySelector('i');
            if (icon) {
                icon.className = isDirty ? 'fas fa-circle re-dirty-dot' : 'fas fa-pen';
            }
        }
        // 更新窗口标题
        document.title = (isDirty ? '● ' : '') + 'LCTA - 美化规则编辑器';
    }

    function updateFileEditTabLabel() {
        const tab = document.querySelector('.re-main-tab[data-maintab="file-edit"]');
        if (!tab) return;
        const name = state.currentFile;
        const display = name
            ? (name.length > 30 ? '...' + name.slice(-27) : name)
            : '未打开文件';
        tab.innerHTML = '<i class="fas fa-pen"></i> ' + escapeHtml(display);
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
        if (!state.currentFile) {
            showToast('请先打开一个文件', 'error');
            return;
        }
        let raw = getFileEditorDoc();
        if (!raw.trim()) {
            showToast('编辑器内容为空', 'error');
            return;
        }
        let parsed;
        try {
            parsed = JSON.parse(raw);
        } catch (e) {
            showToast('JSON 解析错误: ' + e.message, 'error');
            return;
        }
        let originalParsed = state.fileOriginalParsed;
        if (!originalParsed) {
            showToast('没有原始内容可比较（请先加载文件）', 'error');
            return;
        }
        let diffs = diffJson(originalParsed, parsed, '');
        if (!diffs.length) {
            showToast('未检测到变更', 'info');
            clearPendingChanges();
            return;
        }
        let changes = extractChangesFromDiff(diffs, state.currentFile, originalParsed);
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
        if (!state.currentFile) {
            showToast('没有打开的文件', 'error');
            return;
        }
        let raw = getFileEditorDoc();
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
        let api = getApi();
        if (!api || !api.save_file_content) return warnNoApi();
        try {
            let res = await api.save_file_content(state.currentFile, raw);
            if (res && res.success) {
                // Update cache and original
                state.fileOriginalContent = raw;
                state.isDirty = false;
                try { state.fileOriginalParsed = JSON.parse(raw); } catch (e) { void e; }
                if (state.fileCache.has(state.currentFile)) {
                    let cached = state.fileCache.get(state.currentFile);
                    cached.raw = raw;
                    try { cached.parsed = JSON.parse(raw); } catch (e) { void e; }
                }
                updateDirtyState();
                showToast('文件已保存到游戏: ' + state.currentFile, 'success');
            } else {
                showToast('保存失败: ' + ((res && res.error) || ''), 'error');
            }
        } catch (e) {
            showToast('保存异常: ' + (e && e.message ? e.message : e), 'error');
        }
    }

    function revertEditedFile() {
        if (state.fileOriginalContent != null) {
            setFileEditorDoc(state.fileOriginalContent);
            state.isDirty = false;
            clearPendingChanges();
            updateDirtyState();
            showToast('已撤销所有更改', 'info');
        } else {
            showToast('没有可撤销的版本', 'error');
        }
    }

    function refreshEditedFile() {
        let path = state.currentFile;
        if (!path) { showToast('没有打开的文件', 'error'); return; }
        // Reload from cache or backend
        if (state.fileCache.has(path)) {
            let cached = state.fileCache.get(path);
            state.currentFileRaw = cached.raw;
            state.currentFileParsed = cached.parsed;
            loadRawIntoEditor(cached.raw, cached.parsed);
            showToast('已刷新', 'info');
        } else {
            // Use openFile which will fetch from backend
            openFile(path);
        }
    }

    async function generateRulesFromChanges() {
        let changes = state.pendingChanges;
        if (!changes || !changes.length) {
            showToast('没有待处理的变更 — 请先在文件编辑中修改内容并点击「比较变更」', 'error');
            return;
        }
        // Only proceed if a ruleset is selected
        if (!state.currentRuleset || !state.currentRuleset.name) {
            // Switch to ruleset tab and prompt
            switchMainTab('ruleset-edit');
            showToast('请先选择或新建一个规则集', 'error');
            return;
        }
        // Feed changes into smart gen dialog
        state.smartChanges = changes;
        await openSmartGeneration();
    }

    document.addEventListener('DOMContentLoaded', init);
})();