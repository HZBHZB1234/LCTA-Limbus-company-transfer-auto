// ============================
// 订阅工具页（原「工具箱」，2026-10-30 对齐站点订阅语义）
// 账号登录 + 月/赛季订阅 + 名单公开目录 + 预览 + 本地安装管理
// 2026-11-01 重构：状态拆本地/在线两段、目录卡片化、已安装更新检测、任务坞
// ============================
// 设计约束（plan 10.1 / 10.6 / 2026-10-30 一键安装契约）：
//   1) **不依赖**旧 cheat_core.bin 解密门。过季后用户仍必须能停用/卸载/回滚
//      已下载的插件 —— 否则「过季就卸不掉」，等于把用户锁死。
//   2) 本地管理与在线资格**解耦**：先渲染本地快照（毫秒级），在线分片再补齐；
//      在线失败只在对应区域提示，不影响本地列表与操作。
//   3) 所有安装/启停都由 Python 侧重新校验（权限、签名、哈希、路径、游戏是否运行）；
//      JS 只传 tool_id/release_id/action，不传 URL、路径或命令。
//   4) 目录名单对游客公开（与站点一致）：逐条 access_kind/downloadable 决定
//      「安装/更新」按钮，锁定原创显示订阅引导；一键安装由签名清单驱动。
//
// 本文件只做「状态 + 动作 + 事件」；HTML 生成全部在 toolbox-views.js。

