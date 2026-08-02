# 选择你感兴趣的功能

LCTA 是一个综合性工具箱，涵盖启动器、翻译、MOD 管理等多种功能。请勾选你想了解并配置的内容，可多选。我会根据你的选择，引导你完成对应模块的设置。

<div class="elder-feature-grid" data-version="415">

<div class="elder-feature-card">
    <div class="elder-feature-icon"><i class="fas fa-info-circle"></i></div>
    <div class="elder-feature-body">
        <h4>基础介绍</h4>
        <p>了解 LCTA 的基本功能、更新机制以及遇到问题时如何获取帮助。非常简短。</p>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-character-base" checked>
            <span class="checkmark"></span> 我想先大致了解一下 LCTA
        </label>
    </div>
</div>

<div class="elder-feature-card">
    <div class="elder-feature-icon"><i class="fas fa-rocket"></i></div>
    <div class="elder-feature-body">
        <h4>启动器模式</h4>
        <p>每次启动游戏时自动检查并更新汉化包，支持 MOD 加载和文本美化。一劳永逸。</p>
        <details>
            <summary>与 Faust Launcher 对比</summary>
            <ul>
                <li><strong>更多汉化包来源</strong>：支持 LLC、OurPlay、<a onclick="showMarkdownModal('assets/LCTA-AU.md', '什么是LCTA-AU');">LCTA-AU</a> 等</li>
                <li><strong>按需复制</strong>：仅在有更新时才复制文件，无需每次全量复制</li>
                <li><strong>来源直连</strong>：直接从所选汉化来源获取更新，无需等待第三方中转</li>
            </ul>
        </details>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-character-launcher" checked>
            <span class="checkmark"></span> 我希望使用 LCTA 作为启动器
        </label>
    </div>
</div>

<div class="elder-feature-card">
    <div class="elder-feature-icon"><i class="fas fa-language"></i></div>
    <div class="elder-feature-body">
        <h4>手动翻译</h4>
        <p>配置翻译 API 后手动翻译游戏文本。适合对翻译质量和时效性有较高要求的用户。</p>
        <p class="elder-setting-hint">推荐使用 DeepSeek 进行翻译，按实际用量计费，费用不高。</p>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-character-translate" checked>
            <span class="checkmark"></span> 我希望使用 LCTA 进行翻译
        </label>
    </div>
</div>

<div class="elder-feature-card">
    <div class="elder-feature-icon"><i class="fas fa-archive"></i></div>
    <div class="elder-feature-body">
        <h4>数据管理</h4>
        <p>汉化包管理、MOD 管理、缓存与存储设置。所有管理功能都可以在侧边栏方便地访问。</p>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-character-manage" checked>
            <span class="checkmark"></span> 我希望使用 LCTA 进行管理
        </label>
    </div>
</div>

</div>

<button class="primary-btn" onclick="elderManager.switchPage()">
    <i class="fas fa-arrow-right"></i> 继续
</button>
