/* 编辑器内 CM6 搜索面板共享模块 — rule-editor 与 quick-editor 共用
 * 提供：搜索面板中文翻译、自由拖拽（指针捕获 + rAF + 边界钳制）、
 *      以及桥接对象 bridge 的状态同步（isOpen / panelLeft / panelTop / panelRight / onPanelClose）
 * 用法：EditorSearchPanel.attach(container, bridge) — container 为编辑器容器，观察其中出现的 .cm-search 面板
 */
(function () {
    'use strict';

    // ──── 中文翻译 ────
    function localizeSearchPanel(searchEl, bridge) {
        if (searchEl._localized) return;
        searchEl._localized = true;

        // 监听关闭按钮，同步 bridge 状态（必须在 CM6 移除面板前更新）
        var closeBtn = searchEl.querySelector('button[name="close"]');
        if (closeBtn && !closeBtn._closePatched) {
            closeBtn._closePatched = true;
            closeBtn.addEventListener('mousedown', function () {
                if (!bridge) return;
                bridge.isOpen = false;
                // 清除拖拽位置 — 下次 Ctrl+F 恢复默认位置
                bridge.panelLeft = null;
                bridge.panelTop = null;
                bridge.panelRight = null;
                if (bridge.onPanelClose) bridge.onPanelClose();
            });
        }

        // 翻译字典：英文 → 中文
        const T = {
            "Find": "查找", "Replace": "替换",
            "next": "下一个", "previous": "上一个", "all": "全部",
            "match case": "区分大小写", "regexp": "正则", "by word": "全词匹配",
            "replace": "替换", "replace all": "全部替换", "close": "关闭"
        };

        // 翻译 placeholder
        const inputs = searchEl.querySelectorAll('input[type="text"]');
        for (let i = 0; i < inputs.length; i++) {
            const ph = inputs[i].placeholder;
            if (ph && T[ph]) inputs[i].placeholder = T[ph];
        }

        // 翻译 button title / textContent（大小写不敏感）
        const buttons = searchEl.querySelectorAll('button');
        for (let i = 0; i < buttons.length; i++) {
            const btn = buttons[i];
            const title = btn.getAttribute('title');
            if (title) {
                const lower = title.toLowerCase();
                if (T[title]) { btn.setAttribute('title', T[title]); }
                else if (T[lower]) { btn.setAttribute('title', T[lower]); }
            }
            const name = btn.getAttribute('name');
            if (name && T[name]) btn.setAttribute('title', T[name]);
            // 替换按钮文字（如 "replace all" → "全部替换"）
            const trimmed = btn.textContent && btn.textContent.trim();
            if (trimmed && T[trimmed]) {
                btn.textContent = T[trimmed];
            }
        }

        // 翻译 checkbox label 文字
        const labels = searchEl.querySelectorAll('label');
        for (let i = 0; i < labels.length; i++) {
            const lbl = labels[i];
            const title = lbl.getAttribute('title');
            if (title && T[title]) lbl.setAttribute('title', T[title]);
            // 替换 label 内的文本节点（如 "match case" → "区分大小写"）
            for (let k = 0; k < lbl.childNodes.length; k++) {
                const cn = lbl.childNodes[k];
                if (cn.nodeType === 3 && T[cn.textContent.trim()]) { // TEXT_NODE
                    cn.textContent = T[cn.textContent.trim()];
                }
            }
        }
    }

    // ──── 位置钳制（面板不超出编辑器容器边界） ────
    function setSearchPanelPosition(panels, left, top) {
        if (!panels) return;
        var bounds = panels.offsetParent;
        if (!bounds) return;
        var boundsRect = bounds.getBoundingClientRect();
        var panelRect = panels.getBoundingClientRect();
        var margin = 8;
        var maxLeft = Math.max(margin, boundsRect.width - panelRect.width - margin);
        var maxTop = Math.max(margin, boundsRect.height - panelRect.height - margin);
        var clampedLeft = Math.max(margin, Math.min(left, maxLeft));
        var clampedTop = Math.max(margin, Math.min(top, maxTop));
        panels.style.left = clampedLeft + 'px';
        panels.style.top = clampedTop + 'px';
        panels.style.right = 'auto';
        panels.style.bottom = 'auto';
    }

    // ──── 面板拖拽 ────
    function attachDrag(searchEl, bridge) {
        if (searchEl._dragBound) return;
        searchEl._dragBound = true;

        searchEl.addEventListener('pointerdown', function (e) {
            // 仅在点击背景区域时启动拖动（排除交互控件）
            const target = e.target;
            if (e.button !== 0) return;
            if (target.tagName === 'INPUT' || target.tagName === 'BUTTON' ||
                target.tagName === 'LABEL' || target.closest('button') ||
                target.closest('label')) return;

            const panels = searchEl.parentElement; // .cm-panels
            const bounds = panels ? panels.offsetParent : null;
            if (!panels || !bounds) return;

            const rect = panels.getBoundingClientRect();
            const boundsRect = bounds.getBoundingClientRect();
            const startX = e.clientX;
            const startY = e.clientY;
            const startLeft = rect.left - boundsRect.left;
            const startTop = rect.top - boundsRect.top;
            var moved = false;
            var frameId = null;
            var pendingX = startX;
            var pendingY = startY;
            const DEAD_ZONE = 3;   // 3px 死区，区分点击与拖拽

            searchEl.setPointerCapture(e.pointerId);

            function onMove(ev) {
                if (ev.pointerId !== e.pointerId) return;
                var dx = ev.clientX - startX;
                var dy = ev.clientY - startY;
                // 死区：移动 < 3px 不启动拖拽
                if (!moved && Math.abs(dx) < DEAD_ZONE && Math.abs(dy) < DEAD_ZONE) return;
                if (!moved) {
                    moved = true;
                    panels.style.willChange = 'transform';
                    searchEl.classList.add('dragging');
                    searchEl.style.userSelect = 'none';
                }
                pendingX = ev.clientX;
                pendingY = ev.clientY;
                if (frameId) return;
                frameId = requestAnimationFrame(function () {
                    frameId = null;
                    panels.style.transform = 'translate3d(' +
                        (pendingX - startX) + 'px,' + (pendingY - startY) + 'px,0)';
                });
            }

            function onUp(ev) {
                if (ev.pointerId !== e.pointerId) return;
                if (frameId) {
                    cancelAnimationFrame(frameId);
                    frameId = null;
                }
                panels.style.transform = '';
                panels.style.willChange = '';
                searchEl.classList.remove('dragging');
                searchEl.style.userSelect = '';
                if (searchEl.hasPointerCapture(e.pointerId)) {
                    searchEl.releasePointerCapture(e.pointerId);
                }
                searchEl.removeEventListener('pointermove', onMove);
                searchEl.removeEventListener('pointerup', onUp);
                searchEl.removeEventListener('pointercancel', onUp);

                if (moved) {
                    setSearchPanelPosition(
                        panels,
                        startLeft + (pendingX - startX),
                        startTop + (pendingY - startY)
                    );
                    if (bridge) {
                        bridge.panelLeft = panels.style.left;
                        bridge.panelTop = panels.style.top || '';
                        bridge.panelRight = panels.style.right || 'auto';
                    }
                }
            }

            searchEl.addEventListener('pointermove', onMove);
            searchEl.addEventListener('pointerup', onUp);
            searchEl.addEventListener('pointercancel', onUp);
        });
    }

    // ──── 容器观察器：捕获动态出现的 .cm-search 面板并初始化 ────
    function attach(container, bridge) {
        if (!container) return;

        if (container._searchObserver) {
            container._searchObserver.disconnect();
        }

        const observer = new MutationObserver(function (mutations) {
            for (let i = 0; i < mutations.length; i++) {
                const m = mutations[i];
                if (!m.addedNodes || !m.addedNodes.length) continue;
                for (let j = 0; j < m.addedNodes.length; j++) {
                    const node = m.addedNodes[j];
                    if (node.nodeType !== 1) continue;
                    const search = node.classList && node.classList.contains('cm-search')
                        ? node : (node.querySelector && node.querySelector('.cm-search'));
                    if (search) {
                        localizeSearchPanel(search, bridge);
                        attachDrag(search, bridge);
                    }
                }
            }
        });
        observer.observe(container, { childList: true, subtree: true });
        container._searchObserver = observer;
    }

    window.EditorSearchPanel = {
        attach: attach,
        localizeSearchPanel: localizeSearchPanel,
        setSearchPanelPosition: setSearchPanelPosition,
        attachDrag: attachDrag,
    };
})();
