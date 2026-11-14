# LCTA 客户端模组管理机制分析

> **只读分析**。对象：`E:\desktop\work\LCTA-Limbus-company-transfer-auto`（代号 LCTA，Limbus Company 第三方工具箱）。
> **范围**：模组（Mod）管理链路，**不含**订阅工具（toolbox）；toolbox 仅在第 4 节作机制对照。
> **读者假设**：已熟悉订阅工具（Ed25519 签名清单 / journal 事务 / 受管区断言），但不熟悉客户端模组管理。
> 所有结论带 `路径:行号` 证据。明确区分「确实实现」与「有代码但没接线」。

---

## 0. 结论摘要

1. **模型不是「装进游戏目录」，而是「放进独立用户目录 + 启动期临时补丁游戏」**：模组落在 `%APPDATA%\Roaming\LimbusCompanyMods`（可配置），安装动作只做「解压/复制到该目录」，真正生效发生在 Launcher 每次启动游戏时（`launcher/game_launch.py:111-140`）。
2. **生效有 5 条并行通道**：zip→`.carra2` 差分转换 + carra2 解压展平写 Unity 缓存 `__data`（`launcher/patch.py:50-425`）、整包 `.bank` 覆盖游戏音频目录（`launcher/sound.py:104-113`）、`.rebank` 差分补丁 bank（`launcher/bankmod.py:86-167`）、文本 JSON jsonpatch 进 `lang/`（`launcher/changes.py:24-52`）、`.staticmod` 静态数据补丁（`launcher/staticmod.py:528-598`）。退出/下次启动靠 `.bak`、`__original`、本地备份还原。
3. **启停状态不写配置文件**，而是**文件名后缀 `_disable` 的重命名**（`webutils/packages/manage.py:165-174`）；Launcher 侧用「任一路径段以 `_disable` 结尾即禁用」过滤（`launcher/modcache.py:101-108`）。
4. **下载来源是自建镜像站** `https://mods.lcta.top`（可配置）；`webui/nexus/*` 只是内嵌 Nexus 网页的油猴脚本，**不在模组链路**，且仅隐藏调试页可达。
5. **下载器是随包 aria2c（loopback RPC + secret），失败降级 requests 流式**；aria2 层有断点续传（`--continue=true`），但**模组链路主动删 `.aria2` 残片，等于放弃续传**（`function_mod_mirror.py:449-454`）。
6. **完整性校验是可选的**：`size`/`sha256` 由被内嵌的远程网页传入，缺省即整段跳过（`function_mod_mirror.py:122-130,421-422`）；且页面同时决定 URL 与期望哈希，校验只防传输损坏，**不防镜像站被篡改**。
7. **覆盖安装 = 先 `rmtree` 旧目录再解压**，无备份 / 无 journal / 无回滚（`function_mod_mirror.py:386-394`）——这是整条链路最脆弱的一步。
8. **无模组版本/更新判断、无批量更新、无 `mod.json` 元数据、无缩略图、无模组间冲突检测**（见第 6 节关键词与检索证据）。
9. 对比订阅工具，模组链路**完全没有** Ed25519 签名清单、逐文件 sha256 清单、journal 事务回滚、受管区断言、游戏运行检测、zip 炸弹上限（第 4、5 节）。
10. **汉化包与模组不共用目录也不共用开关**：汉化包装在游戏目录 `LimbusCompany_Data\lang`（禁用态为 `_lang`），模组装在用户 Roaming 目录；启停同为「改名」，但一个是**目录级改名**、一个是**文件/目录后缀改名**。

---

## 1. 全景链路（下载 → 落盘 → 安装 → 启停 → 更新 → 卸载）

```
[镜像站窗口 mods.lcta.top/?embed=lcta]
        │  网页 JS 调用 window.pywebview.api
        ▼
ModMirrorWindowAPI.modMirrorRequest(msg)        webui/mod_mirror_api.py:61-68
        │  仅校验 msg["source"] == "lcta-mod-mirror"（字符串，非签名）
        │  主窗口 evaluate_js 派发 CustomEvent('lcta-mod-download')
        ▼
主窗口监听 lcta-mod-download                     webui/js/mod-mirror.js:7-24
        │  pywebview.api.mod_mirror_request(payload, modal.id)
        ▼
LCTA_API.mod_mirror_request                      webui/app_api/mod_mirror.py:46-56
        ▼
webutils.function_mod_mirror.mod_mirror_request  webutils/function_mod_mirror.py:403-481
        │
        ├── kind="standard" ──────────────────────────────────────────────┐
        │     staging = %LOCALAPPDATA%\LCTA\mod-mirror\<id>_standard\      │ :56-60,425
        │     dest    = <id>_<safe_name>.zip                              │ :432
        │     url     = <base>/api/mods/<target_type>/<id>/standard       │ :426
        │                                                                 │
        └── kind="file" ──────────────────────────────────────────────────┤
              save_dir = 系统「下载」目录（不安装）                        │ :428
              url      = <base>/api/mods/<tt>/<id>/download?file_id=...     │ :430
                                                                          │
  ┌───────────────────────────────────────────────────────────────────────┘
  ▼
下载：_download_aria2 → aria2c（先 requests 解析 302 拿 CDN 直链）   :259-308, 311-326
      失败/不可用 → _download_fallback → download_with（requests 流式） :329-335 → utils/net.py:34-81
      进度 5→85，取消时 client.remove(gid) 防污染                     :284-302
  ▼
校验：_verify_expected(dest, size, sha256) —— size/sha256 为 0/空即跳过  :122-130, 458-459
  ▼
安装（kind=standard）：_install_standard                             :381-396
      rmtree(mod_root/<name>)、rmtree(mod_root/<name>_disable)  ← 先删，无备份
      _extract_zip_safe → 成员名净化 + testzip + 逐成员落盘            :133-155
      _flatten_single_root（单根目录内容上提一层）                     :342-349
  ▼
模组目录：%APPDATA%\Roaming\LimbusCompanyMods\<safe_name>\            packages/manage.py:131-140
  （同目录也接受：拖放安装 webutils/drop/*、用户手动放文件、音频工具页 .bank→.rebank 转换）
  ▼
════════════════ 以上是「安装」；以下才是「生效」，每次启动游戏执行 ════════════════
  ▼
Launcher PHASE_PREPARE_MOD（受 launcher.work.mod 开关，默认 false）  launcher/main.py:54,323-324
  ▼  launcher/game_launch.py:50-143
 1) 预清理残留：patch.cleanup_assets / sound.restore_sound /
    staticmod.restore_staticmods / changes.cleanup_patch          :22-38,104
 2) zip → .carra2（Lunartique 格式，sha256 缓存）；非该格式整包解压到模组目录根  patch.py:50-140
 3) 文本 JSON 补丁 → 游戏 lang/*.json（首次写前 .bak）             changes.py:24-52
 4) .carra2 解压展平到临时目录（sha256 缓存）                        patch.py:150-229
 5) 备份 Unity 缓存 __data→__original，注入资源后 LZ4 重打包回写（缓存+单 bundle 回滚） patch.py:323-425
 6) .staticmod 静态数据补丁（launcher.work.staticmod + RiskGate 双开关）  staticmod.py:528-598
 7) .bank 整包覆盖 + .rebank 差分补丁（.bank.bak 备份，后台线程等游戏退出后还原）
                                            sound.py:98-147,167-179; bankmod.py:86-167
  ▼
游戏退出 / 下次启动 → _do_cleanup_assets 还原 __original / .bank.bak / .json.bak / staticmod 备份
                                          game_launch.py:22-38,105,146-152; sound.py:136-165
```

**启停 / 卸载 / 更新**（不进入上图，全是文件系统操作）：

```
启停  toggle_mod(name, enable) → rename  <name> ↔ <name>_disable      packages/manage.py:165-174
列表  fing_mod() → glob *.carra2/*.bank/*.rebank/*.zip/*.json/*.staticmod + 目录，分 able/disable
                                                                    packages/manage.py:142-163
卸载  delete_mod(name, enable) → rmtree / unlink（无用户数据保留）    packages/manage.py:176-188
更新  不存在（无版本元数据、无远端版本查询、无批量更新）
```

---

## 2. 各环节详解

### 2.1 数据来源与下载

#### 2.1.1 来源：自建镜像站，非直连 Nexus

- 默认站点与可配置键：`webutils/function_mod_mirror.py:38-40`
  ```python
  AUTH_KEY = "ui_default.mod_mirror.auth"
  CONFIG_KEY = "ui_default.mod_mirror"
  DEFAULT_BASE_URL = "https://mods.lcta.top"
  ```
  `:47-53` 读 `base_url` 并 `rstrip("/")`。
- 站点以**独立 pywebview 窗口内嵌线上页面**呈现，不是本地 UI：`webui/app_api/mod_mirror.py:28-33`
  ```python
  window = webview.create_window("LCTA - Mod 镜像站", url=f"{base_url()}/?embed=lcta",
                                 width=1280, height=860, resizable=True, text_select=True, js_api=api)
  ```
- 网页 → 宿主只有两条桥（`webui/mod_mirror_api.py`）：
  - **登录态持久化** `modMirrorBridge(action, data)`：`get-auth` / `save-auth` / `clear-auth`（`:35-46`）
  - **下载请求转发** `modMirrorRequest(msg)`：`:61-68`
    ```python
    if not isinstance(msg, dict) or msg.get("source") != "lcta-mod-mirror":
        return {"ok": False, "message": "无效的请求来源"}
    return self._forward_event("lcta-mod-download", msg.get("payload") or {})
    ```
    `_forward_event` 用 `main_window.evaluate_js(...)` 派发 `CustomEvent`（`:50-59`）。
  - **`source` 是网页自己填的字符串常量，不是密码学证明**（见 5.2 R4）。
