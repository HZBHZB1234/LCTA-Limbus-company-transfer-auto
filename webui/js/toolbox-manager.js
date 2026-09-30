// ============================
// 工具箱公共安全层：赛季资格 + 本地安装管理
// ============================
// 设计约束（plan 10.1 / 10.6）：
//   1) **不依赖**旧 cheat_core.bin 解密门。过季后用户仍必须能停用/卸载/回滚
//      已下载的插件 —— 否则「过季就卸不掉」，等于把用户锁死。
//   2) 本地管理与在线资格**解耦**：在线查询失败只提示，不影响本地列表与操作。
//   3) 所有安装/启停都由 Python 侧重新校验（权限、签名、哈希、路径、游戏是否运行）；
//      JS 只传 tool_id/release_id/action，不传 URL、路径或命令。

let toolboxManager = {
    _bound: false,
    _stopped: false,
    _state: null,

    init() {
        this._stopped = false;
        const root = document.getElementById('toolbox-public');
        if (!root) return;
        this._bindOnce();
        // 与 cheat 风险门控一致：未同意风险须知时不显示内容
        if (typeof RiskGate !== 'undefined' && RiskGate.gatePage
            && document.querySelector('[data-risk-overlay="cheat"]')) {
            RiskGate.gatePage('cheat', {
                onAccepted: () => this._show(),
                onRejected: () => this._hide(),
            });
        } else {
            this._show();
        }
        this.refresh();
    },

    stop() {
        this._stopped = true;
    },

    _show() {
        const el = document.getElementById('toolbox-public');
        if (el) el.style.display = '';
    },

    _hide() {
        const el = document.getElementById('toolbox-public');
        if (el) el.style.display = 'none';
    },

    _esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    },

    _bindOnce() {
        if (this._bound) return;
        this._bound = true;
        const bind = (id, fn) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('click', fn);
        };
        bind('tb-refresh-btn', () => this.refresh());
        bind('tb-open-folder-btn', () => this.openFolder());
        bind('tb-save-root-btn', () => this.saveGameRoot());
    },

    async _call(method, ...args) {
        try {
            const fn = pywebview.api[method];
            if (typeof fn !== 'function') return { success: false, message: '当前版本不支持该操作' };
            return await fn.apply(pywebview.api, args);
        } catch (e) {
            return { success: false, message: String(e) };
        }
    },

    async refresh() {
        const res = await this._call('toolbox_status');
        if (this._stopped) return;
        if (!res || !res.success) {
            this._renderError(res && res.message);
            return;
        }
        this._state = res.data || {};
        this._render();
    },

    _renderError(msg) {
        const body = document.getElementById('tb-installed-body');
        if (body) body.innerHTML = `<p class="form-hint">读取失败：${this._esc(msg || '未知错误')}</p>`;
    },

    _render() {
        const d = this._state || {};

        // 崩溃恢复提示：上次安装被中断，已自动回滚
        if (d.recovered) {
            const r = d.recovered;
            const n = (r.restored || []).length + (r.deleted || []).length;
            this._toast(`检测到上次安装未完成，已自动恢复到安装前状态（${n} 个文件）`);
        }

        this._renderAccount(d);
        this._renderRuntime(d);
        this._renderInstalled(d);
        this._renderCatalog(d);

        const rootInput = document.getElementById('tb-game-root');
        if (rootInput && d.local && d.local.game_root && !rootInput.value) {
            rootInput.value = d.local.game_root;
        }
    },

    _renderAccount(d) {
        const body = document.getElementById('tb-account-body');
        if (!body) return;
        const online = d.online;
        const rows = [];

        if (d.local_error) {
            rows.push(`<p class="form-hint">${this._esc(d.local_error)}</p>`);
        }

        if (!d.logged_in) {
            rows.push('<p class="form-hint">未登录资源站。登录后可查看赛季资格并下载本赛季内容。</p>');
        } else if (online) {
            const season = online.season_name || online.season_slug || '当前赛季';
            if (online.unlocked) {
                rows.push(`<p><i class="fas fa-unlock" style="color:#6cc644"></i> <b>${this._esc(season)}</b>：本赛季已解锁</p>`);
                if (online.sources && online.sources.length) {
                    const src = online.sources.map((s) => this._esc(s.source)).join('、');
                    rows.push(`<p class="form-hint">资格来源：${src}</p>`);
                }
            } else {
                rows.push(`<p><i class="fas fa-lock" style="color:#d29922"></i> <b>${this._esc(season)}</b>：尚未解锁</p>`);
                const reason = {
                    email_required: '请先在网站绑定并验证邮箱。',
                    season_inactive: '当前赛季尚未开放。',
                    entitlement_required: '请在网站完成当季解谜或核验爱发电赞助。',
                    account_inactive: '账号已被禁用。',
                    scope_not_allowed: '当前登录方式不能获取工具箱资格。',
                }[online.reason] || '';
                if (reason) rows.push(`<p class="form-hint">${this._esc(reason)}</p>`);
                rows.push('<p class="form-hint">解锁请前往网站「作弊工具箱」页面（解谜或赞助核验）。</p>');
            }
        } else if (d.online_error) {
            // 在线失败不影响本地管理
            rows.push(`<p class="form-hint">在线状态暂时无法获取：${this._esc(d.online_error)}</p>`);
            rows.push('<p class="form-hint">本地安装管理不受影响，仍可停用/卸载/回滚。</p>');
        }

        if (d.game_running === true) {
            rows.push('<p class="form-hint" style="color:#d29922"><i class="fas fa-exclamation-triangle"></i> 游戏正在运行，安装/启停操作会被拒绝，请先关闭游戏。</p>');
        }
        body.innerHTML = rows.join('') || '<p class="form-hint">暂无信息。</p>';
    },

    _renderRuntime(d) {
        const body = document.getElementById('tb-runtime-body');
        if (!body) return;
        const rt = d.local && d.local.runtime;
        if (rt) {
            body.innerHTML = `<p>已安装底座：<b>${this._esc(rt.version || rt.release_id)}</b></p>
                <p class="form-hint">由 LCTA 管理。卸载插件不会影响底座。</p>`;
        } else {
            body.innerHTML = '<p class="form-hint">尚未安装工具箱底座。</p>'
                + '<p class="form-hint">底座与插件请在本页面安装（需要本赛季已解锁且游戏未运行）。</p>';
        }
    },

    _renderInstalled(d) {
        const body = document.getElementById('tb-installed-body');
        if (!body) return;
        const plugins = (d.local && d.local.plugins) || [];
        const unmanaged = (d.local && d.local.unmanaged) || [];

        if (!plugins.length && !unmanaged.length) {
            body.innerHTML = '<p class="form-hint">还没有安装任何插件。</p>';
            return;
        }

        const rows = [];
        if (plugins.length) {
            rows.push('<table class="tb-table"><thead><tr><th>插件</th><th>版本</th><th>状态</th><th>操作</th></tr></thead><tbody>');
            for (const p of plugins) {
                rows.push(`<tr>
                    <td>${this._esc(p.tool_id)}${p.guid ? `<br><small class="form-hint">${this._esc(p.guid)}</small>` : ''}</td>
                    <td>${this._esc(p.version || p.release_id)}</td>
                    <td>${p.enabled ? '已启用' : '已停用'}</td>
                    <td>
                        <button class="secondary-btn tb-toggle" data-tool="${this._esc(p.tool_id)}" data-enable="${p.enabled ? '0' : '1'}">
                            ${p.enabled ? '停用' : '启用'}
                        </button>
                        <button class="secondary-btn tb-verify" data-tool="${this._esc(p.tool_id)}">检查</button>
                        <button class="secondary-btn tb-rollback" data-tool="${this._esc(p.tool_id)}">回滚</button>
                        <button class="secondary-btn tb-uninstall" data-tool="${this._esc(p.tool_id)}">卸载</button>
                    </td>
                </tr>`);
            }
            rows.push('</tbody></table>');
        }
        if (unmanaged.length) {
            rows.push('<p class="form-hint" style="margin-top:1rem">检测到非 LCTA 管理的插件（不会被自动删除或升级）：</p><ul>');
            for (const u of unmanaged) rows.push(`<li class="form-hint">${this._esc(u)}</li>`);
            rows.push('</ul>');
        }
        body.innerHTML = rows.join('');
        this._bindRowActions();
    },

    _bindRowActions() {
        const on = (cls, fn) => {
            document.querySelectorAll(cls).forEach((btn) => {
                btn.addEventListener('click', () => fn(btn));
            });
        };
        on('.tb-toggle', (b) => this.setEnabled(b.dataset.tool, b.dataset.enable === '1'));
        on('.tb-verify', (b) => this.verify(b.dataset.tool));
        on('.tb-rollback', (b) => this.rollback(b.dataset.tool));
        on('.tb-uninstall', (b) => this.uninstall(b.dataset.tool));
    },

    _renderCatalog(d) {
        const card = document.getElementById('tb-catalog-card');
        const body = document.getElementById('tb-catalog-body');
        if (!card || !body) return;
        const unlocked = !!(d.online && d.online.unlocked);
        if (!unlocked) {
            card.style.display = 'none';
            return;
        }
        card.style.display = '';
        const items = (d.catalog && d.catalog.items) || [];
        if (!items.length) {
            body.innerHTML = '<p class="form-hint">本赛季暂无可获取内容。</p>';
            return;
        }
        const rows = ['<table class="tb-table"><thead><tr><th>名称</th><th>版本</th><th>类型</th><th>操作</th></tr></thead><tbody>'];
        for (const it of items) {
            rows.push(`<tr>
                <td>${this._esc(it.tool_name)}</td>
                <td>${this._esc(it.version)}</td>
                <td>${this._esc(it.resource_kind)}</td>
                <td><button class="primary-btn tb-install" data-tool="${this._esc(it.tool_id)}" data-release="${this._esc(it.release_id)}">安装/更新</button></td>
            </tr>`);
        }
        rows.push('</tbody></table>');
        body.innerHTML = rows.join('');
        document.querySelectorAll('.tb-install').forEach((btn) => {
            btn.addEventListener('click', () => this.install(btn.dataset.tool, btn.dataset.release));
        });
    },

    async setEnabled(toolId, enabled) {
        const res = await this._call('toolbox_set_enabled', toolId, enabled);
        this._toast(res && res.success ? (enabled ? '已启用' : '已停用') : (res && res.message));
        await this.refresh();
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
            this._toast(res && res.message, true);
        }
    },

    async rollback(toolId) {
        if (!confirm('回滚到本地备份？当前文件会被替换为备份内容。')) return;
        const res = await this._call('toolbox_rollback', toolId);
        this._toast(res && res.success ? '已回滚到本地备份' : (res && res.message), !(res && res.success));
        await this.refresh();
    },

    async uninstall(toolId) {
        if (!confirm('卸载该插件？只移除 LCTA 管理的文件，你自己的文件与配置会保留。')) return;
        const res = await this._call('toolbox_uninstall', toolId, false);
        this._toast(res && res.success ? '已卸载' : (res && res.message), !(res && res.success));
        await this.refresh();
    },

    async install(toolId, releaseId) {
        if (!confirm('安装/更新该插件？请确认游戏已关闭。')) return;
        this._toast('正在安装，请稍候…');
        const res = await this._call('toolbox_install', toolId, releaseId);
        this._toast(res && res.success ? '安装完成' : (res && res.message), !(res && res.success));
        await this.refresh();
    },

    async openFolder() {
        const res = await this._call('toolbox_open_folder', '');
        if (!res || !res.success) this._toast(res && res.message, true);
    },

    async saveGameRoot() {
        const input = document.getElementById('tb-game-root');
        if (!input) return;
        const res = await this._call('toolbox_set_game_root', input.value.trim());
        this._toast(res && res.success ? '游戏目录已保存' : (res && res.message), !(res && res.success));
        await this.refresh();
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
