"""launcher/patch「模组新增资产」补丁路径回归测试。

回归背景：`patch_bundle_asset` 曾改用 UnityPy 新版的关键字签名构造 ObjectReader
（assets_file/reader/path_id/type_id/serialized_type/class_id/type/byte_start/
byte_size/is_destroyed/is_stripped 共 11 个关键字），而项目依赖固定为
UnityPy==1.10.18——其 `ObjectReader.__init__` 只接受 (assets_file, reader)。
结果是所有「模组新增、原版不存在」的资产都抛
`TypeError: __init__() got an unexpected keyword argument 'path_id'`，
实测日志中 17 个 bundle 有 16 个因此失败（表现为 mod 装了但内容不生效）。
"""
import lzma

import pytest

from UnityPy.enums import ClassIDType
from UnityPy.files import ObjectReader, SerializedFile
from UnityPy.streams import EndianBinaryWriter

TEXT_ASSET = int(ClassIDType.TextAsset)
PAYLOAD = b"LCTA regression payload"


class _StubSerializedType:
    def __init__(self, class_id):
        self.class_id = class_id
        self.script_type_index = 0


class _StubSerializedFile(SerializedFile):
    """只提供补丁路径需要的属性，不调用父类 __init__（无需真实 bundle/读流）。"""

    def __init__(self, types):
        self.types = types
        self.objects = {}
        self.reader = None
        self.big_id_enabled = 0
        self.mark_changed_calls = 0

    def mark_changed(self):
        self.mark_changed_calls += 1


class _StubBundle:
    def __init__(self, serialized_file):
        self.files = {0: serialized_file}
        self.version_player = "vanilla"


class _StubEnv:
    def __init__(self, bundle):
        self._bundle = bundle


class _StubHeader:
    version = 22


def _stub_env():
    serialized_file = _StubSerializedFile([_StubSerializedType(TEXT_ASSET)])
    return _StubEnv(_StubBundle(serialized_file)), serialized_file


def _write_mod_dir(tmp_path, entries):
    """entries: {path_id: type_index}，值写成 lzma-XZ 压缩的模组资产。"""
    mod_dir = tmp_path / "assets"
    mod_dir.mkdir(exist_ok=True)
    for path_id, type_id in entries.items():
        (mod_dir / f"{path_id}.{type_id}").write_bytes(
            lzma.compress(PAYLOAD, format=lzma.FORMAT_XZ))
    return mod_dir


@pytest.fixture(autouse=True, scope="module")
def _restore_global_log_state():
    yield
    import logging

    from globalManagers.LogManager import LogManager

    LogManager._instance = None
    LogManager._initialized = False
    logging.getLogger("LCTA").propagate = True


def _install(patch, monkeypatch):
    monkeypatch.setattr(patch, "get_bundle_file", lambda env: env._bundle)


def test_patch_bundle_asset_registers_new_asset(tmp_path, monkeypatch):
    """原版不存在的资产应被构造并注册进 SerializedFile.objects。"""
    import launcher.patch as patch

    env, serialized_file = _stub_env()
    _install(patch, monkeypatch)

    patch.patch_bundle_asset(env, str(_write_mod_dir(tmp_path, {4242: 0})))

    obj = serialized_file.objects.get(4242)
    assert isinstance(obj, ObjectReader), "新增资产未注册到 objects"
    assert (obj.path_id, obj.type_id) == (4242, 0)
    assert obj.class_id == TEXT_ASSET
    assert obj.type is ClassIDType.TextAsset
    assert obj.serialized_type is serialized_file.types[0]
    assert obj.byte_size == len(PAYLOAD)
    assert serialized_file.mark_changed_calls == 1


def test_new_asset_object_is_serializable(tmp_path, monkeypatch):
    """新建对象必须能被 SerializedFile.save 序列化：write() 不抛且带上资产数据。"""
    import launcher.patch as patch

    env, serialized_file = _stub_env()
    _install(patch, monkeypatch)

    patch.patch_bundle_asset(env, str(_write_mod_dir(tmp_path, {777: 0})))

    writer, data_writer = EndianBinaryWriter(), EndianBinaryWriter()
    serialized_file.objects[777].write(_StubHeader(), writer, data_writer)

    assert PAYLOAD in data_writer.bytes
    assert len(writer.bytes) > 0


def test_unknown_type_index_is_skipped(tmp_path, monkeypatch):
    """type 索引越界时跳过该资产，不应抛异常、不注册对象。"""
    import launcher.patch as patch

    env, serialized_file = _stub_env()
    _install(patch, monkeypatch)

    patch.patch_bundle_asset(env, str(_write_mod_dir(tmp_path, {888: 9})))

    assert 888 not in serialized_file.objects
    assert serialized_file.mark_changed_calls == 0
