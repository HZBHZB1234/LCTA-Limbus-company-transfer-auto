# 订阅工具 Tab 重构：把「状态面板」改造成「资源站客户端」

<!-- Last updated: 2026-11-01 -->

## 0. 背景与结论

订阅工具页（原「工具箱」，2026-10-30 更名）的功能面已经对齐资源站
（mods.lcta.top）：账号登录、赛季资格、游客可见目录、签名清单驱动安装、
离线本地管理、TPM 本机授权。问题在**结构**，不在能力：

- `toolbox_status` 一次串行抓 season/access/catalog/afdian，单请求超时 20s，
  首屏最坏 60–80 秒只有一行「正在读取状态…」；
- 目录是一条密集表格，服务端早已返回的封面、简介、分类、标签、作者一个都没用；
- 本地已安装与目录之间没有版本比对，「有没有更新」只能自己去站点看；
- 注册在客户端是断头路（API 客户端有 `register`，桥接层没暴露，UI 用
  `target=_blank` 链接，在 pywebview 里不可靠）；
- 整页挂在「作弊工具箱」的风险协议下，而作弊页自身已经门控；
- 安装进度只活在模态框里，切页即丢。

本计划把页面重构成「资源站客户端」：页面骨架 + 页内子视图 + 卡片目录 +
已安装管理 + 可恢复任务坞 + 独立账号页。

## 1. 决策（已与作者确认）

1. **取消订阅页的整页作弊风险门控**，改为点击「作弊工具箱」入口时就地门控
   （作弊页 `cheat.html` + `cheat-shell.js` 自身已有门控，整页门控是重复的）。
2. **允许拆成两个 JS 文件**（`toolbox-manager.js` + `toolbox-views.js`），
   同步修改 `webui/index.html` 与 `.github/InitCode.py` 的 `js_files`。
3. **不做内嵌注册/找回密码**：需要注册或找回走 `toolbox_open_site` 用系统
   浏览器打开站点 `/register`、`/forgot-password`，登录仍在客户端内完成。
4. **目录默认排序**：推荐优先；首屏主操作按「登录 → 刷新订阅 → 安装底座」
   三态自动切换。

## 2. 与现有服务端契约的对齐（服务端是唯一事实源）

| 契约 | 现状 | 重构后 |
| --- | --- | --- |
| 目录对游客可见 | `routers/toolbox.py` 用 `get_optional_user`，逐条 `downloadable` | 先渲染游客名单，登录只解锁按钮 |
| 过期 token | `get_optional_user` 只把 401 降级为匿名，catalog 会静默返回游客视图 | 先取 access（触发刷新）再取 catalog，并在 docstring 固化顺序 |
| 换季 | `generation` 存在但客户端未用 | 以 generation 为目录缓存键 |
| 原创/转载 | `_require_download_access` 分类门槛 | 按钮与文案按 `access_kind` 区分 |
| 价格 | 服务端配置 ¥35/月、¥60/赛季 | 客户端只展示，不硬编码 |
| 资格原因 | account_inactive / email_required / season_inactive / entitlement_required / scope_not_allowed | 统一文案表 |

## 3. 目标信息架构

```
订阅工具页
├─ 顶部状态条（常驻）：账号 · 赛季 · 资格/到期 · 底座 · 游戏状态 · [主操作]
├─ 子视图：目录 | 已安装 | 账号与订阅 | 设置与诊断
├─ 目录：工具条(搜索/筛选/排序/刷新/在网站查看) + 卡片瀑布 + 详情抽屉
├─ 已安装：底座卡 + 插件/文件包统一列表(状态徽标/可更新) + 非受管区 + 批量启停
├─ 账号：登录/登出/订阅来源/爱发电/解谜(站点开放时)/注册与找回(跳站点)
└─ 设置：游戏目录(校验原因)/受管路径/全量检查/打开目录/诊断信息
底部：任务坞（安装/下载任务，切页/关窗可恢复）
```

视觉遵守 `2026-10-02-user-centered-frontend-spec.md`：一个页面一个主动作、
状态不只靠颜色、列表组织对象、抽屉组织详情、三主题与 125%/150% 缩放可用。

## 4. 桥接层契约变更（`webui/app_api/toolbox.py`）

旧方法全部保留（含 `toolbox_status`，内部改为 local+online 组合），新增：

| 方法 | 作用 | 关键约束 |
| --- | --- | --- |
| `toolbox_status_local()` | 纯本地快照（game_root/game_running/已安装/恢复） | 毫秒级、离线可用 |
| `toolbox_status_online(force=False)` | season/access/catalog/afdian + `errors{part:{code,message}}` + `fetched_at` + `generation` | 分片失败不拖垮整页 |
| `toolbox_open_site(path)` | 白名单 `{/, /login, /register, /forgot-password, /toolbox, /me}` → 系统浏览器 | **不接受任意 URL** |
| `toolbox_task_status()` | 任务坞快照（当前任务 + 最近若干条） | 进度由 `_toolbox_progress` 写入 |

`BRIDGE_PROTOCOL_VERSION` 2 → 3。错误统一为 `{success: false, code, message}`，
`message` 文案保持不变（现有测试与用户认知依赖它）。

