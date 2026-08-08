/* damage_hook.c
 *
 * LCTA 伤害倍率 Hook DLL (x64, MinGW-w64, MinHook)
 *
 * 原理：对 GameAssembly.dll 中 BattleUnitModel$$GetTakeAttackDmgMultiplier
 * （基类实现）做 MinHook detour —— 当受伤方是敌人
 * （GetOpponentFaction(self)==UNIT_FACTION_PLAYER）时把返回值乘以配置倍率：
 *
 *   before == 0.0（调用方按 1.0 处理的"无修正"）→ 直接置为 multiplier
 *   before != 0.0                             → before * multiplier
 *
 * Enemy/Abnormality/Part/Assistant 四个子类覆写版本最终都 call 基类实现，
 * 单点 detour 全覆盖。详见 docs/DAMAGE_HOOK.md。
 *
 * 偏移数据不在编译期硬编码，而是通过命名共享内存
 * （Local\LCTA_DamageHook_Config）由 Python 端运行时下发：
 *   - RVA + 16 字节 prologue 由 JSON API（web.lcta.top/damage_hook.json）
 *     提供，webutils/function_damage_hook.py 负责缓存与游戏更新后自动失效重拉
 *   - watcher 装钩前用下发 prologue 做运行时自检（VerifyPrologue），
 *     verified=0 即版本已变：回写状态并等待 Python 重发偏移（retry_requested）
 *
 * 安装时机：GameAssembly.dll 由 UnityPlayer 在进程启动后期加载，
 * watcher 轮询等待（最多 60s），无需外部注入时序配合。
 */

#include <windows.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include "MinHook.h"

#define DH_MAGIC        0x44484744u          /* "DHGD" */
#define DH_MAP_NAME     L"Local\\LCTA_DamageHook_Config"
#define DH_POLL_MS      300
#define DH_GA_TIMEOUT_MS 60000               /* 等待 GameAssembly.dll 上限 */
#define DH_LOG_RING_CAP 128                  /* 伤害日志环形缓冲容量（2 的幂） */
#define DH_LOG_LINE_MAX 127                  /* 单条日志最大字节（含 NUL） */

/* UNIT_FACTION.PLAYER == 0（dump.cs TypeDefIndex 16970） */
#define UNIT_FACTION_PLAYER 0

/* 错误码（回写 shared memory last_error） */
#define DH_ERR_OK               0
#define DH_ERR_NO_CONFIG        1            /* 共享内存不可用/未初始化 */
#define DH_ERR_GA_TIMEOUT       2            /* GameAssembly.dll 60s 内未加载 */
#define DH_ERR_PROLOGUE         3            /* prologue 不匹配，版本已变 */
#define DH_ERR_MH_INIT          4
#define DH_ERR_MH_CREATE        5
#define DH_ERR_MH_ENABLE        6

/* 与 webutils/function_damage_hook.py 中 DHConfig（ctypes）保持字段一一对应，
 * 自然对齐，共 16584 字节。 */
typedef struct _DH_CONFIG {
    volatile LONG        magic;
    volatile LONG        enabled;            /* 0/1 */
    volatile LONG        log;                /* 0/1，伤害日志开关 */
    volatile LONG        retry_requested;    /* Python 重发偏移后置 1，watcher 重装 */
    volatile float       multiplier;         /* 倍率（默认 3.0） */
    volatile LONG        rva_take_attack;    /* GetTakeAttackDmgMultiplier RVA */
    volatile LONG        rva_opponent_faction; /* GetOpponentFaction RVA */
    unsigned char        prologue[16];       /* 目标函数前 16 字节（自检用） */
    volatile LONG        gameassembly_found; /* watcher 是否找到 GameAssembly.dll */
    volatile LONG        verified;           /* prologue 自检是否通过 */
    volatile LONG        installed;          /* detour 是否已安装 */
    volatile LONG        last_error;         /* DH_ERR_* */
    volatile LONG        log_count;          /* 已记录伤害事件总数（单调递增） */
    char                 last_log[128];      /* 最近一条伤害日志（UI 展示用） */
    volatile LONG        log_head;           /* 环形缓冲写指针（单调递增，槽位=head%CAP） */
    char                 log_ring[DH_LOG_RING_CAP][DH_LOG_LINE_MAX + 1]; /* 伤害日志环形缓冲 */
    LONG                 _pad;
} DH_CONFIG;

