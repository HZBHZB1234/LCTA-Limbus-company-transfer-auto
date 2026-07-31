# 设置游戏路径

请先设置《边狱公司》的游戏安装目录。这是 LCTA 正常工作的前提 —— 汉化包安装、MOD 加载、启动器功能都依赖于此。

<div data-version="415">

<div class="elder-info-card">
    <h4><i class="fas fa-folder-open"></i> 游戏安装目录</h4>
    <p>选择 Limbus Company 的游戏根目录（包含 <strong>LimbusCompany.exe</strong> 的文件夹）。</p>
    <div class="elder-path-input">
        <input type="text" id="elder-game-path" placeholder="例如：D:\Steam\steamapps\common\Limbus Company">
        <button type="button" class="primary-btn" onclick="pywebview.api.browse_folder('elder-game-path')" style="padding:10px 20px;white-space:nowrap;margin-top:0;">
            <i class="fas fa-folder"></i> 浏览
        </button>
    </div>
    <p class="elder-setting-hint"><strong>Steam 用户</strong>：在库中右键游戏 → 管理 → 浏览本地文件，复制地址栏路径即可。</p>
</div>

<div class="elder-info-card">
    <label for="elder-game-source">游戏来源</label>
    <div class="elder-radio-group">
        <label><input type="radio" id="elder-game-source" name="elder-game-source" value="steam" checked> Steam</label>
        <label><input type="radio" name="elder-game-source" value="ourplay"> OurPlay 加速器</label>
        <label><input type="radio" name="elder-game-source" value="other"> 其他</label>
    </div>
    <p class="elder-setting-hint">选择你的游戏安装来源，向导会据此调整后续下载源建议。</p>
</div>

<div class="elder-tip-card">
    <i class="fas fa-lightbulb"></i>
    <span>如果暂时不确定路径，可以跳过此步骤，之后在「设置」页面中随时配置。若游戏路径留空，首次启动会自动检测 Steam 路径，检测到时会弹窗确认。</span>
</div>

</div>

<button class="primary-btn" onclick="elderManager.switchPage()">
    <i class="fas fa-arrow-right"></i> 继续
</button>
