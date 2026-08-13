# Metadata 恢复

自动恢复《边狱公司》(Limbus Company) Steam 版 IL2CPP `global-metadata.dat` 的解密入口、解密参数与 31 段映射，输出可直接被修复版 Il2CppDumper 消费的标准 v39 文件。**只需 GameAssembly.dll + 加密的 global-metadata.dat，无需 IDA、无需参考标准文件、无需反编译文本。**

---

## 一、背景：为什么要恢复 metadata

《边狱公司》的 `global-metadata.dat`（游戏目录 `LimbusCompany_Data/il2cpp_data/Metadata/` 下）是**加密的**：

- 文件头是自定义格式：07-30 构建为 756 字节 / 63 个三元组，08-06 为 1044 字节 / 87 个三元组，08-13 为 1236 字节 / 103 个三元组（每个三元组 12 字节，记录一个 section 的 offset/size/count）。三元组的**字段排列还会跨版本漂移**（08-06 是 offset/size/count，08-13 是 count/offset/size）。
- 文件内有 7 个「受保护 section」单独加密，其余 24 个 section 明文存储。
- 解密算法：`xorshift64(13,7,17)` 伪随机流 + 256 字节替换表逐字节 XOR，每个区域使用独立 seed。

旧版工具靠 IDA + 参考标准文件反推这些参数，游戏更新后非常脆弱。本页的流水线（v2）是**版本无关**的：直接在 `GameAssembly.dll` 的机器码上定位解密入口、按指令形态提取参数，再用文件本身的结构门验证——不依赖任何版本锚点。

## 二、流水线总览（五阶段）

```
阶段 1  locate   扫描 xorshift64(13,7,17) 指令字节模板 + 反汇编特征评分 → 解密入口候选（top-1）
阶段 2  extract  对候选函数指令级参数提取：header_size / header_seed / 替换表 / 7 个受保护节段
阶段 3  verify   header 解密 → 三元组布局自动判定（6 排列打分）→ 节段结构门 → PASS/FAIL
阶段 4  solve    31 节锚点间隙链拼装：7 受保护节作锚点 + 记录大小 + 内容签名 → 完整映射
阶段 5  rebuild  按标准 v39 布局重建文件 + 四重自验证（sanity / 无缝拼接 / stringLiteral 单调 /
                 固定记录大小一致 / 受保护节结构门）
```

全程离线执行（唯一网络依赖是首次安装 capstone 反汇编库）。

## 三、快速上手（三步）

```
步骤 1  环境检查：确认 capstone 可用（缺失时点「一键安装 capstone」）
步骤 2  输入文件：global-metadata.dat 与 GameAssembly.dll 已从游戏目录自动推导，
        确认存在后即可（可选填写期望重建 SHA-256 用于自检）
步骤 3  点「开始恢复」→ 五阶段流水线自动执行 → 查看各阶段裁决与产物
```

从「设置」页配置游戏路径后，进入本页两个输入框会自动回填：
`<游戏目录>/LimbusCompany_Data/il2cpp_data/Metadata/global-metadata.dat` 与
`<游戏目录>/GameAssembly.dll`（可手动覆盖）。

## 四、前置准备

| 文件 | 必须 | 说明 |
| --- | --- | --- |
| 加密的 `global-metadata.dat` | 是 | 从游戏目录复制，保持原样不要修改 |
| `GameAssembly.dll` | 是 | 与 metadata 同一游戏版本，定位/提取都要反汇编它 |
| 期望重建 SHA-256 | 否 | 有已知真值时填写，作为自检门 |

> 大文件提示：`GameAssembly.dll` 约 50 MB，定位阶段需要全 .text 段扫描，首次运行约十几秒到几十秒，期间可随时取消。

## 五、阶段 1：定位解密入口（自动）

不需要 IDA。流水线在 `GameAssembly.dll` 上做两件事：

