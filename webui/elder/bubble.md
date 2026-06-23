# 气泡文本

气泡文本让每个人格在游戏中说话时显示专属的对话文本，极大提升游戏沉浸感。基于官方文本接口实现。

<div data-version="415">

<div class="elder-hero" style="padding:var(--spacing-md) 0;">
    <span style="font-size:40px;">💬</span>
    <p style="font-size:14px;color:var(--color-text-secondary);margin-top:8px;">
        详细了解：<a href="https://www.bilibili.com/video/BV1GVpszcEi9">B站视频介绍</a>
    </p>
</div>

<div class="elder-option-card">
    <div class="elder-option-icon"><i class="fas fa-paint-brush"></i></div>
    <div class="elder-option-body">
        <h4>下载有颜色的气泡文本</h4>
        <p>下载带有颜色标记的气泡文本版本，视觉更丰富。效果见 <a href="https://www.bilibili.com/video/BV16T1uBBETa">视频演示</a>。</p>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-bubble-color">
            <span class="checkmark"></span> 下载有颜色的气泡文本
        </label>
    </div>
</div>

<div class="elder-option-card">
    <div class="elder-option-icon"><i class="fas fa-random"></i></div>
    <div class="elder-option-body">
        <h4>下载随机加载文本</h4>
        <p>下载包含随机加载文本的气泡版本。在战斗加载页面显示有趣的随机内容，增添乐趣。</p>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-bubble-llc">
            <span class="checkmark"></span> 下载随机加载文本
        </label>
    </div>
</div>

<div class="elder-option-card">
    <div class="elder-option-icon"><i class="fas fa-download"></i></div>
    <div class="elder-option-body">
        <h4>下载后自动安装</h4>
        <p>勾选后，气泡文本下载完成时自动安装到当前已启用的汉化包中，无需手动操作。</p>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-bubble-install" checked>
            <span class="checkmark"></span> 下载后自动安装
        </label>
    </div>
</div>

<div class="elder-warning-card">
    <h4><i class="fas fa-exclamation-triangle"></i> 重要提示</h4>
    <p>气泡文本是直接安装在汉化包上的。<strong>每次切换或更新汉化包后都需要重新安装气泡文本。</strong>如果你在启动器中启用了「气泡文本自动更新」，启动器会在每次更新后自动安装，无需担心。</p>
</div>

</div>

<button class="primary-btn" onclick="elderManager.switchPage()">
    <i class="fas fa-arrow-right"></i> 继续
</button>
