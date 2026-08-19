// Mod 镜像站：主窗口侧接收独立窗口转发的下载请求（lcta-mod-download 事件），
// 弹出进度模态窗，经 pywebview.api.mod_mirror_request 走 aria2c 下载+自动安装。
(function () {
    if (window.__modMirrorBound) return;
    window.__modMirrorBound = true;

    window.addEventListener('lcta-mod-download', function (e) {
        const payload = e.detail && e.detail.payload;
        if (!payload || !window.pywebview || !window.pywebview.api) return;
        const isStandard = payload.kind === 'standard';
        const modal = new ProgressModal(isStandard ? '下载并安装 Mod' : '下载 Mod 文件');
        modal.addLog(isStandard ? '正在准备下载标准版包...' : '正在准备下载...');
        window.pywebview.api.mod_mirror_request(payload, modal.id).then(function (result) {
            if (result && result.success) {
                modal.complete(true, result.message || '操作完成');
            } else if (result && result.message === '已取消') {
                modal.cancel();
            } else {
                modal.complete(false, (result && result.message) || '下载失败');
            }
        }).catch(function () {
            modal.complete(false, '下载失败');
        });
    });
})();

async function openModMirror() {
    if (!window.pywebview || !window.pywebview.api) {
        if (typeof showToast === 'function') showToast('仅在 LCTA 应用内可用', 'error');
        return;
    }
    try {
        const r = await window.pywebview.api.open_mod_mirror();
        if (r && r.message && typeof showToast === 'function') {
            showToast(r.message, r.success ? 'success' : 'error');
        }
    } catch (e) {
        if (typeof showToast === 'function') showToast('打开失败：' + e, 'error');
    }
}