# 文本美化

文本美化使用结构化规则修改语言包 JSON，例如替换文本、添加标签、生成颜色渐变或按技能属性着色。

## 快速使用

1. 在美化页面勾选需要启用的规则集。
2. 点击“保存全部”。
3. 点击“立即应用美化”。

美化会直接修改当前语言包。更新或重装语言包后需要重新应用，请勿对同一个语言包反复执行非幂等规则。

应用美化后，程序会在语言包目录写入一个特征文件（`.lcta_fancy_applied`），用于标记该语言包已美化过。再次对同一语言包点击“立即应用美化”时，程序会先弹窗确认，避免重复应用非幂等规则产生非预期结果。更新或重装语言包会覆盖该目录，特征文件随之消失，属于正常现象。

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
  "name": "文本替换示例",
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

- `path` 支持普通字段、自动列表遍历、`[*]`、`[n]` 和 `[?字段=值]` 首项定位；空路径表示遍历整份 JSON 的所有字符串叶子。规则可带 `required: true`：路径未命中时该规则计入失败并报“路径未命中”错误，简易翻译编辑器生成的派生规则依赖此标志。
- `files` 支持 glob、`{"regex":"..."}` 和 `{"exact":"相对路径"}` 精确匹配对象（简易翻译编辑器生成的派生规则使用后者）；调爪 `aimFile` 导入时保留正则搜索语义。规则集顶层的 `files` 是各规则的默认匹配，规则内省略 `files` 时继承顶层值。
- `replacements` 严格按数组顺序执行。文本替换支持 `literal`、`regex`、`end` 三种 mode；`safe` 是与 mode 正交的布尔标志，用于防止新串包含旧串时替换结果被反复命中；`set` 可直接将目标设为任意 JSON 值。
- `exclude_dirs` 对相对路径中的目录组件执行大小写不敏感的子串排除。

在美化页面点击“导入其他文本替换规则”可多选 bus JSON、调爪 JSON、LCJE 补丁 JSON或 FL 补丁 JSON。LCJE 同时支持编辑器导出的 `{"mods":[{"file":"LLC_zh-CN\\Skills.json","path":"dataList[0].name","old":"旧文本","new":"新文本"}]}`，以及旧版 `{"LLC_zh-CN\\Skills.json":{"dataList[0].name":"新文本"}}` 文件→路径映射，两者都会转换为精确文件、精确路径的整值替换。FL 使用 FaustLauncher 自定义汉化工具生成的 changes.json（形如 `{"LLC_zh-CN\\Personalities.json":{"dataList":[{"id":10212,"changes":{"title":"新文本"}}]}}`），按文件→`id` 匹配或列表逐位导入。也可以直接拖入文件并确认导入。导入会生成独立用户规则集，默认保持禁用，检查内容后再手动启用。

简易翻译编辑器将 `_quick_edits.json` 保存为带 `edits` 和 bus `set` 规则的派生规则集。它会显示在美化列表中，但必须继续通过简易翻译编辑器维护，因此主页面将其设为只读（删除按钮未对其禁用，请勿删除 `_quick_edits` 规则集）。

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
- `StoryData/*.json`：匹配 `StoryData` 目录下的 JSON（该模式要求路径以 `StoryData/` 开头，`*` 可跨越 `/`，因此也会命中更深层的子目录）。
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

`scope` 可省略，省略时以整份 JSON 的根作为作用域。

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

条件之间为 AND 关系。单个条件路径匹配多个值时，任意一个值满足即可。`where` 可省略或为空数组，此时规则无条件作用于所有命中项。

支持的操作符：

| 操作符 | 说明 | 示例值 |
| --- | --- | --- |
| `equals` | 值完全相等 | `10001` |
| `in` | 值属于数组 | `[10001, 10002]` |
| `contains` | 字符串包含指定文本（仅对字符串值匹配） | `"指定"` |
| `regex` | 对值执行正则匹配（数字、布尔值会先转为字符串再匹配） | `"^(?!.*指定).*$"` |

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

普通文字优先使用 `literal`，其执行速度更快，也不需要转义正则字符。`literal` 与 `regex` 均为全局替换，会替换文本中的所有出现。

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

渐变操作会处理文本中的首个 `<color=#...>...</color>` 区域，未找到颜色区域时该操作不生效。

`rate` 控制渐变速度，`rate` 越大渐变越快，默认 2.0，必须为正数。

#### 技能属性颜色

```json
{"type": "skill_color", "idPath": "id"}
```

`idPath` 相对当前 `scope`。引擎根据技能 ID 查询游戏资源中的属性颜色，并按 `enable_cache` 开关将映射缓存到配置的 `cache_path`（默认 `tmp/fancy/skill-colors.json`）。游戏资源指纹变化时缓存自动重建，资源未变化时后续运行直接读取缓存。

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

## LLM 文本美化

美化页面上的「LLM 文本美化」按钮会打开独立窗口，使用 bus 语法匹配文本组后交给 LLM 重写，并输出 bus 引擎格式规则集：

1. **匹配规则**：使用与 bus 相同的文件匹配器（glob / `{"exact":...}` / `{"regex":...}`）与路径语法（`[*]`、`[n]`、`[?字段=值]`、空路径匹配全部字符串叶子）选择要美化的文本组。
2. **排除规则集**：勾选 fancy/ 中已有的 bus 规则集作为排除项。程序会用 bus 引擎在数据副本上模拟执行这些规则集，已被命中的文本路径不会送 LLM，避免重复处理（例如上一次 LLM 美化生成的规则集）。
3. **LLM 设置**：复用「API 配置」页的「LLM通用翻译服务」（base_url / model / api_key），无需重复填写。可勾选「启用去重」：相同文本只送一次 LLM，改写结果自动应用到所有相同文本位置，节省 API 调用（默认开启）。
4. **提示词**：默认仅注入保证 JSON 解析正确的系统提示；勾选「启用自定义美化指令」后可追加自己的美化要求（例如风格、语气）。
5. **输出**：扫描到的文本按批大小打包分割（默认每批 20000 字符，可调并发），LLM 返回后生成 `format: lcta-bus` 规则集存入 `fancy/` 并自动启用，回到美化页点击「立即应用美化」即可生效。

## 规则集编辑器

- 简单模式分别编辑文件 Glob、作用域、目标路径、AND 条件和类型化操作。
- 多个目标路径使用逗号分隔。
- 条件可选择“等于、属于、包含、正则”。
- 操作可选择“替换、包裹、渐变、技能颜色”。
- 高级模式直接编辑完整的 v2 JSON，并可使用“验证”和“格式化”。
- 页面内置若干不可编辑的规则集（如“技能文本美化(FL Like)”、“气泡文本渐变(FL Like)”等），可直接启用使用。
- 智能生成、模板生成、规则校验与实际应用共用同一 v2 引擎；规则预览只生成 JSON 并经校验，不会实际执行。

## 性能说明

规则会在处理文件前完成路径与正则编译。每个 JSON 使用结构化路径直接遍历，不再为每个候选字段重复扫描全部扁平路径。内容没有实际变化时不会重写文件。
