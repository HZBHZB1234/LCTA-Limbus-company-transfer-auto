## 启动器配置

### 为什么要使用启动器

使用LCTA作为启动器，游戏会在每一次启动时自动检测是否有汉化包更新，如果有，那么会自动下载并安装。同时支持自动下载气泡文本，自动运行美化等等。集成了mod加载支持，兼容Faust Launcher格式的模组进行加载。  
也就是说，这可以避免繁杂的汉化包更新，下载气泡文本等操作。  

### 启动器配置
你希望使用启动器的哪些功能?

#### Mod支持
<version>415</version>
通过替换资源，边狱公司可以加载自定义的皮肤模组和音效模组。  
效果举例展示: 
> <img src="https://free.picui.cn/free/2026/03/28/69c772feedff9.webp" width="500">

来源: [n站](https://www.nexusmods.com/limbuscompany/mods/102) ，祥子替换绝望罗

<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" id="elder-launcher-mod">
        <span class="checkmark"></span>
        启用模组
    </label>
</div>

#### 启用气泡文本
<version>415</version>
通过替换文本文件，可以让每一个人格说话时都显示气泡文本
> <img src="https://free.picui.cn/free/2026/03/28/69c775a568da2.png" width="100%">
详细信息: [B站视频]>(https://www.bilibili.com/video/BV1GVpszcEi9)

<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" id="elder-launcher-bubble">
        <span class="checkmark"></span>
        启用气泡文本
    </label>
</div>

#### 启用文本美化
<version>415</version>
包含技能名称美化，技能描述美化、气泡文本美化等等功能。
> <img src="https://free.picui.cn/free/2026/03/28/69c776ed91fe9.png" width="500">
技能描述美化效果展示

<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" id="elder-launcher-fancy">
        <span class="checkmark"></span>
        启用文本美化
    </label>
</div>

---

<button class="primary-btn" onclick="elderManager.switchPage();">
    <i class="fas fa-play"></i>
    继续
</button>