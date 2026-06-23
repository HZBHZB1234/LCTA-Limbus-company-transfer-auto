# 设置向导

欢迎使用 LCTA 设置向导！本向导将分步引导你完成从游戏路径到高级功能的全套初始配置。

无需担心遗漏任何设置 —— 你可以随时通过侧边栏的 **设置向导** 重新进入，也可以使用底部的重置按钮重新开始。

---

<div data-version="1145">

<div class="elder-hero" data-state="first-use" style="display:none">
    <span class="elder-hero-icon"><i class="fas fa-rocket"></i></span>
    <h2 class="elder-hero-title">看起来这是你第一次使用 LCTA</h2>
    <p class="elder-hero-subtitle">让我带你快速完成初始配置，只需几分钟即可上手！</p>
    <button class="primary-btn" onclick="elderManager.switchPage()">
        <i class="fas fa-play"></i> 开始设置向导
    </button>
</div>

<div class="elder-hero" data-state="continue" style="display:none">
    <span class="elder-hero-icon"><i class="fas fa-sync-alt"></i></span>
    <h2 class="elder-hero-title">检测到新设置项</h2>
    <p class="elder-hero-subtitle">LCTA 更新了新的功能，需要你确认和调整一些配置。点击下方按钮查看。</p>
    <button class="primary-btn" onclick="elderManager.switchPage()">
        <i class="fas fa-arrow-right"></i> 查看新设置
    </button>
</div>

<div class="elder-hero" data-state="all-complete" style="display:none">
    <span class="elder-hero-icon"><i class="fas fa-check-circle"></i></span>
    <h2 class="elder-hero-title">全部设置已完成！</h2>
    <p class="elder-hero-subtitle">所有配置项均已是最新状态。你可以直接使用 LCTA，或在侧边栏探索更多功能。</p>
</div>

</div>

---

<button class="primary-btn elder-btn-reset" onclick="elderManager.resetElder()">
    <i class="fas fa-redo-alt"></i> 重置引导进度
</button>
