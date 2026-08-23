// ============================
// 通用插件窗口引导器（公共仓库 · 工具无关）
// ============================
// 职责：
//   1) 等待 pywebview 桥就绪（防竞态，同 rule-editor.js 模式）
//   2) pw_get_bootstrap() 取回 {title, theme, js}
//      - title/theme：设置窗口标题与主题类
//      - js：解密后的功能脚本（私有仓库加密包分发，与打包源码同信任级，
//        与 cheat-shell.js 一致使用 new Function 注入执行）
//   3) 功能脚本约定挂载 window.initPluginWindow()，由本壳在注入后调用；
//      功能 UI 渲染进 #pw-root（壳只提供容器，不感知任何工具语义）
// 失败兜底：锁定 / 数据缺失 / 脚本异常时渲染提示卡，保证窗口不留白屏。

(function () {
    'use strict';

    var _bootstrapped = false;

    function applyTheme(theme) {
        document.body.className = 'theme-' + (theme || 'light');
    }
    window.applyTheme = applyTheme;

    // 兜底提示卡（功能加载失败 / 未解锁等场景），可被后续重试覆盖
    window.pwShowFallback = function (title, detail) {
        var root = document.getElementById('pw-root');
        if (!root) return;
        root.innerHTML =
            '<div class="pw-fallback">' +
            '<h3><i class="fas fa-triangle-exclamation"></i> ' + _esc(title || '插件窗口不可用') + '</h3>' +
            '<p>' + _esc(detail || '') + '</p>' +
            '</div>';
    };

    function _esc(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function getApi() {
        return (typeof window !== 'undefined' && window.pywebview && window.pywebview.api)
            ? window.pywebview.api : null;
    }

    function waitForApi(timeoutMs) {
        return new Promise(function (resolve) {
            if (getApi()) { resolve(getApi()); return; }
            var timer = setTimeout(function () {
                window.removeEventListener('pywebviewready', onReady);
                resolve(null);
            }, timeoutMs || 15000);
            function onReady() {
                clearTimeout(timer);
                resolve(getApi());
            }
            window.addEventListener('pywebviewready', onReady);
        });
    }

    // CodeMirror 由 <script type=module> 异步挂载；功能 JS 初始化前确保可用
    // （超时不视为致命：功能脚本可自行决定是否需要编辑器）
    function waitForCodeMirror(timeoutMs) {
        return new Promise(function (resolve) {
            var waited = 0;
            var timer = setInterval(function () {
                waited += 100;
                if (window.CodeMirror || waited >= (timeoutMs || 10000)) {
                    clearInterval(timer);
                    resolve(window.CodeMirror || null);
                }
            }, 100);
        });
    }

    function hideLoading() {
        var loading = document.getElementById('pw-loading');
        if (loading && loading.parentElement) {
            loading.parentElement.removeChild(loading);
        }
    }

    async function bootstrap() {
        if (_bootstrapped) return;
        _bootstrapped = true;

        var api = await waitForApi(15000);
        if (!api || typeof api.pw_get_bootstrap !== 'function') {
            hideLoading();
            window.pwShowFallback('窗口初始化失败', '后端桥接不可用（pw_get_bootstrap 缺失）');
            return;
        }

        var res = null;
        try {
            res = await api.pw_get_bootstrap();
        } catch (e) {
            hideLoading();
            window.pwShowFallback('窗口初始化失败', String(e));
            return;
        }
        if (!res || !res.success) {
            hideLoading();
            var reasonMap = {
                locked: '作弊工具箱未解锁，请先在主窗口「作弊工具箱」页输入密钥解锁。',
                consent_required: '请先在主窗口「作弊工具箱」页阅读并同意风险须知。'
            };
            var msg = reasonMap[res && res.reason] || (res && res.message) || '功能不可用';
            window.pwShowFallback(res && res.reason === 'locked' ? '工具箱未解锁'
                : (res && res.reason === 'consent_required' ? '需要同意风险须知' : '插件窗口不可用'), msg);
            return;
        }

        var data = res.data || {};
        if (data.title) document.title = data.title;
        applyTheme(data.theme);

        if (!data.js || !String(data.js).trim()) {
            hideLoading();
            window.pwShowFallback('插件窗口数据缺失', '未返回功能脚本');
            return;
        }
        try {
            // 解密 JS 来自自有加密包，与打包源码同信任级（同 cheat-shell.js 约定）
            (new Function(data.js))(); // eslint-disable-line no-new-func
        } catch (e) {
            hideLoading();
            console.error('[plugin-window] feature script error:', e);
            window.pwShowFallback('功能加载失败', String(e));
            return;
        }

        await waitForCodeMirror(10000);

        if (typeof window.initPluginWindow === 'function') {
            try {
                hideLoading();
                window.initPluginWindow();
            } catch (e) {
                console.error('[plugin-window] initPluginWindow error:', e);
                window.pwShowFallback('功能初始化失败', String(e));
            }
        } else {
            hideLoading();
            window.pwShowFallback('插件窗口数据异常', '功能脚本未定义 initPluginWindow 入口');
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootstrap);
    } else {
        bootstrap();
    }
})();