- 主窗口侧接收：`webui/js/mod-mirror.js:7-24`，`payload.kind === 'standard'` 决定弹窗标题，随后 `pywebview.api.mod_mirror_request(payload, modal.id)`（`:13`），`result.message === '已取消'` 时走 `modal.cancel()`（`:16-18`）。
- 入口按钮：`webui/index.html:77-79`（`onclick="openModMirror()"`）→ `webui/js/mod-mirror.js:27-40` → `open_mod_mirror()`。

#### 2.1.2 `webui/nexus/*` 与模组管理**无关**（必须澄清）

- 四个文件是**油猴（UserScript）脚本**，头部带元数据块：`webui/nexus/cn.js:1-16`、`webui/nexus/skip.js:1-21`、`webui/nexus/simulation.js:1-11`。
- `cn.js:1475-1499` 确有「Nexus 直接下载」逻辑，但那是**在网页上下文里 `fetch` + `location.href` 跳转**：
  ```js
  const response = await fetch('https://www.nexusmods.com/Core/Libs/Common/Managers/Downloads?GenerateDownloadUrl', {...});
  const data = await response.json(); location.href = data.url;
  ```
  全仓库 `webui/nexus/*` 内**没有任何 `pywebview.api` 调用**（grep `pywebview|modMirror` 无命中），因此与 LCTA 下载器/安装器零交互。
- 唯一入口是隐藏调试页：`webui/app_api/windows.py:15-16`（`startTest` 开 nexusmods 窗口）、`:18-30`（`eval_skip` / `sign_eval_js` 注入脚本），按钮 `webui/sections/test.html:10,15,20`，而 `test` 区块默认隐藏（`webui/index.html:144` `data-hidden-default="1"`）。
- 且 `cn.js`/`skip.js`/`dict.js` **未纳入版本控制**：`.gitignore:3-4`（`webui/nexus/*.js`，`!webui/nexus/simulation.js`），实测 `git ls-files webui/nexus/` 仅 `simulation.js`，本地 `dict.js` 为 0 字节。
- **判定**：属「Nexus 网页体验增强（去等待 / 中文化）」的实验代码，**有代码、有（隐藏）入口、未接线到模组链路**。模组下载 100% 走镜像站 API。

#### 2.1.3 下载器选择：aria2c 优先，requests 流式降级

- aria2c 定位：`resource_updater/core.py:97-107`
  ```python
  candidates.append(Path(resource_root) / "tools" / "aria2" / "aria2c.exe")
  candidates.append(Path(__file__).resolve().parent.parent / "tools" / "aria2" / "aria2c.exe")
  found = shutil.which("aria2c"); return Path(found) if found else None
  ```
- 模组链路维护**自己的 aria2c 单例池**（引用计数 + 30s 空闲回收）：`webutils/function_mod_mirror.py:164-257`
  - 获取（进程死了重建、读 `ui_default.aria2_dl.jobs/connection_limit`）：`:173-202`
  - 空闲回收（2s 巡检，`_aria2_users <= 0` 才 stop）：`:220-243`（注释显式说明两锁之间新下载会抢实例的竞态）
  - 退出：`:245-256`，`webui/app.py:86` atexit 注册。
- aria2c 启动参数（**多连接 + 续传 + 重试**）：`webutils/function_aria2_downloader.py:74-86`
  ```python
  "--no-conf", "--enable-rpc", "--rpc-listen-all=false", "--rpc-listen-port={}",
  "--rpc-secret={}", "--max-concurrent-downloads={}", "--max-connection-per-server={}",
  "--split=16", "--min-split-size=4M",
  "--continue=true", "--file-allocation=none",
  "--max-tries=5", "--retry-wait=3",
  ```
  RPC 只监听 loopback + 随机 secret（`:59-61,71-77`），子进程绑定父进程寿命（`:101-103`，`ChildProcessJob`）。
- **302 直链解析**（因为站点 API 域会拦 aria2c 的 TLS 指纹）：`webutils/function_mod_mirror.py:311-326`
  ```python
  r = requests.get(url, timeout=15, stream=True, allow_redirects=False, headers={"User-Agent": "..."})
  if r.status_code in (301, 302, 303, 307, 308) and loc:
      return requests.compat.urljoin(url, loc)
  return url
  ```
  测试覆盖：`tests/test_mod_mirror.py:308-373`。
- 下载轮询与分支：`webutils/function_mod_mirror.py:259-308`
  - `complete` → 进度 85 返回 True（`:273-276`）
  - `error` → **降级内置下载器**（`:277-281`）
  - `removed` → 抛 `CancelRunning`（`:282-283`）
  - `Aria2Error`（找不到 aria2c / 启动超时）→ 降级（`:303-305`）
  - 0.5s 轮询、进度映射 `5 + pct*80/100`（`:284-294`）
- 降级下载器：`webutils/utils/net.py:34-81`
  - `verify=True`（TLS 校验开启，`:41-42`）
  - **无 Range 续传**：`:54` `with open(save_path, 'wb')` 直接截断写
  - 分块停滞超时：`_iter_with_timeout`（`:24-31`，60s 无数据即 `TimeoutError`）
  - 只做大小校验且需 `size > 0`：`:69-74`

#### 2.1.4 断点续传 / 限速 / 取消 / 错误处理 / 临时目录

| 能力 | 结论 | 证据 |
|---|---|---|
| 断点续传（aria2 层） | **实现**：`--continue=true` | `function_aria2_downloader.py:81` |
| 断点续传（模组链路） | **主动放弃**：下载前删 `.aria2` 残片与目标文件，强制从零 | `function_mod_mirror.py:449-454` |
| 断点续传（降级器） | **不存在**（无 Range 头，`'wb'` 截断写） | `webutils/utils/net.py:54` |
| 限速 | **不存在**。aria2 启动参数无 `--max-overall-download-limit`；`change_global_option()` 有封装但**全仓库无调用点** | `function_aria2_downloader.py:74-86`；定义 `:232-233`；grep `max-overall｜download_limit｜限速` 无模组相关命中 |
| 取消（aria2 路径） | **实现且较细**：每轮 `check_running`；取消时**同步 `client.remove(gid)`**，避免后台继续写目标文件污染下次下载 | `function_mod_mirror.py:268,282-283,295-302` |
| 取消（降级路径） | 每块 `check_running` 抛 `CancelRunning`；但**已写入的部分文件不删除**（靠后续 size/sha 兜底） | `utils/net.py:56-58,76-77` |
| 取消的 UI 表现 | `function_mod_mirror` 返回 `{"success": False, "message": "已取消"}`；前端据此 `modal.cancel()` | `function_mod_mirror.py:474-476`；`js/mod-mirror.js:16-18` |
| 错误处理 | 统一 `try/except` → `log_error` + 进度归零 + 返回失败字典；**无应用层重试**（仅 aria2 `--max-tries=5`） | `function_mod_mirror.py:477-481` |
| 临时/缓存目录 | staging：`%LOCALAPPDATA%\LCTA\mod-mirror\<target_id>_standard\<target_id>_<name>.zip`，**每个 mod 一个子目录，无清理、无 GC、无容量上限** | `function_mod_mirror.py:56-60,425,432` |
| 缓存复用 | 仅当 payload 带 `sha256` 且 staging 已有同内容文件才跳过下载 | `function_mod_mirror.py:438-446` |
| 失败残留 | 失败/取消后 staging 文件**保留**（无清理），下次下载前才删 | `:449-454`（删除发生在「下一次」） |

> 文档与实现的小偏差：`webui/guide/mod-mirror.md:34` 说「取消后临时文件会留在暂存目录，下次下载自动覆盖」，实现是**下次下载前显式删除残片**（`:449-454`），语义等价但表述不准。

### 2.2 落盘与目录布局

#### 2.2.1 受管区在哪

- 默认：`%APPDATA%\Roaming\LimbusCompanyMods` — `webutils/packages/manage.py:131-132`
  ```python
  def get_default_mod_path():
      return Path.home() / 'AppData' / 'Roaming' / 'LimbusCompanyMods'
  ```
- 可配置：`ui_default.manage.mod_path` — `:134-140`
- Launcher 侧同源读取（带存在性校验后回退默认，并写入 `os.environ['mod_path']`）：`launcher/modfolder.py:5-11`
- UI 配置：`webui/sections/manage.html:57-65`；映射 `webui/js/core.js:269`（`'installed-mod-directory': 'ui_default.manage.mod_path'`）；浏览/清空 `webui/js/modals.js:409-428`。
- **关键差异**：这是**用户级目录，不在游戏目录内**，因此整条模组链路**没有「受管区」概念**（对比订阅工具 `.lcta-toolbox`，见第 4 节）。

#### 2.2.2 命名规则与 mod 目录结构

- 镜像站标准版目录名 = **网页传入的 `name`** 经 `_safe_filename` 清洗：`webutils/function_mod_mirror.py:92-97,419-420,384`
  ```python
  _INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
  s = _INVALID_FILENAME.sub("_", str(name or ""))
  s = re.sub(r"\s+", "_", s).strip("._")[:120]
  ...
  target = mod_root / mod_name          # 直接一层目录，无层级
  disable = mod_root / f"{mod_name}_disable"
  ```
- 落盘 zip 名：`f"{target_id}_{name}.zip"`（`:432`）。
- 包内布局**无强制结构**；解压后若只有一个根目录则内容上提一层：`:342-349`
  ```python
  entries = list(target.iterdir())
  if len(entries) == 1 and entries[0].is_dir():
      for child in list(inner.iterdir()): shutil.move(str(child), str(target / child.name))
      shutil.rmtree(inner)
  ```
- Launcher 实际消费的文件形态（`fing_mod()` 枚举）：`webutils/packages/manage.py:142-163`
  ```python
  *.carra2 / *.bank / *.rebank / *.zip / *.json / *.staticmod  + 所有非 _disable 目录
  禁用态：同名 + _disable（文件与目录都支持）
  ```
  Launcher 递归匹配 + 过滤：`launcher/modcache.py:101-108`
  ```python
  for p in sorted(Path(root).rglob(pattern)):
      if any(seg.endswith("_disable") for seg in p.parts): continue
  ```

