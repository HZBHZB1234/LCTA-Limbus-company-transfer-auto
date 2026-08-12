# Metadata 恢复

自动恢复《边狱公司》(Limbus Company) Steam 版 IL2CPP `global-metadata.dat` 的解密入口、解密参数与 31 段映射，输出可直接被修复版 Il2CppDumper 消费的正式 profile。

---

## 一、背景：为什么要恢复 metadata

《边狱公司》的 `global-metadata.dat`（游戏目录 `LimbusCompany_Data/il2cpp_data/Metadata/` 下）是**加密的**：

- 文件头是自定义格式：07-30 构建为 756 字节 / 63 个三元组，08-06 构建为 1044 字节 / 87 个三元组（每个三元组 12 字节，记录一个 section 的 offset/size/count）。
- 文件内有 7 个「受保护 section」单独加密，其余 24 个 section 明文存储。
- 解密算法：`xorshift64(13,7,17)` 伪随机流 + 256 字节替换表逐字节 XOR，每个区域使用独立 seed。

> 旧版定位方法用「首个字符串引用 → 首个调用者」推断解密入口，依赖枚举顺序，游戏更新后非常脆弱。本工具改用**证据驱动候选评分**：直接扫描 `shl r64,0Dh / shr r64,07h / shl r64,11h` 的 xorshift64(13,7,17) 指令模式，再对候选函数反编译打分（xorshift 循环数、memmove/malloc、64 位立即数、_OWORD 拷贝、全局扇出），跨版本稳定。

## 二、流水线总览（五阶段）

```
阶段 0  locate（IDA 内）    定位解密入口函数 → locate_candidates.json（含替换表 hex）
阶段 1  extract（本页）     反编译文本 → 解密参数（header_size/seed/表/7 节段）
阶段 2  verify（本页）      加密 metadata + 参数 → 布局判定 + 节段结构门 → PASS/FAIL
阶段 3  solve（本页）       + 参考标准文件 → 31 段映射 + 重建标准 v39 文件
阶段 4  apply（本页）       → 正式 profile JSON（自检重建 SHA-256）
```

阶段 0 需要 IDA Pro（本页提供一键安装定位器插件）；阶段 1~4 全部在本页离线完成，无网络依赖。

## 三、结构化流程（推荐，六步骤）

这是最省事的用法：**IDA 插件导出后，其余参数全部自动**，无需手动复制任何内容。

```
步骤 1-2  安装定位器插件（本页「步骤 1-2」卡）→ IDA 中打开 GameAssembly.dll 的 IDB
          → 按 Ctrl-Alt-Shift-M 运行 → 导出写入 <IDB目录>/locator_out/
步骤 3    本页「步骤 3」卡选择导出（locate_candidates.json 或 locator_out 目录）
          → 点「载入导出」→ 候选下拉默认 top-1（可切换 rank 1-5）
          → 替换表 hex 与反编译文本自动填充
步骤 4    输入文件：global-metadata.dat 与 GameAssembly.dll 已从游戏目录自动推导；
          仅需手动选择参考标准文件
步骤 5    反编译文本/替换表 hex 已就绪（可手改），填写可选期望 SHA-256
步骤 6    点「开始完整恢复」→ 四阶段流水线自动执行 → 查看 verdict 与产物
```

载入导出时页面会显示：定位器裁决（PASS/PASS_WITH_REVIEW/FAIL）、所选候选
（#rank 名称 + score）、替换表 hex 与反编译文本的就绪状态。若 top-1 非真值
（罕见），切换到其他候选即可，无需手动处理任何参数。

## 四、前置准备

运行流水线前请准备：

