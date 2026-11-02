# 订阅工具：版本化 + 自动更新 + 工具间依赖（2026-11-02 实施记录）

> 状态：已实施（站点 P0–P3、客户端 P4–P7），两端测试全绿。
> 关联：`site/`（LimbusAssetsUpload 子仓库）与 LCTA 主仓库、私有 `LCTA_CheatingCore`。

## 1. 背景与目标

订阅工具此前有"三个说不清"：

1. **谁更新**：判定靠 `release_id` 字符串不等 —— 而 `release_id` 是随机串，且目录是
   **按发布版本一行**的，同一工具有多个版本时页面"最后一行说了算"，会出现卡片来回跳、
   假更新、把旧版提示成可更新；
2. **多文件**：客户端用 `files[0]` 猜插件主 DLL，发布方调一次顺序就让所有客户端装错；
   插件更新也不清理旧版本残留（BepInEx 会同时加载新旧两个 DLL）；
3. **依赖**：清单里早有 `dependencies` 字段，但只有一个空壳 —— 环检测从来没生效过
   （只拿同工具 release 建图、边又混用 tool_id），客户端完全不读。

本轮目标：让"自动更新"建立在**可比较的版本**与**服务端权威的最新指针**之上，
并把依赖做成真正生效的契约；更新引擎放进**启动器流程**（游戏启动前，唯一能确定
"游戏没运行、DLL 未被占用"的窗口），不做增量更新。

## 2. 关键决策（用户确认）

| 决策 | 结论 |
| --- | --- |
| 增量更新 | **不做**。整版本替换 + 已有 sha 缓存天然复用；只保留"旧文件清理"这一正确性要求 |
| 更新触发 | **启动器管线阶段** `PHASE_TOOLBOX_UPDATE`（`PREPARE_MOD` 之后、`LAUNCH` 之前） |
| 自动范围 | 只升级**已安装**工具；**底座永不自动更新**；绝不降级 |
| 依赖自动补装 | 已装工具的**硬依赖缺失**允许自动补装（修复而非新增功能） |
| 卸载被依赖工具 | **只警告不阻止** |
| 依赖变化 | 不影响自身版本号（改依赖须发新 release，不可变性已保证） |
| 渠道（stable/beta） | **本期不做**，`is_latest` 每工具唯一 |
| LimiNex 挂载 | **移除** —— 它是订阅工具底座（Zylarnex）的旧实现；mapping 由底座自愈 |
| 底座准入 | 订阅专享（服务端 `_require_download_access` 已是双端点校验） |

## 3. 站点侧（LimbusAssetsUpload/site）

### 3.1 清单 schema_version 改为随发布行冻结（前置修正）

`build_manifest` 原先把常量 `MANIFEST_SCHEMA_VERSION` 写进清单：只要为加字段把常量
1→2，**所有存量清单的规范字节串一起变 → 全部验签失败**。改为读
`release.schema_version`（老行 1、新行 2），并加**逐字节 golden 测试**锁死。

### 3.2 版本可比较化 + 最新版指针

- 严格 semver（`1.2.3` / `1.2.3-beta.1`，拒绝 `1.0` / `v1.2.3`）；
- 落库 `version_major/minor/patch/pre/version_sort`，序串零填充 + 正式版 `~` 终结符
  （保证 `1.10.0 > 1.9.0`、`1.2.3 > 1.2.3-beta.1`）；
- 同工具内版本序**不得重复**（`version_exists`）；
- `tool_latest` 指针：`publish` 只前进、`withdraw`/删除回退、撤空即删；
- 发布默认拒绝降级（`version_not_monotonic`），`allow_downgrade=true` 才放行且审计留痕；
- `min_client_protocol`（1..99）随清单下发；
- 迁移 `0013_release_versions`：补列 + 建指针表 + 回填（不可解析 → `0000.0000.0000~`，
  展示文本不动）。

### 3.3 多文件显式入口

- `files[].role`（main/dependency/asset/config，main 唯一）；
- `descriptor.main_dll` 必须命中清单路径、与 role=main 一致、大小写归一；
- 单文件/唯一 main 自动补齐；多文件未声明保留 `files[0]` 历史兜底；
- 上传替换保留 role；移除主文件时清理悬空 `main_dll`。

### 3.4 工具间依赖（重写环检测）

- schema：`tool_id` 或 `release_id`（恰好一个）+ `min_version`（可选，仅 tool_id）+
  `optional`（默认硬依赖）；拒绝重复/自依赖/多余字段；**只校验不改写**
  （依赖进签名清单，改写就改字节串）；
- 发布门禁：依赖存在、有已发布版本、`min_version` 被满足；
- 环检测重写：release 锁定边单独查 + **工具级图**（按 `tool_latest` 取每个工具的当前
  声明）查环 —— 旧实现 `A→B→A` 永远检不出来；
