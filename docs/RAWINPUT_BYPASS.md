# 反 InputDetector 模拟点击检测 — 分析文档与实现方案

> 适用版本：Steam 2026-08-06 客户端（`GameAssembly.dll` 321619 函数 / `CommonLib.dll` 401 函数，MD5 `866eef070ca0fd87dd0b638962c39d3c`）
> 用途：供启动器框架集成，屏蔽游戏对模拟点击的检测

---

## 1. 总体结论（TL;DR）

| 项 | 结论 |
|---|---|
| 检测载体 | `CommonLib.dll`（原生导出库，位于 `LimbusCompany_Data/Plugins/x86_64/`） |
| 检测原理 | 全局低级键盘/鼠标钩子（`WH_KEYBOARD_LL` / `WH_MOUSE_LL`），按**注入标志位**区分"真实输入 / 合成输入"，累计计数器 |
| 判定位置 | `InputDetector$$StartAnalyze`（GameAssembly 内）：`MouseSyntheticRatio >= 0.9 且时长 > 180s` → 重置计数与计时 |
| 上报位置 | `Server.MirrorDungeonInputAnalytics`：把 real/synthetic/ratio 汇总发送到服务器 |
| 钩子点 | CommonLib 导出函数（`RawInput_Get*Synthetic*` 等）+ 两个 LL 钩子回调 |
| 推荐方案 | **方案 C（MinHook detour）**，启动时一次性 patch，不动磁盘文件 |

**核心约束**：`DllIntegrityCheck$$Check` 会对磁盘上的 CommonLib.dll 做 SHA256 校验并缓存结果，因此**绝对不要替换磁盘文件**——所有方案都是纯内存修改，磁盘哈希保持原样即可通过校验。

---

## 2. 游戏处理逻辑详解

### 2.1 CommonLib.dll 的角色

CommonLib.dll 是一个纯原生导出库（无托管层），职责：安装低级钩子、统计真实/合成输入、暴露查询 API。全部导出函数如下（**RVA = 文件偏移，运行时地址 = 模块基址 + RVA**）：

| 导出名 | RVA | 作用 |
|---|---|---|
| `RawInput_GetKeyReal` | 0x12A0 | 返回键盘真实输入计数 |
| `RawInput_GetKeySynthetic` | 0x12B0 | 返回键盘合成输入计数 |
| `RawInput_GetKeySyntheticRatio` | 0x12C0 | 返回键盘合成比例（double） |
| `RawInput_GetMouseReal` | 0x1300 | 返回鼠标真实输入计数 |
| `RawInput_GetMouseSynthetic` | 0x1310 | 返回鼠标合成输入计数 |
| `RawInput_GetMouseSyntheticRatio` | 0x1320 | 返回鼠标合成比例（double） |
| `RawInput_IsInterceptionDetected` | 0x1360 | 是否检测到 Interception 类过滤驱动 |
| `RawInput_IsProton` | 0x1380 | 是否运行在 Wine/Proton |
| `RawInput_IsRunning` | 0x13C0 | 监控线程是否在运行 |
| `RawInput_Reset` | 0x13E0 | 清零四个计数器 |
| `RawInput_Start` | 0x1410 | 安装钩子 + 注册表检测 + 起监控线程 |
| `RawInput_Stop` | 0x16E0 | 停掉监控线程 |

### 2.2 关键全局数据（RVA，模块基址 + RVA）

| 全局变量 | RVA | 含义 |
|---|---|---|
| `dword_1BA90` | 0x1BA90 | 鼠标真实计数 |
| `dword_1BA94` | 0x1BA94 | 鼠标合成计数 |
| `dword_1BA98` | 0x1BA98 | 键盘真实计数 |
| `dword_1BA9C` | 0x1BA9C | 键盘合成计数 |
| `dword_1BAA0` | 0x1BAA0 | IsRunning 标志 |
| `dword_1BAA4` | 0x1BAA4 | InterceptionDetected 标志 |
| `dword_1BAC0` | 0x1BAC0 | 游戏自身进程 PID |