| 文件 | 必须 | 说明 |
| --- | --- | --- |
| 加密的 `global-metadata.dat` | 是 | 从游戏目录复制，保持原样不要修改 |
| 反编译文本（`.c` 文件或粘贴） | 是* | 解密入口函数的 IDA 反编译伪代码（*有已有 profile 时可跳过） |
| 参考标准文件 `global-metadata-standard-*.dat` | 阶段 3/4 | 旧版本的标准 v39 布局文件，提供 31 节权威 (offset,size,count) 与内容锚点；可到 <https://github.com/HZBHZB1234/LimbusMetadataRecovery/releases> 下载标准版本 metadata 文件 |
| `GameAssembly.dll` | 否 | 提供后可自动从反编译文本中的替换表地址读取 256 字节 |
| 期望重建 SHA-256 | 否 | 有已知真值时的自检项 |
| 已有 `candidate_profile.json` | 否 | 跳过阶段 1，直接从验证开始 |

**自动推导**：`global-metadata.dat` 与 `GameAssembly.dll` 会自动从「设置」页配置的游戏路径推导
（`<游戏目录>/LimbusCompany_Data/il2cpp_data/Metadata/global-metadata.dat` 与
`<游戏目录>/GameAssembly.dll`），进入本页时若输入框为空即自动回填，可手动覆盖；
未配置游戏路径或文件缺失时页面会给出提示。

替换表 256 字节是阶段 2 起的必需品，来源三选一：定位器 dump（在 `locate_candidates.json` 的 `table_hex` 字段）、手工粘贴、或本页提供 `GameAssembly.dll` 自动读取。

## 五、阶段 0：IDA 定位器（可选但推荐）

定位器在 IDA 内运行，扫描指令级特征 + 反编译级评分，输出 top-K 候选与替换表字节 dump。

### 4.1 一键安装插件

1. 打开本页「定位器（IDA 插件）」卡片，插件目录留空自动探测（注册表 + 常见安装路径），或手动点击「选择目录」。
2. 点击「安装定位器插件」，写入：
   - `<plugins>/metadata_locator_plugin.py`（插件入口）
   - `<plugins>/metadata_recovery_tools/`（locator + 报告框架，自包含）
3. 重启 IDA。

### 4.2 运行

- **热键**：在 IDA 中打开 `GameAssembly.dll` 的 IDB，按 `Ctrl-Alt-Shift-M`。
- **输出**：`<IDB目录>/locator_out/locate_candidates.json` + 报告 + top-5 反编译文本（`decompile_rank*.c`，直接用于本页阶段 1）。
- **MCP 方式**：在 ida-pro-mcp 中 `py_exec_file` 执行 `webutils/metadata_recovery/locator.py`，然后调用 `run_background(out_dir, top_k=20)`；也可设置环境变量 `LIMBUS_LOCATOR_OUT` 指定输出目录。

### 4.3 结果判读

`locate_candidates.json` 中按 `score` 排序的候选，Top-1 应同时具备：`xorshift_loops >= 5`、`imm64 >= 5`、拷贝类特征（memmove/table_ref/oword ≥3），且 `fanout_stats.fanout` 较大（写出的全局被广泛读取）。

参考真值（用于核对）：08-06 构建 init 函数为 `sub_18069C5E0`、替换表 RVA `0x7354910`；07-30 为 `sub_1806AB0E0`、表 `0x18759C190`。

## 六、阶段 1：参数提取（本页）

**输入**：定位器输出的 `decompile_rank1_*.c`（或 IDA 中手动全选伪代码视图复制粘贴）。

**提取内容**：

- `header_size`：首个 malloc 常量（header 拷贝缓冲）
- `header_seed`：第一个解密循环（`<< 13`）前的 64 位立即数
- `table_addr`：替换表引用 `byte_XXXX[` 的地址
- `sections`（7 个）：每个受保护节段的 `{size_off, offset_off, adj, seed}`，从拷贝调用表达式 `qword_<file> + *(_DWORD *)(qword_<hdr> + <off>) ± adj` 提取

每条提取都记录**证据行**（行号 + 原文）供复核；正则无法匹配的模式进入 `requires_review` 清单，不静默失败。

**输出**：`candidate_profile.json`（`extract-report.json/md` 含全部证据）。

> 经验值：07-30 与 08-06 均为 7 个节段、header_seed 为 12~16 位十六进制；若节段数不是 7 或 xorshift 循环数 < 5，先检查反编译文本是否完整（是否包含整个函数体）。

## 七、阶段 2：参数验证（本页）

