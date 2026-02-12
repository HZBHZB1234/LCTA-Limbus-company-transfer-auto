// ==UserScript==
// @name         GM_* API Compatibility Layer
// @namespace    https://github.com/your-name
// @version      1.1.0
// @description  在普通网页中模拟油猴 GM_* 与 GM.* API，用于直接运行用户脚本
// @author       You
// @run-at       document-start
// @grant        none
// ==/UserScript==

(function() {
    'use strict';

    // ==================== 配置常量 ====================
    const STORAGE_PREFIX = 'GM_Compat_';   // localStorage 前缀
    const DEFAULT_TAB_ID = 'tab_' + Math.random().toString(36).substr(2);
    const IS_GM_ALREADY = typeof window.GM_getValue === 'function';

    // 如果浏览器已原生支持油猴 API（例如安装了扩展），则不再覆盖
    if (IS_GM_ALREADY) {
        console.warn('GM_* API 已存在，兼容层将不会覆盖。');
        return;
    }

    // ==================== 存储系统 (GM_setValue, GM_getValue ...) ====================
    const valueChangeListeners = {};
    let listenerCounter = 0;

    // 核心存储操作
    window.GM_setValue = function(key, value) {
        const oldValue = GM_getValue(key);
        const serialized = JSON.stringify(value);
        try {
            localStorage.setItem(STORAGE_PREFIX + key, serialized);
        } catch (e) {
            console.error('GM_setValue 失败:', e);
        }
        // 触发监听器
        const listeners = valueChangeListeners[key] || [];
        listeners.forEach(({ id, callback }) => {
            try {
                callback(key, oldValue, value, false);
            } catch (e) {
                console.error(`值变更监听器 (${id}) 执行失败:`, e);
            }
        });
    };

    window.GM_getValue = function(key, defaultValue) {
        const item = localStorage.getItem(STORAGE_PREFIX + key);
        if (item === null) return defaultValue;
        try {
            return JSON.parse(item);
        } catch (e) {
            return defaultValue;
        }
    };

    window.GM_deleteValue = function(key) {
        localStorage.removeItem(STORAGE_PREFIX + key);
    };

    window.GM_listValues = function() {
        const keys = [];
        for (let i = 0; i < localStorage.length; i++) {
            const fullKey = localStorage.key(i);
            if (fullKey && fullKey.startsWith(STORAGE_PREFIX)) {
                keys.push(fullKey.slice(STORAGE_PREFIX.length));
            }
        }
        return keys;
    };

    window.GM_addValueChangeListener = function(key, callback) {
        const id = ++listenerCounter;
        if (!valueChangeListeners[key]) valueChangeListeners[key] = [];
        valueChangeListeners[key].push({ id, callback });
        return id;
    };

    window.GM_removeValueChangeListener = function(listenerId) {
        for (const key in valueChangeListeners) {
            valueChangeListeners[key] = valueChangeListeners[key].filter(l => l.id !== listenerId);
            if (valueChangeListeners[key].length === 0) delete valueChangeListeners[key];
        }
    };

    // ==================== 资源模拟 (GM_getResourceText/URL) ====================
    window.GM_resources = {}; // 用户可在此预定义资源

    window.GM_getResourceText = function(name) {
        return window.GM_resources[name];
    };

    window.GM_getResourceURL = function(name) {
        const text = window.GM_resources[name];
        if (typeof text !== 'string') return '';
        // 简单转换为 data URL (仅文本类型)
        return 'data:text/plain;base64,' + btoa(text);
    };

    // ==================== 菜单命令模拟 (GM_registerMenuCommand) ====================
    const menuCommands = [];
    let menuCounter = 0;

    window.GM_registerMenuCommand = function(caption, callback, accessKey) {
        const id = ++menuCounter;
        menuCommands.push({ id, caption, callback, accessKey });
        console.log(`[GM_registerMenuCommand] 已注册: "${caption}" (ID: ${id})，可通过 GM_triggerMenuCommand(${id}) 触发。`);
        return id;
    };

    window.GM_unregisterMenuCommand = function(id) {
        const index = menuCommands.findIndex(cmd => cmd.id === id);
        if (index !== -1) menuCommands.splice(index, 1);
    };

    // 辅助函数：触发已注册的菜单命令（非油猴原生，兼容层提供）
    window.GM_triggerMenuCommand = function(id) {
        const cmd = menuCommands.find(c => c.id === id);
        if (cmd) {
            cmd.callback();
        } else {
            console.warn(`未找到 ID 为 ${id} 的菜单命令`);
        }
    };

    // ==================== 标签页通信模拟 (GM_getTab, GM_saveTab, GM_getTabs) ====================
    let tabStorage = {};

    window.GM_getTab = function(callback) {
        setTimeout(() => callback(tabStorage), 0); // 模拟异步
    };

    window.GM_saveTab = function(tab) {
        tabStorage = { ...tabStorage, ...tab };
    };

    window.GM_getTabs = function(callback) {
        const tabs = {};
        tabs[DEFAULT_TAB_ID] = tabStorage;
        setTimeout(() => callback(tabs), 0);
    };

    // ==================== GM_info ====================
    window.GM_info = {
        script: {
            name: 'Compatibility Layer',
            namespace: '',
            version: '1.0.0',
            description: 'GM_* API 兼容层',
            author: 'You',
            matches: [],
            grant: [],
            resources: {},
            'run-at': 'document-start'
        },
        scriptMetaStr: '',
        scriptHandler: 'GM_Compat',
        version: '1.0.0',
        platform: { arch: 'x86', browser: navigator.userAgent, version: navigator.appVersion }
    };

    // ==================== GM_addStyle ====================
    window.GM_addStyle = function(css) {
        const style = document.createElement('style');
        style.textContent = css;
        (document.head || document.documentElement).appendChild(style);
        return style;
    };

    // ==================== GM_addElement ====================
    window.GM_addElement = function(...args) {
        // 两种调用方式: GM_addElement(tagName, attributes) 或 GM_addElement(parent, tagName, attributes)
        let parent, tagName, attributes;
        if (args.length === 2) {
            parent = document.head || document.documentElement;
            tagName = args[0];
            attributes = args[1];
        } else if (args.length === 3) {
            parent = args[0];
            tagName = args[1];
            attributes = args[2];
        } else {
            throw new Error('GM_addElement: 参数数量错误');
        }
        const element = document.createElement(tagName);
        for (const [key, value] of Object.entries(attributes || {})) {
            if (key === 'textContent' || key === 'innerHTML') {
                element[key] = value;
            } else {
                element.setAttribute(key, value);
            }
        }
        parent.appendChild(element);
        return element;
    };

    // ==================== GM_download ====================
    window.GM_download = function(url, filename) {
        if (!url || !filename) {
            console.error('GM_download: 必须提供 url 和 filename');
            return;
        }
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.rel = 'noopener noreferrer';
        a.dispatchEvent(new MouseEvent('click'));
        console.log(`GM_download: 触发下载 ${filename} (${url})`);
    };

    // ==================== GM_log ====================
    window.GM_log = console.log;

    // ==================== GM_notification ====================
    window.GM_notification = function(options) {
        // 支持两种调用: GM_notification(text) 或 GM_notification(options)
        let text, title, onclick;
        if (typeof options === 'string') {
            text = options;
            title = 'GM Notification';
        } else {
            text = options.text || options.message;
            title = options.title || 'GM Notification';
            onclick = options.onclick;
        }
        if (!window.Notification) {
            console.warn('GM_notification: 当前浏览器不支持 Notification');
            return;
        }
        if (Notification.permission === 'granted') {
            const n = new Notification(title, { body: text });
            if (onclick) n.onclick = onclick;
        } else if (Notification.permission !== 'denied') {
            Notification.requestPermission().then(perm => {
                if (perm === 'granted') {
                    const n = new Notification(title, { body: text });
                    if (onclick) n.onclick = onclick;
                }
            });
        }
    };

    // ==================== GM_openInTab ====================
    window.GM_openInTab = function(url, options) {
        options = options || {};
        const openInBackground = options.active === false;
        const newTab = window.open(url, '_blank');
        if (newTab && !openInBackground) {
            newTab.focus();
        }
        return newTab;
    };

    // ==================== GM_setClipboard ====================
    window.GM_setClipboard = function(data, type) {
        type = type || 'text/plain';
        if (typeof data !== 'string') data = String(data);
        // 优先使用 Clipboard API
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(data).catch(e => {
                console.error('Clipboard API 写入失败，尝试 execCommand:', e);
                fallbackCopy(data);
            });
        } else {
            fallbackCopy(data);
        }
        function fallbackCopy(text) {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
            } catch (e) {
                console.error('execCommand 复制失败:', e);
            }
            document.body.removeChild(textarea);
        }
    };

    // ==================== GM_xmlhttpRequest ====================
    window.GM_xmlhttpRequest = function(details) {
        const xhr = new XMLHttpRequest();
        xhr.open(details.method || 'GET', details.url, true);

        // 设置请求头
        if (details.headers) {
            for (const [key, value] of Object.entries(details.headers)) {
                xhr.setRequestHeader(key, value);
            }
        }

        // 超时
        if (details.timeout) {
            xhr.timeout = details.timeout;
            xhr.ontimeout = function(e) {
                if (details.ontimeout) details.ontimeout(e);
            };
        }

        // 响应类型
        if (details.responseType) {
            xhr.responseType = details.responseType;
        }

        // 事件监听
        xhr.onload = function() {
            if (details.onload) {
                const resp = {
                    finalUrl: xhr.responseURL,
                    readyState: xhr.readyState,
                    response: xhr.response,
                    responseText: xhr.responseText,
                    responseXML: xhr.responseXML,
                    status: xhr.status,
                    statusText: xhr.statusText,
                    responseHeaders: xhr.getAllResponseHeaders()
                };
                details.onload(resp);
            }
        };

        xhr.onerror = function(e) {
            if (details.onerror) details.onerror(e);
        };

        xhr.onprogress = function(e) {
            if (details.onprogress) details.onprogress(e);
        };

        xhr.onreadystatechange = function() {
            if (details.onreadystatechange) details.onreadystatechange(xhr);
        };

        // 发送数据
        xhr.send(details.data || null);

        // 返回 abort 方法
        return {
            abort: function() { xhr.abort(); }
        };
    };

    // ==================== GM_cookie ====================
    window.GM_cookie = function(cmd, details, callback) {
        // cmd: 'list', 'get', 'set', 'delete'
        if (!callback && typeof details === 'function') {
            callback = details;
            details = {};
        }
        if (!callback) callback = function() {};

        const result = [];
        switch (cmd) {
            case 'list':
                // 返回所有可访问的 cookie
                document.cookie.split(';').forEach(pair => {
                    const [name, value] = pair.trim().split('=');
                    result.push({ name, value, domain: location.hostname, path: '/' });
                });
                setTimeout(() => callback(result), 0);
                break;
            case 'get':
                // 按名称获取 cookie
                const name = details.name;
                const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
                const value = match ? decodeURIComponent(match[2]) : null;
                setTimeout(() => callback({ name, value, domain: location.hostname, path: '/' }), 0);
                break;
            case 'set':
                // 设置 cookie
                let cookieStr = `${details.name}=${encodeURIComponent(details.value)}`;
                if (details.domain) cookieStr += `; domain=${details.domain}`;
                if (details.path) cookieStr += `; path=${details.path}`;
                if (details.expires) cookieStr += `; expires=${details.expires.toUTCString()}`;
                if (details.secure) cookieStr += '; secure';
                if (details.httpOnly) {
                    console.warn('GM_cookie: 无法通过 JS 设置 HttpOnly cookie，该标志将被忽略。');
                }
                document.cookie = cookieStr;
                setTimeout(callback, 0);
                break;
            case 'delete':
                // 删除 cookie：设置过期时间为过去
                document.cookie = `${details.name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=${details.path || '/'}`;
                setTimeout(callback, 0);
                break;
            default:
                console.error(`GM_cookie: 未知命令 "${cmd}"`);
                setTimeout(callback, 0);
        }
    };

    // ==================== 实验性/不完整 API 模拟 ====================
    // GM_webRequest - 无法在普通页面模拟网络拦截，仅打印警告
    window.GM_webRequest = function(rules, listener) {
        console.warn('GM_webRequest 在当前环境无法模拟，调用被忽略。');
        return { cancel: function() {} };
    };

    // ==================== 新增：GM 命名空间，支持 GM.* API 调用 ====================
    window.GM = {};

    // 映射存储相关
    GM.getValue = GM_getValue;
    GM.setValue = GM_setValue;
    GM.deleteValue = GM_deleteValue;
    GM.listValues = GM_listValues;
    GM.addValueChangeListener = GM_addValueChangeListener;
    GM.removeValueChangeListener = GM_removeValueChangeListener;

    // 映射资源相关
    GM.getResourceText = GM_getResourceText;
    GM.getResourceUrl = GM_getResourceURL;   // 注意大小写：标准命名为 getResourceUrl

    // 映射菜单命令
    GM.registerMenuCommand = GM_registerMenuCommand;
    GM.unregisterMenuCommand = GM_unregisterMenuCommand;
    GM.triggerMenuCommand = GM_triggerMenuCommand; // 辅助函数，非标准但保留

    // 映射标签页通信
    GM.getTab = GM_getTab;
    GM.saveTab = GM_saveTab;
    GM.getTabs = GM_getTabs;

    // 映射 DOM 操作
    GM.addStyle = GM_addStyle;
    GM.addElement = GM_addElement;

    // 映射工具
    GM.download = GM_download;
    GM.log = GM_log;
    GM.notification = GM_notification;
    GM.openInTab = GM_openInTab;
    GM.setClipboard = GM_setClipboard;
    GM.xmlHttpRequest = GM_xmlhttpRequest;   // 标准命名为 xmlHttpRequest
    GM.cookie = GM_cookie;
    GM.webRequest = GM_webRequest;           // 仅警告

    // 映射 info 对象
    GM.info = GM_info;

    // ==================== 标记兼容层已加载 ====================
    window.__GM_COMPAT_LOADED__ = true;
    console.log('GM_* 兼容层已加载，所有 API 已模拟（包含 GM.* 命名空间）。');
})();