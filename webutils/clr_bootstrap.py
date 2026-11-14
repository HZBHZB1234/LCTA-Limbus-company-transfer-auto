# -*- coding: utf-8 -*-
"""pythonnet / clr_loader 引导与诊断。

背景
----
- LCTA 是 Windows 专属产品,pywebview edgechromium 后端与 launcher 的
  WinForms 界面都依赖 .NET Framework(netfx)运行时。
- pythonnet 在 Windows 上默认即使用 netfx;若 netfx 加载失败,
  clr_loader 的 Release 版原生加载器会吞掉真实异常,只抛出
  "Failed to resolve Python.Runtime.Loader.Initialize" 这类无信息量报错。
- 历史上多处代码在 netfx 失败后自动切换 coreclr/mono:
  coreclr 对 edgechromium 是必然死路(WebView2.WinForms 引用 .NET Core
  WinForms 不存在的 ContextMenu),对 WinForms 直接引用同样是死路。
  因此这里**只**使用 netfx,失败时输出真实异常与修复指引,不再静默切换。
- 「来自互联网」标记(MOTW)是另一类高频成因:从浏览器下载的压缩包经资源
  管理器解压后,目录内每个文件都带 Zone.Identifier(ZoneId=3),.NET 会
  拒绝 LoadFrom(HRESULT 0x80131515),而 clr_loader 只报无信息量的
  "Failed to resolve ...Loader.Initialize"。故加载前先定向清除关键程序集
  的标记,失败后再清一次并重试,最后才输出诊断。

用法
----
    from webutils.clr_bootstrap import ensure_clr
    ensure_clr()
"""
import glob
import os
import re
import site
import subprocess
import sys
import tempfile
import winreg
from pathlib import Path

# .NET Framework 4.7.2 的注册表 Release 值(运行 pythonnet 的最低要求)
NETFX_MIN_RELEASE = 461808

_FIX_HINT = """修复指引:
  1) 若程序目录或 venv 是从网上下载的压缩包解压而来, 先清除「来自互联网」标记
     (带标记的 Python.Runtime.dll 会被 .NET 拒绝加载, 报 0x80131515「不支持操作」):
       Get-ChildItem -LiteralPath "<程序目录>" -Recurse -File | Unblock-File
  2) 重新安装已固定版本的依赖组合:
       pip install --force-reinstall --no-cache-dir pythonnet==3.0.5 clr_loader==0.2.10
  3) 检查杀毒/安全软件是否拦截了 venv 目录或 .NET 进程,将其加入白名单
  4) 确认系统已安装 .NET Framework 4.7.2 及以上版本
     (Windows 10 一般已带 4.8/4.8.1;缺失可安装后再试)
  5) 若以上均无效,请将本错误信息完整提供给开发人员"""

_PS_PROBE = r"""
$ErrorActionPreference = 'Continue'
$dll = '{dll}'
$out = '{out}'
function W($s) {{ $s | Out-File -FilePath $out -Append -Encoding UTF8 }}
Remove-Item $out -ErrorAction SilentlyContinue
W ('-- 反射探针(不经 clr_loader,直接走 .NET Framework), DLL = ' + $dll)
try {{
    $an = [Reflection.AssemblyName]::GetAssemblyName($dll)
    W ('AssemblyName 读取成功: ' + $an.FullName)
}} catch {{
    W ('!! GetAssemblyName 失败: ' + $_.Exception.GetType().Name + ' ' + $_.Exception.Message)
}}
try {{
    [Reflection.Assembly]::Load('netstandard, Version=2.0.0.0, Culture=neutral, PublicKeyToken=cc7b13ffcd2ddd51') | Out-Null
    W 'netstandard 2.0 facade(GAC)加载成功'
}} catch {{
    W ('!! netstandard facade 加载失败: ' + $_.Exception.Message)
}}
try {{
    $asm = [Reflection.Assembly]::LoadFrom($dll)
    $t = $asm.GetType('Python.Runtime.Loader', $true)
    $m = $t.GetMethod('Initialize')
    W ('类型与方法解析成功: ' + $t.FullName + '.' + $m.Name)
}} catch {{
    W ('!! 反射加载失败: ' + $_.Exception.GetType().Name + ' ' + $_.Exception.Message)
}}
"""


