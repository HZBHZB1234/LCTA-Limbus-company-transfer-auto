# 老年人模式

简单而又方便的进行配置  

您可以随时通过*关于*页面底部的按钮重新进入这个页面  

<div id="elder-first-use" style="display: none;">
    <button class="primary-btn" onclick="elderManager.switchPage();">
        <i class="fas fa-play"></i>
        让我们开始吧
    </button>
</div>  

<div id="elder-continue" style="display: none;">
    <span style="font-size: 30px;"><strong>你有新的设置可以设置</strong><br></span>
    <button class="primary-btn" onclick="elderManager.switchPage();">
        <i class="fas fa-play"></i>
        修改新功能的设置
    </button>
</div>  

<div id="elder-all-complete" style="display: none;">
    <span>所有设置已经完成，开始你的游戏之旅吧!</span>
</div>  

---

<button class="primary-btn" onclick="(async ()=> {let elderList = JSON.stringify(elderManager.updateList);
            elderManager.historyList = JSON.parse(elderList);
            for (const value of Object.keys(elderManager.historyList)) {
                elderManager.historyList[value] = 'new';
            };
            configManager.updateConfigValue('--elder', JSON.stringify(elderManager.historyList));
            await configManager.flushPendingUpdates();
            await pywebview.api.resetElder();
            elderManager.initPage();
            })()">
    <i class="fas fa-play"></i>
    重置引导进度
</button>  
<version>1145</version>

<script>
console.log('你好');
if (first_use) {
    document.getElementById('elder-first-use').style.display = 'block';
    return
};
if (elderManager.evalNextPage()) {
    document.getElementById('elder-continue').style.display = 'block';
} else {
    document.getElementById('elder-all-complete').style.display = 'block';
}
</script>