#### 2.2.3 `mod.json` / 元数据 / 图片资源

- **`mod.json` 不存在**。全仓库无任何写入模组元数据文件的代码。grep `mod.json|mod_manifest|mods.json` 仅命中三处**别的东西**：
  - `launcher/staticmod.py:176` — `.staticmod` 包内 `manifest.json`（静态数据格式自带，非模组元数据）
  - `webutils/bank/rebank.py:24` — `.rebank` 包内 `rebank.json`（音频差分格式自带）
  - `webutils/drop/handlers/archive_mod.py:71,74` — `mod_info.json` **仅作「浮士德启动器格式」识别标记**，不读取字段、不持久化
- 因此**无版本号、无作者、无来源 ID（Nexus mod id）、无安装时间、无安装清单、无文件哈希**。安装成功只返回一个目录路径：`function_mod_mirror.py:467-471`
  ```python
  return {"success": True, "message": message, "mod_dir": str(mod_dir)}
  ```
- **图片/缩略图不存在**：grep `cover|thumb|preview|avatar` 在模组链路零命中（命中的是 toolbox `cover_url`、cg `preview_cg`、字体预览，均无关）。
- 唯一的「包内容说明」是一句按扩展名计数的人类可读摘要：`webutils/function_mod_mirror.py:352-378`
  ```python
  counts = {"carra2":0,"bank":0,"rebank":0,"json":0,"wav":0,"other":0}
  ...
  if not mod_kinds: return "警告：包内未识别到可加载的模组文件（carra2/bank/rebank/json）"
  ```
  注意：这只是**提示字符串**，不阻止安装（`:461-466`）。

### 2.3 安装 / 启用 / 停用 / 卸载

#### 2.3.1 「安装」= 只落模组目录，不复制进游戏

- 镜像站标准版：`webutils/function_mod_mirror.py:381-396`
  ```python
  def _install_standard(zip_path: Path, mod_name: str, modal_id: str) -> Path:
      mod_root = Path(get_mod_path()); mod_root.mkdir(parents=True, exist_ok=True)
      target = mod_root / mod_name
      disable = mod_root / f"{mod_name}_disable"
      # 覆盖安装：先移除旧同名目录（含禁用态残留）
      for old in (disable, target):
          if old.exists():
              if old.is_dir(): shutil.rmtree(old)
              else: old.unlink()
      _extract_zip_safe(zip_path, target, modal_id)
      _flatten_single_root(target)
      return target
  ```
- 拖放安装同语义：`webutils/drop/handlers/archive_mod.py:40-59`（zip → `extract_zip_smartly` 到 `mod_path`；目录 → `shutil.copytree`），单文件 → `webutils/drop/handlers/copy_mod.py:19-29`。
  拖放链路：`webui/app_api/drops.py:9-23`（`handle_dropped_files` 识别）→ `:36-47`（`eval_dropped_files` 执行）→ `webutils/drop/eval_files.py:48-143`（按 `REGISTRY` 分派）→ 注册表 `webutils/drop/handlers/__init__.py:59-67`。
- **安装不触碰 BepInEx**：BepInEx 加载树归订阅工具所有，模组链路从不写 `BepInEx/plugins`。
  - `launcher/game_launch.py:254-261`：「BepInEx 框架本身已移交『订阅工具』底座（Zylarnex）管理，cheat core 不再自己挂载」
  - `webutils/toolbox/install.py:9-15`：不变量「停用 = 移出 BepInEx 加载树」
  - grep `BepInEx` 在模组链路（`function_mod_mirror`/`drop`/`launcher.patch|sound|bankmod|changes`）**零命中**。
- 因此模组机制是「**只落 mod 目录，交给 Launcher 自己的 loader 在启动期打补丁**」，不是「写插件」也不是「复制进游戏」。

#### 2.3.2 「启用 / 停用」= 文件名后缀改名（不写配置）

- `webutils/packages/manage.py:165-174`
  ```python
  def toggle_mod(mod_name: str, enable):
      mod_path = get_mod_path()
      safe_join_path(mod_path, mod_name)                       # 防路径穿越
      mod = mod_path / (mod_name if not enable else f'{mod_name}_disable')
      if mod.exists():
          shutil.move(mod, mod_path / (mod_name if enable else f'{mod_name}_disable'))
          return True
      return False
  ```
- 消费侧过滤：`launcher/modcache.py:101-108`（任一路径段以 `_disable` 结尾即禁用，故**整个禁用目录内的所有文件都失效**）；`.staticmod` 有同规则独立实现：`launcher/staticmod.py:163-170`。
- 已知坑（已修，值得记住）：`webutils/packages/manage.py:159-162` 注释指出必须用 `removesuffix('_disable')`，用 `rstrip` 会把 `_disable` 当字符集，`coolmod_disable → coolmo`，导致禁用态无法重新启用。
- 桥接与 UI：`webui/app_api/packages.py:190-199`（`toggle_mod`）、`:180-188`（`find_installed_mod`）；前端 `webui/js/list-managers.js:766-795`（`find_installed_mod` 返回 `able`+`disable` 两列表，合并渲染，`able` 项默认 enabled），`toggleMod` 调 `pywebview.api.toggle_mod(item, enable)`（`:789-791`）。
- **状态存在哪**：**不存在配置文件里**，状态就是磁盘上的文件名。优点：无状态漂移；缺点：用户手改文件名即改状态，且**无审计、无来源标记**。

#### 2.3.3 「卸载」= 直接删，不区分用户数据

- `webutils/packages/manage.py:176-188`
  ```python
  def delete_mod(mod_name: str, enable):
      safe_join_path(mod_path, mod_name)
      mod = mod_path / (mod_name if enable else f'{mod_name}_disable')
      if mod.is_dir(): shutil.rmtree(mod); return True
      mod.unlink(); return True
  ```
- 桥接：`webui/app_api/packages.py:201-210`；UI 有二次确认：`webui/js/list-managers.js:797-818`（`确定要删除模组 "..." 吗？此操作不可撤销。`）。
- **不保留任何用户数据**：无「保留配置」语义（对比订阅工具 `PluginEntry.keep_config`，`webutils/toolbox/state.py:145,175`）。模组本身也没有独立配置区，删目录即全删。
- 相关但相邻的破坏性路径（`clean_mods`）：`webui/app_api/packages.py:339-342`
  ```python
  if clean_mods:
      roaming_path = Path.home() / "AppData" / "Roaming"
      mods_path = roaming_path / "LimbusCompanyMods"     # ← 硬编码，忽略 ui_default.manage.mod_path
      custom_files.append(mods_path)
  ```
  随后进入 `webutils/packages/clean.py:91-110`（对目录下每项调 `clear_by_mod`）→ `:115-177`（读 zip 内 `Assets/Installation/...` 结构推断要删的 Unity 缓存目录，用 `safe_join_path` 限制在 `Unity/ProjectMoon_LimbusCompany` 内，`:155`）。

#### 2.3.4 冲突检测

- **模组间冲突检测不存在**。grep `conflict|冲突` 在模组链路零命中；命中的全是别处：
  - 订阅工具 GUID 冲突：`webutils/toolbox/state.py:333-342`、`webutils/toolbox/install.py:290-294`
  - fancy 规则互斥：`webutils/fancy/builtin_data.py:76,112`
  - 作弊插件动作名冲突：`webutils/cheat_plugins.py:45-58`
  - 订阅工具设备密钥冲突：`webui/app_api/toolbox.py:126-132`
- 模组资源冲突是**无条件最后写胜出，但顺序由文件体积决定**：`launcher/patch.py:168-170`
  ```python
  ordered = [os.path.normpath(p) for p in sorted(carra_files, key=mod_file_size, reverse=True)]
  ```
  即**大包覆盖小包**，无任何提示（`:212-220` 串行 copyfile）。
- **唯一的跨模组冲突处理**在音频：整包 `.bank` 覆盖时先备份 `.bak`（`launcher/sound.py:108-113`），同 bank 的 `.rebank` 检测到 `.bak` 已存在就跳过（`launcher/bankmod.py:120-123`「已被整包 .bank 模组覆盖，跳过」）。
- 同一 bank 的多个 `.rebank` 按文件名排序依次应用（`launcher/bankmod.py:111-112`），失败即整 bank 回滚（`:160-164`）。

### 2.4 更新与版本

#### 2.4.1 「有更新」判断：**不存在**

- grep `mod_update|update_mod|check_mod|installed_version|has_update` 的**模组相关命中为零**：
  - `has_update` 只在应用自身更新：`webutils/update.py:407-469`、`webui/app_api/update.py:24-70`
  - `installed_version` 只在订阅工具依赖门禁：`webutils/toolbox/deps.py:140-141`
- 唯一的「版本」痕迹属于**应用与汉化包**，与模组无关：
  - `launcher/updates.py:33-51`：`launcher.last_install.{llc,ourplay,machine}` 记录汉化包最后版本
  - `:162-165,184-187,217-220`：`return last_version != self.latest_version` —— **字符串不等即更新**，非语义版本比较
  - 应用自身才用逐段整数比较：`webutils/update.py:84-103`（`_version_tuple` + `latest > current`）
- 模组侧只有**内容寻址复用**（免重复计算，不是更新判断）：
  - staging 同 sha256 跳过下载：`function_mod_mirror.py:438-446`
  - carra2 转换缓存：`launcher/patch.py:108-119`
  - carra2 解压缓存：`launcher/patch.py:180-198`
  - bundle 重打包缓存：`launcher/patch.py:376-385`
  - rebank 补丁/导出缓存：`webutils/bank/rebank.py:35-58`、`launcher/bankmod.py:126-146`

#### 2.4.2 批量更新：**不存在**

