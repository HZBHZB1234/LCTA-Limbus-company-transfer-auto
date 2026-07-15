# 游戏加速功能设计文档

**日期**: 2026-07-16
**状态**: 设计中

---

## 1. 概述

基于 OpenSpeedy Python 库，在 LCTA 中添加游戏加速功能。用户可通过 WebUI 页面或 Launcher 模式控制 `LimbusCompany.exe` 的游戏速度（0.1x – 10.0x）。

核心能力：
- WebUI 页面：免责声明锁屏 → 进程检测 → 注入/变速控制
- Launcher 模式：全局热键（`ctrl+s` / `ctrl+shift+s`），游戏内动态变速
- 延迟注入：首次变速时才注入 DLL，避免不必要的检测风险

## 2. 依赖

新增以下 Python 依赖到 `requirements.txt`：

| 包 | 用途 |
|---|---|
| `openspeedy` | DLL 注入 + Windows 时间 API hook，控制进程速度 |
| `keyboard` | Launcher 模式下注册全局热键 |

## 3. 配置项

### 3.1 已有配置桩（config.json 中已存在，需实现）

```json
{
  "speed": {
    "disclaimer_accepted": false
  },
  "launcher": {
    "work": {
      "speed": false,
      "speed_factor": "2.0"
    }
  }
}
```

- `speed.disclaimer_accepted`：用户是否已同意免责声明
- `launcher.work.speed`：Launcher 模式下是否启用加速
- `launcher.work.speed_factor`：Launcher 模式下的目标倍率

### 3.2 配置权限

`launcher.work.speed` 开关放在加速页面内，**受免责声明保护**：用户必须先同意免责声明，才能开启此开关。

## 4. WebUI 页面（speed-section）

### 4.1 锁定状态

进入页面时，若 `speed.disclaimer_accepted !== true`，显示免责声明覆盖层：

**免责声明内容**：

> **⚠ 风险警告**
>
> 游戏加速功能通过 DLL 注入技术实现（OpenSpeedy）。此技术可能被反作弊系统（包括但不限于 EAC、BattlEye、Vanguard、Ricochet）检测并标记，**可能导致游戏账号被封禁**。
>
> - 本功能仅供学习 Windows API Hooking 技术使用
> - 仅建议在单机/离线游戏中使用
> - 在在线竞技游戏中使用违反大多数游戏的用户协议
> - 使用者自行承担全部风险，开发者不承担任何责任

用户须勾选"我已了解上述风险"并点击确认，覆盖层消失，页面功能解锁。

### 4.2 主界面

**进程状态区**：
- 自动检测 `LimbusCompany.exe`（进程名硬编码，无需用户选择）
- 显示：运行状态（●/○）、PID、是否已注入、是否已启用、当前倍率
- 提供刷新按钮

**速度控制区**：
- 滑块：范围 0.1x – 10.0x，步长 0.1x
- 预设按钮：1x、2x、3x、5x
- 数值输入框（与滑块双向同步）

**操作区**：
- [注入] 按钮：检测 `LimbusCompany.exe` 并注入 DLL
- [弹出] 按钮：弹出 DLL
- ☑ 启用加速：对应 `SpeedController.enable()/disable()`，不改变注入状态

**Launcher 设置区**（仅在同意免责声明后可见）：
- ☐ 在 Launcher 模式下启用游戏加速：写入 `launcher.work.speed`
- 显示 Launcher 可用热键说明（纯文本，页面不注册热键）

### 4.3 页面不注册任何全局热键

WebUI 中的热键说明仅供用户参考，实际热键仅在 Launcher 模式下由 `launcher/main.py` 注册。

## 5. SpeedManager（webutils/function_speed.py）

### 5.1 核心类

```python
class SpeedManager:
    """封装 OpenSpeedy SpeedController，管理单例生命周期"""

    _instance: SpeedController | None = None  # OpenSpeedy 控制器实例

    @staticmethod
    def get_game_status() -> dict:
        """返回 LimbusCompany.exe 的状态
        {
            "running": bool,      # 进程是否在运行
            "pid": int | None,    # 进程 PID
            "injected": bool,     # 是否已注入
            "enabled": bool,      # 加速是否启用
            "speed": float | None # 当前全局速度倍率
        }
        """

    @staticmethod
    def inject() -> bool:
        """自动查找 LimbusCompany.exe 并注入 DLL。
        若已注入则直接返回 True。
        返回是否注入成功。"""

    @staticmethod
    def is_injected() -> bool:
        """检查 LimbusCompany.exe 是否已注入。"""

    @staticmethod
    def eject() -> bool:
        """弹出 DLL 并释放 SpeedController。
        返回是否成功。"""

    @staticmethod
    def set_speed(factor: float) -> bool:
        """设置全局速度倍率。若未注入则先注入。"""

    @staticmethod
    def enable() -> bool:
        """启用当前进程的加速效果。"""

    @staticmethod
    def disable() -> bool:
        """禁用当前进程的加速效果。"""

    @staticmethod
    def close():
        """弹出所有注入并清理资源。"""
```

### 5.2 设计要点

- **单一目标进程**：始终针对 `LimbusCompany.exe`，不提供多进程管理
- **延迟注入**：`set_speed()` 调用时才检查并注入，不在构造/打开时注入
- **懒初始化**：`SpeedController` 实例在首次注入时创建
- **WebUI 与 Launcher 共享**：通过静态方法暴露，两端复用同一逻辑
- **错误处理**：捕获 OpenSpeedy 异常（进程不存在、权限不足、架构不匹配等），转换为用户友好的错误消息

