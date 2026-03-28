# 您倾向于如何使用LCTA?

LCTA工具箱是一个极其综合的项目，您可以简单方便的调用使用制作好的功能，也可以完成高度自定义的操作。  
请在下列的选项中勾选你想要了解并配置的内容，可以选择多个。  
个人建议都过一遍，反正不吃亏。

### 我希望基本的了解一下LCTA

<version>415</version>

基本的介绍。非常短

<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" id="elder-character-base" checked onclick="if (!this.checked) {showMessage('꒦ິ^꒦ິ ', (ó﹏ò｡) )}">
        <span class="checkmark"></span>
        我希望基本的了解一下LCTA
    </label>
</div>


### 我希望使用LCTA作为启动器

<version>415</version>

使用LCTA作为启动器，游戏会在每一次启动时自动检测是否有汉化包更新，如果有，那么会自动下载并安装。同时支持自动下载气泡文本，自动运行美化等等。集成了mod加载支持，兼容Faust Launcher格式的模组进行加载。  
#### 什么是LCTA-AU?
<a onclick="showMarkdownModal('assets/LCTA-AU.md', '什么是LCTA-AU');">LCTA-AU</a>(点击链接查看介绍)

相较与Faust Launcher，LCTA启动器具有以下优点：
- 支持更加多的汉化包来源，如<a onclick="showMarkdownModal('assets/LCTA-AU.md', '什么是LCTA-AU');">LCTA-AU</a>与Ourplay。
- 更快的启动速度：浮士德启动器在每一次启动的时候都会重新复制一遍所有的文本文件、执行所有美化、复制所有mod。这会大大降低启动速度。LCTA仅在有更新时才会进行更新，启动速度更快。
- 更加的时效性：浮士德启动器的 *人格技能名称美化*，*汉化包更新*，*气泡文本更新* 这三个功能依赖于 [@folkskill](https://github.com/f0lkskill)手动的进行更新，往往包含半天到数天的延迟。LCTA直接从来源处获取信息，确保没有任何的滞后时间。

<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" id="elder-character-launcher" checked>
        <span class="checkmark"></span>
        我希望使用LCTA作为启动器
    </label>
</div>

### 我希望使用LCTA进行翻译

<version>415</version>

LCTA脱胎与翻译脚本，因此，翻译功能是LCTA的一大特色。在一些情况下，LCTA-AU无法及时的更新，又或是对翻译具有较高的需求，那么您可以手动进行翻译。  
在开始翻译之前，需要先配置API。虽然大部分API都包含翻译功能，但是大部分较为优质API需要付费。一般而言，付费的api的翻译效果会更好。  
个人推荐使用Deepseek进行翻译。使用Deepseek进行翻译，API价格大约一个赛季的开销是10元作用。

<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" id="elder-character-translate">
        <span class="checkmark"></span>
        我希望使用LCTA进行翻译
    </label>
</div>

### 我希望使用LCTA进行管理

<version>415</version>

LCTA提供了不少管理功能，如汉化包管理，mod管理等等。这些内容都可以在左侧的侧边栏中看见。相对的，这个板块的文档内容会略少一些。

<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" id="elder-character-manage">
        <span class="checkmark"></span>
        我希望使用LCTA进行管理
    </label>
</div>

<button class="primary-btn" onclick="elderManager.switchPage();">
    <i class="fas fa-play"></i>
    继续
</button>