### 2.3 检测判定逻辑（两个 LL 钩子回调）

**鼠标回调 `fn`（RVA 0x1200）**：
```c
if (code >= 0 && wParam == WM_LBUTTONDOWN(0x201)) {
    GetForegroundWindow -> GetWindowThreadProcessId
    if (前台进程 == 游戏 PID) {
        if (InterceptionDetected 标志 || (MSLLHOOKSTRUCT.flags & 3) != 0)   // flags 在 lParam+12
            InterlockedIncrement(&dword_1BA94);   // 鼠标合成++
        else
            InterlockedIncrement(&dword_1BA90);   // 鼠标真实++
    }
}
```
`flags & 3` = `LLMHF_INJECTED(0x1) | LLMHF_LOWER_IL_INJECTED(0x2)`——**用 `SendInput`/`mouse_event` 等模拟的点击会自动带上这两个标志位**，因此会被判为合成输入。

**键盘回调 `sub_180001150`（RVA 0x1150）**：
```c
if (code >= 0 && 前台进程 == 游戏 PID && (wParam-0x100)&~0x4 == 0) {  // WM_KEYDOWN/UP, WM_SYSKEYDOWN/UP
    if (InterceptionDetected 标志 || (KBDLLHOOKSTRUCT.flags & 0x12) != 0)  // flags 在 lParam+8
        InterlockedIncrement(&dword_1BA9C);   // 键盘合成++
    else
        InterlockedIncrement(&dword_1BA98);   // 键盘真实++
}
```
`flags & 0x12` = `LLKHF_INJECTED(0x10) | LLKHF_LOWER_IL_INJECTED(0x2)`。

**关键点**：InterceptionDetected 标志存在时，**所有输入一律记为合成**。该标志在 `RawInput_Start` 中通过注册表（`UpperFilters` 键值包含过滤驱动名、`Services\keyboard`/`Services\mouse`、`keyboard.sys`/`mouse.sys` 存在性）设置。

### 2.4 RawInput_Start 启动流程（RVA 0x1410）

1. 原子置 `IsRunning=1`（已有实例则直接返回）
2. 记录 `dword_1BAC0 = GetCurrentProcessId()`
3. 清零四个计数器
4. 查注册表检测 Interception 过滤驱动 → 置 `dword_1BAA4`
5. `CreateThread(StartAddress)` 起监控线程

**监控线程 `StartAddress`（RVA 0x1000）**：
- `SetWindowsHookExW(WH_MOUSE_LL=14, fn, ..., 0)` —— 线程级全局鼠标钩子
- `SetWindowsHookExW(WH_KEYBOARD_LL=13, sub_180001150, ..., 0)` —— 线程级全局键盘钩子
- 进入消息循环 `MsgWaitForMultipleObjects + PeekMessageW + TranslateMessage + DispatchMessageW`，直到 `IsRunning` 被清

### 2.5 GameAssembly.dll 侧消费链（IL2CPP）

游戏通过 **P/Invoke 动态加载** CommonLib（IL2CPP `il2cpp_resolve_dynamic` 风格：`LoadLibraryW("CommonLib")` + `GetProcAddress`），首次调用后把函数指针缓存在全局 qword：

| 缓存全局（GameAssembly VA） | 缓存的 CommonLib 导出 |
|---|---|
| `qword_187E5CF58` | `RawInput_Start` |
| `qword_187E5CF60` | `RawInput_Stop` |
| `qword_187E5CF68` | `RawInput_GetMouseReal` |
| `qword_187E5CF70` | `RawInput_GetMouseSynthetic` |
| `qword_187E5CF78` | `RawInput_GetMouseSyntheticRatio` |
| `qword_187E5CF80` | `RawInput_GetKeyReal` |
| `qword_187E5CF88` | `RawInput_GetKeySynthetic` |
| `qword_187E5CF90` | `RawInput_GetKeySyntheticRatio` |
| `qword_187E5CFA8` | `RawInput_IsProton` |

