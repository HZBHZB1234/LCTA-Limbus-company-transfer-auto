# 设置完成！

<div style="text-align: center; padding: var(--spacing-md) 0;">
    <div style="font-size: 48px; margin-bottom: var(--spacing-sm);">
        🎉
    </div>
    <p style="font-size: 16px; color: var(--color-text-secondary);">
        你已经完成了 LCTA 的初始配置
    </p>
</div>

---

## 你的选择

<div id="elder-summary" style="background: var(--color-bg-secondary); border-radius: 8px; padding: var(--spacing-md); margin: var(--spacing-md) 0;">
    <p><em>基本介绍已阅读</em></p>
</div>

<script>
(function() {
    const summary = document.getElementById('elder-summary');
    const items = [];
    if (configManager.getCachedValue('elder.character.launcher')) {
        items.push('<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid var(--color-border);">\
            <i class="fas fa-rocket" style="color:var(--color-primary);margin-top:2px;"></i>\
            <div><strong>启动器模式</strong><br><span style="font-size:13px;color:var(--color-text-secondary);">已启用。每次启动游戏时将自动检查和更新汉化包。</span></div>\
        </div>');
    }
    if (configManager.getCachedValue('elder.character.translate')) {
        items.push('<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid var(--color-border);">\
            <i class="fas fa-language" style="color:var(--color-primary);margin-top:2px;"></i>\
            <div><strong>手动翻译</strong><br><span style="font-size:13px;color:var(--color-text-secondary);">已选择。请前往 <a onclick="goAndShow(\'config\')" style="cursor:pointer;color:var(--color-primary);text-decoration:underline;">配置汉化API</a> 页面设置翻译服务。</span></div>\
        </div>');
    }
    if (configManager.getCachedValue('elder.character.manage')) {
        items.push('<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px solid var(--color-border);">\
            <i class="fas fa-archive" style="color:var(--color-primary);margin-top:2px;"></i>\
            <div><strong>数据管理</strong><br><span style="font-size:13px;color:var(--color-text-secondary);">已选择。可在侧边栏「已安装数据管理」进行汉化包和模组管理。</span></div>\
        </div>');
    }
    if (items.length === 0) {
        items.push('<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;">\
            <i class="fas fa-smile" style="color:var(--color-primary);margin-top:2px;"></i>\
            <div><strong>基础介绍已完成</strong><br><span style="font-size:13px;color:var(--color-text-secondary);">你可以随时在侧边栏探索更多功能。</span></div>\
        </div>');
    }
    summary.innerHTML = items.join('');
})();
</script>

## 下一步

<div style="display: flex; flex-direction: column; gap: 8px; margin: var(--spacing-md) 0;">

<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--color-bg-secondary);border-radius:6px;">
    <i class="fas fa-1" style="color:var(--color-primary);"></i>
    <span>如果配置了<strong>启动器</strong>，请将 Steam 启动命令粘贴到游戏属性中</span>
</div>

<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--color-bg-secondary);border-radius:6px;">
    <i class="fas fa-2" style="color:var(--color-primary);"></i>
    <span>如果选择了<strong>翻译</strong>，请先在「配置汉化API」页面设置翻译服务</span>
</div>

<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--color-bg-secondary);border-radius:6px;">
    <i class="fas fa-3" style="color:var(--color-primary);"></i>
    <span>每个页面有 <strong>?</strong> 帮助按钮，长按 <kbd>W</kbd> 键也可以打开帮助</span>
</div>

<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--color-bg-secondary);border-radius:6px;">
    <i class="fas fa-4" style="color:var(--color-primary);"></i>
    <span>遇到问题？欢迎加入 <strong>QQ 群：1081988645</strong> 或提交 <a href="https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto/issues" style="color:var(--color-primary);">GitHub Issue</a></span>
</div>

</div>

---

<div style="text-align: center; padding: var(--spacing-md) 0;">
    <button class="primary-btn" onclick="goAndShow('translate');" style="font-size: 16px; padding: 14px 36px;">
        <i class="fas fa-rocket"></i>
        开始使用 LCTA
    </button>
</div>