// ============================
// 订阅工具页 · 纯渲染层（toolbox-views.js）
// ============================
// 只做「状态 → HTML」，不碰 pywebview、不发请求、不绑事件：
// 事件由 toolbox-manager.js 用 data-tb-action 委托统一处理。
// 这样重绘不会丢监听器，也方便单点修改视觉而不动状态机。
//
// 安全：所有来自服务端的文本一律经 _esc()；URL 只用于 <img src>，
// 且必须是服务端目录下发的资源站图片（https）。

const ToolboxViews = {
    // ---------- 基础工具 ----------

    esc(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        }[c]));
    },

    fmtBytes(n) {
        if (n == null || n === '') return '';
        let v = Number(n) || 0;
        if (!v) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB'];
        let i = 0;
        while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
        return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
    },

    _pad(n) {
        return String(n).padStart(2, '0');
    },

    /** 服务端时间戳（可能是 ISO 带 T/Z，也可能是本地日期串）→ 可读文本。 */
    fmtDateTime(value) {
        if (!value) return '';
        const s = String(value);
        const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
        if (m) return `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}`;
        return s.length > 19 ? s.slice(0, 19).replace('T', ' ') : s;
    },

    /** 目录/清单里的 install_kind → 中文类型名。 */
    installKindLabel(kind) {
        return {
            runtime_zip_root: '底座',
            bepinex_plugin_dll: '插件',
            game_relative_files: '文件包',
            download_only: '仅下载',
        }[kind] || '未知类型';
    },

    accessLabel(item) {
        return item && item.access_kind === 'repost' ? '转载 · 免费' : '原创 · 订阅专享';
    },

    accessBadge(item) {
        const repost = item && item.access_kind === 'repost';
        return `<span class="tb-badge tb-badge--${repost ? 'repost' : 'original'}">
            <i class="fas fa-${repost ? 'share' : 'star'}"></i>${repost ? '转载' : '原创'}
        </span>`;
    },

    chip(text, variant, icon) {
        const cls = variant ? ` tb-chip--${variant}` : '';
        const ico = icon ? `<i class="fas fa-${icon}"></i>` : '';
        return `<span class="tb-chip${cls}">${ico}${ToolboxViews.esc(text)}</span>`;
    },

    _initial(item) {
        const name = String((item && (item.name_zh || item.tool_name)) || '?').trim();
        return (name.slice(0, 1) || '?').toUpperCase();
    },

    _gridSkeletons(count) {
        let out = '';
        for (let i = 0; i < count; i += 1) out += '<div class="tb-skeleton"></div>';
        return out;
    },

    empty(icon, text) {
        return `<div class="tb-empty"><i class="fas fa-${icon}"></i>${text}</div>`;
    },

    errorBox(message, action = 'retry', label = '重试') {
        return `<div class="tb-error">
            <i class="fas fa-exclamation-triangle"></i>
            <span>${ToolboxViews.esc(message)}</span>
            <button class="tb-btn tb-btn--sm tb-error-action" data-tb-action="${ToolboxViews.esc(action)}">${ToolboxViews.esc(label)}</button>
        </div>`;
    },

    // ---------- 状态条 ----------

    /**
     * 顶部状态条：账号 / 赛季 / 底座 / 游戏 + 上下文主操作。
     * 主操作三态：未登录→登录；已登录未解锁→刷新订阅；解锁但缺底座→安装底座。
     */
    statusbar(ctx) {
        const online = ctx.online || {};
        const local = ctx.local || {};
        const access = online.access || {};
        const season = online.season || {};
        const localState = local.local || {};
        const runtime = localState.runtime;

        const loggedIn = !!online.logged_in;
        const unlocked = !!access.unlocked;
        const seasonNamed = season.name || season.slug || '';

        let accountText = '未登录';
        let accountSub = loggedIn ? '' : '登录后可订阅与下载';
        if (loggedIn) {
            const user = online.user || {};
            accountText = user.username || user.email || '已登录';
            accountSub = access.email_verified ? '邮箱已验证' : '';
            if (access.email_verified === false) accountSub = '邮箱未验证';
        }

        let seasonText = '未开放';
        let seasonSub = '';
        if (season.season_active) seasonText = seasonNamed || '当前赛季';
        else if (season.season_active === false) seasonText = '本站暂停开放';
        if (season.season_active) seasonSub = unlocked ? '已解锁' : '未订阅';

        let runtimeText = runtime ? (runtime.version || runtime.release_id) : '未安装';
        let runtimeSub = runtime ? '由 LCTA 管理' : '插件安装前需先装底座';

        let gameText = '未配置';
        let gameSub = '';
        if (local.game_root) {
            gameText = '已配置';
            if (local.game_running === true) { gameText = '运行中'; gameSub = '请先关闭游戏'; }
            else if (local.game_running === false) { gameText = '已就绪'; }
        }

        const cells = [
            { label: '账号', value: accountText, sub: accountSub },
            { label: '赛季', value: seasonText, sub: seasonSub },
            { label: '底座', value: runtimeText, sub: runtimeSub },
            { label: '游戏目录', value: gameText, sub: gameSub },
        ].map((c) => `<div class="tb-status-cell">
                <span class="tb-status-label">${ToolboxViews.esc(c.label)}</span>
                <span class="tb-status-value" title="${ToolboxViews.esc(c.value)}">${ToolboxViews.esc(c.value)}${
                    c.sub ? `<span class="tb-sub"> · ${ToolboxViews.esc(c.sub)}</span>` : ''
                }</span>
            </div>`).join('');

        // 上下文主操作：一个页面只有一个主动作
        let primary = '';
        if (!loggedIn) {
            primary = `<button class="tb-btn tb-btn--primary" data-tb-action="go-account">
                <i class="fas fa-sign-in-alt"></i> 登录资源站</button>`;
        } else if (!unlocked) {
            primary = `<button class="tb-btn tb-btn--primary" data-tb-action="refresh-subscription">
                <i class="fas fa-sync"></i> 刷新订阅状态</button>`;
        } else if (!runtime) {
            primary = `<button class="tb-btn tb-btn--primary" data-tb-action="go-runtime">
                <i class="fas fa-layer-group"></i> 安装底座</button>`;
        } else {
            const updates = ToolboxViews.updateCount(ctx);
            primary = updates
                ? `<button class="tb-btn tb-btn--primary" data-tb-action="go-updates">
                    <i class="fas fa-arrow-circle-up"></i> ${updates} 项可更新</button>`
                : `<button class="tb-btn" data-tb-action="refresh">
                    <i class="fas fa-check"></i> 已是最新</button>`;
        }

        return `${cells}<div class="tb-status-actions">${primary}</div>`;
    },

    // ---------- 目录 ----------

    updateCount(ctx) {
        const local = ctx.local && ctx.local.local;
        if (!local) return 0;
        const items = (ctx.online && ctx.online.catalog && ctx.online.catalog.items) || [];
        const latest = ToolboxViews._catalogLatest(items);
        const map = ToolboxViews._installedByTool(local);
        let count = 0;
        for (const [toolId, item] of latest) {
            const installed = map.get(toolId);
            if (ToolboxViews.hasUpdate(item, installed)) count += 1;
        }
        // 底座也参与「可更新」统计（状态条与实际可更新数必须一致）
        const rt = local.runtime;
        const rtItem = latest.get(ToolboxViews._runtimeToolId(latest, items));
        if (rt && rtItem && ToolboxViews.hasUpdate(rtItem, rt)) count += 1;
        return count;
    },

    /**
     * 目录里的「每个工具一行」索引（2026-11-02）。
     *
     * 服务端目录是**按发布版本**一行的：同一工具可能同时有多个版本（历史版本
     * 保留供显式降级）。旧实现直接 set() 覆盖，等于"最后一行说了算"，于是
     * 卡片会来回跳、还会假报"可更新"。这里统一按 is_latest 选行；老站点没有
     * is_latest 时退化为按 version_sort 取最大（好过比 release_id 字符串）。
     */
    _catalogLatest(items) {
        const map = new Map();
        for (const it of (items || [])) {
            if (!it) continue;
            const key = String(it.tool_id);
            const cur = map.get(key);
            if (!cur) { map.set(key, it); continue; }
            const itLatest = !!it.is_latest;
            const curLatest = !!cur.is_latest;
            if (itLatest !== curLatest) {
                if (itLatest) map.set(key, it);
                continue;
            }
            if (String(it.version_sort || '') > String(cur.version_sort || '')) {
                map.set(key, it);
            }
        }
        return map;
    },

    /** 目录里底座（runtime_zip_root）的 tool_id（没有则返回空串）。 */
    _runtimeToolId(latest, items) {
        for (const [toolId, it] of latest) {
            if (it.install_kind === 'runtime_zip_root' || it.resource_kind === 'runtime') {
                return toolId;
            }
        }
        for (const it of (items || [])) {
            if (it.install_kind === 'runtime_zip_root' || it.resource_kind === 'runtime') {
                return String(it.tool_id);
            }
        }
        return '';
    },

    /**
     * 是否「有新版本」。判定只信服务端：
     * - 目标必须是目录里的最新版（旧版行不参与）；
     * - release 相同 → 没变化；
     * - 已装版本序缺失（升级前的旧记录）→ 有更新，让用户装一次把版本记下来；
     * - 否则严格比较 version_sort（正式版 > 同号预发布，由服务端归一化）。
     */
    hasUpdate(item, installed) {
        if (!item || !installed) return false;
        if (!installed.release_id || !item.release_id) return false;
        if (String(installed.release_id) === String(item.release_id)) return false;
        const target = String(item.version_sort || '');
        const current = String(installed.version_sort || '');
        if (!current || !target) return true;
        return target > current;
    },

    _installedByTool(local) {
        const map = new Map();
        if (!local) return map;
        for (const p of (local.plugins || [])) map.set(String(p.tool_id), { ...p, _kind: 'plugin' });
        for (const p of (local.packages || [])) map.set(String(p.tool_id), { ...p, _kind: 'package' });
        return map;
    },

    /** 目录过滤 + 排序（纯函数，管理器只传状态）。 */
    filterCatalog(items, { query, filter, sort }, local) {
        const q = String(query || '').trim().toLowerCase();
        const map = ToolboxViews._installedByTool(local);
        // 同工具多版本：列表只保留最新那一行（历史版本进详情抽屉），
        // 否则一个工具会重复成多张卡、还会互相"假更新"。
        const latestMap = ToolboxViews._catalogLatest(items);
        const latestRows = new Set(Array.from(latestMap.values()));
        let list = (items || []).filter((it) => {
            if (!latestRows.has(it)) return false;
            if (q) {
                const hay = [
                    it.name_zh, it.tool_name, it.author, it.category, it.tags, it.summary,
                ].map((x) => String(x || '').toLowerCase()).join(' ');
                if (!hay.includes(q)) return false;
            }
            if (filter === 'original') return it.access_kind !== 'repost';
            if (filter === 'repost') return it.access_kind === 'repost';
            if (filter === 'downloadable') return !!it.downloadable;
            if (filter === 'update') {
                // 统一口径：只看「目录最新版」与「本地已装」，见 hasUpdate()
                const isRuntime = it.install_kind === 'runtime_zip_root'
                    || it.resource_kind === 'runtime';
                if (isRuntime) {
                    const rt = local && local.runtime;
                    return ToolboxViews.hasUpdate(it, rt);
                }
                const installed = map.get(String(it.tool_id));
                return ToolboxViews.hasUpdate(it, installed);
            }
            return true;
        });

        const byName = (a, b) => String(a.name_zh || a.tool_name || '')
            .localeCompare(String(b.name_zh || b.tool_name || ''), 'zh-Hans-CN');
        if (sort === 'name') {
            list = list.slice().sort(byName);
        } else if (sort === 'recent') {
            // 版本序而非 release_id：后者是随机串，排序没有意义
            list = list.slice().sort((a, b) => String(b.version_sort || '')
                .localeCompare(String(a.version_sort || '')));
        } else {
            list = list.slice().sort((a, b) => {
                const ra = a.recommended ? 1 : 0;
                const rb = b.recommended ? 1 : 0;
                if (ra !== rb) return rb - ra;
                return byName(a, b);
            });
        }
        return list;
    },

    /** 单个目录条目卡片。ctx 用于判断已安装/可更新/依赖底座。 */
    catalogCard(item, ctx) {
        const localState = ctx.local && ctx.local.local;
        const installed = localState
            ? ToolboxViews._installedByTool(localState).get(String(item.tool_id))
            : null;
        const hasUpdate = ToolboxViews.hasUpdate(item, installed);

        const installKind = item.install_kind
            || (item.resource_kind === 'runtime' ? 'runtime_zip_root'
                : item.resource_kind === 'package' ? 'game_relative_files'
                    : item.resource_kind === 'download' ? 'download_only' : 'bepinex_plugin_dll');
        const kindLabel = ToolboxViews.installKindLabel(installKind);
        const needsRuntime = !!item.requires_runtime
            && installKind !== 'runtime_zip_root'
            && !(localState && localState.runtime);

        const name = item.name_zh || item.tool_name || '';
        const en = item.name_zh && item.name_zh !== item.tool_name ? item.tool_name : '';
        const cover = item.cover_url
            ? `<img src="${ToolboxViews.esc(item.cover_url)}" alt="" loading="lazy"
                    style="position:absolute;inset:0" onerror="this.remove()">`
            : '';

        let action = `<button class="tb-btn tb-btn--sm" data-tb-action="preview"
                data-tool="${ToolboxViews.esc(item.tool_id)}"
                data-release="${ToolboxViews.esc(item.release_id)}">详情</button>`;
        if (item.downloadable) {
            const label = installKind === 'download_only' ? '下载'
                : installKind === 'runtime_zip_root' ? (installed ? '更新底座' : '安装底座')
                    : '安装';
            if (needsRuntime) {
                action += `<button class="tb-btn tb-btn--sm" disabled
                    title="需要先安装订阅工具底座">需底座</button>`;
            } else {
                action += `<button class="tb-btn tb-btn--sm tb-btn--primary" data-tb-action="install"
                    data-tool="${ToolboxViews.esc(item.tool_id)}"
                    data-release="${ToolboxViews.esc(item.release_id)}"
                    data-kind="${ToolboxViews.esc(installKind)}">
                    ${hasUpdate ? `更新` : label}</button>`;
            }
        } else if (!ctx.online || !ctx.online.logged_in) {
            action += '<span class="tb-muted" style="font-size:11px">登录后可下载</span>';
        } else {
            action += '<span class="tb-muted" style="font-size:11px"><i class="fas fa-lock"></i> 需订阅</span>';
        }

        const stateChip = hasUpdate
            ? ToolboxViews.chip('可更新', 'warn', 'arrow-circle-up')
            : (installed ? ToolboxViews.chip('已安装', 'ok', 'check') : '');

        // 依赖提示（2026-11-02）：服务端在目录里下发了依赖解析结果，
        // 这里只做展示——真正拦截在客户端安装门禁与桥接层。
        const deps = Array.isArray(item.dependencies) ? item.dependencies : [];
        const hardDeps = deps.filter((d) => d && !d.optional);
        const unmet = hardDeps.filter((d) => !d.in_catalog || d.version_satisfied === false);
        let depChip = '';
        if (hardDeps.length) {
            const names = hardDeps.map((d) => d.tool_name || `#${d.tool_id}`).join('、');
            depChip = unmet.length
                ? ToolboxViews.chip(`缺依赖 ${unmet.length}`, 'warn', 'triangle-exclamation')
                : ToolboxViews.chip(`依赖 ${hardDeps.length}`, 'info', 'link');
            depChip = `<span title="需要：${ToolboxViews.esc(names)}">${depChip}</span>`;
        }

        const meta = [
            item.author ? ToolboxViews.esc(item.author) : '',
            item.category ? ToolboxViews.esc(item.category) : '',
            `v${ToolboxViews.esc(item.version || '')}`,
        ].filter(Boolean).join(' · ');

        return `<article class="tb-item">
            <div class="tb-item-cover">
                <div class="tb-item-cover-fallback">${ToolboxViews.esc(ToolboxViews._initial(item))}</div>
                ${cover}
                <div class="tb-item-badges">
                    ${ToolboxViews.accessBadge(item)}
                    <span class="tb-badge tb-badge--plain">${ToolboxViews.esc(kindLabel)}</span>
                </div>
            </div>
            <div class="tb-item-body">
                <div class="tb-item-name" title="${ToolboxViews.esc(name)}">${ToolboxViews.esc(name)}</div>
                ${en ? `<div class="tb-item-en" title="${ToolboxViews.esc(en)}">${ToolboxViews.esc(en)}</div>` : ''}
                <div class="tb-item-summary">${ToolboxViews.esc(item.summary || '暂无简介')}</div>
                <div class="tb-item-meta">${meta}</div>
                <div class="tb-item-meta">${stateChip}${depChip}${needsRuntime ? ToolboxViews.chip('需底座', 'warn', 'layer-group') : ''}</div>
            </div>
            <div class="tb-item-foot">${action}</div>
        </article>`;
    },

    catalog(ctx) {
        const online = ctx.online || {};
        const items = (online.catalog && online.catalog.items) || [];
        const errors = online.errors || {};
        const loading = ctx.loading || {};

        // 首次进入时本地/在线都还没回来：先给骨架屏，别把「读取中」显示成「没有内容」
        if ((loading.online || loading.local) && !items.length && !errors.catalog) {
            return ToolboxViews._gridSkeletons(6);
        }
        if (errors.catalog && !items.length) {
            return ToolboxViews.errorBox(
                `${errors.catalog.message || '目录暂时无法获取'}`,
                'refresh-online',
                '重新获取',
            );
        }
        if (!items.length) {
            return ToolboxViews.empty('box-open', '本赛季暂未发布内容。<br>内容上架后刷新即可看到。');
        }

        const filtered = ToolboxViews.filterCatalog(
            items,
            { query: ctx.query, filter: ctx.filter, sort: ctx.sort },
            ctx.local && ctx.local.local,
        );
        if (!filtered.length) {
            return ToolboxViews.empty('filter', '没有符合筛选条件的内容。<br>换个关键词或把筛选切回「全部」。');
        }
        return filtered.map((it) => ToolboxViews.catalogCard(it, ctx)).join('');
    },

    // ---------- 已安装 ----------

    runtimeCard(ctx) {
        const local = (ctx.local && ctx.local.local) || {};
        const rt = local.runtime;
        const catalogItems = (ctx.online && ctx.online.catalog && ctx.online.catalog.items) || [];
        const latest = ToolboxViews._catalogLatest(catalogItems);
        const runtimeItem = latest.get(ToolboxViews._runtimeToolId(latest, catalogItems));
        const hasUpdate = ToolboxViews.hasUpdate(runtimeItem, rt);

        const body = rt
            ? `<div class="tb-row-meta">版本 ${ToolboxViews.esc(rt.version || rt.release_id || '')}
                ${hasUpdate ? ` · 目录已发布新版本 ${ToolboxViews.esc(runtimeItem.version || '')}` : ''}</div>
               <div class="tb-row-meta">底座独立于插件：更新它会影响所有插件的加载环境，因此不参与「启动前自动更新」，只在这里手动操作。</div>`
            : '<div class="tb-row-meta">尚未安装订阅工具底座。插件安装前必须先装底座。</div>';
        const lifecycle = rt
            ? `<button class="tb-btn tb-btn--sm" data-tb-action="rollback" data-tool="runtime">
                   回滚底座</button>
               <button class="tb-btn tb-btn--sm tb-btn--danger" data-tb-action="uninstall" data-tool="runtime">
                   卸载底座</button>`
            : '';

        const action = runtimeItem && runtimeItem.downloadable
            ? `<button class="tb-btn tb-btn--sm ${hasUpdate || !rt ? 'tb-btn--primary' : ''}"
                    data-tb-action="install"
                    data-tool="${ToolboxViews.esc(runtimeItem.tool_id)}"
                    data-release="${ToolboxViews.esc(runtimeItem.release_id)}"
                    data-kind="runtime_zip_root">
                    ${rt ? '更新底座' : '安装底座'}</button>`
            : '';

        return `<div class="tb-card">
            <div class="tb-card-head">
                <h3 class="tb-card-title">
                    <i class="fas fa-layer-group"></i> 底座
                    ${rt ? ToolboxViews.chip('已安装', 'ok', 'check') : ToolboxViews.chip('未安装', 'warn', 'exclamation')}
                </h3>
                <div class="tb-row-actions">${action}${lifecycle}</div>
            </div>
            ${body}
        </div>`;
    },

    _rowTitle(name, guid) {
        return `<div class="tb-row-title">${ToolboxViews.esc(name)}${
            guid ? `<span class="tb-muted" style="font-weight:400;font-size:11px">${ToolboxViews.esc(guid)}</span>` : ''
        }</div>`;
    },

    installed(ctx) {
        if (ctx.local && ctx.local.local_error) {
            return ToolboxViews.empty('folder-open',
                `${ToolboxViews.esc(ctx.local.local_error)}<br>在「设置与诊断」里配置正确的游戏目录。`);
        }
        const local = (ctx.local && ctx.local.local) || null;
        if (!local) {
            return ctx.loading && ctx.loading.local
                ? ToolboxViews._gridSkeletons(2)
                : ToolboxViews.empty('folder-open', '尚未配置游戏目录。');
        }
        const catalogItems = (ctx.online && ctx.online.catalog && ctx.online.catalog.items) || [];
        // 只按「最新版」配对：旧实现 set() 覆盖 = 同工具多版本时"最后一行说了算"
        const byTool = ToolboxViews._catalogLatest(catalogItems);

        const plugins = local.plugins || [];
        const packages = local.packages || [];
        const unmanaged = local.unmanaged || [];

        const blocks = [];

        if (plugins.length) {
            const rows = plugins.map((p) => {
                const cat = byTool.get(String(p.tool_id));
                const hasUpdate = ToolboxViews.hasUpdate(cat, p);
                const title = cat ? (cat.name_zh || cat.tool_name || p.tool_id) : p.tool_id;
                return `<div class="tb-row">
                    <div class="tb-row-main">
                        ${ToolboxViews._rowTitle(title, p.guid)}
                        <div class="tb-row-meta">
                            版本 ${ToolboxViews.esc(p.version || p.release_id || '')}
                            · ID ${ToolboxViews.esc(p.tool_id)}
                            ${p.installed_at ? ` · 安装于 ${ToolboxViews.esc(ToolboxViews.fmtDateTime(p.installed_at))}` : ''}
                        </div>
                        <div class="tb-item-meta" style="margin-top:4px">
                            ${p.enabled ? ToolboxViews.chip('已启用', 'ok', 'toggle-on') : ToolboxViews.chip('已停用', '', 'toggle-off')}
                            ${hasUpdate ? ToolboxViews.chip(`可更新 → ${cat.version || ''}`, 'warn', 'arrow-circle-up') : ''}
                        </div>
                    </div>
                    <div class="tb-row-actions">
                        ${hasUpdate && cat && cat.downloadable ? `<button class="tb-btn tb-btn--sm tb-btn--primary"
                            data-tb-action="install" data-tool="${ToolboxViews.esc(p.tool_id)}"
                            data-release="${ToolboxViews.esc(cat.release_id)}" data-kind="bepinex_plugin_dll">更新</button>` : ''}
                        <button class="tb-btn tb-btn--sm" data-tb-action="toggle"
                            data-tool="${ToolboxViews.esc(p.tool_id)}" data-enable="${p.enabled ? '0' : '1'}">
                            ${p.enabled ? '停用' : '启用'}</button>
                        <button class="tb-btn tb-btn--sm" data-tb-action="open-folder" data-tool="${ToolboxViews.esc(p.tool_id)}">目录</button>
                        <button class="tb-btn tb-btn--sm" data-tb-action="verify" data-tool="${ToolboxViews.esc(p.tool_id)}">检查</button>
                        <button class="tb-btn tb-btn--sm" data-tb-action="rollback" data-tool="${ToolboxViews.esc(p.tool_id)}">回滚</button>
                        <button class="tb-btn tb-btn--sm tb-btn--danger" data-tb-action="uninstall" data-tool="${ToolboxViews.esc(p.tool_id)}">卸载</button>
                    </div>
                </div>`;
            }).join('');
            blocks.push(`<div class="tb-card">
                <div class="tb-card-head"><h3 class="tb-card-title">
                    <i class="fas fa-plug"></i> BepInEx 插件
                    <span class="tb-muted" style="font-weight:400">${plugins.length} 个</span>
                </h3></div>
                <div class="tb-rows">${rows}</div>
            </div>`);
        }

        if (packages.length) {
            const rows = packages.map((p) => {
                const cat = byTool.get(String(p.tool_id));
                const hasUpdate = ToolboxViews.hasUpdate(cat, p);
                const title = cat ? (cat.name_zh || cat.tool_name || p.tool_id) : p.tool_id;
                return `<div class="tb-row">
                    <div class="tb-row-main">
                        ${ToolboxViews._rowTitle(title, '')}
                        <div class="tb-row-meta">
                            版本 ${ToolboxViews.esc(p.version || p.release_id || '')}
                            · ID ${ToolboxViews.esc(p.tool_id)}
                            ${p.target_dir ? ` → <code>${ToolboxViews.esc(p.target_dir)}</code>` : ''}
                        </div>
                        <div class="tb-item-meta" style="margin-top:4px">
                            ${ToolboxViews.chip('文件包', '', 'file-archive')}
                            ${hasUpdate ? ToolboxViews.chip(`可更新 → ${cat.version || ''}`, 'warn', 'arrow-circle-up') : ''}
                        </div>
                    </div>
                    <div class="tb-row-actions">
                        ${hasUpdate && cat && cat.downloadable ? `<button class="tb-btn tb-btn--sm tb-btn--primary"
                            data-tb-action="install" data-tool="${ToolboxViews.esc(p.tool_id)}"
                            data-release="${ToolboxViews.esc(cat.release_id)}" data-kind="game_relative_files">更新</button>` : ''}
                        <button class="tb-btn tb-btn--sm" data-tb-action="open-folder" data-tool="${ToolboxViews.esc(p.tool_id)}">目录</button>
                        <button class="tb-btn tb-btn--sm" data-tb-action="verify" data-tool="${ToolboxViews.esc(p.tool_id)}">检查</button>
                        <button class="tb-btn tb-btn--sm" data-tb-action="rollback" data-tool="${ToolboxViews.esc(p.tool_id)}">回滚</button>
                        <button class="tb-btn tb-btn--sm tb-btn--danger" data-tb-action="uninstall" data-tool="${ToolboxViews.esc(p.tool_id)}">卸载</button>
                    </div>
                </div>`;
            }).join('');
            blocks.push(`<div class="tb-card">
                <div class="tb-card-head"><h3 class="tb-card-title">
                    <i class="fas fa-file-archive"></i> 游戏目录文件包
                    <span class="tb-muted" style="font-weight:400">${packages.length} 个</span>
                </h3></div>
                <div class="tb-rows">${rows}</div>
            </div>`);
        }

        if (!plugins.length && !packages.length) {
            blocks.push(`<div class="tb-card">
                <div class="tb-card-head"><h3 class="tb-card-title">
                    <i class="fas fa-puzzle-piece"></i> 已安装内容
                </h3></div>
                ${ToolboxViews.empty('puzzle-piece', '还没有安装任何插件或文件包。<br>到「内容目录」里挑一个安装。')}
            </div>`);
        }

        if (unmanaged.length) {
            const list = unmanaged.map((u) => `<div class="tb-row">
                <div class="tb-row-main">
                    <div class="tb-row-meta" style="margin-top:0"><code>${ToolboxViews.esc(u)}</code></div>
                </div>
                <div class="tb-row-actions">
                    <span class="tb-muted" style="font-size:11px">非 LCTA 管理</span>
                </div>
            </div>`).join('');
            blocks.push(`<div class="tb-card">
                <div class="tb-card-head"><h3 class="tb-card-title">
                    <i class="fas fa-user-shield"></i> 非受管插件
                    <span class="tb-muted" style="font-weight:400">${unmanaged.length} 个 · 不会被自动删除或升级</span>
                </h3></div>
                <div class="tb-rows">${list}</div>
            </div>`);
        }

        return blocks.join('');
    },

    installedSummary(ctx) {
        const local = (ctx.local && ctx.local.local) || null;
        if (!local) return '';
        const plugins = (local.plugins || []).length;
        const packages = (local.packages || []).length;
        const updates = ToolboxViews.updateCount(ctx);
        const parts = [`插件 ${plugins}`, `文件包 ${packages}`];
        if (updates) parts.push(`${updates} 项可更新`);
        return parts.join(' · ');
    },

    // ---------- 账号与订阅 ----------

    subscriptionBlock(ctx) {
        const online = ctx.online || {};
        const access = online.access || null;
        const season = online.season || {};
        const seasonName = season.name || season.slug || '当前赛季';

        if (!access) {
            const err = (online.errors || {}).access;
            if (err) {
                return ToolboxViews.errorBox(
                    `订阅状态暂时无法获取：${err.message || err}`,
                    'refresh-online', '重试',
                ) + '<p class="form-hint" style="margin-top:6px">本地安装管理不受影响，仍可停用/卸载/回滚。</p>';
            }
            return '';
        }

        if (!access.season_active) {
            return `<div class="tb-row">
                <div class="tb-row-main">
                    <div class="tb-row-title"><i class="fas fa-hourglass-half"></i> 当前赛季未开放</div>
                    <div class="tb-row-meta">站点暂停开放期间无法获取原创内容，本地已安装内容仍可管理。</div>
                </div>
            </div>`;
        }

        if (access.unlocked) {
            const sources = (access.sources || []).map((s) => {
                if (s.subscription_kind === 'monthly') {
                    const end = s.expires_at ? ToolboxViews.fmtDateTime(s.expires_at).slice(0, 10) : '未知';
                    return `按月（至 ${end}）`;
                }
                return '按赛季';
            }).join('、');
            const until = (access.sources || [])
                .filter((s) => s.expires_at)
                .map((s) => ToolboxViews.fmtDateTime(s.expires_at).slice(0, 10))
                .sort()
                .pop();
            return `<div class="tb-row">
                <div class="tb-row-main">
                    <div class="tb-row-title">
                        <i class="fas fa-unlock" style="color:var(--color-success)"></i>
                        ${ToolboxViews.esc(seasonName)} 已解锁
                    </div>
                    <div class="tb-row-meta">
                        ${sources ? `订阅来源：${ToolboxViews.esc(sources)}` : '管理员账号：无需订阅'}
                        ${until ? ` · 最近到期 ${ToolboxViews.esc(until)}` : ''}
                    </div>
                </div>
            </div>`;
        }

        const reasonText = {
            account_inactive: '账号已被禁用，请联系站长。',
            season_inactive: '当前赛季尚未开放，请稍后再来。',
            email_required: '请先绑定并验证邮箱（可在资源站账号设置里完成）。',
            entitlement_required: '还没有有效订阅 —— 在爱发电订阅后点「刷新订阅状态」即可。',
            scope_not_allowed: '当前登录方式不能获取订阅资格，请用账号密码登录。',
        }[access.reason] || '';

        const monthly = season.monthly_price_cents;
        const priceLine = monthly != null
            ? `按月 ¥${(monthly / 100).toFixed(2)} / 月（跨赛季不中断）；转载内容无需订阅，登录即可下载。`
            : '';

        return `<div class="tb-row">
            <div class="tb-row-main">
                <div class="tb-row-title">
                    <i class="fas fa-lock" style="color:var(--color-warning)"></i>
                    ${ToolboxViews.esc(seasonName)} 尚未订阅
                </div>
                <div class="tb-row-meta">${ToolboxViews.esc(reasonText)}</div>
                ${priceLine ? `<div class="tb-row-meta">${ToolboxViews.esc(priceLine)}</div>` : ''}
            </div>
        </div>`;
    },

    afdianBlock(ctx) {
        const afdian = (ctx.online || {}).afdian;
        if (!afdian) return '';
        if (!afdian.configured) {
            return `<div class="tb-row">
                <div class="tb-row-main">
                    <div class="tb-row-title"><i class="fas fa-link"></i> 爱发电核验未配置</div>
                    <div class="tb-row-meta">请联系站长人工核验订阅。</div>
                </div>
            </div>`;
        }
        if (!afdian.bound) {
            return `<div class="tb-row">
                <div class="tb-row-main">
                    <div class="tb-row-title"><i class="fas fa-link"></i> 关联爱发电账号</div>
                    <div class="tb-row-meta">关联后系统会自动查询你的订阅并判断资格，无需填写订单号。</div>
                </div>
                <div class="tb-row-actions">
                    <button class="tb-btn tb-btn--sm tb-btn--primary" data-tb-action="afdian-bind">关联账号</button>
                </div>
            </div>`;
        }
        return `<div class="tb-row">
            <div class="tb-row-main">
                <div class="tb-row-title">
                    <i class="fas fa-link" style="color:var(--color-success)"></i>
                    已关联（${ToolboxViews.esc(afdian.provider_user_id || '')}）
                </div>
                <div class="tb-row-meta">订阅成功后点「刷新订阅状态」；核验由服务器主动向爱发电查询订单完成。</div>
            </div>
            <div class="tb-row-actions">
                <button class="tb-btn tb-btn--sm tb-btn--primary" data-tb-action="afdian-refresh">刷新订阅状态</button>
                <button class="tb-btn tb-btn--sm" data-tb-action="toggle-order">手动填订单号</button>
            </div>
        </div>
        <div class="tb-inline" id="tb-order-row" style="display:none;margin-top:8px">
            <input type="text" id="tb-order-no" placeholder="爱发电订单号" style="max-width:240px">
            <button class="tb-btn tb-btn--sm" data-tb-action="verify-order">核验订单</button>
        </div>`;
    },

    puzzleBlock(ctx) {
        const season = (ctx.online || {}).season || {};
        const access = (ctx.online || {}).access;
        if (!season.puzzle_enabled || !access || access.unlocked) return '';
        return `<div class="tb-row" id="tb-puzzle-row">
            <div class="tb-row-main">
                <div class="tb-row-title"><i class="fas fa-puzzle-piece"></i> 解谜获取资格（站点开放时）</div>
                <div class="tb-row-meta">赛季开放谜题时，解题成功可获得当季资格。</div>
                <div id="tb-puzzle-body" style="margin-top:8px"></div>
            </div>
            <div class="tb-row-actions">
                <button class="tb-btn tb-btn--sm" data-tb-action="puzzle-new">获取我的挑战</button>
            </div>
        </div>`;
    },

    account(ctx) {
        const online = ctx.online || {};
        if (ctx.loading && ctx.loading.online && !online.logged_in && !online.catalog) {
            return ToolboxViews._gridSkeletons(2);
        }
        const blocks = [];

        if (!online.logged_in) {
            const base = ctx.base_url || 'https://mods.lcta.top';
            blocks.push(`<div class="tb-card">
                <div class="tb-card-head">
                    <h3 class="tb-card-title"><i class="fas fa-user"></i> 登录资源站</h3>
                </div>
                <p class="form-hint" style="margin-top:0">
                    使用资源站（${ToolboxViews.esc(base)}）账号：原创内容需有效订阅，转载内容登录即可下载。
                </p>
                <div class="tb-form">
                    <input type="text" id="tb-login-identifier" placeholder="用户名或邮箱" autocomplete="username">
                    <input type="password" id="tb-login-password" placeholder="密码" autocomplete="current-password"
                           data-tb-enter="login">
                    <div class="tb-inline">
                        <button class="tb-btn tb-btn--primary" data-tb-action="login">
                            <i class="fas fa-sign-in-alt"></i> 登录
                        </button>
                        <button class="tb-btn" data-tb-action="open-register">
                            注册账号
                        </button>
                        <button class="tb-btn tb-btn--ghost" data-tb-action="open-forgot">
                            忘记密码
                        </button>
                    </div>
                    <p class="form-hint">
                        注册与找回密码在系统浏览器里完成（需要邮箱验证码），完成后回到本页登录。
                    </p>
                    ${ctx.mirror_auth_available ? `<div class="tb-inline" style="padding-top:8px;border-top:1px dashed var(--color-border)">
                        <span class="form-hint" style="margin:0">检测到 Mod 镜像站已登录</span>
                        <button class="tb-btn tb-btn--sm" data-tb-action="sync-login">同步登录态</button>
                    </div>` : ''}
                </div>
            </div>`);
        } else {
            const user = online.user || {};
            const who = user.username || user.email || '已登录';
            blocks.push(`<div class="tb-card">
                <div class="tb-card-head">
                    <h3 class="tb-card-title">
                        <i class="fas fa-user-check" style="color:var(--color-success)"></i> ${ToolboxViews.esc(who)}
                    </h3>
                    <div class="tb-row-actions">
                        <button class="tb-btn tb-btn--sm" data-tb-action="logout">登出</button>
                    </div>
                </div>
                <div class="tb-rows">
                    ${ToolboxViews.subscriptionBlock(ctx)}
                    ${ToolboxViews.afdianBlock(ctx)}
                    ${ToolboxViews.puzzleBlock(ctx)}
                </div>
            </div>`);
        }

        if (ctx.local && ctx.local.game_running === true) {
            blocks.push(`<div class="tb-error">
                <i class="fas fa-exclamation-triangle"></i>
                <span>游戏正在运行：安装/启停会被拒绝，请先关闭游戏。本地浏览与订阅状态不受影响。</span>
            </div>`);
        }

        return blocks.join('');
    },

    // ---------- 设置与诊断 ----------

    settings(ctx) {
        const online = ctx.online || {};
        const local = ctx.local || {};
        const catalogItems = (online.catalog && online.catalog.items) || [];
        const localState = local.local || {};
        const rows = [
            ['桥协议版本', ctx.protocol_version],
            ['资源站地址', online.base_url || ctx.base_url],
            ['目录条目', `${catalogItems.length} 项`],
            ['本地已安装', `${(localState.plugins || []).length} 插件 / ${(localState.packages || []).length} 文件包`],
            ['上次在线刷新', online.fetched_at ? ToolboxViews.fmtDateTime(online.fetched_at) : '本次会话未刷新'],
        ].map(([k, v]) => `<dt>${ToolboxViews.esc(k)}</dt><dd>${ToolboxViews.esc(v == null ? '—' : v)}</dd>`).join('');

        const errs = Object.entries(online.errors || {});
        const errBlock = errs.length
            ? `<div style="margin-top:10px">${errs.map(([part, info]) => `<div class="tb-error">
                    <i class="fas fa-exclamation-triangle"></i>
                    <span>${ToolboxViews.esc(part)}：${ToolboxViews.esc(info.message || '')}</span>
                </div>`).join('')}</div>`
            : '';

        return `<dl class="tb-kv">${rows}</dl>${errBlock}`;
    },

    rootStatus(ctx) {
        const local = ctx.local || {};
        if (local.local_error) {
            return `<div class="tb-error">
                <i class="fas fa-exclamation-triangle"></i>
                <span>${ToolboxViews.esc(local.local_error)}</span>
            </div>`;
        }
        if (!local.game_root) return '';
        const running = local.game_running === true
            ? ToolboxViews.chip('游戏运行中', 'warn', 'exclamation-triangle')
            : (local.game_running === false ? ToolboxViews.chip('游戏未运行', 'ok', 'check') : '');
        return `<div class="tb-inline">
            ${ToolboxViews.chip('目录已校验', 'ok', 'folder')}
            ${running}
            <span class="tb-muted" style="font-size:12px">${ToolboxViews.esc(local.game_root)}</span>
        </div>`;
    },

    // ---------- 详情抽屉 ----------

    drawer(item, ctx) {
        const installKind = item.install_kind
            || (item.resource_kind === 'runtime' ? 'runtime_zip_root'
                : item.resource_kind === 'package' ? 'game_relative_files'
                    : item.resource_kind === 'download' ? 'download_only' : 'bepinex_plugin_dll');
        const kindLabel = ToolboxViews.installKindLabel(installKind);
        const files = item.files || [];
        const total = files.reduce((n, f) => n + (Number(f.size) || 0), 0);

        const images = (item.image_urls || []).filter(Boolean);
        const hero = item.cover_url || images[0] || '';
        const gallery = images.filter((u) => u !== hero).slice(0, 8);

        const fileRows = files.length
            ? `<div class="tb-filelist">${files.map((f) => `<div class="tb-filelist-row">
                    <span class="tb-filelist-path">${ToolboxViews.esc(f.path)}</span>
                    <span class="tb-filelist-size">${ToolboxViews.esc(ToolboxViews.fmtBytes(f.size))}</span>
                </div>`).join('')}</div>`
            : '<p class="form-hint" style="margin:0">当前账号看不到文件元数据（原创内容需订阅解锁）。</p>';

        const body = `
            ${hero ? `<img class="tb-hero" src="${ToolboxViews.esc(hero)}" alt="" onerror="this.remove()">` : ''}
            <div class="tb-inline">
                ${ToolboxViews.accessBadge(item)}
                <span class="tb-badge tb-badge--plain">${ToolboxViews.esc(kindLabel)}</span>
                <span class="tb-muted">v${ToolboxViews.esc(item.version || '')}</span>
                ${item.recommended ? ToolboxViews.chip('推荐', 'ok', 'thumb-up') : ''}
            </div>
            ${item.name_zh && item.name_zh !== item.tool_name
                ? `<div class="tb-muted" style="font-size:12px">${ToolboxViews.esc(item.tool_name)}</div>` : ''}
            ${item.author ? `<div class="tb-muted" style="font-size:12px">作者：${ToolboxViews.esc(item.author)}</div>` : ''}
            ${item.category || item.tags
                ? `<div class="tb-muted" style="font-size:12px">${ToolboxViews.esc([item.category, item.tags].filter(Boolean).join(' · '))}</div>` : ''}
            ${item.description || item.summary
                ? `<p style="margin:0;font-size:13px;line-height:1.7;white-space:pre-wrap">${ToolboxViews.esc(item.description || item.summary)}</p>` : ''}
            ${item.target_dir ? `<div class="tb-muted" style="font-size:12px">安装到：<code>${ToolboxViews.esc(item.target_dir)}</code></div>` : ''}
            ${installKind === 'download_only'
                ? '<div class="tb-muted" style="font-size:12px">只下载到系统「下载」目录，不会写入游戏目录。</div>' : ''}
            ${item.requires_runtime ? '<div class="tb-muted" style="font-size:12px">需要先安装订阅工具底座。</div>' : ''}
            ${item.compat_note ? `<div class="tb-muted" style="font-size:12px">兼容说明：${ToolboxViews.esc(item.compat_note)}</div>` : ''}
            ${item.release_notes ? `<div class="tb-muted" style="font-size:12px">版本说明：${ToolboxViews.esc(item.release_notes)}</div>` : ''}
            <div class="tb-muted" style="font-size:12px">文件：${files.length} 个${total ? `，共 ${ToolboxViews.esc(ToolboxViews.fmtBytes(total))}` : ''}</div>
            ${fileRows}
            ${gallery.length ? `<div class="tb-gallery">${gallery.map((u) => `<img src="${ToolboxViews.esc(u)}" alt="" loading="lazy" onerror="this.remove()">`).join('')}</div>` : ''}
        `;

        const localState = (ctx.local && ctx.local.local) || {};
        const installed = ToolboxViews._installedByTool(localState).get(String(item.tool_id));
        const hasUpdate = ToolboxViews.hasUpdate(item, installed);

        let foot = '<button class="tb-btn" data-tb-action="drawer-close">关闭</button>';
        if (installKind === 'download_only') {
            foot = `<button class="tb-btn" data-tb-action="open-downloads">打开下载目录</button>${foot}`;
        }
        if (item.downloadable) {
            const label = installKind === 'download_only' ? '下载到下载目录'
                : installKind === 'runtime_zip_root' ? (installed ? '更新底座' : '安装底座')
                    : installKind === 'game_relative_files' ? '安装到游戏目录' : (hasUpdate ? '更新' : '安装');
            foot = `<button class="tb-btn tb-btn--primary" data-tb-action="install"
                data-tool="${ToolboxViews.esc(item.tool_id)}"
                data-release="${ToolboxViews.esc(item.release_id)}"
                data-kind="${ToolboxViews.esc(installKind)}">${label}</button>${foot}`;
        } else if (!ctx.online || !ctx.online.logged_in) {
            foot = '<span class="tb-muted">登录后可下载</span>' + foot;
        } else {
            foot = '<span class="tb-muted">需订阅解锁</span>' + foot;
        }

        return {
            title: item.name_zh || item.tool_name || '内容详情',
            body,
            foot,
        };
    },

    // ---------- 任务坞 ----------

    taskDock(snap) {
        if (!snap) return '';
        const current = snap.current;
        const history = snap.history || [];
        const last = history.length ? history[history.length - 1] : null;

        if (current) {
            const pct = Math.max(0, Math.min(100, Number(current.percent) || 0));
            return `<div class="tb-taskdock-head">
                    <span><i class="fas fa-spinner fa-spin"></i> ${ToolboxViews.esc(current.label || '任务进行中')}</span>
                    <span class="tb-muted">${pct}%</span>
                </div>
                <div class="tb-progress"><div class="tb-progress-fill" style="width:${pct}%"></div></div>
                <div class="tb-taskdock-text">${ToolboxViews.esc(current.text || '')}</div>`;
        }
        if (!last) return '';
        const ok = last.status === 'done';
        const when = last.finished_at ? ToolboxViews.fmtDateTime(last.finished_at) : '';
        return `<div class="tb-taskdock-head">
                <span><i class="fas fa-${ok ? 'check-circle' : 'exclamation-circle'}"
                    style="color:${ok ? 'var(--color-success)' : 'var(--color-danger)'}"></i>
                    ${ok ? '最近任务完成' : '最近任务失败'}</span>
                <button class="tb-icon-btn" data-tb-action="task-dismiss" title="收起">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="tb-taskdock-text">${ToolboxViews.esc(last.label || '')} · ${ToolboxViews.esc(when)}</div>
            ${last.message ? `<div class="tb-taskdock-text" style="white-space:normal">${ToolboxViews.esc(last.message)}</div>` : ''}`;
    },
};

window.ToolboxViews = ToolboxViews;
