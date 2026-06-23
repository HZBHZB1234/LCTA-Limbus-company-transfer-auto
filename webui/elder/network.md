# 网络与更新

配置 LCTA 的网络连接和软件更新行为。默认值适合大多数用户，通常无需修改。

<div data-version="415">

<div class="elder-info-card">
    <h4><i class="fas fa-globe"></i> 更新与网络</h4>
    <div class="elder-setting-row">
        <label for="elder-update-use-proxy">使用代理加速 GitHub 更新</label>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-update-use-proxy" checked>
            <span class="checkmark"></span>
        </label>
    </div>
    <p class="elder-setting-hint">国内用户建议开启，使用镜像加速 GitHub 下载。</p>
    <div class="elder-setting-row" style="margin-top:12px;">
        <label for="elder-update-only-stable">仅下载正式版更新</label>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-update-only-stable" checked>
            <span class="checkmark"></span>
        </label>
    </div>
    <p class="elder-setting-hint">关闭后可能收到测试版更新，适合希望尝鲜新功能的用户。</p>
    <div class="elder-setting-row" style="margin-top:12px;">
        <label for="elder-delete-updating">更新后自动清理旧版本包</label>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-delete-updating" checked>
            <span class="checkmark"></span>
        </label>
    </div>
    <p class="elder-setting-hint">建议开启以节省磁盘空间。</p>
</div>

<div class="elder-info-card">
    <h4><i class="fas fa-download"></i> 下载性能</h4>
    <div class="elder-setting-row">
        <label>GitHub 下载线程数</label>
        <input type="number" id="elder-github-max-workers" value="4" min="1" max="16">
    </div>
    <p class="elder-setting-hint">同时下载的文件数量，增大可提升速度但占用更多带宽。推荐值：4</p>
    <div class="elder-setting-row" style="margin-top:12px;">
        <label>请求超时时间（秒）</label>
        <input type="number" id="elder-github-timeout" value="8" min="3" max="60">
    </div>
    <p class="elder-setting-hint">网络较差时可适当增大。推荐值：8</p>
</div>

<div class="elder-info-card">
    <h4><i class="fas fa-bug"></i> 开发者选项</h4>
    <div class="elder-setting-row">
        <label for="elder-debug-mode">调试模式</label>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-debug-mode">
            <span class="checkmark"></span>
        </label>
    </div>
    <p class="elder-setting-hint">启用后将输出更详细的日志信息。<strong>普通用户无需开启</strong>。</p>
</div>

</div>

<button class="primary-btn" onclick="elderManager.switchPage()">
    <i class="fas fa-arrow-right"></i> 继续
</button>
