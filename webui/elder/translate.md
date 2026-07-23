# 翻译设置

配置手动翻译功能的基本选项。在开始翻译之前，需要先选择翻译服务和源语言。

<div data-version="415">

<div class="elder-info-card">
    <h4><i class="fas fa-cogs"></i> 翻译服务</h4>
    <p>选择用于翻译的 API 服务。推荐使用 <strong>DeepSeek</strong>，性价比高，一个赛季约 10 元左右。</p>
    <select id="elder-translator-service" class="elder-select">
        <!-- 翻译服务列表由后端动态填充 -->
    </select>
    <p class="elder-setting-hint">API 密钥请在「配置汉化API」页面中另行设置。</p>
</div>

<div class="elder-info-card">
    <h4><i class="fas fa-globe"></i> 源语言</h4>
    <p>选择游戏原文的语言。大部分文本为英文，部分为日文或韩文。</p>
    <select id="elder-from-lang" class="elder-select">
        <option value="EN">English（英文）</option>
        <option value="JP">日本語（日文）</option>
        <option value="KR">한국어（韩文）</option>
    </select>
</div>

<div class="elder-info-card">
    <h4><i class="fas fa-exchange-alt"></i> 回退翻译</h4>
    <div class="elder-setting-row">
        <label for="elder-fallback">翻译失败时反向回退重试</label>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-fallback" checked>
            <span class="checkmark"></span>
        </label>
    </div>
    <p class="elder-setting-hint">开启后，若源语言方向翻译失败，会自动尝试反向翻译以提高成功率。</p>
</div>

<h3 style="margin-top:20px;">翻译优化选项</h3>

<div class="elder-option-card">
    <div class="elder-option-icon"><i class="fas fa-tags"></i></div>
    <div class="elder-option-body">
        <h4>专有名词替换</h4>
        <p>翻译时自动将人名、地名、技能名等专有名词替换为正确译名，提高翻译准确性。</p>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-enable-proper" checked>
            <span class="checkmark"></span> 启用专有名词替换
        </label>
    </div>
</div>

<div class="elder-option-card">
    <div class="elder-option-icon"><i class="fas fa-user"></i></div>
    <div class="elder-option-body">
        <h4>角色标记</h4>
        <p>翻译时自动识别角色对白并添加说话人标记，帮助 LLM 理解语境，提高翻译质量。</p>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-enable-role" checked>
            <span class="checkmark"></span> 启用角色标记
        </label>
    </div>
</div>

<div class="elder-option-card">
    <div class="elder-option-icon"><i class="fas fa-bolt"></i></div>
    <div class="elder-option-body">
        <h4>状态效果标记</h4>
        <p>翻译技能描述时添加状态效果上下文信息，帮助 LLM 准确翻译游戏术语。</p>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-enable-skill" checked>
            <span class="checkmark"></span> 启用状态效果标记
        </label>
    </div>
</div>

<div class="elder-option-card">
    <div class="elder-option-icon"><i class="fas fa-check-double"></i></div>
    <div class="elder-option-body">
        <h4>规则化后处理校验</h4>
        <p>翻译完成后使用确定性规则引擎自动检测和修复 Buff ID 空格、特殊效果引用缺失等问题。仅对技能文件生效。</p>
        <label class="checkbox-container">
            <input type="checkbox" id="elder-enable-rule-validation" checked>
            <span class="checkmark"></span> 启用规则化校验
        </label>
    </div>
</div>

</div>

<button class="primary-btn" onclick="elderManager.switchPage()">
    <i class="fas fa-arrow-right"></i> 继续
</button>
