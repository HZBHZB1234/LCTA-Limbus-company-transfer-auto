# 汉化包下载

从多个平台下载最新的汉化包，又或是下载气泡文本。

## 下载操作
- 在每个卡片中点击对应的“下载”按钮即可开始对应操作。

## 配置选项

### ourplay下载配置

#### 字体处理选项
<div class="form-group">
    <label>字体处理选项:</label>
    <div class="select-wrapper">
        <select>
            <option value="keep">保留原字体</option>
            <option value="simplify">精简字体</option>
            <option value="llc">使用本地字体缓存</option>
        </select>
        <i class="fas fa-chevron-down"></i>
    </div>
</div>

ourplay下载的汉化包携带了两份相同的字体文件。
- 选择`保留原字体`: 保留两份字体文件
- 选择`精简字体`: 去除冗余的字体文件
- 选择`使用本地字体缓存`: 使用缓存的字体文件。关于缓存的字体文件，详情请见`设置`页面

#### 启用哈希校验

<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" checked>
        <span class="checkmark"></span>
        启用哈希校验
    </label>
    <small class="form-hint">确保下载文件的完整性</small>
</div>

校验文件完整性，如果不完整，则会提出警告。

#### 下载源

<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" >
        <span class="checkmark"></span>
        使用API获取链接
    </label>
</div>

使用webnote API进行请求下载，具有延迟，不建议使用

### 零协会下载配置

#### 压缩格式
<div class="form-group">
    <label>压缩格式:</label>
    <div class="select-wrapper">
        <select>
            <option value="zip">ZIP格式</option>
            <option value="seven">7Z格式</option>
        </select>
        <i class="fas fa-chevron-down"></i>
    </div>
</div>

选择下载的汉化包压缩格式，ZIP兼容性更好，7Z文件小。

#### 文本下载来源
<div class="form-group">
    <label>文本下载来源:</label>
    <div class="select-wrapper">
        <select>
            <option value="github">从github下载</option>
            <option value="mirror">从公益镜像下载 beta</option>
        </select>
        <i class="fas fa-chevron-down"></i>
    </div>
</div>

- `从github下载`：直接从GitHub Release获取。
- `从公益镜像下载`：使用webnote API下载，具有延迟。

#### 使用代理加速下载
<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" checked>
        <span class="checkmark"></span>
        使用代理加速下载
    </label>
</div>

勾选后，将使用代理服务器加速github请求。

#### 使用本地字体缓存
<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox">
        <span class="checkmark"></span>
        使用本地字体缓存
    </label>
    <small class="form-hint">使用本地已有的字体文件，加快下载速度</small>
</div>

使用缓存的字体文件。关于缓存的字体文件，详情请见`设置`页面

#### 保存原始文件而不打包
<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox">
        <span class="checkmark"></span>
        保存原始文件而不打包
    </label>
    <small class="form-hint">保存解压后的原始文件而非打包格式</small>
</div>

勾选后，下载的汉化包会被解压并保留原始文件结构，而不是保存为汉化包。历史遗留选项

### LCTA-AU下载配置

LCTA-AU 是一个自动机翻汉化源，翻译延时仅1-3小时，且翻译质量高于ourplay等加速器。如果您没有其它需求，建议使用本汉化源进行汉化更新。

#### 文本下载来源
<div class="form-group">
    <label>文本下载来源:</label>
    <div class="select-wrapper">
        <select>
            <option value="github">从github下载</option>
            <option value="mirror">从公益镜像下载 beta</option>
        </select>
        <i class="fas fa-chevron-down"></i>
    </div>
</div>

与零协会类似，可选择GitHub直连webnote API。

#### 使用代理加速下载
<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" checked>
        <span class="checkmark"></span>
        使用代理加速下载
    </label>
</div>

勾选后启用github代理加速。

### 气泡文本下载配置

气泡文本是一个基于官方文本接口的语言气泡实现。  
关于气泡文本的详细信息，请见[B站视频](https://www.bilibili.com/video/BV1GVpszcEi9)。  
小贴士: 气泡文本是直接安装在文本包上的。也就是说每一次切换或更新汉化包后都需要重新安装。如果想要避免这个麻烦，详情请见`launcher配置`页面。

#### 下载有颜色的气泡文本
<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox">
        <span class="checkmark"></span>
        下载有颜色的气泡文本
    </label>
</div>

勾选后，将下载彩色气泡。使用效果见[视频](https://www.bilibili.com/video/BV16T1uBBETa)。

#### 下载随机加载文本
<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox">
        <span class="checkmark"></span>
        下载随机加载文本
    </label>
</div>

下载包含随机加载文本的版本，会在战斗加载页面显示。内容为零协会曾经使用的加载文本。

#### 立即安装
<div class="form-group">
    <label class="checkbox-container">
        <input type="checkbox" checked>
        <span class="checkmark"></span>
        立即安装
    </label>
</div>

勾选后，下载完成将自动安装气泡文本到当前汉化包。