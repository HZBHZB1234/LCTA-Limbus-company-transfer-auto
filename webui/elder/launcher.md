# 启动器配置

使用 LCTA 作为启动器，游戏会在每次启动时自动检测汉化包更新，无需手动下载安装。同时支持 MOD 加载、气泡文本自动更新和文本美化功能。

<div data-version="415">

<div class="elder-info-card">
    <h4><i class="fas fa-cog"></i> 更新源选择</h4>
    <p>选择启动器自动更新汉化包时使用的来源。不同的来源适用于不同的使用场景。</p>
    <select id="elder-launcher-update" class="elder-select">
        <option value="LM-G">LM-G — 综合推荐（默认）</option>
        <option value="llc">LLC（零协）— 社区汉化</option>
        <option value="ourplay">OurPlay — 官方合作汉化</option>
        <option value="LCTA-AU">LCTA-AU — 作者自维护的机翻版本</option>
        <option value="LM-A">LM-A — 备选方案</option>
        <option value="LO">LO — 备选方案</option>
        <option value="no">不自动更新</option>
    </select>
    <p class="elder-setting-hint">推荐使用 <strong>LM-G</strong>。LCTA-AU 由作者维护，更新速度约 1-3 小时。</p>
</div>

<div class="elder-option-card">
    <div class="elder-option-icon"><i class="fas fa-puzzle-piece"></i></div>
    <div class="elder-option-body">
        <h4>MOD 支持</h4>
        <p>通过替换资源加载自定义皮肤模组和音效模组。兼容 Faust Launcher 格式。</p>
        <img src="https://free.picui.cn/free/2026/03/28/69c772feedff9.webp" alt="MOD效果展示" style="max-width:100%;border-radius:8px;margin:8px 0;">
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
        <p>启动游戏时自动更新气泡文本，让每个人格说话时都显示专属台词。</p>
        <img src="https://free.picui.cn/free/2026/03/28/69c775a568da2.png" alt="气泡文本效果" style="max-width:100%;border-radius:8px;margin:8px 0;">
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
        <img src="https://free.picui.cn/free/2026/03/28/69c776ed91fe9.png" alt="文本美化效果" style="max-width:100%;border-radius:8px;margin:8px 0;">
        <p class="elder-setting-hint">包含技能名称美化、描述美化、气泡文本美化等。</p>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-launcher-fancy">
            <span class="checkmark"></span> 启用文本美化
        </label>
    </div>
</div>

</div>

<button class="primary-btn" onclick="elderManager.switchPage()">
    <i class="fas fa-arrow-right"></i> 继续
</button>
