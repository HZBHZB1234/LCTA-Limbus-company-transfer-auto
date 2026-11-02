# -*- coding: utf-8 -*-
"""工具间依赖解析（2026-11-02）：安装序、缺口分类、卸载反查。

服务端负责"依赖存在且无环"，客户端这一步负责"本地磁盘上到底能不能装"：
没装、版本太低、被停用、没资格、目录里没有，都要分类上报，且必须在写任何
文件之前判定。
"""
from __future__ import annotations

import pytest

from webutils.toolbox import deps, state


def _manifest(tmp_path, *, plugins=None, packages=None) -> state.Manifest:
    m = state.Manifest(tmp_path / "game")
    for entry in plugins or []:
        m.plugins[entry.tool_id] = entry
    for entry in packages or []:
        m.packages[entry.tool_id] = entry
    return m


def _plugin(tool_id, version_sort, *, enabled=True, dependencies=(), version="1.0.0"):
    return state.PluginEntry(
        tool_id=str(tool_id),
        release_id=f"r{tool_id}",
        version=version,
        version_sort=version_sort,
        enabled=enabled,
        main_dll="A.dll",
        dependencies=list(dependencies),
    )


def _item(tool_id, *, version_sort="0001.0000.0000~", dependencies=(), is_latest=True,
          downloadable=True, install_kind="bepinex_plugin_dll"):
    return {
        "tool_id": int(tool_id),
        "tool_name": f"T{tool_id}",
        "release_id": f"r{tool_id}",
        "version": "1.0.0",
        "version_sort": version_sort,
        "is_latest": is_latest,
        "install_kind": install_kind,
        "access_kind": "original",
        "downloadable": downloadable,
        "dependencies": list(dependencies),
    }


def _dep(tool_id, *, min_sort=None, min_version=None, optional=False, downloadable=None,
         tool_name=None):
    entry = {
        "tool_id": tool_id,
        "optional": optional,
        "in_catalog": True,
        "min_version": min_version,
        "min_version_sort": min_sort,
    }
    if downloadable is not None:
        entry["downloadable"] = downloadable
    if tool_name:
        entry["tool_name"] = tool_name
    return entry


class TestIndex:
    def test_catalog_prefers_latest(self):
        items = [
            _item(1, version_sort="0001.0000.0000~", is_latest=False),
            _item(1, version_sort="0002.0000.0000~", is_latest=True),
            _item(1, version_sort="0003.0000.0000~", is_latest=False),
        ]
        assert deps.catalog_index(items)["1"]["version_sort"] == "0002.0000.0000~"

    def test_catalog_falls_back_to_highest_version(self):
        """老站点没有 is_latest：退化为按 version_sort 取最大（好过比 release_id）。"""
        items = [
            _item(1, version_sort="0001.0000.0000~", is_latest=False),
            _item(1, version_sort="0001.0010.0000~", is_latest=False),
        ]
        assert deps.catalog_index(items)["1"]["version_sort"] == "0001.0010.0000~"

    def test_installed_index_covers_plugins_and_packages(self, tmp_path):
        package = state.PackageEntry(
            tool_id="2", release_id="r2", version="1.0.0", version_sort="0001.0000.0000~"
        )
        m = _manifest(tmp_path, plugins=[_plugin(1, "0001.0000.0000~")], packages=[package])
        index = deps.installed_index(m)
        assert index["1"]["kind"] == "plugin"
        assert index["2"]["kind"] == "package"
        assert index["2"]["enabled"] is True