错误码：`network_error` / `auth_required` / `email_required` /
`season_inactive` / `entitlement_required` / `scope_not_allowed` /
`no_game_root` / `game_running` / `manifest_unsigned` / `signature_invalid` /
`install_kind_unknown` / `manifest_no_files` / `manifest_bad_target` /
`in_progress` / `invalid_target` / `tpm_unavailable`。

## 5. 文件改动地图

| 文件 | 动作 |
| --- | --- |
| `webui/sections/toolbox.html` | 重写：骨架 + 稳定容器 ID；去掉整页风险覆盖层，作弊入口点击时门控 |
| `webui/js/toolbox-manager.js` | 重写：状态机 / 动作 / 任务坞 / 事件 |
| `webui/js/toolbox-views.js` | 新增：纯渲染（卡片/列表/详情/空态/错误态/骨架屏） |
| `webui/css/components.css` | 重写「订阅工具」样式段：Tab、卡片网格、徽标、任务坞、骨架屏 |
| `webui/index.html` | 新增一个 `<script>`（views 在 manager 之前） |
| `.github/InitCode.py` | `js_files` 同步新文件与顺序 |
| `webui/js/preload.js` | toolbox 初始化：离开页面停轮询 |
| `webui/app_api/toolbox.py` | 桥接层拆分与新增（见 §4） |
| `tests/test_toolbox_bridge.py` | 新增：状态拆分、open_site 白名单、任务坞、错误码 |
| `webui/assets/update.md` | 追加本版本条目 |
| `.claude/docs/key-paths.md`、`modules.md` | 同步结构变化 |

## 6. 阶段与验收

| 阶段 | 内容 | 出口条件 |
| --- | --- | --- |
| P0 | 基线测试 + 本计划落盘 | 50 项 toolbox 测试全绿 |
| P1 | 桥接层拆分/补齐 | 旧测试全绿 + 新增单测通过 |
| P2 | 页面骨架 + 样式 + 渲染层 | 三主题、缩放、窄窗正常 |
| P3 | 目录卡片/搜索/筛选/排序/详情 | 游客、锁定、需底座三态正确 |
| P4 | 已安装重做 + 更新检测 + 诊断 | 更新徽标与本地版本一致 |
| P5 | 任务坞 + 镜像站闭环 | 安装中切页再回来仍可见 |
| P6 | 文档、update.md、全量验证 | 测试全绿、文档同步 |

## 7. 非目标

- 不改服务端接口，不改签名/票据/安装引擎；
- 不做「回滚到服务器历史版本」（服务端无历史版本端点）；
- 不做非受管插件「接管」（只列出、打开目录、提示）；
- 不动 Launcher 集成开关位置（AGENTS.md：只能在 `launcher-config.html`）。

## 8. 实施记录（2026-11-01）

按 P0–P6 全部完成，提交顺序：

| 提交 | 内容 |
| --- | --- |
| `docs(toolbox)` | 本计划落盘（P0） |
| `feat(toolbox)` P1 | 桥接层：`toolbox_status_local/online` 拆分、错误码、`toolbox_open_site`、`toolbox_task_status`、`toolbox_validate_game_root`、协议版本 3；新增 17 项单测 |
| `feat(toolbox)` P2–P6 | 页面骨架与样式、`toolbox-views.js` 渲染层、`toolbox-manager.js` 状态机、卡片目录/详情抽屉、已安装更新检测与批量操作、任务坞、镜像站事件复用 |

落地时与计划的差异：

1. **未内嵌注册/找回密码**（按确认的决策 3）：账号视图只保留登录，「注册账号 /
   忘记密码」经 `toolbox_open_site` 走系统浏览器；桥接层因此没有
   `toolbox_register` / `toolbox_request_email_code`，避免留下不可达接口。
2. 新增 `toolbox_validate_game_root(path)`：设置页「检查目录」需要「只校验不落盘」，
   与保存共用 `paths.validate_game_root` 同一判定。
3. 任务坞只做**展示与恢复**，不提供中断：安装/下载本来就是不可暂停的同步任务
   （旧进度窗也只是把「取消」换成「关闭」），凭空给一个取消按钮会骗人。
4. 「已安装」行标题优先显示目录里的中文名（回退 tool_id），因为本地 manifest
   只存 id；「有新版本」筛选与状态条计数统一把底座算进去（避免两边数字不一致）。

验证：

- `pytest tests/test_toolbox_api.py tests/test_toolbox_bridge.py` —— 69 passed；
- `pytest tests/test_toolbox_html_wiring.py` —— 6 passed（静态接线：每个按钮都有
  动作、动作都有处理分支、渲染层不碰桥、关键字段转义、打包顺序与
  `index.html` 一致、整页作弊门控已移除）；
- 真实渲染：以本地 no-store 静态服务 + 注入 `pywebview` 桩在浏览器里跑通
  亮/暗主题、窄窗口（540px 重排）、游客与已登录两态、四个子视图、详情抽屉、
  搜索/筛选/排序（「有新版本」与状态条计数一致）、任务坞收起、卸载确认框、
  TPM 授权三按钮、作弊入口跳转，全程无 JS 运行时错误；
- 打包接线：`webui/index.html` 与 `.github/InitCode.py` 均新增
  `js/toolbox-views.js` 且置于 `js/toolbox-manager.js` 之前（AGENTS.md 硬规则）。

已知限制（沿用旧行为，不在本次范围）：安装/下载任务不可中断；非受管插件只
展示不接管；无「回滚到服务器历史版本」入口。

