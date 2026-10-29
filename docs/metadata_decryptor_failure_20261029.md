# Metadata 解密器失效分析报告（2026-10-29 游戏更新）

> 记录于 2026-10-29。本文件为**本次分析的原始日志**，结论供审核后再据以修正既有文档。
> 涉及证据脚本与产物：`E:\desktop\work\LimbusDecompile\auto_offset_pipeline\probe_20261029\`

## 1. 现象

- 游戏于 **2026-10-29 11:06:12** 更新（`GameAssembly.dll` 164,242,944B；
  `global-metadata.dat` 49,539,960B；DLL SHA-256 =
  `1F31ECDBEE399784E53345C4092F3DADD86E2DA735AD930ADCAB7882D848C326`）。
- `auto_offset_watcher.py` 在 11:51 / 11:56 / 12:02 三次触发全流水线，**阶段1（metadata 解密恢复）
  每次都失败**：
  ```
  locate=PASS  extract=PASS  verify=PASS  solve=FAIL
  求解失败：无可行锚点槽位组合   （退出码 1）
  ```
- 阶段2+（Il2CppDumper / 伤害偏移 / codec 字面量）因阶段1 失败从未执行；线上偏移停更。

## 2. 复现与证据链（逐层排除）

| 阶段 | 结论 | 关键证据 |
|---|---|---|
| locate | ✅ 正确 | xorshift 命中 13 处，唯一候选 `0x180798E10`（score 167.5） |
| extract | ✅ 正确 | `header_size=996`, `header_seed=0x29A00D3CDBBAF6EC`, `table=0x1887D26D0`, 7 个节块；init 反汇编确认：(a) 首分配 `mov ecx,0x3e4`(=996)，(b) 首个 xorshift 前 `movabs rdx,0x29A0…`(=seed)，(c) 7 段 `add rdx,[rip+file_base]` 锚点各自参数可读 |
| header 解密 | ✅ 算法/密钥正确 | 表为 0..255 的置换；解出的 7 个受保护节切片→按各自 seed 解密后**内容吻合语义**：`stringLiteral`=单调 dataIndex(index)、`stringLiteralData`=可打印文本、`string`=「Assembly-CSharp…」字符串堆、其余为 binary；7 节物理位置与 10-23 版（已 PASS）逐一对应 |
| verify | ✅ 正确 | 布局 `count_size_offset` 得分 0.748，7/7 节段解密通过，text/index 节存在 |
| **solve** | ❌ **失败** | 5 个可行锚点槽位组合**全部**在某个 gap 失败 → 整链无解 |

> 重要澄清：本版 `global-metadata.dat` 的 header **明文首字段本就不是 `0xFAB11BAF` 魔数加 version**
> （解密后首 dword 是 204567，全 header 无 `0xFAB11BAF`），这与 10-23 版一致，属正常现象——
> sanity/version 只在**重建后的标准文件**里才存在，与求解无关。**解密本身没有任何问题。**

## 3. 根因

**求解器 `solve_versioned.solve()` 的 `_rec_of()` 判定缺陷。**

```python
def _rec_of(entry):                       # 只凭 size % count == 0 就推断整数记录大小
    if entry["count"] > 0 and entry["size"] > 0 and entry["size"] % entry["count"] == 0:
        return entry["size"] // entry["count"]
    return None