- 模组列表 UI 只有「刷新 / 打开文件夹 / 删除选中 / 单条启停」：`webui/sections/manage.html:73-95`、`webui/js/list-managers.js:766-818`。无「全部更新」按钮、无后端对应方法。
- 音频工具页有**批量格式转换**（`.bank`→`.rebank`）：`webui/js/bank.js:397-434`（逐个调 `bank_convert_mod`），那是格式批处理，不是版本更新。

#### 2.4.3 更新失败回滚

- **模组安装路径无回滚**：旧目录已在解压前被删（`function_mod_mirror.py:386-392`）。解压失败/取消 → 用户丢掉原可用模组（见 5.1 R1）。
- **应用自身更新也无文件级回滚**，且更激进：`webutils/update.py:257-284`
  ```python
  for item in APPLICATION_PATH.iterdir():
      if item.is_file(): item.unlink()
      elif item.is_dir() and not item.name == 'venv': shutil.rmtree(item)
  for item in source_dir.iterdir(): ... shutil.copy / copytree ...
  ```
  失败时仅还原「待执行依赖操作记录」：`webutils/update.py:353-375`、`webui/app_api/update.py:155-174`、`webutils/drop/handlers/update.py:87-90`。
- **Launcher 侧反而有细粒度回滚**（这部分做得好，值得与订阅工具类比）：
  - 单 bundle 补丁失败回滚 `__original`：`launcher/patch.py:403-409`
  - `.rebank` 失败回滚 `.bak`：`launcher/bankmod.py:160-164`
  - 音频校验等待超时回填备份：`launcher/sound.py:86-96`
  - 退出/下次启动统一还原：`launcher/game_launch.py:22-38,105,146-152`；`launcher/sound.py:136-165`；`launcher/patch.py:232-252`；`launcher/staticmod.py:687-724`

### 2.5 标准化 / 格式转换（这条链路是模组的**核心机制**，不是可选优化）

> 全部在 `launcher/` 内，与主项目按 GPL 隔离（`docs/architecture.md:51`：「launcher/ 基于 LimbusModLoader（GPL-3.0）……与主项目在代码层面完全隔离」）。

#### 2.5.1 zip → `.carra2`（Lunartique 差分格式）

- 判定：zip 内存在同时含 `Uninstallation`/`Installation` 的根，且 `Uninstallation` 下至少一个 `__data`：`launcher/compress.py:10-46`
  ```python
  def is_lunartique_zip(zip_path: str) -> bool:
      try:
          with ZipFile(zip_path, "r") as z:
              return len(scan_lunartique_data(z, "Uninstallation")) > 0
      except Exception: return False
  ```
- 转换（逐对象差分 + XZ 压缩，只保留与原版不同的对象）：`launcher/compress.py:49-83`
  ```python
  if vanilla_dict.get(key) == xxh128(data).digest(): continue
  key += f".{obj.type_id}"
  z_f.write(lzma.compress(data, preset=9, format=lzma.FORMAT_XZ))
  ```
- 调度与缓存：`launcher/patch.py:50-140`
  - 缓存键 = 源 zip 的 sha256，产物 `<sha256>.carra2`（`:108-119`）
  - 产物复制回模组目录 `<zip名>.carra2`，**删除源 zip**（`:121-125`）
  - **非 Lunartique 格式不走转换**，而是整包解压到模组目录根并删源 zip（`:99-106`）
    ```python
    with ZipFile(mod_zip) as z: z.extractall(mod_zips_root)
    os.remove(mod_zip)
    ```
  - 多线程：`launcher/patch.py:132-139`（`ThreadPoolExecutor`，线程数 `launcher/game_launch.py:41-47`，`launcher.work.mod_threads` 1-10 默认 5）

#### 2.5.2 `.carra2` 解压展平 → 临时资源目录

- `launcher/patch.py:150-229`：按 `*.carra*` 收集 → sha256 解压缓存（`:180-198`）→ `rglob` 拷到 `mod_asset_root`（`:212-220`）。
- 展平语义：`<account>/<bundle>/<path_id>.<type_id>` 上移一级丢弃 bundle 段（`:194-198`）。
- `mod_asset_root` 是**每次启动的临时目录**：`launcher/game_launch.py:118`（`tempfile.mkdtemp()`），收尾 `rmtree`（`:131`）。

#### 2.5.3 写入游戏（bundle 补丁）

`launcher/patch.py:323-425`，每个 Unity 缓存 bundle 目录：

1. 备份：`os.replace(bundle_path, new_path)` → `__original`（`:373`）
2. 缓存键 = `sha256(原版 xxh128 + 模组树摘要 + 'lz4')`（`:376-380`）
3. 命中 → 直接 `copyfile(cache_file, bundle_path)`（`:381-385`）
4. `UnityPy.load` → `patch_bundle_asset` 注入对象（`:387-388`；注入实现 `:255-309`，`obj.set_raw_data(lzma.decompress(..., FORMAT_XZ))`）
5. `bundle.version_player = "limbus_modded"`（`:392`）→ LZ4 重打包（`_save_bundle` `:311-320`，失败回退 `packer="original"`）→ `atomic_write`（`:394`）
6. 失败 → 回滚 `__original`（`:403-409`）

还原：`launcher/patch.py:232-252`（`cleanup_assets`；用 `version_player != "limbus_modded"` 判断是否本工具所改，`__original` 回填）。

#### 2.5.4 音频标准化：整包 `.bank` 覆盖 + `.rebank` 差分补丁

- 整包覆盖：`launcher/sound.py:98-147`
  - 先 `wait_for_validation()`：删最小 bank 等游戏重新校验生成（超时回填备份）`:76-96`
  - 目标 `.bank` 先改名 `.bank.bak` 再 `copyfile`（`:108-113`）
  - 后台线程等游戏退出 → `restore_sound()` + `patch.cleanup_assets()`（`:124-147`）
- `.rebank` 差分：`launcher/bankmod.py:86-167`（按 `base_bank` 分组、内容摘要缓存、`.bak` 备份、失败回滚 `:160-164`）
  - `base_bank` 来自 zip 内 `rebank.json`（**不可信输入**），已做 basename 校验：`:104-109`
    ```python
    if not base or os.path.basename(base) != base or "/" in base or "\\" in base:
        _log_manager.log("* 非法 base_bank 名称，跳过: %s" % base)
    ```
- WebUI 侧同源实现（导出 / 转换 / 补丁）：`webutils/function_bank.py:258-402`，桥接 `webui/app_api/bank.py:30-42`，UI `webui/js/bank.js:337-434,476-479`
  - 整包 `.bank` → `.rebank`（以游戏当前 bank 为原版；`keep_original=False` 时把 `.bank` 改名 `.bank_disable`）：`webutils/function_bank.py:284-346`（`:340-343`）
- 外部原生依赖（`ctypes.CDLL`）：`webutils/bank/dlls.py:179-180`；自动下载：`webutils/bank/dlls.py:19-38` → `webutils/function_bank.py:86-127`

#### 2.5.5 `.staticmod`（静态数据补丁）

- 格式常量 `FORMAT = "staticmod/v1"`：`launcher/staticmod.py:66`
- 包解析与校验：`launcher/staticmod.py:173-185`（读 zip 内 `manifest.json`，`format` 不匹配即拒）
- 应用：`:528-598`（`apply_staticmods`）；单包应用 `:601-685`（解包→改 TextAsset→重打包→算 CRC→双写 `__data`+`__info`）
- 还原：`:687-724`（从 `%LOCALAPPDATA%/LCTA/staticmod-backup/<outer>/<inner>/` 回填，`:497-500`）
- **双开关**：配置 `launcher.work.staticmod`（默认 **false**，`config_default.json:120`）+ 前端 RiskGate 风险须知（`webui/js/risk-gate.js:28-33`，`consentKey: 'staticmod.disclaimer_accepted'`）；未启用时 `apply_staticmods` 直接返回 disabled，但 `restore_staticmods` 不受开关影响（`:528-552`）

#### 2.5.6 文本 JSON（含「非预期 JSON」）

- 主通道：`launcher/changes.py:24-52`
  ```python
  lang_path = Path(game_path).parent / "LimbusCompany_Data/lang"
  for lang_patch in enabled_mod_files(mod_path, "*.json"):
      patch_data = json.load(...)
      for _lang_file in patch_data.get('patchs', {}):
          lang_file = lang_path / _lang_file            # ← 未做路径净化（见 5.3 R5）
          if not lang_file.exists(): continue
          if not lang_file.with_suffix(".bak").exists():
              shutil.copyfile(lang_file, lang_file.with_suffix(".bak"))
          patched_data = jsonpatch.apply_patch(lang_data, patch_data['patchs'][_lang_file])
          json.dump(patched_data, f)
  ```
- 「非预期 JSON」（bus / 调爪 / FL / LCJE / v2 美化规则集）用 fancy 引擎**临时**应用：`launcher/changes.py:54-60` → `launcher/modfancy.py:153-159` → `:23-78`（识别）→ `:81-150`（应用到 `lang/**`，写前建 `.bak`）
- 回滚：`launcher/changes.py:62-68`（`cleanup_patch` 把 `lang/**/*.bak` 还原为 `.json`）
- 语义边界：`launcher/modfancy.py:9-11` 说明这些改动「只在本次启动会话内生效」；而 `.bak` 机制**同时被汉化包安装复用**（见 2.6.3 风险 R6）。

### 2.6 汉化 / 翻译包管理（与模组的关系）

#### 2.6.1 目录与开关：**不共用**

| 维度 | 汉化包 | 模组 |
|---|---|---|
| 安装位置 | 游戏目录 `LimbusCompany_Data\lang\<包名>` | 用户目录 `%APPDATA%\Roaming\LimbusCompanyMods` |
| 禁用态 | 整个 `lang` 目录改名 `_lang` | 单文件/单目录后缀 `_disable` |
| 开关粒度 | **全局**（一个目录改名 → 所有包一起失效） | **逐模组** |
| 当前选中 | `lang\config.json` 的 `lang` 字段 | 无（文件名即状态） |
| 代码 | `webutils/packages/{install,manage,clean}.py` | `webutils/packages/manage.py` + `launcher/*` |

