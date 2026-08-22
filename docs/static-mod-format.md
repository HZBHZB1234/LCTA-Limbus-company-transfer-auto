# static-mod 格式规范（LCTA 静态数据 Mod）

> 版本：v1（2026-08-22）
> 适用范围：`Limbus Company` 静态数据（static bundle 内 TextAsset JSON：人格/技能/敌人/关卡/抽卡等数值表）
> 逆向依据：`LimbusDecompile/LimbusCompany_StaticData_加载与脚本机制分析报告.md` §9.5（CRC 校验对象 = bundle 解压后块数据拼接的 zlib CRC32）

## 一、为什么需要独立格式

static bundle（`static_s1_0_assets_all_<hash>.bundle`）是全表唯一开启
`UseCrcForCachedBundles=true` 的条目：

- **缓存命中加载时**引擎对「bundle 解压后块数据拼接」计算 zlib CRC32 并与 catalog
  记录比对，失配则判定损坏 → 清除缓存重下；
- 因此 static 数据 Mod **不能**像普通 bundle（carra2）那样只替换缓存 `__data`，
  必须：改包 → 算解压后 CRC → **双写 catalog（crc/size）** + 重建缓存条目。

`.staticmod` 是为此设计的专用格式：以 zip 容器携带「对官方数据的修改意图」，
由 Launcher 在启动时施加到**当前官方版本**上并完成双写。

## 二、文件形态

```
<name>.staticmod          # zip 容器（无 .zip 后缀）
├── manifest.json         # 必填
├── patches/              # 补丁数据（jsonpatch 或 pathset）
│   ├── skill.json
│   └── personality.json
└── full/                 # 可选：整文件（首次加载 diff 成补丁）
    └── enemy/enemy-101.json
```

- 放置于模组目录（默认 `%APPDATA%/LimbusCompanyMods`）；
- 停用：改名 `<name>.staticmod_disable`（与现有 carra2/bank 的 `_disable` 语义一致）；
- 模组目录无 `.staticmod` 时，Launcher 跳过 apply_staticmods 管线（零开销）。

## 三、manifest.json