- 季目录纳入：硬依赖必须同季（`dependency_not_in_season`）；转载工具硬依赖订阅专享
  工具拒绝（`dependency_kind_conflict`）；
- 目录暴露 `dependencies`（含 `min_version_sort` / `in_catalog` / `version_satisfied` /
  `access_kind`，`downloadable` 由路由按请求者资格补）与 `dependents`。

## 4. 客户端（LCTA）

### 4.1 底座生命周期（移除 LimiNex 的前提）

- `install.uninstall_runtime`：只动登记且哈希匹配的文件；安装时覆盖过的原始文件还原；
  `BepInEx/plugins` 用户插件保留；journal + 备份，失败回滚；
- `install.rollback_runtime`；`paths.assert_runtime_target`（游戏目录内、非链接、
  永不动 `LimbusCompany.exe`/`GameAssembly.dll`/`UnityPlayer.dll`）；
- 桥接 `toolbox_uninstall`/`toolbox_rollback` 接受 `""`/`"runtime"`。

### 4.2 依赖解析 `webutils/toolbox/deps.py`

- `resolve`：拓扑安装序 + 缺口分类（missing/outdated/disabled/no_entitlement/
  unknown_version/optional_missing）+ 脏数据环防御；
- `assert_ready`：安装前门禁，**写文件之前** fail-fast；
- `update_order` / `plan_updates` / `missing_installed_dependencies` / `dependents_of`；
- 版本比较只比服务端 `version_sort`，客户端不解析 semver；升级前的旧记录按"未知"上报。

### 4.3 启动器阶段 `launcher/toolbox_update.py`

- 阶段：`PHASE_TOOLBOX_UPDATE`（GUI 进度窗有独立阶段行，`launcher.work.toolbox` 默认开）；
- 前置短路：游戏目录、节流（6h）、联网、`recover_if_needed`、游戏运行中、登录态、
  赛季、资格；
- 执行：`deps.plan_updates`（协议过低的跳过）→ 先补缺失依赖 → 按拓扑序逐个
  `toolbox_install_any`；单工具失败不影响其余，失败后 1 小时内不重试；
- 报告：`<游戏目录>/.lcta-toolbox/{update-state,last-update}.json`，
  `toolbox_update_report()` 供 WebUI 展示。

### 4.4 清单门禁（协议 4）

验签后立即判：`schema_version > 2` 或 `min_client_protocol > BRIDGE_PROTOCOL_VERSION(4)`
→ `client_outdated` 拒绝安装（旧客户端遇新清单会按老逻辑装错，比装不上更糟）。

### 4.5 页面

「可更新」统一走 `ToolboxViews.hasUpdate()` + `_catalogLatest()`（只对 `is_latest` 比
`version_sort`）；目录每个工具只展示最新一行；底座卡补「回滚/卸载底座」；目录卡显示
依赖徽标（缺依赖 N / 依赖 N）；卸载弹出反向依赖警告。

## 5. LimiNex 移除（私有仓库 + 主仓库）

- 删除 `cheatcore/liminex_mount.py`（999 行）、`cheatcore/il2cpp_mapping_a4.py`、
  `tests/test_liminex_mount.py`、`webui/js/cheat.js` 的 `LiminexMountPage`、
  `webui/sections/cheat.html` 的挂载卡；registry 的 managers/配置键/`launcher_extras`
  条目清理（`launcher_extras` 保留空列表以维持宿主契约）；
- 主仓库：`detect_conflicts` 新增 `liminex_legacy` 识别（只上报不擅删）；文档三处标注
  已移除；更新说明新增 v5.1.0 段。

## 6. 兼容矩阵

| 站点 / 客户端 | 旧客户端（协议 3） | 新客户端（协议 4） |
| --- | --- | --- |
| 旧站点（无 version_sort/is_latest） | 现状 | 退化为按 `version_sort` 取最大 + release 比较，不误判 |
| 新站点 | 无感（新增字段是增量；`release_id` 语义不变） | 全功能 |

## 7. 测试

- 站点新增：`test_release_versions.py`(39)、`test_release_main_dll.py`(19)、
  `test_tool_dependencies.py`(35)，`test_tool_releases.py` 增 schema_version golden；
- 客户端新增：`test_toolbox_deps.py`(33)、`test_launcher_toolbox_update.py`(18)、
  `test_toolbox_runtime_lifecycle.py`(14)，bridge 增清单门禁 3 例，packaging 增
  「可更新判定必须走服务端版本序」回归；
- 站点全量 745 passed / 4 skipped；客户端 toolbox+launcher 451 passed。

## 8. 遗留/后续

- 站点季目录需确认已发布 `runtime_zip_root`（Zylarnex）条目，并把存量 LimiNex 用户
  引导到「接管」流程；
- `webui/assets/update.md` 的 v5.1.0 段是发布前草稿，发版时与 `__version__` 一起确认；
- 依赖渠道（stable/beta）如需分批放量，`tool_latest` 主键补一维即可。