证据：
- 汉化包路径与禁用态：`webutils/packages/manage.py:37-50`
  ```python
  lang_path = Path(game_path)/'LimbusCompany_Data'/'lang'
  ...
  return Path(game_path)/'LimbusCompany_Data'/'_lang'
  ```
- 全局开关（目录移动）：`webutils/packages/manage.py:110-129`
  ```python
  if enable: shutil.move(disable_path, lang_path)   # 先把已存在的 lang rmtree 掉再移
  else:      shutil.move(lang_path, disable_path)
  ```
  桥接 `webui/app_api/packages.py:120-127`；UI 开关 `webui/js/modals.js:165`。
- 安装到「当前启用目录」而非重建 `lang`：`webutils/packages/install.py:228-234`
  ```python
  game_path = str(get_active_lang_path(game_path))     # 禁用态装进 _lang
  ```
- 切换选中包（改 `config.json.lang`）：`webutils/packages/manage.py:72-88`；删除正在用的包被拒：`manage.py:104-107`
- 汉化包识别（要求同时含 `BattleAnnouncerDlg` + `Font`）：`webutils/packages/install.py:19-48`；拖放侧结构判定 `webutils/drop/handlers/translation.py:18-34,77-97`

#### 2.6.2 翻译产物与汉化包的关系

- `webutils/function_translate.py` 是 `translateFunc.TranslationPipeline` 的薄封装：`:45-167`
- 产物目录固定为 `LLc-CN-LCTA`，打包成 `LCTA_<version>.zip`（`:139-148`），版本号 `YYYYMMDDNN` 同日递增（`:170-195`）
- 注入字体/许可证/版本元数据：`:198-223`
- **产物即一个标准汉化包**（目录内含 `BattleAnnouncerDlg`、`Font` 等），因此走的是汉化包安装路径（`webutils/packages/install.py`），**与模组完全无关**。
- `translateFunc/*`（`pipeline.py`、`processor.py`、`workers.py`、`builder/*`、`matcher/*`、`proper/*`）只服务翻译，不读写模组目录：grep `mod_path|LimbusCompanyMods` 在 `translateFunc/` 零命中。

#### 2.6.3 两者的真实交集：**游戏 `lang/` 目录 + `.bak` 约定**（这是风险点）

- 模组文本补丁写 `lang/*.json` 并留 `.bak`（`launcher/changes.py:42-43`）
- 模组美化写 `lang/**/*.json` 并留 `.bak`（`launcher/modfancy.py:125-127`）
- 汉化包安装**整目录替换** `lang/<包名>`（`webutils/packages/install.py:259-271` 先 `rmtree` 旧包）
- 切换/删除包时也可能 `rmtree(lang_path)`（`webutils/packages/manage.py:122-123`）
- `cleanup_patch` 会把 `lang/**/*.bak` 无条件还原（`launcher/changes.py:65-68`）

→ 结论：**模组的文本通道寄生在汉化包的目录结构上**，两者没有隔离层，也没有「谁拥有该文件」的记录（详见 5.4 R6）。

---

## 3. 数据与目录布局

### 3.1 目录一览