def _version_tuple(version):
    """'0.2.10' -> (0, 2, 10);忽略非数字段。"""
    return tuple(int(x) for x in re.split(r"[.\-+]", version) if x.isdigit())


# ---------------------------------------------------------------
# 「来自互联网」标记(MOTW)自愈
# ---------------------------------------------------------------
# 带 Zone.Identifier(ZoneId=3) 的程序集会被 .NET Framework 拒绝 LoadFrom:
#   FileLoadException: ... Operation is not supported. (HRESULT: 0x80131515)
# 内层 NotSupportedException 提示启用 loadFromRemoteSources,但**改配置无效**:
# clr_loader 用自带原生库(pyclr_*)托管 CLR 并自建 AppDomain(config_file=NULL),
# 进程级 python.exe.config 与 PYTHONNET_NETFX_CONFIG_FILE 都不会生效(实测)。
# 因此唯一可靠的修法是清掉文件标记本身。
# 通用实现见 webutils/utils/motw.py;此处刻意保持纯标准库、零包内导入,
# 保证在 CLR/日志系统可用之前就能执行。


def _clear_zone_identifier(path):
    """删除单个文件的 Zone.Identifier 备用数据流;返回是否真的删除过。"""
    if os.name != "nt":
        return False
    for candidate in (str(path) + ":Zone.Identifier",
                      "\\\\?\\" + str(path) + ":Zone.Identifier"):
        try:
            os.remove(candidate)
            return True
        except FileNotFoundError:
            return False
        except OSError:
            continue
    return False


def _clear_assembly_motw(dll_path):
    """清除 pythonnet 主程序集与 clr_loader 原生库的 MOTW;返回已清除的文件。

    第 4 段:两者任一被标记都会让 CLR 初始化失败,故一并处理。
    全程 best-effort,永不抛错。
    """
    cleared = []
    paths = [Path(dll_path)]
    site_packages = Path(dll_path).parent.parent.parent
    try:
        paths.extend(sorted(site_packages.glob("clr_loader/ffi/dlls/*/ClrLoader.dll")))
    except OSError:
        pass
    for path in paths:
        try:
            if _clear_zone_identifier(path):
                cleared.append(path)
        except Exception:
            continue
    return cleared


def _site_packages():
    """定位 site-packages,兼容标准 venv 与嵌入式 Python 部署。"""
    cands = []
    try:
        cands = list(site.getsitepackages())
    except AttributeError:
        pass
    for sub in ("Lib/site-packages", "lib/site-packages"):
        p = Path(sys.prefix) / sub
        if p.is_dir():
            cands.append(str(p))
    seen = set()
    for c in cands:
        p = Path(c)
        key = str(p).lower()
        if p.is_dir() and key not in seen:
            seen.add(key)
            yield p


def _clr_loader_version():
    """读取 clr_loader 的 dist-info 版本号,找不到返回空串。"""
    for sp in _site_packages():
        for d in glob.glob(str(sp / "clr_loader-*.dist-info")):
            m = re.search(r"clr_loader-([\d.]+)", Path(d).name)
            if m:
                return m.group(1).rstrip(".")
    return ""


def _check_dotnet_framework():
    """.NET Framework >= 4.7.2 检查;正常返回空串,异常返回说明文字。"""
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full",
        ) as key:
            release, _ = winreg.QueryValueEx(key, "Release")
    except OSError:
        return "未检测到 .NET Framework 4.x(pythonnet 需要 4.7.2 及以上)"
    if release < NETFX_MIN_RELEASE:
        return ".NET Framework 版本过旧 (Release=%d, 需要 >= %d 即 4.7.2)" % (
            release, NETFX_MIN_RELEASE)
    return ""


