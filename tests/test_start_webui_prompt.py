"""
tests/test_start_webui_prompt.py
start_webui 启动期依赖更新提示窗（_run_pending_pip_ops_with_prompt）回归测试。

历史 bug：进度文本经 SetWindowTextW 写进了弹窗标题栏而非正文，标题被改后
FindWindowW 按原标题再也找不到窗口，完成时的 WM_CLOSE 自动关闭永远发不出去，
弹窗只能靠用户手动点「确定」（提前点掉还会循环重弹）。

覆盖（全部经 fake user32 模拟 Win32 行为，不弹真实窗口）：
- 无 pending 操作时完全不弹窗、不触碰 user32
- 正常路径零点击：弹窗随后台完成自动 WM_CLOSE 关闭，仅弹一次
- 进度文本经 WM_SETTEXT 写入正文 Static 子控件，从不改标题栏
- 正文 Static 定位排除 SS_ICON 图标控件
- 用户提前点掉时重弹一次，重弹的窗口仍自动关闭
- 部分失败时才追加一次需确认的报错弹窗
- 后台线程先于弹窗完成时，主循环跳过弹窗（不弹无意义的「已完成」框）
"""
import ctypes
import sys
import threading
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import start_webui
import globalManagers.pending_pip_ops as ppo

WM_CLOSE = 0x0010
WM_SETTEXT = 0x000C
SS_ICON = 0x0003

# 模拟 MessageBox 的子控件结构：图标 Static、正文 Static、按钮
_DEFAULT_BOX_CHILDREN = [
    ("Static", SS_ICON),          # 左上角图标
    ("Static", 0x0000),           # 正文（SS_LEFT）
    ("Button", 0x50000000),       # 确定
]


def make_fake_user32(box_children=None, click_through=0):
    """构造可编排的 user32 假实现。

    - click_through: 前 N 次 MessageBoxW 立即返回（模拟用户提前点掉「确定」），
      之后的弹窗阻塞到收到 WM_CLOSE 才返回（模拟真实模态行为）。
    - 弹窗正文子控件按 box_children 的 (类名, 样式) 顺序生成，
      子控件句柄 = 弹窗句柄 + 1 + 序号。
    - WM_SETTEXT 到某弹窗子控件会同步该弹窗的 text（模拟正文归属）。
    - no_block 事件置位后 MessageBoxW 不再阻塞（流程收尾后的报错弹窗
      无人关闭，由假实现直接返回以结束流程）。
    """
    calls = []            # 记录全部 API 调用（含参数），供断言
    settext_targets = []  # (hwnd, text) —— WM_SETTEXT 的目标与文本
    boxes = []            # 每次 MessageBoxW 一个 dict
    child_styles = {}     # 子控件句柄 -> (类名, 样式)
    open_by_title = {}
    next_hwnd = [1000]
    box_counter = [0]
    no_block = threading.Event()

    def _owning_box(hwnd):
        for box in boxes:
            if box["hwnd"] < hwnd <= box["hwnd"] + len(box_children
                                                       or _DEFAULT_BOX_CHILDREN):
                return box
        return None

    def MessageBoxW(owner, text, title, flags):
        idx = box_counter[0]
        box_counter[0] += 1
        hwnd = next_hwnd[0]
        next_hwnd[0] += 4
        box = {"hwnd": hwnd, "initial_text": text, "text": text,
               "event": threading.Event(), "index": idx, "open": True}
        boxes.append(box)
        open_by_title[title] = box
        calls.append(("MessageBoxW", text, title, flags))
        if idx >= click_through and not no_block.is_set():
            box["event"].wait(timeout=10)  # 模态：等 WM_CLOSE（超时兜底防测试卡死）
        box["open"] = False
        open_by_title.pop(title, None)
        return 1

    def FindWindowW(cls, title):
        calls.append(("FindWindowW", title))
        box = open_by_title.get(title)
        return box["hwnd"] if box else None

    def PostMessageW(hwnd, msg, wparam, lparam):
        calls.append(("PostMessageW", hwnd, msg))
        if msg == WM_CLOSE:
            for box in boxes:
                if box["hwnd"] == hwnd and box["open"]:
                    box["open"] = False
                    box["event"].set()
                    break
        return True

    def SendMessageW(hwnd, msg, wparam, lparam):
        calls.append(("SendMessageW", hwnd, msg))
        if msg == WM_SETTEXT:
            settext_targets.append((hwnd, lparam))
            box = _owning_box(hwnd)
            if box:
                box["text"] = lparam
        return 0

    def SetWindowTextW(hwnd, text):
        # 仅供断言「从不改标题栏」；真实现会改 caption
        calls.append(("SetWindowTextW", hwnd, text))
        return True

    def EnumChildWindows(hwnd, proc, lparam):
        calls.append(("EnumChildWindows", hwnd))
        if not any(b["hwnd"] == hwnd for b in boxes):
            return False
        for i, (cls, style) in enumerate(box_children or _DEFAULT_BOX_CHILDREN):
            child = hwnd + 1 + i
            child_styles[child] = (cls, style)
            if not proc(child, None):
                break
        return True

    def GetClassNameW(hwnd, buf, n):
        cls, _ = child_styles.get(hwnd, ("", 0))
        buf.value = cls
        return len(cls)

    def GetWindowLongW(hwnd, index):
        _, style = child_styles.get(hwnd, ("", 0))
        return style

    class _FakeUser32:
        pass

    fake = _FakeUser32()
    fake.MessageBoxW = MessageBoxW
    fake.FindWindowW = FindWindowW
    fake.PostMessageW = PostMessageW
    fake.SendMessageW = SendMessageW
    fake.SetWindowTextW = SetWindowTextW
    fake.EnumChildWindows = EnumChildWindows
    fake.GetClassNameW = GetClassNameW
    fake.GetWindowLongW = GetWindowLongW
    fake.calls = calls
    fake.settext_targets = settext_targets
    fake.boxes = boxes
    fake.no_block = no_block
    return fake