static DH_CONFIG *g_cfg = NULL;
static HANDLE    g_stop_event = NULL;
static HANDLE    g_watcher = NULL;

/* ------------------------------------------------------------------ */
/* 函数签名与 detour 本体（见 MINHOOK_GUIDE.md §1.3/§5.2）             */
/* ------------------------------------------------------------------ */

/* IL2CPP x64 / MS ABI：5 参数 + 隐藏 MethodInfo*（原样透传） */
typedef float    (__fastcall *fn_GetTakeAttackDmgMultiplier)(void *self, void *action, void *coin, void *attacker, int8_t isCritical, const void *method);
typedef int32_t  (__fastcall *fn_GetOpponentFaction)        (void *self, const void *method);

static fn_GetTakeAttackDmgMultiplier g_pfnOriginal        = NULL;
static fn_GetOpponentFaction         g_pfnGetOpponentFaction = NULL;
static void *g_target = NULL;
static BOOL  g_hooked = FALSE;

static float __fastcall hk_GetTakeAttackDmgMultiplier(
    void *self, void *action, void *coin, void *attacker,
    int8_t isCritical, const void *method)
{
    float before = g_pfnOriginal(self, action, coin, attacker, isCritical, method);
    float result = before;
    DH_CONFIG *cfg = g_cfg;

    if (self && cfg && cfg->enabled && cfg->verified &&
        g_pfnGetOpponentFaction &&
        g_pfnGetOpponentFaction(self, NULL) == UNIT_FACTION_PLAYER)
    {
        /* 0 == "no modifier"，调用方按 1.0 处理（与 DamagePatch.cs 逐行一致） */
        result = (before == 0.0f) ? cfg->multiplier : before * cfg->multiplier;
    }

    if (cfg && cfg->log && result != before) {
        char line[96];
        LONG slot;
        int n = _snprintf(line, sizeof(line) - 1,
                          "target=%p attacker=%p crit=%d mul %.3f -> %.3f",
                          self, attacker, isCritical ? 1 : 0,
                          (double)before, (double)result);
        if (n < 0) n = 0;
        if (n > (int)sizeof(line) - 1) n = (int)sizeof(line) - 1;
        line[n] = '\0';
        cfg->log_count++;
        memcpy((char *)cfg->last_log, line, (size_t)n + 1);
        /* 环形缓冲：先写条目再原子递增 head（head 单调递增，槽位=head%CAP），
         * Python 端可安全按 [head-new, head) 增量抽取，不会读到半条。 */
        slot = cfg->log_head & (DH_LOG_RING_CAP - 1);
        memcpy(cfg->log_ring[slot], line, (size_t)n + 1);
        InterlockedIncrement(&cfg->log_head);
    }

    return result;
}

/* ------------------------------------------------------------------ */
/* 装钩 / 摘钩                                                         */
/* ------------------------------------------------------------------ */

static void uninstall_hook(void)
{
    if (!g_hooked)
        return;
    MH_DisableHook(g_target);
    MH_RemoveHook(g_target);
    MH_Uninitialize();
    g_pfnOriginal = NULL;
    g_pfnGetOpponentFaction = NULL;
    g_target = NULL;
    g_hooked = FALSE;
}

static BOOL verify_prologue(void *addr, const unsigned char *expected)
{
    unsigned char buf[16];
    /* 进程内直接读取即可（rawinput_hook 用 ReadProcessMemory 系通用写法） */
    memcpy(buf, addr, sizeof(buf));
    return memcmp(buf, expected, sizeof(buf)) == 0;
}

