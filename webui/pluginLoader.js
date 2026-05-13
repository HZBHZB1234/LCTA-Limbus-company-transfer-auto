/**
 * pluginLoader.js —— LCTA v5.0.0 插件加载系统
 *
 * 职责:
 *   1. 初始化时从后端获取全量配置 schema + 值 + 导航
 *   2. 按需激活插件页面（动态加载 HTML/JS/CSS）
 *   3. 管理导航按钮的 active 状态
 *
 * 用法:
 *   document.addEventListener('DOMContentLoaded', () => pluginLoader.init());
 */

const pluginLoader = {
    _loadedPlugins: {},
    _activePluginId: null,
    _navConfig: [],

    /** 初始化：获取配置同步和导航 */
    async init() {
        try {
            const sync = await window.pywebview.api.config_get_full_sync();
            if (configManager && configManager.applyFullSync) {
                configManager.applyFullSync(sync.schema, sync.values);
            }
            this._navConfig = sync.nav || [];
            this._buildNav(this._navConfig);
            console.log(`[pluginLoader] 初始化完成，发现 ${this._navConfig.length} 个导航项`);
        } catch (e) {
            console.error('[pluginLoader] 初始化失败:', e);
        }
    },

    /** 激活插件页面 */
    async activatePlugin(pluginId) {
        if (this._activePluginId === pluginId) return;

        try {
            const result = await window.pywebview.api.plugin_activate(pluginId);
            if (!result.success) {
                console.error(`[pluginLoader] 激活插件失败: ${result.message}`);
                return;
            }

            const contentArea = document.getElementById('page-content');
            if (!contentArea) return;

            // 清除旧插件 CSS
            document.querySelectorAll('style[data-plugin]').forEach(s => s.remove());

            // 渲染 HTML
            if (result.html) {
                contentArea.innerHTML = result.html;
            }

            // 动态加载 CSS
            if (result.css) {
                Object.entries(result.css).forEach(([filename, css]) => {
                    const style = document.createElement('style');
                    style.textContent = css;
                    style.dataset.plugin = pluginId;
                    document.head.appendChild(style);
                });
            }

            // 动态执行 JS
            if (result.js) {
                Object.entries(result.js).forEach(([filename, code]) => {
                    try {
                        const fn = new Function('pluginLoader', 'configManager', code);
                        fn(pluginLoader, configManager);
                    } catch (e) {
                        console.error(`[pluginLoader] 执行 ${filename} 失败:`, e);
                    }
                });
            }

            this._activePluginId = pluginId;
            this._updateActiveNav(pluginId);

            console.log(`[pluginLoader] 已激活插件: ${pluginId}`);
        } catch (e) {
            console.error(`[pluginLoader] 激活插件异常:`, e);
        }
    },

    /** 从后端导航配置构建侧边栏按钮 */
    _buildNav(navConfig) {
        const menu = document.querySelector('.sidebar-menu');
        if (!menu) return;

        navConfig.forEach(item => {
            // 检查是否已存在该按钮
            if (document.getElementById(item.id)) return;

            const btn = document.createElement('button');
            btn.id = item.id;
            btn.className = 'nav-btn';
            btn.innerHTML = `<i class="${item.icon}"></i><span>${item.label}</span><div class="nav-indicator"></div>`;
            btn.addEventListener('click', () => this.activatePlugin(item.plugin_id));

            // 条件可见
            if (item.visible_when && configManager) {
                const { config_key, equals } = item.visible_when;
                if (configManager.get(config_key) !== equals) {
                    btn.style.display = 'none';
                }
            }

            menu.appendChild(btn);
        });
    },

    /** 更新导航按钮的 active 状态 */
    _updateActiveNav(pluginId) {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        const manifest = this._navConfig.find(n => n.plugin_id === pluginId);
        if (manifest) {
            const btn = document.getElementById(manifest.id);
            if (btn) btn.classList.add('active');
        }
    },

    /** 获取当前活跃的插件 ID */
    getActivePluginId() {
        return this._activePluginId;
    }
};
