# 启动器配置

使用 LCTA 作为启动器，游戏会在每次启动时自动检测汉化包更新，无需手动下载安装。同时支持 MOD 加载、更新汉化包后自动更新气泡文本模组，以及文本美化功能。

<div data-version="415">

<div class="elder-info-card">
    <h4><i class="fas fa-cog"></i> 更新源选择</h4>
    <p>选择启动器自动更新汉化包时使用的来源。不同的来源适用于不同的使用场景。</p>
    <select id="elder-launcher-update" class="elder-select">
        <option value="LM-G">LM-G — 综合推荐（默认）</option>
        <option value="llc">LLC（零协）— 社区汉化</option>
        <option value="ourplay">OurPlay — 官方合作汉化</option>
        <option value="LCTA-AU">LCTA-AU — 作者自维护的机翻版本</option>
        <option value="LM-A">LM-A — 更新llc+LCTA-AU（API Beta）</option>
        <option value="LO">LO — 更新llc+ourplay</option>
        <option value="no">不自动更新</option>
    </select>
    <p class="elder-setting-hint">推荐使用 <strong>LM-G</strong>。LCTA-AU 由作者维护，更新速度约 1-3 小时。</p>
</div>

<div class="elder-info-card">
    <h4><i class="fas fa-tachometer-alt"></i> CDN 优选</h4>
    <div class="elder-setting-row">
        <label for="elder-launcher-cdn-optimize">启用 CDN 优选</label>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-launcher-cdn-optimize">
            <span class="checkmark"></span>
        </label>
    </div>
    <p class="elder-setting-hint">启动游戏前自动测试 Cloudflare 和 CloudFront 节点速度。</p>
    <div class="elder-setting-row" style="margin-top:8px;">
        <label for="elder-launcher-cdn-auto-apply">CDN 优选自动写入 hosts</label>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-launcher-cdn-auto-apply">
            <span class="checkmark"></span>
        </label>
    </div>
    <p class="elder-setting-hint">需要管理员权限，权限不足时尝试 UAC 提权。</p>
    <div class="elder-setting-row" style="margin-top:8px;">
        <label for="elder-launcher-cdn-ttl">CDN 优选缓存有效期（小时）</label>
        <input type="number" id="elder-launcher-cdn-ttl" value="24" min="0" max="720" step="0.5">
    </div>
    <p class="elder-setting-hint">设为 0 表示每次启动重新测速，推荐 24-72。</p>
</div>

<div class="elder-option-card">
    <div class="elder-option-icon"><i class="fas fa-puzzle-piece"></i></div>
    <div class="elder-option-body">
        <h4>MOD 支持</h4>
        <p>通过替换资源加载自定义皮肤模组和音效模组。兼容 Lunartique 格式。</p>
        <img src="assets/images/launcher-mod-preview.png" alt="MOD效果展示" style="max-width:100%;border-radius:8px;margin:8px 0;">
        <p class="elder-setting-hint">来源：<a href="https://www.nexusmods.com/limbuscompany/mods/102">Nexus Mods</a></p>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-launcher-mod">
            <span class="checkmark"></span> 启用 MOD 支持
        </label>
    </div>
</div>

<div class="elder-option-card">
    <div class="elder-option-icon"><i class="fas fa-comment-dots"></i></div>
    <div class="elder-option-body">
        <h4>气泡文本自动更新</h4>
        <p>每次汉化包更新成功后自动安装气泡文本模组，让人格对话气泡显示彩色文本，并支持随机加载文本。</p>
        <img src="assets/images/launcher-bubble-preview.png" alt="气泡文本效果" style="max-width:100%;border-radius:8px;margin:8px 0;">
        <p class="elder-setting-hint"><a href="https://www.bilibili.com/video/BV1GVpszcEi9">B站视频介绍</a></p>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-launcher-bubble">
            <span class="checkmark"></span> 启用气泡文本自动更新
        </label>
    </div>
</div>

<div class="elder-option-card">
    <div class="elder-option-icon"><i class="fas fa-magic"></i></div>
    <div class="elder-option-body">
        <h4>文本美化</h4>
        <p>自动美化技能名称、技能描述和气泡文本，让文字更有质感。</p>
        <img src="assets/images/launcher-fancy-preview.png" alt="文本美化效果" style="max-width:100%;border-radius:8px;margin:8px 0;">
        <p class="elder-setting-hint">包含技能名称美化、描述美化、气泡文本美化等。</p>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-launcher-fancy">
            <span class="checkmark"></span> 启用文本美化
        </label>
    </div>
</div>

</div>

<p class="elder-setting-hint">更多选项（如图形化进度窗口等）可在主界面「Launcher配置」页调整。</p>

<button class="primary-btn" onclick="elderManager.switchPage()">
    <i class="fas fa-arrow-right"></i> 继续
</button>