```

- 版本表 `versions.V39_REC` 里 `attributeData` 是**字节流 → rec=None**（`stringLiteralData`、`string` 同理）。
- 求解器先按 `_rec_of(entry)` 把候选池 `pool` 分桶到 `pool_by_rec`，再对 `rec=None` 的槽位只取
  `pool_by_rec[None]`。
- **本版（10-29）`attributeData` 恰好 `size == count == 2234324`**，于是 `_rec_of` 返回 **1**（不是 None），
  该条目被分到 `pool_by_rec[1]`。而 `attributeData` 槽位期望 rec=None → **永远选不到它**。
- `attributeData` 是尾段（gap7，紧随 `referencedAssemblies`、`assemblies`）的必需节。
  逐 gap 求解在 gap7 因 `attributeData` 无候选而返回 None → 该锚点槽位组合作废。
  5 个候选组合共用同一份「死账」，因此**全部失败**，抛 `无可行锚点槽位组合`。

**对照 10-23 版为何能过**：该版 `attributeData` `size=2231364 / count=2231362`（size≠count）→
`_rec_of` 返回 None → 正常入选。**10-29 版 count 追平 size（变为 2234324）就触发了隐藏路径。**

> 注：`fieldAndParameterDefaultValueData` 天然是 rec=1（每元素 1 字节，size==count 正常），
> 它与 `attributeData` 在 rec=1 桶里 "撞车"，但因规范序里 fieldAndParameterDefaultValueData 在
> gap5 先被正常消耗，尾段 attributeData 才"恰好"死账——这正是问题隐蔽之处。

## 4. 为什么会出现这种问题（工程层面）

1. **隐式约定未表达**：`_rec_of` 把「size 能被 count 整除」当成「有固定记录大小」，但字节流节
   （attributeData/stringLiteralData/string）在 **count == size** 时同样整除 → 误判。
   版本表已明确写了 rec=None，但求解器**没有以版本表为准**，而是现推 rec，二者产生分歧。
2. **无金样本 → 无端到端回归**：universal 管线的卖点是"无参考标准文件"，但这也意味着
   没有「真值节大小表」可对照，只能靠内容签名/单调性等弱约束。一旦某节行为跨版本变化
   （如 attributeData 的 count 语义），弱约束无法兜底。
3. **合成测试恰好绕开**：`tests/test_metadata_recovery.py` 的合成 fixture 里
   `attributeData=(13001,7)`、`stringLiteralData=(20003,100)`、`string=(200,3)`——**全是 size≠count**，
   因此单测从未覆盖"字节流 size==count"这条崩溃路径。
4. **失败过于"静默"**：`solve` 整体抛 `无可行锚点槽位组合`，不指明是"哪个槽位无候选"，排查成本高
   （本次通过复制 solve 注入 gap 失败统计才定位到 gap7 / attributeData）。
5. **多副本漂移风险**：同一 `universal/` 至少有 3 份拷贝（E 主仓库、D 便携版、FaustLauncher hook），
   版本几乎一致但无统一发布/校验，易出现"改了一处漏一处"。

## 5. 修复方案（已实施并验证）

### 5.1 代码修改 `universal/solve_versioned.py`

**(a) 新增纯函数 `_slot_candidates()`**（可按槽位期望 rec 选候选）：
```python
def _slot_candidates(er_target, pool_by_rec, byte_blobs):
    if er_target is None:
        # 字节流槽位：rec=None 条目 ∪ 被 _rec_of 误判为整数 rec 的 size==count 字节 blob
        return pool_by_rec.get(None, []) + byte_blobs
    return pool_by_rec.get(er_target, [])
```

**(b) solve() 内收集 byte_blobs**（`size==count 且 _rec_of 误判为整数` 的字节 blob）：
```python
byte_blobs = [e for e in pool
              if e["size"] > 0 and e["size"] == e["count"] and _rec_of(e) is not None]