**重要推论**：缓存的指针就是 CommonLib 内部函数的真实入口地址。只要我们在 CommonLib 的 .text 上做 inline patch（方案 A/B/C 都是），无论游戏是否已缓存指针，任何调用路径都会先经过被 patch 的字节 —— **不存在竞态**。

**消费函数（GameAssembly VA）**：

| 函数 | 地址 | 逻辑 |
|---|---|---|
| `InputDetector$$StartDetection` | 0x180ECE260 | `isEnableCheckError` 时：记录 `_startTime`、`_active=1`、`RawInput_Reset`、调 `RawInput_Start` |
| `InputDetector$$StopDetection` | 0x180ECE340 | 置 `_active=0`、`RawInput_Reset`、调 `RawInput_Stop` |
| `InputDetector$$ResetDetection` | 0x180ECE3D0 | 重置 `_startTime` + `RawInput_Reset` |
| `InputDetector$$get_Duration` | 0x180ECDD80 | `unscaledTime - _startTime`（不活跃返回 0） |
| `InputDetector$$StartAnalyze` | 0x180ECE440 | **判定点**：`_active && Duration > 180.0f && MouseSyntheticRatio >= 0.9f && isRefresh` → 重置 `_startTime` + `RawInput_Reset` |
| `InputDetector$$get_Platform` | 0x180ECE0B0 | `RawInput_IsProton` + `DllIntegrityCheck` 拼平台标识字符串 |
| `InputDetector$$OnDestroy` | 0x180ECE250 | 调 StopDetection |
| `RawInputDetector$$get_*` / `Start/Stop/Reset` | 0x180ECDE10~0x180ECE7C0 | 均为"取缓存指针 → 调用"的薄包装 |
| `Server.MirrorDungeonInputAnalytics$$.ctor` | 0x181B82110 | 读 duration、mouseReal、mouseSynthetic、mouseSyntheticRatio、keyReal、keySynthetic、keySyntheticRatio、platform，构造上报对象 |
| `DllIntegrityCheck$$Check` | 0x180ECD430 | SHA256 校验磁盘 CommonLib.dll 文件与硬编码哈希是否一致（结果缓存于静态字段） |

### 2.6 完整数据流

```
物理输入 / 模拟输入(SendInput, LLMHF_INJECTED)
        │
        ▼
CommonLib LL 钩子 (fn / sub_180001150)
  真实→dword_1BA90/98++   合成(flags&3 或 &0x12 或 InterceptionDetected)→dword_1BA94/9C++
        │
        ▼
RawInput_Get*SyntheticRatio = synthetic / (real + synthetic)
        │
        ▼ (P/Invoke, 缓存指针)
GameAssembly: InputDetector.StartAnalyze   → ratio >= 0.9 && >180s → Reset（重测窗口）
             MirrorDungeonInputAnalytics  → 上报服务器
```

> 说明：客户端本身是"测量 + 重置"而非直接封禁，真正的风险是**服务器侧根据上报的 synthetic 比例与分布特征做风控**。因此让 synthetic 计数/比例恒为 0 是同时覆盖客户端与上报两端的做法。

---

## 3. 实现方案（A / B / C）

三个方案全部是**纯内存修改**（不碰磁盘文件），`.text` 段权限为 RX，写前需 `VirtualProtect(PAGE_EXECUTE_READWRITE)`。

**通用前提（方案 A/B 需要、C 由 MinHook 代劳）**：启动器插件注入后，轮询等待 `GetModuleHandleW(L"CommonLib.dll")` 非空（游戏在首次 P/Invoke 时才加载该库，通常出现在 `InputDetector.StartDetection` 场景加载时刻），拿到模块基址后按 RVA 计算目标地址。

### 方案 A：内存补丁导出 Getter（最简）

**原理**：直接把 4 个 Getter 的前几条指令替换为"返回 0"，游戏与上报拿到的合成计数/比例恒为 0。

