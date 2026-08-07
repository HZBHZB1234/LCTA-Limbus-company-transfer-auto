# 伤害倍率 Hook — 分析文档与实现方案

> 参考逆向结论：`E:\desktop\work\LimbusDecompile\docs\MINHOOK_GUIDE.md`（08-06 Steam 客户端，IDA 反编译交叉验证）
> 用途：LCTA 启动器集成"MinHook 原生伤害倍率 detour"，替代 BepInEx 插件 DamageTimes10

---

## 1. 总体结论（TL;DR）

| 项 | 结论 |
|---|---|
| Hook 目标 | `GameAssembly.dll` 内 `BattleUnitModel$$GetTakeAttackDmgMultiplier`（基类实现） |
| 辅助调用 | `BattleUnitModel$$GetOpponentFaction`（不 detour，直接 call，判断目标阵营） |
| 效果 | 受伤方是**敌人**时，返回值 × multiplier（默认 3.0）；`before==0`（"无修正"）时直接置为 multiplier；玩家单位不受影响 |
| 为什么只 hook 基类 | `BattleUnitModel_Enemy/Abnormality/Part/Assistant` 四个子类覆写版本全部直接 call 基类实现，单点 detour 全覆盖 |
| 偏移来源 | **远程 JSON API**（默认 `https://web.lcta.top/damage_hook.json`，可用配置覆盖）——用户无需自行逆向 |
| 缓存 | 本地 `%LOCALAPPDATA%/LCTA/damage-hook/`，按 GameAssembly.dll SHA-256 版本锚定 |
| 自动失效 | 游戏更新 → 本地哈希 ≠ 缓存哈希 → 自动重拉 API；运行中更新 → DLL prologue 自检失败 → 自动重拉并热重装 |
| 加载方式 | `webutils/function_damage_hook.py` 注入 `hooks/damage_hook.dll`（CreateRemoteThread + LoadLibraryW），与输入反检测同链路 |

---

## 2. 架构分工

```
┌───────────────────────────────────────────────────────┐
│ Python 端 (webutils/function_damage_hook.py)           │
│  resolve_offsets():                                    │
│    - 本地 GameAssembly.dll SHA-256（mtime/size 元缓存） │
│    - 缓存命中（哈希一致）→ 直接用，不发网络请求         │
│    - 失效（哈希变化）→ 拉 API → 校验 → 写缓存           │
│      · API 无新版 → 保留旧缓存 + stale 降级注入          │
│  apply(): 写共享内存 LCTA_DamageHook_Config (196B)     │
│  inject()/eject()/get_status()/refresh_offsets()       │
└───────────────┬───────────────────────────────────────┘
                │ LoadLibraryW（远程线程）
┌───────────────▼───────────────────────────────────────┐
│ C 端 (hooks/damage_hook.c + vendor/minhook)            │
│  watcher 线程：等 GameAssembly.dll → VerifyPrologue    │
│  → MH_CreateHook/EnableHook → detour 伤害倍率          │
│  retry_requested=1 → 摘除旧钩 → 按新偏移重装            │
│  状态回写：gameassembly_found/verified/installed/      │
│           last_error/log_count/last_log                │
└───────────────────────────────────────────────────────┘
```

共享内存 `DH_CONFIG` 结构（C/Python ctypes 一一对应，196 字节）：`magic("DHGD") | enabled | log | retry_requested | multiplier(float) | rva_take_attack | rva_opponent_faction | prologue[16] | gameassembly_found | verified | installed | last_error | log_count | last_log[128] | pad`

---

## 3. API 端点与数据格式

默认端点：`https://web.lcta.top/damage_hook.json`（可用 `launcher.work.damage_hook_api` 覆盖，任意返回同格式 JSON 的地址均可）。

```json
{
  "damage_hook": {
    "game_version": "2026-08-06",
    "gameassembly_sha256": "E580119AB44BC1FA3C0CA0B60102BFEA6574D4F162F2B9E64067047DB8CE5A7B",
    "gameassembly_size": 139846144,
    "rva_get_take_attack_dmg_multiplier": 17105360,
    "rva_get_opponent_faction": 16982112,
    "prologue": "48 8B C4 53 55 56 57 41 54 41 55 41 56 41 57 48"
  }
}
```

字段说明：
- `gameassembly_sha256` — 版本锚定（本地文件哈希必须一致才使用/缓存该条目）
- `gameassembly_size` — 校验辅助（可选）
- `rva_*` — 十进制 RVA（= VA − 0x180000000）
- `prologue` — 目标函数前 16 字节 hex（运行时自检，防止偏移错位）
- 仓库内 `damage_hook.json` 为当前版本样例（游戏更新后由维护者更新并部署到 web.lcta.top）

