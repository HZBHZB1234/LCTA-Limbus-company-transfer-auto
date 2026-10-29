// ============================
// 订阅工具页（原「工具箱」，2026-10-30 对齐站点订阅语义）：
// 账号登录 + 月/赛季订阅 + 名单公开目录 + 本地安装管理
// ============================
// 设计约束（plan 10.1 / 10.6 / 2026-10-30 一键安装契约）：
//   1) **不依赖**旧 cheat_core.bin 解密门。过季后用户仍必须能停用/卸载/回滚
//      已下载的插件 —— 否则「过季就卸不掉」，等于把用户锁死。
//   2) 本地管理与在线资格**解耦**：在线查询失败只提示，不影响本地列表与操作。
//   3) 所有安装/启停都由 Python 侧重新校验（权限、签名、哈希、路径、游戏是否运行）；
//      JS 只传 tool_id/release_id/action，不传 URL、路径或命令。
//   4) 目录名单对游客公开（与站点一致）：逐条 access_kind/downloadable 决定
//      「安装/更新」按钮，锁定原创显示订阅引导；一键安装由签名清单驱动。

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
        const rows = [];

        if (d.local_error) {
            rows.push(`<p class="form-hint">${this._esc(d.local_error)}</p>`);
        }

        if (!d.logged_in) {
            // 登录表单：使用资源站账号（identifier 含 @ 按邮箱，否则按用户名）
            rows.push('<p class="form-hint">登录后可查看订阅资格；原创内容需有效订阅，转载内容登录即可下载。</p>');
            rows.push('<div class="tb-login-form">');
            rows.push('<input type="text" id="tb-login-identifier" placeholder="用户名或邮箱" autocomplete="username">');
            rows.push('<input type="password" id="tb-login-password" placeholder="密码" autocomplete="current-password">');
            rows.push('<button id="tb-login-btn" class="primary-btn"><i class="fas fa-sign-in-alt"></i> 登录</button>');
            rows.push('</div>');
            const base = this._esc(d.base_url || 'https://mods.lcta.top');
            rows.push(`<p class="form-hint">没有账号？<a href="${base}/register" target="_blank">前往资源站注册</a>（邮箱验证码注册，回到本页登录即可）。</p>`);
        } else {
            const user = d.user || {};
            const who = user.username || user.email || '已登录';
            rows.push(`<p><i class="fas fa-user-check" style="color:#6cc644"></i> <b>${this._esc(who)}</b>
                <button id="tb-logout-btn" class="secondary-btn" style="margin-left:8px">登出</button></p>`);
            rows.push(this._renderSubscription(d));
            rows.push(this._renderAfdian(d));
            if (d.season && d.season.puzzle_enabled) {
                rows.push(this._renderPuzzleEntry());
            }
        }

        if (d.game_running === true) {
            rows.push('<p class="form-hint" style="color:#d29922"><i class="fas fa-exclamation-triangle"></i> 游戏正在运行，安装/启停操作会被拒绝，请先关闭游戏。</p>');
        }
        body.innerHTML = rows.join('') || '<p class="form-hint">暂无信息。</p>';
        this._bindAccountActions();
    },

    // 订阅资格摘要（2026-10-30 站点语义：monthly 带 expires_at，season 随季失效）
    _renderSubscription(d) {
        const online = d.online;
        const seasonName = (d.season && (d.season.name || d.season.slug)) || '当前赛季';
        const rows = [];
        if (!online) {
            if (d.online_error) {
                rows.push(`<p class="form-hint">订阅状态暂时无法获取：${this._esc(d.online_error)}</p>`);
                rows.push('<p class="form-hint">本地安装管理不受影响，仍可停用/卸载/回滚。</p>');
            }
            return rows.join('');
        }
        if (online.unlocked) {
            rows.push(`<p><i class="fas fa-unlock" style="color:#6cc644"></i> <b>${this._esc(seasonName)}</b>：已解锁</p>`);
            const src = (online.sources || []).map((s) => {
                if (s.subscription_kind === 'monthly') {
                    const end = s.expires_at ? String(s.expires_at).slice(0, 10) : '未知';
                    return `按月（至 ${this._esc(end)}）`;
                }
                return '按赛季';
            }).join('、');
            if (src) rows.push(`<p class="form-hint">订阅：${src}</p>`);
        } else {
            rows.push(`<p><i class="fas fa-lock" style="color:#d29922"></i> <b>${this._esc(seasonName)}</b>：尚未订阅</p>`);
            const reason = {
                account_inactive: '账号已被禁用。',
                season_inactive: '当前赛季尚未开放。',
                email_required: '请先绑定并验证邮箱（注册即自动验证）。',
                entitlement_required: '还没有有效订阅 —— 爱发电订阅后点「刷新订阅状态」即可。',
                scope_not_allowed: '当前登录方式不能获取订阅资格，请用账号密码登录。',
            }[online.reason] || '';
            if (reason) rows.push(`<p class="form-hint">${this._esc(reason)}</p>`);
            if (d.season && d.season.monthly_price_cents != null) {
                const m = (d.season.monthly_price_cents / 100).toFixed(2);
                rows.push(`<p class="form-hint">按月 ¥${this._esc(m)} / 月（跨赛季不中断）；转载内容无需订阅，登录即可下载。</p>`);
            }
        }
        return rows.join('');
    },

    // 爱发电订阅核验区（绑定 → 自动核验；之后每月续费点一次刷新）
    _renderAfdian(d) {
        const afdian = d.afdian;
        const rows = [];
        if (!afdian || !afdian.configured) {
            rows.push('<p class="form-hint">爱发电自动核验尚未配置：请联系站长人工核验订阅。</p>');
            return rows.join('');
        }
        rows.push('<div class="tb-afdian">');
        if (!afdian.bound) {
            rows.push('<p class="form-hint">订阅方式：在爱发电订阅后关联账号，资格自动核验生效。</p>');
            rows.push('<button id="tb-afdian-bind-btn" class="primary-btn"><i class="fas fa-link"></i> 关联爱发电账号</button>');
        } else {
            rows.push(`<p class="form-hint">爱发电：已关联（${this._esc(afdian.provider_user_id || '')}）</p>`);
            rows.push('<button id="tb-afdian-refresh-btn" class="primary-btn"><i class="fas fa-sync"></i> 刷新订阅状态</button>');
            rows.push('<details style="margin-top:8px"><summary class="form-hint">订阅后没有自动生效？手动填写订单号</summary>');
            rows.push('<div class="tb-login-form" style="margin-top:6px">');
            rows.push('<input type="text" id="tb-order-no" placeholder="爱发电订单号">');
            rows.push('<button id="tb-verify-order-btn" class="secondary-btn">核验订单</button>');
            rows.push('</div></details>');
        }
        rows.push('</div>');
        return rows.join('');
    },

    _renderPuzzleEntry() {
        // 站点 PUZZLE_ENABLED=true 时才显示（当前默认关闭，资格只走订阅）
        return '<details style="margin-top:8px"><summary class="form-hint">解谜获取资格（如站点开放）</summary>' +
            '<div style="margin-top:6px"><button id="tb-puzzle-new-btn" class="secondary-btn">获取我的挑战</button>' +
            '<div id="tb-puzzle-body"></div></div></details>';
    },

    _bindAccountActions() {
        const bind = (id, fn) => {
            const el = document.getElementById(id);
            if (el) el.addEventListener('click', fn);
        };
        bind('tb-login-btn', () => this.login());
        bind('tb-logout-btn', () => this.logout());
        bind('tb-afdian-bind-btn', () => this.afdianBind());
        bind('tb-afdian-refresh-btn', () => this.afdianRefresh());
        bind('tb-verify-order-btn', () => this.verifyOrder());
        bind('tb-puzzle-new-btn', () => this.newPuzzle());
        const pwd = document.getElementById('tb-login-password');
        if (pwd) pwd.addEventListener('keyup', (e) => { if (e.key === 'Enter') this.login(); });
    },

    async login() {
        const idEl = document.getElementById('tb-login-identifier');
        const pwdEl = document.getElementById('tb-login-password');
        const identifier = (idEl && idEl.value || '').trim();
        const password = (pwdEl && pwdEl.value) || '';
        if (!identifier || !password) {
            this._toast('请输入用户名/邮箱与密码', true);
            return;
        }
        this._toast('正在登录…');
        const res = await this._call('toolbox_login', identifier, password);
        this._toast(res && res.success ? '登录成功' : (res && res.message), !(res && res.success));
        await this.refresh();
    },

    async logout() {
        if (!confirm('登出资源站账号？本地已安装内容不受影响。')) return;
        const res = await this._call('toolbox_logout');
        this._toast(res && res.success ? '已登出' : (res && res.message), !(res && res.success));
        await this.refresh();
    },

    async afdianBind() {
        const res = await this._call('toolbox_afdian_bind_url');
        if (res && res.success) {
            this._toast('已在系统浏览器打开爱发电授权页，完成授权后回到本页点「刷新订阅状态」');
        } else {
            this._toast(res && res.message, true);
        }
    },

    async afdianRefresh() {
        const res = await this._call('toolbox_afdian_refresh');
        if (res && res.success) {
            const s = res.data || {};
            this._toast(s.verified ? `已核验 ${s.verified} 笔有效订阅` : '暂未查询到新的有效订阅');
        } else {
            this._toast(res && res.message, true);
        }
        await this.refresh();
    },

    async verifyOrder() {
        const el = document.getElementById('tb-order-no');
        const orderNo = (el && el.value || '').trim();
        if (!orderNo) {
            this._toast('请填写爱发电订单号', true);
            return;
        }
        const res = await this._call('toolbox_verify_order', orderNo);
        this._toast(res && res.success ? '订单已核验' : (res && res.message), !(res && res.success));
        await this.refresh();
    },

    async newPuzzle() {
        const res = await this._call('toolbox_new_challenge');
        const body = document.getElementById('tb-puzzle-body');
        if (!res || !res.success) {
            if (body) body.innerHTML = `<p class="form-hint">${this._esc(res && res.message || '获取失败')}</p>`;
            return;
        }
        const ch = res.data || {};
        this._challengeId = ch.challenge_id || '';
        if (body) {
            body.innerHTML = '<textarea id="tb-puzzle-material" class="form-hint" readonly style="width:100%;height:180px">' +
                this._esc(ch.material || '') + '</textarea>' +
                '<div class="tb-login-form" style="margin-top:6px">' +
                '<input type="text" id="tb-puzzle-answer" placeholder="序列号答案">' +
                '<button id="tb-puzzle-solve-btn" class="primary-btn">提交答案</button></div>';
            document.getElementById('tb-puzzle-solve-btn').addEventListener('click', () => this.solvePuzzle());
        }
    },

    async solvePuzzle() {
        const el = document.getElementById('tb-puzzle-answer');
        const answer = (el && el.value || '').trim();
        if (!this._challengeId || !answer) return;
        const res = await this._call('toolbox_solve', this._challengeId, answer);
        this._toast(res && res.success ? '答案正确' : (res && res.message), !(res && res.success));
        await this.refresh();
    },

    _renderRuntime(d) {
        const body = document.getElementById('tb-runtime-body');
        if (!body) return;
        const rt = d.local && d.local.runtime;
        if (rt) {
            body.innerHTML = `<p>已安装底座：<b>${this._esc(rt.version || rt.release_id)}</b></p>
                <p class="form-hint">由 LCTA 管理。卸载插件不会影响底座；更新请在下方目录安装 runtime 条目。</p>`;
        } else {
            body.innerHTML = '<p class="form-hint">尚未安装订阅工具底座。</p>'
                + '<p class="form-hint">请在下方目录安装 runtime 条目（需要相应资格且游戏未运行）；插件安装前必须先装底座。</p>';
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
        if (d.catalog_error) {
            body.innerHTML = `<p class="form-hint">目录暂时无法获取：${this._esc(d.catalog_error)}</p>`;
            return;
        }
        const items = (d.catalog && d.catalog.items) || [];
        if (!items.length) {
            body.innerHTML = '<p class="form-hint">本赛季暂未发布内容。</p>';
            return;
        }
        const rows = ['<table class="tb-table"><thead><tr><th>名称</th><th>版本</th><th>类型</th><th>访问</th><th>操作</th></tr></thead><tbody>'];
        for (const it of items) {
            const kindLabel = it.access_kind === 'repost' ? '转载 · 免费' : '原创 · 订阅专享';
            const kindColor = it.access_kind === 'repost' ? '#6cc644' : '#d29922';
            const resLabel = it.resource_kind === 'runtime' ? '底座' : '插件';
            let action;
            if (it.downloadable) {
                const btnLabel = it.resource_kind === 'runtime' ? '安装底座' : '安装/更新';
                const btnClass = it.resource_kind === 'runtime' ? 'tb-install-runtime' : 'tb-install';
                action = `<button class="primary-btn ${btnClass}" data-tool="${this._esc(it.tool_id)}" data-release="${this._esc(it.release_id)}">${btnLabel}</button>`;
            } else if (!d.logged_in) {
                action = '<span class="form-hint">登录后可下载</span>';
            } else {
                action = '<span class="form-hint"><i class="fas fa-lock"></i> 需订阅解锁</span>';
            }
            const fileCount = (it.files || []).length;
            rows.push(`<tr>
                <td>${this._esc(it.tool_name)}${it.recommended ? ' <span class="form-hint">(推荐)</span>' : ''}</td>
                <td>${this._esc(it.version)}</td>
                <td>${this._esc(resLabel)}</td>
                <td><span style="color:${kindColor}">${this._esc(kindLabel)}</span></td>
                <td>${action}${fileCount ? `<br><small class="form-hint">${fileCount} 个文件</small>` : ''}</td>
            </tr>`);
        }
        rows.push('</tbody></table>');
        if (!d.logged_in) {
            rows.push('<p class="form-hint">名单对游客公开；下载/安装需要登录（原创另需有效订阅）。</p>');
        }
        body.innerHTML = rows.join('');
        document.querySelectorAll('.tb-install').forEach((btn) => {
            btn.addEventListener('click', () => this.install(btn.dataset.tool, btn.dataset.release));
        });
        document.querySelectorAll('.tb-install-runtime').forEach((btn) => {
            btn.addEventListener('click', () => this.installRuntime(btn.dataset.tool, btn.dataset.release));
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
        if (!confirm('安装/更新该插件？请确认游戏已关闭。安装由签名清单驱动，逐文件校验后写入。')) return;
        this._toast('正在安装，请稍候…');
        const res = await this._call('toolbox_install', toolId, releaseId);
        this._toast(res && res.success ? '安装完成' : (res && res.message), !(res && res.success));
        await this.refresh();
    },

    async installRuntime(toolId, releaseId) {
        if (!confirm('安装/更新订阅工具底座？请确认游戏已关闭。\n检测到非 LCTA 管理的 BepInEx 时会要求二次确认（可能覆盖现有框架）。')) {
            return;
        }
        this._toast('正在安装底座，请稍候…');
        let res = await this._call('toolbox_install_runtime', toolId, releaseId, false);
        if (res && !res.success && /非 LCTA 管理的 BepInEx/.test(res.message || '')) {
            if (!confirm(res.message + '\n\n确定继续并覆盖吗？')) return;
            res = await this._call('toolbox_install_runtime', toolId, releaseId, true);
        }
        this._toast(res && res.success ? '底座安装完成' : (res && res.message), !(res && res.success));
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