class TestResolve:
    def test_no_dependencies_is_ok(self, tmp_path):
        info = deps.resolve(_manifest(tmp_path), [_item(1)], 1)
        assert info["ok"] is True
        assert info["order"] == ["1"]

    def test_missing_dependency_blocks(self, tmp_path):
        catalog = [_item(1, dependencies=[_dep(2, tool_name="依赖")])]
        info = deps.resolve(_manifest(tmp_path), catalog, 1)
        assert info["ok"] is False
        assert [g["tool_id"] for g in info["missing"]] == ["2"]

    def test_install_order_is_dependency_first(self, tmp_path):
        """A→B→C，都缺：安装序必须是 C、B、A。"""
        catalog = [
            _item(1, dependencies=[_dep(2)]),
            _item(2, dependencies=[_dep(3)]),
            _item(3),
        ]
        info = deps.resolve(_manifest(tmp_path), catalog, 1)
        assert info["order"] == ["3", "2", "1"]

    def test_installed_and_satisfied_not_in_order(self, tmp_path):
        m = _manifest(tmp_path, plugins=[_plugin(2, "0001.0005.0000~")])
        catalog = [_item(1, dependencies=[_dep(2, min_sort="0001.0002.0000~")])]
        info = deps.resolve(m, catalog, 1)
        assert info["ok"] is True
        assert info["order"] == ["1"]

    def test_outdated_dependency_blocked(self, tmp_path):
        m = _manifest(tmp_path, plugins=[_plugin(2, "0001.0000.0000~", version="1.0.0")])
        catalog = [
            _item(1, dependencies=[_dep(2, min_sort="0001.0002.0000~", min_version="1.2.0")]),
            _item(2, version_sort="0002.0000.0000~"),
        ]
        info = deps.resolve(m, catalog, 1)
        assert info["ok"] is False
        assert [g["tool_id"] for g in info["outdated"]] == ["2"]
        # 需要一起更新：被依赖者排在前面
        assert info["order"] == ["2", "1"]

    def test_legacy_record_without_version_sort_is_unknown(self, tmp_path):
        """升级前的安装记录没有 version_sort：不能当成"满足"。"""
        m = _manifest(tmp_path, plugins=[_plugin(2, "", version="1.2.0")])
        catalog = [_item(1, dependencies=[_dep(2, min_sort="0001.0002.0000~")])]
        info = deps.resolve(m, catalog, 1)
        assert info["ok"] is False
        assert [g["tool_id"] for g in info["unknown_version"]] == ["2"]

    def test_disabled_dependency_blocked(self, tmp_path):
        m = _manifest(tmp_path, plugins=[_plugin(2, "0001.0000.0000~", enabled=False)])
        catalog = [_item(1, dependencies=[_dep(2)])]
        info = deps.resolve(m, catalog, 1)
        assert info["ok"] is False
        assert [g["tool_id"] for g in info["disabled"]] == ["2"]

    def test_optional_missing_does_not_block(self, tmp_path):
        catalog = [_item(1, dependencies=[_dep(2, optional=True)])]
        info = deps.resolve(_manifest(tmp_path), catalog, 1)
        assert info["ok"] is True
        assert [g["tool_id"] for g in info["optional_missing"]] == ["2"]

    def test_missing_dependency_without_entitlement_reported(self, tmp_path):
        catalog = [_item(1, dependencies=[_dep(2, downloadable=False)])]
        info = deps.resolve(_manifest(tmp_path), catalog, 1)
        assert info["ok"] is False
        assert info["no_entitlement"]

    def test_cycle_is_reported_not_hung(self, tmp_path):
        """服务端已拒绝环；这里兜住脏目录数据，不能让解析死循环。"""
        catalog = [
            _item(1, dependencies=[_dep(2)]),
            _item(2, dependencies=[_dep(1)]),
        ]
        info = deps.resolve(_manifest(tmp_path), catalog, 1)
        assert info["ok"] is False
        assert info["cycles"]

    def test_package_dependency(self, tmp_path):
        package = state.PackageEntry(
            tool_id="2", release_id="r2", version="1.0.0", version_sort="0001.0000.0000~"
        )
        m = _manifest(tmp_path, packages=[package])
        catalog = [_item(1, dependencies=[_dep(2)])]
        assert deps.resolve(m, catalog, 1)["ok"] is True


class TestAssertReady:
    def test_passes_with_satisfied_dependencies(self, tmp_path):
        m = _manifest(tmp_path, plugins=[_plugin(2, "0001.0000.0000~")])
        catalog = [_item(1, dependencies=[_dep(2)])]
        assert deps.assert_ready(m, catalog, 1)["ok"] is True

    def test_raises_with_code_and_data(self, tmp_path):
        catalog = [_item(1, dependencies=[_dep(2, tool_name="依赖工具")])]
        with pytest.raises(deps.DependencyError) as ei:
            deps.assert_ready(_manifest(tmp_path), catalog, 1)
        assert ei.value.code == deps.E_DEPENDENCY_MISSING
        assert "依赖工具" in ei.value.message
        assert ei.value.data["missing"][0]["tool_id"] == "2"

    def test_cycle_raises_dedicated_code(self, tmp_path):
        catalog = [
            _item(1, dependencies=[_dep(2)]),
            _item(2, dependencies=[_dep(1)]),
        ]
        with pytest.raises(deps.DependencyError) as ei:
            deps.assert_ready(_manifest(tmp_path), catalog, 1)
        assert ei.value.code == deps.E_DEPENDENCY_CYCLE


class TestUninstallWarnings:
    def test_reports_dependents(self, tmp_path):
        m = _manifest(tmp_path, plugins=[
            _plugin(1, "0001.0000.0000~"),
            _plugin(2, "0001.0000.0000~", dependencies=[{"tool_id": 1}]),
        ])
        assert deps.dependents_of(m, 1) == ["2"]
        warnings = deps.uninstall_warnings(m, 1)
        assert warnings and "2" in warnings[0]

    def test_no_dependents_no_warning(self, tmp_path):
        m = _manifest(tmp_path, plugins=[_plugin(1, "0001.0000.0000~")])
        assert deps.uninstall_warnings(m, 1) == []