**输入**：加密 metadata + 阶段 1 的 profile（含替换表 hex）。

**验证内容**：

1. **header 解密 + 布局自动判定**：`offset_size_count`（offset,size,count）与 `size_count_offset` 双布局打分取优，阈值 0.7。
2. **节段范围校验**：每个受保护节段的物理范围（`logical_offset + adj`）必须在文件内。
3. **结构门**：用该节 seed 解密后分类：
   - `text`：可打印率 ≥ 0.6（stringLiteralData 类）
   - `index`：u32 单调率 ≥ 0.99（stringLiteral dataIndex 类）
   - `binary`：非文本非索引（methods/fields 类，弱证据）
   错误 seed 无法通过可打印率/单调门——这是参数真实性的硬证明。

**裁决**：`PASS` / `PASS_WITH_REVIEW` / `FAIL`。全部节段解密通过且至少存在一个 text/index 节段才可能 PASS。

## 八、阶段 3：31 段映射求解（本页）

**输入**：加密 metadata + profile + 参考标准文件（必须与目标版本同一 Unity/metadata 版本族）。

**算法四相**：

1. **相 1 记录大小匹配（C1）**：参考文件的 `rec_size = size/count` 推导每节记录大小；候选节 = `entry.size % rec_size == 0 且 entry.size / rec_size == entry.count`；零尺寸节匹配零尺寸 entry。整数整除直接淘汰绝大多数诱饵三元组。
2. **相 2 内容指纹（C5）**：非加密节在磁盘上是明文——取参考文件节首多窗口 16 字节锚点在加密文件中定位物理位置（允许 ≤10% 字节漂移），`adj = 物理位置 - 逻辑offset`。受保护节内容加密、指纹必然失败，失败集合恰好用于确认 7 个受保护节。
3. **相 3 链装配（C2/C3/C4）**：非加密节按物理位置排序成骨架链；受保护节物理位置 `logical + adj` 必须恰好填充相邻骨架间隙（≤4 字节 padding）；零尺寸节 snap 到 ≥ logical 的最小链边界；全部 31 节必须 `end == next_start` 首尾相连。
4. **相 4 重建**：按标准 v39 布局重建文件，校验 sanity `0xFAB11BAF`、version、31 节连续，与期望 SHA-256 比对（可选）。

**输出**：`section-map.json`（31 节 `{custom_entry_index, physical_offset_adjustment}`）+ `standard-rebuilt.dat` + `solve-report.json/md`。

> 关键判据：`requires_review == 0` 且重建 SHA-256 精确命中（08-06 真值 `73194A637E4BEF48F5D0396158F2CFEEAC484EFF4864AE01F6CDAE603057A2E7`，43,667,903 字节）。

## 九、阶段 4：正式 profile 提升（本页）

把候选参数 + 31 段映射提升为正式 profile JSON（与旧版恢复脚本直接消费的格式一致）：

- `header`：size/seed/entry_layout
- `substitution_table_hex`：替换表 256 字节
- `protected_sections`：7 个受保护节（seed、physical_offset_adjustment、identified_as 分类）
- `standard_sections`：31 节完整映射
- `metadata_size` / `metadata_sha256`：溯源信息
- 自检：用生成的 profile 重建标准 v39 文件并比对期望 SHA-256

**输出**：`<profile_id>.generated.json` + `apply-report.json/md`。

## 十、结果判读

每阶段独立裁决，含义如下：

| 裁决 | 含义 | 下一步 |
| --- | --- | --- |
| `PASS` | 所有验证门通过，无复核项 | 继续下一阶段 |
| `PASS_WITH_REVIEW` | 门全过，但有歧义项待复核 | 查看报告「需复核项」，凭证据人工/LLM 判断后继续 |
| `FAIL` | 存在失败的门 | 按报告「验证门」逐条定位：反编译文本不完整、替换表错误、参考版本漂移、布局翻转等 |

报告（`*-report.md`）包含：验证门清单（每条含 PASS/FAIL 与证据）、需复核项、关键数据节区。所有产物保存在 `metadata_recovery/run_<时间戳>/` 目录（页面可一键打开），每次运行独立目录，便于跨构建版本对比。

