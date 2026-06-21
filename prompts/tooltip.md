# 配置项悬停提示规范

配置项通过 CSS tooltip + JS 数据映射实现鼠标悬停显示简要说明。

## 架构

```
TOOLTIP_DATA (JS 映射)  →  initTooltips()  →  data-tooltip 属性  →  CSS ::after 伪元素
```

- **`webui/script.js`** — `TOOLTIP_DATA` 对象：`元素ID → 描述文本` 的映射
- **`webui/script.js`** — `initTooltips()` 函数：在页面加载时将描述写入对应 DOM 元素的 `data-tooltip` 属性
- **`webui/style.css`** — `[data-tooltip]::after` 样式：`position: absolute` 的弹出气泡，暗底白字圆角阴影，`opacity`/`visibility` 过渡动画

## 添加新的静态 Tooltip

在 `TOOLTIP_DATA` 映射中添加条目：

```js
'element-id': '鼠标悬停时显示的简要说明文字。',
```

支持的 DOM 元素类型（`initTooltips()` 自动判断）：
- **复选框** (`input[type=checkbox]`)：tooltip 挂载到 `.checkbox-container`
- **文本输入框 / 下拉框** (`input`, `select`, `textarea`)：tooltip 挂载到关联的 `<label>`（通过 `for` 属性匹配）
- **容器元素**（如 `div.form-group`）：tooltip 挂载到 `.form-group` 自身

## 动态 API 配置项的 Tooltip

`APIConfigManager.createSettingField()` 从 `setting.description` 自动生成 tooltip：
- 非 boolean 类型：tooltip 挂载到 `<label>`，同时保留 `<small class="form-hint">` 和 `placeholder`
- boolean 类型：tooltip 挂载到 `.checkbox-container`（此前 boolean 类型完全不展示 description）

## 添加新页面配置项时

1. 在 `index.html` 中为新配置项设置唯一 `id`
2. 在 `TOOLTIP_DATA` 中添加对应的 `id → 描述` 条目
3. 描述应简洁（1-2 句话），说明该项的作用和使用场景