1. **字节模板扫描**：搜索一步 xorshift 的 MSVC 典型展开
   `shl r64,0Dh ; xor r64,r64 ; mov r64,r64 ; shr r64,07h ; ... ; shl r64,11h`（寄存器与双编码通配）。
2. **候选评分**：对每个命中反扫函数起点，统计版本无关特征——xorshift 循环数、128 位拷贝指令（header 拷贝循环）、64 位立即数（seeds）、数据段 lea（替换表引用）、全局写入（文件基址槽）——按加权总分取 top-1。

三版真值（07-30 / 08-06 / 08-13）的 init 函数均为 `sub_18069C5E0`，top-1 稳定命中。

## 六、阶段 2：参数提取（自动）

对定位到的函数窗口反汇编，应用**指令形态规则**（无文本正则、无函数名依赖）：

- `file_base`：文件加载签名（`call → mov [rip+],rax → test rax,rax → jcc`）后的全局写入目标
- `header_size`：首个分配调用前的 `mov ecx,imm`，与 header xor 循环边界 `cmp rX,imm` 交叉验证
- `header_seed`：首个 xorshift 块前的 64 位立即数
- 替换表：函数内首个指向数据段的 `lea r,[rip+...]`，直接按地址读取 256 字节
- 7 个受保护节段：每个 `add rX,[rip+file_base]` 锚点对应一个拷贝调用，反向提取 `size_off` / `offset_off`（兼容直接与强转间接调用形态）、`adj`、`seed`

任一关键参数提取失败都会记录明确错误并终止后续阶段（不静默产出错误参数）。

## 七、阶段 3：结构验证（自动）

用提取出的参数验证参数本身是对的：

1. **header 解密 + 布局自动判定**：对 offset/size/count 的 6 种排列打分（offset 在文件内、size 非负、end 界内、count 整除），取最优——因此 08-06 的 `offset_size_count` 与 08-13 的 `count_offset_size` 都能自动适配，无需人工指定。
2. **节段解密结构门**：每个受保护节段按 `size_off`/`offset_off` 显式字段读取（二进制 memmove 语义），用其 seed 解密后分类：
   - `text`：可打印率 ≥ 0.6
   - `index`：u32 单调率 ≥ 0.99
   - `binary`：非文本非索引
   错误 seed 无法通过可打印率/单调门——这是参数真实性的硬证明。至少存在一个 text/index 节段才可能 PASS。

## 八、阶段 4：31 段映射求解（自动）

无需参考标准文件。利用模型：31 个标准节在物理空间按规范序首尾相连（padding ≤ 8 字节），逻辑序 == 物理序。

1. **锚点**：7 个受保护节（提取阶段已知 entry+adj+seed）物理位置确定，按记录大小匹配候选槽位集合（唯一 rec 直接钉死，跨版本字段序不影响——记录大小按三元组计算）。
2. **间隙拼装**：锚点之间的非保护节按规范序枚举槽位组合，用**内容签名**择优——单调列（index 类）、可打印率（text 类）、4 对齐与死空间零字节；跨间隙回溯保证全局最优。
3. **零尺寸节**（windowsRuntimeTypeNames / windowsRuntimeStrings）snap 到 ≥ logical 的最小链边界。
4. 歧义无法消解时进入 `review` 清单（求解器**永不静默产出错误映射**），此时裁决为 REVIEW。

## 九、阶段 5：标准文件重建（自动）

按标准 v39 布局重建（sanity `0xFAB11BAF` + version + 31 节三元组 + 无缝拼接，受保护节用其 seed 解密），并做**四重自验证**：

1. 输出以 `0xFAB11BAF` + version 开头
2. 三元组布局与拼接一致（每节 offset == 前节终点）
3. stringLiteral 的 dataIndex 单调不减且界内
4. 固定记录大小节 `size == count × rec` 一致
5. 受保护节解密后通过结构门