## 十一、高级 / 手动模式

- **跳过提取**：已有 `candidate_profile.json`（如定位器自动产出或上次运行结果）时，在「反编译文本 / 高级参数」卡片选择该文件，流水线直接从验证开始。
- **仅验证不求解**：不填参考标准文件，流水线只执行阶段 1~2。
- **表 hex 手工提供**：从 `locator_out/locate_candidates.json` 的 `table_hex` 字段复制粘贴，无需提供 DLL。
- **CI 化**：`python -m webutils.metadata_recovery.pipeline --metadata ... --reference ... --decompile-file ... --table-hex ...` 可在命令行跑通同一流水线（配合 `--expect-sha256` 做回归门禁）。

## 十二、常见问题

**Q: 找不到 IDA 或插件不生效？**  
A: 插件目录自动探测失败时手动选择（IDA 9.x 通常在 `C:\Program Files\IDA Professional 9.3\plugins`）；安装后必须**重启 IDA**，在「Edit → Plugins」中应看到 "Locate Metadata Init"。

**Q: 步骤 3 载入导出时提示「无反编译文本」？**  
A: 该候选的 rank > 5（插件只导出前 5 名的反编译文本），或导出目录不完整。切换候选下拉到前 5 名即可；若确认导出目录完整仍缺失，手动在「步骤 5」粘贴反编译文本即可（替换表 hex 已载入）。

**Q: 载入导出后反编译文本没自动填充？**  
A: 检查「步骤 5」的反编译文本输入框是否被手动改过——自动填充只在载入导出时写入一次，手动修改不会被覆盖；重新点「载入导出」即可恢复。

**Q: 切换候选下拉后表格 hex 未变？**  
A: 切换下拉会自动重新载入（`change` 事件触发），但若表格 hex 输入框被手动修改过则保留你的值；清空后重新载入即可。

**Q: 定位器 Top-1 不是真值函数？**  
A: 检查 IDB 是否为该版本构建的完整分析（自动分析完成后再运行）；可扩大 `top_k`（MCP 方式传入）或核对 `fanout` 项；新旧构建的算法结构（封装拷贝函数 vs 节块）差异已内置处理。

**Q: 阶段 2 提示替换表长度不为 256？**  
A: 未提供替换表 hex 或 DLL 中地址错误。确认反编译文本中含 `byte_XXXX[` 引用，且 `GameAssembly.dll` 与该 IDB 是同一文件。

**Q: 提取的节段数不是 7？**  
A: 反编译文本可能不完整（只复制了部分函数体）；或该构建受保护节数量确实变化——以二进制为准，复核 `requires_review` 项。

**Q: 阶段 3 指纹定位失败集合不是 7 个？**  
A: 参考标准文件与目标版本内容漂移过大（跨 Unity/metadata 版本）。换用同一版本族的参考文件；若仍失败，检查 `solve-report.md` 的未定位节清单。

**Q: 全部节段被判为 binary？**  
A: 提取的 seeds 可能全部错误，或该版本结构差异。用已知 profile 交叉验证提取参数（07-30/08-06 夹具测试可先跑通自检）。

**Q: 阶段 4 的 SHA-256 不匹配？**  
A: 期望值填写错误（大小写不敏感，应为 64 位 hex）；或映射求解存在歧义——回看 `solve-report.md` 的需复核项。

## 十三、相关工具

- **修复版 Il2CppDumper**（配合本工具输出 profile 使用）：https://github.com/HZBHZB1234/Il2CppDumper
- **LimbusMetadataRecovery Releases**（标准版本 metadata 文件下载，作参考标准文件）：https://github.com/HZBHZB1234/LimbusMetadataRecovery/releases
- 本功能移植自开源仓库 HZBHZB1234/LimbusMetadataRecovery（证据驱动定位器、参数提取、验证闭环、31 段求解器的完整设计与回归记录见该仓库文档）。
- 参考基线：08-06 构建真值 init `sub_18069C5E0`、map `sub_180693580`；07-30 夹具覆盖两代构建的提取回归。