**目标与补丁字节**（`模块基址 + RVA`）：

| 函数 | RVA | 原入口字节 | 替换为 | 含义 |
|---|---|---|---|---|
| `RawInput_GetKeySynthetic` | 0x12B0 | `31 C9 31 C0 F0 0F B1 0D ... C3` | `31 C0 C3` | `xor eax,eax; ret` → 返回 0 |
| `RawInput_GetMouseSynthetic` | 0x1310 | `31 C9 31 C0 F0 0F B1 0D ... C3` | `31 C0 C3` | 同上 |
| `RawInput_GetKeySyntheticRatio` | 0x12C0 | `31 D2 31 C0 F0 0F B1 0D ...` | `0F 57 C0 C3` | `xorps xmm0,xmm0; ret` → 返回 0.0 |
| `RawInput_GetMouseSyntheticRatio` | 0x1320 | `31 D2 31 C0 F0 0F B1 0D ...` | `0F 57 C0 C3` | 同上 |
| `RawInput_IsInterceptionDetected`（可选加固） | 0x1360 | `31 C9 31 C0 F0 0F B1 0D ...` | `31 C0 C3` | 返回 0 |

> 注意：Patch 用 `xor eax,eax; ret` 需要覆盖原函数至少 3 字节（合成 Getter 原长 13 字节，`retn` 在第 12 字节，安全）；Ratio 函数原长约 46 字节，`xorps xmm0,xmm0; ret` 4 字节足够。返回类型为 `double`（xmm0）与 `int32`（eax）与调用方 C ABI 一致。

**C 实现（启动器插件内）**：
```c
static uint8_t* resolve_rva(HMODULE mod, size_t rva) { return (uint8_t*)mod + rva; }

static bool patch_write(void* dst, const void* src, size_t n) {
    DWORD old;
    if (!VirtualProtect(dst, n, PAGE_EXECUTE_READWRITE, &old)) return false;
    memcpy(dst, src, n);
    VirtualProtect(dst, n, old, &old);
    FlushInstructionCache(GetCurrentProcess(), dst, n);
    return true;
}

void install_scheme_a(HMODULE commonlib) {
    const uint8_t ret0[]   = { 0x31, 0xC0, 0xC3 };        // xor eax,eax; ret
    const uint8_t ret0d[]  = { 0x0F, 0x57, 0xC0, 0xC3 };  // xorps xmm0,xmm0; ret
    patch_write(resolve_rva(commonlib, 0x12B0), ret0,  sizeof(ret0));  // KeySynthetic
    patch_write(resolve_rva(commonlib, 0x1310), ret0,  sizeof(ret0));  // MouseSynthetic
    patch_write(resolve_rva(commonlib, 0x12C0), ret0d, sizeof(ret0d)); // KeySyntheticRatio
    patch_write(resolve_rva(commonlib, 0x1320), ret0d, sizeof(ret0d)); // MouseSyntheticRatio
    patch_write(resolve_rva(commonlib, 0x1360), ret0,  sizeof(ret0));  // IsInterceptionDetected
}
```

**优点**：实现最小、无需第三方库、天然覆盖已缓存指针。
**缺点**：字节级硬编码，CommonLib 更新后 RVA 可能变化；理论上是"说谎型"（内部计数器仍涨，仅出口被掩盖）。

### 方案 B：补丁两个 LL 钩子回调（源头记账）

**原理**：不改 Getter，改**计数源头**——让 LL 钩子回调里的"合成分支"永远不执行，所有输入都累加到真实计数器。这样不仅 Getter 返回 0，内部计数语义也完全"真实"，Interception 驱动在场时同样生效。

**目标与补丁**（`模块基址 + RVA`）：