## 6. Launcher 集成（launcher/main.py）

### 6.1 控制流

```
main_after_mod() / main_after_game()
  │
  ├─ 检查 launcher.work.speed (false → 跳过)
  ├─ 检查 speed.disclaimer_accepted (false → 跳过)
  │
  └─ 启动后台热键线程 → subprocess.call(game)
                          │
                          ├─ ctrl+s → 延迟注入 + 切换 1x / speed_factor
                          ├─ ctrl+shift+s → 延迟注入 + tkinter 滑块窗口
                          │
                          └─ 游戏退出 → 弹出 DLL → 移除热键 → 线程退出
```

### 6.2 热键实现

```python
import keyboard

def start_speed_hotkeys(speed_factor: float):
    """注册全局热键，在后台线程中运行。"""

    speed_enabled = False

    def toggle_speed():
        nonlocal speed_enabled
        # 延迟注入：首次触发时才注入
        if not SpeedManager.is_injected():
            SpeedManager.inject()
        speed_enabled = not speed_enabled
        SpeedManager.set_speed(speed_factor if speed_enabled else 1.0)

    def open_speed_selector():
        # 延迟注入
        if not SpeedManager.is_injected():
            SpeedManager.inject()
        # tkinter 弹出窗口
        _show_tkinter_slider()

    keyboard.add_hotkey('ctrl+s', toggle_speed)
    keyboard.add_hotkey('ctrl+shift+s', open_speed_selector)

    # 阻塞直到退出事件被设置
    exit_event.wait()

    keyboard.remove_all_hotkeys()
    SpeedManager.close()
```

### 6.3 Tkinter 倍率选择窗口

`ctrl+shift+s` 弹出简单 tkinter 窗口：
- 标题："游戏加速"
- 滑块（0.1x – 10.0x）+ 当前值显示
- [确定] 按钮：应用速度并关闭窗口
- 窗口置顶（`topmost=True`），不抢夺游戏焦点

### 6.4 延迟注入

- 游戏启动时**不注入** DLL
- 第一次按 `ctrl+s` 或 `ctrl+shift+s` 时才执行注入
- 优点：避免游戏启动阶段的检测窗口，减少无加速需求时的暴露

## 7. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `webutils/function_speed.py` | **新建** | SpeedManager 类，封装 OpenSpeedy 单例 |
| `webutils/__init__.py` | 修改 | 导入 `function_speed` 并添加至 `__all__` |
| `webui/app.py` | 修改 | LCTA_API 添加 `speed_status`、`speed_inject`、`speed_eject`、`speed_set`、`speed_enable`、`speed_disable` 方法 |
| `webui/index.html` | 修改 | 添加 `speed-btn`（侧栏导航）+ `speed-section`（内容区，含免责声明覆盖层） |
| `webui/js/speed.js` | **新建** | SpeedPage 类：状态轮询、滑块、免责声明流程 |
| `webui/guide/speed.md` | **新建** | 加速功能帮助文档 |
| `launcher/main.py` | 修改 | 添加热键线程启动/清理逻辑、tkinter 倍率选择窗口 |
| `requirements.txt` | 修改 | 添加 `openspeedy`、`keyboard` |

## 8. 安全与错误处理

### 8.1 OpenSpeedy 异常映射

| OpenSpeedy 异常 | 触发场景 | 用户提示 |
|---|---|---|
| `ProcessNotFoundError` | `LimbusCompany.exe` 未运行 | "游戏未运行，请先启动游戏" |
| `ProcessAccessDeniedError` | 游戏以管理员权限运行但 LCTA 未提权 | "权限不足，请以管理员权限运行 LCTA" |
| `ProcessArchitectureMismatch` | Python 与游戏架构不一致（x64 vs x86） | "架构不匹配，请使用对应版本的 Python" |
| `InjectionError` | DLL 注入失败（被杀软拦截等） | "注入失败，请检查杀毒软件是否拦截" |
| `EjectionError` | DLL 弹出失败 | 记录日志，静默忽略 |
| `SpeedRangeError` | 速度倍率超出范围 | "速度倍率必须在 0.001 – 1000 之间" |

### 8.2 权限检查

- Launcher 模式下，若游戏为管理员权限但 LCTA 未提权，提示用户重启 LCTA
- 注入前检查目标进程架构是否与当前 Python 架构一致

## 9. 测试验证

1. **免责声明流程**：清除 `disclaimer_accepted` → 打开加速页面 → 验证覆盖层显示 → 勾选确认 → 验证解锁
2. **进程检测**：启动/关闭 LimbusCompany → 验证状态栏正确显示运行/未运行
3. **WebUI 注入流程**：启动游戏 → 点击注入 → 验证状态变化 → 拖动滑块 → 验证游戏速度变化 → 点击弹出
4. **Launcher 热键**：`python start_webui.py -launcher` → 启动游戏 → `ctrl+s` 切换加速 → 验证游戏速度变化 → 关闭游戏 → 验证清理
5. **Launcher tkinter 窗口**：`ctrl+shift+s` → 弹出滑块窗口 → 选择倍率 → 验证速度变化
6. **延迟注入**：Launcher 模式启动游戏 → 不按热键 → 验证 DLL 未注入 → 按 `ctrl+s` → 验证注入 + 变速
7. **配置开关**：关闭 `launcher.work.speed` → Launcher 模式 → 验证热键未注册
