# universal - 版本无关 metadata 解密管线（v2）

在任意游戏版本上自动完成 metadata 解密的整套流程，**不依赖参考标准文件**、
不依赖 IDA、不依赖函数名/字符串等版本锚点。

## 输入 / 输出

```
输入：GameAssembly.dll + 加密 global-metadata.dat
输出：candidate profile（JSON）+ 标准 v39 重建文件 + 分阶段报告
```

## 架构与版本无关性设计

| 阶段 | 模块 | 版本无关机制 |
|---|---|---|
| 1 定位 | `xorshift_scan` + `init_locator` | xorshift64(13,7,17) 指令字节模板扫描（`shl r64,0Dh / shr r64,07h / shl r64,11h` 三连，寄存器/编码通配）+ 反汇编特征评分；文件加载签名（call→mov [rip+],rax→test→jcc）反扫函数起点，规避函数内早期 return |
| 2 提取 | `extract_disasm` | 指令形态规则：`mov ecx,imm`→分配调用（header_size 双锚交叉）、`movabs r64,imm64`（seeds）、`lea r,[rip+data]`（替换表）、`add r,[rip+file_base]` 锚点的节块（offset_off/size_off/adj 直接读字段，兼容直接/强转间接调用与十进制/十六进制位移） |
| 3 布局 | `layouts` | 三元组 6 全排列打分自动判定（08-06 `offset_size_count`、08-13 `count_offset_size`） |
| 4 验证 | `verify_structural` | 无参考结构门：header 解密→布局→7 节解密→text/index/binary 分类 |
| 5 求解 | `solve_versioned` | 锚点间隙链拼装：7 受保护节（extractor 已知）作锚点，rec 常量表 + 规范序 + 内容签名（单调列/%4 对齐/死空间零字节）唯一确定 31 节映射与物理位置 |
| 6 重建 | `rebuild_validate` | 标准文件重建 + 四重自验证（sanity/无缝拼接/stringLiteral 单调/dataIndex 界内/rec 一致/受保护节结构门） |

版本表：`versions.py`（v39 的 31 节名 + rec 常量表，新 IL2CPP 版本只需加表）。

## 用法

```powershell
python -m universal.pipeline `
  --dll <GameAssembly.dll> --metadata <global-metadata.dat> `
  --out-dir out --name steam-2026-08-13
```

## 回归

```powershell
python universal\tests\test_locator.py   # 08-13/08-06 top1 == sub_18069C5E0
python universal\tests\test_extract.py   # 指令级参数与真值逐项一致
python universal\tests\test_verify.py    # 无参考结构验证 PASS
python universal\tests\test_solve.py     # 08-06 31 节映射+重建 SHA 精确命中；
                                         # 08-13 受保护节命名+gen1 交叉抽查+自验证
```

## 已知限制

- 节间 padding 若存在非零垃圾字节（非全零死空间），死空间签名可能失效，
  进入 requires_review（求解器永不静默产出错误参数）。
- 未来 IL2CPP 版本（v40+）需在 `versions.py` 增加版本表；
  算法本身变更（非 xorshift64(13,7,17)）由定位阶段断言失败即大声报错。
