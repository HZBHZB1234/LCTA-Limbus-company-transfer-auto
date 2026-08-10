/* rawinput_hook.c
 *
 * LCTA 输入反检测 Hook DLL (x64, MinGW-w64)
 *
 * 原理：CommonLib 维护 4 个计数（鼠标/键盘 × 真实/合成），以及两个合成比例
 * getter 和一个拦截检测 getter，供本地化框架生成游戏上报数据。
 *
 * 本 DLL 注入游戏进程后，轮询共享内存配置（由 launcher / webutils 写入），
 * 当 armed=1 时对 CommonLib 的 7 个导出做 14 字节绝对跳转 detour：
 *
 *   auto 模式（mode=0，推荐，仅处理"虚拟点击"问题）：
 *     - 合成计数/比例 getter 一律返回 0（宏产生的虚拟点击全部清零）
 *     - 真实计数 getter 不修改，保持 CommonLib 自身统计（所见即真实）
 *
 *   manual 模式（mode=1，覆盖 PostMessage 类宏产生的"双零"数据）：
 *     - 真实/合成计数 getter 返回共享配置中的自定义值（包含真实计数）
 *     - 合成比例 getter 由计数自动计算：synth / (real + synth)（钳制 < 0.9），
 *       不再由外部指定比例
 *     - volatility>0 时按百分比抖动计数（周期性快照，同一窗口内各 getter 一致），
 *       再据此计算比例，避免恒定数值被检测
 *     - IsInterceptionDetected 一律返回 0
 *
 * 安装时机：真实 getter 在 auto 模式下必须保持未 detour（无 trampoline，
 * detour 后无法取回真实值），因此 watcher 会按模式动态安装/回滚真实 getter。
 */

#include <windows.h>
#include <psapi.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

#define RH_MAGIC        0x52484447u          /* "RHGD" */
#define RH_MAP_NAME     L"Local\\LCTA_RawInputHook_Config"
#define RH_POLL_MS      300
#define RH_JITTER_MS    1000                 /* 抖动快照窗口（毫秒） */
#define RH_RATIO_MAX    0.9                  /* 比例上限，与 Python 端 RATIO_MAX 一致 */
#define RH_RATIO_CLAMP  (RH_RATIO_MAX - 0.01) /* 钳制目标：严格小于 RH_RATIO_MAX，与 Python 端 RATIO_CLAMP 一致 */
#define HOP_SIZE        14                   /* mov rax,imm64; jmp rax; nop; nop */

/* 与 webutils/function_input_bypass.py 中 RHConfig（ctypes）保持字段一一对应，
 * 自然对齐（不做 #pragma pack(1)，ctypes 默认对齐与之保持一致），共 80 字节。 */
typedef struct _RH_CONFIG {
    volatile LONG        magic;
    volatile LONG        mode;               /* 0=auto 1=manual */
    volatile LONG        armed;              /* 0/1 */
    volatile LONG        volatility;         /* 手动模式计数抖动百分比 0-50，0=关闭 */
    volatile LONGLONG    mouse_real;
    volatile LONGLONG    key_real;
    volatile LONGLONG    mouse_synth;
    volatile LONGLONG    key_synth;
    volatile double      mouse_ratio;        /* 手动模式自动计算：synth/(real+synth) */
    volatile double      key_ratio;
    volatile LONG        commonlib_found;    /* watcher 是否找到 CommonLib */
    volatile LONG        installed;          /* 5 个核心 detour 是否已安装 */
    volatile LONG        installed_real;     /* 2 个真实计数 detour 是否已安装 */
    LONG                 _pad2;
} RH_CONFIG;

static RH_CONFIG *g_cfg = NULL;
static HANDLE    g_stop_event = NULL;
static HANDLE    g_watcher = NULL;

/* ------------------------------------------------------------------ */
/* 抖动（volatility）：手动模式下按百分比随机化计数，防止恒定值被检测  */
/* ------------------------------------------------------------------ */

static unsigned long long g_rng_state = 0x9E3779B97F4A7C15ull;

static unsigned long long rng_next(void)
{
    /* xorshift64*：轻量、无外部依赖，供抖动取随机数用 */
    unsigned long long x = g_rng_state;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    g_rng_state = x;
    return x * 0x2545F4914F6CDD1Dull;
}

/* 抖动快照：同一时间窗口内所有 getter 返回一致的计数（含比例），
 * 避免同帧内 real/synth/ratio 互相矛盾导致被检测。 */
#define JITTER_SLOTS 4   /* mouse_real, key_real, mouse_synth, key_synth */