let toolboxManager = {
    _bound: false,
    _escBound: false,
    _stopped: false,

    // 状态
    _local: null,
    _online: null,
    _tasks: null,
    _tab: 'catalog',
    _query: '',
    _filter: 'all',
    _sort: 'recommended',
    _loading: { local: false, online: false },
    _seq: { local: 0, online: 0 },
    _lastOnlineAt: 0,
    _drawerItem: null,
    _dockDismissed: false,
    _challengeId: '',
    _recoveredShown: false,
    _timers: { poll: null, search: null },

    // ------------------------------------------------------------------
    // 生命周期
    // ------------------------------------------------------------------

    init() {
        // 首次进入时 preload.js 的 onSectionLoaded 与 utils.js 的导航生命周期
        // 都会调 init()：800ms 内合并成一次，避免重复打服务端。
        const now = Date.now();
        if (now - (this._lastInitAt || 0) < 800 && this._local) return;
        this._lastInitAt = now;

        this._stopped = false;
        const root = document.getElementById('toolbox-public');
        if (!root) return;
        this._bindOnce();
        this._show();

        // 本地快照立即渲染；在线部分避免来回切页时反复打服务端
        this.refreshLocal();
        if (!this._online || Date.now() - this._lastOnlineAt > 15000) {
            this.refreshOnline();
        } else {
            this._render();
        }
        this._pollTaskOnce();
    },

    stop() {
        this._stopped = true;
        this._stopTaskPoll();
        clearTimeout(this._timers.search);
        this._closeDrawer();
        // 抽屉/任务坞已挂到 body，不会随 section 隐藏而消失 —— 离开页面时主动收起
        const dock = document.getElementById('tb-taskdock');
        if (dock) dock.hidden = true;
    },

    _show() {
        const el = document.getElementById('toolbox-public');
        if (el) el.style.display = '';
    },

    // ------------------------------------------------------------------
    // 事件绑定（一次性；重绘只换 innerHTML，监听器活在容器上）
    // ------------------------------------------------------------------

    _bindOnce() {
        if (this._bound) return;
        this._bound = true;

        // 抽屉与任务坞是 fixed 定位，必须挂在 body 下：
        // .content-section 的 fadeInUp 动画带 forwards，元素长期持有 transform，
        // 会让内部的 position:fixed 相对于该区块而不是视口定位。
        this._reparent('tb-drawer');
        this._reparent('tb-taskdock');

        const root = document.getElementById('toolbox-public');
        const drawer = document.getElementById('tb-drawer');
        const dock = document.getElementById('tb-taskdock');

        [root, drawer, dock].forEach((host) => {
            if (host) host.addEventListener('click', (e) => this._onClick(e));
        });

        if (root) {
            root.querySelectorAll('[data-tb-tab]').forEach((btn) => {
                btn.addEventListener('click', () => this._setTab(btn.dataset.tbTab));
            });
            const search = document.getElementById('tb-search');
            if (search) {
                search.addEventListener('input', (e) => {
                    const value = e.target.value;
                    clearTimeout(this._timers.search);
                    this._timers.search = setTimeout(() => {
                        this._query = value;
                        this._renderCatalog(this._ctx());
                    }, 180);
                });
            }
            const filter = document.getElementById('tb-filter');
            if (filter) {
                filter.addEventListener('change', (e) => {
                    this._filter = e.target.value;
                    this._renderCatalog(this._ctx());
                });
            }
            const sort = document.getElementById('tb-sort');
            if (sort) {
                sort.addEventListener('change', (e) => {
                    this._sort = e.target.value;
                    this._renderCatalog(this._ctx());
                });
            }
        }

        if (!this._escBound) {
            this._escBound = true;
            document.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && this._drawerItem) this._closeDrawer();
            });
        }
    },

    _reparent(id) {
        const el = document.getElementById(id);
        if (el && el.parentElement !== document.body) document.body.appendChild(el);
    },

    /** 统一委托：data-tb-action + data-* 参数，避免重绘后需要重新绑定。 */
    _onClick(e) {
        const el = e.target.closest && e.target.closest('[data-tb-action]');
        if (!el) return;
        const action = el.dataset.tbAction;
        const d = el.dataset;
        switch (action) {
            case 'refresh': this.refresh(); break;
            case 'refresh-online': this.refreshOnline(true); break;
            case 'retry': this.refreshOnline(true); break;
            case 'go-account': this._setTab('account'); break;
            case 'go-runtime': this._installRuntimeFromCatalog(); break;
            case 'go-updates': this._showUpdates(); break;
            case 'preview': this._openDrawer(d.tool, d.release); break;
            case 'drawer-close': this._closeDrawer(); break;
            case 'install': this.install(d.tool, d.release, d.kind); break;
            case 'toggle': this.setEnabled(d.tool, d.enable === '1'); break;
            case 'verify': this.verify(d.tool); break;
            case 'rollback': this.rollback(d.tool); break;
            case 'uninstall': this.uninstall(d.tool); break;
            case 'open-folder': this.openFolder(d.tool); break;
            case 'open-downloads': this.openDownloads(); break;
            case 'enable-all': this.setAllEnabled(true); break;
            case 'disable-all': this.setAllEnabled(false); break;
            case 'login': this.login(); break;
            case 'logout': this.logout(); break;
            case 'sync-login': this.syncMirrorLogin(); break;
            case 'open-register': this.openSite('/register'); break;
            case 'open-forgot': this.openSite('/forgot-password'); break;
            case 'open-site': this.openSite('/toolbox'); break;
            case 'afdian-bind': this.afdianBind(); break;
            case 'afdian-refresh': this.afdianRefresh(); break;
            case 'toggle-order': this._toggleOrderRow(); break;
            case 'verify-order': this.verifyOrder(); break;
            case 'puzzle-new': this.newPuzzle(); break;
            case 'puzzle-solve': this.solvePuzzle(); break;
            case 'save-root': this.saveGameRoot(); break;
            case 'validate-root': this.validateGameRoot(); break;
            case 'check-all': this.checkAll(); break;
            case 'open-cheat': this.openCheat(); break;
            case 'task-dismiss': this._dockDismissed = true; this._renderTaskDock(); break;
            default: break;
        }
    },

    async _call(method, ...args) {
        try {
            const fn = pywebview.api[method];
            if (typeof fn !== 'function') {
                return { success: false, code: 'bridge_missing', message: '当前版本不支持该操作' };
            }
            return await fn.apply(pywebview.api, args);
        } catch (e) {
            return { success: false, code: 'bridge_error', message: String(e) };
        }
    },

    // ------------------------------------------------------------------
    // 数据刷新：本地（毫秒级）→ 在线（分片）
    // ------------------------------------------------------------------

    async refresh() {
        await this.refreshLocal();
        await this.refreshOnline(true);
    },

    async refreshLocal() {
        const token = ++this._seq.local;
        this._loading.local = true;
        this._render();
        const res = await this._call('toolbox_status_local');
        if (this._stopped || token !== this._seq.local) return;
        this._loading.local = false;
        if (res && res.success) {
            this._local = res.data || {};
        } else {
            this._local = { local_error: (res && res.message) || '读取本地状态失败' };
        }
        this._render();
        this._maybeShowRecovered();
    },

    async refreshOnline(force = false) {
        const token = ++this._seq.online;
        this._loading.online = true;
        this._render();
        const res = await this._call('toolbox_status_online', !!force);
        if (this._stopped || token !== this._seq.online) return;
        this._loading.online = false;
        if (res && res.success) {
            this._online = res.data || {};
            this._lastOnlineAt = Date.now();
        } else {
            this._online = { errors: { api: { message: (res && res.message) || '无法获取在线状态' } } };
        }
        this._render();
        this._checkSession();
    },

    _checkSession() {
        const errors = (this._online && this._online.errors) || {};
        const accessErr = errors.access;
        if (accessErr && accessErr.code === 'auth_required') {
            this._toast('登录已失效，请重新登录', true);
        }
    },

    _maybeShowRecovered() {
        const recovered = this._local && this._local.recovered;
        if (!recovered || this._recoveredShown) return;
        this._recoveredShown = true;
        const n = (recovered.restored || []).length + (recovered.deleted || []).length;
        this._toast(`检测到上次安装未完成，已自动恢复到安装前状态（${n} 个文件）`);
    },

    // ------------------------------------------------------------------
    // 渲染
    // ------------------------------------------------------------------

    _ctx() {
        const local = this._local || {};
        const online = this._online || {};
        return {
            local,
            online,
            loading: this._loading,
            query: this._query,
            filter: this._filter,
            sort: this._sort,
            protocol_version: local.protocol_version || online.protocol_version || 0,
            game_root: local.game_root,
            game_running: local.game_running,
            local_error: local.local_error,
            mirror_auth_available: local.mirror_auth_available,
            base_url: online.base_url || '',
        };
    },

    _render() {
        if (this._stopped) return;
        const ctx = this._ctx();
        this._renderStatusbar(ctx);
        this._renderCatalog(ctx);
        this._renderInstalled(ctx);
        this._renderAccount(ctx);
        this._renderSettings(ctx);
        this._renderTaskDock();
        this._syncBadge(ctx);
    },

    _renderStatusbar(ctx) {
        const el = document.getElementById('tb-statusbar');
        if (!el || typeof ToolboxViews === 'undefined') return;
        el.innerHTML = ToolboxViews.statusbar(ctx);
    },

    _renderCatalog(ctx) {
        const el = document.getElementById('tb-catalog-body');
        if (!el || typeof ToolboxViews === 'undefined') return;
        el.innerHTML = ToolboxViews.catalog(ctx);
    },

    _renderInstalled(ctx) {
        const rt = document.getElementById('tb-runtime-body');
        const body = document.getElementById('tb-installed-body');
        const summary = document.getElementById('tb-installed-summary');
        if (!body || typeof ToolboxViews === 'undefined') return;
        if (rt) rt.innerHTML = ToolboxViews.runtimeCard(ctx);
        body.innerHTML = ToolboxViews.installed(ctx);
        if (summary) summary.textContent = ToolboxViews.installedSummary(ctx);
    },

    _renderAccount(ctx) {
        const box = document.getElementById('tb-account-body');
        if (!box || typeof ToolboxViews === 'undefined') return;
        const keep = this._captureValues([
            'tb-login-identifier', 'tb-login-password', 'tb-order-no', 'tb-puzzle-answer',
        ]);
        // 折叠区状态与谜题题面也要跨重绘保留（否则任何刷新都把用户展开的面板收走）
        const orderRow = document.getElementById('tb-order-row');
        const orderOpen = !!(orderRow && orderRow.style.display !== 'none');
        const puzzleBody = document.getElementById('tb-puzzle-body');
        const puzzleHTML = puzzleBody ? puzzleBody.innerHTML : '';

        const html = ToolboxViews.account(ctx);
        if (box.innerHTML !== html) box.innerHTML = html;
        this._restoreValues(keep);

        const row = document.getElementById('tb-order-row');
        if (row && orderOpen) row.style.display = '';
        const body = document.getElementById('tb-puzzle-body');
        if (body && puzzleHTML) body.innerHTML = puzzleHTML;
    },

    _renderSettings(ctx) {
        if (typeof ToolboxViews === 'undefined') return;
        const diag = document.getElementById('tb-diagnostics');
        if (diag) diag.innerHTML = ToolboxViews.settings(ctx);
        const status = document.getElementById('tb-root-status');
        if (status) status.innerHTML = ToolboxViews.rootStatus(ctx);

        const input = document.getElementById('tb-game-root');
        if (input && !input.value && ctx.game_root) input.value = ctx.game_root;
    },

    _renderTaskDock() {
        const dock = document.getElementById('tb-taskdock');
        if (!dock || typeof ToolboxViews === 'undefined') return;
        const snap = this._tasks;
        const has = !!(snap && (snap.current || (snap.history && snap.history.length)));
        if (!has || this._dockDismissed) {
            dock.hidden = true;
            return;
        }
        dock.innerHTML = ToolboxViews.taskDock(snap);
        dock.hidden = false;
    },

    _syncBadge(ctx) {
        const badge = document.getElementById('tb-badge-installed');
        if (!badge) return;
        const local = (ctx.local && ctx.local.local) || null;
        const count = local ? (local.plugins || []).length + (local.packages || []).length : 0;
        badge.textContent = count ? String(count) : '';
        badge.hidden = !count;
    },

    _captureValues(ids) {
        const out = {};
        ids.forEach((id) => {
            const el = document.getElementById(id);
            if (el) out[id] = el.value;
        });
        return out;
    },

    _restoreValues(values) {
        Object.keys(values || {}).forEach((id) => {
            const el = document.getElementById(id);
            if (el && values[id] != null) el.value = values[id];
        });
    },

    _setTab(name) {
        this._tab = name;
        const root = document.getElementById('toolbox-public');
        if (!root) return;
        root.querySelectorAll('[data-tb-tab]').forEach((btn) => {
            const on = btn.dataset.tbTab === name;
            btn.classList.toggle('is-active', on);
            btn.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        root.querySelectorAll('[data-tb-view]').forEach((view) => {
            view.hidden = view.dataset.tbView !== name;
        });
        // 本机授权状态只在该视图可见时才需要（避免每次刷新都多打一次接口）
        if (name === 'account') this.authzRefresh();
    },

    // ------------------------------------------------------------------
    // 目录：详情 / 主操作
    // ------------------------------------------------------------------

    _findItem(toolId, releaseId) {
        const items = (this._online && this._online.catalog && this._online.catalog.items) || [];
        return items.find((x) => String(x.tool_id) === String(toolId)
            && (releaseId == null || String(x.release_id) === String(releaseId))) || null;
    },

    _openDrawer(toolId, releaseId) {
        const item = this._findItem(toolId, releaseId);
        if (!item) {
            this._toast('目录条目已变化，请刷新后重试', true);
            return;
        }
        this._drawerItem = item;
        const view = ToolboxViews.drawer(item, this._ctx());
        const drawer = document.getElementById('tb-drawer');
        const title = document.getElementById('tb-drawer-title');
        const body = document.getElementById('tb-drawer-body');
        const foot = document.getElementById('tb-drawer-foot');
        if (!drawer || !body || !foot) return;
        if (title) title.textContent = view.title;
        body.innerHTML = view.body;
        foot.innerHTML = view.foot;
        drawer.hidden = false;
    },

    _closeDrawer() {
        this._drawerItem = null;
        const drawer = document.getElementById('tb-drawer');
        if (drawer) drawer.hidden = true;
    },

    /** 首屏主操作「安装底座」：直接用目录里的底座条目，避免让用户自己找。 */
    _installRuntimeFromCatalog() {
        const items = (this._online && this._online.catalog && this._online.catalog.items) || [];
        const runtime = items.find((it) => it.install_kind === 'runtime_zip_root'
            || it.resource_kind === 'runtime');
        if (runtime && runtime.downloadable) {
            this.install(runtime.tool_id, runtime.release_id, 'runtime_zip_root');
            return;
        }
        this._setTab('catalog');
        this._toast(runtime
            ? '底座条目当前不可下载（需订阅），请先处理订阅'
            : '目录里暂未发布底座，请稍后刷新', true);
    },

    _showUpdates() {
        this._setTab('catalog');
        this._filter = 'update';
        const sel = document.getElementById('tb-filter');
        if (sel) sel.value = 'update';
        this._renderCatalog(this._ctx());
    },

    // ------------------------------------------------------------------
    // 安装 / 下载
    // ------------------------------------------------------------------

    _newProgress(title) {
        const modal = new ProgressModal(title);
        // 安装/下载是不可暂停的后端任务：隐藏暂停按钮；把「取消」换成「关闭」，
        // 关闭只收起进度窗，任务继续在后台完成（结束后仍有 toast + 任务坞）。
        const pauseBtn = document.getElementById(`pause-btn-${modal.id}`);
        if (pauseBtn) pauseBtn.style.display = 'none';
        const cancelBtn = document.getElementById(`cancel-btn-${modal.id}`);
        if (cancelBtn) {
            const closeBtn = cancelBtn.cloneNode(true);
            closeBtn.textContent = '关闭';
            closeBtn.addEventListener('click', () => modal.close());
            cancelBtn.replaceWith(closeBtn);
        }
        return modal;
    },

    async install(toolId, releaseId, installKind) {
        const item = this._findItem(toolId, releaseId) || {};
        const label = installKind === 'download_only' ? '下载'
            : installKind === 'runtime_zip_root' ? '安装底座'
                : installKind === 'game_relative_files' ? '安装文件包' : '安装/更新';
        const name = item.name_zh || item.tool_name || toolId;
        const where = item.target_dir ? `\n安装位置：${item.target_dir}` : '';
        const body = installKind === 'download_only'
            ? '只下载到系统「下载」目录，不会写入游戏目录。'
            : '请确认游戏已关闭。安装由签名清单驱动，逐文件校验后写入。';
        if (!confirm(`${label}「${name}」？\n${body}${where}`)) return;

        const modal = this._newProgress(`${label}：${name}`);
        modal.addLog('正在校验清单与下载资格…');
        this._dockDismissed = false;
        this._startTaskPoll();
        try {
            let res = await this._call('toolbox_install_any', toolId, releaseId, false, modal.id);
            if (res && !res.success && /非 LCTA 管理的 BepInEx/.test(res.message || '')) {
                modal.addLog(res.message);
                if (confirm(`${res.message}\n\n确定继续并覆盖吗？`)) {
                    res = await this._call('toolbox_install_any', toolId, releaseId, true, modal.id);
                } else {
                    res = { success: false, message: '已取消（检测到非 LCTA 管理的 BepInEx）' };
                }
            }
            if (res && res.success) {
                const saved = res.data && res.data.save_paths;
                modal.complete(true, saved && saved.length ? `已下载到：${saved[0]}` : '操作完成');
                this._toast(saved && saved.length ? '已下载到系统下载目录' : '操作完成');
            } else {
                modal.complete(false, (res && res.message) || '操作失败');
                this._toast((res && res.message) || '操作失败', true);
            }
        } finally {
            this._stopTaskPoll();
            await this._pollTaskOnce();
            await this.refreshLocal();
        }
    },

    async installRuntime(toolId, releaseId) {
        // 兼容旧调用：统一走通用分发
        return this.install(toolId, releaseId, 'runtime_zip_root');
    },

    /** Mod 镜像站 → 主窗口：站点只传 id 与动作，这里重新校验与执行。 */
    async installFromMirror(payload) {
        if (!payload) return;
        const action = payload.action || 'install';
        const modal = this._newProgress(action === 'download-file' ? '下载订阅工具文件' : '从镜像站安装');
        modal.addLog('正在校验请求与签名清单…');
        this._dockDismissed = false;
        this._startTaskPoll();
        try {
            let res;
            if (action === 'download-file') {
                res = await this._call(
                    'toolbox_download_file',
                    payload.tool_id,
                    payload.release_id,
                    payload.file_name,
                    payload.sha256,
                    modal.id,
                );
            } else {
                res = await this._call('toolbox_install_any', payload.tool_id, payload.release_id, false, modal.id);
                if (res && !res.success && /非 LCTA 管理的 BepInEx/.test(res.message || '')) {
                    modal.addLog(res.message);
                    if (confirm(`${res.message}\n\n确定继续并覆盖吗？`)) {
                        res = await this._call(
                            'toolbox_install_any', payload.tool_id, payload.release_id, true, modal.id,
                        );
                    }
                }
            }
            if (res && res.success) {
                const saved = res.data && res.data.save_paths;
                modal.complete(true, saved && saved.length ? `已保存到：${saved[0]}` : '操作完成');
                this._toast(saved && saved.length ? '已保存到系统下载目录' : '操作完成');
            } else {
                modal.complete(false, (res && res.message) || '操作失败');
                this._toast((res && res.message) || '操作失败', true);
            }
        } catch (e) {
            modal.complete(false, String(e));
            this._toast(String(e), true);
        } finally {
            this._stopTaskPoll();
            await this._pollTaskOnce();
            await this.refreshLocal();
        }
    },

    // ------------------------------------------------------------------
    // 任务坞
    // ------------------------------------------------------------------

    _startTaskPoll() {
        this._stopTaskPoll();
        this._timers.poll = setInterval(() => this._pollTaskOnce(), 700);
    },

    _stopTaskPoll() {
        if (this._timers.poll) {
            clearInterval(this._timers.poll);
            this._timers.poll = null;
        }
    },

    async _pollTaskOnce() {
        const res = await this._call('toolbox_task_status');
        if (this._stopped) return;
        if (res && res.success) {
            this._tasks = res.data;
            this._renderTaskDock();
        }
    },

    // ------------------------------------------------------------------
    // 本地管理
    // ------------------------------------------------------------------

    async setEnabled(toolId, enabled) {
        const res = await this._call('toolbox_set_enabled', toolId, !!enabled);
        this._toast(res && res.success ? (enabled ? '已启用' : '已停用') : (res && res.message),
            !(res && res.success));
        await this.refreshLocal();
    },

    async setAllEnabled(enabled) {
        const local = (this._local && this._local.local) || {};
        const plugins = local.plugins || [];
        if (!plugins.length) return;
        const targets = plugins.filter((p) => !!p.enabled !== !!enabled);
        if (!targets.length) {
            this._toast(enabled ? '所有插件都已启用' : '所有插件都已停用');
            return;
        }
        if (!confirm(`${enabled ? '启用' : '停用'}全部 ${targets.length} 个插件？`)) return;
        let failed = 0;
        for (const p of targets) {
            const res = await this._call('toolbox_set_enabled', p.tool_id, !!enabled);
            if (!res || !res.success) failed += 1;
        }
        this._toast(failed ? `${failed} 个插件操作失败` : '已全部' + (enabled ? '启用' : '停用'), !!failed);
        await this.refreshLocal();
    },

    async verify(toolId) {
        const res = await this._call('toolbox_verify_integrity', toolId);
        if (res && res.success && res.data) {
            const d = res.data;
            if (d.ok) {
                this._toast('文件完整，未发现问题');
            } else {
                const parts = [];
                if (d.missing && d.missing.length) parts.push(`缺失 ${d.missing.length} 个文件（可能被杀毒隔离）`);
                if (d.modified && d.modified.length) parts.push(`被修改 ${d.modified.length} 个文件`);
                this._toast(`需要修复：${parts.join('；')}`, true);
            }
        } else {
            this._toast((res && res.message) || '检查失败', true);
        }
    },

    async checkAll() {
        const local = (this._local && this._local.local) || {};
        const targets = [
            ...(local.plugins || []).map((p) => ({ id: p.tool_id, label: p.tool_id, kind: '插件' })),
            ...(local.packages || []).map((p) => ({ id: p.tool_id, label: p.tool_id, kind: '文件包' })),
        ];
        if (!targets.length) {
            this._toast('没有已安装内容可检查');
            return;
        }
        const modal = new ModalWindow('完整性检查', {
            showProgress: false, showCancelButton: false, showMinimizeButton: false, showLog: true,
        });
        const statusEl = document.getElementById(`modal-status-${modal.id}`);
        if (statusEl) statusEl.textContent = `正在检查 ${targets.length} 项…`;
        modal.addLog(`开始检查 ${targets.length} 项已安装内容`);
        let bad = 0;
        for (const t of targets) {
            const res = await this._call('toolbox_verify_integrity', t.id);
            if (res && res.success && res.data && res.data.ok) {
                modal.addLog(`✓ ${t.kind} ${t.label}：完整`);
            } else {
                bad += 1;
                const detail = res && res.data
                    ? [
                        (res.data.missing || []).length ? `缺失 ${res.data.missing.length}` : '',
                        (res.data.modified || []).length ? `被修改 ${res.data.modified.length}` : '',
                    ].filter(Boolean).join('；')
                    : ((res && res.message) || '检查失败');
                modal.addLog(`✗ ${t.kind} ${t.label}：${detail || '异常'}`);
            }
        }
        const footer = document.getElementById(`modal-footer-${modal.id}`);
        if (footer) {
            footer.innerHTML = '<button class="tb-btn" id="tb-check-close">关闭</button>';
            const btn = document.getElementById('tb-check-close');
            if (btn) btn.addEventListener('click', () => modal.close());
        }
        if (statusEl) {
            statusEl.textContent = bad ? `${bad} 项需要修复，其余正常` : '全部完整，未发现问题';
        }
        this._toast(bad ? `${bad} 项需要修复` : '全部完整，未发现问题', !!bad);
    },

    async rollback(toolId) {
        if (!confirm('回滚到本地备份？当前文件会被替换为备份内容。')) return;
        const res = await this._call('toolbox_rollback', toolId);
        this._toast(res && res.success ? '已回滚到本地备份' : (res && res.message), !(res && res.success));
        await this.refreshLocal();
    },

    async uninstall(toolId) {
        const modal = new ModalWindow('卸载内容', {
            showProgress: false, showCancelButton: false, showMinimizeButton: false, showLog: false,
        });
        const statusEl = document.getElementById(`modal-status-${modal.id}`);
        if (statusEl) {
            statusEl.innerHTML = `<p style="margin:0 0 8px">只移除 LCTA 管理的文件，你自己的文件与配置会保留。</p>
                <label class="checkbox-container">
                    <input type="checkbox" id="tb-uninstall-cfg-${modal.id}">
                    <span class="checkmark"></span> 同时删除该插件在 BepInEx 里的配置
                </label>`;
        }
        const footer = document.getElementById(`modal-footer-${modal.id}`);
        if (footer) {
            footer.innerHTML = `<button class="tb-btn tb-btn--danger" id="tb-uninstall-ok-${modal.id}">确认卸载</button>
                <button class="tb-btn" id="tb-uninstall-no-${modal.id}">取消</button>`;
            const cancel = document.getElementById(`tb-uninstall-no-${modal.id}`);
            if (cancel) cancel.addEventListener('click', () => modal.close());
            const ok = document.getElementById(`tb-uninstall-ok-${modal.id}`);
            if (ok) {
                ok.addEventListener('click', async () => {
                    const cfg = document.getElementById(`tb-uninstall-cfg-${modal.id}`);
                    const removeConfig = !!(cfg && cfg.checked);
                    modal.close();
                    const res = await this._call('toolbox_uninstall', toolId, removeConfig);
                    this._toast(res && res.success ? '已卸载' : (res && res.message), !(res && res.success));
                    await this.refreshLocal();
                });
            }
        }
    },

    async openFolder(toolId) {
        const res = await this._call('toolbox_open_folder', toolId || '');
        if (!res || !res.success) this._toast((res && res.message) || '打开失败', true);
    },

    async openDownloads() {
        const res = await this._call('toolbox_open_downloads');
        if (!res || !res.success) this._toast((res && res.message) || '打开失败', true);
    },

    async saveGameRoot() {
        const input = document.getElementById('tb-game-root');
        if (!input) return;
        const value = (input.value || '').trim();
        if (!value) {
            this._toast('请填写 Limbus Company 安装目录', true);
            return;
        }
        const res = await this._call('toolbox_set_game_root', value);
        if (res && res.success) {
            const saved = (res.data && res.data.game_root) || value;
            input.value = saved;
            this._toast('游戏目录已保存');
            await this.refreshLocal();
        } else {
            this._toast((res && res.message) || '目录无效', true);
        }
    },

    async validateGameRoot() {
        const input = document.getElementById('tb-game-root');
        if (!input) return;
        const value = (input.value || '').trim();
        if (!value) {
            this._toast('请填写 Limbus Company 安装目录', true);
            return;
        }
        const res = await this._call('toolbox_validate_game_root', value);
        if (res && res.success) {
            this._toast('目录有效，可以保存');
        } else {
            this._toast((res && res.message) || '目录无效', true);
        }
    },

    // ------------------------------------------------------------------
    // 账号 / 订阅
    // ------------------------------------------------------------------

    async login() {
        const idEl = document.getElementById('tb-login-identifier');
        const pwdEl = document.getElementById('tb-login-password');
        const identifier = ((idEl && idEl.value) || '').trim();
        const password = (pwdEl && pwdEl.value) || '';
        if (!identifier || !password) {
            this._toast('请输入用户名/邮箱与密码', true);
            return;
        }
        this._toast('正在登录…');
        const res = await this._call('toolbox_login', identifier, password);
        if (res && res.success) {
            this._toast('登录成功');
            if (pwdEl) pwdEl.value = '';
            await this.refresh();
        } else {
            this._toast((res && res.message) || '登录失败', true);
        }
    },

    async logout() {
        if (!confirm('登出资源站账号？本地已安装内容不受影响。')) return;
        const res = await this._call('toolbox_logout');
        this._toast(res && res.success ? '已登出' : (res && res.message), !(res && res.success));
        await this.refresh();
    },

    async syncMirrorLogin() {
        const res = await this._call('toolbox_sync_mirror_login', true);
        if (res && res.success) {
            const d = res.data || {};
            this._toast(d.message || (d.synced ? '已从镜像站同步登录' : '客户端已有登录会话'));
            await this.refresh();
        } else {
            this._toast((res && res.message) || '同步失败', true);
        }
    },

    async openSite(path) {
        const res = await this._call('toolbox_open_site', path);
        if (res && res.success) {
            this._toast('已在系统浏览器打开资源站');
        } else {
            this._toast((res && res.message) || '打开失败', true);
        }
    },

    async afdianBind() {
        const res = await this._call('toolbox_afdian_bind_url');
        if (res && res.success) {
            this._toast('已在系统浏览器打开爱发电授权页，完成授权后回到本页点「刷新订阅状态」');
        } else {
            this._toast((res && res.message) || '打开授权页失败', true);
        }
    },

    async afdianRefresh() {
        const res = await this._call('toolbox_afdian_refresh');
        if (res && res.success) {
            const s = res.data || {};
            this._toast(s.verified ? `已核验 ${s.verified} 笔有效订阅` : '暂未查询到新的有效订阅');
        } else {
            this._toast((res && res.message) || '刷新失败', true);
        }
        await this.refreshOnline(true);
    },

    _toggleOrderRow() {
        const row = document.getElementById('tb-order-row');
        if (!row) return;
        row.style.display = row.style.display === 'none' ? '' : 'none';
        if (row.style.display !== 'none') {
            const input = document.getElementById('tb-order-no');
            if (input) input.focus();
        }
    },

    async verifyOrder() {
        const el = document.getElementById('tb-order-no');
        const orderNo = ((el && el.value) || '').trim();
        if (!orderNo) {
            this._toast('请填写爱发电订单号', true);
            return;
        }
        const res = await this._call('toolbox_verify_order', orderNo);
        this._toast(res && res.success ? '订单已核验' : (res && res.message), !(res && res.success));
        await this.refreshOnline(true);
    },

    async newPuzzle() {
        const res = await this._call('toolbox_new_challenge');
        const body = document.getElementById('tb-puzzle-body');
        if (!res || !res.success) {
            if (body) body.innerHTML = `<p class="form-hint" style="margin:0">${this._esc((res && res.message) || '获取失败')}</p>`;
            return;
        }
        const ch = res.data || {};
        this._challengeId = ch.challenge_id || '';
        if (body) {
            body.innerHTML = `<textarea id="tb-puzzle-material" readonly
                style="width:100%;height:160px;font-family:monospace;font-size:12px">${this._esc(ch.material || '')}</textarea>
                <div class="tb-inline" style="margin-top:6px">
                    <input type="text" id="tb-puzzle-answer" placeholder="序列号答案" style="max-width:240px"
                           data-tb-enter="puzzle">
                    <button class="tb-btn tb-btn--sm tb-btn--primary" data-tb-action="puzzle-solve">提交答案</button>
                </div>`;
        }
    },

    async solvePuzzle() {
        const el = document.getElementById('tb-puzzle-answer');
        const answer = ((el && el.value) || '').trim();
        if (!this._challengeId || !answer) return;
        const res = await this._call('toolbox_solve', this._challengeId, answer);
        this._toast(res && res.success ? '答案已提交' : (res && res.message), !(res && res.success));
        await this.refreshOnline(true);
    },

    // ------------------------------------------------------------------
    // 本机授权（TPM）
    // ------------------------------------------------------------------

    async authzRefresh() {
        const msg = document.getElementById('authz-msg');
        const localMsg = document.getElementById('authz-local-msg');
        const listEl = document.getElementById('authz-device-list');
        const enableBtn = document.getElementById('authz-enable-btn');
        const disableBtn = document.getElementById('authz-disable-btn');
        if (!msg || !listEl) return;

        if (!this._online || !this._online.logged_in) {
            msg.textContent = '登录资源站账号后可授权本机。';
            if (localMsg) localMsg.textContent = '未登录。';
            if (enableBtn) enableBtn.disabled = true;
            if (disableBtn) disableBtn.style.display = 'none';
            listEl.innerHTML = '';
            return;
        }

        msg.textContent = '';
        const res = await this._call('toolbox_authz_devices');
        if (this._stopped) return;
        if (!res || !res.success) {
            msg.textContent = (res && res.message) || '读取授权状态失败';
            return;
        }
        const d = res.data || {};
        const devices = d.devices || [];
        const maxDevices = d.max_devices || 2;
        const localId = d.local_device_id;
        const tpmOk = !!d.tpm_available;

        const maxEl = document.getElementById('authz-max-devices');
        if (maxEl) maxEl.textContent = String(maxDevices);

        const isLocalAuthorized = !!(localId && devices.some((x) => x.device_id === localId));
        if (localMsg) {
            if (!tpmOk) {
                localMsg.textContent = '本机没有可用的 TPM，无法授权。';
            } else if (isLocalAuthorized) {
                localMsg.textContent = '本机已授权，可直接通过 Steam 启动游戏。';
            } else if (localId) {
                localMsg.textContent = '本机凭据存在但未在授权列表中，请重新授权。';
            } else {
                localMsg.textContent = '本机尚未授权。';
            }
        }
        if (enableBtn) {
            enableBtn.style.display = isLocalAuthorized ? 'none' : '';
            enableBtn.disabled = !tpmOk;
        }
        if (disableBtn) disableBtn.style.display = isLocalAuthorized ? '' : 'none';

        if (!devices.length) {
            listEl.innerHTML = '<p class="form-hint">暂无已授权设备。</p>';
            return;
        }
        listEl.innerHTML = devices.map((x, i) => {
            const name = this._esc(x.display_name || `设备 ${i + 1}`);
            const fp = this._esc(x.public_key_fingerprint || '');
            const last = x.last_used_at
                ? this._esc(String(x.last_used_at).slice(0, 19).replace('T', ' '))
                : '从未使用';
            const isLocal = x.device_id === localId;
            return `<div style="padding:8px 0;border-bottom:1px solid var(--color-border-light);">
                <strong>${name}${isLocal ? '（本机）' : ''}</strong>
                <div class="form-hint">指纹 ${fp} · 最近使用 ${last}</div>
                ${isLocal ? '' : `<button class="tb-btn tb-btn--sm tb-btn--danger" data-tb-authz-revoke="${this._esc(x.device_id)}">撤销</button>`}
            </div>`;
        }).join('');
        listEl.querySelectorAll('[data-tb-authz-revoke]').forEach((btn) => {
            btn.addEventListener('click', () => this.authzRevoke(btn.dataset.tbAuthzRevoke));
        });
    },

    async authzEnable() {
        const btn = document.getElementById('authz-enable-btn');
        const msg = document.getElementById('authz-msg');
        if (btn) btn.disabled = true;
        if (msg) msg.textContent = '正在生成 TPM 密钥并注册…';
        try {
            const res = await this._call('toolbox_authz_enable', '');
            if (res && res.success) {
                this._toast('本机已授权，可直接通过 Steam 启动游戏');
            } else {
                this._toast((res && res.message) || '授权失败', true);
            }
        } finally {
            if (btn) btn.disabled = false;
            await this.authzRefresh();
        }
    },

    async authzDisable() {
        if (!confirm('撤销本机授权后，游戏将不再加载订阅工具。确定继续？')) return;
        const res = await this._call('toolbox_authz_disable');
        this._toast(res && res.success ? '本机授权已撤销' : (res && res.message), !(res && res.success));
        await this.authzRefresh();
    },

    async authzRevoke(deviceId) {
        if (!deviceId || !confirm('确定撤销这台设备的授权？')) return;
        const res = await this._call('toolbox_authz_revoke', deviceId);
        this._toast(res && res.success ? '已撤销该设备' : ((res && res.message) || '撤销失败'), !(res && res.success));
        await this.authzRefresh();
    },

    // ------------------------------------------------------------------
    // 旧版作弊工具箱入口（门控只在点击时就地弹，不覆盖整个订阅页）
    // ------------------------------------------------------------------

    async openCheat() {
        try {
            const accepted = (typeof RiskGate !== 'undefined')
                ? await RiskGate.getConsent('cheat')
                : true;
            if (accepted) {
                goAndShow('cheat');
                return;
            }
            RiskGate.showConsentModal('cheat', () => goAndShow('cheat'));
        } catch (e) {
            this._toast(String(e), true);
        }
    },

    // ------------------------------------------------------------------
    // 小工具
    // ------------------------------------------------------------------

    _esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    },

    _toast(msg, isError) {
        if (!msg) return;
        if (typeof window.showToast === 'function') {
            window.showToast(msg, isError ? 'error' : 'success');
        } else {
            console[isError ? 'error' : 'log']('[toolbox]', msg);
        }
    },
};

// 账号/解谜输入框回车提交（重绘后依然生效：事件委托在 document 上）
document.addEventListener('keydown', (e) => {
    const el = e.target;
    if (!el || !el.dataset || !el.dataset.tbEnter) return;
    if (e.key !== 'Enter') return;
    if (el.dataset.tbEnter === 'login') toolboxManager.login();
    if (el.dataset.tbEnter === 'puzzle') toolboxManager.solvePuzzle();
});

// Mod 镜像站 → 主窗口：与页面是否已打开无关，脚本加载即监听。
// （用户可能先开镜像站安装，再进入订阅工具页；不能依赖 init() 里的绑定。）
(function bindToolboxMirrorEvents() {
    if (window.__toolboxMirrorEventsBound) return;
    window.__toolboxMirrorEventsBound = true;
    window.addEventListener('lcta-toolbox-install', (e) => {
        const payload = e.detail && e.detail.payload;
        if (payload && typeof toolboxManager !== 'undefined') {
            toolboxManager.installFromMirror(payload);
        }
    });
})();