def get_real_exception(dll_path):
    """用 PowerShell 直接走 .NET Framework 反射,绕过 clr_loader 探测真实异常。

    clr_loader 的 Release 原生加载器会吞掉异常,这里用相同 API
    (GetAssemblyName / LoadFrom / GetType)复现加载步骤,把真实异常暴露出来。
    """
    ps_file = os.path.join(tempfile.gettempdir(), "pn_probe.ps1")
    ps_out = os.path.join(tempfile.gettempdir(), "pn_probe_out.txt")
    ps = _PS_PROBE.format(dll=str(dll_path).replace("'", "''"),
                          out=ps_out.replace("'", "''"))
    try:
        with open(ps_file, "w", encoding="utf-8-sig") as f:
            f.write(ps)
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps_file],
            capture_output=True, timeout=60,
        )
        if os.path.exists(ps_out):
            with open(ps_out, "r", encoding="utf-8-sig") as f:
                return f.read().strip()
    except Exception:
        pass
    finally:
        for p in (ps_file, ps_out):
            try:
                os.unlink(p)
            except OSError:
                pass
    return ""


def _import_clr():
    import clr
    return clr


def ensure_clr():
    """强制 netfx 并导入 clr;失败时抛出带真实原因与修复指引的 RuntimeError。

    预检:
    - Python.Runtime.dll 是否存在且非空
    - clr_loader 版本(< 0.2.8 的 netfx 加载存在已知缺陷)
    - .NET Framework >= 4.7.2
    失败时不再自动切换 coreclr/mono(对 pywebview edgechromium 与 WinForms
    均为死路),而是输出真实异常并抛错。
    """
    os.environ['PYTHONNET_RUNTIME'] = 'netfx'

    dll_path = None
    for sp in _site_packages():
        cand = sp / "pythonnet" / "runtime" / "Python.Runtime.dll"
        if cand.exists():
            dll_path = cand
            break
    if dll_path is None or dll_path.stat().st_size == 0:
        raise RuntimeError(
            "未找到有效的 Python.Runtime.dll(pythonnet 安装损坏或缺失)。\n" + _FIX_HINT)

    issues = []
    clr_loader_ver = _clr_loader_version()
    if clr_loader_ver and _version_tuple(clr_loader_ver) < (0, 2, 8):
        issues.append("clr_loader 版本过旧 (%s < 0.2.8),netfx 加载存在已知缺陷" % clr_loader_ver)
    fw_issue = _check_dotnet_framework()
    if fw_issue:
        issues.append(fw_issue)

    # 预自愈:资源管理器解压下载包会给整个目录盖上 MOTW,带标记的程序集
    # 必然加载失败。这里先定向清一次(单文件,成本极低),命中即无需再走
    # 失败-探测-报错的长路径。
    _clear_assembly_motw(dll_path)

    try:
        return _import_clr()
    except Exception as exc:
        # 导入失败后再次清除并重试一次:clr_loader 自己会加载 clr_loader 的
        # 原生库,首次清理可能只命中了已存在标记的一部分。
        healed = _clear_assembly_motw(dll_path)
        if healed:
            try:
                return _import_clr()
            except Exception:
                pass
        probe = get_real_exception(str(dll_path))
        parts = ["pythonnet(netfx) 初始化失败: %s" % exc]
        if probe:
            parts.append("clr_loader 原生层真实异常:\n%s" % probe)
        if healed:
            parts.append(
                "已清除「来自互联网」标记后重试,仍失败:%s"
                % "、".join(str(p) for p in healed))
        if issues:
            parts.append("环境检查:\n- " + "\n- ".join(issues))
        parts.append(_FIX_HINT)
        raise RuntimeError("\n\n".join(parts)) from exc