static LONGLONG g_jittered[JITTER_SLOTS];
static DWORD    g_jitter_ts = 0;
static LONG     g_jitter_vol = -1;   /* 上次快照使用的波动值，volatility 变化时强制刷新 */

static void refresh_jitter_snapshot(void)
{
    DWORD now = GetTickCount();
    LONG vol = g_cfg ? g_cfg->volatility : 0;
    LONG i;

    if (vol <= 0) {
        g_jitter_vol = 0;
        for (i = 0; i < JITTER_SLOTS; i++) g_jittered[i] = 0;
        return;
    }
    if (g_jitter_vol == vol && now - g_jitter_ts < RH_JITTER_MS)
        return;

    g_jitter_vol = vol;
    g_jitter_ts = now;
    {
        /* 从配置读取原始计数（volatile read） */
        static LONGLONG base[JITTER_SLOTS];
        base[0] = g_cfg->mouse_real;
        base[1] = g_cfg->key_real;
        base[2] = g_cfg->mouse_synth;
        base[3] = g_cfg->key_synth;

        for (i = 0; i < JITTER_SLOTS; i++) {
            LONGLONG v = base[i];
            /* ±vol% 范围内均匀抖动，百分比越小每次变化幅度越小 */
            if (v != 0) {
                double d = (double)(rng_next() & 0xFFFF) / 65535.0;   /* [0,1] */
                double factor = 1.0 + (d * 2.0 - 1.0) * (double)vol / 100.0;
                double r = (double)v * factor;
                if (r < 0.0) r = 0.0;
                v = (LONGLONG)(r + 0.5);
                if (v == 0) v = 1;          /* 保证非零计数不为 0 */
            }
            g_jittered[i] = v;
        }
    }
}

/* ------------------------------------------------------------------ */
/* Hook stub：从共享配置取值并返回                                     */
/* ------------------------------------------------------------------ */

__declspec(noinline) static LONGLONG hk_mouse_synth(void)
{
    if (g_cfg && g_cfg->mode == 1) {
        refresh_jitter_snapshot();
        return (g_jitter_vol > 0) ? g_jittered[2] : g_cfg->mouse_synth;
    }
    return 0;
}

__declspec(noinline) static LONGLONG hk_key_synth(void)
{
    if (g_cfg && g_cfg->mode == 1) {
        refresh_jitter_snapshot();
        return (g_jitter_vol > 0) ? g_jittered[3] : g_cfg->key_synth;
    }
    return 0;
}

__declspec(noinline) static double hk_mouse_ratio(void)
{
    LONGLONG real, synth;
    double ratio;

    if (g_cfg && g_cfg->mode == 1) {
        refresh_jitter_snapshot();
        if (g_jitter_vol > 0) {
            real  = g_jittered[0];
            synth = g_jittered[2];
        } else {
            real  = g_cfg->mouse_real;
            synth = g_cfg->mouse_synth;
        }
        if (real + synth <= 0) return 0.0;
        ratio = (double)synth / (double)(real + synth);
        if (ratio >= RH_RATIO_MAX) ratio = RH_RATIO_CLAMP;
        return ratio;
    }
    return 0.0;
}

__declspec(noinline) static double hk_key_ratio(void)
{
    LONGLONG real, synth;
    double ratio;

    if (g_cfg && g_cfg->mode == 1) {
        refresh_jitter_snapshot();
        if (g_jitter_vol > 0) {
            real  = g_jittered[1];
            synth = g_jittered[3];
        } else {
            real  = g_cfg->key_real;
            synth = g_cfg->key_synth;
        }
        if (real + synth <= 0) return 0.0;
        ratio = (double)synth / (double)(real + synth);
        if (ratio >= RH_RATIO_MAX) ratio = RH_RATIO_CLAMP;
        return ratio;
    }
    return 0.0;
}

__declspec(noinline) static LONG hk_interception(void)
{
    return 0;
}

/* 仅在 manual 模式下安装；auto 模式下保持原始函数，返回自然真实计数。 */
__declspec(noinline) static LONGLONG hk_mouse_real(void)
{
    if (g_cfg && g_cfg->mode == 1) {
        refresh_jitter_snapshot();
        if (g_jitter_vol > 0) return g_jittered[0];
        return g_cfg->mouse_real;
    }
    return 0;
}

