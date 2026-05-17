/**
 * pluginLoader.js —— LCTA v5.0.0 插件加载系统
 *
 * 职责:
 *   1. 初始化时从后端获取全量配置 schema + 值 + 导航
 *   2. 构建侧边栏导航按钮
 *   3. 通过 PagesManager 激活插件页面
 *   4. 管理插件页面的生命周期
 *
 * 每个插件封装一个完整页面（HTML + CSS + JS + 后端 API）。
 */

const pluginLoader = {
    _navConfig: [],

    /** 初始化：获取配置同步和导航，构建侧边栏 */
    async init() {
        try {
            const sync = await window.pywebview.api.config_get_full_sync();

            // 将 schema + values 同步到 ConfigManager
            if (configManager && configManager.applyFullSync) {
                configManager.applyFullSync(sync.schema, sync.values);
            }

            this._navConfig = sync.nav || [];
            this._buildNav(this._navConfig);

            // 版本号更新
            const versionEl = document.querySelector('.version');
            if (versionEl && sync.version) {
                versionEl.textContent = `v${sync.version}`;
            }

            console.log(`[pluginLoader] 初始化完成，schema: ${Object.keys(sync.schema || {}).length} 项，nav: ${this._navConfig.length} 项`);
        } catch (e) {
            console.error('[pluginLoader] 初始化失败:', e);
        }
    },

    /** 从后端导航配置构建侧边栏按钮 */
    _buildNav(navConfig) {
        const menu = document.querySelector('.sidebar-menu');
        if (!menu) return;

        navConfig.forEach(item => {
            if (document.getElementById(item.id)) return;

            const btn = document.createElement('button');
            btn.id = item.id;
            btn.className = 'nav-btn';
            btn.dataset.pluginId = item.plugin_id;
            btn.innerHTML = `<i class="${item.icon}"></i><span>${item.label}</span><div class="nav-indicator"></div>`;

            // 点击时通过 PagesManager 切换页面
            btn.addEventListener('click', () => {
                if (pagesManager) {
                    pagesManager.switchPage(item.plugin_id);
                }
            });

            // 条件可见
            if (item.visible_when && configManager) {
                const { config_key, equals } = item.visible_when;
                const val = configManager.get(config_key);
                if (val !== equals) {
                    btn.style.display = 'none';
                }
            }

            menu.appendChild(btn);
        });

        // 添加日志按钮（内置页面）
        if (!document.getElementById('log-btn')) {
            const logBtn = document.createElement('button');
            logBtn.id = 'log-btn';
            logBtn.className = 'nav-btn';
            logBtn.dataset.pluginId = 'log';
            logBtn.innerHTML = `<i class="fas fa-clipboard-list"></i><span>日志</span><div class="nav-indicator"></div>`;
            logBtn.addEventListener('click', () => {
                if (pagesManager) pagesManager.switchPage('log');
            });
            menu.appendChild(logBtn);
        }

        // 添加关于按钮（跳转到 update 插件页面）
        if (!document.getElementById('about-btn')) {
            const aboutBtn = document.createElement('button');
            aboutBtn.id = 'about-btn';
            aboutBtn.className = 'nav-btn';
            aboutBtn.dataset.pluginId = 'update';
            aboutBtn.innerHTML = `<i class="fas fa-info-circle"></i><span>关于</span><div class="nav-indicator"></div>`;
            aboutBtn.addEventListener('click', () => {
                if (pagesManager) pagesManager.switchPage('update');
            });
            menu.appendChild(aboutBtn);
        }
    },

    /** 获取导航配置 */
    getNavConfig() {
        return this._navConfig;
    },

    /** 获取当前活跃的插件 ID */
    getActivePluginId() {
        return pagesManager ? pagesManager.activeId : null;
    }
};
