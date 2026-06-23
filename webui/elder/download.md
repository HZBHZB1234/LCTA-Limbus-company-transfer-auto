# 手动下载设置

当你手动下载汉化包（而非使用启动器自动更新）时，以下选项控制下载行为。默认值适用于大多数情况。

<div data-version="415">

<div class="elder-source-card">
    <h4><i class="fas fa-users"></i> LLC（零协）</h4>
    <p>社区汉化包，最常用的来源。</p>
    <div class="elder-source-options">
        <div class="elder-setting-row">
            <label for="elder-d-zero-download-source">下载源</label>
            <select id="elder-d-zero-download-source" class="elder-select" style="width:auto;min-width:120px;">
                <option value="github">GitHub</option>
                <option value="mirror">镜像站</option>
            </select>
        </div>
        <div class="elder-setting-row" style="margin-top:8px;">
            <label for="elder-d-zero-zip-type">压缩格式</label>
            <select id="elder-d-zero-zip-type" class="elder-select" style="width:auto;min-width:120px;">
                <option value="zip">Zip</option>
                <option value="seven">7z</option>
            </select>
        </div>
        <div class="elder-setting-row" style="margin-top:8px;">
            <label for="elder-d-zero-use-proxy">使用代理加速</label>
            <label class="checkbox-container">
                <input type="checkbox" id="elder-d-zero-use-proxy" checked>
                <span class="checkmark"></span>
            </label>
        </div>
        <div class="elder-setting-row" style="margin-top:8px;">
            <label for="elder-d-zero-use-cache">使用字体缓存</label>
            <label class="checkbox-container">
                <input type="checkbox" id="elder-d-zero-use-cache" checked>
                <span class="checkmark"></span>
            </label>
        </div>
        <div class="elder-setting-row" style="margin-top:8px;">
            <label for="elder-d-zero-dump-default">保留解包原始文件</label>
            <label class="checkbox-container">
                <input type="checkbox" id="elder-d-zero-dump-default">
                <span class="checkmark"></span>
            </label>
        </div>
        <p class="elder-setting-hint">调试用，普通用户无需开启。</p>
    </div>
</div>

<div class="elder-source-card">
    <h4><i class="fas fa-robot"></i> LCTA-AU</h4>
    <p>作者自维护的机翻汉化包。详见 <a onclick="showMarkdownModal('assets/LCTA-AU.md', '什么是LCTA-AU');">LCTA-AU 介绍</a>。</p>
    <div class="elder-source-options">
        <div class="elder-setting-row">
            <label for="elder-d-machine-download-source">下载源</label>
            <select id="elder-d-machine-download-source" class="elder-select" style="width:auto;min-width:120px;">
                <option value="github">GitHub</option>
                <option value="mirror">镜像站</option>
            </select>
        </div>
        <div class="elder-setting-row" style="margin-top:8px;">
            <label for="elder-d-machine-use-proxy">使用代理加速</label>
            <label class="checkbox-container">
                <input type="checkbox" id="elder-d-machine-use-proxy" checked>
                <span class="checkmark"></span>
            </label>
        </div>
    </div>
</div>

<div class="elder-source-card">
    <h4><i class="fas fa-mobile-alt"></i> OurPlay</h4>
    <p>OurPlay 加速器的汉化包。</p>
    <div class="elder-source-options">
        <div class="elder-setting-row">
            <label for="elder-d-ourplay-font-option">字体处理方式</label>
            <select id="elder-d-ourplay-font-option" class="elder-select" style="width:auto;min-width:120px;">
                <option value="simplify">简化处理</option>
                <option value="keep">保留原样</option>
                <option value="llc">LLC 风格</option>
            </select>
        </div>
        <div class="elder-setting-row" style="margin-top:8px;">
            <label for="elder-d-ourplay-check-hash">启用哈希校验</label>
            <label class="checkbox-container">
                <input type="checkbox" id="elder-d-ourplay-check-hash" checked>
                <span class="checkmark"></span>
            </label>
        </div>
        <div class="elder-setting-row" style="margin-top:8px;">
            <label for="elder-d-ourplay-use-api">使用 API 获取版本信息</label>
            <label class="checkbox-container">
                <input type="checkbox" id="elder-d-ourplay-use-api">
                <span class="checkmark"></span>
            </label>
        </div>
    </div>
</div>

</div>

<button class="primary-btn" onclick="elderManager.switchPage()">
    <i class="fas fa-arrow-right"></i> 继续
</button>