```json
{
  "format": "staticmod/v1",
  "name": "example-static-tweak",
  "version": "1.0.0",
  "description": "示例：把 Yi Sang 组 S1 目标数改 5",
  "patches": [
    {
      "dataClass": "skill",
      "file": "personality-skill-01",
      "opType": "jsonpatch",
      "source": "patches/skill.json"
    }
  ],
  "fullFiles": [
    {
      "dataClass": "enemy",
      "file": "enemy-101",
      "source": "full/enemy/enemy-101.json"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `format` | string | 固定 `staticmod/v1` |
| `patches[]` | 数组 | 每个补丁：`dataClass`+`file` 定位 TextAsset，`opType` 二选一，`source` 包内路径 |
| `fullFiles[]` | 数组 | 整文件替换：`dataClass`+`file`+`source` |

**定位键**：`dataClass`+`file` 对应 static-data-info 清单中的 dataClass 与
fileList 文件名（如 `skill` / `personality-skill-01`），跨版本稳定；
运行时按 **TextAsset.m_Name** 匹配（不依赖 path_id）。

## 四、补丁语义

### 4.1 jsonpatch（RFC 6902）

`patches/*.json` 为操作数组：

```json
[
  { "op": "replace", "path": "/list/0/skillData/0/targetNum", "value": 5 }
]
```

### 4.2 pathset（路径-值覆盖）

`patches/*.json` 为「路径 → 新值」对象（与 mod_config.json 风格一致，编辑器友好）：

```json
{
  "list[0].skillData[0].targetNum": 5,
  "list[1].skillData[0].mpUsage": 2
}
```

路径语法：`字段[下标].字段[下标].字段`，如 `list[0].skillData[0].targetNum`。
实现为 jsonpatch 生成器（下标 → `/0` 指针）。

### 4.3 full（整文件替换）

`full/<dc>/<file>.json` 为**期望的完整 JSON 内容**。加载时：
1. 读官方该文件 → 与 mod 内容做 JSON diff → 生成 jsonpatch；
2. 缓存 diff（`mod-cache/static-full-diff/`）；
3. 以补丁形式应用（跨版本自适应：官方改无关字段不影响，改目标字段冲突时明确报错）。

## 五、跨版本兼容（核心设计）

官方热修/发版会**轮换 static bundle 的 content hash** 并重写 catalog 记录
（2026-08-22 实测：`a83465d0…` → `972e5bc3…`，catalog 同步更新）。
`.staticmod` 不绑定任何具体 hash/偏移，每次应用**动态解析当前 catalog**：

```
搜 'static_s1_0_assets_all_<32hex>.bundle'  → 取尾段 content hash
→ 找该 16B Hash128 记录 → 校验其后外层键（跨版本稳定，如 64bd0105…）
→ crc @ Hash128+0x44、size @ Hash128+0x48（LE32）→ 双写
```

- **补丁按 dataClass/file 定位**，官方改无关字段 → 补丁照常生效；
- 官方改目标字段 → jsonpatch 报冲突 → **明确报错提示 mod 需更新**（不会静默加载错误数值）；
- 定位失败 → 记录错误并跳过，**确保游戏正常启动**。

## 六、加载管线（Launcher）

`game_launch.py prepare_mod` 在 `patch_assets` 之后、`replace_sound` 之前：

```
patch.patch_assets(...)          # 现有 bundle 级 mod
staticmod.apply_staticmods(...)  # 无 .staticmod 直接返回
sound.replace_sound(...)
```

`apply_staticmods` 流程：
1. 收集启用 `.staticmod`（`_disable` 过滤）；
2. 动态定位当前 catalog 中 static 条目；
3. 取现行官方 bundle（缓存 `__data` 或 CDN 补拉）；
4. 解包 → 按 m_Name 匹配 TextAsset → 应用补丁（jsonpatch/pathset/full→diff）→ 重打包（lz4）；
5. 算解压后块数据 CRC32 + 新文件大小；
6. **双写**：catalog 记录区 crc/size（LE32）+ 缓存条目 `<outer>/<inner>/{__data,__info}`
   （LocalLow 与 D:\Unity 双写）。

退出恢复：`restore_staticmods()` 移除补丁缓存条目，让游戏下次重下官方版。

## 七、构建 / 校验工具

```bash
# 打包
python tools/staticmod_build.py build out.staticmod --name demo --version 1.0.0 \
    --description "..." \
    --patch skill:personality-skill-01:patches/skill.json:pathset \
    --full enemy:enemy-101:full/enemy-101.json

# 校验 / 预览
python tools/staticmod_build.py check out.staticmod
python tools/staticmod_build.py info out.staticmod
```

## 八、编辑器（作弊工具箱 → 静态数据编辑器）

入口：WebUI「作弊工具箱」页 → 静态数据编辑器卡片（解锁后可用）。

功能：
- **数据源检测**：自动定位当前 static bundle（catalog 动态解析）；
- **浏览/搜索/筛选**：dataClass 下拉筛选 + 文件名/内容关键字搜索；
- **字段编辑**：路径（`list[0].skillData[0].targetNum`）+ 新值 → 实时 pathset；
- **差异预览**：官方 vs 修改后的行级 diff；
- **导出**：生成 `.staticmod`（默认桌面，可在 Launcher 配置改导出目录）。

## 九、风险声明

- 静态数据为纯客户端定义，修改仅影响本地计算；账号资产（拥有/等级/货币）为
  服务器权威，本格式不涉及也不应被用于伪造资产；
- 涉及在线对战的数值修改存在违反用户协议风险，仅供学习/单机/离线研究；
- 官方每次发版会轮换 bundle hash，文件级修改随之需要重新应用（本格式自动适配，
  但补丁冲突时需更新 mod）。