```
并把 `dfs_entries` 里的候选选择改为 `cands = _slot_candidates(er_target, pool_by_rec, byte_blobs)`。

**(c) 尾段 `finish()` 增加物理位置校验（防御性加固）**：链尾摆放每节前校验
`|run - entry.offset| <= MAX_ADJ`，避免尺寸不符的 blob 混入后"拼满"破坏配准。

### 5.2 效果（真实 10-29 文件端到端实测）

- `solve` 成功：`anchor_slots=[0,1,2,4,5,11,21]`（与 10-23 版语义一致），`review=[]`。
- 重建标准文件 49,532,992B；`validate_standard` **6 项门全 PASS**
  （sanity/version、31 节无缝拼接、stringLiteral 单调、固定 rec 一致、受保护节结构、attributeDataRange 内容门）。
- **Il2CppDumper 实跑成功**：`Metadata Version: 39`，`CodeRegistration=0x1876FA540`，
  `MetadataRegistration=0x1885197D0`，正常产出 `dump.cs(87MB)/script.json/il2cpp.h/DummyDll`。
  （非零退出码仅是已知的 "Press any key" 控制台怪癖，watcher 的 `success_check` 已容忍。）

### 5.3 落地范围（同一 bug 三份副本已全部修复并各自验证）

- `E:\desktop\work\LCTA-Limbus-company-transfer-auto\webutils\metadata_recovery\universal\solve_versioned.py`（**watcher 实际调用**）
- `D:\Video\LCTA-Portable-Full\code\webutils\metadata_recovery\universal\solve_versioned.py`（便携副本）
- `E:\desktop\work\Mutip\FaustLauncher\functions\hook\metadata_recovery\universal\solve_versioned.py`（hook 副本）

### 5.4 回归测试

`tests/test_metadata_recovery.py` 新增 `TestByteStreamRecRegression`（3 例，秒级）：
锁定「size==count 字节 blob 被 `_rec_of` 判为整数 rec」这一诱发条件、`rec=None` 槽位仍能选中该 blob、
且整数 rec 槽位不被污染。

### 5.5 部署（恢复线上偏移）

代码已修复，只需让 watcher 重跑一次即可自动重建偏移与 codec 字面量：
```powershell
python E:\desktop\work\LimbusDecompile\auto_offset_pipeline\auto_offset_watcher.py --once --force
```

## 6. 未来防止类似问题的方案

1. **rec 判定以版本表为准，禁止现推**：`_rec_of` 改为"版本表声明为固定记录大小才返回整数 rec"；
   对 rec=None 的节，一律只按字节流处理（不再用 `size%count` 猜测）。可保留现推作为**仅用于
   对齐校验/告警**，但不作为槽位匹配依据。给 `attributeData` 增加 `dataIndex`/range 内容门做二次确认。
2. **合成 fixture 覆盖边界**：单测显式加入「字节流 size==count」「某节 range/count 追平 size」
   等退化用例（本次已加 `TestByteStreamRecRegression`）。
3. **失败可诊断**：`solve` 失败时输出每个 gap 的失败原因（哪个槽位无候选、缺哪个 rec），
   避免再出现"黑盒 `无可行锚点槽位组合`"。建议默认写入 run-report。
4. **保留金样本做端到端回归**：每次成功 run 归档「加密 metadata 的节三元组真值 + 重建 SHA」
   （脱敏、不入库大文件，仅存三元组与哈希）。下一版更新后先用它做 dry-run 对照，秒级发现回归。
5. **多副本统一**：三份 `universal/` 收敛为单一源（symlink/子模块/发布包），CI 校验三处
   `solve_versioned.py` 等算法文件哈希一致，杜绝"改一处漏一处"。
6. **watcher 自检增强**：阶段1 失败时区分"参数提取错"与"映射求解错"，并把 solve 的 gap 诊断
   摘要写入 `watcher.log` 与 `cheat_damage.json` 的 `status`，便于无人值守时快速定位。
7. **版本表扩展即测试**：`versions.py` 新增版本时，跑一次性 `--dry-run` 对旧金样本与当前样本双验。

## 附录 · 证据脚本

| 脚本 | 用途 |
|---|---|
| `probe_20261029/p1_extract.py` | 复跑 locate+extract，导出解密 header 的整数/三元组视图 |
| `probe_20261029/p2_disasm.py` | 导出 init 反汇编（核对 seed/size/表/7 段锚点） |
| `probe_20261029/p4_ks.py` / `p6_section_content.py` | 从密码学与内容两侧证明 header 解密正确（7 节语义吻合） |
| `probe_20261029/p7_solve_debug.py` / `p9_gaps.py` | 统计 rec 供需、逐 gap 容量，定位 attributeData 死账 |
| `probe_20261029/solve_dbg.py` / `p8_run_dbg.py` | 带 gap 失败诊断的 solve 副本，确认 assign5 卡在 gap7 |
| `probe_20261029/p10_subset.py` | 与 10-23 真值表对照 + 精确 subset-sum 判定 |
| `probe_20261029/p12_verify_fix.py` | 最小修复端到端验证（solve→rebuild→validate 全 PASS） |