鼠标回调 `fn`（RVA 0x1200），判定代码：
```
0x180001256  lock cmpxchg [dword_1BAA4], ebp   ; 读 InterceptionDetected
0x18000125E  jnz loc_18000126F                 ; 非0 → 跳合成分支
0x180001260  test byte [rdi+0Ch], 3            ; 测试 LLMHF_INJECTED|LOWER_IL
0x180001264  jnz loc_18000126F                 ; 注入 → 跳合成分支
0x180001266  lock inc [dword_1BA90]            ; 真实++
0x18000126F  lock inc [dword_1BA94]            ; 合成++  (loc_18000126F)
```
→ 将 `0x18000125E` 与 `0x180001264` 两处 `jnz`（`75 xx`，2 字节）改为 `90 90`（NOP），或改为无条件跳到 0x180001266 的 `EB 06`。

键盘回调 `sub_180001150`（RVA 0x1150），判定代码：
```
0x1800011AC  lock cmpxchg [dword_1BAA4], ebp
0x1800011B4  jnz loc_1800011C5                 ; → 合成分支
0x1800011B6  test byte [rbx+8], 12h            ; LLKHF_INJECTED|LOWER_IL
0x1800011BA  jnz loc_1800011C5
0x1800011BC  lock inc [dword_1BA98]            ; 真实++
0x1800011C5  lock inc [dword_1BA9C]            ; 合成++  (loc_1800011C5)
```
→ 同样把 `0x1800011B4` 与 `0x1800011BA` 两处 `jnz` NOP 掉。

**C 实现**：
```c
void install_scheme_b(HMODULE commonlib) {
    const uint8_t nop2[] = { 0x90, 0x90 };
    patch_write(resolve_rva(commonlib, 0x125E), nop2, 2);  // fn: jnz -> nop
    patch_write(resolve_rva(commonlib, 0x1264), nop2, 2);
    patch_write(resolve_rva(commonlib, 0x11B4), nop2, 2);  // keyboard: jnz -> nop
    patch_write(resolve_rva(commonlib, 0x11BA), nop2, 2);
}
```

**优点**：计数源头归真，即使未来有"直接读计数器内存"的路径也安全；对 Interception 场景天然免疫。
**缺点**：patch 点分散在回调内部，升级适配要同时维护 4 处偏移；需要先确认回调位于函数中间（非入口），不适合 MinHook。

### 方案 C：MinHook detour（推荐，用于已有加载器框架）

**原理**：在 CommonLib 导出函数**入口**做 5 字节跳板 detour（MinHook 负责保存原指令并生成 trampoline），用自定义包装函数接管 4 个 Getter + `IsInterceptionDetected`，其余导出（`GetMouseReal`/`GetKeyReal`/`Start`/`Stop`/`Reset`）保持原样。工程化、升级友好，且因为 hook 的是函数入口，游戏缓存的指针同样命中。

**需要做的**：把 `MinHook.h` + `minhook.lib`（x64 版）加入启动器插件工程；确认加载器线程上下文（BepInEx 插件在 `Awake()` 里做即可，此时 CommonLib 可能尚未加载，用轮询等待）。

