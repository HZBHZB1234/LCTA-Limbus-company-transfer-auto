// ============================
// 高速下载器窗口逻辑
// ============================

(function () {
    'use strict';

    function getApi() {
        return (typeof window !== 'undefined' && window.pywebview && window.pywebview.api)
            ? window.pywebview.api
            : null;
    }

    const STATUS_TEXT = {
        active: '下载中',
        waiting: '等待中',
        paused: '已暂停',
        complete: '已完成',
        error: '失败',
        removed: '已删除',
    };

    const KIND_ICON = {
        http: 'fa-link',
        magnet: 'fa-magnet',
        torrent: 'fa-file-arrow-down',
    };

    const KIND_TEXT = {
        http: '链接',
        magnet: '磁力',
        torrent: '种子',
    };

    let snapshot = null;

    function $(id) {
        return document.getElementById(id);
    }

    function formatBytes(value) {
        const bytes = Number(value) || 0;
        if (bytes <= 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
        const amount = bytes / Math.pow(1024, index);
        return `${amount >= 100 ? amount.toFixed(0) : amount.toFixed(1)} ${units[index]}`;
    }

    function formatSpeed(value) {
        const bytes = Number(value) || 0;
        if (bytes <= 0) return '0 B/s';
        return `${formatBytes(bytes)}/s`;
    }

    function showToast(message, isError) {
        const toast = $('adl-toast');
        toast.textContent = message;
        toast.className = `adl-toast show${isError ? ' error' : ''}`;
        clearTimeout(showToast._timer);
        showToast._timer = setTimeout(() => { toast.className = 'adl-toast'; }, 3500);
    }

    // ---- 状态渲染 ----

    function updateChips(state) {
        const engineChip = $('adl-engine-chip');
        const serverChip = $('adl-server-chip');
        if (!state) return;
        engineChip.className = 'adl-chip ' + (state.available ? 'ok' : 'error');
        engineChip.innerHTML = state.available
            ? '<i class="fas fa-bolt"></i> aria2c 可用'
            : '<i class="fas fa-exclamation-triangle"></i> 未找到 aria2c';
        serverChip.className = 'adl-chip ' + (state.server_running ? 'ok' : (state.available ? 'warn' : 'error'));
        serverChip.innerHTML = state.server_running
            ? '<i class="fas fa-server"></i> 下载服务运行中'
            : (state.available
                ? '<i class="fas fa-server"></i> 下载服务未启动'
                : '<i class="fas fa-server"></i> 服务不可用');
    }

    function renderTasks() {
        if (!snapshot) return;
        const list = $('adl-task-list');
        list.innerHTML = '';
        const tasks = snapshot.tasks || [];
        if (tasks.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'adl-empty';
            empty.innerHTML = '<i class="fas fa-inbox"></i> 暂无任务，粘贴链接或选择种子文件开始下载';
            list.appendChild(empty);
            return;
        }
        tasks.forEach(task => list.appendChild(buildTaskRow(task)));

        const counts = snapshot.counts || {};
        $('adl-count-active').textContent = counts.active || 0;
        $('adl-count-waiting').textContent = counts.waiting || 0;
        $('adl-count-paused').textContent = counts.paused || 0;
        $('adl-count-complete').textContent = counts.complete || 0;
        $('adl-count-error').textContent = (counts.error || 0) + (counts.removed || 0);

        const speed = snapshot.total_speed || 0;
        $('adl-total-speed').innerHTML = speed > 0
            ? `总速度 <b>${formatSpeed(speed)}</b>`
            : '';
    }

    function buildTaskRow(task) {
        const row = document.createElement('div');
        row.className = 'adl-task';

        const main = document.createElement('div');
        main.className = 'adl-task-main';

        const icon = document.createElement('div');
        icon.className = `adl-task-icon ${task.kind}`;
        icon.innerHTML = `<i class="fas ${KIND_ICON[task.kind] || 'fa-link'}"></i>`;

        const info = document.createElement('div');
        info.className = 'adl-task-info';
        const name = document.createElement('div');
        name.className = 'adl-task-name';
        name.textContent = task.name || '(未知文件名)';
        name.title = task.name || '';
        const meta = document.createElement('div');
        meta.className = 'adl-task-meta';
        meta.textContent = `[${KIND_TEXT[task.kind] || '链接'}] ${task.url || ''}`;
        meta.title = task.url || '';
        info.appendChild(name);
        info.appendChild(meta);

        const badge = document.createElement('span');
        badge.className = `adl-status-badge ${task.status}`;
        badge.textContent = STATUS_TEXT[task.status] || task.status;

        const actions = document.createElement('div');
        actions.className = 'adl-task-actions';
        if (task.status === 'active' || task.status === 'waiting') {
            actions.appendChild(makeActionButton('fa-pause', '暂停', a => a.pause_task(task.gid)));
        } else if (task.status === 'paused') {
            actions.appendChild(makeActionButton('fa-play', '继续', a => a.resume_task(task.gid)));
        }
        actions.appendChild(makeActionButton('fa-trash', '删除', a => a.remove_task(task.gid), true));

        main.appendChild(icon);
        main.appendChild(info);
        main.appendChild(badge);
        main.appendChild(actions);

        const progress = document.createElement('div');
        progress.className = 'adl-task-progress';
        const track = document.createElement('div');
        track.className = 'adl-progress-track';
        const fill = document.createElement('div');
        fill.className = 'adl-progress-fill';
        fill.style.width = `${task.pct || 0}%`;
        track.appendChild(fill);
        const pct = document.createElement('span');
        pct.className = 'adl-task-pct';
        if (task.status === 'active' || task.status === 'waiting' || task.status === 'paused') {
            pct.textContent = task.total > 0
                ? `${task.pct}%`
                : `${formatBytes(task.completed)}`;
        } else {
            pct.textContent = task.status === 'complete' ? '100%' : '-';
        }
        progress.appendChild(track);
        progress.appendChild(pct);

        row.appendChild(main);
        row.appendChild(progress);

        if (task.status === 'active' || task.status === 'paused' || task.status === 'waiting') {
            const sizeLine = document.createElement('div');
            sizeLine.className = 'adl-task-meta';
            const parts = [];
            if (task.status === 'active') parts.push(`速度 ${formatSpeed(task.speed)}`);
            parts.push(task.total > 0
                ? `${formatBytes(task.completed)} / ${formatBytes(task.total)}`
                : `已下载 ${formatBytes(task.completed)}`);
            if (task.status === 'paused') parts.push('已暂停');
            sizeLine.textContent = parts.join(' · ');
            row.appendChild(sizeLine);
        }

        if (task.status === 'error') {
            const err = document.createElement('div');
            err.className = 'adl-task-error';
            err.textContent = task.error_message || `错误码 ${task.error_code || '未知'}`;
            row.appendChild(err);
        }

        return row;
    }

    function makeActionButton(icon, text, onClick, isDanger) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `adl-btn${isDanger ? ' adl-btn-danger' : ''}`;
        btn.innerHTML = `<i class="fas ${icon}"></i> ${text}`;
        btn.addEventListener('click', async () => {
            const api = getApi();
            if (!api) {
                showToast('后端尚未就绪，请稍候重试', true);
                return;
            }
            btn.disabled = true;
            try {
                const result = await onClick(api);
                if (result && !result.success && result.message) {
                    showToast(result.message, true);
                }
            } catch (err) {
                showToast(String(err && err.message || err), true);
            } finally {
                btn.disabled = false;
            }
        });
        return btn;
    }

    // ---- 事件分发 ----

    function onDispatch(payload) {
        if (!payload || !payload.type) return;
        if (payload.type === 'snapshot') {
            snapshot = payload.payload || null;
            if (snapshot) {
                updateChips(snapshot);
                renderTasks();
            }
        } else if (payload.type === 'server') {
            if (snapshot) snapshot.server_running = !!(payload.payload && payload.payload.running);
            updateChips(snapshot);
        }
    }

    function setDirWarningVisible(visible) {
        const warning = $('adl-dir-warning');
        if (warning) warning.style.display = visible ? '' : 'none';
    }

    // ---- 初始化 ----

    async function init() {
        const api = getApi();
        if (!api) return;
        const state = await api.get_state();
        if (!state || !state.success) {
            showToast((state && state.message) || '初始化失败', true);
            return;
        }
        const cfg = state.config || {};
        $('adl-save-dir').value = cfg.save_dir || '';
        $('adl-jobs').value = cfg.jobs || 8;
        $('adl-connection-limit').value = cfg.connection_limit || 16;
        $('adl-seed-time').value = cfg.seed_time || 0;
        setDirWarningVisible(cfg.save_dir_exists === false);
        updateChips(state);
        if (state.available && !state.server_running) {
            const started = await api.start_server();
            if (started && !started.success && started.message) {
                showToast(started.message, true);
            }
        }
    }

    function bindEvents() {
        $('adl-browse-dir').addEventListener('click', async () => {
            const api = getApi();
            if (!api) { showToast('后端尚未就绪，请稍候重试', true); return; }
            const result = await api.browse_folder();
            if (result && result.success) {
                $('adl-save-dir').value = result.path;
                setDirWarningVisible(false);
            }
        });

        $('adl-add-urls').addEventListener('click', async () => {
            const api = getApi();
            if (!api) { showToast('后端尚未就绪，请稍候重试', true); return; }
            const textarea = $('adl-urls');
            const urls = (textarea.value || '')
                .split('\n')
                .map(line => line.trim())
                .filter(Boolean);
            const saveDir = $('adl-save-dir').value.trim();
            if (!saveDir) {
                showToast('请先选择保存目录', true);
                return;
            }
            if (urls.length === 0) {
                showToast('请先输入下载链接', true);
                return;
            }
            const result = await api.add_urls({ urls, save_dir: saveDir });
            if (result && result.success) {
                const addedCount = (result.added || []).length;
                const errorCount = (result.errors || []).length;
                if (addedCount > 0) {
                    textarea.value = '';
                    showToast(`已添加 ${addedCount} 个任务` + (errorCount ? `，${errorCount} 个失败` : ''));
                } else {
                    showToast('全部链接添加失败', true);
                }
                (result.errors || []).forEach(item => {
                    if (item && item.error) console.warn('添加失败:', item.url, item.error);
                });
            } else {
                showToast((result && result.message) || '添加失败', true);
            }
        });

        $('adl-add-torrent').addEventListener('click', async () => {
            const api = getApi();
            if (!api) { showToast('后端尚未就绪，请稍候重试', true); return; }
            const saveDir = $('adl-save-dir').value.trim();
            if (!saveDir) {
                showToast('请先选择保存目录', true);
                return;
            }
            const picked = await api.browse_torrent();
            if (!picked || !picked.success) return;
            const result = await api.add_torrent({ path: picked.path, save_dir: saveDir });
            if (result && result.success) {
                showToast(result.message || '已提交种子任务');
            } else {
                showToast((result && result.message) || '添加种子失败', true);
            }
        });

        $('adl-save-config').addEventListener('click', async () => {
            const api = getApi();
            if (!api) { showToast('后端尚未就绪，请稍候重试', true); return; }
            const payload = {
                save_dir: $('adl-save-dir').value.trim(),
                jobs: Number($('adl-jobs').value) || 8,
                connection_limit: Number($('adl-connection-limit').value) || 16,
                seed_time: Number($('adl-seed-time').value) || 0,
            };
            const result = await api.save_window_config(payload);
            showToast(result && result.success ? '设置已保存' : ((result && result.message) || '保存失败'), !(result && result.success));
        });

        $('adl-pause-all').addEventListener('click', async () => {
            const api = getApi();
            if (!api) { showToast('后端尚未就绪，请稍候重试', true); return; }
            const result = await api.pause_all();
            if (result && !result.success && result.message) showToast(result.message, true);
        });

        $('adl-resume-all').addEventListener('click', async () => {
            const api = getApi();
            if (!api) { showToast('后端尚未就绪，请稍候重试', true); return; }
            const result = await api.resume_all();
            if (result && !result.success && result.message) showToast(result.message, true);
        });

        $('adl-purge').addEventListener('click', async () => {
            const api = getApi();
            if (!api) { showToast('后端尚未就绪，请稍候重试', true); return; }
            const result = await api.purge_completed();
            if (result && !result.success && result.message) showToast(result.message, true);
        });
    }

    function bootstrap() {
        window.__aria2DlDispatch = onDispatch;
        bindEvents();
        // pywebview API 可能尚未注入（DOMContentLoaded 早于 pywebviewready），
        // 按 llm-fancy 同款模式：先查一次，未就绪则等 pywebviewready 事件
        if (getApi()) {
            init();
            return;
        }
        let ready = false;
        function handleReady() {
            if (ready) return;
            ready = true;
            init();
        }
        window.addEventListener('pywebviewready', handleReady);
        // 兜底：事件注册前 API 已就绪（事件可能已错过）
        if (window.pywebview && window.pywebview.api) handleReady();
        // 兜底：10 秒仍未就绪，提示重开窗口
        setTimeout(() => {
            if (ready || getApi()) return;
            showToast('无法连接后端 API，请关闭窗口后重新打开', true);
        }, 10000);
    }

    document.addEventListener('DOMContentLoaded', bootstrap);
})();

function applyTheme(theme) {
    document.body.className = `theme-${theme || 'light'}`;
}

window.applyTheme = applyTheme;
