## 气泡文本

气泡文本是一个基于官方文本接口的语言气泡实现，可以让每个人格在游戏中说话时显示气泡文本。

详细信息请见 [B站视频介绍](https://www.bilibili.com/video/BV1GVpszcEi9)

### 配置选项

#### 下载有颜色的气泡文本

勾选后，将下载带有颜色的气泡文本版本。使用效果见 [视频演示](https://www.bilibili.com/video/BV16T1uBBETa)。

#### 下载随机加载文本

勾选后，下载包含随机加载文本的气泡文本版本。这些文本会在战斗加载页面显示有趣的随机内容。

#### 立即安装

勾选后，下载完成将自动安装气泡文本到当前已启用的汉化包。

### 重要提示

气泡文本是直接安装在汉化包上的，也就是说**每次切换或更新汉化包后都需要重新安装气泡文本**。如果觉得麻烦，可以在启动器配置中启用"启用气泡文本"选项，这样启动器会在每次更新后自动安装气泡文本。

### 配置

<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" id="elder-bubble-color">
        <span class="checkmark"></span>
        下载有颜色的气泡文本
    </label>
</div>

<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" id="elder-bubble-llc">
        <span class="checkmark"></span>
        下载随机加载文本
    </label>
</div>

<button class="primary-btn" onclick="elderManager.switchPage();">
  <i class="fas fa-play"></i>
  继续
</button>