| 用途 | 路径 | 可配置键 | 证据 |
|---|---|---|---|
| **模组受管目录**（用户自己的） | `%APPDATA%\Roaming\LimbusCompanyMods` | `ui_default.manage.mod_path` | `packages/manage.py:131-140`；`launcher/modfolder.py:5-11` |
| 镜像站下载 staging | `%LOCALAPPDATA%\LCTA\mod-mirror\<id>_standard\` | 无 | `function_mod_mirror.py:56-60,425` |
| 普通文件下载 | 系统「下载」目录（`SHGetKnownFolderPath`） | 无 | `function_mod_mirror.py:428`；`utils/shell.py:87-101` |
| 统一模组缓存根 | `%LOCALAPPDATA%\LCTA\mod-cache\` | 无 | `launcher/modcache.py:19-23` |
| ├ carra2 转换产物 | `mod-cache/carra2-convert/<zip_sha256>.carra2` | 无 | `launcher/modcache.py:26-29`；`launcher/patch.py:108-119` |
| ├ carra2 解压展平 | `mod-cache/carra2-extract/<carra2_sha256>/` | 无 | `launcher/modcache.py:32-35`；`launcher/patch.py:180-198` |
| ├ bundle 重打包 | `mod-cache/bundle-patch/<digest>/__data` + `meta.json` | 无 | `launcher/modcache.py:38-41`；`launcher/patch.py:376-400` |
| └ rebank 补丁/导出 | `mod-cache/bank/<key>.bank` + `.json`（launcher 与 WebUI **共用**） | 无 | `launcher/modcache.py:44-47`；`webutils/bank/rebank.py:35-40` |
| FMOD 工具 DLL | `%LOCALAPPDATA%\LCTA\fmod-dlls\` | `ui_default.bank.dll_dir` | `webutils/bank/dlls.py:133-151` |
| staticmod 备份 | `%LOCALAPPDATA%\LCTA\staticmod-backup\<outer>\<inner>\` | 无 | `launcher/staticmod.py:497-500` |
| 每次启动的临时资源根 | `%TEMP%\tmpXXXX`（`tempfile.mkdtemp`） | 无 | `launcher/game_launch.py:118,131` |
| 游戏 Unity 缓存（被打补丁处） | `%APPDATA%\..\LocalLow\Unity\ProjectMoon_LimbusCompany\*\*\__data` | 无 | `launcher/patch.py:36-38` |
| 游戏音频目录（被覆盖处） | `<game>\LimbusCompany_Data\StreamingAssets\Assets\Sound\FMODBuilds\Desktop` | 无 | `launcher/sound.py:67-68`；`function_bank.py:29-31` |
| 游戏语言目录（被 jsonpatch 处） | `<game>\LimbusCompany_Data\lang`（禁用态 `_lang`） | 无 | `launcher/changes.py:28`；`packages/manage.py:37-50` |
| **汉化包目录**（与模组无关） | 同上 `lang` | `ui_default.install.package_directory`（源包目录） | `packages/install.py:19-48`；`webui/app_api/packages.py:46-49` |

### 3.2 模组目录内部形态

```
%APPDATA%\Roaming\LimbusCompanyMods\
├── MyMod\                      ← 镜像站标准版/拖放 zip 的目录形态（目录名 = 清洗后 name）
│   ├── <任意包内结构>
│   └── ...
├── coolmod_disable\            ← 禁用态目录（整目录内的文件全部不加载）
├── texture.carra2              ← 贴图模组（单文件）
├── texture.carra2_disable      ← 禁用态单文件
├── sound.bank / sound.bank_disable
├── patch.rebank / patch.rebank_disable
├── lang_patch.json / lang_patch.json_disable
├── static.staticmod / static.staticmod_disable
└── mymod.zip                   ← 未转换的包（启动期会被转成 .carra2 或解压后删除）
```

- 枚举逻辑（注意 `removesuffix` 的正确性）：`webutils/packages/manage.py:142-163`
- 无 `mod.json`、无 `.lcta-*` 元数据目录、无安装清单（见 2.2.3）。

### 3.3 与订阅工具的目录对照

| 订阅工具（toolbox） | 模组 |
|---|---|
| `<game>\.lcta-toolbox\`（manifest/journal/backups/staging/lock） | 无（散落在用户 Roaming 目录） |
| `<game>\BepInEx\plugins\LCTA\<tool_id>\`（启用态） | 无（不进 BepInEx） |
| `<game>\.lcta-toolbox\disabled\<tool_id>\<release_id>\`（停用态） | `<mods>\<name>_disable` |
| 证据：`webutils/toolbox/paths.py:42-51,230-253` | 证据：`packages/manage.py:165-174` |

---

## 4. 与订阅工具机制的差异

| 维度 | 订阅工具（toolbox） | 模组管理 | 证据 |
|---|---|---|---|
| **信任根** | 服务端 Ed25519 签名清单，无签名即拒装 | **无签名**，信任内嵌网页传入的 `payload` | `webui/app_api/toolbox.py:1315-1331` vs `function_mod_mirror.py:410-432` |
| **完整性校验** | 清单逐文件 `sha256` + 大小，**缓存命中也重算** | `size`/`sha256` **可选**，缺省整段跳过；缓存复用也只在有 sha 时 | `webutils/toolbox/download.py:170-185,194-222` vs `function_mod_mirror.py:122-130,438-446` |
| **下载地址来源** | 服务端签发票据 `download_url`，只接受 https 无凭据 | 客户端**自己拼** `<base_url>/api/mods/...` | `toolbox/download.py:63-77`；`toolbox/api.py` 票据 vs `function_mod_mirror.py:426,430` |
| **落盘事务** | journal：先备份→登记→提交，失败/崩溃整体回滚；启动时 `recover_if_needed` | **无**。先 `rmtree` 旧目录再解压 | `webutils/toolbox/state.py:350-510`；`install.py:319-381` vs `function_mod_mirror.py:386-394` |
| **受管区断言** | `assert_managed_target` / `resolve_within` / `assert_not_link`，逐路径核验 | 只有 `safe_join_path`（防 `..`/盘符）+ 解压成员名净化，**无受管区概念** | `toolbox/paths.py:166-201,355-381` vs `packages/manage.py:18-35`；`function_mod_mirror.py:100-155` |
| **启停语义** | 停用 = **移出 BepInEx 加载树**（文件位置即状态） | 停用 = **文件名加 `_disable`**（同样文件位置即状态） | `toolbox/paths.py:235-240`；`install.py:12` vs `packages/manage.py:165-174` |
| **更新语义** | 有 `version`/`version_sort`、依赖声明、`release_id`；更新保持原启停状态 | **无版本、无更新、无依赖** | `toolbox/state.py:130-176`；`install.py:314-320` vs 第 6 节 |
| **冲突检测** | GUID 冲突、底座外来安装检测、包目录重叠检测 | **无**（仅音频 `.bank` vs `.rebank` 的优先级跳过） | `toolbox/state.py:333-342`；`install.py:107-140,589-601` vs `launcher/bankmod.py:120-123` |
| **游戏运行保护** | `runtime.assert_can_install` + 文件锁，游戏运行即拒装 | **无**（安装可在游戏运行时进行；启动期写入才有顺序保证） | `toolbox/runtime.py:221-243`；`install.py:192-200` vs 全链路无命中 |
| **解压防护** | 成员数/总大小/单文件/压缩比上限 + 大小写冲突 + 链接检查 + 布局白名单 | 仅成员名净化 + `testzip` CRC + 落点前缀检查，**无炸弹上限、无大小写冲突检测** | `toolbox/archive.py:26-31,65-133,136-149` vs `function_mod_mirror.py:133-155` |
| **卸载** | 只删 manifest 记载且哈希仍匹配的文件，`keep_config` 默认保留用户配置 | 整个目录 `rmtree`，**不保留任何数据** | `toolbox/install.py:925-989`；`state.py:145,175` vs `packages/manage.py:176-188` |
| **凭据存放** | manifest **刻意不含凭据** | 镜像站 `access_token`/`refresh_token` **明文存 `config.json`** | `toolbox/state.py:258-263` vs `function_mod_mirror.py:78-82` |

**一句话对比**：模组管理是「**用户自己放/装 + 启动期临时补丁 + 文件名即状态**」的开放模型；订阅工具是「**签名清单驱动的受管安装 + 事务 journal + 受管区断言**」的封闭模型。两者**互不共享代码路径、互不共享目录、互不共享信任根**（唯一交集是 `lang/` 目录与 `.bak` 约定，见 2.6.3）。

---

## 5. 安全边界与风险（按严重度排序）

> 严重度：**B**=blocker（可致数据丢失/任意写入）｜**H**=high｜**M**=medium｜**L**=low

### 5.1 高危：覆盖安装「先删后解压」，无备份无回滚

- **B-1｜覆盖安装是不可逆的破坏窗口** — `webutils/function_mod_mirror.py:386-394`
  ```python
  for old in (disable, target):        # ← 旧版本在此已被删除
      if old.exists():
          if old.is_dir(): shutil.rmtree(old)
          else: old.unlink()
  _log_manager.update_modal_progress(92, "解压安装到模组目录...", modal_id)
  _extract_zip_safe(zip_path, target, modal_id)   # ← 这一步失败/取消，旧模组已没了
  ```
  失败路径：`_extract_zip_safe` 抛错（zip 损坏/路径穿越成员/`testzip` 失败/用户取消 `check_running` → `CancelRunning`，`:145`）→ 上层 `:477-481` 只记日志返回失败，**旧模组永久丢失**。
  同缺陷在拖放路径也存在（先 `remove_existing` 再解压）：`webutils/drop/handlers/archive_mod.py:48-50`；`webutils/drop/handler.py:15-21`。
  对照：订阅工具同一动作是「解压到 staging → 校验 → 备份 → journal 登记 → 提交」，失败整体回滚（`webutils/toolbox/install.py:296-381`）。

- **B-2｜模组无签名、无来源绑定，镜像站或内嵌页面被攻破即任意文件落盘** — `function_mod_mirror.py:410-432`
  ```python
  payload = payload or {}
  target_type = str(payload.get("target_type") or "nexus")
  target_id  = str(payload.get("target_id") or "").strip()
  ...
  name = _safe_filename(payload.get("name") or fallback_name, fallback_name)
  expected_sha = str(payload.get("sha256") or "")     # ← 期望哈希由网页给出
  ```
  攻击链：内嵌网页被 XSS / 镜像站被接管 → 网页给出 `kind=standard` + 自己控制的 `name`（决定落盘目录名）+ 空的 `sha256`（跳过校验）→ 客户端下载并解压攻击者 zip 到 `<mods>/<任意名>/`。
  危害边界：受 `_safe_filename`（`:92-97`）与 `_sanitize_member`（`:100-111`）限制，**不能穿越到模组目录之外**；但**模组目录内可写任意结构**，且该目录随后被 Launcher 当作可信输入解析（见 5.2 H-1、5.1 B-3）。

- **B-3｜`lang` 文本补丁路径未净化 → 可从模组包写到 `lang` 之外** — `launcher/changes.py:37-52`
  ```python
  for _lang_file in patch_data.get('patchs', {}):
      lang_file = lang_path / _lang_file        # ← _lang_file 直接来自模组 JSON，未净化
      if not lang_file.exists(): continue       # ← 存在即写；不存在就跳过
      ...
      with open(lang_file, "w") as f: json.dump(patched_data, f)
  ```
  `_lang_file` 若为 `../../../somedir/file.json`，`Path` 拼接后 `exists()` 为真就**直接覆写游戏目录内该文件**（且 `.bak` 建在越界目标旁，`cleanup_patch` 会把它当语言文件还原）。虽然需要目标文件已存在且是合法 JSON，但可覆写游戏目录内任意 `.json`（含 `config.json`、其它语言包文件）。
  同一链路还有 `launcher/modfancy.py:81-150`（遍历 `lang/**` 内的文件，路径来自 `rglob`，相对安全）与 `launcher/staticmod.py`（路径来自 `manifest.json` 的 `source`，用 `z.open(src)` 读包内，写入侧受 catalog 定位约束）。
  **注意**：这是 `launcher/`（GPL 隔离的模组加载器）内的代码，**没有**订阅工具那套 `resolve_within` / `sanitize_member_name`。

### 5.2 高危：Launcher 侧消费不可信模组内容

- **H-1｜`patch.py` 用 `extractall` 解压模组到模组目录根，无成员名校验** — `launcher/patch.py:99-106`
  ```python
  if not is_lunartique_zip(str(mod_zip)):
      with ZipFile(mod_zip) as z:
          z.extractall(mod_zips_root)      # ← 无成员名净化
      os.remove(mod_zip)
  ```
  缓解事实：CPython `zipfile._extract_member` 会 `os.path.splitdrive` 并**丢弃 `..` 与 `.` 段**（实测 3.11.9 源码：`invalid_path_parts = ('', os.path.curdir, os.path.pardir)`），因此经典 Zip Slip 在此**不成立**。但：
  - 绝对路径被「相对化」而非拒绝 → 静默落到 mod 目录内（用户可见性差）
  - 无大小写冲突检测、无 zip 炸弹上限（成员数/总大小/压缩比均无限制）→ 可写满磁盘（`launcher/patch.py:103-104`）
  - 同一路径多成员时**后者静默覆盖前者**（无哈希校验，无提示）

- **H-2｜`.staticmod` 与 `.rebank` 的 manifest 字段被信任到「影响写入位置」** — `launcher/bankmod.py:102-110`（已修，好例子）
  ```python
  base = _base_bank_of(rp) or (os.path.basename(rp)[:-len(_REBANK_EXT)] + ".bank")
  # base_bank 来自 zip 内 rebank.json（潜在恶意），只允许纯文件名
  if not base or os.path.basename(base) != base or "/" in base or "\\" in base:
      ...跳过
  ```
  对比：`.staticmod` 的 `source` 字段只用于 `z.open(src)`（包内读，`launcher/staticmod.py:620-632`），不拼外部路径，风险较低；但 `manifest.json` 的 `patches[].file` / `dataClass` 决定改哪个 TextAsset，属于**语义级信任**（改错数据只影响游戏，不影响文件系统）。

- **H-3｜`config.json` 明文保存镜像站 access/refresh token** — `webutils/function_mod_mirror.py:78-82`
  ```python
  def mod_mirror_save_auth(data):
      if not data: ConfigManager().set(AUTH_KEY, "")
      else: ConfigManager().set(AUTH_KEY, json.dumps(data, ensure_ascii=False))
  ```
  `ConfigManager.save()` 直接 `json.dump(self._data, f)` 到 `config.json`（`globalManagers/ConfigManager.py:159-165`），无加密、无 ACL 收紧。实测本地 `config.json:100-102` 即含完整 JWT（access + refresh + user 信息）。
  对照：订阅工具明确「manifest 刻意不含任何凭据」（`webutils/toolbox/state.py:258-263`）。
  影响：`config.json` 被 `.gitignore` 忽略（`.gitignore:21` `*config.json`）是正确的，但**任何读该文件的本地进程/备份/截图泄露都会带走 refresh token**。

- **H-4｜`source: "lcta-mod-mirror"` 只是字符串常量，不构成来源认证** — `webui/mod_mirror_api.py:64-66`
  ```python
  if not isinstance(msg, dict) or msg.get("source") != "lcta-mod-mirror":
      return {"ok": False, "message": "无效的请求来源"}
  ```
  任何能在该窗口执行 JS 的代码（网页自身、注入脚本、XSS）都能通过此检查。对比订阅工具桥对**订阅安装**做了严格白名单化（只接受 `tool_id`/`release_id` 且 `release_id` 走字符白名单，`webui/mod_mirror_api.py:110-144`，并有测试 `tests/test_mod_mirror.py:687-725` 断言「网页传来的 `target_path` 不得进入转发载荷」）。
  → **同一个桥文件里，订阅工具路径做了载荷白名单，模组路径没有**：`modMirrorRequest` 直接转发整个 `payload`。

### 5.3 中危：路径净化覆盖不全

- **M-1｜`safe_join_path` 只覆盖「用户输入的模组名」，不覆盖「包内成员名」** — `webutils/packages/manage.py:18-35`
  ```python
  if os.path.isabs(name) or ':' in name: raise ValueError(...)
  if '..' in Path(name).parts: raise ValueError(...)
  base = Path(base_path).resolve(); target = (base / name).resolve()
  if target == base or base not in target.parents: raise ValueError(...)
  ```
  这条断言正确用于 `toggle_mod` / `delete_mod`（`manage.py:168,179`）与汉化包删除（`manage.py:96`）。但**拖放安装的成员名净化是另一份实现**（`webutils/packages/clean.py:16-27` `_sanitize_zip_member_name`），而**镜像站安装又自己复制了一份**（`function_mod_mirror.py:100-111` `_sanitize_member`）——三份实现规则一致但**不共享代码**，任何一份漂移都无人察觉。
  对比：订阅工具只有一份 `paths.sanitize_member_name`（覆盖 ADS/UNC/保留设备名/尾点空格/大小写冲突，`webutils/toolbox/paths.py:86-154`），且被 `archive.py` 与 `paths.resolve_within` 复用。

- **M-2｜镜像站解压的落点检查用字符串前缀，存在同前缀兄弟目录绕过** — `function_mod_mirror.py:143-149`
  ```python
  dest_resolved = dest_dir.resolve()
  for info in z.infolist():
      name = _sanitize_member(info.filename)
      target = (dest_dir / name).resolve()
      if not str(target).startswith(str(dest_resolved)):     # ← 字符串前缀比较
          raise ValueError(...)
  ```
  这正是订阅工具文档里点名的错误做法：`webutils/toolbox/paths.py:8-12`「这是常见但**错误**的包含判断：`C:\Games\LCTA-evil` 也以 `C:\Games\LCTA` 开头。必须按路径分量比较（`relative_to` / `commonpath`）」。
  缓解：`_sanitize_member` 已拒绝 `..`/绝对路径/盘符，所以**实际可利用性很低**（需要成员名本身就能逃出，已被拦）。但这是**纵深防御的第二道门失效**，与订阅工具形成鲜明对比。

- **M-3｜`extract_zip_smartly` 完全无成员名校验（被拖放安装使用）** — `webutils/utils/io.py:65-99`
  ```python
  with zipfile.ZipFile(zip_path, 'r') as zip_ref:
      ...
      if len(root_items) == 1: zip_ref.extractall(target_dir)
      else: ... zip_ref.extractall(extract_dir)
  ```
  依赖 CPython 内置 `_extract_member` 的 `..` 过滤（见 5.2 H-1 缓解事实）。调用点：`webutils/drop/handlers/archive_mod.py:50`（模组）、`webutils/packages/install.py:277`（汉化包）、`webutils/packages/install.py:196`（改字体）、`webutils/function_LCTA_auto.py:61`。
  注意：`archive_mod.py:29` 在**预删除前**调了 `_sanitize_zip_member_name`（`_zip_extract_root` 内），所以恶意成员会在预删除阶段被拒；但 `extract_zip_smartly` 本身无防护。

- **M-4｜`clean_mods` 硬编码默认模组路径，忽略用户配置** — `webui/app_api/packages.py:339-342`
  ```python
  mods_path = roaming_path / "LimbusCompanyMods"     # ← 未读 ui_default.manage.mod_path
  ```
  用户若把模组目录改到 D 盘，勾选「清理模组」会**删错对象**：删的是默认路径（可能已废弃/仍存在旧文件），而真正的模组目录未被清理；反之若默认路径存在而用户以为已迁走，会**删掉预期外的数据**。同类硬编码还在 `launcher/modfolder.py:8`（但那里有 `os.path.exists` 兜底，风险低）。

- **M-5｜`clear_by_mod` 从 zip 内容推断要删的缓存目录名** — `webutils/packages/clean.py:115-177`
  ```python
  if 'Installation/' in dir_path: path_del = Path(dir_path).name
  elif dir_path.endswith('/'):    path_del = dir_path.rstrip('/')
  else:                           path_del = Path(dir_path).parts[0] ...
  target_path = safe_join_path(unity_dir, path_del)      # ← 已限制在 unity_dir 内（好）
  if target_path.is_dir(): rmtree(target_path)
  ```
  有 `safe_join_path` 兜底（`:155`，异常时 `:156-158` 记日志并跳过），风险受控；但「用不可信 zip 的目录名决定删除目标」这一模式本身很危险，且**删除的是 Unity 缓存目录（游戏资源缓存）**，删错会导致游戏资源重新下载或异常。

### 5.4 中危：汉化包与模组共用 `lang/` + `.bak` 约定

- **R6｜`.bak` 是全局共享的单一槽位，模组与汉化包互相踩踏** — `launcher/changes.py:42-43,62-68`
  ```python
  if not lang_file.with_suffix(".bak").exists():
      shutil.copyfile(lang_file, lang_file.with_suffix(".bak"))   # 首次才备份
  ...
  def cleanup_patch(_path):
      for lang_file in lang_path.rglob("*.bak"):
          os.replace(lang_file, original_file)                    # 无条件还原
  ```
  冲突场景：汉化包更新写入了新的 `lang/*.json`（无 `.bak`），模组首次启动创建 `.bak`（备份的是**汉化包新版**），游戏退出还原 → 正常。但若**汉化包在模组 `.bak` 存在期间被切换/重装**（`webutils/packages/install.py:259-271` `rmtree` 旧包 + 解压新包），`.bak` 可能指向**旧包内容**，`cleanup_patch` 会把旧内容写回新包 → 汉化包与模组补丁混合、语言文件损坏。
  同类风险在 `launcher/modfancy.py:125-127`（同一 `.bak` 槽位）。
  无任何「谁拥有该文件/该 .bak」的记录 → 无法判定归属，只能靠「先备份者赢」。

- **R7｜汉化包全局开关与模组逐项开关语义不一致，用户易误判** — `webutils/packages/manage.py:110-129` vs `:165-174`
  关掉「客制化翻译」会把**整个 `lang` 目录**移走（所有汉化包一起失效），但模组列表里的开关仍是逐项 `_disable`。UI 上二者并列在「已安装数据管理」页（`webui/sections/manage.html:57-95`、`webui/guide/manage.md:5-12`），语义差异无提示。

### 5.5 低危 / 需注意

- **L-1｜staging 无 GC** — `function_mod_mirror.py:56-60`：每个 `target_id` 一个子目录，永久累积；仅 `launcher/modcache.py:79-98`（`prune_lru` 30 条）与 `webutils/bank/rebank.py:78-88`（20 条）对**缓存**做 LRU，staging 不在其列。
- **L-2｜`mod_mirror_set_base_url` 只校验 scheme，不校验域名** — `webui/app_api/mod_mirror.py:70-80`：任何 `http(s)://` 都被接受（含 `http://` 明文、含内网地址）。属于用户主动配置，但**无「已知可信站点」白名单**，配合 B-2 意味着换一个 base_url 就能让客户端从任意源装模组。
- **L-3｜`_resolve_direct_url` 对任意 3xx 都跟随** — `function_mod_mirror.py:311-326`：`requests.compat.urljoin` 后直接交给 aria2c，**不校验目标 scheme/host**（例如 `Location: file://` 或跳到内网）。实际危害低（服务端可控），但同样**没有订阅工具的 `_is_safe_download_url`（只允许 https、拒凭据，`webutils/toolbox/download.py:63-77`）**。
- **L-4｜外部命令与原生库调用面** — 模组链路本身**不 `subprocess` 执行外部程序**；但相邻链路有：
  - `7z` 解压（`webutils/utils/io.py:210-218` `subprocess.run([exe,'x',file,f'-o{out}','-y'], timeout=300)`），并在缺失时**自动从官网下载 `7zr.exe`**（`io.py:139-163`，只校验 `MZ` 头与 500KB 大小，**无签名校验**）
  - `aria2c.exe`（随包/PATH，`resource_updater/core.py:97-107`）
  - FMOD/FSBANK DLL（`ctypes.CDLL`，`webutils/bank/dlls.py:179-180`），可从 `ui_default.bank.dll_url` **任意 URL 下载**（`webutils/function_bank.py:99-104`），仅校验包内 DLL 名存在（`:57-83`），**无签名/无哈希**
  - `explorer`（打开目录，`packages/manage.py:190-193,212-217`，用列表参数避免命令拼接，安全）
  - **信任模型**：所有外部程序都假设「随包/来自官方/用户自选」，无签名验证。

### 5.6 风险汇总（一表）

| ID | 级别 | 问题 | 证据 |
|---|---|---|---|
| B-1 | blocker | 覆盖安装先删后解压，失败即丢旧模组 | `function_mod_mirror.py:386-394`；`drop/handlers/archive_mod.py:48-50` |
| B-2 | blocker | 模组无签名；`name`/`sha256` 全由内嵌网页决定 | `function_mod_mirror.py:410-432`；`mod_mirror_api.py:64-66` |
| B-3 | blocker | `lang` 补丁路径未净化，可越界覆写游戏目录 JSON | `launcher/changes.py:37-52` |
| H-1 | high | `extractall` 无成员校验 + 无炸弹上限 | `launcher/patch.py:99-106` |
| H-2 | high | 包内 `rebank.json` 的 `base_bank` 曾可逃出音频目录（现已 basename 校验，属「修过的教训」） | `launcher/bankmod.py:102-110` |
| H-3 | high | 镜像站 token 明文进 `config.json` | `function_mod_mirror.py:78-82`；`ConfigManager.py:159-165` |
| H-4 | high | 桥只校验字符串 `source`；模组载荷无白名单（订阅工具有） | `mod_mirror_api.py:61-68` vs `:110-144` |
| M-1 | medium | 成员名净化三份重复实现 | `function_mod_mirror.py:100-111`；`clean.py:16-27`；`toolbox/paths.py:86-154` |
| M-2 | medium | 落点检查用字符串前缀（文档点名的错误做法） | `function_mod_mirror.py:143-149`；`toolbox/paths.py:8-12` |
| M-3 | medium | `extract_zip_smartly` 无成员校验 | `webutils/utils/io.py:65-99` |
| M-4 | medium | `clean_mods` 硬编码默认路径 | `webui/app_api/packages.py:339-342` |
| M-5 | medium | 用 zip 内容推断删除目标 | `webutils/packages/clean.py:115-177` |
| R6 | medium | `.bak` 单槽位共享，汉化包/模组互相踩踏 | `launcher/changes.py:42-43,62-68`；`launcher/modfancy.py:125-127` |
| L-1..L-4 | low | staging 无 GC / base_url 无白名单 / 3xx 不校验 / 外部工具无签名 | 见 5.5 |

---

## 6. 能力缺口清单（不存在 / 未接线）

### 6.1 确实不存在（搜索关键词 + 结论）

| 能力 | 结论 | 搜过的关键词 / 检索范围 |
|---|---|---|
| 模组版本号 / 更新检查 | **不存在** | `mod_update｜update_mod｜check_mod｜installed_version｜has_update` 全仓库 py/js；模组链路零命中 |
| 批量更新 | **不存在** | `webui/sections/manage.html:73-95` 只有刷新/打开/删除；无批量方法 |
| `mod.json` / 安装元数据 | **不存在** | `mod.json｜mod_manifest｜mods.json｜installed.json`；仅命中 staticmod `manifest.json` 与 rebank `rebank.json` |
| 缩略图 / 封面 / 预览图 | **不存在** | `cover｜thumb｜preview｜avatar`；模组链路零命中 |
| 模组间冲突检测 | **不存在** | `conflict｜冲突`；模组链路零命中（仅音频 `.bank` vs `.rebank` 优先级跳过，`bankmod.py:120-123`） |
| 下载限速 | **不存在** | `max-overall｜download_limit｜speed_limit｜限速`；`change_global_option` 有封装但无调用（`function_aria2_downloader.py:232-233`） |
| 断点续传（模组实际行为） | **主动放弃** | `function_mod_mirror.py:449-454`（下载前删 `.aria2` 与目标文件） |
| 安装回滚 / journal | **不存在** | 模组链路无 journal/backup；对照 `webutils/toolbox/state.py:350-510` |
| 游戏运行检测（安装前） | **不存在** | `assert_can_install` 仅出现在 `webutils/toolbox/install.py`；模组链路零命中 |
| zip 炸弹上限（成员数/总大小/压缩比） | **不存在** | `MAX_MEMBERS｜MAX_TOTAL_UNCOMPRESSED｜MAX_COMPRESSION_RATIO` 仅在 `toolbox/archive.py:26-31` |
| 大小写冲突检测 | **不存在**（模组链路） | `check_case_collisions` 仅在 `toolbox/paths.py:141-154` |
| 模组依赖声明 / 依赖门禁 | **不存在** | `dependencies｜requires_runtime` 仅 `toolbox/*` |
| 模组启用/停用的持久化审计 | **不存在**（状态即文件名） | `packages/manage.py:165-174`；无配置文件写入 |
| `BepInEx` 插件式安装 | **不存在**（明确移交订阅工具） | `launcher/game_launch.py:254-261`；`toolbox/install.py:9-15` |
| 模组签名 / 哈希清单 | **不存在** | `ed25519｜signature｜verify_manifest` 仅 `toolbox/*` 与 `webui/app_api/toolbox.py:1315-1331` |

### 6.2 有代码但没接线 / 入口隐藏

| 项 | 状态 | 证据 |
|---|---|---|
| `webui/nexus/*`（Nexus 去等待 + 中文化） | **有代码，仅隐藏调试页可达，未接入模组链路**；且 `cn.js`/`skip.js`/`dict.js` 未纳入 git | `webui/app_api/windows.py:15-30`；`webui/sections/test.html:10,15,20`；`webui/index.html:144`；`.gitignore:3-4` |
| `mod_mirror_status()` / `mod_mirror_set_base_url()` / `mod_mirror_open_folder()` | **后端已实现，前端无调用**（grep `webui/**/*.js|html` 只找到 `mod_mirror_request` 与 `open_mod_mirror`） | 后端 `webui/app_api/mod_mirror.py:58-90`；前端仅 `webui/js/mod-mirror.js:13,33` |
| `Aria2DlClient.change_global_option()` / `pause_all` / `purge_results` | **已实现，模组链路不调用**（只有独立「高速下载器」窗口用 `aria2_manager`，与模组链路是**两套独立 aria2c 实例**） | 定义 `function_aria2_downloader.py:211-233`；模组链路只用 `_aria2_acquire()`（`function_mod_mirror.py:173-202`） |
| 「高速下载器」窗口 | **已接线，但入口在资源更新页**（`resource-updater.js:54` 的 `ru-open-downloader`），不在模组页 | `webui/app_api/windows.py:180-223`；`webui/js/resource-updater.js:54` |
| `webui/sections/bank.html`（音频工具页） | **入口默认隐藏**（`data-hidden-default="1"`），仅调试页有按钮跳转 | `webui/index.html:148`；`webui/sections/test.html` 的 `goAndShow('bank')` |
| `ui_default.bank.dll_url`（DLL 自定义下载源） | 已实现但**默认空**（走 GitHub release） | `webutils/function_bank.py:99-114`；`config.json:96` |
| `ui_default.mod_mirror.auth` | 已接线（登录态持久化），但**明文存 token** | `function_mod_mirror.py:78-82`；`webui/mod_mirror_api.py:35-46` |
| `.staticmod` 应用 | **已接线但默认关闭**（配置 + RiskGate 双开关） | `config_default.json:120`；`webui/js/risk-gate.js:28-33` |
| 模组功能整体 | **已接线但默认关闭**（`launcher.work.mod: false`） | `config_default.json:119`；`launcher/main.py:54,323-324` |

### 6.3 未接线的能力缺口（相对订阅工具的「应该补」清单）

1. **安装事务化**：至少应「解压到 staging → 校验 → 备份旧目录 → 原子切换 → 失败回滚」。当前 `function_mod_mirror.py:386-394` 是最需要改的一处。
2. **签名或哈希锚定**：`sha256` 不应由网页决定；应来自服务端独立获取（与 `download_url` 同源但客户端独立请求），或做「镜像站清单签名」。
3. **安装清单（manifest）**：记录 `source_id`/`sha256`/`install_time`/`files`，才能支持更新检测、完整性检查、精确卸载。
4. **受管区断言下沉到 `launcher/`**：`launcher/changes.py:37-52` 与 `launcher/patch.py:99-106` 应复用 `toolbox/paths.py` 的 `resolve_within` / `sanitize_member_name`（或抽成公共模块）。
5. **zip 防护统一**：`function_mod_mirror._extract_zip_safe` 应对齐 `toolbox/archive.py`（成员数/大小/压缩比上限 + 大小写冲突）。
6. **游戏运行检测**：安装/启停前应像 `toolbox/runtime.assert_can_install` 一样拒绝在游戏运行时改模组（当前只在 Launcher 启动期有顺序保证）。
7. **凭据保管**：镜像站 token 不应与业务配置同文件明文存放。

---

## 附录 A：模组链路核心文件索引

| 文件 | 角色 |
|---|---|
| `webutils/function_mod_mirror.py` | 镜像站下载 + 校验 + 安装主流程（481 行） |
| `webutils/function_aria2_downloader.py` | aria2c JSON-RPC 封装 + 泛用下载任务管理器（671 行） |
| `webutils/utils/net.py` | requests 流式降级下载器 |
| `webutils/packages/manage.py` | 模组目录/枚举/启停/卸载 + 汉化包目录与全局开关（241 行） |
| `webutils/packages/install.py` | 汉化包安装/改字体（与模组仅共享 `lang/`） |
| `webutils/packages/clean.py` | 成员名净化 `_sanitize_zip_member_name` + 按 mod 清缓存 |
| `webutils/drop/*` | 拖放安装：detect / handlers / eval_files（含 FLmod、jsononly、carra、bank、rebank、textFile、font、update） |
| `launcher/game_launch.py` | 启动期模组管线编排（prepare_mod / cleanup） |
| `launcher/patch.py` | zip→carra2、carra2 解压展平、bundle 备份+注入+重打包 |
| `launcher/sound.py` | 整包 `.bank` 覆盖 + 退出还原 |
| `launcher/bankmod.py` | `.rebank` 差分补丁 + 哈希缓存 |
| `launcher/changes.py` | 文本 JSON jsonpatch 到 `lang/` + `.bak` 回滚 |
| `launcher/modfancy.py` | 非文本 JSON 的 fancy 规则集临时应用 |
| `launcher/staticmod.py` | `.staticmod` 静态数据补丁 + 备份还原（727 行） |
| `launcher/modcache.py` | 统一缓存根与 `enabled_mod_files`（`_disable` 过滤） |
| `webui/app_api/mod_mirror.py` | 镜像站窗口 + 下载桥 |
| `webui/mod_mirror_api.py` | 镜像站独立窗口 js_api（模组桥 + 订阅工具桥，两者安全强度不同） |
| `webui/js/mod-mirror.js` | 前端事件接收 + 进度模态窗 |
| `webui/js/list-managers.js:749-818` | 已安装模组列表 / 启停 / 删除 UI |
| `webui/nexus/*` | **不在模组链路**（Nexus 网页增强油猴脚本） |
| `tests/test_mod_mirror.py` | 模组镜像站集成测试（760 行，含 zip 安全/校验/aria2 池/取消） |

## 附录 B：证据复核提示

- 本文所有行号基于分析时的工作区快照；`launcher/` 为 GPL 隔离区，改动需遵守 `docs/architecture.md:51`。
- 复核 `M-2`（字符串前缀判断）时注意：`_sanitize_member` 已在前面拦掉逃逸成员，所以是**纵深防御失效**而非可直接利用。
- 复核 `B-3`（`lang` 路径未净化）时请确认：`_lang_file` 来自模组包内 JSON 的 `patchs` 键名，而非用户直接输入；需目标文件已存在才写。




