# -*- coding: utf-8 -*-
"""订阅工具页静态接线检查（2026-11-01 重构回归）。

这类问题只在真实页面里暴露：HTML 里的静态按钮忘了写 ``data-tb-action``，
点击时委托层找不到动作，页面「看起来正常」但按钮没反应。用纯文本检查把它
挡在提交前（不依赖浏览器/网络）。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECTION = ROOT / "webui" / "sections" / "toolbox.html"
MANAGER = ROOT / "webui" / "js" / "toolbox-manager.js"
VIEWS = ROOT / "webui" / "js" / "toolbox-views.js"
INDEX = ROOT / "webui" / "index.html"
INIT_CODE = ROOT / ".github" / "InitCode.py"


def _section_html() -> str:
    return SECTION.read_text(encoding="utf-8")


def _buttons() -> list[str]:
    return re.findall(r"<button\b[^>]*>", _section_html(), re.S)


def test_every_static_button_is_wired():
    """每个静态按钮必须有委托动作、Tab 动作、抽屉关闭或内联 onclick。"""
    for tag in _buttons():
        wired = (
            "data-tb-action=" in tag
            or "data-tb-tab=" in tag
            or "data-tb-drawer-close" in tag
            or "onclick=" in tag
        )
        assert wired, f"按钮缺少 data-tb-action/data-tb-tab/onclick：{tag}"


def test_static_actions_are_handled_by_manager():
    """HTML 里出现的动作名必须在 manager 的 switch 中有分支。"""
    html = _section_html()
    actions = set(re.findall(r'data-tb-action="([a-z-]+)"', html))
    manager = MANAGER.read_text(encoding="utf-8")
    missing = [a for a in sorted(actions) if f"case '{a}'" not in manager]
    assert not missing, f"订阅工具页动作没有处理分支：{missing}"


def test_no_page_level_cheat_risk_overlay():
    """整页作弊风险门控已移除（作弊入口点击时就地门控，作弊页自身仍门控）。"""
    html = _section_html()
    assert 'data-risk-overlay="cheat"' not in html
    manager = MANAGER.read_text(encoding="utf-8")
    assert "RiskGate.gatePage" not in manager


def test_device_key_conflict_prompts_overwrite():
    """本机密钥属于别的账号时必须弹窗询问覆盖，而不是直接报错（2026-11-05）。

    历史行为只回一句「请先在另一账号取消授权」—— 用户往往已经登录不上那个
    账号，机器就此锁死。前端必须认 `device_key_conflict` 并走确认弹窗，
    同意后带 `overwrite=true` 重试。
    """
    manager = MANAGER.read_text(encoding="utf-8")
    assert "device_key_conflict" in manager, "缺少冲突 code 分支"
    assert "_confirmOverwriteKey" in manager, "缺少覆盖确认弹窗"
    assert "ConfirmModal" in manager, "必须用应用内确认弹窗（原生 confirm 样式不一致）"
    assert "toolbox_authz_enable" in manager
    # 覆盖必须作为独立参数传给后端（否则后端无法区分「用户已同意」）
    assert "'', overwrite" in manager or "'', true" in manager


def test_views_load_before_manager_in_both_places():
    """打包顺序必须与 index.html 一致（AGENTS.md 硬规则）。"""
    index = INDEX.read_text(encoding="utf-8")
    assert index.index("js/toolbox-views.js") < index.index("js/toolbox-manager.js")
    init_code = INIT_CODE.read_text(encoding="utf-8")
    assert init_code.index("'js/toolbox-views.js'") < init_code.index("'js/toolbox-manager.js'")


def test_views_layer_has_no_bridge_calls():
    """渲染层保持纯函数：不直接调 pywebview 桥（状态与动作留在 manager）。"""
    views = VIEWS.read_text(encoding="utf-8")
    assert "pywebview.api" not in views
    assert "fetch(" not in views


def test_auth_changed_event_is_wired():
    """登录态在别处变化时必须立即刷新（2026-11-04）。

    后端 `ToolboxMixin._toolbox_notify_auth_changed()` 派发
    `lcta-toolbox-auth-changed`；manager 必须脚本加载即监听，并实现
    `onAuthChanged()` 强制重拉 —— 否则在镜像站窗口登录后回到本页仍显示「未登录」。
    """
    manager = MANAGER.read_text(encoding="utf-8")
    assert "lcta-toolbox-auth-changed" in manager, "缺少登录态变更事件监听"
    assert "onAuthChanged()" in manager, "缺少 onAuthChanged 处理函数"
    # 监听必须在脚本尾部立即注册（与 lcta-toolbox-install 同样不依赖 init()）
    assert "bindToolboxAuthEvents" in manager
    # 事件处理必须强制刷新在线状态（force=true），不能被 15s 节流挡住
    assert "refreshOnline(true)" in manager


def test_text_is_escaped_in_views():
    """服务端文本渲染前必须经 esc()：禁止直接插值关键字段。"""
    views = VIEWS.read_text(encoding="utf-8")
    raw_fields = (
        "name_zh", "tool_name", "summary", "author", "version", "category", "tags",
        "description", "target_dir", "compat_note", "release_notes", "license",
    )
    leaks = [f"${{item.{f}}}" for f in raw_fields if f"${{item.{f}}}" in views]
    assert not leaks, f"这些字段直接插值会引入 XSS：{leaks}"
    # 卡片标题与简介确实经过 esc（防止有人改成不转义的拼接）
    assert "ToolboxViews.esc(name)" in views
    assert "ToolboxViews.esc(item.summary || '暂无简介')" in views
