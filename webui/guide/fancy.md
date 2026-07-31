# 文本美化

文本美化使用结构化规则修改语言包 JSON，例如替换文本、添加标签、生成颜色渐变或按技能属性着色。

## 快速使用

1. 在美化页面勾选需要启用的规则集。
2. 点击“保存全部”。
3. 点击“立即应用美化”。

美化会直接修改当前语言包。更新或重装语言包后需要重新应用，请勿对同一个语言包反复执行非幂等规则。

## 规则集格式

规则集支持原生 v2 和 bus v1。原生 v2 适合条件、包裹、渐变和技能属性颜色：

```json
{
  "version": 2,
  "name": "示例规则集",
  "desc": "规则集说明",
  "rules": []
}
```

## Bus 替换规则

bus 格式用于顺序文本替换、调爪规则导入和简易翻译编辑：

```json
{
  "format": "lcta-bus",
  "version": 1,
  "name": "巴士替换示例",
  "desc": "按顺序替换技能名称",
  "files": ["*.json"],
  "exclude_dirs": ["config", "font"],
  "rules": [
    {
      "files": [{"regex": "Skills.*\\.json$"}],
      "path": "dataList[?id=10100201].levelList[*].name",
      "replacements": [
        {"from": "肉斩", "to": "舍吾皮肉"},
        {"from": "X", "to": "XX", "safe": true},
        {"from": "！", "to": "。", "mode": "end"},
        {"set": "精确值"}
      ]
    }
  ]
}
```

- `path` 支持普通字段、自动列表遍历、`[*]`、`[n]` 和 `[?字段=值]` 首项定位；空路径表示遍历整份 JSON 的所有字符串叶子。
- `files` 支持 glob、`{"regex":"..."}` 和内部精确路径匹配；调爪 `aimFile` 导入时保留正则搜索语义。
- `replacements` 严格按数组顺序执行，支持 literal、regex、end、safe 和任意 JSON 值的 `set`。
- `exclude_dirs` 对相对路径中的目录组件执行大小写不敏感的子串排除。

在美化页面点击“导入巴士规则”可多选 bus JSON 或调爪 JSON。也可以直接拖入文件并确认导入。导入会生成独立用户规则集，默认保持禁用，检查内容后再手动启用。

简易翻译编辑器将 `_quick_edits.json` 保存为带 `edits` 和 bus `set` 规则的派生规则集。它会显示在美化列表中，但必须继续通过简易翻译编辑器维护，因此主页面将其设为只读。

## V2 规则字段

每条规则包含文件匹配、作用域、目标、条件和操作：

```json
{
  "files": ["Skill*.json"],
  "scope": "dataList[*]",
  "targets": ["desc"],
  "where": [
    {"path": "id", "operator": "in", "value": [10001, 10002]}
  ],
  "actions": [
    {"type": "replace", "mode": "literal", "from": "大于", "to": ">"}
  ]
}
```

### `files`

相对语言包目录的 Glob 列表：

- `Skill*.json`：匹配技能类 JSON。
- `StoryData/*.json`：匹配 `StoryData` 目录下的 JSON。
- `*.json`：匹配任意目录中的 JSON 文件名。

路径统一使用 `/`，不需要编写文件名正则。

### `scope`

指定条件与目标共享的数据作用域。支持：

- 字段：`dataList`
- 任意列表项：`dataList[*]`
- 固定列表项：`levelList[0]`
- 嵌套路径：`dataList[*].levelList[*]`

例如 EGO 名称和描述需要在同一个等级条目中关联，可以使用：

```json
"scope": "dataList[*].levelList[*]"
```

### `targets`

相对作用域的目标路径列表。所有命中的字符串都会依次执行 `actions`：

```json
"targets": ["name", "abName"]
```

目标也支持列表通配符：

```json
"scope": "dataList[*]",
"targets": ["levelList[*].name"]
```

### `where`

条件之间为 AND 关系。单个条件路径匹配多个值时，任意一个值满足即可。

支持的操作符：

| 操作符 | 说明 | 示例值 |
| --- | --- | --- |
| `equals` | 值完全相等 | `10001` |
| `in` | 值属于数组 | `[10001, 10002]` |
| `contains` | 字符串包含指定文本 | `"指定"` |
| `regex` | 对值执行正则匹配 | `"^(?!.*指定).*$"` |

条件示例：

```json
"where": [
  {"path": "id", "operator": "in", "value": [10001, 10002]},
  {"path": "desc", "operator": "contains", "value": "指定"}
]
```

### `actions`

操作按照数组顺序执行。

#### 普通文本替换

```json
{"type": "replace", "mode": "literal", "from": "大于", "to": ">"}
```

普通文字优先使用 `literal`，其执行速度更快，也不需要转义正则字符。

#### 正则替换

```json
{"type": "replace", "mode": "regex", "from": "^(.*)$", "to": "[\\1]"}
```

仅在需要捕获组或复杂匹配时使用 `regex`。

#### 文本包裹

```json
{"type": "wrap", "prefix": "<b>", "suffix": "</b>"}
```

包裹操作比使用 `^(.*)$` 的正则替换更直接、更快。

#### 颜色渐变

```json
{"type": "gradient", "rate": 0.4}
```

渐变操作会处理文本中的首个 `<color=#...>...</color>` 区域。

#### 技能属性颜色

```json
{"type": "skill_color", "idPath": "id"}
```

`idPath` 相对当前 `scope`。引擎根据技能 ID 查询游戏资源中的属性颜色，并将映射缓存到全局缓存目录。游戏资源未变化时，后续运行会直接读取缓存。

## 完整示例

```json
{
  "version": 2,
  "name": "指定技能名称",
  "desc": "美化指定等级的技能名",
  "rules": [
    {
      "files": ["Skills_Ego_Personality-*.json"],
      "scope": "dataList[*].levelList[*]",
      "targets": ["name", "abName"],
      "where": [
        {"path": "desc", "operator": "contains", "value": "指定"}
      ],
      "actions": [
        {"type": "wrap", "prefix": "<color=#ff0000>⚠️", "suffix": "⚠️</color>"},
        {"type": "gradient", "rate": 0.5},
        {"type": "wrap", "prefix": "<b><i>", "suffix": "</i></b>"}
      ]
    }
  ]
}
```

## 规则集编辑器

- 简单模式分别编辑文件 Glob、作用域、目标路径、AND 条件和类型化操作。
- 多个目标路径使用逗号分隔。
- 条件可选择“等于、属于、包含、正则”。
- 操作可选择“替换、包裹、渐变、技能颜色”。
- 高级模式直接编辑完整的 v2 JSON，并可使用“验证”和“格式化”。
- 智能生成、模板、规则预览和实际应用均使用同一个 v2 执行器。

## 性能说明

规则会在处理文件前完成路径与正则编译。每个 JSON 使用结构化路径直接遍历，不再为每个候选字段重复扫描全部扁平路径。内容没有实际变化时不会重写文件。
