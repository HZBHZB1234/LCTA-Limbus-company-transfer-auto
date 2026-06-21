# 设置向导

欢迎使用 LCTA 设置向导！这里将一步一步引导你完成基础配置。

无需担心遗漏任何设置 —— 你可以随时通过侧边栏的 **关于** 页面底部按钮重新进入本向导。

---

### 工作方式

本向导采用**分步引导**模式：

1. 每一页展示一个功能模块，提供简要说明
2. 勾选你感兴趣的内容，点击 **继续** 前往下一步
3. 最后会给出设置摘要和后续建议

> 💡 每个步骤都可以独立跳过，不会影响已有设置。

---

<div id="elder-first-use" style="display: none;">
    <div style="text-align: center; padding: var(--spacing-xl) 0;">
        <div style="font-size: 48px; margin-bottom: var(--spacing-md);">
            <i class="fas fa-rocket"></i>
        </div>
        <p style="font-size: 18px; margin-bottom: var(--spacing-lg);">
            看起来这是你<strong>第一次</strong>使用 LCTA<br>
            让我带你快速完成初始配置吧！
        </p>
        <button class="primary-btn" onclick="elderManager.switchPage();" style="font-size: 16px; padding: 14px 32px;">
            <i class="fas fa-play"></i>
            开始设置向导
        </button>
    </div>
</div>

<div id="elder-continue" style="display: none;">
    <div style="text-align: center; padding: var(--spacing-xl) 0;">
        <div style="font-size: 48px; margin-bottom: var(--spacing-md);">
            <i class="fas fa-sync-alt fa-spin"></i>
        </div>
        <p style="font-size: 18px; margin-bottom: var(--spacing-md);">
            <strong>检测到新设置项</strong>
        </p>
        <p style="font-size: 14px; color: var(--color-text-secondary); margin-bottom: var(--spacing-lg);">
            LCTA 更新了新的功能，需要你确认一些配置
        </p>
        <button class="primary-btn" onclick="elderManager.switchPage();" style="font-size: 16px; padding: 14px 32px;">
            <i class="fas fa-play"></i>
            查看新设置
        </button>
    </div>
</div>

<div id="elder-all-complete" style="display: none;">
    <div style="text-align: center; padding: var(--spacing-xl) 0;">
        <div style="font-size: 48px; margin-bottom: var(--spacing-md);">
            <i class="fas fa-check-circle" style="color: var(--color-success);"></i>
        </div>
        <p style="font-size: 18px; margin-bottom: var(--spacing-lg);">
            🎉 所有设置已完成！
        </p>
        <p style="font-size: 14px; color: var(--color-text-secondary);">
            你可以直接开始游戏，或在侧边栏探索更多功能
        </p>
    </div>
</div>

---

<button class="primary-btn" onclick="(async ()=> {let elderList = JSON.stringify(elderManager.updateList);
            elderManager.historyList = JSON.parse(elderList);
            for (const value of Object.keys(elderManager.historyList)) {
                elderManager.historyList[value] = 'new';
            };
            configManager.updateConfigValue('--elder', JSON.stringify(elderManager.historyList));
            await configManager.flushPendingUpdates();
            await pywebview.api.resetElder();
            await configManager.reloadConfig();
            elderManager.initPage();
            })()" style="font-size: 12px; opacity: 0.6; margin-top: var(--spacing-sm);">
    <i class="fas fa-redo-alt"></i>
    重置引导进度
</button>
<version>1145</version>

<script>
console.log('设置向导 - 首页加载');
if (first_use) {
    document.getElementById('elder-first-use').style.display = 'block';
    return
};
if (elderManager.evalNextPage()) {
    document.getElementById('elder-continue').style.display = 'block';
} else {
    document.getElementById('elder-all-complete').style.display = 'block';
}
</script>