def _fake_apply(fake, result=True, specs=("json_repair",), delay=0.0):
    """构造 apply_pending_pip_ops 假实现：触发一次进度回调后返回 result。"""
    def apply(path=None, progress_callback=None):
        if delay:
            time.sleep(delay)
        if progress_callback:
            progress_callback(f"正在安装依赖 {specs[0]}…")
        fake.no_block.set()  # 流程收尾：后续弹窗（报错框）不再阻塞
        return result
    return apply


def _patch(monkeypatch, fake, pending, apply_fn):
    """把假 user32 与假 pending 数据打进 start_webui 的运行环境。"""
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, *a, **k: fake)
    monkeypatch.setattr(
        ppo, "load_pending_ops", lambda path=None: dict(pending))
    monkeypatch.setattr(
        ppo, "_pending_ops_default_path", lambda: Path("unused"))
    monkeypatch.setattr(ppo, "apply_pending_pip_ops", apply_fn)


def _box_calls(fake):
    return [c for c in fake.calls if c[0] == "MessageBoxW"]


def _wm_close_calls(fake):
    return [c for c in fake.calls
            if c[0] == "PostMessageW" and c[2] == WM_CLOSE]


_HAS_PENDING = {"uninstall": [], "install": ["json_repair"]}
_NO_PENDING = {"uninstall": [], "install": []}


# ========== 无 pending：零交互 ==========

def test_no_pending_ops_never_touches_user32(monkeypatch):
    fake = make_fake_user32()
    _patch(monkeypatch, fake, _NO_PENDING,
           _fake_apply(fake))  # 不应被调用
    start_webui._run_pending_pip_ops_with_prompt()
    assert fake.calls == []


# ========== 正常路径：零点击自动关闭 ==========

