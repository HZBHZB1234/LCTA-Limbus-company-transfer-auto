# 基础设置

一些最常用的基本配置项，帮助你获得更好的使用体验。

<div data-version="415">

<div class="elder-info-card">
    <h4><i class="fas fa-sync-alt"></i> 自动更新</h4>
    <p>启用后，LCTA 会在每次启动时自动检查是否有新版本。如有更新，点击确认即可自动下载安装，无需手动操作。</p>
    <img src="https://free.picui.cn/free/2026/03/28/69c772ff8417f.png" alt="更新提示" style="max-width:500px;border-radius:8px;margin:8px 0;">
    <label class="checkbox-container">
        <input type="checkbox" id="elder-auto-update" checked>
        <span class="checkmark"></span> 启动时自动检查更新
    </label>
</div>

<div class="elder-info-card">
    <h4><i class="fas fa-palette"></i> 界面主题</h4>
    <p>选择你喜欢的配色方案，随时可以在设置中更改。</p>
    <div class="elder-theme-switch">
        <button type="button" class="elder-theme-btn active" data-theme="light" onclick="document.querySelectorAll('.elder-theme-btn').forEach(b=>b.classList.remove('active'));this.classList.add('active');document.getElementById('elder-theme').value='light';">
            <i class="fas fa-sun"></i> 亮色
        </button>
        <button type="button" class="elder-theme-btn" data-theme="dark" onclick="document.querySelectorAll('.elder-theme-btn').forEach(b=>b.classList.remove('active'));this.classList.add('active');document.getElementById('elder-theme').value='dark';">
            <i class="fas fa-moon"></i> 暗色
        </button>
        <button type="button" class="elder-theme-btn" data-theme="purple" onclick="document.querySelectorAll('.elder-theme-btn').forEach(b=>b.classList.remove('active'));this.classList.add('active');document.getElementById('elder-theme').value='purple';">
            <i class="fas fa-crown"></i> 紫色
        </button>
    </div>
    <input type="hidden" id="elder-theme" value="light">
    <p class="elder-setting-hint">你可以在设置页面中随时更改主题。</p>
</div>

<div class="elder-info-card">
    <h4><i class="fas fa-question-circle"></i> 常见问题</h4>
    <details style="margin-bottom:8px;">
        <summary><strong>如何反馈 Bug 或提出建议？</strong></summary>
        <p style="margin-top:8px;">
            推荐通过以下渠道：<br>
            1. <a href="https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto/issues">GitHub Issues</a>（国内可借助 <a href="https://www.dogfight360.com/blog/18682/">Steam Community302</a> 加速）<br>
            2. <strong>QQ 群：1081988645</strong><br>
            反馈时请提供：Bug 出现的具体步骤、LCTA 版本号、相关日志文件。
        </p>
    </details>
    <details>
        <summary><strong>如何获取日志文件？</strong></summary>
        <p style="margin-top:8px;">
            3. 打开 LCTA 安装目录。<br>
            4. 进入 <strong>logs</strong> 文件夹。<br>
            5. 若问题发生在当天，上传 <strong>app.log</strong>；否则根据日期选择对应日志文件。
        </p>
    </details>
</div>

<div class="elder-info-card">
    <h4><i class="fas fa-hand-pointer"></i> 善用帮助</h4>
    <p>在<strong>任意界面</strong>中长按 <kbd style="background:var(--color-bg-primary);border:1px solid var(--color-border);border-radius:4px;padding:2px 6px;font-family:monospace;">W</kbd> 键两秒，即可查看当前页面的详细使用帮助。</p>
</div>

</div>

<button class="primary-btn" onclick="elderManager.switchPage()">
    <i class="fas fa-arrow-right"></i> 继续
</button>
