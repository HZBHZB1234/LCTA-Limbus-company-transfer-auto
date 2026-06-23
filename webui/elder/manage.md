# 数据管理

配置汉化包和 MOD 的存储位置，以及缓存和清理相关选项。

<div data-version="415">

<div class="elder-info-card">
    <h4><i class="fas fa-box"></i> 汉化包存放目录</h4>
    <p>下载的汉化包文件将保存在此目录中。</p>
    <div class="elder-path-input">
        <input type="text" id="elder-package-directory" placeholder="留空使用默认位置 (tmp)">
        <button type="button" class="primary-btn" onclick="pywebview.api.browse_folder('elder-package-directory')" style="padding:10px 20px;white-space:nowrap;margin-top:0;">
            <i class="fas fa-folder"></i> 浏览
        </button>
    </div>
    <p class="elder-setting-hint">留空则使用默认临时目录。</p>
</div>

<div class="elder-info-card">
    <h4><i class="fas fa-puzzle-piece"></i> MOD 安装目录</h4>
    <p>下载的模组将安装到此目录中。</p>
    <div class="elder-path-input">
        <input type="text" id="elder-mod-path" placeholder="留空使用默认位置">
        <button type="button" class="primary-btn" onclick="pywebview.api.browse_folder('elder-mod-path')" style="padding:10px 20px;white-space:nowrap;margin-top:0;">
            <i class="fas fa-folder"></i> 浏览
        </button>
    </div>
</div>

<div class="elder-info-card">
    <h4><i class="fas fa-hdd"></i> 缓存与存储</h4>
    <div class="elder-setting-row">
        <label for="elder-enable-cache">启用资源缓存</label>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-enable-cache" checked>
            <span class="checkmark"></span>
        </label>
    </div>
    <p class="elder-setting-hint">缓存已下载的资源文件，避免重复下载，加快后续操作速度。</p>
    <div class="elder-setting-row" style="margin-top:12px;">
        <label for="elder-enable-storage">启用数据持久化存储</label>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-enable-storage">
            <span class="checkmark"></span>
        </label>
    </div>
    <p class="elder-setting-hint">将翻译结果、配置备份等数据持久化存储到指定目录。</p>
</div>

<div class="elder-info-card">
    <h4><i class="fas fa-broom"></i> 清理选项</h4>
    <p>自动清理临时文件，释放磁盘空间。</p>
    <div class="elder-setting-row">
        <label for="elder-clean-progress">清理进度文件</label>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-clean-progress">
            <span class="checkmark"></span>
        </label>
    </div>
    <div class="elder-setting-row" style="margin-top:8px;">
        <label for="elder-clean-notice">清理通知文件</label>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-clean-notice">
            <span class="checkmark"></span>
        </label>
    </div>
    <div class="elder-setting-row" style="margin-top:8px;">
        <label for="elder-clean-mods">清理默认 MOD 资源</label>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-clean-mods">
            <span class="checkmark"></span>
        </label>
    </div>
</div>

</div>

<button class="primary-btn" onclick="elderManager.switchPage()">
    <i class="fas fa-arrow-right"></i> 继续
</button>