---

## 4. 缓存与自动失效机制

### 4.1 缓存文件

| 文件 | 内容 |
|---|---|
| `offsets-cache.json` | `{local_sha256, local_size, offsets}` —— 只写与本地哈希一致的 API 数据 |
| `local-meta.json` | `{path, size, mtime, sha256}` —— 140MB 文件哈希的增量重算缓存（mtime/size 未变不重算） |

### 4.2 失效路径（双保险）

1. **启动前失效**：本地 GameAssembly.dll 哈希 ≠ 缓存哈希（游戏已更新）→ 自动拉 API。API 已发布新版 → 更新缓存，正常注入；API 未发布（payload 哈希 ≠ 本地哈希）→ **保留旧缓存，降级注入并标记 stale**（可能不生效，页面/日志提示）；网络失败 → 有旧缓存则降级，无缓存则跳过注入。
2. **运行中失效**：游戏热更新 → DLL 内 `VerifyPrologue` 失败 → 回写 `verified=0, last_error=3` → Python 侧检测后 `refresh_offsets()`（force 拉取）→ 重写共享内存并置 `retry_requested=1` → DLL 摘除旧钩并按新偏移重装，进程无需重启。

---

## 5. 配置项

`launcher.work.damage_hook`（bool，Launcher 启动时自动注入）/ `damage_hook_multiplier`（str，默认 "3.0"，钳制 [0.1, 1000]）/ `damage_hook_log`（bool，伤害日志）/ `damage_hook_api`（str，偏移 API 地址）；`damage_hook.disclaimer_accepted`（风险须知同意持久化，RiskGate 统一管理）。

---

## 6. 构建与部署

```bat
powershell -ExecutionPolicy Bypass -File hooks\build.ps1   :: 独立编译 hooks/*.dll
.\build.ps1                                               :: 完整构建（含 damage_hook.dll 缓存编译与 dist 复制）
```

- 依赖：`vendor/minhook/`（v1.3.4 源码，MIT 许可，已内置仓库）
- gcc 编译：`gcc -shared -O2 -s -static-libgcc -o damage_hook.dll hooks/damage_hook.c vendor/minhook/src/{hook,buffer,trampoline}.c vendor/minhook/src/hde/hde64.c -I vendor/minhook/include -I vendor/minhook/src/hde`
- CI（`.github/workflows/release.yml`）与 `build.ps1` 编译命令保持一致（项目规则）；CI 中仓库检出在 `LCTA/` 子目录，路径需带 `LCTA/` 前缀

### 版本更新流程（游戏升级后维护者必做）

1. 新版本 GameAssembly.dll 落地 → 计算 SHA-256 与 `prologue` 前 16 字节
2. 在新 IDB 中按名称查 `BattleUnitModel$$GetTakeAttackDmgMultiplier` / `GetOpponentFaction` 地址（流程见 MINHOOK_GUIDE.md §7）
3. 更新 `damage_hook.json`（仓库内样例）并部署到 `https://web.lcta.top/damage_hook.json`
4. 用户侧完全自动：缓存失效 → 重拉 → 重装

---

## 7. 验证清单

| # | 步骤 | 预期 |
|---|---|---|
| 1 | Launcher 勾选「启用伤害倍率」启动游戏 | 日志出现 `伤害倍率 hook 已注入 (PID: ...)` |
| 2 | WebUI 伤害倍率页状态 | detour 状态 `● 已安装`；偏移来源 缓存/API |
| 3 | 进入战斗 | 敌人受到伤害 ≈ 原值 × 倍率；我方不受影响 |
| 4 | 勾选日志并战斗 | 页面"最近日志"出现 `target=... crit=... mul X -> X` |
| 5 | 游戏更新后 | 状态显示偏移过期 → 自动重拉；或手动点「立即刷新偏移」 |

## 8. 反作弊注意事项

- 只做**内存 detour**，不碰磁盘文件（GameAssembly.dll / CommonLib.dll 一律不动）
- `DllIntegrityCheck$$Check` 只校验磁盘 CommonLib.dll，对 GameAssembly 内存 detour 不触发（详见 MINHOOK_GUIDE.md §9 / docs/ANTICHEAT.md）
- 修改伤害数值属于作弊类功能，使用前必须阅读风险须知（RiskGate 强制门控）