class TestUpdateOrder:
    def test_dependency_updated_first(self):
        catalog = [
            _item(1, dependencies=[_dep(2)]),
            _item(2),
        ]
        assert deps.update_order(["1", "2"], catalog) == ["2", "1"]

    def test_unknown_tools_keep_relative_order(self):
        assert deps.update_order(["3", "1", "2"], []) == ["3", "1", "2"]

    def test_cycle_does_not_hang(self):
        catalog = [
            _item(1, dependencies=[_dep(2)]),
            _item(2, dependencies=[_dep(1)]),
        ]
        assert set(deps.update_order(["1", "2"], catalog)) == {"1", "2"}

class TestPlanUpdates:
    """启动器自动更新的输入：只升级已装工具，不降级，不碰底座。"""

    def _installed(self, tmp_path):
        return _manifest(tmp_path, plugins=[_plugin(1, "0001.0000.0000~", version="1.0.0")])

    def test_picks_newer_latest(self, tmp_path):
        catalog = [_item(1, version_sort="0001.0001.0000~")]
        catalog[0]["release_id"] = "r1-new"
        catalog[0]["version"] = "1.1.0"
        plan = deps.plan_updates(self._installed(tmp_path), catalog)
        assert [u["tool_id"] for u in plan["updates"]] == ["1"]
        assert plan["updates"][0]["from_version"] == "1.0.0"
        assert plan["updates"][0]["to_version"] == "1.1.0"

    def test_same_release_is_noop(self, tmp_path):
        catalog = [_item(1, version_sort="0001.0000.0000~")]  # release_id 与已装相同
        assert deps.plan_updates(self._installed(tmp_path), catalog)["updates"] == []

    def test_never_downgrades(self, tmp_path):
        catalog = [_item(1, version_sort="0000.0009.0000~")]
        catalog[0]["release_id"] = "r1-old"
        plan = deps.plan_updates(self._installed(tmp_path), catalog)
        assert plan["updates"] == []
        assert plan["skipped"][0]["reason"] == "not_newer"

    def test_skips_runtime(self, tmp_path):
        catalog = [_item(1, version_sort="0002.0000.0000~", install_kind="runtime_zip_root")]
        catalog[0]["release_id"] = "r1-rt"
        plan = deps.plan_updates(self._installed(tmp_path), catalog)
        assert plan["updates"] == []
        assert plan["skipped"][0]["reason"] == "runtime_manual"

    def test_skips_without_entitlement(self, tmp_path):
        catalog = [_item(1, version_sort="0002.0000.0000~", downloadable=False)]
        catalog[0]["release_id"] = "r1-new"
        plan = deps.plan_updates(self._installed(tmp_path), catalog)
        assert plan["updates"] == []
        assert plan["skipped"][0]["reason"] == "no_entitlement"

    def test_skips_tool_without_latest_marker(self, tmp_path):
        catalog = [_item(1, version_sort="0002.0000.0000~", is_latest=False)]
        catalog[0]["release_id"] = "r1-new"
        plan = deps.plan_updates(self._installed(tmp_path), catalog)
        assert plan["skipped"][0]["reason"] == "no_latest"

    def test_update_order_respects_dependencies(self, tmp_path):
        m = _manifest(tmp_path, plugins=[
            _plugin(1, "0001.0000.0000~"),
            _plugin(2, "0001.0000.0000~"),
        ])
        catalog = [
            _item(1, version_sort="0002.0000.0000~", dependencies=[_dep(2)]),
            _item(2, version_sort="0002.0000.0000~"),
        ]
        for item in catalog:
            item["release_id"] = f"new-{item['tool_id']}"
        plan = deps.plan_updates(m, catalog)
        assert [u["tool_id"] for u in plan["updates"]] == ["2", "1"]


class TestMissingInstalledDependencies:
    def test_reports_hard_dependency_of_installed_tool(self, tmp_path):
        m = _manifest(tmp_path, plugins=[_plugin(1, "0001.0000.0000~")])
        catalog = [
            _item(1, dependencies=[_dep(2)]),
            _item(2),
        ]
        missing = deps.missing_installed_dependencies(m, catalog)
        assert [x["tool_id"] for x in missing] == ["2"]
        assert missing[0]["needed_by"] == "1"

    def test_ignores_optional_and_satisfied(self, tmp_path):
        m = _manifest(tmp_path, plugins=[
            _plugin(1, "0001.0000.0000~"),
            _plugin(3, "0001.0000.0000~"),
        ])
        catalog = [
            _item(1, dependencies=[_dep(3), _dep(2, optional=True)]),
            _item(2),
            _item(3),
        ]
        assert deps.missing_installed_dependencies(m, catalog) == []