全部通过才裁决 PASS。产物 `standard-rebuilt.dat` 就是给 Il2CppDumper 使用的标准 metadata 文件。

## 十、结果判读

| 裁决 | 含义 | 下一步 |
| --- | --- | --- |
| `PASS` | 所有阶段通过，无复核项 | 产物可直接使用 |
| `REVIEW` | 求解存在歧义项（求解器不静默产出错误映射） | 打开 `run-report.json` 查看 `solve.review` 列表，凭证据人工判断 |
| `FAIL` | 某阶段存在失败 | 按页面「排查建议」定位：文件版本不匹配、文件不完整、算法变体等 |

运行报告（`run-report.json` / `run-report.md`）包含每阶段裁决、证据与全部详细数据；产物统一保存在 `metadata_recovery/run_<时间戳>/` 目录（页面可一键打开），每次运行独立目录，便于跨构建版本对比。

## 十一、高级 / CLI

同一流水线可在命令行运行（配合 `--expect-sha256` 可做回归门禁）：

```powershell
python -m webutils.metadata_recovery.pipeline `
  --metadata <global-metadata.dat> --game-dll <GameAssembly.dll> `
  [--expect-sha256 <64位hex>] [--version 39] [--out-dir <目录>]
```

## 十二、常见问题

**Q: 提示缺少 capstone？**  
A: 点「一键安装 capstone」用当前应用的解释器自动 pip 安装；也可手动 `pip install capstone` 后重启应用。安装失败时日志会显示 pip 的完整输出。

**Q: 定位阶段失败（locate FAIL）？**  
A: 常见原因：GameAssembly.dll 与 metadata 不是同一游戏版本、DLL 文件不完整、或未来算法变更（非 xorshift64(13,7,17) 时定位阶段会断言失败并大声报错）。

**Q: 提取失败（extract FAIL）？**  
A: 查看 `run-report.json` 中 `extract.errors` 的逐条原因（如未定位到 file_base 全局、节块数量异常等），多为 DLL 版本异常或文件损坏。

**Q: 验证失败（verify FAIL）？**  
A: 打开 `run-report.md` 查看哪道验证门未通过。最常见原因：metadata 与 DLL 版本不一致，导致提取参数无法通过结构门。

**Q: 求解为 REVIEW？**  
A: 节间 padding 存在非零垃圾字节时内容签名可能失效。查看 `run-report.json` 的 `solve.review` 列表，按证据人工判断；求解器不会静默产出错误映射。

**Q: 期望 SHA 比对失败？**  
A: 核对期望值来源（64 位 hex，大小写不敏感）；或映射存在歧义导致重建内容有差异——回看 solve 阶段的 review 项。

**Q: 未来游戏更新后还能用吗？**  
A: 流水线是版本无关的：布局自动判定、无参考求解、记录大小表来自版本表。若仅为同版本族的常规更新（三元组数量/布局漂移、分配调用形态变化），无需改动即可适配；若 IL2CPP 版本升级到 v40+ 或算法本体变更，需等待上游 metadata-recovery 仓库更新版本表（见「已知限制」）。

**已知限制**：
- 节间 padding 若非全零死空间，求解可能进入 REVIEW（不会产出错误结果）。
- 未来 IL2CPP v40+ 需在 `versions.py` 增加版本表；算法变更（非 xorshift64(13,7,17)）由定位阶段断言失败即报错。

## 十三、相关工具

- **修复版 Il2CppDumper**（消费本页产出的 `standard-rebuilt.dat`）：https://github.com/HZBHZB1234/Il2CppDumper
- 本功能移植自开源仓库 HZBHZB1234/LimbusMetadataRecovery 的 **universal v2 管线**（版本无关：无 IDA、无参考文件）。设计文档、回归记录与完整代码见该仓库（`universal/` 目录）。
- 回归基线（给开发者参考）：07-30 / 08-06 / 08-13 三版 init 均为 `sub_18069C5E0`