__declspec(noinline) static LONGLONG hk_key_real(void)
{
    if (g_cfg && g_cfg->mode == 1) {
        refresh_jitter_snapshot();
        if (g_jitter_vol > 0) return g_jittered[1];
        return g_cfg->key_real;
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* Detour                                                             */
/* ------------------------------------------------------------------ */

typedef struct _HOP_SLOT {
    void  *target;
    void  *hook;
    BYTE   original[HOP_SIZE];
    BOOL   active;
} HOP_SLOT;

static BOOL hop_patch(HOP_SLOT *slot)
{
    BYTE buf[HOP_SIZE];
    DWORD old;

    if (slot->active) return TRUE;
    if (!slot->target) return FALSE;

    buf[0] = 0x48; buf[1] = 0xB8;                    /* mov rax, imm64   */
    memcpy(&buf[2], &slot->hook, sizeof(void *));
    buf[10] = 0xFF; buf[11] = 0xE0;                  /* jmp rax          */
    buf[12] = 0x90; buf[13] = 0x90;                  /* nop; nop         */

    memcpy(slot->original, slot->target, HOP_SIZE);
    if (!VirtualProtect(slot->target, HOP_SIZE, PAGE_EXECUTE_READWRITE, &old))
        return FALSE;
    memcpy(slot->target, buf, HOP_SIZE);
    VirtualProtect(slot->target, HOP_SIZE, old, &old);
    FlushInstructionCache(GetCurrentProcess(), slot->target, HOP_SIZE);
    slot->active = TRUE;
    return TRUE;
}

static void hop_unpatch(HOP_SLOT *slot)
{
    DWORD old;

    if (!slot->active || !slot->target) return;
    VirtualProtect(slot->target, HOP_SIZE, PAGE_EXECUTE_READWRITE, &old);
    memcpy(slot->target, slot->original, HOP_SIZE);
    VirtualProtect(slot->target, HOP_SIZE, old, &old);
    FlushInstructionCache(GetCurrentProcess(), slot->target, HOP_SIZE);
    slot->active = FALSE;
}

/* ------------------------------------------------------------------ */
/* CommonLib 定位与导出解析                                            */
/* ------------------------------------------------------------------ */

static HMODULE g_commonlib = NULL;

static HMODULE find_commonlib(void)
{
    HMODULE module;
    DWORD size = 0;
    HMODULE *arr = NULL;
    DWORD count, i;
    wchar_t name[128];

    module = GetModuleHandleW(L"CommonLib.dll");
    if (module) return module;

    if (!EnumProcessModulesEx(GetCurrentProcess(), NULL, 0, &size, LIST_MODULES_ALL))
        return NULL;
    if (!size) return NULL;

    arr = (HMODULE *)malloc(size);
    if (!arr) return NULL;
    if (!EnumProcessModulesEx(GetCurrentProcess(), arr, size, &size, LIST_MODULES_ALL)) {
        free(arr);
        return NULL;
    }
    count = size / sizeof(HMODULE);
    for (i = 0; i < count; i++) {
        name[0] = 0;
        if (!GetModuleBaseNameW(GetCurrentProcess(), arr[i], name, 128))
            continue;
        if (_wcsicmp(name, L"CommonLib.dll") == 0) {
            module = arr[i];
            break;
        }
    }
    free(arr);
    return module;
}

static void *find_export(const char *name)
{
    if (!g_commonlib) return NULL;
    return (void *)GetProcAddress(g_commonlib, name);
}

/* ------------------------------------------------------------------ */
/* 7 个目标导出：s_core = 5 个常驻，s_real = 2 个按模式动态            */
/* ------------------------------------------------------------------ */

static HOP_SLOT s_core[5];
static HOP_SLOT s_real[2];
static BOOL g_core_ready = FALSE;
static BOOL g_real_ready = FALSE;

static void core_slots_init(void)
{
    s_core[0].target = find_export("RawInput_GetMouseSynthetic");
    s_core[0].hook   = (void *)hk_mouse_synth;
    s_core[1].target = find_export("RawInput_GetKeySynthetic");
    s_core[1].hook   = (void *)hk_key_synth;
    s_core[2].target = find_export("RawInput_GetMouseSyntheticRatio");
    s_core[2].hook   = (void *)hk_mouse_ratio;
    s_core[3].target = find_export("RawInput_GetKeySyntheticRatio");
    s_core[3].hook   = (void *)hk_key_ratio;
    s_core[4].target = find_export("RawInput_IsInterceptionDetected");
    s_core[4].hook   = (void *)hk_interception;

    s_real[0].target = find_export("RawInput_GetMouseReal");
    s_real[0].hook   = (void *)hk_mouse_real;
    s_real[1].target = find_export("RawInput_GetKeyReal");
    s_real[1].hook   = (void *)hk_key_real;
}

static BOOL ensure_core_hook(void)
{
    int i;

    for (i = 0; i < 5; i++) {
        if (!s_core[i].target) return FALSE;
        if (!hop_patch(&s_core[i])) return FALSE;
    }
    g_core_ready = TRUE;
    if (g_cfg) g_cfg->installed = TRUE;
    return TRUE;
}

static void restore_core_hook(void)
{
    int i;

    for (i = 0; i < 5; i++) hop_unpatch(&s_core[i]);
    g_core_ready = FALSE;
    if (g_cfg) g_cfg->installed = FALSE;
}

static BOOL ensure_real_hook(void)
{
    int i;

    if (!s_real[0].target || !s_real[1].target) return FALSE;
    for (i = 0; i < 2; i++) {
        if (!hop_patch(&s_real[i])) return FALSE;
    }
    g_real_ready = TRUE;
    if (g_cfg) g_cfg->installed_real = TRUE;
    return TRUE;
}

static void restore_real_hook(void)
{
    int i;

    for (i = 0; i < 2; i++) hop_unpatch(&s_real[i]);
    g_real_ready = FALSE;
    if (g_cfg) g_cfg->installed_real = FALSE;
}

/* ------------------------------------------------------------------ */
/* Watcher                                                            */
/* ------------------------------------------------------------------ */

static DWORD WINAPI watcher_thread(LPVOID unused)
{
    (void)unused;
    for (;;) {
        if (WaitForSingleObject(g_stop_event, RH_POLL_MS) == WAIT_OBJECT_0)
            break;

        if (!g_cfg || g_cfg->magic != RH_MAGIC)
            continue;

        if (!g_cfg->armed) {
            /* 未启用：回滚一切 detour，保持原样。hop_unpatch 幂等
             * （active 检查），可覆盖部分 patch 失败后 ready 标志未置位
             * 导致已装槽位无法回滚的场景。 */
            restore_real_hook();
            restore_core_hook();
            continue;
        }

        /* 启用状态：确保 CommonLib 已定位（游戏可能晚于注入加载） */
        if (!g_commonlib) g_commonlib = find_commonlib();
        if (!g_commonlib) {
            g_cfg->commonlib_found = FALSE;
            g_cfg->installed = FALSE;
            g_cfg->installed_real = FALSE;
            continue;
        }
        g_cfg->commonlib_found = TRUE;

        if (!g_core_ready) {
            core_slots_init();
            ensure_core_hook();
        }

        if (g_cfg->mode == 1) {
            if (g_core_ready && !g_real_ready) ensure_real_hook();
        } else {
            if (g_real_ready) restore_real_hook();
        }
    }
    return 0;
}

/* ------------------------------------------------------------------ */
/* DllMain                                                            */
/* ------------------------------------------------------------------ */

static void attach_hook(void)
{
    HANDLE map;
    void  *view;

    g_stop_event = CreateEventW(NULL, TRUE, FALSE, NULL);

    map = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, RH_MAP_NAME);
    if (map) {
        view = MapViewOfFile(map, FILE_MAP_ALL_ACCESS, 0, 0, 0);
        if (view) {
            g_cfg = (RH_CONFIG *)view;
            if (g_cfg->magic != RH_MAGIC)
                g_cfg = NULL;               /* 已打开但未初始化，交由 watcher 重试 */
            CloseHandle(map);
        } else {
            CloseHandle(map);
        }
    }

    g_watcher = CreateThread(NULL, 0, watcher_thread, NULL, 0, NULL);
}

static void detach_hook(void)
{
    if (g_stop_event) {
        SetEvent(g_stop_event);
        if (g_watcher) {
            WaitForSingleObject(g_watcher, 2000);
            CloseHandle(g_watcher);
            g_watcher = NULL;
        }
        CloseHandle(g_stop_event);
        g_stop_event = NULL;
    }
    /* watcher 已退出，恢复残留 detour，避免 DLL 卸载后跳转指向已卸载代码 */
    /* hop_unpatch 幂等（active 检查），无条件调用可覆盖部分 patch 失败场景 */
    restore_core_hook();
    restore_real_hook();
    if (g_cfg) {
        UnmapViewOfFile(g_cfg);
        g_cfg = NULL;
    }
}

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID reserved)
{
    (void)hinst;
    (void)reserved;
    switch (reason) {
    case DLL_PROCESS_ATTACH:
        DisableThreadLibraryCalls(hinst);
        attach_hook();
        break;
    case DLL_PROCESS_DETACH:
        detach_hook();
        break;
    default:
        break;
    }
    return TRUE;
}
