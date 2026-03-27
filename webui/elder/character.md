# 您倾向于如何使用LCTA?

LCTA工具箱是一个极其综合的项目，您可以简单方便的调用使用制作好的功能，也可以完成高度自定义的操作。  
请在下列的选项中勾选你想要了解并配置的内容，可以选择多个。

### 我希望使用LCTA作为启动器

使用LCTA作为启动器，游戏会在每一次启动时自动检测是否有汉化包更新，如果有，那么会自动下载并安装。同时支持自动下载气泡文本，自动运行美化等等。同时集成了mod加载支持，同时兼容Faust Launcher格式的模组进行加载。  

向较与Faust Launcher，LCTA启动器具有以下优点：
- 支持更加多的汉化包来源，如<a onclick="showMarkdownModal('assets/LCTA-AU.md', '什么是LCTA-AU');">LCTA-AU</a>(点击链接查看介绍)与Ourplay。

<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" id="elder-character-launcher">
        <span class="checkmark"></span>
        我希望使用LCTA作为启动器
    </label>
</div>

<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" id="elder-character-translate">
        <span class="checkmark"></span>
        我希望使用LCTA进行翻译
    </label>
</div>

<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" id="elder-character-manage">
        <span class="checkmark"></span>
        我希望使用LCTA进行管理
    </label>
</div>

<div id="elder-first-use">
    <button class="primary-btn" onclick="elderManager.switchPage();">
        <i class="fas fa-play"></i>
        继续
    </button>
</div>  
