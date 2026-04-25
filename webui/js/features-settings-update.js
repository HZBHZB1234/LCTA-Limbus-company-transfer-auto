window.__updateModalShown = window.__updateModalShown || false;

function manualCheckUpdates() {
    const modal = new ProgressModal('检查更新');
    modal.addLog('正在检查是否有可用更新...');

    callApi('manual_check_update')
        .then(function(result) {
            if (result.has_update) {
                modal.complete(true, `发现新版本 ${result.latest_version}，请前往GitHub下载更新`);
                setTimeout(() => {
                    if (!modal.isMinimized) {
                        modal.close();
                        showUpdateInfo(result);
                    }
                }, 2000);
                return;
            }
            modal.complete(true, '当前已是最新版本');
            setTimeout(() => {
                if (!modal.isMinimized) {
                    modal.close();
                }
            }, 2000);
        })
        .catch(function(error) {
            modal.complete(false, '检查更新时发生错误: ' + error);
            setTimeout(() => {
                if (!modal.isMinimized) {
                    modal.close();
                }
            }, 3000);
        });
}

function autoCheckUpdates() {
    callApi('manual_check_update')
        .then(function(result) {
            if (result.has_update) {
                showUpdateInfo(result);
            }
        })
        .catch(function(error) {
            addLogMessage('自动检查更新时发生错误: ' + error, 'error');
        });
}

function doUpdate() {
    this.close();
    const progressModal = new ProgressModal('更新程序');
    progressModal.addLog('开始下载并安装更新...');
    callApi('perform_update_in_modal', progressModal.id)
        .then(function(result) {
            if (!result) {
                progressModal.addLog('更新失败');
                progressModal.complete(false, '更新失败');
                return;
            }
            progressModal.addLog('更新完成');
            progressModal.addLog('正在重新启动程序...');
            progressModal.complete(true, '更新完成');
        })
        .catch(function(error) {
            progressModal.addLog('更新失败: ' + error);
            progressModal.complete(false, '更新失败');
        });
}

async function showUpdateInfo(updateInfo) {
    if (window.__updateModalShown) {
        return;
    }

    window.__updateModalShown = true;

    let htmlMessage = `<p><strong>发现新版本:</strong> ${updateInfo.latest_version}</p>`;
    htmlMessage += `<p><strong>当前版本:</strong> v5.0.0</p>`;

    if (updateInfo.title) {
        htmlMessage += `<p><strong>发布标题:</strong> ${updateInfo.title}</p>`;
    }

    if (updateInfo.body) {
        const body = updateInfo.body.trim();
        const bodyHtml = simpleMarkdownToHtml(body);
        htmlMessage += `<div><strong>更新详情:</strong></div>`;
        htmlMessage += `<div class="markdown-body" id="update-markdown">${bodyHtml}</div>`;
    }

    if (updateInfo.published_at) {
        const publishDate = new Date(updateInfo.published_at);
        htmlMessage += `<p><strong>发布时间:</strong> ${publishDate.toLocaleDateString('zh-CN')}</p>`;
    }

    if (updateInfo.html_url) {
        htmlMessage += `<p><strong>发布页面:</strong> <a href="${updateInfo.html_url}" target="_blank" style="color: var(--color-primary); text-decoration: underline;">点击这里在浏览器中查看</a></p>`;
    }

    const modal = showConfirm(
        '发现新版本',
        '',
        doUpdate,
        function() {
            addLogMessage('用户取消了更新');
            window.__updateModalShown = false;
        }
    );

    const originalClose = modal.close;
    modal.close = function() {
        window.__updateModalShown = false;
        originalClose.call(this);
    };

    setTimeout(async function() {
        const statusElement = document.getElementById(`modal-status-${modal.id}`);
        if (statusElement) {
            statusElement.innerHTML = htmlMessage;
        }
        let isFrozen = await callApi('get_attr', 'is_frozen');
        if (!isFrozen) {
            isFrozen = isFrozen && (await callApi('get_attr', 'debug') === 'true');
        }
        if (isFrozen) {
            const confirmButton = document.getElementById(`confirm-btn-${modal.id}`);
            confirmButton.removeEventListener('click', doUpdate);
            confirmButton.addEventListener('click', () => {
                showMessage('当前版本不兼容自动下载');
                modal.close();
            });
        }
    }, 100);
}

window.manualCheckUpdates = manualCheckUpdates;
window.autoCheckUpdates = autoCheckUpdates;
window.doUpdate = doUpdate;
window.showUpdateInfo = showUpdateInfo;
