# 启动器下载来源设置

针对你在上一步选择的更新源，这里可以调整每个来源的详细下载选项。默认值已适用于大多数情况。

<div data-version="415">

<div class="elder-source-card">
    <h4><i class="fas fa-users"></i> LLC（零协）</h4>
    <p>零协社区汉化包。最常用的汉化来源之一。</p>
    <div class="elder-source-options">
        <div class="elder-setting-row">
            <label for="elder-l-zero-download-source">下载源</label>
            <select id="elder-l-zero-download-source" class="elder-select" style="width:auto;min-width:120px;">
                <option value="github">GitHub</option>
                <option value="mirror">镜像站</option>
            </select>
        </div>
        <div class="elder-setting-row" style="margin-top:8px;">
            <label for="elder-l-zero-zip-type">压缩格式</label>
            <select id="elder-l-zero-zip-type" class="elder-select" style="width:auto;min-width:120px;">
                <option value="seven">7z（更快）</option>
                <option value="zip">Zip（兼容性更好）</option>
            </select>
        </div>
        <div class="elder-setting-row" style="margin-top:8px;">
            <label for="elder-l-zero-use-proxy">使用代理加速</label>
            <label class="checkbox-container">
                <input type="checkbox" id="elder-l-zero-use-proxy" checked>
                <span class="checkmark"></span>
            </label>
        </div>
        <div class="elder-setting-row" style="margin-top:8px;">
            <label for="elder-l-zero-use-cache">使用字体缓存</label>
            <label class="checkbox-container">
                <input type="checkbox" id="elder-l-zero-use-cache" checked>
                <span class="checkmark"></span>
            </label>
        </div>

    </div>
</div>

<div class="elder-source-card">
    <h4><i class="fas fa-robot"></i> LCTA-AU</h4>
    <p>作者自维护的机翻汉化包，更新速度快（约 1-3 小时）。详见 <a onclick="showMarkdownModal('assets/LCTA-AU.md', '什么是LCTA-AU');">LCTA-AU 介绍</a>。</p>
    <div class="elder-source-options">
        <div class="elder-setting-row">
            <label for="elder-l-machine-download-source">下载源</label>
            <select id="elder-l-machine-download-source" class="elder-select" style="width:auto;min-width:120px;">
                <option value="github">GitHub</option>
                <option value="mirror">镜像站</option>
            </select>
        </div>
        <div class="elder-setting-row" style="margin-top:8px;">
            <label for="elder-l-machine-use-proxy">使用代理加速</label>
            <label class="checkbox-container">
                <input type="checkbox" id="elder-l-machine-use-proxy" checked>
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
            <label for="elder-l-ourplay-font-option">字体处理方式</label>
            <select id="elder-l-ourplay-font-option" class="elder-select" style="width:auto;min-width:120px;">
                <option value="simplify">简化处理</option>
                <option value="keep">保留原样</option>
                <option value="llc">LLC 风格</option>
            </select>
        </div>
        <div class="elder-setting-row" style="margin-top:8px;">
            <label for="elder-l-ourplay-use-api">使用 API 获取版本信息</label>
            <label class="checkbox-container">
                <input type="checkbox" id="elder-l-ourplay-use-api" checked>
                <span class="checkmark"></span>
            </label>
        </div>
    </div>
</div>

</div>

<button class="primary-btn" onclick="elderManager.switchPage()">
    <i class="fas fa-arrow-right"></i> 继续
</button>