**C 实现**：
```c
#include <MinHook.h>

typedef __int64 (*GetCountFn)();
typedef double  (*GetRatioFn)();
typedef int     (*GetBoolFn)();

static GetCountFn orig_GetKeySynthetic, orig_GetMouseSynthetic;
static GetRatioFn orig_GetKeySyntheticRatio, orig_GetMouseSyntheticRatio;
static GetBoolFn  orig_IsInterceptionDetected;

// 包装函数：合成系一律返回 0
static __int64 hk_GetKeySynthetic()        { return 0; }
static __int64 hk_GetMouseSynthetic()      { return 0; }
static double  hk_GetKeySyntheticRatio()   { return 0.0; }
static double  hk_GetMouseSyntheticRatio() { return 0.0; }
static int     hk_IsInterceptionDetected() { return 0; }

static void* resolve_export(HMODULE mod, const char* name) {
    return (void*)GetProcAddress(mod, name);
}

void install_scheme_c(HMODULE commonlib) {
    MH_Initialize();
    MH_CreateHook(resolve_export(commonlib, "RawInput_GetKeySynthetic"),
                  &hk_GetKeySynthetic, (LPVOID*)&orig_GetKeySynthetic);
    MH_CreateHook(resolve_export(commonlib, "RawInput_GetMouseSynthetic"),
                  &hk_GetMouseSynthetic, (LPVOID*)&orig_GetMouseSynthetic);
    MH_CreateHook(resolve_export(commonlib, "RawInput_GetKeySyntheticRatio"),
                  &hk_GetKeySyntheticRatio, (LPVOID*)&orig_GetKeySyntheticRatio);
    MH_CreateHook(resolve_export(commonlib, "RawInput_GetMouseSyntheticRatio"),
                  &hk_GetMouseSyntheticRatio, (LPVOID*)&orig_GetMouseSyntheticRatio);
    MH_CreateHook(resolve_export(commonlib, "RawInput_IsInterceptionDetected"),
                  &hk_IsInterceptionDetected, (LPVOID*)&orig_IsInterceptionDetected);
    MH_EnableHook(MH_ALL_HOOKS);
}
```

**启动器框架集成流程**（BepInEx 插件或自研 loader 通用）：
1. 插件 `Awake()`（或注入线程）启动一个后台线程：
```c
DWORD WINAPI waiter(LPVOID) {
    HMODULE cl = NULL;
    for (int i = 0; i < 400 && !cl; i++) {   // 最多等 ~20s
        cl = GetModuleHandleW(L"CommonLib.dll");
        if (!cl) Sleep(50);
    }
    if (cl) install_scheme_c(cl);
    return 0;
}
```
2. 安装完成后退出线程；此后游戏首次 `RawInput_Start` 起钩子时，所有 Getter 已被 detour。

**优点**：不依赖指令硬编码（按导出名解析）、可后续加日志/动态开关、框架兼容性好。
**缺点**：需要引入 MinHook 依赖；若框架是纯托管（C#/BepInEx），需内嵌 x64 native 助手 DLL 或改用 DllImport 导出的 native 库。

---

## 4. 验证方法

1. **静态验证**：确认 `CommonLib.dll` 磁盘哈希不变（`Get-FileHash` 对比原始值），且 `DllIntegrityCheck` 仍返回 true（平台字符串无异常后缀）。
2. **运行时验证**：对 `RawInput_GetMouseSyntheticRatio` 下断点/CE 观测，模拟点击后返回值恒 0；`GetMouseReal` 在真实点击时增长。
3. **行为验证**：自动点击跑一段（>180s）后，`InputDetector$$StartAnalyze` 的 reset 分支（`0x180ECE440` 中 `>= 0.9` 判断）不再命中；`MirrorDungeonInputAnalytics` 上报字段 `mouseSyntheticRatio=0`。
4. **回归**：真实手动点击仍然走 real 计数、游戏行为无变化；`RawInput_IsRunning` 正常为 1（证明钩子线程活着，未破坏监控）。

## 5. 风险与升级适配

- **版本适配**：RVA 基于 2026-08-06 样本。升级后用 IDA 重新定位：导出函数可用 `dumpbin /exports CommonLib.dll` 或 IDA Exports 窗口核对；方案 B 的 4 处偏移建议用特征码（`lock cmpxchg cs:...; jnz; test byte ...`）而非硬编码。
- **磁盘哈希**：任何方案都不得替换/修改磁盘上的 CommonLib.dll，否则 `DllIntegrityCheck` 置为无效，`get_Platform` 与上报会携带异常标识。
- **服务器侧**：本项目只保证客户端计数为 0；若服务器对"零合成+高频率点击"的时间序列另有风控模型，需配合控制点击节奏（如随机间隔、抖动、人工波动）规避。
- **MinHook 卸载**：若游戏热重载 CommonLib（当前未见），需在 `RawInput_Stop` 场景下重新安装；一般启动器场景无需处理。
