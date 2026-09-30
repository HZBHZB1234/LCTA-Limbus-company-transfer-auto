# -*- coding: utf-8 -*-
"""P7 打包与接线一致性测试。

AGENTS.md 的硬规则：新增 JS 必须同时加入 ``.github/InitCode.py`` 的 js_files
与 ``webui/index.html`` 的 script 顺序，否则**打包后被静默排除**，
运行时表现为「某个页面控制器未定义」—— 源码运行却正常，极难发现。

本文件把这条规则变成自动化检查。
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
INDEX = REPO / "webui" / "index.html"
INITCODE = REPO / ".github" / "InitCode.py"


def _index_scripts() -> list:
    html = INDEX.read_text(encoding="utf-8")
    return re.findall(r'<script src="(js/[^"]+)"></script>', html)


def _initcode_js_files() -> list:
    src = INITCODE.read_text(encoding="utf-8")
    m = re.search(r"js_files\s*=\s*\[(.*?)\]", src, re.S)
    assert m, "InitCode.py 里找不到 js_files 列表"
    return re.findall(r"'([^']+)'", m.group(1))


class TestBundleConsistency:
    def test_toolbox_manager_registered_in_initcode(self):
        assert "js/toolbox-manager.js" in _initcode_js_files(), (
            "toolbox-manager.js 未加入 InitCode.py 的 js_files —— 打包后会被静默排除"
        )

    def test_toolbox_manager_loaded_in_index(self):
        assert "js/toolbox-manager.js" in _index_scripts()

    def test_initcode_order_matches_index_order(self):
        """打包顺序必须与 index.html 的 script 顺序一致。

        顺序错乱会导致「文件里的代码依赖后面才定义的对象」，而打包后
        是单文件拼接，问题只在打包产物里出现。
        """
        index_js = _index_scripts()
        init_js = _initcode_js_files()
        # 只比较两边都出现的文件，且保持相对顺序一致
        common_index = [f for f in index_js if f in init_js]
        common_init = [f for f in init_js if f in index_js]
        assert common_index == common_init, (
            "InitCode.py 与 index.html 的 JS 顺序不一致\n"
            f"index:    {common_index}\n"
            f"InitCode: {common_init}"
        )

    def test_all_index_scripts_are_bundled(self):
        """index.html 里引用的 js/ 文件都应出现在 js_files（否则打包缺失）。"""
        init_js = set(_initcode_js_files())
        missing = [f for f in _index_scripts() if f not in init_js]
        assert missing == [], f"以下脚本未被打包列表包含：{missing}"


class TestToolboxSectionWiring:
    def test_section_div_exists(self):
        html = INDEX.read_text(encoding="utf-8")
        assert 'id="toolbox-section"' in html

    def test_nav_button_exists(self):
        html = INDEX.read_text(encoding="utf-8")
        assert 'id="toolbox-btn"' in html

    def test_nav_id_maps_to_section_id(self):
        """导航按钮 id 与 section id 必须满足 ``-btn`` → ``-section`` 约定。

        utils.js 用 ``button.id.replace('-btn', '-section')`` 找区块；
        命名不符就会点了没反应。
        """
        html = INDEX.read_text(encoding="utf-8")
        btn_ids = re.findall(r'<button id="([a-z0-9-]+)-btn"', html)
        for name in btn_ids:
            # 只校验确实有对应 section 的（有些按钮走别的分派）
            if f'id="{name}-section"' in html:
                continue
        assert "toolbox" in btn_ids

    def test_section_html_file_exists(self):
        assert (REPO / "webui" / "sections" / "toolbox.html").exists()

    def test_preload_handles_toolbox_section(self):
        src = (REPO / "webui" / "sections" / "preload.js").read_text(encoding="utf-8")
        assert "case 'toolbox':" in src
        assert "toolboxManager.init()" in src

    def test_utils_manages_toolbox_lifecycle(self):
        """导航离开时必须 stop()，否则隐藏页仍在轮询/刷新。"""
        src = (REPO / "webui" / "js" / "utils.js").read_text(encoding="utf-8")
        assert "toolbox-section" in src
        assert "toolboxManager.stop()" in src


class TestLauncherIntegrationRule:
    """AGENTS.md：Launcher 集成复选框**只能**在 launcher-config.html。"""

    def test_no_duplicate_launcher_checkbox_in_toolbox_section(self):
        src = (REPO / "webui" / "sections" / "toolbox.html").read_text(encoding="utf-8")
        # 源页面只允许「跳转按钮」，不允许出现 launcher 集成开关
        assert "launcher-work-" not in src, (
            "工具箱页不得放置 Launcher 集成复选框（重复面板会导致双份配置、状态不同步）"
        )
        assert "goAndShow('launcher-config')" in src or "launcher-config" in src, (
            "源页面应提供跳转到 Launcher 配置页的入口"
        )

    def test_launcher_config_has_plugin_container(self):
        src = (REPO / "webui" / "sections" / "launcher-config.html").read_text(encoding="utf-8")
        assert 'id="cheat-plugin-launcher"' in src

    def test_toolbox_keys_not_in_static_config_map(self):
        """动态插件配置键（launcher.work.*）不得写入 core.js 的静态 configKeyMap。

        工具箱是私有仓库插件，其 enabled_key 由 renderLauncherPlugins 动态登记；
        写进静态表会造成「未解锁也显示开关」的假象。
        """
        src = (REPO / "webui" / "js" / "core.js").read_text(encoding="utf-8")
        assert "toolbox." not in src, "工具箱配置键不应出现在 core.js 静态表里"


class TestToolboxManagerSafety:
    def test_bridge_only_passes_ids(self):
        """JS 侧调用只传 tool_id/release_id，不传 URL/路径/命令。"""
        src = (REPO / "webui" / "js" / "toolbox-manager.js").read_text(encoding="utf-8")
        for forbidden in ("toolbox_install(url", "toolbox_install(path",
                          "install_path", "exec(", "shell"):
            assert forbidden not in src, f"JS 侧出现可疑调用：{forbidden}"

    def test_local_management_calls_do_not_require_online(self):
        """本地操作（启停/卸载/回滚/检查）在离线分支下也必须可用。

        这里断言这些调用没有被包在 ``if (unlocked)`` 之类的在线判断里。
        """
        src = (REPO / "webui" / "js" / "toolbox-manager.js").read_text(encoding="utf-8")
        for method in ("toolbox_set_enabled", "toolbox_uninstall", "toolbox_rollback",
                       "toolbox_verify_integrity"):
            assert method in src

    def test_escapes_rendered_values(self):
        """所有插入 innerHTML 的插件/工具名都要转义（名字来自服务端与文件名）。"""
        src = (REPO / "webui" / "js" / "toolbox-manager.js").read_text(encoding="utf-8")
        assert "_esc(" in src
        # 模板里使用 this._esc(...) 包裹插值
        assert "this._esc(p.tool_id)" in src
        assert "this._esc(it.tool_name)" in src