def test_success_path_auto_closes_with_single_box(monkeypatch):
    fake = make_fake_user32()
    _patch(monkeypatch, fake, _HAS_PENDING,
           _fake_apply(fake, result=True, delay=0.3))
    start_webui._run_pending_pip_ops_with_prompt()

    # 仅弹一次等待框，经 WM_CLOSE 自动关闭
    assert len(fake.boxes) == 1
    assert fake.boxes[0]["initial_text"] == "正在准备依赖更新…"
    closes = _wm_close_calls(fake)
    assert closes and closes[0][1] == fake.boxes[0]["hwnd"]
    # 进度已同步到正文，且从不修改标题栏
    assert fake.boxes[0]["text"] == "正在安装依赖 json_repair…"
    assert not any(c[0] == "SetWindowTextW" for c in fake.calls)


def test_progress_written_to_body_static_not_caption(monkeypatch):
    fake = make_fake_user32()
    _patch(monkeypatch, fake, _HAS_PENDING,
           _fake_apply(fake, result=True, delay=0.3))
    start_webui._run_pending_pip_ops_with_prompt()

    assert fake.settext_targets, "进度文本未写入任何控件"
    target_hwnd, target_text = fake.settext_targets[0]
    # 正文 = 弹窗子控件中排除图标 Static 后的第一个（句柄 = 弹窗 + 1 + 1）
    assert target_hwnd == fake.boxes[0]["hwnd"] + 2
    assert target_text == "正在安装依赖 json_repair…"
    assert not any(c[0] == "SetWindowTextW" for c in fake.calls)


# ========== 用户提前点掉：重弹且最终自动关闭 ==========

def test_early_click_reshows_then_auto_closes(monkeypatch):
    fake = make_fake_user32(click_through=1)
    _patch(monkeypatch, fake, _HAS_PENDING,
           _fake_apply(fake, result=True, delay=0.3))
    start_webui._run_pending_pip_ops_with_prompt()

    assert len(fake.boxes) == 2  # 提前点掉后重弹一次
    # 重弹窗口的正文随后台进度刷新，并被自动关闭
    assert fake.boxes[1]["text"] == "正在安装依赖 json_repair…"
    closes = _wm_close_calls(fake)
    assert closes and closes[-1][1] == fake.boxes[1]["hwnd"]


# ========== 部分失败：追加一次需确认的报错弹窗 ==========

def test_failure_shows_single_error_box(monkeypatch):
    fake = make_fake_user32()
    _patch(monkeypatch, fake, _HAS_PENDING,
           _fake_apply(fake, result=False, delay=0.3))
    start_webui._run_pending_pip_ops_with_prompt()

    box_calls = _box_calls(fake)
    assert len(box_calls) == 2
    error_call = box_calls[1]
    assert "部分依赖更新未完成" in error_call[1]
    assert error_call[3] & 0x10  # MB_ICONERROR
    # 等待框仍是自动关闭的
    closes = _wm_close_calls(fake)
    assert closes and closes[0][1] == fake.boxes[0]["hwnd"]


# ========== 竞态：worker 先完成 → 不弹无意义窗口 ==========

def test_worker_finishes_before_prompt_shows_nothing(monkeypatch):
    fake = make_fake_user32()
    _patch(monkeypatch, fake, _HAS_PENDING,
           _fake_apply(fake, result=True, delay=0.0))
    # 缩短自动关闭宽限期（该场景下宽限循环会空转直到超时）
    monkeypatch.setattr(
        start_webui, "_PENDING_PROMPT_CLOSE_GRACE_SECONDS", 0.1)

    # 内联线程：worker 同步跑完（done 置位先于主循环判断），主循环应整体跳过
    class _InlineThread:
        def __init__(self, target=None, daemon=None):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr("threading.Thread", _InlineThread)
    start_webui._run_pending_pip_ops_with_prompt()

    assert fake.boxes == []
    assert not _wm_close_calls(fake)