static void install_hook_with_config(void)
{
    HMODULE ga;
    uintptr_t base;
    void *target;
    void *faction;
    BOOL retry = g_cfg->retry_requested ? TRUE : FALSE;

    if (retry) {
        /* Python 已下发新偏移：摘除旧钩后按新配置重装 */
        uninstall_hook();
        g_cfg->retry_requested = FALSE;
    }
    if (g_hooked)
        return;

    ga = GetModuleHandleW(L"GameAssembly.dll");
    if (!ga)
        return;
    base = (uintptr_t)ga;                       /* ASLR：基址必须运行时获取 */

    target = (void *)(base + (uintptr_t)(uint32_t)g_cfg->rva_take_attack);
    faction = (void *)(base + (uintptr_t)(uint32_t)g_cfg->rva_opponent_faction);

    if (!verify_prologue(target, g_cfg->prologue)) {
        g_cfg->verified = FALSE;
        g_cfg->installed = FALSE;
        g_cfg->last_error = DH_ERR_PROLOGUE;    /* 版本已变，等待 Python 重拉偏移 */
        return;
    }
    g_cfg->verified = TRUE;
    g_pfnGetOpponentFaction = (fn_GetOpponentFaction)faction;

    if (MH_Initialize() != MH_OK) {
        g_cfg->last_error = DH_ERR_MH_INIT;
        return;
    }
    if (MH_CreateHook(target, &hk_GetTakeAttackDmgMultiplier,
                      (LPVOID *)&g_pfnOriginal) != MH_OK) {
        g_cfg->last_error = DH_ERR_MH_CREATE;
        MH_Uninitialize();
        return;
    }
    if (MH_EnableHook(target) != MH_OK) {
        g_cfg->last_error = DH_ERR_MH_ENABLE;
        MH_RemoveHook(target);
        MH_Uninitialize();
        return;
    }

    g_target = target;
    g_hooked = TRUE;
    g_cfg->installed = TRUE;
    g_cfg->last_error = DH_ERR_OK;
}

/* ------------------------------------------------------------------ */
/* Watcher                                                            */
/* ------------------------------------------------------------------ */

static void ensure_config(void)
{
    HANDLE map;
    void  *view;

    if (g_cfg && g_cfg->magic == DH_MAGIC)
        return;

    /* 共享内存可能由 Python 端在注入之后才创建（race），
     * 每个轮询周期重试打开。 */
    map = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, DH_MAP_NAME);
    if (!map)
        return;
    view = MapViewOfFile(map, FILE_MAP_ALL_ACCESS, 0, 0, 0);
    if (view) {
        if (view != g_cfg) {
            if (g_cfg)
                UnmapViewOfFile(g_cfg);
            g_cfg = (DH_CONFIG *)view;
        }
        if (g_cfg->magic != DH_MAGIC) {
            /* 已打开但未初始化（Python 尚未写入），下轮重试 */
            UnmapViewOfFile(g_cfg);
            g_cfg = NULL;
        }
    }
    CloseHandle(map);
}

static DWORD WINAPI watcher_thread(LPVOID unused)
{
    DWORD started = GetTickCount();
    DWORD last_attempt = 0;
    (void)unused;

    for (;;) {
        if (WaitForSingleObject(g_stop_event, DH_POLL_MS) == WAIT_OBJECT_0)
            break;

        ensure_config();
        if (!g_cfg)
            continue;                       /* 共享内存未就绪：等待 Python 端 apply() */

        if (!g_cfg->enabled) {
            /* 未启用：保持原样（不装钩也不摘钩，detour 内部按 enabled 放行） */
            continue;
        }

        if (!GetModuleHandleW(L"GameAssembly.dll")) {
            g_cfg->gameassembly_found = FALSE;
            if (GetTickCount() - started > DH_GA_TIMEOUT_MS)
                g_cfg->last_error = DH_ERR_GA_TIMEOUT;
            continue;
        }
        g_cfg->gameassembly_found = TRUE;

        /* 装钩失败（如 prologue 不匹配）后 5 秒退避，避免高频重试 MinHook */
        if (!g_hooked && g_cfg->last_error != DH_ERR_OK &&
            GetTickCount() - last_attempt < 5000)
            continue;
        install_hook_with_config();
        last_attempt = GetTickCount();
    }

    uninstall_hook();
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

    map = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, DH_MAP_NAME);
    if (map) {
        view = MapViewOfFile(map, FILE_MAP_ALL_ACCESS, 0, 0, 0);
        if (view) {
            g_cfg = (DH_CONFIG *)view;
            if (g_cfg->magic != DH_MAGIC)
                g_cfg = NULL;                   /* 已打开但未初始化，交由 watcher 重试 */
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
